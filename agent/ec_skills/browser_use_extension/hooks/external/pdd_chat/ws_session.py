"""Whether the titan WebSocket observer is the live dispatch path.

When it is, the DOM mutation monitor must not dispatch too, or every message
reaches the front desk twice (event_monitor reads ``is_dispatch_live``).
Sends never go over the socket on this site (the page mints the anti-bot
token), so ``ws_enabled("send")`` / ``can_send`` are always False.
"""
from __future__ import annotations

_live = False
# Several stores in one process: whose socket is live, per store (its browser).
_live_by_store: dict = {}


def _store(shop) -> str:
    from .typing_lock import store_key_of
    return store_key_of(shop)


def set_dispatch_live(live: bool, shop=None) -> None:
    global _live
    if shop is not None:
        _live_by_store[_store(shop)] = bool(live)
        _live = any(_live_by_store.values())
    else:
        _live = bool(live)


def is_dispatch_live(shop=None) -> bool:
    """*shop* (its browser session): whether THAT store's socket carries dispatch --
    another store's live socket must not silence this store's page monitor."""
    if shop is not None and _live_by_store:
        return bool(_live_by_store.get(_store(shop)))
    return _live


def ws_enabled(kind: str = "") -> bool:
    return kind != "send" and _live


def can_send(customer_key: str = "", shop=None) -> bool:
    return False
