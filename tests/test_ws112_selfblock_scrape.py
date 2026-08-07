"""ws112 Fix A — self-block scrape in the typing-lock guard.

A name-less product card is dispatched under the synthetic ``card:<talk_id>``
identity and grabs the typing lock. The SAME conversation's real-name text row
(e.g. 陆地飞鱼's "这款有包邮吗") then matches the connect-banner/system guard and
is DEFERRED behind the typing lock its OWN card identity is holding — the
conversation blocks itself.

Live trace 2026-06-24: 陆地飞鱼 sent "这款有包邮吗" but the reply
("这边暂未查到包邮信息，我帮您再核实下。") didn't land until ~2 min later; once the
row was finally scraped the pipeline took ~8s. The 2 min was the self-block
deferral (holder=card:7654863671847404826 == 陆地飞鱼's conversation).

Fix: when the typing-lock holder resolves to the same talk_id as the row, do
NOT go sidebar-only — allow the thread scrape (same conversation, so no
cross-customer mis-delivery). A DIFFERENT customer holding the lock still
defers (genuine browser contention).
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    ws_session as _wss,
)

_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class TalkIdMatchPrimitiveTests(unittest.TestCase):
    """The fix matches the holder's ``card:<talk>`` against the row's talk_id,
    resolved via ws_session.talk_for_name when the item carries no talk_id."""

    def setUp(self) -> None:
        _wss._routing.clear()

    def tearDown(self) -> None:
        _wss._routing.clear()

    def test_same_conv_resolves_and_matches(self) -> None:
        _wss._routing["陆地飞鱼"] = "7654863671847404826"
        holder = "card:7654863671847404826"
        holder_talk = holder.split(":", 1)[1]
        self.assertEqual(_wss.talk_for_name("陆地飞鱼"), holder_talk)  # self-block

    def test_different_conv_does_not_match(self) -> None:
        _wss._routing["陆地飞鱼"] = "7654863671847404826"
        # holder is another customer's card → talk_ids differ → NOT a self-block
        holder_talk = "card:9999999999999999999".split(":", 1)[1]
        self.assertNotEqual(_wss.talk_for_name("陆地飞鱼"), holder_talk)

    def test_unknown_name_resolves_empty(self) -> None:
        # No routing entry → empty → guard's `_row_talk and ...` is falsy → defer.
        self.assertEqual(_wss.talk_for_name("陆地飞鱼"), "")


class SelfBlockSourceWiringTests(unittest.TestCase):
    """Guards against accidental removal / mis-placement of Fix A."""

    def test_marker_present_and_gated(self) -> None:
        self.assertIn("ws112 self-block", _SRC)
        self.assertIn("ECAN_FEIGE_SELFBLOCK_SCRAPE", _SRC)
        self.assertIn("talk_for_name", _SRC)

    def test_selfblock_gates_the_sidebar_only_branch(self) -> None:
        # The self-block flag must be computed BEFORE, and gate, the
        # sidebar-only branch — otherwise the row still defers.
        sb_idx = _SRC.find("_self_block_same_conv = False")
        cond_idx = _SRC.find("if _holder and not _self_block_same_conv:")
        set_idx = _SRC.find('sidebar_only_reason = "typing_lock"')
        self.assertGreater(sb_idx, 0)
        self.assertGreater(cond_idx, sb_idx)   # computed before the branch
        self.assertGreater(set_idx, cond_idx)  # branch sets the flag after


if __name__ == "__main__":
    unittest.main()
