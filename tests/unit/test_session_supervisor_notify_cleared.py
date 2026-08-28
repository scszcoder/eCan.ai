"""
Unit tests for ``SessionSupervisor.notify_session_cleared``.

Background
----------
When the access token expires in CN (CloudBase WeChat) without a refresh
token, ``AuthManager.ensure_valid_tokens`` clears the credentials in
``auth_manager.py`` (sets ``tokens=None``, ``signed_in=False``).
``SessionSupervisor._tick`` then early-exits on ``signed_in=False`` at
the top and never broadcasts ``on_session_expired``. The GUI therefore
keeps behaving as if signed in while every cloud call 401s in the
background.

``notify_session_cleared`` is the supervisor-side hook that closes this
gap. AuthManager calls it immediately after clearing credentials; the
supervisor then fires ``on_session_expired`` to all GUI subscribers,
which is what triggers the auto-logout redirect to the login window
(``gui/LoginoutGUI._on_session_expired``).

We exercise five scenarios:

  1. ``notify_session_cleared`` fires ``on_session_expired``
  2. multiple subscribers all see the same expired event
  3. ``on_session_expired`` callbacks that raise do NOT prevent other
     subscribers from running (exceptions are logged, not propagated)
  4. the in-flight silent-refresh latch is reset so a follow-up refresh
     can still be scheduled
  5. idempotent — calling notify_session_cleared twice fires twice
     (UI redraw is cheap; no debouncing here on purpose)
"""

import importlib
import threading

import pytest


_FakeAuthManager = None  # defined below in conftest-like style for this file


def _supervisor_module():
    return importlib.import_module("auth.session_supervisor")


def _make_supervisor():
    ss = _supervisor_module()

    class _AM:
        signed_in = True
        tokens = {"AccessToken": "stub", "RefreshToken": None}

    supervisor = ss.SessionSupervisor(_AM())
    return supervisor, _AM


# ---------------------------------------------------------------
# 1) notify_session_cleared fires on_session_expired
# ---------------------------------------------------------------

def test_notify_session_cleared_fires_on_session_expired():
    supervisor, _ = _make_supervisor()
    fired: list[str] = []

    def cb():
        fired.append("got-it")

    supervisor.on_session_expired(cb)

    assert fired == []
    supervisor.notify_session_cleared(source="test")
    assert fired == ["got-it"], (
        "notify_session_cleared must invoke every registered "
        "on_session_expired callback"
    )


# ---------------------------------------------------------------
# 2) multiple subscribers all see the event
# ---------------------------------------------------------------

def test_notify_session_cleared_fans_out_to_all_subscribers():
    supervisor, _ = _make_supervisor()
    fired: list[str] = []

    for tag in ("a", "b", "c"):
        tag_holder = [tag]

        def _cb(tag=tag_holder[0]):
            fired.append(tag)

        supervisor.on_session_expired(_cb)

    supervisor.notify_session_cleared(source="test")

    assert sorted(fired) == ["a", "b", "c"]


# ---------------------------------------------------------------
# 3) raising callbacks don't break the others
# ---------------------------------------------------------------

def test_notify_session_cleared_isolates_callback_exceptions():
    supervisor, _ = _make_supervisor()
    fired: list[str] = []

    def _boom():
        raise RuntimeError("subscriber intentionally failed")

    def _good():
        fired.append("good")

    supervisor.on_session_expired(_boom)
    supervisor.on_session_expired(_good)

    # Must not raise even though the first callback blows up.
    supervisor.notify_session_cleared(source="test")

    assert fired == ["good"], (
        "a raising on_session_expired callback must not stop later "
        "callbacks from running"
    )


# ---------------------------------------------------------------
# 4) silent-refresh latch is reset
# ---------------------------------------------------------------

def test_notify_session_cleared_resets_silent_refresh_latch():
    supervisor, _ = _make_supervisor()
    supervisor._silently_refreshing = True
    supervisor._silent_refresh_failures = 5
    supervisor._silent_refresh_next_attempt = 999_999_999.0

    supervisor.notify_session_cleared(source="test")

    assert supervisor._silently_refreshing is False
    assert supervisor._silent_refresh_failures == 0
    assert supervisor._silent_refresh_next_attempt == 0.0


# ---------------------------------------------------------------
# 5) idempotent — twice = two fires
# ---------------------------------------------------------------

def test_notify_session_cleared_is_idempotent_in_count():
    supervisor, _ = _make_supervisor()
    fired = threading.Event() if False else None
    counts: list[int] = [0]

    def _cb():
        counts[0] += 1

    supervisor.on_session_expired(_cb)

    supervisor.notify_session_cleared(source="first")
    supervisor.notify_session_cleared(source="second")

    assert counts[0] == 2, (
        "each notify_session_cleared call must fire callbacks once; "
        "this is by design (no debouncing, subscribers decide what to do)"
    )
