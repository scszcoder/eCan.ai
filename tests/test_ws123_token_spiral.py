"""ws123 — break the HANDOFF-STARVED token re-capture spiral.

Under a high-concurrency burst the shared CDP loop starves, so a raw send's server
echo misses its confirm window and the caller invalidate()s the token; the next send
then re-captures via a SLOW CDP Runtime.evaluate, which piles onto the already-starved
loop and worsens the starvation (122 re-captures in the ws118 1-vs-8 burst). A token is
good for ~90s, so an unconfirmed echo seconds after capture is loop-starvation, not a
stale token. ws123 throttles invalidate() so a fresh token is NOT dropped, and
single-flights the capture so concurrent callers share one eval.
"""
from __future__ import annotations

import time
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    ws_raw_sender as rs,
)

_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/ws_raw_sender.py"
).read_text(encoding="utf-8")


class InvalidateThrottleTests(unittest.TestCase):
    def setUp(self):
        self._cp, self._ts = rs._conn_params, rs._conn_params_ts

    def tearDown(self):
        rs._conn_params, rs._conn_params_ts = self._cp, self._ts

    def test_fresh_token_is_NOT_dropped(self):
        # the spiral case: UNCONFIRMED send seconds after capture -> must keep the token
        rs._conn_params = {"url": "wss://ws.fxg.jinritemai.com/ws/v2?token=fresh"}
        rs._conn_params_ts = time.time()  # just captured
        rs.invalidate()
        self.assertIsNotNone(rs._conn_params)  # preserved -> next send reuses, no re-capture

    def test_old_token_is_still_dropped(self):
        # genuinely old token (past the floor) -> invalidate still works as the stale safety net
        rs._conn_params = {"url": "wss://ws.fxg.jinritemai.com/ws/v2?token=old"}
        rs._conn_params_ts = time.time() - (rs._INVALIDATE_MIN_AGE_S + 50)
        rs.invalidate()
        self.assertIsNone(rs._conn_params)  # dropped -> next send re-captures fresh

    def test_killswitch_restores_old_behavior(self):
        import os
        old = os.environ.get("ECAN_FEIGE_WS_RAW_INVALIDATE_THROTTLE")
        try:
            os.environ["ECAN_FEIGE_WS_RAW_INVALIDATE_THROTTLE"] = "0"
            rs._conn_params = {"url": "wss://x?token=fresh"}
            rs._conn_params_ts = time.time()
            rs.invalidate()
            self.assertIsNone(rs._conn_params)  # throttle off -> always drops
        finally:
            if old is None:
                os.environ.pop("ECAN_FEIGE_WS_RAW_INVALIDATE_THROTTLE", None)
            else:
                os.environ["ECAN_FEIGE_WS_RAW_INVALIDATE_THROTTLE"] = old


class SingleFlightWiringTests(unittest.TestCase):
    def test_capture_is_single_flighted(self):
        self.assertIn("_capture_inflight", _SRC)
        self.assertIn("_settle_capture_inflight", _SRC)
        # single-flight awaits the in-flight future rather than re-evaluating
        self.assertIn("return await _inflight", _SRC)


if __name__ == "__main__":
    unittest.main()
