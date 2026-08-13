"""ws115 — 转人工 handover ack fires reliably (early-arm, both paths).

A customer typing 转人工 is a customer message that must get a response within
Feige's ~40s window. It was being swallowed: the system-message filter matches
`transfer_to_human_label`, and the only ack-arming (`_maybe_arm_handover_ack`)
sits at the BOTTOM of enrich, so an earlier skip (dom-echo / typing-lock /
self-block) on the DOM path bypasses it. Fix: arm the [微笑] ack at the TOP of
enrich_item, before any skip — independent of which guard fires. The WS path
already arms in ws_observer. Behavior chosen by the customer: keep the [微笑]
emoji ack, and keep assisting on later turns.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_mode as hm,
    placeholder_timer as pt,
)

_ENRICH_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class TriggerMatchTests(unittest.TestCase):
    def test_matches_transfer_variants(self):
        for t in ("转人工", "转人工客服", "人工", "人工客服", "我要转人工"):
            self.assertTrue(hm.is_human_trigger(t), t)

    def test_rejects_normal_questions(self):
        for t in ("你好在吗", "这件多少钱", "包邮吗", "什么材质"):
            self.assertFalse(hm.is_human_trigger(t), t)


class AckArmingTests(unittest.TestCase):
    def setUp(self):
        pt.clear_handover_ack("cust_test_zr")

    def tearDown(self):
        pt.clear_handover_ack("cust_test_zr")

    def test_arming_marks_pending_and_drains_once(self):
        # default: handover_ack_enabled() is on
        self.assertTrue(pt.handover_ack_enabled())
        pt.note_handover_ack_needed("cust_test_zr")
        drained = pt._drain_handover_acks()
        self.assertIn("cust_test_zr", drained)
        # second drain (no re-arm) yields nothing -> exactly one ack per handover
        self.assertNotIn("cust_test_zr", pt._drain_handover_acks())


class EarlyArmWiringTests(unittest.TestCase):
    def test_enrich_arms_before_the_skips(self):
        early = _ENRICH_SRC.find("转人工 handover trigger (early-arm)")
        # the bottom-of-pipeline ack call (must come AFTER the early arm)
        late = _ENRICH_SRC.find("_maybe_arm_handover_ack(customer_key, _row_hit")
        self.assertGreater(early, 0)
        self.assertGreater(late, early)  # early-arm precedes the system-filter skip arm
        self.assertIn("is_human_handover_request", _ENRICH_SRC)  # ws117: standalone on the preview


if __name__ == "__main__":
    unittest.main()
