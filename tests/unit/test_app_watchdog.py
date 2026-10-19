"""Unattended mode: the watchdog starts eCan, relaunches it after a crash or a
hang, leaves it alone when the user quit, and cannot restart-loop; the switch
creates/removes the logon task without a console window."""
import json
import time

import pytest

from utils import app_watchdog as wd

NOW = 1_800_000_000.0


def hb(**kw):
    base = {"pid": 1, "updated_at": NOW - 5, "started_at": NOW - 3600, "phase": "main_loop:running",
            "main_loop_tick": NOW - 5, "clean_exit": False}
    base.update(kw)
    return base


@pytest.mark.parametrize("beat, alive, want", [
    (None, False, "not_running"),
    (hb(), True, "ok"),
    (hb(), False, "crashed"),
    (hb(clean_exit=True), False, "quit"),
    (hb(updated_at=NOW - 300), True, "frozen"),                          # whole process stuck
    (hb(main_loop_tick=NOW - 700), True, "hung"),                        # main loop stuck
    (hb(main_loop_tick=NOW - 700, phase="startup:webgui"), True, "ok"),  # never during startup
    (hb(main_loop_tick=NOW - 700, started_at=NOW - 600), True, "ok"),    # not right after start
    (hb(main_loop_tick=None), True, "ok"),                               # older build: no tick
])
def test_assess(beat, alive, want):
    assert wd.assess(beat, NOW, alive) == want


def _drive(monkeypatch, tmp_path, beats, alive_seq):
    """Run the real loop over a scripted sequence of heartbeats."""
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    events = []
    it = iter(zip(beats, alive_seq))
    state = {}

    def fake_read(_p):
        try:
            state["cur"] = next(it)
        except StopIteration:
            raise SystemExit
        return state["cur"][0]

    monkeypatch.setattr(wd, "read_heartbeat", fake_read)
    monkeypatch.setattr(wd, "process_alive", lambda h: state["cur"][1])
    monkeypatch.setattr(wd, "_launch", lambda: events.append("launch"))
    monkeypatch.setattr(wd, "_kill", lambda pid: events.append(f"kill {pid}"))
    monkeypatch.setattr(wd.time, "sleep", lambda s: None)
    monkeypatch.setattr(wd.time, "time", lambda: NOW)
    try:
        rc = wd.run()
    except SystemExit:
        rc = None
    return events, rc


def test_logon_start_launches_even_after_a_previous_clean_exit(monkeypatch, tmp_path):
    events, _ = _drive(monkeypatch, tmp_path, [hb(clean_exit=True)], [False])
    assert events == ["launch"]


def test_hung_app_is_killed_and_relaunched(monkeypatch, tmp_path):
    events, _ = _drive(monkeypatch, tmp_path, [hb(), hb(pid=7, main_loop_tick=NOW - 700)], [True, True])
    assert events == ["kill 7", "launch"]


def test_user_quit_ends_the_watchdog(monkeypatch, tmp_path):
    events, rc = _drive(monkeypatch, tmp_path, [hb(), hb(clean_exit=True)], [True, False])
    assert events == [] and rc == 0


def test_crash_loop_is_capped(monkeypatch, tmp_path):
    n = wd.MAX_RESTARTS + 3
    monkeypatch.setattr(wd, "LAUNCH_GRACE_SEC", 0)
    events, _ = _drive(monkeypatch, tmp_path, [hb()] + [hb()] * n, [True] + [False] * n)
    assert events.count("launch") == wd.MAX_RESTARTS


def test_switch_creates_and_removes_the_logon_task_without_a_window(monkeypatch, tmp_path):
    from utils import unattended as ua
    calls = []
    monkeypatch.setattr(ua, "_marker", lambda: tmp_path / "unattended.json")
    monkeypatch.setattr(ua, "ensure_watchdog_running", lambda: calls.append("ensure"))
    monkeypatch.setattr(ua, "_stop_watchdog", lambda: calls.append("stop"))

    class R:
        returncode = 0
        stdout = stderr = ""

    def fake_run(cmd, **kw):
        calls.append((cmd[1], kw.get("creationflags")))
        return R()

    monkeypatch.setattr(ua.subprocess, "run", fake_run)
    monkeypatch.setattr(ua.sys, "platform", "win32")
    on = ua.set_enabled(True)
    assert on["enabled"] and on["logon_task"] and ua.is_enabled()
    assert ("/Create", ua._NO_WINDOW) in calls and "ensure" in calls
    ua.set_enabled(False)
    assert not ua.is_enabled() and ("/Delete", ua._NO_WINDOW) in calls and "stop" in calls
