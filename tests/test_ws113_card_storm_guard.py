"""ws113 — card re-push storm guard in ws_observer.

A stuck read-ack cursor makes Feige re-push the SAME nameless card every
~1-2 min (longer than the 15s card dedup window), so each re-push reads as a
fresh re-share and re-dispatches. Live 2026-06-24 (ws109): one card conv
7654745775645164840 re-emitted 389x and drove 107 redundant LLM dispatches over
34 min (read-ack cursor stuck at 7598412653639304500, far below the message id)
— a dispatch storm that stalled the app.

Fix: cap identical-card re-dispatches to STORM_MAX within STORM_WINDOW_S. A
human never re-shares the same card that often, so the pattern is a re-push
loop. A genuine re-share resumes once the window clears.
"""
from __future__ import annotations

import unittest
from pathlib import Path

_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/ws_observer.py"
).read_text(encoding="utf-8")


class _Guard:
    """Pure mirror of the guard's run-with-quiet-reset decision."""

    def __init__(self, storm_max=3, reset_s=300.0):
        self.storm_max = storm_max
        self.reset_s = reset_s
        self.last_ts = None
        self.run = 0

    def allow(self, now):
        if self.last_ts is None or (now - self.last_ts) >= self.reset_s:
            self.run = 0                      # quiet gap -> fresh deliberate re-share
        self.run += 1
        self.last_ts = now                    # update even when suppressing
        return self.run <= self.storm_max


class StormGuardLogicTests(unittest.TestCase):
    def test_first_three_dispatch_then_suppress(self):
        g = _Guard(storm_max=3, reset_s=300.0)
        # 8 server re-pushes 90s apart (the live ~1-2 min cadence, no quiet gap)
        allowed = [g.allow(t) for t in [i * 90.0 for i in range(8)]]
        self.assertEqual(allowed[:3], [True, True, True])
        self.assertTrue(all(a is False for a in allowed[3:]))

    def test_genuine_reshare_resumes_after_quiet(self):
        g = _Guard(storm_max=3, reset_s=300.0)
        t = 0.0
        for _ in range(4):                       # exhaust the cap (4th suppressed)
            g.allow(t)
            t += 90.0
        self.assertFalse(g.allow(t))             # still no quiet gap -> suppressed
        t += g.reset_s + 1                        # a quiet stretch passes
        self.assertTrue(g.allow(t))              # deliberate re-share passes

    def test_caps_the_389_storm_to_max(self):
        g = _Guard(storm_max=3, reset_s=300.0)
        dispatched = sum(g.allow(i * 90.0) for i in range(389))  # the live storm
        # Continuous 90s cadence never hits a quiet gap -> only the first 3 pass.
        self.assertEqual(dispatched, 3)


class StormGuardSourceWiringTests(unittest.TestCase):
    def test_marker_present_and_gated(self):
        self.assertIn("ws113 re-push storm guard", _SRC)
        self.assertIn("ECAN_FEIGE_CARD_STORM_GUARD", _SRC)
        self.assertIn("ECAN_FEIGE_CARD_STORM_MAX", _SRC)
        self.assertIn("ECAN_FEIGE_CARD_STORM_RESET_S", _SRC)

    def test_guard_runs_after_the_15s_window_check(self):
        # Must sit inside the template_card RESHARE branch, after the burst-window
        # suppression — not replace it.
        burst_idx = _SRC.find("retransmit burst -> suppress")
        guard_idx = _SRC.find("ws113 re-push storm guard")
        fall_idx = _SRC.find("fall through to dispatch (re-share is a new turn)")
        self.assertGreater(burst_idx, 0)
        self.assertGreater(guard_idx, burst_idx)   # after the 15s window check
        self.assertGreater(fall_idx, guard_idx)    # before the dispatch fall-through


if __name__ == "__main__":
    unittest.main()
