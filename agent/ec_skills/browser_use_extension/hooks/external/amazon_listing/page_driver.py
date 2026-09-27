"""Page primitives for the Amazon Seller Central actions (browser-use 0.12 + CDP).

The actions were ported from vibe-seller's browser helpers, which ran on a
scripting harness (``new_tab``, ``js``, ``cdp``, ``click_at_xy``,
``drain_events``). This is that small surface on top of our BrowserSession, so
the ported logic reads the same.
"""
import asyncio
import json
import os
from typing import Any, Optional

# Walk the DOM through open shadow roots (Seller Central is built from kat-*
# web components, whose buttons and inputs live inside shadow DOM).
WALK = (
    'function* w(r){for(const e of r.querySelectorAll("*")){yield e;'
    'if(e.shadowRoot) yield* w(e.shadowRoot);}}'
)


class Page:
    def __init__(self, browser_session, cdp_session):
        self.session = browser_session
        self.cdp = cdp_session

    @classmethod
    async def open(cls, browser_session, url: str) -> "Page":
        """Open *url* in a new tab and bind to it (their ``new_tab``)."""
        await browser_session.navigate_to(url, new_tab=True)
        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
        return cls(browser_session, cdp_session)

    async def send(self, method: str, **params) -> Any:
        """Raw CDP on this page (their ``cdp('Domain.method', ...)``)."""
        domain, name = method.split('.', 1)
        fn = getattr(getattr(self.cdp.cdp_client.send, domain), name)
        return await fn(params=params or None, session_id=self.cdp.session_id)

    async def js(self, body: str) -> Any:
        """Evaluate a function body that ``return``s a value (their ``js``)."""
        res = await self.send('Runtime.evaluate',
                              expression=f'(function(){{{body}}})()',
                              returnByValue=True, awaitPromise=True)
        return ((res or {}).get('result') or {}).get('value')

    async def js_json(self, body: str) -> Any:
        raw = await self.js(body)
        if isinstance(raw, str) and raw[:1] in '[{':
            try:
                return json.loads(raw)
            except Exception:
                return raw
        return raw

    async def click(self, x: float, y: float) -> None:
        """A TRUSTED click (kat components ignore a JS ``.click()``)."""
        for ev in ('mouseMoved', 'mousePressed', 'mouseReleased'):
            params = {'type': ev, 'x': x, 'y': y}
            if ev != 'mouseMoved':
                params.update(button='left', clickCount=1)
            await self.send('Input.dispatchMouseEvent', **params)

    async def tall_viewport(self, height: int) -> None:
        """Keep low controls on-screen for coordinate clicks."""
        await self.send('Emulation.setDeviceMetricsOverride', width=1920, height=height,
                        deviceScaleFactor=1, mobile=False)

    async def reset_viewport(self) -> None:
        try:
            await self.send('Emulation.clearDeviceMetricsOverride')
        except Exception:
            pass

    async def body_text(self, limit: int = 1500) -> str:
        try:
            return str(await self.js('return (document.body.innerText||"").slice(0,%d);' % limit) or '')
        except Exception:
            return ''


class FileChooser:
    """Catch the real <input type=file> behind a decoy upload button.

    With ``Page.setInterceptFileChooserDialog`` on, a trusted click opens no
    OS dialog; Chrome reports ``Page.fileChooserOpened`` with the real input's
    ``backendNodeId``. One handler per CDP method, so chain the existing one.
    """
    METHOD = 'Page.fileChooserOpened'

    def __init__(self, page: Page):
        self.page = page
        self.node: Optional[int] = None
        self._prev = None

    async def __aenter__(self):
        reg = self.page.cdp.cdp_client._event_registry
        self._prev = reg._handlers.get(self.METHOD)

        def on_open(params, session_id=None):
            if session_id in (None, self.page.cdp.session_id):
                self.node = (params or {}).get('backendNodeId')
            if self._prev is not None:
                try:
                    self._prev(params, session_id)
                except Exception:
                    pass

        reg.register(self.METHOD, on_open)
        await self.page.send('Page.enable')
        await self.page.send('Page.setInterceptFileChooserDialog', enabled=True)
        return self

    async def wait(self, timeout_s: float = 6.0) -> Optional[int]:
        waited = 0.0
        while self.node is None and waited < timeout_s:
            await asyncio.sleep(0.25)
            waited += 0.25
        return self.node

    async def __aexit__(self, *exc):
        try:
            await self.page.send('Page.setInterceptFileChooserDialog', enabled=False)
        except Exception:
            pass
        reg = self.page.cdp.cdp_client._event_registry
        if self._prev is not None:
            reg.register(self.METHOD, self._prev)
        else:
            reg.unregister(self.METHOD)
        return False


def downloads_dir(browser_session, override: str = '') -> str:
    """Where this browser saves downloads (the node's downloads path)."""
    if override:
        return os.path.expanduser(override)
    profile = getattr(browser_session, 'browser_profile', None)
    return str(getattr(profile, 'downloads_path', None) or '')


def newest(dirpath: str, suffixes, after_ts: float) -> Optional[str]:
    try:
        cands = [os.path.join(dirpath, f) for f in os.listdir(dirpath)
                 if f.lower().endswith(tuple(suffixes))]
    except OSError:
        return None
    cands = [p for p in cands if os.path.getmtime(p) > after_ts]
    return max(cands, key=os.path.getmtime) if cands else None
