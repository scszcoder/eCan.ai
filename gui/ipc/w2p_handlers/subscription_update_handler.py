"""Subscribed skills and their prompts: keep them at the author's latest.

Subscribed (rented) skills are read-only for the subscriber, so following the
author's published version is safe -- there is no local work to lose.

* Power-up: subscribed skills are refreshed before the compile
  (skill_file_sync.refresh_subscribed_skills_from_cloud); their prompts are
  refreshed here (``refresh_subscribed_prompts``) -- they used to update only
  on a manual Update click.
* Every ``CHECK_INTERVAL_S`` (30 min, ``ECAN_SUB_UPDATE_CHECK_S``) the cloud is
  asked for newer versions (``run_background_check``). An update whose skill
  is idle on this machine is applied right away; the rest wait as a reminder
  (header update icon) until the user applies them or the skill goes idle.

A skill is idle when no task using it is running, waiting mid-run (input /
pending async event), holding queued messages, or scheduled to run within
``_SCHEDULE_GUARD_S`` -- see ``_task_busy_reason``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

CHECK_INTERVAL_S = float(os.environ.get("ECAN_SUB_UPDATE_CHECK_S") or 1800)
# A scheduled run due this soon counts as busy: updating right before it would
# race the run's start.
_SCHEDULE_GUARD_S = 300

_lock = threading.Lock()
_state: Dict[str, Any] = {"items": [], "checked_at": 0.0, "running": False, "next_check": 0.0}


# ── what is subscribed, and what changed ─────────────────────────────────────

def _me(mainwin) -> str:
    from gui.ipc.w2p_handlers.skill_file_sync import _get_cloud_context
    ctx = _get_cloud_context()
    return str((ctx or {}).get("owner") or getattr(mainwin, "user", "") or "").strip()


def _subscribed_rows(mainwin) -> List[Dict[str, Any]]:
    """Local skill rows of other authors (a subscribed row keeps the author as owner)."""
    me = _me(mainwin)
    svc = getattr(getattr(mainwin, "ec_db_mgr", None), "skill_service", None)
    if not me or svc is None:
        return []
    res = svc.query_skills()
    rows = res.get("data", []) if res.get("success") else []
    # Compare owners in one spelling: "me" is the cloud identity (a WeChat login's
    # bare openid) while the author's own rows say wechat_<openid> or
    # wechat_<openid>@local. A raw compare made every skill of a WeChat author
    # "someone else's" -- their prompts were overwritten into subscribed_prompts
    # and no longer pushed on save (2026-10-22, 飞鸽客服问答00 / 电商售后应答).
    from agent.cloud_api.cloud_api import normalize_cloud_owner
    mine = normalize_cloud_owner(me).lower()
    return [r for r in rows if isinstance(r, dict) and str(r.get("owner") or "").strip()
            and normalize_cloud_owner(str(r.get("owner")).strip()).lower() != mine]


def _author(row: Dict[str, Any]) -> str:
    cfg = row.get("config")
    if isinstance(cfg, str):
        try:
            cfg = json.loads(cfg)
        except Exception:
            cfg = {}
    return str((cfg or {}).get("skill_owner") or row.get("owner") or "").strip()


def _prompt_ids(row: Dict[str, Any]) -> List[str]:
    from gui.ipc.w2p_handlers.skill_handler import _extract_skill_prompt_ids, _skill_file_prompt_ids
    ids = set(_extract_skill_prompt_ids(row))
    try:
        ids |= set(_skill_file_prompt_ids(row))
    except Exception:
        pass
    return sorted(ids)


def _canon(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _cloud_prompt(ctx, pid: str, author: str) -> Optional[Dict[str, Any]]:
    from gui.ipc.w2p_handlers.prompt_cloud_sync import _appsync_request
    resp = _appsync_request(
        "query QueryPrompts($input: PromptQueryInput) { queryPrompts(input: $input) { id prompt } }",
        ctx, variables={"input": {"id": pid, "owner": author}})
    items = (resp.get("data") or {}).get("queryPrompts") or []
    if not items:
        return None
    raw = items[0].get("prompt") or "{}"
    data = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(data, dict):
        return None
    data["id"] = pid
    return data


def _local_subscribed_prompt(pid: str) -> Optional[Dict[str, Any]]:
    from gui.ipc.w2p_handlers import prompt_handler
    path = prompt_handler._get_subscribed_prompts_dir() / f"0_{pid}.json"
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _changed_prompts(ctx, row: Dict[str, Any]) -> List[str]:
    """Prompt ids of *row* whose author copy differs from the local subscribed copy."""
    author = _author(row)
    changed = []
    for pid in _prompt_ids(row):
        try:
            cloud = _cloud_prompt(ctx, pid, author)
        except Exception as e:
            logger.debug(f"[sub-updates] prompt {pid} check failed: {e}")
            continue
        if cloud is None:
            continue
        local = _local_subscribed_prompt(pid)
        if local is None or _canon(local) != _canon(cloud):
            changed.append(pid)
    return changed


def _cloud_skill_version(ctx, row: Dict[str, Any]) -> Optional[str]:
    from gui.ipc.w2p_handlers.skill_file_sync import _appsync_request
    sid = str(row.get("id") or "")
    resp = _appsync_request("query($i: SkillQueryInput!) { getAgentSkills(input: $i) { id version } }",
                            ctx, {"i": {"id": sid, "owner": str(row.get("owner") or "")}})
    data = (resp.get("data") or {}).get("getAgentSkills") or []
    if isinstance(data, dict):
        data = [data]
    hit = next((c for c in data if isinstance(c, dict) and str(c.get("id")) == sid), None)
    return str(hit.get("version")) if hit and hit.get("version") else None


def check_subscribed_updates(mainwin, include_skills: bool = True) -> List[Dict[str, Any]]:
    """Subscribed skills with a newer cloud version and/or changed prompts.

    Each item: {skill_id, name, author, local_version, cloud_version,
    skill_newer, prompts}. Cloud failures skip that skill (offline = no updates)."""
    from gui.ipc.w2p_handlers.skill_file_sync import _get_cloud_context
    from utils.skill_version import CLOUD_NEWER, compare_skill_versions
    ctx = _get_cloud_context()
    if not ctx:
        return []
    items = []
    for row in _subscribed_rows(mainwin):
        sid, name = str(row.get("id") or ""), str(row.get("name") or "")
        if not sid:
            continue
        try:
            cloud_version = _cloud_skill_version(ctx, row) if include_skills else None
            skill_newer = bool(cloud_version) and compare_skill_versions(
                row.get("version"), cloud_version) == CLOUD_NEWER
            prompts = _changed_prompts(ctx, row)
        except Exception as e:
            logger.warning(f"[sub-updates] check failed for '{name}' ({sid}): {e}")
            continue
        if skill_newer or prompts:
            items.append({"skill_id": sid, "name": name, "author": _author(row),
                          "local_version": row.get("version"), "cloud_version": cloud_version,
                          "skill_newer": skill_newer, "prompts": prompts})
    return items


# ── is the skill in use? ─────────────────────────────────────────────────────

def _task_busy_reason(task: Any, now: Optional[datetime] = None) -> str:
    """Why *task* must not have its skill swapped now ('' = idle).

    Status: running, or paused mid-run waiting for input.
    Trigger: async events it is still waiting on, or queued messages.
    Schedule: a run due now or within _SCHEDULE_GUARD_S."""
    try:
        from a2a.types import TaskState
        state = getattr(getattr(task, "status", None), "state", None)
        if state in (TaskState.submitted, TaskState.working, TaskState.input_required):
            return f"status {getattr(state, 'value', state)}"
    except Exception:
        pass
    pending = getattr(task, "pending_events", None) or {}
    try:
        from agent.ec_tasks.models import PendingEventStatus
        if any(getattr(e, "status", None) == PendingEventStatus.PENDING for e in pending.values()):
            return "waiting on an async event"
    except Exception:
        pass
    queue = getattr(task, "queue", None)
    try:
        if queue is not None and not queue.empty():
            return "messages queued"
    except Exception:
        pass
    schedule = getattr(task, "schedule", None)
    triggers = [str(t).lower() for t in (getattr(task, "trigger", None) or [])]
    if schedule is not None and (not triggers or "schedule" in triggers):
        try:
            from agent.ec_tasks.models import RepeatType
            if getattr(schedule, "repeat_type", None) != RepeatType.NONE:
                from agent.ec_tasks.scheduler import get_next_runtime
                next_run, due = get_next_runtime(schedule)
                now = now or datetime.now()
                if due or (now <= next_run <= now + timedelta(seconds=_SCHEDULE_GUARD_S)):
                    return f"scheduled run at {next_run:%H:%M}"
        except Exception:
            pass
    return ""


def _tasks_of_skill(mainwin, skill_id: str, name: str):
    """Every live task (agent task lists and runner tables) bound to the skill."""
    seen = set()
    for agent in getattr(mainwin, "agents", None) or []:
        pools = [getattr(agent, "tasks", None) or []]
        runner_tasks = getattr(getattr(agent, "runner", None), "tasks", None)
        if isinstance(runner_tasks, dict):
            pools.append(list(runner_tasks.values()))
        for pool in pools:
            for t in pool:
                sk = getattr(t, "skill", None)
                if id(t) in seen or sk is None:
                    continue
                if (skill_id and str(getattr(sk, "id", "")) == skill_id) or \
                        (name and str(getattr(sk, "name", "")) == name):
                    seen.add(id(t))
                    yield t


def skill_busy_reason(mainwin, skill_id: str, name: str) -> str:
    for t in _tasks_of_skill(mainwin, skill_id, name):
        reason = _task_busy_reason(t)
        if reason:
            return f"task '{getattr(t, 'name', '?')}': {reason}"
    return ""


# ── applying ─────────────────────────────────────────────────────────────────

def apply_update(mainwin, item: Dict[str, Any]) -> Dict[str, Any]:
    """Apply one update: a newer skill goes through the Update path (files,
    prompts, in-memory rebuild, task rebind); prompts-only refreshes the prompts
    (the runtime reads prompt files per run)."""
    from gui.ipc.w2p_handlers import skill_handler as sh
    svc = mainwin.ec_db_mgr.skill_service
    row = sh._find_local_skill(svc, item["skill_id"])
    if not row:
        return {"ok": False, "error": "skill no longer subscribed"}
    if item.get("skill_newer"):
        me = _me(mainwin)
        request = {"id": "sub-update", "method": "update_subscribed_skill", "source": "local_server"}
        summary = sh._refresh_subscribed_skill(request, {"username": me}, svc, row, item["skill_id"], me)
        return {"ok": summary is not None, **(summary or {"error": "skill not found in cloud"})}
    res = sh._download_skill_prompts(row, extra_prompt_ids=item.get("prompts") or (), refresh=True)
    return {"ok": not res.get("failed"), "prompts_refreshed": res.get("downloaded", []),
            "prompts_failed": res.get("failed", [])}


def _push(items: List[Dict[str, Any]], applied: List[Dict[str, Any]]) -> None:
    try:
        from gui.ipc.api import IPCAPI
        IPCAPI.get_instance()._send_request(
            "push_subscription_updates",
            params={"items": items, "applied": applied, "checked_at": _state["checked_at"]},
            callback=lambda r: None)
    except Exception as e:
        logger.debug(f"[sub-updates] push failed: {e}")


def run_background_check(mainwin) -> Dict[str, Any]:
    """Check for updates; apply those whose skill is idle; remind about the rest."""
    with _lock:
        if _state["running"]:
            return {"skipped": "check already running"}
        _state["running"] = True
    applied, waiting = [], []
    try:
        for item in check_subscribed_updates(mainwin):
            reason = skill_busy_reason(mainwin, item["skill_id"], item["name"])
            if reason:
                waiting.append({**item, "busy": reason})
                logger.info(f"[sub-updates] '{item['name']}' has an update; in use ({reason}) -- reminder")
                continue
            try:
                res = apply_update(mainwin, item)
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            if res.get("ok"):
                applied.append({"skill_id": item["skill_id"], "name": item["name"],
                                "skill_newer": item["skill_newer"], "prompts": item["prompts"]})
                logger.info(f"[sub-updates] auto-updated idle skill '{item['name']}': {res}")
            else:
                waiting.append({**item, "error": res.get("error") or "update failed"})
                logger.warning(f"[sub-updates] auto-update of '{item['name']}' failed: {res}")
    finally:
        with _lock:
            _state.update(items=waiting, checked_at=time.time(), running=False,
                          next_check=time.time() + CHECK_INTERVAL_S)
    _push(waiting, applied)
    return {"items": waiting, "applied": applied}


def background_check_due() -> bool:
    return not _state["running"] and time.time() >= _state["next_check"]


def schedule_first_check() -> None:
    """Power-up already refreshed everything: the first background check is one interval later."""
    _state["next_check"] = time.time() + CHECK_INTERVAL_S


def refresh_subscribed_prompts(mainwin) -> int:
    """Power-up: bring every subscribed skill's prompts to the author's copy
    (the skills themselves were refreshed just before). Returns skills touched."""
    from gui.ipc.w2p_handlers import skill_handler as sh
    touched = 0
    for item in check_subscribed_updates(mainwin, include_skills=False):
        row = sh._find_local_skill(mainwin.ec_db_mgr.skill_service, item["skill_id"])
        if not row:
            continue
        res = sh._download_skill_prompts(row, extra_prompt_ids=item["prompts"], refresh=True)
        if res.get("downloaded"):
            touched += 1
            logger.info(f"[sub-updates] power-up: refreshed prompts of '{item['name']}': {res['downloaded']}")
    return touched


# ── IPC ──────────────────────────────────────────────────────────────────────

def _mainwin():
    from app_context import AppContext
    return AppContext.get_main_window()


@IPCHandlerRegistry.handler("subscription_updates.list")
def handle_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    return create_success_response(request, {"items": list(_state["items"]), "checked_at": _state["checked_at"],
                                             "running": _state["running"]})


@IPCHandlerRegistry.handler("subscription_updates.check")
def handle_check(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        return create_success_response(request, run_background_check(_mainwin()))
    except Exception as e:
        logger.error(f"[sub-updates] check failed: {e}")
        return create_error_response(request, "SUB_UPDATE_CHECK_ERROR", str(e))


@IPCHandlerRegistry.handler("subscription_updates.apply")
def handle_apply(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Apply the listed updates (``skill_ids``; all when omitted) now, even if in
    use -- the user asked; running tasks are rebound to the new skill."""
    try:
        mainwin = _mainwin()
        wanted = set((params or {}).get("skill_ids") or [])
        results, remaining = [], []
        for item in list(_state["items"]):
            if wanted and item["skill_id"] not in wanted:
                remaining.append(item)
                continue
            try:
                res = apply_update(mainwin, item)
            except Exception as e:
                res = {"ok": False, "error": str(e)}
            results.append({"skill_id": item["skill_id"], "name": item["name"], **res})
            if not res.get("ok"):
                remaining.append({**item, "error": res.get("error") or "update failed"})
        with _lock:
            _state["items"] = remaining
        _push(remaining, [r for r in results if r.get("ok")])
        return create_success_response(request, {"results": results, "items": remaining})
    except Exception as e:
        logger.error(f"[sub-updates] apply failed: {e}")
        return create_error_response(request, "SUB_UPDATE_APPLY_ERROR", str(e))
