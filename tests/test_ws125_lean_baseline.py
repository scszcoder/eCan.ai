"""ws125 — ECAN_FEIGE_LEAN_BASELINE master switch (the regression A/B).

ws095 (fastest, no stall at 1-vs-6) had NONE of the post-ws095 MAIN-TAB recovery /
backstop machinery (ws103/104/107/108/110). The good-vs-bad log compare proved it:
identical env, but ws095 emitted 0 ws108-backstop scans / 1 coldstart line vs ws124's
171 / 344. This switch lets a later build run the lean ws095 hot path so the customer
can A/B-confirm that machinery is the stall source. Default OFF.
"""
from __future__ import annotations

import os
import unittest
from pathlib import Path

_EM = Path("agent/ec_skills/browser_use_extension/event_monitor.py").read_text(encoding="utf-8")


class LeanGateWiringTests(unittest.TestCase):
    def test_master_switch_defined_and_wired_at_all_group_b_sites(self):
        self.assertIn("def _feige_lean_baseline()", _EM)
        self.assertIn('ECAN_FEIGE_LEAN_BASELINE', _EM)
        # cold-start recovery short-circuits under lean
        cs = _EM.find("def _coldstart_recovery_active()")
        self.assertGreater(cs, 0)
        self.assertIn("if _feige_lean_baseline():", _EM[cs:cs + 200])
        # ws108 backstop disabled under lean (interval -> inf)
        self.assertIn('_bs_iv = float("inf")', _EM)
        # both stuck-recovery sites consult the switch (negative form)
        self.assertGreaterEqual(_EM.count("not _feige_lean_baseline()"), 2)
        # plus the two positive-form gates (cold-start return + backstop interval)
        self.assertGreaterEqual(_EM.count("if _feige_lean_baseline():"), 2)


class LeanGateBehaviourTests(unittest.TestCase):
    def test_coldstart_recovery_off_under_lean(self):
        try:
            from agent.ec_skills.browser_use_extension.event_monitor import (
                _coldstart_recovery_active, _feige_lean_baseline,
            )
        except Exception as e:
            self.skipTest(f"event_monitor import unavailable: {e}")
        old_lean = os.environ.get("ECAN_FEIGE_LEAN_BASELINE")
        old_cs = os.environ.get("ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE")
        try:
            os.environ["ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE"] = "1"  # would normally enable
            os.environ["ECAN_FEIGE_LEAN_BASELINE"] = "1"             # ...but lean overrides
            self.assertTrue(_feige_lean_baseline())
            self.assertFalse(_coldstart_recovery_active())
            os.environ["ECAN_FEIGE_LEAN_BASELINE"] = ""              # lean off -> recovery active
            self.assertTrue(_coldstart_recovery_active())
        finally:
            for k, v in (("ECAN_FEIGE_LEAN_BASELINE", old_lean),
                         ("ECAN_FEIGE_COLDSTART_RECOVERY_SCRAPE", old_cs)):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


if __name__ == "__main__":
    unittest.main()
