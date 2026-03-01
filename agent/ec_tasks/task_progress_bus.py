"""
Task Progress Bus - In-memory pub/sub for nested task progress visibility.

Provides a singleton bus that allows:
- Child tasks to emit node-level and task-level progress events
- Parent tasks to subscribe to progress by correlation_id (root run_id)
- Querying current state and history for any task in a chain

The bus uses a correlation_id to group all tasks in a launch chain:
  Task A (corr=R1) → launches Task B (corr=R1) → launches Task C (corr=R1)
Any subscriber on corr=R1 sees events from A, B, and C.
"""

import threading
import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger


# Maximum number of events retained per correlation_id
_MAX_HISTORY = 200

# TTL for stale correlation entries (seconds) — entries older than this are GC'd
_STALE_TTL = 3600  # 1 hour


class TaskProgressEvent:
    """A single progress event from a task in a nested chain."""

    __slots__ = (
        "correlation_id", "run_id", "parent_run_id",
        "task_id", "task_name", "depth",
        "event_type", "node_name", "node_status",
        "result", "error", "timestamp",
    )

    def __init__(
        self,
        correlation_id: str,
        run_id: str,
        parent_run_id: str = "",
        task_id: str = "",
        task_name: str = "",
        depth: int = 0,
        event_type: str = "",
        node_name: str = "",
        node_status: str = "",
        result: Any = None,
        error: str = "",
        timestamp: int = 0,
    ):
        self.correlation_id = correlation_id
        self.run_id = run_id
        self.parent_run_id = parent_run_id
        self.task_id = task_id
        self.task_name = task_name
        self.depth = depth
        self.event_type = event_type
        self.node_name = node_name
        self.node_status = node_status
        self.result = result
        self.error = error
        self.timestamp = timestamp or int(time.time() * 1000)

    def to_dict(self) -> dict:
        return {
            "correlation_id": self.correlation_id,
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "depth": self.depth,
            "event_type": self.event_type,
            "node_name": self.node_name,
            "node_status": self.node_status,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp,
        }


class _TaskSnapshot:
    """Live state snapshot for a single task (run_id) in a chain."""

    __slots__ = (
        "run_id", "parent_run_id", "task_id", "task_name",
        "depth", "current_node", "status", "error",
        "result", "thread_ref", "last_updated",
    )

    def __init__(self, run_id: str, parent_run_id: str = "", task_id: str = "",
                 task_name: str = "", depth: int = 0):
        self.run_id = run_id
        self.parent_run_id = parent_run_id
        self.task_id = task_id
        self.task_name = task_name
        self.depth = depth
        self.current_node: str = ""
        self.status: str = "running"  # running | completed | failed | cancelled
        self.error: str = ""
        self.result: Any = None
        self.thread_ref: Optional[threading.Thread] = None
        self.last_updated: float = time.time()

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "parent_run_id": self.parent_run_id,
            "task_id": self.task_id,
            "task_name": self.task_name,
            "depth": self.depth,
            "current_node": self.current_node,
            "status": self.status,
            "error": self.error,
            "last_updated": int(self.last_updated * 1000),
        }


class TaskProgressBus:
    """Thread-safe singleton pub/sub bus for nested task progress."""

    _instance: Optional["TaskProgressBus"] = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._initialized = False
                    cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._bus_lock = threading.Lock()
        # correlation_id → deque of TaskProgressEvent
        self._history: Dict[str, deque] = {}
        # correlation_id → list of (callback, subscriber_id)
        self._subscribers: Dict[str, List[Tuple[Callable, str]]] = {}
        # run_id → _TaskSnapshot  (live state per task)
        self._snapshots: Dict[str, _TaskSnapshot] = {}
        # correlation_id → set of run_ids in this chain
        self._chain: Dict[str, set] = {}
        # Last GC timestamp
        self._last_gc: float = time.time()

    @classmethod
    def get_instance(cls) -> "TaskProgressBus":
        return cls()

    # ────────────────────── Registration ──────────────────────

    def register_task(
        self,
        correlation_id: str,
        run_id: str,
        parent_run_id: str = "",
        task_id: str = "",
        task_name: str = "",
        depth: int = 0,
        thread: Optional[threading.Thread] = None,
    ) -> None:
        """Register a task in the progress chain. Call when a task starts."""
        with self._bus_lock:
            snap = _TaskSnapshot(
                run_id=run_id,
                parent_run_id=parent_run_id,
                task_id=task_id,
                task_name=task_name,
                depth=depth,
            )
            snap.thread_ref = thread
            self._snapshots[run_id] = snap
            self._chain.setdefault(correlation_id, set()).add(run_id)
            if correlation_id not in self._history:
                self._history[correlation_id] = deque(maxlen=_MAX_HISTORY)
        logger.debug(
            f"[TaskProgressBus] registered run_id={run_id[:8]} "
            f"corr={correlation_id[:8]} depth={depth} task={task_name}"
        )

    # ────────────────────── Emit ──────────────────────

    def emit(self, event: TaskProgressEvent) -> None:
        """Emit a progress event. Updates snapshot and notifies subscribers."""
        corr = event.correlation_id
        if not corr:
            return

        with self._bus_lock:
            # Append to history
            ring = self._history.get(corr)
            if ring is None:
                ring = deque(maxlen=_MAX_HISTORY)
                self._history[corr] = ring
            ring.append(event)

            # Update snapshot
            snap = self._snapshots.get(event.run_id)
            if snap is None:
                # Auto-register if not explicitly registered
                snap = _TaskSnapshot(
                    run_id=event.run_id,
                    parent_run_id=event.parent_run_id,
                    task_id=event.task_id,
                    task_name=event.task_name,
                    depth=event.depth,
                )
                self._snapshots[event.run_id] = snap
                self._chain.setdefault(corr, set()).add(event.run_id)

            snap.last_updated = time.time()
            if event.node_name:
                snap.current_node = event.node_name
            if event.event_type in ("task_completed",):
                snap.status = "completed"
                snap.result = event.result
            elif event.event_type in ("task_failed",):
                snap.status = "failed"
                snap.error = event.error or ""
            elif event.event_type in ("task_cancelled",):
                snap.status = "cancelled"

            # Copy subscribers list to release lock before calling back
            subs = list(self._subscribers.get(corr, []))

        # Notify subscribers outside the lock
        for cb, sub_id in subs:
            try:
                cb(event)
            except Exception as ex:
                logger.debug(f"[TaskProgressBus] subscriber {sub_id} error: {ex}")

        # Periodic GC
        if time.time() - self._last_gc > 300:
            self._gc()

    # ────────────────────── Subscribe ──────────────────────

    def subscribe(self, correlation_id: str, callback: Callable[[TaskProgressEvent], None],
                  subscriber_id: str = "") -> Callable[[], None]:
        """
        Subscribe to all events for a correlation_id.
        Returns an unsubscribe callable.
        """
        sub_id = subscriber_id or f"sub-{id(callback)}"
        entry = (callback, sub_id)
        with self._bus_lock:
            self._subscribers.setdefault(correlation_id, []).append(entry)

        def _unsub():
            with self._bus_lock:
                subs = self._subscribers.get(correlation_id, [])
                try:
                    subs.remove(entry)
                except ValueError:
                    pass
        return _unsub

    # ────────────────────── Query ──────────────────────

    def get_task_snapshot(self, run_id: str) -> Optional[dict]:
        """Get live snapshot for a specific task by run_id."""
        with self._bus_lock:
            snap = self._snapshots.get(run_id)
            if snap is None:
                return None
            # Check thread liveness for silent-death detection
            self._check_thread_liveness(snap)
            return snap.to_dict()

    def get_chain_status(self, correlation_id: str) -> dict:
        """
        Get full chain status for a correlation_id.
        Returns all task snapshots + recent events.
        """
        with self._bus_lock:
            run_ids = self._chain.get(correlation_id, set())
            tasks = []
            for rid in run_ids:
                snap = self._snapshots.get(rid)
                if snap:
                    self._check_thread_liveness(snap)
                    tasks.append(snap.to_dict())
            # Sort by depth then by last_updated
            tasks.sort(key=lambda t: (t.get("depth", 0), t.get("last_updated", 0)))

            # Recent events
            ring = self._history.get(correlation_id)
            events = [e.to_dict() for e in ring] if ring else []

        # Derive overall status
        statuses = [t["status"] for t in tasks]
        if any(s == "failed" for s in statuses):
            overall = "failed"
        elif all(s == "completed" for s in statuses) and statuses:
            overall = "completed"
        elif any(s == "cancelled" for s in statuses):
            overall = "cancelled"
        else:
            overall = "running"

        return {
            "correlation_id": correlation_id,
            "overall_status": overall,
            "tasks": tasks,
            "recent_events": events[-20:],  # last 20
            "total_events": len(events),
        }

    def get_history(self, correlation_id: str, limit: int = 50) -> List[dict]:
        """Get event history for a correlation_id."""
        with self._bus_lock:
            ring = self._history.get(correlation_id)
            if not ring:
                return []
            events = list(ring)
        return [e.to_dict() for e in events[-limit:]]

    # ────────────────────── Thread liveness check ──────────────────────

    def _check_thread_liveness(self, snap: _TaskSnapshot) -> None:
        """Detect silent thread death — mark as failed if thread is dead but status is running."""
        if snap.status != "running":
            return
        thr = snap.thread_ref
        if thr is not None and not thr.is_alive():
            # Thread died without emitting completion
            snap.status = "failed"
            snap.error = "Task thread terminated unexpectedly"
            logger.warning(
                f"[TaskProgressBus] silent death detected: run_id={snap.run_id[:8]} "
                f"task={snap.task_name}"
            )

    # ────────────────────── GC ──────────────────────

    def _gc(self) -> None:
        """Remove stale entries older than _STALE_TTL."""
        self._last_gc = time.time()
        cutoff = time.time() - _STALE_TTL
        stale_corrs = []
        with self._bus_lock:
            for corr, run_ids in list(self._chain.items()):
                all_stale = True
                for rid in run_ids:
                    snap = self._snapshots.get(rid)
                    if snap and snap.last_updated > cutoff:
                        all_stale = False
                        break
                if all_stale:
                    stale_corrs.append(corr)

            for corr in stale_corrs:
                run_ids = self._chain.pop(corr, set())
                for rid in run_ids:
                    self._snapshots.pop(rid, None)
                self._history.pop(corr, None)
                self._subscribers.pop(corr, None)

        if stale_corrs:
            logger.debug(f"[TaskProgressBus] GC: removed {len(stale_corrs)} stale chains")
