"""Regression tests for placeholder-after-real-reply suppression
(2026-05-20 v2 per-turn).

History
-------
v1 (mt015 morning): cancel() was insufficient because PreDispatch
re-firing for the same customer with empty src_msg_id armed a second
timer that kept firing.  Switched to cancel_any_for_customer().

v2 (mt015 afternoon): cancel_any_for_customer regressed the common
case — an older in-flight turn's reply landing would kill the LATEST
turn's placeholder timer, leaving the customer with no acknowledgment
for 3+ minutes (客户02 港澳台运费, 客户20 你们默认走什么快递, etc).
Reverted runner to use cancel(customer, src_msg_id) — per-turn.

Both cancel() and cancel_any_for_customer() now also stamp
_REAL_REPLY_AT keyed by (customer, source_msg_id), so the placeholder
submit coroutine can suppress in-flight (already-claimed) placeholders
for the SPECIFIC turn that was answered, leaving other turns alone.
"""
from __future__ import annotations

import time
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    placeholder_timer as _pt,
)


CUST = "客户01"


class PerTurnCancelTests(unittest.TestCase):
    def setUp(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()

    def tearDown(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()

    def test_cancel_specific_turn_does_not_affect_other_turn(self) -> None:
        """The core fix — cancelling turn A's timer must leave turn B's."""
        _pt.arm(CUST, "msg_A", timeout_s=20)
        _pt.arm(CUST, "msg_B", timeout_s=20)
        self.assertTrue(_pt.cancel(CUST, "msg_A"))
        # B's timer must remain
        self.assertEqual(1, sum(1 for k in _pt._REGISTRY if k[0] == CUST))
        # B's suppression flag must be unset
        self.assertFalse(_pt.is_real_reply_recent(CUST, "msg_B"))
        # A's suppression flag is set
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))

    def test_cancel_specific_turn_stamps_suppression(self) -> None:
        _pt.arm(CUST, "msg_A", timeout_s=20)
        self.assertFalse(_pt.is_real_reply_recent(CUST, "msg_A"))
        _pt.cancel(CUST, "msg_A")
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))

    def test_cancel_any_kills_all_AND_stamps_each_turn(self) -> None:
        """cancel_any_for_customer remains available for code paths that
        don't know the src_msg_id (rare).  Stamps per-turn so each
        cancelled turn's in-flight placeholder is suppressed."""
        _pt.arm(CUST, "msg_A", timeout_s=20)
        _pt.arm(CUST, "msg_B", timeout_s=20)
        n = _pt.cancel_any_for_customer(CUST)
        self.assertEqual(2, n)
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_B"))
        # Also stamps empty-src so unknown-src placeholders get caught
        self.assertTrue(_pt.is_real_reply_recent(CUST, ""))

    def test_real_reply_recent_expires(self) -> None:
        _pt.mark_real_reply_delivered(CUST, "msg_A")
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))
        # Force-age past TTL
        _pt._REAL_REPLY_AT[(CUST, "msg_A")] = (
            time.time() - _pt.REAL_REPLY_SUPPRESS_S - 1.0
        )
        self.assertFalse(_pt.is_real_reply_recent(CUST, "msg_A"))

    def test_real_reply_recent_isolated_per_customer(self) -> None:
        _pt.mark_real_reply_delivered(CUST, "msg_A")
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))
        self.assertFalse(_pt.is_real_reply_recent("客户99", "msg_A"))

    def test_claim_then_cancel_specific_turn_suppresses_that_turn(self) -> None:
        """The race the suppression targets: an entry was claimed
        (about to be typed), then the real reply for THIS turn arrives.
        The submit code must consult is_real_reply_recent for this
        specific (customer, src_msg_id) to skip the type."""
        _pt.arm(CUST, "msg_A", timeout_s=20.0)
        _pt.arm(CUST, "msg_B", timeout_s=20.0)
        # Force-expire both deadlines (bypasses the 1s grace at arm time)
        for k in list(_pt._REGISTRY.keys()):
            if k[0] == CUST:
                _pt._REGISTRY[k].deadline_at = time.time() - 1.0
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=20.0)
        self.assertEqual(2, len(expired))
        # Real reply for A arrives between claim and type
        _pt.cancel(CUST, "msg_A")
        # A's already-claimed placeholder should be suppressed at submit
        self.assertTrue(_pt.is_real_reply_recent(CUST, "msg_A"))
        # B's already-claimed placeholder is NOT suppressed (B not answered yet)
        self.assertFalse(_pt.is_real_reply_recent(CUST, "msg_B"))


class FirstSeenAnchoringTests(unittest.TestCase):
    """The placeholder timer's deadline must be anchored to the customer
    message's first-seen time (EventMonitor records it), not to
    PreDispatch's dispatch time.  Under flood load PreDispatch latency
    is 5-15s, so without anchoring a 20s placeholder fires 25-35s after
    the customer sent — too late to satisfy Feige's 30s red-flag clock.
    """
    def setUp(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()
        _pt._FIRST_SEEN_AT.clear()

    def tearDown(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()
        _pt._FIRST_SEEN_AT.clear()

    def test_arm_uses_first_seen_anchor_when_recorded(self) -> None:
        # Customer message arrived 10s ago
        _pt._FIRST_SEEN_AT[(CUST, "msg_A")] = time.time() - 10.0
        # PreDispatch arms with 20s timeout — should fire in 10s, not 20s
        _pt.arm(CUST, "msg_A", timeout_s=20.0)
        entry = _pt._REGISTRY[(CUST, "msg_A")]
        delay = entry.deadline_at - time.time()
        self.assertLess(delay, 11.0, f"expected <11s (20-10 elapsed), got {delay:.1f}s")
        self.assertGreater(delay, 8.0)

    def test_arm_falls_back_to_now_when_no_first_seen(self) -> None:
        _pt.arm(CUST, "msg_unknown", timeout_s=20.0)
        entry = _pt._REGISTRY[(CUST, "msg_unknown")]
        delay = entry.deadline_at - time.time()
        # No anchor → fires at now+20s
        self.assertGreater(delay, 19.0)
        self.assertLess(delay, 21.0)

    def test_arm_grace_period_when_first_seen_is_very_old(self) -> None:
        # Message seen 30s ago, timeout=20s — deadline already past
        # Should grace 1s rather than fire immediately at arm time
        _pt._FIRST_SEEN_AT[(CUST, "msg_old")] = time.time() - 30.0
        _pt.arm(CUST, "msg_old", timeout_s=20.0)
        entry = _pt._REGISTRY[(CUST, "msg_old")]
        delay = entry.deadline_at - time.time()
        self.assertGreaterEqual(delay, 0.9)
        self.assertLess(delay, 2.0)

    def test_mark_message_first_seen_idempotent_keeps_earliest(self) -> None:
        _pt.mark_message_first_seen(CUST, "msg_X")
        first = _pt._FIRST_SEEN_AT[(CUST, "msg_X")]
        time.sleep(0.05)
        _pt.mark_message_first_seen(CUST, "msg_X")
        second = _pt._FIRST_SEEN_AT[(CUST, "msg_X")]
        self.assertEqual(first, second, "second observation must not overwrite first")

    def test_mark_message_first_seen_noop_with_empty_msg_id(self) -> None:
        _pt.mark_message_first_seen(CUST, "")
        # Per-msg-id record stays empty
        self.assertFalse(_pt._FIRST_SEEN_AT)
        # But per-customer fallback IS recorded
        self.assertIn(CUST, _pt._FIRST_SEEN_BY_CUSTOMER)

    def test_per_customer_fallback_used_when_no_per_msg_record(self) -> None:
        # EventMonitor recorded customer arrival without msg_id
        _pt.mark_message_first_seen(CUST, "")
        time.sleep(0.01)
        # PreDispatch later arms with a specific msg_id
        _pt.arm(CUST, "msg_X", timeout_s=20.0)
        entry = _pt._REGISTRY[(CUST, "msg_X")]
        # Anchor used per-customer fallback (≈now), deadline ≈ now+20s
        delay = entry.deadline_at - time.time()
        self.assertGreater(delay, 19.0)
        self.assertLess(delay, 21.0)


class ClaimSuppressedWhenRealReplyInProgressTests(unittest.TestCase):
    """The runner stamps _REAL_REPLY_AT[(cust, src)] right when it starts
    typing the real reply (not just on success).  claim_expired must
    consult this to avoid claiming a placeholder for a turn whose real
    reply is mid-type — preventing the 客户14 6ms-race where both bubbles
    landed in the chat within a few ms of each other."""

    def setUp(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()
        _pt._FIRST_SEEN_AT.clear()
        _pt._FIRST_SEEN_BY_CUSTOMER.clear()

    def tearDown(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()

    def test_claim_skips_entry_when_real_reply_in_progress(self) -> None:
        _pt.arm(CUST, "msg_A", timeout_s=20.0)
        # Force-expire the deadline
        _pt._REGISTRY[(CUST, "msg_A")].deadline_at = time.time() - 1.0
        # Runner just started typing the real reply for msg_A
        _pt.mark_real_reply_delivered(CUST, "msg_A")
        # Sweeper runs claim_expired — should skip msg_A
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=15.0)
        self.assertEqual(0, len(expired), "claim must skip turns with in-progress real reply")
        # Registry entry also dropped (no more wasted firings)
        self.assertNotIn((CUST, "msg_A"), _pt._REGISTRY)

    def test_claim_skips_one_turn_but_returns_other(self) -> None:
        _pt.arm(CUST, "msg_A", timeout_s=20.0)
        _pt.arm(CUST, "msg_B", timeout_s=20.0)
        for k in list(_pt._REGISTRY.keys()):
            if k[0] == CUST:
                _pt._REGISTRY[k].deadline_at = time.time() - 1.0
        _pt.mark_real_reply_delivered(CUST, "msg_A")  # only A in progress
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=15.0)
        # B's placeholder still claimed; A skipped
        self.assertEqual(1, len(expired))
        self.assertEqual("msg_B", expired[0].source_msg_id)


class PerCustomerHardCapTests(unittest.TestCase):
    """Fix B (2026-05-21): regardless of how many timers exist for a
    customer (phantom + real turn both armed because PreDispatch
    supersede missed one), enforce a hard ceiling of max_placeholders
    typed per customer per ``PLACEHOLDER_CAP_WINDOW_S``.

    Without this, the 客户01 phantom-+-real pattern produced 6
    placeholders per customer (3 from each timer).
    """

    def setUp(self) -> None:
        _pt._REGISTRY.clear()
        _pt._REAL_REPLY_AT.clear()
        _pt._FIRST_SEEN_AT.clear()
        _pt._FIRST_SEEN_BY_CUSTOMER.clear()
        _pt._PLACEHOLDERS_TYPED_TS.clear()

    def tearDown(self) -> None:
        _pt._REGISTRY.clear()
        _pt._PLACEHOLDERS_TYPED_TS.clear()

    def test_cap_blocks_further_placeholders_for_same_customer(self) -> None:
        # Simulate that 3 placeholders were typed for this customer
        # within the cap window
        for _ in range(3):
            _pt.mark_placeholder_typed(CUST)
        self.assertEqual(3, _pt.count_recent_placeholders(CUST))
        # New timer arms (e.g., a phantom from a missed supersede)
        _pt.arm(CUST, "phantom_msg", timeout_s=20.0)
        _pt._REGISTRY[(CUST, "phantom_msg")].deadline_at = time.time() - 1.0
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=15.0)
        self.assertEqual(0, len(expired), "cap must block additional placeholders")
        # Entry was dropped (no point keeping a doomed-to-skip timer)
        self.assertNotIn((CUST, "phantom_msg"), _pt._REGISTRY)

    def test_cap_window_expires(self) -> None:
        # Type 3 placeholders, then age them past the window
        for _ in range(3):
            _pt.mark_placeholder_typed(CUST)
        # Force-age all entries past TTL
        _pt._PLACEHOLDERS_TYPED_TS[CUST] = [
            time.time() - _pt.PLACEHOLDER_CAP_WINDOW_S - 1.0
        ] * 3
        # Should report 0 now
        self.assertEqual(0, _pt.count_recent_placeholders(CUST))
        # New timer can fire again
        _pt.arm(CUST, "msg_after_window", timeout_s=20.0)
        _pt._REGISTRY[(CUST, "msg_after_window")].deadline_at = time.time() - 1.0
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=15.0)
        self.assertEqual(1, len(expired))

    def test_cap_isolated_per_customer(self) -> None:
        for _ in range(3):
            _pt.mark_placeholder_typed(CUST)
        # Other customer not at cap
        _pt.arm("客户99", "msg_X", timeout_s=20.0)
        _pt._REGISTRY[("客户99", "msg_X")].deadline_at = time.time() - 1.0
        expired = _pt.claim_expired(max_placeholders=3, rearm_s=15.0)
        self.assertEqual(1, len(expired))
        self.assertEqual("客户99", expired[0].customer_key)


if __name__ == "__main__":
    unittest.main()
