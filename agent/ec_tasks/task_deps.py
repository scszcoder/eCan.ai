""""After task" trigger: run a task when other tasks of the same agent finish.

Task config (task metadata/settings JSON)::

    trigger: [..., "after"]
    after: {"tasks": ["<task id>", ...], "require_success": true}

The task fires when ALL listed tasks have finished since its own last
after-run (and, with ``require_success``, finished successfully).  With a
``schedule`` trigger as well, its scheduled run waits until they are done
("10:30, but not before A").  Finish records live in memory: a finish that
happened before an app restart does not count after it.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def after_config(task: Any) -> Tuple[List[str], bool]:
    """(prerequisite task ids, require_success) -- ``([], False)`` if none."""
    meta = getattr(task, "metadata", None)
    cfg = meta.get("after") if isinstance(meta, dict) else None
    if not isinstance(cfg, dict):
        return [], False
    ids = [str(x).strip() for x in (cfg.get("tasks") or []) if str(x).strip()]
    return list(dict.fromkeys(ids)), bool(cfg.get("require_success", False))


def has_after_trigger(task: Any) -> bool:
    return "after" in (getattr(task, "trigger", None) or []) and bool(after_config(task)[0])


def find_cycle(start_id: str, prereqs_of: Callable[[str], Iterable[str]]) -> Optional[List[str]]:
    """A dependency cycle through ``start_id`` as ``[start, ..., start]``, or None."""
    path: List[str] = []
    seen = set()

    def visit(node: str) -> Optional[List[str]]:
        if node == start_id and path:
            return path + [node]
        if node in seen:
            return None
        seen.add(node)
        path.append(node)
        for nxt in prereqs_of(node) or []:
            hit = visit(str(nxt))
            if hit:
                return hit
        path.pop()
        return None

    return visit(start_id)


class AfterTracker:
    """Per-runner record of finished runs and which ones a dependent consumed."""

    def __init__(self):
        self._lock = threading.Lock()
        self.finished: Dict[str, Dict[str, Any]] = {}   # task id -> {at, ok, summary, name}
        self._consumed: Dict[str, float] = {}           # dependent id -> time of its last after-run

    def record(self, task_id: str, ok: bool, summary: str = "", name: str = "") -> None:
        with self._lock:
            self.finished[task_id] = {"at": time.time(), "ok": bool(ok), "summary": summary, "name": name}

    def status(self, dependent: Any) -> Tuple[bool, List[str]]:
        """(ready, what it still waits for)."""
        ids, need_ok = after_config(dependent)
        since = self._consumed.get(getattr(dependent, "id", ""), 0.0)
        missing = []
        with self._lock:
            for pid in ids:
                f = self.finished.get(pid)
                if not f or f["at"] <= since:
                    missing.append(pid)
                elif need_ok and not f["ok"]:
                    missing.append(f"{pid} (failed)")
        return (bool(ids) and not missing), missing

    def consume(self, dependent: Any) -> Dict[str, Dict[str, Any]]:
        """Mark the prerequisites used; returns their finish records (the run's input)."""
        ids, _ = after_config(dependent)
        with self._lock:
            self._consumed[getattr(dependent, "id", "")] = time.time()
            return {pid: dict(self.finished[pid]) for pid in ids if pid in self.finished}
