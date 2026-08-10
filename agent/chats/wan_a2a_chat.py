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
from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import uuid4

# Apply nest_asyncio for Python 3.11+ nested event loops
nest_asyncio.apply()

from agent.a2a.langgraph_agent.utils import FileContent, TaskSendParams
from a2a.types import Message, TextPart, FilePart, DataPart, Part
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.endpoints import get_endpoint_config, _tcb_ws_url, _appsync_ws_url


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
    max_retries: int = 50,
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
    token = (auth_headers or {}).get('Authorization') or \
            (auth_headers or {}).get('x-api-key') or \
            (mainwin.get_auth_token() if mainwin else '') if mainwin else ''

    logger.debug(f"[wan_a2a] Subscribe channel={channel_id} ({cfg.graphql_endpoint})")

    if on_message_callback is None and mainwin is None:
        raise ValueError("wan_a2a_subscribe requires on_message_callback when mainwin is None")

    if mainwin is not None:
        try:
            from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.feige_page_refresh import (
                register_if_needed as _reg_feige,
            )
            _reg_feige(mainwin)
        except Exception as _e:
            logger.debug(f"[wan_a2a] feige registration skipped: {_e}")

    await _subscribe_ws(
        cfg=cfg,
        token=token,
        channel_id=channel_id,
        mainwin=mainwin,
        on_message_callback=on_message_callback,
        max_retries=max_retries,
    )


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
    """
    retry_count = 0
    base_backoff = 5
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())

    # Build the subscription query and variables (shared for both protocols)
    sub_query = gen_a2a_subscription_query()
    sub_variables = {"channelId": channel_id}
    sub_id = f"a2a-sub-{uuid4().hex}"

    while retry_count < max_retries:
        try:
            ws_url = cfg.build_ws_url(token)
            logger.debug(f"[wan_a2a:WS] Connecting (attempt {retry_count + 1}): {ws_url[:80]}")

            if cfg.is_cn:
                await _tcb_subscribe_loop(
                    cfg=cfg, token=token, ws_url=ws_url,
                    channel_id=channel_id, sub_id=sub_id,
                    sub_query=sub_query, sub_variables=sub_variables,
                    mainwin=mainwin, on_message_callback=on_message_callback,
                    max_retries=max_retries,
                )
            else:
                await _appsync_subscribe_loop(
                    cfg=cfg, ws_url=ws_url,
                    sub_query=sub_query, sub_variables=sub_variables, sub_id=sub_id,
                    mainwin=mainwin, on_message_callback=on_message_callback,
                    ssl_ctx=ssl_ctx,
                    max_retries=max_retries,
                )

        except asyncio.CancelledError:
            logger.info("[wan_a2a:WS] Cancelled")
            if mainwin:
                mainwin.set_wan_connected(False)
            return

        except Exception as _e:
            retry_count += 1
            backoff = min(base_backoff * (2 ** (retry_count - 1)), 60)
            noteworthy = retry_count in (1, 2, 5, 10, 20, 30, 40, 50)
            if noteworthy:
                logger.error(f"[wan_a2a:WS] Error (attempt {retry_count}/{max_retries}): {_e}")
            else:
                logger.debug(f"[wan_a2a:WS] Error (attempt {retry_count}/{max_retries}): {_e}")

            if retry_count < max_retries:
                if noteworthy:
                    logger.info(f"[wan_a2a:WS] Retrying in {backoff}s")
                await asyncio.sleep(backoff)
            else:
                logger.error(f"[wan_a2a:WS] Max retries reached")
                if mainwin:
                    mainwin.set_wan_connected(False)
                return


async def _tcb_subscribe_loop(cfg, token, ws_url, channel_id, sub_id, sub_query, sub_variables, mainwin, on_message_callback, max_retries):
    """CN: TCB SSE (Server-Sent Events) protocol.

    Connects to /api/events?topic=onA2AMessageReceived&channelId=xxx
    Receives SSE events with format: event: onA2AMessageReceived\ndata: {payload}
    """
    import aiohttp

    sse_endpoint = cfg.sse_endpoint
    if not sse_endpoint:
        logger.error("[wan_a2a:TCB] SSE endpoint not configured")
        return

    # Build SSE URL with topic and target
    full_url = f"{sse_endpoint}?topic=onA2AMessageReceived&channelId={channel_id}"
    if token:
        full_url = f"{full_url}&token={token}"

    logger.info(f"[wan_a2a:TCB] Connecting to SSE: {full_url[:80]}")

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    timeout = aiohttp.ClientTimeout(total=0)  # No timeout for SSE

    if mainwin:
        mainwin.set_wan_connected(True)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                full_url,
                headers={'Accept': 'text/event-stream', 'Cache-Control': 'no-cache'},
                timeout=timeout,
                ssl=ssl_context,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.error(f"[wan_a2a:TCB] SSE error: status={response.status} body={body[:200]}")
                    if mainwin:
                        mainwin.set_wan_connected(False)
                    return

                logger.info(f"[wan_a2a:TCB] SSE connected, listening for messages...")
                if mainwin:
                    mainwin.set_wan_msg_subscribed(True)

                current_event = None
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue

                    # SSE comment line (e.g., ": connected topic=...")
                    if line.startswith(':'):
                        logger.debug(f"[wan_a2a:TCB] SSE: {line}")
                        continue

                    # SSE ping
                    if line.startswith(': ping'):
                        continue

                    # SSE event line
                    if line.startswith('event: '):
                        current_event = line[7:].strip()
                        continue

                    # SSE data line
                    if line.startswith('data: '):
                        if current_event == 'onA2AMessageReceived':
                            data_str = line[6:].strip()
                            try:
                                data = json.loads(data_str)
                                payload = data.get('payload', {})
                                if on_message_callback:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        if loop.is_running():
                                            asyncio.create_task(_call_callback(on_message_callback, payload))
                                        else:
                                            loop.run_until_complete(_call_callback(on_message_callback, payload))
                                    except Exception as _e:
                                        logger.debug(f"[wan_a2a:TCB] callback error: {_e}")
                                elif mainwin:
                                    try:
                                        loop = asyncio.get_event_loop()
                                        asyncio.create_task(mainwin.wan_chat_msg_queue.put({"type": "a2a_message", "params": payload}))
                                    except Exception:
                                        pass
                            except json.JSONDecodeError:
                                logger.warning(f"[wan_a2a:TCB] Invalid JSON: {data_str[:100]}")
                        current_event = None
                        continue

                    current_event = None

    except asyncio.CancelledError:
        logger.info("[wan_a2a:TCB] SSE connection cancelled")
        if mainwin:
            mainwin.set_wan_connected(False)
    except aiohttp.ClientError as e:
        logger.error(f"[wan_a2a:TCB] SSE connection error: {e}")
        if mainwin:
            mainwin.set_wan_connected(False)
    except Exception as e:
        logger.error(f"[wan_a2a:TCB] SSE error: {e}")
        if mainwin:
            mainwin.set_wan_connected(False)


async def _appsync_subscribe_loop(cfg, ws_url, sub_query, sub_variables, sub_id, mainwin, on_message_callback, ssl_ctx, max_retries):
    """Intl: AppSync graphql-ws protocol."""
    headers = {'host': cfg.host}
    if cfg.api_key:
        headers['x-api-key'] = cfg.api_key
    else:
        # Token was already embedded in ws_url by build_ws_url()
        pass

    sub_payload = json.dumps({'query': sub_query, 'variables': sub_variables})
    start_msg = {
        'id': sub_id,
        'payload': {
            'data': sub_payload,
            'extensions': {'authorization': headers},
        },
        'type': 'start',
    }

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(
            ws_url,
            protocols=['graphql-ws'],
            ssl=ssl_ctx,
            timeout=aiohttp.ClientTimeout(total=120, connect=30),
        ) as ws:
            logger.info(f"[wan_a2a:AWS] Connected for channel={sub_variables['channelId']}")

            await ws.send_str(json.dumps({"type": "connection_init"}))

            # Wait for connection_ack
            ka_timeout = 300
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    rd = json.loads(msg.data)
                    if rd.get("type") == "connection_ack":
                        if mainwin:
                            mainwin.set_wan_connected(True)
                        ka_timeout = rd.get("payload", {}).get("connectionTimeoutMs", 300000) / 1000
                        break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise Exception(f"Connection closed during ack: {msg}")

            # Send subscription
            await ws.send_str(json.dumps(start_msg))
            logger.debug(f"[wan_a2a:AWS] Subscription sent: {sub_id}")

            # Wait for start_ack
            while True:
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.TEXT:
                    rd = json.loads(msg.data)
                    if rd.get("type") == "start_ack":
                        if mainwin:
                            mainwin.set_wan_msg_subscribed(True)
                        break
                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    raise Exception("Connection closed during subscription ack")

            recv_timeout = ka_timeout + 10
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=recv_timeout)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "data":
                            inner = (data.get("payload") or {}).get("data") or {}
                            for key, val in inner.items():
                                if key and val:
                                    if on_message_callback:
                                        await _call_callback(on_message_callback, val)
                                    elif mainwin:
                                        await mainwin.wan_chat_msg_queue.put({
                                            "type": "a2a_message", "params": val,
                                        })
                        elif data.get("type") == "ka":
                            logger.trace("[wan_a2a:AWS] Keep-alive")
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        return
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        if mainwin:
                            mainwin.set_wan_connected(False)
                        raise Exception("WebSocket error")

                except asyncio.TimeoutError:
                    if mainwin:
                        mainwin.set_wan_connected(False)
                    raise Exception("Recv timeout")


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
