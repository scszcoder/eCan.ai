"""The chat page's greeting (a message the agent wrote) is saved, not routed to an agent."""
import types

from gui.ipc.w2p_handlers import chat_handler as ch


class _ChatService:
    def __init__(self):
        self.saved = []

    def get_chat_by_id(self, chat_id, deep=False):
        return {"success": True}

    def dispatch_add_message(self, chat_id, args):
        self.saved.append(args)
        return {"success": True}


def _send(monkeypatch, role):
    svc, routed = _ChatService(), []
    ctx = types.SimpleNamespace(get_db_chat_service=lambda: svc, main_window=object())
    monkeypatch.setattr(ch, "get_handler_context", lambda request, params: ctx)
    import agent.chats.chat_utils as cu
    monkeypatch.setattr(cu, "gui_a2a_send_chat", lambda mainwin, req: routed.append(req))
    params = {"chatId": "chat-1", "role": role, "content": {"type": "text", "text": "hi"},
              "senderId": "agent_a" if role == "agent" else "user_u", "receiverId": "user_u" if role == "agent" else "agent_a"}
    ch.handle_send_chat({"id": "r1", "method": "send_chat", "params": params}, params)
    return svc.saved, routed


def test_the_agent_greeting_is_saved_but_not_routed(monkeypatch):
    saved, routed = _send(monkeypatch, "agent")
    assert len(saved) == 1 and routed == []


def test_a_user_message_is_still_routed(monkeypatch):
    saved, routed = _send(monkeypatch, "user")
    assert len(saved) == 1 and len(routed) == 1
