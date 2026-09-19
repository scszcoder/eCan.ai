"""Reuse a profile's browser if it is genuinely usable; otherwise start fresh.

The question a run has to answer is "is there a Chromium already running THIS
profile, and can I drive it?" -- and the answer comes from the operating
system, not from the port file we wrote. That file records what we *intended*,
and on 2026-09-18 it was wrong every way it can be: stale after the app exited
without closing the browser, and then pointing at a port the user's own Chrome
had won, so `/json/version` answered from their personal profile.

So `_running_browser_for()` looks for the process that opened this
user-data-dir, and `healthy` means it can actually be driven: its debugging
port answers CDP, and that port serves only this profile. Three outcomes:

    healthy, proxy relay alive   -> reuse it
    running but not usable       -> it also holds the profile directory, so it
                                    has to go before anything can start
    nothing running              -> launch, on a port nobody else is using
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


def _stub_env(monkeypatch, *, running=None, new_port=7100,
              relay_alive=True, port_busy=()):
    """Stand in for the machine: what is running, and which ports are taken."""
    calls = {"popen": 0, "closed": []}

    monkeypatch.setattr(fb, "_running_browser_for", lambda udd: running)
    monkeypatch.setattr(fb, "resolve_browser_path", lambda p: "chrome.exe")
    monkeypatch.setattr(fb, "_proxy_flags", lambda p: ([], lambda: None, 55555))
    monkeypatch.setattr(fb, "_free_port", lambda: new_port)
    monkeypatch.setattr(fb, "_port_open",
                        lambda port, timeout=1.0:
                        (port in port_busy) or (relay_alive and port == 55555))
    monkeypatch.setattr(fb, "_cdp_version",
                        lambda port, timeout=1.0:
                        {"Browser": "Chrome/1"} if port == new_port else None)
    monkeypatch.setattr(fb, "_port_serves_profile", lambda port, udd: True)
    monkeypatch.setattr(fb, "close_profile",
                        lambda pid, grace=15.0: calls["closed"].append(pid) or True)

    class _Proc:
        pid = 9999
        def poll(self): return None
        def terminate(self): pass

    def _popen(argv, **kw):
        calls["popen"] += 1
        calls["argv"] = argv
        return _Proc()

    monkeypatch.setattr(fb.subprocess, "Popen", _popen)
    return calls


# ── reuse ──────────────────────────────────────────────────────────────────

def test_a_healthy_loaded_browser_is_reused(profile, monkeypatch):
    """The point of the whole mechanism: don't relaunch what already works."""
    calls = _stub_env(monkeypatch,
                      running={"pid": 4242, "port": 9500, "healthy": True})
    _write_port_file(profile, port=9500, relay_port=55555)

    br = fb.launch_profile("etsy")

    assert br.attached is True
    assert br.debug_port == 9500
    assert br.pid == 4242
    assert calls["popen"] == 0, "must not start a second browser"
    assert calls["closed"] == [], "and must not close the good one"


def test_reuse_does_not_depend_on_the_port_file(profile, monkeypatch):
    """No port file at all -- discovery alone is enough to find and reuse it."""
    calls = _stub_env(monkeypatch,
                      running={"pid": 4242, "port": 9500, "healthy": True},
                      relay_alive=False)      # nothing recorded, so no relay check

    br = fb.launch_profile("etsy")

    assert br.attached is True and br.debug_port == 9500
    assert calls["popen"] == 0


# ── running, but not usable ────────────────────────────────────────────────

def test_a_browser_whose_relay_died_is_closed_and_replaced(profile, monkeypatch):
    """No relay means no proxy, so it would reach the site from our own IP."""
    calls = _stub_env(monkeypatch,
                      running={"pid": 4242, "port": 9500, "healthy": True},
                      relay_alive=False)
    _write_port_file(profile, port=9500, relay_port=51500)   # relay recorded, dead

    # After close_profile, nothing is running any more.
    seq = [{"pid": 4242, "port": 9500, "healthy": True}, None]
    monkeypatch.setattr(fb, "_running_browser_for", lambda udd: seq.pop(0) if seq else None)

    br = fb.launch_profile("etsy")

    assert calls["closed"] == ["etsy"], "the proxy-less browser must be closed"
    assert calls["popen"] == 1, "and replaced"
    assert br.attached is False


def test_an_unreachable_browser_that_survives_the_request_is_named(profile, monkeypatch):
    """It lost its debugging port to another browser, so it has no CDP
    endpoint of its own, and it still holds the profile directory. Here the
    close request does not take (the pid no longer matches this profile), so
    the user is told which window -- never forced."""
    _stub_env(monkeypatch,
              running={"pid": 37640, "port": 9228, "healthy": False})
    _write_port_file(profile, port=9228, relay_port=55555)

    with pytest.raises(RuntimeError, match="37640"):
        fb.launch_profile("etsy")


def test_an_unreachable_browser_is_not_closed_through_a_shared_port(profile, monkeypatch):
    """close_profile() talks CDP, and that port may belong to someone else's
    browser -- closing through it would shut THEIR tabs. The window-close
    request goes to the process instead, which cannot hit the wrong one."""
    calls = _stub_env(monkeypatch,
                      running={"pid": 37640, "port": 9228, "healthy": False})
    _write_port_file(profile, port=9228, relay_port=55555)

    with pytest.raises(RuntimeError):
        fb.launch_profile("etsy")
    assert calls["closed"] == [], "must not reach through an ambiguous port"


# ── nothing running ────────────────────────────────────────────────────────

def test_with_nothing_running_it_just_launches(profile, monkeypatch):
    calls = _stub_env(monkeypatch, running=None)
    br = fb.launch_profile("etsy")

    assert calls["popen"] == 1
    assert br.attached is False
    assert br.debug_port == 7100


def test_a_busy_port_is_stepped_around_even_when_requested(profile, monkeypatch):
    """The user's own Chrome on 9228 is a real setup other skills drive
    against. Our debugging port is an internal detail, so we move -- failing
    here is what left a run retrying forever on 2026-09-18."""
    calls = _stub_env(monkeypatch, running=None, new_port=7100, port_busy=(9228,))

    br = fb.launch_profile("etsy", debug_port=9228)

    assert br.debug_port == 7100, "must move off the busy port, not fail"
    assert calls["popen"] == 1
    assert f"--remote-debugging-port=7100" in calls["argv"]


# ── the port-identity helpers ──────────────────────────────────────────────

def test_a_foreign_browser_on_the_port_is_detected(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(fb, "_data_dirs_on_port",
                        lambda port: [(37640, r"C:\ecan_browser_data\etsy_kq15tpi"),
                                      (30508, r"C:\chrome_data")])
    assert fb._port_serves_profile(9228, Path(r"C:\ecan_browser_data\etsy_kq15tpi")) is False


def test_our_own_browser_alone_on_the_port_is_fine(monkeypatch):
    from pathlib import Path
    monkeypatch.setattr(fb, "_data_dirs_on_port",
                        lambda port: [(37640, r"C:\ecan_browser_data\etsy_kq15tpi")])
    assert fb._port_serves_profile(9228, Path(r"C:\ecan_browser_data\etsy_kq15tpi")) is True


def test_trailing_separator_and_case_do_not_matter(monkeypatch):
    """Windows hands back both spellings; a false mismatch would refuse runs."""
    from pathlib import Path
    monkeypatch.setattr(fb, "_data_dirs_on_port",
                        lambda port: [(1, "c:\\ECAN_browser_data\\etsy_kq15tpi\\")])
    assert fb._port_serves_profile(9228, Path(r"C:\ecan_browser_data\etsy_kq15tpi")) is True


def test_unknowable_ownership_is_not_a_failure(monkeypatch):
    """No psutil, or the OS refused the socket table: refusing every launch
    would be worse than the risk, so the caller only warns."""
    from pathlib import Path
    monkeypatch.setattr(fb, "_data_dirs_on_port", lambda port: [])
    assert fb._port_serves_profile(9228, Path(r"C:\x")) is None


def test_the_app_closes_profiles_on_quit():
    """A browser left running is what starts this whole problem."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "main.py"
    text = src.read_text(encoding="utf-8", errors="ignore")
    assert "close_all()" in text and "_cleanup_on_quit" in text, (
        "main.py no longer closes fingerprint profiles on quit; every exit "
        "will leave one running with a dead proxy relay"
    )


# ── closing a browser we own but cannot reach ──────────────────────────────

def test_an_unreachable_browser_is_asked_to_close_then_replaced(profile, monkeypatch):
    """The user should not have to hunt for a window. It is a close REQUEST,
    so Chromium still flushes the session on its way out."""
    calls = _stub_env(monkeypatch,
                      running={"pid": 12804, "port": 9228, "healthy": False})
    _write_port_file(profile, port=9228, relay_port=55555)

    asked = []
    monkeypatch.setattr(fb, "_ask_browser_to_quit",
                        lambda pid, udd, grace=20.0: asked.append(pid) or True)
    # Gone once it has been asked.
    seq = [{"pid": 12804, "port": 9228, "healthy": False},
           {"pid": 12804, "port": 9228, "healthy": False}, None]
    monkeypatch.setattr(fb, "_running_browser_for",
                        lambda udd: seq.pop(0) if seq else None)

    br = fb.launch_profile("etsy")

    assert asked == [12804], "must ask the stuck browser to close"
    assert calls["popen"] == 1, "and then launch a fresh one"
    assert br.attached is False


def test_a_browser_that_will_not_close_is_reported_not_forced(profile, monkeypatch):
    """Forcing it would lose the session the profile exists to keep."""
    _stub_env(monkeypatch, running={"pid": 12804, "port": 9228, "healthy": False})
    _write_port_file(profile, port=9228, relay_port=55555)
    monkeypatch.setattr(fb, "_ask_browser_to_quit",
                        lambda pid, udd, grace=20.0: False)

    with pytest.raises(RuntimeError, match="would not close"):
        fb.launch_profile("etsy")


def test_it_refuses_to_close_a_pid_that_is_not_this_profile(monkeypatch, tmp_path):
    """Pids get recycled between the scan and the call; closing the wrong
    process would be far worse than failing here."""
    class _Proc:
        def __init__(self, *a, **k): pass
        def cmdline(self): return ["chrome.exe", r"--user-data-dir=C:\someone_else"]
        def terminate(self): raise AssertionError("must not be reached")
        def wait(self, timeout=None): raise AssertionError("must not be reached")

    import sys, types
    fake = types.SimpleNamespace(Process=_Proc)
    monkeypatch.setitem(sys.modules, "psutil", fake)

    assert fb._ask_browser_to_quit(4242, tmp_path / "etsy_x") is False


def test_a_pid_that_already_exited_counts_as_closed(monkeypatch, tmp_path):
    class _Proc:
        def __init__(self, *a, **k): raise RuntimeError("no such process")

    import sys, types
    monkeypatch.setitem(sys.modules, "psutil", types.SimpleNamespace(Process=_Proc))
    assert fb._ask_browser_to_quit(4242, tmp_path / "etsy_x") is True


def test_renderer_processes_are_not_mistaken_for_the_browser(monkeypatch, tmp_path):
    """Chromium's renderers, GPU and utility processes all inherit
    --user-data-dir. Only the browser process owns the window and the
    debugging port, so picking a child means a close request goes nowhere --
    which is exactly how one appeared to be ignored on 2026-09-18.
    """
    udd = tmp_path / "etsy_x"

    class _P:
        def __init__(self, pid, argv):
            self.pid = pid
            self.info = {"cmdline": argv}

    procs = [
        _P(12804, ["chrome.exe", f"--user-data-dir={udd}", "--type=renderer"]),
        _P(42468, ["chrome.exe", f"--user-data-dir={udd}", "--type=gpu-process"]),
        _P(37640, ["chrome.exe", f"--user-data-dir={udd}",
                   "--remote-debugging-port=9228"]),          # the browser
    ]

    import sys, types
    monkeypatch.setitem(sys.modules, "psutil",
                        types.SimpleNamespace(process_iter=lambda attrs: procs,
                                              NoSuchProcess=Exception,
                                              AccessDenied=Exception))
    monkeypatch.setattr(fb, "_cdp_version", lambda port, timeout=1.0: None)

    found = fb._running_browser_for(udd)
    assert found["pid"] == 37640, "must find the browser, not a renderer"
    assert found["port"] == 9228
