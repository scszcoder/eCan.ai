"""
Browser Event Monitor — auto-starts CDP-based event capture sidecars
from browser_automation node editor config.

Each monitor config in ``inputsValues.eventMonitors.content`` describes a
capture rule (HTTP polling, WebSocket, SSE, DOM mutation, or raw CDP).
When a match fires, the monitor bridges the event into the same
``sync_task_wait_in_line("browser_event", ...)`` dispatch path used by
``BrowserEventService``, so downstream ``pend_event`` nodes configured
with a matching ``browserEventLabel`` resume automatically.

Lifecycle:
    1. ``parse_monitor_configs(inputs)`` extracts and validates configs.
    2. ``start_monitors(session, configs)`` creates capture instances.
    3. ``stop_monitors(monitor_set)`` tears them down.

Only HTTP-polling, DOM mutation, WebSocket, and SSE are implemented in Phase 1.  CDP raw monitors will follow the same bridge pattern in Phase 6.
"""
from __future__ import annotations

import json
import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger
from agent.ec_skills.browser_use_extension.event_monitor_capability import (
    clear_attached_monitor_set,
    get_attached_monitor_set,
    get_event_monitor_capability,
    set_attached_monitor_set,
)
from agent.ec_skills.browser_use_extension.event_models import NormalizedBrowserEvent


# Global registry of active monitor sets keyed by monitor_set_id
# Used for cleanup when sessions close or runners shut down
_active_monitor_sets: Dict[str, ActiveMonitorSet] = {}
_session_start_locks: Dict[int, asyncio.Lock] = {}


def register_monitor_set(monitor_set: ActiveMonitorSet) -> None:
    """Register an active monitor set in the global registry."""
    global _active_monitor_sets
    _active_monitor_sets[monitor_set.monitor_set_id] = monitor_set
    logger.debug(f"[EventMonitor] Registered monitor set {monitor_set.monitor_set_id} in global registry")


def unregister_monitor_set(monitor_set_id: str) -> None:
    """Unregister a monitor set from the global registry."""
    global _active_monitor_sets
    if monitor_set_id in _active_monitor_sets:
        del _active_monitor_sets[monitor_set_id]
        logger.debug(f"[EventMonitor] Unregistered monitor set {monitor_set_id} from global registry")


async def cleanup_all_monitors() -> None:
    """Stop all active monitors in the global registry.
    
    Called when the runner shuts down or when explicitly cleaning up resources.
    """
    global _active_monitor_sets
    monitor_sets = list(_active_monitor_sets.values())
    if not monitor_sets:
        return
    
    logger.info(f"[EventMonitor] Cleaning up {len(monitor_sets)} active monitor set(s)")
    for monitor_set in monitor_sets:
        try:
            await stop_monitors(monitor_set, session=None)
        except Exception as e:
            logger.debug(f"[EventMonitor] Error during cleanup of monitor set {monitor_set.monitor_set_id}: {e}")
    
    _active_monitor_sets.clear()
    logger.info("[EventMonitor] All monitor sets cleaned up")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class EventMonitorConfig:
    """One event-capture rule from the node editor."""

    id: str = ""
    label: str = ""
    enabled: bool = True
    source_type: str = "http_polling"  # http_polling | websocket | sse | dom_mutation | cdp_raw

    # Common
    url_patterns: List[str] = field(default_factory=list)

    # HTTP Polling
    methods: List[str] = field(default_factory=lambda: ["GET", "POST"])
    content_filters: List[str] = field(default_factory=list)  # substring matches
    min_body_length: int = 10

    # WebSocket
    frame_direction: str = "incoming"  # incoming | outgoing | both

    # SSE
    sse_event_types: List[str] = field(default_factory=list)

    # DOM Mutation
    dom_selector: str = ""
    dom_attributes: bool = False
    dom_child_list: bool = True
    dom_subtree: bool = True
    dom_check_interval_ms: int = 250

    # CDP Raw
    cdp_domain: str = ""
    cdp_event_method: str = ""
    cdp_filter_expr: str = ""


def _safe_json_loads(raw: Any) -> Any:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _default_dom_extractor_config(cfg: EventMonitorConfig) -> Dict[str, Any]:
    selectors = [s.strip() for s in (cfg.dom_selector or "").split(",") if s and s.strip()]
    for fallback_selector in (
        "#stat-sessions",
        "#customer-list",
        ".customer-item",
        ".session-row",
        'a[href*="/chat?session="]',
        'a[href*="chat?session="]',
    ):
        if fallback_selector not in selectors:
            selectors.append(fallback_selector)

    page_patterns = [p for p in cfg.url_patterns if isinstance(p, str) and p.strip()]
    if not page_patterns:
        page_patterns = ["/control"]

    return {
        "version": 1,
        "page_url_patterns": page_patterns,
        "roots": selectors or ["body"],
        "items": [
            {
                "selector": 'a[href*="/chat?session="], a[href*="chat?session="]',
                "fields": {
                    "session": {
                        "source": "attr",
                        "attr": "href",
                        "regex": r"[?&]session=([^&]+)",
                        "group": 1,
                    },
                    "chatUrl": {"source": "attr", "attr": "href"},
                    "name": {
                        "source": "closest_text",
                        "closest": ".customer-card, .customer-item, .session-row, li, tr, div",
                        "regex": r"Customer\s*:?\s*([A-Za-z0-9_\-]+)",
                        "group": 1,
                        "fallback": [
                            {
                                "source": "closest_text",
                                "closest": ".customer-card, .customer-item, .session-row, li, tr, div",
                                "split_before": " Session",
                            },
                            {"source": "text"},
                        ],
                    },
                },
            }
        ],
        "key_field": "session",
        "identity": {
            "key_fields": ["session"],
        },
        "empty_text_patterns": ["no customers", "no active customers", "no customers yet"],
        "emit_on": "added",
    }


def _resolve_dom_extractor_config(cfg: EventMonitorConfig) -> Dict[str, Any]:
    advanced = _safe_json_loads(cfg.cdp_filter_expr)
    if isinstance(advanced, dict):
        merged = _default_dom_extractor_config(cfg)
        merged.update({k: v for k, v in advanced.items() if v is not None})

        # If a saved extractor provides an explicit key_field, it must override any
        # default identity config inherited from the control-page extractor.
        explicit_key_field = str(advanced.get("key_field") or merged.get("key_field") or "").strip()
        if explicit_key_field:
            merged["key_field"] = explicit_key_field
            merged["identity"] = {"key_fields": [explicit_key_field]}

        # Support shorthand extractor configs saved by the skill editor, e.g.
        # {page_url_patterns, roots, item_selector, fields, key_field, filters}.
        item_selector = str(advanced.get("item_selector") or merged.get("item_selector") or "").strip()
        raw_fields = advanced.get("fields") if isinstance(advanced.get("fields"), dict) else (
            merged.get("fields") if isinstance(merged.get("fields"), dict) else {}
        )
        if item_selector and raw_fields:
            normalized_fields = {}
            for field_name, spec in raw_fields.items():
                if not isinstance(spec, dict):
                    continue
                normalized = dict(spec)
                if normalized.get("text") is True:
                    normalized.pop("text", None)
                    normalized.setdefault("source", "text")
                elif normalized.get("attr") and not normalized.get("source"):
                    normalized.setdefault("source", "attr")
                elif not normalized.get("source"):
                    normalized.setdefault("source", "text")
                normalized_fields[str(field_name)] = normalized
            if normalized_fields:
                merged["items"] = [{
                    "selector": item_selector,
                    "fields": normalized_fields,
                }]

        # Defensively normalize any merged item field specs as well.
        normalized_items = []
        for item in (merged.get("items") or []):
            if not isinstance(item, dict):
                continue
            normalized_item = dict(item)
            fields = item.get("fields") if isinstance(item.get("fields"), dict) else {}
            normalized_fields = {}
            for field_name, spec in fields.items():
                if not isinstance(spec, dict):
                    continue
                normalized = dict(spec)
                if normalized.get("text") is True:
                    normalized.pop("text", None)
                    normalized.setdefault("source", "text")
                elif normalized.get("attr") and not normalized.get("source"):
                    normalized.setdefault("source", "attr")
                elif not normalized.get("source"):
                    normalized.setdefault("source", "text")
                normalized_fields[str(field_name)] = normalized
            if normalized_fields:
                normalized_item["fields"] = normalized_fields
            normalized_items.append(normalized_item)
        if normalized_items:
            merged["items"] = normalized_items

        # Some older saved monitor payloads omitted identity overrides even though
        # they set key_field=msg_id. Reassert the effective identity after item merge.
        effective_key_field = str(merged.get("key_field") or "").strip()
        if effective_key_field:
            identity_cfg = merged.get("identity")
            if not isinstance(identity_cfg, dict):
                identity_cfg = {}
            identity_cfg["key_fields"] = [effective_key_field]
            merged["identity"] = identity_cfg

        return merged


def _normalize_url_for_monitor(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = raw.lower()
    if normalized.startswith("http://"):
        normalized = normalized[7:]
    elif normalized.startswith("https://"):
        normalized = normalized[8:]
    return normalized.rstrip("/")


def _monitor_url_matches(actual_url: str, pattern: str) -> bool:
    actual = _normalize_url_for_monitor(actual_url)
    wanted = _normalize_url_for_monitor(pattern)
    if not actual or not wanted:
        return False
    return wanted in actual


async def _ensure_monitor_cdp_ready(session: Any, mutation_state: Dict[str, Any], label: str) -> bool:
    """Best-effort ensure the BrowserSession has an initialized root CDP client."""
    try:
        cdp_root = getattr(session, "_cdp_client_root", None)
        session_manager = getattr(session, "session_manager", None)
        if cdp_root is not None and session_manager is not None:
            return True

        now = time.time()
        last_attempt = float(mutation_state.get("_cdp_ready_last_attempt", 0.0) or 0.0)
        if now - last_attempt < 1.0:
            return False
        mutation_state["_cdp_ready_last_attempt"] = now

        logger.info(
            f"[EventMonitor] CDP not ready for monitor '{label}', attempting BrowserSession.start() "
            f"(root={cdp_root is not None}, session_manager={session_manager is not None})"
        )
        if hasattr(session, "start"):
            await session.start()

        cdp_root = getattr(session, "_cdp_client_root", None)
        session_manager = getattr(session, "session_manager", None)
        ready = cdp_root is not None and session_manager is not None
        if ready:
            logger.info(f"[EventMonitor] CDP became ready for monitor '{label}'")
        return ready
    except Exception as exc:
        logger.debug(f"[EventMonitor] ensure_monitor_cdp_ready failed for '{label}': {exc}")
        return False


def _resolve_monitor_target_id(session: Any, cfg: EventMonitorConfig, extractor_cfg: Dict[str, Any]) -> str:
    """Resolve a stable target_id for a monitor.

    Prefer the session's current focused page target. If it does not match the
    monitor's page patterns, search all known page/tab targets for a matching URL.
    """
    try:
        sm = getattr(session, "session_manager", None)
        if sm is None:
            return str(getattr(session, "agent_focus_target_id", "") or "")

        patterns = [p for p in (extractor_cfg.get("page_url_patterns") or []) if isinstance(p, str) and p.strip()]
        focus_target_id = str(getattr(session, "agent_focus_target_id", "") or "")
        all_targets = sm.get_all_targets() or {}

        def _matches_target_url(target: Any) -> bool:
            target_url = str(getattr(target, "url", "") or "")
            if not patterns:
                return True
            return any(_monitor_url_matches(target_url, pat) for pat in patterns)

        if focus_target_id:
            focus_target = sm.get_target(focus_target_id)
            if focus_target and getattr(focus_target, "target_type", "") in ("page", "tab") and _matches_target_url(focus_target):
                return focus_target_id

        for tid, target in all_targets.items():
            if getattr(target, "target_type", "") not in ("page", "tab"):
                continue
            if _matches_target_url(target):
                return str(tid)

        return focus_target_id
    except Exception:
        return str(getattr(session, "agent_focus_target_id", "") or "")
    return _default_dom_extractor_config(cfg)


def _build_dom_runtime_expression(extractor_cfg: Dict[str, Any]) -> str:
    cfg_json = json.dumps(extractor_cfg)
    return f"""
        (async function() {{
            const cfg = {cfg_json};
            const currentUrl = String((window && window.location && window.location.href) || '');

            function normalizeText(value) {{
                return String(value || '').replace(/\\s+/g, ' ').trim();
            }}

            function normalizePattern(value) {{
                const raw = String(value || '').trim();
                if (!raw) return '';
                try {{
                    const parsed = new URL(raw, currentUrl || window.location.origin);
                    return `${{parsed.pathname || ''}}${{parsed.search || ''}}${{parsed.hash || ''}}` || raw;
                }} catch (e) {{
                    return raw;
                }}
            }}

            function queryAllWithin(root, selector) {{
                if (!selector) return [];
                try {{
                    return Array.from((root || document).querySelectorAll(selector));
                }} catch (e) {{
                    return [];
                }}
            }}

            function readField(spec, el, root) {{
                if (!spec || typeof spec !== 'object') return '';
                const source = spec.source || 'text';
                const selector = spec.selector || '';
                const target = selector ? ((el && el.querySelector) ? el.querySelector(selector) : null) : el;
                let raw = '';

                if (source === 'literal') {{
                    raw = spec.value || '';
                }} else if (source === 'attr') {{
                    const attrTarget = target || el;
                    raw = attrTarget && attrTarget.getAttribute ? (attrTarget.getAttribute(spec.attr || 'href') || '') : '';
                }} else if (source === 'closest_text') {{
                    const closestBase = el && el.closest && spec.closest ? el.closest(spec.closest) : null;
                    raw = normalizeText((closestBase && closestBase.textContent) || (el && el.textContent) || '');
                }} else if (source === 'root_text') {{
                    raw = normalizeText((root && root.textContent) || '');
                }} else {{
                    raw = normalizeText((target && target.textContent) || '');
                }}

                if (spec.regex) {{
                    try {{
                        const match = String(raw || '').match(new RegExp(spec.regex, spec.flags || 'i'));
                        raw = match ? (match[spec.group || 1] || match[0] || '') : '';
                    }} catch (e) {{}}
                }}
                if (!raw && Array.isArray(spec.fallback)) {{
                    for (const fb of spec.fallback) {{
                        raw = readField(fb, el, root);
                        if (raw) break;
                    }}
                }}
                if (spec.split_before && raw) {{
                    raw = String(raw).split(spec.split_before)[0] || raw;
                }}
                return normalizeText(raw);
            }}

            const pagePatterns = Array.isArray(cfg.page_url_patterns) ? cfg.page_url_patterns : [];
            if (pagePatterns.length > 0) {{
                let currentPath = currentUrl;
                try {{
                    const parsedCurrent = new URL(currentUrl);
                    currentPath = `${{parsedCurrent.pathname || ''}}${{parsedCurrent.search || ''}}${{parsedCurrent.hash || ''}}` || currentUrl;
                }} catch (e) {{}}
                const pageOk = pagePatterns.some(p => {{
                    const rawPattern = String(p || '').trim();
                    const normalizedPattern = normalizePattern(rawPattern);
                    if (!rawPattern && !normalizedPattern) return false;
                    return (
                        (rawPattern && currentUrl.includes(rawPattern)) ||
                        (normalizedPattern && currentUrl.includes(normalizedPattern)) ||
                        (rawPattern && currentPath.includes(rawPattern)) ||
                        (normalizedPattern && currentPath.includes(normalizedPattern)) ||
                        (rawPattern && rawPattern.includes(currentPath)) ||
                        (normalizedPattern && normalizedPattern.includes(currentPath))
                    );
                }});
                if (!pageOk) {{
                    return JSON.stringify({{status: 'page_mismatch', currentUrl}});
                }}
            }}

            if (cfg.state_fetch && typeof cfg.state_fetch === 'object') {{
                try {{
                    const stateUrl = String(cfg.state_fetch.url || '').trim();
                    const adapter = String(cfg.state_fetch.adapter || '').trim();
                    if (stateUrl && adapter) {{
                        const resp = await fetch(stateUrl, {{ credentials: 'include' }});
                        const data = await resp.json();
                        if (adapter === 'test_rig_control_customers_v1') {{
                            const customersMap = (data && typeof data === 'object' && data.customers && typeof data.customers === 'object')
                                ? data.customers
                                : {{}};
                            const items = Object.values(customersMap).map(c => {{
                                const session = normalizeText((c && c.session_id) || '');
                                const name = normalizeText((c && c.name) || '');
                                return {{
                                    session,
                                    name,
                                    chatUrl: session ? `/chat?session=${{session}}` : '',
                                    identity_key: session,
                                }};
                            }}).filter(item => item.session);
                            if (items.length === 0) {{
                                return JSON.stringify({{
                                    status: 'empty',
                                    currentUrl,
                                    count: 0,
                                    items: [],
                                    key_field: 'session',
                                    key_fields: ['session'],
                                }});
                            }}
                            return JSON.stringify({{
                                status: 'ok',
                                currentUrl,
                                count: items.length,
                                items,
                                key_field: 'session',
                                key_fields: ['session'],
                            }});
                        }}
                    }}
                }} catch (e) {{}}
            }}

            if (cfg.before_extract_js) {{
                try {{
                    const maybePromise = (0, eval)(String(cfg.before_extract_js));
                    if (maybePromise && typeof maybePromise.then === 'function') {{
                        await maybePromise;
                    }}
                }} catch (e) {{}}
            }}

            const roots = [];
            const rootSelectors = Array.isArray(cfg.roots) ? cfg.roots : [];
            rootSelectors.forEach(s => queryAllWithin(document, s).forEach(el => roots.push(el)));
            if (roots.length === 0) roots.push(document.body);
            const rootDebug = roots.slice(0, 3).map((root, idx) => {{
                if (!root) return {{ index: idx, exists: false }};
                let html = '';
                let text = '';
                try {{
                    html = String(root.innerHTML || '').slice(0, 400);
                }} catch (e) {{}}
                try {{
                    text = normalizeText(root.textContent || '').slice(0, 200);
                }} catch (e) {{}}
                return {{
                    index: idx,
                    exists: true,
                    tag: String(root.tagName || '').toLowerCase(),
                    id: String(root.id || ''),
                    className: String(root.className || ''),
                    childCount: Number(root.childElementCount || 0),
                    html,
                    text,
                }};
            }});

            const keyField = cfg.key_field || '';
            const identityCfg = (cfg.identity && typeof cfg.identity === 'object') ? cfg.identity : {{}};
            const keyFields = Array.isArray(identityCfg.key_fields) ? identityCfg.key_fields.map(v => normalizeText(v)) : (keyField ? [keyField] : []);
            const itemSpecs = Array.isArray(cfg.items) ? cfg.items : [];
            const itemFilters = (cfg.filters && typeof cfg.filters === 'object') ? cfg.filters : {{}};
            const selectorDebug = itemSpecs.map((spec, idx) => {{
                const selector = String((spec && spec.selector) || '');
                let total = 0;
                const perRoot = [];
                for (const root of roots.slice(0, 3)) {{
                    const nodes = queryAllWithin(root, selector);
                    const count = Array.isArray(nodes) ? nodes.length : 0;
                    total += count;
                    perRoot.push(count);
                }}
                return {{ index: idx, selector, total, perRoot }};
            }});
            const pageDebug = {{
                bodyMsgCount: queryAllWithin(document, '.msg').length,
                rootMsgCount: queryAllWithin(document, '#messages .msg').length,
                bodyText: normalizeText((document.body && document.body.textContent) || '').slice(0, 400),
            }};
            const extractionDebug = [];
            const items = [];
            const seenKeys = new Set();

            for (const root of roots) {{
                if (!root) continue;
                for (const spec of itemSpecs) {{
                    const nodes = queryAllWithin(root, spec.selector || '');
                    for (const node of nodes) {{
                        const fields = (spec && spec.fields && typeof spec.fields === 'object') ? spec.fields : {{}};
                        const item = {{}};
                        for (const [fieldName, fieldSpec] of Object.entries(fields)) {{
                            item[fieldName] = readField(fieldSpec, node, root);
                        }}
                        let skipReason = '';
                        if (itemFilters.from_equals && normalizeText(item.from) !== normalizeText(itemFilters.from_equals)) {{
                            skipReason = `from_mismatch:${{normalizeText(item.from)}}!=${{normalizeText(itemFilters.from_equals)}}`;
                        }}
                        let itemKey = '';
                        if (keyFields.length > 0) {{
                            itemKey = normalizeText(
                                keyFields.map(fieldName => normalizeText(item[fieldName] || '')).join('|')
                            );
                        }} else if (keyField) {{
                            itemKey = normalizeText(item[keyField] || '');
                        }} else {{
                            itemKey = normalizeText(JSON.stringify(item));
                        }}
                        if (!itemKey) {{
                            // Be defensive for chat-message monitors: older saved configs can
                            // leak the wrong identity key fields, but msg_id is still the real
                            // stable identity for rendered chat messages.
                            for (const fallbackField of ['msg_id', 'message_id', 'session', 'chatUrl', 'timestamp', 'text']) {{
                                const fallbackValue = normalizeText(item[fallbackField] || '');
                                if (fallbackValue) {{
                                    itemKey = fallbackValue;
                                    break;
                                }}
                            }}
                        }}
                        if (!itemKey) {{
                            if (!skipReason) skipReason = 'empty_item_key';
                        }} else if (seenKeys.has(itemKey)) {{
                            if (!skipReason) skipReason = 'duplicate_item_key';
                        }}
                        extractionDebug.push({{
                            selector: String((spec && spec.selector) || ''),
                            item,
                            itemKey,
                            skipReason,
                        }});
                        if (skipReason) continue;
                        seenKeys.add(itemKey);
                        item.identity_key = itemKey;
                        items.push(item);
                    }}
                }}
            }}

            if (items.length === 0) {{
                const pageText = normalizeText((document.body && document.body.textContent) || '').toLowerCase();
                const empties = Array.isArray(cfg.empty_text_patterns) ? cfg.empty_text_patterns : [];
                if (empties.some(p => p && pageText.includes(String(p).toLowerCase()))) {{
                    return JSON.stringify({{
                        status: 'empty',
                        currentUrl,
                        count: 0,
                        items: [],
                        key_field: keyField,
                        debug: {{
                            rootSelectors,
                            rootCount: roots.length,
                            rootDebug,
                            selectorDebug,
                            pageDebug,
                            extractionDebug,
                        }}
                    }});
                }}
                return JSON.stringify({{
                    status: 'no_match',
                    currentUrl,
                    count: 0,
                    items: [],
                    key_field: keyField,
                    debug: {{
                        rootSelectors,
                        rootCount: roots.length,
                        rootDebug,
                        selectorDebug,
                        pageDebug,
                        extractionDebug,
                    }}
                }});
            }}

            return JSON.stringify({{
                status: 'ok',
                currentUrl,
                count: items.length,
                items,
                key_field: keyField,
                key_fields: keyFields
            }});
        }})()
    """


def _parse_event_body_value(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            parsed = json.loads(s)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _build_normalized_browser_event(
    *,
    session: Any = None,
    monitor_id: str,
    label: str,
    source_type: str,
    params_obj: Dict[str, Any],
    sub_id: str = "",
    scope: str = "session",
    change_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = _parse_event_body_value(params_obj.get("body"))
    event = NormalizedBrowserEvent(
        event_id=sub_id or f"evt_{uuid.uuid4().hex[:12]}",
        session_id=str(id(session)) if session is not None else "",
        monitor_id=monitor_id,
        label=label,
        source_type=source_type,
        scope=scope,
        url=str(params_obj.get("url") or ""),
        detected_at=str(int(time.time() * 1000)),
        change_summary=change_summary or {},
        payload=payload,
    )
    return event.to_dict()


@dataclass
class ActiveMonitorSet:
    """Tracks all running monitors for a browser_automation node."""

    monitors: List[Any] = field(default_factory=list)  # PollingCapture instances etc.
    configs: List[EventMonitorConfig] = field(default_factory=list)
    agent_id: str = ""
    monitor_set_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

def parse_monitor_configs(inputs: dict) -> List[EventMonitorConfig]:
    """Extract EventMonitorConfig list from node inputsValues.

    ``inputs`` is the ``config_metadata.get("inputsValues", {})`` dict.
    Returns only enabled configs with a non-empty label.
    """
    raw = (inputs.get("eventMonitors") or {}).get("content", [])
    if not isinstance(raw, list):
        return []

    configs: List[EventMonitorConfig] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        def _pick(*keys: str, default: Any = None) -> Any:
            for key in keys:
                if key in item and item.get(key) is not None:
                    return item.get(key)
            return default

        enabled = item.get("enabled", True)
        if isinstance(enabled, str):
            enabled = enabled.lower() in ("true", "1", "yes", "on")
        if not enabled:
            continue

        label = (item.get("label") or "").strip()
        if not label:
            logger.warning("[EventMonitor] Skipping monitor with empty label")
            continue

        source_type = str(_pick("sourceType", "source_type", default="http_polling") or "http_polling").strip()

        # Parse comma-separated strings into lists
        def _csv(val: Any) -> List[str]:
            if isinstance(val, list):
                return [s.strip() for s in val if isinstance(s, str) and s.strip()]
            if isinstance(val, str) and val.strip():
                return [s.strip() for s in val.split(",") if s.strip()]
            return []

        cfg = EventMonitorConfig(
            id=str(_pick("id", default=f"monitor_{len(configs) + 1}") or f"monitor_{len(configs) + 1}").strip(),
            label=label,
            enabled=True,
            source_type=source_type,
            url_patterns=_csv(_pick("urlPatterns", "url_patterns")),
            methods=_csv(_pick("methods")) or ["GET", "POST"],
            content_filters=_csv(_pick("contentFilters", "content_filters")),
            min_body_length=int(_pick("minBodyLength", "min_body_length", default=10) or 10),
            frame_direction=str(_pick("frameDirection", "frame_direction", default="incoming") or "incoming").strip(),
            sse_event_types=_csv(_pick("sseEventTypes", "sse_event_types")),
            dom_selector=str(_pick("domSelector", "dom_selector", default="") or "").strip(),
            dom_attributes=bool(_pick("domAttributes", "dom_attributes", default=False)),
            dom_child_list=bool(_pick("domChildList", "dom_child_list", default=True)),
            dom_subtree=bool(_pick("domSubtree", "dom_subtree", default=True)),
            dom_check_interval_ms=max(50, int(_pick("domCheckIntervalMs", "dom_check_interval_ms", default=250) or 250)),
            cdp_domain=str(_pick("cdpDomain", "cdp_domain", default="") or "").strip(),
            cdp_event_method=str(_pick("cdpEventMethod", "cdp_event_method", default="") or "").strip(),
            cdp_filter_expr=str(_pick("cdpFilterExpr", "cdp_filter_expr", default="") or "").strip(),
        )
        configs.append(cfg)
        logger.info(
            f"[EventMonitor] Parsed config: label='{cfg.label}', "
            f"source={cfg.source_type}, urls={cfg.url_patterns}"
        )

    return configs


# ---------------------------------------------------------------------------
# Runner bridge (same dispatch path as BrowserEventService)
# ---------------------------------------------------------------------------

def _dispatch_to_runners(
    label_or_event: Any,
    event_data: Optional[dict] = None,
    target_agent_id: str = "",
) -> int:
    """Broadcast an event to all agent runners.

    Returns the number of runners that received the dispatch.
    Uses the exact same ``sync_task_wait_in_line("browser_event", ...)``
    pattern as ``BrowserEventService._dispatch_to_runners``.
    """
    # Backward-compatible call styles:
    #   _dispatch_to_runners(label, event_data)
    #   _dispatch_to_runners(event_data)
    if event_data is None and isinstance(label_or_event, dict):
        event_data = label_or_event
        label = str(event_data.get("sub_type") or event_data.get("type") or "browser_event")
    else:
        label = str(label_or_event)
        event_data = event_data or {}

    from app_context import AppContext

    runners = []
    try:
        mw = AppContext.get_main_window()
        if mw and hasattr(mw, "agents"):
            for ag in (mw.agents or []):
                r = getattr(ag, "runner", None)
                if r:
                    runners.append(r)
    except Exception:
        pass

    if not runners:
        logger.warning(f"[EventMonitor] No runners available for label='{label}'")
        return 0

    # Route to owner agent only when available; otherwise keep legacy broadcast.
    if target_agent_id:
        target_runners = []
        for runner in runners:
            try:
                runner_agent = getattr(runner, "agent", None)
                rid = (
                    getattr(getattr(runner_agent, "card", None), "id", "")
                    or getattr(runner_agent, "id", "")
                    or ""
                )
                if rid == target_agent_id:
                    target_runners.append(runner)
            except Exception:
                continue
        if target_runners:
            runners = target_runners
        else:
            logger.warning(
                f"[EventMonitor] target_agent_id='{target_agent_id}' not found; "
                f"falling back to broadcast for label='{label}'"
            )

    dispatched = 0
    for runner in runners:
        try:
            runner_agent = getattr(runner, "agent", None)
            runner_agent_id = (
                getattr(getattr(runner_agent, "card", None), "id", "")
                or getattr(runner_agent, "id", "")
                or ""
            )
            logger.info(
                f"[EventMonitor] Dispatching browser_event label='{label}' "
                f"to runner_agent_id='{runner_agent_id}' target_agent_id='{target_agent_id or ''}'"
            )
            runner.sync_task_wait_in_line("browser_event", event_data, source="event_monitor")
            dispatched += 1
        except Exception as e:
            logger.debug(f"[EventMonitor] Runner dispatch failed: {e}")

    logger.info(
        f"[EventMonitor] Dispatched '{label}' to {dispatched}/{len(runners)} runner(s)"
    )
    return dispatched


def _build_bridge_callback(label: str, monitor_set_id: str, target_agent_id: str = "", session: Any = None):
    """Build an on_message callback that bridges PollingCapture matches to runners.

    The callback signature matches PollingCapture's on_message:
        (url: str, method: str, status: int, body: str, rule: str) -> None
    """
    _fire_count = 0
    _bridge_started_ms = int(time.time() * 1000)
    _seen_msg_ids: set[str] = set()
    _seen_session_ids: set[str] = set()

    def _trim_set(s: set[str], keep_last: int = 2000) -> None:
        if len(s) <= keep_last:
            return
        # Drop an arbitrary chunk to cap growth.
        for i, k in enumerate(list(s)):
            s.discard(k)
            if i >= len(s) - keep_last:
                break

    def _dispatch_event(sub_type: str, params_obj: dict, fire_count: int) -> None:
        sub_id = f"monitor:{monitor_set_id}:{sub_type}"
        normalized_event = _build_normalized_browser_event(
            session=session,
            monitor_id=monitor_set_id,
            label=sub_type,
            source_type="http_polling",
            params_obj=params_obj,
            sub_id=sub_id,
        )
        event = {
            "type": "browser_event",
            "sub_type": sub_type,
            "sub_id": sub_id,
            "event_method": "EventMonitor.http_polling",
            "domain": "EventMonitor",
            "fire_count": fire_count,
            "agent_id": target_agent_id or "",
            "event": normalized_event,
            "params": params_obj,
            "timestamp": int(time.time() * 1000),
        }
        _dispatch_to_runners(sub_type, event, target_agent_id=target_agent_id)

    def _bridge(url: str, method: str, status: int, body: str, rule: str):
        nonlocal _fire_count
        _fire_count += 1

        # Truncate body for dispatch (avoid bloating event queue)
        truncated_body = body
        if len(body) > 2000:
            truncated_body = body[:2000] + f"...(+{len(body) - 2000})"

        params_obj = {
            "url": url,
            "method": method,
            "status": status,
            "body": truncated_body,
            "rule": rule,
        }

        # Best-effort parse to suppress duplicate/no-op polling and emit synthetic new_customer.
        parsed = None
        try:
            parsed = json.loads(body) if isinstance(body, str) and body.strip().startswith("{") else None
        except Exception:
            parsed = None

        # For chat polling, only dispatch when has_new is true and at least one new msg_id appears.
        if isinstance(parsed, dict):
            session_id = str(parsed.get("session_id") or "").strip()
            has_new = bool(parsed.get("has_new"))
            messages = parsed.get("messages") if isinstance(parsed.get("messages"), list) else []

            if label == "new_chat_msg":
                if not has_new:
                    logger.debug(f"[EventMonitor] Skip polling event (has_new=false): {url}")
                    return

                new_msg_found = False
                for m in messages:
                    if not isinstance(m, dict):
                        continue
                    if str(m.get("from") or "").lower() != "customer":
                        continue
                    msg_id = str(m.get("msg_id") or "").strip()
                    if not msg_id:
                        continue
                    if msg_id not in _seen_msg_ids:
                        _seen_msg_ids.add(msg_id)
                        new_msg_found = True
                _trim_set(_seen_msg_ids, keep_last=4000)
                if not new_msg_found:
                    logger.debug(f"[EventMonitor] Skip polling event (duplicate msg_ids): {url}")
                    return

            # After warmup, first time a session_id is observed => emit synthetic new_customer.
            warmup_ms = 8000
            now_ms = int(time.time() * 1000)
            if session_id and session_id not in _seen_session_ids:
                _seen_session_ids.add(session_id)
                _trim_set(_seen_session_ids, keep_last=2000)
                if now_ms - _bridge_started_ms > warmup_ms:
                    synth_params = dict(params_obj)
                    synth_params["rule"] = "session_first_seen"
                    synth_params["session_id"] = session_id
                    _dispatch_event("new_customer", synth_params, _fire_count)
                    logger.info(
                        f"[EventMonitor] Synthetic new_customer from polling: "
                        f"session_id={session_id}, url={url}"
                    )

        _dispatch_event(label, params_obj, _fire_count)
        logger.info(
            f"[EventMonitor] HTTP polling match #{_fire_count}: "
            f"label='{label}', rule='{rule}', url={url}, "
            f"dispatched via event bridge"
        )

    return _bridge


# ---------------------------------------------------------------------------
# Monitor lifecycle
# ---------------------------------------------------------------------------

async def start_monitors(
    session,  # BrowserSession
    configs: List[EventMonitorConfig],
    agent_id: str = "",
) -> Optional[ActiveMonitorSet]:
    """Start all configured event monitors on the given BrowserSession.

    Returns an ActiveMonitorSet (or None if no monitors to start).
    Only HTTP polling is supported in Phase 1.

    Idempotent: if monitors already exist on this session, returns existing set.
    """
    if not configs:
        return None

    session_key = id(session)
    lock = _session_start_locks.get(session_key)
    if lock is None:
        lock = asyncio.Lock()
        _session_start_locks[session_key] = lock

    async with lock:
        # Check for existing monitors on this session (idempotency)
        existing_set = get_attached_monitor_set(session)
        if existing_set and existing_set.monitors:
            logger.info(
                f"[EventMonitor] Monitors already active on session "
                f"(set_id={existing_set.monitor_set_id}, {len(existing_set.monitors)} monitors). Skipping start."
            )
            return existing_set

        monitor_set = ActiveMonitorSet(configs=configs, agent_id=agent_id or "")

        for cfg in configs:
            logger.info(
                f"[EventMonitor] Processing monitor config: label='{cfg.label}', "
                f"source_type='{cfg.source_type}', enabled={cfg.enabled}"
            )

            if not cfg.enabled:
                logger.debug(f"[EventMonitor] Skipping disabled monitor: label='{cfg.label}'")
                continue
            if cfg.source_type == "http_polling":
                monitor = await _start_http_polling_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "websocket":
                monitor = await _start_websocket_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "sse":
                monitor = await _start_sse_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "dom_mutation":
                monitor = await _start_dom_mutation_monitor(
                    session, cfg, monitor_set.monitor_set_id, monitor_set.agent_id
                )
                if monitor:
                    monitor_set.monitors.append(monitor)
            elif cfg.source_type == "cdp_raw":
                logger.info(
                    f"[EventMonitor] CDP raw monitor '{cfg.label}' - not yet implemented (Phase 6)"
                )
            else:
                logger.warning(
                    f"[EventMonitor] Unknown source_type '{cfg.source_type}' for label '{cfg.label}'"
                )

        started = len(monitor_set.monitors)
        if started > 0:
            # Store on session capability for persistence across loop iterations.
            set_attached_monitor_set(session, monitor_set)
            capability = get_event_monitor_capability(session, create=True)
            if capability:
                capability.configure(configs)
            # Register in global registry for cleanup tracking
            register_monitor_set(monitor_set)
            logger.info(
                f"[EventMonitor] Started {started} monitor(s) "
                f"(set_id={monitor_set.monitor_set_id})"
            )
            return monitor_set
        return None

async def _start_http_polling_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a PollingCapture instance for an HTTP polling monitor config."""
    try:
        from agent.ec_skills.browser_use_extension.polling_capture import PollingCapture, PollingCaptureConfig

        # Build content filter callables from substring strings
        content_filter_fns: List[Callable[[str], Optional[str]]] = []
        for substr in cfg.content_filters:
            # Each content filter checks if the substring is present in body
            # and returns the substring as the rule name on match
            def _make_filter(s: str):
                def _filter(body: str) -> Optional[str]:
                    return s if s in body else None
                return _filter
            content_filter_fns.append(_make_filter(substr))

        capture_config = PollingCaptureConfig(
            url_patterns=cfg.url_patterns,
            methods=cfg.methods,
            content_filters=content_filter_fns,
            min_body_length=cfg.min_body_length,
        )

        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id, session=session)

        capture = PollingCapture(
            session=session,
            config=capture_config,
            on_message=bridge_callback,
        )
        await capture.start()

        logger.info(
            f"[EventMonitor] HTTP polling monitor started: "
            f"label='{cfg.label}', urls={cfg.url_patterns}, "
            f"filters={cfg.content_filters}"
        )
        return capture

    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start HTTP polling monitor '{cfg.label}': {e}")
        return None


async def stop_monitors(monitor_set: Optional[ActiveMonitorSet], session=None) -> None:
    """Stop all monitors in a set (cleanup).
    
    Args:
        monitor_set: The ActiveMonitorSet to stop
        session: Optional BrowserSession to clear the stored monitor reference from
    """
    if not monitor_set:
        return
    for monitor in monitor_set.monitors:
        try:
            if hasattr(monitor, "stop"):
                await monitor.stop()
        except Exception as e:
            logger.debug(f"[EventMonitor] Error stopping monitor: {e}")
    monitor_set.monitors.clear()
    
    # Clear session reference if provided
    if session:
        clear_attached_monitor_set(session)
    
    # Unregister from global registry
    unregister_monitor_set(monitor_set.monitor_set_id)


async def _start_dom_mutation_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a DOM mutation monitor using CDP's DOM events."""
    try:
        logger.info(f"[EventMonitor] Starting DOM mutation monitor '{cfg.label}'...")
        
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client from session
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for DOM mutation monitor '{cfg.label}'")
            return None
        
        logger.debug(f"[EventMonitor] CDP client found for DOM monitor '{cfg.label}'")
        
        # Store mutation state
        mutation_state = {
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "agent_id": target_agent_id or "",
            "last_check": time.time(),
            "last_customer_count": 0,
            "last_keys": [],
            "last_status": "starting",
            "last_current_url": "",
            "last_removed_keys": [],
            "last_reordered_keys": [],
            "last_top_changed": False,
            "check_interval_ms": max(50, int(getattr(cfg, "dom_check_interval_ms", 250) or 250)),
            "page_mismatch_count": 0,
        }
        try:
            extractor_cfg = _resolve_dom_extractor_config(cfg)
            mutation_state["target_id"] = _resolve_monitor_target_id(session, cfg, extractor_cfg)
            logger.info(
                f"[EventMonitor] Bound DOM monitor '{cfg.label}' to target_id="
                f"{str(mutation_state.get('target_id') or '')[-4:] or 'None'}"
            )
        except Exception as _bind_err:
            logger.warning(f"[EventMonitor] Failed to bind DOM monitor target for '{cfg.label}': {_bind_err}")
            mutation_state["target_id"] = str(getattr(session, "agent_focus_target_id", "") or "")

        logger.info(f"[EventMonitor] DOM polling state initialized for '{cfg.label}'")
        
        # Create monitor object that can be checked periodically
        class DOMMutationMonitor:
            def __init__(self, state):
                self.state = state
                self._task: Optional[asyncio.Task] = None
            
            async def check_now(self):
                """Check method that can be called periodically."""
                if not self.state["enabled"]:
                    return
                try:
                    await _check_for_customer_changes(self.state, cfg, bridge_callback, session)
                except Exception as e:
                    logger.error(f"[EventMonitor] Error in DOM check: {e}")

            def start_loop(self):
                if self._task and not self._task.done():
                    return

                async def _run_loop():
                    interval_s = max(0.05, float(self.state.get("check_interval_ms", 250)) / 1000.0)
                    logger.info(
                        f"[EventMonitor] DOM monitor loop started: "
                        f"label='{self.state['config'].label}', interval_ms={self.state.get('check_interval_ms', 250)}"
                    )
                    try:
                        while self.state.get("enabled", False):
                            await self.check_now()
                            await asyncio.sleep(interval_s)
                    except asyncio.CancelledError:
                        logger.debug(f"[EventMonitor] DOM monitor loop cancelled: label='{self.state['config'].label}'")
                        raise
                    except Exception as loop_err:
                        logger.error(f"[EventMonitor] DOM monitor loop error: {loop_err}")

                self._task = asyncio.create_task(_run_loop())
            
            async def stop(self):
                self.state["enabled"] = False
                if self._task and not self._task.done():
                    self._task.cancel()
                    try:
                        await self._task
                    except asyncio.CancelledError:
                        pass
                logger.info(f"[EventMonitor] DOM mutation monitor stopped: label='{self.state['config'].label}'")
        
        monitor = DOMMutationMonitor(mutation_state)
        monitor.start_loop()
        
        logger.info(
            f"[EventMonitor] DOM mutation monitor started: "
            f"label='{cfg.label}', filters={cfg.content_filters}, selector={cfg.dom_selector}, "
            f"interval_ms={mutation_state['check_interval_ms']}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start DOM mutation monitor '{cfg.label}': {e}")
        import traceback
        logger.debug(f"[EventMonitor] DOM mutation startup error traceback: {traceback.format_exc()}")
        return None


async def check_dom_monitors_periodically():
    """Legacy no-op.

    DOM mutation monitors now own their own per-session asyncio loops. Keeping a
    process-global monitor list causes monitor ownership leakage across skills
    and browser sessions.
    """
    return


async def _check_for_customer_changes(mutation_state, cfg, bridge_callback, session):
    """Check for real customer changes in the control panel DOM."""
    try:
        logger.debug(f"[EventMonitor] _check_for_customer_changes called")
        
        extractor_cfg = _resolve_dom_extractor_config(cfg)
        target_id = str(mutation_state.get("target_id") or "")
        if not target_id:
            target_id = _resolve_monitor_target_id(session, cfg, extractor_cfg)
            mutation_state["target_id"] = target_id

        if not await _ensure_monitor_cdp_ready(session, mutation_state, cfg.label):
            logger.debug(f"[EventMonitor] CDP still not ready for monitor '{cfg.label}', deferring check")
            return

        # Get current URL using CDP instead of session.current_url
        current_url = "unknown"
        cdp_session = None
        cdp_client = None
        try:
            # Try to get or create CDP session (this initializes the connection)
            if hasattr(session, 'get_or_create_cdp_session'):
                logger.debug(f"[EventMonitor] Creating CDP session via get_or_create_cdp_session")
                try:
                    cdp_session = await session.get_or_create_cdp_session(target_id=target_id or None, focus=False)
                    cdp_client = cdp_session.cdp_client if cdp_session else None
                except Exception as cdp_err:
                    logger.debug(f"[EventMonitor] Failed to create CDP session: {cdp_err}")
                    if target_id:
                        try:
                            rebound_target_id = _resolve_monitor_target_id(session, cfg, extractor_cfg)
                            if rebound_target_id and rebound_target_id != target_id:
                                mutation_state["target_id"] = rebound_target_id
                                target_id = rebound_target_id
                                cdp_session = await session.get_or_create_cdp_session(target_id=target_id, focus=False)
                                cdp_client = cdp_session.cdp_client if cdp_session else None
                                logger.info(
                                    f"[EventMonitor] Rebound DOM monitor '{cfg.label}' to target_id="
                                    f"{target_id[-4:]}"
                                )
                        except Exception as _rebind_err:
                            logger.debug(f"[EventMonitor] DOM monitor target rebind failed: {_rebind_err}")
                    # Try fallback to session.cdp_client directly
                    if hasattr(session, 'cdp_client'):
                        cdp_client = session.cdp_client
                        logger.debug(f"[EventMonitor] Using session.cdp_client directly")
            elif hasattr(session, 'cdp_client'):
                cdp_client = session.cdp_client
            
            if not cdp_client:
                logger.debug(f"[EventMonitor] No CDP client available")
                # Try fallback methods for URL
                try:
                    if hasattr(session, 'browser_context') and session.browser_context:
                        current_url = getattr(session.browser_context, 'current_url', 'unknown')
                except Exception:
                    pass
                
                if current_url == "unknown" and hasattr(session, 'current_url'):
                    try:
                        current_url = session.current_url
                    except Exception:
                        pass
            else:
                logger.debug(f"[EventMonitor] CDP client available, trying Page domain")
                session_id = cdp_session.session_id if cdp_session else None
                # Try Page domain first - need to enable it first with session_id
                try:
                    # Use proper API with session_id like PollingCapture does
                    if session_id:
                        await cdp_client.send.Page.enable(session_id=session_id)
                        result = await cdp_client.send.Page.getNavigationHistory(session_id=session_id)
                    else:
                        await cdp_client.send.Page.enable()
                        result = await cdp_client.send.Page.getNavigationHistory()
                    entries = result.get("entries", [])
                    if entries:
                        current_url = entries[-1].get("url", "unknown")
                        logger.debug(f"[EventMonitor] Got URL via Page.getNavigationHistory: {current_url}")
                except Exception as page_err:
                    logger.debug(f"[EventMonitor] Page.getNavigationHistory failed: {page_err}")
                    
                # Fallback to Runtime.evaluate
                if current_url == "unknown":
                    try:
                        if session_id:
                            await cdp_client.send.Runtime.enable(session_id=session_id)
                            result = await cdp_client.send.Runtime.evaluate(
                                params={"expression": "window.location.href"},
                                session_id=session_id
                            )
                        else:
                            await cdp_client.send.Runtime.enable()
                            result = await cdp_client.send.Runtime.evaluate(
                                params={"expression": "window.location.href"}
                            )
                        current_url = result.get("result", {}).get("value", "unknown")
                        logger.debug(f"[EventMonitor] Got URL via Runtime.evaluate: {current_url}")
                    except Exception as runtime_err:
                        logger.debug(f"[EventMonitor] Runtime.evaluate failed: {runtime_err}")
        except Exception as url_err:
            logger.debug(f"[EventMonitor] Error getting URL: {url_err}")
        
        logger.debug(f"[EventMonitor] Current URL: {current_url}")
        
        # Even if URL is unknown, try DOM query anyway - browser might be ready.
        if current_url == "unknown":
            logger.debug(f"[EventMonitor] URL unknown, but will try DOM query anyway")
        
        current_count = mutation_state["last_customer_count"]
        current_time = time.time()
        time_since_last = current_time - mutation_state["last_check"]
        
        logger.debug(f"[EventMonitor] Time since last check: {time_since_last:.1f}s")
        
        interval_s = max(0.05, float(mutation_state.get("check_interval_ms", 250)) / 1000.0)
        if time_since_last < interval_s:
            logger.debug(f"[EventMonitor] Too soon to check again, skipping")
            return
        
        mutation_state["last_check"] = current_time
        
        try:
            logger.debug(
                f"[EventMonitor] extractor_cfg label={cfg.label} "
                f"page_url_patterns={extractor_cfg.get('page_url_patterns')} "
                f"roots={extractor_cfg.get('roots')} "
                f"item_selectors={[item.get('selector') for item in (extractor_cfg.get('items') or []) if isinstance(item, dict)]} "
                f"target_id={target_id[-4:] if target_id else 'None'}"
            )
        except Exception:
            pass
        
        # Use JS DOM queries first; the CDP DOM tree often omits the live customer widgets
        # we care about on the local control panel.
        try:
            logger.debug(f"[EventMonitor] Getting CDP client for DOM query")
            # Re-check CDP client - try to create session if not available
            if not cdp_client:
                if hasattr(session, 'get_or_create_cdp_session'):
                    logger.debug(f"[EventMonitor] Creating CDP session for DOM query")
                    cdp_session = await session.get_or_create_cdp_session(target_id=target_id or None, focus=False)
                    cdp_client = cdp_session.cdp_client if cdp_session else None
                elif hasattr(session, 'cdp_client'):
                    cdp_client = session.cdp_client
            
            if not cdp_client:
                logger.debug(f"[EventMonitor] No CDP client available, skipping DOM query")
                return
            
            # Evaluate a generic config-driven DOM extractor in the page context.
            logger.debug(f"[EventMonitor] Sending Runtime DOM query")
            try:
                session_id = cdp_session.session_id if cdp_session else None
                runtime_expr = _build_dom_runtime_expression(extractor_cfg)
                if session_id:
                    await cdp_client.send.Runtime.enable(session_id=session_id)
                    result = await cdp_client.send.Runtime.evaluate(
                        params={"expression": runtime_expr, "awaitPromise": True},
                        session_id=session_id
                    )
                else:
                    await cdp_client.send.Runtime.enable()
                    result = await cdp_client.send.Runtime.evaluate(
                        params={"expression": runtime_expr, "awaitPromise": True}
                    )
                dom_content = result.get("result", {}).get("value", "")
                logger.debug(f"[EventMonitor] DOM query result via Runtime: {dom_content[:100]}...")
            except Exception as runtime_err:
                logger.debug(f"[EventMonitor] Runtime domain query failed: {runtime_err}")
                return
            
            logger.debug(f"[EventMonitor] CDP query completed, parsing result")
            logger.debug(f"[EventMonitor] DOM query result: {dom_content[:100]}...")
            
            try:
                data = json.loads(dom_content) if isinstance(dom_content, str) and dom_content.strip() else {}
            except Exception:
                logger.debug(f"[EventMonitor] DOM query result was not valid JSON")
                return
            if not isinstance(data, dict):
                logger.debug(
                    f"[EventMonitor] DOM query returned non-object payload "
                    f"(type={type(data).__name__}), coercing to empty snapshot"
                )
                data = {}

            status = str(data.get("status") or "")
            current_url = str(data.get("currentUrl") or current_url)
            mutation_state["last_status"] = status or "ok"
            mutation_state["last_current_url"] = current_url
            if status in ("no_match", "empty"):
                debug_info = data.get("debug") if isinstance(data.get("debug"), dict) else {}
                if debug_info:
                    try:
                        logger.debug(
                            "[EventMonitor] DOM debug "
                            f"status={status} "
                            f"rootCount={debug_info.get('rootCount')} "
                            f"rootSelectors={debug_info.get('rootSelectors')} "
                            f"selectorDebug={debug_info.get('selectorDebug')} "
                            f"pageDebug={debug_info.get('pageDebug')} "
                            f"rootDebug={debug_info.get('rootDebug')} "
                            f"extractionDebug={debug_info.get('extractionDebug')}"
                        )
                    except Exception:
                        pass
            if status == "page_mismatch":
                mutation_state["page_mismatch_count"] = int(mutation_state.get("page_mismatch_count") or 0) + 1
                mismatch_count = mutation_state["page_mismatch_count"]
                if (
                    cfg.label == "chat_message_added"
                    and mismatch_count >= 5
                    and current_url
                    and "127.0.0.1:9877/chat?session=" not in current_url
                ):
                    logger.warning(
                        f"[EventMonitor] Retiring stale chat monitor '{cfg.label}' after "
                        f"{mismatch_count} page mismatches; current_url={current_url}"
                    )
                    mutation_state["enabled"] = False
                logger.debug(f"[EventMonitor] DOM page mismatch, skipping: {current_url}")
                return
            mutation_state["page_mismatch_count"] = 0

            items = data.get("items") if isinstance(data.get("items"), list) else []
            key_field = str(data.get("key_field") or "")
            key_fields = data.get("key_fields") if isinstance(data.get("key_fields"), list) else []
            current_keys: List[str] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                if key_fields:
                    key = str(item.get("identity_key") or "").strip()
                elif key_field:
                    key = str(item.get(key_field) or "").strip()
                else:
                    try:
                        key = json.dumps(item, sort_keys=True)
                    except Exception:
                        key = ""
                if key:
                    current_keys.append(key)

            keys_initialized = bool(mutation_state.get("keys_initialized"))
            previous_keys = mutation_state.get("last_keys") or []
            if not isinstance(previous_keys, list):
                previous_keys = []
            previous_top_keys = mutation_state.get("last_top_keys") or []
            if not isinstance(previous_top_keys, list):
                previous_top_keys = []
            previous_key_set = set(str(k) for k in previous_keys if isinstance(k, str) and k)
            current_key_set = set(current_keys)
            added_keys = [k for k in current_keys if k not in previous_key_set]
            if (
                not keys_initialized
                and cfg.label == "chat_message_added"
                and current_keys
            ):
                # For customer chat monitors, treat the first non-empty snapshot as
                # meaningful work instead of silently absorbing it into baseline.
                added_keys = list(current_keys)
            removed_keys = [k for k in previous_keys if isinstance(k, str) and k not in current_key_set]
            reordered_keys = []
            if keys_initialized and previous_keys and current_keys and previous_keys != current_keys:
                reordered_keys = [k for k in current_keys if k in previous_key_set]
            current_top_keys = current_keys[: min(len(current_keys), int(extractor_cfg.get("top_n") or len(current_keys) or 0))]
            top_changed = bool(keys_initialized and previous_top_keys != current_top_keys)
            added_items = []
            if added_keys:
                added_lookup = set(added_keys)
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    if key_fields:
                        item_key = str(item.get("identity_key") or "").strip()
                    else:
                        item_key = str(item.get(key_field) or "").strip() if key_field else json.dumps(item, sort_keys=True)
                    if item_key in added_lookup:
                        added_items.append(item)

            customer_count = int(data.get("count") or len(items) or 0)
            mutation_state["last_customer_count"] = customer_count
            mutation_state["last_keys"] = current_keys
            mutation_state["last_top_keys"] = current_top_keys
            mutation_state["last_removed_keys"] = removed_keys
            mutation_state["last_reordered_keys"] = reordered_keys
            mutation_state["last_top_changed"] = top_changed
            mutation_state["keys_initialized"] = True

            logger.debug(
                f"[EventMonitor] DOM snapshot status={status or 'ok'} count={customer_count} "
                f"(was {current_count}) added={len(added_items)} removed={len(removed_keys)} "
                f"reordered={len(reordered_keys)} top_changed={top_changed}"
            )

            emit_on = str(extractor_cfg.get("emit_on") or "added").lower()
            should_emit = False
            if emit_on == "changed":
                should_emit = bool(added_items or removed_keys)
            elif emit_on == "reordered":
                should_emit = bool(reordered_keys)
            elif emit_on == "top_changed":
                should_emit = top_changed
            elif emit_on == "added_or_reordered":
                should_emit = bool(added_items or reordered_keys)
            else:
                should_emit = bool(added_items)

            if should_emit:
                payload = {
                    "status": status or "ok",
                    "count": customer_count,
                    "items": items,
                    "added": added_items,
                    "removed_keys": removed_keys,
                    "key_field": key_field,
                    "key_fields": key_fields,
                    "reordered_keys": reordered_keys,
                    "top_keys": current_top_keys,
                    "current_url": current_url,
                }
                sub_id = f"dom_{int(time.time() * 1000)}"
                normalized_event = _build_normalized_browser_event(
                    session=session,
                    monitor_id=str(getattr(cfg, "id", "") or monitor_set_id),
                    label=cfg.label,
                    source_type="dom_mutation",
                    params_obj={
                        "url": current_url,
                        "body": payload,
                    },
                    sub_id=sub_id,
                    scope="tab",
                    change_summary={
                        "mode": emit_on,
                        "added_keys": added_keys,
                        "removed_keys": removed_keys,
                        "reordered_keys": reordered_keys,
                        "top_keys": current_top_keys,
                    },
                )
                event_data = {
                    "type": "browser_event",
                    "sub_type": cfg.label,
                    "sub_id": sub_id,
                    "event_method": "DOM.polling",
                    "domain": "DOM",
                    "event": normalized_event,
                    "params": {
                        "url": current_url,
                        "method": "DOM_MUTATION",
                        "status": 200,
                        "body": json.dumps(payload),
                        "rule": cfg.label,
                        "detection": "config_driven_dom_diff",
                        "customer_count": customer_count,
                        "previous_count": current_count,
                    }
                }
                _dispatch_to_runners(
                    cfg.label,
                    event_data,
                    target_agent_id=(mutation_state.get("agent_id") or ""),
                )
                logger.info(
                    f"[EventMonitor] DOM diff detected event: label='{cfg.label}', "
                    f"added={len(added_items)}, removed={len(removed_keys)}, reordered={len(reordered_keys)}, count={customer_count}"
                )
            
        except Exception as e:
            logger.error(f"[EventMonitor] Error querying DOM: {e}")
            import traceback
            logger.debug(f"[EventMonitor] DOM query error traceback: {traceback.format_exc()}")
    
    except Exception as e:
        logger.error(f"[EventMonitor] Error in customer change detection: {e}")
        import traceback
        logger.debug(f"[EventMonitor] Customer change detection error traceback: {traceback.format_exc()}")


async def _simulate_dom_change_detection(cfg, bridge_callback, session):
    """Simulate DOM change detection by checking page content."""
    try:
        # Get current page content
        current_url = session.current_url if hasattr(session, 'current_url') else "unknown"
        
        # If we're on the control panel, check for customer changes
        if "control" in current_url:
            # Simulate finding new customers by checking page content
            # In a real implementation, this would use DOM queries
            simulated_content = "New Customer Session Detected"
            
            # Check if content matches filters
            matched = False
            for filter_str in cfg.content_filters:
                if filter_str.lower() in simulated_content.lower():
                    matched = True
                    break
            
            if matched:
                # Build event data
                event_data = {
                    "type": "browser_event",
                    "sub_type": cfg.label,
                    "sub_id": f"dom_{int(time.time() * 1000)}",
                    "event_method": "Page.domContentUpdated",
                    "domain": "Page",
                    "params": {
                        "url": current_url,
                        "method": "DOM_MUTATION",
                        "status": 200,
                        "body": simulated_content,
                        "rule": cfg.label,
                        "detection": "simulated"
                    }
                }
                
                # Dispatch to runners
                _dispatch_to_runners(cfg.label, event_data)
                logger.info(f"[EventMonitor] DOM mutation simulated match: label='{cfg.label}', content='{simulated_content}'")
    except Exception as e:
        logger.debug(f"[EventMonitor] Error in DOM change detection simulation: {e}")


async def _process_dom_mutation(params, cfg, bridge_callback, session):
    """Process DOM mutation events and check for matches."""
    try:
        # Check if this mutation affects customer list
        # Look for added nodes that might contain customer info
        if "nodes" in params:
            for node in params["nodes"]:
                if node.get("nodeName") in ["DIV", "LI", "SPAN", "TR", "TD"]:
                    # Look for customer-related content
                    node_content = node.get("nodeValue", "") or node.get("textContent", "")
                    
                    # Check content filters
                    matched = False
                    for filter_str in cfg.content_filters:
                        if filter_str.lower() in node_content.lower():
                            matched = True
                            break
                    
                    if matched:
                        # Build event data similar to HTTP polling
                        event_data = {
                            "type": "browser_event",
                            "sub_type": cfg.label,
                            "sub_id": f"dom_{int(time.time() * 1000)}",
                            "event_method": "DOM.setChildNodes",
                            "domain": "DOM",
                            "params": {
                                "url": session.current_url if hasattr(session, 'current_url') else "unknown",
                                "method": "DOM_MUTATION",
                                "status": 200,
                                "body": node_content,
                                "rule": cfg.label,
                                "node_info": node
                            }
                        }
                        
                        # Dispatch to runners
                        _dispatch_to_runners(cfg.label, event_data)
                        logger.info(f"[EventMonitor] DOM mutation matched: label='{cfg.label}', content='{node_content[:50]}...'")
                        break
    except Exception as e:
        logger.debug(f"[EventMonitor] Error processing DOM mutation: {e}")


async def _start_websocket_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a WebSocket monitor for real-time message streams."""
    try:
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client for WebSocket interception
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for WebSocket monitor '{cfg.label}'")
            return None
        
        # Enable Network domain for WebSocket tracking
        await cdp_client.send_raw("Network.enable", {})
        
        # Store WebSocket state
        ws_state = {
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "tracked_connections": set()
        }
        
        # Register WebSocket event handlers
        async def _websocket_created_handler(params):
            """Handle WebSocket creation."""
            try:
                ws_url = params.get("url", "")
                ws_id = params.get("requestId", "")
                
                # Check URL patterns
                for pattern in cfg.url_patterns:
                    if pattern in ws_url:
                        ws_state["tracked_connections"].add(ws_id)
                        logger.debug(f"[EventMonitor] Tracking WebSocket: {ws_url}")
                        break
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in WebSocket created handler: {e}")
        
        async def _websocket_frame_handler(params):
            """Handle WebSocket frame messages."""
            try:
                ws_id = params.get("requestId", "")
                if ws_id not in ws_state["tracked_connections"]:
                    return
                
                payload = params.get("payload", {}).get("data", "")
                
                # Check content filters
                matched = False
                for filter_str in cfg.content_filters:
                    if filter_str.lower() in payload.lower():
                        matched = True
                        break
                
                if matched:
                    # Build event data
                    event_data = {
                        "type": "browser_event",
                        "sub_type": cfg.label,
                        "sub_id": f"ws_{int(time.time() * 1000)}",
                        "event_method": "Network.webSocketFrameReceived",
                        "domain": "Network",
                        "params": {
                            "url": params.get("url", "unknown"),
                            "method": "WEBSOCKET_MESSAGE",
                            "status": 200,
                            "body": payload,
                            "rule": cfg.label,
                            "ws_id": ws_id
                        }
                    }
                    
                    # Dispatch to runners
                    _dispatch_to_runners(cfg.label, event_data, target_agent_id=target_agent_id)
                    logger.info(f"[EventMonitor] WebSocket message matched: label='{cfg.label}', payload='{payload[:50]}...'")
                    
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in WebSocket frame handler: {e}")
        
        # Register handlers
        await cdp_client._event_registry.register("Network.webSocketCreated", _websocket_created_handler)
        await cdp_client._event_registry.register("Network.webSocketFrameReceived", _websocket_frame_handler)
        
        # Create monitor object
        class WebSocketMonitor:
            def __init__(self, state):
                self.state = state
            
            async def stop(self):
                self.state["enabled"] = False
                self.state["tracked_connections"].clear()
                logger.info(f"[EventMonitor] WebSocket monitor stopped: label='{self.state['config'].label}'")
        
        monitor = WebSocketMonitor(ws_state)
        
        logger.info(
            f"[EventMonitor] WebSocket monitor started: "
            f"label='{cfg.label}', url_patterns={cfg.url_patterns}, filters={cfg.content_filters}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start WebSocket monitor '{cfg.label}': {e}")
        return None


async def _start_sse_monitor(
    session, cfg: EventMonitorConfig, monitor_set_id: str, target_agent_id: str = ""
):
    """Start a Server-Sent Events (SSE) monitor."""
    try:
        bridge_callback = _build_bridge_callback(cfg.label, monitor_set_id, target_agent_id)
        
        # Get CDP client for response interception
        cdp_client = session.cdp_client if hasattr(session, 'cdp_client') else None
        if not cdp_client:
            logger.error(f"[EventMonitor] No CDP client available for SSE monitor '{cfg.label}'")
            return None
        
        # Enable Network domain
        await cdp_client.send_raw("Network.enable", {})
        
        # Store SSE state
        sse_state = {
            "enabled": True,
            "callback": bridge_callback,
            "config": cfg,
            "monitor_set_id": monitor_set_id,
            "tracked_streams": set()
        }
        
        # Register SSE response handler
        async def _sse_response_handler(params):
            """Handle SSE response streams."""
            try:
                response = params.get("response", {})
                url = response.get("url", "")
                headers = response.get("headers", {})
                
                # Check if this is an SSE stream
                content_type = headers.get("content-type", "").lower()
                if "text/event-stream" not in content_type:
                    return
                
                # Check URL patterns
                stream_matched = False
                for pattern in cfg.url_patterns:
                    if pattern in url:
                        stream_matched = True
                        break
                
                if not stream_matched:
                    return
                
                # Track this stream
                request_id = params.get("requestId", "")
                sse_state["tracked_streams"].add(request_id)
                
                # Get response body
                try:
                    body_result = await cdp_client.send_raw("Network.getResponseBody", {"requestId": request_id})
                    body = body_result.get("body", "")
                    
                    # Parse SSE events (each line is an event)
                    for line in body.split('\n'):
                        if line.startswith('data:'):
                            event_data = line[5:].strip()  # Remove 'data:' prefix
                            
                            # Check content filters
                            matched = False
                            for filter_str in cfg.content_filters:
                                if filter_str.lower() in event_data.lower():
                                    matched = True
                                    break
                            
                            if matched and event_data:
                                # Build event data
                                event = {
                                    "type": "browser_event",
                                    "sub_type": cfg.label,
                                    "sub_id": f"sse_{int(time.time() * 1000)}",
                                    "event_method": "Network.responseReceived",
                                    "domain": "Network",
                                    "params": {
                                        "url": url,
                                        "method": "SSE_EVENT",
                                        "status": response.get("status", 200),
                                        "body": event_data,
                                        "rule": cfg.label,
                                        "stream_id": request_id
                                    }
                                }
                                
                                # Dispatch to runners
                                _dispatch_to_runners(cfg.label, event, target_agent_id=target_agent_id)
                                logger.info(f"[EventMonitor] SSE event matched: label='{cfg.label}', data='{event_data[:50]}...'")
                                
                except Exception as e:
                    logger.debug(f"[EventMonitor] Error getting SSE response body: {e}")
                    
            except Exception as e:
                logger.debug(f"[EventMonitor] Error in SSE response handler: {e}")
        
        # Register handler
        await cdp_client._event_registry.register("Network.responseReceived", _sse_response_handler)
        
        # Create monitor object
        class SSEMonitor:
            def __init__(self, state):
                self.state = state
            
            async def stop(self):
                self.state["enabled"] = False
                self.state["tracked_streams"].clear()
                logger.info(f"[EventMonitor] SSE monitor stopped: label='{self.state['config'].label}'")
        
        monitor = SSEMonitor(sse_state)
        
        logger.info(
            f"[EventMonitor] SSE monitor started: "
            f"label='{cfg.label}', url_patterns={cfg.url_patterns}, filters={cfg.content_filters}"
        )
        return monitor
        
    except Exception as e:
        logger.error(f"[EventMonitor] Failed to start SSE monitor '{cfg.label}': {e}")
        return None

