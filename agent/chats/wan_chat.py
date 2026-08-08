import json
import ssl
import asyncio
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
        logger.debug(f"ErrorwanSendMessage:{traceback.format_exc()} {e}", "wanSendMessage", mainwin)

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
        logger.debug("wan send8 JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
        return jresp
    except Exception as e:
        logger.debug(f"ErrorwanSendMessage8:{traceback.format_exc()} {e}", "wanSendMessage", mainwin)
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

    while retry_count < max_retries:
        try:
            id_token = auth_token
            if mainwin and hasattr(mainwin, 'get_auth_token'):
                fresh_token = mainwin.get_auth_token()
                if fresh_token:
                    id_token = fresh_token

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
            backoff_time = min(base_backoff * (2 ** (retry_count - 1)), 60)
            noteworthy = retry_count in (1, 2, 5, 10, 20, 30, 40, 50)
            if noteworthy:
                logger.error(f"[wan_chat] Error (attempt {retry_count}/{max_retries}): {e}")
            else:
                logger.debug(f"[wan_chat] Error (attempt {retry_count}/{max_retries}): {e}")
            if retry_count < max_retries:
                if noteworthy:
                    logger.info(f"[wan_chat] Retrying in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"[wan_chat] Max retries reached")
                if mainwin:
                    mainwin.set_wan_connected(False)
                break


async def _wan_chat_tcb_loop(cfg, ws_url, ws_host, chat_id, id_token,
                             ssl_context, timeout, mainwin, retry_count):
    """CN: TCB WebSocket graphql-ws protocol.

    Wire-level identical to ``_wan_chat_appsync_loop`` — same connection_init,
    start with payload.data, start_ack, and `data` frames wrapping
    onMessageReceived. The CN WebSocket SCF speaks graphql-ws.
    """
    import threading
    ka_timeout_sec = 300
    sub_id = "1"

    sub_data = {
        "query": gen_wan_subscription_connection_string(),
        "variables": {"chatID": chat_id},
    }
    sub_payload = json.dumps(sub_data)
    sub_headers = {'host': ws_host, 'Authorization': id_token}
    start_msg = json.dumps({
        "id": sub_id,
        "payload": {
            "data": sub_payload,
            "extensions": {"authorization": sub_headers},
        },
        "type": "start",
    })

    connected_event = threading.Event()
    subscribed_event = threading.Event()

    def _on_open(ws):
        logger.info(f"[wan_chat:TCB] Connected, sending connection_init for chat_id={chat_id}")
        ws.send(json.dumps({"type": "connection_init"}))
        if mainwin:
            mainwin.set_wan_connected(True)
        connected_event.set()

    def _on_message(ws, msg):
        try:
            data = json.loads(msg)
        except Exception:
            return

        msg_type = data.get("type", "")
        if msg_type == "connection_ack":
            logger.info(f"[wan_chat:TCB] connection_ack, sending start")
            ws.send(start_msg)
            return
        if msg_type == "start_ack":
            logger.info(f"[wan_chat:TCB] Subscribed to chat_id={chat_id}")
            if mainwin:
                mainwin.set_wan_msg_subscribed(True)
            subscribed_event.set()
            return
        if msg_type == "ka":
            return

        if msg_type == "data":
            payload = data.get("payload", {}) or {}
            inner = payload.get("data", {}).get("onMessageReceived")
            if not inner:
                return
            inner_type = inner.get("type")
            try:
                loop = asyncio.get_event_loop()
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

    def _on_error(ws, err):
        logger.error(f"[wan_chat:TCB] Error: {err}")

    def _on_close(ws, code, msg):
        logger.info(f"[wan_chat:TCB] Closed: code={code}")
        if mainwin:
            mainwin.set_wan_connected(False)

    ws_client = ws_client_module.WebSocketApp(
        ws_url,
        on_message=_on_message,
        on_open=_on_open,
        on_error=_on_error,
        on_close=_on_close,
        subprotocols=['graphql-ws'],
    )

    def _run():
        ws_client.run_forever(
            sslopt={"ca_certs": certifi.where()},
            ping_interval=25,
            ping_timeout=10,
        )

    thread = threading.Thread(target=_run, daemon=True, name="tcb-ws-chat")
    thread.start()

    # Wait for connection
    if not connected_event.wait(timeout=15):
        logger.error("[wan_chat:TCB] Connection timeout")
        ws_client.close()
        raise Exception("TCB connection timeout")

    if not subscribed_event.wait(timeout=10):
        logger.warning("[wan_chat:TCB] Subscription not confirmed")

    # Keep alive: wait for thread to finish (or external stop)
    while thread.is_alive():
        thread.join(timeout=1)


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
