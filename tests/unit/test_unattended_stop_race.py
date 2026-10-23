"""Regression tests for the start/stop race in unattended mode.

The bug
-------
``stop_watchdog()`` terminated the watchdog and returned immediately:
``psutil.Process.terminate()`` sends SIGTERM and does not wait for the
process to die. The watchdog is in the middle of its poll loop, so it
may still be alive — and still visible — for a moment afterwards.

``ensure_watchdog_running()`` decides whether a watchdog is already up
by asking ``_watchdog_pid()``, which reads the lock file and checks
that the pid is alive and its cmdline contains ``--watchdog``. A
watchdog that has been *sent* SIGTERM but has not died yet satisfies
both checks.

So the sequence "log out, then log back in" can lose the watchdog
entirely:

    1. logout  -> stop_watchdog() -> SIGTERM sent, returns immediately
    2. login   -> ensure_watchdog_running() -> _watchdog_pid() still
                  returns the dying watchdog's pid -> "a watchdog is
                  already running" -> returns without starting one
    3. the dying watchdog dies

The result is that unattended mode is silently dead for the rest of
the session: a crash of eCan is no longer covered, and nothing reports
it, because the thing that would have reported it is the thing that
did not start.

This is the mirror image of the bug fixed in
``test_watchdog_login_gating.py``: that one was "the watchdog was armed
where it should not have been", this one is "the watchdog was not armed
where it should have been".

The fix
-------
``stop_watchdog()`` waits for the process to actually go away before
returning, and escalates to SIGKILL if it does not. After it returns,
there is no watchdog left to be seen, so the next
``ensure_watchdog_running()`` starts a fresh one.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from utils import unattended as ua


def _spawn_sleeper(*, slow_death: float = 0.0, ignore_sigterm: bool = False) -> subprocess.Popen:
    """A child that sleeps, standing in for the watchdog's poll loop.

    Two pathological shapes matter:

    * ``slow_death`` — the child takes that many seconds to finish its
      SIGTERM handler. This is the shape that makes the race real: the
      process is still alive (and still visible to ``_watchdog_pid()``)
      for the whole of that window. The real watchdog has no signal
      handler and dies in milliseconds, but the race is about the
      *contract*, not about today's implementation: ``terminate()`` is
      documented not to wait, so any future slow teardown reopens the
      window.
    * ``ignore_sigterm`` — the child never dies on SIGTERM at all, which
      forces the SIGKILL escalation.
    """
    if os.name == "nt":  # pragma: no cover - the product ships Windows-first
        pytest.skip("the terminate/kill escalation is POSIX-specific here")
    if ignore_sigterm:
        body = (
            "import signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n"
        )
    elif slow_death:
        body = (
            "import signal, sys, time\n"
            "def _handler(sig, frm):\n"
            f"    time.sleep({slow_death})\n"
            "    sys.exit(0)\n"
            "signal.signal(signal.SIGTERM, _handler)\n"
            "print('ready', flush=True)\n"
            "time.sleep(60)\n"
        )
    else:
        body = "print('ready', flush=True)\nimport time\ntime.sleep(60)\n"

    proc = subprocess.Popen(
        [sys.executable, "-c", body],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    assert proc.stdout.readline().strip() == "ready"
    return proc


def _reap(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.kill()
    proc.wait(timeout=10)


def test_stop_watchdog_waits_for_the_process_to_die(monkeypatch):
    """stop_watchdog() must not return while the watchdog is still alive.

    The whole race hinges on this: if stop_watchdog() returns before the
    process is gone, a later ensure_watchdog_running() can see the corpse
    and decide that a watchdog is already running.

    The child here has a *slow* SIGTERM handler, so without the wait
    stop_watchdog() would return while the process is still visible.
    """
    proc = _spawn_sleeper(slow_death=1.5)
    try:
        observed = {}

        def fake_pid():
            observed["alive_at_check"] = proc.poll() is None
            return proc.pid

        monkeypatch.setattr(ua, "_watchdog_pid", fake_pid)

        ua._stop_watchdog()

        assert proc.poll() is not None, (
            "stop_watchdog() returned while the watchdog was still alive"
        )
        assert observed.get("alive_at_check") is True
    finally:
        _reap(proc)


def test_stop_watchdog_leaves_no_visible_watchdog(monkeypatch):
    """After stop_watchdog(), _watchdog_pid() must not find a survivor.

    This is the invariant the start path depends on: if a watchdog can
    still be seen after it was stopped, ensure_watchdog_running() will
    skip starting a replacement and unattended mode is dead.
    """
    proc = _spawn_sleeper(slow_death=1.5)
    try:
        monkeypatch.setattr(ua, "_watchdog_pid", lambda: proc.pid)
        ua._stop_watchdog()
        assert proc.poll() is not None
    finally:
        _reap(proc)


def test_stop_watchdog_escalates_to_kill_for_a_wedged_watchdog(monkeypatch):
    """A watchdog that ignores SIGTERM must still be stopped.

    The real watchdog has no signal handler and dies instantly, but a
    watchdog wedged in an uninterruptible syscall would survive SIGTERM.
    stop_watchdog() escalates to SIGKILL so that such a process cannot
    keep the start path from ever arming a replacement.
    """
    proc = _spawn_sleeper(ignore_sigterm=True)
    try:
        monkeypatch.setattr(ua, "_watchdog_pid", lambda: proc.pid)
        monkeypatch.setattr(ua, "WATCHDOG_STOP_TIMEOUT_S", 0.5)
        monkeypatch.setattr(ua, "WATCHDOG_KILL_TIMEOUT_S", 0.5)
        ua._stop_watchdog()
        assert proc.poll() is not None, (
            "stop_watchdog() left a SIGTERM-ignoring watchdog alive"
        )
    finally:
        _reap(proc)


def test_stop_watchdog_does_not_hang_on_a_process_that_ignores_sigterm(monkeypatch):
    """The escalation must be bounded.

    A watchdog wedged in an uninterruptible syscall must not be able to
    hang the logout path forever. The kill escalation has a timeout, and
    after it the call returns anyway.
    """
    proc = _spawn_sleeper(ignore_sigterm=True)
    try:
        monkeypatch.setattr(ua, "_watchdog_pid", lambda: proc.pid)
        # Shorten the budgets so the test does not spend the real 5s+2s.
        monkeypatch.setattr(ua, "WATCHDOG_STOP_TIMEOUT_S", 0.5)
        monkeypatch.setattr(ua, "WATCHDOG_KILL_TIMEOUT_S", 0.5)

        started = time.monotonic()
        ua._stop_watchdog()
        elapsed = time.monotonic() - started

        assert elapsed < 5, (
            f"stop_watchdog() took {elapsed:.1f}s; the logout path must "
            "not be held hostage by a wedged watchdog"
        )
    finally:
        _reap(proc)


def test_stop_watchdog_still_never_raises(monkeypatch):
    """A cleanup failure must not fail the logout."""
    def boom():
        raise RuntimeError("psutil exploded")

    monkeypatch.setattr(ua, "_stop_watchdog", boom)
    ua.stop_watchdog()   # must not raise


def test_a_watchdog_that_was_stopped_can_be_started_again(monkeypatch):
    """The end-to-end invariant: stop then start leaves a live watchdog.

    This is the scenario the user actually hits: log out, log back in.
    Before the fix the second step could find the dying first watchdog
    and skip starting a replacement.
    """
    proc = _spawn_sleeper(slow_death=1.5)
    try:
        # The stop path sees the process...
        monkeypatch.setattr(ua, "_watchdog_pid", lambda: proc.pid)
        ua._stop_watchdog()
        assert proc.poll() is not None, "the watchdog outlived stop_watchdog()"

        # ...and now the start path must be able to start a fresh one.
        spawned = []
        monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
        monkeypatch.setattr(ua, "is_enabled", lambda: True)
        monkeypatch.setattr(ua, "should_skip_watchdog", lambda: False)
        monkeypatch.setattr(
            ua.subprocess, "Popen",
            lambda *a, **k: spawned.append(a),
        )

        ua.ensure_watchdog_running()
        assert len(spawned) == 1, (
            "a fresh watchdog was not started after the previous one was "
            "stopped; unattended mode is dead until the next app restart"
        )
    finally:
        _reap(proc)
