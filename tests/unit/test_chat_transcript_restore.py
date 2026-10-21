"""An opted-in chat skill that starts fresh (e.g. after an app restart) gets
its chat's recent conversation back in state["history"]."""
from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage

from agent.ec_tasks.chat_transcript import restore_history, restore_limit, transcript_messages


def _row(i, role, text, mid=None):
    return {"id": mid or f"m{i}", "role": role, "content": {"type": "text", "text": text}, "createAt": i}


ROWS = [  # oldest first
    _row(1, "agent", "Hi! Which product?"),
    _row(2, "user", "ABC perfume, 50 ml"),
    _row(3, "agent", "图片做好了：... 文件：C:/tmp/output/img_1.png"),
    {"id": "m4", "role": "agent", "content": {"type": "notification", "notification": {}}, "createAt": 4},
    _row(5, "user", "背景再亮一些", mid="m5"),          # the message that started this run
]


class _Svc:
    def __init__(self, rows):
        self.rows, self.calls = rows, []

    def query_messages_by_chat(self, chatId, limit=20, offset=0, reverse=False):
        self.calls.append((chatId, limit, reverse))
        rows = list(reversed(self.rows)) if reverse else list(self.rows)
        return {"success": True, "data": rows[offset:offset + limit]}


def _task(meta=None, cfg=None, diagram=None):
    return SimpleNamespace(name="t", metadata=meta or {}, skill=SimpleNamespace(config=cfg or {}, diagram=diagram or {}))


def _state(inp="背景再亮一些", msg_id="m5", history=None):
    return {"input": inp, "history": history or [], "attributes": {"chat_id": "chat-1", "msg_id": msg_id}}


def test_opt_in_sources_and_limits():
    assert restore_limit(_task()) == 0
    assert restore_limit(_task(diagram={"restore_chat_history": 30})) == 30
    assert restore_limit(_task(cfg={"restore_chat_history": True})) == 40
    assert restore_limit(_task(meta={"restore_chat_history": 0}, diagram={"restore_chat_history": 30})) == 0  # task wins
    assert restore_limit(_task(diagram={"restore_chat_history": 10_000})) == 200
    assert restore_limit(_task(diagram={"restore_chat_history": "x"})) == 0


def test_restores_text_turns_without_the_current_message():
    st = _state()
    n = restore_history(_task(diagram={"restore_chat_history": 30}), st, _Svc(ROWS))
    assert n == 3
    h = st["history"]
    assert [type(m) for m in h] == [AIMessage, HumanMessage, AIMessage]
    assert h[-1].content.startswith("图片做好了")
    assert all("背景再亮一些" not in m.content for m in h)


def test_current_message_dropped_by_text_when_no_id():
    msgs = transcript_messages(ROWS, current_input="背景再亮一些", current_msg_id="")
    assert len(msgs) == 3 and all(m.content != "背景再亮一些" for m in msgs)


def test_off_or_already_has_history_or_no_chat_does_nothing():
    svc = _Svc(ROWS)
    st = _state()
    assert restore_history(_task(), st, svc) == 0 and st["history"] == [] and not svc.calls
    st2 = _state(history=[HumanMessage(content="kept")])
    assert restore_history(_task(diagram={"restore_chat_history": 30}), st2, svc) == 0
    assert st2["history"][0].content == "kept"
    st3 = {"input": "x", "history": [], "attributes": {}}
    assert restore_history(_task(diagram={"restore_chat_history": 30}), st3, svc) == 0


def test_limit_keeps_the_most_recent_messages():
    rows = [_row(i, "user" if i % 2 else "agent", f"msg {i}") for i in range(1, 21)]
    st = _state(inp="new question", msg_id="none")
    restore_history(_task(diagram={"restore_chat_history": 5}), st, _Svc(rows))
    assert [m.content for m in st["history"]] == [f"msg {i}" for i in range(16, 21)]
