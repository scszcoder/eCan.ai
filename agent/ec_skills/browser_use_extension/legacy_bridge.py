"""Step 4 wire-up — bridge legacy ``BrowserUseHookContext`` to v2 backends.

The runtime invokers in :mod:`browser_node.hooks` historically pass a
single :class:`BrowserUseHookContext` object to every hook.  v2 hooks
declare an ``EXECUTION_TIER`` attribute and expect a tier-typed
context (``CloudHookContext`` / ``LocalReactiveContext`` /
``LocalExtractContext``).  This module builds the right v2 context
from the legacy one without forcing the runner to know about the
hook type.

Design
------

* **One factory per tier shape** — :func:`backends_from_legacy_context`
  produces a :class:`BackendBundle` that the
  :class:`tier_aware_runner.TierAwareRunner` consumes.  All three
  tiers share the same bundle; the builder picks per-tier fields.

* **Best-effort backends** — when a v2-only capability has no legacy
  analogue (e.g. ``agent_registry``), the bridge supplies a safe
  no-op stub.  Hooks that *need* a live backend will fail loudly when
  they try to use it, which is the correct behaviour during the
  rollout (the bridge does not silently mask unimplemented features).

* **Lazy primitives** — the :class:`BrowserSessionPrimitives` adapter
  is built only when the hook actually requests primitives.  Most v2
  hooks (cloud_only, prompt_build) won't, so we don't pay the cost.

* **Soft imports for site-specific bits** — the typing_lock and
  send_chat modules belong to bundles outside the runner.  We import
  them lazily and fall back to no-op shims when they're absent.

This bridge is **dormant** until a v2 hook is registered — legacy
hooks (no ``EXECUTION_TIER``) keep using the old call convention
unchanged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from agent.ec_skills.browser_node.contexts import (
    AgentRegistry,
    BrowserPrimitives,
    BrowserUseHookContext,
    DispatchState,
    SendChatProxy,
    SessionKV,
    TypingLock,
)
from agent.ec_skills.browser_use_extension.tier_aware_runner import (
    BackendBundle,
    RunMode,
)

logger = logging.getLogger("ecan.legacy_bridge")

__all__ = [
    "backends_from_legacy_context",
    "DictSessionKV",
    "LegacyDispatchState",
    "BrowserSessionPrimitives",
    "NoopAgentRegistry",
    "NoopSendChat",
    "NoopTypingLock",
]


# ============================================================================
# Adapter implementations — real where possible, no-op where the legacy
# context has no analogue
# ============================================================================


class DictSessionKV:
    """:class:`SessionKV` view over a plain dict.

    The dict is borrowed from ``dispatch_state_by_agent`` so all v2
    hooks for a given ``(agent_id, node_name)`` share state.  Mutations
    are visible across hook invocations within the same run.
    """

    def __init__(self, store: dict):
        self._d = store

    def get(self, k, d=None):
        return self._d.get(k, d)

    def set(self, k, v):
        self._d[k] = v

    def delete(self, k):
        self._d.pop(k, None)

    def keys(self):
        return list(self._d.keys())


class LegacyDispatchState:
    """:class:`DispatchState` adapter over the legacy inflight helpers.

    Inflight bookkeeping reuses ``is_dispatch_inflight`` /
    ``mark_dispatch_inflight`` / ``clear_dispatch_inflight`` from
    :mod:`build_node`.  ``last_dispatched_msg_id`` is stored in a
    dedicated dict so it survives across cycles for the same
    ``(agent_id, node_name)``.
    """

    def __init__(
        self,
        ctx: BrowserUseHookContext,
        msg_id_store: dict,
    ):
        self._ctx = ctx
        self._mids = msg_id_store

    def is_inflight(self, key: str) -> float:
        try:
            return float(self._ctx.is_dispatch_inflight(key) or 0.0)
        except Exception:
            return 0.0

    def mark_inflight(self, key: str) -> None:
        try:
            self._ctx.mark_dispatch_inflight(key)
        except Exception:
            pass

    def clear_inflight(self, key: str) -> None:
        try:
            self._ctx.clear_dispatch_inflight(key)
        except Exception:
            pass

    def get_last_dispatched_msg_id(self, key: str) -> str:
        return str(self._mids.get(key, ""))

    def set_last_dispatched_msg_id(self, key: str, msg_id: str) -> None:
        self._mids[key] = str(msg_id or "")

    @property
    def inflight_ttl_s(self) -> float:
        return float(getattr(self._ctx, "inflight_ttl_s", 60.0))


class BrowserSessionPrimitives:
    """:class:`BrowserPrimitives` adapter over a browser-use session.

    Bridges v2's typed primitives surface to the legacy
    ``browser_session.eval_js`` / page query path.  Used when a v2
    local-tier hook runs in full_local mode against an existing
    browser-use session.

    The surface is *minimal but correct* — each method maps to the
    closest equivalent in the legacy session API.  ``read_dom``,
    ``click``, ``type``, ``wait_for`` defer to JS evaluation when
    no direct page method is exposed; this is functionally equivalent
    on Feige-style SPA sites.
    """

    def __init__(self, browser_session: Any):
        self._sess = browser_session
        # Lazy import keeps this module's import-time deps small —
        # extension_tools_service drags in browser_use bits.
        try:
            from agent.ec_skills.browser_use_extension.extension_tools_service import (
                _evaluate_js as _eval_js_helper,
            )
            self._eval_helper: Optional[Callable] = _eval_js_helper
        except Exception:
            self._eval_helper = None

    async def eval_js(self, snippet: str, *, timeout_ms: int = 3000) -> Any:
        if self._eval_helper is None:
            raise RuntimeError(
                "BrowserSessionPrimitives.eval_js: extension_tools_service "
                "._evaluate_js is unavailable; cannot bridge to browser_session"
            )
        return await self._eval_helper(self._sess, snippet)

    async def read_dom(self, selector: str, *, depth: int = 2) -> dict:
        # Use JS to extract a normalised subtree — keeps API uniform
        # with the hybrid-cloud RpcBrowserPrimitives.read_dom.
        snippet = (
            "(() => {"
            f"const el = document.querySelector({selector!r});"
            "if (!el) return {tag: '', text: '', children: []};"
            "return {tag: el.tagName.toLowerCase(),"
            " text: (el.textContent || '').slice(0, 2000)};"
            "})()"
        )
        try:
            return await self.eval_js(snippet)
        except Exception:
            return {}

    async def click(self, selector: str, *, timeout_ms: int = 3000) -> bool:
        snippet = (
            "(() => {"
            f"const el = document.querySelector({selector!r});"
            "if (!el) return false;"
            "el.click(); return true;"
            "})()"
        )
        try:
            return bool(await self.eval_js(snippet))
        except Exception:
            return False

    async def type(
        self,
        selector: str,
        text: str,
        *,
        clear_first: bool = True,
        submit: bool = False,
    ) -> bool:
        # Best-effort JS-driven input fill.  Real typing fidelity
        # (keystroke events, IME composition) is left to the bundle's
        # tool-registry call; this primitive is a *fallback*.
        text_js = repr(text)
        snippet = (
            "(() => {"
            f"const el = document.querySelector({selector!r});"
            "if (!el) return false;"
            f"if ({str(clear_first).lower()}) el.value = '';"
            f"el.value = (el.value || '') + {text_js};"
            "el.dispatchEvent(new Event('input', {bubbles: true}));"
            "el.dispatchEvent(new Event('change', {bubbles: true}));"
            f"if ({str(submit).lower()}) {{"
            "const form = el.closest('form');"
            "if (form) form.submit();"
            "}"
            "return true;"
            "})()"
        )
        try:
            return bool(await self.eval_js(snippet))
        except Exception:
            return False

    async def wait_for(
        self,
        selector: str,
        *,
        condition: str = "present",
        timeout_ms: int = 5000,
    ) -> bool:
        # Polling loop in JS; one round-trip rather than many.
        cond_check = {
            "present": "el !== null",
            "visible": (
                "el !== null && el.offsetWidth > 0 && el.offsetHeight > 0"
            ),
            "hidden": "el === null || el.offsetWidth === 0",
        }.get(condition, "el !== null")
        snippet = (
            "(async () => {"
            f"const start = Date.now(); const limit = {int(timeout_ms)};"
            "while (Date.now() - start < limit) {"
            f"const el = document.querySelector({selector!r});"
            f"if ({cond_check}) return true;"
            "await new Promise(r => setTimeout(r, 50));"
            "} return false;"
            "})()"
        )
        try:
            return bool(await self.eval_js(snippet))
        except Exception:
            return False


class NoopAgentRegistry:
    """:class:`AgentRegistry` stub for environments without one wired.

    Returns no workers; PreDispatch will then fall back to its
    affinity / assigned-sessions logic.  Replace with a real
    registry when integrating with a live cloud orchestrator.
    """

    def list_workers(self, *, exclude: str = "") -> list[str]:
        return []

    def get_load(self, agent_id: str) -> int:
        return 0


class NoopSendChat:
    """:class:`SendChatProxy` stub.

    Returns ``{"success": False}`` so PreDispatch records a failed
    dispatch attempt without crashing.  Replace by wiring a real
    send_chat (e.g. ``agent.mcp.server.chat_utils.chat_tools.send_chat``).
    """

    async def send_chat(self, target, msg, *, metadata=None):
        logger.warning(
            f"[legacy_bridge] NoopSendChat invoked target={target!r} "
            f"msg_len={len(msg or '')} — wire a real SendChatProxy in "
            f"BackendBundle to actually deliver"
        )
        return {"success": False, "error": "no SendChatProxy wired"}


class NoopTypingLock:
    """:class:`TypingLock` stub — always grants the lock.

    Acceptable when the host browser is single-customer / single-tab.
    For Feige-style multi-customer pages, supply the real
    ``typing_lock`` module.
    """

    def try_acquire(self, key: str, *, ttl_s: float | None = None) -> bool:
        return True

    def release(self, key: str) -> None:
        pass

    def holder(self) -> str:
        return ""


# ============================================================================
# Public factory
# ============================================================================


# Storage keys we attach to dispatch_state_by_agent so bridge state is
# reusable across calls within one node lifetime.
_KV_KEY_SUFFIX = "_v2_session_kv"
_MSG_ID_KEY_SUFFIX = "_v2_last_msg_ids"


def _bridge_state_dicts(
    ctx: BrowserUseHookContext,
) -> tuple[dict, dict]:
    """Return ``(session_kv_store, last_msg_id_store)`` keyed off the
    legacy ``dispatch_state_by_agent`` map so bridge state survives
    across hook invocations within one node run."""
    base = ctx.dispatch_state_by_agent
    kv_key = (
        str(ctx.calling_agent_id or ""),
        str(ctx.node_name or ""),
        _KV_KEY_SUFFIX,
    )
    mid_key = (
        str(ctx.calling_agent_id or ""),
        str(ctx.node_name or ""),
        _MSG_ID_KEY_SUFFIX,
    )
    if not isinstance(base.get(kv_key), dict):
        base[kv_key] = {}
    if not isinstance(base.get(mid_key), dict):
        base[mid_key] = {}
    return base[kv_key], base[mid_key]


def backends_from_legacy_context(
    ctx: BrowserUseHookContext,
    *,
    agent: Any = None,
    agent_registry: AgentRegistry | None = None,
    send_chat: SendChatProxy | None = None,
    typing_lock: TypingLock | None = None,
    primitives: BrowserPrimitives | None = None,
    run_id: str = "",
) -> BackendBundle:
    """Build a :class:`BackendBundle` from a legacy hook context.

    Parameters
    ----------
    ctx
        The legacy :class:`BrowserUseHookContext` the runtime already built.
    agent
        Optional browser-use agent (late-phase only) — used to derive
        ``primitives`` if none was supplied.
    agent_registry, send_chat, typing_lock, primitives
        Optional explicit overrides — supply when integrating a real
        backend.  Defaults to the no-op stubs in this module.
    run_id
        Optional correlation ID for cross-tier RPCs.  Empty string is
        fine in full_local mode.
    """
    kv_store, msg_id_store = _bridge_state_dicts(ctx)

    if primitives is None and agent is not None:
        bs = getattr(agent, "browser_session", None)
        if bs is not None:
            primitives = BrowserSessionPrimitives(bs)

    return BackendBundle(
        node_name=str(ctx.node_name or ""),
        calling_agent_id=str(ctx.calling_agent_id or ""),
        state=DictSessionKV(kv_store),
        dispatch_state=LegacyDispatchState(ctx, msg_id_store),
        agent_registry=agent_registry or NoopAgentRegistry(),
        send_chat=send_chat or NoopSendChat(),
        primitives=primitives,
        typing_lock=typing_lock or NoopTypingLock(),
        transport=None,           # full_local mode — set in step-5 wire-up
        safe_format_dict=ctx.safe_format_dict,
        resolve_template=ctx.resolve_template,
        normalize_dispatch_identity_key=ctx.normalize_dispatch_identity_key,
        parse_json_input=ctx.parse_json_input,
        send_log=ctx.send_log,
        run_id=run_id or f"node:{ctx.node_name}:{int(time.time() * 1000)}",
    )
