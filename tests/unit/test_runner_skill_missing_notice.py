"""A chat message to a task with no skill must say so in the chat.

The runner refused the run (SKILL_MISSING) in the log only, so the user saw an
agent that never answered.
"""
from types import SimpleNamespace

from agent.chats import chat_utils
from agent.ec_tasks.runner import TaskRunner


def _chat_msg(chat_id):
    return {"id": "m1", "method": "message/send",
            "params": {"chatId": chat_id, "content": "hi", "senderId": "u1"}}


def test_notice_goes_to_the_chat(monkeypatch):
    sent = []
    monkeypatch.setattr(chat_utils, "_notify_chat_undeliverable", lambda cid, text: sent.append((cid, text)))
    TaskRunner._notify_skill_missing(None, SimpleNamespace(name="做图需求采集00"), _chat_msg("chat-1"))
    assert len(sent) == 1
    assert sent[0][0] == "chat-1" and "做图需求采集00" in sent[0][1]


def test_no_chat_no_notice(monkeypatch):
    sent = []
    monkeypatch.setattr(chat_utils, "_notify_chat_undeliverable", lambda cid, text: sent.append((cid, text)))
    TaskRunner._notify_skill_missing(None, SimpleNamespace(name="t"), None)   # schedule run
    assert sent == []
