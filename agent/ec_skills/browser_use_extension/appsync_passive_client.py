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

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand, PassiveBrowserStepResult


@dataclass(frozen=True)
class AppSyncPassiveClientConfig:
    http_endpoint: str
    ws_endpoint: str
    api_host: str
    auth_token: str
    run_id: str
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
        result
        dom_tree
      }
    }
    """


class AppSyncPassiveClient:
    """AppSync WebSocket client for passive browser commands.
    
    This client subscribes to onPassiveCommand and dispatches commands
    via a callback. It is decoupled from PassiveAgent to allow flexible
    routing of commands to different handlers (e.g., task queues).
    """
    
    def __init__(
        self,
        *,
        config: AppSyncPassiveClientConfig,
        on_command_received: Callable[[PassiveBrowserCommand], None],
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        self._config = config
        self._on_command_received = on_command_received
        self._on_error = on_error

        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws: websocket.WebSocketApp | None = None
        self._ws_thread: threading.Thread | None = None
        self._subscription_id = "PassiveCommand1"

        self._stopped = False
        self._lock = threading.Lock()

    async def start(self) -> None:
        logger.info(f"[AppSyncPassiveClient] Starting subscription for run_id={self._config.run_id}, client_id={self._config.client_id}")
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

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
                logger.info("[AppSyncPassiveClient] WebSocket connection acknowledged")
                auth_headers = _build_auth_headers(self._config.auth_token)
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
                                **auth_headers,
                            }
                        },
                    },
                }
                try:
                    ws.send(json.dumps(start_payload))
                    logger.info(f"[AppSyncPassiveClient] Subscription started for run_id={self._config.run_id}")
                except Exception as e:
                    logger.error(f"[AppSyncPassiveClient] Failed to send subscription start: {e}")
                    return
                return

            if msg_type in ("ka", "keepalive"):
                return

            if msg_type == "data" and data.get("id") == self._subscription_id:
                # Log the raw message for debugging (truncate screenshot data)
                from agent.ec_skills.browser_use_extension.passive_agent_node import truncate_screenshot_for_logging
                try:
                    log_data = truncate_screenshot_for_logging(data)
                    log_msg = json.dumps(log_data)
                    print(f"[AppSyncPassiveClient] Raw WebSocket message received: {log_msg[:500]}..." if len(log_msg) > 500 else f"[AppSyncPassiveClient] Raw WebSocket message received: {log_msg}")
                except Exception:
                    print(f"[AppSyncPassiveClient] Raw WebSocket message received: {message[:200]}...")
                
                # Check for errors in the payload
                payload = data.get("payload") or {}
                errors = payload.get("errors")
                if errors:
                    logger.error(f"[AppSyncPassiveClient] AppSync subscription error: {errors}")
                    print(f"[AppSyncPassiveClient] ❌ AppSync subscription error: {errors}")
                    return
                
                payload_data = payload.get("data")
                if not isinstance(payload_data, dict):
                    logger.warning(f"[AppSyncPassiveClient] payload.data is not a dict: {type(payload_data)}")
                    return
                envelope = payload_data.get("onPassiveCommand")
                if not isinstance(envelope, dict):
                    logger.warning(f"[AppSyncPassiveClient] onPassiveCommand is null or not a dict: {envelope}")
                    return

                try:
                    cmd_raw = envelope.get("command")
                    logger.debug(f"[AppSyncPassiveClient] Raw command received: {cmd_raw}")
                    cmd_obj = json.loads(cmd_raw) if isinstance(cmd_raw, str) else cmd_raw
                    # Handle double-encoded JSON (string containing JSON string)
                    if isinstance(cmd_obj, str):
                        logger.debug(f"[AppSyncPassiveClient] cmd_obj is still a string, parsing again...")
                        cmd_obj = json.loads(cmd_obj)
                    logger.debug(f"[AppSyncPassiveClient] Parsed cmd_obj type={type(cmd_obj).__name__}, value={cmd_obj}")
                    cmd = PassiveBrowserCommand.model_validate(cmd_obj)
                    logger.info(f"[AppSyncPassiveClient] Received command: run_id={cmd.run_id}, step_id={cmd.step_id}")
                except Exception as e:
                    logger.error(f"[AppSyncPassiveClient] Failed to parse command: {e}")
                    logger.error(f"[AppSyncPassiveClient] cmd_raw was: {cmd_raw}")
                    return

                self._dispatch_command(cmd)

        def on_open(ws) -> None:
            logger.info("[AppSyncPassiveClient] WebSocket opened, sending connection_init")
            try:
                ws.send(json.dumps({"type": "connection_init", "payload": {}}))
            except Exception as e:
                logger.error(f"[AppSyncPassiveClient] Failed to send connection_init: {e}")
                return

        def on_error(ws, error) -> None:
            logger.error(f"[AppSyncPassiveClient] WebSocket error: {error}")
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
        """Dispatch command to the registered callback."""
        if self._stopped:
            logger.debug("[AppSyncPassiveClient] Ignoring command - client stopped")
            return
        
        try:
            logger.debug(f"[AppSyncPassiveClient] Dispatching command: {cmd.step_id}")
            self._on_command_received(cmd)
        except Exception as e:
            logger.error(f"[AppSyncPassiveClient] Error dispatching command: {e}")
            if self._on_error is not None:
                try:
                    self._on_error(e)
                except Exception:
                    pass

    async def _publish_step_result(self, result: PassiveBrowserStepResult) -> None:
        # Mask large data to avoid AppSync payload size limit (240KB)
        result_dict = result.model_dump()
        browser_data = result_dict.get("browser")
        logger.info(f"[AppSyncPassiveClient] browser_data type={type(browser_data).__name__}, keys={list(browser_data.keys()) if isinstance(browser_data, dict) else 'N/A'}")
        if browser_data and isinstance(browser_data, dict):
            # Mask screenshot
            screenshot = browser_data.get("screenshot_base64")
            if screenshot and isinstance(screenshot, str) and len(screenshot) > 100:
                screenshot_len = len(screenshot)
                browser_data["screenshot_base64"] = f"[MASKED:{screenshot_len} bytes]"
                logger.info(f"[AppSyncPassiveClient] ✅ Masked screenshot_base64 ({screenshot_len} bytes)")
            
            # Mask DOM tree (selector_map/elements) - temporarily mask to stay under 240KB limit
            selector_map = browser_data.get("selector_map")
            if selector_map and isinstance(selector_map, (list, dict)):
                selector_map_len = len(json.dumps(selector_map)) if selector_map else 0
                browser_data["selector_map"] = f"[MASKED:{selector_map_len} bytes, {len(selector_map) if isinstance(selector_map, list) else 'dict'} items]"
                logger.info(f"[AppSyncPassiveClient] ✅ Masked selector_map ({selector_map_len} bytes)")
            
            # Also mask dom_text if it's large
            dom_text = browser_data.get("dom_text")
            if dom_text and isinstance(dom_text, str) and len(dom_text) > 10000:
                dom_text_len = len(dom_text)
                browser_data["dom_text"] = f"[MASKED:{dom_text_len} chars]"
                logger.info(f"[AppSyncPassiveClient] ✅ Masked dom_text ({dom_text_len} chars)")
        else:
            logger.warning(f"[AppSyncPassiveClient] browser_data is not a dict, cannot mask")
        
        # Remove null values - AppSync AWSJSON cannot handle null in non-nullable fields
        from agent.ec_skills.browser_use_extension.passive_agent_node import remove_null_values
        result_dict = remove_null_values(result_dict)
        
        # Ensure all required fields have valid defaults (not null)
        # Required format: {"schema_version":1,"type":"browser_use_passive_step_result","ok":true,"elapsed_ms":5,"actions":[],"action_results":[],"errors":[],"browser":{}}
        if "schema_version" not in result_dict:
            result_dict["schema_version"] = 1
        if "type" not in result_dict:
            result_dict["type"] = "browser_use_passive_step_result"
        if "ok" not in result_dict:
            result_dict["ok"] = True
        if "elapsed_ms" not in result_dict:
            result_dict["elapsed_ms"] = 0
        if "actions" not in result_dict:
            result_dict["actions"] = []
        if "action_results" not in result_dict:
            result_dict["action_results"] = []
        if "errors" not in result_dict:
            result_dict["errors"] = []
        if not result_dict.get("browser"):
            result_dict["browser"] = {}
        
        envelope = {
            "runId": result.run_id,
            "clientId": self._config.client_id,
            "stepId": result.step_id,
            "result": json.dumps(result_dict),  # AWSJSON type - JSON-encoded string
            "dom_tree": json.dumps({}),
        }

        auth_headers = _build_auth_headers(self._config.auth_token)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self._config.http_endpoint,
                json={"query": _publish_step_result_mutation(), "variables": {"input": envelope}},
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
                raise RuntimeError(f"AppSync publishPassiveStepResult failed: {data.get('errors')}")

    async def stop(self) -> None:
        with self._lock:
            self._stopped = True
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:
                pass


def make_appsync_passive_client_from_env(
    *,
    on_command_received: Callable[[PassiveBrowserCommand], None],
    on_error: Callable[[Exception], None] | None = None,
) -> AppSyncPassiveClient:
    """Create an AppSyncPassiveClient from environment variables.
    
    Required env vars:
        EC_APPSYNC_HTTP_ENDPOINT: AppSync HTTP endpoint
        EC_APPSYNC_TOKEN: API key or JWT token
        EC_BROWSER_PASSIVE_RUN_ID: Run ID to subscribe to (or '*' for all)
        EC_BROWSER_PASSIVE_CLIENT_ID: Client ID for this subscriber
    
    Optional env vars:
        EC_APPSYNC_WS_ENDPOINT: WebSocket endpoint (derived from HTTP if not set)
        EC_APPSYNC_HOST: API host (derived from endpoints if not set)
    """
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
    # AppSync subscriptions require exact match - wildcards don't work
    if not run_id or run_id == "*":
        run_id = "0123456789"
        logger.warning(f"[AppSyncPassiveClient] EC_BROWSER_PASSIVE_RUN_ID not set or '*', defaulting to '{run_id}'")
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
    return AppSyncPassiveClient(
        config=cfg,
        on_command_received=on_command_received,
        on_error=on_error,
    )
