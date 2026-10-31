"""A page in a store's logged-in browser, driven over CDP the way an engineer
would drive DevTools: evaluate, look, click by what is visible, type whole
strings, read the page's own network traffic.

Nothing here is site-specific. The explorer's guard rails live in ``tools``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

NETWORK_KEEP = 300


def browser_port(store_id: str = "", profile_id: str = "") -> int:
    """The debug port of the running store browser for *store_id* (or *profile_id*)."""
    from agent.ec_skills.browser_use_extension.fingerprint.fingerprint_browser import running_profiles
    from agent.ec_skills.browser_use_extension.fingerprint.profile_registry import get_profile
    for pid, br in running_profiles().items():
        port = int(getattr(br, "debug_port", 0) or 0)
        if not port:
            continue
        if profile_id and pid == profile_id:
            return port
        try:
            if store_id and str((get_profile(pid) or {}).get("store_id") or "") == store_id:
                return port
        except Exception:
            continue
    return 0


def _targets(port: int) -> List[dict]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=5) as r:
        return [t for t in json.load(r) if t.get("type") == "page"]


def _new_target(port: int, url: str) -> dict:
    req = urllib.request.Request(f"http://127.0.0.1:{port}/json/new?{urllib.parse.quote(url, safe=':/?&=%#')}",
                                 method="PUT")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


async def keep_awake(send) -> None:
    """A background tab that behaves like the front one: focused, never frozen.
    Store browsers launched before the anti-throttling flags still throttle it."""
    for method, params in (("Emulation.setFocusEmulationEnabled", {"enabled": True}),
                           ("Page.setWebLifecycleState", {"state": "active"})):
        try:
            await send(method, params)
        except Exception as exc:
            logger.debug(f"[explorer] {method} not applied: {exc}")


class PageSession:
    """One tab: ours (opened for the exploration, closed after) or a tab the run
    left on the page that failed (reused, never closed)."""

    def __init__(self, port: int, target: dict, owned: bool):
        self.port, self.target, self.owned = port, target, owned
        self.client = None
        self.network: List[Dict[str, Any]] = []

    @classmethod
    async def open(cls, port: int, start_url: str, reuse: str = "") -> "PageSession":
        """Attach to the newest tab matching *reuse* (a URL regex), else open *start_url*."""
        target, owned = None, False
        if reuse:
            rx = re.compile(reuse)
            hits = [t for t in _targets(port) if rx.search(str(t.get("url") or ""))]
            target = hits[0] if hits else None
        if target is None:
            # blank first: the network log must be on before the page's own requests
            target, owned = _new_target(port, "about:blank"), True
        page = cls(port, target, owned)
        await page._connect()
        if owned:
            await page.navigate(start_url)
        return page

    async def _connect(self) -> None:
        from cdp_use import CDPClient
        self.client = CDPClient(url=self.target["webSocketDebuggerUrl"])
        await self.client.start()
        for domain in ("Page", "Runtime", "Network"):
            await self.send(f"{domain}.enable", {})
        await keep_awake(self.send)

        def on_response(event, *_):
            r = (event or {}).get("response") or {}
            self.network.append({"id": event.get("requestId"), "url": r.get("url", ""), "status": r.get("status"),
                                 "type": event.get("type", ""), "mime": r.get("mimeType", "")})
            del self.network[:-NETWORK_KEEP]
        try:
            self.client.register.Network.responseReceived(on_response)
        except Exception as exc:              # network log is a convenience
            logger.debug(f"[explorer] no network log: {exc}")

    async def send(self, method: str, params: Optional[dict] = None, timeout: float = 30.0) -> dict:
        return await asyncio.wait_for(self.client.send_raw(method, params or {}), timeout) or {}

    async def evaluate(self, expression: str, timeout: float = 30.0) -> Any:
        # Chrome stops a script that runs past `timeout` (ms) -- a loop no longer
        # freezes the tab; an awaited promise is not cut short.
        t0 = time.monotonic()
        try:
            res = await self.send("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                                       "awaitPromise": True, "timeout": int(timeout * 1000)}, timeout + 5)
        except RuntimeError:
            if time.monotonic() - t0 < timeout - 1:
                raise
            return f"page error: the script ran longer than {timeout:.0f} s and was stopped (an endless loop?)"
        if res.get("exceptionDetails"):
            ex = res["exceptionDetails"]
            return "page error: " + str((ex.get("exception") or {}).get("description") or ex.get("text"))[:800]
        return (res.get("result") or {}).get("value")

    async def url(self) -> str:
        return str(await self.evaluate("location.href") or "")

    async def wait_loaded(self, seconds: float = 15) -> None:
        for _ in range(int(seconds * 2)):
            if await self.evaluate("document.readyState") == "complete":
                return
            await asyncio.sleep(0.5)

    async def navigate(self, url: str) -> str:
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(1.0)
        await self.wait_loaded(20)
        return await self.url()

    async def screenshot(self, selector: str = "") -> str:
        """PNG as base64: the viewport, or the element *selector* names."""
        params: Dict[str, Any] = {"format": "png"}
        if selector:
            rect = await self.evaluate("(()=>{const e=document.querySelector(%s);if(!e)return null;e.scrollIntoView({block:'center'});"
                                       "const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})()" % json.dumps(selector))
            if isinstance(rect, list) and rect[2] > 0 and rect[3] > 0:
                params["clip"] = {"x": rect[0], "y": rect[1], "width": min(rect[2], 1600), "height": min(rect[3], 2000),
                                  "scale": 1}
        res = await self.send("Page.captureScreenshot", params, 30)
        return res.get("data") or ""

    async def mouse_click(self, x: float, y: float) -> None:
        # No mouseMoved: in a background tab Chrome answers it only with the next
        # frame (~5 s); a press and release at the point is a full click.
        for kind in ("mousePressed", "mouseReleased"):
            await self.send("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left",
                                                         "clickCount": 1})

    async def insert_text(self, text: str) -> None:
        # The whole string in one event: a title box that rewrites itself while
        # typing dropped characters typed one by one (抖店 run 55).
        await self.send("Input.insertText", {"text": text})

    async def press(self, key: str) -> None:
        codes = {"Enter": 13, "Escape": 27, "Tab": 9, "Backspace": 8, "ArrowDown": 40, "ArrowUp": 38}
        code = codes.get(key, 0)
        for kind in ("keyDown", "keyUp"):
            await self.send("Input.dispatchKeyEvent", {"type": kind, "key": key, "code": key,
                                                       "windowsVirtualKeyCode": code})

    async def response_body(self, request_id: str) -> str:
        try:
            res = await self.send("Network.getResponseBody", {"requestId": request_id}, 15)
        except Exception as exc:
            return f"(body not available: {exc})"
        body = res.get("body") or ""
        if res.get("base64Encoded"):
            try:
                body = base64.b64decode(body).decode("utf-8", "replace")
            except Exception:
                return "(binary body)"
        return body

    async def close(self) -> None:
        try:
            if self.client is not None:
                await self.client.stop()
        except Exception:
            pass
        if self.owned:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/close/{self.target.get('id')}", timeout=5)
            except Exception:
                pass
