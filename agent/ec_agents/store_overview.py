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


def is_front_desk_name(name: str) -> bool:
    """A front-desk agent/task is named with 前台 (the reception role).

    Front-desk tasks drive the store's live-chat browser (飞鸽客服前台001,
    前台-<店铺名>, 淘宝客服前台01…); Q&A/应答 and export/刷新 tasks do not. The
    name is a reliable marker across platforms, so reconciliation can run off
    DB rows without compiling skills.
    """
    return "前台" in str(name or "")


def plan_front_desk_reconcile(front_desks: List[dict], store_names: Dict[str, str]) -> List[dict]:
    """Which stores have more than one front desk, and the recommended cleanup.

    The target rule is exactly ONE front desk per store. A store can end up with
    two when a legacy single-store deploy (fixed name 前台小张 / 飞鸽客服前台001)
    and a newer store-scoped deploy (前台-<店铺名>) both landed. This is PURE and
    read-only — it recommends, it does not delete; enactment is a separate,
    confirmed step.

    ``front_desks``: ``[{store_id, agent_id, agent_name, task_id, task_name}]``.
    ``store_names``: ``{store_id: display_name}`` (to spot the store-scoped one).

    For each store with >1 distinct front-desk agent, returns
    ``{store_id, store_name, keep, retire, ambiguous, note}``. ``keep`` is the
    store-scoped agent (its name carries the store's display name) when exactly
    one is store-scoped; otherwise ``ambiguous`` is True, ``keep`` is None and
    nothing is recommended for removal (a human picks).
    """
    by_store: Dict[str, List[dict]] = {}
    for fd in front_desks or []:
        sid = str((fd or {}).get("store_id") or "").strip()
        if sid:
            by_store.setdefault(sid, []).append(fd)

    plans: List[dict] = []
    for sid, rows in by_store.items():
        agents = {r.get("agent_id") for r in rows}
        if len(agents) < 2:
            continue  # one front desk (possibly several tasks) — nothing to do
        display = str(store_names.get(sid) or "").strip()

        def _store_scoped(r: dict) -> bool:
            if not display:
                return False
            return display in str(r.get("agent_name") or "") or display in str(r.get("task_name") or "")

        scoped = [r for r in rows if _store_scoped(r)]
        scoped_agents = {r.get("agent_id") for r in scoped}
        if len(scoped_agents) == 1:
            keep_agent = next(iter(scoped_agents))
            keep = next(r for r in rows if r.get("agent_id") == keep_agent)
            retire = [r for r in rows if r.get("agent_id") != keep_agent]
            plans.append({
                "store_id": sid, "store_name": display, "keep": keep, "retire": retire,
                "ambiguous": False,
                "note": f"keep the store-scoped front desk {keep.get('agent_name')!r}; "
                        f"retire {len({r.get('agent_id') for r in retire})} generic duplicate(s)",
            })
        else:
            plans.append({
                "store_id": sid, "store_name": display, "keep": None, "retire": [],
                "ambiguous": True,
                "note": "cannot auto-pick (no single store-scoped front desk); "
                        "choose which agent to keep",
            })
    return plans


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
    # A store in its own store process: its agents run there, not in this one.
    from agent.ec_agents.store_reporter import _store_process_keys
    for sid in _store_process_keys():
        for a in stores.get(sid, {}).get("agents", []):
            a["running"] = True
            a["where"] = "store_process"
    svc = getattr(getattr(mainwin, "ec_db_mgr", None), "usage_event_service", None)
    if svc is not None:
        # occurred_at is naive UTC (metering.emit), so the windows are too.
        now = datetime.utcnow()
        rows = {d: svc.count_by_meter(since=now - timedelta(days=d)) for d in WINDOWS_DAYS}
        for sid, meters in summarize_meters(rows).items():
            stores.setdefault(sid, {"agents": [], "tasks": [], "meters": []})["meters"] = meters
    return stores
