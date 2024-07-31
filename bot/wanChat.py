import Cloud
import json
import ssl
import websockets
import asyncio
import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from Cloud import gen_wan_send_chat_message_string
import base64
from datetime import datetime
from Logger import log3

# Wan Chat Logic
# Commander will connect to websocket and subscribe, and wan logging is default off, then sit in a loop
# and listen for turn on logging command,
# Staff Officer will get online and connect to websocket and shoot out ping command to any commander out there.
# once hearing ack back from the commander off websocket, it sends a request logging command if needed.
#


STATUS_UPDATE_SUBSCRIPTION = """
subscription onStatusUpdate {
  onStatusUpdate {
    id
    content
    sender
    receiver
    timestamp
    parameters
  }
}
"""

COMMAND_RECEIVED_SUBSCRIPTION = """
subscription onCommandReceived {
  onCommandReceived {
    id
    content
    sender
    receiver
    timestamp
    parameters
  }
}
"""

MESSAGE_RECEIVED_SUBSCRIPTION = """
subscription onMessageReceived {
  onMessageReceived {
    id
    content
    sender
    receiver
    timestamp
    parameters
  }
}
"""
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



async def wanSendMessage(msg_req, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    variables = {
        "input": {
            "content": msg_req["content"],
            "chatID": msg_req["chatID"],
            "receiver": msg_req["receiver"],
            "parameters": msg_req["parameters"],
            "sender": msg_req["sender"]
        }
    }
    query_string = gen_wan_send_chat_message_string()
    headers = {
        'Content-Type': "application/json",
        'Authorization': token,
        'cache-control': "no-cache",
    }
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
            print(jresp)
            return jresp



async def wanHandleRxMessage(session, token, websocket, in_msg_queue):
    while True:
        try:
            response = await websocket.recv()
            response_data = json.loads(response)
            log3("WAN RECEIVED SOMETHING:"+response)
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
    SigV4Auth(credentials, 'appsync', 'us-west-2').add_auth(request)
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
                sub_data = {
                    "query": """
                        subscription onMessageReceived($chatID: String!) {
                            onMessageReceived(chatID: $chatID) {
                                id
                                content
                                sender
                                receiver
                                timestamp
                                parameters
                            }
                        }
                    """,
                    "variables": {"chatID": chat_id}
                }
                sub_data_string = json.dumps(sub_data)
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
                await websocket.send(json.dumps(SUB_REG))

                while True:
                    try:
                        response = await websocket.recv()
                        response_data = json.loads(response)
                        print(f"ACK RECEIVED: {response_data}")
                        if response_data.get("type") == "start_ack":
                            print("MESSAGE SUBSCRIPTION SUCCEEDED!!!!")
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

    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatusCode) as e:
        print(f"Websocket Connection error: {e}. Retrying in 5 seconds...")
        mainwin.set_wan_connected(False)
        await asyncio.sleep(5)
        await subscribe_to_wan_chat()


