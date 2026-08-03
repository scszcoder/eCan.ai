"""ws114 — Feige-own-bot suppressor scaffolding.

Periodically toggles Feige's built-in 智能客服 bot ON->OFF (parallel to the DOM
monitor) so it stays suppressed while our agents work. The CDP/DOM toggle steps
are placeholders for now; these tests guard the gate + the monitor wiring.
"""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    feige_bot_control as bot,
)

_MON_SRC = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")


class SuppressorGateTests(unittest.TestCase):
    def test_tick_is_noop_when_gate_off(self):
        # Default (env unset) -> tick returns immediately without resolving a session.
        asyncio.run(bot.suppress_feige_bot_tick())  # must not raise

    def test_placeholders_are_callable_and_return_false(self):
        self.assertFalse(asyncio.run(bot.turn_on_feige_bot(None, "tid")))
        self.assertFalse(asyncio.run(bot.turn_off_feige_bot(None, "tid")))


class SuppressorWiringTests(unittest.TestCase):
    def test_monitor_fires_the_tick_on_a_throttle(self):
        # The suppressor must be wired into the periodic DOM-monitor tick, gated,
        # with its own throttle interval — mirroring the cold-start scan.
        self.assertIn("ECAN_LIVE_CHAT_BOT_SUPPRESS", _MON_SRC)
        self.assertIn("ECAN_LIVE_CHAT_BOT_SUPPRESS_INTERVAL_S", _MON_SRC)
        self.assertIn("suppress_bot_tick", _MON_SRC)
        self.assertIn("_LIVE_CHAT_BOT_TOGGLE_LAST", _MON_SRC)

    def test_default_off(self):
        # Gate is opt-in (== "1"), so a default build does not run the placeholders.
        self.assertIn('(_live_chat_env("ECAN_LIVE_CHAT_BOT_SUPPRESS") or "") == "1"', _MON_SRC)


if __name__ == "__main__":
    unittest.main()
