"""ws119/120/121 — bot-toggle capture + the real on/off API it revealed.

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
from unittest import mock

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    feige_bot_control as bc,
)

_BC_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
    "feige_bot_control.py"
).read_text(encoding="utf-8")

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
        self.assertIn("ECAN_LIVE_CHAT_BOT_TOGGLE_CAPTURE", _EM_SRC)

    def test_marker_and_request_response_handlers_present(self):
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
            "feige_bot_control.py"
        ).read_text(encoding="utf-8")
        self.assertIn("[FEIGE-BOT-TOGGLE-CAP]", src)
        # captures BOTH the request (endpoint/payload) and the response body
        self.assertIn("Network.requestWillBeSent", src)
        self.assertIn("Network.getResponseBody", src)

    def test_ws120_body_fetch_is_off_pump(self):
        # ws120: the loadingFinished handler must NOT await send_raw inline (that
        # deadlocks cdp_use's single read loop — the ws119 0-RESP bug). It must
        # schedule the body fetch as a detached task instead.
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/"
            "feige_bot_control.py"
        ).read_text(encoding="utf-8")
        self.assertIn("asyncio.create_task(_fetch_body", src)
        self.assertIn("_TOGGLE_CAP_TASKS", src)
        # _on_done itself is a plain (sync) handler that returns immediately
        self.assertIn("def _on_done(params, session_id=None):", src)
        self.assertNotIn("async def _on_done", src)


class Ws121ToggleApiTests(unittest.TestCase):
    """ws121: turn_on/off are real intelligence_robot API calls, not placeholders."""

    def test_no_longer_placeholders(self):
        self.assertNotIn("PLACEHOLDER", _BC_SRC)
        # the captured endpoints + payloads are wired in
        self.assertIn("intelligence_robot/close", _BC_SRC)
        self.assertIn("intelligence_robot/open", _BC_SRC)
        self.assertIn("intelligence_robot/"  # status read
                      "status", _BC_SRC)
        self.assertIn('"close_type": 1', _BC_SRC)
        self.assertIn('"open_scenes"', _BC_SRC)
        # in-page XHR path (so secsdk attaches x-secsdk-csrf-token)
        self.assertIn("XMLHttpRequest", _BC_SRC)
        self.assertIn("withCredentials=true", _BC_SRC)

    def _canned(self, status_open):
        async def fake(bs, tid, method, url, body):
            if method == "GET" and "status" in url:
                return {"ok": True, "status": 200, "code": 0,
                        "data": {"open_status": status_open}}
            return {"ok": True, "status": 200, "code": 0, "data": None}
        return fake

    def test_status_and_toggles(self):
        async def go():
            with mock.patch.object(bc, "_bot_api_call", side_effect=self._canned(1)):
                self.assertEqual(await bc.get_bot_status(None, None), 1)
                self.assertTrue(await bc.turn_off_feige_bot(None, None))
                self.assertTrue(await bc.turn_on_feige_bot(None, None))
        asyncio.run(go())

    def test_toggle_returns_false_on_nonzero_code(self):
        async def fake(bs, tid, method, url, body):
            return {"ok": True, "status": 200, "code": 4000003, "data": None}
        async def go():
            with mock.patch.object(bc, "_bot_api_call", side_effect=fake):
                self.assertFalse(await bc.turn_off_feige_bot(None, None))
        asyncio.run(go())

    def test_ws122_no_double_json_parse(self):
        # ws122 regression: _evaluate_js auto-json.loads() a string JS result, so it
        # hands back a DICT. _bot_api_call must NOT json.loads() again. The ws121
        # live bug: double-parse -> TypeError -> None -> get_bot_status None -> the
        # tick logged "status=None" forever and never closed an actually-open bot.
        import agent.ec_skills.browser_use_extension.extension_tools_service as ets

        async def fake_eval(bs, expr, **kw):
            # mimic _evaluate_js: it returns the ALREADY-parsed dict
            return {"ok": True, "status": 200, "code": 0, "data": {"open_status": 1}}

        async def go():
            with mock.patch.object(ets, "_evaluate_js", side_effect=fake_eval):
                self.assertEqual(await bc.get_bot_status(None, "tid"), 1)
                self.assertTrue(await bc.turn_off_feige_bot(None, "tid"))
        asyncio.run(go())
        # and the source must not re-parse a dict
        self.assertIn("isinstance(raw, dict)", _BC_SRC)

    def test_tick_is_ensure_off_not_blind_toggle(self):
        # ws121: tick reads status and only closes when ON — never blind on->off.
        self.assertIn("status = await get_bot_status", _BC_SRC)
        self.assertIn("if status == 1:", _BC_SRC)
        self.assertIn("await turn_off_feige_bot", _BC_SRC)
        # the old blind on->off pairing is gone
        self.assertNotIn("placeholder on->off", _BC_SRC)


if __name__ == "__main__":
    unittest.main()
