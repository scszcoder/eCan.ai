"""Skill "Update": refresh a subscribed skill and ALL its prompts in place.

Unsubscribe + re-subscribe cascade-deletes the agent/task links, so updating a
skill meant re-linking every agent and task by hand. And the prompt step only
fetched MISSING prompts, so an author's republished prompt never reached a
machine that already had the old one (0.9.99yd alpha: pr-731906 stayed stale
through two republishes).
"""
import json
from types import SimpleNamespace
from unittest.mock import patch

from gui.ipc.w2p_handlers import prompt_handler, skill_handler

SKILL = {"id": "skill_x", "name": "淘宝客服前台01", "owner": "author", "config": {"skill_owner": "author"}}


def _prompt_dirs(tmp_path, mine=(), subscribed=()):
    my_dir, sub_dir = tmp_path / "my_prompts", tmp_path / "subscribed_prompts"
    for d, items in ((my_dir, mine), (sub_dir, subscribed)):
        d.mkdir()
        for pid, body in items:
            (d / f"0_{pid}.json").write_text(json.dumps({"id": pid, "mdContent": body}), encoding="utf-8")
    return my_dir, sub_dir


def _cloud(*_a, variables=None, **_k):
    pid = variables["input"]["id"]
    return {"data": {"queryPrompts": [{"id": pid, "prompt": json.dumps({"mdContent": f"NEW {pid}"})}]}}


def _run(tmp_path, refresh, mine=(), subscribed=()):
    my_dir, sub_dir = _prompt_dirs(tmp_path, mine, subscribed)
    with patch.object(prompt_handler, "_get_my_prompts_dir", return_value=my_dir), \
            patch.object(prompt_handler, "_get_subscribed_prompts_dir", return_value=sub_dir), \
            patch.object(prompt_handler, "_load_all_prompts", side_effect=lambda: [
                p for d, src in ((my_dir, "my_prompts"), (sub_dir, "subscribed"))
                for p, _m in prompt_handler._load_prompts_from_directory(d, source=src, read_only=False)]), \
            patch.object(skill_handler, "_extract_skill_prompt_ids", return_value=["pr-1", "pr-2"]), \
            patch("gui.ipc.w2p_handlers.prompt_cloud_sync._get_cloud_context", return_value={"owner": "me"}), \
            patch("gui.ipc.w2p_handlers.prompt_cloud_sync._appsync_request", side_effect=_cloud):
        summary = skill_handler._download_skill_prompts(SKILL, refresh=refresh)
    body = lambda pid: json.loads((sub_dir / f"0_{pid}.json").read_text(encoding="utf-8"))["mdContent"]
    return summary, body


def test_refresh_overwrites_a_stale_subscribed_prompt(tmp_path):
    summary, body = _run(tmp_path, refresh=True, subscribed=[("pr-1", "OLD"), ("pr-2", "OLD")])
    assert sorted(summary["downloaded"]) == ["pr-1", "pr-2"] and body("pr-1") == "NEW pr-1"


def test_without_refresh_a_prompt_already_local_is_kept(tmp_path):
    summary, body = _run(tmp_path, refresh=False, subscribed=[("pr-1", "OLD")])
    assert summary["downloaded"] == ["pr-2"] and body("pr-1") == "OLD"


def test_refresh_replaces_a_my_prompts_copy_of_the_authors_prompt_and_keeps_a_backup(tmp_path):
    # 0.9.99yf alpha: a stale my_prompts pr-731906 was "kept"; my_prompts is
    # read first, so the update changed nothing.
    summary, body = _run(tmp_path, refresh=True, mine=[("pr-1", "MINE")])
    assert sorted(summary["downloaded"]) == ["pr-1", "pr-2"] and body("pr-1") == "NEW pr-1"
    assert summary["replaced_own"] == ["pr-1"] and summary["kept_own"] == []
    assert not (tmp_path / "my_prompts" / "0_pr-1.json").exists()
    backups = list((tmp_path / "my_prompts" / ".replaced").glob("0_pr-1.*.json"))
    assert len(backups) == 1 and json.loads(backups[0].read_text(encoding="utf-8"))["mdContent"] == "MINE"


def test_refresh_keeps_an_own_prompt_the_author_does_not_serve(tmp_path):
    def cloud(*_a, variables=None, **_k):
        if variables["input"]["id"] == "pr-1":
            return {"errors": [{"message": "Cross-owner access is forbidden"}]}
        return _cloud(variables=variables)
    with patch.object(skill_handler, "_extract_skill_prompt_ids", return_value=["pr-1", "pr-2"]):
        my_dir, sub_dir = _prompt_dirs(tmp_path, mine=[("pr-1", "MINE")])
        with patch.object(prompt_handler, "_get_my_prompts_dir", return_value=my_dir), \
                patch.object(prompt_handler, "_get_subscribed_prompts_dir", return_value=sub_dir), \
                patch("gui.ipc.w2p_handlers.prompt_cloud_sync._get_cloud_context", return_value={"owner": "me"}), \
                patch("gui.ipc.w2p_handlers.prompt_cloud_sync._appsync_request", side_effect=cloud):
            summary = skill_handler._download_skill_prompts(SKILL, refresh=True)
    assert summary["kept_own"] == ["pr-1"] and summary["replaced_own"] == []
    assert json.loads((my_dir / "0_pr-1.json").read_text(encoding="utf-8"))["mdContent"] == "MINE"


def test_hidden_backup_dirs_are_neither_scanned_for_prompts_nor_published(tmp_path):
    # 0.9.99yf: "2个提示词未能更新" = pr ids only a .harness_bak/ backup referenced.
    from gui.ipc.w2p_handlers import skill_file_sync
    import io, zipfile
    sk = tmp_path / "淘宝客服前台01_skill"
    (sk / "diagram_dir" / ".harness_bak").mkdir(parents=True)
    (sk / "diagram_dir" / "a.json").write_text('{"p": "pr-731906"}', encoding="utf-8")
    (sk / "diagram_dir" / ".harness_bak" / "old.json").write_text('{"p": "pr-382693"}', encoding="utf-8")
    with patch("gui.ipc.w2p_handlers.skill_file_sync._get_my_skills_dir", return_value=str(tmp_path)):
        assert skill_handler._skill_file_prompt_ids({"name": "淘宝客服前台01"}) == ["pr-731906"]
    names = zipfile.ZipFile(io.BytesIO(skill_file_sync._zip_skill_dir(sk))).namelist()
    assert [n.replace("\\", "/") for n in names] == ["diagram_dir/a.json"]


class _Svc:
    def __init__(self, row):
        self.row, self.updated = row, []

    def get_skill_by_id(self, sid):
        return {"success": bool(self.row and self.row["id"] == sid), "data": self.row}

    def query_skills(self, **_k):
        return {"success": True, "data": [self.row] if self.row else []}

    def update_skill(self, sid, data):
        self.updated.append((sid, data))
        return {"success": True}


def _update(svc, username="customer"):
    req = SimpleNamespace(id="1", method="update_subscribed_skill")
    with patch.object(skill_handler, "resolve_username", return_value=username), \
            patch.object(skill_handler, "_get_skill_service", return_value=svc), \
            patch.object(skill_handler, "_find_cloud_skill_for_subscribe",
                         return_value={**SKILL, "version": "1.0.2"}), \
            patch.object(skill_handler, "_prepare_skill_data",
                         side_effect=lambda t, o, sid: {"id": sid, "name": t["name"], "version": t["version"]}), \
            patch.object(skill_handler, "download_skill_files_from_cloud"), \
            patch.object(skill_handler, "_download_skill_prompts",
                         return_value={"downloaded": ["pr-731906"], "failed": [], "kept_own": []}) as dl, \
            patch.object(skill_handler, "_update_skill_in_memory"), \
            patch.object(skill_handler, "get_handler_context", return_value=None), \
            patch.object(skill_handler, "_sync_runtime_tasks_for_skill", return_value=2), \
            patch.object(skill_handler, "create_success_response", side_effect=lambda r, d: ("ok", d)), \
            patch.object(skill_handler, "create_error_response", side_effect=lambda r, c, m: ("err", c)):
        out = skill_handler.handle_update_subscribed_skill(req, {"skillId": "skill_x"})
    return out, dl


def test_update_keeps_the_local_skill_and_refreshes_its_prompts():
    svc = _Svc({"id": "skill_x", "askid": "a1", "owner": "author", "version": "1.0.1"})
    (kind, data), dl = _update(svc)
    assert kind == "ok" and data["version_before"] == "1.0.1" and data["version_after"] == "1.0.2"
    assert data["prompts_refreshed"] == ["pr-731906"]
    assert svc.updated[0][0] == "skill_x" and svc.updated[0][1]["askid"] == "a1"   # same row: links kept
    assert svc.updated[0][1]["source"] == "subscribed"
    assert dl.call_args.kwargs["refresh"] is True


def test_update_refuses_your_own_skill_and_an_unsubscribed_one():
    (kind, code), _dl = _update(_Svc({"id": "skill_x", "owner": "Customer"}), username="customer")
    assert (kind, code) == ("err", "UPDATE_OWN_SKILL")
    (kind, code), _dl = _update(_Svc(None))
    assert (kind, code) == ("err", "SKILL_NOT_SUBSCRIBED")
