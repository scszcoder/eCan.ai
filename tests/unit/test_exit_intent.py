"""Exit-intent lease: "I am shutting down on purpose — do not relaunch me".

Why this exists
---------------
eCan already records a *clean exit* flag in the heartbeat
(utils/crash_boundary.py -> runlogs/process_heartbeat.json) and the watchdog
honours it (utils/app_watchdog.py::assess). That covers the happy path.

The gap: between "the user pressed the close button" and "atexit ran" there is
a real window of seconds-to-minutes where eCan is tearing down (Qt teardown,
worker drain, proxy shutdown, session flush). If the process dies *inside*
that window — power loss, taskkill /F, OOM killer — no clean-exit flag was
ever written, so the watchdog sees "process gone, no clean exit" and relaunches
an app the user deliberately closed.

So the marker is a *lease*, not a flag: it says "I am on my way out, leave me
alone for the next N seconds". The lease is written at the *start* of the
shutdown, not at the end, and it expires by itself.

These tests are the spec. They are written before the implementation.
"""

import json
import os
import time

import pytest

from utils import exit_intent as ei

NOW = 1_800_000_000.0


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_lease(log_dir, pid, reason="user_close", grace_s=300, age_s=0):
    """Write a lease that belongs to a specific process id."""
    path = ei.exit_intent_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": reason,
        "at": time.time() - age_s,
        "grace_s": grace_s,
        "pid": pid,
    }), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# A. File-system layer
# --------------------------------------------------------------------------

def test_mark_creates_file_with_required_fields(tmp_path):
    ok = ei.mark_exiting(reason="user_close", grace_s=30, log_dir=str(tmp_path))
    assert ok is True
    data = _read(ei.exit_intent_path(str(tmp_path)))
    assert data["reason"] == "user_close"
    assert data["grace_s"] == 30
    assert data["pid"] == os.getpid()
    assert isinstance(data["at"], float)


def test_mark_creates_runlogs_dir_when_missing(tmp_path):
    target = tmp_path / "nested" / "runlogs"
    assert not target.exists()
    ei.mark_exiting(reason="x", log_dir=str(target))
    assert (target / ei.EXIT_INTENT_NAME).exists()


def test_mark_is_atomic_no_partial_file_left_behind(tmp_path):
    ei.mark_exiting(reason="x", log_dir=str(tmp_path))
    leftovers = [p.name for p in tmp_path.iterdir() if ".tmp" in p.name]
    assert leftovers == []


def test_mark_overwrites_previous_lease(tmp_path):
    ei.mark_exiting(reason="first", grace_s=10, log_dir=str(tmp_path))
    ei.mark_exiting(reason="second", grace_s=20, log_dir=str(tmp_path))
    data = _read(ei.exit_intent_path(str(tmp_path)))
    assert data["reason"] == "second"
    assert data["grace_s"] == 20


def test_mark_is_idempotent(tmp_path):
    ei.mark_exiting(reason="x", log_dir=str(tmp_path))
    first = _read(ei.exit_intent_path(str(tmp_path)))
    ei.mark_exiting(reason="x", log_dir=str(tmp_path))
    second = _read(ei.exit_intent_path(str(tmp_path)))
    assert first["reason"] == second["reason"]
    assert first["grace_s"] == second["grace_s"]


def test_mark_swallows_write_errors(tmp_path):
    """A failing marker must never prevent the app from shutting down."""
    class Boom:
        def write_text(self, *a, **k):
            raise OSError("disk full")
        def replace(self, *a, **k):
            raise OSError("disk full")

    original = ei.exit_intent_path
    ei.exit_intent_path = lambda log_dir=None: Boom()
    try:
        assert ei.mark_exiting(reason="x", log_dir=str(tmp_path)) is False
    finally:
        ei.exit_intent_path = original


# --------------------------------------------------------------------------
# A/B. Reading: validity, expiry, clock skew, hostile files
# --------------------------------------------------------------------------

def test_is_exiting_false_when_no_file(tmp_path):
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_is_exiting_true_within_grace(tmp_path):
    ei.mark_exiting(reason="x", grace_s=30, log_dir=str(tmp_path))
    now = time.time()
    assert ei.is_exiting(log_dir=str(tmp_path), now=now) is True
    assert ei.is_exiting(log_dir=str(tmp_path), now=now + 29) is True


def test_is_exiting_false_after_grace(tmp_path):
    ei.mark_exiting(reason="x", grace_s=30, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 31) is False


def test_is_exiting_false_for_empty_file(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("", encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_is_exiting_false_for_corrupt_json(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_is_exiting_false_for_oversized_file(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x" * (ei.MAX_INTENT_BYTES + 1), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_is_exiting_false_when_grace_s_missing(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"reason": "x", "at": time.time()}), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_is_exiting_handles_ntp_clock_rewind(tmp_path):
    """Clock jumping backwards must not make the lease immortal *or* expire it."""
    ei.mark_exiting(reason="x", grace_s=30, log_dir=str(tmp_path))
    at = time.time()
    # now is 100s *before* the marker was written
    assert ei.is_exiting(log_dir=str(tmp_path), now=at - 100) is True


def test_is_exiting_handles_future_timestamp(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"reason": "x", "at": time.time() + 3600, "grace_s": 30}),
                 encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time()) is True


def test_is_exiting_zero_grace_expires_immediately(tmp_path):
    ei.mark_exiting(reason="x", grace_s=0, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 0.001) is False


def test_is_exiting_negative_grace_expires_immediately(tmp_path):
    ei.mark_exiting(reason="x", grace_s=-5, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 0.001) is False


def test_is_exiting_accepts_infinite_grace(tmp_path):
    """`uninstall` wants a permanent lease: grace_s = inf."""
    ei.mark_exiting(reason="uninstall", grace_s=float("inf"), log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path), now=time.time() + 10**9) is True


def test_is_exiting_handles_unicode_reason(tmp_path):
    ei.mark_exiting(reason="用户主动关闭", grace_s=30, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True
    assert _read(ei.exit_intent_path(str(tmp_path)))["reason"] == "用户主动关闭"


def test_is_exiting_handles_emoji_reason(tmp_path):
    ei.mark_exiting(reason="quit 🚀", grace_s=30, log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_is_exiting_defaults_reason_when_empty(tmp_path):
    ei.mark_exiting(reason="", grace_s=30, log_dir=str(tmp_path))
    data = _read(ei.exit_intent_path(str(tmp_path)))
    assert data["reason"]


def test_is_exiting_does_not_raise_on_permission_error(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o000)
    try:
        assert ei.is_exiting(log_dir=str(tmp_path)) in (True, False)
    finally:
        if p.exists():
            os.chmod(p, 0o600)


# --------------------------------------------------------------------------
# Clearing
# --------------------------------------------------------------------------

def test_clear_removes_lease(tmp_path):
    ei.mark_exiting(reason="x", grace_s=30, log_dir=str(tmp_path))
    ei.clear_exit_intent(log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_clear_is_noop_when_no_file(tmp_path):
    ei.clear_exit_intent(log_dir=str(tmp_path))   # must not raise


def test_clear_is_noop_on_unreadable_file(tmp_path):
    p = ei.exit_intent_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    os.chmod(p, 0o000)
    try:
        ei.clear_exit_intent(log_dir=str(tmp_path))   # must not raise
    finally:
        if p.exists():
            os.chmod(p, 0o600)


# --------------------------------------------------------------------------
# D. Watchdog integration — the whole point of the module
# --------------------------------------------------------------------------

def test_watchdog_does_not_relaunch_during_exit_lease(tmp_path, monkeypatch):
    """A process that is shutting down must not be treated as 'crashed'."""
    from utils import app_watchdog as wd
    hb = {"pid": 4242, "updated_at": NOW - 5, "started_at": NOW - 3600,
          "phase": "main_loop:running", "main_loop_tick": NOW - 5, "clean_exit": False}
    assert wd.assess(hb, NOW, alive=False) == "crashed"        # without the lease
    assert wd.assess(hb, NOW, alive=False, exiting=True) == "exiting"


def test_watchdog_still_relaunches_after_lease_expired(tmp_path, monkeypatch):
    from utils import app_watchdog as wd
    hb = {"pid": 4242, "updated_at": NOW - 5, "started_at": NOW - 3600,
          "phase": "main_loop:running", "main_loop_tick": NOW - 5, "clean_exit": False}
    assert wd.assess(hb, NOW, alive=False, exiting=False) == "crashed"


def test_watchdog_does_not_kill_a_shutting_down_process(tmp_path, monkeypatch):
    """During the lease the process is alive but its loop is idle — it must not
    be judged 'hung' and killed."""
    from utils import app_watchdog as wd
    hb = {"pid": 4242, "updated_at": NOW - 5, "started_at": NOW - 3600,
          "phase": "main_loop:running", "main_loop_tick": NOW - 700, "clean_exit": False}
    assert wd.assess(hb, NOW, alive=True) == "hung"
    assert wd.assess(hb, NOW, alive=True, exiting=True) == "exiting"


def test_watchdog_clean_exit_still_wins_over_lease(tmp_path):
    """Backward compatibility: the legacy clean_exit flag must keep working."""
    from utils import app_watchdog as wd
    hb = {"pid": 4242, "updated_at": NOW - 5, "started_at": NOW - 3600,
          "phase": "main_loop:running", "main_loop_tick": NOW - 5, "clean_exit": True}
    assert wd.assess(hb, NOW, alive=False, exiting=True) == "quit"


def test_watchdog_run_does_not_launch_while_lease_active(monkeypatch, tmp_path):
    """End-to-end on the real loop: an exiting process must not be relaunched."""
    from utils import app_watchdog as wd
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    now = time.time()
    hb = {"pid": 4242, "updated_at": now - 5, "started_at": now - 3600,
          "phase": "main_loop:running", "main_loop_tick": now - 5, "clean_exit": False}
    monkeypatch.setattr(wd, "read_heartbeat", lambda _p: hb)
    monkeypatch.setattr(wd, "process_alive", lambda h: False)
    launched = []
    monkeypatch.setattr(wd, "_launch", lambda: launched.append("launch"))

    sleeps = {"n": 0}

    def fake_sleep(_s):
        sleeps["n"] += 1
        if sleeps["n"] > 1:
            raise SystemExit

    monkeypatch.setattr(wd.time, "sleep", fake_sleep)
    # The lease must belong to the process the watchdog is watching.
    _write_lease(str(tmp_path), pid=4242, grace_s=300, age_s=1)
    try:
        wd.run()
    except SystemExit:
        pass
    assert launched == []


def test_watchdog_run_launches_when_no_lease(monkeypatch, tmp_path):
    from utils import app_watchdog as wd
    monkeypatch.setattr(wd, "runlogs_dir", lambda: tmp_path)
    now = time.time()
    hb = {"pid": 4242, "updated_at": now - 5, "started_at": now - 3600,
          "phase": "main_loop:running", "main_loop_tick": now - 5, "clean_exit": False}
    monkeypatch.setattr(wd, "read_heartbeat", lambda _p: hb)
    monkeypatch.setattr(wd, "process_alive", lambda h: False)
    launched = []
    monkeypatch.setattr(wd, "_launch", lambda: launched.append("launch"))

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
    # No lease -> the app must be relaunched (once per poll round).
    assert launched
