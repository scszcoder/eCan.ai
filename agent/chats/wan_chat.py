import json
import ssl
import asyncio
from typing import Optional
import aiohttp
import httpx
from agent.cloud_api.cloud_api import gen_wan_send_chat_message_string, gen_wan_subscription_connection_string
import base64
from datetime import datetime
import xml.etree.ElementTree as ET
import traceback
import requests
import os
import websockets
import websocket as ws_client_module
from websockets.exceptions import ConnectionClosed as ConnectionClosedError
import certifi
from utils.logger_helper import logger_helper as logger
from agent.cloud_api.endpoints import get_endpoint_config

# Wan Chat Logic
# Commander will connect to websocket and subscribe, and wan logging is default off, then sit in a loop
# and listen for turn on logging command,
# Staff Officer will get online and connect to websocket and shoot out ping command to any commander out there.
# once hearing ack back from the commander off websocket, it sends a request logging command if needed.

# Module-level timestamps for keep-alive tracking
last_connected_ts = datetime.now()
last_subscribed_ts = datetime.now()


def _resolve_ws_token(mainwin, auth_token: str) -> Optional[str]:
    """Pick the best token for the WebSocket connection.

    Priority for CN (CloudBase):
      1. WeChat session token (30-day, server-minted) — survives the
         10-minute access_token expiry. Read from keyring / file fallback
         via AuthManager. This is the standard token for the CN WS path.
      2. Current AccessToken (10-min JWT) — last-resort fallback when
         no session token is on disk (e.g., user has never re-logged
         since the session-token scheme was rolled out).

    For Intl (AWS AppSync): just delegate to ``mainwin.get_auth_token()``
    which already prefers IdToken over AccessToken.

    Returns None when no token is available — caller treats that as
    "auth manager cleared credentials; user must re-login".
    """
    if not mainwin:
        return auth_token
    # Pull directly from the auth_manager when possible — bypasses the
    # legacy IdToken preference which doesn't apply to the WS path on CN.
    am = getattr(mainwin, "auth_manager", None)
    # If AuthManager has already flagged the session as no longer signed in
    # (e.g., CN WeChat session expired and ``_is_wechat_flow`` cleared
    # credentials via supervisor on a previous tick), don't hand back the
    # cached expired token — that just spins the WS loop every 60s with
    # ``Token refresh returned same token`` ERROR spam. Returning None lets
    # the caller hit the ``if not id_token: stopping reconnect loop`` branch
    # and surface a one-shot ``user re-login required`` message instead of
    # one ERROR per minute for hours.
    if am is not None and getattr(am, "signed_in", True) is False:
        return None
    is_cn = bool(getattr(am, "_is_cn", False))
    if is_cn and am is not None and hasattr(am, "_get_wechat_session_token"):
        try:
            ok, session_tok = am._get_wechat_session_token()
            if ok and session_tok and len(session_tok.strip()) > 10:
                return session_tok
        except Exception:
            pass
    # Intl or CN-without-session-token — keep the existing getter path.
    if hasattr(mainwin, "get_auth_token"):
        try:
            tok = mainwin.get_auth_token()
            if tok:
                return tok
        except Exception:
            pass
    return auth_token


async def wanStopSubscription(mainwin):
    init_msg = {"type": "stop"}
    current_ws = mainwin.get_websocket()
    if current_ws:
        try:
            await current_ws.send(json.dumps(init_msg))
            while True:
                try:
                    response = await current_ws.recv()
                    response_data = json.loads(response)
                    logger.debug(f"WAN stop subscription received: {response_data}")
                    if response_data.get("type") == "complete":
                        logger.info("WAN subscription stopped")
                        mainwin.set_wan_msg_subscribed(False)
                        break
                except ConnectionClosedError as e:
                    logger.error(f"WAN stop subscription connection closed: {e}")
                    mainwin.set_wan_connected(False)
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"WAN stop subscription JSON decode failed: {e}")
                    break
        except Exception as e:
            logger.error(f"Failed to stop WAN subscription: {e}")

def validate_msg_fields(msg_req, mainwin):
    expected_fields = {
        "chatID": str,
        "sender": str,
        "receiver": str,
        "type": str,
        "contents": str,
        "parameters": str
    }
    for field, expected_type in expected_fields.items():
        value = msg_req.get(field)
        if value is None:
            logger.debug(f"Field '{field}' is missing or None, which could cause an error."+json.dumps(msg_req), "wanSendMessage", mainwin)
        elif not isinstance(value, expected_type):
            logger.debug(f"Field '{field}' has type {type(value)}, expected {expected_type}. Value: {value}"+json.dumps(msg_req), "wanSendMessage", mainwin)

def wanSendMessage(msg_req, mainwin):
    """Send a chat message via GraphQL HTTP."""
    cfg = get_endpoint_config()
    token = mainwin.get_auth_token()
    session = mainwin.session
    try:
        validate_msg_fields(msg_req, mainwin)
        variables = {
            "input": {
                "chatID": msg_req["chatID"],
                "sender": msg_req["sender"],
                "receiver": msg_req["receiver"],
                "type": msg_req["type"],
                "contents": msg_req["contents"],
                "parameters": msg_req["parameters"]
            }
        }
        query_string = gen_wan_send_chat_message_string()
        headers = cfg.build_http_headers(token)
        session.headers.update(headers)
        response = session.post(
            url=cfg.graphql_endpoint,
            json={'query': query_string, 'variables': variables},
            timeout=30
        )
        return response.json()
    except Exception as e:
        # Per CLAUDE.md §6, cloud 5xx (INTERNAL_SERVER_ERROR) is expected
        # behavior — server-side issue, not a client bug. Log at WARNING
        # rather than DEBUG so it doesn't spam logs during sustained outages.
        logger.warning(f"ErrorwanSendMessage: {e}", "wanSendMessage", mainwin)

async def wanSendMessage8(msg_req, mainwin):
    """Send a chat message via GraphQL HTTP (async version)."""
    cfg = get_endpoint_config()
    token = mainwin.get_auth_token()
    try:
        variables = {
            "input": {
                "chatID": msg_req["chatID"],
                "sender": msg_req["sender"],
                "receiver": msg_req["receiver"],
                "type": msg_req["type"],
                "contents": msg_req["contents"],
                "parameters": msg_req["parameters"]
            }
        }
        query_string = gen_wan_send_chat_message_string()
        headers = cfg.build_http_headers(token)
        logger.debug("about to send wan msg: "+json.dumps(variables), "wanSendMessage", mainwin)

        def _sync_post():
            with httpx.Client(verify=certifi.where(), timeout=30.0) as client:
                return client.post(
                    url=cfg.graphql_endpoint,
                    headers=headers,
                    json={'query': query_string, 'variables': variables}
                )
        response = await asyncio.to_thread(_sync_post)
        jresp = response.json()
        # Per CLAUDE.md §6, cloud 5xx (INTERNAL_SERVER_ERROR) is expected
        # behavior — server-side issue, not a client bug. Only log the
        # response at DEBUG level when it succeeded; log failures at WARNING
        # to avoid log spam during sustained outages.
        if isinstance(jresp, dict) and "errors" in jresp:
            logger.warning(
                f"wan send8 cloud error: {json.dumps(jresp.get('errors'))}",
                "wanSendMessage", mainwin
            )
        else:
            logger.debug("wan send8 JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
        return jresp
    except Exception as e:
        logger.warning(f"ErrorwanSendMessage8: {e}", "wanSendMessage", mainwin)
        logger.error(f"WAN send message trouble payload: {msg_req}")

async def wanHandleRxMessage(mainwin):
    logger.info("Start WAN RX task")
    while not mainwin.get_wan_msg_subscribed():
        logger.debug("Waiting for WAN websocket subscription")
        await asyncio.sleep(1)
    logger.info("WAN RX ready to receive messages")
    websocket = mainwin.get_websocket()
    in_msg_queue = mainwin.get_wan_msg_queue()
    while True:
        try:
            response = await websocket.recv()
            logger.debug("WAN RECEIVED SOMETHING:" + response)
            response_data = json.loads(response)
            if response_data["type"] == "data":
                command = response_data["payload"]["data"]["onMessageReceived"]
                logger.debug(f"WAN chat message received: {command}")
                asyncio.create_task(in_msg_queue.put(command))
            elif response_data.get("type") == "ka":
                this_ts = datetime.now()
                td = this_ts - last_connected_ts
                td_seconds = td.total_seconds()
                if td_seconds > 90:
                    logger.warning("WAN keep-alive out of sync")
                    last_connected_ts = this_ts
                else:
                    last_connected_ts = this_ts
            else:
                logger.warning(f"WAN unknown message: {response}")
        except ConnectionClosedError:
            logger.error("WAN RX connection lost. Attempting to reconnect...")
            break

def getSignedHeaders(url, credentials):
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    request = AWSRequest(method='GET', url=url, data='')
    SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
    return dict(request.headers.items())

async def subscribeToWanChat(mainwin, auth_token, chat_id="nobody", max_retries=50):
    """
    Subscribe to WAN Chat via WebSocket.
    - CN (TCB):  graphql-ws subprotocol, token in query string
    - Intl (AppSync): graphql-ws subprotocol, token in Authorization header

    All endpoint resolution handled by CloudEndpointConfig.

    Both versions use the same wire-level semantics:
      CN side: `onMessageReceived(chatID)` subscription via TCB WebSocket graphql-ws
      Intl side: `onMessageReceived(chatID)` subscription via AppSync graphql-ws
    """
    cfg = get_endpoint_config()
    retry_count = 0
    base_backoff = 5
    # Track consecutive 401s separately so we can apply a longer backoff and
    # trigger an auth-refresh on each retry. A long-lived app that reuses a
    # cached token past its 1h expiry will otherwise spin forever on 401.
    consecutive_auth_failures = 0
    last_used_token: Optional[str] = None

    while retry_count < max_retries:
        try:
            # Always pull a fresh token from auth_manager; never reuse the
            # stale auth_token parameter from initial subscription. The
            # auth_manager is responsible for refreshing expired tokens via
            # the refresh_token grant.
            #
            # On CN we prefer the 30-day WeChat session token over the
            # 10-minute access_token so the WS connection survives the
            # access_token's natural expiry. The server-side
            # ``ecan-graphql-ws`` verifies this eCan-signed session token
            # directly on every reconnect.
            id_token = _resolve_ws_token(mainwin, auth_token)
            if not id_token:
                # No fresh token — auth_manager cleared credentials because the
                # token expired and there is no refresh_token (e.g., WeChat
                # login). The auth_token parameter is the same stale token
                # we've already proven doesn't work; using it again just
                # triggers another 401. Stop retrying — the user must re-login.
                if consecutive_auth_failures > 0 or last_used_token:
                    logger.error(
                        "[wan_chat] No usable token from auth_manager; "
                        "stopping reconnect loop (user re-login required)."
                    )
                    if mainwin:
                        mainwin.set_wan_connected(False)
                    return
                # First connection before any auth failure: only fall back to
                # the bootstrap param if mainwin isn't ready yet.
                id_token = auth_token

            # If we're retrying because of an auth failure, force a hard
            # token refresh to make sure we never reuse the same bad token.
            if consecutive_auth_failures > 0 and mainwin and hasattr(mainwin, 'auth_manager'):
                try:
                    am = mainwin.auth_manager
                    if am and hasattr(am, 'cognito_service') and am.cognito_service:
                        rt = (am.tokens or {}).get('RefreshToken') or \
                             (am.tokens or {}).get('refresh_token')
                        if rt:
                            logger.info("[wan_chat] Forcing on-demand token refresh after 401")
                            am.cognito_service.refresh_tokens(rt)
                            id_token = _resolve_ws_token(mainwin, auth_token)
                except Exception as _ref_err:
                    logger.warning(f"[wan_chat] Forced token refresh failed: {_ref_err}")

            if id_token and id_token == last_used_token and consecutive_auth_failures > 0:
                # Same token came back even after a forced refresh attempt —
                # the refresh token itself is no good. Back off significantly
                # so we don't hammer the server while waiting for the user to
                # re-login.
                backoff_for_auth = min(60 * (2 ** min(consecutive_auth_failures - 1, 4)), 600)
                logger.warning(
                    f"[wan_chat] Token refresh returned same token; "
                    f"backing off {backoff_for_auth}s (attempt {retry_count + 1}/{max_retries}). "
                    f"User re-login required."
                )
                await asyncio.sleep(backoff_for_auth)
                continue

            last_used_token = id_token
            ws_url = cfg.build_ws_url(id_token)
            ws_host = cfg.host
            logger.debug(f"[wan_chat] Connecting: {ws_url[:80]}, host={ws_host}, is_cn={cfg.is_cn}")

            ssl_context = ssl.create_default_context(cafile=certifi.where())
            timeout = aiohttp.ClientTimeout(total=60, connect=60, sock_read=300)

            if cfg.is_cn:
                await _wan_chat_tcb_loop(
                    cfg=cfg, ws_url=ws_url, ws_host=ws_host,
                    chat_id=chat_id, id_token=id_token,
                    ssl_context=ssl_context, timeout=timeout,
                    mainwin=mainwin, retry_count=retry_count,
                )
            else:
                await _wan_chat_appsync_loop(
                    cfg=cfg, ws_url=ws_url, ws_host=ws_host,
                    chat_id=chat_id, id_token=id_token,
                    ssl_context=ssl_context, timeout=timeout,
                    mainwin=mainwin, retry_count=retry_count,
                )
            # If we reach here, connection was lost — retry
            raise Exception("Connection lost")

        except asyncio.CancelledError:
            logger.info("[wan_chat] Subscription cancelled")
            if mainwin:
                mainwin.set_wan_connected(False)
            return

        except Exception as e:
            retry_count += 1
            err_str = str(e)
            # aiohttp wraps the underlying HTTP error in WSServerHandshakeError
            # with status and message attributes.
            is_auth_error = (
                '401' in err_str
                or 'Invalid response status' in err_str
                or 'Unauthorized' in err_str
            )

            if is_auth_error:
                consecutive_auth_failures += 1
                logger.error(
                    f"[wan_chat] AUTH FAILURE (attempt {retry_count}/{max_retries}): {e}. "
                    f"Consecutive 401s={consecutive_auth_failures}."
                )
                # Nudge the SessionSupervisor to refresh now — without this the
                # WS loop sits in 5/10/20/40/80/120s backoff for an hour while
                # the supervisor's 30s tick silently no-ops on the still-valid
                # local TTL. notify_token_rejected(force=True) bypasses the
                # TTL guard and runs an immediate refresh / silent re-auth.
                if mainwin is not None and consecutive_auth_failures in (1, 3):
                    try:
                        from auth.session_supervisor import get_session_supervisor
                        sup = get_session_supervisor()
                        if sup is not None:
                            sup.notify_token_rejected(source="wan_chat_ws_401")
                            logger.info(
                                "[wan_chat] Nudged SessionSupervisor to refresh token "
                                "(consecutive_401s=%d)", consecutive_auth_failures,
                            )
                    except Exception as nudge_exc:
                        logger.warning(f"[wan_chat] Failed to nudge supervisor: {nudge_exc}")
                # No point backing off quickly — auth needs seconds to refresh.
                # 5s, 10s, 20s, 40s, 80s, 120s capped.
                backoff_time = min(5 * (2 ** min(consecutive_auth_failures - 1, 4)), 120)
            else:
                consecutive_auth_failures = 0
                backoff_time = min(base_backoff * (2 ** (retry_count - 1)), 60)
                noteworthy = retry_count in (1, 2, 5, 10, 20, 30, 40, 50)
                # Generic 'Connection lost' is just the wrapper layer noticing
                # the inner loop returned (which the inner loop already logged
                # with the actual cause). Avoid double-logging at ERROR — the
                # inner loop's INFO/ERROR is the source of truth.
                is_synthetic_connection_lost = err_str.strip() == "Connection lost"
                if noteworthy and not is_synthetic_connection_lost:
                    logger.error(f"[wan_chat] Error (attempt {retry_count}/{max_retries}): {e}")
                elif noteworthy:
                    logger.info(f"[wan_chat] Retrying after: {e}")
                else:
                    logger.debug(f"[wan_chat] Error (attempt {retry_count}/{max_retries}): {e}")

            if retry_count < max_retries:
                logger.info(f"[wan_chat] Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error("[wan_chat] Max retries reached")
                if mainwin:
                    mainwin.set_wan_connected(False)
                break


async def _wan_chat_tcb_loop(cfg, ws_url, ws_host, chat_id, id_token,
                             ssl_context, timeout, mainwin, retry_count):
    """CN: TCB 自建 WS 服务 (graphql-ws / AppSync-compatible).

    Connects to wss://.../ws with subprotocol "graphql-ws" — wire-level
    identical to AWS AppSync, so the same retry / keepalive logic applies.
    Receives frames of shape:
      { type: 'data', id, payload: { data: { onMessageReceived: <msg> } } }
    """
    ka_timeout_sec = 300
    recv_timeout = ka_timeout_sec + 10
    sub_id = f"wan-sub-{chat_id}"

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                ws_url,
                protocols=['graphql-ws'],
                ssl=ssl_context,
                heartbeat=25,
                autoping=True,
            ) as websocket:
                logger.info("[wan_chat:TCB-WS] Connected to WebSocket")

                # Step 1: connection_init
                await websocket.send_str(json.dumps({"type": "connection_init"}))

                # Wait for connection_ack
                while True:
                    msg = await websocket.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        response_data = json.loads(msg.data)
                        if response_data.get("type") == "connection_ack":
                            logger.info("[wan_chat:TCB-WS] Connection acknowledged")
                            mainwin.set_wan_connected(True)
                            mainwin.set_websocket(websocket)
                            last_connected_ts = datetime.now()
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.error(f"[wan_chat:TCB-WS] Connection closed during ack: {msg}")
                        mainwin.set_wan_connected(False)
                        return

                if not mainwin.get_wan_connected():
                    raise Exception("TCB-WS connection not established")

                # Step 2: start subscription — AppSync-compatible payload shape
                sub_data = {
                    "query": gen_wan_subscription_connection_string(),
                    "variables": {"chatID": chat_id}
                }
                sub_payload = json.dumps(sub_data)
                # CN WeChat token is stored as "userId/@@/jwt" but the TCB WS
                # server expects either "Bearer <jwt>" or a bare JWT.
                # Extract the JWT part (after "/@@/") so the subscription auth succeeds.
                auth_value = id_token
                if id_token and '/@@/' in id_token:
                    auth_value = id_token.split('/@@/', 1)[-1]
                sub_headers = {'host': ws_host, 'Authorization': auth_value} if auth_value else {}
                sub_reg = {
                    "id": sub_id,
                    "payload": {
                        "data": sub_payload,
                        "extensions": {"authorization": sub_headers},
                    },
                    "type": "start",
                }
                await websocket.send_str(json.dumps(sub_reg))

                # Wait for start_ack
                while True:
                    msg = await websocket.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        response_data = json.loads(msg.data)
                        if response_data.get("type") == "start_ack":
                            logger.info(f"[wan_chat:TCB-WS] Subscribed to chat_id={chat_id}")
                            mainwin.set_wan_msg_subscribed(True)
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.error(f"[wan_chat:TCB-WS] Connection closed during subscription ack: {msg}")
                        mainwin.set_wan_connected(False)
                        return

                # Step 3: message loop
                while True:
                    msg = await asyncio.wait_for(websocket.receive(), timeout=recv_timeout)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        rcvd = json.loads(msg.data)
                        # data frame: AppSync wraps payload.data.<fieldName>
                        if rcvd.get("type") == "data":
                            inner = (rcvd.get("payload") or {}).get("data") or {}
                            inner_msg = inner.get("onMessageReceived")
                            if inner_msg:
                                _handle_wan_message(inner_msg, mainwin)
                        elif rcvd.get("type") == "ka":
                            this_ts = datetime.now()
                            td = this_ts - last_connected_ts
                            if td.total_seconds() > 90:
                                logger.warning("WAN keep-alive out of sync")
                                last_connected_ts = this_ts
                            else:
                                last_connected_ts = this_ts
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info("[wan_chat:TCB-WS] WebSocket closed normally")
                        mainwin.set_wan_connected(False)
                        return
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"[wan_chat:TCB-WS] WebSocket error: {websocket.exception()}")
                        mainwin.set_wan_connected(False)
                        return
    except asyncio.CancelledError:
        logger.error("[wan_chat:TCB-WS] Cancelled")
        if mainwin:
            mainwin.set_wan_connected(False)
        raise
    except asyncio.TimeoutError:
        # Expected when the TCB gateway cuts idle WS connections faster than
        # our ka_timeout_sec (300s). Reconnect succeeds immediately on the
        # next iteration, so this is transient infrastructure noise — log it
        # at INFO rather than ERROR to keep monitoring dashboards clean.
        logger.info(
            f"[wan_chat:TCB-WS] Idle recv timed out after {recv_timeout}s "
            f"(server-side idle close); reconnecting"
        )
        if mainwin:
            mainwin.set_wan_connected(False)
    except Exception as e:
        # Re-raise after logging so the outer retry loop (which knows how to
        # detect 401 / WSServerHandshakeError and nudge SessionSupervisor)
        # actually sees the real exception. Previously this swallowed the
        # exception with `return`, leaving the outer retry loop with the
        # generic "Connection lost" placeholder — which failed the
        # ``is_auth_error`` check and meant supervisor never got nudged.
        # Symptom: WS reconnect loop hammered every 60s with
        # "WSServerHandshakeError: 401" ERROR lines indefinitely.
        logger.error(
            f"[wan_chat:TCB-WS] Loop error: {type(e).__name__}: {e or '(no message)'}"
        )
        if mainwin:
            mainwin.set_wan_connected(False)
        raise


def _handle_wan_message(inner, mainwin):
    """Handle received WAN message, dispatch to appropriate queue."""
    if not inner:
        return
    inner_type = inner.get("type")
    try:
        if inner_type == "chat":
            asyncio.create_task(mainwin.gui_chat_msg_queue.put(inner))
        elif inner_type == "command" and inner.get("contents", {}).get("cmd") in ["cancel", "pause", "suspend", "resume"]:
            asyncio.create_task(mainwin.gui_rpa_msg_queue.put(inner))
        elif inner_type in ["logs", "heartbeat"]:
            asyncio.create_task(mainwin.gui_monitor_msg_queue.put(inner))
        else:
            asyncio.create_task(mainwin.gui_monitor_msg_queue.put(inner))
    except Exception:
        pass


async def _wan_chat_appsync_loop(cfg, ws_url, ws_host, chat_id, id_token,
                                  ssl_context, timeout, mainwin, retry_count):
    """Intl: AppSync graphql-ws protocol (original logic)."""
    ka_timeout_sec = 300
    recv_timeout = ka_timeout_sec + 10

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                ws_url,
                protocols=['graphql-ws'],
                ssl=ssl_context,
                heartbeat=25,
                autoping=True,
            ) as websocket:
                logger.info("[wan_chat:AppSync] Connected to WebSocket")

                init_msg = {"type": "connection_init"}
                await websocket.send_str(json.dumps(init_msg))

                # Wait for connection_ack
                while True:
                    msg = await websocket.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        response_data = json.loads(msg.data)
                        if response_data.get("type") == "connection_ack":
                            logger.info("[wan_chat:AppSync] Connection acknowledged")
                            mainwin.set_wan_connected(True)
                            mainwin.set_websocket(websocket)
                            last_connected_ts = datetime.now()
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.error(f"[wan_chat:AppSync] Connection closed during ack: {msg}")
                        mainwin.set_wan_connected(False)
                        return

                if not mainwin.get_wan_connected():
                    raise Exception("AppSync connection not established")

                # Subscribe via GraphQL
                sub_data = {
                    "query": gen_wan_subscription_connection_string(),
                    "variables": {"chatID": chat_id}
                }
                sub_payload = json.dumps(sub_data)
                sub_headers = {'host': ws_host, 'Authorization': id_token}
                sub_reg = {
                    "id": "1",
                    "payload": {
                        "data": sub_payload,
                        "extensions": {"authorization": sub_headers}
                    },
                    "type": "start"
                }
                await websocket.send_str(json.dumps(sub_reg))

                # Wait for start_ack
                while True:
                    msg = await websocket.receive()
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        response_data = json.loads(msg.data)
                        if response_data.get("type") == "start_ack":
                            logger.info(f"[wan_chat:AppSync] Subscribed to chat_id={chat_id}")
                            mainwin.set_wan_msg_subscribed(True)
                            break
                    elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                        logger.error(f"[wan_chat:AppSync] Connection closed during subscription ack: {msg}")
                        mainwin.set_wan_connected(False)
                        return

                # Message loop
                while True:
                    msg = await asyncio.wait_for(websocket.receive(), timeout=recv_timeout)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        rcvd = json.loads(msg.data)
                        if "payload" in rcvd and "onMessageReceived" in rcvd["payload"]["data"]:
                            inner = rcvd["payload"]["data"]["onMessageReceived"]
                            if inner.get("type") == "chat":
                                asyncio.create_task(mainwin.gui_chat_msg_queue.put(inner))
                            elif inner.get("type") == "command" and inner.get("contents", {}).get("cmd") in ["cancel", "pause", "suspend", "resume"]:
                                asyncio.create_task(mainwin.gui_rpa_msg_queue.put(inner))
                            elif inner.get("type") in ["logs", "heartbeat"]:
                                asyncio.create_task(mainwin.gui_monitor_msg_queue.put(inner))
                            else:
                                asyncio.create_task(mainwin.gui_monitor_msg_queue.put(inner))
                        elif rcvd.get("type") == "ka":
                            last_connected_ts = datetime.now()
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        logger.info("[wan_chat:AppSync] WebSocket closed normally")
                        mainwin.set_wan_connected(False)
                        return
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        logger.error(f"[wan_chat:AppSync] WebSocket error: {websocket.exception()}")
                        mainwin.set_wan_connected(False)
                        return
    except asyncio.CancelledError:
        logger.error("[wan_chat:AppSync] Cancelled")
        if mainwin:
            mainwin.set_wan_connected(False)
        raise
    except asyncio.TimeoutError:
        # Expected when the AppSync gateway cuts idle WS connections faster
        # than our ka_timeout_sec (300s). Reconnect succeeds immediately on
        # the next iteration, so this is transient infrastructure noise —
        # log it at INFO rather than ERROR.
        logger.info(
            f"[wan_chat:AppSync] Idle recv timed out after {recv_timeout}s "
            f"(server-side idle close); reconnecting"
        )
        if mainwin:
            mainwin.set_wan_connected(False)
    except Exception as e:
        logger.error(f"[wan_chat:AppSync] Loop error: {e}")
        if mainwin:
            mainwin.set_wan_connected(False)

def parseCommandString(input_str):
    if input_str.startswith(":"):
        input_str = input_str[1:]
        try:
            root = ET.fromstring(input_str)
            cmd_type = root.tag
            if cmd_type == "cmd":
                command = {}
                cmd_name = root.findtext('.')
                command["name"] = cmd_name.strip() if cmd_name else None
                for child in root:
                    if child.tag in ["bots", "missions", "skills", "vehicle", "logs", "log outlets", "data", "file"]:
                        if child.text:
                            command[child.tag] = child.text.strip()
                        else:
                            command[child.tag] = None
                logger.debug(f"Parsed WAN command: {command}")
                return json.dumps(command, indent=4)
            elif cmd_type == "resp":
                response = {}
                resp_name = root.findtext('.')
                response["name"] = resp_name.strip() if resp_name else None
                for child in root:
                    if child.tag in ["hil", "file"]:
                        if child.text:
                            response[child.tag] = child.text.strip()
                        else:
                            response[child.tag] = None
                logger.debug(f"Parsed WAN response: {response}")
                return cmd_type, json.dumps(response, indent=4)
        except ET.ParseError:
            return "Invalid XML command format."
    else:
        return "chat", input_str
