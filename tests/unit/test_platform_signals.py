"""Cross-platform exit-signal handling for the shutdown lease.

The watchdog must know that the app is going away. ``atexit`` covers the
normal interpreter shutdown, but not:

* ``kill <pid>`` / SIGTERM on macOS and Linux;
* Ctrl+C in a terminal (SIGINT);
* Windows ``CTRL_BREAK_EVENT`` (SIGBREAK) and console Ctrl+C
  (``CTRL_C_EVENT``), which only a console-mode process can receive.

Windows has no SIGTERM at all: ``signal.signal(SIGTERM, ...)`` raises
``ValueError`` there. Every platform must therefore be probed individually and
a refusal to install one handler must never prevent the others.

These tests pin the cross-platform behaviour without depending on the host
platform: the install function is exercised with synthetic "signal objects"
that raise the platform errors.
"""

import os
import signal as real_signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from utils import platform_signals as ps

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_install_returns_the_handlers_it_actually_registered(monkeypatch):
    registered = []

    def fake_signal(sig, handler):
        registered.append(sig)
        return real_signal.getsignal(sig)

    monkeypatch.setattr(ps._signal, "signal", fake_signal)
    names = ps.install_exit_handlers(lambda name: None, platform="linux", respect_pytest=False)
    assert "SIGTERM" in names
    assert "SIGINT" in names
    assert "SIGBREAK" not in names


def test_install_skips_sigbreak_on_posix(monkeypatch):
    registered = []
    monkeypatch.setattr(ps._signal, "signal", lambda sig, h: registered.append(sig))
    ps.install_exit_handlers(lambda name: None, platform="darwin", respect_pytest=False)
    assert all(getattr(s, "name", "") != "SIGBREAK" for s in registered)


def test_install_includes_sigbreak_on_windows(monkeypatch):
    registered = []
    # SIGBREAK only exists on Windows; simulate it so the test is host-independent.
    monkeypatch.setattr(ps._signal, "SIGBREAK", 21, raising=False)
    monkeypatch.setattr(ps._signal, "signal", lambda sig, h: registered.append(sig))
    monkeypatch.setattr(ps._sys, "platform", "win32")
    names = ps.install_exit_handlers(lambda name: None, platform="win32", respect_pytest=False)
    assert "SIGBREAK" in names


def test_install_ignores_value_error_from_missing_signal(monkeypatch):
    """Windows has no SIGTERM; a ValueError must not abort the install."""
    def fake_signal(sig, handler):
        if sig is real_signal.SIGTERM:
            raise ValueError("signal only works in main thread")
        return real_signal.getsignal(sig)

    monkeypatch.setattr(ps._signal, "signal", fake_signal)
    names = ps.install_exit_handlers(lambda name: None, platform="win32", respect_pytest=False)
    assert "SIGTERM" not in names
    assert "SIGINT" in names


def test_install_ignores_attribute_error_for_absent_signal(monkeypatch):
    def fake_signal(sig, handler):
        if sig is real_signal.SIGINT:
            raise AttributeError("no SIGINT here")
        return real_signal.getsignal(sig)

    monkeypatch.setattr(ps._signal, "signal", fake_signal)
    names = ps.install_exit_handlers(lambda name: None, platform="linux", respect_pytest=False)
    assert "SIGINT" not in names
    assert "SIGTERM" in names


def test_install_never_raises(monkeypatch):
    def boom(sig, handler):
        raise OSError("nope")

    monkeypatch.setattr(ps._signal, "signal", boom)
    names = ps.install_exit_handlers(lambda name: None, platform="linux", respect_pytest=False)
    assert names == []


def test_handler_calls_the_mark_callback_with_the_signal_name(monkeypatch):
    seen = []
    registered = {}

    def fake_signal(sig, handler):
        registered[sig] = handler
        return real_signal.getsignal(sig)

    monkeypatch.setattr(ps._signal, "signal", fake_signal)
    # The handler re-delivers the signal to itself so the process dies (see
    # P0-1). That is covered by the subprocess tests; here it would kill the
    # pytest runner, so stub it out.
    monkeypatch.setattr(ps, "_restore_and_redeliver", lambda signum, previous: None)
    ps.install_exit_handlers(lambda name: seen.append(name), platform="linux", respect_pytest=False)
    for sig, handler in registered.items():
        handler(sig, None)
    assert "SIGTERM" in seen
    assert "SIGINT" in seen


def test_handler_swallows_callback_errors(monkeypatch):
    """A failing marker must not turn a signal into a crash."""

    def bad_mark(name):
        raise RuntimeError("disk full")

    registered = {}
    monkeypatch.setattr(ps._signal, "signal",
                        lambda sig, handler: registered.__setitem__(sig, handler))
    monkeypatch.setattr(ps, "_restore_and_redeliver", lambda signum, previous: None)
    ps.install_exit_handlers(bad_mark, platform="linux", respect_pytest=False)
    for sig, handler in registered.items():
        handler(sig, None)   # must not raise


def test_install_is_skipped_during_pytest(monkeypatch):
    """Installing real signal handlers inside pytest would break Ctrl+C."""
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_x::test_y (call)")
    registered = []
    monkeypatch.setattr(ps._signal, "signal", lambda sig, h: registered.append(sig))
    names = ps.install_exit_handlers(lambda name: None, platform="linux")
    assert names == []
    assert registered == []


def test_install_skipped_when_disabled_by_env(monkeypatch):
    monkeypatch.setenv("ECAN_NO_EXIT_SIGNALS", "1")
    registered = []
    monkeypatch.setattr(ps._signal, "signal", lambda sig, h: registered.append(sig))
    names = ps.install_exit_handlers(lambda name: None, platform="linux", respect_pytest=False)
    assert names == []


# --------------------------------------------------------------------------
# P0-1: a registered handler must not swallow the signal's default action.
#
# Installing a Python handler REPLACES SIG_DFL. If the handler merely records
# the intent and returns, the process keeps running: the signal never kills
# it. That breaks every caller that relies on a signal terminating the
# process (unattended.py's watchdog stop, worker_supervisor's terminate(),
# and Ctrl+C in a terminal).
#
# These tests spawn a real child process, deliver a real signal and assert
# the child actually died. A monkeypatched handler cannot express this.
# --------------------------------------------------------------------------

_CHILD_SRC = textwrap.dedent(
    """
    import sys, time
    sys.path.insert(0, {repo!r})
    from utils import platform_signals as ps

    ps.install_exit_handlers(lambda name: None, respect_pytest=False)
    with open({marker!r}, "w") as fh:
        fh.write("READY")
    while True:
        time.sleep(0.05)
    """
)


def _spawn_signal_child(tmp_path, marker_name="ready.marker"):
    """Start a child that installs the real exit handlers.

    The child signals readiness through a marker file rather than stdout:
    importing ``utils`` prints banner noise of its own, and a marker file
    gives the parent a bounded wait instead of a blocking ``readline``.
    """
    marker = tmp_path / marker_name
    src = _CHILD_SRC.format(repo=str(REPO_ROOT), marker=str(marker))
    env = dict(os.environ)
    env.pop("PYTEST_CURRENT_TEST", None)
    env.pop("ECAN_NO_EXIT_SIGNALS", None)

    proc = subprocess.Popen(
        [sys.executable, "-c", src],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=str(tmp_path),
        text=True,
    )
    deadline = time.time() + 20
    while time.time() < deadline:
        if marker.exists():
            return proc
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    return proc


def _wait_for_exit(proc, timeout=10):
    deadline = time.time() + timeout
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.05)
    return proc.poll()


@pytest.mark.skipif(sys.platform == "win32", reason="SIGTERM does not exist on Windows")
def test_sigterm_handler_still_lets_the_process_die(tmp_path):
    """SIGTERM must terminate the child, not merely be recorded.

    The child installs the real handlers. If the handler swallows the
    signal, ``poll()`` stays None and the child outlives its own SIGTERM.
    """
    proc = _spawn_signal_child(tmp_path)
    try:
        assert proc.poll() is None, "child exited before installing its handlers"

        proc.send_signal(real_signal.SIGTERM)

        rc = _wait_for_exit(proc)

        assert rc is not None, (
            "process survived SIGTERM: the handler swallowed the signal's "
            "default termination"
        )
        # Negative return code on POSIX means "killed by that signal".
        assert rc == -real_signal.SIGTERM, (
            f"expected death by SIGTERM, got returncode {rc}"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT/SIGTERM differ on Windows")
def test_sigint_handler_still_lets_the_process_die(tmp_path):
    """Ctrl+C must still interrupt the child (KeyboardInterrupt / SIGINT)."""
    proc = _spawn_signal_child(tmp_path)
    try:
        assert proc.poll() is None, "child exited before installing its handlers"

        proc.send_signal(real_signal.SIGINT)

        rc = _wait_for_exit(proc)

        assert rc is not None, (
            "process survived SIGINT: Ctrl+C can no longer stop the app"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)
