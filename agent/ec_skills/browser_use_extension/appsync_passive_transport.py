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


def _transport_log(msg: str, level: str = "info") -> None:
    """Log to both local logger and skill editor console (frontend)."""
    print(msg)  # Always print to stdout
    try:
        from utils.logger_helper import logger_helper as logger
        if level == "debug":
            logger.debug(msg)
        elif level == "warning":
            logger.warning(msg)
        elif level == "error":
            logger.error(msg)
        else:
            logger.info(msg)
    except Exception:
        pass
    try:
        from agent.cloud_worker.cloud_logger import get_skill_editor_logger
        se_logger = get_skill_editor_logger()
        if se_logger:
            se_logger.log(msg)
    except Exception:
        pass


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
        print("[AppSyncPassiveTransport] auth_headers: NO TOKEN")
        return {}
    if tok.lower().startswith("bearer "):
        print(f"[AppSyncPassiveTransport] auth_headers: Authorization (Bearer), token_len={len(tok)}")
        return {"Authorization": tok}
    if tok.count(".") >= 2:
        print(f"[AppSyncPassiveTransport] auth_headers: Authorization (JWT), token_len={len(tok)}")
        return {"Authorization": tok}
    print(f"[AppSyncPassiveTransport] auth_headers: x-api-key, key_len={len(tok)}")
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
        command
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
        self._subscription_acked = threading.Event()

    async def publish_command(self, cmd: PassiveBrowserCommand) -> None:
        # AWSJSON scalar expects a JSON string, not a nested object
        command_json_str = json.dumps(cmd.model_dump())
        
        payload = {
            "runId": cmd.run_id,
            "clientId": self._config.client_id,
            "stepId": cmd.step_id,
            "command": command_json_str,  # JSON string for AWSJSON type
        }
        
        # Log the IDs being used for debugging
        print(f"[AppSyncPassiveTransport] publishPassiveCommand: clientId={self._config.client_id}, runId={cmd.run_id}, stepId={cmd.step_id}")

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
            print(
                f"[AppSyncPassiveTransport] Starting subscription: clientId={self._config.client_id}, runId={run_id}"
            )

        signed_ws_url = _make_signed_ws_url(
            self._config.ws_endpoint,
            api_host=self._config.api_host,
            auth_token=self._config.auth_token,
        )

        def on_message(ws, message: str) -> None:
            try:
                data = json.loads(message)
            except Exception as exc:
                print(f"[AppSyncPassiveTransport] WS message parse error: {exc}, raw={message[:500]}")
                return

            msg_type = data.get("type")
            msg_id = data.get("id")

            # Log ALL WebSocket message types for diagnostics
            if msg_type not in ("ka", "keepalive"):
                payload_preview = str(data.get("payload", ""))[:300]
                print(f"[AppSyncPassiveTransport] WS msg: type={msg_type}, id={msg_id}, payload={payload_preview}")

            if msg_type == "connection_ack":
                print("[AppSyncPassiveTransport] WebSocket connection acknowledged")
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
                print(f"[AppSyncPassiveTransport] Sending subscription start: id={self._subscription_id}, runId={self._subscribed_run_id}, clientId={self._config.client_id}")
                try:
                    ws.send(json.dumps(start_payload))
                    print("[AppSyncPassiveTransport] Subscription start message sent successfully")
                except Exception as exc:
                    print(f"[AppSyncPassiveTransport] ERROR sending subscription start: {exc}")
                    return
                return

            if msg_type in ("ka", "keepalive"):
                return

            if msg_type == "start_ack":
                print(f"[AppSyncPassiveTransport] ✅ Subscription ACKNOWLEDGED by AppSync: id={msg_id}")
                self._subscription_acked.set()
                return

            if msg_type == "error":
                error_payload = data.get("payload", {})
                print(f"[AppSyncPassiveTransport] ❌ Subscription ERROR from AppSync: id={msg_id}, errors={error_payload}")
                return

            if msg_type == "complete":
                print(f"[AppSyncPassiveTransport] Subscription COMPLETED by server: id={msg_id}")
                return

            if msg_type == "connection_error":
                print(f"[AppSyncPassiveTransport] ❌ Connection ERROR: {data.get('payload', {})}")
                return

            if msg_type == "data" and msg_id == self._subscription_id:
                # Log raw WebSocket data to frontend
                _transport_log(f"[PassiveTransport] 📨 RAW WS DATA received: {message[:500]}...")
                
                payload_data = (data.get("payload") or {}).get("data")
                if not isinstance(payload_data, dict):
                    _transport_log(f"[PassiveTransport] ❌ payload_data not dict: {type(payload_data)}", level="error")
                    return
                envelope = payload_data.get("onPassiveStepResult")
                if not isinstance(envelope, dict):
                    errors = (data.get("payload") or {}).get("errors")
                    _transport_log(f"[PassiveTransport] ❌ no onPassiveStepResult envelope, errors={errors}", level="error")
                    return

                received_run_id = envelope.get("runId")
                received_step_id = envelope.get("stepId")
                
                # Log what we're waiting for vs what we received
                waiting_keys = list(self._waiters.keys())
                _transport_log(
                    f"[PassiveTransport] ✅ Envelope received: stepId={received_step_id}, runId={received_run_id}, "
                    f"waiting_for={waiting_keys}"
                )

                try:
                    result_raw = envelope.get("result")
                    result_obj = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                    
                    # Log raw result structure for debugging
                    _transport_log(f"[PassiveTransport] 📋 Raw result keys: {list(result_obj.keys()) if isinstance(result_obj, dict) else type(result_obj)}")
                    
                    # Inject run_id and step_id from envelope into result object
                    result_obj["run_id"] = received_run_id
                    result_obj["step_id"] = received_step_id
                    # Also inject dom_tree if present in envelope
                    dom_tree_raw = envelope.get("dom_tree")
                    if dom_tree_raw:
                        result_obj["dom_tree"] = json.loads(dom_tree_raw) if isinstance(dom_tree_raw, str) else dom_tree_raw
                    
                    parsed = PassiveBrowserStepResult.model_validate(result_obj)
                    _transport_log(f"[PassiveTransport] ✅ Pydantic validation PASSED for stepId={received_step_id}")
                except Exception as exc:
                    # Log detailed validation error to frontend
                    _transport_log(
                        f"[PassiveTransport] ❌ Pydantic validation FAILED: {exc}\n"
                        f"  Raw data: {json.dumps(result_obj, default=str)[:1000]}",
                        level="error"
                    )
                    return

                _transport_log(f"[PassiveTransport] 📤 Delivering result for stepId={received_step_id}")
                self._deliver_from_thread(parsed)

        def on_open(ws) -> None:
            print("[AppSyncPassiveTransport] WebSocket opened, sending connection_init")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as exc:
                print(f"[AppSyncPassiveTransport] ERROR sending connection_init: {exc}")
                return

        def on_error(ws, error) -> None:
            print(f"[AppSyncPassiveTransport] ❌ WebSocket error: {error}")

        def on_close(ws, close_status_code, close_msg) -> None:
            print(f"[AppSyncPassiveTransport] WebSocket closed: code={close_status_code}, msg={close_msg}")

        self._ws = websocket.WebSocketApp(
            signed_ws_url,
            header=[],
            on_message=on_message,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close,
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

    async def prepare_for_result(self, *, run_id: str, step_id: str) -> None:
        """Start subscription, wait for ack, and pre-register the waiter.

        MUST be called BEFORE publish_command so the subscription is
        ready to receive the response from the local client.
        """
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._ensure_subscription_started(run_id=run_id)

        # Wait until AppSync acknowledges the subscription (start_ack)
        if not self._subscription_acked.is_set():
            print("[AppSyncPassiveTransport] Waiting for subscription ack before publishing command...")
            acked = await self._loop.run_in_executor(
                None, self._subscription_acked.wait, 30.0
            )
            if not acked:
                raise TimeoutError("Subscription acknowledgement timed out after 30s")
            print("[AppSyncPassiveTransport] ✅ Subscription ack received, safe to publish")

        # Pre-register the waiter so results that arrive immediately are caught
        key = (run_id, step_id)
        if key not in self._waiters and key not in self._pending:
            fut: asyncio.Future[PassiveBrowserStepResult] = self._loop.create_future()
            self._waiters[key] = fut

    async def wait_for_result(self, *, run_id: str, step_id: str, timeout_s: float) -> PassiveBrowserStepResult:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._ensure_subscription_started(run_id=run_id)

        key = (run_id, step_id)
        if key in self._pending:
            return self._pending.pop(key)

        # Reuse waiter if prepare_for_result already registered one
        fut = self._waiters.get(key)
        if fut is None:
            fut = self._loop.create_future()
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

    ws_endpoint_env = (os.environ.get("EC_APPSYNC_WS_ENDPOINT") or "").strip()
    if ws_endpoint_env:
        ws_endpoint = ws_endpoint_env
    else:
        # Always derive from HTTP to avoid stale ECAN_WS_URL endpoints
        ws_endpoint = _derive_realtime_endpoint(http_endpoint)

    api_host = (os.environ.get("EC_APPSYNC_HOST") or "").strip() or _derive_api_host(http_endpoint, ws_endpoint)
    token = (os.environ.get("EC_APPSYNC_TOKEN") or os.environ.get("EC_BROWSER_PASSIVE_TOKEN") or "").strip()
    client_id = (os.environ.get("EC_BROWSER_PASSIVE_CLIENT_ID") or "").strip()

    if not token:
        raise ValueError("Missing EC_APPSYNC_TOKEN / EC_BROWSER_PASSIVE_TOKEN")
    if not client_id:
        raise ValueError("Missing EC_BROWSER_PASSIVE_CLIENT_ID")

    # Log auth method and endpoints for diagnostics
    is_jwt = token.count(".") >= 2
    print(
        "[AppSyncPassiveTransport] make_from_env: "
        f"auth_type={'JWT' if is_jwt else 'API_KEY'}, token_len={len(token)}, client_id={client_id}, "
        f"http_endpoint={http_endpoint}, ws_endpoint={ws_endpoint}, api_host={api_host}"
    )

    cfg = AppSyncPassiveTransportConfig(
        http_endpoint=http_endpoint,
        ws_endpoint=ws_endpoint,
        api_host=api_host,
        auth_token=token,
        client_id=client_id,
    )
    return AppSyncPassivePubSubTransport(config=cfg)
