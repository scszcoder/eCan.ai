"""Run a skill once for one store ("为店铺运行一次") -- no temporary agent.

A store-scoped skill (e.g. 抖店商品导出) must run in that store's logged-in
browser, and only a task carries the store (task_vars) and its browser
(browser_identity). So the run goes to the agent that already runs a task for
that store (its operations agent 运营-<store> when it has one, else its front
desk): a ONE-OFF task is added to it with the store's
vars and browser, set to run once in the background after the store's browser
has been quiet a while (start_after_idle_min, capped by
start_after_idle_max_min) so it does not cut into live work. When that run
ends the runner retires the task (removed from the agent and the database --
see TaskRunner's ``one_off`` handling); nothing accumulates. A second request
while one is still queued for the same skill and store reports that one.

Called by the ``skills.run_for_store`` IPC handler -- the same handler the
``ecan skills run-for-store`` CLI command and the Skills page button use.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

ONE_OFF_SETTINGS = {"run_once": True, "one_off": True, "run_class": "background",
                    "start_after_idle_min": 5, "start_after_idle_max_min": 60}
_STORE_VAR_KEYS = ("store_id", "store_url", "store_urls")


def _meta(task) -> dict:
    m = getattr(task, "metadata", None)
    return m if isinstance(m, dict) else {}


def _store_of(task) -> str:
    return str((_meta(task).get("task_vars") or {}).get("store_id") or "").strip()


def _store_tasks(mainwin):
    """(agent, task) for every (non one-off) store task with a browser identity,
    the store's operations agent (运营-<store>, ``store_ops`` tasks) first --
    chores belong there, not on the live 客服 front desk."""
    pairs = [(ag, t) for ag in list(getattr(mainwin, "agents", None) or [])
             for t in list(getattr(ag, "tasks", None) or [])
             if _store_of(t) and not _meta(t).get("one_off") and _meta(t).get("browser_identity")]
    return sorted(pairs, key=lambda p: not _meta(p[1]).get("store_ops"))


def store_hosts(mainwin) -> List[Dict[str, Any]]:
    """Stores a one-off can run for: [{store_id, agent_id, agent_name, task_id}],
    one per store -- its operations agent, else the agent running its task."""
    out, seen = [], set()
    for ag, t in _store_tasks(mainwin):
        sid, card = _store_of(t), getattr(ag, "card", None)
        if sid in seen:
            continue
        seen.add(sid)
        out.append({"store_id": sid, "agent_id": str(getattr(card, "id", "") or ""),
                    "agent_name": str(getattr(card, "name", "") or ""), "task_id": str(getattr(t, "id", ""))})
    return out


def _host(mainwin, store_id: str) -> Tuple[Any, Any]:
    for ag, t in _store_tasks(mainwin):
        if _store_of(t) == store_id:
            return ag, t
    return None, None


def _skill_row(mainwin, skill_ref: str) -> Optional[dict]:
    svc = mainwin.ec_db_mgr.skill_service
    for q in ({"id": skill_ref}, {"name": skill_ref}):
        try:
            rows = (svc.query_skills(**q) or {}).get("data") or []
        except Exception:
            rows = []
        exact = [r for r in rows if str(r.get("id")) == skill_ref or str(r.get("name")) == skill_ref]
        if exact:
            return exact[0]
    # A skill that is only in my_skills as files (shipped or synced, never
    # registered -- 2026-10-24 KEN: 抖店营销导出): register it, as Fast Deploy does.
    try:
        from agent.ec_skills.extern_skills.extern_skills import user_skills_root
        from gui.ipc.w2p_handlers.skill_handler import sync_skill_from_file
        path = user_skills_root() / f"{skill_ref}_skill" / "diagram_dir" / f"{skill_ref}_skill.json"
        if path.is_file() and (sync_skill_from_file(str(path), params={"_skip_cloud_sync": True,
                                                                        "_skill_service": svc}) or {}).get("success"):
            logger.info(f"[one-off] registered skill {skill_ref!r} from its files")
            rows = (svc.query_skills(name=skill_ref) or {}).get("data") or []
            return next((r for r in rows if str(r.get("name")) == skill_ref), None)
    except Exception as e:
        logger.warning(f"[one-off] could not register skill {skill_ref!r} from its files: {e}")
    return None


def run_for_store(mainwin, skill_ref: str, store_id: str) -> Dict[str, Any]:
    """Queue one run of *skill_ref* (id or name) for *store_id*. Returns
    {task_id, task_name, agent_id, agent_name, store_id, already_queued}."""
    skill_ref, store_id = str(skill_ref or "").strip(), str(store_id or "").strip()
    skill = _skill_row(mainwin, skill_ref)
    if not skill:
        raise ValueError(f"skill not found: {skill_ref}")
    host, host_task = _host(mainwin, store_id)
    if host is None:
        known = ", ".join(h["store_id"] for h in store_hosts(mainwin)) or "none"
        raise ValueError(f"no agent in the app runs a task for store {store_id!r} "
                         f"(stores with one: {known})")
    card = getattr(host, "card", None)
    agent_id, agent_name = str(getattr(card, "id", "") or ""), str(getattr(card, "name", "") or "")
    skill_id, skill_name = str(skill["id"]), str(skill.get("name") or skill_ref)

    for t in list(getattr(host, "tasks", None) or []):
        meta = _meta(t)
        if (meta.get("one_off") and _store_of(t) == store_id and not meta.get("completed_once_at")
                and str(getattr(getattr(t, "skill", None), "id", "") or meta.get("one_off_skill_id")) == skill_id):
            return {"task_id": t.id, "task_name": t.name, "agent_id": agent_id, "agent_name": agent_name,
                    "store_id": store_id, "already_queued": True}

    hmeta = _meta(host_task)
    task_vars = {k: v for k, v in (hmeta.get("task_vars") or {}).items() if k in _STORE_VAR_KEYS}
    name = f"{skill_name}·{store_id}（一次性）"
    db = mainwin.ec_db_mgr
    tr = db.task_service.add_task({
        "name": name, "owner": getattr(mainwin, "user", "") or "", "source": "one_off",
        "description": f"One run of {skill_name} for store {store_id}; removed when it finishes",
        "task_type": "browser_automation", "trigger": "auto", "status": "pending",
        "settings": {"task_vars": task_vars, "browser_identity": dict(hmeta.get("browser_identity") or {}),
                     **ONE_OFF_SETTINGS, "one_off_skill_id": skill_id},
    })
    if not tr.get("success"):
        raise RuntimeError(f"could not create the one-off task: {tr.get('error')}")
    task_id = tr.get("id")
    try:
        link = db.task_service.add_skill_to_task(task_id, skill_id, role="primary")
        if not (isinstance(link, dict) and link.get("success")):
            raise RuntimeError(f"could not link the task to the skill: {(link or {}).get('error')}")
        rel = db.agent_service.assign_task_to_agent(agent_id, task_id, None)
        if not rel.get("success"):
            raise RuntimeError(f"could not give the task to {agent_name}: {rel.get('error')}")
        _attach_live(mainwin, host, task_id)
    except Exception:
        db.task_service.delete_task(task_id)
        raise
    logger.info(f"[one-off] queued {skill_name!r} for store {store_id!r} on {agent_name!r} "
                f"(task {task_id}; runs once the store's browser has been quiet, then is removed)")
    return {"task_id": task_id, "task_name": name, "agent_id": agent_id, "agent_name": agent_name,
            "store_id": store_id, "already_queued": False}


def _attach_live(mainwin, agent, task_id: str) -> None:
    """Give the running agent the task and start its loop with the 'auto'
    trigger: the runner then applies run_once + the quiet-browser wait."""
    from agent.ec_agents.create_agent_tasks import _convert_db_agent_task_to_object
    rows = (mainwin.ec_db_mgr.task_service.query_tasks(id=task_id) or {}).get("data") or []
    if not rows:
        raise RuntimeError("the new task is not in the database")
    task = _convert_db_agent_task_to_object(rows[0], main_win=mainwin)
    if task is None:
        raise RuntimeError("could not load the new task")
    task.agent_id = str(getattr(getattr(agent, "card", None), "id", "") or "")
    agent.tasks.append(task)
    pool = getattr(agent, "thread_pool_executor", None) or getattr(mainwin, "threadPoolExecutor", None)
    if pool is None or getattr(agent, "runner", None) is None:
        raise RuntimeError("the agent is not running")
    import uuid
    task.run_id = getattr(task, "run_id", None) or str(uuid.uuid4())
    future = pool.submit(agent.runner.launch_unified_run, task, ["auto", "message"])
    if hasattr(agent, "active_tasks") and hasattr(agent, "task_lock"):
        with agent.task_lock:
            agent.active_tasks[task.run_id] = future


def retire(agent, task, ok: bool) -> None:
    """A one-off task's run is over: drop it from the agent and the database."""
    try:
        tasks = getattr(agent, "tasks", None)
        if isinstance(tasks, list) and task in tasks:
            tasks.remove(task)
        ev = getattr(task, "cancellation_event", None)
        if ev is not None:
            ev.set()                      # its loop ends instead of waiting for messages
        svc = getattr(getattr(getattr(agent, "mainwin", None), "ec_db_mgr", None), "task_service", None)
        if svc is not None:
            svc.delete_task(task.id)
        logger.info(f"[one-off] '{task.name}' {'finished' if ok else 'ended with an error'}; removed")
    except Exception as e:
        logger.warning(f"[one-off] could not remove '{getattr(task, 'name', '?')}': {e}")
