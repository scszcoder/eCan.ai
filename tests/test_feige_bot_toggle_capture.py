"""ws119 — bot-toggle capture: passive sniffer for the 智能客服 enable/disable XHR.

The 智能客服 on/off is an authenticated HTTP config mutation (NOT a chat-WS
frame — the Frontier socket carries only chat). Rather than driving the fragile
multi-dialog DOM toggle (关闭 -> retention modal -> reason -> 仍要停用; 开启 ->
欢迎回来 modal -> 跳过该步), we capture the one XHR the settings SPA fires so the
on/off steps can become a single fetch(). Gated ECAN_FEIGE_BOT_TOGGLE_CAPTURE=1,
default OFF, marker [FEIGE-BOT-TOGGLE-CAP].
"""
from __future__ import annotations

import asyncio
import os
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    feige_bot_control as bc,
)

_EM_SRC = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")


class GateTests(unittest.TestCase):
    def test_capture_is_noop_when_gated_off(self):
        old = os.environ.get("ECAN_FEIGE_BOT_TOGGLE_CAPTURE")
        try:
            os.environ.pop("ECAN_FEIGE_BOT_TOGGLE_CAPTURE", None)
            bc._TOGGLE_CAP_STARTED[0] = False
            asyncio.run(bc.start_bot_toggle_capture())  # must not raise / start
            self.assertFalse(bc._TOGGLE_CAP_STARTED[0])
            self.assertIsNone(bc._TOGGLE_CAP_CLIENT[0])
        finally:
            if old is None:
                os.environ.pop("ECAN_FEIGE_BOT_TOGGLE_CAPTURE", None)
            else:
                os.environ["ECAN_FEIGE_BOT_TOGGLE_CAPTURE"] = old


class WiringTests(unittest.TestCase):
    def test_starter_wired_into_tick_driver(self):
        self.assertIn("start_bot_toggle_capture", _EM_SRC)
        self.assertIn("ECAN_FEIGE_BOT_TOGGLE_CAPTURE", _EM_SRC)

    def test_marker_and_request_response_handlers_present(self):
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
            "feige_bot_control.py"
        ).read_text(encoding="utf-8")
        self.assertIn("[FEIGE-BOT-TOGGLE-CAP]", src)
        # captures BOTH the request (endpoint/payload) and the response body
        self.assertIn("Network.requestWillBeSent", src)
        self.assertIn("Network.getResponseBody", src)


if __name__ == "__main__":
    unittest.main()
