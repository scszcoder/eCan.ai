"""First save of a NEW skill (2026-10-21, 电商售后应答): the editor's save made a
second record of the skill its own file had just created, and the files upload
asked for an upload URL before the cloud record existed ("Skill archive upload
is not permitted")."""
from unittest.mock import MagicMock, patch

import gui.ipc.w2p_handlers.skill_file_sync as sfs
import gui.ipc.w2p_handlers.skill_handler as sh

ME = "o3YBk2dxaRe3LKqJXCf5z3PfvD5M"
PATH = r"C:\x\my_skills\售后_skill\diagram_dir\售后_skill.json"


def _save(by_path):
    service = MagicMock()
    service.get_skill_by_id.return_value = {"success": False, "data": None, "error": "Skill not found"}
    service.get_skill_by_path.return_value = by_path
    service.update_skill.return_value = {"success": True}
    service.add_skill.return_value = {"success": True, "id": "editor_id", "updated": False}
    with patch.object(sh, "resolve_username", return_value=ME), \
         patch.object(sh, "_get_skill_service", return_value=service), \
         patch.object(sh, "get_handler_context", return_value=None), \
         patch.object(sh, "_SKILL_FILE_SYNC_AVAILABLE", False), \
         patch.object(sh, "_trigger_cloud_sync", lambda *a, **k: (k.get("on_done") or (lambda *x: None))(True, "")), \
         patch.object(sh, "_upload_skill_prompts", lambda *a, **k: None), \
         patch.object(sh, "_update_skill_in_memory", lambda *a, **k: None), \
         patch.object(sh, "create_error_response", side_effect=lambda req, code, msg: {"error": code, "message": msg}), \
         patch.object(sh, "create_success_response", side_effect=lambda req, data: {"success": True, **data}):
        resp = sh.handle_save_agent_skill(MagicMock(), {"username": ME, "skill_info": {
            "id": "editor_id", "name": "售后", "path": PATH}})
    return resp, service


def test_the_record_its_file_just_created_is_updated_not_duplicated():
    row = {"id": "skill_588e", "name": "售后", "owner": ME, "version": "1", "path": PATH}
    resp, service = _save({"success": True, "data": row})
    assert resp.get("success") and resp["skill_id"] == "skill_588e"
    service.add_skill.assert_not_called()
    assert service.update_skill.call_args[0][0] == "skill_588e"
    assert service.update_skill.call_args[0][1]["id"] == "skill_588e"


def test_a_really_new_skill_is_still_created():
    resp, service = _save({"success": False, "data": None})
    assert resp.get("success")
    service.add_skill.assert_called_once()


def test_a_different_skill_at_that_path_is_not_taken_over():
    row = {"id": "skill_other", "name": "别的技能", "owner": ME, "version": "1", "path": PATH}
    _resp, service = _save({"success": True, "data": row})
    service.add_skill.assert_called_once()
    service.update_skill.assert_not_called()


def test_upload_url_waits_for_the_cloud_record():
    refused = {"errors": [{"message": "Skill archive upload is not permitted",
                           "extensions": {"code": "NOT_FOUND"}}]}
    ok = {"data": {"requestSkillFileUploadUrl": {"uploadUrl": "u", "s3Key": "k", "expiresIn": 900}}}
    answers = [refused, refused, ok]
    with patch.object(sfs, "_appsync_request", side_effect=lambda *a, **k: answers.pop(0)), \
         patch.object(sfs.time, "sleep", lambda s: None):
        assert sfs._request_upload_url("skill_588e", ME, "售后_skill.zip", {})["uploadUrl"] == "u"
    assert not answers


def test_other_refusals_are_not_retried():
    other = {"errors": [{"message": "Skill archive uploads must use the caller namespace"}]}
    calls = []
    with patch.object(sfs, "_appsync_request", side_effect=lambda *a, **k: calls.append(1) or other), \
         patch.object(sfs.time, "sleep", lambda s: None):
        assert sfs._request_upload_url("s", ME, "f.zip", {}) is None
    assert len(calls) == 1
