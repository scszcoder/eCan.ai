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
specific site.  Feige is the first registered handler today; planned
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

    Returns False if no handler is registered (e.g. the feige_chat
    bundle wasn't loaded for this skill), True on a handler that
    accepted the request.  Extra ``**kwargs`` are forwarded to the
    handler — used today to thread the runner's worker loop into the
    Feige handler.
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
