"""
Pins the graceful thread-pool drain in OfflineSyncManager.stop_auto_retry.

Background: ``stop_auto_retry`` used to call ``self._executor.shutdown(wait=False)``
immediately after stopping the retry thread. Any sync task still executing in the
pool was abandoned mid-flight, so a shutdown/restart could silently drop the last
few queued cloud writes.

The fix tracks in-flight submissions with ``_pending_submissions`` (guarded by
``_submission_lock``), decrements via a Future done-callback, and makes
``stop_auto_retry`` wait up to ``drain_timeout`` seconds for the counter to reach
zero before shutting the pool down. The wait is bounded so a hung network call
cannot freeze app shutdown forever.
"""

import importlib
import threading
import time
import unittest.mock as mock


def _import():
    return importlib.import_module("agent.cloud_api.offline_sync_manager")


def _bare_manager(osm):
    """Build an OfflineSyncManager without running __init__ (which wires the
    real queue, supervisor and thread pool)."""
    manager = osm.OfflineSyncManager.__new__(osm.OfflineSyncManager)
    manager._stop_retry = False
    manager._retry_thread = None
    manager._pending_submissions = 0
    manager._submission_lock = threading.Lock()
    manager._executor = mock.MagicMock()
    return manager


def test_stop_waits_for_pending_submissions_to_drain():
    """stop_auto_retry must block until the pending counter reaches zero."""
    osm = _import()
    manager = _bare_manager(osm)

    # Simulate 3 in-flight tasks that finish after ~0.3s.
    manager._pending_submissions = 3

    def _finish_soon():
        time.sleep(0.3)
        with manager._submission_lock:
            manager._pending_submissions = 0

    worker = threading.Thread(target=_finish_soon)
    worker.start()

    started = time.monotonic()
    manager.stop_auto_retry(drain_timeout=5.0)
    elapsed = time.monotonic() - started
    worker.join(timeout=2.0)

    assert elapsed >= 0.25, (
        f"stop_auto_retry returned after {elapsed:.2f}s without waiting for "
        "the in-flight task — the drain loop is not blocking"
    )
    assert manager._pending_submissions == 0
    manager._executor.shutdown.assert_called_once_with(wait=False)


def test_stop_returns_immediately_when_nothing_pending():
    """With no in-flight tasks the drain loop must not add latency."""
    osm = _import()
    manager = _bare_manager(osm)
    manager._pending_submissions = 0

    started = time.monotonic()
    manager.stop_auto_retry(drain_timeout=30.0)
    elapsed = time.monotonic() - started

    assert elapsed < 0.5, (
        f"stop_auto_retry slept {elapsed:.2f}s despite an empty pool"
    )
    manager._executor.shutdown.assert_called_once_with(wait=False)


def test_stop_is_bounded_by_drain_timeout():
    """A stuck task must not block shutdown past drain_timeout."""
    osm = _import()
    manager = _bare_manager(osm)
    manager._pending_submissions = 1  # never drains

    started = time.monotonic()
    manager.stop_auto_retry(drain_timeout=0.5)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, (
        f"stop_auto_retry ran {elapsed:.2f}s — the drain wait is not bounded "
        "by drain_timeout, so a hung network call would freeze shutdown"
    )
    # Shutdown still happens even though the task never finished.
    manager._executor.shutdown.assert_called_once_with(wait=False)


def test_done_callback_decrements_counter():
    """The Future done-callback must decrement the pending counter."""
    osm = _import()
    manager = _bare_manager(osm)

    # Build a real callback the way sync_to_cloud_async does: the counter starts
    # at 1 and the callback fires when the Future completes.
    manager._pending_submissions = 1
    import concurrent.futures

    future = concurrent.futures.Future()

    def _done_callback(fut):
        with manager._submission_lock:
            manager._pending_submissions -= 1

    future.add_done_callback(_done_callback)
    future.set_result(None)  # completes the Future, runs the callback

    assert manager._pending_submissions == 0, (
        "a completed Future must decrement the pending submission counter"
    )


def test_submit_failure_undoes_the_increment(monkeypatch):
    """If the pool is already shut down, submit() raises RuntimeError and the
    pending-counter must be rolled back — otherwise a later stop_auto_retry
    would wait pointlessly for a task that will never run."""
    osm = _import()
    manager = _bare_manager(osm)
    # Mock get_cloud_service before sync_to_cloud_async can call it.
    mock_service = mock.MagicMock()
    monkeypatch.setattr("agent.cloud_api.offline_sync_manager.get_cloud_service",
                        mock.MagicMock(return_value=mock_service))
    manager._executor.submit.side_effect = RuntimeError(
        "cannot schedule new futures")

    # sync_to_cloud_async increments the counter before calling submit().
    # If submit() fails, the counter must still end up at 0.
    try:
        manager.sync_to_cloud_async(
            data_type="agent", operation="add", data={"id": "x"}
        )
    except RuntimeError:
        pass

    assert manager._pending_submissions == 0, (
        "a failed submit must not leave a phantom pending submission behind"
    )
