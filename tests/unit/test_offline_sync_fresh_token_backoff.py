"""
Pins the fresh-token cache-lag backoff in OfflineSyncManager.

Background: a CloudBase login finishes, AuthManager.complete_login_from_provider
installs the new JWT, and 30-60 seconds later the SCF gateway still says
401 because the upstream auth cache hasn't propagated the new token yet.
``SessionSupervisor._drive_silent_refresh`` already suppresses
``on_session_expired`` for that grace window, BUT the supervisor has no way
to back the OfflineSyncManager's ``sync_pending_queue`` loop off — every
iteration of the same batch task sees the rejection, calls
``_notify_supervisor_of_token_rejection``, then ``_wait_for_active_session``
returns immediately (session_state never moves out of "active" because the
supervisor swallowed the expiry), and the loop retries the same task ~125ms
later. Runlog 2026-08-14 10:45:09 shows that: 401 at .263, .387, .553.

The fix lives in OfflineSyncManager._is_token_expired_error branch: read
``SessionSupervisor._last_token_installed_at`` and, if the rejection falls
inside the grace window, **break out of the batch instead of nudging +
waiting + retrying**. The task stays on the queue and the next auto-retry
tick picks it up after the cache has caught up.
"""

import importlib
import time
import unittest.mock as mock

import pytest


def _import():
    return importlib.import_module(
        "agent.cloud_api.offline_sync_manager"
    )


def _make_supervisor_with_installed_at(installed_at: float):
    sup = mock.MagicMock()
    sup._last_token_installed_at = installed_at
    # Match the real ``SessionSupervisor.is_fresh_token_rejection`` semantics:
    # return True only if installed_at > 0 AND wall_age < grace (60s).
    sup.is_fresh_token_rejection.return_value = (
        installed_at > 0 and (time.time() - installed_at) < 60
    )
    return sup


def test_fresh_token_rejection_backs_off_batch(monkeypatch):
    """A 401 within the grace window must NOT nudge + retry-storm.

    It must log + break out of the batch, leaving the task on the queue
    for the next auto-retry tick after the cache lag clears.
    """
    osm = _import()

    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._pause_lock = mock.MagicMock()
    manager._notify_supervisor_of_token_rejection = mock.MagicMock()
    manager._wait_for_active_session = mock.MagicMock(return_value=True)

    # Token installed 5 seconds ago — well inside the grace window.
    fresh_sup = _make_supervisor_with_installed_at(time.time() - 5)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: fresh_sup,
    )

    assert manager._is_fresh_token_rejection(), (
        "a 401 5 seconds after install must be classified as fresh-token "
        "cache lag so the batch backs off"
    )


def test_old_token_rejection_does_not_trigger_backoff(monkeypatch):
    """A 401 long after install must NOT short-circuit the retry path."""
    osm = _import()

    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._pause_lock = mock.MagicMock()

    # Token installed 5 minutes ago — well past the grace window.
    old_sup = _make_supervisor_with_installed_at(time.time() - 300)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: old_sup,
    )

    assert not manager._is_fresh_token_rejection(), (
        "a 401 5 minutes after install is a real auth failure — must "
        "fall through to the normal nudge + retry path"
    )


def test_no_supervisor_does_not_trigger_backoff(monkeypatch):
    """When no supervisor is wired (tests, web mode, no auth) the loop must
    keep its old behavior (always retry on 401)."""
    osm = _import()

    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._pause_lock = mock.MagicMock()

    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: None,
    )

    assert not manager._is_fresh_token_rejection(), (
        "without a supervisor wired, every 401 must go through the "
        "normal retry path — we cannot fabricate a 'fresh' signal"
    )


def test_fresh_token_rejection_breaks_batch_without_retrying(monkeypatch):
    """End-to-end shape: when _is_token_expired_error fires AND the token
    is fresh, the loop logs + breaks — does NOT nudge the supervisor,
    does NOT mark_failed, does NOT call _wait_for_active_session."""
    osm = _import()

    sync_queue = mock.MagicMock()
    sync_queue.get_pending_tasks.return_value = iter([
        {"id": "agent_add_X", "data_type": "agent",
         "operation": "add", "data": {"id": "agent_add_X", "name": "x"}},
    ])

    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._pause_lock = mock.MagicMock()
    manager._session_state = "active"
    manager._notify_supervisor_of_token_rejection = mock.MagicMock()
    manager._wait_for_active_session = mock.MagicMock(return_value=True)

    # Fresh token: 10 seconds old.
    fresh_sup = _make_supervisor_with_installed_at(time.time() - 10)
    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: fresh_sup,
    )

    # Stub CloudAPIService.sync_to_cloud so it returns UNAUTHENTICATED.
    sync_to_cloud = mock.MagicMock(return_value={
        "success": False,
        "errors": [{"message": "Invalid or expired access token"}],
    })

    with mock.patch.object(osm, "get_cloud_service",
                           return_value=mock.MagicMock(sync_to_cloud=sync_to_cloud)):
        manager.sync_queue = sync_queue
        result = manager.sync_pending_queue()

    sync_to_cloud.assert_called_once(), (
        "first attempt should happen normally"
    )
    manager._notify_supervisor_of_token_rejection.assert_not_called(), (
        "fresh-token 401 must NOT nudge the supervisor — the supervisor's "
        "grace window already covers it; nudging just floods log + triggers "
        "a tick that we don't want"
    )
    manager._wait_for_active_session.assert_not_called(), (
        "fresh-token 401 must NOT block on _wait_for_active_session — that "
        "loop returns immediately when state is 'active' and is the root "
        "cause of the 125ms retry-storm"
    )
    sync_queue.mark_failed.assert_not_called(), (
        "task must stay on the queue for the next auto-retry tick, not be "
        "marked failed"
    )


def test_repeated_fresh_token_rejections_fall_through_to_nudge(monkeypatch):
    """The same fresh token getting rejected over and over is a real
    revocation, not cache lag.  After ``_FRESH_TOKEN_REJECTION_LIMIT``
    consecutive 401s, ``_is_fresh_token_rejection`` must return False so the
    normal nudge + retry path runs (instead of parking the task indefinitely).

    Without this, the OfflineSyncManager hangs the queue for the entire
    fresh-token grace window (60s) for every task, then waits another 5 min
    between auto-retry ticks, while the user sees a normal-looking GUI and
    every cloud write silently fails.  Reproduced in runlog 2026-08-14 19:02
    where ``addAgents`` returned 401 with a token still showing 9 minutes
    left locally — CloudBase had revoked it because the upstream WeChat
    session expired."""
    osm = _import()

    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._pause_lock = mock.MagicMock()

    # Real SessionSupervisor object so we exercise the counter logic, not
    # a MagicMock that papers over it.
    ss_mod = importlib.import_module("auth.session_supervisor")
    supervisor = ss_mod.SessionSupervisor(mock.MagicMock(signed_in=True, tokens={
        "AccessToken": "stub.stub",
    }))

    # Fresh token: 10 seconds old — within the 60s grace window.
    supervisor._last_token_installed_at = time.time() - 10

    monkeypatch.setattr(
        "auth.session_supervisor.get_session_supervisor",
        lambda: supervisor,
    )

    # First ``_FRESH_TOKEN_REJECTION_LIMIT`` calls still report fresh.
    for i in range(supervisor._FRESH_TOKEN_REJECTION_LIMIT):
        assert manager._is_fresh_token_rejection(), (
            f"call #{i + 1} of {_FRESH_TOKEN_REJECTION_LIMIT} is inside the "
            f"grace window and must still be classified as cache lag"
        )

    # The next call crosses the limit and must give up on the cache-lag
    # hypothesis — the user's local JWT decoder still says 9 minutes of
    # life left, but the server (CloudBase) has revoked the token.
    assert not manager._is_fresh_token_rejection(), (
        "after _FRESH_TOKEN_REJECTION_LIMIT consecutive rejections of a "
        "fresh-by-clock token, the supervisor must stop suppressing the "
        "real-revocation path so the user's session-expired broadcast can "
        "fire and the queue task can be nudged to retry"
    )

    # A freshly installed token resets the counter so the next 401 inside
    # the new grace window is treated as cache lag again.
    supervisor.notify_token_installed()
    assert manager._is_fresh_token_rejection(), (
        "notify_token_installed must reset the rejection counter so a "
        "genuinely fresh token's first 401 isn't poisoned by the previous "
        "token's revoke history"
    )