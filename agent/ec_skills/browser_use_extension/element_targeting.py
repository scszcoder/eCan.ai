"""How an element is named, and which naming actually worked.

Platform-side and deliberately business-free: no site, no selector, no DOM.
Sites describe their own elements and report which strategy resolved them;
this module owns the vocabulary and the bookkeeping.

Why it exists
-------------
A stored selector is a bet that the site will not change. We keep losing that
bet -- ws189, ws193, mt062/063 and the June sidebar redesign were all the same
failure, and each was repaired by hand, days after a customer noticed.

Two independent projects converged on the same answer (see
``docs/SELF_HEALING_ROADMAP.md``): **the durable identifier is what a human
would say, not what the DOM says.** ``TargetDescriptor`` is that vocabulary --
visible text plus enough context to disambiguate -- and it is deliberately the
same shape both of them landed on, so their findings transfer.

What this module does NOT do (yet)
----------------------------------
Phase 1 is measurement only. Nothing here resolves an element, and no caller's
behaviour changes. Sites keep resolving exactly as they do today and simply say
which of their strategies won. A week of that tells us whether semantic naming
actually holds up on a given site -- before anything is built on the assumption
that it does.

Phases 2 (resolve from a live element table) and 3 (persist what was resolved)
are specified in the roadmap and both consume this vocabulary.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

# Keep a rollup this size at most. Resolutions happen per element per poll, so
# an unbounded counter map on a long-lived session would be a slow leak.
_MAX_TRACKED_KEYS = 512

# Emit a rollup no more often than this. Per-resolution logging would drown the
# run log; the point is the distribution, not each event.
_ROLLUP_INTERVAL_S = 300.0


@dataclass(frozen=True)
class TargetDescriptor:
    """How a human would point at an element.

    Mirrors the schema ``workflow-use`` arrived at after deprecating its own
    ``cssSelector`` / ``xpath`` / ``elementHash`` fields. Kept identical on
    purpose: their field semantics are field-tested, and staying compatible
    means their examples read directly onto ours.

    ``selector_fallbacks`` is where a CSS/XPath expression may still live --
    ordered, lowest priority, and explicitly a fallback rather than the
    identity of the element.
    """

    # PRIMARY: visible or accessible text. Disambiguate inline the way a person
    # would -- "Send (in the reply box)", "Edit (item 2 of 3)".
    target_text: str = ""

    # Context hints, stored as TEXT, never as selectors.
    container_hint: str = ""        # "Personal Information", "conversation list"
    position_hint: str = ""         # "item 2 of 3", "first", "last"
    role: str = ""                  # button, textbox, link, listitem...
    interaction_hint: str = ""      # form_submit, navigation, table_action

    # LAST RESORT, ordered. Present so a site can migrate incrementally rather
    # than in one cut-over.
    selector_fallbacks: tuple = ()

    def is_semantic(self) -> bool:
        """True when this names the element by meaning rather than structure."""
        return bool(self.target_text or self.container_hint or self.position_hint)

    def is_fragile(self) -> tuple:
        """``(fragile, why)`` -- does this name the element only by WHERE it is?

        A descriptor with neither visible text nor a container says nothing
        about what the element *is*, only where it sits, and where moves.
        ``position_hint="item 2 of 3"`` is the clearest case: it works until
        that customer has a fourth conversation, and then it silently points at
        the wrong row. Each cycle looks like a success locally -- heal, break,
        heal, break -- so nothing ever flags it.

        This is about the descriptor's *form*, not its track record. A fragile
        descriptor that has worked twenty times is still fragile; it has just
        not met the page that breaks it yet.
        """
        if self.target_text or self.container_hint:
            return False, ""
        if self.position_hint:
            return True, ("names only a position, so it breaks when the "
                          "collection changes size or order")
        return True, "no semantic anchor at all"

    def describe(self) -> str:
        """Short human-readable form, for logs and failure messages."""
        bits = [b for b in (self.target_text, self.container_hint,
                            self.position_hint, self.role) if b]
        return " | ".join(bits) or "(no semantic descriptor)"


@dataclass
class _Counter:
    ok: int = 0
    miss: int = 0

    def total(self) -> int:
        return self.ok + self.miss


@dataclass
class _Bucket:
    """Per (site, element) strategy tallies."""
    strategies: Dict[str, _Counter] = field(default_factory=dict)
    first_seen: float = field(default_factory=time.time)
    last_logged: float = 0.0


_LOCK = threading.Lock()
_BUCKETS: Dict[tuple, _Bucket] = {}


def record_resolution(
    site: str,
    element: str,
    strategy: str,
    ok: bool = True,
    *,
    descriptor: Optional[TargetDescriptor] = None,
    detail: str = "",
) -> None:
    """Note that *strategy* was the one that resolved *element* on *site*.

    Call this wherever an element is located today, with whatever names the
    site already uses. Cheap, thread-safe, and never raises -- instrumentation
    must not be able to break the path it measures.

    Args:
        site: free-form owner label chosen by the calling bundle. Platform code
            never interprets it.
        element: what was being located ("sidebar_row_name", "send_button").
        strategy: which approach won ("semantic_text", "data_qa_id",
            "legacy_hashed_class", "none"). The names are the site's own.
        ok: False when this strategy was tried and did not resolve.
        descriptor: the semantic descriptor, when the site has one. Recorded
            for Phase 3; unused today beyond the log line.
        detail: short free text for the rollup log.
    """
    try:
        key = (str(site or "?"), str(element or "?"))
        strat = str(strategy or "unknown")
        now = time.time()
        emit = None

        with _LOCK:
            if key not in _BUCKETS and len(_BUCKETS) >= _MAX_TRACKED_KEYS:
                return                      # full: drop rather than grow
            bucket = _BUCKETS.setdefault(key, _Bucket())
            counter = bucket.strategies.setdefault(strat, _Counter())
            if ok:
                counter.ok += 1
            else:
                counter.miss += 1

            if now - bucket.last_logged >= _ROLLUP_INTERVAL_S:
                bucket.last_logged = now
                emit = (key, _format_bucket(bucket))

        if emit:
            (site_name, element_name), summary = emit
            logger.info(
                f"[element-targeting] {site_name}/{element_name}: {summary}"
                + (f" | {detail}" if detail else "")
            )
    except Exception:
        # Never let measurement break the thing being measured.
        pass


def _format_bucket(bucket: _Bucket) -> str:
    """'data_qa_id=412/412 ok, legacy_hashed_class=3/9 ok' — busiest first."""
    parts = []
    for name, counter in sorted(
        bucket.strategies.items(), key=lambda kv: kv[1].total(), reverse=True
    ):
        parts.append(f"{name}={counter.ok}/{counter.total()} ok")
    return ", ".join(parts) or "(nothing recorded)"


def resolution_report() -> Dict[str, Dict[str, Dict[str, int]]]:
    """Everything recorded so far, as plain dicts.

    Shape: ``{site: {element: {strategy: {"ok": n, "miss": n}}}}``. For the log
    analyser and for answering the Phase 1 question: is the semantic strategy
    carrying the load, or are the brittle ones still doing the work?
    """
    out: Dict[str, Dict[str, Dict[str, int]]] = {}
    with _LOCK:
        for (site, element), bucket in _BUCKETS.items():
            per_element = out.setdefault(site, {}).setdefault(element, {})
            for name, counter in bucket.strategies.items():
                per_element[name] = {"ok": counter.ok, "miss": counter.miss}
    return out


def log_resolution_report(reason: str = "") -> None:
    """Dump the whole report at INFO. Call at run end or on a drift signal."""
    report = resolution_report()
    if not report:
        return
    logger.info(f"[element-targeting] report{f' ({reason})' if reason else ''}:")
    for site, elements in sorted(report.items()):
        for element, strategies in sorted(elements.items()):
            busiest = sorted(strategies.items(),
                             key=lambda kv: kv[1]["ok"] + kv[1]["miss"],
                             reverse=True)
            summary = ", ".join(
                f"{n}={c['ok']}/{c['ok'] + c['miss']} ok" for n, c in busiest
            )
            logger.info(f"[element-targeting]   {site}/{element}: {summary}")


def reset() -> None:
    """Drop all counters. Tests, and a fresh window after a site redesign."""
    with _LOCK:
        _BUCKETS.clear()


def record_from_js_tally(
    site: str,
    element: str,
    tally: Any,
    *,
    detail: str = "",
) -> int:
    """Record a ``{strategy: count}`` map produced in the page.

    Site JS that resolves many elements in one pass (a sidebar scan, a results
    table) should tally per strategy in-page and hand the map over, rather than
    calling back per element. Returns how many resolutions were recorded.

    Tolerant by design: a malformed tally from a page we do not control must
    not raise into the caller.
    """
    if not isinstance(tally, dict):
        return 0
    recorded = 0
    for strategy, count in tally.items():
        try:
            n = int(count)
        except (TypeError, ValueError):
            continue
        if n <= 0:
            continue
        # One aggregate call rather than n calls: same counters, less lock churn.
        _record_bulk(site, element, str(strategy), n, detail=detail)
        recorded += n
    return recorded


def _record_bulk(site: str, element: str, strategy: str, count: int,
                 *, detail: str = "") -> None:
    try:
        key = (str(site or "?"), str(element or "?"))
        now = time.time()
        emit = None
        with _LOCK:
            if key not in _BUCKETS and len(_BUCKETS) >= _MAX_TRACKED_KEYS:
                return
            bucket = _BUCKETS.setdefault(key, _Bucket())
            counter = bucket.strategies.setdefault(str(strategy), _Counter())
            counter.ok += count
            if now - bucket.last_logged >= _ROLLUP_INTERVAL_S:
                bucket.last_logged = now
                emit = (key, _format_bucket(bucket))
        if emit:
            (site_name, element_name), summary = emit
            logger.info(
                f"[element-targeting] {site_name}/{element_name}: {summary}"
                + (f" | {detail}" if detail else "")
            )
    except Exception:
        pass


# ── change detection ───────────────────────────────────────────────────────
#
# You cannot schedule the event this whole design exists for. A site ships a
# redesign when it suits them -- twice in two months, with no notice -- so an
# evidence plan that depends on someone watching during the right week is not
# a plan.
#
# But a redesign has a signature: the strategy that was resolving almost every
# element stops resolving any. That shows up on the FIRST scan after the change,
# which is typically long before a customer notices anything. The counters are
# already there; this just reads them.

# A strategy has to have been doing real work before its collapse means
# anything. Below this, a run of misses is just noise.
_DRIFT_MIN_BASELINE = 20

# What counts as "was carrying the load".
_DRIFT_DOMINANT_SHARE = 0.6


@dataclass
class DriftSignal:
    site: str
    element: str
    strategy: str          # the one that collapsed
    baseline_share: float  # how much of the work it used to do
    recent_ok: int
    recent_total: int

    def describe(self) -> str:
        return (
            f"{self.site}/{self.element}: '{self.strategy}' was resolving "
            f"{self.baseline_share:.0%} of elements and now resolves "
            f"{self.recent_ok}/{self.recent_total}"
        )


def detect_drift(baseline: Optional[Dict[str, Any]] = None) -> list:
    """Strategies that used to carry an element and have stopped.

    Compares a *baseline* report (from a known-good period, e.g. persisted at
    the end of a healthy run) against what is being seen now. Returns a list of
    :class:`DriftSignal`.

    This is a smoke alarm, not a diagnosis: a collapse can also mean the page
    simply did not render, or the session landed somewhere unexpected. It says
    "look now", which is the part currently missing -- today the first signal
    is a customer complaining days later.
    """
    if not baseline:
        return []

    signals = []
    current = resolution_report()
    for site, elements in (baseline or {}).items():
        for element, strategies in (elements or {}).items():
            total_before = sum(
                (c.get("ok", 0) + c.get("miss", 0)) for c in strategies.values()
            )
            if total_before < _DRIFT_MIN_BASELINE:
                continue

            now = current.get(site, {}).get(element, {})
            total_now = sum((c.get("ok", 0) + c.get("miss", 0)) for c in now.values())
            if total_now == 0:
                continue        # nothing observed yet; not evidence of anything

            for strategy, counts in strategies.items():
                was = counts.get("ok", 0) / total_before if total_before else 0.0
                if was < _DRIFT_DOMINANT_SHARE:
                    continue
                recent = now.get(strategy, {})
                recent_ok = recent.get("ok", 0)
                if recent_ok == 0:
                    signals.append(DriftSignal(
                        site=site, element=element, strategy=strategy,
                        baseline_share=was, recent_ok=recent_ok,
                        recent_total=total_now,
                    ))
    return signals


def log_drift(
    baseline: Optional[Dict[str, Any]] = None,
    *,
    evidence: Optional[Dict[str, Any]] = None,
) -> list:
    """Check for drift, say so loudly, and put it on the permanent record.

    Two outputs, for two different readers. The warning goes to the run log,
    for whoever is watching today. The journal entry goes to
    ``drift_journal``, for whoever asks in two years what the site looked like
    the last time it moved -- by which time this run's log is long gone.

    Args:
        baseline: a report from a known-good period.
        evidence: anything else the caller can add about the moment -- a DOM
            structure sample, a websocket payload's field names. Optional, and
            shape-summarised before it is stored; see :mod:`drift_journal`.

    Returns the signals.
    """
    signals = detect_drift(baseline)
    for signal in signals:
        logger.warning(
            f"[element-targeting] POSSIBLE SITE CHANGE — {signal.describe()}. "
            f"A parser that was carrying this element has stopped resolving it."
        )
        _journal_drift(signal, baseline, evidence)
        # A parser that was carrying an element and now resolves nothing is a
        # degradation the operator should see, not just a log line.
        try:
            from . import degraded_state
            degraded_state.mark_degraded(
                "parser_collapse",
                f"'{signal.strategy}' stopped resolving",
                site=signal.site, element=signal.element)
        except Exception:
            pass
    return signals


def _journal_drift(signal: "DriftSignal", baseline, extra) -> None:
    """Write one drift signal to the permanent record. Never raises."""
    try:
        from . import drift_journal

        was = (baseline or {}).get(signal.site, {}).get(signal.element, {})
        now = resolution_report().get(signal.site, {}).get(signal.element, {})

        # Strategy names and counts are our own vocabulary and integers -- no
        # page content -- so they are recorded verbatim. Anything the caller
        # attached goes through the journal's shape summariser instead.
        drift_journal.record_event(
            signal.site,
            "strategy_collapse",
            element=signal.element,
            summary=signal.describe(),
            evidence={
                "collapsed_strategy": signal.strategy,
                "baseline_share": round(signal.baseline_share, 4),
                "strategies_before": was,
                "strategies_after": now,
            },
            raw_ok=True,
        )
        if extra:
            drift_journal.record_event(
                signal.site,
                "strategy_collapse_context",
                element=signal.element,
                summary=f"page evidence at {signal.describe()}",
                evidence=extra,          # shape-summarised, not verbatim
            )
    except Exception:
        pass
