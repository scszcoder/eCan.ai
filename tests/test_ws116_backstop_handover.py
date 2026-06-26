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

    def test_handover_request_catches_real_requests(self):
        # ws117: the backstop uses is_human_handover_request (SHORT standalone).
        for t in ("人工", "转人工", "我要转人工", "人工客服", "转人工客服"):
            self.assertTrue(hm.is_human_handover_request(t), t)

    def test_handover_request_excludes_our_own_text(self):
        # ws117 regression: the ws116 backstop runs on the sidebar PREVIEW, which is
        # often OUR placeholder/reply or a platform notice — all contain 人工 and
        # MUST NOT arm a false [微笑] (live ws116 1-vs-6: 191 false firings on
        # '人工服务正在回复中...' -> CDP-eval flood -> earlier HANDOFF-STARVED).
        for t in ("人工服务正在回复中...", "正在为您转接人工客服",
                  "现在是人工客服为您服务", "这边暂未查到运费险信息转人工",
                  "穿久了会不会缩水啊", "75斤推荐1个"):
            self.assertFalse(hm.is_human_handover_request(t), t)


class BackstopWiringTests(unittest.TestCase):
    def test_arms_ack_before_routing(self):
        marker = _FD_SRC.find("ws116 backstop handover trigger")
        arm = _FD_SRC.find("_bs_note_ho(_name)")
        route = _FD_SRC.find("ws108 missed-msg backstop: routing")
        self.assertGreater(marker, 0)
        self.assertGreater(arm, 0)
        self.assertGreater(route, arm)  # ack armed before the routing decision
        self.assertIn("is_human_handover_request", _FD_SRC)  # ws117: standalone, not substring


if __name__ == "__main__":
    unittest.main()
