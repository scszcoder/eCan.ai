"""Save the shipping-label PDFs a store's browser has open in tabs.

Shopify's "Print shipping label" / "Reprint shipping label" opens the label in a new tab
instead of downloading it (2026-11-18: a Shopify label was bought but no file
landed). This reads each such tab's PDF from inside the tab (so the store's session and
blob: URLs work), writes it to a folder, and closes the tab. Pages on the store's admin
site are never touched.
"""
import base64
import json
import os
import time
import urllib.request
from pathlib import Path
from typing import List

from utils.logger_helper import logger_helper as logger

_FETCH_JS = ("(async () => { const r = await fetch(location.href, {credentials: 'include'});"
             " const b = new Uint8Array(await r.arrayBuffer()); let s = '';"
             " for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));"
             " return JSON.stringify({type: r.headers.get('content-type') || '', b64: btoa(s)}); })()")


def is_candidate(url: str, admin_hosts=("admin.shopify.com", "www.etsy.com")) -> bool:
    """A tab that may hold a label PDF: not blank, not a chrome page, not the store's admin."""
    u = (url or "").lower()
    if not u or u.startswith(("about:", "chrome:", "devtools:", "chrome-extension:", "data:")):
        return False
    host = u.split("://", 1)[-1].split("/", 1)[0]
    return u.startswith("blob:") or host not in admin_hosts or u.split("?", 1)[0].endswith(".pdf")


def _port_for(profile_id: str) -> int:
    from agent.ec_skills.browser_use_extension.fingerprint import fingerprint_browser as fb
    from agent.ec_skills.browser_use_extension.fingerprint import profile_registry as pr
    prof = pr.get_profile(profile_id) or {}
    running = fb._running_browser_for(Path(prof.get("user_data_dir") or "")) if prof.get("user_data_dir") else None
    return int((running or {}).get("port") or 0)


def save_pdf_tabs(profile_id: str, dest_dir: str) -> List[str]:
    """Write every PDF open in *profile_id*'s browser tabs to *dest_dir*; returns the paths."""
    import websocket                                   # websocket-client
    port = _port_for(profile_id)
    if not port:
        logger.info(f"[pdf_tabs] no running browser for {profile_id!r}")
        return []
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10))
    saved = []
    for t in tabs:
        if t.get("type") != "page" or not is_candidate(t.get("url", "")):
            continue
        try:
            ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=60)
            try:
                ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                    "params": {"expression": _FETCH_JS, "awaitPromise": True, "returnByValue": True}}))
                while True:
                    r = json.loads(ws.recv())
                    if r.get("id") == 1:
                        break
            finally:
                ws.close()
            v = json.loads(((r.get("result") or {}).get("result") or {}).get("value") or "{}")
            data = base64.b64decode(v.get("b64") or "")
            if "pdf" not in v.get("type", "").lower() and not data.startswith(b"%PDF"):
                continue
            os.makedirs(dest_dir, exist_ok=True)
            path = os.path.join(dest_dir, f"label_tab_{int(time.time() * 1000)}.pdf")
            with open(path, "wb") as f:
                f.write(data)
            saved.append(path)
            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{t['id']}", timeout=10)
            logger.info(f"[pdf_tabs] saved {len(data)} bytes from {t.get('url', '')[:80]} -> {path}; tab closed")
        except Exception as e:
            logger.warning(f"[pdf_tabs] could not read tab {t.get('url', '')[:80]}: {e}")
    return saved
