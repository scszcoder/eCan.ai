from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from agent.db.services.db_chat_service import DBChatService
from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent

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
    """Route a human chat message directly to the recipient agent.

    Resolution order for recipient agent:
      1. receiverId from request params  (set by frontend)
      2. Non-sender member from chat DB  (fallback)
      3. First agent with a runner       (last resort)
    """
    logger.debug("[chat_utils] gui_a2a_send_chat:", type(req), req)
    agents = mainwin.agents
    params = req.get("params", {})
    sender_id = params.get("senderId")
    chat_id = params.get("chatId")

    if not chat_id:
        logger.error("[chat_utils] No chatId found in request parameters")
        return {"error": "No chatId provided"}

    # Guard: if agents list is not ready yet, bail out gracefully.
    # The message has already been saved to the DB by handle_send_chat,
    # so nothing is lost. Retrying when the user sends the next message
    # will succeed once agents have been built and launched.
    if not agents:
        logger.warning(
            f"[chat_utils] Agents not yet ready (receiverId={params.get('receiverId')}), "
            f"skipping routing for chatId={chat_id}. "
            f"Message is saved in DB and will be picked up on the next user action."
        )
        return None

    # --- Resolve recipient agent ---
    def _find_agent_by_id(agent_id: str):
        return next(
            (ag for ag in agents
             if hasattr(ag, 'card') and ag.card and ag.card.id == agent_id),
            None,
        )

    recipient_agent: EC_Agent = None
    recipient_id = params.get("receiverId")

    # 1. Try receiverId from request params (frontend knows who the user is chatting with)
    if recipient_id:
        recipient_agent = _find_agent_by_id(recipient_id)

    # 2. Fallback: look up chat members from DB, pick the non-sender member
    if not recipient_agent:
        db_chat_service = mainwin.ec_db_mgr.get_chat_service()
        if db_chat_service:
            this_chat = db_chat_service.get_chat_by_id(chat_id, deep=False)
            if this_chat.get("success"):
                member_ids = [m["userId"] for m in this_chat["data"].get("members", [])]
                for mid in member_ids:
                    if mid != sender_id:
                        recipient_agent = _find_agent_by_id(mid)
                        if recipient_agent:
                            recipient_id = mid
                            break

    # 3. Last resort: first agent with a runner (skip twin if still around)
    if not recipient_agent:
        recipient_agent = next(
            (ag for ag in agents
             if hasattr(ag, 'runner') and ag.runner
             and (not hasattr(ag, 'card') or not ag.card or ag.card.name != "My Twin Agent")),
            None,
        )
        if not recipient_agent:
            recipient_agent = next(
                (ag for ag in agents if hasattr(ag, 'runner') and ag.runner), None
            )

    if not recipient_agent:
        avail = [getattr(ag.card, 'name', 'N/A') for ag in agents if hasattr(ag, 'card') and ag.card]
        logger.error(f"[chat_utils] No recipient agent found (receiverId={recipient_id}), available: {avail}")
        return {"error": f"Recipient agent not found: {recipient_id}"}

    logger.info(f"[chat_utils] Routing chat directly to recipient agent: "
                f"{recipient_agent.card.name} (id={recipient_agent.card.id})")

    # Attach recipient_ids for downstream consumers (pend_event node, etc.)
    req["params"]["recipient_ids"] = [recipient_id] if recipient_id else []
    req["params"]["transport"] = req["params"].get("transport") or "gui"
    req["params"]["senderType"] = req["params"].get("senderType") or "human"

    # --- Dispatch to recipient agent's runner ---
    runner_method = recipient_agent.runner.sync_task_wait_in_line
    if asyncio.iscoroutinefunction(runner_method):
        logger.debug("[chat_utils] Runner method is a coroutine, running with asyncio.run()")

        def run_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(runner_method("chat_message", req))
            finally:
                loop.close()

        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async)
            result = future.result()
    else:
        logger.debug("[chat_utils] Runner method is synchronous, calling directly.")
        result = runner_method("chat_message", req)

    return result

# Note: ContentType and ContentSchema have been moved to agent.db.utils
# They are imported at the top of this file for backward compatibility
