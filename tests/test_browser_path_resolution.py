"""A configured browser path that is a folder, or carries flags, must not reach CreateProcess."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb


class BrowserPathTests(unittest.TestCase):
    def setUp(self):
        self.app_dir = Path(tempfile.mkdtemp()) / "Application"
        self.app_dir.mkdir()
        self.exe = self.app_dir / "chrome.exe"
        self.exe.write_bytes(b"")

    def test_a_folder_in_the_env_var_resolves_to_the_browser_inside(self):
        # The customer's setting: ECAN_CHROMIUM_PATH=...\Chrome\Application
        with mock.patch.dict(os.environ, {"ECAN_CHROMIUM_PATH": str(self.app_dir)}):
            self.assertEqual(fb.resolve_browser_path({}), str(self.exe))

    def test_a_path_with_flags_is_not_launched_as_is(self):
        flagged = f'{self.exe} --remote-debugging-port=9228 --user-data-dir="C:\chrome_data"'
        with mock.patch.dict(os.environ, {"ECAN_CHROMIUM_PATH": str(self.exe)}):
            got = fb.resolve_browser_path({"browser": {"path": flagged}})
        self.assertEqual(got, str(self.exe), "falls through to the next valid source")

    def test_a_plain_exe_path_still_wins(self):
        self.assertEqual(fb.resolve_browser_path({"browser": {"path": str(self.exe)}}), str(self.exe))

    def test_playwright_browsers_path_env_is_searched(self):
        # eCan installs its Chromium under its own app-data dir and points
        # Playwright at it via PLAYWRIGHT_BROWSERS_PATH. A fingerprint profile
        # with no recorded binary must still find it there, not only in
        # Playwright's default location.
        root = Path(tempfile.mkdtemp()) / "ms-playwright"
        chrome = root / "chromium-1148" / "chrome-win" / "chrome.exe"
        chrome.parent.mkdir(parents=True)
        chrome.write_bytes(b"")
        with mock.patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(root)}):
            os.environ.pop("ECAN_CHROMIUM_PATH", None)
            self.assertEqual(fb.resolve_browser_path({}), str(chrome))

    def test_newest_chromium_build_wins(self):
        root = Path(tempfile.mkdtemp()) / "ms-playwright"
        for build in ("chromium-1100", "chromium-1148"):
            exe = root / build / "chrome-win" / "chrome.exe"
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
        with mock.patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(root)}):
            os.environ.pop("ECAN_CHROMIUM_PATH", None)
            got = fb.resolve_browser_path({})
        self.assertEqual(got, str(root / "chromium-1148" / "chrome-win" / "chrome.exe"))


if __name__ == "__main__":
    unittest.main()
