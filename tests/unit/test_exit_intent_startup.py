"""Startup must clear a stale shutdown lease and install the exit handlers.

Two things have to happen when eCan starts:

1. **Clear a stale lease.** The previous process may have died while holding
   a lease (power loss during a quit, kill -9). That lease would make the
   watchdog stand down for the whole grace window even though the app is now
   running and healthy — so a crash in that window would go unnoticed. The
   lease belongs to a *process*, and a new process starts without one.

2. **Install the exit-signal handlers**, so that a SIGTERM/SIGINT records the
   intent before the process dies.

Both must be safe to call on every startup and must never raise.
"""

import json
import os
import time

import pytest

from utils import exit_intent as ei


def _write_lease_as_other_process(log_dir, reason="user_exit", grace_s=600):
    """Write a lease that belongs to a *previous* process."""
    path = ei.exit_intent_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "reason": reason,
        "at": time.time(),
        "grace_s": grace_s,
        "pid": os.getpid() + 1,
    }), encoding="utf-8")
    return path


def test_startup_clears_a_stale_lease(tmp_path):
    _write_lease_as_other_process(str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True
    ei.on_startup(log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_startup_is_safe_without_a_lease(tmp_path):
    ei.on_startup(log_dir=str(tmp_path))   # must not raise
    assert ei.is_exiting(log_dir=str(tmp_path)) is False


def test_startup_keeps_a_lease_written_by_this_process(tmp_path):
    """The app itself may have taken a lease before calling on_startup
    (e.g. a restart triggered by an OTA update). Do not drop it."""
    ei.mark_exiting(reason="ota_update", grace_s=600, log_dir=str(tmp_path))
    ei.on_startup(log_dir=str(tmp_path))
    assert ei.is_exiting(log_dir=str(tmp_path)) is True


def test_startup_installs_the_exit_signal_handlers(monkeypatch, tmp_path):
    installed = []
    monkeypatch.setattr(ei, "_install_handlers", lambda: installed.append(True))
    ei.on_startup(log_dir=str(tmp_path))
    assert installed == [True]


def test_startup_never_raises_when_the_lease_cannot_be_cleared(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("permission denied")
    monkeypatch.setattr(ei, "clear_exit_intent", boom)
    ei.on_startup(log_dir=str(tmp_path))   # must not raise


def test_startup_never_raises_when_signal_install_fails(monkeypatch, tmp_path):
    def boom():
        raise RuntimeError("not on the main thread")
    monkeypatch.setattr(ei, "_install_handlers", boom)
    ei.on_startup(log_dir=str(tmp_path))   # must not raise
