import Cloud
import json
import ssl
import websockets
import asyncio
import aiohttp
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from Cloud import gen_wan_chat_message_string
import base64

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


async def wan_send_message(content, sender, token):
    APPSYNC_API_ENDPOINT_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql'
    variables = {
        "content": content,
        "sender": sender
    }
    query_string = gen_wan_chat_message_string(content['msg'])
    headers = {
        'Content-Type': "application/graphql",
        'Authorization': token,
        'cache-control': "no-cache",
    }
    async with aiohttp.ClientSession() as session8:
        async with session8.post(
                url=APPSYNC_API_ENDPOINT_URL,
                timeout=aiohttp.ClientTimeout(total=300),
                headers=headers,
                json={
                        'query': query_string,
                        'variables': variables
                }
        ) as response:
            jresp = await response.json()
            print(jresp)
            return jresp



async def wan_handle_rx_message(session, token, websocket, in_msg_queue):
    while True:
        try:
            response = await websocket.recv()
            response_data = json.loads(response)
            if response_data["type"] == "data":
                command = response_data["payload"]["data"]["onCommandReceived"]
                print("Command received:", command)
                # Execute the command here
                asyncio.create_task(in_msg_queue.put(command))
        except websockets.exceptions.ConnectionClosedError:
            print("Connection lost. Attempting to reconnect...")
            break


def get_signed_headers(url, credentials):
    request = AWSRequest(method='GET', url=url, data='')
    SigV4Auth(credentials, 'appsync', 'us-west-2').add_auth(request)
    return dict(request.headers.items())

# Function to subscribe to commands
async def subscribe_to_wan_chat(mainwin, session, tokens):
    WS_URL = 'wss://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com/graphql'
    WS_API_HOST = '3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com'
    try:
        api_headers = {
            'Content-Type': 'application/json',
            'Host': WS_API_HOST,
            "Authorization": tokens['AuthenticationResult']['IdToken']
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
            # "Host": "3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-realtime-api.us-east-1.amazonaws.com",
            "Sec-WebSocket-Protocol": "graphql-ws"
        }

        # async with websockets.connect(WS_URL, extra_headers={
        #     'Content-Type': 'application/json',
        #     'Authorization': tokens['AuthenticationResult']['IdToken']
        # }) as websocket:
        async with websockets.connect(ws_url, extra_headers=headers, subprotocols=['graphql-ws']) as websocket:
        # ws_session = aiohttp.ClientSession()
        # async with ws_session.ws_connect(WS_URL, headers=headers, protocols=['graphql-ws']) as ws:
        # async with ws_session.ws_connect(WS_URL, headers=headers) as ws:
            print("Connected to WebSocket")
            # Send connection init message
            init_msg = {
                # "type": "connection_init"
                "type": "connection_init"
                # "payload": {
                #     "authToken": tokens['AuthenticationResult']['IdToken']
                # }
            }
            print("SENDING CONN MSG")
            await websocket.send(json.dumps(init_msg))
            # await ws.send_json(init_msg)
            print("INIT MSG SENT")

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
                        await subscribe_to_wan_chat(websocket)
                    elif response_data.get("type") == "data":
                        message_data = response_data["payload"]["data"]["onMessageSent"]
                        print(f"[{message_data['timestamp']}] {message_data['sender']}: {message_data['message']}")
                except websockets.exceptions.ConnectionClosedError as e:
                    print(f"Connection closed with error: {e}")
                    break
                except json.JSONDecodeError as e:
                    print(f"Failed to decode JSON: {e}")
                    break


    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatusCode) as e:
        print(f"Websocket Connection error: {e}. Retrying in 5 seconds...")
        await asyncio.sleep(5)
        await subscribe_to_wan_chat()