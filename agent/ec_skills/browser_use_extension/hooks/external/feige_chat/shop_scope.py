"""Which Feige shop (store login) a piece of work belongs to.

Several Feige shops can run in one process, each in its own Chrome. A shop is
identified by its browser: the profile directory when the browser has one (it
survives a browser restart on a new CDP port), else the CDP endpoint
(``host:port``). Every front desk, WS observer and send for a shop works
through that browser, so any of them can name the shop from the
``browser_session`` it already holds.

Per-shop state in the bundle follows one rule (see ``ws_session``): the FIRST
shop keeps the existing module-level state, so a process running one shop
behaves exactly as before; every other shop gets state of its own.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


def _url_key(url: str) -> str:
    url = str(url or "").strip()
    if not url:
        return ""
    try:
        p = urlparse(url if "://" in url else f"http://{url}")
        host = (p.hostname or "").lower()
        if host in ("localhost", "::1"):
            host = "127.0.0.1"
        return f"{host}:{p.port}" if p.port else host
    except Exception:
        return url.lower()


def shop_key_of(browser_session_or_key) -> str:
    """The shop key of a browser session (or a key/URL passed through), or ""."""
    s = browser_session_or_key
    if s is None:
        return ""
    if isinstance(s, str):
        return s if s.startswith("profile:") else _url_key(s)
    bp = getattr(s, "browser_profile", None)
    udd = getattr(bp, "user_data_dir", None) if bp is not None else None
    if udd:
        try:
            return "profile:" + os.path.normcase(os.path.abspath(str(udd)))
        except Exception:
            return "profile:" + str(udd)
    url = getattr(s, "cdp_url", None) or (getattr(bp, "cdp_url", None) if bp is not None else None)
    return _url_key(url)
