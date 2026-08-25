"""CN publish-time zip package: upload, zip-first download, safe extraction.

The author's save uploads the whole skill dir as ONE artifact
(``<folder>/_package.zip``) via writeSkillFile + signed COS PUT; the
subscriber's download tries that single object first (readSkillFile +
signed GET + unzip) and falls back to the per-file listing flow when no
package exists. Extraction guards against zip-slip (author-controlled
input).
"""

import io
import json
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


class TestPackageUpload:
    def _run(self, tmp_path, appsync_resp):
        skill_dir = tmp_path / "demo_skill"
        (skill_dir / "code_dir").mkdir(parents=True)
        (skill_dir / "code_dir" / "a.py").write_text("pass")
        put_calls = []

        def fake_request(method, url, data=None, timeout=None):
            put_calls.append((method, url, data))
            return SimpleNamespace(status_code=200, text="")

        with patch.object(sfs, "_appsync_request", return_value=appsync_resp) as gql, \
             patch.object(sfs.http_requests, "request", side_effect=fake_request):
            ok = sfs._cn_upload_skill_package(skill_dir, dict(CTX))
        return ok, gql, put_calls

    def test_registers_and_puts_zip_bytes(self, tmp_path):
        resp = {"data": {"writeSkillFile": [
            {"filePath": "x", "uploadUrl": "https://cos/put", "method": "PUT"}]}}
        ok, gql, puts = self._run(tmp_path, resp)
        assert ok
        # writeSkillFile registered the well-known package path
        sent = gql.call_args.kwargs["variables"]["input"][0]
        assert sent["filePath"].endswith("demo_skill/_package.zip")
        assert sent["userId"] == AUTHOR
        # and the PUT body is a real zip containing the skill files
        method, url, body = puts[0]
        assert method == "PUT" and url == "https://cos/put"
        names = zipfile.ZipFile(io.BytesIO(body)).namelist()
        assert any(n.replace("\\", "/") == "code_dir/a.py" for n in names)

    def test_no_upload_url_returns_false(self, tmp_path):
        ok, _, puts = self._run(tmp_path, {"data": {"writeSkillFile": [{"filePath": "x"}]}})
        assert not ok and puts == []


class TestPackageDownload:
    def _read_resp(self, url):
        return {"data": {"readSkillFile": json.dumps([{"downloadUrl": url}])}}

    def test_zip_first_success(self, tmp_path):
        zb = _make_zip({"diagram_dir/demo_skill.json": "{}"})
        with patch.object(sfs, "_appsync_request", return_value=self._read_resp("https://cos/get")), \
             patch.object(sfs.http_requests, "get",
                          return_value=SimpleNamespace(content=zb)):
            ok = sfs._cn_try_package_download("demo_skill", AUTHOR, dict(CTX), tmp_path / "demo_skill")
        assert ok
        assert (tmp_path / "demo_skill" / "diagram_dir" / "demo_skill.json").exists()

    def test_missing_package_returns_false(self, tmp_path):
        with patch.object(sfs, "_appsync_request", return_value={"data": {"readSkillFile": "[]"}}):
            ok = sfs._cn_try_package_download("demo_skill", AUTHOR, dict(CTX), tmp_path / "demo_skill")
        assert not ok

    def test_tries_owner_prefixed_fallback_path(self, tmp_path):
        zb = _make_zip({"a.txt": "x"})
        calls = []

        def fake_gql(query, ctx, variables=None):
            calls.append(variables["filePath"])
            if variables["filePath"].startswith("wechat_"):
                return self._read_resp("https://cos/get")
            return {"data": {"readSkillFile": "[]"}}

        with patch.object(sfs, "_appsync_request", side_effect=fake_gql), \
             patch.object(sfs.http_requests, "get", return_value=SimpleNamespace(content=zb)):
            ok = sfs._cn_try_package_download("demo_skill", AUTHOR, dict(CTX), tmp_path / "d")
        assert ok
        assert calls == ["demo_skill/_package.zip",
                         f"{AUTHOR}/my_skills/demo_skill/_package.zip"]


class TestDownloadFallbackFlow:
    """_download_skill_files_cn: package hit skips listing; miss falls back."""

    def _run(self, tmp_path, package_ok, listing):
        gql_queries = []

        def fake_gql(query, ctx, variables=None):
            gql_queries.append((query, variables))
            if "listSkillFiles" in query:
                return {"data": {"listSkillFiles": json.dumps(listing)}}
            # readSkillFile: package vs regular file
            fp = variables["filePath"]
            if fp.endswith("_package.zip"):
                if package_ok:
                    return {"data": {"readSkillFile": json.dumps([{"downloadUrl": "https://cos/pkg"}])}}
                return {"data": {"readSkillFile": "[]"}}
            return {"data": {"readSkillFile": json.dumps([{"downloadUrl": f"https://cos/{fp}"}])}}

        zb = _make_zip({"from_pkg.txt": "pkg"})

        def fake_get(url, timeout=None):
            return SimpleNamespace(content=zb if url == "https://cos/pkg" else b"filebytes")

        with patch.object(sfs, "_get_cloud_context", return_value=dict(CTX)), \
             patch.object(sfs, "_get_my_skills_dir", return_value=tmp_path), \
             patch.object(sfs, "_appsync_request", side_effect=fake_gql), \
             patch.object(sfs.http_requests, "get", side_effect=fake_get), \
             patch.object(sfs.threading, "Thread", _InlineThread):
            sfs._download_skill_files_cn({"name": "demo"}, file_owner=AUTHOR)
        return gql_queries

    def test_package_hit_skips_listing(self, tmp_path):
        queries = self._run(tmp_path, package_ok=True, listing=[])
        assert not any("listSkillFiles" in q for q, _ in queries)
        assert (tmp_path / "demo_skill" / "from_pkg.txt").read_text() == "pkg"

    def test_package_miss_falls_back_to_per_file(self, tmp_path):
        listing = [{"filePath": f"{AUTHOR}/my_skills/demo_skill/code_dir/a.py"},
                   {"filePath": f"{AUTHOR}/my_skills/demo_skill/_package.zip"}]
        queries = self._run(tmp_path, package_ok=False, listing=listing)
        assert any("listSkillFiles" in q for q, _ in queries)
        # owner-prefixed path normalized under the local skills root
        assert (tmp_path / "demo_skill" / "code_dir" / "a.py").read_bytes() == b"filebytes"
        # the zip artifact itself is not downloaded as a source file
        assert not (tmp_path / "demo_skill" / "_package.zip").exists()
