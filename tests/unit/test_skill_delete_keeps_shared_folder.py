"""Deleting a skill removes its folder -- unless another skill still uses it.

Two rows of one skill (the first-save duplicate) share a folder; deleting the
spare row used to rmtree the folder the remaining skill runs from. 2026-10-04.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import gui.ipc.w2p_handlers.skill_handler as sh


def _svc(rows):
    s = MagicMock()
    s.query_skills.return_value = {"success": True, "data": rows}
    return s


def _ctx(skills=()):
    c = MagicMock()
    c.get_agent_skills.return_value = list(skills)
    return c


def test_folder_still_used_by_another_row_is_reported(tmp_path):
    root = tmp_path / "x_skill"
    keep = {"id": "skill_keep", "path": str(root / "diagram_dir" / "x_skill.json").replace("\\", "/")}
    with patch.object(sh, "get_handler_context", return_value=_ctx()):
        assert sh._skill_dir_users(root, _svc([keep, {"id": "other", "path": str(tmp_path / "y_skill" / "a.json")}])) == ["skill_keep"]


def test_unused_folder_is_free(tmp_path):
    with patch.object(sh, "get_handler_context", return_value=_ctx()):
        assert sh._skill_dir_users(tmp_path / "x_skill", _svc([{"id": "o", "path": str(tmp_path / "x_skill_2" / "a.json")}])) == []


def test_lookup_failure_counts_as_in_use(tmp_path):
    s = MagicMock()
    s.query_skills.side_effect = RuntimeError("db locked")
    assert sh._skill_dir_users(tmp_path / "x_skill", s) == ["(unknown)"]


def test_in_memory_skill_also_counts(tmp_path):
    root = tmp_path / "x_skill"
    mem = SimpleNamespace(id="skill_mem", path=str(root / "diagram_dir" / "x_skill.json"))
    with patch.object(sh, "get_handler_context", return_value=_ctx([mem])):
        assert sh._skill_dir_users(root, _svc([])) == ["skill_mem"]


def test_delete_handler_keeps_a_shared_folder_and_removes_an_unshared_one(tmp_path):
    def _skill_dir(name):
        d = tmp_path / f"{name}_skill" / "diagram_dir"
        d.mkdir(parents=True)
        f = d / f"{name}_skill.json"
        f.write_text("{}", encoding="utf-8")
        return str(f)

    shared = _skill_dir("twin")
    alone = _skill_dir("solo")
    rows = {"spare": {"id": "spare", "name": "twin", "owner": "me", "path": shared},
            "keep": {"id": "keep", "name": "twin", "owner": "me", "path": shared},
            "solo": {"id": "solo", "name": "solo", "owner": "me", "path": alone}}
    svc = MagicMock()
    svc.get_skills_by_owner.side_effect = lambda o: {"success": True, "data": list(rows.values())}
    svc.get_skill_by_id.side_effect = lambda i: {"success": True, "data": rows.get(i)}
    svc.query_skills.side_effect = lambda **k: {"success": True, "data": list(rows.values())}
    svc.delete_skill.side_effect = lambda i: (rows.pop(i, None), {"success": True})[1]

    with patch.object(sh, "resolve_username", return_value="me"), \
         patch.object(sh, "_get_skill_service", return_value=svc), \
         patch.object(sh, "get_handler_context", return_value=_ctx()), \
         patch.object(sh, "_sync_skill_delete_to_cloud", return_value={"success": True}), \
         patch.object(sh, "_fetch_cloud_skills", return_value=[]):
        sh.handle_delete_agent_skill({"id": "r1", "method": "delete_agent_skill"}, {"username": "me", "skill_id": "spare"})
        assert (tmp_path / "twin_skill").exists(), "the remaining skill's folder must survive"
        sh.handle_delete_agent_skill({"id": "r2", "method": "delete_agent_skill"}, {"username": "me", "skill_id": "solo"})
        assert not (tmp_path / "solo_skill").exists(), "an unshared folder is still removed"
