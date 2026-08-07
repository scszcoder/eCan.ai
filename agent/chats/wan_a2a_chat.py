"""
wan_a2a_chat.py - Unified A2A Messaging over AWS AppSync WebSocket

This module provides A2A-compatible messaging over WAN using AWS AppSync GraphQL.
It uses the same message format as local A2A (TaskSendParams/Message) for seamless
LAN/WAN interoperability.

Usage:
    # Send a message
    await wan_a2a_send_message(mainwin, channel_id, message, recipient_id=None)
    
    # Subscribe to a channel (for receiving messages)
    await wan_a2a_subscribe(mainwin, channel_id)
"""

import json
import ssl
import asyncio
import aiohttp
import base64
import traceback
import os
import certifi
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

from a2a.types import (
    Message, 
    TextPart, 
    FilePart, 
    DataPart,
    Part
)
from agent.cloud_api.cloud_api import get_appsync_endpoint
from utils.logger_helper import logger_helper as logger


# =============================================================================
# Configuration
# =============================================================================

def _build_http_headers(mainwin, auth_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    if auth_headers is not None:
        return {
            'Content-Type': "application/json",
            'cache-control': "no-cache",
            **auth_headers,
        }
    if mainwin is None:
        raise ValueError("wan_a2a_chat requires either mainwin or auth_headers")
    token = mainwin.get_auth_token()
    return {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }


def _build_ws_api_headers(endpoints: Dict[str, str], mainwin, auth_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {
        'host': endpoints["host"],
    }
    if auth_headers is not None:
        headers.update(auth_headers)
        return headers
    if mainwin is None:
        raise ValueError("wan_a2a_chat requires either mainwin or auth_headers")
    token = mainwin.get_auth_token()
    headers['Authorization'] = token
    return headers

def get_a2a_appsync_endpoints():
    """Get AppSync endpoints for A2A messaging"""
    from config.constants import API_DEV_MODE
    
    if API_DEV_MODE:
        return {
            "http": "https://cpzjfests5ea5nk7cipavakdnm.appsync-api.us-east-1.amazonaws.com/graphql",
            "ws": "wss://cpzjfests5ea5nk7cipavakdnm.appsync-realtime-api.us-east-1.amazonaws.com/graphql",
            "host": "cpzjfests5ea5nk7cipavakdnm.appsync-api.us-east-1.amazonaws.com"
        }
    else:
        return {
            "http": "https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql",
            "ws": "wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql",
            "host": "3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com"
        }


# =============================================================================
# GraphQL Queries/Mutations
# =============================================================================

def gen_a2a_send_message_mutation() -> str:
    """Generate GraphQL mutation for sending A2A message"""
    return """
    mutation SendA2AMessage($input: A2AMessageInput!) {
        sendA2AMessage(input: $input) {
            id
            channelId
            sessionId
            senderId
            recipientId
            message {
                role
                parts {
                    type
                    text
                    file {
                        name
                        mimeType
                        bytes
                        uri
                    }
                    data
                    metadata
                }
                metadata
            }
            acceptedOutputModes
            historyLength
            metadata
            timestamp
        }
    }
    """


def gen_a2a_subscription_query() -> str:
    """Generate GraphQL subscription for receiving A2A messages"""
    return """
    subscription OnA2AMessageReceived($channelId: String!) {
        onA2AMessageReceived(channelId: $channelId) {
            id
            channelId
            sessionId
            senderId
            recipientId
            message {
                role
                parts {
                    type
                    text
                    file {
                        name
                        mimeType
                        bytes
                        uri
                    }
                    data
                    metadata
                }
                metadata
            }
            acceptedOutputModes
            historyLength
            metadata
            timestamp
        }
    }
    """


def gen_a2a_get_messages_query() -> str:
    """Generate GraphQL query for fetching message history"""
    return """
    query GetA2AMessages($channelId: String!, $limit: Int, $nextToken: String) {
        getA2AMessages(channelId: $channelId, limit: $limit, nextToken: $nextToken) {
            items {
                id
                channelId
                sessionId
                senderId
                recipientId
                message {
                    role
                    parts {
                        type
                        text
                        file {
                            name
                            mimeType
                            bytes
                            uri
                        }
                        data
                        metadata
                    }
                    metadata
                }
                acceptedOutputModes
                historyLength
                metadata
                timestamp
            }
            nextToken
        }
    }
    """


# =============================================================================
# Message Conversion Utilities
# =============================================================================

def task_send_params_to_graphql_input(
    params: TaskSendParams,
    channel_id: str,
    sender_id: str,
    recipient_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert A2A TaskSendParams to GraphQL A2AMessageInput format.
    
    This is the bridge between local A2A format and WAN GraphQL format.
    Since we designed the GraphQL schema to match A2A, this is mostly a 1:1 mapping.
    """
    # Convert message parts
    parts = []
    for part in params.message.parts:
        part_dict = {"type": part.type}
        
        if isinstance(part, TextPart):
            part_dict["text"] = part.text
        elif isinstance(part, FilePart):
            part_dict["file"] = {
                "name": part.file.name,
                "mimeType": part.file.mimeType,
                "bytes": part.file.bytes,
                "uri": part.file.uri
            }
        elif isinstance(part, DataPart):
            part_dict["data"] = part.data
        
        if part.metadata:
            part_dict["metadata"] = json.dumps(part.metadata) if isinstance(part.metadata, dict) else part.metadata
            
        parts.append(part_dict)
    
    # Serialize metadata dicts to JSON strings for AWSJSON scalar type
    msg_metadata = params.message.metadata
    if isinstance(msg_metadata, dict):
        msg_metadata = json.dumps(msg_metadata)
    
    top_metadata = params.metadata
    if isinstance(top_metadata, dict):
        top_metadata = json.dumps(top_metadata)
    
    return {
        "channelId": channel_id,
        "sessionId": params.sessionId,
        "senderId": sender_id,
        "recipientId": recipient_id,
        "message": {
            "role": params.message.role,
            "parts": parts,
            "metadata": msg_metadata
        },
        "acceptedOutputModes": params.acceptedOutputModes,
        "historyLength": params.historyLength,
        "metadata": top_metadata
    }


def _parse_metadata(metadata):
    """Parse metadata from JSON string to dict if needed."""
    if metadata is None:
        return None
    if isinstance(metadata, str):
        try:
            return json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            return metadata
    return metadata


def graphql_response_to_task_send_params(response: Dict[str, Any]) -> TaskSendParams:
    """
    Convert GraphQL A2AMessage response back to A2A TaskSendParams.
    
    Used when receiving messages from WAN subscription.
    """
    msg_data = response.get("message", {})
    
    # Convert parts back to A2A Part objects
    parts: List[Part] = []
    for part_data in msg_data.get("parts", []):
        part_type = part_data.get("type", "text")
        
        if part_type == "text":
            parts.append(TextPart(
                type="text",
                text=part_data.get("text", ""),
                metadata=_parse_metadata(part_data.get("metadata"))
            ))
        elif part_type == "file":
            file_data = part_data.get("file", {})
            parts.append(FilePart(
                type="file",
                file=FileContent(
                    name=file_data.get("name"),
                    mimeType=file_data.get("mimeType"),
                    bytes=file_data.get("bytes"),
                    uri=file_data.get("uri")
                ),
                metadata=_parse_metadata(part_data.get("metadata"))
            ))
        elif part_type == "data":
            parts.append(DataPart(
                type="data",
                data=part_data.get("data", {}),
                metadata=_parse_metadata(part_data.get("metadata"))
            ))
    
    message = Message(
        role=msg_data.get("role", "agent"),
        parts=parts,
        metadata=_parse_metadata(msg_data.get("metadata"))
    )
    
    return TaskSendParams(
        id=response.get("id", str(uuid4())),
        sessionId=response.get("sessionId", str(uuid4())),
        message=message,
        acceptedOutputModes=response.get("acceptedOutputModes"),
        historyLength=response.get("historyLength"),
        metadata=_parse_metadata(response.get("metadata"))
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
    endpoints: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Send an A2A message over WAN via AWS AppSync GraphQL.
    
    Args:
        mainwin: MainWindow instance (for auth token)
        channel_id: Pub/sub channel ID (use group ID for group chat)
        message: A2A Message object
        sender_id: Sender agent ID
        recipient_id: Optional recipient agent ID (None for broadcast)
        session_id: Optional session ID (auto-generated if not provided)
        accepted_output_modes: Optional list of accepted output modes
        metadata: Optional metadata dict
        auth_headers: Optional auth headers (API key or JWT)
        endpoints: Optional AppSync endpoints
        
    Returns:
        GraphQL response dict
    """
    endpoints = endpoints or get_a2a_appsync_endpoints()
    
    # Build TaskSendParams
    params = TaskSendParams(
        id=str(uuid4()),
        sessionId=session_id or str(uuid4()),
        message=message,
        acceptedOutputModes=accepted_output_modes or ["text", "json"],
        metadata=metadata
    )
    
    # Convert to GraphQL input
    graphql_input = task_send_params_to_graphql_input(
        params=params,
        channel_id=channel_id,
        sender_id=sender_id,
        recipient_id=recipient_id
    )
    
    variables = {"input": graphql_input}
    query_string = gen_a2a_send_message_mutation()
    
    headers = _build_http_headers(mainwin=mainwin, auth_headers=auth_headers)
    
    try:
        logger.debug(f"[wan_a2a] Sending message to channel: {channel_id}")
        
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.post(
                url=endpoints["http"],
                timeout=aiohttp.ClientTimeout(total=30),
                headers=headers,
                json={
                    'query': query_string,
                    'variables': variables
                }
            ) as response:
                result = await response.json()
                
                if "errors" in result:
                    logger.error(f"[wan_a2a] GraphQL errors: {result['errors']}")
                else:
                    logger.debug(f"[wan_a2a] Message sent successfully: {result}")
                
                return result
                
    except Exception as e:
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
    endpoints: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Synchronous version of wan_a2a_send_message.
    Uses requests library for blocking HTTP call.
    """
    import requests
    
    endpoints = endpoints or get_a2a_appsync_endpoints()
    headers = _build_http_headers(mainwin=mainwin, auth_headers=auth_headers)
    
    # Build TaskSendParams
    params = TaskSendParams(
        id=str(uuid4()),
        sessionId=session_id or str(uuid4()),
        message=message,
        acceptedOutputModes=accepted_output_modes or ["text", "json"],
        metadata=metadata
    )
    
    # Convert to GraphQL input
    graphql_input = task_send_params_to_graphql_input(
        params=params,
        channel_id=channel_id,
        sender_id=sender_id,
        recipient_id=recipient_id
    )
    
    variables = {"input": graphql_input}
    query_string = gen_a2a_send_message_mutation()
    
    http_endpoint = endpoints["http"]
    
    try:
        logger.debug(f"[wan_a2a_sync] Sending message to channel: {http_endpoint}, {headers}, {query_string}, {variables}")
        
        response = requests.post(
            url=http_endpoint,
            headers=headers,
            json={
                'query': query_string,
                'variables': variables
            },
            timeout=30
        )
        
        result = response.json()
        
        if "errors" in result:
            logger.error(f"[wan_a2a_sync] GraphQL errors: {result['errors']}")
        else:
            logger.debug(f"[wan_a2a_sync] Message sent successfully")
        
        return result
        
    except Exception as e:
        logger.error(f"[wan_a2a_sync] Error sending message: {traceback.format_exc()}")
        raise


# =============================================================================
# Subscribe to Channel (WebSocket)
# =============================================================================

async def wan_a2a_subscribe(
    mainwin,
    channel_id: str,
    on_message_callback=None,
    max_retries: int = 50,
    auth_headers: Optional[Dict[str, str]] = None,
    endpoints: Optional[Dict[str, str]] = None
):
    """
    Subscribe to A2A messages on a channel via AWS AppSync WebSocket.
    
    Args:
        mainwin: MainWindow instance
        channel_id: Channel to subscribe to
        on_message_callback: Optional callback function(TaskSendParams, sender_id, channel_id)
        max_retries: Maximum retry attempts for connection
        auth_headers: Optional auth headers (API key or JWT)
        endpoints: Optional AppSync endpoints
    """
    endpoints = endpoints or get_a2a_appsync_endpoints()
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

    retry_count = 0
    base_backoff = 5

    # Build SSL context once; reuse across reconnect attempts.
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    while retry_count < max_retries:
        try:
            # Build WebSocket connection URL with auth headers
            api_headers = _build_ws_api_headers(endpoints=endpoints, mainwin=mainwin, auth_headers=auth_headers)

            header_b64 = base64.b64encode(json.dumps(api_headers).encode('utf-8')).decode('utf-8')
            ws_url = f"{endpoints['ws']}?header={header_b64}&payload=e30="

            # Do NOT set heartbeat here: AWS AppSync realtime API uses its own application-layer
            # keep-alive ("ka" messages) and does not reliably respond to WebSocket PING frames.
            # An aiohttp heartbeat would send PING every N seconds and close the connection if PONG
            # is not received within N/2 seconds — this causes spurious disconnects, especially
            # when the event loop is briefly busy with other I/O.  The recv_timeout below (based on
            # ka_timeout_sec) is sufficient to detect a truly dead connection.
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    ws_url,
                    protocols=['graphql-ws'],
                    ssl=ssl_context,
                    timeout=aiohttp.ClientTimeout(total=120, connect=30),
                ) as websocket:
                    logger.info(f"[wan_a2a] Connected to WebSocket for channel: {channel_id}")

                    # Connection init
                    await websocket.send_str(json.dumps({"type": "connection_init"}))

                    # Wait for connection ack
                    ka_timeout_sec = 300
                    while True:
                        msg = await websocket.receive()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            response_data = json.loads(msg.data)
                            if response_data.get("type") == "connection_ack":
                                logger.info("[wan_a2a] WebSocket connection acknowledged")
                                if mainwin is not None:
                                    mainwin.set_wan_connected(True)
                                ka_timeout_sec = response_data.get("payload", {}).get("connectionTimeoutMs", 300000) / 1000
                                break
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            logger.error(f"[wan_a2a] Connection closed during ack: {msg}")
                            raise Exception("Connection closed during ack")

                    # Send subscription request
                    sub_data = {
                        "query": gen_a2a_subscription_query(),
                        "variables": {"channelId": channel_id}
                    }

                    sub_request = {
                        "id": f"a2a-sub-{uuid4().hex}",
                        "payload": {
                            "data": json.dumps(sub_data),
                            "extensions": {
                                "authorization": {k: v for k, v in api_headers.items() if k != 'content-type'}
                            }
                        },
                        "type": "start"
                    }

                    await websocket.send_str(json.dumps(sub_request))
                    logger.debug(f"[wan_a2a] Subscription request sent for channel: {channel_id}")

                    # Wait for subscription ack
                    while True:
                        msg = await websocket.receive()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            response_data = json.loads(msg.data)
                            if response_data.get("type") == "start_ack":
                                logger.info(f"[wan_a2a] Subscribed to channel: {channel_id}")
                                if mainwin is not None:
                                    mainwin.set_wan_msg_subscribed(True)
                                break
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            raise Exception("Connection closed during subscription ack")

                    # Message receive loop
                    recv_timeout = ka_timeout_sec + 10
                    connection_lost = False
                    while True:
                        try:
                            msg = await asyncio.wait_for(websocket.receive(), timeout=recv_timeout)

                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)

                                if data.get("type") == "data":
                                    # Extract A2A message from subscription payload
                                    a2a_msg = data.get("payload", {}).get("data", {}).get("onA2AMessageReceived")

                                    if a2a_msg:
                                        logger.debug(f"[wan_a2a] Received message from {a2a_msg.get('senderId')}")

                                        # Convert to TaskSendParams
                                        task_params = graphql_response_to_task_send_params(a2a_msg)

                                        # Call callback or put in queue
                                        if on_message_callback:
                                            await on_message_callback(
                                                task_params,
                                                a2a_msg.get("senderId"),
                                                a2a_msg.get("channelId")
                                            )
                                        else:
                                            # Put in mainwin's message queue
                                            await mainwin.wan_chat_msg_queue.put({
                                                "type": "a2a_message",
                                                "params": task_params,
                                                "senderId": a2a_msg.get("senderId"),
                                                "channelId": a2a_msg.get("channelId"),
                                                "recipientId": a2a_msg.get("recipientId")
                                            })

                                elif data.get("type") == "ka":
                                    # Keep-alive
                                    logger.trace("[wan_a2a] Keep-alive received")

                            elif msg.type == aiohttp.WSMsgType.CLOSED:
                                logger.info("[wan_a2a] WebSocket closed normally")
                                if mainwin is not None:
                                    mainwin.set_wan_connected(False)
                                # Don't treat normal closure as error - just exit cleanly
                                return
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                logger.error(f"[wan_a2a] WebSocket error: {websocket.exception()}")
                                if mainwin is not None:
                                    mainwin.set_wan_connected(False)
                                connection_lost = True
                                break

                        except asyncio.TimeoutError:
                            logger.warning("[wan_a2a] WebSocket recv timeout - connection may be stale")
                            if mainwin is not None:
                                mainwin.set_wan_connected(False)
                            connection_lost = True
                            break
                        except asyncio.CancelledError:
                            logger.info("[wan_a2a] Subscription cancelled")
                            if mainwin is not None:
                                mainwin.set_wan_connected(False)
                            return

                    # Only raise exception if connection was lost abnormally
                    if connection_lost:
                        raise Exception("Connection lost")
                    
        except asyncio.CancelledError:
            logger.info("[wan_a2a] Subscription task cancelled")
            if mainwin is not None:
                mainwin.set_wan_connected(False)
            return
            
        except Exception as e:
            retry_count += 1
            backoff_time = min(base_backoff * (2 ** (retry_count - 1)), 60)
            # Reduce log spam during sustained outages (2026-05-18): a
            # 30-min disconnect produced ~270 identical ERROR lines per
            # channel × 9 channels.  Log at ERROR for attempts 1, 2, 5,
            # 10, 20, 30, 40, 50 (the user-actionable points where the
            # outage class changes — transient blip vs sustained
            # disconnect vs persistent failure).  Other attempts log at
            # DEBUG so they're available when diagnosing but don't
            # drown the error log.
            _is_noteworthy_attempt = retry_count in (1, 2, 5, 10, 20, 30, 40, 50)
            if _is_noteworthy_attempt:
                logger.error(
                    f"[wan_a2a] Connection error (attempt {retry_count}/{max_retries}, "
                    f"channel={channel_id}): {e}"
                )
            else:
                logger.debug(
                    f"[wan_a2a] Connection error (attempt {retry_count}/{max_retries}, "
                    f"channel={channel_id}): {e}"
                )

            if retry_count < max_retries:
                if _is_noteworthy_attempt:
                    logger.info(f"[wan_a2a] Retrying in {backoff_time}s (channel={channel_id})")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"[wan_a2a] Max retries reached for channel={channel_id}")
                if mainwin is not None:
                    mainwin.set_wan_connected(False)
                break
    
    logger.error(f"[wan_a2a] Subscription failed after {max_retries} attempts")


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
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to send a simple text message over WAN.
    
    Args:
        mainwin: MainWindow instance
        channel_id: Channel ID
        text: Text content
        sender_id: Sender agent ID
        recipient_id: Optional recipient ID
        role: Message role ("user" or "agent")
        session_id: Optional session ID
        metadata: Optional metadata
    """
    message = Message(
        role=role,
        parts=[TextPart(type="text", text=text)],
        metadata=metadata
    )
    
    return await wan_a2a_send_message(
        mainwin=mainwin,
        channel_id=channel_id,
        message=message,
        sender_id=sender_id,
        recipient_id=recipient_id,
        session_id=session_id,
        metadata=metadata
    )


async def wan_a2a_send_to_group(
    mainwin,
    group_id: str,
    message: Message,
    sender_id: str,
    session_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Send a message to a group channel (all subscribers receive).
    
    Args:
        mainwin: MainWindow instance
        group_id: Group/channel ID
        message: A2A Message object
        sender_id: Sender agent ID
        session_id: Optional session ID
        metadata: Optional metadata
    """
    return await wan_a2a_send_message(
        mainwin=mainwin,
        channel_id=group_id,
        message=message,
        sender_id=sender_id,
        recipient_id=None,  # Broadcast to all subscribers
        session_id=session_id,
        metadata=metadata
    )
