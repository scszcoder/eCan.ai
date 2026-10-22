"""The uninstaller and the OTA installer must both stop the watchdog.

Two situations where the watchdog must *not* bring eCan back:

**Uninstall.** The user removed the app. The unattended logon task and the
watchdog would keep relaunching an executable that no longer exists, and the
watchdog would log a crash-loop forever. The uninstaller therefore writes a
permanent lease and removes the logon task.

**OTA update.** The installer replaces the running executable. While that
happens, the old build must not be relaunched.

Inno Setup cannot call Python, so the uninstaller writes the lease file
itself (plain JSON, UTF-8). The format must therefore stay trivially
compatible with what ``utils/exit_intent.py`` reads — these tests pin that
contract in both directions.
"""

import json
import os
import time

import pytest

from utils import exit_intent as ei


# --------------------------------------------------------------------------
# The lease file format is a contract with the Inno Setup uninstaller.
# --------------------------------------------------------------------------

def test_lease_format_is_what_the_installer_writes(tmp_path):
    """A hand-written lease (as the Inno Setup [Code] section writes it) must
    be understood by the Python side."""
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "uninstall",
        "at": time.time(),
        "grace_s": "inf",          # the installer writes a string
        "pid": 0,
    }), encoding="utf-8")

    lease = ei.read_exit_lease(str(tmp_path))
    assert lease is not None
    assert lease["reason"] == "uninstall"
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_lease_format_accepts_numeric_grace(tmp_path):
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "uninstall", "at": time.time(), "grace_s": 999999, "pid": 0,
    }), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_lease_format_accepts_string_grace_numbers(tmp_path):
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "ota_update", "at": time.time(), "grace_s": "600", "pid": 0,
    }), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_lease_format_rejects_a_garbage_grace(tmp_path):
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "uninstall", "at": time.time(), "grace_s": "forever", "pid": 0,
    }), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_lease_format_rejects_a_missing_at(tmp_path):
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"reason": "uninstall", "grace_s": "inf"}), encoding="utf-8")
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


# --------------------------------------------------------------------------
# The watchdog must stand down once the app is gone.
# --------------------------------------------------------------------------

def test_watchdog_stands_down_after_a_permanent_lease(monkeypatch, tmp_path):
    """With a permanent lease the watchdog must not relaunch the app."""
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
    path = ei.exit_intent_path(str(tmp_path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": "uninstall", "at": now, "grace_s": "inf", "pid": 0,
    }), encoding="utf-8")
    try:
        wd.run()
    except SystemExit:
        pass
    assert launched == []


# --------------------------------------------------------------------------
# The uninstaller also has to remove the logon task and the marker.
# --------------------------------------------------------------------------

def test_uninstall_removes_the_unattended_marker(monkeypatch, tmp_path):
    """The uninstaller must delete unattended.json, otherwise a later
    reinstall would immediately re-arm the watchdog."""
    from utils import unattended as ua
    marker = tmp_path / "unattended.json"
    marker.write_text(json.dumps({"enabled": True}), encoding="utf-8")
    monkeypatch.setattr(ua, "_marker", lambda: marker)
    assert ua.is_enabled() is True
    ua.disable_for_uninstall(log_dir=str(tmp_path))
    assert not marker.exists()
    assert ua.is_enabled() is False


def test_uninstall_is_safe_when_nothing_is_there(tmp_path):
    from utils import unattended as ua
    ua.disable_for_uninstall(log_dir=str(tmp_path))   # must not raise


def test_uninstall_writes_a_permanent_lease(tmp_path):
    from utils import unattended as ua
    ua.disable_for_uninstall(log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True
    lease = ei.read_exit_lease(str(tmp_path))
    assert lease["reason"] == "uninstall"
