"""Whether the titan WebSocket observer is the live dispatch path.

When it is, the DOM mutation monitor must not dispatch too, or every message
reaches the front desk twice (event_monitor reads ``is_dispatch_live``).
Sends never go over the socket on this site (the page mints the anti-bot
token), so ``ws_enabled("send")`` / ``can_send`` are always False.
"""
from __future__ import annotations

_live = False


def set_dispatch_live(live: bool) -> None:
    global _live
    _live = bool(live)


def is_dispatch_live() -> bool:
    return _live


def ws_enabled(kind: str = "") -> bool:
    return kind != "send" and _live


def can_send(customer_key: str = "") -> bool:
    return False
