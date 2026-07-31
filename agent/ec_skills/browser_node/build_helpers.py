"""Lifted browser-session helpers + state from
``build_browser_automation_node`` (Phase 6.7, 2026-04-24).

Houses the eight helper functions and four state dicts that were
previously closures of ``build_browser_automation_node`` in
``build_node.py``.  Lifting them shrinks ``build_browser_automation_node``
by ~530 lines and ``RunContext`` by ~14 fields.

Helpers:

* :func:`extract_runtime_invocation_input` — pull live invocation
  payload (chat content / params metadata) out of a workflow state dict.
* :func:`get_browser_profile_settings` — load profile by name from
  backend config.
* :func:`is_session_started` — strong/weak signal that a
  ``BrowserSession`` is fully ready.
* :func:`is_session_alive` — ``is_session_started`` AND event-bus alive
  AND CDP websocket open.
* :func:`extract_assignment_scope` — best-effort JSON parse of the
  current assignment payload.
* :func:`resolve_browser_scope_key` — stable scope key for cache keys
  (chat-id when present, else ``node:<name>``).
* :func:`patch_browser_session_lifecycle_debug` — attach one-time debug
  hooks to a live ``BrowserSession`` / CDP client.
* :func:`cleanup_stale_browser_sessions` — sweep dead sessions out of
  the cache.
* :func:`get_or_create_browser_session` — main entry point: returns a
  cached session if alive, else acquires a fresh one via
  ``BrowserManager``.

State dicts (module-level singletons; previously per-build-call):

* :data:`cached_browser_sessions` — scope_key → ``BrowserSession``.
* :data:`last_known_focus_target_ids` — scope_key → CDP target_id of
  last-focused tab (survives session recreation).
* :data:`browser_start_locks` — cdp_port → threading.Lock for
  cross-worker startup serialization.
* :data:`cached_bu_agents` — scope_key → ``browser_use.Agent`` (~860 MB
  per re-instantiation, so caching is critical).

Constants:

* :data:`MAX_BROWSER_CACHE_SIZE` = 3 — eviction trigger for
  ``cached_browser_sessions``.
* :data:`NEW_TAB_WAIT_SEC` = 2.0 — fallback blank-tab wait.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import traceback
from typing import Any

from utils.logger_helper import logger_helper as logger

from agent.ec_skills.build_node import (
    send_skill_editor_log,
    _cached_passive_agents,
)


# ─── Module-level state ──────────────────────────────────────────────
# Previously lived as build-scope locals inside
# ``build_browser_automation_node``; promoted to module-level in Phase
# 6.7.  Behavior change: these are now shared across all compiled
# nodes (was previously isolated per ``build_browser_automation_node``
# invocation).  Safe because all keys include node identity
# (``node:<name>`` or ``chat:<id>``) so collisions cannot occur.

cached_browser_sessions: dict[str, Any] = {}
_cached_browser_sessions_insertion_order: list[str] = []  # Track insertion order for FIFO eviction
last_known_focus_target_ids: dict[str, str] = {}  # survives session recreation per scope
browser_start_locks: dict[int, Any] = {}  # thread locks keyed by CDP port for cross-worker startup serialization
# Tunable timeouts for browser session startup (can be overridden via env vars)
BROWSER_START_LOCK_TIMEOUT = int(os.getenv("EC_BROWSER_START_LOCK_TIMEOUT", "30"))  # was 60s
BROWSER_SESSION_START_TIMEOUT = int(os.getenv("EC_BROWSER_SESSION_START_TIMEOUT", "20"))  # was 30s

# CRITICAL: cached_bu_agents is a massive memory leak risk!
# Each browser-use Agent consumes ~860 MB (per comments).
# Must have strict size limits to prevent runaway memory growth.
# Can be overridden via ECAN_MAX_BU_AGENTS_CACHE_SIZE env var.
_MAX_BU_AGENTS_CACHE_SIZE = int(os.environ.get("ECAN_MAX_BU_AGENTS_CACHE_SIZE", "4"))
cached_bu_agents: dict[str, Any] = {}
_cached_bu_agents_insertion_order: list[str] = []  # Track insertion order for FIFO eviction

DEFAULT_NODE_SCOPED_SKILL_NAMES = {"customer_front_desk", "飞鸽前台", "飞鸽前台0"}

MAX_BROWSER_CACHE_SIZE = 3  # Limit cache size to prevent unbounded memory growth
NEW_TAB_WAIT_SEC = 2.0  # seconds to wait after creating a fallback blank tab


def _evict_bu_agent_if_needed() -> None:
    """Evict oldest browser-use Agent if cache exceeds size limit.
    
    Each cached_bu_agents entry consumes ~860 MB, so we must keep
    this cache strictly bounded. Uses FIFO eviction based on insertion order.
    """
    global _cached_bu_agents_insertion_order
    
    if len(cached_bu_agents) <= _MAX_BU_AGENTS_CACHE_SIZE:
        return
    
    # Evict oldest entries until we're under the limit
    while len(cached_bu_agents) > _MAX_BU_AGENTS_CACHE_SIZE and _cached_bu_agents_insertion_order:
        oldest_key = _cached_bu_agents_insertion_order.pop(0)
        if oldest_key in cached_bu_agents:
            agent = cached_bu_agents.pop(oldest_key, None)
            logger.warning(
                f"[build_helpers] EVICTED cached_bu_agents entry '{oldest_key}' "
                f"to prevent memory leak (cache size: {len(cached_bu_agents)}/{_MAX_BU_AGENTS_CACHE_SIZE})"
            )
            # Try to clean up the agent if it has a cleanup method
            if agent is not None:
                try:
                    if hasattr(agent, 'stop'):
                        agent.stop()
                except Exception:
                    pass


# ─── Trivial helpers (0-1 closure refs in original) ──────────────────

def _is_response_payload_text(value: str) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = json.loads(value)
    except Exception:
        return False
    if not isinstance(parsed, dict):
        return False
    return bool(
        str(parsed.get("response_text") or "").strip()
        and str(parsed.get("customer_name") or parsed.get("customer_id") or "").strip()
    )


def extract_runtime_invocation_input(state: dict | None) -> str:
    """Extract the live invocation payload for browser-use task grounding.

    Browser-use nodes do not consume graph state directly; they only see the
    composed task string. For resumed chat/service flows we must inject the
    current assignment/customer payload into that task string so the model
    does not fall back to examples or stale memory.
    """
    if not isinstance(state, dict):
        return ""

    candidates = []
    event_type = ""

    pr_events = (state.get("prompt_refs") or {}).get("events", "")
    if isinstance(pr_events, str) and pr_events.strip():
        try:
            evt = json.loads(pr_events)
            if isinstance(evt, dict):
                event_type = str(evt.get("event_type") or "").strip()
                human_text = evt.get("human_text")
                if isinstance(human_text, str) and human_text.strip():
                    candidates.append(human_text.strip())
        except Exception:
            pass

    current_input = state.get("current_invocation_input")
    if isinstance(current_input, str) and current_input.strip():
        candidates.append(current_input.strip())

    attrs = state.get("attributes", {}) if isinstance(state.get("attributes"), dict) else {}
    attr_current_input = attrs.get("current_invocation_input")
    if isinstance(attr_current_input, str) and attr_current_input.strip():
        candidates.append(attr_current_input.strip())

    direct_input = state.get("input")
    if isinstance(direct_input, str) and direct_input.strip():
        candidates.append(direct_input.strip())

    messages = state.get("messages")
    if isinstance(messages, list) and len(messages) > 4:
        msg_payload = messages[4]
        if isinstance(msg_payload, str) and msg_payload.strip():
            candidates.append(msg_payload.strip())

    params = attrs.get("params", {}) if isinstance(attrs.get("params"), dict) else {}
    metadata = params.get("metadata", {}) if isinstance(params.get("metadata"), dict) else {}
    meta_params = metadata.get("params", {}) if isinstance(metadata.get("params"), dict) else {}

    content_obj = meta_params.get("content")
    if isinstance(content_obj, str) and content_obj.strip():
        candidates.append(content_obj.strip())
    elif isinstance(content_obj, dict):
        text_val = content_obj.get("text")
        if isinstance(text_val, str) and text_val.strip():
            candidates.append(text_val.strip())

    message = params.get("message")
    if isinstance(message, dict):
        parts = message.get("parts")
        if isinstance(parts, list) and parts:
            first = parts[0]
            if isinstance(first, dict):
                text_val = first.get("text")
                if isinstance(text_val, str) and text_val.strip():
                    candidates.append(text_val.strip())
    else:
        try:
            parts = getattr(message, "parts", None)
            if isinstance(parts, (list, tuple)) and parts:
                text_val = getattr(parts[0], "text", None)
                if isinstance(text_val, str) and text_val.strip():
                    candidates.append(text_val.strip())
        except Exception:
            pass

    suppress_response_payload = (
        event_type == "browser_event"
        or bool(state.get("_ecan_predispatch_actionable_items"))
    )
    for candidate in candidates:
        if candidate:
            if suppress_response_payload and _is_response_payload_text(candidate):
                logger.info(
                    "[BrowserAutomation] Skipped stale response_text runtime "
                    "input during browser_event/pre-dispatch cycle"
                )
                continue
            return candidate
    return ""


def get_browser_profile_settings(profile_name: str) -> dict:
    """Load browser profile settings from backend configuration."""
    try:
        from gui.ipc.w2p_handlers.browser_use_handler import get_profile_by_name, get_default_profile

        if profile_name:
            profile = get_profile_by_name(profile_name)
        else:
            profile = get_default_profile()

        if profile:
            logger.debug(f"[BrowserAutomation] Loaded profile settings: {profile.get('name', 'unknown')}")
            return profile
    except Exception as e:
        logger.warning(f"[BrowserAutomation] Failed to load browser profile settings: {e}")

    return {}


def is_session_started(session) -> bool:
    """Check BrowserSession is fully started (CDP root client ready).

    `session_manager is not None` can become true before CDP root client
    is initialized, which leads to runtime errors like
    "Root CDP client not initialized" during watchdog events.
    """
    if session is None:
        return False

    if getattr(session, "_ecan_fast_attach_ready", False):
        return True

    # Prefer strong signal: root CDP client initialized.
    root_client = getattr(session, "_cdp_client_root", None)
    if root_client is None:
        root_client = getattr(session, "cdp_client_root", None)
    if root_client is not None:
        return True

    # Defensive fallback for older/newer browser_use internals.
    return getattr(session, "session_manager", None) is not None and getattr(session, "event_bus", None) is not None


def is_session_alive(session) -> bool:
    """Check session is started AND its event bus is still operational AND CDP connection alive."""
    if not is_session_started(session):
        logger.debug(f"[BrowserAutomation] is_session_alive: session_manager is None")
        return False
    try:
        eb = getattr(session, 'event_bus', None)
        if eb is None:
            logger.debug(f"[BrowserAutomation] is_session_alive: event_bus is None")
            return False
        eq = getattr(eb, 'event_queue', None)
        eq_shutdown = getattr(eq, '_is_shutdown', False) if eq is not None else 'no_queue'
        eb_running = getattr(eb, '_is_running', False)
        rl_task = getattr(eb, '_runloop_task', None)
        rl_done = rl_task.done() if rl_task is not None else 'no_task'
        logger.debug(
            f"[BrowserAutomation] is_session_alive: "
            f"eb._is_running={eb_running}, eq._is_shutdown={eq_shutdown}, "
            f"runloop_task.done={rl_done}, session_id={session.id}"
        )
        if eq is not None and getattr(eq, '_is_shutdown', False):
            return False
        if not eb_running:
            return False

        # Verify websocket connection is not closed — check multiple possible attribute
        # names used by different Playwright/CDP client versions.
        cdp_client = getattr(session, '_cdp_client_root', None) or getattr(session, 'cdp_client_root', None)
        if cdp_client:
            ws = getattr(cdp_client, 'ws', None) or getattr(cdp_client, 'websocket', None)
            if ws is None:
                logger.debug(
                    f"[BrowserAutomation] is_session_alive: CDP client found but no websocket attribute "
                    f"(tried ws, websocket); skipping CDP check, assuming alive"
                )
            elif getattr(ws, 'closed', False) or getattr(ws, '_closed', False):
                logger.debug(f"[BrowserAutomation] is_session_alive: CDP websocket is closed")
                return False

        return True
    except Exception as e:
        logger.debug(f"[BrowserAutomation] is_session_alive: exception: {e}")
        return False


def extract_assignment_scope(runtime_input: str) -> dict:
    """Best-effort parse of the current assignment payload."""
    if not isinstance(runtime_input, str) or not runtime_input.strip():
        return {}
    try:
        payload = json.loads(runtime_input)
        if isinstance(payload, dict):
            return payload
    except Exception:
        pass
    return {}


# ── Front-desk dispatcher pattern: skill-level pin-to-node opt-in ──
#
# Stress test 2026-04-30 (20 simultaneous customers, 1 front-desk + 3 Q&A) showed
# the front-desk skill ``customer_front_desk`` was creating a new browser session
# per customer because ``state["messages"][1]`` (the customer-id index) leaked
# into the scope-key resolver below.  Each new session waited 30-35 s on the
# CDP startup lock for ``cdp_port=9228``, throttling throughput to ~1 customer
# /min and triggering a positive feedback loop with the focus-preflight
# state-summary timeouts.
#
# A "front-desk dispatcher" needs the OPPOSITE behaviour from a per-chat Q&A
# bot: one shared browser session, rotated across many customer tabs by tab
# switches.  The ``pin_browser_scope_to_node`` opt-in below lets a skill author
# declare this intent in mapping_rules; the resolver then returns ``node:<name>``
# regardless of any chat-id present in state.
_PIN_BROWSER_SCOPE_CACHE: dict[str, bool] = {}


def _resolve_pin_to_node_from_skill(skill_name: str) -> bool:
    """Return True if the skill's ``mapping_rules`` opted into node-scoped
    browser sessions (front-desk dispatcher pattern).  Cached per skill name.
    """
    if not skill_name:
        return False
    if skill_name in _PIN_BROWSER_SCOPE_CACHE:
        return _PIN_BROWSER_SCOPE_CACHE[skill_name]
    pinned = False
    try:
        from app_context import AppContext
        mw = AppContext.get_main_window()
        if mw:
            for sk in (getattr(mw, "agent_skills", None) or []):
                if getattr(sk, "name", "") != skill_name:
                    continue
                mr = getattr(sk, "mapping_rules", None) or {}
                if isinstance(mr, dict):
                    flag = mr.get("pin_browser_scope_to_node")
                    if isinstance(flag, bool):
                        pinned = flag
                    elif isinstance(flag, str):
                        pinned = flag.strip().lower() in ("1", "true", "yes", "on")
                break
    except Exception:
        pinned = False
    _PIN_BROWSER_SCOPE_CACHE[skill_name] = pinned
    return pinned


def reset_pin_browser_scope_cache() -> None:
    """Clear the per-skill pin-to-node cache.  Used by tests and by mapping-rule
    edits at runtime so a skill author can flip the flag without restarting."""
    try:
        _PIN_BROWSER_SCOPE_CACHE.clear()
    except Exception:
        pass


def resolve_browser_scope_key(
    state: dict | None = None,
    *,
    node_name: str,
    pin_to_node: bool | None = None,
    skill_name: str | None = None,
) -> str:
    """Resolve a stable browser scope key from workflow state.

    Session-scoped chat tasks must not share browser cache/state with other
    customer sessions. Prefer chat/session identity when present.

    The ``node_name`` is required (was a closure ref in the original;
    now an explicit kwarg).

    ``pin_to_node`` overrides the chat-id-based scope resolution: when truthy,
    always returns ``node:<name>``.  Resolution order:
      1. Explicit ``pin_to_node`` kwarg (tests / programmatic callers).
      2. ``state["attributes"]["pin_browser_scope_to_node"]`` flag.
      3. ``state["attributes"]["params"]["pinBrowserScopeToNode"]`` flag.
      4. Skill ``mapping_rules.pin_browser_scope_to_node`` (cached, looked up
         via ``state["attributes"]["skill_name"]``).
      5. Default: chat-id-based scope (existing behaviour).
    """
    # Pin-to-node opt-in: front-desk dispatcher pattern (one shared browser
    # session rotated across customer tabs, vs the default per-chat isolation).
    try:
        if pin_to_node is True:
            return f"node:{node_name}"
        _attrs_pin = state.get("attributes", {}) if isinstance(state, dict) else {}
        if isinstance(_attrs_pin, dict):
            _v = _attrs_pin.get("pin_browser_scope_to_node")
            if _v is True or (isinstance(_v, str) and _v.strip().lower() in ("1", "true", "yes", "on")):
                return f"node:{node_name}"
            _params_pin = _attrs_pin.get("params", {}) if isinstance(_attrs_pin, dict) else {}
            if isinstance(_params_pin, dict):
                _v = _params_pin.get("pinBrowserScopeToNode")
                if _v is True or (isinstance(_v, str) and _v.strip().lower() in ("1", "true", "yes", "on")):
                    return f"node:{node_name}"
            _skill_name = str(
                skill_name
                or (_attrs_pin.get("skill_name") if isinstance(_attrs_pin, dict) else "")
                or ""
            ).strip()
            if _skill_name.lower() in DEFAULT_NODE_SCOPED_SKILL_NAMES:
                return f"node:{node_name}"
            if _skill_name and _resolve_pin_to_node_from_skill(_skill_name):
                return f"node:{node_name}"
    except Exception:
        pass

    try:
        state = state or {}
        attrs = state.get("attributes", {}) if isinstance(state, dict) else {}
        params = attrs.get("params", {}) if isinstance(attrs, dict) else {}
        meta_params = {}
        if isinstance(params.get("metadata"), dict):
            meta_params = params.get("metadata", {}).get("params", {}) or {}

        candidates = [
            attrs.get("chat_id"),
            params.get("chatId"),
            meta_params.get("chatId"),
        ]
        if isinstance(state, dict):
            messages = state.get("messages")
            if isinstance(messages, list) and len(messages) > 1:
                candidates.append(messages[1])

        for value in candidates:
            if value:
                # Include skill_name in scope to isolate different skills on same chat
                # e.g., "chat:123:product_research_chat" vs "chat:123:product_lister_chat"
                if skill_name:
                    return f"chat:{value}:{skill_name}"
                return f"chat:{value}"
    except Exception:
        pass
    return f"node:{node_name}"


def cleanup_stale_browser_sessions() -> None:
    """Remove dead sessions from cached_browser_sessions in a thread-safe way.

    Call this after task cancellation to prevent zombie sessions from being
    reused by subsequent tasks. Replicates the CDP WebSocket closed-check from
    is_session_alive() but iterates the cache dict safely.
    """
    _lock = threading.Lock()
    with _lock:
        stale_keys = []
        for scope_key, session in cached_browser_sessions.items():
            try:
                cdp_client = getattr(session, '_cdp_client_root', None) or getattr(session, 'cdp_client_root', None)
                if cdp_client:
                    ws = getattr(cdp_client, 'ws', None) or getattr(cdp_client, 'websocket', None)
                    if ws is not None and (getattr(ws, 'closed', False) or getattr(ws, '_closed', False)):
                        stale_keys.append(scope_key)
            except Exception:
                pass
        for key in stale_keys:
            cached_browser_sessions.pop(key, None)
            logger.debug(f"[cleanup_stale_browser_sessions] Removed dead session: {key}")


async def _safe_stop_browser_session(session: Any) -> None:
    if session is None:
        return
    try:
        stop = getattr(session, "stop", None)
        if stop is not None:
            result = stop()
            if hasattr(result, "__await__"):
                await asyncio.wait_for(result, timeout=5.0)
            return
    except Exception:
        pass
    try:
        close = getattr(session, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await asyncio.wait_for(result, timeout=5.0)
    except Exception:
        pass


def invalidate_browser_session_for_recovery(
    session: Any,
    *,
    reason: str,
    stop_worker: bool = True,
) -> bool:
    if session is None:
        return False
    removed = False
    removed_keys: list[str] = []
    try:
        old_focus = getattr(session, "agent_focus_target_id", None)
    except Exception:
        old_focus = None
    for key, cached in list(cached_browser_sessions.items()):
        if cached is session:
            if old_focus:
                last_known_focus_target_ids[key] = old_focus
            cached_browser_sessions.pop(key, None)
            removed_keys.append(key)
            removed = True
    try:
        _cached_passive_agents.pop(id(session), None)
    except Exception:
        pass
    for key in removed_keys:
        try:
            cached_bu_agents.pop(key, None)
        except Exception:
            pass
    try:
        setattr(session, "_ecan_force_recreate", True)
        setattr(session, "_ecan_recovery_reason", reason)
    except Exception:
        pass
    if removed:
        logger.warning(
            f"[BrowserAutomation] Invalidated cached BrowserSession for recovery "
            f"reason={reason!r} keys={removed_keys}"
        )
    try:
        loop = None
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.create_task(_safe_stop_browser_session(session))
    except Exception:
        pass
    if stop_worker:
        try:
            from agent.ec_skills.llm_utils.llm_utils import stop_persistent_worker_threads_containing
            for key in removed_keys:
                suffix = re.sub(r"[^\w\-]+", "_", key)
                stopped = stop_persistent_worker_threads_containing(suffix)
                if stopped:
                    logger.warning(
                        f"[BrowserAutomation] Stopped persistent worker(s) "
                        f"for recovered scope key={key!r}: {stopped}"
                    )
        except Exception:
            pass
    return removed


def release_browser_cache_pressure(reason: str, aggressive: bool = False) -> int:
    removed = 0
    keys = list(cached_browser_sessions.keys())
    if not aggressive:
        keys = [key for key in keys if not key.startswith("chat:")]
    for key in keys:
        session = cached_browser_sessions.get(key)
        if session is None:
            continue
        if invalidate_browser_session_for_recovery(
            session,
            reason=reason,
            stop_worker=aggressive,
        ):
            removed += 1
    if aggressive:
        try:
            cached_bu_agents.clear()
        except Exception:
            pass
    return removed


def patch_browser_session_lifecycle_debug(session, source: str) -> None:
    """Attach one-time debug hooks to the live BrowserSession/CDP client."""
    try:
        if session is None:
            return

        _debug_scope_key = getattr(session, "_ecan_browser_scope_key", "")
        _cached_for_scope = cached_browser_sessions.get(_debug_scope_key) if _debug_scope_key else None

        logger.info(
            f"[BrowserAutomation][LifecycleDebug] Patch attempt source={source} "
            f"session_obj={id(session)} cached_obj={id(_cached_for_scope) if _cached_for_scope else 'none'} "
            f"same_as_cached={session is _cached_for_scope} scope={_debug_scope_key or 'unscoped'}"
        )

        if not getattr(session, "_ecan_lifecycle_debug_patched", False):
            _orig_reset = getattr(session, "reset", None)
            if _orig_reset:
                async def _debug_reset(*a, **kw):
                    logger.warning(
                        "[BrowserAutomation][LifecycleDebug] BrowserSession.reset() called.\n"
                        + "".join(traceback.format_stack(limit=20))
                    )
                    return await _orig_reset(*a, **kw)
                session.reset = _debug_reset

            _orig_reconnect = getattr(session, "reconnect", None)
            if _orig_reconnect:
                async def _debug_reconnect(*a, **kw):
                    logger.warning(
                        "[BrowserAutomation][LifecycleDebug] BrowserSession.reconnect() called.\n"
                        + "".join(traceback.format_stack(limit=20))
                    )
                    return await _orig_reconnect(*a, **kw)
                session.reconnect = _debug_reconnect

            _orig_auto_reconnect = getattr(session, "_auto_reconnect", None)
            if _orig_auto_reconnect:
                async def _debug_auto_reconnect(*a, **kw):
                    logger.warning(
                        "[BrowserAutomation][LifecycleDebug] BrowserSession._auto_reconnect() called.\n"
                        + "".join(traceback.format_stack(limit=20))
                    )
                    return await _orig_auto_reconnect(*a, **kw)
                session._auto_reconnect = _debug_auto_reconnect

            setattr(session, "_ecan_lifecycle_debug_patched", True)
            logger.info("[BrowserAutomation] Patched browser session lifecycle debug hooks")

        _cdp_root = getattr(session, "_cdp_client_root", None)
        if _cdp_root is not None:
            logger.info(
                f"[BrowserAutomation][LifecycleDebug] CDP root present source={source} "
                f"cdp_obj={id(_cdp_root)} patched={getattr(_cdp_root, '_ecan_debug_patched', False)}"
            )
        else:
            logger.info(f"[BrowserAutomation][LifecycleDebug] No CDP root yet source={source}")

        if _cdp_root and hasattr(_cdp_root, "stop") and not getattr(_cdp_root, "_ecan_debug_patched", False):
            _orig_cdp_stop = _cdp_root.stop

            async def _debug_cdp_stop(*a, **kw):
                logger.warning(
                    "[BrowserAutomation][LifecycleDebug] CDPClient.stop() called.\n"
                    + "".join(traceback.format_stack(limit=20))
                )
                return await _orig_cdp_stop(*a, **kw)

            _cdp_root.stop = _debug_cdp_stop
            setattr(_cdp_root, "_ecan_debug_patched", True)
            logger.info("[BrowserAutomation] Patched CDPClient.stop lifecycle debug hook")
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Failed to patch browser lifecycle debug hooks: {exc}")


# ─── Heavy lift: get_or_create_browser_session ───────────────────────

async def get_or_create_browser_session(
    mainwin,
    state: dict | None = None,
    calling_agent_id: str | None = None,
    *,
    ctx: Any,
):
    """Get or create browser session based on node editor settings.

    The 13 closure refs from the original are now sourced via:
      * ``ctx.node_name`` / ``ctx.browser_driver_setting`` /
        ``ctx.browser_type_setting`` / ``ctx.cdp_port_setting`` /
        ``ctx.downloads_path`` / ``ctx.node_profile`` — settings
      * Module-level helpers (``resolve_browser_scope_key``,
        ``is_session_started``, ``is_session_alive``,
        ``get_browser_profile_settings``)
      * Module-level state dicts (``cached_browser_sessions``,
        ``last_known_focus_target_ids``, ``browser_start_locks``,
        ``MAX_BROWSER_CACHE_SIZE``) and the build_node module-level
        ``_cached_passive_agents`` (imported at module top).
    """
    from gui.manager.browser_manager import BrowserManager, BrowserType, BrowserStatus

    browser_scope_key = resolve_browser_scope_key(
        state,
        node_name=ctx.node_name,
        skill_name=getattr(ctx, "skill_name", ""),
    )
    isolate_scope = browser_scope_key.startswith("chat:")
    _cached_browser_session = cached_browser_sessions.get(browser_scope_key)
    _last_known_focus_target_id = last_known_focus_target_ids.get(browser_scope_key)

    # Return cached session if still valid AND event bus alive
    if (
        _cached_browser_session is not None
        and not getattr(_cached_browser_session, "_ecan_force_recreate", False)
        and is_session_alive(_cached_browser_session)
    ):
        logger.debug(f"[BrowserAutomation] Reusing cached browser session: {_cached_browser_session.id}")
        return _cached_browser_session

    # Invalidate stale cache - but preserve the focus target
    if _cached_browser_session is not None:
        old_focus = getattr(_cached_browser_session, 'agent_focus_target_id', None)
        if old_focus:
            _last_known_focus_target_id = old_focus
            last_known_focus_target_ids[browser_scope_key] = old_focus
            logger.info(f"[BrowserAutomation] Saved focus target from dying session: ...{old_focus[-4:]}")
        old_sid = id(_cached_browser_session)
        old_pa = _cached_passive_agents.get(old_sid)
        if old_pa and hasattr(old_pa, '_last_focus_target_id') and old_pa._last_focus_target_id:
            _last_known_focus_target_id = old_pa._last_focus_target_id
            last_known_focus_target_ids[browser_scope_key] = old_pa._last_focus_target_id
            logger.info(f"[BrowserAutomation] Saved focus target from PassiveAgent: ...{old_pa._last_focus_target_id[-4:]}")
        logger.info(f"[BrowserAutomation] Cached session {_cached_browser_session.id} is stale (event bus dead), creating new one")
        _cached_passive_agents.pop(old_sid, None)
        cached_browser_sessions.pop(browser_scope_key, None)

    profile_settings = get_browser_profile_settings(ctx.node_profile)
    if profile_settings:
        log_msg = f"[BrowserAutomation] Using profile: {profile_settings.get('name', ctx.node_profile)}"
        logger.info(log_msg)
        send_skill_editor_log("log", log_msg)

    log_msg = f"[BrowserAutomation] Getting browser session: browser={ctx.browser_type_setting}, driver={ctx.browser_driver_setting}, cdp_port_config={ctx.cdp_port_setting}"
    logger.debug(log_msg)
    send_skill_editor_log("log", log_msg)
    if not hasattr(mainwin, 'browser_manager') or mainwin.browser_manager is None:
        # Read browser pool config from general settings if available
        _bm_slots = None
        _bm_max_agents = 0
        try:
            _gs = getattr(getattr(mainwin, 'config_manager', None), 'general_settings', None)
            if _gs:
                _bm_slots = _gs.browser_slots or None
                _bm_max_agents = _gs.browser_max_agents_per_instance or 0
        except Exception:
            pass
        mainwin.browser_manager = BrowserManager(
            default_webdriver_path=mainwin.getWebDriverPath(),
            slots=_bm_slots,
            max_agents_per_browser=_bm_max_agents,
        )

    browser_manager: BrowserManager = mainwin.browser_manager

    browser_type_map = {
        'new chromium': BrowserType.CHROME,
        'existing chrome': BrowserType.CHROME,
        'ads power': BrowserType.ADSPOWER,
        'adspower': BrowserType.ADSPOWER,
        'ziniao': BrowserType.CHROME,
        'multi-login': BrowserType.CHROME,
    }
    browser_type = browser_type_map.get(ctx.browser_type_setting, BrowserType.CHROME)

    # Runtime browser-slot resolution: task state (assigned by scheduler
    # or auto-assigned by BrowserManager) takes priority over skill config.
    _state_cdp_port = ""
    _state_browser_profile = ""
    _state_slot_id = ""
    try:
        _slot_state = state if isinstance(state, dict) else {}
        _slot_attrs = _slot_state.get("attributes", {}) if isinstance(_slot_state, dict) else {}
        _slot_params = _slot_attrs.get("params", {}) if isinstance(_slot_attrs, dict) else {}
        # Check state root, then attributes, then params for cdp_port
        _state_cdp_port = str(
            _slot_state.get("cdp_port")
            or _slot_attrs.get("cdp_port")
            or _slot_params.get("cdp_port")
            or ""
        ).strip()
        _state_browser_profile = str(
            _slot_state.get("browser_profile")
            or _slot_attrs.get("browser_profile")
            or _slot_params.get("browser_profile")
            or ""
        ).strip()
        _state_slot_id = str(
            _slot_state.get("browser_slot_id")
            or _slot_attrs.get("browser_slot_id")
            or _slot_params.get("browser_slot_id")
            or ""
        ).strip()
        if _state_cdp_port or _state_slot_id:
            logger.info(
                f"[BrowserAutomation] Runtime browser slot from state: "
                f"cdp_port={_state_cdp_port or '(auto)'}, "
                f"slot_id={_state_slot_id or '(none)'}, "
                f"profile={_state_browser_profile or '(default)'}"
            )
    except Exception as _slot_err:
        logger.debug(f"[BrowserAutomation] Browser slot resolution from state failed: {_slot_err}")

    # If we have a slot_id but no cdp_port, resolve port from the slot
    if _state_slot_id and not _state_cdp_port:
        try:
            _slot_obj = browser_manager.get_slot(_state_slot_id)
            if _slot_obj:
                _state_cdp_port = str(_slot_obj.cdp_port)
                if not _state_browser_profile and _slot_obj.profile:
                    _state_browser_profile = _slot_obj.profile
                logger.info(f"[BrowserAutomation] Resolved slot {_state_slot_id} → cdp_port={_state_cdp_port}")
        except Exception:
            pass

    # Priority: runtime slot > skill-editor config > default 9228
    # Special values: "auto" or "0" → cdp_port=0, which tells
    # BrowserManager to auto-select from its port pool.
    _cdp_source = "default"
    if _state_cdp_port:
        _cdp_source = "state"
        if _state_cdp_port.lower() == "auto" or _state_cdp_port == "0":
            cdp_port = 0
        elif _state_cdp_port.isdigit():
            cdp_port = int(_state_cdp_port)
        else:
            cdp_port = 9228
    elif ctx.cdp_port_setting:
        _cdp_source = "config"
        if ctx.cdp_port_setting.lower() == "auto" or ctx.cdp_port_setting == "0":
            cdp_port = 0
        elif ctx.cdp_port_setting.isdigit():
            cdp_port = int(ctx.cdp_port_setting)
        else:
            cdp_port = 9228
    else:
        cdp_port = 9228
    logger.info(
        f"[BrowserAutomation] Resolved cdp_port={'auto' if cdp_port == 0 else cdp_port} "
        f"(from={_cdp_source})"
    )

    _agent_id_base = calling_agent_id or getattr(mainwin, 'current_agent_id', 'default_agent') or 'default_agent'
    _node_agent_id = (
        f"{_agent_id_base}:{ctx.node_name}:{browser_scope_key}"
        if isolate_scope else f"{_agent_id_base}:{ctx.node_name}"
    )
    _connect_webdriver = str(ctx.browser_driver_setting or "").strip().lower() != "native"
    logger.info(
        f"[BrowserAutomation] Browser attach plan: driver={ctx.browser_driver_setting} "
        f"connect_webdriver={_connect_webdriver} cdp_port={cdp_port}"
    )
    auto_browser = browser_manager.acquire_browser(
        agent_id=_node_agent_id,
        task=(f"browser_automation_{ctx.node_name}:{browser_scope_key}" if isolate_scope else f"browser_automation_{ctx.node_name}"),
        browser_type=browser_type,
        cdp_port=cdp_port,
        webdriver_path=mainwin.getWebDriverPath(),
        downloads_path=ctx.downloads_path,
        profile=ctx.node_profile or _state_browser_profile,
        connect_webdriver=_connect_webdriver,
    )

    if auto_browser and auto_browser.status != BrowserStatus.ERROR:
        # When cdp_port was auto-assigned (0), update to the actual port
        # so downstream locks and logging use the real value.
        if cdp_port == 0 and auto_browser.cdp_port:
            cdp_port = auto_browser.cdp_port
            logger.info(f"[BrowserAutomation] Auto-assigned browser on cdp_port={cdp_port}")

        if auto_browser.webdriver:
            mainwin.setWebDriver(auto_browser.webdriver)

        if ctx.browser_driver_setting == 'native' and auto_browser.browser_session:
            log_msg = f"[BrowserAutomation] Starting browser session: {auto_browser.browser_session.id}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

            # Each agent gets its own independent CDP connection via
            # browser_session.start().  No donor/shared-session pattern — sharing
            # session_manager/event_bus causes tab contamination when multiple
            # agents run concurrently on the same Chrome.
            fast_attach_ready = False
            if isolate_scope and ctx.browser_type_setting == 'existing chrome':
                try:
                    sm = getattr(auto_browser.browser_session, "session_manager", None)
                    eb = getattr(auto_browser.browser_session, "event_bus", None)
                    targets = sm.get_all_targets() if sm and hasattr(sm, "get_all_targets") else {}
                    page_targets = [
                        tid for tid, t in (targets or {}).items()
                        if getattr(t, "target_type", "") in ("page", "tab")
                    ]
                    if eb is not None and page_targets:
                        fast_attach_ready = True
                        setattr(auto_browser.browser_session, "_ecan_fast_attach_ready", True)
                        logger.info(
                            f"[BrowserAutomation] Fast-attach ready (own session already started) "
                            f"{auto_browser.browser_session.id}: page_targets={len(page_targets)} "
                            f"scope={browser_scope_key}"
                        )
                except Exception as _fast_attach_exc:
                    logger.warning(
                        f"[BrowserAutomation] Fast-attach probe failed for session "
                        f"{auto_browser.browser_session.id}: {_fast_attach_exc}"
                    )

            if not is_session_started(auto_browser.browser_session) and not fast_attach_ready:
                start_lock = browser_start_locks.get(cdp_port)
                if start_lock is None:
                    start_lock = threading.Lock()
                    browser_start_locks[cdp_port] = start_lock

                logger.info(
                    f"[BrowserAutomation] Waiting for startup lock on cdp_port={cdp_port} "
                    f"scope={browser_scope_key} session={auto_browser.browser_session.id}"
                )
                _lock_acquired = await asyncio.to_thread(
                    lambda: start_lock.acquire(timeout=BROWSER_START_LOCK_TIMEOUT)
                )
                if not _lock_acquired:
                    logger.error(
                        f"[BrowserAutomation] Startup lock timed out after {BROWSER_START_LOCK_TIMEOUT}s on cdp_port={cdp_port} "
                        f"scope={browser_scope_key}; cannot start independent session"
                    )
                else:
                    try:
                        if not is_session_started(auto_browser.browser_session):
                            logger.info(
                                f"[BrowserAutomation] Acquired startup lock on cdp_port={cdp_port}; "
                                f"starting session {auto_browser.browser_session.id} scope={browser_scope_key}"
                            )
                            _start_task = asyncio.create_task(auto_browser.browser_session.start())
                            try:
                                await asyncio.wait_for(
                                    asyncio.shield(_start_task), timeout=BROWSER_SESSION_START_TIMEOUT
                                )
                            except asyncio.TimeoutError:
                                logger.warning(
                                    f"[BrowserAutomation] browser_session.start() timed out after {BROWSER_SESSION_START_TIMEOUT}s "
                                    f"for {auto_browser.browser_session.id} scope={browser_scope_key}; "
                                    f"will retry once"
                                )
                                # Retry once — transient CDP handshake failures can occur
                                # when multiple sessions connect in quick succession.
                                try:
                                    _start_task2 = asyncio.create_task(auto_browser.browser_session.start())
                                    await asyncio.wait_for(
                                        asyncio.shield(_start_task2), timeout=BROWSER_SESSION_START_TIMEOUT
                                    )
                                    logger.info(
                                        f"[BrowserAutomation] Retry start() succeeded for "
                                        f"{auto_browser.browser_session.id}"
                                    )
                                except (asyncio.TimeoutError, Exception) as _retry_err:
                                    logger.error(
                                        f"[BrowserAutomation] Retry start() also failed for "
                                        f"{auto_browser.browser_session.id}: {_retry_err}"
                                    )
                        else:
                            logger.info(
                                f"[BrowserAutomation] Session already started after waiting for lock: "
                                f"{auto_browser.browser_session.id}"
                            )
                    finally:
                        try:
                            start_lock.release()
                        except Exception:
                            pass
            elif fast_attach_ready:
                logger.info(
                    f"[BrowserAutomation] Skipped browser_session.start() (already started): "
                    f"{auto_browser.browser_session.id} scope={browser_scope_key}"
                )
            log_msg = f"[BrowserAutomation] Browser session started!"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)
            try:
                setattr(auto_browser.browser_session, "_ecan_browser_scope_key", browser_scope_key)
            except Exception:
                pass

            if _last_known_focus_target_id:
                try:
                    from browser_use.browser.events import SwitchTabEvent
                    cur_focus = auto_browser.browser_session.agent_focus_target_id
                    if cur_focus != _last_known_focus_target_id:
                        await auto_browser.browser_session.event_bus.dispatch(
                            SwitchTabEvent(target_id=_last_known_focus_target_id)
                        )
                        logger.info(
                            f"[BrowserAutomation] Restored focus from ...{cur_focus[-4:] if cur_focus else 'None'} "
                            f"to ...{_last_known_focus_target_id[-4:]} after session recreation"
                        )
                    else:
                        logger.debug(f"[BrowserAutomation] Focus already on correct target: ...{cur_focus[-4:]}")
                except Exception as e:
                    logger.warning(f"[BrowserAutomation] Failed to restore focus after session recreation: {e}")

            # Evict oldest entries if cache exceeds max size
            if len(cached_browser_sessions) >= MAX_BROWSER_CACHE_SIZE:
                evicted = 0
                for _key in list(cached_browser_sessions.keys()):
                    if _key == browser_scope_key:
                        continue
                    # Only evict entries for non-chat scopes (chat sessions should be stable)
                    if not _key.startswith("chat:"):
                        _old_session = cached_browser_sessions.pop(_key, None)
                        last_known_focus_target_ids.pop(_key, None)
                        # Remove from insertion order tracking
                        if _key in _cached_browser_sessions_insertion_order:
                            _cached_browser_sessions_insertion_order.remove(_key)
                        if _old_session is not None:
                            _cached_passive_agents.pop(id(_old_session), None)
                        evicted += 1
                        if evicted >= 2:  # Remove up to 2 entries per insertion
                            break
            
            # Track insertion order for FIFO eviction
            if browser_scope_key not in _cached_browser_sessions_insertion_order:
                _cached_browser_sessions_insertion_order.append(browser_scope_key)
            
            cached_browser_sessions[browser_scope_key] = auto_browser.browser_session
            return auto_browser.browser_session

        return auto_browser
    else:
        error_msg = auto_browser.last_error if auto_browser else "Unknown error"
        logger.error(f"[BrowserAutomation] Failed to acquire browser: {error_msg}")
        return None
