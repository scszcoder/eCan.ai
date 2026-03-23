"""AppSync Realtime WebSocket Subscription Client

Connects to the AWS AppSync realtime WebSocket endpoint and subscribes to
GraphQL subscriptions (e.g. onSkillEditorStreamEvent).  Received events are
relayed to the desktop frontend via the local WebSocket push infrastructure
(AppWebSocketManager / IPCAPI).

Auth: Uses **Cognito token auth** (Authorization header), matching the
pattern used by all other desktop subscriptions (subscribe_cloud_llm_task,
etc.).  The API key is NOT required.

Protocol reference (graphql-ws over AppSync):
  1. Build URL:  wss://<realtime-endpoint>/graphql?header=<b64>&payload=<b64>
  2. Send:       {"type": "connection_init"}
  3. Receive:    {"type": "connection_ack", "payload": {"connectionTimeoutMs": ...}}
  4. Send:       {"id": "<sub-id>", "type": "start", "payload": {"data": "<json>", "extensions": {"authorization": <headers>}}}
  5. Receive:    {"id": "<sub-id>", "type": "start_ack"}
  6. Receive:    {"id": "<sub-id>", "type": "data", "payload": {"data": {...}}}
  7. Send:       {"id": "<sub-id>", "type": "stop"}  (to unsubscribe)
  8. Keep-alive: {"type": "ka"}
"""

from __future__ import annotations

import base64
import json
import ssl
import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse, urlunparse, urlencode, parse_qsl

from utils.logger_helper import logger_helper as logger

try:
    import websocket  # websocket-client (already used by subscribe_cloud_llm_task)
    WEBSOCKET_AVAILABLE = True
except ImportError:
    WEBSOCKET_AVAILABLE = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUB_SKILL_EDITOR_STREAM = """subscription OnSkillEditorStreamEvent($owner: String!) {
  onSkillEditorStreamEvent(owner: $owner) {
    eventId
    owner
    sessionId
    flowgramId
    eventType
    payload
    timestamp
  }
}"""

# Reconnect parameters
RECONNECT_BASE_DELAY = 2      # seconds
RECONNECT_MAX_DELAY = 60      # seconds
RECONNECT_BACKOFF = 1.5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_base64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _derive_realtime_url_and_host(ws_endpoint: str) -> tuple:
    """Convert an AppSync HTTPS endpoint (or WSS) to the realtime WSS URL.

    Returns (realtime_wss_url, api_host) matching the pattern used by
    subscribe_cloud_llm_task in cloud_api.py.
    """
    url = ws_endpoint
    # https://xxx.appsync-api.region.amazonaws.com/graphql → wss://xxx.appsync-realtime-api.region.amazonaws.com/graphql
    if url.startswith("https://") and "appsync-api" in url:
        rest = url[len("https://"):]
        rest = rest.replace("appsync-api", "appsync-realtime-api", 1)
        url = "wss://" + rest
    elif url.startswith("http://"):
        url = "wss://" + url[len("http://"):]

    parsed = urlparse(url)
    # api_host: the normal (non-realtime) AppSync host for the Authorization header
    api_host = parsed.netloc.replace("appsync-realtime-api", "appsync-api")
    return url, api_host


def _build_signed_url(realtime_url: str, header_obj: Dict[str, str]) -> str:
    """Build the full signed WebSocket URL with header/payload query params.

    Matches the URL construction in subscribe_cloud_llm_task.
    """
    parsed = urlparse(realtime_url)
    header_b64 = _to_base64(json.dumps(header_obj))
    payload_b64 = _to_base64(json.dumps({}))
    query = dict(parse_qsl(parsed.query))
    query.update({"header": header_b64, "payload": payload_b64})
    return urlunparse((
        parsed.scheme, parsed.netloc, parsed.path,
        parsed.params, urlencode(query), parsed.fragment,
    ))


def _maybe_parse_awsjson(value: Any) -> Any:
    """Parse an AWSJSON field (string → object). Returns original if already parsed or None."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed and (trimmed.startswith("{") or trimmed.startswith("[")):
            try:
                return json.loads(trimmed)
            except (json.JSONDecodeError, ValueError):
                pass
    return value


# ---------------------------------------------------------------------------
# AppSync Subscription Client
# ---------------------------------------------------------------------------

class AppSyncSubscriptionClient:
    """Manages a persistent WebSocket connection to AppSync realtime API.

    Uses Cognito token auth (same as subscribe_cloud_llm_task).
    Subscribes to ``onSkillEditorStreamEvent`` and relays events to the
    desktop frontend.
    """

    _instance: Optional["AppSyncSubscriptionClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "AppSyncSubscriptionClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._ws = None
                    inst._thread: Optional[threading.Thread] = None
                    inst._running = False
                    inst._owner: Optional[str] = None
                    inst._id_token: Optional[str] = None
                    inst._ws_endpoint: Optional[str] = None
                    inst._api_host: Optional[str] = None
                    inst._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
                    inst._auth_error_detected = False
                    cls._instance = inst
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def configure(
        self,
        owner: str,
        id_token: str,
        ws_endpoint: str,
    ) -> None:
        """Set credentials.  Call before ``start()``.

        Args:
            owner:       User identifier (email) for subscription filter.
            id_token:    Cognito ID token (Authorization header).
            ws_endpoint: AppSync GraphQL endpoint URL (https or wss).
        """
        self._owner = owner
        self._id_token = id_token
        self._ws_endpoint = ws_endpoint
        _, self._api_host = _derive_realtime_url_and_host(ws_endpoint)
        logger.info(
            f"[AppSyncSubClient] Configured: owner={owner}, "
            f"endpoint={ws_endpoint[:60]}..., api_host={self._api_host}"
        )

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback invoked for every subscription event."""
        self._event_handlers.append(handler)

    def start(self) -> None:
        """Start the subscription listener in a background daemon thread."""
        if not WEBSOCKET_AVAILABLE:
            logger.error("[AppSyncSubClient] 'websocket-client' package not installed")
            return
        if self._running:
            logger.debug("[AppSyncSubClient] Already running")
            return
        if not self._id_token or not self._owner:
            logger.warning("[AppSyncSubClient] Cannot start — missing id_token or owner")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_with_retry, daemon=True, name="appsync-sub-client"
        )
        self._thread.start()
        logger.info("[AppSyncSubClient] Background thread started")

    def stop(self) -> None:
        """Stop the subscription listener."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("[AppSyncSubClient] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Background thread: connect with retry
    # ------------------------------------------------------------------

    def _run_with_retry(self) -> None:
        """Connect → subscribe → listen.  Reconnect on failure."""
        delay = RECONNECT_BASE_DELAY
        while self._running:
            try:
                self._connect_and_listen()
                if not self._running:
                    break
                if self._auth_error_detected:
                    logger.warning(
                        "[AppSyncSubClient] Auth error detected on websocket "
                        f"connection, refreshing token and reconnecting in {delay:.0f}s …"
                    )
                    self._refresh_token()
                else:
                    logger.warning(
                        "[AppSyncSubClient] WebSocket closed, "
                        f"reconnecting in {delay:.0f}s …"
                    )
                time.sleep(delay)
                delay = min(delay * RECONNECT_BACKOFF, RECONNECT_MAX_DELAY)
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    f"[AppSyncSubClient] Connection lost ({exc}), "
                    f"reconnecting in {delay:.0f}s …"
                )
                time.sleep(delay)
                delay = min(delay * RECONNECT_BACKOFF, RECONNECT_MAX_DELAY)

                # Refresh token on reconnect (it may have been rotated)
                self._refresh_token()

    def _refresh_token(self) -> None:
        """Re-read the Cognito token from MainWindow (it may have been refreshed)."""
        try:
            from app_context import AppContext
            mainwin = AppContext.get_main_window()
            if mainwin:
                new_token = mainwin.get_auth_token()
                if new_token:
                    self._id_token = new_token
                    logger.debug("[AppSyncSubClient] Token refreshed")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Single connection lifecycle (blocking, runs in daemon thread)
    # ------------------------------------------------------------------

    def _connect_and_listen(self) -> None:
        """Open WebSocket, subscribe, and block until closed.

        Raises ConnectionError if the socket was never successfully opened
        (e.g. connection refused, DNS failure) so that _run_with_retry
        applies exponential back-off instead of spinning.
        """
        realtime_url, api_host = _derive_realtime_url_and_host(self._ws_endpoint)
        self._api_host = api_host

        header_obj = {
            "host": api_host,
            "Authorization": self._id_token,
        }
        signed_url = _build_signed_url(realtime_url, header_obj)

        logger.info(f"[AppSyncSubClient] Connecting to {realtime_url[:80]}…")

        self._connection_opened = False

        ws = websocket.WebSocketApp(
            signed_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
            subprotocols=["graphql-ws"],
        )
        self._ws = ws
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        if not self._connection_opened:
            raise ConnectionError("WebSocket connection was never established")

    # ------------------------------------------------------------------
    # WebSocketApp callbacks
    # ------------------------------------------------------------------

    def _on_open(self, ws) -> None:
        self._connection_opened = True
        logger.info("[AppSyncSubClient] WebSocket opened, sending connection_init")
        try:
            ws.send(json.dumps({"type": "connection_init", "payload": {}}))
        except Exception as e:
            logger.error(f"[AppSyncSubClient] Failed to send connection_init: {e}")

    def _on_error(self, ws, error) -> None:
        logger.error(f"[AppSyncSubClient] WebSocket error: {error}")

    def _on_close(self, ws, status_code, msg) -> None:
        if status_code == 1000:
            logger.info(f"[AppSyncSubClient] WebSocket closed normally: code={status_code}, msg={msg}")
        else:
            logger.warning(f"[AppSyncSubClient] WebSocket closed: code={status_code}, msg={msg}")
        self._ws = None

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except Exception:
            return

        msg_type = data.get("type")

        if msg_type == "connection_ack":
            self._auth_error_detected = False
            timeout_ms = data.get("payload", {}).get("connectionTimeoutMs", 300_000)
            logger.info(f"[AppSyncSubClient] connection_ack (timeout={timeout_ms}ms)")
            # Now subscribe
            self._send_subscription(ws)
            return

        if msg_type == "ka":
            return

        if msg_type == "start_ack":
            logger.info(f"[AppSyncSubClient] Subscription confirmed: {data.get('id')}")
            return

        if msg_type == "data":
            self._handle_data_message(data)
            return

        if msg_type in ("error", "connection_error"):
            logger.error(f"[AppSyncSubClient] Error from AppSync: {data}")
            payload = data.get("payload") if isinstance(data, dict) else None
            err_text = json.dumps(payload or data, ensure_ascii=False)
            if "UnauthorizedException" in err_text or "Token has expired" in err_text:
                self._auth_error_detected = True
                self._refresh_token()
                try:
                    ws.close()
                except Exception:
                    pass
            return

        logger.debug(f"[AppSyncSubClient] Unhandled message type: {msg_type}")

    def _send_subscription(self, ws) -> None:
        """Send the 'start' message to subscribe to onSkillEditorStreamEvent."""
        sub_id = "sub-se-stream-1"
        header_obj = {
            "host": self._api_host,
            "Authorization": self._id_token,
        }
        data_obj = {
            "query": SUB_SKILL_EDITOR_STREAM,
            "variables": {"owner": self._owner},
        }
        start_payload = {
            "id": sub_id,
            "type": "start",
            "payload": {
                "data": json.dumps(data_obj),
                "extensions": {"authorization": header_obj},
            },
        }
        logger.info(f"[AppSyncSubClient] Subscribing: {sub_id} (owner={self._owner})")
        try:
            ws.send(json.dumps(start_payload))
        except Exception as e:
            logger.error(f"[AppSyncSubClient] Failed to send subscription start: {e}")

    # ------------------------------------------------------------------
    # Event dispatch
    # ------------------------------------------------------------------

    def _handle_data_message(self, msg: Dict[str, Any]) -> None:
        """Process a 'data' message from AppSync."""
        payload = msg.get("payload", {}).get("data", {})

        event = payload.get("onSkillEditorStreamEvent")
        if not event:
            return

        # Parse AWSJSON payload field
        event["payload"] = _maybe_parse_awsjson(event.get("payload"))

        event_type = (event.get("eventType") or "").strip()
        session_id = (event.get("sessionId") or "").strip()

        logger.info(
            f"[AppSyncSubClient] Received event: type={event_type}, "
            f"session={session_id[:12]}…"
        )

        # Relay to desktop frontend
        self._relay_to_frontend(event)

        # Notify registered handlers
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.debug(f"[AppSyncSubClient] Handler error: {exc}")

    def _relay_to_frontend(self, event: Dict[str, Any]) -> None:
        """Push the AppSync event to the desktop frontend through the local
        WebSocket (IPCAPI + AppWebSocketManager)."""
        event_type = (event.get("eventType") or "").strip()
        session_id = (event.get("sessionId") or "").strip()
        payload = event.get("payload") or {}

        if not event_type:
            return

        try:
            from gui.ipc.api import IPCAPI
            ipc = IPCAPI.get_instance()
        except Exception:
            ipc = None

        try:
            if event_type == "skill_editor.chat.stream_chunk":
                if ipc:
                    ipc.push_skill_editor_chat_chunk(
                        session_id=session_id,
                        message_id=payload.get("messageId", ""),
                        chunk=payload.get("chunk", ""),
                        chunk_index=payload.get("chunkIndex", 0),
                    )

            elif event_type == "skill_editor.chat.stream_end":
                logger.debug(
                    f"[AppSyncSubClient] stream_end payload keys: "
                    f"{list(payload.keys()) if isinstance(payload, dict) else type(payload)}"
                )
                # The cloud Lambda's stream_end only carries messageId +
                # fullContent.  The structured data (clarification, a2ui,
                # plan) lives in the message metadata stored in DynamoDB.
                # Re-fetch the latest message to get it.
                enriched = dict(payload) if isinstance(payload, dict) else {}
                if session_id and not enriched.get("clarification"):
                    try:
                        enriched = self._enrich_stream_end(session_id, enriched)
                    except Exception as exc:
                        logger.debug(f"[AppSyncSubClient] enrich failed: {exc}")

                if ipc:
                    ipc.push_skill_editor_chat_done(
                        session_id=session_id,
                        message_id=enriched.get("messageId", payload.get("messageId", "")),
                        full_content=enriched.get("fullContent", payload.get("fullContent", "")),
                        extra=enriched,
                    )

                # Also forward flowgram / plan / validation if present
                flowgram = payload.get("flowgram")
                if flowgram and ipc:
                    ipc.push_skill_editor_canvas_command(
                        session_id=session_id,
                        command_type="canvas.load_flowgram_data",
                        payload={"flowgram": flowgram},
                    )

            elif event_type == "skill_editor.chat.error":
                if ipc:
                    ipc.push_skill_editor_chat_error(
                        session_id=session_id,
                        error_code=payload.get("code", "CLOUD_ERROR"),
                        error_message=payload.get("message", "Unknown error"),
                    )

            elif event_type == "skill_editor.event":
                if ipc:
                    ipc.push_skill_editor_canvas_command(
                        session_id=session_id,
                        command_type=payload.get("commandType", event_type),
                        payload=payload,
                    )

            else:
                # Generic: broadcast raw event via local WebSocket
                try:
                    from gui.LocalServer import app_ws_manager
                    app_ws_manager.broadcast_sync(
                        event_type,
                        payload,
                        channel_id=f"session:{session_id}" if session_id else None,
                    )
                except Exception:
                    pass

        except Exception as exc:
            logger.warning(
                f"[AppSyncSubClient] Failed to relay event {event_type}: {exc}"
            )

    def _enrich_stream_end(self, session_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
        """Re-fetch the latest message from cloud history to get structured
        metadata (clarification, a2ui, plan, state) that the subscription's
        stream_end payload does not carry."""
        from gui.ipc.w2p_handlers.skill_editor_cloud_relay import (
            relay_get_history, _parse_awsjson,
        )

        history = relay_get_history(session_id)
        if not history:
            return base

        messages = history.get("messages") or []
        if not messages:
            return base

        # Take the last assistant message
        last_msg = None
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "assistant":
                last_msg = m
                break
        if not last_msg:
            return base

        raw_metadata = last_msg.get("metadata")
        logger.info(
            f"[AppSyncSubClient] enrich: raw metadata snippet="
            f"{str(raw_metadata)[:300] if raw_metadata else 'None'}"
        )

        metadata = _parse_awsjson(raw_metadata)
        if not isinstance(metadata, dict):
            logger.debug(
                f"[AppSyncSubClient] enrich: metadata not a dict, "
                f"type={type(metadata)}"
            )
            return base

        logger.info(
            f"[AppSyncSubClient] enrich: metadata keys={list(metadata.keys())}"
        )

        # Merge structured fields from metadata into the base payload
        enriched = dict(base)
        for key in ("clarification", "a2ui", "plan", "state", "intent",
                     "flowgram", "validation", "sessionName"):
            val = metadata.get(key)
            if val is not None:
                enriched[key] = _parse_awsjson(val) if isinstance(val, str) else val

        return enriched


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
appsync_sub_client = AppSyncSubscriptionClient()


# ---------------------------------------------------------------------------
# Convenience: start after MainWindow init
# ---------------------------------------------------------------------------

def start_appsync_subscriptions_for_desktop() -> None:
    """Called from MainWindow init to start cloud subscriptions on desktop.

    Reads Cognito token + WS endpoint from the running MainWindow and starts
    the background subscription listener.
    """
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            logger.debug("[AppSyncSubClient] No MainWindow — skipping subscription start")
            return

        owner = getattr(mainwin, "user", None) or ""
        if not owner:
            logger.debug("[AppSyncSubClient] No user — skipping subscription start")
            return

        id_token = ""
        ws_endpoint = ""

        try:
            id_token = mainwin.get_auth_token() or ""
        except Exception:
            pass
        try:
            ws_endpoint = mainwin.getWSApiEndpoint() or ""
        except Exception:
            pass
        if not ws_endpoint:
            try:
                ws_endpoint = mainwin.getWanApiEndpoint() or ""
            except Exception:
                pass

        if not id_token:
            logger.warning("[AppSyncSubClient] No auth token — cannot subscribe to AppSync")
            return
        if not ws_endpoint:
            logger.warning("[AppSyncSubClient] No WS endpoint — cannot subscribe to AppSync")
            return

        appsync_sub_client.configure(
            owner=owner,
            id_token=id_token,
            ws_endpoint=ws_endpoint,
        )
        appsync_sub_client.start()

    except Exception as exc:
        logger.warning(f"[AppSyncSubClient] Failed to start: {exc}\n{traceback.format_exc()}")
