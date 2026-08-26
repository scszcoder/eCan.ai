"""CN skill-file sync via the presigned zip flow + per-file fallback.

Live-verified against the deployed TCB backend (2026-08-27): CN
implements the intl-style presigned flow — requestSkillFileUploadUrl →
signed COS PUT of the zip; requestSkillFileDownloadUrl → signed GET →
unzip. The old writeSkillFile-package and scalar-shaped
listSkillFiles/readSkillFile queries did NOT match the deployed SDL
(typed results needing selection sets; readSkillFile returns file
content INLINE, no downloadUrl) — validation errors were silently
swallowed as "no files listed" (the v0.9.95n empty-my_skills incident).
"""

import io
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.skill_file_sync as sfs


AUTHOR = "wechat_b603a407904569a4ea88f9ac"
CTX = {"owner": AUTHOR, "session": None, "token": "t", "endpoint": "e"}


def _make_zip(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


class _InlineThread:
    """threading.Thread stand-in that runs the target synchronously."""

    def __init__(self, target=None, daemon=None, name=None):
        self._target = target

    def start(self):
        if self._target:
            self._target()


class TestUnzipSafety:
    def test_extracts_normal_entries(self, tmp_path):
        zb = _make_zip({"code_dir/x.py": "print(1)", "data_mapping.json": "{}"})
        assert sfs._unzip_to_skill_dir(zb, tmp_path / "s_skill")
        assert (tmp_path / "s_skill" / "code_dir" / "x.py").read_text() == "print(1)"

    def test_zip_slip_entry_skipped(self, tmp_path):
        dest = tmp_path / "inner" / "s_skill"
        zb = _make_zip({"../evil.txt": "pwn", "ok.txt": "fine"})
        assert sfs._unzip_to_skill_dir(zb, dest)
        assert (dest / "ok.txt").exists()
        assert not (tmp_path / "inner" / "evil.txt").exists()
        assert not (tmp_path / "evil.txt").exists()


class TestCnPackageUpload:
    """CN save = zip + requestSkillFileUploadUrl + signed PUT (real skill id)."""

    def _run(self, tmp_path, url_info):
        skill_dir = tmp_path / "demo_skill"
        (skill_dir / "code_dir").mkdir(parents=True)
        (skill_dir / "code_dir" / "a.py").write_text("pass")
        put_bytes = []
        with patch.object(sfs, "_request_upload_url", return_value=url_info) as req, \
             patch.object(sfs, "_upload_to_s3",
                          side_effect=lambda url, b: put_bytes.append((url, b)) or True):
            ok = sfs._cn_upload_skill_package(skill_dir, dict(CTX), "skill_4f24592c81894ae7")
        return ok, req, put_bytes

    def test_uploads_zip_via_presigned_url(self, tmp_path):
        ok, req, puts = self._run(tmp_path, {"uploadUrl": "https://cos/put", "s3Key": "k"})
        assert ok
        # requested with the REAL skill id + canonical zip file name
        args = req.call_args.args
        assert args[0] == "skill_4f24592c81894ae7"
        assert args[1] == AUTHOR
        assert args[2] == "demo_skill.zip"
        url, body = puts[0]
        assert url == "https://cos/put"
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        assert any(n.replace("\\", "/") == "code_dir/a.py" for n in names)

    def test_no_upload_url_returns_false(self, tmp_path):
        ok, _, puts = self._run(tmp_path, None)
        assert not ok and puts == []

    def test_missing_skill_id_skips(self, tmp_path):
        skill_dir = tmp_path / "demo_skill"
        skill_dir.mkdir()
        with patch.object(sfs, "_request_upload_url") as req:
            assert not sfs._cn_upload_skill_package(skill_dir, dict(CTX), "")
        req.assert_not_called()


class TestCnZipFirstDownload:
    """CN download: presigned zip primary; typed per-file queries fallback."""

    def _run(self, tmp_path, url_info, listing=None, contents=None):
        gql_queries = []

        def fake_gql(query, ctx, variables=None):
            gql_queries.append((query, variables))
            if "listSkillFiles" in query:
                return {"data": {"listSkillFiles": listing or []}}
            if "readSkillFile" in query:
                fp = variables["filePath"]
                body = (contents or {}).get(fp)
                return {"data": {"readSkillFile": [{"filePath": fp, "content": body}]
                                 if body is not None else []}}
            return {}

        zb = _make_zip({"from_zip.txt": "zipped"})
        with patch.object(sfs, "_get_cloud_context", return_value=dict(CTX)), \
             patch.object(sfs, "_get_my_skills_dir", return_value=tmp_path), \
             patch.object(sfs, "_request_download_url", return_value=url_info) as req, \
             patch.object(sfs, "_download_from_s3", return_value=zb), \
             patch.object(sfs, "_appsync_request", side_effect=fake_gql), \
             patch.object(sfs.threading, "Thread", _InlineThread):
            sfs._download_skill_files_cn({"id": "skill_x", "name": "demo"}, file_owner=AUTHOR)
        return req, gql_queries

    def test_presigned_zip_primary(self, tmp_path):
        req, queries = self._run(tmp_path, {"downloadUrl": "https://cos/get"})
        # requested with real skill id + AUTHOR namespace
        assert req.call_args.args[0] == "skill_x"
        assert req.call_args.args[1] == AUTHOR
        assert (tmp_path / "demo_skill" / "from_zip.txt").read_text() == "zipped"
        assert not any("listSkillFiles" in q for q, _ in queries)  # no fallback needed

    def test_fallback_uses_typed_queries_and_inline_content(self, tmp_path):
        listing = [{"filePath": "demo_skill/code_dir/a.py"},
                   {"filePath": "demo_skill/demo_skill.zip"}]
        contents = {"demo_skill/code_dir/a.py": "print('hi')"}
        _, queries = self._run(tmp_path, None, listing=listing, contents=contents)
        # typed selection sets (the old scalar shape failed SDL validation)
        list_q = next(q for q, _ in queries if "listSkillFiles" in q)
        assert "{ filePath }" in list_q
        read_q = next(q for q, _ in queries if "readSkillFile" in q)
        assert "content" in read_q
        # inline content written; zip artifact skipped
        assert (tmp_path / "demo_skill" / "code_dir" / "a.py").read_text() == "print('hi')"
        assert not (tmp_path / "demo_skill" / "demo_skill.zip").exists()

    def test_owner_prefixed_paths_normalized(self, tmp_path):
        listing = [{"filePath": f"{AUTHOR}/my_skills/demo_skill/b.py"}]
        contents = {f"{AUTHOR}/my_skills/demo_skill/b.py": "x = 1"}
        self._run(tmp_path, None, listing=listing, contents=contents)
        assert (tmp_path / "demo_skill" / "b.py").read_text() == "x = 1"


class TestZipOnlySave:
    """CN save uploads ONE zip via the presigned flow — nothing else."""

    def test_save_uses_presigned_flow(self, tmp_path):
        skill_dir = tmp_path / "demo_skill"
        (skill_dir / "diagram_dir").mkdir(parents=True)
        (skill_dir / "diagram_dir" / "demo_skill.json").write_text("{}")
        with patch.object(sfs, "_is_intl_app", return_value=False), \
             patch.object(sfs, "_get_cloud_context", return_value=dict(CTX)), \
             patch.object(sfs, "_resolve_skill_dir", return_value=skill_dir), \
             patch.object(sfs, "_is_valid_skill_dir", return_value=True), \
             patch.object(sfs, "_request_upload_url",
                          return_value={"uploadUrl": "https://cos/put", "s3Key": "k"}) as req, \
             patch.object(sfs, "_upload_to_s3", return_value=True) as put, \
             patch.object(sfs.threading, "Thread", _InlineThread):
            sfs._CN_SYNCED_SKILL_DIRS.discard(str(skill_dir))
            sfs.upload_skill_files_to_cloud({"id": "skill_x", "name": "demo"})
        req.assert_called_once()
        assert req.call_args.args[0] == "skill_x"
        put.assert_called_once()
