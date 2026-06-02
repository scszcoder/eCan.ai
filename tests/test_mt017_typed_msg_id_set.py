"""mt024: typed-msg-id set fixes mt017 mis-fire after ledger TTL expiry.

Live trace 2026-05-22 08:19:40 (packet) / 08:19:41 (肽斯特) — bot's
real reply silently dropped via ``[DIRECT-DELIVERY] human-intervention
skip`` because mt017 mis-fired on OUR own typed bubble.  The bubble
was typed at 08:14:34 (5 min earlier), its text aged out of the
``recent_agent_replies_by_customer`` 90 s ledger by 08:16:04, and the
mt021 baseline gate had already moved past it on the next scrape.
So the next thread-scrape after a quiet period treated our own bubble
as "human typed something we don't recognise" and marked the customer
human-handled — dropping every subsequent reply for 120 s.

Fix: when ``feige_send_message`` returns a verified send, the JS now
surfaces the typed bubble's ``data-id`` as ``verified_msg_id``, and the
Python handler registers it in a permanent (no-TTL) typed-msg-id set
in ``human_intervention``.  The mt017 detection in
``pre_dispatch_enrich`` consults this set BEFORE firing mark_handled,
treating any bubble we typed (even years ago) as ours.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_intervention as _hi,
)


CUST = "packet"


class TypedMsgIdSetTests(unittest.TestCase):
    def setUp(self) -> None:
        _hi._TYPED_AGENT_MSG_IDS.clear()
        _hi._TYPED_AGENT_MSG_IDS_ORDER.clear()

    def tearDown(self) -> None:
        _hi._TYPED_AGENT_MSG_IDS.clear()
        _hi._TYPED_AGENT_MSG_IDS_ORDER.clear()

    def test_unrecorded_is_unknown(self) -> None:
        self.assertFalse(_hi.is_known_typed_msg_id(CUST, "mid_42"))

    def test_record_then_check_round_trip(self) -> None:
        _hi.record_typed_msg_id(CUST, "mid_42")
        self.assertTrue(_hi.is_known_typed_msg_id(CUST, "mid_42"))

    def test_record_isolated_per_customer(self) -> None:
        _hi.record_typed_msg_id(CUST, "mid_42")
        self.assertFalse(_hi.is_known_typed_msg_id("其他客户", "mid_42"))

    def test_empty_inputs_are_safe(self) -> None:
        _hi.record_typed_msg_id("", "mid_42")
        _hi.record_typed_msg_id(CUST, "")
        _hi.record_typed_msg_id("", "")
        self.assertFalse(_hi.is_known_typed_msg_id(CUST, "mid_42"))
        self.assertFalse(_hi.is_known_typed_msg_id(CUST, ""))

    def test_dup_record_no_growth(self) -> None:
        _hi.record_typed_msg_id(CUST, "mid_42")
        _hi.record_typed_msg_id(CUST, "mid_42")
        _hi.record_typed_msg_id(CUST, "mid_42")
        self.assertEqual(1, len(_hi._TYPED_AGENT_MSG_IDS[CUST]))
        self.assertEqual(1, len(_hi._TYPED_AGENT_MSG_IDS_ORDER[CUST]))

    def test_cap_evicts_oldest(self) -> None:
        cap = _hi._TYPED_AGENT_MSG_IDS_CAP
        for i in range(cap + 5):
            _hi.record_typed_msg_id(CUST, f"mid_{i}")
        # First 5 evicted, last `cap` retained
        for i in range(5):
            self.assertFalse(
                _hi.is_known_typed_msg_id(CUST, f"mid_{i}"),
                msg=f"mid_{i} should have been evicted",
            )
        for i in range(5, cap + 5):
            self.assertTrue(
                _hi.is_known_typed_msg_id(CUST, f"mid_{i}"),
                msg=f"mid_{i} should still be tracked",
            )

    def test_whitespace_trimmed(self) -> None:
        _hi.record_typed_msg_id(CUST, "  mid_x  ")
        self.assertTrue(_hi.is_known_typed_msg_id(CUST, "mid_x"))
        self.assertTrue(_hi.is_known_typed_msg_id(CUST, "  mid_x  "))


class JSReturnAndPythonRecordWiringTests(unittest.TestCase):
    """Confirm the JS surfaces ``verified_msg_id`` AND the Python
    handler records it, so a future refactor that drops either side is
    caught here."""

    def test_js_returns_verified_msg_id_on_success(self) -> None:
        src = Path("agent/ec_skills/browser_use_extension/extension_tools_service.py").read_text(encoding="utf-8")
        self.assertIn("verified_msg_id: latestAgentBubbleMsgId()", src)
        self.assertIn("function latestAgentBubbleMsgId()", src)

    def test_python_records_verified_msg_id(self) -> None:
        src = Path("agent/ec_skills/browser_use_extension/extension_tools_service.py").read_text(encoding="utf-8")
        self.assertIn('data.get("verified_msg_id")', src)
        self.assertIn("record_typed_msg_id", src)

    def test_predispatch_consults_set_before_firing(self) -> None:
        src = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py").read_text(encoding="utf-8")
        self.assertIn("is_known_typed_msg_id", src)


if __name__ == "__main__":
    unittest.main()
