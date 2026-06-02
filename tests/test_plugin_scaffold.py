"""Tests for plugin_scaffold CLI."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension import plugin_scaffold


class PluginScaffoldTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._dest = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scaffold_creates_expected_files(self):
        out = plugin_scaffold.scaffold("my_plug", self._dest)
        self.assertTrue(out.is_dir())
        self.assertTrue((out / "hook.yaml").is_file())
        self.assertTrue((out / "hooks.py").is_file())
        self.assertTrue((out / "README.md").is_file())
        self.assertTrue((out / "tests" / "test_my_plug.py").is_file())
        self.assertTrue((out / "gui" / "bridge.js").is_file())
        self.assertTrue((out / "gui" / "config.html").is_file())
        self.assertTrue((out / "gui" / "node.html").is_file())
        self.assertTrue((out / "gui" / "status.html").is_file())
        self.assertTrue((out / "gui" / "theme.css").is_file())

    def test_manifest_substitutes_bundle_name(self):
        out = plugin_scaffold.scaffold("acme_chat", self._dest)
        manifest = (out / "hook.yaml").read_text(encoding="utf-8")
        self.assertIn("bundle: acme_chat", manifest)
        self.assertIn("storage_namespace: acme_chat", manifest)

    def test_scaffolded_manifest_validates(self):
        out = plugin_scaffold.scaffold("xyz", self._dest)
        # Use the same loader we use in production to ensure the
        # manifest passes Pydantic validation end-to-end.
        from agent.ec_skills.browser_use_extension.hook_loader import _read_manifest_file
        data = _read_manifest_file(out)
        self.assertEqual(data["bundle"], "xyz")
        self.assertGreater(len(data["hooks"]), 0)

    def test_refuses_to_overwrite_existing(self):
        plugin_scaffold.scaffold("dup", self._dest)
        with self.assertRaises(SystemExit):
            plugin_scaffold.scaffold("dup", self._dest)

    def test_rejects_invalid_name(self):
        with self.assertRaises(SystemExit):
            plugin_scaffold.scaffold("bad name", self._dest)
        with self.assertRaises(SystemExit):
            plugin_scaffold.scaffold("1starts-with-digit", self._dest)


if __name__ == "__main__":
    unittest.main()
