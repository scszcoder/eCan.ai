"""
Long-running Knowledge Service jobs (imports, re-index) with progress.

Each job runs in a worker thread and reports (stage, done, total, message).
Progress is persisted to ``ks_job`` so the GUI can poll it, and pushed to
listeners (the IPC layer broadcasts it to the Knowledge page). Progress
writes are throttled so a 10k-row import doesn't do 10k commits.
"""
from __future__ import annotations

import threading
import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from knowledge.ks._log import logger


class JobCancelled(Exception):
    pass


class JobContext:
    """Handed to the job function to report progress and check for cancel."""

    def __init__(self, runner: "JobRunner", job_id: str):
        self._runner = runner
        self.job_id = job_id
        self._last_push = 0.0
        self.errors: List[str] = []

    def progress(self, stage: str, done: int = 0, total: int = 0, message: str = "", force: bool = False) -> None:
        if self._runner.is_cancelled(self.job_id):
            raise JobCancelled()
        now = time.monotonic()
        if force or now - self._last_push >= 0.25 or (total and done >= total):
            self._last_push = now
            frac = (done / total) if total else 0.0
            self._runner._update(self.job_id, status="running", stage=stage, done=done, total=total,
                                 progress=round(min(1.0, frac), 4), message=message)

    def error(self, message: str) -> None:
        self.errors.append(message)


class JobRunner:
    def __init__(self, store, listeners: Optional[List[Callable[[Dict[str, Any]], None]]] = None):
        self._store = store  # knowledge.ks.service.KSStore
        self._listeners = listeners or []
        self._cancel: set = set()
        self._lock = threading.Lock()

    def add_listener(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        self._listeners.append(fn)

    def is_cancelled(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._cancel

    def cancel(self, job_id: str) -> None:
        with self._lock:
            self._cancel.add(job_id)

    def _update(self, job_id: str, **fields) -> Dict[str, Any]:
        job = self._store.update_job(job_id, **fields)
        for fn in list(self._listeners):
            try:
                fn(job)
            except Exception as e:  # a broken listener must not kill the job
                logger.debug(f"[KS] job listener failed: {e}")
        return job

    def submit(self, kind: str, title: str, fn: Callable[[JobContext], Dict[str, Any]],
               tenant_id: str = "", run_inline: bool = False) -> Dict[str, Any]:
        job = self._store.create_job(kind=kind, title=title, tenant_id=tenant_id)
        job_id = job["id"]

        def _run():
            ctx = JobContext(self, job_id)
            self._update(job_id, status="running", stage="starting", message="")
            try:
                result = fn(ctx) or {}
                status = "succeeded"
                message = result.pop("_message", "") if isinstance(result, dict) else ""
                self._update(job_id, status=status, stage="done", progress=1.0,
                             result=result, errors=ctx.errors[:500], message=message)
            except JobCancelled:
                self._update(job_id, status="cancelled", stage="cancelled", errors=ctx.errors[:500],
                             message="已取消 / Cancelled")
            except Exception as e:
                logger.error(f"[KS] job {job_id} failed: {e}\n{traceback.format_exc()}")
                self._update(job_id, status="failed", stage="failed", errors=(ctx.errors + [str(e)])[:500],
                             message=str(e))
            finally:
                with self._lock:
                    self._cancel.discard(job_id)

        if run_inline:
            _run()
        else:
            threading.Thread(target=_run, name=f"ks-job-{job_id}", daemon=True).start()
        return self._store.get_job(job_id)
