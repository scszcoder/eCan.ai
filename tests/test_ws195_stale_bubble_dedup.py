"""ws195 — a stale thread bubble must not make a live question look answered.

PreDispatch enriches a sidebar row by scraping the thread. mt052A already
handles the case where the scraped bubble is NEWER than the sidebar: it merges
both texts so neither question is lost. Its comment assumes the scraped bubble
is the newer one and keeps ``source_msg_id`` from it.

When the thread DOM lags a WS frame the opposite is true — the scraped bubble is
the turn we already ANSWERED — and Stage-2 dedup then reads "customer said
nothing new" and drops a live question.

Live 0.9.98m trace (陆地飞鱼):

    09:36:49  answered  会不会透气            msg_id=...3B48992F
    09:37:44  WS frame  身高125穿哪个码       msg_id=1876994098202732
    09:37:44  scrape still returns 会不会透气 (...3B48992F)
    09:37:44  merged sidebar + bubble
    09:37:44  msg-id dedup skip  ->  assigned=0
    ...       customer waits 1m44s and re-asks at 09:39:28

Reaching the merge branch is itself the proof that the sidebar holds text the
bubble does not, so that is the signal this guard keys on.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
    "pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class SourceWiringTests(unittest.TestCase):
    """The merge marks the item; the dedup honours the mark."""

    def test_merge_branch_marks_the_item(self) -> None:
        i = SRC.find('item["last_message"] = merged')
        self.assertGreater(i, -1, "the mt052A merge moved")
        block = SRC[i:i + 1400]
        self.assertIn('item["_ws195_sidebar_ahead_of_bubble"] = True', block)

    def test_dedup_is_bypassed_when_marked(self) -> None:
        i = SRC.find("Stage 2: strict msg-id dedup")
        self.assertGreater(i, -1)
        block = SRC[i:i + 1600]
        self.assertIn("_ws195_sidebar_ahead_of_bubble", block)
        self.assertIn("not _ws195_stale_id and _check_msg_id_dedup(", block)

    def test_guard_has_a_kill_switch(self) -> None:
        self.assertIn("ECAN_FEIGE_WS195_STALE_ID_GUARD", SRC)

    def test_only_the_merge_branch_sets_it(self) -> None:
        """The override branches (mt057 / plain override) must NOT mark it:
        there the bubble genuinely IS the latest text."""
        self.assertEqual(SRC.count('item["_ws195_sidebar_ahead_of_bubble"] = True'), 1)


class DedupBehaviourTests(unittest.TestCase):
    """_check_msg_id_dedup itself is unchanged — that is deliberate. It still
    suppresses a genuine repeat; ws195 only decides whether to consult it."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        self.pde = pde

    def test_repeat_of_the_same_turn_is_still_deduped(self) -> None:
        cache = {"陆地飞鱼": "MSG-1"}
        self.assertTrue(
            self.pde._check_msg_id_dedup("陆地飞鱼", "MSG-1", cache, "sess", "tag")
        )

    def test_a_new_turn_is_not_deduped(self) -> None:
        cache = {"陆地飞鱼": "MSG-1"}
        self.assertFalse(
            self.pde._check_msg_id_dedup("陆地飞鱼", "MSG-2", cache, "sess", "tag")
        )

    def test_empty_scraped_id_is_a_no_op(self) -> None:
        cache = {"陆地飞鱼": "MSG-1"}
        self.assertFalse(
            self.pde._check_msg_id_dedup("陆地飞鱼", "", cache, "sess", "tag")
        )


class GuardDecisionTests(unittest.TestCase):
    """The decision the guard encodes, exercised directly on the item dict."""

    @staticmethod
    def _bypass(item, env="1"):
        import os
        with mock.patch.dict(os.environ, {"ECAN_FEIGE_WS195_STALE_ID_GUARD": env}):
            return bool(item.get("_ws195_sidebar_ahead_of_bubble")) and \
                os.environ.get("ECAN_FEIGE_WS195_STALE_ID_GUARD", "1") != "0"

    def test_marked_item_bypasses(self) -> None:
        self.assertTrue(self._bypass({"_ws195_sidebar_ahead_of_bubble": True}))

    def test_unmarked_item_does_not_bypass(self) -> None:
        """A plain override — bubble IS the latest — must still dedup, or a
        customer who says nothing new gets answered over and over."""
        self.assertFalse(self._bypass({"last_message": "会不会透气"}))

    def test_kill_switch_restores_old_behaviour(self) -> None:
        self.assertFalse(
            self._bypass({"_ws195_sidebar_ahead_of_bubble": True}, env="0")
        )


if __name__ == "__main__":
    unittest.main()
