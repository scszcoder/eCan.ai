"""The spec that packs third_party/ms-playwright must give PyInstaller a target
DIRECTORY for each file, not the full file path.

Field bug (shipped installer): the generator passed the file's full relpath as
the datas dest. PyInstaller appends basename(src) to the dest, so every file
landed at "<name>/<name>" — chrome.exe became a directory, chrome.dll/chrome.exe
went missing, and the whole ms-playwright tree shipped as empty dirs. The
fingerprint browser then could not launch ("no Chromium binary found").
"""

import os
import tempfile
import unittest
from pathlib import Path

from PyInstaller.building.utils import format_binaries_and_datas


class PyInstallerDestContractTests(unittest.TestCase):
    """Pin the behaviour the generator must respect."""

    def setUp(self):
        root = Path(tempfile.mkdtemp())
        self.src = root / "chromium-1181" / "chrome-win" / "chrome.exe"
        self.src.parent.mkdir(parents=True)
        self.src.write_bytes(b"MZ")
        self.pw_root = root  # stands in for third_party/ms-playwright source

    def _targets(self, dest):
        toc = format_binaries_and_datas([(str(self.src), dest)])
        return {os.path.normpath(t) for t, _ in toc}

    def test_full_path_dest_nests_the_file_the_shipped_bug(self):
        rel = os.path.relpath(self.src, self.pw_root)  # chromium-1181/chrome-win/chrome.exe
        bad_dest = os.path.join("third_party/ms-playwright", rel)  # includes filename
        targets = self._targets(bad_dest)
        nested = os.path.normpath("third_party/ms-playwright/chromium-1181/chrome-win/chrome.exe/chrome.exe")
        self.assertIn(nested, targets, "full-path dest nests the file (the bug)")

    def test_dirname_dest_places_the_file_correctly(self):
        rel = os.path.relpath(self.src, self.pw_root)
        good_dest = os.path.join("third_party/ms-playwright", os.path.dirname(rel))  # directory only
        targets = self._targets(good_dest)
        want = os.path.normpath("third_party/ms-playwright/chromium-1181/chrome-win/chrome.exe")
        self.assertIn(want, targets)
        # and it must NOT be nested
        bad = os.path.normpath("third_party/ms-playwright/chromium-1181/chrome-win/chrome.exe/chrome.exe")
        self.assertNotIn(bad, targets)


class GeneratorTemplateRegressionTests(unittest.TestCase):
    """Guard the actual spec generator source against reintroducing the bug."""

    def test_minibuild_uses_dirname_for_third_party_dests(self):
        src = (Path(__file__).resolve().parents[2]
               / "build_system" / "minibuild_core.py").read_text(encoding="utf-8")
        # The nesting form must be gone for both third_party trees.
        self.assertNotIn("os.path.join('third_party/ms-playwright', rel_path)", src)
        self.assertNotIn("os.path.join('third_party/browser_extensions', rel_path)", src)
        # And the directory form must be present.
        self.assertIn(
            "os.path.join('third_party/ms-playwright', os.path.dirname(rel_path))", src
        )


if __name__ == "__main__":
    unittest.main()
