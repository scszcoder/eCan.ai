"""
End-to-end smoke test for plugin Phase 1.

Drives the substrate as the IPC handlers will: install → enable → autoload
warm-loads → disable → autoload skips → dependents → uninstall.
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

from agent.ec_skills.browser_use_extension import (
    plugin_autoload,
    plugin_dependents,
    plugin_installer,
    plugin_registry,
)


_MANIFEST = textwrap.dedent("""\
    api_version: 1
    kind: hook_bundle
    bundle: e2e_demo
    version: 0.1.0
    author: "e2e"
    description: "e2e smoke bundle"
    hooks:
      - name: e2e_demo_hook
        entrypoint: "hooks.py:E2EDemoHook"
        stage: on_event_normalized
        tier: 1
        priority: 50
""")

_HOOKS_PY = (
    "class E2EDemoHook:\n"
    "    def __init__(self, config=None, manifest=None):\n"
    "        self.config = config or {}\n"
    "    async def run(self, ctx, payload):\n"
    "        return None\n"
)


def _make_bundle_dir(root: Path, name: str = "e2e_demo") -> Path:
    bd = root / name
    bd.mkdir(parents=True, exist_ok=True)
    (bd / "hook.yaml").write_text(
        _MANIFEST.replace("bundle: e2e_demo", f"bundle: {name}"), encoding="utf-8",
    )
    (bd / "hooks.py").write_text(_HOOKS_PY, encoding="utf-8")
    return bd


def _make_skill_referencing(root: Path, skill_name: str, bundle_name: str) -> Path:
    skill_dir = root / skill_name / "diagram_dir"
    skill_dir.mkdir(parents=True, exist_ok=True)
    diagram = {
        "skillId": f"skill_{skill_name}",
        "skillName": skill_name,
        "workFlow": {
            "nodes": [{
                "id": "ba1",
                "type": "browser-automation",
                "data": {
                    "title": "BA",
                    "inputsValues": {
                        "hookBundles": {
                            "type": "constant",
                            "content": json.dumps([{"path": bundle_name}]),
                        }
                    },
                },
            }],
            "edges": [],
        },
    }
    p = skill_dir / f"{skill_name}.json"
    p.write_text(json.dumps(diagram, indent=2), encoding="utf-8")
    return p


class PluginPhase1E2ETest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._appdata = Path(self._tmp.name) / "appdata"
        self._appdata.mkdir(parents=True, exist_ok=True)
        self._workspace = Path(self._tmp.name) / "workspace"
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._cwd = Path(self._tmp.name) / "repo"
        (self._cwd / "my_skills").mkdir(parents=True, exist_ok=True)

        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata),
        )
        self._envi_patcher.start()
        self._cwd_patcher = patch.object(Path, "cwd", return_value=self._cwd)
        self._cwd_patcher.start()
        plugin_autoload.reset()

    def tearDown(self):
        plugin_autoload.reset()
        self._cwd_patcher.stop()
        self._envi_patcher.stop()
        self._tmp.cleanup()

    def test_full_install_autoload_disable_uninstall_cycle(self):
        # ---- 1. Install a local bundle ----
        src = _make_bundle_dir(self._workspace, "e2e_demo")
        result = plugin_installer.install_from_dir(src)
        self.assertEqual(result.name, "e2e_demo")

        # registry sees it, enabled by default
        entry = plugin_registry.get("e2e_demo")
        self.assertIsNotNone(entry)
        self.assertTrue(entry.enabled)
        self.assertEqual(entry.install_source, "local")

        # ---- 2. Autoload picks it up ----
        summary = plugin_autoload.initialize()
        loaded = [x["name"] for x in summary["loaded"]]
        self.assertIn("e2e_demo", loaded)
        hooks = plugin_autoload.get_loaded_hooks("e2e_demo")
        self.assertEqual(len(hooks), 1)
        self.assertEqual(hooks[0].__class__.__name__, "E2EDemoHook")

        # ---- 3. Re-initialize is idempotent ----
        summary2 = plugin_autoload.initialize()
        self.assertTrue(summary2["already_initialized"])

        # ---- 4. Disable + reset + reinitialize → skipped ----
        self.assertTrue(plugin_registry.set_enabled("e2e_demo", False))
        plugin_autoload.reset()
        summary3 = plugin_autoload.initialize()
        loaded3 = [x["name"] for x in summary3["loaded"]]
        self.assertNotIn("e2e_demo", loaded3)
        skipped_names = [s["name"] for s in summary3["skipped"]]
        self.assertIn("e2e_demo", skipped_names)

        # ---- 5. Plant a skill that depends on it ----
        _make_skill_referencing(self._cwd / "my_skills", "alpha_skill", "e2e_demo")
        deps = plugin_dependents.find_dependents("e2e_demo")
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].skill_name, "alpha_skill")

        # ---- 6. Uninstall is blocked while dependents exist ----
        with self.assertRaises(plugin_installer.DependentsBlockedError):
            plugin_installer.uninstall("e2e_demo")
        # still in registry
        self.assertIsNotNone(plugin_registry.get("e2e_demo"))

        # ---- 7. Force uninstall succeeds ----
        plugin_installer.uninstall("e2e_demo", force=True)
        self.assertIsNone(plugin_registry.get("e2e_demo"))
        self.assertFalse(Path(result.install_path).exists())

    def test_broken_bundle_does_not_block_autoload_of_good_one(self):
        # Install one good bundle.
        good_src = _make_bundle_dir(self._workspace, "good_one")
        plugin_installer.install_from_dir(good_src)

        # Plant a stale registry entry pointing at a missing path
        # (simulates a bundle deleted from disk after install).
        plugin_registry.record_install(
            "ghost",
            version="0.0.1",
            install_source="local",
            install_path=str(self._appdata / "plugins" / "does_not_exist"),
        )

        summary = plugin_autoload.initialize()
        loaded = [x["name"] for x in summary["loaded"]]
        errs = [e["bundle"] for e in summary["errors"]]
        self.assertIn("good_one", loaded)
        self.assertIn("ghost", errs)
        self.assertNotIn("good_one", errs)


if __name__ == "__main__":
    unittest.main()
