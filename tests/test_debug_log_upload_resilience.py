"""Bug report from a customer PC, 2026-10-22: right after a crash the user was
not logged in (dead end), and then a one-shot upload was cut off (SSLEOFError)
with the signed URL and its token shown in the error dialog."""
import types
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
    """runlogs in tmp; no skills, no cloud; the background uploader is not started."""
    runlogs = tmp_path / "runlogs"
    runlogs.mkdir()
    (runlogs / "eCan.log").write_text("crash at 21:40\n", encoding="utf-8")
    monkeypatch.setattr(dlh, "_get_log_path", lambda: runlogs / "eCan.log")
    monkeypatch.setattr(dlh, "_get_zip_output_path", lambda ts: runlogs / f"log_{ts}.zip")
    monkeypatch.setattr(dlh, "_find_skill_dirs", lambda ids: {})
    monkeypatch.setattr(dlh, "_get_my_prompts_dir", lambda: tmp_path / "none")
    started = []
    monkeypatch.setattr(dlh, "_start_pending_uploader", lambda: started.append(1))
    return types.SimpleNamespace(runlogs=runlogs, pending=runlogs / dlh.PENDING_SUBDIR,
                                 started=started)


def _waiting(env):
    return sorted(env.pending.glob("report_*.zip")) if env.pending.is_dir() else []


def test_not_logged_in_is_not_a_dead_end(local_only, monkeypatch):
    # Right after a crash, before login: no error -- the dialog goes on, and the
    # report is saved and uploads by itself later.
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: None)
    verdict = dlh.validate_bug_description("app crashed at 21:40 with two stores open", [])
    assert verdict["status"] == "offline"
    msg = dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], None)
    assert msg.startswith(dlh.QUEUED_MARK) and "无需任何操作" in msg
    assert len(_waiting(local_only)) == 1 and local_only.started
    assert not list(local_only.runlogs.glob("log_*.zip"))           # no temp zip left


def test_a_cut_off_upload_is_saved_for_later_not_failed(local_only, monkeypatch, no_sleep):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: {"owner": "u1"})

    def put(*a, **k):
        raise _ssl_drop()
    monkeypatch.setattr(dlh.http_requests, "put", put)
    grant = {"uploadUrl": SIGNED, "zipKey": "debug-logs/x.zip"}
    msg = dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], grant)
    assert msg.startswith(dlh.QUEUED_MARK) and "TOKENSECRET" not in msg
    assert len(_waiting(local_only)) == 1
    assert not list(local_only.runlogs.glob("log_*.zip"))


def test_a_waiting_report_uploads_by_itself_once_online(local_only, monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: None)
    dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], None)
    assert dlh.upload_pending_once() == 0                         # still not logged in
    assert len(_waiting(local_only)) == 1

    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: {"owner": "u1"})
    monkeypatch.setattr(dlh, "_request_debug", lambda ctx, owner, ids, desc:
                        ("ok", {"uploadUrl": SIGNED, "zipKey": "debug-logs/y.zip"}))
    puts, done = [], []
    monkeypatch.setattr(dlh.http_requests, "put", lambda url, data, headers, timeout:
                        puts.append(url) or type("R", (), {"status_code": 200})())
    monkeypatch.setattr(dlh, "_appsync_request", lambda q, ctx, v=None:
                        done.append(v) or {"data": {"requestDebugDone": {}}})
    assert dlh.upload_pending_once() == 1
    assert puts and done[0]["zipKey"] == "debug-logs/y.zip"
    assert done[0]["description"] == "app crashed at 21:40"
    assert not _waiting(local_only) and not list(local_only.pending.glob("*.json"))


def test_waiting_reports_are_not_packed_into_the_next_report(local_only, monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: None)
    dlh.perform_log_analysis_upload(["s1"], "first report", [], None)
    import zipfile
    out = local_only.runlogs / "check.zip"
    with zipfile.ZipFile(out, "w") as zf:
        dlh._add_runlogs_dir(zf, local_only.runlogs, exclude=out)
        names = zf.namelist()
    assert not [n for n in names if dlh.PENDING_SUBDIR in n]


def test_a_successful_upload_leaves_nothing_behind(local_only, monkeypatch):
    monkeypatch.setattr(dlh, "_get_cloud_context", lambda: {"owner": "u1"})
    monkeypatch.setattr(dlh.http_requests, "put",
                        lambda *a, **k: type("R", (), {"status_code": 200})())
    monkeypatch.setattr(dlh, "_appsync_request",
                        lambda q, ctx, v=None: {"data": {"requestDebugDone": {"message": "ok"}}})
    grant = {"uploadUrl": SIGNED, "zipKey": "debug-logs/x.zip"}
    assert dlh.perform_log_analysis_upload(["s1"], "app crashed at 21:40", [], grant) == "ok"
    assert not _waiting(local_only) and not local_only.started
    assert not list(local_only.runlogs.glob("log_*.zip"))
