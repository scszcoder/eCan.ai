"""Saving an existing skill publishes its new version only after its files are
in the cloud (2026-10-19, 飞鸽客服前台01: the record was updated first, the COS
upload then timed out twice, and subscribers' update check saw the new version
but downloaded the OLD files)."""
from unittest.mock import MagicMock, patch

import gui.ipc.w2p_handlers.skill_handler as sh

ME = "o3YBk2dxaRe3LKqJXCf5z3PfvD5M"


def _save(upload_result):
    service = MagicMock()
    service.get_skill_by_id.return_value = {
        "success": True, "data": {"id": "skill_7f", "name": "飞鸽客服前台01", "owner": ME, "version": "1"}}
    service.update_skill.return_value = {"success": True}
    calls = []

    def fake_upload(data, on_done=None):
        calls.append("files")
        on_done(*upload_result)

    def fake_record(data, op, req, params, update_publish_flags=False, on_done=None):
        calls.append(f"record:{getattr(op, 'name', op)}")
        on_done(True, "")

    with patch.object(sh, "resolve_username", return_value=ME), \
         patch.object(sh, "_get_skill_service", return_value=service), \
         patch.object(sh, "get_handler_context", return_value=None), \
         patch.object(sh, "_SKILL_FILE_SYNC_AVAILABLE", True), \
         patch.object(sh, "upload_skill_files_to_cloud", side_effect=fake_upload, create=True), \
         patch.object(sh, "_trigger_cloud_sync", side_effect=fake_record), \
         patch.object(sh, "_upload_skill_prompts", lambda *a, **k: None), \
         patch.object(sh, "_update_skill_in_memory", lambda *a, **k: None), \
         patch.object(sh, "create_error_response", side_effect=lambda req, code, msg: {"error": code, "message": msg}), \
         patch.object(sh, "create_success_response", side_effect=lambda req, data: {"success": True, **data}):
        resp = sh.handle_save_agent_skill(MagicMock(), {"username": ME,
                                                        "skill_info": {"id": "skill_7f", "name": "飞鸽客服前台01"}})
    status = sh._CLOUD_SAVES["skill_7f"].wait(0.1)
    return resp, calls, status


def test_files_upload_first_then_the_record():
    resp, calls, status = _save((True, ""))
    assert resp.get("success") and calls == ["files", "record:UPDATE"]
    assert status["ok"] is True


def test_failed_upload_does_not_publish_the_new_version():
    resp, calls, status = _save((False, "Read timed out. (read timeout=120)"))
    assert calls == ["files"]                         # record NOT updated
    assert status["ok"] is False and "timed out" in status["errors"]["files"]
    assert "not published" in status["errors"]["record"]


def test_skill_without_files_still_publishes_its_record():
    _, calls, status = _save((False, "skill folder not found"))
    assert calls == ["files", "record:UPDATE"]
