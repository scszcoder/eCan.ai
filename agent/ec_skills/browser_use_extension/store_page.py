"""Run a READ request inside a store's own logged-in chat page.

The store browsers eCan launched (fingerprint_browser.running_profiles) already
hold the merchant's login; the platform's back-office API answers the page's
own requests. A tool that needs store data (the buyer's orders, the product
list) evaluates one fetch() in that page over the Chrome DevTools Protocol --
no navigation, no clicks, nothing changes on screen. Callers pass read
requests only.
"""
from __future__ import annotations

import asyncio
import json
import re
import urllib.request
from typing import Any, Dict, List

STORE_TABS: Dict[str, re.Pattern] = {
    # the 飞鸽 workstation (not eCan's own #ecan_det detection tab)
    "douyin": re.compile(r"^https://im\.jinritemai\.com/pc_seller_v2/main/workspace(?!.*#ecan_det)"),
    "pdd": re.compile(r"^https://mms\.pinduoduo\.com/chat-merchant"),
}
ALIASES = {
    "douyin": ("douyin", "feige", "抖店", "飞鸽", "doudian", "jinritemai"),
    "pdd": ("pdd", "pinduoduo", "拼多多"),
}


def platform_of(name: str) -> str:
    n = str(name or "").strip().lower()
    for key, names in ALIASES.items():
        if n == key or any(a.lower() in n for a in names):
            return key
    return ""


def store_tabs(platform: str) -> List[Dict[str, str]]:
    """One chat tab per store browser of *platform* that this app launched:
    [{profile, store_id, ws}] (store_id = the eCan store the profile logs in to)."""
    from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser import running_profiles
    from agent.ec_skills.browser_use_extension.fingerprint.profile_registry import get_profile
    tabs = []
    for pid, br in running_profiles().items():
        port = getattr(br, "debug_port", 0)
        if not port:
            continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
                targets = json.load(r)
        except Exception:
            continue
        # The plain chat tab, else eCan's detection tab on the same signed-in page
        # (a read works from either; 2026-10-23 KEN had only the detection tab left).
        pages = [t for t in targets if t.get("type") == "page"]
        pages = sorted(pages, key=lambda t: "#ecan_det" in str(t.get("url") or ""))
        for t in pages:
            url = str(t.get("url") or "").replace("#ecan_det", "")
            if STORE_TABS[platform].search(url):
                try:
                    store_id = str((get_profile(pid) or {}).get("store_id") or "")
                except Exception:
                    store_id = ""
                tabs.append({"profile": pid, "store_id": store_id, "ws": t.get("webSocketDebuggerUrl", "")})
                break
    return tabs


async def evaluate(ws_url: str, expression: str, timeout: float = 20.0) -> Any:
    """Evaluate *expression* (returning a JSON string, possibly via a Promise) in
    the tab; returns the parsed value."""
    from cdp_use import CDPClient
    client = CDPClient(url=ws_url)
    await client.start()
    try:
        res = await asyncio.wait_for(client.send_raw("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True}), timeout)
        val = ((res or {}).get("result") or {}).get("value")
        if val is None:
            raise RuntimeError(str(((res or {}).get("exceptionDetails") or {}).get("text") or "no result"))
        return json.loads(val)
    finally:
        try:
            await client.stop()
        except Exception:
            pass


_marked: set = set()


def _profile_for_cdp(cdp_url: str) -> str:
    """The registry profile whose browser listens on *cdp_url*'s port, or ""."""
    m = re.search(r":(\d+)", str(cdp_url or "").split("//", 1)[-1])
    if not m:
        return ""
    from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser import running_profiles
    for pid, br in running_profiles().items():
        if str(getattr(br, "debug_port", "")) == m.group(1):
            return pid
    return ""


def note_signed_in(profile_id: str = "", cdp_url: str = "", proof: str = "") -> None:
    """The store's page just proved its seller session works (its chat socket
    delivers, or a back-office read succeeded): mark the profile signed in, so
    Fast Deploy / the profile list stop asking for a sign-in nobody needs.
    Once per browser per run; never raises."""
    key = profile_id or cdp_url
    if not key or key in _marked:
        return
    _marked.add(key)
    try:
        from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as reg
        pid = profile_id or _profile_for_cdp(cdp_url)
        if pid and reg.login_state(pid).get("state") != reg.LOGIN_OK:
            reg.set_login_state(pid, reg.LOGIN_OK, f"seen working: {proof}"[:200])
    except Exception:
        pass
