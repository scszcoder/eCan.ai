"""
Tests for plugin_dependents — scan skill diagrams for hookBundles refs.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.ec_skills.browser_use_extension import plugin_dependents as pd


def _write_skill(
    root: Path,
    skill_name: str,
    *,
    hook_bundle_refs: list[dict] | None = None,
    nested_in_loop: bool = False,
    node_type: str = "browser-automation",
) -> Path:
    """Write a minimal skill diagram with one node that may carry hookBundles."""
    skill_dir = root / skill_name
    diagram_dir = skill_dir / "diagram_dir"
    diagram_dir.mkdir(parents=True, exist_ok=True)

    node_data: dict = {"title": "BA_Node_1"}
    if hook_bundle_refs is not None:
        node_data["inputsValues"] = {
            "hookBundles": {
                "type": "constant",
                "content": json.dumps(hook_bundle_refs),
            }
        }

    node = {
        "id": "node_ba_1",
        "type": node_type,
        "data": node_data,
    }

    if nested_in_loop:
        # Wrap inside a loop node to verify recursion.
        diagram_nodes = [
            {
                "id": "loop_1",
                "type": "loop",
                "blocks": [node],
            }
        ]
    else:
        diagram_nodes = [node]

    diagram = {
        "skillId": f"skill_{skill_name}",
        "skillName": skill_name,
        "workFlow": {"nodes": diagram_nodes, "edges": []},
    }
    (diagram_dir / f"{skill_name}.json").write_text(
        json.dumps(diagram, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return diagram_dir / f"{skill_name}.json"


class PluginDependentsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self._root = Path(self._tmp.name)
        self._cwd = self._root / "repo"
        (self._cwd / "my_skills").mkdir(parents=True, exist_ok=True)
        self._appdata = self._root / "appdata"
        self._appdata.mkdir(parents=True, exist_ok=True)

        # Force candidate_skill_roots to look under our tmp dirs.
        self._cwd_patcher = patch.object(Path, "cwd", return_value=self._cwd)
        self._cwd_patcher.start()
        self._envi_patcher = patch(
            "config.envi.getECBotDataHome", return_value=str(self._appdata)
        )
        self._envi_patcher.start()

    def tearDown(self):
        self._envi_patcher.stop()
        self._cwd_patcher.stop()
        self._tmp.cleanup()

    # ----- basics -----
    def test_no_skills_returns_empty(self):
        self.assertEqual(pd.find_dependents("anything"), [])
        self.assertFalse(pd.has_dependents("anything"))

    def test_skill_with_no_hook_bundles_is_not_a_dependent(self):
        _write_skill(self._cwd / "my_skills", "alpha_skill", hook_bundle_refs=None)
        self.assertEqual(pd.find_dependents("feige_chat"), [])

    def test_finds_bare_name_reference(self):
        _write_skill(
            self._cwd / "my_skills", "alpha_skill",
            hook_bundle_refs=[{"path": "feige_chat", "enabled": True}],
        )
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].skill_name, "alpha_skill")
        self.assertEqual(deps[0].node_id, "node_ba_1")

    def test_finds_absolute_path_reference_by_basename(self):
        _write_skill(
            self._cwd / "my_skills", "alpha_skill",
            hook_bundle_refs=[{"path": "C:/somewhere/feige_chat", "enabled": True}],
        )
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)

    def test_recurses_into_loop_blocks(self):
        _write_skill(
            self._cwd / "my_skills", "alpha_skill",
            hook_bundle_refs=[{"path": "feige_chat"}],
            nested_in_loop=True,
        )
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)

    def test_ignores_non_browser_automation_nodes(self):
        _write_skill(
            self._cwd / "my_skills", "alpha_skill",
            hook_bundle_refs=[{"path": "feige_chat"}],
            node_type="llm",
        )
        self.assertEqual(pd.find_dependents("feige_chat"), [])

    def test_skips_bundle_diagram_file(self):
        # When both <skill>.json and <skill>_bundle.json exist, the bundle
        # variant should be ignored to avoid double-counting.
        _write_skill(
            self._cwd / "my_skills", "alpha_skill",
            hook_bundle_refs=[{"path": "feige_chat"}],
        )
        # Create the _bundle variant pointing at the same bundle.
        diagram_dir = self._cwd / "my_skills" / "alpha_skill" / "diagram_dir"
        diagram = json.loads((diagram_dir / "alpha_skill.json").read_text(encoding="utf-8"))
        (diagram_dir / "alpha_skill_bundle.json").write_text(
            json.dumps(diagram), encoding="utf-8"
        )
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)

    def test_skips_unparseable_diagram(self):
        # Write a malformed file alongside a good one.
        good_root = self._cwd / "my_skills"
        _write_skill(good_root, "alpha_skill",
                     hook_bundle_refs=[{"path": "feige_chat"}])
        bad_dir = good_root / "beta_skill" / "diagram_dir"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "beta_skill.json").write_text("{not json", encoding="utf-8")
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].skill_name, "alpha_skill")

    def test_multi_match_returns_all(self):
        _write_skill(self._cwd / "my_skills", "alpha_skill",
                     hook_bundle_refs=[{"path": "feige_chat"}])
        _write_skill(self._cwd / "my_skills", "beta_skill",
                     hook_bundle_refs=[{"path": "feige_chat"}])
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 2)
        names = sorted(d.skill_name for d in deps)
        self.assertEqual(names, ["alpha_skill", "beta_skill"])

    def test_accepts_content_as_already_parsed_list(self):
        # Older saves may store content as a list, not a JSON string.
        skill_dir = self._cwd / "my_skills" / "alpha_skill"
        diagram_dir = skill_dir / "diagram_dir"
        diagram_dir.mkdir(parents=True, exist_ok=True)
        diagram = {
            "skillId": "skill_alpha",
            "skillName": "alpha_skill",
            "workFlow": {"nodes": [{
                "id": "node_ba_1",
                "type": "browser-automation",
                "data": {
                    "title": "BA",
                    "inputsValues": {
                        "hookBundles": {
                            "type": "constant",
                            "content": [{"path": "feige_chat"}],
                        }
                    },
                },
            }], "edges": []},
        }
        (diagram_dir / "alpha_skill.json").write_text(
            json.dumps(diagram), encoding="utf-8"
        )
        deps = pd.find_dependents("feige_chat")
        self.assertEqual(len(deps), 1)


if __name__ == "__main__":
    unittest.main()
