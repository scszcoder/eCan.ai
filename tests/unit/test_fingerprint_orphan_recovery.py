"""An orphaned profile browser is recovered, never attached to.

When the process that launched a profile dies without closing it -- a crash, a
kill, or an exit that skipped close_all -- the browser is left running with the
SOCKS relay gone. It then has NO proxy, so reaching the site through it would
come from this machine's own address: the one thing an anti-detect profile must
never do.

Attaching is therefore refused. But refusing alone left the user hunting for a
stray Chromium window before anything could run again (observed 2026-09-18: a
leftover browser on port 9668 failed every retry of the etsy skill). Since an
orphan has no proxy, nothing can legitimately still be using it, so it is closed
-- gracefully, which is also what flushes the session the profile exists to keep
-- and a fresh one is launched with a fresh relay.
"""

import pytest

from agent.ec_skills.browser_use_extension.fingerprint import (
    fingerprint_browser as fb,
    profile_registry as reg,
)


@pytest.fixture
def profile(tmp_path, monkeypatch):
    """A registered profile with a proxy, rooted in tmp_path."""
    monkeypatch.setattr(reg, "_registry_path", lambda: tmp_path / "browser_profiles.json")
    monkeypatch.setenv("ECAN_BROWSER_DATA_ROOT", str(tmp_path / "data"))

    class _Keyring:
        store = {}
        def set_password(self, s, a, p): self.store[(s, a)] = p
        def get_password(self, s, a): return self.store.get((s, a))
        def delete_password(self, s, a): self.store.pop((s, a), None)

    import sys
    monkeypatch.setitem(sys.modules, "keyring", _Keyring())
    rec = reg.make_profile("etsy", proxy={"scheme": "socks5", "host": "p.example",
                                          "port": 1080, "username": "u"})
    reg.save_profile(rec, proxy_password="s3cret")
    monkeypatch.setattr(fb, "_RUNNING", {})
    return reg.get_profile("etsy")


def _write_port_file(profile, port, relay_port, pid=4242):
    import json
    from pathlib import Path
    udd = Path(profile["user_data_dir"])
    udd.mkdir(parents=True, exist_ok=True)
    (udd / ".ecan_cdp.json").write_text(
        json.dumps({"port": port, "pid": pid, "relay_port": relay_port,
                    "started": 1}), encoding="utf-8")


def _stub_launch(monkeypatch, new_port):
    """Make a fresh launch succeed without starting a real browser."""
    calls = {"popen": 0, "closed": []}

    monkeypatch.setattr(fb, "resolve_browser_path", lambda p: "chrome.exe")
    monkeypatch.setattr(fb, "_proxy_flags", lambda p: ([], lambda: None, 55555))
    monkeypatch.setattr(fb, "_free_port", lambda: new_port)

    class _Proc:
        pid = 9999
        def poll(self): return None

    def _popen(argv, **kw):
        calls["popen"] += 1
        return _Proc()

    monkeypatch.setattr(fb.subprocess, "Popen", _popen)
    return calls


def test_an_orphan_is_closed_and_relaunched(profile, monkeypatch):
    calls = _stub_launch(monkeypatch, new_port=7100)

    # Old browser answers on 9668; the new one answers on 7100.
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0:
                        {"Browser": "Chrome/1"} if port in (9668, 7100) else None)
    # Its relay is dead; nothing is listening anywhere.
    monkeypatch.setattr(fb, "_port_open", lambda port, timeout=1.0: False)

    closed = []
    monkeypatch.setattr(fb, "close_profile",
                        lambda pid, grace=15.0: closed.append(pid) or True)

    _write_port_file(profile, port=9668, relay_port=51500)
    br = fb.launch_profile("etsy")

    assert closed == ["etsy"], "the orphan must be closed, not left running"
    assert calls["popen"] == 1, "a fresh browser must be launched"
    assert br.attached is False, "the recovered run owns its browser"
    assert br.debug_port == 7100, "and must not reuse the orphan's port"


def test_a_healthy_running_browser_is_still_attached_to(profile, monkeypatch):
    """Recovery must not become 'always restart'."""
    _stub_launch(monkeypatch, new_port=7100)
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0: {"Browser": "Chrome/1"} if port == 9668 else None)
    monkeypatch.setattr(fb, "_port_open", lambda port, timeout=1.0: True)  # relay alive

    closed = []
    monkeypatch.setattr(fb, "close_profile",
                        lambda pid, grace=15.0: closed.append(pid) or True)

    _write_port_file(profile, port=9668, relay_port=51500)
    br = fb.launch_profile("etsy")

    assert closed == [], "a live browser with a working relay must not be closed"
    assert br.attached is True
    assert br.debug_port == 9668


def test_when_the_orphan_cannot_be_closed_we_refuse_rather_than_leak(profile, monkeypatch):
    """Failing closed is still the fallback: never attach to a proxy-less browser."""
    _stub_launch(monkeypatch, new_port=7100)
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0: {"Browser": "Chrome/1"} if port == 9668 else None)
    monkeypatch.setattr(fb, "_port_open", lambda port, timeout=1.0: False)
    monkeypatch.setattr(fb, "close_profile", lambda pid, grace=15.0: False)

    _write_port_file(profile, port=9668, relay_port=51500)
    with pytest.raises(RuntimeError, match="own IP"):
        fb.launch_profile("etsy")


def test_a_profile_with_no_proxy_is_not_treated_as_orphaned(profile, monkeypatch):
    """relay_port 0 means a direct profile, which is a healthy configuration."""
    _stub_launch(monkeypatch, new_port=7100)
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0: {"Browser": "Chrome/1"} if port == 9668 else None)
    monkeypatch.setattr(fb, "_port_open", lambda port, timeout=1.0: False)

    closed = []
    monkeypatch.setattr(fb, "close_profile",
                        lambda pid, grace=15.0: closed.append(pid) or True)

    _write_port_file(profile, port=9668, relay_port=0)
    br = fb.launch_profile("etsy")

    assert closed == []
    assert br.attached is True


def test_the_app_closes_profiles_on_quit():
    """The orphan exists because nothing called close_all on shutdown."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "main.py"
    text = src.read_text(encoding="utf-8", errors="ignore")
    assert "close_all()" in text and "_cleanup_on_quit" in text, (
        "main.py no longer closes fingerprint profiles on quit; every exit "
        "will orphan a browser with a dead proxy relay"
    )
