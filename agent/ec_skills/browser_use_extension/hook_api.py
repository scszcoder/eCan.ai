"""
Hook API — public contract for the HookedAgent plugin system.

This module defines the versioned contract between the HookedAgent runtime
and hook implementations (built-in, skill-bundle, distributor).

The runtime invokes hooks at well-defined *stages* of the browser-use agent
loop.  Each hook returns a *Decision* telling the runtime what to do next:
continue normally, replace the payload, bypass the LLM with deterministic
actions, drop the event, hand off to another agent, or escalate to the LLM
even though a prior hook said Bypass.

Versioning
----------
The contract evolves via ``HOOK_API_VERSION``.  Every manifest must declare
the version it was written against.  The loader refuses to register a hook
whose declared version the current runtime does not support (or, in the
future, applies a compat shim).  This prevents silent breakage when fields
are renamed, stages added, or decision verbs deprecated.

Only public symbols below are part of the contract.  Anything prefixed with
an underscore is runtime-private and may change without a version bump.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Contract version.  Bump when the public shape changes (new stage, renamed
# field on HookContext, removed decision).  Loader-side compatibility is
# handled by ``hook_dispatcher._is_api_version_supported``.
# ---------------------------------------------------------------------------
HOOK_API_VERSION: int = 1


# ---------------------------------------------------------------------------
# Stages — insertion points in the browser-use agent loop.
# Keep this list aligned with the patch sites in HookedAgent.
# ---------------------------------------------------------------------------
class Stage(str, Enum):
    ON_EVENT_RAW = "on_event_raw"
    ON_EVENT_NORMALIZED = "on_event_normalized"
    ON_PRE_STEP = "on_pre_step"
    ON_POST_OBSERVE = "on_post_observe"  # LLM bypass opportunity
    ON_PRE_ACTION = "on_pre_action"
    ON_POST_ACTION = "on_post_action"
    ON_STEP_END = "on_step_end"
    ON_ERROR = "on_error"
    ON_DONE = "on_done"
    # mt051B (2026-05-28): generic live-chat placeholder dispatch.
    # Fired by the runner when a chat-task placeholder needs to be
    # typed/sent.  Site-specific hooks (Feige, future Shopify/WeChat
    # integrations, etc.) own the implementation; the runner remains
    # agnostic about how the placeholder reaches the customer.
    # Payload contract: ``LiveChatPlaceholderRequest`` (see below).
    # No consumers yet at the time of mt051B; mt051C migrates Feige's
    # ``_enqueue_direct_placeholder`` to plug in here.  Adding a stage
    # is purely additive — HOOK_API_VERSION stays at 1.
    ON_LIVE_CHAT_PLACEHOLDER_NEEDED = "on_live_chat_placeholder_needed"


# ---------------------------------------------------------------------------
# Decisions — the runtime reads these and acts accordingly.
# ---------------------------------------------------------------------------
class Decision(str, Enum):
    CONTINUE = "continue"
    REPLACE = "replace"
    BYPASS = "bypass"
    DROP = "drop"
    HANDOFF = "handoff"
    ESCALATE = "escalate"


# Tiers ----------------------------------------------------------------------
# 0 = built-in (ships with the app, safety-critical, cannot be disabled by
#     Tier-1/Tier-2 hooks)
# 1 = distributor (signed bundle deployed with the app)
# 2 = skill-local (lives in the skill bundle, user-authored)
Tier = Literal[0, 1, 2]


# ---------------------------------------------------------------------------
# BypassAction — the payload shape returned alongside Decision.BYPASS.
# Lists one or more tool invocations the runtime will execute deterministi-
# cally in place of the LLM's decision.
# ---------------------------------------------------------------------------
class BypassAction(BaseModel):
    name: str = Field(..., description="Registered tool name, e.g. 'feige_send_message'.")
    args: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# LiveChatPlaceholderRequest — payload contract for the
# ON_LIVE_CHAT_PLACEHOLDER_NEEDED stage.
#
# Added in mt051B (2026-05-28).  The runner uses this envelope to dispatch
# placeholder-send requests to a site-specific hook (Feige today, planned
# Shopify / WeChat / other e-commerce live-chat integrations).  Field
# semantics deliberately use site-neutral names: each hook unwraps these
# into whatever its underlying API needs (e.g. Feige reads ``session_id``
# as ``customer_key`` and ``turn_id`` as ``source_msg_id``).
#
# Runtime handles (``browser_session``, tab routing, etc.) live on the
# HookContext — NOT on this request — so the same envelope works for
# headless cloud workers, desktop GUI sessions, etc.
# ---------------------------------------------------------------------------
class LiveChatPlaceholderRequest(BaseModel):
    session_id: str = Field(
        ...,
        description=(
            "Site-specific conversation identifier.  Feige: customer_key "
            "(sidebar customer name).  Shopify: conversation_id.  "
            "WeChat: openid.  Required."
        ),
    )
    turn_id: str = Field(
        "",
        description=(
            "Site-specific dedup key for this turn.  Feige: source_msg_id "
            "(DOM bubble id).  Shopify: event_id.  Empty string is allowed "
            "for stateless sites that don't need per-turn dedup."
        ),
    )
    text: str = Field(
        ...,
        description="The placeholder text to type or send.  Required.",
    )
    armed_at: float = Field(
        0.0,
        description=(
            "Wall-clock seconds (time.time()) when the placeholder timer was "
            "armed.  Used by the mt050P newer-turn semantic — site hooks "
            "compare this against any recent real-reply stamp to decide if "
            "a stale-but-recent reply should suppress this placeholder.  "
            "0.0 means unknown; site hook should fall back to current time."
        ),
    )
    site_context: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Opaque blob the site hook may interpret.  The generic "
            "dispatcher passes this through unchanged.  Use for runtime "
            "data that doesn't belong on HookContext (e.g. preferred tab "
            "id, dispatch-time correlation ids).  Site hooks that don't "
            "need it can ignore the field entirely."
        ),
    )


# ---------------------------------------------------------------------------
# HookResult — what a hook returns from run().
# ---------------------------------------------------------------------------
class HookResult(BaseModel):
    decision: Decision = Decision.CONTINUE
    # For REPLACE: new payload (event dict / state).
    # For BYPASS:  list[BypassAction] (serialised as list of dicts).
    # For HANDOFF/DROP/CONTINUE/ESCALATE: may be None.
    payload: Any = None
    handoff_agent: Optional[str] = None
    reason: str = ""

    # Convenience constructors --------------------------------------------------
    @classmethod
    def cont(cls, reason: str = "") -> "HookResult":
        return cls(decision=Decision.CONTINUE, reason=reason)

    @classmethod
    def replace(cls, payload: Any, reason: str = "") -> "HookResult":
        return cls(decision=Decision.REPLACE, payload=payload, reason=reason)

    @classmethod
    def bypass(cls, actions: list[BypassAction] | list[dict], reason: str = "") -> "HookResult":
        norm: list[dict] = []
        for a in actions or []:
            if isinstance(a, BypassAction):
                norm.append(a.model_dump())
            elif isinstance(a, dict):
                # Lightweight validation so downstream can trust shape.
                BypassAction.model_validate(a)
                norm.append(a)
            else:
                raise TypeError(f"BypassAction expected, got {type(a).__name__}")
        return cls(decision=Decision.BYPASS, payload=norm, reason=reason)

    @classmethod
    def drop(cls, reason: str = "") -> "HookResult":
        return cls(decision=Decision.DROP, reason=reason)

    @classmethod
    def handoff(cls, agent: str, reason: str = "") -> "HookResult":
        return cls(decision=Decision.HANDOFF, handoff_agent=agent, reason=reason)

    @classmethod
    def escalate(cls, reason: str = "") -> "HookResult":
        return cls(decision=Decision.ESCALATE, reason=reason)


# ---------------------------------------------------------------------------
# Failure policy literals — declared per-hook in the manifest.
# ---------------------------------------------------------------------------
FailurePolicy = Literal["fall_through", "drop", "escalate_llm"]


class CircuitBreakerConfig(BaseModel):
    failure_threshold: int = 5
    cool_down_s: float = 60.0


class Budget(BaseModel):
    timeout_ms: int = 500
    rate_per_minute: int = 120


class Permissions(BaseModel):
    # Tool name globs, e.g. ["feige_*", "send_chat"].  Empty list = no tool
    # access.  Evaluated by the ToolProxy at call time.
    tools: list[str] = Field(default_factory=list)
    network: Literal["none", "whitelist", "full"] = "none"
    storage: Literal["none", "skill_scoped"] = "skill_scoped"


# ---------------------------------------------------------------------------
# HookManifest — declarative front door for every hook, regardless of
# runtime lane (python / js_injected / subprocess).  The loader trusts the
# manifest first; code is opaque until the manifest validates.
# ---------------------------------------------------------------------------
class HookManifest(BaseModel):
    hook_api_version: int = HOOK_API_VERSION

    name: str
    version: str = "0.0.0"
    author: str = ""

    runtime: Literal["python", "js_injected", "subprocess"] = "python"
    stage: Stage
    priority: int = 100  # lower = earlier within stage
    enabled: bool = True
    tier: Tier = 2

    # Trigger predicate.  Known keys (loose contract):
    #   event_type: str | list[str]  (match on normalized event dict)
    #   site: str                    (match on site_adapter.name)
    #   url_contains: str            (match on current page url)
    #   action_name: str | list[str] (match on action about to run; pre-action)
    #   has_fields: list[str]        (payload dict must contain all of these)
    # Unknown keys are ignored so forward-compatible matchers can be added.
    matches: dict[str, Any] = Field(default_factory=dict)

    permissions: Permissions = Field(default_factory=Permissions)
    budget: Budget = Field(default_factory=Budget)

    # State persistence model — user-selectable per hook.
    # "memory": lives on the HookedAgent instance; cleared on agent teardown.
    # "disk":   persisted under the skill bundle's state dir; survives runs.
    state: Literal["memory", "disk"] = "memory"

    # When non-empty, hooks sharing this namespace string get the SAME
    # StateStore instance.  Used by paired hooks (e.g. typing_lock_acquire
    # at on_pre_action + typing_lock_release at on_post_action) so the lock
    # state written by one is read by the other.  When empty (default),
    # each hook gets its own store keyed by its name.
    state_namespace: str = ""

    on_timeout: FailurePolicy = "fall_through"
    on_error: FailurePolicy = "fall_through"
    circuit_breaker: CircuitBreakerConfig = Field(default_factory=CircuitBreakerConfig)

    # Pointer to the hook implementation.  Shape depends on runtime:
    #   python:       "relative/path.py:ClassName"
    #   js_injected:  "relative/path.js"
    #   subprocess:   ["deno", "run", "relative/path.ts"]  (argv, first token is exe)
    entrypoint: Any

    @field_validator("hook_api_version")
    @classmethod
    def _api_version_is_positive(cls, v: int) -> int:
        if not isinstance(v, int) or v <= 0:
            raise ValueError(f"hook_api_version must be a positive integer, got {v!r}")
        return v

    @field_validator("name")
    @classmethod
    def _name_is_identifier_like(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("name must be a non-empty string")
        # Permissive: allow dots and dashes in names, but no whitespace.
        if any(ch.isspace() for ch in v):
            raise ValueError(f"name must not contain whitespace: {v!r}")
        return v


# ---------------------------------------------------------------------------
# Runtime-facing interfaces (Protocols — hooks only need to *look* like this).
# ---------------------------------------------------------------------------
@runtime_checkable
class ToolProxy(Protocol):
    """Scoped tool invoker passed to hooks via ``HookContext.tools``.

    Construction is the runtime's responsibility; it enforces the manifest's
    ``permissions.tools`` list.  Hooks call ``await ctx.tools.<name>(**args)``
    or ``await ctx.tools.call(name, **args)``; both route through the same
    permission-gated path.
    """

    async def call(self, name: str, /, **args: Any) -> Any: ...


@runtime_checkable
class StateStore(Protocol):
    """Small KV store scoped to a single hook.

    When manifest ``state="memory"``: values live on the HookedAgent and are
    lost on teardown.  When manifest ``state="disk"``: values persist under
    the skill bundle's state dir (JSON-serialised).  Hooks don't need to
    know which backend they got.
    """

    def get(self, key: str, default: Any = None) -> Any: ...
    def set(self, key: str, value: Any) -> None: ...
    def delete(self, key: str) -> None: ...
    def keys(self) -> list[str]: ...


@runtime_checkable
class HookContext(Protocol):
    """Read-only surface passed to every hook invocation.

    The runtime guarantees all attributes are present when ``run()`` is
    called.  Hooks MUST NOT mutate ``manifest``, ``site_adapter``, or
    ``config`` — these are shared across invocations.

    ``browser_session`` is the live ``browser_use.BrowserSession`` handle.
    It's ``None`` only in non-browser test contexts; in production code
    paths invoked from a ``HookedAgent`` it is always the same instance
    the underlying ``Agent`` is bound to.  Hooks that need DOM access
    (e.g. evaluate JS, read URL, wait for selector) use this directly,
    typically through helpers in ``extension_tools_service`` such as
    ``_evaluate_js(ctx.browser_session, script)``.
    """

    manifest: HookManifest
    trace_id: str
    span_id: str
    step: int
    site_adapter: dict  # resolved per-node; data-only (selectors/policy)
    tools: ToolProxy
    state: StateStore
    logger: Any
    config: dict  # user-supplied config from the node editor
    browser_session: Any  # browser_use.BrowserSession | None

    # Optional diagnostics — hooks may or may not emit custom spans.
    def emit_span(self, name: str, attrs: dict | None = None) -> None: ...


@runtime_checkable
class Hook(Protocol):
    """The minimum a hook implementation must provide.

    Concrete base classes and convenience decorators live in
    ``hooks/builtin/base.py``; this Protocol is what the dispatcher checks.
    """

    manifest: HookManifest

    async def run(self, ctx: HookContext, payload: Any) -> HookResult: ...


# ---------------------------------------------------------------------------
# Exceptions — raised by the loader, not by hooks themselves.
# ---------------------------------------------------------------------------
class HookApiError(Exception):
    """Base for hook-api related errors raised by the runtime."""


class IncompatibleHookApiVersion(HookApiError):
    """Raised when a manifest declares an unsupported hook_api_version."""


class DuplicateHookName(HookApiError):
    """Raised when two hooks register with the same name."""


class PermissionDenied(HookApiError):
    """Raised by the ToolProxy when a hook calls a tool outside its
    declared permissions."""


class TierViolation(HookApiError):
    """Raised when non-Tier-0 code attempts to register a Tier-0 hook."""


__all__ = [
    "HOOK_API_VERSION",
    "Stage",
    "Decision",
    "Tier",
    "BypassAction",
    "LiveChatPlaceholderRequest",
    "HookResult",
    "FailurePolicy",
    "CircuitBreakerConfig",
    "Budget",
    "Permissions",
    "HookManifest",
    "ToolProxy",
    "StateStore",
    "HookContext",
    "Hook",
    "HookApiError",
    "IncompatibleHookApiVersion",
    "DuplicateHookName",
    "PermissionDenied",
    "TierViolation",
]
