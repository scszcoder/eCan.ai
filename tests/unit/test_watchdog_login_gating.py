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
import re

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


# --------------------------------------------------------------------------
# Every path that brings the main window up must arm the watchdog.
# --------------------------------------------------------------------------

def _enclosing_function(src: str, index: int) -> str:
    """The name of the ``def`` that contains ``src[index]``."""
    head = src[:index]
    matches = list(re.finditer(r"^    (?:async )?def (\w+)\(", head, re.M))
    assert matches, "no enclosing def found"
    return matches[-1].group(1)


def _body_of(src: str, fn_name: str) -> str:
    """The source of ``fn_name``'s body, up to the next method definition."""
    start = src.index(f"def {fn_name}(")
    end = src.find("\n    def ", start)
    if end == -1:
        end = src.find("\n    async def ", start)
    if end == -1:
        end = len(src)
    return src[start:end]


def _arms_watchdog(src: str, fn_name: str, _seen=None) -> bool:
    """Does ``fn_name`` (directly or via a helper it calls) arm the watchdog?

    Follows one level of helper indirection: the arming lives in
    ``_arm_watchdog_after_login``, which the launch path calls. A grep for
    the literal string in the launch function would miss that, and so would
    a naive check — which is how this gap survived the original fix.
    """
    seen = _seen if _seen is not None else set()
    if fn_name in seen:
        return False
    seen.add(fn_name)

    body = _body_of(src, fn_name)
    if "ensure_watchdog_running" in body:
        return True
    for helper in re.findall(r"self\.(\w+)\(", body):
        if helper == fn_name:
            continue
        try:
            if _arms_watchdog(src, helper, seen):
                return True
        except ValueError:
            continue
    return False


def test_every_main_window_launch_path_starts_the_watchdog():
    """No route to a running main window may skip arming unattended mode.

    There are two ways the main window comes up, and the watchdog has to be
    started on both:

      * ``_async_launch_main_window`` — the normal path, after a fresh
        authentication (password, Google, WeChat QR).
      * ``login()``'s "already authenticated" branch — taken when the
        session was restored at startup, before any login gesture. On CN,
        ``AuthManager.__init__`` calls ``try_restore_cloudbase_session`` /
        ``try_restore_wechat_session``, so a WeChat QR user is already
        ``signed_in`` before the UI ever asks. Their main window therefore
        comes up through the *sync* ``_launch_main_window``, not through
        the async one.

    Arming the watchdog only on the async path left that second case with
    no watchdog: unattended mode silently did nothing for every user whose
    session was restored. The source-text grep in
    ``test_login_starts_the_watchdog`` cannot see that — the string is
    present in the file either way.
    """
    src = _source("gui/LoginoutGUI.py")

    launch_calls = [
        m.start()
        for m in re.finditer(r"self\._launch_main_window\(", src)
    ]
    assert launch_calls, "no main window launch call found"

    unwatched = []
    for call in launch_calls:
        fn = _enclosing_function(src, call)
        # The call inside the helper's own def is the definition, not a use.
        if fn == "_launch_main_window":
            continue
        if not _arms_watchdog(src, fn):
            unwatched.append(fn)

    assert not unwatched, (
        "these paths bring the main window up without arming the watchdog, "
        "so unattended mode does nothing for them: "
        + ", ".join(sorted(set(unwatched)))
    )


def test_every_logout_path_stops_the_watchdog():
    """No route to a signed-out state may leave the watchdog running.

    The mirror of the start-side check. If a logout path skips
    ``stop_watchdog``, the watchdog survives the sign-out and relaunches
    eCan onto the login screen — the exact failure the whole gating
    change exists to prevent.

    Every path that ends in a sign-out has to stop the watchdog:

      * ``Login.handleLogout`` — the user-initiated logout, and also the
        one the session-expiry callback schedules via ``QTimer.singleShot``
        (so an expired session cannot leave the watchdog armed either);
      * ``MainWindow.logout`` — the graceful cleanup that ``handleLogout``
        delegates to.
    """
    src = _source("gui/LoginoutGUI.py")

    # Every place that signs the user out.
    sign_out_calls = [
        m.start()
        for m in re.finditer(r"self\.(?:auth_manager\.logout\(\)|main_win\.logout\(\))", src)
    ]
    assert sign_out_calls, "no sign-out call found in gui/LoginoutGUI.py"

    # ``handleLogout`` stops the watchdog before it signs out, so a call
    # inside it is covered by that one stop.
    logout_body = _body_of(src, "handleLogout")
    assert "stop_watchdog" in logout_body, (
        "handleLogout must stop the watchdog before signing the user out"
    )
    stop_pos = logout_body.index("stop_watchdog")
    for call in sign_out_calls:
        fn = _enclosing_function(src, call)
        if fn != "handleLogout":
            continue
        offset = call - src.index("def handleLogout(")
        assert stop_pos < offset, (
            "the watchdog must be stopped before the sign-out, not after: "
            "a sign-out that races the watchdog can still be relaunched"
        )


def test_the_watchdog_is_armed_from_the_single_launch_choke_point():
    """The arming must sit inside the window-creation path.

    ``_launch_main_window`` may defer the real work onto the Qt main thread
    with ``QTimer.singleShot``, so its caller returns before the window
    exists. Arming the watchdog from the caller would therefore start it
    for a launch that had not happened yet — and, on the deferred path,
    possibly for one that then failed.
    """
    src = _source("gui/LoginoutGUI.py")
    body = _body_of(src, "_launch_main_window")
    assert "_arm_watchdog_after_login" in body, (
        "the watchdog must be armed from inside the window-creation path, "
        "not from the caller of _launch_main_window"
    )


# --------------------------------------------------------------------------
# Behaviour of the arming helper.
# --------------------------------------------------------------------------

def test_arming_the_watchdog_never_raises(monkeypatch):
    """A failure to arm unattended mode must not fail the login."""
    from utils import unattended as ua
    from gui.LoginoutGUI import Login

    def boom():
        raise RuntimeError("no unattended marker")

    monkeypatch.setattr(ua, "ensure_watchdog_running", boom)

    login = Login.__new__(Login)   # no __init__: no Qt, no auth manager
    login._arm_watchdog_after_login()   # must not raise


def test_arming_the_watchdog_calls_the_real_helper(monkeypatch):
    """The helper must actually start the watchdog."""
    from utils import unattended as ua
    from gui.LoginoutGUI import Login

    started = []
    monkeypatch.setattr(ua, "ensure_watchdog_running", lambda: started.append("start"))

    login = Login.__new__(Login)
    login._arm_watchdog_after_login()
    assert started == ["start"]
