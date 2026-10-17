"""nas_upload reconnects once after a dead SMB connection.

2026-10-12: after a network drop the cached connection stayed dead and every
upload failed (crawler parts "0 saved, 29 failed") until the app restarted.
"""
import pytest

from agent.ec_skills.nas import ugreen_nas as nas


def test_upload_reconnects_and_retries_once(tmp_path, monkeypatch):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-")
    calls, resets = [], []

    def flaky(lp, relpath, relative_to_base):
        calls.append(relpath)
        if len(calls) == 1:
            raise RuntimeError("connection reset")
        return {"path": relpath, "bytes": 5}

    monkeypatch.setattr(nas, "_upload_once", flaky)
    monkeypatch.setenv("ECAN_NAS_UPLOAD_ROOTS", str(tmp_path))
    monkeypatch.setattr(nas, "_reset_session", lambda: resets.append(1))
    assert nas.nas_upload(str(f), "d/a.pdf")["bytes"] == 5
    assert calls == ["d/a.pdf", "d/a.pdf"] and resets == [1]


def test_second_failure_is_raised(tmp_path, monkeypatch):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-")

    def dead(lp, relpath, relative_to_base):
        raise RuntimeError("still down")

    monkeypatch.setattr(nas, "_upload_once", dead)
    monkeypatch.setenv("ECAN_NAS_UPLOAD_ROOTS", str(tmp_path))
    monkeypatch.setattr(nas, "_reset_session", lambda: None)
    with pytest.raises(RuntimeError):
        nas.nas_upload(str(f), "d/a.pdf")
