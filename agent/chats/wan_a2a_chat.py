"""
wan_a2a_chat.py - A2A Messaging over Cloud (CN/Intl unified)

使用统一的 CloudEndpointConfig 端点驱动:
  - CN:  TCB CloudBase WebSocket (graphql-ws protocol)
  - Intl: AWS AppSync GraphQL WebSocket (graphql-ws protocol)

执行逻辑完全一致,仅配置文件不同。
"""

import json
import ssl
import asyncio
import aiohttp
import base64
import traceback
import os
import certifi
import nest_asyncio
import websocket as ws_client_module
import sys as _sys

# nest_asyncio.apply() patches asyncio process-wide and, on Python 3.12+, makes
# asyncio.current_task() return None inside coroutines driven by run_until_complete
# — every asyncio.wait_for/asyncio.timeout then raises
# "RuntimeError: Timeout should be used inside a task". This module itself does no
# nested run_until_complete, so on 3.12+ we skip it entirely (no-op). Kept for <3.12
# where it was actually relied upon.
if _sys.version_info < (3, 12):
    import nest_asyncio
    nest_asyncio.apply()

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4
from agent.a2a.langgraph_agent.utils import FileContent, TaskSendParams
from a2a.types import Message, TextPart, FilePart, DataPart, Part
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.endpoints import get_endpoint_config, _appsync_ws_url


# =============================================================================
# GraphQL Queries/Mutations
# =============================================================================

def gen_a2a_send_message_mutation() -> str:
    """GraphQL mutation for sending an A2A message."""
    return """
    mutation SendA2AMessage($input: A2AMessageInput!) {
        sendA2AMessage(input: $input) {
            id channelId sessionId senderId recipientId
            message {
                role parts {
                    type text
                    file { name mimeType bytes uri }
                    data metadata
                }
                metadata
            }
            acceptedOutputModes historyLength metadata timestamp
        }
    }
    """


def gen_a2a_subscription_query() -> str:
    """GraphQL subscription for receiving A2A messages."""
    return """
    subscription OnA2AMessageReceived($channelId: String!) {
        onA2AMessageReceived(channelId: $channelId) {
            id channelId sessionId senderId recipientId
            message {
                role parts {
                    type text
                    file { name mimeType bytes uri }
                    data metadata
                }
                metadata
            }
            acceptedOutputModes historyLength metadata timestamp
        }
    }
    """


def gen_a2a_get_messages_query() -> str:
    """GraphQL query for fetching A2A message history."""
    return """
    query GetA2AMessages($channelId: String!, $limit: Int, $nextToken: String) {
        getA2AMessages(channelId: $channelId, limit: $limit, nextToken: $nextToken) {
            items {
                id channelId sessionId senderId recipientId
                message {
                    role parts {
                        type text
                        file { name mimeType bytes uri }
                        data metadata
                    }
                    metadata
                }
                acceptedOutputModes historyLength metadata timestamp
            }
            nextToken
        }
    }
    """


# =============================================================================
# Message Conversion
# =============================================================================

def task_send_params_to_graphql_input(
    params: TaskSendParams,
    channel_id: str,
    sender_id: str,
    recipient_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert A2A TaskSendParams to GraphQL A2AMessageInput."""
    parts = []
    for part in params.message.parts:
        part_dict: Dict[str, Any] = {"type": part.type}
        if isinstance(part, TextPart):
            part_dict["text"] = part.text
        elif isinstance(part, FilePart):
            part_dict["file"] = {
                "name": part.file.name,
                "mimeType": part.file.mimeType,
                "bytes": part.file.bytes,
                "uri": part.file.uri,
            }
        elif isinstance(part, DataPart):
            part_dict["data"] = part.data
        if part.metadata:
            part_dict["metadata"] = json.dumps(part.metadata) if isinstance(part.metadata, dict) else part.metadata
        parts.append(part_dict)

    msg_meta = params.message.metadata
    if isinstance(msg_meta, dict):
        msg_meta = json.dumps(msg_meta)
    top_meta = params.metadata
    if isinstance(top_meta, dict):
        top_meta = json.dumps(top_meta)

    return {
        "channelId": channel_id,
        "sessionId": params.sessionId,
        "senderId": sender_id,
        "recipientId": recipient_id,
        "message": {"role": params.message.role, "parts": parts, "metadata": msg_meta},
        "acceptedOutputModes": params.acceptedOutputModes,
        "historyLength": params.historyLength,
        "metadata": top_meta,
    }


def _parse_metadata(metadata):
    if metadata is None:
        return None
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            return metadata
    return metadata


def graphql_response_to_task_send_params(response: Dict[str, Any]) -> TaskSendParams:
    """Convert GraphQL response back to A2A TaskSendParams."""
    msg_data = response.get("message", {})
    parts: List[Part] = []
    for part_data in msg_data.get("parts", []):
        part_type = part_data.get("type", "text")
        if part_type == "text":
            parts.append(TextPart(
                type="text",
                text=part_data.get("text", ""),
                metadata=_parse_metadata(part_data.get("metadata")),
            ))
        elif part_type == "file":
            file_data = part_data.get("file", {})
            parts.append(FilePart(
                type="file",
                file=FileContent(
                    name=file_data.get("name"),
                    mimeType=file_data.get("mimeType"),
                    bytes=file_data.get("bytes"),
                    uri=file_data.get("uri"),
                ),
                metadata=_parse_metadata(part_data.get("metadata")),
            ))
        elif part_type == "data":
            parts.append(DataPart(
                type="data",
                data=part_data.get("data", {}),
                metadata=_parse_metadata(part_data.get("metadata")),
            ))

    message = Message(
        role=msg_data.get("role", "agent"),
        parts=parts,
        metadata=_parse_metadata(msg_data.get("metadata")),
    )
    return TaskSendParams(
        id=response.get("id", str(uuid4())),
        sessionId=response.get("sessionId", str(uuid4())),
        message=message,
        acceptedOutputModes=response.get("acceptedOutputModes"),
        historyLength=response.get("historyLength"),
        metadata=_parse_metadata(response.get("metadata")),
    )


# =============================================================================
# Send Message (HTTP POST)
# =============================================================================

async def wan_a2a_send_message(
    mainwin,
    channel_id: str,
    message: Message,
    sender_id: str,
    recipient_id: Optional[str] = None,
    session_id: Optional[str] = None,
    accepted_output_modes: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    endpoints: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Send an A2A message over WAN via GraphQL HTTP.

    All endpoint resolution is delegated to CloudEndpointConfig.
    """
    cfg = get_endpoint_config()
    token = (auth_headers or {}).get('Authorization') or \
            (auth_headers or {}).get('x-api-key') or \
            (mainwin.get_auth_token() if mainwin else '')

    params = TaskSendParams(
        id=str(uuid4()),
        sessionId=session_id or str(uuid4()),
        message=message,
        acceptedOutputModes=accepted_output_modes or ["text", "json"],
        metadata=metadata,
    )
    graphql_input = task_send_params_to_graphql_input(params, channel_id, sender_id, recipient_id)

    logger.debug(f"[wan_a2a] Sending to channel={channel_id}: {cfg.graphql_endpoint}")

    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)
    headers = cfg.build_http_headers(token)
    if auth_headers:
        for k, v in auth_headers.items():
            if k not in headers:
                headers[k] = v

    try:
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                cfg.graphql_endpoint,
                headers=headers,
                json={
                    'query': gen_a2a_send_message_mutation(),
                    'variables': {"input": graphql_input},
                },
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                result = await resp.json()
                if "errors" in result:
                    logger.error(f"[wan_a2a] GraphQL errors: {result['errors']}")
                else:
                    logger.debug(f"[wan_a2a] Message sent successfully")
                return result
    except Exception:
        logger.error(f"[wan_a2a] Error sending message: {traceback.format_exc()}")
        raise


def wan_a2a_send_message_sync(
    mainwin,
    channel_id: str,
    message: Message,
    sender_id: str,
    recipient_id: Optional[str] = None,
    session_id: Optional[str] = None,
    accepted_output_modes: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    auth_headers: Optional[Dict[str, str]] = None,
    endpoints: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Synchronous version of wan_a2a_send_message."""
    import requests
    cfg = get_endpoint_config()
    token = (auth_headers or {}).get('Authorization') or \
            (auth_headers or {}).get('x-api-key') or \
            (mainwin.get_auth_token() if mainwin else '')

    params = TaskSendParams(
        id=str(uuid4()),
        sessionId=session_id or str(uuid4()),
        message=message,
        acceptedOutputModes=accepted_output_modes or ["text", "json"],
        metadata=metadata,
    )
    graphql_input = task_send_params_to_graphql_input(params, channel_id, sender_id, recipient_id)

    logger.debug(f"[wan_a2a:sync] Sending to {cfg.graphql_endpoint}")

    headers = cfg.build_http_headers(token)
    if auth_headers:
        for k, v in auth_headers.items():
            if k not in headers:
                headers[k] = v

    try:
        resp = requests.post(
            cfg.graphql_endpoint,
            headers=headers,
            json={
                'query': gen_a2a_send_message_mutation(),
                'variables': {"input": graphql_input},
            },
            timeout=30,
        )
        result = resp.json()
        if "errors" in result:
            logger.error(f"[wan_a2a:sync] GraphQL errors: {result['errors']}")
        return result
    except Exception:
        logger.error(f"[wan_a2a:sync] Error: {traceback.format_exc()}")
        raise


# =============================================================================
# Subscribe (WebSocket)
# =============================================================================

async def wan_a2a_subscribe(
    mainwin,
    channel_id: str,
    on_message_callback=None,
    max_retries: int = 5,
    auth_headers: Optional[Dict[str, str]] = None,
    endpoints: Optional[Dict[str, str]] = None,
):
    """
    Subscribe to A2A messages on a channel.

    All protocol differences (CN TCB vs Intl AppSync) are now handled inside
    _subscribe_ws() — both sides use the graphql-ws wire protocol, so the
    same subscription query and message shape work on either backend.
    """
    cfg = get_endpoint_config()

    logger.debug(f"[wan_a2a] Subscribe channel={channel_id} ({cfg.graphql_endpoint})")

    if on_message_callback is None and mainwin is None:
        raise ValueError("wan_a2a_subscribe requires on_message_callback when mainwin is None")

    # Idempotently register the live-chat page-refresh handler on first use.
    # Called from every wan_a2a_subscribe invocation (9× per app run, one
    # per agent channel) but the bundle's module-level _handler_registered
    # flag ensures only the first call actually wires the callback.
    if mainwin is not None:
        try:
            from agent.ec_skills import live_chat_dispatch
            # Bridge is None when no live-chat bundle is loaded ->
            # AttributeError -> same skip path as the old lazy import.
            live_chat_dispatch.runner_bridge().page_refresh.register_if_needed(mainwin)
        except Exception as _reg_err:
            logger.debug(
                f"[wan_a2a] page-refresh registration skipped: "
                f"{type(_reg_err).__name__}: {_reg_err}"
            )

        # Pass mainwin to _subscribe_ws so it can pull a fresh token on every
        # reconnect attempt (handles long-running app + 1h JWT expiry).
        # The auth_headers param is used by tests/non-GUI callers that don't
        # have a mainwin.
        await _subscribe_ws(
            cfg=cfg,
            token="",  # signals _subscribe_ws to fetch fresh each retry
            channel_id=channel_id,
            mainwin=mainwin,
            on_message_callback=on_message_callback,
            max_retries=max_retries,
        )


async def _resolve_fresh_token(mainwin) -> str:
    """Pull the current JWT from mainwin, refreshing if expired.

    On CN (CloudBase) we prefer the 30-day WeChat session token over the
    10-minute access_token — the server mints a fresh access_token from
    it via the resolver's ``registerWeChatSession`` / ``refreshWeChatToken``
    path, so the same token stays usable across WS reconnects while the
    access_token keeps expiring.

    Returns empty string if no mainwin/token available.
    """
    if not mainwin:
        return ""
    # Try session token first on CN — same preference as wan_chat.
    am = getattr(mainwin, "auth_manager", None)
    if am is not None and getattr(am, "_is_cn", False) and hasattr(am, "_get_wechat_session_token"):
        try:
            ok, session_tok = am._get_wechat_session_token()
            if ok and session_tok and len(session_tok.strip()) > 10:
                return session_tok
        except Exception:
            pass
    if not hasattr(mainwin, 'get_auth_token'):
        return ""
    try:
        token = mainwin.get_auth_token()
        return token if isinstance(token, str) else ""
    except Exception as exc:
        logger.debug(f"[wan_a2a] get_auth_token failed: {exc}")
        return ""


async def _subscribe_ws(
    cfg,
    token: str,
    channel_id: str,
    mainwin,
    on_message_callback,
    max_retries: int,
):
    """
    WebSocket subscription using the unified endpoint config.

    Protocol is selected automatically:
      CN  → TCB JSON protocol (action=subscribe/unsubscribe)
      Intl → AppSync graphql-ws protocol (connection_init/start/stop)

    Token handling:
      - If ``token`` arg is empty AND mainwin is provided, fetch a fresh
        token from mainwin on every reconnect (handles 1h JWT expiry in
        long-running sessions).
      - If ``token`` arg is non-empty, use it as-is (for tests/non-GUI).
    """
    retry_count = 0
    base_backoff = 5
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    # Auth-failure tracking: applies longer backoff and clearer logging
    # when server keeps rejecting the token (e.g. 1h JWT expired and
    # refresh_token grant also expired — user needs to re-login).
    consecutive_auth_failures = 0
    fetch_fresh_each_retry = (token == "" and mainwin is not None)

    # Build the subscription query and variables (shared for both protocols)
    sub_query = gen_a2a_subscription_query()
    sub_variables = {"channelId": channel_id}
    sub_id = f"a2a-sub-{uuid4().hex}"

    while retry_count < max_retries:
        try:
            # Always fetch fresh token at the top of each attempt when in
            # "mainwin mode". This avoids the long-lived-stale-token bug.
            if fetch_fresh_each_retry:
                token = await _resolve_fresh_token(mainwin)
                if not token:
                    logger.warning(
                        f"[wan_a2a:WS] No auth token from mainwin "
                        f"(attempt {retry_count + 1}/{max_retries}); "
                        f"waiting 5s for auth to become available"
                    )
                    await asyncio.sleep(5)
                    continue

            ws_url = cfg.build_ws_url(token)
            logger.debug(f"[wan_a2a:WS] Connecting (attempt {retry_count + 1}): {ws_url[:80]}")
            # Both CN (TCB TCS) and Intl (AWS AppSync) use the same graphql-ws
            # protocol. The only difference is the auth header (Bearer vs API key).
            await _graphql_ws_subscribe_loop(
                cfg=cfg, token=token, ws_url=ws_url,
                channel_id=channel_id, sub_id=sub_id,
                sub_query=sub_query, sub_variables=sub_variables,
                mainwin=mainwin, on_message_callback=on_message_callback,
                max_retries=max_retries,
            )

        except asyncio.CancelledError:
            logger.info("[wan_a2a:WS] Cancelled")
            if mainwin:
                mainwin.set_wan_connected(False)
            return

        except Exception as _e:
            retry_count += 1
            err_str = str(_e)
            is_auth_error = (
                '401' in err_str
                or 'Invalid response status' in err_str
                or 'Unauthorized' in err_str
            )

            if is_auth_error:
                consecutive_auth_failures += 1
                logger.error(
                    f"[wan_a2a:WS] AUTH FAILURE (attempt {retry_count}/{max_retries}): "
                    f"{_e}. Consecutive 401s={consecutive_auth_failures}."
                )
                # Longer backoff for auth: 5s, 10s, 20s, 40s, 80s, 120s capped.
                backoff = min(5 * (2 ** min(consecutive_auth_failures - 1, 4)), 120)
            else:
                consecutive_auth_failures = 0
                backoff = min(base_backoff * (2 ** (retry_count - 1)), 60)
                noteworthy = retry_count in (1, 2, 5, 10, 20, 30, 40, 50)
                if noteworthy:
                    logger.error(f"[wan_a2a:WS] Error (attempt {retry_count}/{max_retries}): {_e}")
                else:
                    logger.debug(f"[wan_a2a:WS] Error (attempt {retry_count}/{max_retries}): {_e}")

            if retry_count < max_retries:
                logger.info(f"[wan_a2a:WS] Retrying in {backoff}s")
                await asyncio.sleep(backoff)
            else:
                logger.error(f"[wan_a2a:WS] Max retries reached")
                if mainwin:
                    mainwin.set_wan_connected(False)
                return


async def _graphql_ws_subscribe_loop(cfg, token, ws_url, channel_id, sub_id, sub_query, sub_variables, mainwin, on_message_callback, max_retries):
    """GraphQL WebSocket subscription loop (CN TCB / Intl AppSync unified).

    Both CN and Intl use the graphql-ws subprotocol over their respective WS
    endpoints. The only difference is the auth header format, handled by cfg.

    Args:
        cfg: CloudEndpointConfig instance with is_cn property
        ws_url: Pre-built WS URL with auth query params
    """
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    # Log tag reflects actual backend: TCB for CN, AppSync for Intl
    tag = "[wan_a2a:TCB]" if cfg.is_cn else "[wan_a2a:AppSync]"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                ws_url,
                protocols=['graphql-ws'],
                ssl=ssl_ctx,
                timeout=aiohttp.ClientTimeout(total=120, connect=30),
            ) as ws:
                logger.info(f"{tag} Connected for channel={channel_id}")

                # Step 1: connection_init
                await ws.send_str(json.dumps({"type": "connection_init"}))

                # Wait for connection_ack
                ka_timeout = 300
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=ka_timeout + 10)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "connection_ack":
                            logger.info(f"{tag} Connection acknowledged")
                            if mainwin:
                                mainwin.set_wan_connected(True)
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        # Server closes connection during ack — expected during
                        # startup/reconnect storms. Retry loop in _subscribe_ws will
                        # re-attempt automatically. Log as WARNING per error-classification
                        # rules (Expected Behavior, not True Bug).
                        logger.warning(f"{tag} Connection closed during ack: {msg}")
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        return

                # Step 2: start subscription
                sub_payload = json.dumps({"query": sub_query, "variables": sub_variables})
                sub_headers = {'host': cfg.host, 'Authorization': token} if token else {}
                start_msg = {
                    "id": sub_id,
                    "payload": {
                        "data": sub_payload,
                        "extensions": {"authorization": sub_headers},
                    },
                    "type": "start",
                }
                await ws.send_str(json.dumps(start_msg))

                # Wait for start_ack
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=30)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "start_ack":
                            logger.info(f"{tag} Subscribed to channel={channel_id}")
                            if mainwin:
                                mainwin.set_wan_msg_subscribed(True)
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        # Server closes connection during subscription ack — expected
                        # during startup/reconnect. Log as WARNING per error-classification
                        # rules (Expected Behavior, not True Bug).
                        logger.warning(f"{tag} Connection closed during subscription ack: {msg}")
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        return

                # Step 3: message loop
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=ka_timeout + 10)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "data":
                            inner = (data.get("payload") or {}).get("data") or {}
                            inner_msg = inner.get("onA2AMessageReceived")
                            if inner_msg and on_message_callback:
                                try:
                                    if asyncio.get_event_loop().is_running():
                                        asyncio.create_task(_call_callback(on_message_callback, inner_msg))
                                    else:
                                        asyncio.get_event_loop().run_until_complete(_call_callback(on_message_callback, inner_msg))
                                except Exception as _e:
                                    logger.debug(f"{tag} callback error: {_e}")
                        elif data.get("type") == "ka":
                            pass
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info(f"{tag} WebSocket closed normally")
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        return
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"{tag} WebSocket error: {msg}")
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        return

    except asyncio.CancelledError:
        logger.info(f"{tag} SSE connection cancelled")
        if mainwin:
            mainwin.set_wan_connected(False)
    except aiohttp.ClientError as e:
        logger.error(f"{tag} SSE connection error: {e}")
        if mainwin:
            mainwin.set_wan_connected(False)
    except Exception as e:
        logger.error(f"{tag} SSE error: {e}")
        if mainwin:
            mainwin.set_wan_connected(False)


async def _call_callback(callback, data):
    """Call an async or sync callback uniformly."""
    try:
        if asyncio.iscoroutinefunction(callback):
            await callback(data)
        else:
            callback(data)
    except Exception as _e:
        logger.debug(f"[wan_a2a] callback error: {_e}")


# =============================================================================
# Convenience Functions
# =============================================================================

async def wan_a2a_send_text(
    mainwin,
    channel_id: str,
    text: str,
    sender_id: str,
    recipient_id: Optional[str] = None,
    role: str = "agent",
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    message = Message(
        role=role,
        parts=[TextPart(type="text", text=text)],
        metadata=metadata,
    )
    return await wan_a2a_send_message(
        mainwin=mainwin,
        channel_id=channel_id,
        message=message,
        sender_id=sender_id,
        recipient_id=recipient_id,
        session_id=session_id,
        metadata=metadata,
    )


async def wan_a2a_send_to_group(
    mainwin,
    group_id: str,
    message: Message,
    sender_id: str,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return await wan_a2a_send_message(
        mainwin=mainwin,
        channel_id=group_id,
        message=message,
        sender_id=sender_id,
        recipient_id=None,
        session_id=session_id,
        metadata=metadata,
    )
