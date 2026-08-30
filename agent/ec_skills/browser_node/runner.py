"""``BrowserUseRunner`` — async orchestrator for the browser-automation node.

Replaces the inner closure ``_run_browser_use`` from
``build_browser_automation_node``.  Splits the four execution paths
into dedicated methods:

* :meth:`run` — top-level orchestrator (mustache resolution, runtime
  input injection, event extraction, task assembly, early hooks,
  assignment scope, mode dispatch).

* :meth:`_run_skill_passive_step` — passive ``skill_passive_step``:
  bypass browser automation, execute MCP tools directly, publish step
  result to cloud.  Used by the cloud orchestrator for non-browser
  skill steps.

* :meth:`_run_browser_passive_step` — passive ``browser_use_passive_step``:
  use ``PassiveAgent`` (no LLM, no message history) to execute action
  dicts and return DOM snapshot to cloud.

* :meth:`_run_cloud_agent` — full cloud-agent path: LLM lives in
  cloud worker (or local), browser actions sent to local executor
  via ``CloudAgent`` + passive transport.

* :meth:`_run_full_local_agent` — full local browser-use ``Agent``
  with custom controller, hook bundles, event monitors, step
  monkey-patches, and ``agent.run()``.  This is the heaviest path.

State held by this class (one instance per compiled node):

* ``cfg``         — :class:`NodeConfig` (build-time settings).
* ``sessions``    — :class:`BrowserSessionManager` (browser cache).
* ``prompts``     — pre-resolved system + user prompts (build-time).
* ``cached_bu_agents`` — per-scope cache of ``browser_use.Agent``
  instances (~860 MB savings per round when reused).

Module-level state still lives in ``build_node.py`` for now:
``_first_invocation_done``, ``_passive_steps_processed``, etc.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from typing import Any

from utils.logger_helper import logger_helper as logger

# Memoizes BrowserProfile() instances keyed by their constructor inputs.
# See note in build_browser_profile(); empirically saves ~10 s per node entry
# on Windows after the first call. Process-lifetime cache — fine because the
# profile is a static template and the inputs (user_data_dir, flags) don't
# change between turns on the same skill node.
_BROWSER_PROFILE_CACHE: dict = {}

from agent.ec_skills.browser_node.config import NodeConfig
from agent.ec_skills.browser_node.session import BrowserSessionManager
from agent.ec_skills.browser_node.events import (
    EventSnapshot,
    extract_event_snapshot,
    fetch_event_items,
    compact_items,
    filter_actionable,
    render_triggering_event_block,
)
from agent.ec_skills.browser_node.hooks import (
    build_hook_context,
    invoke_early_hooks,
    invoke_prompt_build_hooks,
    invoke_late_hooks,
    PromptBuildOutcome,
)
from agent.ec_skills.browser_node.agent import reset_bu_agent_for_next_round


# Re-imports from build_node — these will move into this package
# when Phase 6 collapses the giant function.
# Phase 6.5 (2026-04-24): context dataclasses live in their own module
# now to break the runner→build_node import cycle.
from agent.ec_skills.browser_node.contexts import (
    BrowserUseHookContext,
    PromptBuildContext,
    _AssignmentContext,
)

# Phase 6.7 (2026-04-24): browser-session helpers + state dicts moved
# out of build_browser_automation_node into a dedicated module.
from agent.ec_skills.browser_node import build_helpers as _bh

from agent.ec_skills.build_node import (
    _resolve_mustache_template,
    _SafeFormatDict,
    _parse_json_input,
    _log_browser_use_result_summary,
    send_skill_editor_log,
    get_traceback,
    THINKING_SUPPRESSION_INSTRUCTION,
    # Module-level state used by the lifted BrowserRunSession (Phase 6.3).
    _first_invocation_done,
    _passive_steps_lock,
    _passive_steps_processed,
    _DISPATCH_INFLIGHT_TTL_S,
    _is_dispatch_inflight,
    _mark_dispatch_inflight,
    _clear_dispatch_inflight,
    # Phase 6.7: module-level helpers + state previously plumbed via RunContext.
    _normalize_dispatch_identity_key,
    _resolve_template,
    _cached_passive_agents,
    _dispatch_state_by_agent,
)


# ─── Phase 6 RunContext (2026-04-24) ─────────────────────────────────
# Frozen dataclass capturing every build-scope closure ref needed by
# ``_BrowserRunSession`` (currently nested inside
# :func:`agent.ec_skills.build_node.build_browser_automation_node`).
#
# Constructed *once* per compiled node at the bottom of
# ``build_browser_automation_node`` (after every helper / setting is
# resolved) and passed to each ``_BrowserRunSession.__init__`` call.
# Lifecycle = lifetime of the compiled LangGraph node; reused across
# every pend-event-loop iteration.
#
# Phase-6 lift target: once the class body is ported to use
# ``self.ctx.*`` for every name listed here, ``_BrowserRunSession``
# becomes portable and can be moved verbatim to this module.
#
# Categorization of fields:
#   * "settings"  — immutable build-time values from the node JSON +
#                   NodeConfig + env / Settings defaults.
#   * "helpers"   — callables closed over the outer function's scope.
#   * "state"     — mutable dicts shared with the build scope (refs,
#                   not copies — they outlive the run).
#   * "hooks"     — registered lifecycle-hook callables.
#   * "monitors"  — parsed event-monitor configs.
from dataclasses import dataclass, field
from typing import Callable


# mt054B (2026-05-31): bump CDP WebSocket ping_interval / ping_timeout.
#
# Chrome's CDP WebSocket pings every ~20s by default (websockets library
# default ping_interval=20, ping_timeout=20).  Under heavy event-loop
# load, our app misses the ping/pong exchange → Chrome closes the
# connection with code 1011 ("keepalive ping timeout") → browser-use's
# SessionManager clears all owned data → reconnect storm → session_manager
# view goes empty → mt053K's recovery fires but only catches the
# downstream symptom.  Customer 1-to-7 trace 2026-05-31 12:02→12:09:
# 8 reconnect cycles in 7 minutes, 76s + 194s EventMonitor heartbeat
# gaps proving the event loop was completely frozen.
#
# Bumping ping_interval to 60s and ping_timeout to 120s gives us 2 min of
# event-loop grace before Chrome decides we're dead — enough to absorb
# transient blocks (GC pauses, big JSON parses, etc.) without losing the
# CDP attachment.  Pair this with mt054A (find the blocker) for the
# proper structural fix.
#
# Monkey-patch is one-shot at module import.  Sets a sentinel attribute
# to avoid double-patching if runner.py is re-imported (test isolation).
_MT054B_PING_INTERVAL_S: float = 60.0
_MT054B_PING_TIMEOUT_S: float = 120.0


def _mt054b_install_ws_ping_patch() -> None:
    try:
        import cdp_use.client as _cdp_client_mod
    except Exception:
        return
    if getattr(_cdp_client_mod, "_mt054b_ws_ping_patched", False):
        return
    _ws_mod = getattr(_cdp_client_mod, "websockets", None)
    if _ws_mod is None:
        return
    _orig_connect = getattr(_ws_mod, "connect", None)
    if _orig_connect is None:
        return

    async def _patched_connect(*args, **kwargs):
        kwargs.setdefault("ping_interval", _MT054B_PING_INTERVAL_S)
        kwargs.setdefault("ping_timeout", _MT054B_PING_TIMEOUT_S)
        return await _orig_connect(*args, **kwargs)

    _ws_mod.connect = _patched_connect
    setattr(_cdp_client_mod, "_mt054b_ws_ping_patched", True)
    try:
        logger.info(
            f"[mt054B] CDP WebSocket ping patch installed: "
            f"ping_interval={_MT054B_PING_INTERVAL_S}s, "
            f"ping_timeout={_MT054B_PING_TIMEOUT_S}s "
            f"(was 20s/20s; absorbs event-loop blocks up to ~2 min before "
            f"Chrome closes the connection)"
        )
    except Exception:
        pass


_mt054b_install_ws_ping_patch()


@dataclass
class RunContext:
    """Per-node closure-capture container for ``_BrowserRunSession``.

    Frozen-by-convention: callers should treat fields as read-only.
    The mutable dict / list fields are *shared with the build scope by
    reference*, not copied, so cache mutations performed by helpers
    persist across runs.

    Field naming preserves the original closure-name underscores
    (``_resolve_browser_scope_key``) to keep the Phase-6 mass-rewrite
    a pure ``X`` → ``self.ctx.X`` operation with no name collisions.
    """

    # ── Identity / metadata (4) ─────────────────────────────────
    node_name: str
    skill_name: str
    owner: str
    inputs: dict

    # ── Node-editor settings (23) ───────────────────────────────
    # Phase 6.7 added cdp_port_setting + downloads_path so the lifted
    # ``get_or_create_browser_session`` can reach them via ctx.
    node_llm_provider: Any
    node_model_name: Any
    node_use_vision: bool
    node_use_thinking: bool
    node_max_actions_per_step: Any
    node_dom_limit: Any
    node_dom_focus_selector: Any
    node_profile: Any
    node_headless: bool
    node_keep_browser_alive: bool
    node_max_steps: Any
    node_timeout_seconds: Any
    enable_judge_setting: bool
    enable_stealth_setting: bool
    enable_platform_profile_setting: bool
    use_pc_chrome_setting: bool
    user_data_dir_setting: str
    system_prompt_id: Any
    user_prompt_id: Any
    loop_history_mode: Any
    privacy_strategy_setting: str
    run_environment_setting: str
    event_monitor_done_policy: str
    browser_type_setting: str
    browser_driver_setting: str
    cdp_port_setting: str
    downloads_path: Any
    actionable_field: Any

    # ── Lifecycle hook registries (3) ───────────────────────────
    before_browser_session_setup_hooks: list
    before_prompt_build_hooks: list
    before_browser_use_run_hooks: list

    # ── Event monitor configs (1) ───────────────────────────────
    event_monitor_configs: list = field(default_factory=list)

    # Phase 6.7 (2026-04-24) dropped 18 fields:
    #   * 9 helpers — now in browser_node/build_helpers.py
    #   * 5 state dicts — now module-level in build_helpers.py
    #     (cached_browser_sessions, cached_bu_agents,
    #     last_known_focus_target_ids) or already module-level in
    #     build_node.py (cached_passive_agents, dispatch_state_by_agent)
    #   * 4 module-level callables (normalize_dispatch_identity_key,
    #     resolve_template) and module-level state already importable
    #     from build_node directly
    #   * max_browser_cache_size — now MAX_BROWSER_CACHE_SIZE in
    #     build_helpers.py


# ``BrowserUseRunner`` (815 lines) deleted 2026-04-24 — fully inlined into
# module-level free functions (``_publish_passive_step_result``,
# ``build_local_llm`` + ``_build_local_llm_from_node_config_impl``,
# ``run_cloud_agent`` + 4 cloud helpers).  See ``REFACTOR_ROADMAP.md``.


# ─────────────────────────────────────────────────────────────────────
# Lambda-proxy decision helpers (live in build_node.py).  Re-imported
# at call site to avoid the import cycle.
# ─────────────────────────────────────────────────────────────────────


def _front_desk_has_pending_replies() -> bool:
    """Yield-on-pending-reply check (Fix 12 Option A, 2026-05-13).

    Returns True if any registered TaskRunner has Q&A reply payloads
    queued in its chat_message buffer.  Used by ``make_step_patch``'s
    yield-check to exit the front-desk's browser-use loop early when
    Q&A bots have already delivered answers waiting to be typed —
    instead of letting the loop chew through all 20 customer scrapes
    while replies pile up unconsumed.

    Safe defaults: any exception → False (don't yield, fall through to
    normal flow).  Always called from ``make_step_patch`` which catches
    its own exceptions so a slow registry lookup can't block the step.
    """
    try:
        # Lazy import to avoid a startup circular dep (ec_tasks.runner
        # imports browser_node.runner indirectly via the build chain).
        from agent.ec_tasks.runner import (
            TaskRunnerRegistry as _TRR,
            _has_queued_live_chat_response_payload as _has_replies,
        )
    except Exception:
        return False
    try:
        # ``TaskRunnerRegistry`` doesn't expose an iter; we walk its
        # internal weakref dict defensively.  Any task with live-chat
        # response payloads in queue triggers — typically only the
        # live-chat reception task accumulates these but checking
        # all tasks is cheaper than name-matching and robust to renames.
        registry_obj = getattr(_TRR, "_runners", None) or getattr(_TRR, "_registry", None)
        if registry_obj is None:
            return False
        # Snapshot to a list (the dict may be a WeakValueDictionary).
        try:
            tasks_iter = list(registry_obj.values())
        except Exception:
            tasks_iter = list(registry_obj)
        for task in tasks_iter:
            try:
                if _has_replies(task):
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def _should_use_proxy(inputs: dict) -> bool:
    """Re-export of the decision helper from build_node."""
    from agent.ec_skills.build_node import _should_use_proxy as _impl

    return _impl(inputs)


def _get_proxy_config() -> dict | None:
    from agent.ec_skills.build_node import _get_proxy_config as _impl

    return _impl()


# ─────────────────────────────────────────────────────────────────────
# Module-level passive-path entry points (callable without a runner
# instance — used by ``build_node.py`` while the in-place extraction
# is in progress and the runner orchestrator is not yet wired in).
# ─────────────────────────────────────────────────────────────────────

async def run_skill_passive_step(passive_cmd: dict, mainwin: Any) -> dict:
    """Execute MCP tools directly, publish step result, return ``passive=True``.

    Bypasses all browser automation.  Used by the cloud orchestrator
    when a skill step does not need browser DOM — just invoke the
    named MCP tool with the supplied ``tool_input`` and return the
    result (still wrapped in a ``PassiveBrowserStepResult`` for
    protocol uniformity).
    """
    from agent.mcp.local_client import mcp_call_tool as _mcp_call_tool

    logger.info("[PassiveMode] skill_passive_step — executing MCP tools directly")
    t0 = time.perf_counter()
    actions = passive_cmd.get("actions", []) if isinstance(passive_cmd, dict) else []
    stop_on_error = (
        bool(passive_cmd.get("stop_on_error", True))
        if isinstance(passive_cmd, dict)
        else True
    )

    results: list[dict] = []
    errors: list[str] = []
    for idx, act in enumerate(actions):
        if not isinstance(act, dict):
            continue
        params = act.get("mcp_tool", act)
        tool_name = params.get("tool", "")
        tool_input = params.get("tool_input", {})
        try:
            logger.info(f"[PassiveMode] MCP tool[{idx}]: {tool_name} input={tool_input}")
            res = await _mcp_call_tool(tool_name, tool_input)
            logger.info(f"[PassiveMode] MCP tool[{idx}] result: {res}")
            results.append({"extracted_content": str(res) if res else ""})
        except Exception as exc:
            msg = f"mcp_tool[{idx}] '{tool_name}' failed: {type(exc).__name__}: {exc}"
            logger.error(f"[PassiveMode] {msg}", exc_info=True)
            results.append({"error": msg})
            errors.append(msg)
            if stop_on_error:
                break

    payload = {
        "ok": not bool(errors),
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "actions": actions,
        "action_results": results,
        "errors": errors,
        "browser": {},
    }
    await _publish_passive_step_result(
        passive_cmd, payload, mainwin, label="skill"
    )
    return {"passive": True, **payload}


async def _publish_passive_step_result(
    passive_cmd: dict | None,
    payload: dict,
    mainwin: Any,
    *,
    label: str,
) -> None:
    """Publish a ``PassiveBrowserStepResult`` back to cloud.

    Free-function replacement for the original
    ``BrowserUseRunner._publish_passive_result`` static method (which is
    being phased out as part of the Phase-6 cleanup — see
    ``REFACTOR_ROADMAP.md``).
    """
    if not passive_cmd or not mainwin:
        return
    try:
        from agent.ec_skills.browser_use_extension.passive_utils import publish_step_result
        from agent.ec_skills.browser_use_extension.passive_protocol import (
            PassiveBrowserStepResult,
        )

        run_id = passive_cmd.get("run_id", "")
        step_id = passive_cmd.get("step_id", "")
        if not run_id or not step_id:
            return
        result = PassiveBrowserStepResult(
            run_id=run_id,
            step_id=step_id,
            ok=not bool(payload.get("errors")),
            elapsed_ms=int(payload.get("elapsed_ms") or 0),
            actions=payload.get("actions") or [],
            action_results=payload.get("action_results") or [],
            errors=payload.get("errors") or [],
            browser=payload.get("browser") or {},
        )
        http_endpoint = mainwin.getWanApiEndpoint()
        auth_token = mainwin.get_auth_token()
        client_id = mainwin.getAcctSiteID()
        logger.info(
            f"[{label}Passive] publish_step_result: client_id={client_id} "
            f"run_id={run_id} step_id={step_id}"
        )
        await publish_step_result(result, http_endpoint, auth_token, client_id)
        logger.info(f"[{label}Passive] Published step result to cloud")
        send_skill_editor_log("log", f"[{label}Passive] Published step result to cloud")
    except Exception as exc:
        logger.error(f"[{label}Passive] Failed to publish step result: {exc}")
        send_skill_editor_log("warning", f"[{label}Passive] Failed to publish: {exc}")


def _extract_passive_actions(state: dict | None, node_name: str) -> list:
    """Extract passive actions from any of 5 possible state paths.

    Priority order:
        1. ``state.tool_input.{node_name}.actions``
        2. ``state.tool_input.actions``
        3. ``state.browser_use_actions``
        4. ``state.attributes.passive_command.actions``
        5. ``state.attributes.passive_command_actions``
    """
    if not isinstance(state, dict):
        return []

    # 1 + 2: tool_input variants
    try:
        tool_input = state.get("tool_input")
        if isinstance(tool_input, dict):
            node_input = tool_input.get(node_name)
            if isinstance(node_input, dict) and isinstance(node_input.get("actions"), list):
                logger.debug(f"[PassiveMode] Found actions in tool_input.{node_name}.actions")
                return node_input.get("actions")
            if isinstance(tool_input.get("actions"), list):
                logger.debug("[PassiveMode] Found actions in tool_input.actions")
                return tool_input.get("actions")
    except Exception:
        pass

    # 3: browser_use_actions
    if isinstance(state.get("browser_use_actions"), list):
        logger.debug("[PassiveMode] Found actions in browser_use_actions")
        return state.get("browser_use_actions")

    # 4 + 5: attributes
    try:
        attrs = state.get("attributes", {}) or {}
        pc = attrs.get("passive_command")
        if isinstance(pc, dict) and isinstance(pc.get("actions"), list):
            logger.debug("[PassiveMode] Found actions in attributes.passive_command.actions")
            return pc.get("actions")
        if isinstance(attrs.get("passive_command_actions"), list):
            logger.debug("[PassiveMode] Found actions in attributes.passive_command_actions")
            return attrs.get("passive_command_actions")
    except Exception:
        pass

    return []


async def run_browser_passive_step(
    state: dict,
    mainwin: Any,
    *,
    get_browser_session,
    is_session_started,
    last_known_focus_target_id: str | None,
    last_known_focus_target_ids: dict,
    browser_scope_key: str,
    node_name: str,
    calling_agent_id: str | None,
    passive_agent_cache: dict,
) -> dict:
    """Execute action dicts via :class:`PassiveAgent` and publish the result.

    Dependency-injected helpers replace the original closure captures so
    this function is callable from either the runner or directly from
    ``build_node.py`` while the in-place extraction is in progress.

    Args:
        get_browser_session: ``async (mainwin, *, state, calling_agent_id) -> session``
        is_session_started: ``(session) -> bool``
        last_known_focus_target_id: focus target captured from a prior round (or ``None``).
        last_known_focus_target_ids: ``{scope_key: target_id}`` cache to update on success.
        browser_scope_key: scope key under which to record the post-run focus target.
        node_name: used by :func:`_extract_passive_actions`.
        calling_agent_id: forwarded to ``get_browser_session``.
        passive_agent_cache: ``{id(session): PassiveAgent}`` reuse map.
    """
    from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent
    from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller

    actions = _extract_passive_actions(state, node_name)
    logger.info(f"[PassiveMode] Extracted {len(actions)} actions from state")
    if not isinstance(actions, list):
        return {"error": "browser-use passive mode enabled but actions is not a list"}

    browser_session = await get_browser_session(
        mainwin, state=state, calling_agent_id=calling_agent_id
    )
    if not browser_session:
        return {"error": "browser-use passive mode: failed to acquire browser session"}

    if not is_session_started(browser_session):
        start_task = asyncio.create_task(browser_session.start())
        await start_task

    # Reuse PassiveAgent across loop iterations (keyed by browser_session id).
    sid = id(browser_session)
    pa = passive_agent_cache.get(sid)
    if pa is None:
        pa = PassiveAgent(
            browser_session=browser_session,
            tools=custom_controller,
            privacy_enabled=True,
        )
        if last_known_focus_target_id:
            pa._last_focus_target_id = last_known_focus_target_id
            logger.info(
                f"[PassiveMode] Transferred focus target ...{last_known_focus_target_id[-4:]} "
                f"to new PassiveAgent"
            )
        passive_agent_cache[sid] = pa
        logger.info(f"[PassiveMode] Created new PassiveAgent for session {sid}")
    else:
        logger.debug(f"[PassiveMode] Reusing cached PassiveAgent for session {sid}")

    # Resolve passive_command (for run_id/step_id and per-step settings).
    passive_cmd = None
    include_screenshot = False
    stop_on_error = True
    if isinstance(state, dict):
        attrs = state.get("attributes", {}) or {}
        passive_cmd = attrs.get("passive_command")
        if isinstance(passive_cmd, dict):
            include_screenshot = bool(passive_cmd.get("include_screenshot", False))
            stop_on_error = bool(passive_cmd.get("stop_on_error", True))

    payload: dict | None = None
    exec_error: Exception | None = None
    try:
        payload = await pa.execute_actions(
            actions=actions,
            stop_on_error=stop_on_error,
            include_screenshot=include_screenshot,
        )
        # Update focus target for next round.
        if getattr(pa, "_last_focus_target_id", None):
            last_known_focus_target_ids[browser_scope_key] = pa._last_focus_target_id
    except Exception as exc:
        exec_error = exc
        err = get_traceback(exc, "ErrorBuildBrowserAutomationNodePassive")
        logger.error(err)
        send_skill_editor_log("error", err)
        payload = {"error": str(err), "errors": [str(err)]}

    # Publish to cloud (even on error, so the cloud worker knows what happened).
    await _publish_passive_step_result(
        passive_cmd, payload or {}, mainwin, label="browser"
    )

    if exec_error is not None:
        return {"error": str((payload or {}).get("error", str(exec_error)))}

    # Strip screenshot_base64 to keep state history logs clean.
    if isinstance(payload.get("browser"), dict):
        payload["browser"].pop("screenshot_base64", None)

    logger.info(
        "[PassiveMode] Browser automation node returning. "
        "Workflow should continue to loop condition check."
    )
    send_skill_editor_log("log", "[PassiveMode] Browser automation complete. Loop should continue.")
    return {"passive": True, **payload}


async def start_cdp_session_with_stealth(
    browser_session: Any,
    *,
    keep_browser_alive: bool,
    fp_profile: dict | None,
    is_session_started,
    patch_lifecycle_debug,
) -> None:
    """Start a CDP-mode browser session and inject stealth JS.

    Sequence:

      1. Apply ``keep_alive`` to ``browser_session.browser_profile``
         (browser-use decides reset/teardown from this flag, not from
         the separate ``BrowserProfile`` we built earlier — for
         event-monitored loops we need this propagated onto the
         actual reused session).
      2. Optional pre-start lifecycle-debug patch.
      3. ``browser_session.start()`` if not already started.  Wrapped
         in ``asyncio.create_task`` so parallel branches with distinct
         session objects don't serialize on a global asyncio.Lock.
      4. Optional post-start lifecycle-debug patch.
      5. Stealth JS injection (CDP is connected after start, so this
         is the earliest point we can inject).  Failures are
         non-fatal — logged at warning and swallowed.

    The two callable params (``is_session_started``,
    ``patch_lifecycle_debug``) are passed in because they remain as
    closures in ``build_node`` (many other call sites would also
    need to be migrated to extract them).
    """
    # 1. keep_alive
    try:
        if hasattr(browser_session, "browser_profile") and browser_session.browser_profile:
            browser_session.browser_profile.keep_alive = bool(keep_browser_alive)
            logger.info(
                f"[BrowserAutomation] Applied keep_alive={bool(keep_browser_alive)} "
                f"to reused browser session profile"
            )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] Failed to apply keep_alive to reused browser session: {exc}"
        )

    # 2. pre-start lifecycle-debug patch
    if keep_browser_alive:
        patch_lifecycle_debug(browser_session, source="pre_start")

    # 3. start session
    if not is_session_started(browser_session):
        # Parallel branches have distinct session objects; no shared lock
        # needed (a global asyncio.Lock would serialize fan-out branches).
        start_task = asyncio.create_task(browser_session.start())
        await start_task

    # 4. post-start lifecycle-debug patch
    if keep_browser_alive:
        patch_lifecycle_debug(browser_session, source="post_start")

    # 5. stealth JS injection (non-fatal)
    if fp_profile:
        try:
            from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_service import (
                inject_stealth,
            )

            ok = await inject_stealth(browser_session, fp_profile)
            if ok:
                logger.info(
                    f"[BrowserAutomation] Stealth JS injected into existing-browser session "
                    f"(profile={fp_profile.get('id', '?')})"
                )
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] Stealth JS injection failed (non-fatal): {exc}"
            )


def update_browser_session_cache(
    agent: Any,
    *,
    browser_scope_key: str,
    cached_browser_sessions: dict,
    cached_browser_session: Any | None,
    last_known_focus_target_ids: dict,
    cached_passive_agents: dict,
    keep_browser_alive: bool,
    max_cache_size: int,
    patch_lifecycle_debug=None,
) -> None:
    """Defensive post-construction update of the per-scope browser session cache.

    Some agent constructors replace/wrap the ``browser_session``
    reference, so this runs **after** agent creation to:

      * Log the agent vs cached session identity (lifecycle debug).
      * If the live agent session is **not** the cached one, evict
        up to two non-``chat:`` entries from the cache when it has
        reached ``max_cache_size`` (chat sessions are protected
        because they back active conversations); store the new
        session and tag it with ``_ecan_browser_scope_key``; drop
        the matching entries from ``last_known_focus_target_ids`` and
        ``cached_passive_agents``.
      * Re-apply ``keep_alive`` to the live session's
        ``browser_profile`` (some constructors override this).
      * Re-run the optional ``patch_lifecycle_debug`` hook on the
        live session at source ``"post_agent_create"``.

    Failures are logged at warning level and swallowed so a
    diagnostic-only patch failure cannot break the agent run.
    """
    try:
        agent_session = getattr(agent, "browser_session", None)
        logger.info(
            f"[BrowserAutomation][LifecycleDebug] Agent/browser session identity: "
            f"agent_session_obj={id(agent_session) if agent_session else 'none'} "
            f"cached_obj={id(cached_browser_session) if cached_browser_session else 'none'} "
            f"same_as_cached={agent_session is cached_browser_session} "
            f"scope={browser_scope_key}"
        )
        if agent_session and agent_session is not cached_browser_session:
            # Evict up to 2 non-chat entries when at capacity.
            if len(cached_browser_sessions) >= max_cache_size:
                evicted = 0
                for key in list(cached_browser_sessions.keys()):
                    if key == browser_scope_key:
                        continue
                    if not key.startswith("chat:"):
                        old_sess = cached_browser_sessions.pop(key, None)
                        last_known_focus_target_ids.pop(key, None)
                        if old_sess is not None:
                            cached_passive_agents.pop(id(old_sess), None)
                        evicted += 1
                        if evicted >= 2:
                            break
            cached_browser_sessions[browser_scope_key] = agent_session
            try:
                setattr(agent_session, "_ecan_browser_scope_key", browser_scope_key)
            except Exception:
                pass
            logger.info(
                f"[BrowserAutomation] Updated scoped cache from live agent session "
                f"for scope={browser_scope_key}"
            )
        if (
            agent_session
            and hasattr(agent_session, "browser_profile")
            and agent_session.browser_profile
        ):
            agent_session.browser_profile.keep_alive = bool(keep_browser_alive)
            logger.info(
                f"[BrowserAutomation] Agent session keep_alive="
                f"{agent_session.browser_profile.keep_alive}"
            )
        if keep_browser_alive and patch_lifecycle_debug is not None:
            patch_lifecycle_debug(agent_session, source="post_agent_create")
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] Failed to apply keep_alive on agent session: {exc}"
        )


def log_step_budget(agent: Any) -> None:
    """Log the agent's final step + failure budget for postmortem diagnostics.

    Particularly important because hitting ``max_steps`` or
    ``max_failures`` causes browser-use to clobber ``AgentOutput`` →
    ``DoneAgentOutput``; without this log it's hard to tell from the
    skill output whether the agent ran out of steps vs returned
    cleanly.

    Failures are logged at debug level and swallowed.
    """
    try:
        st = getattr(agent, "state", None)
        settings = getattr(agent, "settings", None)
        steps_used = getattr(st, "n_steps", "?") if st else "?"
        max_steps = getattr(settings, "max_steps", "?") if settings else "?"
        consec_fail = getattr(st, "consecutive_failures", "?") if st else "?"
        max_fail = getattr(settings, "max_failures", "?") if settings else "?"
        stopped = getattr(st, "stopped", "?") if st else "?"
        ao_clobbered = (
            agent.AgentOutput is getattr(agent, "DoneAgentOutput", None)
            if hasattr(agent, "AgentOutput")
            else "?"
        )
        logger.info(
            f"[BrowserAutomation] Run finished: "
            f"steps={steps_used}/{max_steps}, "
            f"failures={consec_fail}/{max_fail}, "
            f"stopped={stopped}, "
            f"AgentOutput_clobbered={ao_clobbered}"
        )
    except Exception as exc:
        logger.debug(f"[BrowserAutomation] Step count log failed: {exc}")


def log_browser_use_token_usage(history: Any) -> None:
    """Log browser-use's per-model token + cost summary for diagnostics only.

    The summary is **not** recorded into ``TokenTracker`` because the
    raw underlying LLM calls are already recorded by
    ``LoggingBrowserUseChatOpenAI``.  Recording both would double-count
    tokens and mislead later analysis.

    Failures are logged at warning level and swallowed.
    """
    try:
        usage = getattr(history, "usage", None)
        if usage and (getattr(usage, "total_tokens", 0) or 0) > 0:
            by_model = getattr(usage, "by_model", None) or {}
            if by_model:
                for m_name, m_stats in by_model.items():
                    m_in = getattr(m_stats, "prompt_tokens", 0) or 0
                    m_out = getattr(m_stats, "completion_tokens", 0) or 0
                    if m_in > 0 or m_out > 0:
                        logger.info(
                            f"[TokenTracker] BrowserUse summary model={m_name} "
                            f"in={m_in} out={m_out}"
                        )
            logger.info(
                f"[TokenTracker] BrowserUse total: "
                f"{getattr(usage, 'total_tokens', 0)} tokens, "
                f"{getattr(usage, 'entry_count', 0)} LLM calls, "
                f"cost=${getattr(usage, 'total_cost', 0.0):.4f}"
            )
        else:
            logger.debug(
                f"[TokenTracker] BrowserUse: no usage summary in history "
                f"({len(getattr(history, 'history', []))} steps)"
            )
    except Exception as exc:
        logger.warning(f"[TokenTracker] Failed to record browser-use token usage: {exc}")


def extract_triggering_event(state: dict | None) -> tuple[Any, str, dict, str]:
    """Extract the event that resumed this node, with multi-path fallback.

    Resolution order:

      1. ``state["prompt_refs"]["events"]`` — the canonical path,
         JSON-encoded by the pend_event resume machinery.
      2. ``state["browser_event"]`` — top-level fallback used by
         ``resume.py``'s ``resume_payload``.
      3. ``state["attributes"]["browser_event"]`` — state-patch path.

    Returns ``(evt, evt_type, evt_ctx, evt_label)`` with empty
    string / None / empty dict defaults when no event is present.
    The label is sourced from ``context.sub_type`` /
    ``context.label`` first, falling back to top-level
    ``sub_type`` / ``label`` on the event itself.
    """
    event_json = ""
    evt: Any = None
    evt_type = ""
    evt_ctx: dict = {}
    evt_label = ""

    if isinstance(state, dict):
        pr = state.get("prompt_refs")
        if isinstance(pr, dict):
            event_json = pr.get("events", "")

    if event_json and isinstance(event_json, str) and event_json.strip():
        evt = json.loads(event_json)
        evt_type = evt.get("event_type", "")
        evt_ctx = evt.get("context", {}) if isinstance(evt.get("context"), dict) else {}

    # Before falling back to stale browser_event state, check whether the
    # live invocation input is a Q&A response payload. In bursty queues the
    # pend_event resume can carry the chat_message in state.input while
    # prompt_refs.events is empty and attributes.browser_event still points
    # at an older DOM mutation.
    if not evt_type and isinstance(state, dict):
        try:
            runtime_input = _bh.extract_runtime_invocation_input(state)
            parsed = json.loads(runtime_input) if runtime_input else {}
            if (
                isinstance(parsed, dict)
                and str(parsed.get("response_text") or "").strip()
                and str(parsed.get("customer_name") or parsed.get("customer_id") or "").strip()
            ):
                evt_type = "chat_message"
                evt_ctx = {}
                evt = {
                    "event_type": "chat_message",
                    "human_text": runtime_input,
                }
                logger.warning(
                    f"[BrowserAutomation] event injection recovered "
                    f"chat_message from runtime input while prompt_refs.events "
                    f"was empty; customer={parsed.get('customer_name') or parsed.get('customer_id')!r}"
                )
        except Exception:
            pass

    # Fallback: state["browser_event"] or state["attributes"]["browser_event"].
    if not evt_type and isinstance(state, dict):
        be_fallback = (
            state.get("browser_event")
            or (state.get("attributes") or {}).get("browser_event")
        )
        if isinstance(be_fallback, dict) and be_fallback.get("type"):
            evt_type = be_fallback.get("type", "")
            evt_ctx = {}
            evt = be_fallback
            logger.info(
                f"[BrowserAutomation] event injection fallback: "
                f"prompt_refs.events was empty, using state browser_event "
                f"(type={evt_type}, sub_type={be_fallback.get('sub_type', '')})"
            )

    if evt_type:
        evt_label = (
            evt_ctx.get("sub_type") or evt_ctx.get("label")
            or (evt.get("sub_type") if evt else "")
            or (evt.get("label") if evt else "")
            or ""
        )

    return evt, evt_type, evt_ctx, evt_label


def resolve_event_actionable_items(
    *,
    evt_ctx: dict,
    evt_label: str,
    state: dict | None,
) -> tuple[list, str]:
    """Resolve the current snapshot of actionable items for a ``browser_event``.

    Three resolution paths, tried in order — the first non-empty wins:

      * **Path 0 (preferred): live EventMonitor snapshot.**  The
        ``state.attributes.browser_event`` body is frozen at the last
        ``pend_event`` resume; if this node has been running for a
        while, the DOM has since moved on.  Read each active
        monitor's current ``last_items`` directly so downstream
        filters see fresh data.  Prefers a label match, but falls
        back to **any** monitor with non-empty items because
        ``evt_label`` is frequently empty for ``chat_message``
        triggers.
      * **Path 1: legacy ``context.params.body``.**  Older event
        payloads embed a JSON-encoded body string under
        ``context.params.body`` containing ``items``.
      * **Path 2 (stalest): ``state.attributes.browser_event.body``.**
        Stored by ``resume.py``; only used if the live monitor
        snapshot is unavailable.

    Returns ``(items, source_label)`` where ``source_label`` is
    something like ``"live_monitor[chat]"``, ``"context.params.body"``,
    or ``"state.attributes.browser_event"``.  Both are empty if no
    items can be resolved.
    """
    evt_items: list | None = None
    evt_items_src = ""

    # ws020: when WS reader owns detection, TRUST the WS-detected event over the
    # live_monitor DOM snapshot. Normally Path 0 (live_monitor) is preferred
    # because a stored event can be stale by the time this node runs. Under WS
    # detection the opposite holds: the WS observer just detected THIS exact
    # message and pend_event resumed with it (so it's fresh), while the DOM poll
    # may be bound to a dedicated detection tab whose sidebar is stale — on
    # 2026-06-07 live_monitor returned a prior session's `童趣科普|转人工` instead
    # of the live `sc|有蓝色格子衫吗`, which the system-message filter then dropped
    # → dead silence on every message. So when the browser_event is ws_frontier-
    # sourced, take its items FIRST. Kill-switch: ECAN_LIVE_CHAT_WS_TRUST_EVENT=0.
    from agent.ec_skills.live_chat_dispatch import live_chat_env as _lc_env
    if (_lc_env("ECAN_LIVE_CHAT_WS_TRUST_EVENT") or "1") != "0" and isinstance(state, dict):
        _be = (
            state.get("browser_event")
            or (state.get("attributes") or {}).get("browser_event")
        )
        if isinstance(_be, dict):
            _be_body = _be.get("body", {})
            _be_items = _be_body.get("items", []) if isinstance(_be_body, dict) else []
            # resume.py stores the WS marker as the per-item `source` and on the
            # preserved `normalized_event.source_type` (top-level event_method/domain
            # are NOT copied into the payload). Key on those.
            _norm_ev = _be.get("normalized_event") if isinstance(_be.get("normalized_event"), dict) else {}
            _ws_sourced = (
                str(_be.get("source") or "") == "ws_frontier"
                or str(_norm_ev.get("source_type") or "") == "ws_frontier"
                or any(
                    isinstance(_it, dict) and str(_it.get("source") or "") == "ws_frontier"
                    for _it in (_be_items or [])
                )
            )
            if _be_items and _ws_sourced:
                evt_items = _be_items
                evt_items_src = "ws_frontier:browser_event"

    # Path 0: live EventMonitor snapshot.
    try:
        from agent.ec_skills.browser_use_extension.event_monitor import (
            _active_monitor_sets as _ams,
        )

        live_items = None
        live_src_label = ""
        fallback_items = None
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
                if evt_label and mlabel == evt_label:
                    live_items = list(cand)
                    live_src_label = mlabel
                    break
                if fallback_items is None:
                    fallback_items = list(cand)
                    fallback_label = mlabel
            if live_items:
                break
        if not live_items and fallback_items:
            live_items = fallback_items
            live_src_label = fallback_label or "(no-label)"
        if live_items and not evt_items:   # ws020: don't override a ws_frontier item
            evt_items = live_items
            evt_items_src = f"live_monitor[{live_src_label}]"
    except Exception as exc:
        logger.debug(f"[BrowserAutomation] live monitor snapshot lookup failed: {exc}")

    # Path 1: context.params.body (legacy JSON-encoded body).
    if not evt_items:
        evt_body = evt_ctx.get("params", {})
        if isinstance(evt_body, dict):
            evt_body_str = evt_body.get("body", "")
            if isinstance(evt_body_str, str) and evt_body_str:
                try:
                    parsed = json.loads(evt_body_str)
                    items = parsed.get("items", []) if isinstance(parsed, dict) else []
                    if items:
                        evt_items = items
                        evt_items_src = "context.params.body"
                except Exception:
                    pass

    # Path 2: state["attributes"]["browser_event"]["body"]["items"].
    if not evt_items and isinstance(state, dict):
        be_data = (
            state.get("browser_event")
            or (state.get("attributes") or {}).get("browser_event")
        )
        if isinstance(be_data, dict):
            be_body = be_data.get("body", {})
            if isinstance(be_body, dict):
                items = be_body.get("items", [])
                if items:
                    evt_items = items
                    evt_items_src = "state.attributes.browser_event"

    return (evt_items or []), evt_items_src


def build_browser_event_base_hint(evt_label: str) -> str:
    """Build the base ``browser_event`` hint text with CRITICAL RULES.

    Opens with a DOM-monitor-change statement (adding the
    ``(label: …)`` parenthetical when an ``evt_label`` is provided)
    followed by four CRITICAL RULES that tell the LLM its memory
    has been wiped and prior agent replies in the DOM should not be
    read as evidence of dispatch.

    Rules 2–4 exist because the ``browser_event`` flow is commonly
    driven by chat DOM monitors where prior replies are *always*
    visible and would otherwise short-circuit the LLM into
    incorrectly calling ``done()`` without dispatching.  The rules
    are intentionally verbose — earlier terser versions were
    repeatedly ignored by the LLM.

    The return value is **appendable**: callers typically prepend
    this to a snapshot of actionable items (produced by
    ``build_actionable_items_fallback_text`` or by a prompt-build
    hook) before appending the whole block to the task.
    """
    return (
        "The DOM monitor detected a change in the watched region"
        + (f" (label: {evt_label})" if evt_label else "")
        + ". A new item or state change has occurred.\n\n"
        "**CRITICAL RULES FOR THIS INVOCATION:**\n"
        "1. Your memory from previous rounds has been WIPED. You have NO record of any prior dispatches.\n"
        "2. Do NOT infer dispatch status from the chat DOM. Previous agent replies visible in the chat thread are for OLDER messages, not the current one.\n"
        "3. If the snapshot below shows a customer with a message that looks like a question, you MUST dispatch it — even if you see prior agent replies in the DOM.\n"
        "4. The ONLY way a message counts as \"already dispatched\" is if YOU called bu_send_chat for that EXACT message text in THIS round. Seeing prior replies in the chat is NOT evidence of dispatch."
    )


def build_actionable_items_fallback_text(
    *,
    compact_items: list[dict],
    actionable_raw: list[dict],
    actionable_field: str,
    node_name: str,
) -> str:
    """Build the fallback snapshot text when no prompt-build hook handled the event.

    Two branches, chosen by whether the node opted into the
    actionable-items pattern via ``actionable_field``:

      * **With ``actionable_field``**: renders
        ``actionable_raw`` (pre-filtered to items whose
        ``actionable_field`` is non-empty) under a
        ``### actionable_items (N of M)`` header.  The LLM sees
        only the items it's meant to process.
      * **Without ``actionable_field``**: renders the full
        ``compact_items`` under ``Current snapshot (N items)`` and
        appends a terse "none dispatched this round" reminder.
        Used by nodes that want the LLM to see everything and
        filter itself.

    Both branches emit an ``INFO`` log recording how many items
    were injected and which filter (if any) was applied, keyed by
    ``node_name`` for postmortem diagnostics.

    Returns the text to append to ``_new_msg_hint``; never raises.
    """
    if actionable_field:
        items_json = json.dumps(actionable_raw, ensure_ascii=False, indent=2)
        text = (
            f"\n\n### ctionable_items ({len(actionable_raw)} of "
            f"{len(compact_items)}, filtered by {actionable_field} non-empty):"
            f"\n```json\n{items_json}\n```"
        )
        logger.info(
            f"[BrowserAutomation] Injected {len(actionable_raw)} actionable "
            f"items (filter='{actionable_field}') into task hint (node={node_name})"
        )
        return text
    items_json = json.dumps(compact_items, ensure_ascii=False, indent=2)
    text = (
        f"\n\nCurrent snapshot ({len(compact_items)} items):"
        f"\n```json\n{items_json}\n```"
        "\n\n**None of the above items have been dispatched in this round.** "
        "You must process each actionable item from scratch."
    )
    logger.info(
        f"[BrowserAutomation] Injected {len(compact_items)} "
        f"event items into task hint (node={node_name})"
    )
    return text


def build_chat_message_event_line(state: dict | None) -> str:
    """Build the ``Triggering Event`` hint for a ``chat_message`` resume.

    Pulls ``response_text`` + ``customer_name`` from
    ``state["input"]`` (which carries the JSON-encoded chat payload
    set by the upstream event producer) so the browser-use LLM
    knows *exactly* what text to type — without this, it may see a
    previous reply already rendered in the DOM and mistakenly
    assume the work is done.

    When a ``response_text`` is present, returns a **NEW**-reply
    directive hinting at the recipient and the exact text, with
    strict "deliver this round before `done()`" instructions.  The
    "how to deliver" (tool names) is intentionally deferred to the
    node's own system prompt — this generic helper makes no
    business-case-specific assumption.

    When no ``response_text`` is available, returns a terse fallback
    pointing the LLM at the ``Current Invocation Input`` section
    that ``prepare_task_with_runtime_context`` already injected.
    """
    chat_response_text = ""
    chat_customer_name = ""
    try:
        cm_input = state.get("input", "") if isinstance(state, dict) else ""
        if isinstance(cm_input, str) and cm_input.strip():
            cm_parsed = json.loads(cm_input)
            if isinstance(cm_parsed, dict):
                chat_response_text = cm_parsed.get("response_text", "")
                chat_customer_name = cm_parsed.get("customer_name", "")
    except (json.JSONDecodeError, Exception):
        pass

    if chat_response_text:
        return (
            f"A **NEW** reply was generated by another agent for recipient "
            f"**{chat_customer_name}**.\n\n"
            f"**Reply text to deliver:**\n{chat_response_text}\n\n"
            f"You MUST deliver this reply THIS round using the tools defined "
            f"for this node's purpose (see system prompt), then call `done()`. "
            f" Do NOT skip — even if a prior reply was already sent, this is "
            f"a DIFFERENT message.  Do NOT call `done()` before delivery."
        )
    return (
        "A new chat message arrived from another agent or from the customer. "
        "Check the Current Invocation Input for the message content and act on it."
    )


def compact_actionable_items(items: list) -> list[dict]:
    """Strip heavy fields from each item dict and drop empty values.

    Removes avatar / image / icon URLs (which can balloon prompt
    size) and any keys whose value is ``None``, ``""``, or ``[]``.
    Items that are not dicts are skipped.
    """
    skip_keys = {"avatar_url", "avatar", "image_url", "icon_url"}
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        ci = {
            k: v for k, v in it.items()
            if k not in skip_keys and v not in (None, "", [])
        }
        if ci:
            out.append(ci)
    return out


def prepare_task_with_runtime_context(
    task: str,
    *,
    state: dict | None,
    mainwin: Any,
    node_name: str,
    skill_name: str,
    resolve_mustache_template,
    extract_runtime_invocation_input,
) -> tuple[str, bool]:
    """Resolve mustache templates and inject runtime invocation input into the task.

    Two sequential transformations on the task string:

      1. **Mustache resolution** — if ``task`` contains ``{{`` and
         ``state`` is non-empty, run ``resolve_mustache_template``
         (the build-scope closure) which substitutes
         ``{{llm_result}}``, ``{{browser_research}}``, etc. from the
         state.  Failures are logged at warning and the original task
         is preserved.  This must happen at runtime (not build time)
         because ``state`` carries the actual values.
      2. **Runtime invocation input injection** — pulls the current
         invocation input via ``extract_runtime_invocation_input``,
         appends it under a ``## Current Invocation Input`` section,
         and detects whether it carries a ``response_text`` (so the
         caller can clear it from state after the LLM consumes it,
         preventing duplicates on subsequent ``browser_event`` cycles).

    Returns ``(updated_task, runtime_had_response_text)``.
    """
    # 1. Mustache resolution.
    if state and "{{" in task:
        try:
            resolved = resolve_mustache_template(task, state, mainwin)
            if resolved != task:
                logger.info(
                    f"[BrowserAutomation] ✅ Resolved mustache templates in task "
                    f"(node={node_name}, original_len={len(task)}, "
                    f"resolved_len={len(resolved)})"
                )
                send_skill_editor_log(
                    "log",
                    f"[BrowserAutomation] Resolved mustache templates in task "
                    f"(len: {len(task)} → {len(resolved)})",
                )
                preview = resolved[:500] + "..." if len(resolved) > 500 else resolved
                logger.debug(f"[BrowserAutomation] Resolved task preview:\n{preview}")
                task = resolved
            else:
                logger.warning(
                    f"[BrowserAutomation] ⚠️ Task still contains unresolved mustache templates "
                    f"(node={node_name}). Check that upstream nodes have executed and "
                    f"state contains the expected data."
                )
                send_skill_editor_log(
                    "warning",
                    f"[BrowserAutomation] Unresolved mustache templates in task for node={node_name}",
                )
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] Failed to resolve mustache templates: {exc}"
            )

    # 2. Runtime invocation input injection.
    runtime_input = extract_runtime_invocation_input(state)
    runtime_had_response_text = False
    if runtime_input:
        task = (
            f"{task}\n\n"
            f"## Current Invocation Input\n"
            f"{runtime_input}"
        )
        logger.info(
            f"[BrowserAutomation] Injected runtime invocation input into task "
            f"(node={node_name}, skill={skill_name}, len={len(runtime_input)})"
        )
        send_skill_editor_log(
            "log",
            f"[BrowserAutomation] Injected runtime input into task (len={len(runtime_input)})",
        )
        try:
            ri_parsed = json.loads(runtime_input)
            if isinstance(ri_parsed, dict) and ri_parsed.get("response_text"):
                runtime_had_response_text = True
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    return task, runtime_had_response_text


def persist_focus_target(
    agent: Any,
    *,
    browser_scope_key: str,
    last_known_focus_target_ids: dict,
) -> None:
    """Persist the post-run focus target across node iterations.

    Reads ``agent.browser_session.agent_focus_target_id`` (the CDP
    target id of the tab the agent ended its run on) and stores it
    under ``browser_scope_key`` in the shared dict so the next
    invocation's CDP focus preflight can rebind to the same tab even
    if the underlying ``BrowserSession`` object has been recreated.

    Failures are swallowed silently — the next preflight will fall
    back to its tab-discovery logic.
    """
    try:
        focus_after_run = getattr(
            getattr(agent, "browser_session", None),
            "agent_focus_target_id",
            None,
        )
        if focus_after_run:
            last_known_focus_target_ids[browser_scope_key] = focus_after_run
    except Exception:
        pass


async def stop_non_cached_browser_session(
    agent: Any,
    *,
    browser_scope_key: str,
    cached_browser_sessions: dict,
    browser_type_setting: str,
) -> None:
    """Stop the agent's browser session iff it is not the cached one.

    Cached sessions (the one stored under ``browser_scope_key`` in
    ``cached_browser_sessions``) are reused across invocations and
    must not be stopped here.  ``new chromium`` mode also skips the
    stop call because browser-use manages that browser's lifecycle
    itself.

    Failures are logged at warning and swallowed so the ``finally``
    block can never mask a primary exception.
    """
    if not (hasattr(agent, "browser_session") and agent.browser_session):
        return
    is_cached_session = (
        agent.browser_session == cached_browser_sessions.get(browser_scope_key)
    )
    if not is_cached_session and browser_type_setting != "new chromium":
        try:
            await agent.browser_session.stop()
            logger.debug("[BrowserAutomation] Browser session stopped (non-cached)")
        except Exception as exc:
            logger.warning(f"[BrowserAutomation] Failed to stop browser session: {exc}")


def clear_consumed_response_text(
    state: dict,
    *,
    runtime_had_response_text: bool,
    node_name: str,
    skill_name: str,
) -> None:
    """Clear consumed ``response_text`` from all state sources.

    After the LLM processes a ``chat_message`` response, clear it from
    every state location that re-injection consults so subsequent
    ``browser_event`` cycles don't re-inject and re-send it.

    Mutates the input state in-place; no-op if no ``response_text``
    was consumed this round.
    """
    if not runtime_had_response_text:
        return
    state["input"] = ""
    if isinstance(state.get("messages"), list) and len(state["messages"]) > 4:
        state["messages"][4] = ""
    try:
        attrs = state.get("attributes")
        if isinstance(attrs, dict):
            attrs.pop("params", None)
    except Exception:
        pass
    logger.info(
        f"[BrowserAutomation] Cleared consumed response_text from state "
        f"(node={node_name}, skill={skill_name})"
    )


async def run_agent_with_dispatch(
    agent: Any,
    *,
    agent_kwargs: dict,
    cancellation_event: Any | None,
    step_focus_target: str | None,
    abort_when_pre_dispatched: bool,
    pre_dispatch_flag_attr: str,
    dom_focus_selector: str | None,
    node_max_steps: int | None,
    node_timeout_seconds: float | None,
) -> Any:
    """Run ``agent.run()`` via the appropriate dispatch branch.

    Four branches, in priority order:

      1. **CloudAgent / PrivacyAgent** — pass ``cancellation_event``
         directly to ``run()``; these agent classes support it natively.
      2. **Cancellation only** — install a thin ``_step_check_cancel``
         wrapper on ``agent.step``.  Without this, the stop button has
         no effect on browser-use which doesn't poll cancellation.
      3. **Full step patch** — refocus / abort guard / DOM focus
         (any of which require the layered ``make_step_patch``).
         Restores ``agent.step`` in ``finally`` and silently swallows
         the ``CancelledError("…fast-path…")`` raised by the abort
         guard, returning ``history=None`` instead.
      4. **Default** — plain ``agent.run()`` via ``_run_agent_call``.

    The internal ``_run_agent_call`` enforces a 30-step safety
    ceiling when ``node_max_steps`` is unset and an optional
    ``asyncio.wait_for`` timeout when ``node_timeout_seconds`` is set.
    ``max_actions_per_step`` is **not** passed to ``run()`` — it's a
    constructor param and would raise ``TypeError`` if forwarded.

    The caller adds ``cancellation_event`` to ``agent_kwargs`` here
    (so branches 2/3 see it on ``agent.run(**agent_kwargs)``).

    Returns the agent's history (or ``None`` if the abort guard
    fast-path fired).  Re-raises any non-fast-path
    ``asyncio.CancelledError`` for the caller to handle.
    """
    async def _run_agent_call(**run_kwargs):
        import time
        _start_time = time.time()
        # Safety ceiling: cap at 30 steps if maxSteps is not configured.
        effective_max_steps = node_max_steps if node_max_steps else 30
        run_kwargs.setdefault("max_steps", effective_max_steps)
        logger.info(
            f"[DEBUG_TIMEOUT] _run_agent_call START: "
            f"node_max_steps={node_max_steps}, effective_max_steps={effective_max_steps}, "
            f"node_timeout_seconds={node_timeout_seconds}"
        )
        # max_actions_per_step is a constructor param, not a run() param.
        run_coro = agent.run(**run_kwargs)
        if node_timeout_seconds:
            logger.info(f"[DEBUG_TIMEOUT] _run_agent_call: wrapping with asyncio.wait_for timeout={node_timeout_seconds}s")
            try:
                result = await asyncio.wait_for(run_coro, timeout=node_timeout_seconds)
                _elapsed = time.time() - _start_time
                logger.info(f"[DEBUG_TIMEOUT] _run_agent_call SUCCESS: elapsed={_elapsed:.1f}s, timeout={node_timeout_seconds}s")
                return result
            except asyncio.TimeoutError:
                _elapsed = time.time() - _start_time
                logger.error(f"[DEBUG_TIMEOUT] _run_agent_call TIMEOUT: elapsed={_elapsed:.1f}s >= timeout={node_timeout_seconds}s")
                raise
        else:
            logger.info(f"[DEBUG_TIMEOUT] _run_agent_call: NO timeout wrapper, running without time limit")
            result = await run_coro
            _elapsed = time.time() - _start_time
            logger.info(f"[DEBUG_TIMEOUT] _run_agent_call COMPLETED (no timeout): elapsed={_elapsed:.1f}s")
            return result

    agent_class_name = agent.__class__.__name__
    needs_step_patch = bool(hasattr(agent, "step")) and (
        bool(cancellation_event)
        or bool(step_focus_target)
        or abort_when_pre_dispatched
        or bool(dom_focus_selector)
    )

    # Always pass cancellation_event so stop button works for all agent types.
    if cancellation_event:
        agent_kwargs["cancellation_event"] = cancellation_event
        logger.info(f"[BrowserAutomation] Passing cancellation_event to agent.run()")

    # ── Universal yield-on-pending-reply wrapper (Fix 12-A v2, 2026-05-13) ─
    # The earlier Fix 12-A put the yield check inside ``make_step_patch``,
    # but the front-desk uses ``PrivacyAgent`` which hits Branch 1 (native
    # cancellation support) below — ``make_step_patch`` never runs for it,
    # so the yield never fired (0 events in the test run).
    #
    # Fix: install a thin yield wrapper on ``agent.step`` BEFORE the branch
    # dispatch, so it applies regardless of which branch handles the agent.
    # Branch 3's ``make_step_patch`` still works correctly — its
    # ``orig_step = agent.step`` captures our wrapper, so both checks fire
    # (ours first, then the layered cancel/focus/abort guard).  Outer
    # ``finally`` restores the truly-original step.
    #
    # All branches now need a "fast-path" CancelledError handler — added
    # below for Branches 1, 2, 4 (Branch 3 already has it).
    _ecan_yield_wrapper_orig_step = None
    if (
        hasattr(agent, "step")
        and os.getenv("ECAN_AGENT_YIELD_ON_PENDING_REPLY", "1") != "0"
    ):
        _ecan_yield_wrapper_orig_step = agent.step

        async def _ecan_yield_check_step(*a, **kw):
            try:
                _sc = getattr(agent, "_ecan_step_count", 0) + 1
                agent._ecan_step_count = _sc
                if _sc >= 3 and _front_desk_has_pending_replies():
                    logger.info(
                        f"[BrowserAutomation] LLM step yielding (step={_sc}): "
                        f"front-desk has queued Q&A replies; raising "
                        f"fast-path CancelledError so pend_event can deliver "
                        f"them.  Un-dispatched customers re-detected on next "
                        f"browser_event cycle."
                    )
                    raise asyncio.CancelledError(
                        "yield-on-pending-reply fast-path"
                    )
            except asyncio.CancelledError:
                raise
            except Exception as _yield_err:  # never block step
                logger.debug(
                    f"[BrowserAutomation] yield-check failed (non-fatal): {_yield_err}"
                )
            return await _ecan_yield_wrapper_orig_step(*a, **kw)

        agent.step = _ecan_yield_check_step

    def _swallow_fast_path(exc: BaseException) -> bool:
        """Return True if ``exc`` is a fast-path CancelledError that should
        be swallowed (returning None to the caller).  Re-raise everything
        else."""
        if not isinstance(exc, asyncio.CancelledError):
            return False
        msg = str(exc) or "CancelledError"
        return "fast-path" in msg

    try:
        # Branch 1: native cancellation support.
        if cancellation_event and agent_class_name in ("CloudAgent", "PrivacyAgent"):
            try:
                return await _run_agent_call(cancellation_event=cancellation_event)
            except asyncio.CancelledError as ce:
                if _swallow_fast_path(ce):
                    logger.info(
                        f"[BrowserAutomation] LLM run stopped (branch=native): {ce}"
                    )
                    return None
                raise

        # Branch 2: cancellation-only thin wrapper.
        if cancellation_event and not needs_step_patch:
            async def _step_check_cancel(*a, **kw):
                if cancellation_event and cancellation_event.is_set():
                    logger.info("[BrowserAutomation] Cancellation requested, stopping")
                    raise asyncio.CancelledError("Task cancelled by user")
                return await agent.step(*a, **kw)

            agent.step = _step_check_cancel
            try:
                history = await agent.run(**agent_kwargs)
            except asyncio.CancelledError as ce:
                if _swallow_fast_path(ce):
                    logger.info(
                        f"[BrowserAutomation] LLM run stopped (branch=cancel-only): {ce}"
                    )
                    return None
                raise
            if cancellation_event and cancellation_event.is_set():
                logger.info(
                    "[BrowserAutomation] Cancellation set after agent.run() (simple path), stopping"
                )
                raise asyncio.CancelledError("Task cancelled after LLM response")
            return history

        # Branch 3: full layered step patch.
        if needs_step_patch:
            step_with_cancel, orig_step = make_step_patch(
                agent,
                cancellation_event=cancellation_event,
                refocus_target_id=step_focus_target,
                abort_when_pre_dispatched=abort_when_pre_dispatched,
                pre_dispatch_flag_attr=pre_dispatch_flag_attr,
                dom_focus_selector=dom_focus_selector,
            )
            agent.step = step_with_cancel
            labels = []
            if cancellation_event:
                labels.append("cancellation")
            if step_focus_target:
                labels.append(f"tab refocus (target=...{step_focus_target[-4:]})")
            if abort_when_pre_dispatched:
                labels.append(f"preDispatch abort guard (flag={pre_dispatch_flag_attr})")
            if dom_focus_selector:
                labels.append(f"DOM focus ({dom_focus_selector})")
            logger.info(
                f"[BrowserAutomation] Patched agent.step: {', '.join(labels) or 'basic'}"
            )
            try:
                return await _run_agent_call()
            except asyncio.CancelledError as ce:
                ce_msg = str(ce) or "CancelledError"
                if "fast-path" in ce_msg:
                    logger.info(f"[BrowserAutomation] LLM run stopped: {ce_msg}")
                    # Synthetic None so downstream doesn't crash.
                    return None
                raise
            finally:
                agent.step = orig_step

        # Branch 4: plain run.
        try:
            return await _run_agent_call()
        except asyncio.CancelledError as ce:
            if _swallow_fast_path(ce):
                logger.info(
                    f"[BrowserAutomation] LLM run stopped (branch=plain): {ce}"
                )
                return None
            raise
    finally:
        # Restore the truly-original agent.step.  If Branch 3 ran, it
        # has its own finally that already restored to OUR yield wrapper;
        # this outer finally then restores to the true original.
        if _ecan_yield_wrapper_orig_step is not None:
            try:
                agent.step = _ecan_yield_wrapper_orig_step
            except Exception:
                pass
            # Clear the per-run step counter so a fresh run starts fresh.
            try:
                if hasattr(agent, "_ecan_step_count"):
                    delattr(agent, "_ecan_step_count")
            except Exception:
                pass


def resolve_step_patch_config(
    inputs: dict | None,
) -> tuple[bool, bool, str]:
    """Parse the ``stepPatches`` input + the legacy ``enable_step_refocus`` fallback.

    The ``stepPatches`` input (JSON) gates three orthogonal step-level
    behaviours:

      * ``refocus_assigned_tab`` — per-step tab refocus safety net.
        Default off because forcing refocus each step can bounce the
        agent back to an originating tab in research/executor flows
        and cause repeated clicks.
      * ``abort_when_pre_dispatched`` — abort a stale LLM run when an
        earlier deterministic dispatch has already handled all work.
        Reads ``pre_dispatch_flag_attr`` (default
        ``_ecan_frontdesk_dispatched_all``) on the browser session.
      * ``pre_dispatch_flag_attr`` — the attribute name on the
        browser session to check for the pre-dispatch flag.

    The legacy standalone ``enable_step_refocus`` input is honoured
    only when ``stepPatches.refocus_assigned_tab`` is not set.

    Returns ``(refocus_enabled, abort_when_pre_dispatched, pre_dispatch_flag_attr)``.
    """
    cfg = _parse_json_input(inputs, "stepPatches") or {}
    if not isinstance(cfg, dict):
        cfg = {}
    refocus_enabled = bool(cfg.get("refocus_assigned_tab", False))
    abort_when_pre_dispatched = bool(cfg.get("abort_when_pre_dispatched", False))
    pre_dispatch_flag_attr = str(
        cfg.get("pre_dispatch_flag_attr") or "_ecan_frontdesk_dispatched_all"
    )

    # Back-compat: legacy standalone `enable_step_refocus` input.
    if not refocus_enabled and isinstance(inputs, dict):
        legacy_refocus = (
            str((inputs.get("enable_step_refocus") or {}).get("content", "") or "")
            .strip()
            .lower()
        )
        if legacy_refocus == "true":
            refocus_enabled = True

    return refocus_enabled, abort_when_pre_dispatched, pre_dispatch_flag_attr


def make_step_patch(
    agent: Any,
    *,
    cancellation_event: Any | None,
    refocus_target_id: str | None,
    abort_when_pre_dispatched: bool,
    pre_dispatch_flag_attr: str,
    dom_focus_selector: str | None,
):
    """Build the per-step wrapper installed in place of ``agent.step``.

    The returned coroutine layers four optional behaviours, in order:

      1. **preDispatch abort guard** — if a deterministic dispatch
         (``preDispatch`` config) has already handled all work, the
         current LLM step is stale; raise ``CancelledError`` with a
         "fast-path" tag the caller recognises to swallow gracefully.
      2. **Per-step tab refocus** — re-acquire focus on the assigned
         tab.  With independent sessions this is a safety net.
      3. **Cancellation check** — cooperative stop support.
      4. **DOM focus pruning** — hide elements NOT matching the
         configured CSS selectors before browser-use extracts the
         DOM snapshot, then restore visibility afterwards so the
         page remains usable for user interaction.

    The wrapper closes over ``_orig_step`` so the caller can restore
    it in a ``finally`` block.  All hooks degrade gracefully on
    failure (logged at debug, no impact on the run).
    """
    orig_step = agent.step

    async def _step_with_cancel(*a, **kw):
        # Note: yield-on-pending-reply check (Fix 12-A) is installed
        # at a higher level in ``run_agent_with_dispatch`` so it
        # applies to ALL branches (including Branch 1 / PrivacyAgent
        # which doesn't reach this step_patch path).  When this
        # wrapper is in use (Branch 3), the yield wrapper is below
        # us in the chain — orig_step here is the yield wrapper.

        # 1. preDispatch abort guard.
        if abort_when_pre_dispatched:
            bs_check = getattr(agent, "browser_session", None)
            if bs_check and getattr(bs_check, pre_dispatch_flag_attr, False):
                logger.info(
                    f"[BrowserAutomation] LLM step aborted: "
                    f"preDispatch already completed (flag={pre_dispatch_flag_attr})"
                )
                raise asyncio.CancelledError("Work completed by preDispatch")

        # 2. Per-step tab refocus.
        bs = getattr(agent, "browser_session", None) if refocus_target_id else None
        if refocus_target_id and bs:
            try:
                from browser_use.browser.events import SwitchTabEvent as _STE

                cur = getattr(bs, "agent_focus_target_id", None)
                if cur != refocus_target_id:
                    await bs.event_bus.dispatch(_STE(target_id=refocus_target_id))
                    logger.debug(
                        f"[BrowserAutomation] Per-step tab refocus: "
                        f"...{cur[-4:] if cur else 'None'} → ...{refocus_target_id[-4:]}"
                    )
                else:
                    logger.debug(
                        f"[BrowserAutomation] Per-step tab refocus: already on ...{refocus_target_id[-4:]}"
                    )
            except Exception as exc:
                logger.debug(f"[BrowserAutomation] Per-step tab refocus skipped: {exc}")

        # 3. Cancellation check.
        if cancellation_event and cancellation_event.is_set():
            logger.info("[BrowserAutomation] Cancellation requested, stopping")
            raise asyncio.CancelledError("Task cancelled by user")

        # 4. DOM focus pruning.
        dom_hidden = False
        if dom_focus_selector:
            try:
                dom_bs = getattr(agent, "browser_session", None)
                dom_page = getattr(dom_bs, "current_page", None) if dom_bs else None
                if dom_page:
                    sel_escaped = dom_focus_selector.replace("\\", "\\\\").replace("'", "\\'")
                    hide_js = f"""(function() {{
  var sels = '{sel_escaped}'.split(',').map(function(s) {{ return s.trim(); }}).filter(Boolean);
  if (!sels.length) return 0;
  var keep = new Set();
  sels.forEach(function(sel) {{
    document.querySelectorAll(sel).forEach(function(el) {{
      keep.add(el);
      var p = el.parentElement;
      while (p) {{ keep.add(p); p = p.parentElement; }}
      el.querySelectorAll('*').forEach(function(d) {{ keep.add(d); }});
    }});
  }});
  var hidden = 0;
  document.querySelectorAll('body *').forEach(function(el) {{
    if (!keep.has(el)) {{
      var st = el.style;
      if (st.display !== 'none') {{
        el.setAttribute('data-ecan-dom-focus-orig', st.display || '');
        st.display = 'none';
        hidden++;
      }}
    }}
  }});
  return hidden;
}})()"""
                    hide_result = await dom_page.evaluate(hide_js)
                    dom_hidden = True
                    logger.debug(
                        f"[BrowserAutomation] DOM focus: hid {hide_result} elements "
                        f"(selectors={dom_focus_selector!r})"
                    )
            except Exception as exc:
                logger.debug(f"[BrowserAutomation] DOM focus hide failed: {exc}")

        try:
            return await orig_step(*a, **kw)
        finally:
            if dom_hidden:
                try:
                    restore_js = """(function() {
  var els = document.querySelectorAll('[data-ecan-dom-focus-orig]');
  els.forEach(function(el) {
    el.style.display = el.getAttribute('data-ecan-dom-focus-orig') || '';
    el.removeAttribute('data-ecan-dom-focus-orig');
  });
  return els.length;
})()"""
                    dom_page = getattr(
                        getattr(agent, "browser_session", None), "current_page", None
                    )
                    if dom_page:
                        restored = await dom_page.evaluate(restore_js)
                        logger.debug(
                            f"[BrowserAutomation] DOM focus: restored {restored} elements"
                        )
                except Exception as exc:
                    logger.debug(f"[BrowserAutomation] DOM focus restore failed: {exc}")

    return _step_with_cancel, orig_step


def maybe_first_invocation_short_circuit(
    *,
    state: dict,
    evt_type: str | None,
    event_monitor_configs: list,
    first_invocation_done: set,
    browser_scope_key: str | None,
    node_name: str,
) -> dict | None:
    """Return a "skip-LLM" state on the first event-monitored invocation, else ``None``.

    On auto-launch the ``browser_automation`` node runs before any
    event has fired.  Without event context the LLM has no actionable
    items, no pre-resolved agent list, and no override block — it
    loops aimlessly.  Since the EventMonitor has just been started,
    we skip the LLM entirely and return a "done" state so the graph
    flows to ``pend_event``, which picks up the first real
    ``browser_event`` within seconds.

    The ``first_invocation_done`` set guards against repeating the
    skip if ``pend_event`` retries before an event arrives.  It is
    keyed by ``browser_scope_key`` (or falls back to ``node_name``).
    Mutates the set in-place on a hit.

    Returns the patched ``state`` (with ``hot_path_type=
    "first_invocation_skip"``) or ``None`` if this is not a
    first-invocation.
    """
    if evt_type or not event_monitor_configs:
        return None

    fi_scope = browser_scope_key or node_name
    logger.info(
        f"[BrowserAutomation] First-invocation check: "
        f"scope={fi_scope}, already_done={fi_scope in first_invocation_done}, "
        f"done_set={first_invocation_done}"
    )
    if fi_scope in first_invocation_done:
        return None

    first_invocation_done.add(fi_scope)
    logger.info(
        f"[BrowserAutomation] First-invocation short-circuit: "
        f"no triggering event but {len(event_monitor_configs)} "
        f"event monitor(s) configured — skipping LLM, flowing "
        f"to pend_event immediately (node={node_name}, scope={fi_scope})"
    )
    send_skill_editor_log(
        "log",
        "[BrowserAutomation] First invocation: no event → "
        "skipping LLM, entering event loop",
    )
    state["result"] = {
        "llm_result": {
            "all_done": False,
            "work_done": False,
            "hot_path": True,
            "hot_path_type": "first_invocation_skip",
        }
    }
    return state


async def start_event_monitors_for_agent(
    agent: Any,
    *,
    event_monitor_configs: list,
    calling_agent_id: str | None,
    skill_name: str,
    browser_scope_key: str,
) -> Any | None:
    """Auto-start event monitors on the agent's browser session.

    The monitor configs are **deep-copied** before being passed to the
    capability — every task instance of the same compiled skill shares
    the same closure-scoped config list, and without the copy a
    monitor's mutable state would leak across concurrent tasks.

    Returns the active ``MonitorSet`` or ``None`` (no monitors / no
    session / failure).  Failures are logged at warning level and
    swallowed — the agent run will proceed without monitors rather
    than fail outright.
    """
    if not event_monitor_configs:
        return None
    bs = getattr(agent, "browser_session", None)
    if not bs:
        return None
    try:
        import copy as _copy

        from agent.ec_skills.browser_use_extension.event_monitor_capability import (
            get_event_monitor_capability,
        )

        logger.info(
            f"[BrowserAutomation] Pre-copy monitor state: "
            f"labels={[c.label for c in event_monitor_configs]}, "
            f"list_id={id(event_monitor_configs)}, "
            f"obj_ids={[id(c) for c in event_monitor_configs]}, "
            f"skill={skill_name}, scope={browser_scope_key}"
        )
        configs_copy = _copy.deepcopy(event_monitor_configs)
        capability = get_event_monitor_capability(bs, create=True)
        active = (
            await capability.ensure_started(
                configs=configs_copy, agent_id=calling_agent_id or ""
            )
            if capability
            else None
        )
        if active:
            log_msg = (
                f"[BrowserAutomation] Event monitors started: "
                f"{len(active.monitors)} active "
                f"(set_id={active.monitor_set_id})"
            )
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)
        return active
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Failed to start event monitors: {exc}")
        return None


def patch_agent_for_monitored_keep_alive(agent: Any) -> None:
    """Monkey-patch ``agent.eventbus.stop`` and ``agent.close`` to preserve a monitored session.

    browser-use always calls ``agent.close()`` at the end of ``run()``.
    Even when ``keep_alive=True`` it stops the agent's event bus, which
    tears down the CDP/session plumbing our long-lived event monitors
    depend on.

    Two complementary patches:

      * **Event-bus**: replace ``agent.eventbus.stop`` with a no-op
        that just logs.  We stash the original under
        ``_ecan_orig_stop`` for inspection; the ``_ecan_preserve_patched``
        marker prevents double-patching.
      * **agent.close**: wrap to skip teardown entirely if the
        attached browser session has an active monitor set.  If
        anything goes wrong inspecting the monitor capability we
        fall through to the original close so we don't leak a
        permanently-held session.

    Both patches are idempotent and only meaningful when the caller
    passes a real keep-alive monitored agent.  No-op for agents that
    do not have ``close`` (e.g. a partially-constructed agent in a
    fallback path).
    """
    if not hasattr(agent, "close"):
        return

    # Patch the event bus.
    try:
        eventbus = getattr(agent, "eventbus", None)
        if (
            eventbus
            and hasattr(eventbus, "stop")
            and not getattr(eventbus, "_ecan_preserve_patched", False)
        ):
            orig_stop = eventbus.stop

            async def _preserve_eventbus_stop(*a, **kw):
                logger.info(
                    f"[BrowserAutomation] Preserving agent event bus on monitored keep_alive run end: "
                    f"args={a}, kwargs={kw}"
                )
                return None

            eventbus.stop = _preserve_eventbus_stop
            setattr(eventbus, "_ecan_preserve_patched", True)
            setattr(eventbus, "_ecan_orig_stop", orig_stop)
            logger.info(
                "[BrowserAutomation] Patched agent.eventbus.stop to preserve monitored keep_alive session"
            )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] Failed to patch agent eventbus stop for monitored "
            f"keep_alive session: {exc}"
        )

    # Patch agent.close.
    orig_close = agent.close

    async def _close_preserving_monitored_session():
        try:
            bs = getattr(agent, "browser_session", None)
            has_active_monitor_set = False
            try:
                from agent.ec_skills.browser_use_extension.event_monitor_capability import (
                    get_event_monitor_capability,
                )

                cap = get_event_monitor_capability(bs, create=False) if bs else None
                active = cap.get_active_monitor_set() if cap else None
                has_active_monitor_set = bool(active and getattr(active, "monitors", None))
            except Exception:
                has_active_monitor_set = False

            if bs and has_active_monitor_set:
                logger.info(
                    "[BrowserAutomation] Preserving monitored keep_alive browser session on agent.close()"
                )
                # Preserve aggressively: do not let browser-use tear down
                # any more process/session state at the run boundary.
                return
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] Preserved close path failed, falling back to original close: {exc}"
            )
        await orig_close()

    agent.close = _close_preserving_monitored_session
    logger.info(
        "[BrowserAutomation] Patched agent.close to preserve monitored keep_alive session"
    )


def patch_eventbus_dispatch_for_shutdown(agent: Any) -> None:
    """Monkey-patch eventbus.dispatch to handle QueueShutDown gracefully.

    browser-use's agent.run() calls eventbus.dispatch() in its finally block
    (to emit UpdateAgentTaskEvent) even when the queue has already been shut down
    by another concurrent task's cleanup. This raises QueueShutDown from bubus,
    which propagates as a confusing error.

    This patch wraps dispatch() to catch QueueShutDown and log it instead of
    crashing. The patch is idempotent and only meaningful when the agent has an
    eventbus with dispatch method.

    IMPORTANT: We must patch BOTH agent.eventbus AND agent.browser_session.event_bus
    because browser-use internally calls browser_session.event_bus.dispatch(BrowserStartEvent())
    in browser_session.start(), which is where QueueShutDown errors occur.
    """
    # Import QueueShutDown exception class
    from bubus.service import QueueShutDown as _QueueShutDown

    def _make_shutdown_handler(name: str):
        def _dispatch_handling_shutdown(*args, **kwargs):
            try:
                return _orig_dispatch(*args, **kwargs)
            except Exception as exc:
                if isinstance(exc, _QueueShutDown):
                    logger.warning(
                        f"[BrowserAutomation] QueueShutDown in {name} ignored "
                        f"(queue was shut down by another task): {args[0] if args else 'unknown event'}"
                    )
                    return args[0] if args else None
                raise
        return _dispatch_handling_shutdown

    # Patch agent.eventbus if present
    if hasattr(agent, "eventbus"):
        eventbus = getattr(agent, "eventbus", None)
        if eventbus and hasattr(eventbus, "dispatch") and not getattr(eventbus, "_ecan_dispatch_shutdown_patched", False):
            _orig_dispatch = eventbus.dispatch
            eventbus.dispatch = _make_shutdown_handler("agent.eventbus")
            setattr(eventbus, "_ecan_dispatch_shutdown_patched", True)
            setattr(eventbus, "_ecan_orig_dispatch", _orig_dispatch)
            logger.info(
                "[BrowserAutomation] Patched agent.eventbus.dispatch to handle QueueShutDown gracefully"
            )

    # Patch agent.browser_session.event_bus if present (CRITICAL for browser startup)
    # This is where QueueShutDown errors occur during browser_session.start()
    browser_session = getattr(agent, "browser_session", None)
    if browser_session and hasattr(browser_session, "event_bus"):
        event_bus = getattr(browser_session, "event_bus", None)
        if event_bus and hasattr(event_bus, "dispatch") and not getattr(event_bus, "_ecan_dispatch_shutdown_patched", False):
            _orig_dispatch = event_bus.dispatch
            event_bus.dispatch = _make_shutdown_handler("browser_session.event_bus")
            setattr(event_bus, "_ecan_dispatch_shutdown_patched", True)
            setattr(event_bus, "_ecan_orig_dispatch", _orig_dispatch)
            logger.info(
                "[BrowserAutomation] Patched browser_session.event_bus.dispatch to handle QueueShutDown gracefully"
            )


def register_agent_for_extension_tools(
    agent: Any,
    *,
    state: dict | None,
    calling_agent_id: str | None,
    skill_name: str,
    node_name: str,
    owner: str,
) -> None:
    """Register the live agent + runtime context with ``extension_tools_service``.

    Extension tools (the @-functions exposed to skills) read these
    globals to know which agent + skill they're running inside; without
    this registration, calling an extension tool from a sub-skill
    invoked by browser-use would crash with "no agent registered".

    Failures are logged at debug level and swallowed — the agent will
    still run, only extension tools will be unavailable.
    """
    try:
        from agent.ec_skills.browser_use_extension.extension_tools_service import (
            set_current_agent,
            set_current_runtime_context,
        )

        set_current_agent(agent)
        task_id = (
            (state.get("attributes") or {}).get("task_id", "")
            if isinstance(state, dict)
            else ""
        )
        set_current_runtime_context(
            agent_id=calling_agent_id or "",
            task_id=task_id,
            skill_name=skill_name,
            node_id=node_name,
            owner=owner,
        )
    except Exception as exc:
        logger.debug(
            f"[BrowserAutomation] Failed to register current agent for extension tools: {exc}"
        )


def is_matching_control_url(actual_url: str, preferred_url: str) -> bool:
    """Treat ``localhost`` and ``127.0.0.1`` control-panel URLs as equivalent.

    Local control panels are commonly served on either host name; for
    pre-run navigation we want a tab at ``http://localhost:9877/control``
    to match a preferred URL of ``http://127.0.0.1:9877/control``.

    For non-local hosts we fall back to a strict, trailing-slash-
    insensitive equality check.
    """
    from urllib.parse import urlparse

    if not actual_url or not preferred_url:
        return False
    try:
        actual = urlparse(actual_url)
        preferred = urlparse(preferred_url)
        actual_host = (actual.hostname or "").lower()
        preferred_host = (preferred.hostname or "").lower()
        local_hosts = {"127.0.0.1", "localhost"}
        if actual_host not in local_hosts or preferred_host not in local_hosts:
            return actual_url.rstrip("/") == preferred_url.rstrip("/")
        return (
            (actual.port or 80) == (preferred.port or 80)
            and actual.path.rstrip("/").startswith("/control")
            and preferred.path.rstrip("/").startswith("/control")
        )
    except Exception:
        return actual_url.rstrip("/") == preferred_url.rstrip("/")


def extract_preferred_start_url(task_text: str, workflow_state: dict | None) -> str | None:
    """Pull a deterministic startup URL from task/state for control-page workflows.

    Searches the task text and (if present) the JSON-serialised state
    for the first match of
    ``https?://(127.0.0.1|localhost):9877/control...``.  Returns the
    matched URL or ``None`` if no match is found.
    """
    pattern = r'https?://(?:127\.0\.0\.1|localhost):9877/control[^\s\'"]*'
    candidates = [task_text]
    if isinstance(workflow_state, dict):
        try:
            candidates.append(json.dumps(workflow_state, ensure_ascii=False))
        except Exception:
            pass

    for candidate in candidates:
        if not candidate:
            continue
        match = re.search(pattern, candidate, re.IGNORECASE)
        if match:
            return match.group(0)
    return None
async def run_pre_run_navigation(
    browser_session: Any,
    *,
    target_focus: str | None,
    asg_cfg: dict | None,
    assignment_chat_url: str,
    assignment_session_id: str,
    assignment_tab_id: str,
    assignment_customer_name: str,
    task: str,
    state: dict | None,
    last_known_focus_target_id: str | None,
) -> tuple[bool, str | None]:
    """CDP-mode pre-run navigation: anchor the focused tab at the right URL.

    Two alternative anchoring strategies, in priority order:

      1. **Assignment URL navigation**: if the node's ``assignment``
         config names a URL-bearing field (default ``"chat_url"``)
         and that scope field is present, ensure the focused tab is
         loaded there before the LLM runs.  When this path consumes
         a URL, we skip the generic fallback so the two strategies
         don't fight each other.
      2. **Generic preferred_start_url fallback**: if the task or
         state contains a ``localhost:9877/control...`` URL (a
         control-panel workflow) we either switch to a matching tab
         or pre-navigate the focused tab.  ``is_matching_control_url``
         is used so localhost and 127.0.0.1 are treated as equivalent.

    Returns ``(tab_already_at_correct_url, last_known_focus_target_id)``.
    The ``tab_already_at_correct_url`` flag tells the caller to set
    ``agent.directly_open_url = False`` (suppresses browser-use's
    auto-navigate-from-task-URL initial action, which would otherwise
    time out at 30s on an already-stable page).
    """
    from browser_use.browser.events import NavigateToUrlEvent, SwitchTabEvent

    sm = getattr(browser_session, "session_manager", None)
    tab_already_at_correct_url = False
    new_last_known = last_known_focus_target_id

    # Assignment URL navigation.
    asg_nav_field = "chat_url"
    if isinstance(asg_cfg, dict) and asg_cfg.get("enabled", True):
        asg_nav_field = (
            str(asg_cfg.get("navigate_field") or "chat_url").strip() or "chat_url"
        )
    asg_nav_url_map = {
        "chat_url": assignment_chat_url,
        "session_id": assignment_session_id,
        "tab_id": assignment_tab_id,
        "customer_name": assignment_customer_name,
    }
    asg_nav_url = str(asg_nav_url_map.get(asg_nav_field) or "").strip()
    assignment_nav_used = False
    if asg_nav_url and target_focus:
        latest_focus = getattr(browser_session, "agent_focus_target_id", None)
        focused_target = sm.get_target(latest_focus) if (sm and latest_focus) else None
        focused_url = str(getattr(focused_target, "url", "") or "").strip()
        if focused_url.rstrip("/") != asg_nav_url.rstrip("/"):
            await browser_session.event_bus.dispatch(
                NavigateToUrlEvent(url=asg_nav_url, new_tab=False)
            )
            logger.info(
                f"[BrowserAutomation] Focus preflight navigated to assignment "
                f"{asg_nav_field}: {asg_nav_url}"
            )
            await asyncio.sleep(1.0)
            # Timeout protection: state-summary can hang indefinitely on heavy pages
            try:
                await asyncio.wait_for(
                    browser_session.get_browser_state_summary(include_screenshot=False),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[BrowserAutomation] State-summary TIMEOUT after 5s after navigation to "
                    f"{asg_nav_field}, proceeding anyway"
                )
        else:
            logger.info(
                f"[BrowserAutomation] Focus preflight: tab already at assignment "
                f"{asg_nav_field}, no navigation needed: {asg_nav_url}"
            )
            tab_already_at_correct_url = True
        assignment_nav_used = True

    # Generic preferred_start_url fallback — only when no assignment URL.
    preferred_start_url = (
        None if assignment_nav_used else extract_preferred_start_url(task, state)
    )
    if preferred_start_url and sm:
        latest_focus = getattr(browser_session, "agent_focus_target_id", None)
        all_targets = sm.get_all_targets() if sm else {}
        preferred_target_id = None
        current_target = sm.get_target(latest_focus) if latest_focus else None
        current_url = getattr(current_target, "url", "") if current_target else ""

        for tid, target in (all_targets or {}).items():
            if getattr(target, "target_type", "") not in ("page", "tab"):
                continue
            target_url = getattr(target, "url", "") or ""
            if is_matching_control_url(target_url, preferred_start_url):
                preferred_target_id = tid
                break

        if preferred_target_id and preferred_target_id != latest_focus:
            await browser_session.event_bus.dispatch(
                SwitchTabEvent(target_id=preferred_target_id)
            )
            new_last_known = preferred_target_id
            logger.info(
                f"[BrowserAutomation] Switched to preferred control tab: "
                f"...{preferred_target_id[-4:]} url={preferred_start_url}"
            )
            # Timeout protection: state-summary can hang indefinitely on heavy pages
            try:
                await asyncio.wait_for(
                    browser_session.get_browser_state_summary(include_screenshot=False),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[BrowserAutomation] State-summary TIMEOUT after 5s after tab switch, proceeding anyway"
                )
        elif not is_matching_control_url(current_url, preferred_start_url):
            await browser_session.event_bus.dispatch(
                NavigateToUrlEvent(url=preferred_start_url, new_tab=False)
            )
            logger.info(
                f"[BrowserAutomation] Pre-navigated focused tab to preferred startup URL: "
                f"{preferred_start_url}"
            )
            await asyncio.sleep(0.8)
            # Timeout protection: state-summary can hang indefinitely on heavy pages
            try:
                await asyncio.wait_for(
                    browser_session.get_browser_state_summary(include_screenshot=False),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"[BrowserAutomation] State-summary TIMEOUT after 5s after navigation, proceeding anyway"
                )

    return tab_already_at_correct_url, new_last_known


# mt053K (2026-05-31): URL substrings that identify a tab as the
# live-chat seller-workspace target.  Used by the CDP-direct rediscovery
# helper below; conservative match (substring, not regex) so it survives
# the site's query-string variants.
_MT053K_LIVE_CHAT_URL_HINTS = (
    "im.jinritemai.com",
    "/pc_seller_v2/main/workspace",
)


async def _mt053k_try_cdp_rediscover_and_attach(
    browser_session: Any,
    *,
    skill_name: str,
    node_name: str,
) -> bool:
    """Rediscover Chrome tabs via direct CDP when session_manager's
    view is empty.  Used as a recovery hook from run_cdp_focus_preflight.

    Background: browser-use's session_manager tracks targets it has
    explicitly attached to.  Under high-concurrency CDP churn (mt052D OOB
    + rapid open_session / pool tab allocation), a target_detach event
    can drop our attachment.  EventMonitor keeps working because it
    holds its own independent CDP attachment to a specific target_id;
    session_manager goes blank.  Customer 1-to-7 trace 2026-05-31
    12:11→12:13 froze on exactly this — Chrome had ≥1 live-chat tab open
    the entire time but session_manager couldn't see it.

    Strategy: open an independent CDPClient to the browser's debug
    websocket (same pattern EventMonitor uses), call Target.getTargets
    to enumerate REAL Chrome tabs, log what we find for operator
    visibility, attempt Target.attachToTarget on the first workspace-matching
    target.  Return True iff the attach succeeded so the caller can
    re-read session_manager's view.
    """
    cdp_url = getattr(browser_session, "cdp_url", None)
    if not cdp_url:
        bp = getattr(browser_session, "browser_profile", None)
        cdp_url = getattr(bp, "cdp_url", None) if bp else None
    if not cdp_url:
        logger.warning(
            f"[BrowserAutomation] mt053K: no cdp_url on browser_session; "
            f"cannot rediscover targets (skill={skill_name}, node={node_name})"
        )
        return False
    client = None
    try:
        from cdp_use import CDPClient as _MT053K_CDPClient
        client = _MT053K_CDPClient(url=cdp_url)
        await client.start()
        targets_resp = await asyncio.wait_for(
            client.send_raw("Target.getTargets", {}),
            timeout=5.0,
        )
        all_target_infos = (
            targets_resp.get("targetInfos") if isinstance(targets_resp, dict) else None
        ) or []
        page_targets = [
            ti for ti in all_target_infos
            if str(ti.get("type", "")) in ("page", "tab")
        ]
        live_chat_targets = [
            ti for ti in page_targets
            if any(hint in str(ti.get("url", "")) for hint in _MT053K_LIVE_CHAT_URL_HINTS)
        ]
        logger.warning(
            f"[BrowserAutomation] mt053K CDP-direct rediscovery: "
            f"chrome_targets_total={len(all_target_infos)}, "
            f"page_targets={len(page_targets)}, "
            f"live_chat_targets={len(live_chat_targets)} "
            f"(session_manager saw 0 — proves the lost-binding hypothesis) "
            f"skill={skill_name}, node={node_name}"
        )
        if not live_chat_targets:
            # Chrome itself has no live-chat tab — operator action needed.
            if page_targets:
                _sample_urls = [str(ti.get("url", ""))[:80] for ti in page_targets[:3]]
                logger.warning(
                    f"[BrowserAutomation] mt053K: Chrome has {len(page_targets)} "
                    f"non-live-chat page target(s); sample URLs: {_sample_urls}"
                )
            return False
        # Attempt to attach to the first live-chat target.  flatten=True puts
        # us into the unified session so subsequent session_manager polls
        # discover it.
        chosen = live_chat_targets[0]
        chosen_tid = str(chosen.get("targetId") or "")
        chosen_url = str(chosen.get("url", ""))[:80]
        if not chosen_tid:
            return False
        try:
            attach = await asyncio.wait_for(
                client.send_raw(
                    "Target.attachToTarget",
                    {"targetId": chosen_tid, "flatten": True},
                ),
                timeout=5.0,
            )
        except Exception as attach_exc:
            logger.warning(
                f"[BrowserAutomation] mt053K: attachToTarget failed for "
                f"target=...{chosen_tid[-8:]} url={chosen_url!r}: {attach_exc}"
            )
            return False
        sid = attach.get("sessionId") if isinstance(attach, dict) else None
        if not sid:
            logger.warning(
                f"[BrowserAutomation] mt053K: attachToTarget returned no "
                f"sessionId for target=...{chosen_tid[-8:]}"
            )
            return False
        logger.info(
            f"[BrowserAutomation] mt053K: attached to recovered live-chat target "
            f"...{chosen_tid[-8:]} session=...{sid[-6:]} url={chosen_url!r}; "
            f"caller will re-read session_manager view"
        )
        return True
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] mt053K rediscovery error (non-fatal, "
            f"will raise the original 'no tabs' error): {exc}"
        )
        return False
    finally:
        if client is not None:
            try:
                await client.stop()
            except Exception:
                pass


async def run_cdp_focus_preflight(
    browser_session: Any,
    *,
    last_known_focus_target_id: str | None,
    assignment_tab_id: str,
    assignment_chat_url: str,
    skill_name: str,
    node_name: str,
) -> tuple[str | None, str | None]:
    """CDP-mode focus preflight: re-bind the agent focus to a valid page target.

    If ``agent_focus_target_id`` is missing/invalid (common after a
    target detach), pick the best target in priority order:

      1. The tab matching ``assignment_tab_id`` or ``assignment_chat_url``
         (CRM/agent-assignment override).
      2. The current focus, if still valid.
      3. The last-known focus from a prior round.
      4. The first available page target.

    Then, if the chosen target differs from the current focus, dispatch
    a ``SwitchTabEvent`` and run a state-summary refresh with a 3-second
    timeout + one retry.  ``get_browser_state_summary`` has been
    observed to hang indefinitely under target detach, so we cap it
    here and SKIP the refresh on persistent failure (the next
    ``get_browser_state_summary`` in the run loop will refresh anyway).

    Returns:
        ``(target_focus, new_last_known_focus_target_id)``.  Both may
        be ``None`` if the preflight chose to no-op.

    Raises:
        RuntimeError: when no page targets exist (all tabs closed).
    """
    from browser_use.browser.events import NavigateToUrlEvent, SwitchTabEvent  # noqa: F401

    sm = getattr(browser_session, "session_manager", None)
    all_targets = sm.get_all_targets() if sm else {}
    page_target_ids = [
        tid
        for tid, t in (all_targets or {}).items()
        if getattr(t, "target_type", "") in ("page", "tab")
    ]

    cur_focus = getattr(browser_session, "agent_focus_target_id", None)
    valid_cur_focus = cur_focus in page_target_ids if cur_focus else False
    valid_last_focus = (
        last_known_focus_target_id in page_target_ids
        if last_known_focus_target_id
        else False
    )

    try:
        logger.info(
            f"[BrowserAutomation] Focus preflight entry: "
            f"target_count={len(page_target_ids)}, "
            f"cur_focus_valid={valid_cur_focus}, "
            f"last_focus_valid={valid_last_focus}, "
            f"assignment_tab_id={(assignment_tab_id or '')[-6:] or 'none'}, "
            f"skill={skill_name}, node={node_name}"
        )
    except Exception:
        pass

    def _resolve_assignment_target(
        preferred_tab_id: str, preferred_chat_url: str
    ) -> str | None:
        preferred_tab_id = str(preferred_tab_id or "").strip()
        preferred_chat_url = str(preferred_chat_url or "").strip()
        if not all_targets:
            return None
        # Exact target_id match, or upper-case suffix match (CRM IDs are
        # often the last 6 hex chars of the full target id).
        if preferred_tab_id:
            if preferred_tab_id in page_target_ids:
                return preferred_tab_id
            preferred_upper = preferred_tab_id.upper()
            for tid in page_target_ids:
                if str(tid or "").upper().endswith(preferred_upper):
                    return str(tid)
        # URL match — case-sensitive exact (with trailing-slash normalisation).
        if preferred_chat_url:
            preferred_norm = preferred_chat_url.rstrip("/")
            for tid, target in (all_targets or {}).items():
                if getattr(target, "target_type", "") not in ("page", "tab"):
                    continue
                target_url = str(getattr(target, "url", "") or "").strip().rstrip("/")
                if target_url and target_url == preferred_norm:
                    return str(tid)
        return None

    if not page_target_ids:
        # mt053K (2026-05-31): session_manager.get_all_targets() returning
        # empty does NOT mean Chrome has no tabs.  It means our session's
        # attached-targets view is blank — typically because a target
        # detach event under high-concurrency CDP churn dropped our
        # bindings, OR our cached session object went stale relative to
        # Chrome.  Customer 1-to-7 trace 2026-05-31 12:11→12:13: the
        # session went empty at 12:11:17 while EventMonitor (which uses
        # its OWN direct-CDP target binding) kept reading live-chat tabs fine
        # the entire time — proving Chrome had tabs we just couldn't see.
        # Before raising, try a CDP-direct rediscovery: call Target.getTargets
        # via a fresh CDP client, find any live-chat tab, and try to attach
        # so session_manager picks it up on the next call.
        mt053k_recovered = await _mt053k_try_cdp_rediscover_and_attach(
            browser_session, skill_name=skill_name, node_name=node_name,
        )
        if mt053k_recovered:
            # Re-read session_manager's view after the reattach attempt.
            all_targets = sm.get_all_targets() if sm else {}
            page_target_ids = [
                tid
                for tid, t in (all_targets or {}).items()
                if getattr(t, "target_type", "") in ("page", "tab")
            ]
            logger.info(
                f"[BrowserAutomation] mt053K: post-reattach session_manager "
                f"now sees {len(page_target_ids)} page target(s), "
                f"node={node_name}"
            )
        if not page_target_ids:
            error_msg = (
                "[BrowserAutomation] Focus preflight failed: no browser tabs "
                "available in session_manager AND CDP-direct rediscovery did "
                "not recover a live-chat target.  Chrome may have crashed, the "
                "user may have closed the live-chat tab, or the browser_session "
                "object may be irrecoverably stale (consider restarting eCan)."
            )
            logger.error(error_msg)
            send_skill_editor_log("error", error_msg)
            raise RuntimeError(error_msg)

    # Pick the best target focus.
    try:
        assignment_target_focus = _resolve_assignment_target(
            assignment_tab_id, assignment_chat_url
        )
    except Exception:
        assignment_target_focus = None

    if assignment_target_focus:
        target_focus = assignment_target_focus
    elif valid_cur_focus:
        target_focus = cur_focus
    elif valid_last_focus:
        target_focus = last_known_focus_target_id
    else:
        target_focus = page_target_ids[0]

    new_last_known = last_known_focus_target_id
    # ── Fix #2 (stress-test 2026-04-30): track whether the preflight
    # actually dispatched a SwitchTabEvent.  When the focus didn't move,
    # the state-summary refresh is pure overhead under high CDP load
    # (3 s × 2 attempts = 6 s wasted per iteration when 23 tabs are open).
    # Returned as the 3rd tuple element so the post-preflight site can
    # also skip its own redundant refresh.
    did_switch = False
    if target_focus:
        if cur_focus != target_focus:
            await browser_session.event_bus.dispatch(SwitchTabEvent(target_id=target_focus))
            logger.info(
                f"[BrowserAutomation] Focus preflight switched target: "
                f"...{cur_focus[-4:] if cur_focus else 'None'} -> ...{target_focus[-4:]}"
            )
            did_switch = True
        new_last_known = target_focus

    if target_focus and did_switch:
        # Defensive state-summary refresh with timeout + one retry.
        # ``get_browser_state_summary`` has hung indefinitely under target
        # detach.  Wrap with wait_for(3s); on final failure, log and SKIP.
        ok = False
        for attempt in range(2):
            try:
                await asyncio.wait_for(
                    browser_session.get_browser_state_summary(include_screenshot=False),
                    timeout=3.0,
                )
                ok = True
                break
            except asyncio.TimeoutError:
                logger.warning(
                    f"[BrowserAutomation] Focus preflight state-summary TIMEOUT "
                    f"after 3s (attempt {attempt + 1}/2), "
                    f"target=...{target_focus[-4:] if target_focus else 'None'}, "
                    f"target_count={len(page_target_ids)}, "
                    f"skill={skill_name}, node={node_name}"
                )
            except Exception as inner:
                logger.warning(
                    f"[BrowserAutomation] Focus preflight state-summary error "
                    f"(attempt {attempt + 1}/2): {inner}"
                )
        if not ok:
            try:
                cdp_url = getattr(browser_session, "cdp_url", "") or ""
                pf_target = sm.get_target(target_focus) if sm else None
                pf_url = getattr(pf_target, "url", "") if pf_target else ""
                logger.warning(
                    f"[BrowserAutomation] Focus preflight: SKIPPING state-summary "
                    f"refresh after 2 failed attempts. Proceeding with run. "
                    f"target=...{target_focus[-4:] if target_focus else 'None'}, "
                    f"url={pf_url}, cdp={cdp_url}, "
                    f"skill={skill_name}, node={node_name}"
                )
            except Exception:
                logger.warning(
                    "[BrowserAutomation] Focus preflight: SKIPPING state-summary "
                    "refresh after 2 failed attempts (state snapshot unavailable)"
                )

    elif target_focus and not did_switch:
        logger.debug(
            f"[BrowserAutomation] Focus preflight: skipping state-summary "
            f"refresh (focus unchanged), target=...{target_focus[-4:] if target_focus else 'None'}, "
            f"skill={skill_name}, node={node_name}"
        )

    return target_focus, new_last_known, did_switch


def maybe_apply_extract_patch(agent_kwargs: dict) -> None:
    """Apply the ``extract`` tool's ``max_char_limit`` patch from ``max_input_tokens``.

    The patch ensures the extract tool respects the model's context
    length and prevents token overflow.  The patch reserves ~24K
    tokens for system prompt, history, and overhead.

    Reloads the patch module in dev mode so iterating on the patch
    code does not require restarting the app.  No-op if
    ``max_input_tokens`` is not set in ``agent_kwargs``.
    """
    if "max_input_tokens" not in agent_kwargs:
        return
    try:
        # Dev-mode hot-reload so patch edits take effect on the next run.
        import sys
        mod_name = "agent.ec_skills.browser_use_extension.extract_patch"
        if mod_name in sys.modules:
            import importlib

            importlib.reload(sys.modules[mod_name])
            logger.debug("[BrowserAutomation] 🔄 Reloaded extract_patch module (dev mode)")

        from agent.ec_skills.browser_use_extension.extract_patch import (
            patch_extract_max_char_limit,
        )

        ok = patch_extract_max_char_limit(agent_kwargs["max_input_tokens"])
        if ok:
            logger.debug(
                f"[BrowserAutomation] ✅ Extract patch applied/verified "
                f"(max_input_tokens={agent_kwargs['max_input_tokens']:,})"
            )
        else:
            logger.warning("[BrowserAutomation] ⚠️ Extract patch returned False")
    except Exception as exc:
        logger.error(
            f"[BrowserAutomation] ❌ Failed to apply extract patch: {exc}",
            exc_info=True,
        )


async def acquire_or_reuse_local_agent(
    *,
    AgentClass: type,
    task: str,
    llm: Any,
    controller: Any,
    agent_kwargs: dict,
    bu_scope_key: str,
    cached_bu_agents: dict,
    loop_history_mode: str,
    fp_profile: dict | None,
    browser_session: Any | None = None,
) -> Any:
    """Acquire-or-reuse a cached ``browser_use.Agent`` (both modes).

    When ``browser_session`` is supplied (CDP / existing-browser mode),
    we pass it explicitly to the constructor and re-bind it onto the
    cached agent on a cache hit (the session may have been recreated
    by the focus preflight).  Stealth JS injection is skipped — the
    caller has already done it after CDP connect.

    When ``browser_session`` is ``None`` (new-chromium mode), browser-use
    creates and manages its own session, and we pre-start it after
    construction so the supplied ``fp_profile`` (if any) can be
    injected before any page loads.

    The new-chromium docstring continues below for parity:

    Cache invalidation rules:
      * Class change (``BUAgent`` ↔ ``PrivacyAgent``).
      * Hooks now wanted but the cached agent was built without
        hook kwargs.

    On a cache miss we construct a fresh agent, snapshot its
    ``AgentOutput`` schema (so ``reset_bu_agent_for_next_round`` can
    restore it later when browser-use clobbers it to ``DoneAgentOutput``),
    install it under ``bu_scope_key``, and — if a stealth fingerprint
    profile is supplied — pre-start the browser session so CDP
    connects and we can inject stealth JS before any page loads.
    """
    cached = cached_bu_agents.get(bu_scope_key)

    # Invalidate on class change or hook-config change.
    want_hooks = bool(agent_kwargs.get("hooks_enabled"))
    cached_has_hooks = bool(getattr(cached, "hooks_enabled", False))
    if cached is not None and (
        type(cached) is not AgentClass
        or (want_hooks and not cached_has_hooks)
    ):
        logger.info(
            f"[BrowserAutomation] Evicting cached agent "
            f"(class={type(cached).__name__}→{AgentClass.__name__}, "
            f"cached_hooks={cached_has_hooks}, want_hooks={want_hooks}, "
            f"scope={bu_scope_key})"
        )
        _bh.cached_bu_agents.pop(bu_scope_key, None)
        if bu_scope_key in _bh._cached_bu_agents_insertion_order:
            _bh._cached_bu_agents_insertion_order.remove(bu_scope_key)
        cached = None

    if cached is not None:
        reset_bu_agent_for_next_round(cached, loop_history_mode, task)
        # CDP mode: re-bind the (possibly recreated) session onto the
        # cached agent.  No-op on new-chromium (caller passes None).
        if browser_session is not None:
            try:
                cached.browser_session = browser_session
            except Exception:
                pass
        logger.info(
            f"[BrowserAutomation] Reusing cached browser-use agent "
            f"(scope={bu_scope_key}, mode={loop_history_mode})"
        )
        return cached

    # CDP mode passes browser_session explicitly; new-chromium lets
    # browser-use create its own session.
    constructor_kwargs = dict(agent_kwargs)
    if browser_session is not None:
        constructor_kwargs["browser_session"] = browser_session
    agent = AgentClass(task=task, llm=llm, controller=controller, **constructor_kwargs)
    if hasattr(agent, "AgentOutput"):
        # Snapshot the full schema so reset_bu_agent_for_next_round can
        # restore it after browser-use clobbers it to DoneAgentOutput.
        agent._ecan_full_AgentOutput = agent.AgentOutput
    
    # CRITICAL: Evict old agents BEFORE adding new one to prevent memory leak
    # Each cached_bu_agents entry consumes ~860 MB
    _bh._evict_bu_agent_if_needed()
    
    # Track insertion order for FIFO eviction
    if bu_scope_key not in _bh._cached_bu_agents_insertion_order:
        _bh._cached_bu_agents_insertion_order.append(bu_scope_key)
    
    _bh.cached_bu_agents[bu_scope_key] = agent
    logger.info(
        f"[BrowserAutomation] Created new browser-use agent and cached "
        f"(scope={bu_scope_key}, loop_history_mode={loop_history_mode}, "
        f"cache_size={len(_bh.cached_bu_agents)}/{_bh._MAX_BU_AGENTS_CACHE_SIZE})"
    )

    # Stealth JS injection only for new-chromium mode.  In CDP mode the
    # caller has already injected before this function runs.
    if browser_session is None and fp_profile and getattr(agent, "browser_session", None):
        try:
            await agent.browser_session.start()
            from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_service import (
                inject_stealth,
            )

            ok = await inject_stealth(agent.browser_session, fp_profile)
            if ok:
                logger.info(
                    f"[BrowserAutomation] Stealth JS injected into new-chromium session "
                    f"(profile={fp_profile.get('id', '?')})"
                )
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] Stealth JS injection failed (non-fatal): {exc}"
            )

    return agent


def build_browser_profile(
    *,
    profile_settings: dict | None,
    node_profile: str | None,
    keep_alive: bool,
    headless: bool | None,
    target_url: str | None = None,
) -> Any:
    """Create a ``BrowserProfile`` with persistent ``user_data_dir`` and lock cleanup.

    The returned profile preserves login state (cookies, sessions)
    across runs by pinning ``user_data_dir``.  If the profile_settings
    dict does not specify a ``user_data_dir``, we auto-assign one
    under ``<user_data>/browser_profiles/<safe_id>/``.  Stale Chromium
    lock files in that dir are cleaned up automatically before
    returning so a previous abnormal exit does not break startup.

    The ``keep_alive`` flag is propagated as ``True`` only when the
    caller has event monitors that need to outlive the agent.  Pass
    ``headless=None`` for "let the browser default win".
    """
    from browser_use.browser.profile import BrowserProfile  # type: ignore
    from utils.user_path_helper import ensure_user_data_dir
    from agent.ec_skills.browser_use_extension.profile_lock_cleaner import (
        ensure_profile_unlocked,
    )
    from config.app_settings import app_settings

    disable_extensions = app_settings.is_dev_mode
    settings = profile_settings or {}

    use_pc_chrome = settings.get("use_pc_chrome", False)
    user_data_dir = settings.get("user_data_dir", "")

    if not user_data_dir:
        # Auto-assign profile directory based on task/session id
        ident = settings.get("id") or settings.get("name") or node_profile or "default"
        safe_id = re.sub(r"[^\w\-]", "_", str(ident))
        user_data_dir = ensure_user_data_dir(
            subdir=os.path.join("browser_profiles", safe_id)
        )
        logger.info(f"[BrowserAutomation] Auto-assigned user_data_dir: {user_data_dir}")

        # Support using PC Chrome if requested
        if use_pc_chrome:
            logger.info("[BrowserAutomation] Using PC Chrome profile")
            settings["_is_using_pc_chrome"] = True

    # Clean stale lock files (prevents startup failure after abnormal exits).
    # Diagnostic: ~10 s gaps were observed here in CDP/existing-browser flows
    # where Chrome is alive and holding SingletonLock; Path.exists()/is_symlink()
    # on Windows can block when antivirus or filesystem locks are contended.
    _t0 = time.perf_counter()
    ensure_profile_unlocked(user_data_dir, auto_clean=True)
    _dt_ms = (time.perf_counter() - _t0) * 1000.0
    if _dt_ms > 200.0:
        logger.warning(
            f"[BrowserAutomation][Perf] ensure_profile_unlocked took {_dt_ms:.0f} ms "
            f"(user_data_dir={user_data_dir})"
        )
    else:
        logger.debug(f"[BrowserAutomation][Perf] ensure_profile_unlocked took {_dt_ms:.0f} ms")

    # BrowserProfile() consistently takes 8–11 s on every call after the first
    # for the same user_data_dir on this machine (Pydantic v2 with
    # validate_assignment=True + revalidate_instances='always', combined with
    # whatever filesystem probing model_post_init does on Windows). Empirically
    # the result for identical inputs is also identical, and the rest of the
    # browser_automation hot path reuses a cached browser-use agent against the
    # same CDP session, so we memoize the profile per (user_data_dir, flags).
    _profile_key = (
        bool(not disable_extensions),
        str(user_data_dir),
        bool(keep_alive),
        bool(headless) if headless is not None else None,
    )
    _cached = _BROWSER_PROFILE_CACHE.get(_profile_key)
    if _cached is not None:
        logger.debug(
            f"[BrowserAutomation][Perf] BrowserProfile() served from cache "
            f"(key={_profile_key})"
        )
        return _cached

    _t0 = time.perf_counter()
    profile = BrowserProfile(
        enable_default_extensions=not disable_extensions,
        user_data_dir=user_data_dir,
        keep_alive=keep_alive or None,
        headless=headless if headless else None,
    )
    _dt_ms = (time.perf_counter() - _t0) * 1000.0
    if _dt_ms > 200.0:
        logger.warning(f"[BrowserAutomation][Perf] BrowserProfile() init took {_dt_ms:.0f} ms")
    _BROWSER_PROFILE_CACHE[_profile_key] = profile
    return profile


def apply_stealth_fingerprint(
    browser_profile: Any,
    profile_settings: dict | None,
    *,
    calling_agent_id: str | None,
    node_name: str,
) -> dict | None:
    """If the profile has ``enableStealth=True``, wire fingerprint fields onto ``browser_profile``.

    Reads stealth fields from ``profile_settings`` and builds an
    ``_fp_profile`` dict (user_agent, viewport, locale, anti-detect
    args, hardware noise toggles, WebGPU + geolocation overrides).
    If userAgent and canvasNoiseSeed are both empty we treat that as
    "user wants a random/auto profile" and call ``get_random_profile``
    with a deterministic seed (``{calling_agent_id}:{node_name}``) so
    the stealth identity stays stable across runs of the same node.

    The actual stealth JS injection happens later (after CDP connects
    in :func:`session.py` / the agent run loop) — here we only set
    BrowserProfile attributes that take effect at start time.

    Returns the resolved ``_fp_profile`` dict (or ``None`` on disabled
    or failure).  Failures are logged at warning level and swallowed
    so the run continues without stealth.
    """
    if not (profile_settings and profile_settings.get("enableStealth")):
        return None
    try:
        from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_service import (
            apply_profile_to_browser_profile,
            get_random_profile,
        )
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Stealth fingerprint import failed: {exc}")
        return None

    bp_settings = profile_settings
    fp = {
        "id": bp_settings.get("id", "stealth"),
        "userAgent": bp_settings.get("user_agent") or "",
        "viewport": (
            {
                "width": bp_settings["viewport_width"],
                "height": bp_settings["viewport_height"],
            }
            if bp_settings.get("viewport_width") and bp_settings.get("viewport_height")
            else None
        ),
        "deviceScaleFactor": bp_settings.get("deviceScaleFactor"),
        "timezone": bp_settings.get("timezone") or "",
        "locale": bp_settings.get("locale") or "",
        "displayLanguage": bp_settings.get("displayLanguage") or "",
        "platform": bp_settings.get("platform") or "",
        "languages": bp_settings.get("languages") or [],
        "canvasNoiseSeed": bp_settings.get("canvasNoiseSeed") or "",
        "webgl": {
            "vendor": bp_settings.get("webglVendor") or "",
            "renderer": bp_settings.get("webglRenderer") or "",
        },
        "hardwareConcurrency": bp_settings.get("hardwareConcurrency"),
        "deviceMemory": bp_settings.get("deviceMemory"),
        "webrtcPolicy": bp_settings.get("webrtcPolicy") or "block",
        "doNotTrack": bp_settings.get("doNotTrack") or "",
        # Hardware noise toggles.
        "noiseWebGLImage": bp_settings.get("noiseWebGLImage", True),
        "noiseClientRects": bp_settings.get("noiseClientRects", True),
        "noiseSpeechVoices": bp_settings.get("noiseSpeechVoices", True),
        "noiseMediaDevices": bp_settings.get("noiseMediaDevices", True),
        "fontProtection": bp_settings.get("fontProtection", True),
        "customFonts": bp_settings.get("customFonts") or [],
        "portScanProtection": bp_settings.get("portScanProtection", True),
        "portScanAllowedPorts": bp_settings.get("portScanAllowedPorts") or "80,443",
        # WebGPU + geolocation.
        "webgpuMode": bp_settings.get("webgpuMode") or "based_on_webgl",
        "geoLocationMode": bp_settings.get("geoLocationMode") or "",
        "geolocation": bp_settings.get("geolocation"),
        "hardwareAcceleration": bp_settings.get("hardwareAcceleration") or "default",
        "proxy": bp_settings.get("fingerprintProxy"),
    }

    try:
        # If key fields are empty, user wants a random/auto profile.
        if not fp["userAgent"] and not fp["canvasNoiseSeed"]:
            fp_seed = f"{calling_agent_id or 'default'}:{node_name}"
            fp = get_random_profile(seed=fp_seed)
            logger.info(
                f"[BrowserAutomation] Stealth: auto-generated fingerprint profile "
                f"(seed={fp_seed}, id={fp.get('id')})"
            )
        else:
            logger.info(
                f"[BrowserAutomation] Stealth: using configured fingerprint profile "
                f"(id={fp.get('id')}, ua_len={len(fp.get('userAgent', ''))})"
            )
        apply_profile_to_browser_profile(browser_profile, fp)
        return fp
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Stealth profile setup failed (non-fatal): {exc}")
        return None


def maybe_apply_cloud_llm_kwargs(
    agent_kwargs: dict,
    mainwin: Any,
    *,
    use_privacy_agent: bool,
    calling_agent_id: str | None,
    skill_name: str,
    node_name: str,
    system_prompt_id: str | None,
    user_prompt_id: str | None,
) -> None:
    """Optionally inject cloud-LLM transport kwargs into ``agent_kwargs``.

    Feature-flagged on ``EC_BROWSER_USE_CLOUD_LLM``.  Only applies when
    ``use_privacy_agent`` is True (the vanilla ``browser_use.Agent``
    does not accept these kwargs).  Mutates ``agent_kwargs`` in place.
    """
    try:
        cloud_enabled = os.environ.get("EC_BROWSER_USE_CLOUD_LLM", "").strip().lower() in {
            "1", "true", "yes", "on",
        }
    except Exception:
        cloud_enabled = False

    if not (cloud_enabled and use_privacy_agent):
        return

    try:
        try:
            cloud_endpoint = mainwin.getWanApiEndpoint()
        except Exception:
            cloud_endpoint = None
        cloud_agent_id = calling_agent_id or getattr(mainwin, "current_agent_id", None)
        agent_kwargs.update(
            {
                "cloud_llm_enabled": True,
                "cloud_session": getattr(mainwin, "session", None),
                "cloud_token": mainwin.get_auth_token(),
                "cloud_endpoint": cloud_endpoint,
                "cloud_acct_site_id": mainwin.getAcctSiteID(),
                "cloud_agent_id": cloud_agent_id,
                "cloud_skill_id": skill_name,
                "cloud_node_id": node_name,
                "cloud_system_prompt_id": system_prompt_id,
                "cloud_user_prompt_id": user_prompt_id,
                "cloud_work_type": "browser_use_next_action",
            }
        )
        logger.info(
            f"[BrowserAutomation] Cloud LLM enabled for PrivacyAgent "
            f"(agent_id={cloud_agent_id})"
        )
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Failed to configure cloud LLM mode: {exc}")


def apply_hook_bundle_kwargs(
    agent_kwargs: dict,
    raw_inputs: dict,
    *,
    privacy_strategy: str,
) -> None:
    """Parse ``hookBundles`` / ``siteAdapter`` and merge into ``agent_kwargs``.

    PrivacyAgent gains three hook-related kwargs; each defaults to "off".
    A node keeps its legacy behaviour unless the author sets at least
    one of:

      * ``hookBundles``   (JSON array)  → external bundle specs
      * ``siteAdapter``   (JSON object) → shared selector/policy data

    Environment variable ``EC_BROWSER_USE_HOOKS_ENABLED`` flips the
    built-in Tier-0 safety hooks on for every browser-automation node
    — use it for canarying.  When either the env var OR node has
    supplied bundles / site_adapter, we assume the operator wants the
    built-in safety rails on.

    If ``privacy_strategy == 'none'`` and we're enabling hooks, we
    explicitly disable privacy filtering so the user's explicit
    "no privacy" setting is honoured (the hook dispatcher works
    independently of the filter pipeline).

    Mutates ``agent_kwargs`` in place; never raises (each parsing
    failure is logged and swallowed so a malformed JSON in one knob
    does not break the whole run).
    """
    # Hook bundles.
    try:
        raw = (raw_inputs.get("hookBundles") or {}).get("content")
        parsed = None
        if isinstance(raw, str) and raw.strip():
            parsed = json.loads(raw)
        if parsed:
            if not isinstance(parsed, list):
                raise ValueError(
                    f"hookBundles must be a JSON array, got {type(parsed).__name__}"
                )
            agent_kwargs["hook_bundles"] = parsed
            logger.info(
                f"[BrowserAutomation] Hook bundles configured: {len(parsed)} spec(s)"
            )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] Failed to parse hookBundles; "
            f"continuing without external hooks: {exc}"
        )

    # Site adapter.
    try:
        raw = (raw_inputs.get("siteAdapter") or {}).get("content")
        parsed = None
        if isinstance(raw, str) and raw.strip():
            parsed = json.loads(raw)
        if parsed:
            if not isinstance(parsed, dict):
                raise ValueError(
                    f"siteAdapter must be a JSON object, got {type(parsed).__name__}"
                )
            agent_kwargs["site_adapter"] = parsed
            logger.info(
                f"[BrowserAutomation] site_adapter configured (name={parsed.get('name')!r})"
            )
    except Exception as exc:
        logger.warning(
            f"[BrowserAutomation] Failed to parse siteAdapter; "
            f"continuing without it: {exc}"
        )

    # Canary flag for Tier-0 built-in hooks.
    env_flag = os.environ.get("EC_BROWSER_USE_HOOKS_ENABLED", "").strip().lower() in {
        "1", "true", "yes", "on",
    }
    opted_in = bool(
        env_flag
        or agent_kwargs.get("hook_bundles")
        or agent_kwargs.get("site_adapter")
    )
    if opted_in:
        agent_kwargs["hooks_enabled"] = True
        logger.info(
            f"[BrowserAutomation] PrivacyAgent hooks_enabled=True "
            f"(env={env_flag}, bundles={bool(agent_kwargs.get('hook_bundles'))}, "
            f"site_adapter={bool(agent_kwargs.get('site_adapter'))})"
        )

    # Auto-upgrade compatibility: keep privacy off if the user said 'none'.
    if privacy_strategy == "none":
        agent_kwargs["privacy_enabled"] = False
        logger.info(
            "[BrowserAutomation] privacy_enabled=False (hook-only PrivacyAgent upgrade)"
        )


def _build_local_llm_from_node_config_impl(
    mainwin: Any,
    *,
    llm_provider: str | None,
    llm_model_name: str | None,
) -> Any:
    """Build LLM strictly from node-editor selection (no fallback).

    Free-function implementation; replaces the former
    ``BrowserUseRunner._build_local_llm_from_node_config`` instance
    method.
    """
    from agent.ec_skills.llm_utils.llm_utils import (
        create_browser_use_llm_by_provider_type,
        extract_provider_config,
    )

    provider = llm_provider
    model_name = llm_model_name
    logger.info(
        f"[BrowserAutomation] Using node-specific LLM: provider={provider}, model={model_name}"
    )
    try:
        cm = mainwin.config_manager
        provider_dict = cm.llm_manager.get_provider(provider)
        logger.info(
            f"[BrowserAutomation] get_provider('{provider}') returned: {provider_dict is not None}"
        )
        if not provider_dict:
            raise ValueError(
                f"Provider '{provider}' not found in config. Please check provider name in node settings."
            )
        config = extract_provider_config(
            provider_dict, config_manager=cm, node_model_name=model_name
        )
        api_key = config.get("api_key")
        base_url = config.get("base_url")
        provider_type_id = config.get("provider_type")
        llm = create_browser_use_llm_by_provider_type(
            provider_type=provider_type_id,
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            mainwin=mainwin,
        )
        if llm is None:
            raise ValueError(
                f"Failed to create LLM with provider '{provider_type_id}' "
                f"(display: {provider}), model '{model_name}'. "
                f"Check API key and base_url configuration."
            )
        logger.info(
            f"[BrowserAutomation] ✅ Created LLM with node settings: "
            f"provider={provider}, model={model_name}"
        )
        return llm
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Failed to create LLM with node settings:\n"
            f"  Provider: {provider}\n"
            f"  Model: {model_name}\n"
            f"  Error: {exc}\n\n"
            f"Please check:\n"
            f"  1. Provider name is correct in node settings\n"
            f"  2. Model name is correct and belongs to the provider\n"
            f"  3. API key is configured in Settings > LLM Management\n"
            f"  4. Base URL is correct (if using local/custom provider)"
        ) from exc


def build_local_llm(
    mainwin: Any,
    *,
    llm_provider: str | None,
    llm_model_name: str | None,
    raw_inputs: dict,
) -> Any:
    """Module-level entry point for the full-local LLM resolution.

    Order of preference: lambda proxy → node-specified provider →
    global default LLM via mainwin.config_manager.

    Free-function implementation; replaces the former
    ``BrowserUseRunner._build_local_llm`` instance method (the
    ``_NoSessionsShim`` wrapper hack is no longer needed).

    Raises:
        ValueError: when no LLM can be created (with actionable
                    message identifying the missing config).
    """
    from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm

    # Proxy first.
    if _should_use_proxy(raw_inputs):
        proxy = _get_proxy_config()
        if proxy:
            from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

            provider = llm_provider or "openai"
            model = llm_model_name or "gpt-4o"
            masked = (
                proxy["auth_token"][:20] + "..."
                if len(proxy.get("auth_token", "")) > 20
                else proxy.get("auth_token", "(empty)")
            )
            logger.info(
                f"[BrowserAutomation] Using Lambda proxy (local): {provider}/{model}, "
                f"endpoint={proxy['endpoint']}, user={proxy['user_id']}, token={masked}"
            )
            return ChatLambdaProxy(
                model=model,
                provider_name=provider,
                user_id=proxy["user_id"],
                lambda_endpoint=proxy["endpoint"],
                auth_token=proxy["auth_token"],
            )

    def _proxy_fallback(reason: str):
        """Missing/broken local LLM config → cloud LLM proxy, when configured."""
        proxy = _get_proxy_config()
        if not proxy:
            return None
        from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

        provider = llm_provider or "openai"
        model = llm_model_name or "gpt-4o"
        logger.info(
            f"[BrowserAutomation] Falling back to Lambda proxy ({reason}): "
            f"{provider}/{model}, endpoint={proxy['endpoint']}"
        )
        return ChatLambdaProxy(
            model=model,
            provider_name=provider,
            user_id=proxy["user_id"],
            lambda_endpoint=proxy["endpoint"],
            auth_token=proxy["auth_token"],
        )

    # ── CN default routing (2026-08-28) ──
    # On CN builds every provider goes through the llm-proxy by default; only
    # ollama (the customer's own private LLM server) and explicit node useProxy
    # values stay direct. Policy: build_node._cn_llm_proxy_by_default.
    try:
        from agent.ec_skills.build_node import _cn_llm_proxy_by_default
        # Only when the node names a provider — the global-default path below
        # resolves its own provider (which may be the customer's ollama).
        if llm_provider and _cn_llm_proxy_by_default(llm_provider, None, raw_inputs):
            llm = _proxy_fallback("CN default routing: llm-proxy")
            if llm is not None:
                return llm
    except Exception as _cn_policy_err:
        logger.debug(f"[BrowserAutomation] CN default-routing check skipped: {_cn_policy_err}")

    # Node-specified provider+model.
    if llm_provider and llm_model_name:
        try:
            return _build_local_llm_from_node_config_impl(
                mainwin,
                llm_provider=llm_provider,
                llm_model_name=llm_model_name,
            )
        except ValueError as exc:
            llm = _proxy_fallback(f"node LLM unavailable: {exc}")
            if llm is not None:
                return llm
            raise

    # Global default.
    logger.info("[BrowserAutomation] No node-specific LLM settings, using global default")
    try:
        llm = create_browser_use_llm(mainwin=mainwin, skip_playwright_check=True)
        if llm is None:
            llm = _proxy_fallback("no global default LLM configured")
            if llm is not None:
                return llm
            raise ValueError(
                "Failed to create LLM from global default settings.\n\n"
                "Please configure a default LLM in Settings > LLM Management:\n"
                "  1. Select a provider (OpenAI, DeepSeek, Qwen, etc.)\n"
                "  2. Enter API key\n"
                "  3. Set as default provider"
            )
        logger.info("[BrowserAutomation] ✅ Using global default LLM")
        return llm
    except ValueError as exc:
        llm = _proxy_fallback(f"global default LLM failed: {exc}")
        if llm is not None:
            return llm
        raise
    except Exception as exc:
        llm = _proxy_fallback(f"global default LLM failed: {exc}")
        if llm is not None:
            return llm
        raise ValueError(
            f"Failed to create LLM from global default settings:\n"
            f"  Error: {exc}\n\n"
            f"Please check Settings > LLM Management:\n"
            f"  1. Verify default provider is set\n"
            f"  2. Verify API key is configured\n"
            f"  3. Verify base URL is correct (if using local provider)"
        ) from exc


def attach_llm_token_context(
    llm: Any,
    state: dict | None,
    *,
    skill_name: str,
    node_name: str,
    llm_provider: str | None,
    llm_model_name: str | None,
    browser_scope_key: str,
) -> None:
    """Attach a ``_ec_token_context`` dict to the LLM for usage attribution."""
    try:
        attrs = state.get("attributes") or {} if isinstance(state, dict) else {}
        session_id = None
        if isinstance(state, dict):
            session_id = (
                state.get("session_id")
                or state.get("chat_id")
                or attrs.get("sessionId")
            )
        setattr(
            llm,
            "_ec_token_context",
            {
                "skill_name": skill_name,
                "node_name": node_name,
                "source_id": f"{skill_name}::{node_name}",
                "source_name": f"{skill_name}::{node_name}",
                "task_id": attrs.get("task_id"),
                "run_id": state.get("run_id") if isinstance(state, dict) else None,
                "session_id": session_id,
                "browser_scope_key": browser_scope_key,
                "node_model_name": llm_model_name,
                "node_llm_provider": llm_provider,
            },
        )
    except Exception as exc:
        logger.debug(f"[BrowserAutomation] token context attach failed: {exc}")


def make_browser_step_callback(node_name: str, run_id: str | None = None):
    """Factory for the per-step progress callback (sync).

    Sends an intermediate ``update_run_stat`` IPC update so the skill
    editor shows real-time progress during long browser-automation runs.
    Cloud-mode is detected at call-time and short-circuited (the cloud
    worker has its own progress reporting).
    """
    def _on_browser_step(browser_state_summary, model_output, step_number):
        try:
            from agent.cloud_worker.cloud_logger import is_cloud_mode

            if is_cloud_mode():
                return
            from gui.ipc.api import IPCAPI
            import time as _t

            ipc = IPCAPI.get_instance()
            # Build a concise step summary from model_output actions.
            action_summary = ""
            try:
                actions = getattr(model_output, "action", None)
                if actions and isinstance(actions, list):
                    names = [
                        getattr(a, "name", "") or type(a).__name__
                        for a in actions[:3]
                    ]
                    action_summary = ", ".join(n for n in names if n)
            except Exception:
                pass
            step_label = f"step {step_number}" + (
                f" ({action_summary})" if action_summary else ""
            )
            send_skill_editor_log(
                "log", f"[BrowserAutomation] 📍 {node_name}: {step_label}"
            )
            ipc.update_run_stat(
                agent_task_id=run_id or "0123456789",
                current_node=node_name,
                status="running",
                langgraph_state={
                    "_browser_step": step_number,
                    "_browser_action": action_summary,
                },
                timestamp=int(_t.time() * 1000),
            )
        except Exception:
            pass

    return _on_browser_step


def make_browser_done_callback(agent_ref: dict):
    """Factory for the on-done callback that stops session event monitors.

    Args:
        agent_ref: Single-key dict ``{"agent": <agent>}`` filled in by
                   the closure once the agent is constructed.  We close
                   over the dict (not the agent) so the callback works
                   even though the agent doesn't exist at registration time.
    """
    async def _on_browser_done(_history):
        try:
            agent_obj = agent_ref.get("agent")
            session_obj = (
                getattr(agent_obj, "browser_session", None) if agent_obj else None
            )
            if not session_obj:
                return
            from agent.ec_skills.browser_use_extension.event_monitor_capability import (
                get_event_monitor_capability,
            )

            capability = get_event_monitor_capability(session_obj, create=False)
            if capability:
                await capability.stop()
                logger.info(
                    "[BrowserAutomation] Stopped session event monitors on done()"
                )
        except Exception as exc:
            logger.warning(
                f"[BrowserAutomation] Failed to stop monitors on done(): {exc}"
            )

    return _on_browser_done


def resolve_available_file_paths(state: dict | None) -> list[str]:
    """Scan ``state`` for a ``product_dir`` and return image paths under it.

    Pulls ``product_dir`` from (in priority order):
      1. ``state.prompt_refs.product_dir``
      2. ``state.tool_result.<node>.product_dir``
      3. ``state.tool_result.<node>.{final|content|extracted_content}``
         parsed as JSON containing a top-level ``product_dir`` field.

    Returns image file absolute paths inside that directory, excluding
    UUID-named files (these are research-downloaded artefacts that
    should not be auto-attached to the agent).  On any failure (missing
    dir, bad permissions, JSON decode error) returns an empty list and
    logs at warning level — never raises.
    """
    product_dir = _resolve_product_dir(state)
    if not product_dir:
        logger.debug(
            f"[BrowserAutomation] product_dir not found in state; "
            f"skipping available_file_paths ({product_dir!r})"
        )
        return []
    if not os.path.isdir(product_dir):
        logger.debug(
            f"[BrowserAutomation] product_dir is not a directory; "
            f"skipping available_file_paths ({product_dir!r})"
        )
        return []

    image_exts = {
        ".jpg", ".jpeg", ".png", ".webp",
        ".gif", ".bmp", ".tiff", ".tif",
        ".heic", ".heif",
    }
    uuid_pat = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\.",
        re.IGNORECASE,
    )
    try:
        paths = [
            os.path.join(product_dir, name)
            for name in os.listdir(product_dir)
            if os.path.splitext(name.lower())[1] in image_exts
            and not uuid_pat.match(name)
        ]
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Failed to list product_dir: {exc}")
        return []
    if paths:
        logger.info(
            f"[BrowserAutomation] available_file_paths: "
            f"{len(paths)} image(s) from {product_dir}"
        )
    else:
        logger.debug(
            f"[BrowserAutomation] No image files found in product_dir={product_dir}"
        )
    return paths


def _resolve_product_dir(state: dict | None) -> str | None:
    """Internal: pull a ``product_dir`` string from ``state`` via 3 paths."""
    if not isinstance(state, dict):
        return None
    # 1. Direct from prompt_refs (fastest).
    pr = state.get("prompt_refs") or {}
    cand = pr.get("product_dir") if isinstance(pr, dict) else None
    if isinstance(cand, str) and cand:
        return cand
    # 2 + 3. Scan tool_result entries.
    tr = state.get("tool_result") or {}
    if not isinstance(tr, dict):
        return None
    for node_out in tr.values():
        if not isinstance(node_out, dict):
            continue
        pd = node_out.get("product_dir")
        if isinstance(pd, str) and pd:
            return pd
        for fk in ("final", "content", "extracted_content"):
            fv = node_out.get(fk)
            if not isinstance(fv, str):
                continue
            try:
                parsed = json.loads(fv)
            except Exception:
                continue
            if isinstance(parsed, dict):
                cand = parsed.get("product_dir")
                if isinstance(cand, str) and cand:
                    return cand
    return None


def _build_cloud_llm_from_node_config_impl(
    *,
    llm_provider: str | None,
    llm_model_name: str | None,
) -> Any:
    """Build a cloud LLM strictly from node-editor specified provider+model.

    Free-function implementation; replaces the former
    ``BrowserUseRunner._build_cloud_llm_from_node_config`` instance method.
    """
    from agent.ec_skills.llm_utils.llm_utils import create_browser_use_llm_by_provider_type

    provider_lower = (llm_provider or "").lower()
    model_name = llm_model_name
    if not model_name:
        try:
            from app_context import AppContext

            mainwin_cfg = AppContext.get_main_window()
            if mainwin_cfg and hasattr(mainwin_cfg, "config_manager"):
                provider_cfg = mainwin_cfg.config_manager.llm_manager.get_provider(llm_provider)
                if provider_cfg:
                    model_name = provider_cfg.get("default_model")
        except Exception:
            pass
    if not model_name:
        raise RuntimeError(
            f"[BrowserAutomation] Node specified provider '{llm_provider}' "
            f"but model_name is missing"
        )

    # Per-provider env var lookup (mirrors original behavior).
    api_key = ""
    base_url: str | None = None
    if provider_lower == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("OPENAI_BASE_URL", "").strip() or None
    elif provider_lower == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    elif provider_lower == "deepseek":
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
    elif provider_lower == "ecanai":
        api_key = os.environ.get("ECANAI_LLM_API_KEY", "").strip()
        if not api_key:
            try:
                from utils.env.secure_store import get_current_username, secure_store
                api_key = (
                    secure_store.get("ECANAI_LLM_API_KEY", username=get_current_username()) or ""
                ).strip()
            except Exception as exc:
                logger.warning(f"[BrowserAutomation] Failed to read eCanAI API key: {exc}")
        base_url = os.environ.get(
            "ECANAI_LLM_BASE_URL",
            "https://sccb0-d0gc5398xf028be6a.service.tcloudbase.com/api/llm-proxy/v1",
        ).strip()
    elif provider_lower in ("azure", "azure_openai"):
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", "").strip()
        base_url = os.environ.get("AZURE_OPENAI_ENDPOINT", "").strip() or None
    else:
        api_key = os.environ.get("LLM_API_KEY", "").strip()

    if not api_key and provider_lower != "ollama":
        raise RuntimeError(
            f"[BrowserAutomation] Node specified provider '{llm_provider}' "
            f"but no API key found in environment. Please set the required API key."
        )

    llm = create_browser_use_llm_by_provider_type(
        provider_type=provider_lower,
        model_name=model_name,
        api_key=api_key,
        base_url=base_url,
        mainwin=None,
    )
    if not llm:
        raise RuntimeError(
            f"[BrowserAutomation] Failed to create LLM for node-specified provider "
            f"'{llm_provider}'"
        )
    logger.info(
        f"[BrowserAutomation] Created LLM from node config: provider={llm_provider}, "
        f"model={model_name}"
    )
    send_skill_editor_log(
        "log", f"[BrowserAutomation] LLM created: {llm_provider}/{model_name}"
    )
    return llm


def _build_cloud_llm_impl(
    *,
    llm_provider: str | None,
    llm_model_name: str | None,
    raw_inputs: dict,
) -> Any:
    """Cloud-LLM resolution: proxy → node-specified → default-from-Settings.

    Free-function implementation; replaces the former
    ``BrowserUseRunner._build_cloud_llm`` instance method.
    """
    from agent.ec_skills.llm_utils.llm_utils import (
        create_browser_use_llm_by_provider_type,
        extract_provider_config,
    )

    # Proxy first.
    if _should_use_proxy(raw_inputs):
        proxy = _get_proxy_config()
        if proxy:
            from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

            provider = llm_provider or "openai"
            model = llm_model_name or "gpt-4o"
            logger.info(f"[BrowserAutomation] Using Lambda proxy (cloud): {provider}/{model}")
            send_skill_editor_log("log", f"[BrowserAutomation] LLM via Lambda proxy: {provider}/{model}")
            return ChatLambdaProxy(
                model=model,
                provider_name=provider,
                user_id=proxy["user_id"],
                lambda_endpoint=proxy["endpoint"],
                auth_token=proxy["auth_token"],
            )

    def _proxy_fallback(reason: str):
        """Missing/broken local LLM config → cloud LLM proxy, when configured."""
        proxy = _get_proxy_config()
        if not proxy:
            return None
        from agent.ec_skills.browser_use_extension.lambda_proxy_llm import ChatLambdaProxy

        provider = llm_provider or "openai"
        model = llm_model_name or "gpt-4o"
        logger.info(
            f"[BrowserAutomation] Falling back to Lambda proxy ({reason}): {provider}/{model}"
        )
        return ChatLambdaProxy(
            model=model,
            provider_name=provider,
            user_id=proxy["user_id"],
            lambda_endpoint=proxy["endpoint"],
            auth_token=proxy["auth_token"],
        )

    # Node-specified provider.
    if llm_provider:
        try:
            return _build_cloud_llm_from_node_config_impl(
                llm_provider=llm_provider, llm_model_name=llm_model_name,
            )
        except (ValueError, RuntimeError) as exc:
            llm = _proxy_fallback(f"node LLM unavailable: {exc}")
            if llm is not None:
                return llm
            raise

    # Default from Settings.
    from app_context import AppContext

    ctx = AppContext.get_instance()
    mainwin_ctx = ctx.get_main_window()
    if not mainwin_ctx or not hasattr(mainwin_ctx, "config_manager"):
        raise RuntimeError(
            "[BrowserAutomation] Cannot access Settings to get default LLM configuration"
        )
    llm_config = mainwin_ctx.config_manager.llm_manager.get_default_llm_config()
    provider_dict = llm_config["provider_dict"]
    provider_type, model_name_default, api_key, base_url = extract_provider_config(provider_dict)
    if not api_key and provider_type not in ("ollama", "ryoais"):
        llm = _proxy_fallback(
            f"no API key for default provider '{llm_config['provider_id']}'"
        )
        if llm is not None:
            return llm
        raise RuntimeError(
            f"[BrowserAutomation] No API key configured for default LLM provider "
            f"'{llm_config['provider_id']}'"
        )
    llm = create_browser_use_llm_by_provider_type(
        provider_type=provider_type,
        model_name=llm_model_name or llm_config["model_name"],
        api_key=api_key,
        base_url=base_url,
        mainwin=None,
    )
    if not llm:
        raise RuntimeError(
            f"[BrowserAutomation] Failed to create LLM instance for default provider "
            f"'{llm_config['provider_id']}'"
        )
    logger.info(
        f"[BrowserAutomation] Created LLM from Settings: {llm_config['provider_id']}, "
        f"model: {llm_config['model_name']}"
    )
    send_skill_editor_log(
        "log", f"[BrowserAutomation] Using default LLM: {llm_config['provider_id']}"
    )
    return llm


def _build_cloud_transport_impl() -> Any:
    """Prefer the cloud worker's global transport; else build from env.

    Free-function replacement for the former
    ``BrowserUseRunner._build_cloud_transport`` static method.
    """
    try:
        from agent.cloud_worker.worker_main import get_global_passive_transport

        transport = get_global_passive_transport()
        if transport is not None:
            logger.info("[BrowserAutomation] Using global CloudWorkerPassiveTransport")
            send_skill_editor_log("log", "[BrowserAutomation] Using cloud worker passive transport")
            return transport
        logger.warning(
            "[BrowserAutomation] get_global_passive_transport() returned None — "
            "falling back to env-based transport"
        )
        send_skill_editor_log(
            "log",
            "[BrowserAutomation] ⚠️ Global passive transport is None, falling back to env-based",
        )
    except ImportError as exc:
        logger.warning(f"[BrowserAutomation] cloud_worker import failed: {exc}")
    except Exception as exc:
        logger.warning(f"[BrowserAutomation] Error getting global transport: {exc}")

    from agent.ec_skills.browser_use_extension.cloud_agent import (
        make_default_cloud_transport_from_env,
    )

    transport = make_default_cloud_transport_from_env()
    logger.info("[BrowserAutomation] Created transport from environment")
    return transport


def _resolve_cloud_run_id_impl(state: dict | None) -> str:
    """Resolve a stable run_id matching the PassiveStepResultListener.

    Free-function replacement for the former
    ``BrowserUseRunner._resolve_cloud_run_id`` static method.
    """
    import uuid

    run_id: str | None = None
    explicit: str | None = None
    state_dev = False
    try:
        if isinstance(state, dict):
            explicit = state.get("browser_use_run_id")
            run_id = explicit
            md = state.get("metadata")
            attrs = state.get("attributes")
            state_dev = bool(
                state.get("dev_mode")
                or (md.get("dev_mode") if isinstance(md, dict) else False)
                or (attrs.get("dev_mode") if isinstance(attrs, dict) else False)
            )
            if not run_id:
                attrs = state.get("attributes") or {}
                run_id = attrs.get("chat_id")
            if not run_id:
                attrs = state.get("attributes") or {}
                run_id = attrs.get("run_id") or attrs.get("passive_run_id")
            if not run_id:
                md = state.get("metadata") or {}
                if isinstance(md, dict):
                    run_id = md.get("run_id") or md.get("passive_run_id")
    except Exception:
        run_id = None

    try:
        from config.app_settings import app_settings

        dev_mode = bool(state_dev or getattr(app_settings, "is_dev_mode", False))
    except Exception:
        dev_mode = bool(state_dev)

    if dev_mode and not explicit:
        dev = (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
        run_id = dev or "0123456789"

    if not isinstance(run_id, str) or not run_id.strip():
        run_id = (
            (os.environ.get("ECAN_RUN_ID") or "").strip()
            or (os.environ.get("EC_BROWSER_PASSIVE_RUN_ID") or "").strip()
        )
    if not isinstance(run_id, str) or not run_id.strip():
        run_id = uuid.uuid4().hex
    logger.debug(f"[BrowserAutomation] Cloud mode run_id={run_id}")
    return run_id


def _resolve_acct_site_id_impl(mainwin: Any, transport: Any) -> str | None:
    """Prefer mainwin (hybrid runs); fall back to transport.client_id; then env.

    Free-function replacement for the former
    ``BrowserUseRunner._resolve_acct_site_id`` static method.
    """
    if mainwin is not None and hasattr(mainwin, "getAcctSiteID"):
        try:
            site = mainwin.getAcctSiteID()
            if site:
                return site
        except Exception:
            pass
    if transport is not None and hasattr(transport, "client_id"):
        return transport.client_id
    return os.environ.get("EC_ACCT_SITE_ID", "").strip() or None


async def run_cloud_agent(
    task: str,
    state: dict,
    mainwin: Any,
    calling_agent_id: str | None,
    *,
    skill_name: str,
    node_name: str,
    owner: str,
    use_vision: bool,
    use_thinking: bool,
    use_judge: bool,
    llm_provider: str,
    llm_model_name: str,
    raw_inputs: dict,
) -> dict:
    """Run via :class:`CloudAgent` with passive transport for browser ops.

    Module-level entry point (no runner instance required).  Free-function
    implementation; replaces the former
    ``BrowserUseRunner._run_cloud_agent`` instance method (the
    ``_NoSessionsShim`` wrapper hack is no longer needed).
    """
    from agent.ec_skills.browser_use_extension.cloud_agent import CloudAgent
    from agent.ec_skills.browser_use_extension.extension_tools_service import (
        custom_controller,
        set_current_agent,
    )

    logger.info("[BrowserAutomation] Running in CLOUD AGENT mode (hybrid_cloud/full_cloud)")
    send_skill_editor_log("log", "[BrowserAutomation] Starting cloud agent mode")

    try:
        llm = _build_cloud_llm_impl(
            llm_provider=llm_provider,
            llm_model_name=llm_model_name,
            raw_inputs=raw_inputs,
        )
        transport = _build_cloud_transport_impl()
        run_id = _resolve_cloud_run_id_impl(state)
        cloud_agent_id = (state.get("attributes") or {}).get("agent_id") if isinstance(state, dict) else None
        acct_site_id = _resolve_acct_site_id_impl(mainwin, transport)

        agent_kwargs = {
            "use_vision": use_vision,
            "use_thinking": use_thinking,
            "use_judge": use_judge,
        }
        if not use_thinking:
            agent_kwargs["extend_system_message"] = THINKING_SUPPRESSION_INSTRUCTION.strip()

        agent = CloudAgent(
            task=task,
            llm=llm,
            controller=custom_controller,
            transport=transport,
            run_id=run_id,
            acct_site_id=acct_site_id,
            agent_id=cloud_agent_id,
            skill_id=skill_name,
            node_id=node_name,
            **agent_kwargs,
        )
        try:
            setattr(agent, "_ecan_skill_name", skill_name)
            setattr(agent, "_ecan_node_id", node_name)
            setattr(agent, "_ecan_owner", owner)
        except Exception:
            pass
        set_current_agent(agent)

        try:
            desc = agent.tools.registry.get_prompt_description(page_url=None)
            logger.info(
                f"[Browser-Use] LLM sees {len(agent.tools.registry.actions)} total actions in system prompt"
            )
            logger.debug(f"[Browser-Use] Full tool list for LLM:\n{desc}")
        except Exception:
            pass

        logger.info(f"[BrowserAutomation] Starting CloudAgent run_id={run_id}")
        send_skill_editor_log("log", f"[BrowserAutomation] CloudAgent starting, run_id={run_id}")
        history = await agent.run()
        log_step_budget(agent)

        final = history.final_result() if hasattr(history, "final_result") else None
        _log_browser_use_result_summary(history, skill_name=skill_name, node_name=node_name)

        logger.info("[BrowserAutomation] CloudAgent completed")
        send_skill_editor_log("log", "[BrowserAutomation] CloudAgent completed")
        return {
            "cloud": True,
            "client_assisted_cloud": True,
            "mode": "client_assisted_cloud",
            "run_id": run_id,
            "final": final,
            "history": str(history),
        }
    except Exception as exc:
        err = get_traceback(exc, "ErrorBuildBrowserAutomationNodeCloudAgent")
        logger.error(err)
        send_skill_editor_log("error", err)
        return {"error": str(err)}


# ─── Phase 6.3 lift target (2026-04-24) ────────────────────────────
# Lifted verbatim from build_node.py.  Class body already converted to
# self.ctx.* in Phase 6.2 — no closure refs remain.  External
# dependencies (logger, RunContext, BrowserUseHookContext,
# _AssignmentContext, _first_invocation_done, etc.) are imported at
# the top of this module.

class BrowserRunSession:
    """Per-call orchestrator for a single ``_run_browser_use`` invocation.

    Lifted to module scope in Phase 6.3 (2026-04-24).  Originally a
    nested class inside :func:`build_browser_automation_node` that
    captured ~50 closure refs via Python's lexical scoping; those refs
    are now threaded explicitly through the :class:`RunContext`
    dataclass on ``self.ctx``.

    Lifecycle: one instance per ``_run_browser_use`` invocation
    (constructed by the thin delegator in ``build_node.py``).  Reused
    state (browser-session caches, browser-use agent caches, focus
    target ids, dispatch state) lives on ``self.ctx``, which is itself
    constructed once per compiled node and shared across every
    pend-event-loop iteration.

    The 18 methods split the run flow into named phases — see
    :meth:`run` for the orchestration order.  Each phase method
    references closure data via ``self.ctx.<name>`` and per-call data
    via ``self.task`` / ``self.mainwin`` / ``self.state`` /
    ``self.calling_agent_id``.

    See ``REFACTOR_ROADMAP.md`` for the multi-phase decomposition
    history that produced this class.
    """

    def __init__(self, *, ctx, task, mainwin, state, calling_agent_id):
        self.ctx = ctx
        self.task = task
        self.mainwin = mainwin
        self.state = state
        self.calling_agent_id = calling_agent_id

    def _build_hook_ctx(self) -> "BrowserUseHookContext":
        """Factory for the BrowserUseHookContext passed to every hook.

        All three hook phases (before_browser_session_setup,
        before_prompt_build, before_browser_use_run) need the same
        wide context — this method captures the 16 build-scope
        references in one place so the call sites become a single
        line.  Hooks use this to access build-scope helpers
        (scope-key resolution, runtime-input extraction, dispatch
        state) without ``build_node`` having to plumb each one as
        a parameter.

        Closure refs (via the nested class scope): ``node_name``,
        ``_resolve_browser_scope_key``, ``_extract_runtime_invocation_input``,
        ``_parse_json_input``, ``send_skill_editor_log``,
        ``_normalize_dispatch_identity_key``, ``_SafeFormatDict``,
        ``_cached_browser_sessions``, ``_dispatch_state_by_agent``,
        ``_is_dispatch_inflight``, ``_mark_dispatch_inflight``,
        ``_clear_dispatch_inflight``, ``_DISPATCH_INFLIGHT_TTL_S``,
        ``_resolve_template``, ``_get_or_create_browser_session``
        from ``build_browser_automation_node``.
        """
        return BrowserUseHookContext(
            node_name=str(self.ctx.node_name or ""),
            calling_agent_id=str(self.calling_agent_id or ""),
            mainwin=self.mainwin,
            resolve_scope_key=lambda s: _bh.resolve_browser_scope_key(
                s,
                node_name=self.ctx.node_name,
                skill_name=self.ctx.skill_name,
            ),
            extract_runtime_invocation_input=_bh.extract_runtime_invocation_input,
            parse_json_input=_parse_json_input,
            send_log=send_skill_editor_log,
            normalize_dispatch_identity_key=_normalize_dispatch_identity_key,
            safe_format_dict=_SafeFormatDict,
            cached_browser_sessions=_bh.cached_browser_sessions,
            dispatch_state_by_agent=_dispatch_state_by_agent,
            is_dispatch_inflight=_is_dispatch_inflight,
            mark_dispatch_inflight=_mark_dispatch_inflight,
            clear_dispatch_inflight=_clear_dispatch_inflight,
            inflight_ttl_s=_DISPATCH_INFLIGHT_TTL_S,
            resolve_template=_resolve_template,
            # Phase 6.7: wrap to bind ctx=self.ctx; the hook contract still
            # expects ``get_or_create_browser_session(mainwin, state=..., calling_agent_id=...)``.
            get_or_create_browser_session=(
                lambda mainwin, state=None, calling_agent_id=None:
                    _bh.get_or_create_browser_session(
                        mainwin, state=state, calling_agent_id=calling_agent_id, ctx=self.ctx,
                    )
            ),
            # Pipe the flowgram per-node runEnvironment flag through so
            # the v2 hook wire-up can pick the right RunMode.
            run_environment=str(self.ctx.run_environment_setting or "full_local"),
        )

    async def _inject_event_context(
        self,
        *,
        task: str,
    ) -> tuple[dict | None, str, str | None]:
        """Inject the triggering-event hint into the task string.

        When this browser_automation node was resumed by pend_event
        after an event (browser_event, chat_message, etc.), expose
        the event metadata so the LLM knows WHY this invocation
        was triggered.  Also runs the ``before_prompt_build`` hook
        phase, which may short-circuit by returning a state dict.

        Returns ``(early_exit, task, evt_type)`` where:

        * ``early_exit`` is a state dict (when a prompt-build hook
          short-circuits) or ``None`` (proceed normally).
        * ``task`` is the (possibly augmented) task string with
          event context and any actionable-items override prepended.
        * ``evt_type`` is the resolved event type (``browser_event``,
          ``chat_message``, etc.) for downstream consumers.

        Closure refs (via the nested class scope): ``actionable_field``,
        ``node_name``, ``inputs``, ``_before_prompt_build_hooks``
        from ``build_browser_automation_node``.
        """
        state = self.state
        _override_block = ""  # prepended to task when actionable_items is non-empty
        _evt_type: str | None = None
        try:
            from agent.ec_skills.browser_node.runner import (
                extract_triggering_event as _extract_evt,
            )
            _evt, _evt_type, _evt_ctx, _evt_label = _extract_evt(state)
            if _evt_type:
                _evt_lines = [
                    "## Triggering Event",
                    f"This invocation was resumed by a **{_evt_type}** event.",
                ]
                if _evt_label:
                    _evt_lines.append(f"Event label: **{_evt_label}**")
                if _evt_type == "browser_event":
                    from agent.ec_skills.browser_node.runner import (
                        build_browser_event_base_hint as _build_base_hint,
                    )
                    _new_msg_hint = _build_base_hint(_evt_label)
                    # Inject raw event body items so the LLM has the
                    # current snapshot without needing to call a list
                    # tool.  Resolution + compaction delegated to helpers.
                    try:
                        from agent.ec_skills.browser_node.runner import (
                            resolve_event_actionable_items as _resolve_evt_items,
                            compact_actionable_items as _compact_items_fn,
                        )
                        _evt_items, _evt_items_src = _resolve_evt_items(
                            evt_ctx=_evt_ctx, evt_label=_evt_label, state=state
                        )
                        if _evt_items and _evt_items_src:
                            logger.info(
                                f"[BrowserAutomation] actionable_items source="
                                f"{_evt_items_src} ({len(_evt_items)} item(s)), "
                                f"node={self.ctx.node_name}"
                            )
                        if _evt_items:
                            _compact_items = _compact_items_fn(_evt_items)
                            if _compact_items:
                                # Compute actionable_raw once: the subset of compact_items
                                # whose configured actionable_field is non-empty.  Empty when
                                # the node author didn't opt into the actionable-items pattern.
                                #
                                # 2026-05-25 mt042A: when actionable_field is
                                # ``pending_timer`` (the live-chat sidebar
                                # convention), also accept rows whose
                                # pending_timer is empty BUT
                                # unread_badge >= 1.  The real site populates
                                # pending_timer lazily — seconds to minutes
                                # after the new row appears in the sidebar —
                                # so the FIRST dom_observed for a card / image
                                # / image-with-text customer message arrives
                                # with pending_timer='' and unread_badge='1'.
                                # Pre-mt042A the actionable filter dropped
                                # these rows entirely and PreDispatch ran
                                # with 0 items → no dispatch → no re-emit
                                # until the customer's NEXT interaction or a
                                # platform stall warning fires.
                                # Live trace 2026-05-25 14:54:42 肽斯特:
                                # pasted product card, pending_timer='',
                                # unread_badge='1' → filtered out → bot
                                # silent for 1m32s until platform stall
                                # warning poisoned the sidebar with a system
                                # pattern, after which thread-scrape fallback
                                # kept failing on tab focus.
                                #
                                # The unread_badge fallback only WIDENS the
                                # actionable set (never narrows it) — items
                                # that pass today still pass.
                                def _mt042a_actionable(it: dict) -> bool:
                                    af = self.ctx.actionable_field
                                    if str(it.get(af, "") or "").strip():
                                        return True
                                    if af == "pending_timer":
                                        try:
                                            return int(str(it.get("unread_badge", "0") or "0").strip() or "0") >= 1
                                        except (TypeError, ValueError):
                                            return False
                                    return False
                                _actionable_raw = (
                                    [it for it in _compact_items if _mt042a_actionable(it)]
                                    if self.ctx.actionable_field else []
                                )
                                try:
                                    from agent.ec_skills import live_chat_dispatch as _lcd
                                    # Bridge None -> AttributeError -> same
                                    # silent fallback as the old failed import.
                                    _lc_ledger = _lcd.runner_bridge().trace_ledger.log_event

                                    for _it in _actionable_raw:
                                        if not isinstance(_it, dict):
                                            continue
                                        _cust = (
                                            _it.get("customer_id")
                                            or _it.get("customer_name")
                                            or _it.get("name")
                                            or ""
                                        )
                                        if not _cust:
                                            continue
                                        _lc_ledger(
                                            "actionable_resolved",
                                            customer=str(_cust),
                                            customer_id=str(_it.get("customer_id") or ""),
                                            customer_name=str(_it.get("customer_name") or _it.get("name") or ""),
                                            session_id=str(_it.get("session_id") or _it.get("identity_key") or ""),
                                            source_msg_id=str(_it.get("latest_message_msg_id") or _it.get("msg_id") or ""),
                                            latest_preview=str(
                                                _it.get("latest_message")
                                                or _it.get("last_message")
                                                or _it.get("message")
                                                or ""
                                            ),
                                            source=str(_evt_items_src or ""),
                                            event_label=str(_evt_label or ""),
                                            node=self.ctx.node_name,
                                            actionable_count=len(_actionable_raw),
                                            compact_count=len(_compact_items),
                                        )
                                except Exception:
                                    pass

                                # Invoke prompt-build hooks.  Site plugins register here to
                                # apply business-case-specific enrichment.  If any hook
                                # supplies non-empty text (or a short_circuit_state), the
                                # generic fallback injection below is skipped.
                                _pb_handled = False
                                if self.ctx.before_prompt_build_hooks:
                                    _pb_ctx = PromptBuildContext(
                                        compact_items=list(_compact_items),
                                        actionable_raw=list(_actionable_raw),
                                        actionable_field=str(self.ctx.actionable_field or ""),
                                        event_type=str(_evt_type or ""),
                                        event_label=str(_evt_label or ""),
                                    )
                                    _pb_hook_ctx = self._build_hook_ctx()
                                    for _pb_hook in self.ctx.before_prompt_build_hooks:
                                        _pb_result = await _pb_hook(state, self.ctx.inputs, _pb_hook_ctx, _pb_ctx)
                                        if _pb_result is None:
                                            continue
                                        if _pb_result.short_circuit_state is not None:
                                            state.update(_pb_result.short_circuit_state)
                                            return state, task, _evt_type
                                        if _pb_result.task_hint_append:
                                            _new_msg_hint += _pb_result.task_hint_append
                                            _pb_handled = True
                                        if _pb_result.override_prepend:
                                            _override_block = _pb_result.override_prepend + _override_block
                                            _pb_handled = True

                                # Generic fallback injection when no prompt-build
                                # hook added text.  See helper docstring.
                                if not _pb_handled:
                                    from agent.ec_skills.browser_node.runner import (
                                        build_actionable_items_fallback_text as _build_fallback_text,
                                    )
                                    _new_msg_hint += _build_fallback_text(
                                        compact_items=_compact_items,
                                        actionable_raw=_actionable_raw,
                                        actionable_field=str(self.ctx.actionable_field or ""),
                                        node_name=self.ctx.node_name,
                                    )
                    except Exception:
                        pass
                    _evt_lines.append(_new_msg_hint)
                elif _evt_type == "chat_message":
                    from agent.ec_skills.browser_node.runner import (
                        build_chat_message_event_line as _build_chat_line,
                    )
                    _evt_lines.append(_build_chat_line(state))
                task = f"{task}\n\n" + "\n".join(_evt_lines)
                logger.info(
                    f"[BrowserAutomation] Injected triggering event context "
                    f"(event_type={_evt_type}, label={_evt_label}, node={self.ctx.node_name})"
                )
        except Exception as _evt_inject_err:
            logger.info(f"[BrowserAutomation] Failed to inject event context: {_evt_inject_err}")

        # Prepend the override block so it appears BEFORE the user's system
        # prompt. The LLM processes the task top-to-bottom; putting these
        # rules first ensures they take precedence over any conflicting
        # anti-duplicate heuristics in the system prompt.
        if _override_block:
            task = _override_block + task
            logger.info(
                f"[BrowserAutomation] Prepended actionable_items protocol override "
                f"(node={self.ctx.node_name}, override_len={len(_override_block)})"
            )

        return None, task, _evt_type

    async def _invoke_early_hooks(self) -> dict | None:
        """Invoke registered before-browser-session-setup hooks.

        Early hooks run BEFORE the (expensive) browser-use agent
        is constructed, so a live-chat-style fast-path (HOT-PATH-B:
        chat_message arrives with a pre-computed reply, type it
        into the site directly, short-circuit the LLM) doesn't pay
        for agent setup it will throw away.  Hooks acquire a
        browser session via ``hook_ctx.get_or_create_browser_session``.

        Returns the first hook's non-``None`` state dict (which
        short-circuits the whole node), or ``None`` to let the
        late phase run.

        Closure refs (via the nested class scope):
        ``_before_browser_session_setup_hooks``, ``inputs``
        from ``build_browser_automation_node``.
        """
        if not self.ctx.before_browser_session_setup_hooks:
            return None
        _early_hook_ctx = self._build_hook_ctx()
        for _early_hook in self.ctx.before_browser_session_setup_hooks:
            _early_result = await _early_hook(
                None, self.state, self.ctx.inputs, _early_hook_ctx
            )
            if _early_result is not None:
                return _early_result
        return None

    async def _extract_assignment_and_scope(
        self,
        *,
        task: str,
        runtime_input: str,
    ) -> tuple[dict | None, str, _AssignmentContext]:
        """Extract assignment scope, run the assignment gate, resolve scope keys.

        Three sub-steps:

        1. Pull ``session_id``, ``tab_id``, ``chat_url``,
           ``customer_name`` out of ``runtime_input`` (or fall back
           to ``state.chat_id``).
        2. Apply the data-driven assignment gate: when configured
           ``require_any_of`` fields are missing and ``on_missing
           == "skip_node"``, return an early-exit state dict.  When
           a ``scope_contract_template`` is configured, render it
           with the assignment values and append to ``task``.
        3. Resolve the browser scope key, look up the cached session
           and last-known focus target id.

        Returns ``(early_exit, task, _AssignmentContext)``:

        * ``early_exit`` is the state dict to return directly from
          :meth:`run` when the assignment gate skips the node, or
          ``None`` (proceed normally).
        * ``task`` is the (possibly augmented) task string.
        * The :class:`_AssignmentContext` bundles the 8 cross-phase
          vars consumed by downstream phases.

        Closure refs (via the nested class scope): ``inputs``,
        ``_extract_assignment_scope``, ``_parse_json_input``,
        ``_SafeFormatDict``, ``_resolve_browser_scope_key``,
        ``_cached_browser_sessions``, ``_last_known_focus_target_ids``,
        ``node_name`` from ``build_browser_automation_node``.
        """
        state = self.state
        assignment_scope = _bh.extract_assignment_scope(runtime_input)
        assignment_session_id = str(
            assignment_scope.get("session_id")
            or assignment_scope.get("sessionId")
            or (state.get("chat_id") if isinstance(state, dict) else "")
            or ""
        ).strip()
        assignment_tab_id = str(
            assignment_scope.get("tab_id") or assignment_scope.get("tabId") or ""
        ).strip()
        assignment_chat_url = str(
            assignment_scope.get("chat_url") or assignment_scope.get("chatUrl") or ""
        ).strip()
        assignment_customer_name = str(
            assignment_scope.get("customer_name") or assignment_scope.get("customerName") or ""
        ).strip()

        # ── Data-driven assignment gate + scope-contract injection ──
        # Replaces the previous `if skill_name == "rt_chat_bot":` block.
        # Config shape (authored on the node editor as JSON):
        #   {
        #     "enabled": true,
        #     "require_any_of": ["session_id", "chat_url"],
        #     "on_missing": "skip_node",   // or "proceed"
        #     "scope_contract_template": "## Runtime Scope Contract ...\n..."
        #   }
        # Template placeholders: {session_id}, {tab_id}, {chat_url},
        # {customer_name}.  Missing keys render as empty strings.
        _asg_cfg = _parse_json_input(self.ctx.inputs, "assignment")
        if isinstance(_asg_cfg, dict) and _asg_cfg.get("enabled", True):
            _require_any = [str(f) for f in (_asg_cfg.get("require_any_of") or [])]
            if _require_any:
                _scope_values = {
                    "session_id": assignment_session_id,
                    "tab_id": assignment_tab_id,
                    "chat_url": assignment_chat_url,
                    "customer_name": assignment_customer_name,
                }
                _present = any(str(_scope_values.get(f) or "").strip() for f in _require_any)
                if not _present:
                    _on_missing = str(_asg_cfg.get("on_missing") or "skip_node").strip()
                    if _on_missing == "skip_node":
                        logger.info(
                            f"[BrowserAutomation] assignment gate: require_any_of={_require_any} "
                            f"not present — skipping browser run. node={self.ctx.node_name}, "
                            f"runtime_input={(runtime_input or '')[:200]}"
                        )
                        return (
                            {"result": {"llm_result": {"all_done": False, "work_done": False}}},
                            task,
                            _AssignmentContext(
                                asg_cfg=_asg_cfg,
                                session_id=assignment_session_id,
                                tab_id=assignment_tab_id,
                                chat_url=assignment_chat_url,
                                customer_name=assignment_customer_name,
                                browser_scope_key="",
                                cached_browser_session=None,
                                last_known_focus_target_id=None,
                            ),
                        )

            _tpl = _asg_cfg.get("scope_contract_template")
            if isinstance(_tpl, str) and _tpl.strip():
                try:
                    _rendered = _tpl.format_map(_SafeFormatDict({
                        "session_id": assignment_session_id,
                        "tab_id": assignment_tab_id,
                        "chat_url": assignment_chat_url,
                        "customer_name": assignment_customer_name,
                    }))
                    task = f"{task}\n\n{_rendered}"
                    logger.info(
                        f"[BrowserAutomation] Applied scope contract "
                        f"(session_id={assignment_session_id or 'unknown'}, "
                        f"tab_id={assignment_tab_id or 'none'}), node={self.ctx.node_name}"
                    )
                except Exception as _render_err:
                    logger.warning(
                        f"[BrowserAutomation] Scope contract render failed "
                        f"(non-fatal): {_render_err}"
                    )

        _browser_scope_key = _bh.resolve_browser_scope_key(
            state,
            node_name=self.ctx.node_name,
            skill_name=self.ctx.skill_name,
        )
        _cached_browser_session = _bh.cached_browser_sessions.get(_browser_scope_key)
        _last_known_focus_target_id = _bh.last_known_focus_target_ids.get(_browser_scope_key)

        return (
            None,
            task,
            _AssignmentContext(
                asg_cfg=_asg_cfg if isinstance(_asg_cfg, dict) else None,
                session_id=assignment_session_id,
                tab_id=assignment_tab_id,
                chat_url=assignment_chat_url,
                customer_name=assignment_customer_name,
                browser_scope_key=_browser_scope_key,
                cached_browser_session=_cached_browser_session,
                last_known_focus_target_id=_last_known_focus_target_id,
            ),
        )

    def _resolve_run_mode(self) -> tuple[bool, bool]:
        """Determine ``passive_enabled`` and ``cloud_agent_enabled`` from node config.

        Reads the node-editor ``run_environment_setting`` (one of
        ``full_local``, ``passive_local``, ``hybrid_cloud``,
        ``full_cloud``).  Falls back to environment variables
        (``EC_BROWSER_USE_PASSIVE``, ``EC_BROWSER_USE_MODE``,
        ``EC_BROWSER_USE_CLOUD_AGENT``) for backward compatibility
        when the setting is missing or ``full_local``.

        Cloud mode takes precedence over passive mode (i.e. when
        both flags would be true, ``passive_enabled`` is forced to
        False).

        Closure refs (via the nested class scope):
        ``run_environment_setting`` from
        ``build_browser_automation_node``.
        """
        passive_enabled = False
        cloud_agent_enabled = False

        if self.ctx.run_environment_setting == 'passive_local':
            passive_enabled = True
        elif self.ctx.run_environment_setting == 'hybrid_cloud':
            cloud_agent_enabled = True
        elif self.ctx.run_environment_setting == 'full_cloud':
            cloud_agent_enabled = True
        else:
            # full_local or fallback - check env vars for backward compat.
            try:
                passive_enabled = os.environ.get("EC_BROWSER_USE_PASSIVE", "").strip().lower() in {"1", "true", "yes", "on"}
            except Exception:
                passive_enabled = False

            try:
                cloud_agent_enabled = (
                    os.environ.get("EC_BROWSER_USE_MODE", "").strip().lower() in {"client_assisted_cloud", "cloud"}
                    or os.environ.get("EC_BROWSER_USE_CLOUD_AGENT", "").strip().lower() in {"1", "true", "yes", "on"}
                )
            except Exception:
                cloud_agent_enabled = False

        # Cloud mode takes precedence over passive mode.
        if cloud_agent_enabled:
            passive_enabled = False

        logger.info(
            f"[BrowserAutomation] Run mode: run_environment={self.ctx.run_environment_setting}, "
            f"passive={passive_enabled}, cloud={cloud_agent_enabled}"
        )
        return passive_enabled, cloud_agent_enabled

    async def _run_passive_branch(
        self,
        *,
        browser_scope_key: str,
        last_known_focus_target_id,
    ) -> dict:
        """Handle ``passive_local`` run mode (cloud-driven MCP fast-path).

        Two sub-paths handled by helpers in ``browser_node.runner``:

        * **skill_passive_step** — incoming command is an MCP tool
          call from cloud; bypass browser automation entirely and
          execute MCP tools directly via
          :func:`run_skill_passive_step`.
        * **browser_use_passive_step** — normal browser automation
          under cloud control via :func:`run_browser_passive_step`.

        Includes a duplicate-execution guard keyed by
        ``run_id:step_id`` (or ``run_id:node_name`` fallback) using
        the module-level ``_passive_steps_processed`` set + lock.

        Always returns an early-exit dict (the passive branch never
        falls through to the local LLM construction path).

        Closure refs (via the nested class scope): ``node_name``,
        ``calling_agent_id``, ``_get_or_create_browser_session``,
        ``_is_session_started``, ``_last_known_focus_target_ids``,
        ``_cached_passive_agents`` (module-level)
        from ``build_browser_automation_node``.
        """
        try:
            from agent.ec_skills.browser_use_extension.passive_agent import PassiveAgent  # noqa: F401

            # Guard against double-execution: check if this step_id was already processed.
            # Use module-level lock and set to prevent race condition.
            global _passive_steps_processed

            state = self.state
            passive_cmd_check = None
            if isinstance(state, dict):
                attrs_check = state.get("attributes", {})
                passive_cmd_check = attrs_check.get("passive_command")

            # Build step_key from passive_command or fall back to node_name + run_id.
            step_key = None
            if isinstance(passive_cmd_check, dict):
                step_id_check = passive_cmd_check.get("step_id", "")
                run_id_check = passive_cmd_check.get("run_id", "")
                step_key = f"{run_id_check}:{step_id_check}"
            else:
                if isinstance(state, dict):
                    attrs = state.get("attributes", {})
                    run_id_fallback = attrs.get("run_id", "")
                    if run_id_fallback:
                        step_key = f"{run_id_fallback}:{self.ctx.node_name}"

            if step_key:
                with _passive_steps_lock:
                    if step_key in _passive_steps_processed:
                        logger.info(f"[BrowserAutomation] Skipping duplicate execution for step: {step_key}")
                        return {"passive": True, "skipped": True, "reason": "duplicate_execution"}

                    _passive_steps_processed.add(step_key)
                    logger.info(f"[BrowserAutomation] Processing step: {step_key}")
                    if len(_passive_steps_processed) > 1000:
                        _passive_steps_processed = set(list(_passive_steps_processed)[-500:])
            else:
                logger.warning(f"[BrowserAutomation] No step_key available for duplicate detection, proceeding anyway")

            # ── skill_passive_step fast-path ──────────────────────────
            # If the incoming command is a skill_passive_step (MCP tool
            # call from cloud), bypass the entire browser automation
            # setup and execute MCP tools directly.
            passive_cmd = None
            if isinstance(state, dict):
                passive_cmd = state.get("attributes", {}).get("passive_command")
            _cmd_type = passive_cmd.get("type", "") if isinstance(passive_cmd, dict) else ""

            if _cmd_type == "skill_passive_step":
                from agent.ec_skills.browser_node.runner import (
                    run_skill_passive_step as _run_skill_passive_step,
                )
                return await _run_skill_passive_step(passive_cmd, self.mainwin)

            # ── browser_use_passive_step — normal browser automation ──
            # Delegate to browser_node.runner.run_browser_passive_step.
            # Closure-captured helpers are passed explicitly via DI so
            # the helper has no hidden coupling to build_node.py.
            from agent.ec_skills.browser_node.runner import (
                run_browser_passive_step as _run_browser_passive_step,
            )
            return await _run_browser_passive_step(
                state,
                self.mainwin,
                # Phase 6.7: bind ctx=self.ctx for the lifted helper.
                get_browser_session=(
                    lambda mainwin, state=None, calling_agent_id=None:
                        _bh.get_or_create_browser_session(
                            mainwin, state=state, calling_agent_id=calling_agent_id, ctx=self.ctx,
                        )
                ),
                is_session_started=_bh.is_session_started,
                last_known_focus_target_id=last_known_focus_target_id,
                last_known_focus_target_ids=_bh.last_known_focus_target_ids,
                browser_scope_key=browser_scope_key,
                node_name=self.ctx.node_name,
                calling_agent_id=self.calling_agent_id,
                passive_agent_cache=_cached_passive_agents,
            )
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNodePassive")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
            return {"error": str(err_msg)}

    def _resolve_agent_class(self):
        """Choose between vanilla ``BUAgent`` and ``PrivacyAgent``.

        ``PrivacyAgent`` is used when:

        * ``privacy_strategy != 'none'`` (classic privacy path), OR
        * the node opted into the hook system — i.e.
          ``hookBundles`` or ``siteAdapter`` is configured on the
          node, or ``EC_BROWSER_USE_HOOKS_ENABLED=1`` is set in
          the environment.  The hook dispatcher lives inside
          ``PrivacyAgent``, so even hook-only nodes need this
          wrapper.

        Falls back to ``BUAgent`` if ``PrivacyAgent`` import fails.

        Closure refs (via the nested class scope): ``inputs``,
        ``privacy_strategy_setting``
        from ``build_browser_automation_node``.  ``BUAgent`` is
        lazy-imported here because it's also imported inside
        :meth:`run` as a local — methods of a nested class cannot
        see another method's locals, only enclosing-function scope.
        """
        from browser_use import Agent as BUAgent
        _node_hook_bundles_raw = (self.ctx.inputs.get("hookBundles") or {}).get("content")
        _node_site_adapter_raw = (self.ctx.inputs.get("siteAdapter") or {}).get("content")
        _hooks_env_flag = os.environ.get(
            "EC_BROWSER_USE_HOOKS_ENABLED", ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        _node_wants_hooks = bool(
            _hooks_env_flag
            or (isinstance(_node_hook_bundles_raw, str) and _node_hook_bundles_raw.strip())
            or (isinstance(_node_site_adapter_raw, str) and _node_site_adapter_raw.strip())
        )

        AgentClass = BUAgent
        use_privacy_agent = (self.ctx.privacy_strategy_setting != 'none') or _node_wants_hooks

        if use_privacy_agent:
            try:
                from agent.ec_skills.browser_use_extension.privacy_agent import PrivacyAgent
                AgentClass = PrivacyAgent
                if self.ctx.privacy_strategy_setting == 'none' and _node_wants_hooks:
                    logger.info(
                        f"[BrowserAutomation] Upgrading to PrivacyAgent for hook support "
                        f"(privacy=none, hooks_env={_hooks_env_flag}, "
                        f"bundles={bool(_node_hook_bundles_raw)}, "
                        f"site_adapter={bool(_node_site_adapter_raw)})"
                    )
                else:
                    logger.info(f"[BrowserAutomation] Using PrivacyAgent for browser-use (strategy={self.ctx.privacy_strategy_setting})")
            except Exception as _privacy_import_exc:
                logger.info(f"[BrowserAutomation] PrivacyAgent not available, using browser_use.Agent ({_privacy_import_exc})")
        else:
            logger.info("[BrowserAutomation] Privacy strategy is 'none' and no hook bundles configured, using standard browser_use.Agent")

        return AgentClass

    def _build_local_llm_and_kwargs(
        self,
        *,
        browser_scope_key: str,
    ) -> tuple["Any", "Any", dict]:
        """Build the local LLM, attach token context, and assemble ``agent_kwargs``.

        Three sub-steps:

        1. Resolve LLM via :func:`browser_node.runner.build_local_llm`
           (proxy → node-specified provider → Settings default,
           raising ``ValueError`` with an actionable message on
           any path failure).
        2. Attach token context (run-id binding for token-budget
           accounting) via :func:`attach_llm_token_context`.
        3. Build ``agent_kwargs`` via
           :func:`get_agent_kwargs_with_compaction` honoring node
           editor settings: ``use_vision``, ``use_thinking``,
           ``enable_judge``, ``max_actions_per_step``, and
           data-driven DOM size reduction (``domLimit``,
           ``domFocusSelector``).

        Returns ``(llm, controller, agent_kwargs)``.

        Closure refs (via the nested class scope): ``mainwin``,
        ``node_llm_provider``, ``node_model_name``, ``inputs``,
        ``skill_name``, ``node_name``, ``custom_controller``,
        ``node_use_vision``, ``node_use_thinking``,
        ``enable_judge_setting``, ``node_max_actions_per_step``,
        ``node_dom_limit``, ``node_dom_focus_selector``
        from ``build_browser_automation_node``.  ``custom_controller``
        is lazy-imported here because it's also imported inside
        :meth:`run` as a local — methods of a nested class cannot
        see another method's locals, only enclosing-function scope.
        """
        from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
        from agent.ec_skills.browser_node.runner import (
            build_local_llm as _build_local_llm,
            attach_llm_token_context as _attach_token_ctx,
        )
        llm = _build_local_llm(
            self.mainwin,
            llm_provider=self.ctx.node_llm_provider,
            llm_model_name=self.ctx.node_model_name,
            raw_inputs=self.ctx.inputs,
        )
        _attach_token_ctx(
            llm,
            self.state,
            skill_name=self.ctx.skill_name,
            node_name=self.ctx.node_name,
            llm_provider=self.ctx.node_llm_provider,
            llm_model_name=self.ctx.node_model_name,
            browser_scope_key=browser_scope_key,
        )

        controller = custom_controller

        # Use unified agent configuration for consistency across local and cloud modes.
        from agent.ec_skills.browser_use_extension.agent_config import get_agent_kwargs_with_compaction

        # Data-driven DOM size reduction via node editor settings.
        # domLimit (chars) caps max_clickable_elements_length; domFocusSelector
        # prunes non-matching elements via CDP before DOM extraction.
        if self.ctx.node_dom_limit:
            logger.info(
                f"[BrowserAutomation] DOM limit set to "
                f"{self.ctx.node_dom_limit} chars (was default ~18-25K)"
            )
        if self.ctx.node_dom_focus_selector:
            logger.info(
                f"[BrowserAutomation] DOM focus selector: {self.ctx.node_dom_focus_selector!r}"
            )

        agent_kwargs = get_agent_kwargs_with_compaction(
            use_vision=self.ctx.node_use_vision,
            use_thinking=self.ctx.node_use_thinking,
            use_judge=self.ctx.enable_judge_setting,
            llm=llm,
            max_actions_per_step=self.ctx.node_max_actions_per_step,
            **({'max_clickable_elements_length': self.ctx.node_dom_limit} if self.ctx.node_dom_limit else {}),
        )
        # Log the actual message_compaction settings (INFO level for visibility).
        if 'message_compaction' in agent_kwargs:
            mc = agent_kwargs['message_compaction']
            logger.info(
                f"[BrowserAutomation] ⚡ Agent Config: "
                f"compaction=enabled={mc.enabled}, every={mc.compact_every_n_steps}steps, "
                f"trigger={mc.trigger_char_count}chars, keep={mc.keep_last_items}items, "
                f"summary={mc.summary_max_chars}chars, "
                f"max_clickable={agent_kwargs.get('max_clickable_elements_length', 'default')}, "
                f"max_input_tokens={agent_kwargs.get('max_input_tokens', 'N/A')}, "
                f"max_actions_per_step={agent_kwargs.get('max_actions_per_step', 'default')}"
            )
        else:
            logger.warning("[BrowserAutomation] ⚠️ No message_compaction in agent_kwargs - history may grow unbounded!")

        return llm, controller, agent_kwargs

    def _build_browser_profile_and_callbacks(
        self,
        *,
        agent_kwargs: dict,
        task: str,
    ) -> tuple["Any", dict, bool]:
        """Build browser profile, attach lifecycle callbacks, populate file paths.

        Five sub-steps (mutates ``agent_kwargs`` in place):

        1. Build the persistent ``BrowserProfile`` via
           :func:`browser_node.runner.build_browser_profile`
           (auto-assigns ``user_data_dir`` under
           ``<user_data>/browser_profiles/<safe_id>/`` if the
           node didn't set one, cleans stale Chromium lock files).
        2. Apply fingerprint / stealth via :func:`apply_stealth_fingerprint`
           and return the resolved ``fp_profile`` so the post-CDP
           stealth-JS injection can reuse it.
        3. Attach per-step + on-done lifecycle callbacks
           (:func:`make_browser_step_callback`,
           :func:`make_browser_done_callback`).  The done-callback
           fires only when ``event_monitor_done_policy == 'stop'``.
        4. Populate ``available_file_paths`` from ``state``
           (init_params / analyze_product output) via
           :func:`resolve_available_file_paths`.
        5. Apply the extract-tool ``max_char_limit`` patch derived
           from ``max_input_tokens`` via :func:`maybe_apply_extract_patch`.

        Returns ``(fp_profile, agent_ref, keep_browser_alive)``.
        ``agent_ref`` is a ``dict`` shared with the done-callback so
        the agent registers itself for the callback's session lookup.

        Closure refs (via the nested class scope):
        ``_get_browser_profile_settings``, ``node_profile``,
        ``_event_monitor_configs``, ``node_headless``, ``node_name``,
        ``browser_type_setting``, ``event_monitor_done_policy``
        from ``build_browser_automation_node``.
        """
        from agent.ec_skills.browser_node.runner import (
            build_browser_profile as _build_browser_profile,
            apply_stealth_fingerprint as _apply_stealth_fp,
            make_browser_step_callback as _make_step_cb,
            make_browser_done_callback as _make_done_cb,
            resolve_available_file_paths as _resolve_afp,
            maybe_apply_extract_patch as _maybe_extract_patch,
        )

        # Per-run browser identity (SHARED_SKILL Phase 3/B2): state-carried
        # overrides (task browser_identity / scheduler slot) win over the
        # node's build-time config so tasks sharing one skill can each run
        # their own browser profile / user_data_dir / headless mode.
        _run_identity = _bh.resolve_state_browser_identity(self.state)
        _effective_profile = _run_identity.get("browser_profile") or self.ctx.node_profile
        _effective_user_data_dir = (
            _run_identity.get("user_data_dir") or self.ctx.user_data_dir_setting
        )
        _effective_headless = _run_identity.get("headless")
        if _effective_headless is None:
            _effective_headless = self.ctx.node_headless
        if _run_identity:
            logger.info(
                f"[BrowserAutomation] Per-run browser identity overrides for "
                f"node={self.ctx.node_name}: {sorted(_run_identity.keys())} → "
                f"effective profile={_effective_profile!r} "
                f"user_data_dir={_effective_user_data_dir!r} "
                f"headless={_effective_headless} "
                f"(node config: profile={self.ctx.node_profile!r} "
                f"user_data_dir={self.ctx.user_data_dir_setting!r} "
                f"headless={self.ctx.node_headless})"
            )

        profile_settings = _bh.get_browser_profile_settings(_effective_profile)

        # Merge node-level stealth settings into profile_settings
        if self.ctx.enable_stealth_setting:
            profile_settings = profile_settings or {}
            profile_settings["enableStealth"] = True

        # Merge per-run/node-level user_data_dir if specified (overrides platform profile)
        if _effective_user_data_dir:
            profile_settings = profile_settings or {}
            profile_settings["user_data_dir"] = _effective_user_data_dir
        
        # Pass platform profile settings to build_browser_profile
        if self.ctx.enable_platform_profile_setting:
            profile_settings = profile_settings or {}
            profile_settings["enable_platform_profile"] = True
            profile_settings["use_pc_chrome"] = self.ctx.use_pc_chrome_setting
        
        # Extract target URL for platform-aware profile selection
        target_url = None
        try:
            # Try to get URL from task params
            task_params = getattr(self, '_task_params', {}) or {}
            task_text = task_params.get('task_text', '') or str(task_params)
            
            # Extract URL patterns from task
            import re
            url_patterns = re.findall(r'https?://[^\s<>"\']+', task_text)
            if url_patterns:
                target_url = url_patterns[0]
                logger.info(f"[BrowserAutomation] Extracted target URL for platform profile: {target_url}")
        except Exception:
            pass
        
        keep_browser_alive = bool(self.ctx.node_keep_browser_alive or self.ctx.event_monitor_configs)

        # Diagnostic: a ~10 s silent gap was observed between profile build and
        # the "Using persistent profile" log below. Bracket both suspect calls
        # so the next slow run pinpoints which one stalls.
        _bp_t0 = time.perf_counter()
        browser_profile = _build_browser_profile(
            profile_settings=profile_settings,
            node_profile=_effective_profile,
            keep_alive=keep_browser_alive,
            headless=_effective_headless,
            target_url=target_url,
        )
        _bp_dt_ms = (time.perf_counter() - _bp_t0) * 1000.0
        if _bp_dt_ms > 500.0:
            logger.warning(
                f"[BrowserAutomation][Perf] _build_browser_profile took {_bp_dt_ms:.0f} ms "
                f"(node={self.ctx.node_name})"
            )

        # Fingerprint / stealth — reused by the later stealth-JS injection
        # step (after CDP connects).
        _fp_t0 = time.perf_counter()
        _fp_profile = _apply_stealth_fp(
            browser_profile,
            profile_settings,
            calling_agent_id=self.calling_agent_id,
            node_name=self.ctx.node_name,
        )
        _fp_dt_ms = (time.perf_counter() - _fp_t0) * 1000.0
        if _fp_dt_ms > 500.0:
            logger.warning(
                f"[BrowserAutomation][Perf] _apply_stealth_fp took {_fp_dt_ms:.0f} ms "
                f"(node={self.ctx.node_name}, stealth_enabled={bool(_fp_profile)})"
            )

        if self.ctx.browser_type_setting == 'new chromium':
            logger.info("[BrowserAutomation] Using persistent Chromium profile for new chromium mode")
        else:
            logger.info("[BrowserAutomation] Using persistent profile for existing-browser/CDP mode")
        try:
            from config.app_settings import app_settings as _bn_app_settings
            _disable_ext = _bn_app_settings.is_dev_mode
        except Exception:
            _disable_ext = False
        logger.info(f"[BrowserAutomation] Extensions {'disabled (dev mode)' if _disable_ext else 'enabled (production mode)'}")
        if keep_browser_alive:
            logger.info("[BrowserAutomation] Browser profile keep_alive enabled for event-monitored workflow")

        if browser_profile:
            agent_kwargs['browser_profile'] = browser_profile

        # Lifecycle callbacks: per-step progress + on-done event-monitor stop.
        # Factories close over the names they need (node_name for the step
        # label, _agent_ref for the done-callback's session lookup).
        _agent_ref: dict[str, "Any"] = {}
        if self.ctx.event_monitor_configs and self.ctx.event_monitor_done_policy == "stop":
            agent_kwargs["register_done_callback"] = _make_done_cb(_agent_ref)
        agent_kwargs["register_new_step_callback"] = _make_step_cb(self.ctx.node_name)

        # available_file_paths: scan state for product_dir
        # (init_params / analyze_product output) and return absolute
        # paths to every non-UUID image file.
        try:
            _file_paths = _resolve_afp(self.state)
            if _file_paths:
                agent_kwargs["available_file_paths"] = _file_paths
        except Exception as _afp_err:
            logger.warning(f"[BrowserAutomation] Failed to set available_file_paths: {_afp_err}")

        logger.info(f"[BrowserAutomation] Agent kwargs: {agent_kwargs}")
        logger.debug("[BROWSER USE]Agent task:", task)

        # Apply extract-tool max_char_limit patch from max_input_tokens.
        _maybe_extract_patch(agent_kwargs)

        # NOTE (2026-05-11): the "serialize browser-use's get_browser_state_summary
        # via the per-session CDP operation lock" patch was REMOVED — it was
        # the prime suspect for the hard process hang at 18:58 (deadlock in the
        # agent step loop), and the data never showed browser-use's own
        # state-build was actually contending with the live-chat send/scrape path.
        # If we revisit this, do it as an explicit reentrant-by-asyncio-task
        # lock with a much shorter acquire timeout, and validate it under flood.

        return _fp_profile, _agent_ref, keep_browser_alive

    def _apply_post_kwargs_extensions(
        self,
        *,
        agent_kwargs: dict,
        use_privacy_agent: bool,
    ) -> None:
        """Apply optional cloud-LLM-transport + hook-bundle kwargs.

        Two strictly-additive extensions, both mutate ``agent_kwargs``:

        1. ``maybe_apply_cloud_llm_kwargs`` — wires cloud LLM
           transport for ``PrivacyAgent`` when an env-flag is
           set.  No-op for vanilla ``BUAgent``.
        2. ``apply_hook_bundle_kwargs`` — parses ``hookBundles`` /
           ``siteAdapter`` from inputs, sets ``hooks_enabled`` per
           env-var or per-node opt-in, and turns privacy filtering
           off when the upgrade was hook-only.  Only runs when
           ``use_privacy_agent`` is True (the dispatcher lives
           inside ``PrivacyAgent``).

        Closure refs (via the nested class scope): ``mainwin``
        (closure of outer fn? no — method-local of run; we use
        ``self.mainwin``), ``calling_agent_id``,
        ``skill_name``, ``node_name``, ``system_prompt_id``,
        ``user_prompt_id``, ``inputs``, ``privacy_strategy_setting``
        from ``build_browser_automation_node``.
        """
        from agent.ec_skills.browser_node.runner import (
            maybe_apply_cloud_llm_kwargs as _maybe_cloud_kwargs,
        )
        _maybe_cloud_kwargs(
            agent_kwargs,
            self.mainwin,
            use_privacy_agent=use_privacy_agent,
            calling_agent_id=self.calling_agent_id,
            skill_name=self.ctx.skill_name,
            node_name=self.ctx.node_name,
            system_prompt_id=self.ctx.system_prompt_id,
            user_prompt_id=self.ctx.user_prompt_id,
        )

        if use_privacy_agent:
            from agent.ec_skills.browser_node.runner import (
                apply_hook_bundle_kwargs as _apply_hook_kwargs,
            )
            _apply_hook_kwargs(
                agent_kwargs, self.ctx.inputs, privacy_strategy=self.ctx.privacy_strategy_setting
            )

    async def _acquire_browser_and_agent(
        self,
        *,
        AgentClass,
        task: str,
        llm,
        controller,
        agent_kwargs: dict,
        fp_profile,
        agent_ref: dict,
        keep_browser_alive: bool,
        last_known_focus_target_id,
        asg_ctx,
    ) -> tuple["Any", "Any"]:
        """Acquire the browser session + browser-use Agent.

        Two mutually-exclusive paths driven by ``browser_type_setting``:

        * **new chromium** — let browser-use create and manage its
          own Chromium instance.  Just acquires-or-reuses a cached
          local agent via :func:`acquire_or_reuse_local_agent`.
        * **existing browser via CDP** — connects to an existing
          Chromium via :func:`_get_or_create_browser_session`,
          starts CDP + injects stealth-JS via
          :func:`start_cdp_session_with_stealth`, runs the focus
          preflight (:func:`run_cdp_focus_preflight`), executes
          pre-run navigation (:func:`run_pre_run_navigation`) to
          anchor the focused tab at the assignment URL, then
          acquires-or-reuses the cached agent.  Suppresses
          browser-use's auto-navigate-from-task-URL when the tab
          is already at the correct URL.  Falls back to creating
          a fresh ``AgentClass`` instance if session creation
          fails or the driver is unsupported.

        Returns ``(agent, last_known_focus_target_id)``.  The
        returned focus id reflects the post-preflight + post-prenav
        value so the run-scope ``_last_known_focus_target_id``
        nonlocal in :meth:`run` stays in sync.

        Side-effect: sets ``agent_ref['agent']`` so the
        done-callback registered earlier can find the agent.

        Closure refs (via the nested class scope):
        ``browser_type_setting``, ``browser_driver_setting``,
        ``_resolve_browser_scope_key``, ``_cached_bu_agents``,
        ``loop_history_mode``, ``_get_or_create_browser_session``,
        ``_is_session_started``,
        ``_patch_browser_session_lifecycle_debug``,
        ``assignment_tab_id``, ``assignment_chat_url``,
        ``assignment_session_id``, ``assignment_customer_name``,
        ``_asg_cfg``, ``skill_name``, ``node_name``
        from ``build_browser_automation_node``.
        """
        from agent.ec_skills.browser_node.runner import (
            acquire_or_reuse_local_agent as _acquire_agent,
        )
        state = self.state
        mainwin = self.mainwin

        if self.ctx.browser_type_setting == 'new chromium':
            # Mode 1: Let browser-use create and manage its own Chromium browser.
            logger.info("[BrowserAutomation] Mode: new chromium - browser-use will create browser")
            _bu_scope_key = _bh.resolve_browser_scope_key(
                state,
                node_name=self.ctx.node_name,
                skill_name=self.ctx.skill_name,
            )
            agent = await _acquire_agent(
                AgentClass=AgentClass,
                task=task,
                llm=llm,
                controller=controller,
                agent_kwargs=agent_kwargs,
                bu_scope_key=_bu_scope_key,
                cached_bu_agents=_bh.cached_bu_agents,
                loop_history_mode=self.ctx.loop_history_mode,
                fp_profile=fp_profile,
            )
            agent_ref["agent"] = agent
            return agent, last_known_focus_target_id

        # Mode 2: Connect to existing browser via CDP.
        logger.info(
            f"[BrowserAutomation] Mode: existing browser - connecting via CDP "
            f"(type={self.ctx.browser_type_setting}, driver={self.ctx.browser_driver_setting})"
        )

        browser_session = await _bh.get_or_create_browser_session(
            mainwin, state=state, calling_agent_id=self.calling_agent_id, ctx=self.ctx,
        )

        if browser_session and self.ctx.browser_driver_setting == 'native':
            log_msg = f"[BrowserAutomation] Connected to browser session: {getattr(browser_session, 'id', 'unknown')}"
            logger.info(log_msg)
            send_skill_editor_log("log", log_msg)

            # CDP session start: keep_alive + lifecycle-debug patches
            # + start() + stealth-JS injection.
            from agent.ec_skills.browser_node.runner import (
                start_cdp_session_with_stealth as _start_cdp_session,
            )
            await _start_cdp_session(
                browser_session,
                keep_browser_alive=keep_browser_alive,
                fp_profile=fp_profile,
                is_session_started=_bh.is_session_started,
                patch_lifecycle_debug=_bh.patch_browser_session_lifecycle_debug,
            )

            # CDP focus preflight — re-bind agent focus to a valid page target.
            try:
                from browser_use.browser.events import NavigateToUrlEvent, SwitchTabEvent  # noqa: F401
                from agent.ec_skills.browser_node.runner import (
                    run_cdp_focus_preflight as _run_focus_preflight,
                )
                target_focus, last_known_focus_target_id, _did_focus_switch = await _run_focus_preflight(
                    browser_session,
                    last_known_focus_target_id=last_known_focus_target_id,
                    assignment_tab_id=asg_ctx.tab_id,
                    assignment_chat_url=asg_ctx.chat_url,
                    skill_name=self.ctx.skill_name,
                    node_name=self.ctx.node_name,
                )
            except Exception as _focus_exc:
                logger.warning(f"[BrowserAutomation] Focus preflight failed: {_focus_exc}")
                raise

            # Restore browser state so selector/session mapping is fresh
            # before agent.run() picks it up.
            #
            # ── Hang-bound: get_browser_state_summary has been observed
            # to deadlock indefinitely in ``bubus`` under target detach
            # /high concurrency (see eCan.log.1 around 14:34:04: stack
            # ends at runner.py:4376 → browser/session.py:1520 →
            # bubus/models.py:574 → asyncio.wait_for → TimeoutError).
            # When this hangs, the entire front-desk node is wedged and
            # the worker reply queue stops draining, so customer messages
            # silently never get answered.  Cap with the same 3 s budget
            # as the focus preflight + one retry; on persistent failure
            # log a warning and proceed.  ``agent.run()`` re-acquires
            # state internally if needed.
            #
            # Fix #2 (stress-test 2026-04-30): skip when no SwitchTabEvent
            # was dispatched.  Without a tab change, cached state is still
            # valid; agent.run() re-acquires lazily if needed.  Eliminates
            # 6 s per iteration (3 s x 2 attempts) under 23-tab CDP load.
            if target_focus and _did_focus_switch:
                _state_ok = False
                for _attempt in range(2):
                    try:
                        await asyncio.wait_for(
                            browser_session.get_browser_state_summary(include_screenshot=False),
                            timeout=3.0,
                        )
                        _state_ok = True
                        break
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"[BrowserAutomation] post-preflight state-summary "
                            f"TIMEOUT after 3s (attempt {_attempt + 1}/2), "
                            f"target=...{(target_focus or '')[-4:]}, "
                            f"skill={self.ctx.skill_name}, node={self.ctx.node_name}"
                        )
                    except Exception as _state_exc:
                        logger.warning(
                            f"[BrowserAutomation] post-preflight state-summary "
                            f"error (attempt {_attempt + 1}/2): {_state_exc}"
                        )
                if not _state_ok:
                    logger.warning(
                        f"[BrowserAutomation] post-preflight state-summary: "
                        f"SKIPPING after 2 failed attempts. Proceeding with "
                        f"agent.run() which will re-acquire state lazily. "
                        f"target=...{(target_focus or '')[-4:]}, "
                        f"skill={self.ctx.skill_name}, node={self.ctx.node_name}"
                    )

            # Pre-run navigation: anchor focused tab at the assignment URL.
            from agent.ec_skills.browser_node.runner import (
                run_pre_run_navigation as _run_prenav,
            )
            _tab_already_at_correct_url, last_known_focus_target_id = await _run_prenav(
                browser_session,
                target_focus=target_focus,
                asg_cfg=asg_ctx.asg_cfg,
                assignment_chat_url=asg_ctx.chat_url,
                assignment_session_id=asg_ctx.session_id,
                assignment_tab_id=asg_ctx.tab_id,
                assignment_customer_name=asg_ctx.customer_name,
                task=task,
                state=state,
                last_known_focus_target_id=last_known_focus_target_id,
            )

            # Acquire-or-reuse cached browser-use agent (CDP path).
            _bu_scope_key = _bh.resolve_browser_scope_key(
                state,
                node_name=self.ctx.node_name,
                skill_name=self.ctx.skill_name,
            )
            agent = await _acquire_agent(
                AgentClass=AgentClass,
                task=task,
                llm=llm,
                controller=controller,
                agent_kwargs=agent_kwargs,
                bu_scope_key=_bu_scope_key,
                cached_bu_agents=_bh.cached_bu_agents,
                loop_history_mode=self.ctx.loop_history_mode,
                fp_profile=None,
                browser_session=browser_session,
            )
            agent_ref["agent"] = agent

            # Suppress browser-use's auto-navigate-from-task-URL feature when
            # the assigned chat tab is already loaded at the correct URL.
            if _tab_already_at_correct_url:
                try:
                    agent.directly_open_url = False
                    logger.info(
                        "[BrowserAutomation] Suppressed auto-navigate (directly_open_url=False): "
                        "tab already at correct URL"
                    )
                except Exception:
                    pass
        else:
            # Fallback: browser session creation failed or unsupported driver.
            logger.warning(
                f"[BrowserAutomation] Failed to connect to existing browser, falling back "
                f"to new browser (session={browser_session}, driver={self.ctx.browser_driver_setting})"
            )
            agent = AgentClass(task=task, llm=llm, controller=controller, **agent_kwargs)
            agent_ref["agent"] = agent

        return agent, last_known_focus_target_id

    async def _finalize_agent_setup(
        self,
        *,
        agent,
        keep_browser_alive: bool,
        last_known_focus_target_id,
    ) -> tuple[str, "Any"]:
        """Post-construction agent wiring + event monitor start.

        Six sub-steps run after the agent has been created (either
        new-chromium or CDP path):

        1. Stamp ``_ecan_skill_name``, ``_ecan_node_id``,
           ``_ecan_owner`` on the agent for downstream identification.
        2. Re-resolve ``browser_scope_key`` and merge the
           post-preflight ``last_known_focus_target_id`` with the
           cached value (the dict only updates *after* agent.run(),
           so the per-step refocus needs the live preflight result).
        3. Defensive post-construction
           :func:`update_browser_session_cache` — re-applies
           ``keep_alive`` and refreshes lifecycle-debug patches.
        4. :func:`register_agent_for_extension_tools` so
           ``@-extension`` tools called from sub-skills can find the
           agent + runtime context.
        5. Monkey-patch ``agent.eventbus.stop`` + ``agent.close``
           via :func:`patch_agent_for_monitored_keep_alive` to
           preserve the browser session across the ``agent.run()``
           boundary when this run has long-lived event monitors.
        6. :func:`start_event_monitors_for_agent` — Phase 1 HTTP
           polling.  Configs are deep-copied to prevent cross-task
           mutation of shared closure state.

        Returns ``(browser_scope_key, last_known_focus_target_id)``.

        Closure refs (via the nested class scope): ``skill_name``,
        ``node_name``, ``owner``, ``_resolve_browser_scope_key``,
        ``_cached_browser_sessions``, ``_last_known_focus_target_ids``,
        ``_cached_passive_agents``, ``_MAX_BROWSER_CACHE_SIZE``,
        ``_patch_browser_session_lifecycle_debug``,
        ``_event_monitor_configs``
        from ``build_browser_automation_node``.
        """
        try:
            setattr(agent, "_ecan_skill_name", self.ctx.skill_name)
            setattr(agent, "_ecan_node_id", self.ctx.node_name)
            setattr(agent, "_ecan_owner", self.ctx.owner)
        except Exception:
            pass

        state = self.state
        browser_scope_key = _bh.resolve_browser_scope_key(
            state,
            node_name=self.ctx.node_name,
            skill_name=self.ctx.skill_name,
        )
        cached_browser_session = _bh.cached_browser_sessions.get(browser_scope_key)
        # Merge with the dict value rather than overwriting: the focus preflight
        # (CDP path) may have set last_known_focus_target_id to the active tab.
        # Re-reading the dict here would discard that value (the dict is only
        # updated *after* agent.run() completes), so the per-step refocus would
        # have nothing to refocus to.
        last_known_focus_target_id = (
            last_known_focus_target_id
            or _bh.last_known_focus_target_ids.get(browser_scope_key)
        )

        # Defensive post-construction cache update + keep_alive re-application.
        from agent.ec_skills.browser_node.runner import (
            update_browser_session_cache as _update_session_cache,
            register_agent_for_extension_tools as _register_agent,
            start_event_monitors_for_agent as _start_monitors,
        )
        _update_session_cache(
            agent,
            browser_scope_key=browser_scope_key,
            cached_browser_sessions=_bh.cached_browser_sessions,
            cached_browser_session=cached_browser_session,
            last_known_focus_target_ids=_bh.last_known_focus_target_ids,
            cached_passive_agents=_cached_passive_agents,
            keep_browser_alive=keep_browser_alive,
            max_cache_size=_bh.MAX_BROWSER_CACHE_SIZE,
            patch_lifecycle_debug=_bh.patch_browser_session_lifecycle_debug,
        )

        # Register the live agent + runtime context with extension_tools_service.
        _register_agent(
            agent,
            state=state,
            calling_agent_id=self.calling_agent_id,
            skill_name=self.ctx.skill_name,
            node_name=self.ctx.node_name,
            owner=self.ctx.owner,
        )

        # Monkey-patch eventbus.stop + close to preserve the browser session
        # across agent.run() when this run has long-lived event monitors.
        if keep_browser_alive and self.ctx.event_monitor_configs:
            from agent.ec_skills.browser_node.runner import (
                patch_agent_for_monitored_keep_alive as _patch_keep_alive,
            )
            _patch_keep_alive(agent)

        # Always patch eventbus.dispatch to handle QueueShutDown gracefully.
        # This prevents errors when multiple concurrent tasks try to dispatch
        # after the eventbus has been shut down by another task's cleanup.
        from agent.ec_skills.browser_node.runner import (
            patch_eventbus_dispatch_for_shutdown as _patch_dispatch_shutdown,
        )
        _patch_dispatch_shutdown(agent)

        # Auto-start event monitors on the agent's browser session.
        await _start_monitors(
            agent,
            event_monitor_configs=self.ctx.event_monitor_configs,
            calling_agent_id=self.calling_agent_id,
            skill_name=self.ctx.skill_name,
            browser_scope_key=browser_scope_key,
        )

        return browser_scope_key, last_known_focus_target_id

    async def _run_cloud_branch(self, task: str) -> dict:
        """Delegate to ``browser_node.runner.run_cloud_agent`` for cloud modes.

        Used by ``hybrid_cloud`` and ``full_cloud`` ``run_environment``
        settings.  The runner owns LLM resolution (proxy /
        node-specified / Settings default), transport setup,
        ``run_id`` resolution, and the ``CloudAgent`` run loop.

        Closure refs (via the nested class scope): ``skill_name``,
        ``node_name``, ``owner``, ``node_use_vision``,
        ``node_use_thinking``, ``enable_judge_setting``,
        ``node_llm_provider``, ``node_model_name``, ``inputs``
        from ``build_browser_automation_node``.
        """
        from agent.ec_skills.browser_node.runner import (
            run_cloud_agent as _run_cloud_agent,
        )
        return await _run_cloud_agent(
            task,
            self.state,
            self.mainwin,
            self.calling_agent_id,
            skill_name=self.ctx.skill_name,
            node_name=self.ctx.node_name,
            owner=self.ctx.owner,
            use_vision=self.ctx.node_use_vision,
            use_thinking=self.ctx.node_use_thinking,
            use_judge=self.ctx.enable_judge_setting,
            llm_provider=self.ctx.node_llm_provider or "",
            llm_model_name=self.ctx.node_model_name or "",
            raw_inputs=self.ctx.inputs,
        )

    async def _handle_pre_dispatch(
        self,
        *,
        agent,
        llm,
        evt_type,
        browser_scope_key: str,
    ) -> tuple[dict | None, "Any"]:
        """Run the pre-dispatch sequence: first-invocation skip, late hooks, cancellation wiring.

        Returns ``(early_exit, cancellation_event)`` where:

        * ``early_exit`` is the state/result dict to return directly
          from :meth:`run` when the first-invocation short-circuit
          fires *or* when a registered before-browser-use-run hook
          intercepts.  ``None`` means proceed to the agent dispatch.
        * ``cancellation_event`` is fetched from the global
          cancellation registry by ``task_id`` and (if non-None)
          attached to ``llm._ec_cancellation_event`` so
          ``create_with_logging`` can poll it without a registry
          lookup.

        Closure refs (via the nested class scope): ``_event_monitor_configs``,
        ``node_name``, ``_first_invocation_done``,
        ``_before_browser_use_run_hooks``, ``_build_hook_ctx``,
        ``inputs`` from ``build_browser_automation_node``.
        """
        # First-invocation short-circuit — skip LLM and let pend_event
        # pick up the first real browser_event within seconds.  See
        # helper docstring for full rationale.
        from agent.ec_skills.browser_node.runner import (
            maybe_first_invocation_short_circuit as _maybe_fi_skip,
        )
        _fi_state = _maybe_fi_skip(
            state=self.state,
            evt_type=evt_type,
            event_monitor_configs=self.ctx.event_monitor_configs,
            first_invocation_done=_first_invocation_done,
            browser_scope_key=browser_scope_key,
            node_name=self.ctx.node_name,
        )
        if _fi_state is not None:
            return _fi_state, None

        # ── Invoke registered before-browser-use-run hooks ──────
        # Each hook gets a BrowserUseHookContext exposing the
        # closure-scoped helpers (resolve_scope_key,
        # extract_runtime_invocation_input) + module-level state
        # dicts.  The first hook to return a non-None state dict
        # short-circuits the LLM.  Site-specific patterns (e.g.
        # the live-chat bundle front_desk's PreDispatch fan-out) register
        # themselves via ``register_before_browser_use_run_hook``
        # at module-import time; build_node itself has no knowledge
        # of what any registered hook does.
        if self.ctx.before_browser_use_run_hooks:
            _bur_hook_ctx = self._build_hook_ctx()
            for _bur_hook in self.ctx.before_browser_use_run_hooks:
                _bur_hook_result = await _bur_hook(
                    agent, self.state, self.ctx.inputs, _bur_hook_ctx
                )
                if _bur_hook_result is not None:
                    return _bur_hook_result, None

        # Register current agent instance so extension tools (e.g. list_files)
        # can auto-authorize discovered file paths for later read_long_content/read_file calls.
        try:
            from agent.ec_skills.browser_use_extension.extension_tools_service import set_current_agent

            set_current_agent(agent)
        except Exception as _set_agent_exc:
            logger.warning(f"[BrowserAutomation] Failed to register current agent for extension tools: {_set_agent_exc}")

        # Look up cancellation_event from global registry by task_id
        from agent.ec_tasks import cancellation_registry
        task_id = (self.state.get("attributes") or {}).get("task_id") if isinstance(self.state, dict) else None
        cancellation_event = cancellation_registry.get(task_id) if task_id else None
        if not cancellation_event:
            logger.debug(f"[BrowserAutomation] No cancellation_event for task_id={task_id}")

        # Store cancellation_event directly on the LLM so create_with_logging can poll it
        # without a registry lookup by task_id (which may be stored at wrong state path).
        if cancellation_event:
            try:
                setattr(llm, "_ec_cancellation_event", cancellation_event)
            except Exception:
                pass

        return None, cancellation_event

    async def _run_agent_dispatch(
        self,
        *,
        agent,
        agent_kwargs: dict,
        cancellation_event,
        last_known_focus_target_id,
        browser_scope_key: str,
        runtime_had_response_text: bool,
    ) -> dict:
        """Run the browser-use agent (with full cancel/focus dispatch) and finalize.

        Wraps the inner try-block of :meth:`run`: resolves step-patch
        config, computes the step focus target, dispatches the
        ``agent.run()`` call via ``run_agent_with_dispatch``, then
        delegates result post-processing to :meth:`_finalize_result`.

        Closure refs (via the nested class scope): ``inputs``,
        ``node_dom_focus_selector``, ``node_max_steps``,
        ``node_timeout_seconds`` from ``build_browser_automation_node``.
        """
        from agent.ec_skills.browser_node.runner import (
            resolve_step_patch_config as _resolve_step_cfg,
            run_agent_with_dispatch as _run_agent_dispatch_helper,
        )
        _refocus_enabled, _abort_when_pre_dispatched, _pre_dispatch_flag_attr = (
            _resolve_step_cfg(self.ctx.inputs)
        )

        _step_focus_target = None
        if _refocus_enabled and hasattr(agent, 'step'):
            # NOTE: ``locals().get("assignment_target_focus")`` is a
            # defensive lookup carried over from the original closure
            # body — the name has never actually been assigned, so it
            # always falls through to ``last_known_focus_target_id``.
            # Preserved verbatim for behavior parity.
            _step_focus_target = (
                locals().get("assignment_target_focus")
                or last_known_focus_target_id
                or None
            )

        # 4-way agent.run() dispatch (cloud/privacy native, simple
        # cancel wrapper, full step patch, plain).  See helper.
        history = await _run_agent_dispatch_helper(
            agent,
            agent_kwargs=agent_kwargs,
            cancellation_event=cancellation_event,
            step_focus_target=_step_focus_target,
            abort_when_pre_dispatched=_abort_when_pre_dispatched,
            pre_dispatch_flag_attr=_pre_dispatch_flag_attr,
            dom_focus_selector=self.ctx.node_dom_focus_selector,
            node_max_steps=self.ctx.node_max_steps,
            node_timeout_seconds=self.ctx.node_timeout_seconds,
        )
        return await self._finalize_result(
            agent=agent,
            history=history,
            browser_scope_key=browser_scope_key,
            runtime_had_response_text=runtime_had_response_text,
            cancellation_event=cancellation_event,
        )

    async def _finalize_result(
        self,
        *,
        agent,
        history,
        browser_scope_key: str,
        runtime_had_response_text: bool,
        cancellation_event,
    ) -> dict:
        """Post-run extraction: persist focus, log diagnostics, build result dict.

        Runs immediately after ``run_agent_with_dispatch`` returns and
        before the ``finally``-block cleanup.  Side-effects:

        * Re-raises ``CancelledError`` if cancellation was set during
          the agent run (must short-circuit before any post-processing).
        * Persists the post-run focus target so the next invocation's
          CDP preflight can rebind to the same tab.
        * Emits step-budget, history, final-result, and token-usage
          diagnostics for postmortem analysis.
        * Clears ``response_text`` from state so subsequent
          ``browser_event`` cycles do not re-inject it.

        Closure refs (via the nested class scope): ``_last_known_focus_target_ids``,
        ``_log_browser_use_result_summary``, ``node_name``, ``skill_name``
        from ``build_browser_automation_node``.
        """
        import asyncio
        if cancellation_event and cancellation_event.is_set():
            logger.info(
                "[BrowserAutomation] Cancellation set after agent.run(), stopping node execution"
            )
            raise asyncio.CancelledError("Task cancelled after LLM response")

        # Persist post-run focus target.
        from agent.ec_skills.browser_node.runner import (
            persist_focus_target as _persist_focus,
        )
        _persist_focus(
            agent,
            browser_scope_key=browser_scope_key,
            last_known_focus_target_ids=_bh.last_known_focus_target_ids,
        )

        # Log step budget for postmortem diagnostics.
        from agent.ec_skills.browser_node.runner import (
            log_step_budget as _log_step_budget,
        )
        _log_step_budget(agent)

        # Truncate long output for logging.
        history_str = str(history)
        if len(history_str) > 10000:
            history_str = history_str[:10000] + '... (truncated)'
        logger.debug(f"[BROWSER USE]Agent Run History: {history_str}")

        final = history.final_result() if (history and hasattr(history, 'final_result')) else None
        if history:
            _log_browser_use_result_summary(history, skill_name=self.ctx.skill_name, node_name=self.ctx.node_name)
        consecutive_failures = getattr(getattr(agent, "state", None), "consecutive_failures", 0) or 0
        
        # 详细日志记录失败状态
        logger.info(f"[BrowserAutomation] Run completed: final={type(final).__name__}, consecutive_failures={consecutive_failures}, node={self.ctx.node_name}")
        
        if final is None and consecutive_failures:
            current_url = ""
            try:
                browser_session = getattr(agent, "browser_session", None)
                if browser_session:
                    # Timeout protection: state-summary can hang indefinitely
                    try:
                        state = await asyncio.wait_for(
                            browser_session.get_browser_state_summary(include_screenshot=False),
                            timeout=5.0
                        )
                        current_url = str(getattr(state, "url", "") or "")
                    except asyncio.TimeoutError:
                        logger.warning(
                            f"[BrowserAutomation] State-summary TIMEOUT after 5s after failed run, "
                            f"skipping URL capture"
                        )
            except Exception as exc:
                logger.warning(f"[BrowserAutomation] Failed to read browser state after failed run: {exc}")
            
            # 获取更详细的错误信息
            error_details = {}
            try:
                if history:
                    error_details["history_length"] = len(history.history) if hasattr(history, 'history') else "N/A"
                    error_details["last_result"] = str(history.history[-1])[-500:] if hasattr(history, 'history') and history.history else "N/A"
            except Exception as hist_err:
                logger.debug(f"[BrowserAutomation] Failed to get history details: {hist_err}")
            
            final = {
                "status": "failed",
                "error": "browser-use run ended with consecutive failures before producing research data",
                "consecutive_failures": consecutive_failures,
                "current_url": current_url,
                "node": self.ctx.node_name,
                "error_details": error_details,
            }
            logger.error(f"[BrowserAutomation] Returning structured browser failure: {final}")
        final_str = str(final)
        if len(final_str) > 10000:
            final_str = final_str[:10000] + '... (truncated)'
        logger.debug(f"[BROWSER USE]Agent Run Results: {final_str}")

        # Log browser-use's per-model token + cost summary.
        from agent.ec_skills.browser_node.runner import (
            log_browser_use_token_usage as _log_bu_tokens,
        )
        _log_bu_tokens(history)

        # Clear consumed response_text so subsequent browser_event cycles
        # don't re-inject and re-send it.
        from agent.ec_skills.browser_node.runner import (
            clear_consumed_response_text as _clear_resp,
        )
        _clear_resp(
            self.state,
            runtime_had_response_text=runtime_had_response_text,
            node_name=self.ctx.node_name,
            skill_name=self.ctx.skill_name,
        )

        return {"final": final, "history": str(history)}

    async def _cleanup(self, *, agent, browser_scope_key: str) -> None:
        """Finally-block cleanup: stop non-cached browser session.

        Event monitors are intentionally *not* stopped here —
        they persist across the pend_event loop for downstream
        nodes to receive events.  Global monitor cleanup happens
        when the runner shuts down.

        Closure refs (via the nested class scope): ``_cached_browser_sessions``
        and ``browser_type_setting`` from ``build_browser_automation_node``.

        :param agent: The browser-use Agent instance (may be ``None``
            if the run raised before agent construction).
        :param browser_scope_key: The scope key used to look up the
            cached session (``"chat:<id>"`` or ``"node:<name>"``).
        """
        from agent.ec_skills.browser_node.runner import (
            stop_non_cached_browser_session as _stop_non_cached,
        )
        await _stop_non_cached(
            agent,
            browser_scope_key=browser_scope_key,
            cached_browser_sessions=_bh.cached_browser_sessions,
            browser_type_setting=self.ctx.browser_type_setting,
        )

    async def run(self) -> dict:
        # Unpack instance args into bare names so the body below
        # can stay verbatim from the original ``_run_browser_use``.
        task = self.task
        mainwin = self.mainwin
        state = self.state
        calling_agent_id = self.calling_agent_id
        # Note: previously `nonlocal _last_known_focus_target_ids` from when
        # this class was nested inside ``build_browser_automation_node``.
        # Phase 6.2 rewrote every closure ref to ``self.ctx.*``, so the dict
        # is now ``_bh.last_known_focus_target_ids`` (mutable, shared
        # by reference with the build scope — mutations still persist).
        # Entry trace — pairs with [BA._auto] worker_call start/done so we
        # can see whether the hang is in the thread-hop itself or inside
        # the coroutine body.
        import time as _rbu_time
        _rbu_t0 = _rbu_time.perf_counter()
        try:
            _rbu_thread_name = threading.current_thread().name
        except Exception:
            _rbu_thread_name = "?"
        logger.info(
            f"[BA._run_browser_use] enter node={self.ctx.node_name} thread={_rbu_thread_name} "
            f"calling_agent_id={calling_agent_id!r} task_len={len(task or '')}"
        )

        try:
            import asyncio
            from browser_use import Agent as BUAgent
            from browser_use.browser.profile import BrowserProfile
            from agent.ec_skills.browser_use_extension.extension_tools_service import custom_controller
            # from browser_use.browser.context import BUBrowserContext as BUBrowserContext
        
            # Patch navigation timeout to reduce "Page readiness timeout" warnings
            # browser_use hardcodes 4s cross-domain / 2s same-domain, which is too short for many sites
            log_msg = f"🤖 Executing node Browser Automation node: {self.ctx.node_name}"
            logger.debug(log_msg)
            send_skill_editor_log("log", log_msg)

            # Resolve mustache templates + inject runtime invocation input.
            from agent.ec_skills.browser_node.runner import (
                prepare_task_with_runtime_context as _prepare_task,
            )
            task, _runtime_had_response_text = _prepare_task(
                task,
                state=state,
                mainwin=mainwin,
                node_name=self.ctx.node_name,
                skill_name=self.ctx.skill_name,
                resolve_mustache_template=_resolve_mustache_template,
                extract_runtime_invocation_input=_bh.extract_runtime_invocation_input,
            )
            # Recompute runtime_input for downstream consumers
            # (assignment-scope extraction + assignment-gate diagnostics).
            # _prepare_task already injected it into the task; this binding
            # is just so the references at lines below resolve.
            runtime_input = _bh.extract_runtime_invocation_input(state)

            # Inject triggering-event context + run prompt-build hooks.
            _early_exit, task, _evt_type = await self._inject_event_context(task=task)
            if _early_exit is not None:
                return _early_exit

            # Early hooks: run BEFORE browser-use agent construction.
            _early_exit = await self._invoke_early_hooks()
            if _early_exit is not None:
                return _early_exit

            # Assignment scope: extract vars + run gate + render scope contract.
            _asg_early, task, _asg_ctx = await self._extract_assignment_and_scope(
                task=task, runtime_input=runtime_input,
            )
            if _asg_early is not None:
                return _asg_early
            _asg_cfg = _asg_ctx.asg_cfg
            assignment_session_id = _asg_ctx.session_id
            assignment_tab_id = _asg_ctx.tab_id
            assignment_chat_url = _asg_ctx.chat_url
            assignment_customer_name = _asg_ctx.customer_name
            _browser_scope_key = _asg_ctx.browser_scope_key
            _cached_browser_session = _asg_ctx.cached_browser_session
            _last_known_focus_target_id = _asg_ctx.last_known_focus_target_id

            def _extract_preferred_start_url(task_text: str, workflow_state: dict | None) -> str | None:
                """Pull a deterministic startup URL from task/state for control-page workflows."""
                pattern = r'https?://(?:127\.0\.0\.1|localhost):9877/control[^\s\'"]*'
                candidates = [task_text]
                if isinstance(workflow_state, dict):
                    try:
                        candidates.append(json.dumps(workflow_state, ensure_ascii=False))
                    except Exception:
                        pass

                for candidate in candidates:
                    if not candidate:
                        continue
                    match = re.search(pattern, candidate, re.IGNORECASE)
                    if match:
                        return match.group(0)
                return None

            # Determine run mode (passive / cloud-agent / full-local).
            passive_enabled, cloud_agent_enabled = self._resolve_run_mode()

            # PASSIVE LOCAL MODE: cloud-driven MCP fast-path.
            if passive_enabled:
                return await self._run_passive_branch(
                    browser_scope_key=_browser_scope_key,
                    last_known_focus_target_id=_last_known_focus_target_id,
                )

            # Choose vanilla Agent vs PrivacyAgent (privacy strategy + hook system).
            AgentClass = self._resolve_agent_class()
            use_privacy_agent = AgentClass.__name__ != 'Agent'

            # CLOUD AGENT MODE: hybrid_cloud / full_cloud.
            if cloud_agent_enabled:
                return await self._run_cloud_branch(task)


            # LOCAL EXECUTION MODES: Require mainwin
            if not mainwin:
                raise ValueError("mainwin is required. Must use mainwin configuration for browser_use LLM.")

            # Build local LLM, attach token context, assemble agent_kwargs.
            llm, controller, agent_kwargs = self._build_local_llm_and_kwargs(
                browser_scope_key=_browser_scope_key,
            )
        
            # Browser profile + stealth fingerprint + lifecycle callbacks +
            # available_file_paths + extract-tool char-limit patch.
            _fp_profile, _agent_ref, keep_browser_alive = self._build_browser_profile_and_callbacks(
                agent_kwargs=agent_kwargs,
                task=task,
            )


            # Apply optional cloud-LLM-transport + hook-bundle kwargs.
            self._apply_post_kwargs_extensions(
                agent_kwargs=agent_kwargs,
                use_privacy_agent=use_privacy_agent,
            )

            # Multimodal: when the inbound payload (state["input"]) carries
            # ``latest_message_attachments`` with eager-fetched data URIs,
            # build browser-use ``sample_images`` so a vision-capable LLM
            # can actually see the customer's image alongside the text.
            # No-op for text-only turns; vision-gated by llm.supports_vision.
            from agent.ec_skills.browser_node.multimodal import (
                apply_multimodal_to_agent_kwargs as _apply_mm_kwargs,
            )
            _n_images = _apply_mm_kwargs(
                agent_kwargs, state=self.state, llm=llm,
            )
            if _n_images:
                logger.info(
                    f"[BrowserAutomation] Multimodal: injected {_n_images} "
                    f"customer image(s) as sample_images (use_vision forced ON)"
                )

            # Acquire browser session + browser-use Agent (new-chromium or CDP path).
            agent, _last_known_focus_target_id = await self._acquire_browser_and_agent(
                AgentClass=AgentClass,
                task=task,
                llm=llm,
                controller=controller,
                agent_kwargs=agent_kwargs,
                fp_profile=_fp_profile,
                agent_ref=_agent_ref,
                keep_browser_alive=keep_browser_alive,
                last_known_focus_target_id=_last_known_focus_target_id,
                asg_ctx=_asg_ctx,
            )

            # Multimodal cache-reuse fix: when the Agent above was re-acquired
            # from ``cached_bu_agents`` (NOT freshly constructed), its
            # ``sample_images`` is stuck at the previous turn's list — the
            # constructor kwargs we just set above don't apply.  Mutate the
            # cached Agent's ``sample_images`` (and its ``_message_manager``
            # copy) so this turn's images flow through.  Also clears stale
            # images on text-only turns so they don't bleed across customers.
            from agent.ec_skills.browser_node.multimodal import (
                refresh_agent_sample_images as _refresh_mm,
            )
            _refresh_mm(agent, state=self.state, llm=llm)

            # Post-construction: agent attrs, cache update, register, keep-alive, monitors.
            _browser_scope_key, _last_known_focus_target_id = await self._finalize_agent_setup(
                agent=agent,
                keep_browser_alive=keep_browser_alive,
                last_known_focus_target_id=_last_known_focus_target_id,
            )

            # Pre-dispatch: first-invocation skip, late hooks, cancellation wiring.
            _early_exit, cancellation_event = await self._handle_pre_dispatch(
                agent=agent,
                llm=llm,
                evt_type=_evt_type,
                browser_scope_key=_browser_scope_key,
            )
            if _early_exit is not None:
                return _early_exit

            try:
                return await self._run_agent_dispatch(
                    agent=agent,
                    agent_kwargs=agent_kwargs,
                    cancellation_event=cancellation_event,
                    last_known_focus_target_id=_last_known_focus_target_id,
                    browser_scope_key=_browser_scope_key,
                    runtime_had_response_text=_runtime_had_response_text,
                )
            except asyncio.CancelledError:
                # CRITICAL: Cancellation must propagate up, NOT be converted to RuntimeError
                logger.info("[BrowserAutomation] CancelledError caught, re-raising to propagate cancellation")
                raise
            except asyncio.TimeoutError as e:
                timeout_msg = (
                    f"Browser automation node timed out after {self.ctx.node_timeout_seconds}s"
                    if self.ctx.node_timeout_seconds
                    else "Browser automation node timed out"
                )
                logger.error(f"[BrowserAutomation] {timeout_msg}")
                raise RuntimeError(timeout_msg) from e
            finally:
                # Event monitors intentionally persist across the pend_event
                # loop; only the non-cached browser session is torn down here.
                # See :meth:`_BrowserRunSession._cleanup` for details.
                await self._cleanup(
                    agent=agent,
                    browser_scope_key=_browser_scope_key,
                )
        except Exception as e:
            err_msg = get_traceback(e, "ErrorBuildBrowserAutomationNode")
            logger.error(err_msg)
            send_skill_editor_log("error", err_msg)
            # Re-raise the exception so LangGraph can mark the node as failed
            _err_text = str(e).strip() or repr(e)
            raise RuntimeError(f"Browser automation failed: {_err_text}") from e
