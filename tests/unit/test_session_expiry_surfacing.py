"""A real session expiry must always surface to the user.

``SessionSupervisor._drive_silent_refresh`` is the last line of defence before
eCan decides the user has to log in again. Two things must never happen:

1. A genuine expiry is swallowed. When the local ``exp`` is inside (or past)
   the grace window, or the token has been installed longer than the grace
   window, the user has to be told — otherwise the app sits there silently
   signed-in with a dead token.

2. A *transport* failure logs the user out. An unreachable server must never
   cost the user their session.

The distinction is what the exception means. ``_get_wechat_session_token``
raising ``AttributeError`` (the method is missing, or the auth manager is a
stub) says nothing about the network, so it must not be treated as "transient
— stay signed in".
"""

import time as _time

import pytest


def _make_supervisor(am):
    import importlib
    ss = importlib.import_module("auth.session_supervisor")
    return ss.SessionSupervisor(am)


class _BareAM:
    """An auth manager that exposes neither session-token method."""

    signed_in = True

    def __init__(self):
        self.tokens = {"AccessToken": "stub", "RefreshToken": None}


class _NoSessionTokenAM(_BareAM):
    """Auth manager with the method, but no stored 30-day session token."""

    def _get_wechat_session_token(self):
        return False, None


class _TransportDownAM(_BareAM):
    """Auth manager whose session-token lookup fails at the transport level."""

    def _get_wechat_session_token(self):
        raise ConnectionError("endpoint unreachable")


def _expired_count(supervisor):
    calls = []
    supervisor.on_session_expired(lambda: calls.append(1))
    return calls


# --------------------------------------------------------------------------
# 1. A missing method must not masquerade as a network problem
# --------------------------------------------------------------------------

def test_missing_session_token_method_still_logs_out():
    supervisor = _make_supervisor(_BareAM())
    calls = _expired_count(supervisor)

    supervisor.notify_token_installed()
    # Old enough that the fresh-token grace guard cannot apply.
    supervisor._last_token_installed_at = _time.time() - 120
    supervisor._drive_silent_refresh(int(_time.time()) + 9 * 60)

    assert len(calls) == 1, (
        "AttributeError from a missing _get_wechat_session_token is not a "
        "transport failure; the user must still be told to re-login"
    )


def test_no_stored_session_token_still_logs_out():
    supervisor = _make_supervisor(_NoSessionTokenAM())
    calls = _expired_count(supervisor)

    supervisor.notify_token_installed()
    supervisor._last_token_installed_at = _time.time() - 120
    supervisor._drive_silent_refresh(int(_time.time()) + 9 * 60)

    assert len(calls) == 1, (
        "with no 30-day session token to fall back on, this is a real "
        "expiry — the user must be told"
    )


# --------------------------------------------------------------------------
# 2. A genuine transport failure must NOT log the user out
# --------------------------------------------------------------------------

def test_transport_failure_does_not_log_out():
    supervisor = _make_supervisor(_TransportDownAM())
    calls = _expired_count(supervisor)

    supervisor.notify_token_installed()
    supervisor._last_token_installed_at = _time.time() - 120
    supervisor._drive_silent_refresh(int(_time.time()) + 9 * 60)

    assert calls == [], (
        "an unreachable server must never cost the user their session"
    )


# --------------------------------------------------------------------------
# 3. The backoff must not swallow a nudge that lands inside the window
# --------------------------------------------------------------------------

def test_a_re_nudge_inside_the_backoff_still_reports_after_grace():
    """After the grace window the next nudge must emit expired.

    The backoff gate currently returns before the grace logic runs, so a
    nudge that arrives while ``_silent_refresh_next_attempt`` is still in the
    future is dropped entirely — even when the token is genuinely dead.
    """
    supervisor = _make_supervisor(_NoSessionTokenAM())
    calls = _expired_count(supervisor)

    supervisor.notify_token_installed()
    supervisor._last_token_installed_at = _time.time() - 70

    # A previous tick armed a backoff that has not elapsed yet.
    with supervisor._lock:
        supervisor._silent_refresh_next_attempt = _time.monotonic() + 600

    supervisor._drive_silent_refresh(int(_time.time()) + 9 * 60)

    assert len(calls) == 1, (
        "a backoff armed for a cache-lag retry must not suppress a real "
        "logout once the grace window has passed"
    )