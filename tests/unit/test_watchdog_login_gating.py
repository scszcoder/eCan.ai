"""Unattended mode must not keep an app alive that nobody is using.

The bug (2026-10-23): the crash/hang watchdog was started from
``main.py`` at boot, before anybody had signed in.  With unattended mode
on, that meant the watchdog would relaunch eCan whenever it exited —
including the case where the user had deliberately logged out, leaving
eCan sitting on the login screen.  The app came straight back up, again
on the login screen.

The fix ties the watchdog to the *signed-in* state:

  * it starts only after a successful login,
  * it stops when the user logs out.

``gui/LoginoutGUI.py`` cannot be imported without PySide6, so the wiring
is checked against the source text while the behaviour of the helpers is
exercised directly.
"""

import pathlib

import pytest


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _source(rel_path: str) -> str:
    return (REPO_ROOT / rel_path).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Behaviour of the helpers.
# --------------------------------------------------------------------------

def test_stop_watchdog_reaches_the_real_killer(monkeypatch):
    from utils import unattended as ua

    calls = []
    monkeypatch.setattr(ua, "_stop_watchdog", lambda: calls.append("stop"))

    ua.stop_watchdog()
    assert calls == ["stop"]


def test_stop_watchdog_never_raises(monkeypatch):
    """A logout must not fail because of cleanup."""
    from utils import unattended as ua

    def boom():
        raise RuntimeError("psutil exploded")

    monkeypatch.setattr(ua, "_stop_watchdog", boom)
    ua.stop_watchdog()   # must not raise


def test_stop_watchdog_stops_a_running_watchdog(monkeypatch):
    """End to end through the public helper: a running watchdog process
    must actually be terminated.
    """
    from utils import unattended as ua

    killed = []

    class FakeProc:
        def terminate(self):
            killed.append("terminated")

    monkeypatch.setattr(ua, "_watchdog_pid", lambda: 4242)
    import psutil
    monkeypatch.setattr(psutil, "Process", lambda pid: FakeProc())

    ua.stop_watchdog()
    assert killed == ["terminated"]


def test_ensure_watchdog_running_still_works(monkeypatch):
    """The start path is unchanged: it arms unattended mode."""
    from utils import unattended as ua

    monkeypatch.delenv("ECAN_NO_WATCHDOG", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(ua, "_is_dev_mode", lambda: False)
    monkeypatch.setattr(ua, "is_enabled", lambda: True)
    monkeypatch.setattr(ua, "_watchdog_pid", lambda: None)
    spawned = []
    monkeypatch.setattr(ua.subprocess, "Popen", lambda *a, **k: spawned.append(a))

    ua.ensure_watchdog_running()
    assert len(spawned) == 1


# --------------------------------------------------------------------------
# Wiring: who calls what.
# --------------------------------------------------------------------------

def test_main_does_not_start_the_watchdog():
    """The watchdog must not be armed at boot — that is what relaunched
    eCan onto the login screen after the user logged out.
    """
    src = _source("main.py")
    assert "ensure_watchdog_running" not in src, (
        "main.py must not start the watchdog — it belongs to the post-login "
        "path, otherwise it relaunches an app nobody is signed into"
    )


def test_login_starts_the_watchdog():
    """A successful login is what arms unattended mode."""
    src = _source("gui/LoginoutGUI.py")
    assert "ensure_watchdog_running" in src, (
        "the watchdog must be started once the user is signed in"
    )


def test_logout_stops_the_watchdog():
    """Nothing signed in means nothing to keep alive."""
    src = _source("gui/LoginoutGUI.py")
    assert "stop_watchdog" in src, (
        "logging out must stop the watchdog — it would otherwise relaunch "
        "eCan back onto the login screen"
    )


def test_the_watchdog_start_happens_after_the_main_window_launch():
    """The start must be tied to a *successful* login, not merely to the
    login attempt.
    """
    src = _source("gui/LoginoutGUI.py")
    start = src.index("ensure_watchdog_running")
    launch = src.index("self._launch_main_window(request.schedule_mode)")
    assert launch < start, (
        "the watchdog must be started after the main window is up, so a "
        "failed login never arms unattended mode"
    )
