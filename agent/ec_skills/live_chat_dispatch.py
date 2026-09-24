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
import contextvars
from typing import Any, Callable

from utils.logger_helper import logger_helper as logger

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

# Keyed by site name (the bundle's ``site_plugin_name``, which is also the
# ``path`` a node's ``hookBundles`` entry refers to). This replaced a single
# last-write-wins global: with two live-chat bundles loaded, the later import
# won and the other platform's dispatch silently ran through the wrong
# bridge — wrong DOM driver, wrong selectors, wrong send path.
_BRIDGES: "dict[str, Any]" = {}

# The site whose node is currently executing. Set at browser-node entry from
# the node's ``hookBundles``; ``None`` outside a node run.
#
# ContextVars do NOT flow into ``ThreadPoolExecutor.submit`` or a raw
# ``threading.Thread`` — the placeholder sweeper and the dedicated CDP loop
# both run off-loop and will read ``None`` there. That is survivable while one
# bundle is loaded (the sole-bridge fallback answers), and is the reason the
# fallback stays until a second bundle actually ships. A raw thread that needs
# the bridge under two bundles must be handed the site at hand-off, the way
# ``_TimerEntry.store_key`` is stamped at ``arm()``.
_ACTIVE_SITE: contextvars.ContextVar = contextvars.ContextVar(
    "ecan_active_site", default=None
)


def register_runner_bridge(bridge: Any, site: str = "") -> None:
    """Register a site bundle's runner bridge under its site name.

    ``site`` defaults to the bridge's own ``site_plugin_name``, so a bundle
    that already declares one needs no call-site change.
    """
    key = str(site or getattr(bridge, "site_plugin_name", "") or "").strip()
    if not key:
        # An unnamed bridge cannot be told apart from another unnamed one.
        # Keep it — one bundle is the norm — but say so, because it is what
        # would make resolution ambiguous later.
        key = "_unnamed"
        logger.warning(
            "[live_chat] runner bridge registered without a site name; it will "
            "only resolve while it is the only bridge loaded"
        )
    _BRIDGES[key] = bridge
    logger.info(f"[live_chat] runner bridge registered for site {key!r} "
                f"(loaded: {sorted(_BRIDGES)})")


def set_active_site(site: "str | None") -> Any:
    """Mark which site's node is executing. Returns a reset token.

    A blank or whitespace-only site normalizes to ``None`` — "no active site"
    and "an active site named nothing" must not be different states.
    """
    normalized = str(site).strip() if site else ""
    return _ACTIVE_SITE.set(normalized or None)


def reset_active_site(token: Any) -> None:
    """Undo a :func:`set_active_site`. Never raises."""
    try:
        _ACTIVE_SITE.reset(token)
    except Exception:
        pass


def active_site() -> "str | None":
    """The site whose node is currently executing, if any."""
    return _ACTIVE_SITE.get()


def bridge_sites() -> "list[str]":
    """Sites with a registered bridge — introspection for diagnostics."""
    return sorted(_BRIDGES)


def runner_bridge(site: "str | None" = None) -> Any:
    """The runner bridge to use, or ``None``.

    Resolution order — explicit argument, then the executing node's site, then
    the sole registered bridge:

    * **explicit** wins, for a caller that knows which site it means;
    * **active site** is the normal path once more than one bundle exists;
    * **sole bridge** makes a single-bundle process behave exactly as the old
      global did, which is why this change is a no-op for every install today.

    With two or more bridges and no active site, this returns ``None`` and logs
    loudly rather than guessing. A missing bridge already has a defined
    meaning at all 100-odd call sites (fall back to generic behaviour), so
    degrading is safe; picking the wrong platform's DOM driver is not.
    """
    if not _BRIDGES:
        return None

    # An explicit argument means the caller knows which site it wants; giving
    # it a different one would be worse than giving it nothing.
    if site:
        found = _BRIDGES.get(str(site).strip())
        if found is None:
            logger.warning(
                f"[live_chat] no runner bridge for requested site {site!r} "
                f"(loaded: {sorted(_BRIDGES)})"
            )
        return found

    key = _ACTIVE_SITE.get() or ""
    if key:
        found = _BRIDGES.get(key)
        if found is not None:
            return found
        # The node declared a bundle that registered no bridge — an ordinary
        # hook bundle, not a live-chat one. With a single live-chat bundle
        # loaded there is still only one possible answer, and that is what the
        # old global returned, so keep returning it.
        if len(_BRIDGES) == 1:
            return next(iter(_BRIDGES.values()))
        logger.error(
            f"[live_chat] active site {key!r} has no runner bridge and "
            f"{len(_BRIDGES)} are loaded {sorted(_BRIDGES)} — refusing to guess."
        )
        return None

    if len(_BRIDGES) == 1:
        return next(iter(_BRIDGES.values()))
    logger.error(
        f"[live_chat] {len(_BRIDGES)} runner bridges loaded {sorted(_BRIDGES)} and no "
        f"active site — refusing to guess which platform this call belongs to. "
        f"The browser-automation node should declare its bundle in hookBundles; "
        f"a raw thread must be handed the site explicitly."
    )
    return None


def clear_runner_bridge(site: "str | None" = None) -> None:
    """Test helper — drop one site's bridge, or every bridge."""
    if site:
        _BRIDGES.pop(str(site).strip(), None)
    else:
        _BRIDGES.clear()


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
