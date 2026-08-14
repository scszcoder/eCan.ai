"""
Regression test for the WeChat short-lived-token logout bug.

Background
----------
CloudBase WeChat OAuth (via ``wechat_login.php``) issues an access token
whose JWT ``exp`` is only 10 minutes out — but the AuthManager sets
``ExpiresIn=7200`` (2 hours), so on the client we previously believed the
token was good for 2 hours. The supervisor's ``REFRESH_LEAD_SECONDS`` is
300 (5 minutes).

When the token was a true WeChat 10-minute token, the timeline was:

    t=0     login → install token (exp = t+600)
    t=300   supervisor _tick → remaining=300s ≤ REFRESH_LEAD
            → no refresh_token (WeChat) → _drive_silent_refresh
            → grace window passed (token_age=300s) → emit_expired
            → user kicked to login page despite 5 minutes of token life left

The fix: ``_tick`` no longer routes ``0 < remaining <= REFRESH_LEAD`` AND
no ``refresh_token`` into ``_drive_silent_refresh``. We just log and wait
for the genuine ``remaining <= 0`` branch to fire, at which point the
token really is dead and the logout is honest.

We pin this with two tests:

  1. _tick when remaining is in (0, REFRESH_LEAD] with no refresh_token
     must NOT emit on_session_expired.
  2. _tick when remaining has gone negative (true expiry) with no
     refresh_token still routes through _drive_silent_refresh and emits
     on_session_expired (we must not regress that path).
"""

import time as _time

import pytest


def _supervisor_module():
    import importlib
    return importlib.import_module("auth.session_supervisor")


def _make_supervisor(refresh_token=None):
    ss = _supervisor_module()

    # Stub JWT must have at least one dot for _decode_exp to even attempt
    # parsing. Body decodes to {"exp": 0} — tests override the token via
    # _last_token_installed_at + a real-ish exp by patching the supervisor
    # to read _decode_exp directly. Easier: use a JWT whose payload is
    # the test's chosen exp.
    tokens = {"AccessToken": "stub.stub", "RefreshToken": refresh_token}
    tokens_holder = tokens

    class _AM:
        signed_in = True
        tokens = tokens_holder

    return ss.SessionSupervisor(_AM())


def _make_jwt_with_exp(exp_unix_seconds: int) -> str:
    """Build a syntactically valid (unsigned) JWT whose exp = exp_unix_seconds.

    Supervisor's _decode_exp reads the payload without verifying the
    signature, so an unsigned stub is fine for testing.
    """
    import base64
    import json

    header = {"alg": "none", "typ": "JWT"}
    payload = {"exp": exp_unix_seconds, "iat": exp_unix_seconds - 60}
    b64 = lambda d: base64.urlsafe_b64encode(
        json.dumps(d).encode()
    ).rstrip(b"=").decode()
    return f"{b64(header)}.{b64(payload)}.stub"


def _install_token_exp(supervisor, exp_unix_seconds: int, age_seconds: float):
    """Replace supervisor's tokens dict + install timestamp so the next
    _tick reads the requested exp / install age."""
    supervisor._am.tokens["AccessToken"] = _make_jwt_with_exp(exp_unix_seconds)
    supervisor._last_token_installed_at = _time.time() - age_seconds


def test_tick_with_short_remaining_and_no_refresh_token_does_not_logout(monkeypatch):
    """Remaining 4 minutes, no refresh_token → must NOT emit expired.

    Reproduces the exact log from the 11:15:17 incident: token_age=299s,
    remaining=288s, no refresh_token. The fix makes this branch a no-op.
    """
    supervisor = _make_supervisor(refresh_token=None)

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))
    supervisor.notify_token_installed()

    # Mark the install 600s ago so the cache-lag grace check inside
    # _drive_silent_refresh (if it were called) would NOT suppress — we
    # are testing that _tick doesn't route here in the first place.
    _install_token_exp(
        supervisor,
        exp_unix_seconds=int(_time.time()) + 240,  # 4 min remaining
        age_seconds=600,
    )

    supervisor._tick(force=False)

    assert expired_calls == [], (
        "Remaining=240s, no refresh_token: must NOT emit on_session_expired. "
        "The token is still valid; emitting here kicked the user out 5 "
        "minutes before real expiry (regression of the 11:15 logout storm)."
    )


def test_tick_with_negative_remaining_and_no_refresh_token_still_logs_out(monkeypatch):
    """True expiry (remaining <= 0) must still emit on_session_expired.

    The fix only relaxes the (0, REFRESH_LEAD] branch. We must still
    surface real expiries through _drive_silent_refresh → emit_expired.
    """
    supervisor = _make_supervisor(refresh_token=None)

    expired_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))
    supervisor.notify_token_installed()

    _install_token_exp(
        supervisor,
        exp_unix_seconds=int(_time.time()) - 30,  # expired 30s ago
        age_seconds=600,
    )

    supervisor._tick(force=False)

    assert expired_calls == [1], (
        "Truly expired token (remaining=-30s) MUST emit on_session_expired. "
        "Regressing this would leave a logged-out app with no logout signal."
    )


def test_tick_with_refresh_token_proactive_refresh_unchanged(monkeypatch):
    """The presence of a refresh_token must NOT be affected by the fix.

    Even inside REFRESH_LEAD with a refresh_token, _tick should still
    attempt the refresh (existing behavior).
    """
    supervisor = _make_supervisor(refresh_token="rtok")

    expired_calls: list[int] = []
    refreshed_calls: list[int] = []

    supervisor.on_session_expired(lambda: expired_calls.append(1))
    supervisor.on_session_refreshed(lambda *_a, **_kw: refreshed_calls.append(1))
    supervisor.notify_token_installed()

    refresh_attempts: list[str] = []

    def _fake_refresh(token):
        refresh_attempts.append(token)
        return True

    monkeypatch.setattr(supervisor, "_attempt_refresh", _fake_refresh)

    _install_token_exp(
        supervisor,
        exp_unix_seconds=int(_time.time()) + 240,  # 4 min remaining
        age_seconds=360,
    )

    supervisor._tick(force=False)

    assert refresh_attempts == ["rtok"], (
        "refresh_token path must still attempt the refresh"
    )
    # Two _emit_refreshed calls expected: notify_token_installed + the
    # successful refresh inside _tick. We assert >= 1 to avoid coupling to
    # the supervisor's internal notify order.
    assert refreshed_calls, "refresh_token path must emit refreshed"
    assert expired_calls == []