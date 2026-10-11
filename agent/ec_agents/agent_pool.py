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
import math
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
         lookup: Optional[Callable[[str], Any]] = None, pool_id: str = "") -> str:
    """The member that should get the next turn; reserves it (call ``release``).
    With ``pool_id``, only that pool's active members are considered (parked
    ones only when no active member is a candidate)."""
    ids = [i for i in candidate_ids if i]
    if not ids:
        return ""
    lookup = lookup or _default_lookup
    with _LOCK:
        if pool_id and scaling_enabled():
            active = set(_active.get(pool_id) or ())
            ids = [i for i in ids if i in active] or ids
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
    _ensure_controller()


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


# ── the active set (Phase 6c) ────────────────────────────────────────────────
#
# Each pool has an ACTIVE subset of its members; ``pick`` only chooses among
# them.  A controller tick (every TICK_S) sizes it between min and max:
#   * at least min -- raised ahead of the usual traffic for this weekday-hour
#     (pre-warm: expected turns / TURNS_PER_MEMBER_HOUR, looking 10 min ahead);
#   * grow by one when the active members have more turns than members, or
#     turns started since the last change waited (p90) > ECAN_POOL_SCALE_UP_WAIT_S;
#   * shrink by one when nothing is queued or running, the last change is
#     idle_minutes old and the turns of that period fit on one member fewer.
# Shrinking PARKS a member: it is no longer picked, finishes what it already
# has (that is the drain) and stays running, so it can come back instantly.
# ECAN_POOL_SCALING=0: no controller, every member is picked.

TICK_S = 15.0
_UP_COOLDOWN_S = 30.0

_active: Dict[str, List[str]] = {}
_changed_at: Dict[str, float] = {}
_controller: Optional[threading.Thread] = None


def scaling_enabled() -> bool:
    return enabled() and os.environ.get("ECAN_POOL_SCALING", "1") != "0"


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def active_members(pool_id: str) -> List[str]:
    with _LOCK:
        return list(_active.get(pool_id) or [])


def total_active() -> int:
    """Members picked from across all pools (one shared by pools counts once)."""
    with _LOCK:
        return len({m for act in _active.values() for m in act})


def _waits_since(members: List[str], since: float, now: float) -> List[float]:
    return [w for m in members for t, w in _turns.get(m, ()) if t >= since and now - t <= _WAIT_WINDOW_S]


def _last_turn(member: str) -> float:
    dq = _turns.get(member)
    return dq[-1][0] if dq else 0.0


def _target_min(pool_id: str, settings: Dict[str, int], now: float) -> int:
    per_member = _env_float("ECAN_POOL_TURNS_PER_MEMBER_HOUR", 60.0)
    expected = max(expected_turns(pool_id, now) or 0.0, expected_turns(pool_id, now + 600) or 0.0)
    warm = math.ceil(expected / per_member) if per_member > 0 else 0
    return min(settings["max"], max(settings["min"], warm))


def tick(now: Optional[float] = None, lookup: Optional[Callable[[str], Any]] = None) -> Dict[str, List[str]]:
    """One controller pass over every pool. Returns {pool: active members}."""
    lookup = lookup or _default_lookup
    now = time.time() if now is None else now
    out = {}
    for pool_id, pool in pools().items():
        try:
            out[pool_id] = _tick_pool(pool_id, pool, now, lookup)
        except Exception as e:
            logger.warning(f"[agent-pool] controller failed for pool {pool_id[-6:]}: {e}")
    return out


# Manual size (ecan agents pool --pin N): exactly N members answer, no scaling,
# until unpinned.  In memory only; an app restart forgets it.
_pins: Dict[str, int] = {}


def set_pin(front_desk_id: str, size: Optional[int]) -> Optional[List[str]]:
    """Pin the pool's active size (None = back to automatic). Applies now;
    returns the active members, or None if there is no such pool."""
    pool = pools().get(front_desk_id)
    if pool is None:
        return None
    if not scaling_enabled():
        raise ValueError("pool sizing is off (ECAN_POOL_SCALING=0): every member answers")
    with _LOCK:
        if size is None:
            _pins.pop(front_desk_id, None)
        else:
            _pins[front_desk_id] = max(1, int(size))
    logger.info(f"[agent-pool] pool ...{front_desk_id[-6:]} "
                f"{'unpinned (automatic)' if size is None else f'pinned to {max(1, int(size))}'}")
    return _tick_pool(front_desk_id, pool, time.time(), _default_lookup)


def pin_of(front_desk_id: str) -> Optional[int]:
    return _pins.get(front_desk_id)


def _tick_pinned(pool_id: str, members: List[str], size: int, loads: Dict[str, int]) -> List[str]:
    target = min(size, len(members))
    with _LOCK:
        act = [m for m in (_active.get(pool_id) or []) if m in members]
        before = list(act)
        while len(act) < target:
            act.append(min((m for m in members if m not in act), key=lambda m: loads[m]))
        while len(act) > target:
            act.remove(min(act, key=_last_turn))   # the one used least recently
        _active[pool_id] = act
        if act != before:
            _changed_at[pool_id] = time.time()
    if act != before:
        logger.info(f"[agent-pool] pool ...{pool_id[-6:]} active {len(before)} -> {len(act)} (pinned to {size}); "
                    f"active={[m[-6:] for m in act]}")
    return act


def _tick_pool(pool_id: str, pool: Dict[str, Any], now: float, lookup) -> List[str]:
    settings = pool["settings"]
    members = [m for m in pool["members"] if getattr(lookup(m), "_running", False)] or list(pool["members"])
    if pool_id in _pins and members:
        loads = {m: agent_load(lookup(m)) if lookup(m) is not None else 0 for m in members}
        return _tick_pinned(pool_id, members, _pins[pool_id], loads)
    if settings["max"] <= 0 or not members:
        with _LOCK:
            _active[pool_id] = list(members)
        return list(members)
    loads = {m: agent_load(lookup(m)) if lookup(m) is not None else 0 for m in members}
    floor = _target_min(pool_id, settings, now)
    ceiling = min(settings["max"], len(members))
    up_wait = _env_float("ECAN_POOL_SCALE_UP_WAIT_S", 5.0)
    per_member_hour = _env_float("ECAN_POOL_TURNS_PER_MEMBER_HOUR", 60.0)
    with _LOCK:
        act = [m for m in (_active.get(pool_id) or []) if m in members]
        changed = _changed_at.get(pool_id, 0.0)
        before = list(act)
        reason = ""
        if not act:
            # Start with the busiest members, so nobody mid-turn gets parked.
            act = sorted(members, key=lambda m: -loads[m])[:max(1, floor)]
            reason = "start"
        parked = [m for m in members if m not in act]
        busy = sum(loads[m] for m in act)
        p90 = _percentile(_waits_since(act, changed, now), 0.9)
        if len(act) < floor and parked:
            act.append(min(parked, key=lambda m: loads[m]))
            reason = reason or ("pre-warm" if floor > settings["min"] else "minimum")
        elif (len(act) < ceiling and parked and now - changed >= _UP_COOLDOWN_S
              and (busy > len(act) or p90 > up_wait)):
            act.append(min(parked, key=lambda m: loads[m]))
            reason = f"demand: {busy} queued/running on {len(before)}, p90 wait {p90:.1f}s"
        elif len(act) > max(1, floor) and busy == 0 and now - changed >= settings["idle_minutes"] * 60:
            idle_s = settings["idle_minutes"] * 60
            recent = sum(1 for m in act for t, _ in _turns.get(m, ()) if now - t <= idle_s)
            fits = per_member_hour * idle_s / 3600
            if fits <= 0 or recent <= (len(act) - 1) * fits:
                act.remove(min(act, key=_last_turn))   # the one used least recently
                reason = f"idle: {recent} turn(s) in {settings['idle_minutes']} min"
        _active[pool_id] = act
        if act != before:
            _changed_at[pool_id] = now
    if act != before:
        logger.info(f"[agent-pool] pool ...{pool_id[-6:]} active {len(before)} -> {len(act)} ({reason}); "
                    f"active={[m[-6:] for m in act]} parked={[m[-6:] for m in members if m not in act]}")
    return act


def _controller_loop() -> None:
    while True:
        time.sleep(TICK_S)
        tick()


def _ensure_controller() -> None:
    global _controller
    if _controller is not None or not scaling_enabled():
        return
    with _LOCK:
        if _controller is None:
            _controller = threading.Thread(target=_controller_loop, name="AgentPoolController", daemon=True)
            _controller.start()


def pool_view(front_desk_id: str, lookup: Optional[Callable[[str], Any]] = None) -> Optional[Dict[str, Any]]:
    """What the front desk's agent page shows about its pool, or None."""
    lookup = lookup or _default_lookup
    stats = pool_stats(front_desk_id, lookup)
    if not stats:
        return None
    active = set(active_members(front_desk_id)) if scaling_enabled() else set(stats["members"])
    rows = []
    for m in stats["members"]:
        ag = lookup(m)
        rows.append({"id": m, "name": getattr(getattr(ag, "card", None), "name", "") or m,
                     "active": m in active or not active, "running": bool(getattr(ag, "_running", False)),
                     "load": stats["load"].get(m, 0), "last_turn": _last_turn(m) or None})
    return {"settings": stats["settings"], "members": rows, "scaling": scaling_enabled(),
            "pinned": _pins.get(front_desk_id),
            "active_count": sum(1 for r in rows if r["active"]),
            "wait_p50_s": stats["wait_p50_s"], "wait_p90_s": stats["wait_p90_s"],
            "turns_last_hour": stats["turns_last_hour"],
            "expected_turns_this_hour": stats["expected_turns_this_hour"]}


# ── picking from a skill's own code (Phase 6d) ───────────────────────────────
#
# A front desk without PreDispatch (千牛: no browser node) picks its Q&A agent
# in its skill's code node. It can call this instead of its own round-robin:
#
#     from agent.ec_agents.agent_pool import pick_for_customer
#     qa_agent_id = pick_for_customer(front_desk_agent_id, customer_id,
#                                     candidate_ids=qa_agent_ids)
#
# Same choice as PreDispatch: the buyer's agent from the last 30 min if it is
# among the least loaded, else the least-loaded active member; the pool is
# registered, so the controller sizes it and its waits are measured.

_STICKY_TTL_S = 1800.0
_sticky: Dict[tuple, tuple] = {}         # (front desk, customer) -> (member, t)
_pick_state: Dict[str, dict] = {}         # front desk -> round-robin state
_HOLD_S = 10.0                            # reservation until the turn is (surely) queued


def _listeners_of(front_desk_id: str) -> List[str]:
    try:
        from agent.ec_tasks.runner import find_my_listeners
        return list(find_my_listeners(front_desk_id) or [])
    except Exception:
        return []


def pick_for_customer(front_desk_id: str, customer_id: str, candidate_ids: Any = None,
                      lookup: Optional[Callable[[str], Any]] = None) -> str:
    """The Q&A agent for this customer's turn ('' if the pool is empty).

    ``candidate_ids``: list or comma-separated ids (e.g. task_vars.qa_agent_ids);
    omitted -> the agents listening to this front desk."""
    lookup = lookup or _default_lookup
    if isinstance(candidate_ids, str):
        candidate_ids = [c.strip() for c in candidate_ids.split(",")]
    ids = [str(c) for c in (candidate_ids or _listeners_of(front_desk_id)) if c]
    if not ids:
        return ""
    with _LOCK:
        registered = (_pools.get(front_desk_id) or {}).get("members")
    if registered != ids:
        register_pool(front_desk_id, ids, settings_of(lookup(front_desk_id)))
    now = time.time()
    key = (front_desk_id, str(customer_id or ""))
    with _LOCK:
        prior = _sticky.get(key)
        prefer = prior[0] if prior and now - prior[1] < _STICKY_TTL_S else ""
        state = _pick_state.setdefault(front_desk_id, {})
    choice = pick(ids, state, prefer_id=prefer, lookup=lookup, pool_id=front_desk_id)
    if choice:
        with _LOCK:
            _sticky[key] = (choice, now)
            if len(_sticky) > 5000:
                for k in [k for k, (_, t) in _sticky.items() if now - t >= _STICKY_TTL_S]:
                    _sticky.pop(k, None)
        # The code node sends right after picking; hold the reservation that long.
        timer = threading.Timer(_HOLD_S, release, args=(choice,))
        timer.daemon = True
        timer.start()
    return choice
