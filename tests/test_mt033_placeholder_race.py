"""mt033 — placeholder text must be in the recent-reply ledger BEFORE the
CDP typing eval is awaited, and EventMonitor's dom_echo filter must
consult the multi-slot ledger (not just the single-slot field).

Live trace 2026-05-23 13:02:22 肽斯特 (customer's 3-customer flood run,
``customer_logs/eCan.log.1``)::

    13:02:22.541  feige_send: Sent "您好，稍等一下哦~"
    13:02:22.779  ← dom_observed bogus "肽斯特|您好，稍等一下哦~"  ← FILTER FAILED
    13:02:22.883  placeholder_timer typed → remember_agent_reply (TOO LATE)

The 240ms window between CDP success and the post-await ledger write
let the mutation observer fire while ``last_agent_reply_by_customer``
was still empty/stale.  The bogus dom_observed entered the front-desk
queue as if 肽斯特 had typed "您好，稍等一下哦~".  Over the 25-min run
this generated 27+ phantom dispatches, choking 8 idle Q&A bots behind
a serial front-desk → ~3 typings/min vs theoretical ~30+/min.

The fix is two-part:

1. ``runner.py`` placeholder_timer pre-registers ``remember_agent_reply``
   BEFORE awaiting ``_ph_invoke(_send_fn, ...)`` so the ledger is hot
   the instant the bubble appears in the DOM.

2. ``event_monitor.py`` Feige dom_echo filter consults
   ``matches_recent_agent_reply`` (multi-slot, 90s TTL, prefix-tolerant)
   in addition to the single-slot fallback, so a real reply that
   overwrites the single slot doesn't strand the placeholder text in
   an un-recognised state.

These tests are source-level guards: they confirm the orderings and
the import wiring stay in place across future refactors.  Behaviour-
level tests for the LangGraph runtime would require standing up the
full browser-use + placeholder_timer + pool stack, which is outside
the scope of a regression unit test.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


RUNNER_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
MONITOR_SRC = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")


class PlaceholderPreRegisterOrderingTests(unittest.TestCase):
    """``remember_agent_reply`` must appear BEFORE ``await _ph_invoke``
    in the placeholder_timer block, so the multi-slot ledger contains
    the placeholder text the instant the DOM mutation observer sees the
    bubble."""

    def test_placeholder_block_imports_dispatch_state(self) -> None:
        # The mt033 import statement is present in the placeholder block.
        self.assertIn(
            "dispatch_state as _ph_ds",
            RUNNER_SRC,
            "placeholder pre-register must import dispatch_state",
        )

    def test_mt033_marker_present(self) -> None:
        self.assertIn("2026-05-23 mt033", RUNNER_SRC)

    def test_remember_agent_reply_called_before_ph_invoke(self) -> None:
        """The remember_agent_reply call must come BEFORE the
        ``await _ph_invoke(_send_fn, _send_params)`` in the
        placeholder_timer scope.  We locate both line offsets and
        assert the ledger write is FIRST."""
        # The placeholder send is uniquely identified by ``_ph_invoke``
        # plus ``_send_params``.  There is only one such await in the
        # placeholder_timer scope.
        invoke_match = re.search(
            r"await\s+_ph_invoke\(_send_fn,\s*_send_params\)",
            RUNNER_SRC,
        )
        self.assertIsNotNone(
            invoke_match,
            "the placeholder-typer await on _ph_invoke must exist",
        )

        # Search BACKWARDS from the invoke for the nearest
        # remember_agent_reply call — that's the pre-register.
        before_invoke = RUNNER_SRC[: invoke_match.start()]
        last_remember_idx = before_invoke.rfind("_ph_ds.remember_agent_reply(")
        self.assertGreater(
            last_remember_idx,
            -1,
            "remember_agent_reply must be called BEFORE the await on "
            "_ph_invoke (pre-register).  Found nothing in the preceding "
            "scope — the mt033 fix may have been reverted.",
        )

        # And the pre-register must be REASONABLY close to the await
        # (within ~3000 chars), i.e. inside the same placeholder block,
        # not somewhere else entirely.
        self.assertLess(
            invoke_match.start() - last_remember_idx,
            3000,
            "remember_agent_reply pre-register must be in the SAME "
            "block as the placeholder _ph_invoke await",
        )

    def test_no_remember_agent_reply_between_invoke_and_typed_marker(
        self,
    ) -> None:
        """Belt-and-braces: after mt033, there should NOT be a second
        ``remember_agent_reply`` between the await and the typed-marker
        log line, because the pre-register has already done the work."""
        invoke_match = re.search(
            r"await\s+_ph_invoke\(_send_fn,\s*_send_params\)\s*\n\s*_ok\s*=\s*True",
            RUNNER_SRC,
        )
        self.assertIsNotNone(invoke_match)
        # The "typed placeholder" log marker bounds the search window.
        typed_marker_idx = RUNNER_SRC.find(
            "[placeholder_timer] typed placeholder",
            invoke_match.end(),
        )
        self.assertGreater(typed_marker_idx, 0)
        between = RUNNER_SRC[invoke_match.end() : typed_marker_idx]
        self.assertNotIn(
            "_ph_ds.remember_agent_reply",
            between,
            "After mt033 the placeholder-timer remember_agent_reply "
            "lives BEFORE the await — a copy after the await is the "
            "old buggy pattern and would re-introduce the 240ms race",
        )


class EventMonitorMultiSlotFilterTests(unittest.TestCase):
    """The Feige dom_echo filter must consult the multi-slot
    ``matches_recent_agent_reply`` ledger so older placeholder texts
    (which the single-slot field forgets after a real reply
    overwrites it) still get recognised as our own DOM-echo."""

    def test_filter_imports_matches_recent_agent_reply(self) -> None:
        self.assertIn(
            "matches_recent_agent_reply",
            MONITOR_SRC,
            "event_monitor.py must import matches_recent_agent_reply "
            "from dispatch_state for the multi-slot echo check",
        )

    def test_filter_calls_multi_slot_before_single_slot(self) -> None:
        """In the per-item echo branch, the multi-slot call must
        appear BEFORE the single-slot fallback so the multi-slot wins
        when both can match.  This isolates the bug fix to the cases
        the multi-slot is actually meant to cover."""
        # Anchor on the dropped-reason strings, which are unique.
        recent_idx = MONITOR_SRC.find('"dom_echo:recent_agent_reply"')
        last_idx = MONITOR_SRC.find('"dom_echo:last_agent_reply"')
        self.assertGreater(
            recent_idx,
            -1,
            "the recent_agent_reply drop-reason marker must exist "
            "(see mt033 in event_monitor.py)",
        )
        self.assertGreater(last_idx, -1)
        self.assertLess(
            recent_idx,
            last_idx,
            "multi-slot check must be emitted BEFORE single-slot "
            "fallback so the more-recent ledger wins",
        )

    def test_mt033_marker_present_in_event_monitor(self) -> None:
        self.assertIn("2026-05-23 mt033", MONITOR_SRC)


class MultiSlotLedgerBehaviourTests(unittest.TestCase):
    """Unit-test the multi-slot ledger directly so we know the
    EventMonitor's new dependency behaves as expected after mt033."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as _ds,
        )
        self._ds = _ds
        # Use a stable customer key that won't collide with other tests.
        self.cust = "_mt033_test_cust"
        # Clear any leftover state from previous test runs.
        try:
            _ds.recent_agent_replies_by_customer.pop(self.cust, None)
            _ds.last_agent_reply_by_customer.pop(self.cust, None)
        except Exception:
            pass

    def tearDown(self) -> None:
        try:
            self._ds.recent_agent_replies_by_customer.pop(self.cust, None)
            self._ds.last_agent_reply_by_customer.pop(self.cust, None)
        except Exception:
            pass

    def test_multi_slot_remembers_placeholder_after_real_reply(self) -> None:
        """The single-slot is overwritten by the most recent reply, but
        the multi-slot must still match a prior placeholder.  This is
        exactly the case event_monitor.py now leans on."""
        self._ds.remember_agent_reply(self.cust, "您好，稍等一下哦~")
        self._ds.remember_agent_reply(
            self.cust,
            "这款是纯棉的，面料比较柔软亲肤……",
        )

        # Single-slot now holds the real reply only.
        self.assertEqual(
            self._ds.normalize_reply_text("这款是纯棉的，面料比较柔软亲肤……"),
            self._ds.last_agent_reply_by_customer.get(
                self._ds._fingerprint(self.cust, "x")[0]
            ),
        )

        # Multi-slot still recognises the OLDER placeholder text.
        match = self._ds.matches_recent_agent_reply(
            self.cust, "您好，稍等一下哦~"
        )
        self.assertEqual(match, "您好，稍等一下哦~")

        # And still recognises the latest real reply.
        match2 = self._ds.matches_recent_agent_reply(
            self.cust, "这款是纯棉的，面料比较柔软亲肤……"
        )
        self.assertTrue(match2)

    def test_unknown_text_returns_empty_string(self) -> None:
        """A genuine customer message that doesn't echo any of our
        recent replies must not be matched (false-positive would
        silence a real question)."""
        self._ds.remember_agent_reply(self.cust, "您好，稍等一下哦~")
        match = self._ds.matches_recent_agent_reply(
            self.cust, "你们家衣服尺码偏大还是偏小？"
        )
        self.assertEqual(match, "")


if __name__ == "__main__":
    unittest.main()
