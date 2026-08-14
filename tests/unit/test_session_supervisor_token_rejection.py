"""
Unit tests for the token-rejection nudge path.

Background
----------
``SessionSupervisor.notify_token_rejected`` is called by AppSync / CloudBase
clients whenever the server responds with UNAUTHENTICATED.  Before the fix,
the underlying ``_tick`` looked at the locally decoded ``exp`` and decided
nothing needed refreshing if ``remaining > REFRESH_LEAD_SECONDS``.  When the
local cache and the server disagreed (server says expired, local exp says
9 minutes left), the nudge was a no-op and every subsequent sync still hit
the same UNAUTHENTICATED wall until the next auto-retry tick minutes later.

After the fix, a nudge is treated as authoritative: ``_tick(force=True)``
collapses ``remaining`` to zero so the supervisor actually attempts the
refresh / silent re-auth right then.

We exercise four scenarios:

  1. ``_tick(force=True)`` with a refresh_token forces a refresh attempt
     even when local exp says 581s remain  (regression guard for the bug).
  2. ``_tick(force=True)`` without a refresh_token (CN WeChat) drives the
     silent-refresh path instead.
  3. ``_tick()`` (no force) with 581s remaining stays a no-op  (so the
     30s background tick keeps its old behaviour for non-nudged calls).
  4. ``OfflineSyncManager.sync_pending_queue`` running into UNAUTHENTICATED
     nudges the supervisor AND waits for the session to come back before
     marking the task.  This is the end-to-end shape the bugfix needs to
     preserve.
"""

import importlib
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------


def _make_jwt(exp_unix: int) -> str:
    """Build a minimal <base64header>.<base64payload>.<sig> string.

    We don't need a real signature — the supervisor decodes payloads
    unverified (same trust model as AuthManager._decode_jwt_payload_unsafe).
    """
    import base64
    import json

    def _b64(obj: bytes) -> str:
        return base64.urlsafe_b64encode(obj).rstrip(b"=").decode("ascii")

    header = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    payload = _b64(json.dumps({"exp": exp_unix, "sub": "test"}).encode())
    return f"{header}.{payload}.sig"


class _FakeAuthManager:
    """Bare-bones double that quacks like AuthManager for the supervisor."""

    def __init__(self, *, signed_in: bool = True, tokens: dict | None = None):
        self.signed_in = signed_in
        self.tokens = tokens or {}


def _build_supervisor(am):
    ss = importlib.import_module("auth.session_supervisor")
    return ss.SessionSupervisor(am)


# ---------------------------------------------------------------
# 1) force=True with refresh_token triggers _attempt_refresh
# ---------------------------------------------------------------

def test_tick_force_with_refresh_token_attempts_refresh(monkeypatch):
    """Nudge with local remaining=581s must still trigger a refresh.

    Bug guard: previously _tick saw remaining > REFRESH_LEAD_SECONDS (300s)
    and returned without doing anything, so notify_token_rejected was a
    silent no-op when local TTL was stale.
    """
    ss = importlib.import_module("auth.session_supervisor")

    future_exp = int(time.time()) + 581  # matches the value in the bug log
    access_token = _make_jwt(future_exp)
    am = _FakeAuthManager(
        tokens={
            "AccessToken": access_token,
            "RefreshToken": "rt-123",
        },
    )
    supervisor = _build_supervisor(am)

    refresh_calls: list[str] = []
    silent_calls: list[int] = []

    def fake_attempt(rt):
        refresh_calls.append(rt)
        return True

    def fake_silent(exp):
        silent_calls.append(exp)

    monkeypatch.setattr(supervisor, "_attempt_refresh", fake_attempt)
    monkeypatch.setattr(supervisor, "_drive_silent_refresh", fake_silent)

    supervisor._tick(force=True)

    assert refresh_calls == ["rt-123"], (
        "force=True with a refresh_token must call _attempt_refresh "
        "even when local remaining is far above REFRESH_LEAD_SECONDS"
    )
    assert silent_calls == [], (
        "_drive_silent_refresh must NOT run when refresh_token is present"
    )


# ---------------------------------------------------------------
# 2) force=True without refresh_token drives silent re-auth
# ---------------------------------------------------------------

def test_tick_force_without_refresh_token_drives_silent_refresh(monkeypatch):
    """CN WeChat path: no refresh_token, so the nudge triggers a silent
    WeChat OAuth via _drive_silent_refresh.
    """
    ss = importlib.import_module("auth.session_supervisor")

    future_exp = int(time.time()) + 581
    access_token = _make_jwt(future_exp)
    am = _FakeAuthManager(
        tokens={"AccessToken": access_token},  # no RefreshToken
    )
    supervisor = _build_supervisor(am)

    refresh_calls: list[str] = []
    silent_calls: list[int] = []

    def fake_attempt(rt):
        refresh_calls.append(rt)
        return True

    def fake_silent(exp):
        silent_calls.append(exp)

    monkeypatch.setattr(supervisor, "_attempt_refresh", fake_attempt)
    monkeypatch.setattr(supervisor, "_drive_silent_refresh", fake_silent)

    supervisor._tick(force=True)

    assert silent_calls == [future_exp], (
        "force=True without a refresh_token must drive the silent "
        "WeChat re-auth path with the original exp"
    )
    assert refresh_calls == [], (
        "_attempt_refresh must NOT run when there is no refresh_token"
    )


# ---------------------------------------------------------------
# 3) Non-forced _tick stays a no-op for fresh tokens (no regression)
# ---------------------------------------------------------------

def test_tick_no_force_still_skips_when_remaining_far_above_lead(monkeypatch):
    """The background 30s tick must keep its old behaviour: when local
    TTL says we're comfortably above REFRESH_LEAD_SECONDS (300s), don't
    refresh on every tick.  Only ``force=True`` from a nudge should
    collapse that guard.
    """
    ss = importlib.import_module("auth.session_supervisor")

    far_future_exp = int(time.time()) + 3600  # 1 hour — plenty of headroom
    access_token = _make_jwt(far_future_exp)
    am = _FakeAuthManager(
        tokens={
            "AccessToken": access_token,
            "RefreshToken": "rt-123",
        },
    )
    supervisor = _build_supervisor(am)

    refresh_calls: list[str] = []
    silent_calls: list[int] = []

    def fake_attempt(rt):
        refresh_calls.append(rt)
        return True

    def fake_silent(exp):
        silent_calls.append(exp)

    monkeypatch.setattr(supervisor, "_attempt_refresh", fake_attempt)
    monkeypatch.setattr(supervisor, "_drive_silent_refresh", fake_silent)

    supervisor._tick(force=False)

    assert refresh_calls == [], (
        "background ticks must not preemptively refresh a token that "
        "still has well over REFRESH_LEAD_SECONDS of local TTL left"
    )
    assert silent_calls == [], (
        "background ticks must not drive silent re-auth either"
    )


# ---------------------------------------------------------------
# 4) notify_token_rejected always passes force=True (wiring test)
# ---------------------------------------------------------------

def test_notify_token_rejected_uses_force_flag(monkeypatch):
    """The public ``notify_token_rejected`` API must invoke ``_tick`` with
    force=True — this is the contract the rest of the app relies on.
    """
    ss = importlib.import_module("auth.session_supervisor")

    future_exp = int(time.time()) + 581
    am = _FakeAuthManager(
        tokens={"AccessToken": _make_jwt(future_exp), "RefreshToken": "rt"},
    )
    supervisor = _build_supervisor(am)

    captured = {}

    def fake_tick(force=False):
        captured["force"] = force

    monkeypatch.setattr(supervisor, "_tick", fake_tick)

    supervisor.notify_token_rejected(source="app:test")

    assert captured.get("force") is True, (
        "notify_token_rejected must pass force=True so the nudge is "
        "authoritative regardless of local TTL"
    )


# ---------------------------------------------------------------
# 5) End-to-end: OfflineSyncManager retries a task after refresh
# ---------------------------------------------------------------

class _FakeSyncResult:
    """Minimal dict-like for service.sync_to_cloud return values."""

    def __init__(self, success: bool, errors=None):
        self._d = {
            "success": success,
            "synced": success,
            "cached": False,
            "errors": errors or [],
        }

    def __getitem__(self, k):
        return self._d[k]

    def get(self, k, default=None):
        return self._d.get(k, default)


class _RecordingService:
    """Stand-in for cloud_api.get_cloud_service(data_type).sync_to_cloud."""

    def __init__(self, responses):
        # responses: list of _FakeSyncResult returned on each call
        self._responses = list(responses)
        self.calls = 0

    def sync_to_cloud(self, items, operation, timeout):
        self.calls += 1
        if not self._responses:
            raise AssertionError(
                f"RecordingService received more sync_to_cloud calls "
                f"({self.calls}) than prepared responses"
            )
        return self._responses.pop(0)


def test_offline_sync_manager_retries_task_after_token_refresh(monkeypatch):
    """The OfflineSyncManager must:

      1. try the task,
      2. on UNAUTHENTICATED, nudge the supervisor and wait for the session
         to come back,
      3. retry the SAME task once the supervisor signals a refresh,
      4. advance through the rest of the batch normally.

    This is the user-visible behaviour the bugfix unlocks.
    """
    osm = importlib.import_module("agent.cloud_api.offline_sync_manager")

    # First call: UNAUTHENTICATED; subsequent calls succeed.
    service = _RecordingService([
        _FakeSyncResult(False, errors=["Invalid or expired access token"]),
        _FakeSyncResult(True),
        _FakeSyncResult(True),
    ])

    # Two pending tasks so we can verify the second one also gets processed
    # in the same batch (regression guard: the old code break'd out of the
    # for-loop and stranded everything on the queue for the next 5-min tick).
    queue = SimpleNamespace(
        _pending=[
            {"id": "t1", "data_type": "agent", "operation": "add",
             "data": {"id": "agent-1"}},
            {"id": "t2", "data_type": "agent", "operation": "add",
             "data": {"id": "agent-2"}},
        ],
    )

    class _FakeQueue:
        def __init__(self, tasks):
            self._tasks = list(tasks)
            self.successes = []
            self.failures = []

        def get_pending_tasks(self):
            return list(self._tasks)

        def get_failed_tasks(self):
            return []

        def mark_success(self, task_id):
            self.successes.append(task_id)
            self._tasks = [t for t in self._tasks if t["id"] != task_id]

        def mark_failed(self, task_id, *_args, **_kwargs):
            self.failures.append(task_id)

    fake_queue = _FakeQueue(queue._pending)

    # Supervisor double: track nudge calls, immediately fire a refreshed
    # event so sync_pending_queue wakes up from _wait_for_active_session.
    class _FakeSupervisor:
        def __init__(self, osm):
            self._osm = osm
            self._state = "active"
            self._cond = threading.Condition()
            self.notify_calls = []

        def notify_token_rejected(self, *, source):
            self.notify_calls.append(source)
            # Simulate the supervisor successfully rotating tokens on a
            # background thread; wake the OfflineSyncManager waiter.
            def _emit():
                with self._cond:
                    self._state = "active"
                    self._cond.notify_all()
            threading.Thread(target=_emit, daemon=True).start()

        def on_session_refreshed(self, cb):
            # Not needed for this test — we drive state directly.
            pass

        def on_session_expired(self, cb):
            pass

        def on_session_expiring_soon(self, cb):
            pass

        def is_silent_refresh_in_flight(self):
            return False

    fake_sup = _FakeSupervisor(None)

    # Patch the supervisor + queue factories the manager uses.
    monkeypatch.setattr(osm, "get_offline_sync_queue", lambda: fake_queue)
    monkeypatch.setattr(osm, "get_cloud_service", lambda _dt: service)

    # Build the manager but skip its __init__ supervisor wiring.
    mgr = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    mgr.sync_queue = fake_queue
    mgr.OFFLINE_SYNC_ENABLED = True
    mgr._session_state = "active"
    mgr._pause_lock = threading.Condition()
    mgr._notify_supervisor_of_token_rejection = (
        lambda source: fake_sup.notify_token_rejected(source=source)
    )
    # When the manager asks "are we active?", answer from fake_sup's state.
    def _wait(timeout):
        deadline = time.monotonic() + timeout
        with mgr._pause_lock:
            while True:
                if mgr._session_state == "active" and fake_sup._state == "active":
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                mgr._pause_lock.wait(timeout=remaining)
    mgr._wait_for_active_session = _wait

    result = mgr.sync_pending_queue(timeout_per_task=5.0)

    assert fake_sup.notify_calls, (
        "OfflineSyncManager must nudge the supervisor on UNAUTHENTICATED"
    )
    assert "t1" in fake_queue.successes, (
        f"task t1 must be retried and synced after refresh; "
        f"successes={fake_queue.successes} failures={fake_queue.failures}"
    )
    # Bug regression guard: under the old for-loop, hitting UNAUTHENTICATED
    # on t1 broke out of the loop and stranded t2 on the pending queue for
    # the next 5-min tick.  After the fix the SAME batch processes t2 too.
    assert "t2" in fake_queue.successes, (
        f"task t2 must also sync in the same batch after the supervisor "
        f"refresh — otherwise the old 'break out of for-loop on UNAUTHENTICATED' "
        f"behaviour has resurfaced. successes={fake_queue.successes} "
        f"failures={fake_queue.failures}"
    )
    assert result["synced"] == 2 and result["failed"] == 0, (
        f"both tasks must sync after a single nudge+wait; got {result}"
    )
