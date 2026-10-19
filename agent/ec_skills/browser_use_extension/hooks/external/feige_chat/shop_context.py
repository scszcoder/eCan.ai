"""Which shop the current work is for, and per-customer records kept per shop.

Several Feige shops can run in one process (one front desk per store). A
buyer is identified by name, and the same buyer can talk to two of the
seller's stores -- the per-customer records (recent messages, recent agent
replies, last dispatched msg id, ...) were keyed by name alone, so one store's
conversation leaked into the other's Q&A context (2026-10-19: store 二号's
牙膏 question was answered "这边主营童装" with store 三号's replies in its history).

``ShopScopedDict`` keys an entry by (current shop, customer) for every shop but
the first, which keeps plain keys -- a single-store process is unchanged. The
current shop is a context variable set where the shop is known: the front-desk
dispatch (front_desk.before_run_hook / route_inbound_customer_ws), the reply
send (site_tools.feige_send_message) and the runner's direct delivery (via the
runner bridge). Unset means the first shop, as before.
"""
from __future__ import annotations

import contextvars
from typing import Any

_CURRENT_SHOP: contextvars.ContextVar[str] = contextvars.ContextVar("feige_current_shop", default="")
_SEP = "\x1f"


def set_current_shop(shop: str) -> Any:
    """Enter *shop* (a shop key, see shop_scope). Returns a reset token."""
    return _CURRENT_SHOP.set(str(shop or ""))


def reset_current_shop(token: Any) -> None:
    if token is not None:
        try:
            _CURRENT_SHOP.reset(token)
        except Exception:
            pass


def current_shop() -> str:
    return _CURRENT_SHOP.get()


def _prefix() -> str:
    shop = _CURRENT_SHOP.get()
    if not shop:
        return ""
    try:
        from .ws_session import _k
        return _k(shop)          # "" for the first shop
    except Exception:
        return ""


def scoped_key(key: Any) -> Any:
    p = _prefix()
    return f"{p}{_SEP}{key}" if p and isinstance(key, str) else key


class ShopScopedDict(dict):
    """A dict whose keyed access is per current shop (see module docstring).
    Iteration, len() and clear() see the raw entries of every shop."""

    def __getitem__(self, key):
        return super().__getitem__(scoped_key(key))

    def __setitem__(self, key, value):
        super().__setitem__(scoped_key(key), value)

    def __delitem__(self, key):
        super().__delitem__(scoped_key(key))

    def __contains__(self, key):
        return super().__contains__(scoped_key(key))

    def get(self, key, default=None):
        return super().get(scoped_key(key), default)

    def setdefault(self, key, default=None):
        return super().setdefault(scoped_key(key), default)

    def pop(self, key, *default):
        return super().pop(scoped_key(key), *default)
