"""Bug report from a customer PC, 2026-10-22: right after a crash the user was
not logged in (dead end), and then a one-shot upload was cut off (SSLEOFError)
with the signed URL and its token shown in the error dialog."""
from pathlib import Path

import pytest
import requests

from gui.ipc.w2p_handlers import debug_log_handler as dlh

SIGNED = ("https://bucket.cos.ap-shanghai.myqcloud.com/debug-logs/x.zip"
          "?q-ak=AKIDsecret&x-cos-security-token=TOKENSECRET")


def _ssl_drop():
    import ssl
    inner = ssl.SSLEOFError(8, "EOF occurred in violation of protocol")
    return requests.exceptions.SSLError(
        requests.packages.urllib3.exceptions.MaxRetryError(None, SIGNED, inner))


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(dlh.time, "sleep", lambda s: None)


def test_a_dropped_upload_is_retried(tmp_path, monkeypatch, no_sleep):
    z = tmp_path / "p.zip"
    z.write_bytes(b"zip")
    tries = []

    def put(url, data, headers, timeout):
        tries.append(url)
        if len(tries) < 3:
            raise _ssl_drop()
        return type("R", (), {"status_code": 200})()
    monkeypatch.setattr(dlh.http_requests, "put", put)
    assert dlh._put_zip(SIGNED, z).status_code == 200
    assert len(tries) == 3


def test_a_failed_upload_never_shows_the_signed_url(tmp_path, monkeypatch, no_sleep):
    z = tmp_path / "p.zip"
    z.write_bytes(b"zip")

    def put(*a, **k):
        raise _ssl_drop()
    monkeypatch.setattr(dlh.http_requests, "put", put)
    with pytest.raises(RuntimeError) as e:
        dlh._put_zip(SIGNED, z)
    msg = str(e.value)
    assert "SSLEOFError" in msg
    assert "TOKENSECRET" not in msg and "AKID" not in msg and "http" not in msg


@pytest.fixture
def local_only(tmp_path, monkeypatch):
    """runlogs + a Desktop in tmp; no skills, no cloud."""
    runlogs = tmp_path / "runlogs"
    runlogs.mkdir()
    (runlogs / "eCan.log").write_text("crash at 21:40\n", encoding="utf-8")
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    monkeypatch.setattr(dlh, "_get_log_path", lambda: runlogs / "eCan.log")
    monkeypatch.setattr(dlh, "_get_zip_output_path", lambda ts: runlogs / f"log_{ts}.zip")
    monkeypatch.setattr(dlh, "_find_skill_dirs", lambda ids: {})
    monkeypatch.setattr(dlh, "_get_my_prompts_dir", lambda: tmp_path / "none")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home / "Desktop"


def test_not_logged_in_keeps_the_package_and_says_where(local_only, monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: None)
    with pytest.raises(RuntimeError) as e:
        dlh.validate_bug_description("app crashed at 21:40 while two stores were open", [])
    kept = list(local_only.glob("eCan-bug-report-*.zip"))
    assert len(kept) == 1
    assert "请先登录" in str(e.value) and str(kept[0]) in str(e.value)


def test_a_failed_upload_keeps_the_package(local_only, monkeypatch, no_sleep):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: {"owner": "u1"})

    def put(*a, **k):
        raise _ssl_drop()
    monkeypatch.setattr(dlh.http_requests, "put", put)
    grant = {"uploadUrl": SIGNED, "zipKey": "debug-logs/x.zip"}
    with pytest.raises(RuntimeError) as e:
        dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], grant)
    kept = list(local_only.glob("eCan-bug-report-*.zip"))
    assert len(kept) == 1 and str(kept[0]) in str(e.value)
    assert "TOKENSECRET" not in str(e.value)
    assert not list((local_only.parent.parent / "runlogs").glob("log_*.zip"))   # temp zip gone


def test_a_successful_upload_leaves_nothing_behind(local_only, monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: {"owner": "u1"})
    monkeypatch.setattr(dlh.http_requests, "put",
                        lambda *a, **k: type("R", (), {"status_code": 200})())
    monkeypatch.setattr(dlh, "_appsync_request",
                        lambda q, ctx, v=None: {"data": {"requestDebugDone": {"message": "ok"}}})
    grant = {"uploadUrl": SIGNED, "zipKey": "debug-logs/x.zip"}
    assert dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], grant) == "ok"
    assert not list(local_only.glob("*.zip"))
    assert not list((local_only.parent.parent / "runlogs").glob("log_*.zip"))
