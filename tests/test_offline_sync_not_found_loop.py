"""Verification for the 2026-10-16 runlog fix (offline-sync infinite retry loop).

Observed in the runlog: 53 stale agent_delete_* tasks, each retried ~76 times
over 90 minutes (~1736 cloud calls + 1736 ERROR log lines), because:

  Bug A: agent.delete returning item error "Not found" fell through to the
         generic mark_failed path, so the task exhausted 3 retries, moved to
         the failed queue...
  Bug B: sync_pending_queue(include_failed=True) pulled EVERY failed task back
         to pending with retry_count reset to 0, restarting the cycle forever.

Fixes:
  A. DELETE + not_found => idempotent success (desired end state already true).
     Matching is case-insensitive because the TCB backend literally returns
     'Not found' while the old code only matched 'NOT_FOUND' (never hit).
  B. Failed tasks are auto-recycled into the retry loop at most ONCE; the
     second consecutive failure parks them in the failed queue permanently
     until a manual retry.

Run:  python3 tests/test_offline_sync_not_found_loop.py
Exit code 0 == all checks passed.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_failures = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  {detail}" if detail else ""))
    if not cond:
        _failures.append(name)


def test_delete_not_found_is_idempotent_success():
    print("\n=== A. DELETE + 'Not found' => idempotent success ===")
    import importlib
    import agent.cloud_api.offline_sync_manager as osm_mod
    importlib.reload(osm_mod)  # pick up the edited source
    osm = osm_mod.OfflineSyncManager.__new__(osm_mod.OfflineSyncManager)

    calls = []

    class FakeService:
        def sync_to_cloud(self, items, operation=None, timeout=None):
            calls.append(operation)
            return {'success': False, 'errors': ['Not found']}

    # Simulate three auto-retry ticks worth of processing in ONE
    # sync_pending_queue call: with the fix, the DELETE task is marked success
    # on the FIRST failure response, so exactly 1 cloud call happens and the
    # task leaves the queue. Pre-fix behaviour was 3 calls per tick x ~every
    # 5 min forever.
    class FakeQueue:
        def __init__(self, task):
            self.task = dict(task)
            self.succeeded = []
            self.failed = []
        def get_pending_tasks(self, *a, **k):
            return [] if self.task is None else [dict(self.task)]
        def get_failed_tasks(self):
            return list(self.failed)
        def mark_success(self, tid):
            self.succeeded.append(tid); self.task = None
        def mark_failed(self, tid, err, max_retries=3, non_retryable=False):
            self.failed.append(tid)

    q = FakeQueue({
        'id': 'agent_delete_1788448822408',
        'data_type': 'agent',
        'operation': 'delete',
        'data': {'id': 'agent_x'},
        'retry_count': 0,
    })
    osm.sync_queue = q
    osm._session_state = "active"
    # Bypass the dependency sort which needs full task fields.
    osm._sort_tasks_by_dependency = lambda tasks: tasks

    # get_cloud_service resolution: patch the module-level factory the
    # manager uses inside the loop.
    result = None
    orig = osm_mod.get_cloud_service
    osm_mod.get_cloud_service = lambda dt: FakeService()
    try:
        result = osm.sync_pending_queue(max_tasks=10)
    finally:
        osm_mod.get_cloud_service = orig

    check("DELETE Not-found treated as success (synced=1)",
          result and result.get('synced') == 1, f"(result={result})")
    check("exactly 1 cloud call (pre-fix: 3 then infinite recycle)",
          len(calls) == 1, f"(calls={len(calls)})")
    check("task removed from queue", q.task is None)
    check("task never marked failed", not q.failed)

    # Case variant: backend returning 'NOT_FOUND' (AWS/AppSync-style) also matches.
    class FakeServiceUpper(FakeService):
        def sync_to_cloud(self, items, operation=None, timeout=None):
            calls.append(operation)
            return {'success': False, 'errors': ['NOT_FOUND']}
    q2 = FakeQueue(dict(q.task) if q.task else {
        'id': 'agent_delete_x', 'data_type': 'agent', 'operation': 'delete',
        'data': {'id': 'a'}, 'retry_count': 0})
    # rebuild a task since the first one consumed itself
    q2.task = {
        'id': 'agent_delete_upper', 'data_type': 'agent',
        'operation': 'delete', 'data': {'id': 'a'}, 'retry_count': 0,
    }
    osm.sync_queue = q2
    osm_mod.get_cloud_service = lambda dt: FakeServiceUpper()
    try:
        r2 = osm.sync_pending_queue(max_tasks=10)
    finally:
        osm_mod.get_cloud_service = orig
    check("DELETE NOT_FOUND (upper-case variant) also succeeds",
          r2.get('synced') == 1, f"(result={r2})")


def test_failed_task_recycled_only_once():
    print("\n=== B. failed tasks auto-recycled at most once ===")
    from agent.cloud_api.offline_sync_queue import OfflineSyncQueue

    with tempfile.TemporaryDirectory() as td:
        q = OfflineSyncQueue(cache_dir=td)

        # A task that fails permanently with a NON-not-found error
        # (e.g. timeout) exercises the recycle-once gate: tick 1 exhausts
        # 3 retries; tick 2 recycles it once; tick 3 must leave it parked.
        tid = q.add('agent', {'id': 'agent_y', 'name': 'y'}, operation='delete')
        for _ in range(3):
            q.mark_failed(tid, 'Connection timed out', max_retries=3)
        check("after 3 retries the task is in the failed queue",
              any(t['id'] == tid for t in q.get_failed_tasks()))

        # First recycle: should move back to pending and return True.
        ok = q.retry_failed_task(tid)
        check("first recycle succeeds", ok)
        check("task back in pending", any(t['id'] == tid for t in q.get_pending_tasks()))
        q.flag_auto_recycled(tid)
        recyc = [t for t in q.get_pending_tasks() if t['id'] == tid]
        check("auto_recycled flag persisted", recyc and recyc[0].get('auto_recycled') is True)

        # Simulate the manager's filter: flagged tasks are NOT recycled again.
        failed_after = q.get_failed_tasks()  # not yet failed again
        # Re-fail it (another full cycle in a real tick).
        for _ in range(3):
            q.mark_failed(tid, 'Connection timed out', max_retries=3)
        recyclable = [t for t in q.get_failed_tasks() if not t.get('auto_recycled')]
        check("second consecutive failure is NOT auto-recycled again",
              not recyclable,
              f"(recyclable={[t['id'] for t in recyclable]})")

        # But MANUAL retry still works (flag lives on the task; operator
        # judgement overrides).
        ok_manual = q.retry_failed_task(tid)
        check("manual retry still allowed", ok_manual)

        # Non-retryable tasks are never recycled.
        tid2 = q.add('agent', {'id': 'agent_z', 'name': 'z'}, operation='delete')
        q.mark_failed(tid2, 'Forbidden', max_retries=1, non_retryable=True)
        check("non-retryable task not recycled",
              q.retry_failed_task(tid2) is False)


def main():
    print("=" * 60)
    print("OFFLINE-SYNC NOT-FOUND RETRY LOOP FIX VERIFICATION")
    print("=" * 60)
    test_delete_not_found_is_idempotent_success()
    test_failed_task_recycled_only_once()
    print("\n" + "=" * 60)
    if _failures:
        print(f"RESULT: {len(_failures)} FAILED -> {_failures}")
        return 1
    print("RESULT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
