"""DOM-event payload extraction, compaction, and task-prompt injection.

This module owns the transformation:

    state  ──extract──▶  EventSnapshot  ──compact──▶  CompactItems
                                           │
                                           ▼
                                       inject text  ──▶  task_hint string
                                       (Triggering Event block + items)

Pure data transformations — no browser session, no LLM, no closures.
``state`` is the LangGraph state dict; everything else is plain values.

The four-path event-payload fallback chain (live monitor →
context.params.body → state.attributes.browser_event → state-root) is
implemented in :func:`extract_event_snapshot`.  Heavy DOM fields
(avatars, URLs) are stripped in :func:`compact_items`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from utils.logger_helper import logger_helper as logger


# ─────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────

@dataclass
class EventSnapshot:
    """One triggering-event payload, normalised across the four sources.

    ``source`` records which fallback path won (useful for debugging
    "why did the LLM see stale data?").  ``items`` is the raw
    DOM-extracted item list (NOT yet compacted) — pass through
    :func:`compact_items` before showing to the LLM.
    """

    event_type: str = ""              # browser_event | chat_message | timer | ...
    event_label: str = ""             # monitor label (e.g. "新消息")
    items: list[dict] = field(default_factory=list)
    source: str = ""                  # live_monitor[label] | context.params.body | state.attributes | state.root | (none)
    raw_event: dict | None = None     # the original event dict (if available)
    context: dict = field(default_factory=dict)

    @property
    def has_event(self) -> bool:
        return bool(self.event_type)

    @property
    def is_browser_event(self) -> bool:
        return self.event_type == "browser_event"


# ─────────────────────────────────────────────────────────────────────
# Extraction
# ─────────────────────────────────────────────────────────────────────

def extract_event_snapshot(state: dict | None) -> EventSnapshot:
    """Resolve the triggering-event payload from ``state``.

    Order of precedence:

    1. ``state["prompt_refs"]["events"]`` — the canonical resume payload
       written by ``pend_event_node``/``resume.py``.
    2. ``state["browser_event"]`` (top-level) or
       ``state["attributes"]["browser_event"]`` — fallback set when
       the resume code routed directly to ``state``.

    The ``items`` field is NOT yet populated here — call
    :func:`fetch_event_items` afterwards to apply the live-monitor
    fallback chain (it needs a different module).  This split lets
    callers extract the event metadata without paying the cost of
    walking ``_active_monitor_sets`` when they don't need items.
    """
    if not isinstance(state, dict):
        return EventSnapshot()

    snap = EventSnapshot()

    # Path 1: prompt_refs.events
    pr = state.get("prompt_refs")
    if isinstance(pr, dict):
        ev_json = pr.get("events", "")
        if isinstance(ev_json, str) and ev_json.strip():
            try:
                ev = json.loads(ev_json)
                if isinstance(ev, dict):
                    snap.raw_event = ev
                    snap.event_type = str(ev.get("event_type") or "")
                    ctx = ev.get("context")
                    if isinstance(ctx, dict):
                        snap.context = ctx
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

    # Path 2: state["browser_event"] / state["attributes"]["browser_event"]
    if not snap.event_type:
        be = state.get("browser_event")
        if not isinstance(be, dict):
            attrs = state.get("attributes") or {}
            be = attrs.get("browser_event") if isinstance(attrs, dict) else None
        if isinstance(be, dict) and be.get("type"):
            snap.raw_event = be
            snap.event_type = str(be.get("type") or "")
            snap.context = {}
            logger.info(
                f"[BrowserAutomation] event injection fallback: "
                f"prompt_refs.events was empty, using state browser_event "
                f"(type={snap.event_type}, sub_type={be.get('sub_type', '')})"
            )

    # Resolve label.  May appear in context.sub_type, context.label, or
    # at the top-level of the raw event under either name.
    if snap.event_type:
        snap.event_label = (
            snap.context.get("sub_type")
            or snap.context.get("label")
            or (snap.raw_event.get("sub_type") if snap.raw_event else "")
            or (snap.raw_event.get("label") if snap.raw_event else "")
            or ""
        )

    return snap


def fetch_event_items(snap: EventSnapshot, state: dict | None) -> list[dict]:
    """Populate ``snap.items`` (and return them) using a 4-path fallback.

    Tried in order:

    0. **Live monitor snapshot** — read ``last_items`` directly from
       ``event_monitor._active_monitor_sets`` (preferred — always
       freshest).  Picks a monitor whose label matches ``snap.event_label``
       when possible; otherwise any monitor with a non-empty
       ``last_items`` (label is often missing on chat_message-triggered
       runs).
    1. **context.params.body** — JSON string at
       ``snap.context["params"]["body"]`` containing ``{"items": [...]}``.
    2. **state.attributes.browser_event.body.items** — the resume
       payload's frozen DOM snapshot (stalest).
    3. **state.browser_event.body.items** — top-level resume payload
       variant.

    All four paths produce a ``list[dict]``; if every path is empty the
    list is empty and ``snap.source`` is left as ``"(none)"``.

    Mutates ``snap`` in place AND returns the items, so callers can use
    either pattern.
    """
    items: list[dict] = []
    source = "(none)"

    # ── Path 0: live monitor snapshot ──
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import (
            _active_monitor_sets as _ams,
        )

        live = None
        live_label = ""
        fallback_items: list[dict] | None = None
        fallback_label = ""
        for mset in _ams.values():
            for mon in getattr(mset, "monitors", []) or []:
                mcfg = getattr(mon, "config", None)
                mlabel = getattr(mcfg, "label", "") if mcfg else ""
                mstate = getattr(mon, "state", None)
                if not isinstance(mstate, dict):
                    continue
                cand = mstate.get("last_items") or []
                if not (isinstance(cand, list) and cand):
                    continue
                if snap.event_label and mlabel == snap.event_label:
                    live = list(cand)
                    live_label = mlabel
                    break
                if fallback_items is None:
                    fallback_items = list(cand)
                    fallback_label = mlabel
            if live:
                break
        if not live and fallback_items:
            live = fallback_items
            live_label = fallback_label or "(no-label)"
        if live:
            items = live
            source = f"live_monitor[{live_label}]"
    except Exception as exc:
        logger.debug(f"[BrowserAutomation] live monitor snapshot lookup failed: {exc}")

    # ── Path 1: context.params.body ──
    if not items:
        body = snap.context.get("params") if isinstance(snap.context, dict) else None
        if isinstance(body, dict):
            body_str = body.get("body", "")
            if isinstance(body_str, str) and body_str:
                try:
                    parsed = json.loads(body_str)
                    cand = parsed.get("items") or []
                    if isinstance(cand, list) and cand:
                        items = cand
                        source = "context.params.body"
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

    # ── Paths 2 & 3: state.[attributes.]browser_event.body.items ──
    if not items and isinstance(state, dict):
        be_data = state.get("browser_event")
        if not isinstance(be_data, dict):
            attrs = state.get("attributes") or {}
            be_data = attrs.get("browser_event") if isinstance(attrs, dict) else None
        if isinstance(be_data, dict):
            body = be_data.get("body")
            if isinstance(body, str) and body:
                try:
                    parsed = json.loads(body)
                    cand = parsed.get("items") or []
                    if isinstance(cand, list) and cand:
                        items = cand
                        source = "state.attributes.browser_event"
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            elif isinstance(body, dict):
                cand = body.get("items") or []
                if isinstance(cand, list) and cand:
                    items = cand
                    source = "state.browser_event"

    snap.items = items
    snap.source = source
    return items


# ─────────────────────────────────────────────────────────────────────
# Compaction
# ─────────────────────────────────────────────────────────────────────

# Fields stripped from each item before showing to the LLM.  These
# tend to be large (base64 avatars, lengthy URLs) and add no semantic
# signal for decisions.
_COMPACT_HEAVY_FIELDS = frozenset({
    "avatar", "avatar_url", "thumbnail", "icon", "image", "image_url",
    "url", "href", "src", "img_src",
    # lengthy structural blobs that occasionally appear from extractors
    "_raw_html", "_node", "_dom",
})


def compact_items(items: list[dict], *, max_field_chars: int = 500) -> list[dict]:
    """Strip heavy fields and clamp long strings for LLM consumption.

    Pure: input is not mutated.  Items that are not dicts are passed
    through unchanged (defensive — extractors sometimes emit strings).
    Long string fields are truncated with an ellipsis suffix.
    """
    out: list[dict] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            out.append(raw)
            continue
        compact: dict = {}
        for k, v in raw.items():
            if k in _COMPACT_HEAVY_FIELDS:
                continue
            if isinstance(v, str) and len(v) > max_field_chars:
                compact[k] = v[: max_field_chars - 1] + "…"
            else:
                compact[k] = v
        out.append(compact)
    return out


def filter_actionable(
    items: list[dict],
    actionable_field: str,
) -> list[dict]:
    """Return only items whose ``actionable_field`` value is non-empty.

    When ``actionable_field`` is empty, returns the input as-is.  Used
    to derive the "actionable_items" list that feeds the prompt-build
    hooks (e.g. a live-chat bundle's pending-reply filter).
    """
    if not actionable_field:
        return list(items or [])
    out: list[dict] = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        val = it.get(actionable_field)
        if val is None:
            continue
        if isinstance(val, str) and not val.strip():
            continue
        if isinstance(val, (list, dict)) and not val:
            continue
        out.append(it)
    return out


# ─────────────────────────────────────────────────────────────────────
# Task-prompt injection
# ─────────────────────────────────────────────────────────────────────

# The "CRITICAL RULES" paragraph appended to a browser_event task hint.
# Defeats the LLM's tendency to assume prior dispatches from stale DOM.
_BROWSER_EVENT_CRITICAL_RULES = (
    "**CRITICAL RULES FOR THIS INVOCATION:**\n"
    "1. Your memory from previous rounds has been WIPED. You have NO record of any prior dispatches.\n"
    "2. Do NOT infer dispatch status from the chat DOM. Previous agent replies visible in the chat thread "
    "are for OLDER messages, not the current one.\n"
    "3. If the snapshot below shows a customer with a message that looks like a question, you MUST dispatch "
    "it — even if you see prior agent replies in the DOM.\n"
    "4. The ONLY way a message counts as \"already dispatched\" is if YOU called bu_send_chat for that EXACT "
    "message text in THIS round. Seeing prior replies in the chat is NOT evidence of dispatch."
)


def render_triggering_event_block(snap: EventSnapshot) -> str:
    """Compose the "## Triggering Event" markdown block for the task.

    Returns ``""`` when ``snap.event_type`` is empty (no event to
    inject).  When the event is a ``browser_event``, appends the
    CRITICAL RULES paragraph.
    """
    if not snap.event_type:
        return ""

    lines = [
        "## Triggering Event",
        f"This invocation was resumed by a **{snap.event_type}** event.",
    ]
    if snap.event_label:
        lines.append(f"Event label: **{snap.event_label}**")

    if snap.event_type == "browser_event":
        msg_hint = (
            "The DOM monitor detected a change in the watched region"
            + (f" (label: {snap.event_label})" if snap.event_label else "")
            + ". A new item or state change has occurred.\n\n"
            + _BROWSER_EVENT_CRITICAL_RULES
        )
        lines.append("")
        lines.append(msg_hint)

    return "\n".join(lines)


def render_items_snapshot_block(
    compact: list[dict],
    *,
    actionable: list[dict] | None = None,
    actionable_field: str = "",
) -> str:
    """Compose a markdown block listing the (compacted) DOM items.

    When both an actionable filter and the raw list are provided, the
    actionable list is rendered as the primary "must-process" section
    and the raw list as a smaller context section.  Otherwise the
    full compacted list is rendered.
    """
    if not compact and not actionable:
        return ""

    lines = ["## Current DOM Snapshot"]

    if actionable_field and actionable is not None:
        lines.append("")
        lines.append(
            f"### Actionable items (filter: `{actionable_field}` non-empty)"
        )
        lines.append(
            "**You MUST process every entry below this round.**  This list is "
            "ground truth — do not claim an item is already handled unless YOU "
            "personally dispatched it during the current round."
        )
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(actionable, ensure_ascii=False, indent=2))
        lines.append("```")
        if compact and len(compact) != len(actionable):
            lines.append("")
            lines.append("### All items (context only)")
            lines.append("```json")
            lines.append(json.dumps(compact, ensure_ascii=False, indent=2))
            lines.append("```")
    else:
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(compact, ensure_ascii=False, indent=2))
        lines.append("```")

    return "\n".join(lines)
