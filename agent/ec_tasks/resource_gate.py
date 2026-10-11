"""Exclusive resources for task runs.

Two runs that need the same exclusive resource (a browser profile, a
user-named resource) never execute at the same time; everything else runs in
parallel as before.  A run that cannot get its resources is parked in a wait
line and re-submitted when they free up -- no thread blocks while waiting.

Wait-line order: priority class (reactive < scheduled < background), then
arrival, then the task's position in its agent's task list (ties only).

Which resources a task needs (``resource_keys``):
  * the browser profile it is bound to, but only when its skill actually drives
    a browser (has a ``browser-automation`` node or declares ``requires:
    ["browser"]``).  These inferred keys are scoped to the task's own agent:
    the conflict being solved is several duties of one agent fighting over one
    browser; agents that cooperate on one store (front desk + Q&A) are not
    serialized against each other.
  * ``metadata["exclusive_resources"]``: names the user gave; global.

Holders are re-entrant: a task that already holds a key may acquire it again
directly (its own resume / follow-up turn).  Waiters are only granted when
their keys are completely free, so queued runs of one task stay in order.

Kill switch: ``ECAN_TASK_RESOURCE_GATE=0``.
"""
from __future__ import annotations

import itertools
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from utils.logger_helper import logger_helper as logger

REACTIVE, SCHEDULED, BACKGROUND = 0, 1, 2
_CLASS_NAMES = {REACTIVE: "reactive", SCHEDULED: "scheduled", BACKGROUND: "background"}


def gate_enabled() -> bool:
    return os.environ.get("ECAN_TASK_RESOURCE_GATE", "1") != "0"


# ── what a task needs ────────────────────────────────────────────────────────

def _has_browser_node(obj: Any, depth: int = 0) -> bool:
    if depth > 12:
        return False
    if isinstance(obj, dict):
        if obj.get("type") == "browser-automation":
            return True
        return any(_has_browser_node(v, depth + 1) for v in obj.values() if isinstance(v, (dict, list)))
    if isinstance(obj, list):
        return any(_has_browser_node(v, depth + 1) for v in obj)
    return False


def skill_drives_browser(skill: Any) -> bool:
    if skill is None:
        return False
    try:
        if "browser" in [str(r).lower() for r in (getattr(skill, "requires", None) or [])]:
            return True
    except Exception:
        pass
    return _has_browser_node(getattr(skill, "diagram", None) or {})


def _browser_key(identity: Any) -> str:
    if not isinstance(identity, dict):
        return ""
    for k in ("browser_profile_id", "fingerprint_profile_id", "profile_id",
              "user_data_dir", "cdp_port", "browser_slot_id", "slot"):
        v = identity.get(k)
        if v not in (None, ""):
            return f"browser:{v}"
    return ""


def resource_keys(task: Any, agent_id: str = "") -> Tuple[str, ...]:
    """The exclusive resources a run of ``task`` needs (sorted, de-duplicated)."""
    keys = set()
    meta = getattr(task, "metadata", None)
    meta = meta if isinstance(meta, dict) else {}
    for name in meta.get("exclusive_resources") or []:
        name = str(name).strip()
        if name:
            keys.add(f"user:{name}")
    if skill_drives_browser(getattr(task, "skill", None)):
        bk = _browser_key(meta.get("browser_identity"))
        if bk:
            keys.add(f"agent:{agent_id or getattr(task, 'agent_id', '') or '?'}/{bk}")
    return tuple(sorted(keys))


def priority_class(task: Any, trigger_type: str) -> int:
    meta = getattr(task, "metadata", None)
    if isinstance(meta, dict) and str(meta.get("run_class") or "").lower() == "background":
        return BACKGROUND
    if str(trigger_type or "").lower() in ("message", "chat_queue", "a2a_queue", "human chat",
                                           "agent message", "interaction", "manual", "dev"):
        return REACTIVE
    return SCHEDULED


# ── the gate ─────────────────────────────────────────────────────────────────

@dataclass
class _Waiter:
    holder: str
    keys: Tuple[str, ...]
    prio: int
    seq: int
    tiebreak: int
    on_grant: Callable[[], None]
    label: str = ""
    trigger: str = ""
    since: float = field(default_factory=time.time)

    def order(self):
        return (self.prio, self.seq, self.tiebreak)


class ResourceGate:
    def __init__(self, spawn: Optional[Callable[[Callable[[], None]], None]] = None):
        self._lock = threading.Lock()
        self._held: Dict[str, Tuple[str, int]] = {}   # key -> (holder, count)
        self._waiters: List[_Waiter] = []
        self._seq = itertools.count()
        self._spawn = spawn or _spawn_thread

    # Every "granted" (including the hold handed to ``on_grant``) is released
    # exactly once with ``release(holder, keys)``.
    def acquire_or_wait(self, holder: str, keys: Tuple[str, ...], prio: int, tiebreak: int,
                        on_grant: Callable[[], None], label: str = "", trigger: str = "",
                        dedupe_trigger: bool = False) -> str:
        """``"granted"`` (keys taken), ``"queued"`` (``on_grant`` runs later with the
        keys already held -- it must release them), or ``"duplicate"`` (this holder
        already waits with the same trigger and ``dedupe_trigger`` is set)."""
        if not keys:
            return "granted"
        with self._lock:
            # Already ours (a granted waiter re-submitting, or our own follow-up
            # turn): take it again.  Otherwise only if free and nobody is queued.
            if self._holds_all(holder, keys) or (
                    self._free_for(holder, keys, reentrant=True) and not self._waits_before(holder, keys)):
                self._take(holder, keys)
                return "granted"
            if dedupe_trigger and any(w.holder == holder and w.trigger == trigger for w in self._waiters):
                return "duplicate"
            w = _Waiter(holder, keys, prio, next(self._seq), tiebreak, on_grant, label, trigger)
            self._waiters.append(w)
            blockers = sorted({self._held[k][0] for k in keys if k in self._held})
        logger.info(f"[resource-gate] '{label}' waits for {list(keys)} "
                    f"({_CLASS_NAMES.get(prio, prio)}, held by {blockers or 'earlier waiters'})")
        return "queued"

    def release(self, holder: str, keys: Tuple[str, ...]) -> None:
        if not keys:
            return
        with self._lock:
            for k in keys:
                h = self._held.get(k)
                if not h or h[0] != holder:
                    continue
                if h[1] <= 1:
                    del self._held[k]
                else:
                    self._held[k] = (holder, h[1] - 1)
            granted = self._grant_waiters()
        for w in granted:
            logger.info(f"[resource-gate] '{w.label}' gets {list(w.keys)} "
                        f"after {time.time() - w.since:.1f}s")
            self._spawn(w.on_grant)

    def drop_waiters(self, holder: str) -> int:
        with self._lock:
            before = len(self._waiters)
            self._waiters = [w for w in self._waiters if w.holder != holder]
            return before - len(self._waiters)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "held": {k: {"holder": h, "count": c} for k, (h, c) in self._held.items()},
                "waiting": [{"holder": w.holder, "label": w.label, "keys": list(w.keys),
                             "class": _CLASS_NAMES.get(w.prio, w.prio), "since": w.since}
                            for w in sorted(self._waiters, key=_Waiter.order)],
            }

    # ── internals (call with self._lock held) ──
    def _holds_all(self, holder, keys):
        return all(self._held.get(k, ("", 0))[0] == holder for k in keys)

    def _free_for(self, holder, keys, reentrant):
        for k in keys:
            h = self._held.get(k)
            if h and not (reentrant and h[0] == holder):
                return False
        return True

    def _waits_before(self, holder, keys):
        """Someone else already queued for one of ``keys`` (don't jump the line)."""
        ks = set(keys)
        return any(w.holder != holder and ks.intersection(w.keys) for w in self._waiters)

    def _take(self, holder, keys):
        for k in keys:
            h = self._held.get(k)
            self._held[k] = (holder, (h[1] + 1) if h else 1)

    def _grant_waiters(self) -> List[_Waiter]:
        granted, blocked = [], set()
        for w in sorted(self._waiters, key=_Waiter.order):
            # A key wanted by a better-placed waiter is reserved for it, so a
            # later waiter can't slip in ahead even if its other keys are free.
            if blocked.intersection(w.keys) or not self._free_for(w.holder, w.keys, reentrant=False):
                blocked.update(w.keys)
                continue
            self._take(w.holder, w.keys)
            granted.append(w)
            blocked.update(w.keys)
        for w in granted:
            self._waiters.remove(w)
        return granted


def _spawn_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="ResourceGateGrant", daemon=True).start()


_gate: Optional[ResourceGate] = None
_gate_lock = threading.Lock()


def get_gate() -> ResourceGate:
    global _gate
    with _gate_lock:
        if _gate is None:
            _gate = ResourceGate()
        return _gate
