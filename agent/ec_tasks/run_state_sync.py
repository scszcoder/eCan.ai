"""A background task's run state in its task record, locally and in the cloud.

The cloud read crawl tasks as "pending, 0 %" for weeks: runs never touched the task record
(server note 9a.6, item 4). Now a scheduled / auto / after run marks its task ``running``
when it starts and ``completed`` / ``failed`` (with the error) / ``cancelled`` when it ends,
and syncs the whole record the way the Tasks page saves it. Chat and A2A message turns are
left out: there are many and they are not background work.

The agent's own ``status`` is its enabled/disabled setting, so it is not written here;
an agent's live state reaches the cloud in the gateway's status_report events.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from utils.logger_helper import logger_helper as logger

SYNCED_TRIGGERS = ("schedule", "auto", "after")
_ERROR_MAX = 1000
_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="run-state-sync")   # in order, off the run


def outcome(task: Any) -> str:
    """The record status for a run that just ended, from the task's A2A state."""
    state = getattr(getattr(task, "status", None), "state", None)
    state = str(getattr(state, "value", state) or "")
    return {"completed": "completed", "failed": "failed", "canceled": "cancelled",
            "cancelled": "cancelled"}.get(state, "pending")     # input-required etc.: waiting again


def error_text(task: Any) -> str:
    msg = getattr(getattr(task, "status", None), "message", None)
    parts = getattr(msg, "parts", None) or []
    texts = [str(getattr(getattr(p, "root", p), "text", "") or "") for p in parts]
    return " ".join(t for t in texts if t)[:_ERROR_MAX]


def record(mainwin: Any, task: Any, status: str, trigger_type: str, error: str = "") -> None:
    """Queue the update; never raises and never blocks the run."""
    if str(trigger_type or "") not in SYNCED_TRIGGERS:
        return
    task_id = str(getattr(task, "id", "") or "")
    if not task_id or getattr(task, "source", "") == "code":   # code tasks have no record to update
        return
    try:
        _pool.submit(_record, mainwin, task_id, status, error)
    except Exception as e:
        logger.debug(f"[run-state] not queued for {task_id}: {e}")


def _record(mainwin: Any, task_id: str, status: str, error: str) -> None:
    try:
        svc = getattr(getattr(mainwin, "ec_db_mgr", None), "task_service", None)
        if svc is None:
            return
        fields = {"status": status, "error_message": error[:_ERROR_MAX] if status == "failed" else ""}
        if status == "completed":
            fields["progress"] = 1.0
        res = svc.update_task(task_id, fields)
        if not (res or {}).get("success"):
            logger.debug(f"[run-state] {task_id}: no local record ({(res or {}).get('error')})")
            return
        row = (svc.get_task_by_id(task_id) or {}).get("data")
        if not isinstance(row, dict):
            return
        from agent.cloud_api.constants import DataType, Operation
        from agent.cloud_api.offline_sync_manager import get_sync_manager
        get_sync_manager().sync_to_cloud(DataType.TASK, {**row, "id": task_id}, Operation.UPDATE)
        logger.info(f"[run-state] task {row.get('name') or task_id} -> {status}")
    except Exception as e:
        logger.warning(f"[run-state] could not record {status} for {task_id}: {e}")
