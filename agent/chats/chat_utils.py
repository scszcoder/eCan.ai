
import asyncio
import time
import json
import os
from utils.logger_helper import logger_helper as logger
from agent.ec_skill import FileAttachment

# supposed data structure
request= {'params': None}
request['params'] = {
                    "message": [
                        {
                            "id": "10",
                            "chat_id": "2",
                            "session_id": "1",
                            "content": "please help analyze these files and provided a detailed description of each file.",
                            "attachments": [
                                {
                                    "id": "0",
                                    "name": "test0.png",
                                    "type": "image",
                                    "size": "",
                                    "url": "",
                                    "content": "",
                                    "file": "C:/Users/songc/PycharmProjects/ecbot/test0.png",
                                }
                        #         {
                        #             "id": "1",
                        #             "name": "test1.pdf",
                        #             "type": "application",
                        #             "size": "",
                        #             "url": "",
                        #             "content": "",
                        #             "file": "C:/Users/songc/PycharmProjects/ecbot/test1.pdf",
                        #         },
                        #         {
                        #             "id": "2",
                        #             "name": "test2.wav",
                        #             "type": "audio",
                        #             "size": "",
                        #             "url": "",
                        #             "content": "",
                        #             "file": "C:/Users/songc/PycharmProjects/ecbot/test2.wav",
                        #         }
                            ],
                            "sender_id": "1",
                            "sender_name": "twin",
                            "recipient_id": "2",
                            "recipient_name": "procurement",
                            "txTimestamp": "string",
                            "rxTimestamp": "string",
                            "readTimestamp": "string",
                            "status": 'sending',
                            "isEdited": False,
                            "isRetracted": False,
                            "ext": None,
                            "replyTo": "0",
                            "atList": []
                        }
                    ]
                }

# 2025-06-27 12:34:27,161 - ecbot - DEBUG - web_to_python: Received message:
#
# {
#     'id': '6511f96d-3d6f-4e95-b679-67ea7e8fabfe',
#     'type': 'request',
#     'method': 'send_chat',
#     'params': {
#         'chatId': 'chat-000005',
#         'senderId': '50f6f2c8fb6f473d8763b78a3432a420',
#         'role': 'user',
#         'content': 'hell me about it',
#         'createAt': '1751052867105',
#         'senderName': 'My Twin Agent',
#         'status': 'sending',
#         'attachment': [
#             {
#                 'name': 'test0.png',
#                 'type': 'image/png',
#                 'size': 657,
#                 'url': 'C:\\Users\\songc\\PycharmProjects\\ecbot/songc_yahoo_com/tmp_files/546d566708dd4d94941ffefeb3c69506.png',
#                 'status': 'done',
#                 'uid': '8c25ed52-ae18-4c2d-9cf9-618dba1d7bf2'
#             }
#         ]
#     },
#     'timestamp': 1751052867161
# }

def a2a_send_chat(mainwin, req):
    print("a2a_send_chat:", req)
    agents = mainwin.agents
    twin_agent = next((ag for ag in agents if ag.card.name == "My Twin Agent"), None)
    chat_service = mainwin.chat_service
    # Get chat with members and messages
    this_chat = chat_service.get_chat_by_id("chat-000001", deep=True)

    if this_chat["success"]:
        chat_data = this_chat["data"]
        member_user_ids = [member["userId"] for member in chat_data.get("members", [])]

        # Use chat data
    else:
        print(f"Error: {this_chat['error']}")
        member_user_ids = []

    if member_user_ids:
        if twin_agent.card.id in member_user_ids:
            recipient_ids = member_user_ids.remove(twin_agent.card.id)
        else:
            recipient_ids = member_user_ids
    else:
        recipient_ids = []

    req["params"]["recipient_ids"] = recipient_ids
    print("twin:", twin_agent.card.name, "recipients:", recipient_ids)

    runner_method = twin_agent.runner.chat_wait_in_line
    if asyncio.iscoroutinefunction(runner_method):
        logger.debug("Runner method is a coroutine, running with asyncio.run()")

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(runner_method(req))
            finally:
                loop.close()

        # Run the coroutine in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async)
            result = future.result()

        # loop = asyncio.get_event_loop()
        # # asyncio.set_event_loop(loop)
        # # 在独立的后台线程中，可以安全使用 asyncio.run()
        # # result = await runner_method(params["message"])
        # result = loop.run_until_complete(runner_method(params["message"]))
    else:
        logger.debug("Runner method is synchronous, calling directly.")
        result = runner_method(request)

    return result

