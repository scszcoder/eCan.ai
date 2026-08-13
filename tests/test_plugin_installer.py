"""
Tests for plugin_installer — local install / uninstall flows.
"""

from __future__ import annotations

import io
import json
import os
import sys
import textwrap
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension import (
    plugin_installer as pi,
    plugin_registry as pr,
    plugin_dependents as pd,
)


_GOOD_MANIFEST = textwrap.dedent(
    """\
    api_version: 1
    kind: hook_bundle
    bundle: {name}
    version: {version}
    author: "tester"
    description: "test bundle"
    hooks:
      - name: demo_hook
        entrypoint: "hooks.py:DemoHook"
        stage: on_event_normalized
        tier: 1
        priority: 50
    """
)

_HOOKS_PY = (
    "class DemoHook:\n"
    "    def __init__(self, config=None, manifest=None): pass\n"
    "    async def run(self, ctx, payload): return None\n"
)


def _write_bundle_dir(root: Path, name: str = "demo_bundle", version: str = "1.0.0") -> Path:
    bd = root / name
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "hook.yaml").write_text(
        _GOOD_MANIFEST.format(name=name, version=version), encoding="utf-8"
    )
    (bd / "hooks.py").write_text(_HOOKS_PY, encoding="utf-8")
    return bd


def _make_zip_from_dir(src_dir: Path, zip_path: Path, *, wrap_in_top_dir: bool = True) -> Path:
    """Build a zip from src_dir. If wrap_in_top_dir, archive paths start with src_dir.name/."""
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src_dir):
            for fn in files:
                p = Path(root) / fn
                rel = p.relative_to(src_dir.parent if wrap_in_top_dir else src_dir)
                zf.write(p, arcname=str(rel))
    return zip_path


class PluginInstallerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._appdata.mkdir(parents=True, exist_ok=True)
        self._workspace = Path(self._tmp.name) / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)

        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata)
        )
        self._envi_patcher.start()

        # Patch dependents to return nothing by default; individual tests
        # that exercise the dependents-block path override this.
        self._dep_patcher = patch.object(pd, "find_dependents", return_value=[])
        self._dep_patcher.start()

    def tearDown(self):
        self._dep_patcher.stop()
        self._envi_patcher.stop()
        self._tmp.cleanup()

    # ----- install from dir -----
    def test_install_from_dir_happy_path(self):
        src = _write_bundle_dir(self._workspace)
        result = pi.install_from_dir(src)

        self.assertEqual(result.name, "demo_bundle")
        self.assertEqual(result.version, "1.0.0")
        self.assertEqual(result.install_source, "local")
        self.assertEqual(result.kind, "hook_bundle")

        installed = Path(result.install_path)
        self.assertTrue(installed.is_dir())
        self.assertTrue((installed / "hook.yaml").is_file())
        self.assertTrue((installed / "hooks.py").is_file())

        entry = pr.get("demo_bundle")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.install_source, "local")
        self.assertTrue(entry.enabled)

    def test_install_from_dir_rejects_missing_source(self):
        with self.assertRaises(pi.PluginInstallerError):
            pi.install_from_dir(self._workspace / "nope")

    def test_install_from_dir_rejects_copy_false(self):
        src = _write_bundle_dir(self._workspace)
        with self.assertRaises(pi.PluginInstallerError):
            pi.install_from_dir(src, copy=False)

    def test_reinstall_overwrites_previous_version(self):
        src = _write_bundle_dir(self._workspace, version="1.0.0")
        first = pi.install_from_dir(src)
        # Replace source with a newer version and reinstall.
        (Path(first.install_path).parent / "demo_bundle_workspace_unused").mkdir(exist_ok=True)
        _write_bundle_dir(self._workspace, version="2.0.0")
        second = pi.install_from_dir(src)
        self.assertEqual(second.version, "2.0.0")
        self.assertEqual(pr.get("demo_bundle").version, "2.0.0")
        # No backup left behind.
        leftovers = list(pr.plugins_dir().glob("demo_bundle.bak.*"))
        self.assertEqual(leftovers, [])

    # ----- manifest validation -----
    def test_install_rejects_missing_bundle_field(self):
        bd = self._workspace / "broken"
        bd.mkdir()
        (bd / "hook.yaml").write_text("api_version: 1\nhooks: []\n", encoding="utf-8")
        with self.assertRaises(pi.InvalidBundleError):
            pi.install_from_dir(bd)

    def test_install_rejects_empty_hooks(self):
        bd = self._workspace / "empty_hooks"
        bd.mkdir()
        (bd / "hook.yaml").write_text(
            "api_version: 1\nbundle: empty_hooks\nversion: 1.0\nhooks: []\n",
            encoding="utf-8",
        )
        with self.assertRaises(pi.InvalidBundleError):
            pi.install_from_dir(bd)

    def test_install_rejects_tier_zero(self):
        bd = self._workspace / "tier0"
        bd.mkdir()
        (bd / "hook.yaml").write_text(textwrap.dedent("""\
            api_version: 1
            bundle: tier0
            version: 1.0
            hooks:
              - name: bad
                entrypoint: "hooks.py:Bad"
                stage: on_event_normalized
                tier: 0
                priority: 50
            """), encoding="utf-8")
        with self.assertRaises(pi.InvalidBundleError):
            pi.install_from_dir(bd)

    def test_install_rejects_invalid_bundle_name(self):
        bd = self._workspace / "bad name"
        bd.mkdir()
        (bd / "hook.yaml").write_text(textwrap.dedent("""\
            api_version: 1
            bundle: "bad name with spaces"
            version: 1.0
            hooks:
              - name: x
                entrypoint: "hooks.py:X"
                stage: on_event_normalized
                tier: 1
                priority: 50
            """), encoding="utf-8")
        with self.assertRaises(pi.InvalidBundleError):
            pi.install_from_dir(bd)

    # ----- install from zip -----
    def test_install_from_zip_with_top_dir(self):
        src = _write_bundle_dir(self._workspace)
        zp = self._workspace / "bundle.zip"
        _make_zip_from_dir(src, zp, wrap_in_top_dir=True)

        result = pi.install_from_zip(zp)
        self.assertEqual(result.name, "demo_bundle")
        self.assertTrue(Path(result.install_path).is_dir())

    def test_install_from_zip_with_bundle_at_root(self):
        src = _write_bundle_dir(self._workspace)
        zp = self._workspace / "bundle.zip"
        _make_zip_from_dir(src, zp, wrap_in_top_dir=False)

        result = pi.install_from_zip(zp)
        self.assertEqual(result.name, "demo_bundle")

    def test_install_from_zip_rejects_non_zip(self):
        text = self._workspace / "not_a_zip.txt"
        text.write_text("hello", encoding="utf-8")
        with self.assertRaises(pi.PluginInstallerError):
            pi.install_from_zip(text)

    def test_install_from_zip_rejects_path_traversal(self):
        zp = self._workspace / "evil.zip"
        with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../escape.txt", "boom")
        with self.assertRaises(pi.PluginInstallerError):
            pi.install_from_zip(zp)

    # ----- uninstall -----
    def test_uninstall_happy_path(self):
        src = _write_bundle_dir(self._workspace)
        result = pi.install_from_dir(src)
        self.assertTrue(Path(result.install_path).is_dir())

        pi.uninstall("demo_bundle")
        self.assertFalse(Path(result.install_path).exists())
        self.assertIsNone(pr.get("demo_bundle"))

    def test_uninstall_unknown_raises(self):
        with self.assertRaises(pi.PluginInstallerError):
            pi.uninstall("nonexistent")

    def test_uninstall_blocked_by_dependents(self):
        src = _write_bundle_dir(self._workspace)
        pi.install_from_dir(src)

        fake_dep = pd.Dependent(
            skill_id="s1", skill_name="alpha", skill_path="/x",
            node_id="n1", node_name="BA",
        )
        with patch.object(pd, "find_dependents", return_value=[fake_dep]):
            with self.assertRaises(pi.DependentsBlockedError) as ctx:
                pi.uninstall("demo_bundle")
            self.assertEqual(len(ctx.exception.dependents), 1)

        # Registry row should still be intact.
        self.assertIsNotNone(pr.get("demo_bundle"))

    def test_uninstall_force_overrides_dependents(self):
        src = _write_bundle_dir(self._workspace)
        pi.install_from_dir(src)
        fake_dep = pd.Dependent(
            skill_id="s1", skill_name="alpha", skill_path="/x",
            node_id="n1", node_name="BA",
        )
        with patch.object(pd, "find_dependents", return_value=[fake_dep]):
            pi.uninstall("demo_bundle", force=True)
        self.assertIsNone(pr.get("demo_bundle"))


if __name__ == "__main__":
    unittest.main()
