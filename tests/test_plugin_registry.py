"""
Tests for plugin_registry — per-user installed-plugin state.
"""

from __future__ import annotations

import json
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension import plugin_registry as pr


def _write_minimal_bundle(parent_dir: Path, name: str = "demo_bundle", kind: str = "hook_bundle") -> Path:
    bundle_dir = parent_dir / name
    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = textwrap.dedent(
        f"""\
        api_version: 1
        kind: {kind}
        bundle: {name}
        version: 0.0.1
        author: "test"
        description: "minimal test bundle"
        hooks:
          - name: demo_hook
            entrypoint: "hooks.py:DemoHook"
            stage: on_event_normalized
            tier: 1
            priority: 50
        """
    )
    (bundle_dir / "hook.yaml").write_text(manifest, encoding="utf-8")
    (bundle_dir / "hooks.py").write_text(
        "class DemoHook:\n"
        "    def __init__(self, config=None, manifest=None): pass\n"
        "    async def run(self, ctx, payload): return None\n",
        encoding="utf-8",
    )
    return bundle_dir


class PluginRegistryTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._appdata.mkdir(parents=True, exist_ok=True)

        # Patch getECBotDataHome so plugins_dir() points into the tmp dir.
        self._patcher = patch("config.envi.getECBotDataHome", return_value=str(self._appdata))
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    # ----- basics -----
    def test_empty_registry_when_file_missing(self):
        self.assertEqual(pr.load_registry(), {})
        self.assertEqual(pr.list_installed(), [])

    def test_save_and_load_round_trip(self):
        pr.record_install(
            "alpha",
            version="1.2.3",
            install_source="local",
            install_path="/some/path",
            kind="hook_bundle",
        )
        reg = pr.load_registry()
        self.assertIn("alpha", reg)
        self.assertEqual(reg["alpha"].version, "1.2.3")
        self.assertEqual(reg["alpha"].install_source, "local")
        self.assertTrue(reg["alpha"].enabled)

    def test_registry_json_is_pretty_and_sorted(self):
        pr.record_install("zeta", version="1.0", install_source="local", install_path="/p1")
        pr.record_install("alpha", version="1.0", install_source="local", install_path="/p2")
        text = pr.registry_path().read_text(encoding="utf-8")
        data = json.loads(text)
        self.assertEqual(list(data.keys()), ["alpha", "zeta"])  # sort_keys=True

    def test_persisted_payload_excludes_name_and_summary(self):
        pr.record_install("alpha", version="1.0", install_source="local", install_path="/p")
        text = pr.registry_path().read_text(encoding="utf-8")
        data = json.loads(text)
        # name is the dict key, not a field
        self.assertNotIn("name", data["alpha"])
        # manifest_summary is runtime-derived
        self.assertNotIn("manifest_summary", data["alpha"])

    # ----- enable/disable -----
    def test_set_enabled_toggles(self):
        pr.record_install("alpha", version="1.0", install_source="local", install_path="/p")
        self.assertTrue(pr.set_enabled("alpha", False))
        self.assertFalse(pr.get("alpha").enabled)
        self.assertTrue(pr.set_enabled("alpha", True))
        self.assertTrue(pr.get("alpha").enabled)

    def test_set_enabled_returns_false_for_unknown(self):
        self.assertFalse(pr.set_enabled("nonexistent", True))

    # ----- uninstall -----
    def test_record_uninstall_removes_row(self):
        pr.record_install("alpha", version="1.0", install_source="local", install_path="/p")
        self.assertTrue(pr.record_uninstall("alpha"))
        self.assertIsNone(pr.get("alpha"))
        self.assertFalse(pr.record_uninstall("alpha"))  # second time: no-op

    # ----- malformed registry -----
    def test_corrupt_registry_returns_empty(self):
        pr.registry_path().parent.mkdir(parents=True, exist_ok=True)
        pr.registry_path().write_text("this is not json", encoding="utf-8")
        self.assertEqual(pr.load_registry(), {})

    def test_non_dict_root_returns_empty(self):
        pr.registry_path().parent.mkdir(parents=True, exist_ok=True)
        pr.registry_path().write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(pr.load_registry(), {})

    def test_malformed_entry_is_dropped(self):
        pr.registry_path().parent.mkdir(parents=True, exist_ok=True)
        pr.registry_path().write_text(
            json.dumps({"good": {"version": "1.0", "install_path": "/p"},
                        "bad": "not-a-dict"}),
            encoding="utf-8",
        )
        reg = pr.load_registry()
        self.assertIn("good", reg)
        self.assertNotIn("bad", reg)

    # ----- atomic write -----
    def test_atomic_write_leaves_no_temp_files(self):
        pr.record_install("alpha", version="1.0", install_source="local", install_path="/p")
        leftovers = [n for n in os.listdir(pr.plugins_dir())
                     if n.startswith(".registry.") and n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    # ----- list_all merges installed + in-tree -----
    def test_list_all_includes_user_installed_bundle(self):
        bundle_dir = _write_minimal_bundle(pr.plugins_dir(), name="user_demo")
        pr.record_install(
            "user_demo",
            version="0.0.1",
            install_source="local",
            install_path=str(bundle_dir),
        )
        names = [e.name for e in pr.list_all()]
        self.assertIn("user_demo", names)

    def test_list_all_attaches_manifest_summary(self):
        bundle_dir = _write_minimal_bundle(pr.plugins_dir(), name="summary_demo")
        pr.record_install(
            "summary_demo",
            version="0.0.1",
            install_source="local",
            install_path=str(bundle_dir),
        )
        entry = pr.get("summary_demo")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.manifest_summary["author"], "test")
        self.assertEqual(len(entry.manifest_summary["hooks"]), 1)
        self.assertEqual(entry.manifest_summary["hooks"][0]["name"], "demo_hook")

    def test_kind_backfilled_from_manifest_when_default(self):
        bundle_dir = _write_minimal_bundle(pr.plugins_dir(), name="kind_demo", kind="hook_bundle")
        pr.record_install(
            "kind_demo",
            version="0.0.1",
            install_source="local",
            install_path=str(bundle_dir),
        )
        entry = pr.get("kind_demo")
        self.assertEqual(entry.kind, "hook_bundle")

    def test_installed_dir_for_missing_bundle_yields_empty_summary(self):
        # Registry row points to a nonexistent path — should not crash.
        pr.record_install(
            "ghost",
            version="0.0.1",
            install_source="local",
            install_path=str(pr.plugins_dir() / "ghost_not_there"),
        )
        entry = pr.get("ghost")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.manifest_summary, {})


if __name__ == "__main__":
    unittest.main()
