"""This machine as a tree: host/vehicle -> store -> agent -> task -> skill
(agents that serve no store: host -> agent -> task -> skill).

The gateway answers the ``machine_tree`` tool with it, as data and as a chat
widget (``{"type": "tree", ...}``) the helper chat panel renders as an
expandable tree. The cloud passes the widget through untouched, so every name
and count in it comes from this machine, not from a model. Browser profile ids
never leave the machine, so they are not in it.
"""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Optional

NO_STORE = ""          # agents/tasks that serve no store
_DESC_MAX = 200


def _short(text: Any, n: int = _DESC_MAX) -> str:
    s = " ".join(str(text or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _details(*pairs: tuple) -> List[Dict[str, str]]:
    return [{"label": k, "value": str(v)} for k, v in pairs if v not in (None, "", [], {})]


def _task_state(task: Any) -> str:
    state = getattr(getattr(task, "status", None), "state", None)
    return str(getattr(state, "value", state) or "")


def _skill_node(key: str, skill: Any) -> Optional[Dict[str, Any]]:
    if skill is None:
        return None
    if isinstance(skill, str):                       # named but not loaded
        return {"key": key, "kind": "skill", "label": skill, "badge": "not loaded"}
    name = getattr(skill, "name", "") or "?"
    return {"key": key, "kind": "skill", "label": name,
            "badge": "" if getattr(skill, "runnable", None) is not None else "not runnable",
            "details": _details(("Description", _short(getattr(skill, "description", ""))),
                                ("Version", getattr(skill, "version", "")),
                                ("Mode", getattr(skill, "run_mode", "")))}


def _runs_elsewhere(agent: Any) -> Dict[str, Any]:
    try:
        from agent.ec_agents.vehicle_affinity import runs_elsewhere
        return runs_elsewhere(agent)
    except Exception:
        return {}


def _schedule(task: Any) -> str:
    s = getattr(task, "schedule", None)
    if s is None:
        return ""
    rt = getattr(s, "repeat_type", "")
    rt = str(getattr(rt, "value", rt) or "")
    every = f"every {getattr(s, 'repeat_number', '')} {getattr(s, 'repeat_unit', '')}".strip()
    start = getattr(s, "start_date_time", "") or ""
    return ", ".join(p for p in (rt, every if every != "every" else "", f"from {start}" if start else "") if p)


def _task_node(key: str, task: Any) -> Dict[str, Any]:
    skill = _skill_node(f"{key}/skill", getattr(task, "skill", None))
    state = _task_state(task)
    trigger = ", ".join(str(t) for t in (getattr(task, "trigger", None) or []) if t)
    return {"key": key, "kind": "task", "label": getattr(task, "name", "") or getattr(task, "id", "") or "task",
            "badge": " · ".join(p for p in (trigger, state) if p),
            "details": _details(("Task id", getattr(task, "id", "")), ("Trigger", trigger or "none"),
                                ("Schedule", _schedule(task)), ("Status", state),
                                ("Skill", (skill or {}).get("label") or "none"),
                                ("Description", _short(getattr(task, "description", "")))),
            "children": [skill] if skill else []}


def build(mainwin: Any, machine_address: str = "") -> Dict[str, Any]:
    """``{"data": root_node, "widget": {...}}`` for this machine."""
    from agent.ec_agents.store_overview import _task_store_id

    stores: Dict[str, Dict[str, Any]] = {}
    try:
        svc = getattr(getattr(mainwin, "ec_db_mgr", None), "store_service", None)
        for s in (svc.list_stores() if svc is not None else []) or []:
            stores[str(s.get("store_id") or "")] = s
    except Exception:
        pass                                          # the tree still shows the agents and tasks

    # store_id -> agent_id -> {"agent": agent, "tasks": [...]}, in the agents' order
    by_store: Dict[str, Dict[str, Dict[str, Any]]] = {sid: {} for sid in stores}
    for agent in list(getattr(mainwin, "agents", None) or []):
        card = getattr(agent, "card", None)
        aid = getattr(card, "id", "") or getattr(agent, "id", "") or ""
        tasks = list(getattr(agent, "tasks", None) or [])
        for task in tasks or [None]:
            sid = _task_store_id(task) if task is not None else NO_STORE
            slot = by_store.setdefault(sid, {}).setdefault(aid, {"agent": agent, "tasks": []})
            if task is not None:
                slot["tasks"].append(task)

    def agent_node(key: str, agent: Any, tasks: List[Any]) -> Dict[str, Any]:
        card = getattr(agent, "card", None)
        away = _runs_elsewhere(agent)                 # another machine's agent: shown, not claimed
        where = away.get("host") or (away.get("vehicle_id") or "")[:8] if away else ""
        running = bool(getattr(agent, "_running", False)) and not away
        n = len(tasks)
        return {"key": key, "kind": "agent", "label": getattr(card, "name", "") or "agent",
                "badge": " · ".join(p for p in (f"runs on {where}" if away else "", "running" if running else "",
                                                f"{n} task{'s' if n != 1 else ''}" if n else "no tasks") if p),
                "details": _details(("Agent id", getattr(card, "id", "")),
                                    ("Runs on", f"{where} (another machine)" if away else ""),
                                    ("Description", _short(getattr(card, "description", "")))),
                "children": [_task_node(f"{key}/t{i}", t) for i, t in enumerate(tasks)]}

    store_nodes = []
    for sid, agents in by_store.items():
        if sid == NO_STORE:
            continue
        rec = stores.get(sid) or {}
        key = f"store:{sid}"
        store_nodes.append({
            "key": key, "kind": "store", "label": rec.get("name") or sid,
            "badge": rec.get("platform") or "",
            "details": _details(("Store id", sid), ("Platform", rec.get("platform")),
                                ("URLs", ", ".join(rec.get("store_urls") or [])),
                                ("Status", rec.get("status") or ("no store record" if not rec else "")),
                                ("Agents", len(agents))),
            "children": [agent_node(f"{key}/a:{aid}", v["agent"], v["tasks"]) for aid, v in agents.items()]})
    # Agents that serve no store sit right under the host, one row each: the owner wants to see
    # every agent with its tasks and their skills, not a folder to open first.
    loose = by_store.get(NO_STORE) or {}
    store_nodes += [agent_node(f"a:{aid}", v["agent"], v["tasks"]) for aid, v in loose.items()]

    try:
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        vehicle_id = resolve_local_vehicle_id(mainwin) or ""
    except Exception:
        vehicle_id = ""
    host = socket.gethostname()
    all_agents = list(getattr(mainwin, "agents", None) or [])
    n_away = sum(1 for a in all_agents if _runs_elsewhere(a))
    n_agents = len(all_agents) - n_away
    root = {"key": f"host:{machine_address or host}", "kind": "host", "label": host, "badge": "online",
            "details": _details(("Machine", machine_address), ("Vehicle id", vehicle_id),
                                ("Stores", len(stores)), ("Agents", n_agents),
                                ("Agents on other machines", n_away)),
            "children": store_nodes}
    return {"data": root,
            "widget": {"type": "tree", "title": f"{host}: stores, agents, tasks and skills",
                       "nodes": [root], "expand": [root["key"]]}}
