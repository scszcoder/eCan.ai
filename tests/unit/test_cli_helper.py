"""ecan helper: answers become clarificationResponses, and each reply prints once
whether it streamed, arrived whole, or only came back from the send call."""
import click
import pytest

from cli.helper.commands import Printer, clarification_questions, format_questions, parse_answers


class _Out:
    def __init__(self):
        self.text, self.errors = "", []

    def print(self, *args, end="\n", flush=False):
        self.text += " ".join(str(a) for a in args) + end

    def error(self, msg):
        self.errors.append(msg)


def _chunk(sid, mid, chunk):
    return {"type": "skill_editor.chat.stream_chunk", "payload": {"sessionId": sid, "messageId": mid, "chunk": chunk}}


def _end(sid, mid, text, **extra):
    return {"type": "skill_editor.chat.stream_end",
            "payload": {"sessionId": sid, "messageId": mid, "fullContent": text, **extra}}


def test_parse_answers_choices_and_free_text():
    assert parse_answers(("q1=c2", "q2=a,b"), ('q3=only in chat',)) == {
        "q1": ["c2"], "q2": ["a", "b"], "q3": ["other"], "freeform_q3": ["only in chat"]}
    assert parse_answers((), ()) == {}
    with pytest.raises(click.BadParameter):
        parse_answers(("q1",), ())
    with pytest.raises(click.BadParameter):
        parse_answers((), ("q1=",))


def test_questions_from_list_or_dict():
    q = [{"id": "q1", "question": "Where?", "choices": [{"id": "c1", "label": "Chat", "allow_freeform": True}]}]
    assert clarification_questions({"clarification": q}) == q
    assert clarification_questions({"clarification": {"questions": q}}) == q
    assert clarification_questions({}) == []
    text = format_questions(q)
    assert "[q1] Where?" in text and "c1: Chat" in text and "--text" in text


def test_streamed_reply_prints_chunks_once_and_ignores_other_sessions():
    out = _Out()
    p = Printer(out, "s1")
    assert p.handle(_chunk("s1", "m1", "Hel")) and p.handle(_chunk("s1", "m1", "lo"))
    assert not p.handle(_chunk("s2", "m9", "not mine"))
    p.handle(_end("s1", "m1", "Hello"))
    p.handle(_end("s1", "m1", "Hello"))                  # a repeat push
    p.reply({"message": {"id": "m1", "content": "Hello"}})   # and the send call's copy
    assert out.text.count("Hello") == 1 and "not mine" not in out.text
    assert p.ends == 1


def test_whole_reply_with_questions_and_manager_tag():
    out = _Out()
    p = Printer(out, "s1")
    p.handle(_end("s1", "m2", "Built it.", source="manager",
                  clarification=[{"id": "q1", "question": "Schedule?", "choices": [{"id": "c1", "label": "Daily"}]}]))
    assert "manager> " in out.text and "Built it." in out.text and "[q1] Schedule?" in out.text


def test_send_reply_printed_when_nothing_streamed():
    out = _Out()
    p = Printer(out, "s1")
    p.reply({"message": {"id": "m3", "content": "Only via the call"}})
    assert "helper> " in out.text and "Only via the call" in out.text


def test_error_event_is_reported():
    out = _Out()
    p = Printer(out, "s1")
    assert p.handle({"type": "skill_editor.chat.error", "payload": {"sessionId": "s1", "code": "X", "message": "boom"}})
    assert out.errors == ["boom (X)"]


def test_status_chunks_then_final_reply_on_its_own_line():
    out = _Out()
    p = Printer(out, "s1")
    p.handle(_chunk("s1", "sse-1", "Thinking..."))       # status stream, never ended
    p.handle(_end("s1", "m4", "OK"))
    assert click.unstyle(out.text).endswith("Thinking...\nhelper> OK\n")
