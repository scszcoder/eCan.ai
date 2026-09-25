"""A WeChat login shows the user's WeChat nickname, never the internal wechat_<openid>."""

import json
import unittest
from types import SimpleNamespace


class DialogCaptureTests(unittest.TestCase):
    def _capture(self, stored):
        from gui.auth.wechat_login_dialog import WechatLoginDialog
        got = {}
        fake = SimpleNamespace(_resolved=False, _resolve=lambda r: got.update(r or {}))
        WechatLoginDialog._on_storage_read(fake, json.dumps(stored))
        return got

    def test_nickname_and_avatar_are_passed_through(self):
        got = self._capture({"token": "t", "username": "wechat_o3Y", "auth": "true",
                             "nickname": "小明", "avatarUrl": "https://x/a.png"})
        self.assertEqual((got["nickname"], got["avatarUrl"]), ("小明", "https://x/a.png"))

    def test_an_older_callback_without_them_still_logs_in(self):
        got = self._capture({"token": "t", "username": "wechat_o3Y", "auth": "true"})
        self.assertEqual(got["token"], "t")
        self.assertEqual((got["nickname"], got["avatarUrl"]), ("", ""))

    def test_the_page_is_asked_for_both(self):
        from gui.auth.wechat_login_dialog import _READ_STORAGE_JS
        self.assertIn("nickname", _READ_STORAGE_JS)
        self.assertIn("avatarUrl", _READ_STORAGE_JS)


class HeaderTests(unittest.TestCase):
    def test_the_header_never_shows_an_openid(self):
        from pathlib import Path
        src = Path("gui_v2/src/components/Layout/AppHeader.tsx").read_text(encoding="utf-8")
        self.assertIn("!s.startsWith('wechat_')", src)
        self.assertIn("common.wechat_user", src)


if __name__ == "__main__":
    unittest.main()
