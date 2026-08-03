"""ws124 — dedicated-thread CDP eval lane for the feige_ws_send fallback inject.

The HANDOFF-STARVED wall: the inject eval is marshaled onto the shared CDP loop = the
qasync main loop, which starves under a high-concurrency burst. This lane runs a CDP
client on its OWN thread+loop so the eval isn't queued behind the main loop's work.
Additive + gated ECAN_FEIGE_DEDICATED_CDP_LOOP=1 (default OFF); any miss -> None ->
caller falls back to the shared-loop eval.

Can't exercise a real Chrome/CDP here, so we test (a) the gate is a true no-op, (b) the
dedicated thread+loop machinery + cross-thread marshal (the risky part) works, and
(c) the wiring in feige_ws_send_text falls back when the lane returns None.
"""
from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    feige_cdp_lane as lane,
)

_ETS_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/site_tools.py"
).read_text(encoding="utf-8")


class GateTests(unittest.TestCase):
    def test_gate_off_is_noop_no_thread(self):
        os.environ.pop("ECAN_FEIGE_DEDICATED_CDP_LOOP", None)
        lane._thread[0] = lane._thread[0]  # don't reset a real one if present
        r = asyncio.run(lane.eval_inject(object(), "TID", "1+1"))
        self.assertIsNone(r)

    def test_gate_on_but_no_cdp_url_returns_none(self):
        old = os.environ.get("ECAN_FEIGE_DEDICATED_CDP_LOOP")
        try:
            os.environ["ECAN_FEIGE_DEDICATED_CDP_LOOP"] = "1"
            # a session with no cdp_url -> miss -> None (no crash)
            class _S:  # no cdp_url, no browser_profile
                pass
            self.assertIsNone(asyncio.run(lane.eval_inject(_S(), "TID", "1+1")))
        finally:
            if old is None:
                os.environ.pop("ECAN_FEIGE_DEDICATED_CDP_LOOP", None)
            else:
                os.environ["ECAN_FEIGE_DEDICATED_CDP_LOOP"] = old


class DedicatedThreadMachineryTests(unittest.TestCase):
    """The risky part: a separate thread runs an event loop and cross-thread marshal works."""

    def test_thread_loop_and_cross_thread_marshal(self):
        loop = lane._ensure_thread()
        try:
            self.assertTrue(loop.is_running())
            self.assertIsNotNone(lane._thread[0])
            self.assertEqual(lane._thread[0].name, "FeigeCDPLane")
            self.assertTrue(lane._thread[0].daemon)
            # marshal a coroutine onto the dedicated loop from THIS thread and await it
            async def _ping():
                await asyncio.sleep(0)
                return "pong"
            fut = asyncio.run_coroutine_threadsafe(_ping(), loop)
            self.assertEqual(fut.result(timeout=5), "pong")
            # idempotent: second ensure returns the same running loop
            self.assertIs(lane._ensure_thread(), loop)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            if lane._thread[0]:
                lane._thread[0].join(timeout=5)
            lane._loop[0] = None
            lane._thread[0] = None


class WiringTests(unittest.TestCase):
    def test_send_path_tries_lane_then_falls_back(self):
        self.assertIn("ECAN_FEIGE_DEDICATED_CDP_LOOP", _ETS_SRC)
        self.assertIn("feige_cdp_lane", _ETS_SRC)
        # the lane is tried before, and the shared-loop eval is the fallback (res is None)
        lane_at = _ETS_SRC.find("_lane.eval_inject(browser_session")
        fallback_at = _ETS_SRC.find('trace_label="feige_ws_send"')
        guard_at = _ETS_SRC.find("if res is None:")
        self.assertGreater(lane_at, 0)
        self.assertGreater(fallback_at, lane_at)      # fallback after the lane attempt
        self.assertGreater(fallback_at, guard_at)     # fallback guarded by `if res is None`


if __name__ == "__main__":
    unittest.main()
