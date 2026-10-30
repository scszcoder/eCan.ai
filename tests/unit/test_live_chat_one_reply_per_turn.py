"""One reply per buyer turn (customer complaint 2026-10-28: one 千牛 question
answered 4 times and billed 4 times; 拼多多 KEN 10-27: a replayed queue sent
3 messages of one buyer to 3 Q&A tasks)."""
import pytest

from agent.ec_skills import live_chat_turns as turns


@pytest.fixture(autouse=True)
def _clean():
    turns.reset()
    yield
    turns.reset()


def test_a_superseded_turn_reply_is_dropped_and_the_merged_one_goes_out():
    turns.mark_superseded("2488488648", "1793068232212", "人工服务")
    assert turns.skip_reason(["2488488648"], "1793068232212", "人工服务") == "superseded_by_newer_turn"
    assert turns.skip_reason(["2488488648"], "1793068255116", "人工服务\n这个款式容易起球嘛") == ""


def test_a_later_turn_with_the_same_words_is_not_taken_for_the_superseded_one():
    turns.mark_superseded("u1", "m1", "在吗")
    assert turns.skip_reason(["u1"], "m9", "在吗") == ""


def test_the_same_question_seen_under_two_ids_is_answered_once():
    # 千牛: memory scan id and the backstop's cold:<uid>:<text> id for one message.
    turns.note_delivered(["u1"], "mem:u1:这款能当天发货吗", "这款能当天发货吗")
    assert turns.skip_reason(["u1"], "cold:u1:这款能当天发货吗", "这款能当天发货吗") == "turn_already_answered"
    assert turns.skip_reason(["u1"], "mem:u1:这款能当天发货吗", "") == "turn_already_answered"
    assert turns.skip_reason(["u2"], "x", "这款能当天发货吗") == ""


def test_a_new_question_after_an_answer_goes_out():
    turns.note_delivered(["u1"], "m1", "这款能当天发货吗")
    assert turns.skip_reason(["u1"], "m2", "有M码吗") == ""


def test_the_same_words_much_later_are_a_new_turn(monkeypatch):
    turns.note_delivered(["u1"], "m1", "在吗")
    real = turns.time.time
    monkeypatch.setattr(turns.time, "time", lambda: real() + turns.SAME_TEXT_WINDOW_S + 1)
    assert turns.skip_reason(["u1"], "m2", "在吗") == ""


def test_coalescing_only_folds_an_unanswered_turn():
    turns.note_delivered(["u1"], "m1", "人工服务")
    assert turns.was_answered("u1", "m1")
    assert not turns.was_answered("u1", "m2")
    assert not turns.was_answered("u1", "")
