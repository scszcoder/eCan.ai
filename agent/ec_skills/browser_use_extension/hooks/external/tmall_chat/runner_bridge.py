"""Tmall (千牛) runner bridge — the one facade the platform resolves
site capabilities through (``live_chat_dispatch.runner_bridge()``).

PARTIAL SURFACE BY DESIGN (design decision D3 in
``docs/TMALL_QIANNIU_CHAT_DESIGN.md``): the decoupling's guard-semantics
invariant means every platform call site wraps bridge use in try/except
and falls back to its site-agnostic default when an attribute is missing —
exactly like a failed lazy import.  This bridge implements only what the
Phase 1 DOM-first scaffold supports; everything else (``dispatch_state``,
``placeholder_timer``, ``hot_path``, ``ws_session``, ``pre_dispatch_enrich``,
``front_desk``, ...) is intentionally absent and raises ``AttributeError``
inside those guards.  Add attributes here one at a time as their modules
are ported from ``feige_chat``.

Design rules (same as ``feige_chat/runner_bridge.py``):

* Every attribute resolves lazily (property / method doing a local import)
  so importing this module stays cheap and cycle-free.
* Attribute names are platform-neutral; anything Tmall-branded (function
  names, env-var spellings, defaults) stays on this side of the boundary.
"""
from __future__ import annotations

from typing import Any


class TmallRunnerBridge:
    """Site bridge for the Qianniu (千牛) Web workbench."""

    # ------------------------------------------------------------------
    # Lazy module accessors (generic names → tmall_chat modules)
    # ------------------------------------------------------------------
    @property
    def typing_lock(self):
        from . import typing_lock
        return typing_lock

    @property
    def system_message_filter(self):
        from . import system_message_filter
        return system_message_filter

    @property
    def ws_observer(self):
        # Phase 1: capture-only frame logger (no decode, no dispatch).
        from . import ws_observer
        return ws_observer

    @property
    def dom(self):
        from . import dom
        return dom

    @property
    def tunables(self):
        from . import tunables
        return tunables

    @property
    def site_adapter_preset(self) -> dict:
        from .site_adapter_preset import DEFAULT_SITE_ADAPTER
        return DEFAULT_SITE_ADAPTER

    # ------------------------------------------------------------------
    # Identity strings
    # ------------------------------------------------------------------
    @property
    def tool_name_glob(self) -> str:
        return "tmall_*"

    @property
    def open_session_tool_name(self) -> str:
        return "tmall_open_session"

    @property
    def send_message_tool_name(self) -> str:
        return "tmall_send_message"

    @property
    def list_sessions_tool_name(self) -> str:
        return "tmall_list_sessions"

    @property
    def trace_label_prefix(self) -> str:
        return "tmall_"

    @property
    def site_plugin_name(self) -> str:
        return "tmall_chat"

    # ------------------------------------------------------------------
    # DOM helpers
    # ------------------------------------------------------------------
    async def resolve_tab_target_id(self, session: Any, **kwargs: Any):
        from .dom import resolve_tmall_tab_target_id
        return await resolve_tmall_tab_target_id(session, **kwargs)

    # ------------------------------------------------------------------
    # Typed tunables the platform asks for by method (site-branded env
    # spellings stay bundle-side).
    # ------------------------------------------------------------------
    def typing_concurrency(self, state: dict | None = None) -> int:
        from .tunables import resolve_int, DEFAULT_TMALL_TYPING_CONCURRENCY
        return resolve_int("TMALL_TYPING_CONCURRENCY", DEFAULT_TMALL_TYPING_CONCURRENCY, state)

    def tab_resolve_timeout_s(self, state: dict | None = None) -> float:
        from .tunables import resolve_float, DEFAULT_TMALL_TAB_RESOLVE_TIMEOUT_S
        return resolve_float("TMALL_TAB_RESOLVE_TIMEOUT_S", DEFAULT_TMALL_TAB_RESOLVE_TIMEOUT_S, state)

    # ------------------------------------------------------------------
    # Send-outcome policy
    # ------------------------------------------------------------------
    @property
    def retryable_send_reasons(self) -> frozenset[str]:
        return frozenset({"tool_failed:tmall_send_message"})

    @property
    def node_tunable_number_fields(self) -> "list[tuple[str, str]]":
        return []

    @property
    def node_tunable_bool_fields(self) -> "list[tuple[str, str]]":
        return []

    def classify_send_error(self, err: str) -> "str | None":
        """Map the send tool's site-specific error markers to the runner's
        generic outcome reason codes.  Phase 1 has no verify pipeline yet,
        so only the generic input-not-found marker is classified."""
        text = str(err or "")
        if "tmall_send_failed:input_not_found" in text:
            return "send_failed_input_not_found"
        return None

    # ------------------------------------------------------------------
    # CDP health passthroughs — the machinery is platform-side and
    # site-neutral; the bridge just forwards (same as feige_chat).
    # ------------------------------------------------------------------
    def cdp_health_cooldown_remaining(self) -> float:
        from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        fn = getattr(_ets, "live_chat_cdp_health_cooldown_remaining", None)
        return float(fn()) if callable(fn) else 0.0

    def mark_cdp_unhealthy(self, *args: Any, **kwargs: Any) -> None:
        from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        fn = getattr(_ets, "mark_live_chat_cdp_unhealthy", None)
        if callable(fn):
            fn(*args, **kwargs)

    def mark_cdp_healthy(self) -> None:
        from agent.ec_skills.browser_use_extension import extension_tools_service as _ets
        fn = getattr(_ets, "mark_live_chat_cdp_healthy", None)
        if callable(fn):
            fn()


def register() -> None:
    """Register the Tmall runner bridge (called from package __init__)."""
    from agent.ec_skills import live_chat_dispatch
    live_chat_dispatch.register_runner_bridge(TmallRunnerBridge())
