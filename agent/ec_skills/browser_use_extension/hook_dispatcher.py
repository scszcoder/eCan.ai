"""
HookDispatcher — runtime registry + execution engine for hooks.

One dispatcher is owned per ``HookedAgent`` instance.  Responsibilities:

1. Registration
     * Validate each manifest (schema + API version + tier).
     * Enforce "Tier-0 can only be registered from our own package".
     * Reject duplicate names.

2. Dispatch
     * Look up hooks for a stage, ordered by priority then registration.
     * For each hook, evaluate ``matches`` against the payload; skip if miss.
     * Enforce per-hook timeout (from manifest.budget.timeout_ms).
     * Trap exceptions; apply ``on_error`` / ``on_timeout`` policy.
     * Chain CONTINUE/REPLACE; stop on first terminal decision
       (BYPASS / DROP / HANDOFF / ESCALATE).

3. Tracing
     * Emit a structured span per hook invocation with trace_id/span_id,
       duration, decision, and optional reason.

4. Circuit breaker
     * Per-hook failure counter with cool-down; short-circuits a misbehaving
       hook without disabling the whole stage.

This module is deliberately transport-free: Python hooks are invoked in
process; JS-injected and subprocess lanes will register ``runtime="python"``
shim hooks that bridge into their respective transports (added in later PRs).
"""

from __future__ import annotations

import asyncio
import fnmatch
import inspect
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable

from .hook_api import (
    HOOK_API_VERSION,
    BypassAction,
    Decision,
    DuplicateHookName,
    Hook,
    HookApiError,
    HookContext,
    HookManifest,
    HookResult,
    IncompatibleHookApiVersion,
    PermissionDenied,
    Stage,
    StateStore,
    Tier,
    TierViolation,
    ToolProxy,
)

# Route INFO/WARN/ERROR into the shared eCan log stream so per-stage
# hook decisions are visible alongside BrowserAutomation lines.
logger = logging.getLogger("eCan")

# Package prefix whose callers are allowed to register Tier-0 hooks.  Keep
# this list narrow; it's the structural (not conventional) guard.
_TIER0_ALLOWED_PACKAGE_PREFIXES: tuple[str, ...] = (
    "agent.ec_skills.",
    "agent.ec_skills.browser_use_extension.",
)


def _is_api_version_supported(declared: int) -> bool:
    """Return True when the runtime can execute hooks with this API version.

    Today we only support the exact current version.  A future runtime may
    accept multiple versions (N and N-1) via compatibility shims; this helper
    is where that logic lands.
    """
    return declared == HOOK_API_VERSION


def _caller_module_name(skip_frames: int = 2) -> str:
    """Return the dotted module name of the caller *skip_frames* above.

    Used to enforce Tier-0 registration rules without needing the caller to
    explicitly identify itself.  Falls back to the empty string when the
    stack is too shallow (e.g. in some test harnesses).
    """
    frame = inspect.currentframe()
    try:
        for _ in range(skip_frames):
            if frame is None:
                return ""
            frame = frame.f_back
        if frame is None:
            return ""
        mod = inspect.getmodule(frame)
        return (getattr(mod, "__name__", "") or "") if mod else ""
    finally:
        # Avoid reference cycles per the inspect docs.
        del frame


def _caller_is_tier0_allowed() -> bool:
    mod_name = _caller_module_name(skip_frames=3)
    return any(mod_name.startswith(p) for p in _TIER0_ALLOWED_PACKAGE_PREFIXES)


# ---------------------------------------------------------------------------
# Matchers — small evaluator for manifest ``matches`` predicates.
# ---------------------------------------------------------------------------
def _matches_payload(matches: dict, payload: Any, site_adapter: dict | None) -> bool:
    """Evaluate a manifest ``matches`` dict against a payload.

    Unknown keys are ignored so future matcher types don't break older hooks.
    All known keys are AND-combined; missing keys are treated as "don't care".
    """
    if not matches:
        return True

    def _as_dict(p: Any) -> dict:
        if isinstance(p, dict):
            return p
        if hasattr(p, "model_dump"):
            try:
                return p.model_dump()
            except Exception:
                return {}
        return {}

    pd = _as_dict(payload)

    # event_type: str | list[str]
    want_et = matches.get("event_type")
    if want_et is not None:
        have = pd.get("event_type") or pd.get("type") or ""
        if isinstance(want_et, str):
            if have != want_et:
                return False
        elif isinstance(want_et, (list, tuple, set)):
            if have not in want_et:
                return False

    # site: str — compared against site_adapter.name
    want_site = matches.get("site")
    if want_site is not None:
        sa_name = (site_adapter or {}).get("name") or ""
        if sa_name != want_site:
            return False

    # url_contains: str — substring test against url field in payload
    want_url = matches.get("url_contains")
    if want_url:
        url = pd.get("url") or ""
        if want_url not in url:
            return False

    # action_name: str | list[str] — match action about to run (pre-action)
    want_action = matches.get("action_name")
    if want_action is not None:
        have = pd.get("action_name") or ""
        if isinstance(want_action, str):
            if have != want_action:
                return False
        elif isinstance(want_action, (list, tuple, set)):
            if have not in want_action:
                return False

    # has_fields: list[str] — payload must contain all keys with non-empty value
    want_fields = matches.get("has_fields") or []
    if want_fields:
        for k in want_fields:
            if not pd.get(k):
                return False

    return True


# ---------------------------------------------------------------------------
# Circuit breaker state.
# ---------------------------------------------------------------------------
@dataclass
class _CircuitState:
    failures: int = 0
    opened_at: float = 0.0  # 0 = closed

    def trip(self, threshold: int, cool_down_s: float, now: float) -> None:
        self.failures += 1
        if self.failures >= threshold:
            self.opened_at = now

    def should_skip(self, cool_down_s: float, now: float) -> bool:
        if self.opened_at <= 0:
            return False
        if now - self.opened_at >= cool_down_s:
            # Reset — allow a probe.
            self.failures = 0
            self.opened_at = 0.0
            return False
        return True


# ---------------------------------------------------------------------------
# Per-hook runtime record.
# ---------------------------------------------------------------------------
@dataclass
class _Registered:
    hook: Hook
    manifest: HookManifest
    registration_index: int
    breaker: _CircuitState = field(default_factory=_CircuitState)

    @property
    def sort_key(self) -> tuple[int, int]:
        # Lower priority runs first; ties broken by registration order.
        return (int(self.manifest.priority), int(self.registration_index))


# ---------------------------------------------------------------------------
# Dispatcher.
# ---------------------------------------------------------------------------
class HookDispatcher:
    """Registers hooks and dispatches them stage-by-stage.

    The dispatcher is runtime-owned and per-agent.  Instantiate once and
    call ``register()`` for each hook (built-in, bundle-loaded, user-
    supplied).  Then call ``await dispatch(stage, payload, ctx_factory)``
    from the HookedAgent's patched method bodies.

    ``ctx_factory`` is a callable the dispatcher invokes with
    ``(manifest)`` and expects back a fully-prepared ``HookContext`` — this
    keeps construction of ``tools`` / ``state`` / ``span_id`` out of the
    dispatcher (which shouldn't know about tool registries or storage).
    """

    def __init__(self, *, site_adapter: dict | None = None, trace_id: str | None = None):
        self._by_stage: dict[Stage, list[_Registered]] = {s: [] for s in Stage}
        self._by_name: dict[str, _Registered] = {}
        self._next_index: int = 0
        self._site_adapter: dict = dict(site_adapter or {})
        self._trace_id: str = trace_id or uuid.uuid4().hex

    # Accessors -----------------------------------------------------------
    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def site_adapter(self) -> dict:
        return self._site_adapter

    def update_site_adapter(self, site_adapter: dict | None) -> None:
        self._site_adapter = dict(site_adapter or {})

    def list_hooks(self, stage: Stage | None = None) -> list[HookManifest]:
        if stage is None:
            rows = [r for rs in self._by_stage.values() for r in rs]
        else:
            rows = list(self._by_stage.get(stage, ()))
        return [r.manifest for r in sorted(rows, key=lambda r: r.sort_key)]

    # Registration --------------------------------------------------------
    def register(self, hook: Hook, *, allow_tier0: bool | None = None) -> None:
        """Register a hook.  Validates manifest + tier.

        ``allow_tier0`` bypasses the package-prefix check (used by tests).
        Production code must not set this to True.
        """
        manifest = getattr(hook, "manifest", None)
        if not isinstance(manifest, HookManifest):
            raise HookApiError(
                f"hook {type(hook).__name__!r} is missing a valid ``manifest`` attribute"
            )
        if not _is_api_version_supported(manifest.hook_api_version):
            raise IncompatibleHookApiVersion(
                f"hook {manifest.name!r} declares hook_api_version="
                f"{manifest.hook_api_version}, runtime supports {HOOK_API_VERSION}"
            )
        if manifest.tier == 0 and not (allow_tier0 is True or _caller_is_tier0_allowed()):
            raise TierViolation(
                f"hook {manifest.name!r} requested Tier-0 but caller is outside "
                f"the allowed package prefixes {_TIER0_ALLOWED_PACKAGE_PREFIXES}"
            )
        if manifest.name in self._by_name:
            raise DuplicateHookName(
                f"a hook named {manifest.name!r} is already registered"
            )
        if not hasattr(hook, "run") or not callable(hook.run):
            raise HookApiError(
                f"hook {manifest.name!r} does not expose an async run() method"
            )

        record = _Registered(
            hook=hook,
            manifest=manifest,
            registration_index=self._next_index,
        )
        self._next_index += 1
        self._by_name[manifest.name] = record
        self._by_stage[manifest.stage].append(record)
        # Keep the stage list pre-sorted so dispatch doesn't re-sort each call.
        self._by_stage[manifest.stage].sort(key=lambda r: r.sort_key)

        logger.info(
            "[HookDispatcher] registered hook %r (stage=%s, tier=%s, priority=%s)",
            manifest.name, manifest.stage.value, manifest.tier, manifest.priority,
        )

    def unregister(self, name: str) -> bool:
        """Remove a hook by name.  Returns True when removed.

        Tier-0 hooks cannot be removed by this method (use a separate,
        privileged path if that ever becomes necessary).
        """
        rec = self._by_name.get(name)
        if rec is None:
            return False
        if rec.manifest.tier == 0:
            raise TierViolation(
                f"cannot unregister Tier-0 hook {name!r}"
            )
        self._by_name.pop(name, None)
        self._by_stage[rec.manifest.stage].remove(rec)
        logger.info("[HookDispatcher] unregistered hook %r", name)
        return True

    def get_hook(self, name: str) -> Hook | None:
        """Return the registered hook instance by name, or None if missing.

        Primarily used by ``PrivacyAgent.shutdown_hooks()`` to walk hooks
        that declare external resources (subprocess lanes, etc.).
        """
        rec = self._by_name.get(name)
        return rec.hook if rec is not None else None

    # Dispatch ------------------------------------------------------------
    async def dispatch(
        self,
        stage: Stage,
        payload: Any,
        *,
        ctx_factory: Callable[[HookManifest], HookContext],
        step: int = 0,
    ) -> HookResult:
        """Run all enabled hooks for *stage*.

        Semantics:
          * Iterate in (priority, registration) order.
          * Skip hooks whose matcher misses, or whose breaker is open.
          * CONTINUE: go to next hook.
          * REPLACE: update payload, go to next hook.
          * BYPASS / DROP / HANDOFF / ESCALATE: stop; return this result.

        If no hook returns a terminal decision, the final accumulated
        (possibly Replace-updated) payload is returned as CONTINUE.
        """
        rows = [r for r in self._by_stage.get(stage, ()) if r.manifest.enabled]
        if not rows:
            return HookResult.cont()

        current_payload = payload
        now_base = time.monotonic()

        for rec in rows:
            if rec.breaker.should_skip(
                cool_down_s=rec.manifest.circuit_breaker.cool_down_s,
                now=time.monotonic(),
            ):
                logger.debug(
                    "[HookDispatcher] skipping hook %r (circuit open)",
                    rec.manifest.name,
                )
                continue

            if not _matches_payload(rec.manifest.matches, current_payload, self._site_adapter):
                continue

            ctx = ctx_factory(rec.manifest)
            t0 = time.monotonic()
            timeout_s = max(0.001, float(rec.manifest.budget.timeout_ms) / 1000.0)

            try:
                result = await asyncio.wait_for(
                    rec.hook.run(ctx, current_payload),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                rec.breaker.trip(
                    threshold=rec.manifest.circuit_breaker.failure_threshold,
                    cool_down_s=rec.manifest.circuit_breaker.cool_down_s,
                    now=time.monotonic(),
                )
                logger.warning(
                    "[HookDispatcher] hook %r timed out after %s ms (policy=%s)",
                    rec.manifest.name,
                    rec.manifest.budget.timeout_ms,
                    rec.manifest.on_timeout,
                )
                result = self._policy_to_result(rec.manifest.on_timeout, reason="timeout")
            except Exception as err:  # noqa: BLE001 — intentional broad catch
                rec.breaker.trip(
                    threshold=rec.manifest.circuit_breaker.failure_threshold,
                    cool_down_s=rec.manifest.circuit_breaker.cool_down_s,
                    now=time.monotonic(),
                )
                logger.exception(
                    "[HookDispatcher] hook %r raised %s (policy=%s)",
                    rec.manifest.name, type(err).__name__, rec.manifest.on_error,
                )
                result = self._policy_to_result(rec.manifest.on_error, reason=f"{type(err).__name__}:{err}")
            else:
                # Successful invocation — reset failure count (but keep
                # breaker state if it was already open in probe mode).
                rec.breaker.failures = 0

            duration_ms = (time.monotonic() - t0) * 1000.0
            logger.debug(
                "[HookDispatcher] hook=%r stage=%s decision=%s duration_ms=%.1f reason=%r",
                rec.manifest.name, stage.value, result.decision.value, duration_ms, result.reason,
            )

            if result.decision == Decision.CONTINUE:
                continue
            if result.decision == Decision.REPLACE:
                current_payload = result.payload if result.payload is not None else current_payload
                continue
            # Terminal decisions: BYPASS / DROP / HANDOFF / ESCALATE
            return result

        # All hooks ran without a terminal decision.
        return HookResult(decision=Decision.CONTINUE, payload=current_payload)

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _policy_to_result(policy: str, *, reason: str) -> HookResult:
        if policy == "drop":
            return HookResult.drop(reason=reason)
        if policy == "escalate_llm":
            return HookResult.escalate(reason=reason)
        # Default: fall_through behaves as Continue (safe).
        return HookResult.cont(reason=reason)


# ---------------------------------------------------------------------------
# Scoped ToolProxy — permission-gated wrapper over a tool-call callable.
# Kept in this module because the dispatcher/hook glue is what needs it; the
# actual tool registry lives elsewhere and is passed in at construction time.
# ---------------------------------------------------------------------------
class ScopedToolProxy:
    """Enforces ``permissions.tools`` globs on every call.

    Construct one per hook invocation (cheap).  The runtime supplies a
    raw ``call(name, **args)`` coroutine; this proxy checks the name against
    the hook's allowed glob list before delegating.
    """

    def __init__(
        self,
        *,
        raw_call: Callable[..., Awaitable[Any]],
        allowed_globs: Iterable[str],
        hook_name: str,
    ):
        self._raw_call = raw_call
        # Pre-compile globs as regex fragments for speed.
        self._patterns = tuple(fnmatch.translate(g) for g in allowed_globs)
        self._compiled = tuple(re.compile(p) for p in self._patterns)
        self._hook_name = hook_name

    def _is_allowed(self, name: str) -> bool:
        return any(pat.match(name) for pat in self._compiled)

    async def call(self, name: str, /, **args: Any) -> Any:
        if not self._is_allowed(name):
            raise PermissionDenied(
                f"hook {self._hook_name!r} attempted to call tool {name!r}; "
                f"not permitted by its manifest"
            )
        return await self._raw_call(name, **args)

    # Sugar: ctx.tools.feige_send_message(text=...) style.
    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        async def _invoke(**args: Any) -> Any:
            return await self.call(name, **args)

        return _invoke


# ---------------------------------------------------------------------------
# MemoryStateStore — default StateStore backend for manifest.state == "memory".
# A disk-backed variant will live in a later PR alongside the bundle loader.
# ---------------------------------------------------------------------------
class MemoryStateStore:
    """Simple in-process dict; scoped per (agent, hook_name) by construction."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def keys(self) -> list[str]:
        return list(self._data.keys())


__all__ = [
    "HookDispatcher",
    "ScopedToolProxy",
    "MemoryStateStore",
]
