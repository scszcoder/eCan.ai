"""Is this install currently failing, and can the person running it tell?

The gap this fills: every detector built so far writes to a log or to the
permanent journal. Neither is visible to the person whose shop is not getting
replies. They find out when a customer complains — which is the situation the
whole self-healing effort exists to leave.

So the three things that know something is wrong report here, and this reports
into the readiness ledger (``utils.agent_status``) that already drives the dots
on the Agents page. A degraded install looks degraded in its own UI.

Why a delay before it turns red
------------------------------
A single missed resolution is normal: pages render late, a scan catches a frame
mid-rebuild. Going red on the first miss would make the dot meaningless within a
day. A degradation therefore has to persist for ``DEGRADED_AFTER_S`` before it
is reported as such; until then it is ``watching``, which is visible without
crying wolf.

The level advances when something reports again, not on a timer -- there is no
thread here. That is sufficient because every condition this tracks recurs by
nature: a collapsed parser collapses on the next scan too, and a site that has
stopped answering keeps not answering. It does mean a degradation that stops
being reported stays at whatever level it last reached until something clears
it, which is why :func:`mark_recovered` exists and is called on success.

Platform-side and business-free: sources name themselves and this never
interprets the names.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from utils.logger_helper import logger_helper as logger

# How long a problem must persist before the install is called degraded rather
# than merely watched.
DEGRADED_AFTER_S = 120.0


@dataclass
class _Degradation:
    source: str
    detail: str
    since: float
    site: str = ""
    element: str = ""


_LOCK = threading.Lock()
_ACTIVE: Dict[str, _Degradation] = {}


def mark_degraded(source: str, detail: str = "", *,
                  site: str = "", element: str = "") -> None:
    """Something is wrong, and *source* is what noticed.

    Repeat calls for the same source keep the original start time, so the age
    of a problem is how long it has actually been happening rather than how
    recently it was last mentioned.
    """
    try:
        key = str(source or "?")
        with _LOCK:
            existing = _ACTIVE.get(key)
            if existing is None:
                _ACTIVE[key] = _Degradation(
                    source=key, detail=str(detail)[:200], since=time.time(),
                    site=str(site), element=str(element))
            else:
                existing.detail = str(detail)[:200] or existing.detail
        _push()
    except Exception as exc:
        logger.debug(f"[degraded] could not mark {source}: {exc}")


def mark_recovered(source: str) -> None:
    """*source* is working again. Clears its degradation."""
    try:
        key = str(source or "?")
        with _LOCK:
            gone = _ACTIVE.pop(key, None)
        if gone is not None:
            held = int(time.time() - gone.since)
            logger.info(f"[degraded] recovered: {key} (was degraded {held}s)")
            _push()
    except Exception as exc:
        logger.debug(f"[degraded] could not clear {source}: {exc}")


def state() -> Tuple[str, str]:
    """``("ok" | "watching" | "degraded", detail)`` for the whole install."""
    with _LOCK:
        if not _ACTIVE:
            return "ok", ""
        now = time.time()
        oldest = min(_ACTIVE.values(), key=lambda d: d.since)
        age = int(now - oldest.since)
        parts = []
        for d in sorted(_ACTIVE.values(), key=lambda d: d.since):
            where = f"{d.site}/{d.element}".strip("/")
            parts.append(f"{d.source}"
                         + (f"@{where}" if where else "")
                         + (f" ({d.detail})" if d.detail else ""))
        detail = "; ".join(parts)[:400]
        level = "degraded" if age >= DEGRADED_AFTER_S else "watching"
        return level, f"{detail} | {age}s"


def _push() -> None:
    """Send the current level to the readiness ledger. Never raises."""
    try:
        level, detail = state()
        from utils import agent_status
        agent_status.report(targeting=level, targeting_detail=detail or None)
    except Exception as exc:
        logger.debug(f"[degraded] could not report: {exc}")


def refresh() -> None:
    """Re-evaluate and report. For a periodic caller, and for run end.

    Needed because ``watching`` becomes ``degraded`` through time passing, and
    nothing here runs on a timer.
    """
    _push()


def active() -> Dict[str, Dict[str, object]]:
    """What is currently wrong. For reports and tests."""
    with _LOCK:
        now = time.time()
        return {
            key: {"detail": d.detail, "site": d.site, "element": d.element,
                  "age_s": int(now - d.since)}
            for key, d in sorted(_ACTIVE.items())
        }


def reset() -> None:
    """Clear everything. Tests, and a deliberate re-baseline."""
    with _LOCK:
        _ACTIVE.clear()
