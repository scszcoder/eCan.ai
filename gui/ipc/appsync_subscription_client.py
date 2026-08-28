"""AppSync Realtime WebSocket Subscription Client

Connects to the AWS AppSync realtime WebSocket endpoint and subscribes to
GraphQL subscriptions (e.g. onSkillEditorStreamEvent).  Received events are
relayed to the desktop frontend via the local WebSocket push infrastructure
(AppWebSocketManager / IPCAPI).

Auth: Supports two modes selected via ``auth_type`` in ``configure()``:
  - "cognito" : Cognito ID token via Authorization header (Intl users).
  - "cloudbase" : CloudBase API Key via x-api-key header (CN users).

CN Fallback: When WebSocket subscription is unavailable (CN version with
no AppSync-compatible endpoint), falls back to HTTP polling mode.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import ssl
from utils.app_env import is_cn
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

import requests

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
# CN WebSocket Client (TCB API Gateway WebSocket)
# ---------------------------------------------------------------------------

class CNWebSocketClient:
    """CN version WebSocket client for real-time events.

    Uses TCB API Gateway WebSocket to receive real-time events,
    providing the same functionality as AppSync Subscriptions.
    """

    _instance: Optional["CNWebSocketClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CNWebSocketClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._ws = None
                    inst._thread: Optional[threading.Thread] = None
                    inst._running = False
                    inst._owner: Optional[str] = None
                    inst._token: Optional[str] = None
                    inst._ws_endpoint: Optional[str] = None
                    inst._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
                    inst._reconnect_delay = RECONNECT_BASE_DELAY
                    inst._session = requests.Session()
                    cls._instance = inst
        return cls._instance

    def configure(
        self,
        owner: str,
        token: str,
        ws_endpoint: str,
    ) -> None:
        """Configure the WebSocket client.

        Args:
            owner: User identifier for filtering events.
            token: TCB auth token.
            ws_endpoint: TCB WebSocket endpoint URL.
        """
        self._owner = owner
        self._token = token
        self._ws_endpoint = ws_endpoint
        logger.info(
            f"[CNWebSocketClient] Configured: owner={owner}, endpoint={ws_endpoint[:60]}..."
        )

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback invoked for every subscription event."""
        self._event_handlers.append(handler)

    def start(self) -> None:
        """Start the WebSocket connection in a background daemon thread."""
        if self._running:
            logger.debug("[CNWebSocketClient] Already running")
            return
        if not WEBSOCKET_AVAILABLE:
            logger.error("[CNWebSocketClient] 'websocket-client' package not installed")
            return
        if not self._owner or not self._token or not self._ws_endpoint:
            logger.warning("[CNWebSocketClient] Cannot start — missing config")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_with_retry, daemon=True, name="cn-ws-client"
        )
        self._thread.start()
        logger.info("[CNWebSocketClient] Background thread started")

    def stop(self) -> None:
        """Stop the WebSocket connection."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("[CNWebSocketClient] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_with_retry(self) -> None:
        """Connect → subscribe → listen. Reconnect on failure."""
        while self._running:
            try:
                self._connect_and_listen()
                if not self._running:
                    break
                logger.warning(
                    f"[CNWebSocketClient] WebSocket closed, reconnecting in {self._reconnect_delay:.0f}s..."
                )
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * RECONNECT_BACKOFF, RECONNECT_MAX_DELAY)
            except Exception as exc:
                if not self._running:
                    break
                logger.warning(
                    f"[CNWebSocketClient] Connection error ({exc}), reconnecting in {self._reconnect_delay:.0f}s..."
                )
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * RECONNECT_BACKOFF, RECONNECT_MAX_DELAY)

    def _connect_and_listen(self) -> None:
        """Open WebSocket, subscribe, and block until closed."""
        logger.info(f"[CNWebSocketClient] Connecting to {self._ws_endpoint}...")

        # Build WebSocket URL with auth token
        parsed = urlparse(self._ws_endpoint)
        query = dict(parse_qsl(parsed.query))
        query['token'] = self._token
        ws_url = urlunparse((
            parsed.scheme.replace('https', 'wss'),
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment
        ))

        self._connection_opened = False

        ws = websocket.WebSocketApp(
            ws_url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
            on_open=self._on_open,
        )
        self._ws = ws
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        if not self._connection_opened:
            raise ConnectionError("WebSocket connection was never established")

    def _on_open(self, ws) -> None:
        self._connection_opened = True
        self._reconnect_delay = RECONNECT_BASE_DELAY
        logger.info("[CNWebSocketClient] WebSocket opened")

        # Subscribe to all event channels
        channels = [
            'skill-editor-stream',
            'task-status',
            'a2a-message',
            'passive-command',
            'account-notification',
        ]
        for channel in channels:
            ws.send(json.dumps({
                'action': 'subscribe',
                'channel': channel
            }))
            logger.info(f"[CNWebSocketClient] Subscribed to {channel}")

    def _on_error(self, ws, error) -> None:
        logger.error(f"[CNWebSocketClient] WebSocket error: {error}")

    def _on_close(self, ws, status_code, msg) -> None:
        logger.info(f"[CNWebSocketClient] WebSocket closed: code={status_code}, msg={msg}")
        self._ws = None

    def _on_message(self, ws, message: str) -> None:
        try:
            data = json.loads(message)
        except Exception:
            return

        # Handle ping
        if data.get('action') == 'ping':
            ws.send(json.dumps({'action': 'pong'}))
            return

        # Handle event messages
        event_type = data.get('type', '')
        event_data = data.get('data', {})

        if not event_type:
            return

        logger.info(f"[CNWebSocketClient] Received event: type={event_type}")

        # Parse payload
        event_data['payload'] = _maybe_parse_awsjson(event_data.get('payload'))

        # Relay to frontend
        self._relay_to_frontend(event_data)

        # Notify handlers
        for handler in self._event_handlers:
            try:
                handler(event_data)
            except Exception as exc:
                logger.debug(f"[CNWebSocketClient] Handler error: {exc}")

    def _relay_to_frontend(self, event: Dict[str, Any]) -> None:
        """Push the event to the desktop frontend."""
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
                enriched = dict(payload) if isinstance(payload, dict) else {}
                if session_id and not enriched.get("clarification"):
                    try:
                        enriched = self._enrich_stream_end(session_id, enriched)
                    except Exception as exc:
                        logger.debug(f"[CNWebSocketClient] enrich failed: {exc}")

                if ipc:
                    ipc.push_skill_editor_chat_done(
                        session_id=session_id,
                        message_id=enriched.get("messageId", payload.get("messageId", "")),
                        full_content=enriched.get("fullContent", payload.get("fullContent", "")),
                        extra=enriched,
                    )

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
            logger.warning(f"[CNWebSocketClient] Failed to relay event {event_type}: {exc}")

    def _enrich_stream_end(self, session_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
        """Re-fetch the latest message from cloud history."""
        try:
            from gui.ipc.w2p_handlers.skill_editor_cloud_relay import (
                relay_get_history, _parse_awsjson,
            )
            history = relay_get_history(session_id)
            if not history:
                return base

            messages = history.get("messages") or []
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    metadata = _parse_awsjson(m.get("metadata"))
                    if isinstance(metadata, dict):
                        enriched = dict(base)
                        for key in ("clarification", "a2ui", "plan", "state", "intent",
                                    "flowgram", "validation", "sessionName"):
                            val = metadata.get(key)
                            if val is not None:
                                enriched[key] = _parse_awsjson(val) if isinstance(val, str) else val
                        return enriched
                    break
        except Exception:
            pass
        return base


# Singleton instance
cn_ws_client = CNWebSocketClient()


# ---------------------------------------------------------------------------
# CN Polling Client (Legacy fallback - deprecated, use CNWebSocketClient)
# ---------------------------------------------------------------------------

class CNPollingClient:
    """CN version HTTP polling client for real-time events.

    Since TCB does not support AppSync-compatible WebSocket subscriptions,
    this client polls the TCB GraphQL endpoint at regular intervals to
    check for new events.

    Events are relayed to the same handlers as the WebSocket client.
    """

    _instance: Optional["CNPollingClient"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "CNPollingClient":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._thread: Optional[threading.Thread] = None
                    inst._running = False
                    inst._owner: Optional[str] = None
                    inst._token: Optional[str] = None
                    inst._endpoint: Optional[str] = None
                    inst._event_handlers: List[Callable[[Dict[str, Any]], None]] = []
                    inst._last_event_id: Optional[str] = None
                    inst._poll_interval = 5  # seconds
                    # Auth-failure tracking: when token is rejected we back off
                    # exponentially instead of spamming the server every 5s.
                    # This caps log noise AND avoids hammering the auth endpoint.
                    inst._consecutive_auth_failures = 0
                    inst._auth_backoff_until = 0.0
                    inst._session = requests.Session()
                    inst._session.headers.update({
                        'Content-Type': 'application/json',
                        'cache-control': 'no-cache'
                    })
                    cls._instance = inst
        return cls._instance

    def configure(
        self,
        owner: str,
        token: str,
        endpoint: str,
        poll_interval: int = 5,
    ) -> None:
        """Configure the polling client.

        Args:
            owner: User identifier for filtering events.
            token: TCB auth token (Bearer token).
            endpoint: TCB GraphQL endpoint URL.
            poll_interval: Polling interval in seconds (default: 5).
        """
        self._owner = owner
        self._token = token
        self._endpoint = endpoint
        self._poll_interval = max(1, poll_interval)
        logger.info(
            f"[CNPollingClient] Configured: owner={owner}, endpoint={endpoint[:60]}..., "
            f"poll_interval={self._poll_interval}s"
        )

    def add_event_handler(self, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register a callback invoked for every subscription event."""
        self._event_handlers.append(handler)

    def start(self) -> None:
        """Start the polling loop in a background daemon thread."""
        if self._running:
            logger.debug("[CNPollingClient] Already running")
            return
        if not self._owner or not self._token or not self._endpoint:
            logger.warning("[CNPollingClient] Cannot start — missing config")
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="cn-polling-client"
        )
        self._thread.start()
        logger.info("[CNPollingClient] Background thread started")

    def stop(self) -> None:
        """Stop the polling loop."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        self._thread = None
        logger.info("[CNPollingClient] Stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _run_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            # Respect auth-failure backoff: if we're in a backoff window,
            # sleep until it expires instead of hammering the server.
            now = time.time()
            if self._auth_backoff_until > now:
                sleep_for = min(self._auth_backoff_until - now, 5.0)
                for _ in range(int(sleep_for * 10)):
                    if not self._running:
                        return
                    time.sleep(0.1)
                continue

            try:
                events = self._poll_events()
                for event in events:
                    self._handle_event(event)
            except Exception as exc:
                logger.warning(f"[CNPollingClient] Poll error: {exc}")

            # Sleep in small increments to allow quick shutdown
            for _ in range(self._poll_interval * 10):
                if not self._running:
                    break
                time.sleep(0.1)

    def _is_auth_error(self, errors: List[Dict[str, Any]]) -> bool:
        """Detect UNAUTHENTICATED errors from TCB GraphQL responses."""
        if not errors:
            return False
        for err in errors:
            ext = err.get('extensions') or {}
            code = err.get('errorType') or err.get('code') or ext.get('code')
            msg = (err.get('message') or '').lower()
            if code in ('UNAUTHENTICATED', 'UnauthorizedException'):
                return True
            if 'unauthenticated' in msg or 'invalid or expired' in msg:
                return True
        return False

    def _refresh_token(self) -> Optional[str]:
        """Try to obtain a refreshed auth token from the main window.

        Returns the new token on success, None otherwise. The new token is
        also stored on the polling client so subsequent polls use it.
        """
        try:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if not main_window or not hasattr(main_window, 'get_auth_token'):
                return None
            new_token = main_window.get_auth_token()
            if new_token and new_token != self._token:
                logger.info("[CNPollingClient] Token refreshed from main window")
                self._token = new_token
                return new_token
            return new_token if new_token else None
        except Exception as exc:
            logger.debug(f"[CNPollingClient] Token refresh failed: {exc}")
            return None

    def _poll_events(self) -> List[Dict[str, Any]]:
        """Poll the TCB endpoint for new events.

        Queries the skill_editor_events collection for new events since
        the last poll.
        """
        query = """
        query GetSkillEditorEvents($sessionId: String!, $since: String) {
            getSkillEditorEvents(sessionId: $sessionId, since: $since) {
                eventId
                owner
                sessionId
                flowgramId
                eventType
                payload
                timestamp
            }
        }
        """

        since = self._last_event_id or ""
        variables = {
            "sessionId": self._owner,  # Use owner as session filter
            "since": since if since else None,
        }

        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._token}',
                'cache-control': 'no-cache'
            }
            response = self._session.post(
                self._endpoint,
                headers=headers,
                json={'query': query, 'variables': variables},
                timeout=30,
            )

            if response.status_code != 200:
                logger.warning(f"[CNPollingClient] Poll failed: {response.status_code}")
                return []

            data = response.json()
            if 'errors' in data:
                errors = data['errors']
                if self._is_auth_error(errors):
                    # Real bug: token is rejected. Try to refresh once, and if
                    # it still fails, back off so we don't hammer the server.
                    self._consecutive_auth_failures += 1
                    refreshed = self._refresh_token()
                    if refreshed:
                        # Reset failure counter so next poll tries fresh token.
                        self._consecutive_auth_failures = 0
                        self._auth_backoff_until = 0.0
                        # Don't return [] here — let the next poll cycle try
                        # the new token. The current event stream is stale
                        # anyway since auth just failed.
                    else:
                        # Exponential backoff capped at 5 minutes:
                        #   5s, 10s, 20s, 40s, 80s, 160s, 300s, 300s, ...
                        backoff = min(5 * (2 ** min(self._consecutive_auth_failures - 1, 6)), 300)
                        self._auth_backoff_until = time.time() + backoff
                        logger.warning(
                            f"[CNPollingClient] Auth failed {self._consecutive_auth_failures}× consecutively; "
                            f"backing off {backoff}s until {time.strftime('%H:%M:%S', time.localtime(self._auth_backoff_until))}"
                        )
                else:
                    # Non-auth error: log it but keep polling at normal rate.
                    logger.warning(f"[CNPollingClient] GraphQL errors: {errors}")
                return []

            # Successful poll: reset failure counter and backoff.
            if self._consecutive_auth_failures > 0:
                logger.info("[CNPollingClient] Auth recovered, resuming normal polling")
                self._consecutive_auth_failures = 0
                self._auth_backoff_until = 0.0

            events = data.get('data', {}).get('getSkillEditorEvents', [])
            if events and isinstance(events, list):
                # Update last event ID for next poll
                self._last_event_id = events[-1].get('eventId')

            return events if isinstance(events, list) else []

        except Exception as exc:
            logger.debug(f"[CNPollingClient] Poll request failed: {exc}")
            return []

    def _handle_event(self, event: Dict[str, Any]) -> None:
        """Process and dispatch a polled event."""
        if not event:
            return

        # Parse payload if it's a JSON string
        event["payload"] = _maybe_parse_awsjson(event.get("payload"))

        event_type = (event.get("eventType") or "").strip()
        session_id = (event.get("sessionId") or "").strip()

        logger.info(
            f"[CNPollingClient] Received event: type={event_type}, "
            f"session={session_id[:12] if session_id else 'N/A'}..."
        )

        # Relay to desktop frontend (same as WebSocket client)
        self._relay_to_frontend(event)

        # Notify registered handlers
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as exc:
                logger.debug(f"[CNPollingClient] Handler error: {exc}")

    def _relay_to_frontend(self, event: Dict[str, Any]) -> None:
        """Push the event to the desktop frontend through the local
        WebSocket (IPCAPI + AppWebSocketManager).

        Mirrors the behavior of AppSyncSubscriptionClient._relay_to_frontend().
        """
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
                enriched = dict(payload) if isinstance(payload, dict) else {}
                if session_id and not enriched.get("clarification"):
                    try:
                        enriched = self._enrich_stream_end(session_id, enriched)
                    except Exception as exc:
                        logger.debug(f"[CNPollingClient] enrich failed: {exc}")

                if ipc:
                    ipc.push_skill_editor_chat_done(
                        session_id=session_id,
                        message_id=enriched.get("messageId", payload.get("messageId", "")),
                        full_content=enriched.get("fullContent", payload.get("fullContent", "")),
                        extra=enriched,
                    )

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
            logger.warning(f"[CNPollingClient] Failed to relay event {event_type}: {exc}")

    def _enrich_stream_end(self, session_id: str, base: Dict[str, Any]) -> Dict[str, Any]:
        """Re-fetch the latest message from cloud history to get structured
        metadata (clarification, a2ui, plan, state)."""
        try:
            from gui.ipc.w2p_handlers.skill_editor_cloud_relay import (
                relay_get_history, _parse_awsjson,
            )
            history = relay_get_history(session_id)
            if not history:
                return base

            messages = history.get("messages") or []
            last_msg = None
            for m in reversed(messages):
                if isinstance(m, dict) and m.get("role") == "assistant":
                    last_msg = m
                    break
            if not last_msg:
                return base

            raw_metadata = last_msg.get("metadata")
            metadata = _parse_awsjson(raw_metadata)
            if not isinstance(metadata, dict):
                return base

            enriched = dict(base)
            for key in ("clarification", "a2ui", "plan", "state", "intent",
                         "flowgram", "validation", "sessionName"):
                val = metadata.get(key)
                if val is not None:
                    enriched[key] = _parse_awsjson(val) if isinstance(val, str) else val

            return enriched
        except Exception:
            return base


# Singleton instance
cn_polling_client = CNPollingClient()


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
                    inst._auth_type: Optional[str] = None   # "cognito" or "cloudbase"
                    inst._id_token: Optional[str] = None
                    inst._api_key: Optional[str] = None      # CloudBase API Key
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
        auth_type: str = "cognito",
        ws_endpoint: str = "",
        id_token: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        """Set credentials. Call before ``start()``.

        Args:
            owner:       User identifier (email) for subscription filter.
            auth_type:   "cognito" (Intl, default) or "cloudbase" (CN).
            ws_endpoint: AppSync GraphQL endpoint URL (https or wss).
            id_token:    Cognito ID token (required when auth_type="cognito").
            api_key:     CloudBase API Key (required when auth_type="cloudbase").
        """
        self._owner = owner
        self._auth_type = auth_type
        self._id_token = id_token
        self._api_key = api_key
        self._ws_endpoint = ws_endpoint
        _, self._api_host = _derive_realtime_url_and_host(ws_endpoint)
        logger.info(
            f"[AppSyncSubClient] Configured: owner={owner}, auth_type={auth_type}, "
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
        if self._auth_type == "cognito":
            if not self._id_token or not self._owner:
                logger.warning("[AppSyncSubClient] Cannot start — missing id_token or owner")
                return
        elif self._auth_type == "cloudbase":
            if not self._api_key or not self._owner:
                logger.warning("[AppSyncSubClient] Cannot start — missing api_key or owner")
                return
        elif self._auth_type is None:
            # Legacy call without auth_type — assume cognito (backwards compat)
            if not self._id_token or not self._owner:
                logger.warning("[AppSyncSubClient] Cannot start — missing id_token or owner")
                return
        else:
            logger.warning(f"[AppSyncSubClient] Unknown auth_type: {self._auth_type}")
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
        """Re-read the Cognito token from MainWindow (it may have been refreshed).

        For cloudbase auth the API key does not expire, so this is a no-op.
        """
        if self._auth_type == "cloudbase":
            return
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

    def _build_auth_headers(self) -> Dict[str, str]:
        """Build the auth headers for the subscription payload based on auth_type."""
        if self._auth_type == "cloudbase":
            return {"host": self._api_host, "x-api-key": self._api_key or ""}
        # cognito (default) or None (legacy)
        return {"host": self._api_host, "Authorization": self._id_token or ""}

    def _connect_and_listen(self) -> None:
        """Open WebSocket, subscribe, and block until closed.

        Raises ConnectionError if the socket was never successfully opened
        (e.g. connection refused, DNS failure) so that _run_with_retry
        applies exponential back-off instead of spinning.
        """
        realtime_url, api_host = _derive_realtime_url_and_host(self._ws_endpoint)
        self._api_host = api_host

        header_obj = self._build_auth_headers()
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
        header_obj = self._build_auth_headers()
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
                     "flowgram", "validation", "sessionName",
                     # Cloud-proposed CLI command (agent/task CRUD)
                     "cli_command", "requires_confirmation", "proposal"):
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

    Reads auth credentials + WS endpoint from the running MainWindow and starts
    the background subscription listener.  Auth type is determined by ECAN_APP_ID:
      - ECAN_APP_ID=cn  → CNWebSocketClient (TCB API Gateway WebSocket)
      - otherwise        → AppSyncSubscriptionClient (AWS AppSync WebSocket)
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

        endpoint = ""
        try:
            endpoint = mainwin.getWanApiEndpoint() or ""
        except Exception:
            pass
        if not endpoint:
            logger.warning("[AppSyncSubClient] No endpoint — cannot subscribe")
            return

        is_cn_flag = is_cn()
        if is_cn_flag:
            # CN version: use TCB WebSocket client
            token = _get_cloudbase_token()
            if not token:
                logger.warning("[AppSyncSubClient] CN: no token available — skipping")
                return

            # Get WebSocket endpoint for TCB
            ws_endpoint = _get_tcb_websocket_endpoint()
            if not ws_endpoint:
                logger.warning("[AppSyncSubClient] CN: no WebSocket endpoint — falling back to polling")
                # Fallback to polling if WebSocket not available
                cn_polling_client.configure(
                    owner=owner,
                    token=token,
                    endpoint=endpoint,
                    poll_interval=5,
                )
                cn_polling_client.start()
                return

            logger.info(f"[AppSyncSubClient] CN detected — using TCB WebSocket client")
            cn_ws_client.configure(
                owner=owner,
                token=token,
                ws_endpoint=ws_endpoint,
            )
            cn_ws_client.start()
        else:
            # Intl version: use WebSocket client
            id_token = ""
            try:
                id_token = mainwin.get_auth_token() or ""
            except Exception:
                pass
            if not id_token:
                logger.warning("[AppSyncSubClient] Intl: no auth token — cannot subscribe")
                return
            appsync_sub_client.configure(
                owner=owner,
                auth_type="cognito",
                ws_endpoint=endpoint,
                id_token=id_token,
            )
            appsync_sub_client.start()

    except Exception as exc:
        logger.warning(f"[AppSyncSubClient] Failed to start: {exc}\n{traceback.format_exc()}")


def _get_tcb_websocket_endpoint() -> Optional[str]:
    """Get the TCB API Gateway WebSocket endpoint from config."""
    try:
        import yaml
        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "apps", "cn", "config", "auth_config.yml",
        )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("CLOUDBASE", {}).get("WEBSOCKET_ENDPOINT") or ""
    except Exception:
        return None


def _get_cloudbase_token() -> Optional[str]:
    """Get the TCB auth token from AuthManager."""
    try:
        from auth.auth_manager import AuthManager
        auth_mgr = AuthManager()
        tokens = auth_mgr.get_tokens()
        if not tokens:
            return None

        # Try various token field names
        for key in ('id_token', 'IdToken', 'access_token', 'AccessToken',
                     'token', 'session_token'):
            token = tokens.get(key)
            if token and isinstance(token, str):
                return token

        # Try nested AuthenticationResult
        auth_result = tokens.get('AuthenticationResult') or tokens.get('authenticationResult')
        if auth_result and isinstance(auth_result, dict):
            for key in ('IdToken', 'id_token', 'AccessToken', 'access_token'):
                token = auth_result.get(key)
                if token and isinstance(token, str):
                    return token

        return None
    except Exception:
        return None


def _get_cloudbase_appsync_api_key() -> Optional[str]:
    """Read the CloudBase AppSync API Key from auth_config.yml."""
    try:
        import yaml
        cfg_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "apps", "cn", "config", "auth_config.yml",
        )
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        return cfg.get("APPSYNC_API_KEY") or cfg.get("CLOUDBASE", {}).get("APPSYNC_API_KEY") or ""
    except Exception:
        return None
