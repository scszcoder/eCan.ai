"""Lifecycle-hook context factory + invokers.

Three hook phases (see ``docs/BUILD_NODE_LIFECYCLE_HOOKS.md`` for the
full contract):

1. **Early** — runs *before* the browser-use agent is constructed.
   Hooks can short-circuit using only the triggering event payload
   (e.g. type a pre-computed reply directly into the DOM).

2. **Prompt-build** — runs once compact_items + actionable filter
   are computed.  Hooks can append to the task hint, prepend a
   protocol-override block, or short-circuit.

3. **Late** — runs *after* the agent + browser session are ready.
   Hooks have access to ``agent.browser_session`` for DOM walks
   (e.g. PreDispatch sidebar fan-out).

This module owns the context-construction + iteration logic; the
hook lists themselves and the dataclasses live in ``build_node.py``
(which currently re-exports them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from utils.logger_helper import logger_helper as logger

# Re-import contracts from build_node to avoid duplicate definitions.
# Phase 6.5 (2026-04-24): context dataclasses live in their own module
# now.  build_node.py re-exports them for back-compat.
from agent.ec_skills.browser_node.contexts import (
    BrowserUseHookContext,
    PromptBuildContext,
    PromptBuildResult,
)
from agent.ec_skills.build_node import (
    _before_browser_session_setup_hooks,
    _before_prompt_build_hooks,
    _before_browser_use_run_hooks,
    _parse_json_input,
    _normalize_dispatch_identity_key,
    _resolve_template,
    _SafeFormatDict,
    _dispatch_state_by_agent,
    _is_dispatch_inflight,
    _mark_dispatch_inflight,
    _clear_dispatch_inflight,
    _DISPATCH_INFLIGHT_TTL_S,
    send_skill_editor_log,
)

from agent.ec_skills.browser_node.session import BrowserSessionManager

# v2 tier-aware dispatch (Step 4 wire-up).  Imported lazily inside the
# invokers to avoid pulling pydantic at module-import time when no v2
# hook is registered.  See ``_dispatch_v2_if_eligible`` for the
# detection contract.


# ─────────────────────────────────────────────────────────────────────
# Aggregated prompt-build result
# ─────────────────────────────────────────────────────────────────────

@dataclass
class PromptBuildOutcome:
    """Aggregated effect of running every prompt-build hook in turn.

    Returned by :func:`invoke_prompt_build_hooks` so the caller doesn't
    need to know how many hooks fired or how their effects combine.
    """

    short_circuit_state: dict | None = None
    task_hint_append: str = ""
    override_prepend: str = ""
    handled: bool = False  # True iff any hook contributed text/short-circuit

    @property
    def is_short_circuit(self) -> bool:
        return self.short_circuit_state is not None


# ─────────────────────────────────────────────────────────────────────
# HookContext factory
# ─────────────────────────────────────────────────────────────────────

def build_hook_context(
    *,
    cfg_node_name: str,
    calling_agent_id: str,
    mainwin: Any,
    sessions: BrowserSessionManager,
    extract_runtime_invocation_input: Callable[[dict | None], str],
    run_environment: str = "full_local",
) -> BrowserUseHookContext:
    """Construct a ``BrowserUseHookContext`` for one hook invocation.

    Encapsulates the field plumbing so callers don't have to remember
    all 17 fields.  The session manager + the runtime-input extractor
    are passed in because they are owned by ``BrowserUseRunner``, not
    by this module.
    """
    return BrowserUseHookContext(
        node_name=str(cfg_node_name or ""),
        calling_agent_id=str(calling_agent_id or ""),
        mainwin=mainwin,
        resolve_scope_key=sessions.resolve_scope_key,
        extract_runtime_invocation_input=extract_runtime_invocation_input,
        parse_json_input=_parse_json_input,
        send_log=send_skill_editor_log,
        normalize_dispatch_identity_key=_normalize_dispatch_identity_key,
        safe_format_dict=_SafeFormatDict,
        cached_browser_sessions=sessions.cached_sessions,
        dispatch_state_by_agent=_dispatch_state_by_agent,
        is_dispatch_inflight=_is_dispatch_inflight,
        mark_dispatch_inflight=_mark_dispatch_inflight,
        clear_dispatch_inflight=_clear_dispatch_inflight,
        inflight_ttl_s=_DISPATCH_INFLIGHT_TTL_S,
        resolve_template=_resolve_template,
        get_or_create_browser_session=sessions.get_or_create,
        run_environment=str(run_environment or "full_local"),
    )


# ─────────────────────────────────────────────────────────────────────
# v2 dispatch detection (Step 4 wire-up)
# ─────────────────────────────────────────────────────────────────────

# Sentinel returned by ``_dispatch_v2_if_eligible`` when the hook is
# legacy-style and the caller should fall back to direct invocation.
_LEGACY_FALLBACK = object()


async def _dispatch_v2_if_eligible(
    hook: Any,
    ctx: BrowserUseHookContext,
    *args: Any,
    agent: Any = None,
    **kwargs: Any,
) -> Any:
    """Dispatch *hook* via :class:`TierAwareRunner` if it is a v2 hook.

    Returns the hook's result on v2 dispatch; returns
    :data:`_LEGACY_FALLBACK` if the hook lacks ``EXECUTION_TIER`` so
    the caller can run the legacy code path.

    A v2 hook is any object with a string ``EXECUTION_TIER`` attribute
    AND an async ``run`` method.  Anything else falls through.
    """
    tier = getattr(hook, "EXECUTION_TIER", None)
    if not isinstance(tier, str) or not callable(getattr(hook, "run", None)):
        return _LEGACY_FALLBACK

    # Lazy imports — keep cold-start cheap when no v2 hooks register.
    from agent.ec_skills.browser_use_extension.tier_aware_runner import (
        RunMode,
        TierAwareRunner,
    )
    from agent.ec_skills.browser_use_extension.legacy_bridge import (
        backends_from_legacy_context,
    )

    # Pick the RunMode from the per-node ``runEnvironment`` flag in
    # the flowgram JSON — this is a per-skill / per-node config, not
    # an env var.  Legacy-only modes (``full_local`` / ``passive_local``
    # / ``full_cloud``) all run hooks in-process on whichever side they
    # land on, which maps to FULL_LOCAL in the v2 enum.  Only
    # ``hybrid_cloud`` selects the RPC-routed mode.
    mode = (
        RunMode.HYBRID_CLOUD
        if str(getattr(ctx, "run_environment", "") or "").lower() == "hybrid_cloud"
        else RunMode.FULL_LOCAL
    )
    backends = backends_from_legacy_context(ctx, agent=agent)
    runner = TierAwareRunner(mode, backends)
    return await runner.dispatch(hook, *args, **kwargs)


# ─────────────────────────────────────────────────────────────────────
# Invokers — one per phase
# ─────────────────────────────────────────────────────────────────────

async def invoke_early_hooks(
    state: dict,
    inputs: dict,
    ctx: BrowserUseHookContext,
) -> dict | None:
    """Run every registered early hook; first non-None result wins.

    Returns the short-circuit state when a hook handles the round, or
    ``None`` to let the runner proceed to the agent-construction path.
    """
    if not _before_browser_session_setup_hooks:
        return None
    for hook in _before_browser_session_setup_hooks:
        try:
            # v2 path: hooks declaring EXECUTION_TIER are dispatched
            # through the tier-aware runner; everything else uses the
            # legacy callable contract.  The runtime is mode-agnostic.
            v2_result = await _dispatch_v2_if_eligible(
                hook, ctx, state, inputs, agent=None,
            )
            if v2_result is _LEGACY_FALLBACK:
                result = await hook(None, state, inputs, ctx)
            else:
                result = v2_result
        except Exception as exc:
            qual = getattr(hook, "__qualname__", type(hook).__name__)
            mod = getattr(hook, "__module__", type(hook).__module__)
            logger.warning(
                f"[BrowserAutomation] early hook {mod}.{qual} raised: {exc}"
            )
            continue
        if result is not None:
            return result
    return None


async def invoke_prompt_build_hooks(
    state: dict,
    inputs: dict,
    ctx: BrowserUseHookContext,
    pb_ctx: PromptBuildContext,
) -> PromptBuildOutcome:
    """Run every prompt-build hook; aggregate text mutations.

    A hook returning ``PromptBuildResult(short_circuit_state=...)``
    short-circuits immediately — text mutations from earlier hooks
    in the same round are discarded (matches the original behaviour).
    """
    outcome = PromptBuildOutcome()
    if not _before_prompt_build_hooks:
        return outcome

    for hook in _before_prompt_build_hooks:
        try:
            v2_result = await _dispatch_v2_if_eligible(
                hook, ctx, state, inputs, pb_ctx,
            )
            if v2_result is _LEGACY_FALLBACK:
                result: PromptBuildResult | None = await hook(
                    state, inputs, ctx, pb_ctx,
                )
            else:
                result = v2_result  # type: ignore[assignment]
        except Exception as exc:
            qual = getattr(hook, "__qualname__", type(hook).__name__)
            mod = getattr(hook, "__module__", type(hook).__module__)
            logger.warning(
                f"[BrowserAutomation] prompt-build hook "
                f"{mod}.{qual} raised: {exc}"
            )
            continue
        if result is None:
            continue
        if result.short_circuit_state is not None:
            outcome.short_circuit_state = result.short_circuit_state
            outcome.handled = True
            return outcome
        if result.task_hint_append:
            outcome.task_hint_append += result.task_hint_append
            outcome.handled = True
        if result.override_prepend:
            outcome.override_prepend = result.override_prepend + outcome.override_prepend
            outcome.handled = True
    return outcome


async def invoke_late_hooks(
    agent: Any,
    state: dict,
    inputs: dict,
    ctx: BrowserUseHookContext,
) -> dict | None:
    """Run every late-phase hook; first non-None state dict short-circuits."""
    if not _before_browser_use_run_hooks:
        return None
    for hook in _before_browser_use_run_hooks:
        try:
            v2_result = await _dispatch_v2_if_eligible(
                hook, ctx, state, inputs, agent=agent,
            )
            if v2_result is _LEGACY_FALLBACK:
                result = await hook(agent, state, inputs, ctx)
            else:
                result = v2_result
        except Exception as exc:
            qual = getattr(hook, "__qualname__", type(hook).__name__)
            mod = getattr(hook, "__module__", type(hook).__module__)
            logger.warning(
                f"[BrowserAutomation] late hook {mod}.{qual} raised: {exc}"
            )
            continue
        if result is not None:
            return result
    return None
