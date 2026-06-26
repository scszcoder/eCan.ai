"""ws116 — missed-msg backstop arms the 转人工/人工 handover ack.

Live 2026-06-25 (ws113 run, customer 'packet'): customer typed 人工, but the WS
reader never decoded a 人工 text frame, the DOM monitor was paused under
WS-owns-dispatch, and bare 人工 matches NO system filter — so the handover fell
through every crack (no dispatch, no [微笑] ack). The ws108 backstop scans the
sidebar continuously regardless of who owns dispatch, so it arms the ack for any
handover-trigger preview. Arming only (no routing change), idempotent +
rate-limited.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_mode as hm,
    system_message_filter as smf,
)

_FD_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/front_desk.py"
).read_text(encoding="utf-8")


class HandoverPreviewTriggerTests(unittest.TestCase):
    def test_bare_renref_not_caught_by_system_filter(self):
        # The gap: bare 人工 matches no system pattern (only 转人工 does), so the
        # backstop's system-skip never sees it as a handover.
        self.assertIsNone(smf.first_matching_pattern("人工"))
        self.assertEqual(smf.first_matching_pattern("转人工"), "transfer_to_human_label")

    def test_is_human_trigger_catches_both(self):
        # is_human_trigger is the discriminator the backstop now uses.
        self.assertTrue(hm.is_human_trigger("人工"))
        self.assertTrue(hm.is_human_trigger("转人工"))
        self.assertFalse(hm.is_human_trigger("这款面料透气吗"))
        self.assertFalse(hm.is_human_trigger("穿久了会不会缩水啊"))


class BackstopWiringTests(unittest.TestCase):
    def test_arms_ack_before_routing(self):
        marker = _FD_SRC.find("ws116 backstop handover trigger")
        arm = _FD_SRC.find("_bs_note_ho(_name)")
        route = _FD_SRC.find("ws108 missed-msg backstop: routing")
        self.assertGreater(marker, 0)
        self.assertGreater(arm, 0)
        self.assertGreater(route, arm)  # ack armed before the routing decision
        self.assertIn("is_human_trigger", _FD_SRC)


if __name__ == "__main__":
    unittest.main()
