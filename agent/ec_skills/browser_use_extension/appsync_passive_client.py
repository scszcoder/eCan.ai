import asyncio
import base64
import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
import websocket

from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent
from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand, PassiveBrowserStepResult


@dataclass(frozen=True)
class AppSyncPassiveClientConfig:
    http_endpoint: str
    ws_endpoint: str
    api_host: str
    auth_token: str
    run_id: str
    client_id: str


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

    header_obj = {
        "host": api_host,
        "Authorization": auth_token,
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


def _on_command_subscription() -> str:
    return """
    subscription OnPassiveCommand($runId: ID!, $clientId: ID!) {
      onPassiveCommand(runId: $runId, clientId: $clientId) {
        runId
        clientId
        stepId
        command
      }
    }
    """


def _publish_step_result_mutation() -> str:
    return """
    mutation PublishPassiveStepResult($input: PassiveBrowserStepResultEnvelopeInput!) {
      publishPassiveStepResult(input: $input) {
        runId
        clientId
        stepId
      }
    }
    """


class AppSyncPassiveClient:
    def __init__(
        self,
        *,
        config: AppSyncPassiveClientConfig,
        passive_agent: PassiveAgent,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._config = config
        self._agent = passive_agent
        self._on_error = on_error

        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._subscription_id = "PassiveCommand1"

        self._stopped = False
        self._lock = threading.Lock()

    async def start(self) -> None:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        await self._agent.start()

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
                data_obj = {
                    "query": _on_command_subscription(),
                    "operationName": "OnPassiveCommand",
                    "variables": {"runId": self._config.run_id, "clientId": self._config.client_id},
                }
                start_payload = {
                    "id": self._subscription_id,
                    "type": "start",
                    "payload": {
                        "data": json.dumps(data_obj),
                        "extensions": {
                            "authorization": {
                                "host": self._config.api_host,
                                "Authorization": self._config.auth_token,
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
                envelope = payload_data.get("onPassiveCommand")
                if not isinstance(envelope, dict):
                    return

                try:
                    cmd_raw = envelope.get("command")
                    cmd_obj = json.loads(cmd_raw) if isinstance(cmd_raw, str) else cmd_raw
                    cmd = PassiveBrowserCommand.model_validate(cmd_obj)
                except Exception:
                    return

                self._dispatch_command(cmd)

        def on_open(ws) -> None:
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception:
                return

        def on_error(ws, error) -> None:
            exc = error if isinstance(error, Exception) else Exception(str(error))
            if self._on_error is not None:
                try:
                    self._on_error(exc)
                except Exception:
                    pass

        self._ws = websocket.WebSocketApp(
            signed_ws_url,
            header=[],
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
            subprotocols=["graphql-ws"],
        )

        self._ws_thread = threading.Thread(
            target=lambda: self._ws.run_forever(sslopt={"cert_reqs": 0}),
            daemon=True,
        )
        self._ws_thread.start()

    def _dispatch_command(self, cmd: PassiveBrowserCommand) -> None:
        loop = self._loop
        if loop is None:
            return

        async def _handle() -> None:
            try:
                await self._handle_command(cmd)
            except Exception as e:
                if self._on_error is not None:
                    self._on_error(e)

        try:
            loop.call_soon_threadsafe(lambda: asyncio.create_task(_handle()))
        except Exception:
            return

    async def _handle_command(self, cmd: PassiveBrowserCommand) -> None:
        if self._stopped:
            return

        payload = await self._agent.execute_actions(
            cmd.actions,
            stop_on_error=bool(cmd.stop_on_error),
            include_screenshot=bool(cmd.include_screenshot),
        )

        result = PassiveBrowserStepResult(
            run_id=cmd.run_id,
            step_id=cmd.step_id,
            ok=not bool(payload.get("errors")),
            elapsed_ms=int(payload.get("elapsed_ms") or 0),
            actions=payload.get("actions") or [],
            action_results=payload.get("action_results") or [],
            errors=payload.get("errors") or [],
            browser=payload.get("browser") or {},
        )

        await self._publish_step_result(result)

    async def _publish_step_result(self, result: PassiveBrowserStepResult) -> None:
        envelope = {
            "runId": result.run_id,
            "clientId": self._config.client_id,
            "stepId": result.step_id,
            "result": result.model_dump(),
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._config.http_endpoint,
                json={"query": _publish_step_result_mutation(), "variables": {"input": envelope}},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": self._config.auth_token,
                    "cache-control": "no-cache",
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict) and data.get("errors"):
                raise RuntimeError(f"AppSync publishPassiveStepResult failed: {data.get('errors')}")

    async def stop(self) -> None:
        with self._lock:
            self._stopped = True
        try:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
        finally:
            await self._agent.stop()


def make_appsync_passive_client_from_env(*, passive_agent: PassiveAgent) -> AppSyncPassiveClient:
    http_endpoint = (os.environ.get("EC_APPSYNC_HTTP_ENDPOINT") or "").strip()
    if not http_endpoint:
        raise ValueError("Missing EC_APPSYNC_HTTP_ENDPOINT")

    ws_endpoint = (os.environ.get("EC_APPSYNC_WS_ENDPOINT") or os.environ.get("ECAN_WS_URL") or "").strip()
    if not ws_endpoint:
        ws_endpoint = _derive_realtime_endpoint(http_endpoint)

    api_host = (os.environ.get("EC_APPSYNC_HOST") or "").strip() or _derive_api_host(http_endpoint, ws_endpoint)
    token = (os.environ.get("EC_APPSYNC_TOKEN") or "").strip()
    run_id = (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
    client_id = (os.environ.get("EC_BROWSER_PASSIVE_CLIENT_ID") or "").strip()

    if not token:
        raise ValueError("Missing EC_APPSYNC_TOKEN")
    if not run_id:
        raise ValueError("Missing EC_BROWSER_PASSIVE_RUN_ID")
    if not client_id:
        raise ValueError("Missing EC_BROWSER_PASSIVE_CLIENT_ID")

    cfg = AppSyncPassiveClientConfig(
        http_endpoint=http_endpoint,
        ws_endpoint=ws_endpoint,
        api_host=api_host,
        auth_token=token,
        run_id=run_id,
        client_id=client_id,
    )
    return AppSyncPassiveClient(config=cfg, passive_agent=passive_agent)
