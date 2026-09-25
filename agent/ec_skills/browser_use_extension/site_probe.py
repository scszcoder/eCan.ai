"""Site probe: record what a live web app says over the wire, to reverse-engineer it.

Attach to a browser that is already running a store session (any CDP endpoint)
and write, as JSON lines:

* every WebSocket the site's pages -- and their workers -- open: URL,
  handshake headers, every frame both directions (text verbatim, binary as the
  base64 CDP hands over), close;
* the site's API calls (XHR/fetch) whose URL matches the preset: method, URL,
  request body, status, response body (JSON/text, size-capped);
* one DOM snapshot of each matching page when it is first attached.

This is how the first live-chat bundle's WS reader and sender came to exist:
a corpus first, decoding offline after. The probe is site-agnostic; a site's bundle supplies
the preset (``hooks/external/<bundle>/site.py: PROBE_PRESET``) so no site name
lives here.

Cookie and authorization header VALUES are redacted (length kept). Frame and
API payloads are not -- they are the point -- so a capture holds real customer
messages: it stays on this machine, under ``runlogs/probe/``.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

_SECRET_HEADERS = {"cookie", "set-cookie", "authorization", "x-csrf-token", "anti-content",
                   "accesstoken", "access-token", "x-auth-token"}
_TEXTUAL = ("json", "text", "javascript", "xml", "protobuf", "octet-stream")


@dataclass
class ProbePreset:
    """What to watch, supplied by a site bundle."""
    name: str
    page_markers: List[str]                      # substrings of a page URL to attach to
    api_markers: List[str] = field(default_factory=list)   # substrings of API URLs to record
    api_exclude: List[str] = field(default_factory=lambda: [
        ".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".ico", ".mp4"])
    body_limit: int = 256 * 1024

    def page(self, url: str) -> bool:
        return any(m in (url or "") for m in self.page_markers)

    def api(self, url: str) -> bool:
        u = (url or "").split("?", 1)[0].lower()
        if any(u.endswith(x) for x in self.api_exclude):
            return False
        return any(m in (url or "") for m in (self.api_markers or self.page_markers))


def load_preset(bundle: str) -> ProbePreset:
    """``PROBE_PRESET`` from ``hooks/external/<bundle>/site.py``."""
    import importlib
    mod = importlib.import_module(
        f"agent.ec_skills.browser_use_extension.hooks.external.{bundle}.site")
    raw = getattr(mod, "PROBE_PRESET")
    return raw if isinstance(raw, ProbePreset) else ProbePreset(**raw)


def _redact(headers: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = {}
    for k, v in (headers or {}).items():
        out[k] = f"<redacted {len(str(v))} chars>" if k.lower() in _SECRET_HEADERS else v
    return out


_SECRET_QUERY = ("token", "sign", "ticket", "auth", "session", "cookie", "secret", "key")


def redact_url(url: str) -> str:
    """The URL with token-like query values replaced (a chat socket often carries its login)."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
    try:
        parts = urlsplit(url or "")
        if not parts.query:
            return url
        q = [(k, f"redacted-{len(v)}" if any(t in k.lower() for t in _SECRET_QUERY) else v)
             for k, v in parse_qsl(parts.query, keep_blank_values=True)]
        return urlunsplit(parts._replace(query=urlencode(q)))
    except Exception:
        return url


def default_out_dir() -> str:
    """``<appdata>/runlogs/probe`` -- where Fetch logs and support zips pick it up."""
    try:
        from config.app_info import app_info
        return os.path.join(app_info.appdata_path, "runlogs", "probe")
    except Exception:
        return os.path.join("runlogs", "probe")


def browser_ws_url(cdp_url: str) -> str:
    if cdp_url.startswith("ws"):
        return cdp_url
    with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=5) as r:
        return json.load(r)["webSocketDebuggerUrl"]


class SiteProbe:
    def __init__(self, cdp_url: str, preset: ProbePreset, out_dir: str = ""):
        out_dir = out_dir or default_out_dir()
        self.cdp_url = cdp_url
        self.preset = preset
        os.makedirs(out_dir, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.base = os.path.join(out_dir, f"{preset.name}_{stamp}")
        self.path = self.base + ".jsonl"
        self._fp = open(self.path, "a", encoding="utf-8")
        self._client = None
        self._attached: Dict[str, str] = {}        # targetId -> sessionId
        self._ws_url: Dict[str, str] = {}          # requestId -> socket URL
        self._api: Dict[str, Dict[str, Any]] = {}  # requestId -> request record
        self.stats: Counter = Counter()
        self._tasks: set = set()

    # ── output ──
    def _write(self, rec: Dict[str, Any]) -> None:
        rec["ts"] = round(time.time(), 3)
        self._fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fp.flush()

    def _spawn(self, coro) -> None:
        t = asyncio.ensure_future(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)

    # ── lifecycle ──
    async def start(self) -> None:
        from cdp_use import CDPClient
        self._client = CDPClient(url=browser_ws_url(self.cdp_url))
        await self._client.start()
        reg = self._client._event_registry
        for ev, fn in (
            ("Target.targetCreated", self._on_target),
            ("Target.targetInfoChanged", self._on_target),
            ("Target.attachedToTarget", self._on_attached),
            ("Network.webSocketCreated", self._on_ws_created),
            ("Network.webSocketWillSendHandshakeRequest", self._on_ws_handshake),
            ("Network.webSocketHandshakeResponseReceived", self._on_ws_handshake_resp),
            ("Network.webSocketFrameReceived", lambda p, s=None: self._on_frame("recv", p, s)),
            ("Network.webSocketFrameSent", lambda p, s=None: self._on_frame("sent", p, s)),
            ("Network.webSocketFrameError", self._on_ws_error),
            ("Network.webSocketClosed", self._on_ws_closed),
            ("Network.requestWillBeSent", self._on_request),
            ("Network.responseReceived", self._on_response),
            ("Network.loadingFinished", self._on_loading_finished),
        ):
            reg.register(ev, fn)
        await self._client.send_raw("Target.setDiscoverTargets", {"discover": True})
        infos = (await self._client.send_raw("Target.getTargets", {})).get("targetInfos", [])
        for info in infos:
            await self._maybe_attach(info)
        self._write({"kind": "probe_start", "preset": self.preset.name, "cdp": self.cdp_url,
                     "pages": [redact_url(i.get("url", "")) for i in infos
                               if self.preset.page(i.get("url", ""))]})
        logger.info(f"[site-probe] {self.preset.name}: attached to {len(self._attached)} target(s) -> {self.path}")

    async def stop(self) -> Dict[str, Any]:
        for t in list(self._tasks):
            t.cancel()
        try:
            if self._client:
                await self._client.stop()
        except Exception:
            pass
        self._write({"kind": "probe_stop", "stats": dict(self.stats)})
        self._fp.close()
        return summarize(self.path)

    # ── targets ──
    async def _maybe_attach(self, info: Dict[str, Any]) -> None:
        tid, ttype, url = info.get("targetId"), info.get("type"), info.get("url", "")
        if not tid or tid in self._attached:
            return
        wanted = (ttype == "page" and self.preset.page(url)) or \
                 (ttype in ("service_worker", "shared_worker") and self.preset.page(url))
        if not wanted:
            return
        # Claim it before awaiting: targetCreated and targetInfoChanged arrive
        # together for a new tab, and two attaches would log every frame twice.
        self._attached[tid] = ""
        try:
            sid = (await self._client.send_raw(
                "Target.attachToTarget", {"targetId": tid, "flatten": True})).get("sessionId")
        except Exception as exc:
            self._attached.pop(tid, None)
            self._write({"kind": "attach_failed", "target": tid, "url": url, "error": str(exc)})
            return
        if not sid:
            self._attached.pop(tid, None)
            return
        self._attached[tid] = sid
        await self._prepare_session(sid, ttype, url)
        if ttype == "page":
            self._spawn(self._snapshot_dom(sid, url))

    async def _prepare_session(self, sid: str, ttype: str, url: str) -> None:
        try:
            await self._client.send_raw("Network.enable", {"maxPostDataSize": 65536}, session_id=sid)
        except Exception as exc:
            self._write({"kind": "network_enable_failed", "type": ttype, "url": url, "error": str(exc)})
        try:
            # Dedicated workers a page starts: a chat socket often lives there.
            await self._client.send_raw("Target.setAutoAttach", {
                "autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True}, session_id=sid)
        except Exception:
            pass
        self._write({"kind": "attached", "type": ttype, "url": redact_url(url), "sid": sid})
        self.stats[f"attached_{ttype}"] += 1

    def _on_target(self, params, session_id=None):
        info = params.get("targetInfo") or {}
        self._spawn(self._maybe_attach(info))

    def _on_attached(self, params, session_id=None):
        info = params.get("targetInfo") or {}
        sid = params.get("sessionId")
        tid = info.get("targetId")
        if sid and tid and tid not in self._attached:
            self._attached[tid] = sid
            self._spawn(self._prepare_session(sid, info.get("type", ""), info.get("url", "")))

    async def _snapshot_dom(self, sid: str, url: str) -> None:
        await asyncio.sleep(3)   # let the SPA render
        try:
            r = await self._client.send_raw("Runtime.evaluate", {
                "expression": "document.documentElement.outerHTML", "returnByValue": True},
                session_id=sid)
            html = ((r.get("result") or {}).get("value")) or ""
            n = self.stats["dom_snapshots"] + 1
            path = f"{self.base}_dom{n}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"<!-- {url} -->\n{html}")
            self.stats["dom_snapshots"] = n
            self._write({"kind": "dom_snapshot", "url": url, "file": path, "bytes": len(html)})
        except Exception as exc:
            self._write({"kind": "dom_snapshot_failed", "url": url, "error": str(exc)})

    # ── websockets ──
    def _on_ws_created(self, p, s=None):
        rid = p.get("requestId", "")
        self._ws_url[rid] = redact_url(p.get("url", ""))
        self._write({"kind": "ws_created", "rid": rid, "url": self._ws_url[rid], "sid": s,
                     "initiator": (p.get("initiator") or {}).get("type")})
        self.stats["ws_created"] += 1

    def _on_ws_handshake(self, p, s=None):
        req = p.get("request") or {}
        self._write({"kind": "ws_handshake", "rid": p.get("requestId"), "url": self._ws_url.get(p.get("requestId"), ""),
                     "headers": _redact(req.get("headers"))})

    def _on_ws_handshake_resp(self, p, s=None):
        resp = p.get("response") or {}
        self._write({"kind": "ws_handshake_response", "rid": p.get("requestId"), "status": resp.get("status"),
                     "headers": _redact(resp.get("headers"))})

    def _on_frame(self, direction, p, s=None):
        resp = p.get("response") or {}
        rid = p.get("requestId", "")
        self._write({"kind": "ws_frame", "dir": direction, "rid": rid, "url": self._ws_url.get(rid, ""),
                     "opcode": resp.get("opcode"), "mask": resp.get("mask"),
                     "payload": resp.get("payloadData", ""), "sid": s})
        self.stats[f"ws_{direction}"] += 1

    def _on_ws_error(self, p, s=None):
        self._write({"kind": "ws_error", "rid": p.get("requestId"), "error": p.get("errorMessage")})

    def _on_ws_closed(self, p, s=None):
        rid = p.get("requestId", "")
        self._write({"kind": "ws_closed", "rid": rid, "url": self._ws_url.get(rid, "")})

    # ── API calls ──
    def _on_request(self, p, s=None):
        req = p.get("request") or {}
        url = req.get("url", "")
        if p.get("type") not in ("XHR", "Fetch", None) or not self.preset.api(url):
            return
        self._api[p.get("requestId", "")] = {
            "kind": "api", "method": req.get("method"), "url": redact_url(url), "sid": s,
            "request_headers": _redact(req.get("headers")), "request_body": req.get("postData"),
        }

    def _on_response(self, p, s=None):
        rec = self._api.get(p.get("requestId", ""))
        if rec is not None:
            resp = p.get("response") or {}
            rec.update(status=resp.get("status"), mime=resp.get("mimeType"),
                       response_headers=_redact(resp.get("headers")))

    def _on_loading_finished(self, p, s=None):
        rid = p.get("requestId", "")
        rec = self._api.pop(rid, None)
        if rec is not None:
            self._spawn(self._finish_api(rid, rec, s))

    async def _finish_api(self, rid: str, rec: Dict[str, Any], sid: Optional[str]) -> None:
        mime = str(rec.get("mime") or "")
        if any(k in mime for k in _TEXTUAL):
            try:
                body = await self._client.send_raw("Network.getResponseBody", {"requestId": rid},
                                                   session_id=sid)
                data = body.get("body") or ""
                if body.get("base64Encoded"):
                    rec["response_body_b64"] = data[: self.preset.body_limit]
                else:
                    rec["response_body"] = data[: self.preset.body_limit]
                rec["truncated"] = len(data) > self.preset.body_limit
            except Exception as exc:
                rec["response_body_error"] = str(exc)
        self._write(rec)
        self.stats["api"] += 1


# ── offline summary ──────────────────────────────────────────────────

def _shape(payload: str, opcode) -> str:
    """A short structural fingerprint of one frame, for grouping."""
    if opcode == 2 or opcode == "2":
        try:
            raw = base64.b64decode(payload)
            return f"binary len~{len(raw) // 64 * 64} head={raw[:4].hex()}"
        except Exception:
            return "binary (undecodable)"
    try:
        obj = json.loads(payload)
    except Exception:
        return f"text len~{len(payload) // 64 * 64}"
    if isinstance(obj, dict):
        tag = next((f"{k}={obj[k]}" for k in ("cmd", "type", "event", "op", "action", "msg_type")
                    if k in obj and isinstance(obj[k], (str, int))), "")
        return f"json{{{','.join(sorted(obj))[:120]}}} {tag}".strip()
    return f"json[{type(obj).__name__}]"


def summarize(path: str, samples: int = 2) -> Dict[str, Any]:
    """Sockets, frame shapes and API endpoints seen in one capture file."""
    sockets: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"recv": 0, "sent": 0, "shapes": Counter(),
                                                              "samples": {}})
    apis: Counter = Counter()
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == "ws_frame":
                s = sockets[r.get("url") or r.get("rid")]
                s[r["dir"]] += 1
                shape = f"{r['dir']} {_shape(r.get('payload', ''), r.get('opcode'))}"
                s["shapes"][shape] += 1
                smp = s["samples"].setdefault(shape, [])
                if len(smp) < samples:
                    smp.append(str(r.get("payload", ""))[:600])
            elif r.get("kind") == "api":
                apis[f"{r.get('method')} {str(r.get('url', '')).split('?', 1)[0]}"] += 1
    return {
        "file": path,
        "sockets": {u: {"recv": s["recv"], "sent": s["sent"],
                        "shapes": s["shapes"].most_common(25), "samples": s["samples"]}
                    for u, s in sockets.items()},
        "apis": apis.most_common(60),
    }


# ── running one from the app ─────────────────────────────────────────

def available_sites() -> List[str]:
    """Bundles that ship a probe preset (``hooks/external/<bundle>/site.py``)."""
    from pathlib import Path
    root = Path(__file__).parent / "hooks" / "external"
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and not p.name.startswith("_") and (p / "site.py").is_file())


class ProbeRunner:
    """One probe on its own thread and event loop, started and stopped from any thread."""

    def __init__(self, cdp_url: str, preset: ProbePreset, out_dir: str = ""):
        self.probe = SiteProbe(cdp_url, preset, out_dir)
        self.summary: Optional[Dict[str, Any]] = None
        self.error = ""
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._started = None
        self._thread = None

    def start(self, timeout: float = 20.0) -> None:
        import threading
        self._started = threading.Event()
        self._thread = threading.Thread(target=self._run, name=f"site-probe-{self.probe.preset.name}",
                                        daemon=True)
        self._thread.start()
        if not self._started.wait(timeout):
            raise RuntimeError("the probe did not attach in time")
        if self.error:
            raise RuntimeError(self.error)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main())
        finally:
            self._loop.close()

    async def _main(self) -> None:
        self._stop = asyncio.Event()
        try:
            await self.probe.start()
        except Exception as exc:
            self.error = f"could not attach: {exc}"
            self._started.set()
            return
        self._started.set()
        await self._stop.wait()
        self.summary = await self.probe.stop()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self, timeout: float = 20.0) -> Dict[str, Any]:
        if self._loop and self._stop and self.running:
            self._loop.call_soon_threadsafe(self._stop.set)
            self._thread.join(timeout)
        return self.summary or {"file": self.probe.path}
