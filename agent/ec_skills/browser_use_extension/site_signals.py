"""Declared health signals: the first thing that fires when a site moves.

Platform-side and business-free. A bundle declares the small set of cheap,
site-specific checks that fire before anything else when that site changes or
when we start failing on it; this module owns the vocabulary, the severity
scale, and what happens when one trips.

Why declared rather than scattered
----------------------------------
Platform cannot know what failure looks like on a given site. Whoever built
the bundle does -- they know which attribute the row parser leans on, and which
phrase the site uses when it has given up on us. Today that knowledge is
scattered across constants and comments, so nobody can answer "what do we
actually depend on about this site?" (which is exactly the question ws193
raised and nobody could answer). Declaring it makes it one enumerable table.

The four kinds
--------------
``distress``
    The site itself is telling us we failed. The closest thing to ground truth
    there is, because it needs no inference on our part.
``anchor``
    A structural feature some parser depends on. Its disappearance is the site
    having shipped a change.
``invariant``
    Two independent observation paths that should agree. Disagreement means we
    are missing something, even when nothing has visibly broken.
``liveness``
    Something that should keep happening. Its absence catches total blindness,
    which every other kind misses -- because a detector that is not running at
    all reports nothing, exactly like a healthy site.

``distress`` and ``invariant`` are the two that cover the dangerous case (a
customer arriving and us never noticing) because neither depends on us having
attempted anything.

Every signal carries an ``example``: a concrete input that must trip it. A
signal nobody can trip on demand is a signal nobody should trust, and the
example is what lets a test prove otherwise.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

KINDS = ("distress", "anchor", "invariant", "liveness")

# What a trip means for whoever is watching.
#   incident -- a customer is affected, or will be. Look now.
#   warning  -- degraded; worth knowing, not yet an outage.
#   info     -- expected traffic worth counting, not a fault.
SEVERITIES = ("incident", "warning", "info")


@dataclass(frozen=True)
class SiteSignal:
    """One declared tripwire."""

    name: str
    kind: str
    severity: str
    means: str              # plain words: what it means when this trips
    example: str = ""       # an input that MUST trip it; see module docstring

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"unknown signal kind {self.kind!r}; expected {KINDS}")
        if self.severity not in SEVERITIES:
            raise ValueError(
                f"unknown severity {self.severity!r}; expected {SEVERITIES}")


@dataclass
class _Tally:
    count: int = 0
    first_at: float = 0.0
    last_detail: str = ""


_LOCK = threading.Lock()
_REGISTRY: Dict[str, Dict[str, SiteSignal]] = {}
_TRIPS: Dict[tuple, _Tally] = {}


def register(site: str, signals: List[SiteSignal]) -> None:
    """Declare a bundle's signals. Idempotent; re-registering replaces."""
    with _LOCK:
        _REGISTRY[str(site)] = {s.name: s for s in signals}


def declared(site: str = "") -> Dict[str, Any]:
    """Every declared signal, or one site's. For reports and tests."""
    with _LOCK:
        if site:
            return dict(_REGISTRY.get(str(site), {}))
        return {s: dict(d) for s, d in _REGISTRY.items()}


def trip(site: str, name: str, *, detail: str = "",
         evidence: Optional[Dict[str, Any]] = None) -> bool:
    """Record that a declared signal fired. Returns True if it was known.

    Logs at a level matching the declared severity and puts the first
    occurrence of the day on the permanent record. Never raises -- a signal
    must not be able to break the path that noticed it.

    Args:
        site: the bundle that declared the signal.
        name: the signal's declared name. An undeclared name is logged and
            ignored rather than invented, so the registry stays the truth.
        detail: short context for the log line. Keep it free of customer text.
        evidence: structured context for the journal. Shape-summarised there.
    """
    try:
        import time

        with _LOCK:
            signal = _REGISTRY.get(str(site), {}).get(str(name))
            if signal is None:
                logger.warning(
                    f"[site-signal] {site}/{name} tripped but is not declared; "
                    f"add it to the bundle's signal set")
                return False
            key = (str(site), str(name))
            tally = _TRIPS.setdefault(key, _Tally(first_at=time.time()))
            tally.count += 1
            tally.last_detail = detail
            count = tally.count

        line = (f"[site-signal] {signal.severity.upper()} {site}/{name}: "
                f"{signal.means}" + (f" | {detail}" if detail else "")
                + (f" (x{count} this run)" if count > 1 else ""))
        if signal.severity == "incident":
            logger.error(line)
        elif signal.severity == "warning":
            logger.warning(line)
        else:
            logger.info(line)

        # An incident means a customer is affected right now. That belongs on
        # the readiness dots, not only in the log -- a warning is worth knowing
        # about, an incident is worth someone looking.
        if signal.severity == "incident":
            try:
                from . import degraded_state
                degraded_state.mark_degraded(
                    f"signal:{name}", signal.means, site=site, element=name)
            except Exception:
                pass

        # Only faults go on the permanent record. `info` signals are ordinary
        # traffic; journalling them would bury the ones that matter.
        if signal.severity in ("incident", "warning"):
            from . import drift_journal
            drift_journal.record_event(
                site, "site_signal", element=name,
                summary=f"{signal.severity}: {signal.means}",
                evidence={"kind": signal.kind, "severity": signal.severity,
                          "detail": detail, **(evidence or {})},
            )
        return True

    except Exception as exc:
        logger.debug(f"[site-signal] could not record {site}/{name}: {exc}")
        return False


def trip_report(site: str = "") -> Dict[str, Dict[str, Any]]:
    """What has tripped this run: ``{site/name: {count, means, severity}}``."""
    out: Dict[str, Dict[str, Any]] = {}
    with _LOCK:
        for (s, name), tally in _TRIPS.items():
            if site and s != site:
                continue
            signal = _REGISTRY.get(s, {}).get(name)
            out[f"{s}/{name}"] = {
                "count": tally.count,
                "severity": signal.severity if signal else "?",
                "kind": signal.kind if signal else "?",
                "means": signal.means if signal else "",
            }
    return out


def log_trip_report(reason: str = "") -> None:
    """Dump what tripped. Call at run end, beside the targeting report."""
    report = trip_report()
    if not report:
        return
    logger.info(f"[site-signal] report{f' ({reason})' if reason else ''}:")
    for key, row in sorted(report.items(),
                           key=lambda kv: (kv[1]["severity"] != "incident",
                                           -kv[1]["count"])):
        logger.info(f"[site-signal]   {key}: x{row['count']} "
                    f"[{row['severity']}] {row['means']}")


def reset() -> None:
    """Drop trip counts (not the registry). Tests, and a fresh run window."""
    with _LOCK:
        _TRIPS.clear()
