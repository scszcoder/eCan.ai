"""mt060: tests for the two delivery-layer fixes.

(a) hot_path_v2._verify_reply_source_turn_v2 must NOT condemn a generated reply
    as stale_reply_source_msg_id on a transient EMPTY scrape — it retries first.
(b) placeholder_timer.placeholder_standing_unanswered backs the "弹出多次"
    dedup: suppress a second placeholder only while one is still standing
    unanswered (never the first, never after a real reply).
"""
import json
import time

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import hot_path_v2
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import placeholder_timer as pt


class _FakePrimitives:
    """Minimal BrowserPrimitives stand-in: eval_js pops scripted results."""

    def __init__(self, results):
        self._results = list(results)
        self.calls = 0

    async def eval_js(self, _script):
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return self._results[-1] if self._results else ""


def _bubble(msg_id="", text=""):
    return json.dumps({"msg_id": msg_id, "text": text})


def _payload(msg_id="m-123", text="这个款式有多少个颜色？"):
    return {"source_customer_msg_id": msg_id, "source_latest_message": text}


# ───────────────────────── (a) stale-reply retry ─────────────────────────

async def test_empty_then_match_recovers_not_stale():
    # First two scrapes come back empty (contention), third returns the bubble.
    prims = _FakePrimitives(["", "", _bubble(msg_id="m-123", text="x")])
    outcome = hot_path_v2.HotPathOutcomeV2()
    ok, reason = await hot_path_v2._verify_reply_source_turn_v2(
        prims, _payload(), node_name="t", outcome=outcome
    )
    assert ok is True and reason == ""
    assert prims.calls == 3  # retried until a real scrape arrived


async def test_all_empty_still_stale_no_worse():
    prims = _FakePrimitives(["", "", ""])
    outcome = hot_path_v2.HotPathOutcomeV2()
    ok, reason = await hot_path_v2._verify_reply_source_turn_v2(
        prims, _payload(), node_name="t", outcome=outcome
    )
    assert ok is False and reason == "stale_reply_source_msg_id"
    assert prims.calls == 3  # tried the full budget before giving up


async def test_match_first_call_no_wasted_retries():
    prims = _FakePrimitives([_bubble(msg_id="m-123", text="x")])
    outcome = hot_path_v2.HotPathOutcomeV2()
    ok, reason = await hot_path_v2._verify_reply_source_turn_v2(
        prims, _payload(), node_name="t", outcome=outcome
    )
    assert ok is True and reason == ""
    assert prims.calls == 1


async def test_confirmed_different_bubble_is_stale():
    # A real, non-empty, DIFFERENT bubble must still be treated as stale —
    # the retry must not mask a genuine newer message.
    prims = _FakePrimitives([_bubble(msg_id="m-999", text="完全不同的新问题")])
    outcome = hot_path_v2.HotPathOutcomeV2()
    ok, reason = await hot_path_v2._verify_reply_source_turn_v2(
        prims, _payload(), node_name="t", outcome=outcome
    )
    assert ok is False and reason == "stale_reply_source_msg_id"
    assert prims.calls == 1  # non-empty result → decided immediately, no retry


# ─────────────────────── (b) placeholder dedup ───────────────────────

def _reset(cust):
    with pt._REGISTRY_LOCK:
        pt._PLACEHOLDERS_TYPED_TS.pop(cust, None)
        pt._REAL_REPLY_AT.pop((cust, ""), None)


def test_no_placeholder_means_not_standing():
    cust = "mt060_b_none"
    _reset(cust)
    assert pt.placeholder_standing_unanswered(cust) < 0


def test_recent_placeholder_is_standing():
    cust = "mt060_b_recent"
    _reset(cust)
    pt.mark_placeholder_typed(cust)
    age = pt.placeholder_standing_unanswered(cust)
    assert age >= 0.0  # one is standing → a second would be suppressed


def test_real_reply_clears_standing():
    cust = "mt060_b_reply"
    _reset(cust)
    pt.mark_placeholder_typed(cust)
    pt.mark_real_reply_delivered(cust)  # reply replaces the placeholder on screen
    assert pt.placeholder_standing_unanswered(cust) < 0  # new placeholder allowed


def test_old_placeholder_not_standing():
    cust = "mt060_b_old"
    _reset(cust)
    with pt._REGISTRY_LOCK:
        pt._PLACEHOLDERS_TYPED_TS[cust] = [time.time() - (pt.PLACEHOLDER_STANDING_WINDOW_S + 5)]
    assert pt.placeholder_standing_unanswered(cust) < 0
