"""抖店 alpha 2026-10-21 09:38: the reply to 肽斯特's "尺码偏大还是偏小" was
dropped as stale (older_bubble_match, index 5): the thread holds the same
question from an earlier test day. The buyer had sent nothing newer."""
from types import SimpleNamespace

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import dispatch_state as ds
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.site_tools import _answers_newest_turn

SRC = "66D4EACA-A994-4A55-B382-77A20584B7CE"
OLDER = {"stale_reason": "older_bubble_match", "matched_older_bubble_index": 5}


def _with_newest(msg_id, fn):
    saved = dict(ds.last_dispatched_msg_id_by_customer)
    try:
        ds.last_dispatched_msg_id_by_customer.clear()
        if msg_id:
            ds.last_dispatched_msg_id_by_customer["肽斯特"] = msg_id
        return fn()
    finally:
        ds.last_dispatched_msg_id_by_customer.clear()
        ds.last_dispatched_msg_id_by_customer.update(saved)


def test_the_newest_question_is_sent_despite_an_identical_older_one():
    assert _with_newest(SRC, lambda: _answers_newest_turn(OLDER, SRC, "肽斯特", False, SimpleNamespace()))


def test_a_buyer_who_has_moved_on_still_gets_the_stale_drop():
    assert not _with_newest("NEWER-MSG", lambda: _answers_newest_turn(OLDER, SRC, "肽斯特", False, SimpleNamespace()))


def test_no_rescue_for_a_vanished_bubble_or_a_second_try():
    assert not _with_newest(SRC, lambda: _answers_newest_turn(
        {"stale_reason": "no_match"}, SRC, "肽斯特", False, SimpleNamespace()))
    assert not _with_newest(SRC, lambda: _answers_newest_turn(OLDER, SRC, "肽斯特", True, SimpleNamespace()))
    assert not _with_newest(SRC, lambda: _answers_newest_turn(
        OLDER, SRC, "肽斯特", False, SimpleNamespace(_newest_turn_rescue_attempted=True)))
    assert not _with_newest("", lambda: _answers_newest_turn(OLDER, SRC, "肽斯特", False, SimpleNamespace()))
