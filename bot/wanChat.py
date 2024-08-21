import Cloud
import json
import ssl
import websockets
import asyncio
import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from Cloud import gen_wan_send_chat_message_string, gen_wan_subscription_connection_string
import base64
from datetime import datetime
from Logger import log3

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



async def wanSendMessage(msg_req, token, websocket):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'

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
    print("about to send wan msg:", variables, query_string, headers)
    print("++++++++++++++++++++++++++++++++++++++++++++++++++++")
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
            print("send JRESP:", jresp)
            return jresp


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
async def subscribeToWanChat(mainwin, tokens, chat_id="nobody"):
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'
    WS_API_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com'
    id_token = tokens['AuthenticationResult']['IdToken']
    try:
        api_headers = {
            'Content-Type': 'application/json',
            'Host': WS_API_HOST,
            "Authorization": id_token
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

        headers = {
            "Sec-WebSocket-Protocol": "graphql-ws"
        }

        async with websockets.connect(ws_url, extra_headers=headers, subprotocols=['graphql-ws']) as websocket:
            print("Connected to WebSocket")
            # Send connection init message
            init_msg = {
                "type": "connection_init"
            }

            await websocket.send(json.dumps(init_msg))

            # Wait for connection ack
            # async for msg in ws:
            # Wait for connection_ack
            while True:
                try:
                    response = await websocket.recv()
                    response_data = json.loads(response)
                    print(f"RECEIVED: {response_data}")
                    if response_data.get("type") == "connection_ack":
                        print("WEBSOCKET CONNECTED!!!!")
                        mainwin.set_wan_connected(True)
                        mainwin.set_websocket(websocket)
                        last_connected_ts = datetime.now()
                        break

                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"Connection closed with error: {e}")
                    mainwin.set_wan_connected(False)
                    break
                except json.JSONDecodeError as e:
                    print(f"Failed to decode JSON: {e}")
                    break

            if mainwin.get_wan_connected():
                # now request to subscribe to the API
                print("NOW start to subscribe1")
                sub_data = {
                    "query": gen_wan_subscription_connection_string(),
                    "variables": {"chatID": chat_id}
                }
                print("NOW start to subscribe2")

                sub_data_string = json.dumps(sub_data)
                print("NOW start to subscribe3")

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
                print("SENDING WEBSOCKET SUBSCRIPTION REGISTRATION REQUEST!!!!")

                await websocket.send(json.dumps(SUB_REG))

                while True:
                    try:
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        print(f"ACK RECEIVED: {response_data}")
                        if response_data.get("type") == "start_ack":
                            print("MESSAGE SUBSCRIPTION TO "+"SUCCEEDED!!!!")
                            print(chat_id)

                            mainwin.set_wan_msg_subscribed(True)
                            last_subscribed_ts = datetime.now()
                            break
                    except websockets.exceptions.ConnectionClosedError as e:
                        print(f"Connection closed with error: {e}")
                        mainwin.set_wan_connected(False)
                        break
                    except json.JSONDecodeError as e:
                        print(f"Failed to decode JSON: {e}")
                        break

                while True:
                    try:
                        message = await websocket.recv()
                        print(f"SUBSCRIBE Received message: {message}", type(message))  # this is string.
                        # send the message to
                        rcvd = json.loads(message)
                        print("actual msg:", type(rcvd["payload"]["data"]["onMessageReceived"]))
                        # route the message either to chat or RPA
                        if rcvd["payload"]["data"]["onMessageReceived"]["type"] == "chat":
                            asyncio.create_task(mainwin.gui_chat_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                        else:
                            asyncio.create_task(mainwin.gui_rpa_msg_queue.put(rcvd["payload"]["data"]["onMessageReceived"]))
                    except websockets.exceptions.ConnectionClosed:
                        print("WebSocket connection closed.")
                        break

    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatusCode) as e:
        print(f"Websocket Connection error: {e}. Retrying in 5 seconds...")
        mainwin.set_wan_connected(False)
        await asyncio.sleep(5)
        await subscribe_to_wan_chat()


