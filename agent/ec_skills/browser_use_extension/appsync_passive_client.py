import asyncio
import base64
import json
import os
import time
import threading
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import httpx
import websocket

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.passive_protocol import PassiveBrowserCommand, PassiveBrowserStepResult
from agent.cloud_api.cloud_api import _track_appsync_ws_thread


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


def _decode_awsjson(value: Any, *, max_depth: int = 5) -> Any:
    """Decode AppSync AWSJSON values which are sometimes double-serialized.

    In practice `command` may arrive as:
    - dict (already decoded)
    - JSON string
    - JSON string that itself contains a JSON string
    """
    cur = value
    for _ in range(max(1, int(max_depth))):
        if not isinstance(cur, str):
            return cur
        s = cur.strip()
        if not s:
            return cur
        try:
            cur = json.loads(s)
        except Exception:
            return cur
    return cur


_INTERACTIVE_TAGS = {
    "a",
    "button",
    "input",
    "select",
    "textarea",
    "option",
}
_INTERACTIVE_ROLES = {
    "button",
    "link",
    "textbox",
    "combobox",
    "listbox",
    "checkbox",
    "radio",
    "menu",
    "menuitemcheckbox",
    "tab",
    "menuitem",
    "switch",
}
_KEEP_ATTRS = ("id", "class", "className", "role", "aria-label", "name", "value", "href")


def _truncate_text(value: str | None, max_len: int = 2000) -> str | None:
    if not value or not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value[:max_len]


def _node_text(node: dict[str, Any]) -> str | None:
    for key in ("text", "textContent", "nodeValue", "value"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _node_tag(node: dict[str, Any]) -> str | None:
    for key in ("tag", "tag_name", "tagName", "nodeName"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _node_role(node: dict[str, Any], attrs: dict[str, Any]) -> str | None:
    for key in ("role", "ariaRole"):
        value = node.get(key) or attrs.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
    return None


def _node_children(node: dict[str, Any]) -> list[Any]:
    for key in ("children", "childNodes"):
        value = node.get(key)
        if isinstance(value, list):
            return value
    return []


def _reduce_dom_tree_node(node: Any, max_bytes: int) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(node, dict) or max_bytes <= 0:
        return None, max_bytes

    attrs = node.get("attributes") if isinstance(node.get("attributes"), dict) else {}
    tag = _node_tag(node)
    role = _node_role(node, attrs)
    text_value = _truncate_text(_node_text(node))
    is_text = bool(text_value)
    is_interactive = bool(
        node.get("is_interactive")
        or node.get("interactive")
        or (tag in _INTERACTIVE_TAGS)
        or (role in _INTERACTIVE_ROLES)
    )

    reduced: dict[str, Any] = {}
    if tag:
        reduced["tag"] = tag
    if role:
        reduced["role"] = role
    if text_value:
        reduced["text"] = text_value

    for key in _KEEP_ATTRS:
        value = node.get(key) if key in node else attrs.get(key)
        if isinstance(value, str) and value.strip():
            reduced_key = "class" if key == "className" else key
            reduced.setdefault(reduced_key, value.strip())

    children = _node_children(node)
    if not (is_text or is_interactive or children):
        return None, max_bytes

    base_size = len(json.dumps(reduced))
    if base_size > max_bytes:
        return None, max_bytes

    remaining = max_bytes - base_size
    reduced_children: list[dict[str, Any]] = []
    for child in children:
        child_reduced, remaining = _reduce_dom_tree_node(child, remaining)
        if not child_reduced:
            if remaining <= 0:
                break
            continue
        candidate = dict(reduced, children=reduced_children + [child_reduced])
        candidate_size = len(json.dumps(candidate))
        if candidate_size > max_bytes:
            break
        reduced_children.append(child_reduced)
        remaining = max_bytes - candidate_size

    if reduced_children:
        reduced["children"] = reduced_children

    return reduced, max_bytes - len(json.dumps(reduced))


def _reduce_dom_tree_payload(payload: Any, max_bytes: int) -> Any:
    if not payload or max_bytes <= 0:
        return {}

    try:
        if isinstance(payload, dict) and ("root" in payload or "_root" in payload):
            root_key = "root" if "root" in payload else "_root"
            reduced_root, _ = _reduce_dom_tree_node(payload.get(root_key), max_bytes)
            if not reduced_root:
                return {}
            reduced_payload: Any = {root_key: reduced_root}
        elif isinstance(payload, list):
            reduced_list: list[dict[str, Any]] = []
            remaining = max_bytes
            for node in payload:
                reduced_node, remaining = _reduce_dom_tree_node(node, remaining)
                if reduced_node:
                    reduced_list.append(reduced_node)
                if remaining <= 0:
                    break
            reduced_payload = reduced_list
        elif isinstance(payload, dict):
            reduced_node, _ = _reduce_dom_tree_node(payload, max_bytes)
            reduced_payload = reduced_node or {}
        else:
            return {}

        if len(json.dumps(reduced_payload)) > max_bytes:
            return {
                "_truncated": True,
                "original_bytes": len(json.dumps(payload)),
                "max_bytes": max_bytes,
                "note": "dom_tree reduced but still exceeded size cap",
            }
        return reduced_payload
    except Exception as exc:
        logger.error(f"[AppSyncPassiveClient] Failed to reduce dom_tree: {exc}")
        return {}


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
        self._reconnect_delay = float(os.getenv("ECAN_PASSIVE_WS_RECONNECT_DELAY", "3.0"))
        self._max_reconnect_delay = float(os.getenv("ECAN_PASSIVE_WS_MAX_RECONNECT_DELAY", "60.0"))
        self._current_reconnect_delay = self._reconnect_delay
        self._reconnect_count = 0

    def _close_existing_ws(self) -> None:
        """Close any existing WebSocket connection and wait for thread to finish."""
        old_ws = self._ws
        old_thread = self._ws_thread
        self._ws = None
        self._ws_thread = None
        if old_ws is not None:
            try:
                old_ws.close()
                logger.info("[AppSyncPassiveClient] Closed stale WebSocket")
            except Exception:
                pass
        if old_thread is not None and old_thread.is_alive():
            try:
                old_thread.join(timeout=5.0)
            except Exception:
                pass

    async def start(self) -> None:
        auth_headers = _build_auth_headers(self._config.auth_token)
        auth_type = "NONE"
        if "x-api-key" in auth_headers:
            auth_type = "API_KEY"
        elif "Authorization" in auth_headers:
            auth_type = "AUTHORIZATION"

        logger.info(
            "[AppSyncPassiveClient] Starting subscription "
            f"run_id={self._config.run_id}, client_id={self._config.client_id}, "
            f"auth_type={auth_type}, token_len={len((self._config.auth_token or '').strip())}, "
            f"http_endpoint={self._config.http_endpoint}, ws_endpoint={self._config.ws_endpoint}, "
            f"api_host={self._config.api_host}"
        )
        # Fix C: Clean up any stale WebSocket from a previous run
        self._close_existing_ws()
        with self._lock:
            self._stopped = False
        if self._loop is None:
            self._loop = asyncio.get_running_loop()

        self._start_ws()

    def _start_ws(self) -> None:
        """Create and start the WebSocket connection (called by start() and reconnect)."""
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
                from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
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
                    return
                envelope = payload_data.get("onPassiveCommand")
                if not isinstance(envelope, dict):
                    return

                try:
                    cmd_raw = envelope.get("command")
                    cmd_obj = json.loads(cmd_raw) if isinstance(cmd_raw, str) else cmd_raw
                    # AWSJSON can arrive multiply-encoded (string-within-string); unwrap until we get a dict
                    for _ in range(5):
                        if not isinstance(cmd_obj, str):
                            break
                        cmd_obj = json.loads(cmd_obj)
                    cmd = PassiveBrowserCommand.model_validate(cmd_obj)
                    logger.info(f"[AppSyncPassiveClient] Received command: type={cmd.type}, run_id={cmd.run_id}, step_id={cmd.step_id}, actions_count={len(cmd.actions) if cmd.actions else 0}")
                except Exception as e:
                    logger.error(f"[AppSyncPassiveClient] Failed to parse command: {e}")
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

        def on_close(ws, close_status_code, close_msg) -> None:
            # status=1000 is a normal close - should NOT trigger reconnect
            if close_status_code == 1000:
                logger.info(
                    f"[AppSyncPassiveClient] WebSocket closed normally: status={close_status_code}, msg={close_msg}, skipping reconnect"
                )
                return  # Don't reconnect on normal close
            
            logger.warning(
                f"[AppSyncPassiveClient] WebSocket closed unexpectedly: status={close_status_code}, msg={close_msg}"
            )
            if not self._stopped:
                self._schedule_reconnect()

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
            name=f"PassiveBrowserClient-ws-{id(self)}",
            daemon=True,
        )
        _track_appsync_ws_thread(self._ws_thread)
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
        result_dict.pop("dom_tree", None)  # Remove from result dict, we'll extract from browser.dom_text
        max_dom_tree_bytes = int(os.getenv("ECAN_PASSIVE_DOM_TREE_MAX_BYTES", "204800"))
        browser_data = result_dict.get("browser")
        logger.info(f"[AppSyncPassiveClient] browser_data type={type(browser_data).__name__}, keys={list(browser_data.keys()) if isinstance(browser_data, dict) else 'N/A'}")
        
        # Extract dom_text and selector_map from browser to use as dom_tree (separate AppSync field)
        dom_tree_payload = {}
        if browser_data and isinstance(browser_data, dict):
            # Extract dom_text and move to dom_tree field
            dom_text = browser_data.pop("dom_text", None)
            if dom_text and isinstance(dom_text, str):
                dom_tree_payload["dom_text"] = dom_text
                logger.info(f"[AppSyncPassiveClient] ✅ Extracted dom_text ({len(dom_text)} chars) for dom_tree field")
            
            # Extract selector_map and move to dom_tree field (cloud worker needs it for element interaction)
            selector_map = browser_data.pop("selector_map", None)
            if selector_map and isinstance(selector_map, (list, dict)):
                dom_tree_payload["selector_map"] = selector_map
                selector_map_len = len(json.dumps(selector_map)) if selector_map else 0
                logger.info(f"[AppSyncPassiveClient] ✅ Extracted selector_map ({selector_map_len} bytes, {len(selector_map) if isinstance(selector_map, list) else 'dict'} items) for dom_tree field")
            
            # Mask screenshot
            screenshot = browser_data.get("screenshot_base64")
            if screenshot and isinstance(screenshot, str) and len(screenshot) > 100:
                screenshot_len = len(screenshot)
                browser_data["screenshot_base64"] = "[OCR_PENDING]"
                browser_data.setdefault("ocr_text", "[OCR_PLACEHOLDER]")
                logger.info(f"[AppSyncPassiveClient] ✅ Replaced screenshot_base64 with OCR placeholder ({screenshot_len} bytes)")
        else:
            logger.warning(f"[AppSyncPassiveClient] browser_data is not a dict, cannot mask")
        
        # Remove null values - AppSync AWSJSON cannot handle null in non-nullable fields
        from agent.ec_skills.browser_use_extension.passive_utils import remove_null_values
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

        dom_tree_original_json = json.dumps(dom_tree_payload or {})
        if len(dom_tree_original_json) > max_dom_tree_bytes:
            logger.warning(
                "[AppSyncPassiveClient] dom_tree exceeds cap: %s bytes > %s bytes. Reducing.",
                len(dom_tree_original_json),
                max_dom_tree_bytes,
            )
        dom_tree_payload = _reduce_dom_tree_payload(dom_tree_payload or {}, max_dom_tree_bytes)
        dom_tree_json = json.dumps(dom_tree_payload or {})
        if len(dom_tree_json) > max_dom_tree_bytes:
            logger.warning(
                "[AppSyncPassiveClient] Reduced dom_tree still exceeds cap: %s bytes > %s bytes. Truncating.",
                len(dom_tree_json),
                max_dom_tree_bytes,
            )
            dom_tree_payload = {
                "_truncated": True,
                "original_bytes": len(dom_tree_original_json),
                "max_bytes": max_dom_tree_bytes,
                "note": "dom_tree truncated to stay under websocket payload limit",
            }
            dom_tree_json = json.dumps(dom_tree_payload)
        
        envelope = {
            "runId": result.run_id,
            "clientId": self._config.client_id,
            "stepId": result.step_id,
            "result": json.dumps(result_dict),  # AWSJSON type - JSON-encoded string
            "dom_tree": dom_tree_json,
        }
        
        # Log full envelope before sending
        logger.debug(f"[_publish_step_result] Sending envelope: runId={envelope['runId']}, stepId={envelope['stepId']}, result_len={len(envelope['result'])}, dom_tree_len={len(envelope['dom_tree'])}")
        logger.debug(f"[_publish_step_result] Full envelope: {envelope}")

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

    def _schedule_reconnect(self) -> None:
        """Schedule a reconnect attempt after exponential backoff delay."""
        if self._stopped:
            return
        self._reconnect_count += 1
        delay = min(self._current_reconnect_delay, self._max_reconnect_delay)
        logger.info(f"[AppSyncPassiveClient] Scheduling reconnect #{self._reconnect_count} in {delay:.1f}s")

        def _reconnect() -> None:
            time.sleep(delay)
            if self._stopped:
                return
            logger.info(f"[AppSyncPassiveClient] Reconnecting (attempt #{self._reconnect_count})...")
            try:
                self._start_ws()
                # Reset delay on successful reconnect start
                self._current_reconnect_delay = self._reconnect_delay
                logger.info(f"[AppSyncPassiveClient] Reconnect #{self._reconnect_count} initiated")
            except Exception as e:
                logger.error(f"[AppSyncPassiveClient] Reconnect failed: {e}")
                # Exponential backoff
                self._current_reconnect_delay = min(self._current_reconnect_delay * 2, self._max_reconnect_delay)
                self._schedule_reconnect()

        t = threading.Thread(target=_reconnect, name=f"PassiveBrowserClient-reconnect-{id(self)}", daemon=True)
        _track_appsync_ws_thread(t)
        t.start()

    async def stop(self) -> None:
        with self._lock:
            self._stopped = True
        self._close_existing_ws()


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
        run_id = "test-run-001"
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
