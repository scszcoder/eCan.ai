"""A chromium install dir with no runnable browser binary must NOT validate.

Field bug (2026-09): a corrupt first-run copy left chromium-<build> as a tree of
empty dirs with no chrome.exe, yet validate_browser_installation returned True
(it trusted browsers.json / folder presence). copy_playwright_browsers then
skipped the re-copy forever, so chrome.exe never came back and the fingerprint
front desk could not launch. The validator must require the actual binary.
"""

import tempfile
import unittest
from pathlib import Path

from agent.playwright.core.utils import PlaywrightCoreUtils as P


def _root() -> Path:
    return Path(tempfile.mkdtemp()) / "ms-playwright"


class ValidateBrowserInstallationTests(unittest.TestCase):
    def test_chromium_with_runnable_binary_validates(self):
        root = _root()
        exe = root / "chromium-1181" / "chrome-win" / "chrome.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"MZ")  # non-empty
        (root / "browsers.json").write_text("{}", encoding="utf-8")
        self.assertTrue(P.validate_browser_installation(root))

    def test_chromium_dir_without_chrome_exe_fails_even_with_browsers_json(self):
        # The exact corruption: the build dir and its subfolders exist, but the
        # browser binary is gone. browsers.json must not rescue it.
        root = _root()
        (root / "chromium-1181" / "chrome-win").mkdir(parents=True)
        (root / "chromium-1181" / "locales").mkdir(parents=True)
        (root / "browsers.json").write_text("{}", encoding="utf-8")
        self.assertFalse(P.validate_browser_installation(root))

    def test_zero_byte_chrome_exe_fails(self):
        root = _root()
        exe = root / "chromium-1181" / "chrome-win" / "chrome.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")  # empty -> not runnable
        self.assertFalse(P.validate_browser_installation(root))

    def test_chrome_exe_created_as_a_directory_fails(self):
        # The copy turned files into empty dirs; a chrome.exe *directory* is not
        # a runnable binary.
        root = _root()
        (root / "chromium-1181" / "chrome-win" / "chrome.exe").mkdir(parents=True)
        self.assertFalse(P.validate_browser_installation(root))


if __name__ == "__main__":
    unittest.main()
