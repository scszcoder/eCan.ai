"""Spending limits and a circuit breaker for the L2 resolver.

L2 calls the strongest available model, by decision -- "no room for mistake".
That makes an unhealed element a money leak with no upper bound: the element
fails, the resolver is asked, the answer does not stick, and the next poll asks
again. Forever, on every affected machine, with nobody watching.

``ResolverBudget`` in ``element_resolver`` is a per-run cap held by the caller.
It is not enough on its own for three reasons:

* A long-lived chat session is one "run" that lasts for days, so a per-run
  cap is effectively no cap.
* It lives in memory, so a machine stuck in a bad state gets a fresh budget
  every restart -- and a machine stuck in a bad state restarts a lot.
* It is global, so one hopeless element can spend the whole allowance and
  starve every other element on the page.

This module adds what is missing: per-element and per-day limits that survive a
restart, exponential backoff, and a breaker that stops asking entirely and says
so loudly.

The reason a breaker rather than a smaller budget
------------------------------------------------
Silence plus spend is the worst outcome. A budget that quietly runs out leaves
the machine broken *and* unremarkable. When the breaker opens it is an ERROR in
the log and a record in the permanent journal, so "we gave up on this element on
this date" is answerable in two years -- and the machine is visibly degraded
rather than quietly useless.

Platform-side and business-free: it counts against labels the caller supplies
and never interprets them.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from utils.logger_helper import logger_helper as logger

# Per (site, element) per UTC day. An element that needs twenty resolutions in
# one day is not being healed, it is broken.
DAILY_CAP_PER_ELEMENT = 20

# Per machine per UTC day, across every site and element. The backstop for
# "many elements each just under their own cap".
DAILY_CAP_TOTAL = 200

# Consecutive failures for one element before the breaker opens. Distinct from
# the daily cap: a genuinely unresolvable element should stop costing money in
# minutes, not after twenty tries.
CIRCUIT_AFTER_FAILURES = 5

# How long an open breaker stays open. Long enough that a site outage does not
# cost anything, short enough that a deploy which fixes the page recovers by
# itself within the hour.
CIRCUIT_COOLDOWN_S = 3600.0

# Backoff between attempts for the same element, doubling per consecutive
# failure, capped. Stops a fast poll loop from spending the daily cap in a
# minute.
BACKOFF_BASE_S = 5.0
BACKOFF_MAX_S = 300.0


@dataclass
class _ElementState:
    calls_today: int = 0
    consecutive_failures: int = 0
    last_attempt_at: float = 0.0
    circuit_open_until: float = 0.0
    total_calls: int = 0
    resolved: int = 0


_LOCK = threading.Lock()
_STATE: Dict[str, _ElementState] = {}
_DAY = ""
_TOTAL_TODAY = 0
_LOADED = False


def _state_path() -> Path:
    override = (os.getenv("ECAN_RESOLVER_GUARD_DIR") or "").strip()
    if override:
        base = Path(override)
    else:
        try:
            from config.app_info import app_info
            base = Path(app_info.appdata_path)
        except Exception:
            base = Path.home() / ".ecan"
    base.mkdir(parents=True, exist_ok=True)
    return base / "resolver_guard.json"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load() -> None:
    """Restore today's spend. Must survive a restart or the cap means nothing."""
    global _DAY, _TOTAL_TODAY, _LOADED
    if _LOADED:
        return
    _LOADED = True
    _DAY = _today()
    try:
        path = _state_path()
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
        # A stored day that is not today means the caps reset, but the breakers
        # and lifetime totals do not -- a breaker that opened at 23:59 must not
        # be cleared by midnight.
        same_day = data.get("day") == _DAY
        if same_day:
            _TOTAL_TODAY = int(data.get("total_today") or 0)
        for key, row in (data.get("elements") or {}).items():
            if not isinstance(row, dict):
                continue
            state = _ElementState(
                calls_today=int(row.get("calls_today") or 0) if same_day else 0,
                consecutive_failures=int(row.get("consecutive_failures") or 0),
                last_attempt_at=float(row.get("last_attempt_at") or 0.0),
                circuit_open_until=float(row.get("circuit_open_until") or 0.0),
                total_calls=int(row.get("total_calls") or 0),
                resolved=int(row.get("resolved") or 0),
            )
            _STATE[str(key)] = state
    except Exception as exc:
        logger.debug(f"[resolver-guard] could not load state: {exc}")


def _save() -> None:
    try:
        path = _state_path()
        payload = {
            "day": _DAY,
            "total_today": _TOTAL_TODAY,
            "elements": {
                key: {
                    "calls_today": s.calls_today,
                    "consecutive_failures": s.consecutive_failures,
                    "last_attempt_at": round(s.last_attempt_at, 3),
                    "circuit_open_until": round(s.circuit_open_until, 3),
                    "total_calls": s.total_calls,
                    "resolved": s.resolved,
                }
                for key, s in _STATE.items()
            },
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    except Exception as exc:
        logger.debug(f"[resolver-guard] could not save state: {exc}")


def _roll_day_if_needed() -> None:
    global _DAY, _TOTAL_TODAY
    today = _today()
    if today == _DAY:
        return
    _DAY = today
    _TOTAL_TODAY = 0
    for state in _STATE.values():
        state.calls_today = 0


def allow(site: str, element: str) -> Tuple[bool, str]:
    """May L2 be called for this element right now?

    Returns ``(permitted, reason)``. When not permitted, *reason* is a short
    phrase for the caller to log -- the caller should then fail the way it did
    before L2 existed, not retry.
    """
    try:
        key = f"{site}::{element}"
        now = time.time()
        with _LOCK:
            _load()
            _roll_day_if_needed()
            state = _STATE.setdefault(key, _ElementState())

            if state.circuit_open_until > now:
                left = int(state.circuit_open_until - now)
                return False, f"circuit open for {left}s"

            if _TOTAL_TODAY >= DAILY_CAP_TOTAL:
                return False, f"machine daily cap {DAILY_CAP_TOTAL} reached"

            if state.calls_today >= DAILY_CAP_PER_ELEMENT:
                return False, (f"element daily cap {DAILY_CAP_PER_ELEMENT} "
                               f"reached")

            if state.consecutive_failures:
                wait = min(BACKOFF_MAX_S,
                           BACKOFF_BASE_S * (2 ** (state.consecutive_failures - 1)))
                if now - state.last_attempt_at < wait:
                    return False, (f"backing off "
                                   f"{int(wait - (now - state.last_attempt_at))}s")
            return True, ""
    except Exception as exc:
        # A guard that throws must not be the thing that blocks a resolution.
        logger.debug(f"[resolver-guard] allow() failed open: {exc}")
        return True, ""


def record_attempt(site: str, element: str) -> None:
    """Count a call that is about to be made. Charge before the answer, so a
    crashed or timed-out call still costs its budget."""
    try:
        global _TOTAL_TODAY
        key = f"{site}::{element}"
        with _LOCK:
            _load()
            _roll_day_if_needed()
            state = _STATE.setdefault(key, _ElementState())
            state.calls_today += 1
            state.total_calls += 1
            state.last_attempt_at = time.time()
            _TOTAL_TODAY += 1
            _save()
    except Exception as exc:
        logger.debug(f"[resolver-guard] could not record attempt: {exc}")


def record_outcome(site: str, element: str, resolved: bool) -> None:
    """Report whether the resolution stuck. Opens the breaker on a losing run."""
    try:
        key = f"{site}::{element}"
        opened = False
        with _LOCK:
            _load()
            state = _STATE.setdefault(key, _ElementState())
            if resolved:
                state.resolved += 1
                state.consecutive_failures = 0
            else:
                state.consecutive_failures += 1
                if (state.consecutive_failures >= CIRCUIT_AFTER_FAILURES
                        and state.circuit_open_until <= time.time()):
                    state.circuit_open_until = time.time() + CIRCUIT_COOLDOWN_S
                    opened = True
            _save()

        if opened:
            logger.error(
                f"[resolver-guard] CIRCUIT OPEN {site}/{element}: "
                f"{CIRCUIT_AFTER_FAILURES} resolutions in a row did not stick. "
                f"Not calling the resolver for this element for "
                f"{int(CIRCUIT_COOLDOWN_S)}s. This element is BROKEN, not "
                f"healing -- it needs a human.")
            try:
                from . import drift_journal
                drift_journal.record_event(
                    site, "resolver_circuit_open", element=element,
                    summary=("gave up resolving this element after "
                             f"{CIRCUIT_AFTER_FAILURES} failed attempts"),
                    evidence={"consecutive_failures": CIRCUIT_AFTER_FAILURES,
                              "cooldown_s": int(CIRCUIT_COOLDOWN_S)},
                    raw_ok=True,
                )
            except Exception:
                pass
    except Exception as exc:
        logger.debug(f"[resolver-guard] could not record outcome: {exc}")


def report() -> Dict[str, Any]:
    """Spend and breaker state. For the run-end report and the CLI."""
    with _LOCK:
        _load()
        now = time.time()
        return {
            "day": _DAY,
            "calls_today": _TOTAL_TODAY,
            "daily_cap": DAILY_CAP_TOTAL,
            "elements": {
                key: {
                    "calls_today": s.calls_today,
                    "total_calls": s.total_calls,
                    "resolved": s.resolved,
                    "consecutive_failures": s.consecutive_failures,
                    "circuit_open": s.circuit_open_until > now,
                }
                for key, s in sorted(_STATE.items())
            },
        }


def log_report(reason: str = "") -> None:
    """Say what L2 cost and what it gave up on. Quiet when it was never used."""
    data = report()
    if not data["calls_today"] and not data["elements"]:
        return
    logger.info(f"[resolver-guard] spend{f' ({reason})' if reason else ''}: "
                f"{data['calls_today']}/{data['daily_cap']} calls today")
    for key, row in data["elements"].items():
        if not row["total_calls"]:
            continue
        note = " CIRCUIT OPEN" if row["circuit_open"] else ""
        logger.info(f"[resolver-guard]   {key}: {row['calls_today']} today, "
                    f"{row['resolved']}/{row['total_calls']} stuck{note}")


def reset() -> None:
    """Drop all state, in memory and on disk. Tests, and a deliberate clear."""
    global _DAY, _TOTAL_TODAY, _LOADED
    with _LOCK:
        _STATE.clear()
        _TOTAL_TODAY = 0
        _DAY = _today()
        _LOADED = True
        try:
            path = _state_path()
            if path.exists():
                path.unlink()
        except Exception:
            pass
