""""After task" trigger: run a task when other tasks of the same agent finish.

Task config (task metadata/settings JSON)::

    trigger: [..., "after"]
    after: {"tasks": ["<task id>", ...], "require_success": true}

The task fires when ALL listed tasks have finished since its own last
after-run (and, with ``require_success``, finished successfully).  With a
``schedule`` trigger as well, its scheduled run waits until they are done
("10:30, but not before A").  Finish records are kept in the tasks' settings
(``last_finish`` on a prerequisite, ``after_consumed_at`` on a dependent; the
runner saves them), so a finish before an app restart still counts after it.
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


def after_cycle_error(task_id: str, task_data: Dict[str, Any], task_service) -> str:
    """'' or why saving ``task_data`` (its ``settings.after``) would make the
    "after" prerequisites form a cycle.  Other tasks are read from the DB."""
    import json
    settings = task_data.get('settings') if isinstance(task_data, dict) else None
    cfg = settings.get('after') if isinstance(settings, dict) else None
    own = [str(x) for x in (cfg.get('tasks') or [])] if isinstance(cfg, dict) else []
    if not own:
        return ''
    names = {task_id: task_data.get('name') or task_id}

    def prereqs(tid: str) -> list:
        if tid == task_id:
            return own
        try:
            res = task_service.query_tasks(id=tid)
            row = (res.get('data') or [{}])[0] if res.get('success') else {}
        except Exception:
            return []
        names[tid] = row.get('name') or tid
        st = row.get('metadata', row.get('settings'))
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except ValueError:
                st = {}
        after = st.get('after') if isinstance(st, dict) else None
        return [str(x) for x in (after.get('tasks') or [])] if isinstance(after, dict) else []

    cycle = find_cycle(task_id, prereqs)
    if not cycle:
        return ''
    return 'Task dependencies form a cycle: ' + ' -> '.join(names.get(i, i) for i in cycle)


class AfterTracker:
    """Per-runner record of finished runs and which ones a dependent consumed."""

    def __init__(self):
        self._lock = threading.Lock()
        self.finished: Dict[str, Dict[str, Any]] = {}   # task id -> {at, ok, summary, name}
        self._consumed: Dict[str, float] = {}           # dependent id -> time of its last after-run

    def seed(self, tasks: Iterable[Any]) -> None:
        """Load the records saved in the tasks' settings (after a restart)."""
        with self._lock:
            for t in tasks or []:
                meta = getattr(t, "metadata", None)
                tid = getattr(t, "id", "")
                if not isinstance(meta, dict) or not tid:
                    continue
                f = meta.get("last_finish")
                if isinstance(f, dict) and f.get("at") and tid not in self.finished:
                    self.finished[tid] = {"at": float(f["at"]), "ok": bool(f.get("ok")),
                                          "summary": str(f.get("summary") or ""), "name": getattr(t, "name", "")}
                c = meta.get("after_consumed_at")
                if c and tid not in self._consumed:
                    try:
                        self._consumed[tid] = float(c)
                    except (TypeError, ValueError):
                        pass

    def record(self, task_id: str, ok: bool, summary: str = "", name: str = "") -> Dict[str, Any]:
        with self._lock:
            rec = {"at": time.time(), "ok": bool(ok), "summary": summary, "name": name}
            self.finished[task_id] = rec
            return dict(rec)

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

    def consumed_at(self, dependent_id: str) -> float:
        with self._lock:
            return self._consumed.get(dependent_id, 0.0)
