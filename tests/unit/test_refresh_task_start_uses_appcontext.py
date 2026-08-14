"""Regression test: ``_start_refresh_task_attempt`` must successfully start
the token refresh loop on a known running event loop, even when called from
a thread that has no running loop of its own.

Background (runlog 2026-08-14 18:37:56):
    AuthManager.__init__ -> try_restore_cloudbase_session -> start_refresh_task
runs during early startup, BEFORE the qasync main loop has begun running.
The legacy implementation used ``asyncio.get_running_loop()`` which only sees
the current thread's loop, so the 5-attempt retry chain (which runs on a
fresh thread via ``threading.Timer``) never finds the qasync loop and the
refresh loop never starts. The fix schedules onto ``AppContext.main_loop``
via ``run_coroutine_threadsafe`` once that loop is running.
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest


def _make_auth_manager_stub():
    """Construct a stub AuthManager that exposes only the bits the method
    under test touches. Keeps the test independent of heavy Cognito/CloudBase
    imports that ``AuthManager.__init__`` would otherwise pull in."""
    am = MagicMock()
    am.tokens = {"AccessToken": "AT-stub", "RefreshToken": "RT-stub"}
    am._is_cn = True
    am.refresh_task = None
    # ``MagicMock`` auto-creates ``_REFRESH_LOOP_START_MAX_RETRIES`` and
    # ``_REFRESH_LOOP_START_RETRY_DELAY`` as MagicMocks, which breaks ``<``
    # comparisons in the retry-budget branch. Pin them to real values so the
    # legacy fallback path is testable.
    am._REFRESH_LOOP_START_MAX_RETRIES = 5
    am._REFRESH_LOOP_START_RETRY_DELAY = 3
    return am


def test_start_refresh_task_schedules_via_appcontext_loop(monkeypatch):
    """When AppContext.main_loop is running, the task must be scheduled via
    run_coroutine_threadsafe, NOT via get_running_loop on the calling thread."""
    # Pretend the calling thread has no running loop.
    async def _never_called():
        raise AssertionError("should not run on the calling thread")

    am = _make_auth_manager_stub()

    # Build a fake qasync loop that says it is running.
    fake_loop = MagicMock()
    fake_loop.is_running.return_value = True

    fake_future = MagicMock()
    fake_future.done.return_value = False

    with patch("app_context.AppContext.get_main_loop", return_value=fake_loop), \
         patch("auth.auth_manager.asyncio.run_coroutine_threadsafe",
               return_value=fake_future) as fake_rcts, \
         patch("auth.auth_manager.asyncio.get_running_loop",
               side_effect=AssertionError("must not call get_running_loop")):
        from auth.auth_manager import AuthManager
        AuthManager._start_refresh_task_attempt(am, attempt=0)

    fake_rcts.assert_called_once()
    # The coroutine passed to run_coroutine_threadsafe is the bound
    # _token_refresh_loop method on the AuthManager stub.
    args, _kwargs = fake_rcts.call_args
    assert args[1] is fake_loop, "must schedule onto AppContext.main_loop"


def test_start_refresh_task_falls_back_when_loop_not_running(monkeypatch):
    """If AppContext.main_loop exists but qasync hasn't called run_forever()
    yet, the method must NOT silently give up — it should fall back to the
    threading.Timer retry chain so a later attempt can succeed."""
    am = _make_auth_manager_stub()

    # Fake a qasync loop that is created but not yet running.
    fake_loop = MagicMock()
    fake_loop.is_running.return_value = False

    import threading as _threading
    with patch("app_context.AppContext.get_main_loop", return_value=fake_loop), \
         patch.object(_threading, "Timer") as fake_timer:
        from auth.auth_manager import AuthManager
        AuthManager._start_refresh_task_attempt(am, attempt=0)

    # Must have scheduled a retry.
    fake_timer.assert_called_once()
    # Retry delay matches the existing budget.
    args, _kwargs = fake_timer.call_args
    # args = (delay, function, args=[attempt+1])
    delay = args[0]
    assert delay == AuthManager._REFRESH_LOOP_START_RETRY_DELAY * 1


def test_start_refresh_task_uses_caller_loop_when_no_appcontext(monkeypatch):
    """When called from inside a coroutine (e.g. after the loop is already
    running), and AppContext has no loop set, the legacy get_running_loop
    path must still work."""
    am = _make_auth_manager_stub()

    async def _runner():
        # We are now inside a running event loop on the main thread.
        from auth.auth_manager import AuthManager
        with patch("app_context.AppContext.get_main_loop", return_value=None):
            AmOnTheLoop = MagicMock()
            AmOnTheLoop.create_task.return_value = "fake_task"
            with patch("auth.auth_manager.asyncio.get_running_loop",
                       return_value=AmOnTheLoop):
                AuthManager._start_refresh_task_attempt(am, attempt=0)

        AmOnTheLoop.create_task.assert_called_once()
        assert am.refresh_task == "fake_task"

    asyncio.run(_runner())
