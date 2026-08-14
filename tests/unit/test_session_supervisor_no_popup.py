"""
Unit tests for ``SessionSupervisor._drive_silent_refresh`` after the
no-popup policy change (2026-08).

Background
----------
CloudBase WeChat OAuth returns a 10-minute access token with no
refresh_token. Historically, when the supervisor ticked past the
expiry window it popped a WeChat OAuth window at the user — that is
explicitly forbidden now. The new contract is:

  * Never pop a browser window on the user's behalf.
  * Emit ``on_session_expired`` so the GUI can render a non-blocking
    "session expired" banner and the user can re-login at will.
  * ``on_session_expiring_soon`` is NOT fired here; that callback
    chain ends in ``LoginoutGUI.prompt_for_reauth`` which calls
    ``AuthManager.wechat_login`` which opens the browser.

We verify two scenarios:

  1. ``_drive_silent_refresh`` (no refresh_token, expiring) fires
     ``on_session_expired`` and never ``on_session_expiring_soon``.
  2. After ``_drive_silent_refresh`` runs, ``_last_token_installed_at``
     is irrelevant — nothing is launched, no popup is queued.

The original fresh-token-grace scenario is gone since the grace
window served only to delay a popup we no longer pop.
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
# 1) on_session_expired — yes; on_session_expiring_soon — no
# ---------------------------------------------------------------

def test_drive_silent_refresh_emits_expired_only():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []
    expiring_calls: list[dict] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))
    supervisor.on_session_expiring_soon(
        lambda info: expiring_calls.append(info)
    )

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    assert len(expired_calls) == 1, (
        "session expired callback must fire exactly once so the GUI "
        "can show a 'session expired' banner"
    )
    assert expiring_calls == [], (
        "expiring-soon callback must NOT fire — that chain ends in a "
        "browser popup, which the no-popup policy forbids"
    )


# ---------------------------------------------------------------
# 2) drive_silent_refresh is idempotent / safe to call repeatedly
# ---------------------------------------------------------------

def test_drive_silent_refresh_is_safe_to_call_twice():
    supervisor = _make_supervisor()

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)
    supervisor._drive_silent_refresh(future_exp)

    # Each call must independently emit (no in-flight latch blocking
    # the second one when the first was just a no-op log + emit).
    assert len(expired_calls) == 2, (
        "every call must emit on_session_expired; no automatic "
        "browser popup should be queued"
    )


# ---------------------------------------------------------------
# 3) silent refresh state is reset for the next token install
# ---------------------------------------------------------------

def test_drive_silent_refresh_clears_latches_for_next_login():
    supervisor = _make_supervisor()

    future_exp = int(_time.time()) + 9 * 60
    supervisor._drive_silent_refresh(future_exp)

    with supervisor._lock:
        assert supervisor._silently_refreshing is False
        assert supervisor._silent_refresh_next_attempt == 0.0
        assert supervisor._silent_refresh_failures == 0

    # A subsequent fresh install must not be blocked by stale state.
    supervisor.notify_token_installed()
    with supervisor._lock:
        assert supervisor._last_token_installed_at > 0
