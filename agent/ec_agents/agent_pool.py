"""Picking which agent of a pool gets the next turn (Phase 6a).

A front desk's pool is the set of agents listening to it (resolved by the
dispatcher).  Instead of plain round-robin -- which sends a new customer to an
agent busy mid-reply while another sits idle -- ``pick`` chooses the member
that will start soonest:

  load = turns queued on its tasks + 1 per task executing now
         + turns picked for it but not yet queued (reservations)

Lowest load wins; ties go to the agent this customer had last time, then
round-robin.  Members not running here are skipped (unless none is).  The
caller holds the reservation until the recipient has queued the turn
(``release``), so a burst of picks spreads over idle agents instead of all
landing on the one that looked idle.

General-purpose: knows nothing about any site.  Kill switch
``ECAN_POOL_PICK=0`` (plain round-robin).  Log grep ``[agent-pool]``.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_LOCK = threading.Lock()
_reserved: Dict[str, List[float]] = {}   # agent id -> reservation timestamps
_RESERVATION_TTL_S = 30.0                 # a lost release can't pin load forever


def enabled() -> bool:
    return os.environ.get("ECAN_POOL_PICK", "1") != "0"


def _default_lookup(agent_id: str):
    try:
        from agent.agent_service import get_agent_by_id
        return get_agent_by_id(agent_id)
    except Exception:
        return None


def agent_load(agent: Any) -> int:
    """Turns waiting or running on the agent's tasks (0 for a task-less agent)."""
    from agent.ec_tasks.runner import _task_execution_future_running
    load = 0
    for task in list(getattr(agent, "tasks", None) or []):
        try:
            q = getattr(task, "queue", None)
            load += q.qsize() if q is not None else 0
            load += 1 if _task_execution_future_running(task) else 0
        except Exception:
            continue
    return load


def _reservations(agent_id: str, now: float) -> int:
    stamps = [t for t in _reserved.get(agent_id, []) if now - t < _RESERVATION_TTL_S]
    if stamps:
        _reserved[agent_id] = stamps
    else:
        _reserved.pop(agent_id, None)
    return len(stamps)


def pick(candidate_ids: List[str], state: dict, prefer_id: str = "",
         lookup: Optional[Callable[[str], Any]] = None) -> str:
    """The member that should get the next turn; reserves it (call ``release``)."""
    ids = [i for i in candidate_ids if i]
    if not ids:
        return ""
    lookup = lookup or _default_lookup
    with _LOCK:
        rr = state.get("rr_index", 0)
        state["rr_index"] = rr + 1
        if not enabled():
            choice = ids[rr % len(ids)]
        else:
            now = time.time()
            agents = {i: lookup(i) for i in ids}
            running = [i for i in ids if getattr(agents[i], "_running", False)]
            pool = running or ids   # nothing reported running: don't strand the turn
            loads = {i: agent_load(agents[i]) + _reservations(i, now) if agents[i] is not None else 10**6
                     for i in pool}
            best = min(loads.values())
            tied = [i for i in pool if loads[i] == best]
            if prefer_id in tied:
                choice = prefer_id
            else:
                choice = tied[rr % len(tied)]
            _reserved.setdefault(choice, []).append(now)
            if len(pool) > 1:
                logger.info(f"[agent-pool] picked ...{choice[-6:]} load={loads[choice]} "
                            f"pool={ {i[-6:]: loads[i] for i in pool} }"
                            + (f" (sticky)" if choice == prefer_id else ""))
        return choice


def release(agent_id: str) -> None:
    """The picked agent has queued the turn (or the send failed)."""
    with _LOCK:
        stamps = _reserved.get(agent_id)
        if stamps:
            stamps.pop(0)
            if not stamps:
                _reserved.pop(agent_id, None)
