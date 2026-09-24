"""One store's local picture: who serves it and what it has produced.

The cloud registry answers "where does this store run" (store_list). This
answers the rest from what this machine holds: the agents and tasks whose
``task_vars.store_id`` names the store, and the business outcomes recorded
against it in the local usage-event log (a delivered 客服 reply, and more as
MCP tools gain meters). Kept pure over its inputs so it tests without a GUI.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List

WINDOWS_DAYS = (7, 30)


def _task_store_id(task: Any) -> str:
    from agent.ec_skills.prompt_variable_providers import STORE_ID_VAR
    md = getattr(task, "metadata", None)
    tv = md.get("task_vars") if isinstance(md, dict) else None
    return str((tv or {}).get(STORE_ID_VAR) or "").strip() if isinstance(tv, dict) else ""


def summarize_agents(agents: Iterable[Any]) -> Dict[str, Dict[str, List[dict]]]:
    """``{store_id: {"agents": [...], "tasks": [...]}}`` from in-memory agents."""
    out: Dict[str, Dict[str, List[dict]]] = {}
    for agent in agents or []:
        card = getattr(agent, "card", None)
        agent_row = {
            "id": getattr(card, "id", "") or "",
            "name": getattr(card, "name", "") or "",
            "running": bool(getattr(agent, "_running", False)),
            "status": getattr(agent, "status", "") or "",
        }
        for task in list(getattr(agent, "tasks", None) or []):
            sid = _task_store_id(task)
            if not sid:
                continue
            bucket = out.setdefault(sid, {"agents": [], "tasks": []})
            if not any(a["id"] == agent_row["id"] for a in bucket["agents"]):
                bucket["agents"].append(dict(agent_row))
            bucket["tasks"].append({
                "id": getattr(task, "id", "") or "",
                "name": getattr(task, "name", "") or "",
                "agent_id": agent_row["id"],
            })
    return out


def summarize_meters(rows_by_window: Dict[int, List[dict]]) -> Dict[str, List[dict]]:
    """``{store_id: [meter with d7/d30 counts]}`` from count_by_meter rows per window."""
    from agent.ec_skills.meter_registry import describe
    acc: Dict[str, Dict[tuple, dict]] = {}
    for days, rows in rows_by_window.items():
        for r in rows or []:
            sid = str(r.get("store_id") or "")
            if not sid:
                continue   # account-wide outcomes belong to no single store
            key = (r.get("scenario_code") or "", r.get("meter_code") or "")
            entry = acc.setdefault(sid, {}).setdefault(key, {
                **describe(*key), **{f"d{d}": 0 for d in WINDOWS_DAYS}})
            entry[f"d{days}"] = int(r.get("quantity") or 0)
    return {sid: sorted(m.values(), key=lambda x: (x["scenario_code"], x["meter_code"]))
            for sid, m in acc.items()}


def local_store_overview(mainwin: Any) -> Dict[str, dict]:
    """Agents, tasks and outcome counts for every store this machine knows."""
    stores: Dict[str, dict] = {
        sid: {"agents": v["agents"], "tasks": v["tasks"], "meters": []}
        for sid, v in summarize_agents(getattr(mainwin, "agents", None) or []).items()
    }
    svc = getattr(getattr(mainwin, "ec_db_mgr", None), "usage_event_service", None)
    if svc is not None:
        # occurred_at is naive UTC (metering.emit), so the windows are too.
        now = datetime.utcnow()
        rows = {d: svc.count_by_meter(since=now - timedelta(days=d)) for d in WINDOWS_DAYS}
        for sid, meters in summarize_meters(rows).items():
            stores.setdefault(sid, {"agents": [], "tasks": [], "meters": []})["meters"] = meters
    return stores
