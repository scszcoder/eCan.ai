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


def test_a_widget_sent_as_a_json_string_reaches_the_panel_as_an_object():
    import json
    from gui.ipc.appsync_subscription_client import _relay_manager_message
    got = {}

    class Ipc:
        def push_skill_editor_chat_done(self, **kw):
            got.update(kw)
    widget = {"type": "tree", "nodes": [{"key": "host:m", "kind": "host", "label": "H"}]}
    _relay_manager_message(Ipc(), "s1", json.dumps({"text": "Here is your setup.", "messageId": "m1",
                                                     "widget": json.dumps(widget)}))
    assert got["extra"]["widget"] == widget and got["full_content"] == "Here is your setup."


def test_the_chat_done_push_forwards_the_widget_to_the_panel(monkeypatch):
    """It forwarded only a fixed list of fields, without 'widget': the tree reached the desktop, never the panel."""
    import types
    from gui.ipc.api import IPCAPI
    from gui.ipc.w2p_handlers import skill_editor_chat_handler as h
    mirrored = []
    monkeypatch.setattr(h, "mirror_chat_message", lambda *a, **k: mirrored.append(a))   # never the real history
    sent = []
    fake = types.SimpleNamespace(_send_request=lambda method, data, **kw: sent.append((method, data)))
    widget = {"type": "tree", "nodes": [{"key": "host:m", "kind": "host", "label": "H"}]}
    IPCAPI.push_skill_editor_chat_done(fake, session_id="s1", message_id="m1", full_content="Here.",
                                       extra={"widget": widget, "source": "manager"})
    assert sent[0][0] == "skill_editor.chat.stream_end" and sent[0][1]["widget"] == widget
    assert mirrored and mirrored[0][:4] == ("s1", "assistant", "Here.", "m1")                   # and a local copy is kept
