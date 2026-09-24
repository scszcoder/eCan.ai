from __future__ import annotations

import asyncio
import time
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

def _notify_chat_undeliverable(chat_id: str, text: str) -> None:
    """Tell the CHAT WINDOW a message could not be delivered.

    Until now this failed in the log only: the user typed, nothing happened,
    and the reason (an agent that never started) sat in eCan.log. The same push
    channel the agents' own replies use carries the notice, so it appears
    inline in the thread the user is looking at.

    Best-effort — a failure to explain a failure must not raise.
    """
    try:
        from app_context import AppContext
        web_gui = AppContext.get_web_gui()
        if not web_gui:
            return
        web_gui.get_ipc_api().push_chat_message(chat_id, {
            "chatId": chat_id,
            "role": "system",
            "senderId": "system",
            "content": text,
            "createAt": int(time.time() * 1000),
            "undeliverable": True,
        })
    except Exception as exc:
        logger.warning(f"[chat_utils] could not surface delivery failure to the chat window: {exc}")


def _agent_startup_hint(mainwin, agent_key: str = "") -> str:
    """Why is the agent missing? The startup failure reason, when we know it.

    Recorded by agent_converter when conversion raises (keyed by both name and
    id). Falls back to any recorded reason, since a single missing provider key
    usually takes every agent down together.
    """
    try:
        failures = getattr(mainwin, "agent_conversion_failures", None)
        if not isinstance(failures, dict) or not failures:
            return ""
        if agent_key:
            reason = str(failures.get(str(agent_key), "")).strip()
            if reason:
                return reason
        return str(next(iter(failures.values()), "")).strip()
    except Exception:
        return ""


def _chat_has_other_member(mainwin, chat_id, sender_id) -> bool:
    """Whether the chat names a recipient besides the sender."""
    try:
        svc = mainwin.ec_db_mgr.get_chat_service()
        chat = svc.get_chat_by_id(chat_id, deep=False) if svc else None
        if chat and chat.get("success"):
            return any(m.get("userId") and m.get("userId") != sender_id
                       for m in chat["data"].get("members", []))
    except Exception:
        pass
    return False


def _runs_elsewhere(agent) -> str:
    """Why this in-memory agent will NOT process a message queued here, or "".

    Every agent of the account is in ``mainwin.agents``, including ones the
    placement gates kept from starting on this machine. Queueing a chat into
    such an agent's runner loses it silently -- its tasks never launched here.
    An agent that is starting, or belongs here but has not launched yet, still
    gets the message (the runner picks it up once its tasks start).
    """
    if getattr(agent, "_running", False) or getattr(agent, "_starting", False):
        return ""
    if (getattr(agent, "status", "active") or "active") == "disabled":
        return "it is turned off"
    store_bound = False
    try:
        # Read-only: placement_for_agent may CLAIM an unassigned store, and
        # sending a chat must never change where a store runs.
        from agent.ec_agents.store_placement import refresh, store_ids_of_agent
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        stores = store_ids_of_agent(agent)
        store_bound = bool(stores)
        if stores:
            mainwin = getattr(agent, "mainwin", None)
            me = resolve_local_vehicle_id(mainwin)
            entries = (refresh(mainwin) or {}).get("stores") or {}
            for sid in stores:
                assigned = (entries.get(sid) or {}).get("assigned")
                if assigned and me and assigned != me:
                    return f"store {sid} is assigned to another machine"
    except Exception:
        pass
    try:
        from agent.ec_tasks.worker_placement import PLACE_DELEGATE, placement_for_agent as place
        decision, key = place(agent)
        if decision == PLACE_DELEGATE:
            return f"it runs in its own store process ({key})"
    except Exception:
        pass
    if not store_bound:   # a store agent is placed by its store, never by its pin
        try:
            from agent.ec_agents.vehicle_affinity import agent_launch_allowed
            allowed, why = agent_launch_allowed(agent)
            if not allowed:
                return f"it runs on another machine ({why})"
        except Exception:
            pass
    return ""


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
        hint = _agent_startup_hint(mainwin, params.get('receiverId') or '')
        _notify_chat_undeliverable(
            chat_id,
            "⚠️ 该助手尚未启动，消息未送达。"
            + (f"\n原因：{hint}" if hint else "")
            + "\n请检查 设置 > LLM 管理 中的 API Key，然后重启应用。"
            + "\n\nThis agent has not started, so the message was not delivered."
            + (f"\nReason: {hint}" if hint else "")
            + "\nCheck the provider API key in Settings > LLM Management, then restart."
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

    # A recipient was named (by the request or the chat's members) but is not
    # in this app: say so. Handing the message to some OTHER agent -- the old
    # last resort -- had the wrong agent answer the user.
    named = bool(recipient_id) or _chat_has_other_member(mainwin, chat_id, sender_id)
    if not recipient_agent and named:
        logger.warning(f"[chat_utils] recipient {recipient_id or '(chat member)'} is not in this app; "
                       f"not delivering chat {chat_id} to a stand-in agent")
        _notify_chat_undeliverable(
            chat_id,
            "⚠️ 该助手不在本机，消息未送达。"
            + "\n\nThis agent is not on this machine, so the message was not delivered."
        )
        return {"error": f"Recipient agent not on this machine: {recipient_id}"}

    # 3. Last resort, only for a chat with no identifiable recipient at all:
    # first agent with a runner (skip twin if still around)
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
        # Some agents started, this one did not — say which ones did, since the
        # difference is usually one agent's provider key.
        _notify_chat_undeliverable(
            chat_id,
            "⚠️ 未找到该助手，消息未送达。"
            + (f"\n已启动：{', '.join(avail)}" if avail else "")
            + "\n\nRecipient agent not found, so the message was not delivered."
            + (f"\nRunning agents: {', '.join(avail)}" if avail else "")
        )
        return {"error": f"Recipient agent not found: {recipient_id}"}

    elsewhere = _runs_elsewhere(recipient_agent)
    if elsewhere:
        name = getattr(recipient_agent.card, "name", recipient_id)
        logger.warning(f"[chat_utils] not queueing chat {chat_id} to '{name}': {elsewhere}")
        _notify_chat_undeliverable(
            chat_id,
            f"⚠️ 「{name}」不在本机运行，消息未送达。"
            + f"\n\n'{name}' is not running on this machine ({elsewhere}), so the message was not delivered."
        )
        return {"error": f"Recipient agent not running here: {elsewhere}"}

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
