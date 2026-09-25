"""Which stores run in their own store process on this machine.

Owner decision (2026-09-24): a store gets its own store process (a worker,
ONE_APP_MANY_STORES.md) only when this machine serves **two or more stores of
the same platform**. One store per platform keeps running in the app process
exactly as before. The reason is platform-shaped state that is not yet
store-scoped -- the live-chat runner bridge, typing lock, tab pool,
display-name-keyed customer state -- which two stores of one platform must not
share (docs/OPEN_ITEMS.md, Phase E decision point).

The key is the store id. Only the PARENT decides the policy. A store process is
told its key at spawn and runs exactly the agents of that store, so the two can
never disagree about who runs what.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Set

from utils.logger_helper import logger_helper as logger

MIN_STORES_PER_PLATFORM = 2


def _platform_of(mainwin: Any, store_id: str) -> str:
    try:
        rec = mainwin.ec_db_mgr.store_service.get_store(store_id)
        return str((rec or {}).get("platform") or "").strip()
    except Exception:
        return ""


def stores_served_here(mainwin: Any, agents: Iterable[Any], snapshot: Any, me: str) -> List[str]:
    """Stores this machine serves: named by a local, enabled agent and not assigned elsewhere."""
    from agent.ec_agents.store_placement import store_ids_of_agent
    entries = (snapshot or {}).get("stores") or {}
    out: List[str] = []
    for agent in agents or []:
        if (getattr(agent, "status", "active") or "active") == "disabled":
            continue
        for sid in store_ids_of_agent(agent):
            e = entries.get(sid) or {}
            if e.get("status") == "archived":
                continue
            assigned = e.get("assigned")
            if assigned and me and assigned != me:
                continue
            if sid not in out:
                out.append(sid)
    return out


def isolated_store_ids(mainwin: Any, stores: Iterable[str]) -> Set[str]:
    """The stores among ``stores`` that share a platform with another one of them."""
    by_platform: Dict[str, List[str]] = defaultdict(list)
    for sid in stores:
        platform = _platform_of(mainwin, sid)
        if platform:   # a store with no platform cannot be grouped
            by_platform[platform].append(sid)
    return {sid for group in by_platform.values() if len(group) >= MIN_STORES_PER_PLATFORM
            for sid in group}


def isolated_here(mainwin: Any) -> Set[str]:
    """This machine's isolated stores right now. Never raises; {} on doubt (run in-process)."""
    try:
        from agent.ec_agents.store_placement import refresh
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        me = resolve_local_vehicle_id(mainwin)
        served = stores_served_here(mainwin, getattr(mainwin, "agents", None) or [], refresh(mainwin), me)
        return isolated_store_ids(mainwin, served)
    except Exception as e:
        logger.warning(f"[StoreIsolation] could not decide; running stores in-process: {e}")
        return set()


def store_isolation_key(agent: Any) -> str:
    """The store-process key for a store-bound agent, or "" to run it in-process."""
    from agent.ec_agents.store_placement import store_ids_of_agent
    from agent.ec_tasks.worker_placement import worker_key_of_process
    stores = store_ids_of_agent(agent)
    if not stores:
        return ""
    mine = worker_key_of_process()
    if mine:
        # Inside a store process: this agent belongs here iff it serves this store.
        return mine if mine in stores else stores[0]
    isolated = [s for s in stores if s in isolated_here(getattr(agent, "mainwin", None))]
    if not isolated:
        return ""
    if len(stores) > 1:
        name = getattr(getattr(agent, "card", None), "name", "") or "?"
        logger.error(f"[StoreIsolation] agent {name!r} serves several stores {stores}, and "
                     f"{isolated[0]!r} needs its own store process; an agent lives in one "
                     f"process, so it follows {isolated[0]!r}. Give each store its own agents.")
    return isolated[0]
