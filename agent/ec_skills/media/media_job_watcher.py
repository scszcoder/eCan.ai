"""Async-mode media jobs: the other half of a parked media-gen node.

In async mode the media-gen node submits a video / music job, records it here
and parks its task (LangGraph ``interrupt``), so no worker thread is held while
the vendor renders. This module learns the outcome -- pushed by the proxy on
``onLongLLMTaskComplete`` (workType ``media_gen``) or found by polling on ONE
shared background thread -- then queues a ``media_gen`` event onto the parked
task, which resumes the node. The node reads the outcome from here, not from
the event, so a skill's own resume mapping cannot lose it.

The watcher also owns the node's timeout: at the deadline it cancels the job and
records ``timeout``. While a job runs it raises the task's parked-wait limit (the
runner fails a task parked longer than RUN_EVENT_TIMEOUT_SEC, 600 s by default).

Jobs are kept on disk too. After a restart the parked run is gone, so a job
reloaded from disk is only polled to its end (settling its charge) or cancelled
at its deadline -- never delivered.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

EVENT_TYPE = "media_gen"
POLL_INITIAL_S = 5.0
POLL_MAX_S = 30.0
DELIVERY_RETRY_S = 10.0
TIMEOUT_HOLD_MARGIN_S = 120.0
STALE_AFTER_S = 3600.0
_TERMINAL = ("succeeded", "failed", "cancelled", "expired", "timeout")

_lock = threading.RLock()
_jobs: Dict[str, Dict[str, Any]] = {}
_loaded = False
_thread: Optional[threading.Thread] = None
_wake = threading.Event()


# ── persistence ──────────────────────────────────────────────────────────────

def _store_path() -> str:
    from utils.user_path_helper import ensure_user_data_dir
    return os.path.join(ensure_user_data_dir(subdir="generated_medias"), "pending_media_jobs.json")


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        path = _store_path()
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                saved = json.load(f) or {}
            for key, entry in saved.items():
                if isinstance(entry, dict) and not entry.get("done"):
                    entry["orphan"] = True          # its parked run did not survive the restart
                    entry["next_poll"] = 0.0
                    _jobs[key] = entry
            if _jobs:
                logger.info(f"[MediaJobs] reloaded {len(_jobs)} unfinished job(s) to settle")
    except Exception as e:
        logger.warning(f"[MediaJobs] could not load pending jobs: {e}")


def _save() -> None:
    try:
        path = _store_path()
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: {kk: vv for kk, vv in v.items() if kk != "prev_timeout_set"}
                       for k, v in _jobs.items()}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"[MediaJobs] could not persist pending jobs: {e}")


# ── node-facing API ──────────────────────────────────────────────────────────

def lookup(key: str) -> Optional[Dict[str, Any]]:
    with _lock:
        _load()
        entry = _jobs.get(key)
        return dict(entry) if entry else None


def record(key: str, *, job_id: str, kind: str, task_id: str, timeout_s: float) -> None:
    """Track a submitted job for the parked node *key* and start watching it."""
    with _lock:
        _load()
        entry = {"key": key, "job_id": job_id, "kind": kind, "task_id": task_id,
                 "deadline": time.time() + float(timeout_s), "status": "queued", "job": None,
                 "done": False, "delivered": False, "orphan": False,
                 "next_poll": time.time() + POLL_INITIAL_S, "interval": POLL_INITIAL_S}
        runner = _runner_for(task_id)
        if runner is not None:
            entry["prev_timeout"] = runner.hold_pending_timeout(task_id, float(timeout_s) + TIMEOUT_HOLD_MARGIN_S)
            entry["prev_timeout_set"] = True
        _jobs[key] = entry
        _save()
    logger.info(f"[MediaJobs] watching {kind} job {job_id} for task {task_id} (timeout {timeout_s:.0f}s)")
    _ensure_thread()


def release(key: str) -> None:
    """The node consumed the outcome: forget the job, restore the task's wait limit."""
    with _lock:
        entry = _jobs.pop(key, None)
        _save()
    if entry and entry.get("prev_timeout_set"):
        runner = _runner_for(entry.get("task_id", ""))
        if runner is not None:
            runner.restore_pending_timeout(entry["task_id"], entry.get("prev_timeout"))


def ensure_started() -> None:
    """Resume watching jobs left on disk by a previous run (settle or cancel them)."""
    with _lock:
        _load()
        pending = bool(_jobs)
    if pending:
        _ensure_thread()


def on_push(result_obj: Dict[str, Any]) -> bool:
    """A job outcome pushed on ``onLongLLMTaskComplete``. True when it was ours.

    The push carries no output URL (by design: no signed URL goes over the
    socket), so it only says "look now": the job is polled at once, and that
    GET returns the outputs with fresh URLs."""
    if not isinstance(result_obj, dict) or result_obj.get("workType") != EVENT_TYPE:
        return False
    job_id = str(result_obj.get("taskID") or "")
    with _lock:
        _load()
        entry = next((e for e in _jobs.values() if e.get("job_id") == job_id), None)
        if entry is not None and not entry.get("done"):
            entry["next_poll"] = 0.0
    if entry is None:
        logger.info(f"[MediaJobs] push for unknown job {job_id} (ignored)")
        return True
    logger.info(f"[MediaJobs] push: {entry['kind']} job {job_id} {result_obj.get('status')}; collecting now")
    _ensure_thread()
    return True


# ── internals ────────────────────────────────────────────────────────────────

def _runner_for(task_id: str):
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        agents = mainwin.get_agents() if hasattr(mainwin, "get_agents") else getattr(mainwin, "agents", [])
        for agent in agents or []:
            runner = getattr(agent, "runner", None)
            if runner is not None and hasattr(runner, "_find_task") and runner._find_task(task_id):
                return runner
    except Exception:
        pass
    return None


def _finish(entry: Dict[str, Any], job: Dict[str, Any]) -> None:
    with _lock:
        if entry.get("done"):
            return
        entry.update(job=job, status=job.get("status"), done=True)
        orphan = entry.get("orphan")
        if orphan:
            _jobs.pop(entry["key"], None)
        _save()
    logger.info(f"[MediaJobs] {entry['kind']} job {entry['job_id']} {job.get('status')}"
                + (" (orphan from a previous run; settled, not delivered)" if orphan else ""))
    if not orphan:
        _deliver(entry)


def _deliver(entry: Dict[str, Any]) -> None:
    runner = _runner_for(entry.get("task_id", ""))
    ok = False
    if runner is not None:
        from agent.cloud_api.cloud_api import convert_cloud_result_to_task_send_params
        request = convert_cloud_result_to_task_send_params(
            {"taskID": entry["job_id"], "results": {"job_id": entry["job_id"], "status": entry.get("status")}},
            EVENT_TYPE)
        ok = runner.deliver_to_task(entry["task_id"], EVENT_TYPE, request)
    with _lock:
        entry["delivered"] = ok
        entry["next_poll"] = time.time() + DELIVERY_RETRY_S
        _save()
    if not ok:
        logger.warning(f"[MediaJobs] could not wake task {entry.get('task_id')} for job "
                       f"{entry['job_id']} yet; retrying")


def _poll(entry: Dict[str, Any]) -> None:
    from agent.ec_skills.media.proxy_media_client import ProxyMediaClient
    client = ProxyMediaClient.from_ecanai()
    try:
        get = client.get_music if entry["kind"] == "music" else client.get_video
        job = get(entry["job_id"])
        if job.get("status") in _TERMINAL:
            _finish(entry, job)
            return
        if time.time() >= entry["deadline"]:
            try:
                (client.cancel_music if entry["kind"] == "music" else client.cancel_video)(entry["job_id"])
            except Exception as e:
                logger.warning(f"[MediaJobs] cancel of timed-out job {entry['job_id']} failed: {e}")
            _finish(entry, {"id": entry["job_id"], "status": "timeout",
                            "error": {"code": "client_timeout",
                                      "message": f"{entry['kind']} {entry['job_id']} still "
                                                 f"{job.get('status')} at the node's timeout"}})
            return
        with _lock:
            entry["status"] = job.get("status")
            entry["interval"] = min(float(entry.get("interval") or POLL_INITIAL_S) * 2, POLL_MAX_S)
            entry["next_poll"] = time.time() + entry["interval"]
    finally:
        client.close()


def _loop() -> None:
    global _thread
    while True:
        now = time.time()
        with _lock:
            # A delivered outcome nobody came back for (the agent was stopped).
            stale = [k for k, e in _jobs.items()
                     if e.get("done") and now > float(e.get("deadline") or 0) + STALE_AFTER_S]
            for k in stale:
                _jobs.pop(k, None)
            if stale:
                _save()
            due = [e for e in _jobs.values()
                   if now >= float(e.get("next_poll") or 0) and not (e.get("done") and e.get("delivered"))]
            idle = not _jobs
            if idle:
                _thread = None
                return
        for entry in due:
            try:
                if not entry.get("done"):
                    _poll(entry)
                elif not entry.get("delivered"):
                    _deliver(entry)
            except Exception as e:
                logger.warning(f"[MediaJobs] {entry.get('kind')} job {entry.get('job_id')}: {e}")
                with _lock:
                    entry["next_poll"] = time.time() + POLL_MAX_S
        _wake.wait(1.0)
        _wake.clear()


def _ensure_thread() -> None:
    global _thread
    with _lock:
        if _thread is not None and _thread.is_alive():
            _wake.set()
            return
        _thread = threading.Thread(target=_loop, name="media-job-watcher", daemon=True)
        _thread.start()
