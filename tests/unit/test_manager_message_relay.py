"""manager.message events (the cloud Manager posting into the helper chat) reach the chat panel."""
import json

from gui.ipc import appsync_subscription_client as C


class FakeIPC:
    def __init__(self):
        self.done = []

    def push_skill_editor_chat_done(self, **kw):
        self.done.append(kw)


def test_a_manager_message_is_shown_as_an_assistant_message():
    ipc = FakeIPC()
    C._relay_manager_message(ipc, "s1", json.dumps({"messageId": "c1:progress", "text": "Asking your desktop…"}))
    C._relay_manager_message(ipc, "", {"sessionId": "s1", "messageId": "c1:progress", "fullContent": "Done: $37 spent."})
    assert [(d["session_id"], d["message_id"], d["full_content"]) for d in ipc.done] == [
        ("s1", "c1:progress", "Asking your desktop…"), ("s1", "c1:progress", "Done: $37 spent.")]


def test_a_manager_message_without_text_or_session_is_not_shown():
    ipc = FakeIPC()
    C._relay_manager_message(ipc, "s1", {"messageId": "x"})
    C._relay_manager_message(ipc, "", {"text": "hi"})
    assert ipc.done == []


def test_each_event_path_relays_manager_messages(monkeypatch):
    seen = []
    monkeypatch.setattr(C, "_relay_manager_message", lambda ipc, sid, payload: seen.append((sid, payload)))
    event = {"eventType": "manager.message", "sessionId": "s1", "payload": {"text": "hi"}}
    for cls in (C.CNWebSocketClient, C.CNPollingClient, C.AppSyncSubscriptionClient):
        cls._relay_to_frontend(object.__new__(cls), event)
    assert seen == [("s1", {"text": "hi"})] * 3
