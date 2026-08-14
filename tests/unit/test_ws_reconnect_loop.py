"""
Unit tests for ``agent.cloud_api.cloud_api._appsync_ws_reconnect_loop`` and
the auth-failure sharing primitives it depends on.

The reconnect loop is a background thread target, so these tests build a fake
``WebSocketApp`` (no real network) and drive its ``on_error``/``on_close``
hooks manually — that's the path that was previously silent and caused an
infinite 401 reconnect storm. We assert three exit conditions:

  1. **Auth failure (401/403)** observed via on_error/on_close → loop exits
     within the next iteration and sets the process-global ``_auth_failure_event``.
  2. **Hard failure limit** (``_WS_HARD_FAILURE_LIMIT``) reached → loop exits
     even when errors do not match the 401/403 pattern.
  3. **Cross-subscription signalling**: a 401 in subscription A causes
     subscription B's loop to bail out at the top of its next iteration
     without ever issuing a TCP upgrade.

Also covers the ``_install_session_recovery_hook`` / ``clear_session_invalidated``
lifecycle so a re-login can lift the latch.
"""

import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure ECAN_APP_ID=cn BEFORE any project imports (mirror test_cloudbase_adapter).
os.environ.setdefault("ECAN_APP_ID", "cn")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

from agent.cloud_api import cloud_api as ca  # noqa: E402


# ============================================================
# Helpers
# ============================================================


class FakeWebSocketApp:
    """Mimics enough of ``websocket.WebSocketApp`` for the reconnect loop.

    The loop calls ``build_ws_fn(token, host, signed_url)`` and then
    ``ws.run_forever(...)``.  We capture the hooks the loop installs, run
    them synchronously according to a script the test sets up, and report
    when the loop has exited.
    """

    def __init__(self, script=None):
        # script: list of dicts, each describing one iteration of
        # run_forever().  Possible keys:
        #   "exit_immediately": bool — ws.run_forever returns right away
        #   "on_error": str | None — error message to deliver
        #   "on_close": (code, msg) | None — close payload to deliver
        self.script = script or []
        self.idx = 0
        self.connected_calls = 0
        self.exit_reason = None  # "auth" | "hard_limit" | "transient_exhausted" | None
        self._loop_finished = threading.Event()
        self.on_error = None
        self.on_close = None
        self.on_open = None

    def run_forever(self, **_kwargs):
        self.connected_calls += 1
        while self.idx < len(self.script):
            step = self.script[self.idx]
            self.idx += 1
            if step.get("exit_immediately"):
                return  # mimics ws.run_forever returning on connection drop
            if "on_error" in step and self.on_error is not None:
                self.on_error(self, step["on_error"])
            if "on_close" in step and self.on_close is not None:
                code, msg = step["on_close"]
                self.on_close(self, code, msg)


def _run_loop_in_thread(script, *, initial_token="tok-initial", max_retries=2,
                        base_backoff=0.001, timeout=2.0):
    """Run ``_appsync_ws_reconnect_loop`` against a fake WS and return the thread.

    Returns the thread + the FakeWebSocketApp(s) it created so the test can
    assert on them.  We use a tiny ``base_backoff`` so transient retries
    don't blow up the test runtime; auth failures still return immediately.
    """
    apps: list[FakeWebSocketApp] = []

    def build_ws(token, host, signed_url):
        # Pick the next script.  Tests usually provide one script repeated;
        # we cycle through it by referencing the same FakeWebSocketApp each
        # iteration (the loop's wrapper replaces on_error/on_close each
        # time, so reusing is fine).
        if not apps:
            apps.append(FakeWebSocketApp(script))
        return apps[0]

    thread = threading.Thread(
        target=ca._appsync_ws_reconnect_loop,
        args=("TestLabel", "wss://invalid/", initial_token, build_ws),
        kwargs={"max_retries": max_retries, "base_backoff": base_backoff},
        daemon=True,
    )
    thread.start()
    thread.join(timeout=timeout)
    return thread, apps


# ============================================================
# Tests for the auth-failure sharing primitives
# ============================================================


class TestAuthFailureLatch:
    """Direct tests of the process-global latch."""

    def setup_method(self):
        # Reset the latch between tests — order matters here.
        ca.clear_session_invalidated()

    def teardown_method(self):
        ca.clear_session_invalidated()

    def test_initial_state_is_clean(self):
        assert ca.is_session_invalidated() is False

    def test_flag_sets_event_once(self):
        ca._flag_auth_failure("Sub1", "on_close=401 Unauthorized")
        assert ca.is_session_invalidated() is True

        # Second call is idempotent — event stays set, no exception.
        ca._flag_auth_failure("Sub2", "on_error=401")
        assert ca.is_session_invalidated() is True

    def test_clear_resets_state(self):
        ca._flag_auth_failure("Sub1", "on_close=401")
        assert ca.is_session_invalidated() is True

        ca.clear_session_invalidated()
        assert ca.is_session_invalidated() is False


# ============================================================
# Tests for the reconnect loop's three exit paths
# ============================================================


class TestReconnectLoopExitsOn401:
    """Scenario: handshake 401 raised via on_error → loop must exit."""

    def setup_method(self):
        ca.clear_session_invalidated()

    def teardown_method(self):
        ca.clear_session_invalidated()

    def test_on_error_401_stops_loop(self):
        # First (and only) iteration: ws.run_forever triggers on_error with
        # a 401 handshake message, then returns.
        script = [{"on_error": "Handshake status 401 Unauthorized"}]
        thread, apps = _run_loop_in_thread(script, timeout=2.0)

        assert not thread.is_alive(), "Loop should exit on 401 within 1 iteration"
        assert ca.is_session_invalidated() is True
        assert apps[0].connected_calls == 1

    def test_on_close_401_stops_loop(self):
        # Some TCB / AppSync deployments close cleanly with a 401 code rather
        # than invoking on_error first.
        script = [{"on_close": (401, "Unauthorized")}]
        thread, apps = _run_loop_in_thread(script, timeout=2.0)

        assert not thread.is_alive()
        assert ca.is_session_invalidated() is True
        assert apps[0].connected_calls == 1

    def test_on_close_403_stops_loop(self):
        script = [{"on_close": (403, "Forbidden")}]
        thread, apps = _run_loop_in_thread(script, timeout=2.0)

        assert not thread.is_alive()
        assert ca.is_session_invalidated() is True

    def test_cross_subscription_bail_out(self):
        """Subscription A detects a 401 → subscription B should never connect.

        We simulate B starting *after* A has already flagged the latch.
        """
        ca._flag_auth_failure("CloudLLMTask", "on_close=401 Unauthorized")
        assert ca.is_session_invalidated() is True

        # B's build_ws is called by the loop *if* it gets past the latch.
        # If our bail-out works, build_ws is never invoked.
        build_ws_calls: list[str] = []

        def build_ws(token, host, signed_url):
            build_ws_calls.append(signed_url)
            return FakeWebSocketApp([])

        thread = threading.Thread(
            target=ca._appsync_ws_reconnect_loop,
            args=("StoryUpdate", "wss://invalid/", "tok", build_ws),
            daemon=True,
        )
        thread.start()
        thread.join(timeout=2.0)

        assert not thread.is_alive(), "Loop B should bail at top of next iteration"
        assert build_ws_calls == [], "Loop B must not issue any TCP upgrade"


class TestReconnectLoopHardFailureLimit:
    """Scenario: backend returns 1006 every time → loop must stop after N.

    These errors do NOT match the 401/403 pattern, so without the hard
    limit the loop would loop forever (no exception, no auth match).
    """

    def setup_method(self):
        ca.clear_session_invalidated()
        ca._WS_HARD_FAILURE_LIMIT = 3  # shrink for test speed

    def teardown_method(self):
        ca.clear_session_invalidated()
        ca._WS_HARD_FAILURE_LIMIT = 10  # restore default

    def test_close_1006_loop_exits_after_limit(self):
        # Each iteration: on_close(1006, "") then exit.  Loop keeps
        # calling build_ws until consecutive_failures >= limit, then exits.
        script = [{"on_close": (1006, "abnormal closure")} for _ in range(20)]
        thread, apps = _run_loop_in_thread(script, max_retries=999, timeout=2.0)

        assert not thread.is_alive(), "Loop must exit after hard failure limit"
        assert ca.is_session_invalidated() is False, (
            "1006 is not an auth failure — global latch should NOT be set"
        )
        # We connect until we hit the limit (3 in this test).  Allow 1-5
        # attempts to absorb the race between on_close callback and the
        # limit check at end of run_forever.
        assert 1 <= apps[0].connected_calls <= 5


class TestReconnectLoopRespectsMaxRetries:
    """Scenario: transient exception → loop honors ``max_retries`` then exits."""

    def setup_method(self):
        ca.clear_session_invalidated()

    def teardown_method(self):
        ca.clear_session_invalidated()

    def test_transient_exception_exits_after_max_retries(self):
        # The legacy code path: build_ws raises a transient exception.
        def build_ws(token, host, signed_url):
            raise OSError("simulated network glitch")

        thread = threading.Thread(
            target=ca._appsync_ws_reconnect_loop,
            args=("TestLabel", "wss://invalid/", "tok", build_ws),
            kwargs={"max_retries": 2, "base_backoff": 0.001},
            daemon=True,
        )
        thread.start()
        thread.join(timeout=2.0)

        assert not thread.is_alive(), "Loop must exit after max_retries transient failures"
        assert ca.is_session_invalidated() is False, (
            "Transient errors must not flag auth failure"
        )


# ============================================================
# Tests for the SessionSupervisor recovery hook
# ============================================================


class TestSessionRecoveryHook:
    """The hook should clear the latch on refresh and be idempotent."""

    def setup_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False

    def teardown_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False

    def test_install_succeeds_when_supervisor_available(self):
        supervisor = MagicMock()
        supervisor.refreshed_cbs = []  # we'll mirror the real API
        supervisor.on_session_refreshed = lambda cb: supervisor.refreshed_cbs.append(cb)

        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            assert ca._install_session_recovery_hook() is True
            assert len(supervisor.refreshed_cbs) == 1

    def test_install_is_idempotent(self):
        supervisor = MagicMock()
        supervisor.refreshed_cbs = []
        supervisor.on_session_refreshed = lambda cb: supervisor.refreshed_cbs.append(cb)

        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            assert ca._install_session_recovery_hook() is True
            assert ca._install_session_recovery_hook() is True
            assert ca._install_session_recovery_hook() is True
            assert len(supervisor.refreshed_cbs) == 1, (
                "Second install must be a no-op, not double-register"
            )

    def test_install_returns_false_when_supervisor_missing(self):
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=None):
            assert ca._install_session_recovery_hook() is False
            assert ca._session_recovery_hook_installed is False

    def test_refresh_callback_clears_latch(self):
        supervisor = MagicMock()
        supervisor.refreshed_cbs = []
        supervisor.on_session_refreshed = lambda cb: supervisor.refreshed_cbs.append(cb)

        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            ca._install_session_recovery_hook()

            # Simulate the latch being set, then refresh firing.
            ca._flag_auth_failure("TestSub", "on_close=401")
            assert ca.is_session_invalidated() is True

            supervisor.refreshed_cbs[0]({"sub": "u1"})
            assert ca.is_session_invalidated() is False


# ============================================================
# Tests for the proactive-close hook
# ============================================================


def _make_supervisor_with_two_cbs():
    """Returns (supervisor_mock, list_of_refreshed_cbs)."""
    supervisor = MagicMock()
    refreshed_cbs: list = []
    supervisor.on_session_refreshed = lambda cb: refreshed_cbs.append(cb)
    return supervisor, refreshed_cbs


class TestProactiveCloseHook:
    """The refresh callback should close all currently-active ws so the
    reconnect loop rebuilds the signed URL with the new token, instead of
    waiting for the server to eventually drop the old connection."""

    def setup_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False
        ca._proactive_close_hook_installed = False
        with ca._active_ws_lock:
            ca._active_ws_by_label.clear()

    def teardown_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False
        ca._proactive_close_hook_installed = False
        with ca._active_ws_lock:
            ca._active_ws_by_label.clear()

    def test_install_registers_with_supervisor(self):
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            assert ca._install_proactive_close_hook() is True
            assert ca._proactive_close_hook_installed is True
            assert len(refreshed_cbs) == 1

    def test_install_is_idempotent(self):
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            assert ca._install_proactive_close_hook() is True
            assert ca._install_proactive_close_hook() is True
            assert ca._install_proactive_close_hook() is True
            assert len(refreshed_cbs) == 1

    def test_install_returns_false_when_supervisor_missing(self):
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=None):
            assert ca._install_proactive_close_hook() is False
            assert ca._proactive_close_hook_installed is False

    def test_refresh_closes_all_active_ws(self):
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            ca._install_proactive_close_hook()

            # Register two fake ws (different labels, like CloudLLMTask +
            # SceneComplete would do).
            ws_a = MagicMock()
            ws_b = MagicMock()
            ca.register_active_ws("CloudLLMTask", ws_a)
            ca.register_active_ws("SceneComplete", ws_b)

            # Simulate the supervisor firing on_session_refreshed.
            refreshed_cbs[0]({"sub": "u1"})

            ws_a.close.assert_called_once_with()
            ws_b.close.assert_called_once_with()

            # After the sweep, the registry should be empty so the loop's
            # next iteration can re-register its (newly-signed) ws.
            with ca._active_ws_lock:
                assert ca._active_ws_by_label == {}

    def test_refresh_is_safe_with_no_active_ws(self):
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            ca._install_proactive_close_hook()

            # No ws registered — refresh still fires without raising.
            refreshed_cbs[0]({"sub": "u1"})

    def test_refresh_survives_close_exception(self):
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            ca._install_proactive_close_hook()

            ws_broken = MagicMock()
            ws_broken.close.side_effect = RuntimeError("already closed")
            ws_ok = MagicMock()
            ca.register_active_ws("Bad", ws_broken)
            ca.register_active_ws("Good", ws_ok)

            # Should not raise even if one close() explodes.
            refreshed_cbs[0]({"sub": "u1"})

            ws_broken.close.assert_called_once_with()
            ws_ok.close.assert_called_once_with()

    def test_register_overwrites_previous_ws_for_same_label(self):
        ws1 = MagicMock(name="ws1")
        ws2 = MagicMock(name="ws2")
        ca.register_active_ws("CloudLLMTask", ws1)
        ca.register_active_ws("CloudLLMTask", ws2)

        # Only the latest ws is in the registry.
        with ca._active_ws_lock:
            assert list(ca._active_ws_by_label.values()) == [ws2]

    def test_unregister_removes_ws(self):
        ws = MagicMock(name="ws")
        ca.register_active_ws("CloudLLMTask", ws)
        ca.unregister_active_ws("CloudLLMTask")
        with ca._active_ws_lock:
            assert "CloudLLMTask" not in ca._active_ws_by_label

    def test_unregister_does_nothing_if_label_unknown(self):
        ca.unregister_active_ws("NotRegistered")  # must not raise

    def test_unregister_ignores_stale_ws(self):
        ws_new = MagicMock(name="new")
        ws_stale = MagicMock(name="stale")
        ca.register_active_ws("CloudLLMTask", ws_new)

        # A late unregister for an already-replaced ws is a no-op.
        ca.unregister_active_ws("CloudLLMTask", ws_stale)
        with ca._active_ws_lock:
            assert ca._active_ws_by_label["CloudLLMTask"] is ws_new


class TestReconnectLoopRegistersAndUnregistersActiveWs:
    """The loop's life cycle around ``register_active_ws`` / ``unregister_active_ws``."""

    def setup_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False
        ca._proactive_close_hook_installed = False
        with ca._active_ws_lock:
            ca._active_ws_by_label.clear()

    def teardown_method(self):
        ca.clear_session_invalidated()
        ca._session_recovery_hook_installed = False
        ca._proactive_close_hook_installed = False
        with ca._active_ws_lock:
            ca._active_ws_by_label.clear()

    def test_registered_ws_is_unregistered_after_run_forever_returns(self):
        # A ws that simply returns from run_forever (no error).  The loop
        # should then disconnect, retry, hit max_retries, and exit.  We
        # assert the registry ends up empty.
        script = [{"exit_immediately": True}] * 5
        thread, apps = _run_loop_in_thread(script, max_retries=2, timeout=2.0)

        assert not thread.is_alive()
        with ca._active_ws_lock:
            assert ca._active_ws_by_label == {}, (
                "Loop must unregister every ws before exiting"
            )

    def test_refresh_during_open_connection_triggers_close(self):
        """If a refresh fires while run_forever is blocked, our wrapper should
        proactively close the ws.  This is the core value of the hook."""
        # Block the fake ws on a long sleep; we close it externally.
        import time

        blocker = threading.Event()

        class BlockingWs:
            def __init__(self):
                self.connected = False
                self.closed = False
                self.on_error = None
                self.on_close = None

            def run_forever(self, **_kw):
                self.connected = True
                blocker.wait(timeout=2.0)
                # Returns when ``blocker.set()`` is called from outside
                # (mimicking server-initiated close or our own ws.close()).

            def close(self):
                self.closed = True
                blocker.set()

        ws = BlockingWs()
        apps = [ws]

        def build_ws(token, host, signed_url):
            return ws

        thread = threading.Thread(
            target=ca._appsync_ws_reconnect_loop,
            args=("RefreshTest", "wss://invalid/", "tok", build_ws),
            kwargs={"max_retries": 99, "base_backoff": 0.001},
            daemon=True,
        )
        thread.start()

        # Wait for ws to be registered.
        for _ in range(50):
            with ca._active_ws_lock:
                if "RefreshTest" in ca._active_ws_by_label:
                    break
            time.sleep(0.02)
        with ca._active_ws_lock:
            assert "RefreshTest" in ca._active_ws_by_label

        # Simulate supervisor firing on_session_refreshed with the hook
        # already installed.  The hook should call ws.close().
        supervisor, refreshed_cbs = _make_supervisor_with_two_cbs()
        with patch("auth.session_supervisor.get_session_supervisor",
                   return_value=supervisor):
            ca._install_proactive_close_hook()
            refreshed_cbs[0]({"sub": "u1"})

        # Wait for the loop thread to finish (ws.close unblocks run_forever).
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert ws.closed is True
        assert ws.connected is True
        with ca._active_ws_lock:
            assert "RefreshTest" not in ca._active_ws_by_label