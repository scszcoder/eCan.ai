"""The watchdog must distinguish a *live* lease from a leftover one.

A lease is only meaningful for the process that wrote it. Two situations
must not be confused with "the app is quitting right now":

**Logon.** The Windows logon task starts the watchdog at user login. The app
is not running yet, and the appdata folder still holds the lease of the
previous session (the user closed eCan and then rebooted). The watchdog must
start the app — it must not sit out the leftover lease.

**Uninstall.** The uninstaller writes a permanent lease and removes the logon
task. A watchdog that is already running must stop, not linger forever
waiting for a lease that never expires.
"""

import json
import time

import pytest

from utils import exit_intent as ei


def _write_lease(log_dir, reason="user_exit", grace_s=300, age_s=0):
    path = ei.exit_intent_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": reason, "at": time.time() - age_s,
        "grace_s": grace_s, "pid": 4242,
    }), encoding="utf-8")
    return path


def _hb(updated_at, pid=4242):
    return {"pid": pid, "updated_at": updated_at, "started_at": updated_at - 3600,
            "phase": "main_loop:running", "main_loop_tick": updated_at, "clean_exit": False}


def _run_watchdog(monkeypatch, tmp_path, hb, launches):
    from utils import app_watchdog as wd
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    monkeypatch.setattr(wd, "read_heartbeat", lambda _p: hb)
    monkeypatch.setattr(wd, "process_alive", lambda h: False)
    monkeypatch.setattr(wd, "_launch", lambda: launches.append("launch"))
    sleeps = {"n": 0}

    def fake_sleep(_s):
        sleeps["n"] += 1
        if sleeps["n"] > 1:
            raise SystemExit

    monkeypatch.setattr(wd.time, "sleep", fake_sleep)
    try:
        wd.run()
    except SystemExit:
        pass


def test_logon_with_a_leftover_lease_still_starts_the_app(monkeypatch, tmp_path):
    """The watchdog starts at logon; the app must come up, not wait out a
    lease left behind by the previous session."""
    launches = []
    now = time.time()
    # The heartbeat is from the previous session — hours old, different pid.
    _write_lease(str(tmp_path), grace_s=300, age_s=10)
    _run_watchdog(monkeypatch, tmp_path, _hb(now - 3600, pid=777), launches)
    assert launches, "the app must be started at logon despite a leftover lease"


def test_logon_with_a_matching_pid_but_stale_heartbeat_still_starts(monkeypatch, tmp_path):
    """Even with the same pid recorded, a stale heartbeat means the lease is
    not about the process that is running now."""
    launches = []
    now = time.time()
    _write_lease(str(tmp_path), grace_s=300, age_s=10)
    _run_watchdog(monkeypatch, tmp_path, _hb(now - 3600, pid=4242), launches)
    assert launches, "a stale heartbeat must not silence the watchdog"


def test_a_fresh_lease_on_a_fresh_heartbeat_stops_the_relaunch(monkeypatch, tmp_path):
    """The opposite case: the app was running a moment ago and is quitting
    now. The watchdog must not relaunch it."""
    launches = []
    now = time.time()
    _write_lease(str(tmp_path), grace_s=300, age_s=1)
    _run_watchdog(monkeypatch, tmp_path, _hb(now - 1), launches)
    assert launches == []


def test_a_permanent_lease_stops_the_watchdog(monkeypatch, tmp_path):
    """An uninstall lease never expires — the watchdog must give up instead of
    lingering forever."""
    from utils import app_watchdog as wd
    launches = []
    now = time.time()
    _write_lease(str(tmp_path), reason="uninstall", grace_s="inf", age_s=1)
    _run_watchdog(monkeypatch, tmp_path, _hb(now - 1), launches)
    assert launches == []


def test_the_lease_is_ignored_when_the_heartbeat_is_stale():
    from utils import app_watchdog as wd
    now = time.time()
    lease = {"reason": "user_exit", "at": now, "grace_s": 300.0, "pid": 4242}
    stale = _hb(now - 3600)
    assert wd.should_honour_lease(stale, now, lease) is False
    fresh = _hb(now - 1)
    assert wd.should_honour_lease(fresh, now, lease) is True


def test_a_lease_without_a_heartbeat_is_not_honoured():
    from utils import app_watchdog as wd
    lease = {"reason": "user_exit", "at": time.time(), "grace_s": 300.0, "pid": 4242}
    assert wd.should_honour_lease(None, time.time(), lease) is False


def test_a_lease_for_a_different_process_is_not_honoured():
    from utils import app_watchdog as wd
    now = time.time()
    lease = {"reason": "user_exit", "at": now, "grace_s": 300.0, "pid": 9999}
    assert wd.should_honour_lease(_hb(now - 1), now, lease) is False


def test_a_permanent_lease_is_detected():
    from utils import app_watchdog as wd
    lease = {"reason": "uninstall", "at": time.time(), "grace_s": float("inf"), "pid": 1}
    assert wd.is_permanent_lease(lease) is True
    assert wd.is_permanent_lease({"reason": "user_exit", "at": time.time(),
                                  "grace_s": 120.0, "pid": 1}) is False
    assert wd.is_permanent_lease(None) is False
