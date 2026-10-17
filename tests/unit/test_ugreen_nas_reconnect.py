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


def test_every_smb_call_carries_the_credentials(tmp_path, monkeypatch):
    # 2026-10-16: one worker's failed upload reset the shared connection cache while other
    # uploads were mid-flight; their new connections had no registered session and failed
    # "SpnegoError (7): No credentials", whole parts at a time. Calls now log in themselves.
    import io
    import sys
    import types

    calls = []

    def needs_creds(name):
        def call(*args, **kwargs):
            calls.append(name)
            if kwargs.get("username") != "u" or kwargs.get("password") != "p":
                raise RuntimeError("SpnegoError (7): No credentials were supplied")
            return io.BytesIO() if name == "open_file" else []
        return call

    fake = types.ModuleType("smbclient")
    for name in ("open_file", "makedirs", "scandir", "remove"):
        setattr(fake, name, needs_creds(name))
    fake.register_session = lambda *a, **k: None
    fake.reset_connection_cache = lambda **k: None
    monkeypatch.setitem(sys.modules, "smbclient", fake)
    monkeypatch.setattr(nas, "nas_config", lambda: {"host": "h", "share": "s", "base": "b"})
    monkeypatch.setattr(nas, "_creds", lambda: ("u", "p"))
    monkeypatch.setenv("ECAN_NAS_UPLOAD_ROOTS", str(tmp_path))
    f = tmp_path / "a.pdf"
    f.write_bytes(b"%PDF-")
    nas._session_ready.clear()
    assert nas.nas_upload(str(f), "d/a.pdf")["bytes"] == 5
    assert nas.nas_list("d") == []
    assert {"open_file", "makedirs", "scandir"} <= set(calls)
