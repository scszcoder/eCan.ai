"""Lightweight registry for site-specific live-chat handlers.

Sits between the generic runner.py and the per-site bundles in
``hooks/external/<site>/``.  Sites register handlers for specific
live-chat stages; runner code looks up by stage and calls the
registered handler.

Kept deliberately minimal — no HookContext / HookManifest / budgets /
circuit breakers — until multiple sites force the need.  The
``hook_api.py`` Stage enum + payload dataclasses are the canonical
names; this module just stores callables keyed by stage.

Added in mt051C (2026-05-28) so the runner can fire
``Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED`` without knowing about any
specific site.  The Douyin live-chat bundle is the first registered
handler today; planned
e-commerce live-chat integrations (Shopify, WeChat, etc.) will each
register their own handler the same way.
"""
from typing import Any, Callable

from agent.ec_skills.browser_use_extension.hook_api import (
    LiveChatPlaceholderRequest,
    Stage,
)

# Handler signature: receives the request + dispatcher-side keyword
# context (e.g. worker_loop).  Returns True on a successful schedule
# / synchronous handle, False on no-op or failure.  Sites are free to
# accept additional kwargs; the dispatcher passes through whatever
# the runner provides.
PlaceholderHandler = Callable[..., bool]

_REGISTRY: dict[Stage, PlaceholderHandler] = {}


def register_placeholder_handler(handler: PlaceholderHandler) -> None:
    """Register the site-specific placeholder handler.

    Only one handler per process — registering replaces any prior
    handler (last-write-wins).  Multi-site setups should coordinate
    which bundle owns the registration on import (typically the only
    one whose site is currently active).
    """
    _REGISTRY[Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED] = handler


def dispatch_placeholder(
    req: LiveChatPlaceholderRequest, **kwargs: Any
) -> bool:
    """Fire the registered placeholder handler.

    Returns False if no handler is registered (e.g. no live-chat
    bundle was loaded for this skill), True on a handler that
    accepted the request.  Extra ``**kwargs`` are forwarded to the
    handler — used today to thread the runner's worker loop into the
    site handler.
    """
    handler = _REGISTRY.get(Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED)
    if handler is None:
        return False
    return handler(req, **kwargs)


def has_placeholder_handler() -> bool:
    """True iff a placeholder handler has been registered."""
    return Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED in _REGISTRY


def clear_placeholder_handler() -> None:
    """Test helper — drop any registered handler.  Production code
    should not call this."""
    _REGISTRY.pop(Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED, None)


# ---------------------------------------------------------------------------
# Runner bridge (2026-08-01)
#
# Generalization of the mt051C placeholder registration: the runner's
# direct-delivery / shutdown / dedup paths need a couple dozen
# site-specific capabilities (trace ledger, delivery durability,
# tab-pool, typing-lock, DOM scrape, tunables, ...).  Instead of the
# runner lazy-importing the site bundle's modules directly (which put
# business-specific imports all over ``ec_tasks/runner.py``), the
# active live-chat bundle registers ONE bridge object here at package
# import and the runner resolves capabilities through it by generic
# attribute names.
#
# Contract: the bridge is any object exposing the attributes the
# runner asks for (see the active bundle's ``runner_bridge.py``
# for the reference implementation and the attribute inventory).  A
# missing bridge (bundle not loaded — i.e. no live-chat skill running)
# must degrade to the same no-op behaviour as a failed lazy import did
# before: runner call sites guard with ``bridge = runner_bridge()`` /
# ``if bridge is None: <fallback>``.
# ---------------------------------------------------------------------------

_RUNNER_BRIDGE: Any = None


def register_runner_bridge(bridge: Any) -> None:
    """Register the active site bundle's runner bridge (last-write-wins,
    same single-site convention as ``register_placeholder_handler``)."""
    global _RUNNER_BRIDGE
    _RUNNER_BRIDGE = bridge


def runner_bridge() -> Any:
    """Return the registered runner bridge, or None when no live-chat
    bundle has been loaded in this process."""
    return _RUNNER_BRIDGE


def clear_runner_bridge() -> None:
    """Test helper — drop the registered bridge."""
    global _RUNNER_BRIDGE
    _RUNNER_BRIDGE = None


def live_chat_env(name: str) -> "str | None":
    """Read a live-chat tunable env var by its platform-neutral name.

    Falls back to any legacy site-branded alias of the same knob (e.g.
    a bundle's historical ``ECAN_<SITE>_X`` spelling of
    ``ECAN_LIVE_CHAT_X``) so existing ops run-scripts keep working
    while platform code stays site-agnostic.  Shared twin of
    ``ec_tasks.runner._live_chat_env`` for the other platform modules.
    """
    import os
    import re
    val = os.getenv(name)
    if val is not None:
        return val
    m = re.match(r"^(DIRECT|ECAN)_LIVE_CHAT_([A-Z0-9_]+)$", name)
    if not m:
        return None
    alias_pat = re.compile(rf"^{m.group(1)}_[A-Z0-9]+_{re.escape(m.group(2))}$")
    for key, value in os.environ.items():
        if key != name and alias_pat.match(key):
            return value
    return None
