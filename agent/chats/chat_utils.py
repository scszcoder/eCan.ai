import asyncio
from agent.db.services.db_chat_service import DBChatService
from agent.ec_agent import EC_Agent
from utils.logger_helper import logger_helper as logger

# supposed data structure
request= {'params': None}
request['params'] = {
                    "message": [
                        {
                            "id": "10",
                            "chat_id": "2",
                            "session_id": "1",
                            "content": "Wasssuuuuupppppp!",
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

def gui_a2a_send_chat(mainwin, req):
    logger.debug("[chat_utils] gui_a2a_send_chat:", type(req), req)
    agents = mainwin.agents
    twin_agent: EC_Agent = next((ag for ag in agents if ag.card.name == "My Twin Agent"), None)
    db_chat_service: DBChatService = mainwin.db_chat_service
    
    # Get chatId from request parameters
    chat_id = req.get("params", {}).get("chatId")
    if not chat_id:
        logger.error("[chat_utils] No chatId found in request parameters")
        return {"error": "No chatId provided"}
    
    logger.debug(f"[chat_utils] Getting chat data for chatId: {chat_id}")
    # Get chat with members and messages
    this_chat = db_chat_service.get_chat_by_id(chat_id, deep=True)

    recipient_ids = []
    if this_chat["success"]:
        chat_data = this_chat["data"]
        member_user_ids = [member["userId"] for member in chat_data.get("members", [])]
        
        # Filter out twin_agent from member_user_ids to get recipients
        if member_user_ids:
            recipient_ids = [uid for uid in member_user_ids if uid != twin_agent.card.id]
    else:
        logger.warning(f"[chat_utils] Chat not found: {this_chat['error']}")
        # Try to get receiverId from request params as fallback
        receiver_id = req.get("params", {}).get("receiverId")
        if receiver_id:
            logger.info(f"[chat_utils] Using receiverId from request params: {receiver_id}")
            recipient_ids = [receiver_id]
        else:
            logger.warning("[chat_utils] No receiverId found in request params, continuing without recipients")
            recipient_ids = []

    req["params"]["recipient_ids"] = recipient_ids
    logger.debug("[chat_utils] twin:", twin_agent.card.name, "recipients:", recipient_ids)

    runner_method = twin_agent.runner.sync_task_wait_in_line
    if asyncio.iscoroutinefunction(runner_method):
        logger.debug("[chat_utils] Runner method is a coroutine, running with asyncio.run()")

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(runner_method("human_chat", req))
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
        logger.debug("[chat_utils] Runner method is synchronous, calling directly.")
        result = runner_method("human_chat", req)

    return result

# Note: ContentType and ContentSchema have been moved to agent.db.utils
# They are imported at the top of this file for backward compatibility
