"""
Unit tests for SessionSupervisor._drive_silent_refresh after the
no-popup policy change (2026-08).

Background
----------
CloudBase WeChat OAuth returns a 10-minute access token with no
refresh_token. Historically, when the supervisor ticked past the
expiry window it popped a WeChat OAuth window at the user — that is
explicitly forbidden now. The new contract is:

  * Never pop a browser window on the user's behalf.
  * ``on_session_expiring_soon`` is NOT fired here; that callback
    chain ends in ``LoginoutGUI.prompt_for_reauth`` which calls
    ``AuthManager.wechat_login`` which opens the browser.
  * For a fresh token (just installed, well within its local exp),
    a server 401 is almost always CloudBase cache lag — we suppress
    on_session_expired and retry after the grace window.
  * For a real expiry (or an old token still being rejected), we
    emit on_session_expired so the GUI can show a "session expired"
    banner and the user can re-login at will.

We verify four scenarios:

  1. Fresh token (just installed) + server 401 -> no
     on_session_expired, no on_session_expiring_soon; rescheduled.
  2. Fresh token + real imminent expiry (≤ 60s remaining) -> emit
     on_session_expired (real logout, no popup).
  3. Old token (> 60s ago installed) + server 401 -> emit
     on_session_expired (real logout, no popup).
  4. Re-nudge after grace window elapses -> emit on_session_expired
     (the cache lag window has passed, the token really is dead).
"""

import time as _time

import pytest


def _supervisor_module():
    import importlib
    return importlib.import_module("auth.session_supervisor")


def _make_supervisor():
    ss = _supervisor_module()

    tokens = {"AccessToken": "stub", "RefreshToken": None}
    tokens_holder = tokens

    class _AM:
        signed_in = True
        tokens = tokens_holder

    return ss.SessionSupervisor(_AM())


# ---------------------------------------------------------------
# 1) Fresh token + server 401 -> no callbacks, rescheduled
# ---------------------------------------------------------------

def test_fresh_token_401_does_not_logout():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []
    expiring_calls: list[dict] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))
    supervisor.on_session_expiring_soon(
        lambda info: expiring_calls.append(info)
    )

    supervisor.notify_token_installed()  # t0

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert expired_calls == [], (
        "fresh token rejected by server is CloudBase cache lag, not a "
        "real expiry — must NOT log the user out"
    )
    assert expiring_calls == [], (
        "on_session_expiring_soon must NOT fire — that chain ends in a "
        "browser popup, which the no-popup policy forbids"
    )
    with supervisor._lock:
        assert supervisor._silent_refresh_next_attempt > _time.monotonic(), (
            "next_attempt should be rescheduled into the future"
        )


# ---------------------------------------------------------------
# 2) Fresh token + real imminent expiry -> emit expired
# ---------------------------------------------------------------

def test_fresh_token_with_real_imminent_expiry_logs_out():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))

    supervisor.notify_token_installed()  # t0

    # Real expiry: token dies in 30s. The grace guard must NOT suppress
    # this — the user genuinely needs to re-login.
    imminent_exp = int(_time.time()) + 30
    supervisor._drive_silent_refresh(imminent_exp)

    assert len(expired_calls) == 1, (
        "when the token really is about to die, even a fresh token "
        "must surface on_session_expired"
    )


# ---------------------------------------------------------------
# 3) Old token + server 401 -> emit expired
# ---------------------------------------------------------------

def test_old_token_401_logs_out():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))

    supervisor.notify_token_installed()
    # Pretend 2 minutes have passed since install.
    supervisor._last_token_installed_at = _time.time() - 120

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert len(expired_calls) == 1, (
        "an old token still being rejected is a real logout — emit "
        "on_session_expired"
    )


# ---------------------------------------------------------------
# 4) After grace window, emit expired even on a fresh install
# ---------------------------------------------------------------

def test_re_nudge_after_grace_logs_out():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))

    supervisor.notify_token_installed()
    # Pretend 70 seconds have passed since install.
    supervisor._last_token_installed_at = _time.time() - 70

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert len(expired_calls) == 1, (
        "after the grace window, the next nudge must emit "
        "on_session_expired"
    )
