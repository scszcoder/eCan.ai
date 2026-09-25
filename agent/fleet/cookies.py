"""Cookies in and out of a running browser, over CDP.

A Chromium cookie database is encrypted with a key bound to the OS account
(DPAPI on Windows), so copied to another machine it reads as EMPTY. Cookies
therefore travel as data: read out of the running browser on the source,
written back into the running browser on the receiver.
"""

from __future__ import annotations

import itertools
import json
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

from utils.logger_helper import logger_helper as logger

PENDING_FILE = ".ecan_pending_cookies.json"

# CookieParam fields Storage.setCookies accepts; the rest of a Cookie
# (size, session, ...) is derived by the browser.
_PARAM_FIELDS = ("name", "value", "domain", "path", "secure", "httpOnly", "sameSite",
                 "expires", "priority", "sameParty", "sourceScheme", "sourcePort", "partitionKey")


def _browser_ws(cdp_url: str) -> str:
    with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=5) as r:
        return json.load(r)["webSocketDebuggerUrl"]


def _cdp(cdp_url: str, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
    import websocket
    ws = websocket.create_connection(_browser_ws(cdp_url), timeout=30, suppress_origin=True)
    try:
        ws.send(json.dumps({"id": 1, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(ws.recv())
            if msg.get("id") == 1:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result") or {}
    finally:
        ws.close()


def get_cookies(cdp_url: str) -> List[Dict[str, Any]]:
    """Every cookie of the browser at *cdp_url*, as CookieParams."""
    cookies = _cdp(cdp_url, "Storage.getCookies").get("cookies") or []
    out = []
    for c in cookies:
        p = {k: c[k] for k in _PARAM_FIELDS if k in c}
        if c.get("session") or p.get("expires", 0) in (-1, 0):
            p.pop("expires", None)          # a session cookie has no expiry
        out.append(p)
    return out


def set_cookies(cdp_url: str, cookies: List[Dict[str, Any]], batch: int = 200) -> int:
    it = iter(cookies)
    n = 0
    while True:
        part = list(itertools.islice(it, batch))
        if not part:
            return n
        _cdp(cdp_url, "Storage.setCookies", {"cookies": part})
        n += len(part)


def apply_pending(user_data_dir: str, cdp_url: str) -> int:
    """Write cookies that arrived with a moved profile, once, at its first launch.

    The file is removed only after the browser accepted them, so a failed
    attempt is retried at the next launch instead of silently losing the login.
    """
    path = Path(user_data_dir) / PENDING_FILE
    if not path.is_file():
        return 0
    try:
        cookies = json.loads(path.read_text(encoding="utf-8"))
        n = set_cookies(cdp_url, cookies if isinstance(cookies, list) else [])
    except Exception as exc:
        logger.error(f"[fleet] could not restore the moved login's cookies ({exc}); "
                     f"will retry at the next launch")
        return 0
    try:
        os.remove(path)
    except OSError:
        pass
    logger.info(f"[fleet] restored {n} cookie(s) of a moved login")
    return n
