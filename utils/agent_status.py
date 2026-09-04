"""Per-agent readiness ledger: ``[AGENT-STATUS]`` structured records + snapshot.

The questions an operator asks when an agent "does nothing" are STATE, not
events: is a Chrome attached (existing or auto-started)? does the site tab
exist? is the DOM monitor running and what did it last see? which detection
path owns dispatch? This module keeps one small dict per agent, emits a JSON
log line whenever a value changes (and at least every ``HEARTBEAT_S`` on
activity), and serves the latest snapshot to the Agents page.

Keys (all optional, string/number values; unknown keys are allowed):

    chrome            attached_existing | auto_started | unreachable
    chrome_port       CDP port
    site_tab          found | missing
    site_tab_url      matched URL (truncated)
    monitor           running | stopped
    monitor_label     monitor label (e.g. 新消息)
    monitor_hb        last heartbeat status: ok | empty | no_match | page_mismatch | cdp_error
    dom_roots         roots found by the extractor
    dom_items         items found by the extractor
    dom_last_items_at ISO time of the last non-empty scrape
    detection         ws | dom
    updated_at        ISO time of the last change

Attribution: the agent comes from the active log scope (see ``utils.log_scope``)
unless ``agent_id`` is passed explicitly. Reports with no attributable agent
land under ``"_unscoped"`` so nothing is lost.

The Feige-specific *values* (which URL is "the site tab") come from the caller;
this module is platform-general (any site-monitoring agent has a browser, a
tab, a monitor, DOM targets, and a detection path).
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from utils.logger_helper import logger_helper as logger
from utils.log_scope import get_scope

HEARTBEAT_S = 60.0
UNSCOPED = "_unscoped"

_lock = threading.Lock()
_status: Dict[str, Dict[str, Any]] = {}
_last_emit: Dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _agent_key(agent_id: Optional[str]) -> str:
    if agent_id:
        return str(agent_id)
    sc = get_scope()
    return str(sc.get("agent_id") or sc.get("agent_name") or UNSCOPED)


def report(agent_id: Optional[str] = None, **fields: Any) -> Dict[str, Any]:
    """Merge *fields* into the agent's readiness dict. Emits a ``[AGENT-STATUS]``
    line when anything changed, or when the last emit is older than
    ``HEARTBEAT_S`` (so a periodic caller such as the monitor heartbeat gives a
    steady pulse). Never raises."""
    try:
        key = _agent_key(agent_id)
        clean = {k: v for k, v in fields.items() if v is not None}
        now = time.monotonic()
        with _lock:
            cur = _status.setdefault(key, {})
            changed = any(cur.get(k) != v for k, v in clean.items())
            if changed:
                cur.update(clean)
                cur["updated_at"] = _now_iso()
            due = (now - _last_emit.get(key, 0.0)) >= HEARTBEAT_S
            snap = dict(cur)
            if changed or due:
                _last_emit[key] = now
                emit = True
            else:
                emit = False
        if emit:
            sc = get_scope()
            payload = {"agent_id": key, "agent_name": sc.get("agent_name"), **snap}
            logger.info("[AGENT-STATUS] " + json.dumps(payload, ensure_ascii=False, default=str))
        return snap
    except Exception as e:  # observability must never break run logic
        try:
            logger.debug(f"[AGENT-STATUS] report failed: {e}")
        except Exception:
            pass
        return {}


def snapshot(agent_id: str) -> Dict[str, Any]:
    with _lock:
        return dict(_status.get(str(agent_id), {}))


def snapshot_all() -> Dict[str, Dict[str, Any]]:
    with _lock:
        return {k: dict(v) for k, v in _status.items()}


def clear(agent_id: Optional[str] = None) -> None:
    """Drop one agent's readiness (or everything) — used by tests and on stop."""
    with _lock:
        if agent_id is None:
            _status.clear()
            _last_emit.clear()
        else:
            _status.pop(str(agent_id), None)
            _last_emit.pop(str(agent_id), None)
