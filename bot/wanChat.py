import bot.Cloud
import json
import ssl
import websockets
import asyncio
import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from bot.Cloud import gen_wan_send_chat_message_string, gen_wan_subscription_connection_string
import base64
from datetime import datetime
from bot.Logger import log3
import xml.etree.ElementTree as ET
import traceback
import requests

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
                    print(f"RECEIVED: {response_data}")
                    if response_data.get("type") == "complete":
                        print("SUBSCRIPTION STOPPED!!!!")
                        mainwin.set_wan_msg_subscribed(False)
                        break

                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"Connection closed with error: {e}")
                    mainwin.set_wan_connected(False)
                    break
                except json.JSONDecodeError as e:
                    print(f"Failed to decode JSON: {e}")
                    break
        except Exception as e:
            print(f"Failed to stop subscription: {e}")


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
            log3(f"Field '{field}' is missing or None, which could cause an error."+json.dumps(msg_req), "wanSendMessage", mainwin)
        elif not isinstance(value, expected_type):
            log3(f"Field '{field}' has type {type(value)}, expected {expected_type}. Value: {value}"+json.dumps(msg_req), "wanSendMessage", mainwin)


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
        # log3("wan send JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
        return jresp

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorwanSendMessage:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorwanSendMessage traceback information not available:" + str(e)
        log3(ex_stat, "wanSendMessage", mainwin)



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
        log3("about to send wan msg: "+json.dumps(variables), "wanSendMessage", mainwin)
        # log3("++++++++++++++++++++++++++++++++++++++++++++++++++++", "wanSendMessage", mainwin)
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
                log3("wan send8 JRESP:"+json.dumps(jresp), "wanSendMessage", mainwin)
                return jresp

    except Exception as e:
        # Get the traceback information
        traceback_info = traceback.extract_tb(e.__traceback__)
        # Extract the file name and line number from the last entry in the traceback
        if traceback_info:
            ex_stat = "ErrorwanSendMessage8:" + traceback.format_exc() + " " + str(e)
        else:
            ex_stat = "ErrorwanSendMessage8 traceback information not available:" + str(e)
        log3(ex_stat, "wanSendMessage", ex_stat)
        print("trouble maker:", msg_req)

async def wanHandleRxMessage(mainwin):
    print("START WAN RX TASK")
    while not mainwin.get_wan_msg_subscribed():
        print("WAITING FOR WEBSOCKET")
        await asyncio.sleep(1)

    print("finally ready to receive....")
    websocket = mainwin.get_websocket()
    in_msg_queue = mainwin.get_wan_msg_queue()
    while True:
        try:
            response = await websocket.recv()
            log3("WAN RECEIVED SOMETHING:" + response)
            response_data = json.loads(response)
            if response_data["type"] == "data":
                command = response_data["payload"]["data"]["onMessageReceived"]
                print("Wan Chat Message received:", command)
                # Execute the command here
                asyncio.create_task(in_msg_queue.put(command))
            elif response_data.get("type") == "ka":
                this_ts = datetime.now()
                td = this_ts - last_connected_ts
                # Get the time difference in seconds
                td_seconds = td.total_seconds()
                if td_seconds > 90:
                    # something is wrong, we're suppose to receive this every minute or so.
                    print("WARNING: Keep Alive Out Of Sync")
                    last_connected_ts = this_ts
                else:
                    last_connected_ts = this_ts
            else:
                print("UNKNOWN MESSAGE! "+response)
        except websockets.exceptions.ConnectionClosedError:
            print("Connection lost. Attempting to reconnect...")
            break


def getSignedHeaders(url, credentials):
    request = AWSRequest(method='GET', url=url, data='')
    SigV4Auth(credentials, 'appsync', 'us-east-1').add_auth(request)
    return dict(request.headers.items())

# Function to subscribe to commands
async def subscribeToWanChat(mainwin, auth_token, chat_id="nobody"):
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'
    WS_API_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com'
    id_token = auth_token
    ka_timeout_sec = 300
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

        # Create SSL context to handle certificate verification
        ssl_context = ssl.create_default_context()
        # For AWS AppSync, we can safely disable hostname checking
        # as we're connecting to a known AWS service
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Open WS connection (use subprotocols only; AppSync auth is in query header param)
        async with websockets.connect(
            ws_url,
            subprotocols=['graphql-ws'],
            open_timeout=30,
            ssl=ssl_context,
        ) as websocket:
            print("Connected to Wan Chat WebSocket")
            # Send connection init message
            init_msg = {"type": "connection_init"}
            await websocket.send(json.dumps(init_msg))

            # Wait for connection ack
            while True:
                try:
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    print(f"RECEIVED: {response_data}")
                    if response_data.get("type") == "connection_ack":
                        print("WAN CHAT WEBSOCKET CONNECTED!!!!")
                        mainwin.set_wan_connected(True)
                        mainwin.set_websocket(websocket)
                        ka_timeout_sec = response_data["payload"]["connectionTimeoutMs"]/1000
                        last_connected_ts = datetime.now()
                        break
                except asyncio.CancelledError:
                    logger.info("WAN Chat connection cancelled during setup (logout/shutdown)")
                    mainwin.set_wan_connected(False)
                    raise  # Re-raise to propagate cancellation
                except websockets.exceptions.ConnectionClosedError as e:
                    logger.error(f"Wan Chat Connection closed with error: {e}")
                    mainwin.set_wan_connected(False)
                    break
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

                await websocket.send(json.dumps(SUB_REG))

                while True:
                    try:
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        print(f"ACK RECEIVED: {response_data}")
                        if response_data.get("type") == "start_ack":
                            print("WAN CHATMESSAGE SUBSCRIPTION TO "+"SUCCEEDED!!!!")
                            print(chat_id)

                            mainwin.set_wan_msg_subscribed(True)
                            last_subscribed_ts = datetime.now()
                            break
                    except asyncio.CancelledError:
                        logger.info("WAN Chat subscription cancelled during ack wait (logout/shutdown)")
                        mainwin.set_wan_connected(False)
                        mainwin.set_wan_msg_subscribed(False)
                        raise  # Re-raise to propagate cancellation
                    except websockets.exceptions.ConnectionClosedError as e:
                        logger.error(f"Connection closed with error: {e}")
                        mainwin.set_wan_connected(False)
                        break
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}")
                        mainwin.set_wan_connected(False)
                        break

                while True:
                    try:
                        # Add timeout to recv to prevent hanging during shutdown
                        message = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        print(f"WAN CHAT SUBSCRIBE Received message: {message}", type(message))  # this is string.
                        # send the message to
                        rcvd = json.loads(message)
                        if "payload" in rcvd:
                            if "onMessageReceived" in rcvd["payload"]["data"]:
                                print("actual msg:", type(rcvd["payload"]["data"]["onMessageReceived"]))
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
                                    this_ts = datetime.now()
                                    td = this_ts - last_connected_ts
                                    # Get the time difference in seconds
                                    td_seconds = td.total_seconds()
                                    if td_seconds > ka_timeout_sec:
                                        # Keep alive timeout - this is normal for long-running connections
                                        print(f"INFO: Keep Alive timeout after {td_seconds:.1f}s (limit: {ka_timeout_sec}s)")
                                        print("INFO: This is normal behavior - connection will be re-established")
                                        raise Exception("Keep Alive Timeout")
                                    else:
                                        last_connected_ts = this_ts
                    except asyncio.CancelledError:
                        logger.info("WAN Chat message loop cancelled (logout/shutdown)")
                        mainwin.set_wan_connected(False)
                        raise  # Re-raise to propagate cancellation
                    except asyncio.TimeoutError:
                        logger.info("WebSocket recv timeout - connection may be closing")
                        mainwin.set_wan_connected(False)
                        break
                    except websockets.exceptions.ConnectionClosedOK:
                        logger.info("WebSocket connection closed normally")
                        mainwin.set_wan_connected(False)
                        break
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.warning(f"WebSocket connection closed: {e}")
                        mainwin.set_wan_connected(False)
                        break
                    except Exception as e:
                        traceback_info = traceback.extract_tb(e.__traceback__)
                        ex_stat = "ErrorsubscribeReceive:" + traceback.format_exc() + " " + str(e)
                        log3(ex_stat)
                        mainwin.set_wan_connected(False)
                        break

                if not mainwin.get_wan_connected():
                    raise Exception("Keep Alive Timeout")
    except asyncio.CancelledError:
        logger.info("WAN Chat subscription cancelled (logout/shutdown)")
        mainwin.set_wan_connected(False)
        # Don't retry when cancelled - this is intentional shutdown
        return
    except Exception as e:
        if "Keep Alive Timeout" in str(e):
            logger.warning(f"INFO: WebSocket Keep Alive timeout - reconnecting in 5 seconds...")
        else:
            logger.error(f"Websocket Connection error: {e}. Retrying in 5 seconds...")
        traceback_info = traceback.extract_tb(e.__traceback__)
        ex_stat = "ErrorsubscribeToWanChat:" + traceback.format_exc() + " " + str(e)
        log3(ex_stat)
        mainwin.set_wan_connected(False)
        
        # Check if we should retry - don't retry if the main window is shutting down
        if hasattr(mainwin, '_shutting_down') and mainwin._shutting_down:
            logger.warning("INFO: Main window is shutting down, not retrying WAN Chat connection")
            return
            
        await asyncio.sleep(5)
        await subscribeToWanChat(mainwin, auth_token, chat_id)


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
                print("COMMAND:", command)
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
                print("RESPONSE:", response)
                return cmd_type, json.dumps(response, indent=4)

        except ET.ParseError:
            return "Invalid XML command format."

    else:
        # Return the input string as a regular chat message
        return "chat", input_str