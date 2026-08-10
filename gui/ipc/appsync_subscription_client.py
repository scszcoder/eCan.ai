"""AppSync Realtime WebSocket Subscription Client

Connects to the AppSync-compatible realtime WebSocket endpoint and subscribes
to GraphQL subscriptions (e.g. onSkillEditorStreamEvent).  Received events are
relayed to the desktop frontend via the local WebSocket push infrastructure
(AppWebSocketManager / IPCAPI).

Both CN (TCB TCS WS) and Intl (AWS AppSync) use the same client — only the
auth mechanism differs. CN uses TCB JWT Bearer token; Intl uses Cognito ID token.

GraphQL-ws subprotocol is used for both CN and Intl connections.
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


# Module-level singleton
appsync_sub_client = AppSyncSubscriptionClient()


# ---------------------------------------------------------------------------
# Convenience: start after MainWindow init
# ---------------------------------------------------------------------------

def start_appsync_subscriptions_for_desktop() -> None:
    """Called from MainWindow init to start cloud subscriptions on desktop.

    Reads auth credentials + WS endpoint from the running MainWindow and starts
    the background subscription listener.  CN (TCB) and Intl (AWS AppSync) both
    use the same AppSyncSubscriptionClient with graphql-ws subprotocol — only the
    auth mechanism differs.
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

        # CN: TCB JWT Bearer token; Intl: Cognito ID token
        id_token = ""
        try:
            id_token = mainwin.get_auth_token() or ""
        except Exception:
            pass
        if not id_token:
            logger.warning("[AppSyncSubClient] No auth token — cannot subscribe")
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
