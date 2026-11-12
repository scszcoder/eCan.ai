"""Helper-chat history is kept on this machine too, in cloud relay mode: the user's messages,
the cloud's replies and the Manager's late results (with their tree widgets), and it is merged
with the cloud's copy when sessions and history are read."""

import pytest

from gui.ipc.w2p_handlers import skill_editor_chat_handler as h


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "_get_chat_history_path", lambda: str(tmp_path / "history.json"))
    monkeypatch.setattr(h._chat_store, "_sessions", {})
    monkeypatch.setattr(h._chat_store, "_initialized", True)
    return h._chat_store


def test_a_cloud_session_gets_a_local_copy_under_the_clouds_ids(store, tmp_path):
    h.mirror_chat_message("sess-1", "user", "show me my agents")
    h.mirror_chat_message("sess-1", "assistant", "Asking your desktop...", "m1", {"source": "manager"})
    h.mirror_chat_message("sess-1", "assistant", "Here is your setup.", "m1",
                          {"source": "manager", "widget": {"type": "tree", "nodes": []}, "fullContent": "x"})
    s = store.get_session("sess-1")
    assert [m.content for m in s.messages] == ["show me my agents", "Here is your setup."]   # m1 replaced itself
    assert s.messages[1].metadata == {"source": "manager", "widget": {"type": "tree", "nodes": []}}
    assert s.name == "show me my agents" and (tmp_path / "history.json").exists()


def test_empty_messages_are_not_kept(store):
    h.mirror_chat_message("sess-1", "assistant", "   ", "m1")
    assert store.get_session("sess-1") is None


def test_sessions_list_adds_the_ones_only_this_machine_has(store):
    h.mirror_chat_message("cloud-1", "user", "a")
    h.mirror_chat_message("local-only", "user", "b")
    merged = h._merge_local_sessions([{"id": "cloud-1", "name": "from cloud"}])
    assert [s["id"] for s in merged] == ["cloud-1", "local-only"] and merged[0]["name"] == "from cloud"


def test_history_adds_local_only_messages_and_restores_the_widget(store):
    h.mirror_chat_message("sess-1", "user", "q")
    h.mirror_chat_message("sess-1", "assistant", "tree answer", "m1", {"widget": {"type": "tree", "nodes": []}})
    s = store.get_session("sess-1")
    q, a = s.messages
    a.timestamp = q.timestamp + 10
    late = h.ChatMessage(id="late", role=h.ChatRole.ASSISTANT, content="late result", timestamp=q.timestamp + 20)
    s.messages.append(late)
    cloud = {"messages": [{"id": "m1", "role": "assistant", "content": "tree answer", "timestamp": a.timestamp,
                           "metadata": {"state": "complete"}}], "total": 1, "sessionId": "sess-1"}
    out = h._merge_local_history("sess-1", cloud)
    contents = [m["content"] for m in out["messages"]]
    assert contents == ["q", "tree answer", "late result"] and out["total"] == 3
    assert out["messages"][1]["metadata"] == {"widget": {"type": "tree", "nodes": []}, "state": "complete"}


def test_history_of_a_session_this_machine_never_saw_is_the_clouds(store):
    cloud = {"messages": [{"id": "x", "content": "c", "timestamp": 1}], "total": 1}
    assert h._merge_local_history("unknown", cloud) is cloud


def test_cloud_timestamps_as_strings_merge_with_local_ones(store):
    """The cloud sends ISO or digit strings; the local copy has ints. Sorting both failed."""
    h.mirror_chat_message("sess-1", "user", "q")
    q = store.get_session("sess-1").messages[0]
    q.timestamp = 1_700_000_000_000                                   # 2023-11-14T22:13:20Z
    cloud = {"messages": [{"id": "a", "content": "later", "timestamp": "2023-11-14T22:13:21Z"},
                          {"id": "b", "content": "earlier", "timestamp": "1699999999000"}], "total": 2}
    out = h._merge_local_history("sess-1", cloud)
    assert [m["content"] for m in out["messages"]] == ["earlier", "q", "later"]
