"""mt034 — two coordinated fixes for the customer's persistent latency:

1. ``normalize_reply_text`` now STRIPS whitespace instead of collapsing
   it to a single space.  Feige's sidebar preview strips ``\\n`` to
   nothing; collapsing to a space introduced a phantom space at every
   line break and broke exact equality between the bot's recorded
   reply and the sidebar text — multi-line bot replies leaked past
   the dom_echo filter and re-entered the queue as "new customer
   messages".  Live trace 2026-05-23 16:22:26 肽斯特.

2. ``feige_send_message`` source guard now relaxes the strict latest-
   only match when the gap between the target bubble (the customer
   message the bot's reply was meant for) and the latest customer
   bubble is within ``ECAN_FEIGE_STALE_GAP_S`` (default 300s).  The
   strict guard was discarding bot replies whenever the customer
   typed a 2nd question within seconds of the first — even though
   both questions deserved answers.  Live trace 2026-05-23 16:27:29
   肽斯特: bot's answer to "能不能包邮，能发顺丰吗" (Q1) was rejected
   because 肽斯特 typed Q2 "110cm衣服尺码" 74s later; Q1 was silently
   lost.

The fixes are coordinated because they hit different stages of the
same failure path: phantom dispatches (Fix 1) inflate the queue,
which makes more turns hit the stale-guard race (Fix 2) which drops
even more answers.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dispatch_state as _ds,
)


class NormalizeWhitespaceStripTests(unittest.TestCase):
    """Behaviour change: ``\\s+`` is replaced by '' (was ' ')."""

    def test_newline_in_reply_strips_to_no_space(self) -> None:
        # The live trace text from 2026-05-23 16:22:26
        reply = (
            "可以的，这款面料比较柔软亲肤，小宝宝日常穿是没问题的，舒适度也可以。\n"
            "如果您不想踩坑，可以优先看看这种比较基础、百搭的推荐款。\n"
            "您方便告诉我宝宝现在的身高或月龄吗？我可以顺便帮您推荐更合适的尺码和款式。"
        )
        sidebar = (
            "可以的，这款面料比较柔软亲肤，小宝宝日常穿是没问题的，舒适度也可以。"
            "如果您不想踩坑，可以优先看看这种比较基础、百搭的推荐款。"
            "您方便告诉我宝宝现在的身高或月龄吗？我可以顺便帮您推荐更合适的尺码和款式。"
        )
        # After mt034 normalize, the two MUST normalize to identical
        # 120-char prefixes so reply_echo_matches can compare them.
        n_reply = _ds.normalize_reply_text(reply)
        n_sidebar = _ds.normalize_reply_text(sidebar)
        self.assertEqual(n_reply, n_sidebar)

    def test_no_phantom_space_at_line_breaks(self) -> None:
        # A reply with internal newlines must NOT have spaces after
        # normalization where the newlines were.
        normalized = _ds.normalize_reply_text("aaa\nbbb")
        self.assertEqual(normalized, "aaabbb")
        self.assertNotIn(" ", normalized)

    def test_trailing_leading_whitespace_stripped(self) -> None:
        self.assertEqual(_ds.normalize_reply_text("  hello\n\nworld  "), "helloworld")

    def test_empty_input_returns_empty(self) -> None:
        self.assertEqual(_ds.normalize_reply_text(""), "")
        self.assertEqual(_ds.normalize_reply_text(None), "")

    def test_truncates_to_120_chars(self) -> None:
        long_text = "中" * 200
        self.assertEqual(len(_ds.normalize_reply_text(long_text)), 120)

    def test_reply_echo_matches_post_mt034_multiline_case(self) -> None:
        # End-to-end: with the new normalize, reply_echo_matches must
        # recognise the sidebar echo of a multi-line bot reply.
        reply = "前面说的款式都挺合适。\n建议先选120码。"
        sidebar = "前面说的款式都挺合适。建议先选120码。"
        self.assertTrue(_ds.reply_echo_matches(sidebar, reply))


class TimeGapStaleRelaxationTests(unittest.TestCase):
    """The Python-side decision logic for the time-gap relaxation.
    Source-level guards that catch accidental removal in a future
    refactor.  Behavioural tests at the JS+Python boundary would need
    the full browser-use stack, which isn't worth standing up here."""

    SRC = Path(
        "agent/ec_skills/browser_use_extension/extension_tools_service.py"
    ).read_text(encoding="utf-8")

    def test_js_accepts_bypass_parameter(self) -> None:
        # The JS IIFE signature must include the new parameter.
        self.assertIn(
            "expectedSourceText, bypassOlderBubbleMatch",
            self.SRC,
            "JS function signature must accept bypassOlderBubbleMatch",
        )
        # And the invocation must pass the placeholder.
        self.assertIn(
            "EXPECTED_SOURCE_TEXT, BYPASS_OLDER_BUBBLE_MATCH",
            self.SRC,
        )

    def test_js_branches_on_bypass_for_older_bubble_match(self) -> None:
        # The crucial code path that turns rejection → sourceOk.
        self.assertIn("matchedAt > 0 && bypassOlderBubbleMatch", self.SRC)
        self.assertIn("source_guard_bypassed_older_bubble_match", self.SRC)

    def test_python_substitutes_bypass_placeholder(self) -> None:
        self.assertIn(
            'replace("BYPASS_OLDER_BUBBLE_MATCH"',
            self.SRC,
        )

    def test_python_reads_bypass_attr_from_params(self) -> None:
        # The retry sets ``_mt034_bypass_older_bubble_match`` on params.
        self.assertIn("_mt034_bypass_older_bubble_match", self.SRC)

    def test_python_retry_only_on_older_bubble_match(self) -> None:
        # Retry must be gated on stale_reason == older_bubble_match.
        # no_match (bubble vanished) must still hard-fail.
        m = re.search(
            r'data\.get\("stale_reason"\)\s*==\s*"older_bubble_match"',
            self.SRC,
        )
        self.assertIsNotNone(m, "must gate retry on older_bubble_match")

    def test_python_retry_uses_first_seen_registry(self) -> None:
        self.assertIn("get_message_first_seen", self.SRC)
        # And it imports from placeholder_timer module (where the
        # registry lives).
        self.assertIn(
            "placeholder_timer as _mt034_pt",
            self.SRC,
        )

    def test_python_retry_honours_stale_gap_env_var(self) -> None:
        self.assertIn('"ECAN_FEIGE_STALE_GAP_S"', self.SRC)
        # Default 300 must be present.
        self.assertIn('"300"', self.SRC)

    def test_python_retry_calls_self_recursively(self) -> None:
        # The retry must recursively call feige_send_message with the
        # bypass flag set, NOT just return the failed result.
        self.assertIn(
            "return await feige_send_message(",
            self.SRC,
        )

    def test_python_retry_emits_ledger_event(self) -> None:
        self.assertIn("feige_send_mt034_stale_relaxed", self.SRC)


class GapDecisionLogicTests(unittest.TestCase):
    """Pure-Python mirror of the decision logic for fast exercising."""

    @staticmethod
    def should_retry(
        stale_reason: str,
        target_ts: float,
        latest_ts: float,
        bypass_already_on: bool,
        threshold_s: float = 300.0,
    ) -> bool:
        if stale_reason != "older_bubble_match":
            return False
        if bypass_already_on:
            return False
        if target_ts <= 0 or latest_ts <= 0:
            return False
        if latest_ts <= target_ts:
            return False
        gap_s = latest_ts - target_ts
        return 0 < gap_s <= threshold_s

    def test_retry_when_gap_under_threshold(self) -> None:
        self.assertTrue(self.should_retry("older_bubble_match", 1000.0, 1074.0, False))
        # 74s gap matches the 肽斯特 包邮/110cm trace.

    def test_no_retry_at_boundary_plus_one(self) -> None:
        self.assertFalse(self.should_retry("older_bubble_match", 1000.0, 1301.0, False))

    def test_no_retry_at_exact_boundary_plus(self) -> None:
        # Gap exactly equal to threshold IS allowed (<=).
        self.assertTrue(self.should_retry("older_bubble_match", 1000.0, 1300.0, False))

    def test_no_retry_when_bypass_already_on(self) -> None:
        # Prevents infinite recursion on the second pass.
        self.assertFalse(self.should_retry("older_bubble_match", 1000.0, 1050.0, True))

    def test_no_retry_for_no_match_stale_reason(self) -> None:
        # Genuine "bubble has vanished" must still hard-fail.
        self.assertFalse(self.should_retry("no_match", 1000.0, 1050.0, False))

    def test_no_retry_when_timestamps_missing(self) -> None:
        # Registry purged or never recorded → conservative skip.
        self.assertFalse(self.should_retry("older_bubble_match", 0.0, 1050.0, False))
        self.assertFalse(self.should_retry("older_bubble_match", 1000.0, 0.0, False))

    def test_no_retry_when_latest_not_actually_newer(self) -> None:
        # Defensive: latest must be strictly newer than target.
        self.assertFalse(self.should_retry("older_bubble_match", 1050.0, 1050.0, False))
        self.assertFalse(self.should_retry("older_bubble_match", 1050.0, 1000.0, False))

    def test_custom_threshold_via_env_var_concept(self) -> None:
        # If admin sets a smaller threshold (e.g. 60s), longer gaps fail.
        self.assertFalse(self.should_retry("older_bubble_match", 1000.0, 1074.0, False, threshold_s=60.0))
        self.assertTrue(self.should_retry("older_bubble_match", 1000.0, 1059.0, False, threshold_s=60.0))


if __name__ == "__main__":
    unittest.main()
