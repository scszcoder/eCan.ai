import asyncio
import base64
import json
import os
import threading
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
import websocket

from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand, PassiveBrowserStepResult


@dataclass(frozen=True)
class AppSyncPassiveTransportConfig:
    http_endpoint: str
    ws_endpoint: str
    api_host: str
    auth_token: str
    client_id: str


def _build_auth_headers(auth_token: str) -> dict[str, str]:
    tok = (auth_token or "").strip()
    if not tok:
        return {}
    if tok.lower().startswith("bearer "):
        return {"Authorization": tok}
    if tok.count(".") >= 2:
        return {"Authorization": tok}
    return {"x-api-key": tok}


def _derive_realtime_endpoint(http_endpoint: str) -> str:
    http_endpoint = (http_endpoint or "").strip()
    if http_endpoint.startswith("https://") and "appsync-api" in http_endpoint:
        rest = http_endpoint[len("https://") :]
        rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
        return "wss://" + rest
    return http_endpoint


def _derive_api_host(http_endpoint: str, ws_endpoint: str) -> str:
    endpoint = (http_endpoint or "").strip() or (ws_endpoint or "").strip()
    parsed = urlparse(endpoint)
    host = parsed.netloc
    if "appsync-realtime-api" in host:
        host = host.replace("appsync-realtime-api", "appsync-api")
    return host


def _make_signed_ws_url(ws_url: str, *, api_host: str, auth_token: str) -> str:
    parsed = urlparse(ws_url)

    header_obj: dict[str, Any] = {
        "host": api_host,
        **_build_auth_headers(auth_token),
    }
    payload_obj: dict[str, Any] = {}

    header_b64 = base64.b64encode(json.dumps(header_obj).encode("utf-8")).decode("utf-8")
    payload_b64 = base64.b64encode(json.dumps(payload_obj).encode("utf-8")).decode("utf-8")

    query = dict(parse_qsl(parsed.query))
    query.update({
        "header": header_b64,
        "payload": payload_b64,
    })

    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )


def _publish_command_mutation() -> str:
    return """
    mutation PublishPassiveCommand($input: PassiveBrowserCommandEnvelopeInput!) {
      publishPassiveCommand(input: $input) {
        runId
        clientId
        stepId
      }
    }
    """


def _on_step_result_subscription() -> str:
    return """
    subscription OnPassiveStepResult($runId: ID!, $clientId: ID!) {
      onPassiveStepResult(runId: $runId, clientId: $clientId) {
        runId
        clientId
        stepId
        result
        dom_tree
      }
    }
    """


class AppSyncPassivePubSubTransport:
    def __init__(self, *, config: AppSyncPassiveTransportConfig) -> None:
        self._config = config

        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._started = False

        self._pending: dict[tuple[str, str], PassiveBrowserStepResult] = {}
        self._waiters: dict[tuple[str, str], asyncio.Future[PassiveBrowserStepResult]] = {}
        self._lock = threading.Lock()

        self._subscription_id = "PassiveStepResult1"
        self._subscribed_run_id: str | None = None

    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        payload = {
            "runId": cmd.run_id,
            "clientId": self._config.client_id,
            "stepId": cmd.step_id,
            "command": cmd.model_dump(),
        }

        auth_headers = _build_auth_headers(self._config.auth_token)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._config.http_endpoint,
                json={"query": _publish_command_mutation(), "variables": {"input": payload}},
                headers={
                    "Content-Type": "application/json",
                    **auth_headers,
                    "cache-control": "no-cache",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("errors"):
                raise RuntimeError(f"AppSync publishPassiveCommand failed: {data.get('errors')}")

    def _ensure_subscription_started(self, *, run_id: str) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._subscribed_run_id = run_id

        signed_ws_url = _make_signed_ws_url(
            self._config.ws_endpoint,
            api_host=self._config.api_host,
            auth_token=self._config.auth_token,
        )

        def on_message(ws, message: str) -> None:
            try:
                data = json.loads(message)
            except Exception:
                return

            msg_type = data.get("type")

            if msg_type == "connection_ack":
                auth_headers = _build_auth_headers(self._config.auth_token)
                data_obj = {
                    "query": _on_step_result_subscription(),
                    "operationName": "OnPassiveStepResult",
                    "variables": {"runId": self._subscribed_run_id, "clientId": self._config.client_id},
                }
                start_payload = {
                    "id": self._subscription_id,
                    "type": "start",
                    "payload": {
                        "data": json.dumps(data_obj),
                        "extensions": {
                            "authorization": {
                                "host": self._config.api_host,
                                **auth_headers,
                            }
                        },
                    },
                }
                try:
                    ws.send(json.dumps(start_payload))
                except Exception:
                    return
                return

            if msg_type in ("ka", "keepalive"):
                return

            if msg_type == "data" and data.get("id") == self._subscription_id:
                payload_data = (data.get("payload") or {}).get("data")
                if not isinstance(payload_data, dict):
                    return
                envelope = payload_data.get("onPassiveStepResult")
                if not isinstance(envelope, dict):
                    return

                try:
                    run_id = envelope.get("runId")
                    step_id = envelope.get("stepId")
                    result_raw = envelope.get("result")
                    result_obj = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                    parsed = PassiveBrowserStepResult.model_validate(result_obj)
                except Exception:
                    return

                self._deliver_from_thread(parsed)

        def on_open(ws) -> None:
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception:
                return

        self._ws = websocket.WebSocketApp(
            signed_ws_url,
            header=[],
            on_message=on_message,
            on_open=on_open,
            subprotocols=["graphql-ws"],
        )

        self._ws_thread = threading.Thread(
            target=lambda: self._ws.run_forever(sslopt={"cert_reqs": 0}),
            daemon=True,
        )
        self._ws_thread.start()

    def _deliver_from_thread(self, result: PassiveBrowserStepResult) -> None:
        loop = self._loop
        if loop is None:
            return

        def _resolve() -> None:
            key = (result.run_id, result.step_id)
            fut = self._waiters.pop(key, None)
            if fut is not None and not fut.done():
                fut.set_result(result)
                return
            self._pending[key] = result

        try:
            loop.call_soon_threadsafe(_resolve)
        except Exception:
            return

    async def wait_for_result(self, *, run_id: str, step_id: str, timeout_s: float) -> PassiveBrowserStepResult:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._ensure_subscription_started(run_id=run_id)

        key = (run_id, step_id)
        if key in self._pending:
            return self._pending.pop(key)

        fut: asyncio.Future[PassiveBrowserStepResult] = self._loop.create_future()
        self._waiters[key] = fut

        try:
            return await asyncio.wait_for(fut, timeout=max(1.0, float(timeout_s)))
        except asyncio.TimeoutError:
            self._waiters.pop(key, None)
            raise TimeoutError(f"Timed out waiting for passive step result run_id={run_id} step_id={step_id}")


def make_appsync_passive_transport_from_env() -> AppSyncPassivePubSubTransport:
    http_endpoint = (os.environ.get("EC_APPSYNC_HTTP_ENDPOINT") or os.environ.get("EC_BROWSER_PASSIVE_PUB_ENDPOINT") or "").strip()
    if not http_endpoint:
        raise ValueError("Missing EC_APPSYNC_HTTP_ENDPOINT")

    ws_endpoint = (os.environ.get("EC_APPSYNC_WS_ENDPOINT") or os.environ.get("ECAN_WS_URL") or "").strip()
    if not ws_endpoint:
        ws_endpoint = _derive_realtime_endpoint(http_endpoint)

    api_host = (os.environ.get("EC_APPSYNC_HOST") or "").strip() or _derive_api_host(http_endpoint, ws_endpoint)
    token = (os.environ.get("EC_APPSYNC_TOKEN") or os.environ.get("EC_BROWSER_PASSIVE_TOKEN") or "").strip()
    client_id = (os.environ.get("EC_BROWSER_PASSIVE_CLIENT_ID") or "").strip()

    if not token:
        raise ValueError("Missing EC_APPSYNC_TOKEN / EC_BROWSER_PASSIVE_TOKEN")
    if not client_id:
        raise ValueError("Missing EC_BROWSER_PASSIVE_CLIENT_ID")

    cfg = AppSyncPassiveTransportConfig(
        http_endpoint=http_endpoint,
        ws_endpoint=ws_endpoint,
        api_host=api_host,
        auth_token=token,
        client_id=client_id,
    )
    return AppSyncPassivePubSubTransport(config=cfg)
