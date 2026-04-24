"""
Hooks package — plugin surface for the HookedAgent (a.k.a. PrivacyAgent).

Subpackages:
    builtin/   — Tier-0 hooks that ship with the app.  These cannot be
                 disabled or re-registered by third-party code.

Public symbols are re-exported from ``hook_api`` for convenience so plugin
authors can write::

    from agent.ec_skills.browser_use_extension.hooks import (
        Hook, HookManifest, HookResult, Stage, Decision,
    )
"""
from __future__ import annotations

from ..hook_api import (  # noqa: F401
    HOOK_API_VERSION,
    BypassAction,
    Budget,
    CircuitBreakerConfig,
    Decision,
    DuplicateHookName,
    Hook,
    HookApiError,
    HookContext,
    HookManifest,
    HookResult,
    IncompatibleHookApiVersion,
    PermissionDenied,
    Permissions,
    Stage,
    StateStore,
    Tier,
    TierViolation,
    ToolProxy,
)

__all__ = [
    "HOOK_API_VERSION",
    "BypassAction",
    "Budget",
    "CircuitBreakerConfig",
    "Decision",
    "DuplicateHookName",
    "Hook",
    "HookApiError",
    "HookContext",
    "HookManifest",
    "HookResult",
    "IncompatibleHookApiVersion",
    "PermissionDenied",
    "Permissions",
    "Stage",
    "StateStore",
    "Tier",
    "TierViolation",
    "ToolProxy",
]
