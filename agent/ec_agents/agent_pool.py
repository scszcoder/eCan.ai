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

import collections
import json as _json
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


# ── pools, settings and metrics (Phase 6b) ───────────────────────────────────
#
# A pool is a front desk's recipient set (registered by the dispatcher each
# time it looks the set up).  Settings live in the front desk task's metadata:
#   pool: {min, max, idle_minutes}
# Metrics come from the members' runners: when a chat turn is queued on a
# member (note_enqueued) and when the member starts executing it
# (note_started) -- the wait between the two is what a bigger active set
# would shorten.  Turns per weekday-hour are kept (EWMA) in pool_traffic.json
# for pre-warming.

DEFAULT_IDLE_MINUTES = 10
_WAIT_WINDOW_S = 600          # p50/p90 over the last 10 min
_KEEP_TURNS_S = 2 * 3600

_pools: Dict[str, Dict[str, Any]] = {}            # front desk id -> {members, settings, seen}
_enqueued: "collections.OrderedDict[int, tuple]" = collections.OrderedDict()   # id(request) -> (t, request)
_turns: Dict[str, collections.deque] = {}          # member id -> deque[(t_start, wait_s)]
_traffic: Optional[Dict[str, Dict[str, float]]] = None
_traffic_hour: Optional[int] = None
_ENQUEUED_MAX = 2000


def pool_settings(raw: Any, n_members: int) -> Dict[str, int]:
    """min/max/idle_minutes from a task's ``pool`` setting, with defaults
    (min 2, max = members, 10 min) and clamped to the member count."""
    raw = raw if isinstance(raw, dict) else {}
    n = max(0, int(n_members))

    def _int(key, default):
        try:
            return int(raw.get(key, default))
        except (TypeError, ValueError):
            return default
    mx = min(n, max(1, _int("max", n))) if n else 0
    mn = min(mx, max(0, _int("min", 2)))
    return {"min": mn, "max": mx, "idle_minutes": max(1, _int("idle_minutes", DEFAULT_IDLE_MINUTES))}


def settings_of(front_desk_agent: Any) -> Any:
    """The ``pool`` setting on one of the front desk agent's tasks, if any."""
    for task in list(getattr(front_desk_agent, "tasks", None) or []):
        meta = getattr(task, "metadata", None)
        if isinstance(meta, dict) and isinstance(meta.get("pool"), dict):
            return meta["pool"]
    return None


def register_pool(front_desk_id: str, members: List[str], raw_settings: Any = None) -> None:
    if not front_desk_id:
        return
    with _LOCK:
        _pools[front_desk_id] = {"members": list(members), "seen": time.time(),
                                 "settings": pool_settings(raw_settings, len(members))}


def pools() -> Dict[str, Dict[str, Any]]:
    with _LOCK:
        return {k: dict(v, members=list(v["members"])) for k, v in _pools.items()}


def note_enqueued(request: Any) -> None:
    """A chat turn was queued on a member's task."""
    with _LOCK:
        _enqueued[id(request)] = (time.time(), request)   # the ref keeps id() unique until popped
        while len(_enqueued) > _ENQUEUED_MAX:
            _enqueued.popitem(last=False)


def note_started(agent_id: str, request: Any) -> None:
    """The member started executing a turn; records how long it waited."""
    if not agent_id or request is None:
        return
    now = time.time()
    _roll_traffic_hour(now)    # before old turns are trimmed below
    with _LOCK:
        entry = _enqueued.pop(id(request), None)
        if entry is None or entry[1] is not request:
            return
        dq = _turns.setdefault(agent_id, collections.deque())
        dq.append((now, now - entry[0]))
        while dq and now - dq[0][0] > _KEEP_TURNS_S:
            dq.popleft()


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def pool_stats(front_desk_id: str, lookup: Optional[Callable[[str], Any]] = None) -> Dict[str, Any]:
    """Members with their current load, recent waits and turns in the last hour."""
    lookup = lookup or _default_lookup
    with _LOCK:
        pool = _pools.get(front_desk_id)
        if not pool:
            return {}
        now = time.time()
        members = list(pool["members"])
        waits, hour_turns = [], 0
        for m in members:
            for t, w in _turns.get(m, ()):
                if now - t <= _WAIT_WINDOW_S:
                    waits.append(w)
                if now - t <= 3600:
                    hour_turns += 1
        reserved = {m: _reservations(m, now) for m in members}
        settings = dict(pool["settings"])
    load = {m: (agent_load(lookup(m)) if lookup(m) is not None else 0) + reserved[m] for m in members}
    return {"members": members, "settings": settings, "load": load,
            "wait_p50_s": round(_percentile(waits, 0.5), 2), "wait_p90_s": round(_percentile(waits, 0.9), 2),
            "turns_10min": len(waits), "turns_last_hour": hour_turns,
            "expected_turns_this_hour": expected_turns(front_desk_id)}


# ── weekday-hour traffic (pre-warm) ──

def _traffic_path() -> str:
    from utils.path_manager import get_writable_path
    return get_writable_path("pool_traffic.json")


def _load_traffic() -> Dict[str, Dict[str, float]]:
    global _traffic
    if _traffic is None:
        try:
            with open(_traffic_path(), encoding="utf-8") as f:
                data = _json.load(f)
            _traffic = data if isinstance(data, dict) else {}
        except Exception:
            _traffic = {}
    return _traffic


def _slot(ts: float) -> str:
    lt = time.localtime(ts)
    return f"{lt.tm_wday}-{lt.tm_hour}"


def _roll_traffic_hour(now: float) -> None:
    """At the first turn of a new hour, fold the finished hour into the EWMA."""
    global _traffic_hour
    hour = int(now // 3600)
    with _LOCK:
        if _traffic_hour is None:
            _traffic_hour = hour
            return
        if hour == _traffic_hour:
            return
        finished = range(max(_traffic_hour, hour - 24), hour)   # quiet hours count as 0
        _traffic_hour = hour
        traffic = _load_traffic()
        for h in finished:
            start, end = h * 3600, (h + 1) * 3600
            slot = _slot(start)
            for fd, p in _pools.items():
                n = sum(1 for m in p["members"] for t, _ in _turns.get(m, ()) if start <= t < end)
                per = traffic.setdefault(fd, {})
                old = per.get(slot)
                per[slot] = round(n if old is None else 0.7 * old + 0.3 * n, 2)
        snapshot = _json.dumps(traffic, ensure_ascii=False)
    try:
        with open(_traffic_path(), "w", encoding="utf-8") as f:
            f.write(snapshot)
    except Exception as e:
        logger.debug(f"[agent-pool] traffic save failed: {e}")


def expected_turns(front_desk_id: str, ts: Optional[float] = None) -> Optional[float]:
    """Typical turns in this weekday-hour, or None until there is history."""
    with _LOCK:
        return _load_traffic().get(front_desk_id, {}).get(_slot(ts if ts is not None else time.time()))
