"""The site probe: generic core, site presets from bundles, secrets never written."""

import json
import tempfile
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension import site_probe as sp


class PresetTests(unittest.TestCase):
    def test_pdd_preset_comes_from_its_bundle(self):
        preset = sp.load_preset("pdd_chat")
        self.assertEqual(preset.name, "pdd_chat")
        self.assertTrue(preset.page("https://mms.pinduoduo.com/chat-merchant/index.html"))
        self.assertFalse(preset.page("https://im.jinritemai.com/pc_seller_v2/main/workspace"))
        self.assertTrue(preset.api("https://mms.pinduoduo.com/plateau/chat/list"))
        self.assertFalse(preset.api("https://mms.pinduoduo.com/static/app.js"))

    def test_the_core_names_no_site(self):
        src = Path(sp.__file__).read_text(encoding="utf-8")
        for site in ("pinduoduo", "jinritemai", "feige", "taobao"):
            self.assertNotIn(site, src.lower())


class RedactionTests(unittest.TestCase):
    def test_secret_headers_keep_only_their_length(self):
        out = sp._redact({"Cookie": "a=1; b=2", "User-Agent": "UA", "Authorization": "Bearer x"})
        self.assertEqual(out["User-Agent"], "UA")
        self.assertEqual(out["Cookie"], "<redacted 8 chars>")
        self.assertNotIn("Bearer", json.dumps(out))

    def test_token_like_query_values_are_redacted(self):
        url = sp.redact_url("wss://m-ws.example.com/?access_token=abc123&role=mall&sign=zz")
        self.assertNotIn("abc123", url)
        self.assertNotIn("sign=zz", url)
        self.assertIn("role=mall", url)


class SummaryTests(unittest.TestCase):
    def test_frames_are_grouped_by_socket_and_shape(self):
        lines = [
            {"kind": "ws_frame", "dir": "recv", "url": "wss://x/ws", "opcode": 1,
             "payload": json.dumps({"cmd": "new_msg", "uid": 1, "text": "hi"})},
            {"kind": "ws_frame", "dir": "recv", "url": "wss://x/ws", "opcode": 1,
             "payload": json.dumps({"cmd": "new_msg", "uid": 2, "text": "yo"})},
            {"kind": "ws_frame", "dir": "sent", "url": "wss://x/ws", "opcode": 2, "payload": "CAESA2FiYw=="},
            {"kind": "api", "method": "POST", "url": "https://x/api/list?t=1"},
        ]
        path = Path(tempfile.mkdtemp()) / "c.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in lines), encoding="utf-8")
        s = sp.summarize(str(path))
        sock = s["sockets"]["wss://x/ws"]
        self.assertEqual((sock["recv"], sock["sent"]), (2, 1))
        shapes = dict(sock["shapes"])
        self.assertEqual(shapes["recv json{cmd,text,uid} cmd=new_msg"], 2)
        self.assertIn("sent binary len~0 head=08011203", shapes)
        self.assertEqual(s["apis"], [("POST https://x/api/list", 1)])


class AppHandlerTests(unittest.TestCase):
    def test_pdd_is_offered_as_a_site(self):
        self.assertIn("pdd_chat", sp.available_sites())

    def test_recording_needs_an_open_login(self):
        from types import SimpleNamespace
        from unittest import mock
        from gui.ipc.w2p_handlers import site_probe_handler as h
        from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser
        req = SimpleNamespace(id="1", method="site_probe.start")
        with mock.patch.object(fingerprint_browser, "profile_status", return_value={"running": False}), \
             mock.patch.object(h, "create_error_response", side_effect=lambda r, code, msg: code):
            self.assertEqual(h.handle_start(req, {"profile_id": "x", "site": "pdd_chat"}), "NOT_RUNNING")

    def test_captures_land_in_app_data_runlogs(self):
        self.assertTrue(sp.default_out_dir().replace("\\", "/").endswith("runlogs/probe"))


if __name__ == "__main__":
    unittest.main()
