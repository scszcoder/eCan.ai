"""Startup auto-refresh of subscribed skills (skill_file_sync).

v0.9.95x incident: a republished rented skill only reached subscribers via a
manual skills-page update click. refresh_subscribed_skills_from_cloud runs at
startup before the compile; these tests pin its core guarantees:

- only non-owned (subscribed) rows are considered
- refresh happens only when the cloud version is NEWER
- a failed zip download leaves the DB row untouched (update stays visible)
- a successful download syncs version + parsed diagram into the DB row
"""

import json
from unittest.mock import patch

import pytest

from gui.ipc.w2p_handlers import skill_file_sync as sfs


AUTHOR = "wechat_author"
ME = "customer_user"
SID = "skill_71209937ed7449bf"


class _FakeSkillService:
    def __init__(self, rows):
        self.rows = rows
        self.updates = []

    def query_skills(self, **kw):
        return {"success": True, "data": self.rows}

    def update_skill(self, skill_id, fields):
        self.updates.append((skill_id, fields))
        return {"success": True}


class _FakeMainwin:
    def __init__(self, svc):
        class _Mgr:
            pass
        self.ec_db_mgr = _Mgr()
        self.ec_db_mgr.skill_service = svc


def _row(version="1.0.0", owner=AUTHOR):
    return {"id": SID, "name": "飞鸽客服前台00", "owner": owner, "version": version}


def _run(rows, cloud_resp, url_info, zip_ok, tmp_path, dir_exists=True,
         with_files=True, auto_fetch=True):
    svc = _FakeSkillService(rows)
    mainwin = _FakeMainwin(svc)
    dest_root = tmp_path / "my_skills"
    if dir_exists:
        skill_dir = dest_root / "飞鸽客服前台00_skill"
        (skill_dir / "diagram_dir").mkdir(parents=True)
        if with_files:
            (skill_dir / "diagram_dir" / "skill.json").write_text("{}", encoding="utf-8")
    ctx = {"session": None, "token": "t", "endpoint": "e", "owner": ME}
    with patch.object(sfs, "_get_cloud_context", return_value=ctx), \
         patch.object(sfs, "_appsync_request", return_value=cloud_resp), \
         patch.object(sfs, "_request_download_url", return_value=url_info), \
         patch.object(sfs, "_download_from_s3", return_value=b"zipbytes" if zip_ok else None), \
         patch.object(sfs, "_unzip_to_skill_dir", return_value=zip_ok), \
         patch.object(sfs, "_auto_fetch_sub_skills_enabled", return_value=auto_fetch), \
         patch.object(sfs, "_get_my_skills_dir", return_value=dest_root):
        n = sfs.refresh_subscribed_skills_from_cloud(mainwin)
    return n, svc


def _cloud(version="260828020744021", diagram='{"nodes": []}'):
    return {"data": {"getAgentSkills": [{"id": SID, "version": version, "diagram": diagram}]}}


def test_refreshes_when_cloud_newer(tmp_path):
    n, svc = _run([_row("1.0.0")], _cloud(), {"downloadUrl": "u"}, True, tmp_path)
    assert n == 1
    assert svc.updates == [(SID, {"version": "260828020744021", "diagram": {"nodes": []}})]


def test_skips_when_versions_equal(tmp_path):
    n, svc = _run([_row("260828020744021")], _cloud(), {"downloadUrl": "u"}, True, tmp_path)
    assert n == 0 and svc.updates == []


def test_skips_own_skills(tmp_path):
    n, svc = _run([_row("1.0.0", owner=ME)], _cloud(), {"downloadUrl": "u"}, True, tmp_path)
    assert n == 0 and svc.updates == []


def test_failed_download_keeps_row_untouched(tmp_path):
    n, svc = _run([_row("1.0.0")], _cloud(), {"downloadUrl": "u"}, False, tmp_path)
    assert n == 0 and svc.updates == []


def test_no_local_files_allows_db_only_refresh(tmp_path):
    # No local dir: a failed zip must not block the row update (compile will
    # fall back to the DB diagram since there is no file to prefer).
    n, svc = _run([_row("1.0.0")], _cloud(), None, False, tmp_path, dir_exists=False)
    assert n == 1
    assert svc.updates[0][1]["version"] == "260828020744021"


def test_cloud_error_is_nonfatal(tmp_path):
    n, svc = _run([_row("1.0.0")], {"errors": [{"message": "boom"}]},
                  {"downloadUrl": "u"}, True, tmp_path)
    assert n == 0 and svc.updates == []


# ── ECAN_AUTO_FETCH_SUB_SKILLS (2026-08-31) ─────────────────────────────────
# Subscribed skills whose FILES are missing from my_skills are fetched even
# when the version is current, unless the option is off.

def test_missing_files_same_version_auto_fetches(tmp_path):
    n, svc = _run([_row("260828020744021")], _cloud(), {"downloadUrl": "u"},
                  True, tmp_path, dir_exists=False)
    assert n == 1


def test_empty_husk_dir_counts_as_missing(tmp_path):
    n, svc = _run([_row("260828020744021")], _cloud(), {"downloadUrl": "u"},
                  True, tmp_path, dir_exists=True, with_files=False)
    assert n == 1


def test_auto_fetch_disabled_skips_missing_files(tmp_path):
    n, svc = _run([_row("260828020744021")], _cloud(), {"downloadUrl": "u"},
                  True, tmp_path, dir_exists=False, auto_fetch=False)
    assert n == 0 and svc.updates == []


def test_missing_files_fetch_failure_counts_nothing(tmp_path):
    n, svc = _run([_row("260828020744021")], _cloud(), None, False,
                  tmp_path, dir_exists=False)
    assert n == 0 and svc.updates == []


def test_env_var_controls_option(monkeypatch):
    mainwin = _FakeMainwin(_FakeSkillService([]))
    monkeypatch.setenv("ECAN_AUTO_FETCH_SUB_SKILLS", "0")
    assert sfs._auto_fetch_sub_skills_enabled(mainwin) is False
    monkeypatch.setenv("ECAN_AUTO_FETCH_SUB_SKILLS", "1")
    assert sfs._auto_fetch_sub_skills_enabled(mainwin) is True
    monkeypatch.delenv("ECAN_AUTO_FETCH_SUB_SKILLS")
    assert sfs._auto_fetch_sub_skills_enabled(mainwin) is True  # default ON
