"""Tests for human-intervention state tracking (mt017).

The flow detected by ``pre_dispatch_enrich._scrape_and_override_last_message``:
  1. Thread scrape returns ``latest_agent_bubble`` (new in mt017)
  2. If bubble text is NOT in ``dispatch_state.recent_agent_replies_by_customer``,
     it must have been typed by a human (not eCan)
  3. ``human_intervention.mark_handled(customer)`` is called +
     ``placeholder_timer.cancel_any_for_customer(customer)`` aborts in-flight
  4. ``is_handled_recent(customer)`` blocks subsequent dispatches +
     direct-delivery typing for the next HUMAN_HANDLED_TTL_S seconds
"""
from __future__ import annotations

import time
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_intervention as _hi,
    placeholder_timer as _pt,
    dispatch_state as _ds,
)


CUST = "客户01"


class HumanInterventionStateTests(unittest.TestCase):
    def setUp(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _hi._HUMAN_HANDLED_MSG_ID.clear()
        _hi._BASELINE_AGENT_MSG_ID.clear()

    def tearDown(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _hi._HUMAN_HANDLED_MSG_ID.clear()
        _hi._BASELINE_AGENT_MSG_ID.clear()

    def test_mark_then_is_handled(self) -> None:
        self.assertFalse(_hi.is_handled_recent(CUST))
        _hi.mark_handled(CUST, "msg_abc")
        self.assertTrue(_hi.is_handled_recent(CUST))
        self.assertEqual("msg_abc", _hi.get_handled_msg_id(CUST))

    def test_handled_expires_after_ttl(self) -> None:
        _hi.mark_handled(CUST, "msg_abc")
        self.assertTrue(_hi.is_handled_recent(CUST))
        # Force-age past TTL
        _hi._HUMAN_HANDLED_AT[CUST] = time.time() - _hi.HUMAN_HANDLED_TTL_S - 1.0
        self.assertFalse(_hi.is_handled_recent(CUST))

    def test_isolated_per_customer(self) -> None:
        _hi.mark_handled(CUST, "msg_abc")
        self.assertFalse(_hi.is_handled_recent("客户99"))

    def test_mark_refreshes_ts(self) -> None:
        _hi.mark_handled(CUST, "msg_abc")
        ts1 = _hi._HUMAN_HANDLED_AT[CUST]
        time.sleep(0.02)
        _hi.mark_handled(CUST, "msg_xyz")
        ts2 = _hi._HUMAN_HANDLED_AT[CUST]
        self.assertGreater(ts2, ts1)
        self.assertEqual("msg_xyz", _hi.get_handled_msg_id(CUST))

    def test_clear(self) -> None:
        _hi.mark_handled(CUST, "msg_abc")
        _hi.clear(CUST)
        self.assertFalse(_hi.is_handled_recent(CUST))
        self.assertEqual("", _hi.get_handled_msg_id(CUST))

    def test_snapshot_excludes_expired(self) -> None:
        _hi.mark_handled(CUST, "msg_abc")
        _hi.mark_handled("客户99", "msg_xyz")
        _hi._HUMAN_HANDLED_AT[CUST] = time.time() - _hi.HUMAN_HANDLED_TTL_S - 1.0
        snap = _hi.snapshot()
        self.assertIn("客户99", snap["active"])
        self.assertNotIn(CUST, snap["active"])


class HumanInterventionIntegratesWithPlaceholderTimerTests(unittest.TestCase):
    """When a human reply is detected, the placeholder timer should be
    cancelled for that customer.  This is wired in pre_dispatch_enrich
    but we can test the cancel mechanism here directly."""

    def setUp(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()
        _pt._FIRST_SEEN_AT.clear()
        _pt._FIRST_SEEN_BY_CUSTOMER.clear()
        _pt._PLACEHOLDERS_TYPED_TS.clear()

    def tearDown(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _pt._REGISTRY.clear()

    def test_cancel_any_for_customer_kills_timer(self) -> None:
        _pt.arm(CUST, "msg_A", timeout_s=20.0)
        self.assertIn((CUST, "msg_A"), _pt._REGISTRY)
        # Simulate the pre_dispatch_enrich detection flow
        _hi.mark_handled(CUST, "human_msg_id", source="thread_scrape")
        _pt.cancel_any_for_customer(CUST)
        self.assertNotIn((CUST, "msg_A"), _pt._REGISTRY)


class HumanInterventionLedgerComparisonTests(unittest.TestCase):
    """Detection logic in pre_dispatch_enrich:
       _is_ours = matches_recent_agent_reply(customer_key, bubble_text)
       not _is_ours → human"""

    def setUp(self) -> None:
        _ds.last_agent_reply_by_customer.clear()
        _ds.recent_agent_replies_by_customer.clear()

    def tearDown(self) -> None:
        _ds.last_agent_reply_by_customer.clear()
        _ds.recent_agent_replies_by_customer.clear()

    def test_our_own_reply_is_not_classified_as_human(self) -> None:
        # eCan typed this earlier
        _ds.remember_agent_reply(CUST, "好的，我帮您查询一下。")
        # Bubble visible in thread matches what we typed
        match = _ds.matches_recent_agent_reply(CUST, "好的，我帮您查询一下。")
        self.assertTrue(match)  # → NOT human

    def test_human_typed_reply_is_classified_as_human(self) -> None:
        # eCan typed this earlier
        _ds.remember_agent_reply(CUST, "好的，我帮您查询一下。")
        # Different text appears — human typed something we didn't
        match = _ds.matches_recent_agent_reply(CUST, "亲，我看了一下您的订单，明天就能发出哦。")
        self.assertFalse(match)  # → IS human

    def test_placeholder_text_is_recognized_as_ours(self) -> None:
        """Placeholders are remembered via dispatch_state.remember_agent_reply
        in the runner — so a "稍等" bubble shouldn't get classified human."""
        _ds.remember_agent_reply(CUST, "您好，稍等一下哦~")
        match = _ds.matches_recent_agent_reply(CUST, "您好，稍等一下哦~")
        self.assertTrue(match)


class BaselineMsgIdGatingTests(unittest.TestCase):
    """2026-05-21 baseline fix: the FIRST agent bubble observed per
    customer per process is treated as pre-existing (could be a stale
    bubble from a prior app session or one aged out of the recent-reply
    ledger TTL).  Only NEW msg_ids fire mark_handled.

    Without this gating the flood-test 14:28 run mis-fired mt017 for all
    20 customers, silently dropping every Q&A reply.
    """

    def setUp(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _hi._HUMAN_HANDLED_MSG_ID.clear()
        _hi._BASELINE_AGENT_MSG_ID.clear()

    def tearDown(self) -> None:
        _hi._HUMAN_HANDLED_AT.clear()
        _hi._HUMAN_HANDLED_MSG_ID.clear()
        _hi._BASELINE_AGENT_MSG_ID.clear()

    def test_no_baseline_initially(self) -> None:
        self.assertEqual("", _hi.get_baseline_msg_id(CUST))

    def test_set_and_get_baseline(self) -> None:
        _hi.set_baseline_msg_id(CUST, "msg_001")
        self.assertEqual("msg_001", _hi.get_baseline_msg_id(CUST))

    def test_baseline_per_customer(self) -> None:
        _hi.set_baseline_msg_id(CUST, "msg_001")
        self.assertEqual("", _hi.get_baseline_msg_id("客户99"))

    def test_baseline_can_be_overwritten(self) -> None:
        _hi.set_baseline_msg_id(CUST, "msg_001")
        _hi.set_baseline_msg_id(CUST, "msg_002")
        self.assertEqual("msg_002", _hi.get_baseline_msg_id(CUST))

    def test_clear_preserves_baseline(self) -> None:
        # baseline should outlive the human-handled state so the same
        # pre-existing bubble doesn't keep re-triggering mark_handled
        # after an operator clears it
        _hi.set_baseline_msg_id(CUST, "msg_baseline")
        _hi.mark_handled(CUST, "msg_baseline", source="test")
        _hi.clear(CUST)
        self.assertEqual("msg_baseline", _hi.get_baseline_msg_id(CUST))
        self.assertFalse(_hi.is_handled_recent(CUST))


if __name__ == "__main__":
    unittest.main()
