"""Review fixes on the chip-crawler merge: NAS upload sources, NAS actions only
where a NAS is configured, fingerprint browsers never reclaimed, chip-pilot re-arm."""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent.ec_skills.nas import ugreen_nas as nas


@pytest.fixture
def no_nas_env(monkeypatch, tmp_path):
    for k in ("ECAN_NAS_USER", "ECAN_NAS_PASSWORD", "ECAN_NAS_CREDS_FILE", "ECAN_NAS_UPLOAD_ROOTS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.setattr(nas, "_find_creds_file", lambda: None)


def test_nas_configured_only_with_credentials(no_nas_env, monkeypatch):
    assert nas.nas_configured() is False
    monkeypatch.setenv("ECAN_NAS_USER", "u")
    monkeypatch.setenv("ECAN_NAS_PASSWORD", "p")
    assert nas.nas_configured() is True


def test_upload_only_from_allowed_folders(no_nas_env, monkeypatch, tmp_path):
    secret = tmp_path / "uli.json"
    secret.write_text("{}")
    with pytest.raises(PermissionError):
        nas.nas_upload(str(secret))
    docs = tmp_path / "chip_docs" / "Microchip"
    docs.mkdir(parents=True)
    pdf = docs / "a.pdf"
    pdf.write_bytes(b"%PDF")
    monkeypatch.setenv("ECAN_NAS_UPLOAD_ROOTS", str(tmp_path / "chip_docs"))
    nas._check_upload_source(pdf)                               # allowed now
    with pytest.raises(PermissionError):
        nas._check_upload_source(docs / ".." / ".." / "uli.json")   # no escaping the root


def test_fingerprint_browser_profile_is_never_reclaimed(tmp_path):
    from agent.ec_skills.browser_use_extension import profile_lock_cleaner as plc
    (tmp_path / ".ecan_cdp.json").write_text("{}")
    with patch.object(plc, "find_profile_owner_processes", side_effect=AssertionError("must not scan")):
        assert plc.reclaim_orphaned_profile(tmp_path) == {"orphans_killed": [], "live_owners": []}


def test_chip_pilot_arm_forgets_a_finished_run_and_allows_docs_upload(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from cli.tasks import commands as tc
    ctx = MagicMock(username="me")
    ctx.require_auth.return_value = None
    ctx.db.task_service.query_tasks.return_value = {"data": [{"id": "c1", "name": "ChipDocsCoordinator task"}]}
    ctx.db.task_service.get_task_skills.return_value = {"data": []}
    ctx.db.task_service.get_task_by_id.return_value = {"success": True, "data": {
        "name": "c", "trigger": "auto", "metadata": {"run_once": True, "completed_once_at": "2026-10-11T10:00:00"}}}
    ctx.db.task_service.update_task.return_value = {"success": True}
    (tmp_path / "run.env").write_text("ECAN_NAS_UPLOAD_ROOTS=D:/old\n", encoding="utf-8")
    with patch.object(tc, "get_context", return_value=ctx), patch("cli.base.context.get_context", return_value=ctx), \
         patch.object(tc, "get_output", return_value=MagicMock()), patch("cli.base.sync.cloud_sync"), \
         patch.object(tc, "_chip_skill_ids", return_value={}), \
         patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
        r = CliRunner().invoke(tc.chip_pilot, ["--docs-root", "C:/chip_docs"])
    assert r.exit_code == 0, r.output
    armed = [c.args[1] for c in ctx.db.task_service.update_task.call_args_list if "trigger" in c.args[1]][-1]
    assert "completed_once_at" not in armed["settings"] and armed["settings"]["run_once"] is True
    assert "ECAN_NAS_UPLOAD_ROOTS=D:/old;C:/chip_docs" in (tmp_path / "run.env").read_text(encoding="utf-8")
