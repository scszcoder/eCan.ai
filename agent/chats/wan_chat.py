import json
import ssl
import asyncio
import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from agent.cloud_api.cloud_api import gen_wan_send_chat_message_string, gen_wan_subscription_connection_string
import base64
from datetime import datetime
import xml.etree.ElementTree as ET
import traceback
import requests
import os
import websockets
from utils.logger_helper import logger_helper as logger

# Wan Chat Logic
# Commander will connect to websocket and subscribe, and wan logging is default off, then sit in a loop
# and listen for turn on logging command,
# Staff Officer will get online and connect to websocket and shoot out ping command to any commander out there.
# once hearing ack back from the commander off websocket, it sends a request logging command if needed.
#


async def wanStopSubscription(mainwin):
    APPSYNC_API_ENDPOINT_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    init_msg = {
        "type": "stop"
    }

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

                except websockets.exceptions.ConnectionClosedError as e:
                    logger.error(f"WAN stop subscription connection closed: {e}")
                    mainwin.set_wan_connected(False)
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"WAN stop subscription JSON decode failed: {e}")
                    break
        except Exception as e:
            logger.error(f"Failed to stop WAN subscription: {e}")


def validate_msg_fields(msg_req, mainwin):
    # Expected fields and types based on the schema
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
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'

    session = mainwin.session
    token = mainwin.get_auth_token()

    try:
        validate_msg_fields(msg_req, mainwin)
        variables = {
            "input": {
                "chatID": msg_req["chatID"],
                "sender": msg_req["sender"],
                "receiver": msg_req["receiver"],
                "type": msg_req["type"],
                "contents": msg_req["contents"],
                # "content": {
                #     "text": msg_req["contents"]
                # },
                "parameters": msg_req["parameters"]
            }
        }
        query_string = gen_wan_send_chat_message_string()
        headers = {
            'Content-Type': "application/json",
            'Authorization': token,
            'cache-control': "no-cache",
        }
        # print("about to send wan msg:", variables, query_string, headers)
        # print("++++++++++++++++++++++++++++++++++++++++++++++++++++")
        session.headers.update(headers)
        response = session.post(
            url=APPSYNC_API_ENDPOINT_URL,
            json={
                'query': query_string,
                'variables': variables
            },
            timeout=30  # Timeout in seconds as int or float
        )
        jresp = response.json()
        # logger.debug("wan send JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
        return jresp

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorwanSendMessage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorwanSendMessage traceback information not available:" + str(e)
        logger.debug(ex_stat, "wanSendMessage", mainwin)



async def wanSendMessage8(msg_req, mainwin):
    try:
        APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
        WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'
        token = mainwin.get_auth_token()

        variables = {
            "input": {
                "chatID": msg_req["chatID"],
                "sender": msg_req["sender"],
                "receiver": msg_req["receiver"],
                "type": msg_req["type"],
                "contents": msg_req["contents"],
                # "content": {
                #     "text": msg_req["contents"]
                # },
                "parameters": msg_req["parameters"]
            }
        }
        query_string = gen_wan_send_chat_message_string()
        headers = {
            'Content-Type': "application/json",
            'Authorization': token,
            'cache-control': "no-cache",
        }
        logger.debug("about to send wan msg: "+json.dumps(variables), "wanSendMessage", mainwin)
        # logger.debug("++++++++++++++++++++++++++++++++++++++++++++++++++++", "wanSendMessage", mainwin)
        async with aiohttp.ClientSession() as session8:
            async with session8.post(
                    url=APPSYNC_API_ENDPOINT_URL,
                    timeout=aiohttp.ClientTimeout(total=30),
                    headers=headers,
                    json={
                            'query': query_string,
                            'variables': variables
                    }
            ) as response:
                jresp = await response.json()
                logger.debug("wan send8 JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
                return jresp

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorwanSendMessage8:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorwanSendMessage8 traceback information not available:" + str(e)
        logger.debug(ex_stat, "wanSendMessage", ex_stat)
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
                # Execute the command here
                asyncio.create_task(in_msg_queue.put(command))
            elif response_data.get("type") == "ka":
                this_ts = datetime.now()
                td = this_ts - last_connected_ts
                # Get the time difference in seconds
                td_seconds = td.total_seconds()
                if td_seconds > 90:
                    # something is wrong, we're suppose to receive this every minute or so.
                    logger.warning("WAN keep-alive out of sync")
                    last_connected_ts = this_ts
                else:
                    last_connected_ts = this_ts
            else:
                logger.warning(f"WAN unknown message: {response}")
        except websockets.exceptions.ConnectionClosedError:
            logger.error("WAN RX connection lost. Attempting to reconnect...")
            break


def getSignedHeaders(url, credentials):
    request = AWSRequest(method='GET', url=url, data='')
    SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
    return dict(request.headers.items())

# Function to subscribe to commands
async def subscribeToWanChat(mainwin, auth_token, chat_id="nobody", max_retries=50):
    """
    Subscribe to WAN Chat with WebSocket
    
    Args:
        mainwin: Main window instance
        auth_token: Authentication token
        chat_id: Chat ID to subscribe to
        max_retries: Maximum number of retry attempts (default: 50)
    """
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'
    WS_API_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com'
    id_token = auth_token
    ka_timeout_sec = 300
    retry_count = 0
    base_backoff = 5
    
    # Use loop instead of recursion to prevent stack overflow
    while retry_count < max_retries:
        try:
            api_headers = {
                'content-type': 'application/json',
                'host': WS_API_HOST,
                'Authorization': id_token
            }
            # Convert the dictionary to a JSON string
            json_str = json.dumps(api_headers)

            # Encode the JSON string to bytes
            json_bytes = json_str.encode('utf-8')

            # Encode the bytes to a Base64 string
            base64_bytes = base64.b64encode(json_bytes)

            # Convert the Base64 bytes back to a string
            base64_str = base64_bytes.decode('utf-8')

            ws_url = f"{WS_URL}?header={base64_str}&payload=e30="

            # Create SSL context and disable verification for AWS AppSync
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            # Log proxy usage if configured (aiohttp will automatically use HTTPS_PROXY)
            https_proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
            if https_proxy:
                logger.info(f"🌐 Proxy detected, aiohttp will use: {https_proxy}")

            # Create aiohttp session with timeout configuration
            # aiohttp automatically uses HTTPS_PROXY/HTTP_PROXY environment variables
            timeout = aiohttp.ClientTimeout(
                total=60,  # Total timeout for the operation
                connect=60,  # Connection timeout
                sock_read=300  # Socket read timeout (for long-lived connections)
            )
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # Connect to WebSocket with AppSync subprotocol
                async with session.ws_connect(
                    ws_url,
                    protocols=['graphql-ws'],
                    ssl=ssl_context,
                    heartbeat=25,  # Send ping every 25s to keep connection alive
                    autoping=True,  # Automatically respond to pings
                ) as websocket:
                    logger.info("Connected to WAN chat WebSocket")
                    # Send connection init message
                    init_msg = {"type": "connection_init"}
                    await websocket.send_str(json.dumps(init_msg))

                    # Wait for connection ack
                    while True:
                        try:
                            msg = await websocket.receive()
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                response_data = json.loads(msg.data)
                                logger.debug(f"WAN websocket received: {response_data}")
                                if response_data.get("type") == "connection_ack":
                                    logger.info("WAN chat websocket connection acknowledged")
                                    mainwin.set_wan_connected(True)
                                    mainwin.set_websocket(websocket)
                                    ka_timeout_sec = response_data["payload"]["connectionTimeoutMs"]/1000
                                    last_connected_ts = datetime.now()
                                    recv_timeout = ka_timeout_sec + 10
                                    logger.info(f"Keep Alive: server={ka_timeout_sec}s, client recv timeout={recv_timeout}s")
                                    break
                            elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                logger.error(f"WAN Chat Connection closed during ack: {msg}")
                                mainwin.set_wan_connected(False)
                                break
                        except asyncio.CancelledError:
                            logger.info("WAN Chat connection cancelled during setup (logout/shutdown)")
                            mainwin.set_wan_connected(False)
                            raise  # Re-raise to propagate cancellation
                        except json.JSONDecodeError as e:
                            logger.error(f"Failed to decode JSON: {e}")
                            break

                    if mainwin.get_wan_connected():
                        # now request to subscribe to the API
                        logger.debug("NOW start to wan chat subscribe1")
                        sub_data = {
                            "query": gen_wan_subscription_connection_string(),
                            "variables": {"chatID": chat_id}
                        }
                        logger.debug("NOW start to wan chat subscribe2")

                        sub_data_string = json.dumps(sub_data)
                        logger.debug("NOW start to wan chat subscribe3"+sub_data_string)

                        SUB_REG = {
                            "id": "1",
                            "payload": {
                                "data": sub_data_string,
                                "extensions": {
                                    "authorization": {
                                        "Authorization": id_token,
                                        "host": WS_API_HOST
                                    }
                                }
                            },
                            "type": "start"
                        }
                        logger.debug("SENDING WAN CHATWEBSOCKET SUBSCRIPTION REGISTRATION REQUEST!!!!"+json.dumps(SUB_REG))

                        await websocket.send_str(json.dumps(SUB_REG))

                        while True:
                            try:
                                msg = await websocket.receive()
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    response_data = json.loads(msg.data)
                                    logger.debug(f"ACK RECEIVED: {response_data}")
                                    if response_data.get("type") == "start_ack":
                                        logger.debug("WAN CHATMESSAGE SUBSCRIPTION TO "+"SUCCEEDED!!!!")
                                        logger.debug(chat_id)

                                        mainwin.set_wan_msg_subscribed(True)
                                        last_subscribed_ts = datetime.now()
                                        break
                                elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                                    logger.error(f"Connection closed during subscription ack: {msg}")
                                    mainwin.set_wan_connected(False)
                                    break
                            except asyncio.CancelledError:
                                logger.error("WAN Chat subscription cancelled during ack wait (logout/shutdown)")
                                mainwin.set_wan_connected(False)
                                mainwin.set_wan_msg_subscribed(False)
                                raise  # Re-raise to propagate cancellation
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to decode JSON: {e}")
                                mainwin.set_wan_connected(False)
                                break

                        while True:
                            try:
                                # Use recv_timeout configured at connection time
                                msg = await asyncio.wait_for(websocket.receive(), timeout=recv_timeout)
                                
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    logger.debug(f"WAN subscription message: {msg.data}")
                                    # send the message to
                                    rcvd = json.loads(msg.data)
                                elif msg.type == aiohttp.WSMsgType.CLOSED:
                                    logger.info("WebSocket connection closed normally")
                                    mainwin.set_wan_connected(False)
                                    break
                                elif msg.type == aiohttp.WSMsgType.ERROR:
                                    logger.error(f"WebSocket error: {websocket.exception()}")
                                    mainwin.set_wan_connected(False)
                                    break
                                else:
                                    continue  # Skip non-text messages
                                if "payload" in rcvd:
                                    if "onMessageReceived" in rcvd["payload"]["data"]:
                                        logger.debug("WAN message payload type: %s", type(rcvd["payload"]["data"]["onMessageReceived"]))
                                        # route the message either to chat or RPA
                                        # possible types: chat/command/ping/loopback/pong/logs/request/heartbeat/chat
                                        if rcvd["payload"]["data"]["onMessageReceived"]["type"] == "chat":
                                            asyncio.create_task(mainwin.gui_chat_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                                        elif rcvd["payload"]["data"]["onMessageReceived"]["type"] == "command" and rcvd["payload"]["data"]["onMessageReceived"]["contents"]["cmd"] in ["cancel", "pause", "suspend", "resume"]:
                                            asyncio.create_task(mainwin.gui_rpa_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                                        elif rcvd["payload"]["data"]["onMessageReceived"]["type"] in ["logs", "heartbeat"]:
                                            asyncio.create_task(mainwin.gui_monitor_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                                        else:
                                            asyncio.create_task(mainwin.gui_monitor_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                                else:
                                    if "type" in rcvd:
                                        if rcvd["type"] == "ka":
                                            # Keep alive received - update timestamp
                                            # This is normal, just update the last connected time
                                            last_connected_ts = datetime.now()
                                            logger.trace(f"Keep Alive received, connection healthy")
                            except asyncio.CancelledError:
                                logger.error("WAN Chat message loop cancelled (logout/shutdown)")
                                mainwin.set_wan_connected(False)
                                raise  # Re-raise to propagate cancellation
                            except asyncio.TimeoutError:
                                logger.error("WebSocket recv timeout - connection may be closing")
                                mainwin.set_wan_connected(False)
                                break
                            except Exception as e:
                                traceback_info = traceback.extract_tb(e.__traceback__)
                                ex_stat = "ErrorsubscribeReceive:" + traceback.format_exc() + " " + str(e)
                                logger.debug(ex_stat)
                                mainwin.set_wan_connected(False)
                                break

                        if not mainwin.get_wan_connected():
                            # Connection was lost, will retry
                            logger.info("WAN Chat connection lost, will retry...")
                            raise Exception("Connection Lost")
            
            # If we got here, connection was successful and closed normally
            logger.info("WAN Chat connection completed successfully")
            return
        
        except asyncio.CancelledError:
            logger.info("WAN Chat subscription cancelled (logout/shutdown)")
            mainwin.set_wan_connected(False)
            # Don't retry when cancelled - this is intentional shutdown
            return
        
        except TimeoutError as e:
            retry_count += 1
            backoff_time = min(base_backoff * (2 ** (retry_count - 1)), 60)
            logger.error(f"Websocket Connection timeout: {e} (attempt {retry_count}/{max_retries})")
            logger.error(f"Connection details: URL={WS_URL[:50]}..., Host={WS_API_HOST}")
            logger.error("This may indicate: 1) Network connectivity issues, 2) Firewall blocking, 3) AWS AppSync service issues")
            logger.error(f"Error {subscribeToWanChat.__name__}: {traceback.format_exc()} {e}")
            if retry_count < max_retries:
                logger.info(f"Retrying WAN Chat connection in {backoff_time}s...")
                await asyncio.sleep(backoff_time)
            else:
                logger.error(f"Max retries ({max_retries}) reached for WAN Chat connection")
                logger.error(f"Please check: 1) Internet connection, 2) Firewall/proxy settings, 3) AWS AppSync service status")
                mainwin.set_wan_connected(False)
                break
    
    # If we exit the loop without returning, we've hit max retries
    logger.error(f"WAN Chat connection failed after {max_retries} attempts")


def parseCommandString(input_str):
    # Check if the string starts with ':'
    if input_str.startswith(":"):
        # Remove the leading ':' character
        input_str = input_str[1:]

        # Try to parse the XML content
        try:
            root = ET.fromstring(input_str)

            # Extract the command name from the text content of the <cmd> tag
            cmd_type = root.tag             # could be "cmd", "resp",

            # Parse known tags and add them to the command structure
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
        # Return the input string as a regular chat message
        return "chat", input_str