"""Store placement: the store's assignment decides which machine runs it.

For an agent whose tasks carry an explicit ``task_vars.store_id`` (a
"store-bound" agent), the vehicle pin is NOT consulted. The vehicle gate fails
open -- an empty pin, or a pin naming no known machine, starts the agent on
every machine of the account -- which gave a customer two replies once a second
machine came up. Here the answer comes from the cloud store registry instead:

    assigned to this machine          -> run
    assigned to another machine       -> skip
    unassigned                        -> claim it (atomic, one winner); run if won
    cloud unreachable and no cache    -> run, WARNING (owner decision D2)

An agent can serve several stores (a store belongs to the task, not the
agent), and it is one unit of placement, so it runs here only if EVERY store
it serves resolves to "run". Split across machines is refused loudly.

Moving a store: a machine only starts a store assigned to it once the previous
holder has released it (``reportedVehicleId`` empty or this machine) or has gone
offline -- gap over duplicate. See docs/STORE_PLACEMENT_DESIGN.md.

The last ``store_list`` is cached on disk per user, so a machine keeps serving
its stores through a cloud outage.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

RUN = "run"
SKIP = "skip"

# One store_list for a burst of agent starts, not one per agent.
CACHE_TTL_S = 50.0
CACHE_FILE = "store_assignments.json"

_lock = threading.Lock()
_mem: Dict[str, Any] = {}          # {"fetched_at": float, "stores": {sid: entry}}
_warned_unknown: set = set()


# ── which stores an agent serves ─────────────────────────────────────

def store_ids_of_agent(agent: Any) -> List[str]:
    """Explicit store ids across the agent's tasks, order kept. [] = not store-bound."""
    from agent.ec_skills.prompt_variable_providers import STORE_ID_VAR
    out: List[str] = []
    for task in list(getattr(agent, "tasks", None) or []):
        md = getattr(task, "metadata", None)
        if not isinstance(md, dict) and isinstance(task, dict):
            md = task.get("metadata")
        tv = md.get("task_vars") if isinstance(md, dict) else None
        sid = str((tv or {}).get(STORE_ID_VAR) or "").strip() if isinstance(tv, dict) else ""
        if sid and sid not in out:
            out.append(sid)
    return out


# ── the assignment cache ─────────────────────────────────────────────

def _cache_path(mainwin: Any) -> str:
    home = getattr(mainwin, "my_ecb_data_homepath", "") or ""
    return os.path.join(home, CACHE_FILE) if home else ""


def _entry(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "assigned": row.get("assignedVehicleId") or None,
        "reported": row.get("reportedVehicleId") or None,
        "reported_online": row.get("reportedVehicleOnline"),
        "status": row.get("status") or "active",
    }


def _load_disk(mainwin: Any) -> Optional[Dict[str, Any]]:
    path = _cache_path(mainwin)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data.get("stores"), dict) else None
    except Exception as e:
        logger.warning(f"[StorePlacement] assignment cache unreadable: {e}")
        return None


def _save_disk(mainwin: Any, data: Dict[str, Any]) -> None:
    path = _cache_path(mainwin)
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception as e:
        logger.warning(f"[StorePlacement] could not persist assignment cache: {e}")


def refresh(mainwin: Any, force: bool = False) -> Optional[Dict[str, Any]]:
    """The current assignments: cloud if reachable, else the last cache, else None."""
    with _lock:
        now = time.time()
        if not force and _mem and now - _mem.get("fetched_at", 0) < CACHE_TTL_S:
            return _mem
        try:
            from agent.cloud_api.store_api import store_list
            data = store_list(include_archived=True)
            snap = {"fetched_at": now,
                    "stores": {r["storeId"]: _entry(r) for r in (data.get("stores") or [])
                               if r.get("storeId")}}
            _mem.clear()
            _mem.update(snap)
            _save_disk(mainwin, snap)
            return _mem
        except Exception as e:
            if _mem:
                logger.warning(f"[StorePlacement] store_list failed, using last assignments: {e}")
                return _mem
            disk = _load_disk(mainwin)
            if disk:
                logger.warning(f"[StorePlacement] store_list failed, using cached assignments: {e}")
                _mem.update(disk)
                return _mem
            logger.warning(f"[StorePlacement] store_list failed and no cached assignments: {e}")
            return None


def note_claimed(store_id: str, vehicle_id: str) -> None:
    """Record a won claim locally so the rest of this burst sees it."""
    with _lock:
        stores = _mem.setdefault("stores", {})
        entry = stores.setdefault(store_id, {"assigned": None, "reported": None,
                                             "reported_online": None, "status": "active"})
        entry["assigned"] = vehicle_id


# ── the decision ─────────────────────────────────────────────────────

def decide_store(store_id: str, me: str, snapshot: Optional[Dict[str, Any]],
                 claim=None) -> Tuple[str, str]:
    """``(RUN|SKIP, reason)`` for one store on machine ``me``.

    ``claim(store_id) -> bool`` is only called for an unassigned store; it
    returns whether this machine won. Pure apart from that call.
    """
    if snapshot is None:
        return RUN, "unknown: cloud unreachable and no cached assignment"
    entry = (snapshot.get("stores") or {}).get(store_id)
    if entry and entry.get("status") == "archived":
        return SKIP, "store is archived"
    assigned = (entry or {}).get("assigned")
    if not assigned:
        if claim is None:
            return SKIP, "unassigned (not claimed)"
        try:
            won = claim(store_id)
        except Exception as e:
            # Same exposure as D2: a claim we cannot make is a cloud we cannot reach.
            return RUN, f"unknown: claim failed ({e})"
        return (RUN, "claimed") if won else (SKIP, "claimed by another machine")
    if assigned != me:
        return SKIP, f"assigned to another machine ({assigned[:12]}..)"
    reported = (entry or {}).get("reported")
    if reported and reported != me and (entry or {}).get("reported_online"):
        # Moving in: the previous holder still runs it. Gap over duplicate.
        return SKIP, f"waiting for {reported[:12]}.. to release it"
    return RUN, "assigned here"


def placement_for_agent(agent: Any) -> Tuple[Optional[str], str]:
    """``(None, "")`` for an agent this module does not govern, else ``(RUN|SKIP, reason)``."""
    stores = store_ids_of_agent(agent)
    if not stores:
        return None, ""
    mainwin = getattr(agent, "mainwin", None)
    from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
    me = resolve_local_vehicle_id(mainwin)
    if not me:
        return RUN, "unknown: this machine has no stable id yet"
    snapshot = refresh(mainwin)

    def claim(store_id: str) -> bool:
        from agent.cloud_api.store_api import store_claim
        won = bool(store_claim(store_id, me).get("won"))
        if won:
            note_claimed(store_id, me)
        return won

    # Two passes: claim nothing while any store blocks the agent, or a store
    # would end up assigned here with no agent running it.
    first = [(sid, *decide_store(sid, me, snapshot)) for sid in stores]
    blocked = any(v == SKIP and why != "unassigned (not claimed)" for _, v, why in first)
    decisions = first if blocked else [(sid, *decide_store(sid, me, snapshot, claim))
                                       for sid in stores]
    for sid, verdict, why in decisions:
        if why.startswith("unknown") and sid not in _warned_unknown:
            _warned_unknown.add(sid)
            logger.warning(f"[StorePlacement] store {sid!r}: {why} -- running it here; "
                           f"a second machine in the same state would run it too")
    skips = [(sid, why) for sid, verdict, why in decisions if verdict == SKIP]
    if not skips:
        return RUN, "; ".join(f"{sid}: {why}" for sid, _, why in decisions)
    if len(stores) > 1 and len(skips) < len(stores):
        name = getattr(getattr(agent, "card", None), "name", "") or "?"
        logger.error(f"[StorePlacement] agent {name!r} serves stores placed on different "
                     f"machines ({skips}); an agent runs in one place, so it is NOT started "
                     f"here. Give each machine's stores their own agent.")
    return SKIP, "; ".join(f"{sid}: {why}" for sid, why in skips)
