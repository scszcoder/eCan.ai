"""Step 4 — tier-aware context builder + v2 hook dispatcher.

The integration glue between the existing hook discovery (build_node's
``_discover_external_hook_bundles`` / ``hook_loader``) and the v2 hooks
shipped by step 2.

Responsibilities
----------------

1. **Context builder per tier** — given a tier label and a backend
   bundle (state KV, dispatch state, primitives source, send-chat
   proxy, etc.), produce the right typed context shape:

   * ``cloud_only``      → :class:`CloudHookContext`
   * ``local_reactive``  → :class:`LocalReactiveContext`
   * ``local_extract``   → :class:`LocalExtractContext`

2. **Mode-aware backend selection** — the same v2 hook code runs in
   either of two modes:

   * **full_local** — backends are in-process (real
     :class:`BrowserPrimitives`, real :class:`SessionKV` dict).
   * **hybrid_cloud** — backends are RPC proxies over a
     :class:`HybridTransport`.

3. **v2 hook dispatch** — given a hook instance (with
   ``EXECUTION_TIER`` set), build the right context and call ``run``.

Design
------

This module is **not** a replacement for ``hook_loader.py`` — it
sits BESIDE it.  Bundle loading still happens via the existing
discovery flow; this module wires the loaded hooks to the right
context at invocation time.

The module is **transport-agnostic for tests**: every backend can be
swapped via constructor args.  Production binding (Step 5+)
constructs ``BackendBundle`` from the live skill runtime; tests use
in-memory backends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from agent.ec_skills.browser_node.contexts import (
    AgentRegistry,
    BrowserPrimitives,
    CloudHookContext,
    DispatchState,
    LocalExtractContext,
    LocalReactiveContext,
    SendChatProxy,
    SessionKV,
    TypingLock,
)
from agent.ec_skills.browser_use_extension.hybrid_protocol import (
    HybridTransport,
    RpcBrowserPrimitives,
    RpcScrapeFunction,
)

logger = logging.getLogger("ecan.tier_aware_runner")

__all__ = [
    "RunMode",
    "BackendBundle",
    "ContextBuilder",
    "TierAwareRunner",
    "build_context_for_hook",
    "dispatch_v2_hook",
]


# ============================================================================
# RunMode — the configuration knob
# ============================================================================


class RunMode(str, Enum):
    """How the v2 hooks are wired at runtime.

    * ``FULL_LOCAL`` — every backend is in-process.  Single-machine
      deployment, no AppSync involvement.  Identical to v1's runtime
      modulo the new context shapes.

    * ``HYBRID_CLOUD`` — cloud_only hooks run on the cloud agent and
      use :class:`RpcBrowserPrimitives` / :class:`RpcScrapeFunction`
      to drive the local browser via AppSync.  local_reactive and
      local_extract hooks run on the local agent against in-process
      primitives.

    The mode is normally set once per skill run from the node-editor
    config (``runEnvironment``).  Hooks themselves never observe it —
    only the runner does, when picking which backend to wire.
    """

    FULL_LOCAL = "full_local"
    HYBRID_CLOUD = "hybrid_cloud"


# ============================================================================
# BackendBundle — the per-run capability set
# ============================================================================


@dataclass
class BackendBundle:
    """The full set of pluggable backends a runner may need.

    Not all tiers consume all fields:

    * ``CloudHookContext`` uses agent_registry + send_chat + dispatch_state + state
    * ``LocalReactiveContext`` uses primitives + typing_lock + state + dispatch_state
    * ``LocalExtractContext`` uses primitives only

    Optional fields default to ``None``; the builder raises a clear
    error if a tier needs a missing one.
    """

    # Identity
    node_name: str
    calling_agent_id: str

    # State / orchestration
    state: SessionKV | None = None
    dispatch_state: DispatchState | None = None

    # Cloud-side capabilities
    agent_registry: AgentRegistry | None = None
    send_chat: SendChatProxy | None = None

    # Local-side capabilities (full_local mode) or proxies (hybrid_cloud)
    primitives: BrowserPrimitives | None = None
    typing_lock: TypingLock | None = None

    # Cross-tier transport (hybrid_cloud only)
    transport: HybridTransport | None = None

    # Templating + utilities — usually thin lambdas
    safe_format_dict: Callable[..., dict] = dict
    resolve_template: Callable[[str, dict], str] = field(
        default=lambda s, _d: s
    )
    normalize_dispatch_identity_key: Callable[[str], str] = field(
        default=lambda s: (s or "").strip().lower()
    )
    parse_json_input: Callable[[dict, str], Any] = field(
        default=lambda d, k: d.get(k)
    )
    send_log: Callable[[str, str], None] = field(
        default=lambda level, msg: None
    )

    # Run-correlation (for transport step IDs)
    run_id: str = ""


# ============================================================================
# Context builder
# ============================================================================


_KNOWN_TIERS = {"cloud_only", "local_reactive", "local_extract"}


class ContextBuilder:
    """Builds the right typed context for a tier + mode combination.

    Use cases:
      * runtime invokes a v2 hook → calls :meth:`build` with the hook's
        ``EXECUTION_TIER`` to receive a ready-to-pass context.
      * tests construct a builder once, reuse for many hooks.
    """

    def __init__(self, mode: RunMode, backends: BackendBundle):
        self.mode = mode
        self.backends = backends

    # ── public dispatch ──
    def build(self, tier: str) -> Any:
        """Return the typed context for a hook of the given tier.

        Raises
        ------
        ValueError
            For unknown tiers, or when a required backend is missing.
        """
        if tier == "cloud_only":
            return self._build_cloud()
        if tier == "local_reactive":
            return self._build_local_reactive()
        if tier == "local_extract":
            return self._build_local_extract()
        raise ValueError(
            f"unknown EXECUTION_TIER: {tier!r} "
            f"(expected one of {sorted(_KNOWN_TIERS)})"
        )

    # ── per-tier builders ──
    def _build_cloud(self) -> CloudHookContext:
        b = self.backends
        self._require("cloud_only", "state", b.state)
        self._require("cloud_only", "dispatch_state", b.dispatch_state)
        self._require("cloud_only", "agent_registry", b.agent_registry)
        self._require("cloud_only", "send_chat", b.send_chat)
        return CloudHookContext(
            node_name=b.node_name,
            calling_agent_id=b.calling_agent_id,
            agent_registry=b.agent_registry,
            send_chat=b.send_chat,
            dispatch_state=b.dispatch_state,
            state=b.state,
            parse_json_input=b.parse_json_input,
            normalize_dispatch_identity_key=b.normalize_dispatch_identity_key,
            resolve_template=b.resolve_template,
            safe_format_dict=b.safe_format_dict,
            send_log=b.send_log,
        )

    def _build_local_reactive(self) -> LocalReactiveContext:
        b = self.backends
        self._require("local_reactive", "state", b.state)
        self._require("local_reactive", "dispatch_state", b.dispatch_state)
        self._require("local_reactive", "typing_lock", b.typing_lock)
        primitives = self._select_primitives("local_reactive")
        return LocalReactiveContext(
            node_name=b.node_name,
            calling_agent_id=b.calling_agent_id,
            primitives=primitives,
            typing_lock=b.typing_lock,
            state=b.state,
            dispatch_state=b.dispatch_state,
            safe_format_dict=b.safe_format_dict,
            resolve_template=b.resolve_template,
            normalize_dispatch_identity_key=b.normalize_dispatch_identity_key,
            send_log=b.send_log,
        )

    def _build_local_extract(self) -> LocalExtractContext:
        b = self.backends
        primitives = self._select_primitives("local_extract")
        return LocalExtractContext(
            node_name=b.node_name,
            calling_agent_id=b.calling_agent_id,
            primitives=primitives,
            send_log=b.send_log,
        )

    # ── primitives selection — the only mode-aware decision ──
    def _select_primitives(self, tier: str) -> BrowserPrimitives:
        b = self.backends
        if self.mode == RunMode.FULL_LOCAL:
            self._require(tier, "primitives (FULL_LOCAL)", b.primitives)
            return b.primitives  # type: ignore[return-value]
        # HYBRID_CLOUD — but local_reactive / local_extract hooks
        # ALMOST ALWAYS run on the local side where in-process
        # primitives are correct.  The Rpc proxy is used only when
        # cloud-side delegation is configured (rare).  In tests we
        # let the caller force one or the other by setting
        # backends.primitives explicitly OR backends.transport for the
        # proxy case.
        if b.primitives is not None:
            return b.primitives
        self._require(tier, "transport (HYBRID_CLOUD without primitives)", b.transport)
        return RpcBrowserPrimitives(b.transport, run_id=b.run_id or "default")  # type: ignore[arg-type]

    # ── helpers ──
    @staticmethod
    def _require(tier: str, field_name: str, value: Any) -> None:
        if value is None:
            raise ValueError(
                f"BackendBundle.{field_name} is required for tier "
                f"{tier!r} but was None"
            )


# ============================================================================
# Convenience: top-level dispatch helper
# ============================================================================


def build_context_for_hook(
    hook: Any,
    mode: RunMode,
    backends: BackendBundle,
) -> Any:
    """Inspect ``hook.EXECUTION_TIER`` and return its context.

    Convenience wrapper around :class:`ContextBuilder`.  Raises
    ``ValueError`` if the hook has no ``EXECUTION_TIER`` attribute.
    """
    tier = getattr(hook, "EXECUTION_TIER", None)
    if not isinstance(tier, str):
        raise ValueError(
            f"hook {type(hook).__name__} has no string EXECUTION_TIER "
            f"attribute (got {tier!r}); cannot dispatch as a v2 hook"
        )
    return ContextBuilder(mode, backends).build(tier)


async def dispatch_v2_hook(
    hook: Any,
    mode: RunMode,
    backends: BackendBundle,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Build the context, then call ``await hook.run(ctx, *args, **kwargs)``.

    The integration entry point for runtime code that already knows
    which v2 hook to invoke.  v1 hooks (no ``EXECUTION_TIER``) raise.
    """
    ctx = build_context_for_hook(hook, mode, backends)
    if not hasattr(hook, "run"):
        raise ValueError(
            f"hook {type(hook).__name__} has no run() method"
        )
    return await hook.run(ctx, *args, **kwargs)


# ============================================================================
# TierAwareRunner — small stateful façade for runtime use
# ============================================================================


class TierAwareRunner:
    """Stateful runner: hold the mode + backends once, dispatch many hooks.

    Production use:

        runner = TierAwareRunner(RunMode.HYBRID_CLOUD, backends)
        await runner.dispatch(hook_a, state, inputs)
        await runner.dispatch(hook_b, state, inputs, scrape_fn=...)

    Tests benefit from this too — fewer constructor args per call.
    """

    def __init__(self, mode: RunMode, backends: BackendBundle):
        self.mode = mode
        self.backends = backends
        self._builder = ContextBuilder(mode, backends)

    async def dispatch(self, hook: Any, *args: Any, **kwargs: Any) -> Any:
        ctx = self._builder.build(getattr(hook, "EXECUTION_TIER", "<missing>"))
        return await hook.run(ctx, *args, **kwargs)

    def context_for(self, tier: str) -> Any:
        """Build a context without running a hook — useful when a hook
        function (not a class instance) is used directly."""
        return self._builder.build(tier)
