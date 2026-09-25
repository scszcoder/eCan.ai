"""Standalone site probe: attach to a Chrome that is already running with a
debugging port and record the site's WebSocket + API traffic.

No eCan install and no Python needed on the target machine when built as an
exe (see the bottom of this file). Same capture format as the in-app recorder
(agent/ec_skills/browser_use_extension/site_probe.py), so the same summarize /
decode tooling reads it.

    pdd_probe.exe                         # port 9228, Pinduoduo merchant pages
    pdd_probe.exe --port 9222 --minutes 20
    pdd_probe.exe --match mms.pinduoduo.com --api pinduoduo.com,yangkeduo.com

Chrome must have been started with a debugging port AND its own data folder
(Chrome 136+ ignores the port on the default profile), e.g.

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9228 --user-data-dir=C:\\chrome_data

Output: a folder next to the exe, pdd_probe_out\\<time>.jsonl plus DOM
snapshots and a summary. It holds real customer messages; cookie and auth
header values and token-like URL parameters are redacted.
"""

import argparse
import base64
import json
import os
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websocket  # websocket-client

SECRET_HEADERS = {"cookie", "set-cookie", "authorization", "x-csrf-token", "anti-content",
                  "accesstoken", "access-token", "x-auth-token"}
SECRET_QUERY = ("token", "sign", "ticket", "auth", "session", "cookie", "secret", "key")
TEXTUAL = ("json", "text", "javascript", "xml", "protobuf", "octet-stream")
STATIC = (".js", ".css", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".woff", ".ico", ".mp4")
BODY_LIMIT = 256 * 1024


def redact_headers(h):
    return {k: (f"<redacted {len(str(v))} chars>" if k.lower() in SECRET_HEADERS else v)
            for k, v in (h or {}).items()}


_ANTI_BODY = __import__("re").compile(r'("anti_content"\s*:\s*")[^"]*(")')


def redact_body(body):
    """Request bodies carry the page's anti-bot token too (anti_content)."""
    if not body or "anti_content" not in body:
        return body
    return _ANTI_BODY.sub(lambda m: f"{m.group(1)}<redacted>{m.group(2)}", body)


# Read-only look at what the page exposes: is there a page-level fetch wrapper
# (window.__mms.fetch, as on the mms backend pages) that signs requests itself?
# Only typeof / key names are read -- nothing is called.
GLOBALS_JS = r"""(() => {
  const w = window, out = {};
  try { out.mms_type = typeof w.__mms; } catch (e) { out.mms_type = 'err:' + e; }
  try { out.mms_keys = w.__mms ? Object.keys(w.__mms).slice(0, 60) : null; } catch (e) { out.mms_keys = 'err:' + e; }
  try { out.mms_fetch_type = typeof (w.__mms && w.__mms.fetch); } catch (e) { out.mms_fetch_type = 'err:' + e; }
  try { out.mms_fetch_src = (w.__mms && typeof w.__mms.fetch === 'function') ? String(w.__mms.fetch).slice(0, 400) : null; } catch (e) {}
  try {
    out.globals = Object.getOwnPropertyNames(w)
      .filter(n => /mms|anti|titan|pdd|captcha|webpack|chat|kefu|socket/i.test(n))
      .slice(0, 120)
      .map(n => { let t; try { t = typeof w[n]; } catch (e) { t = 'err'; } return n + ':' + t; });
  } catch (e) { out.globals = 'err:' + e; }
  try { out.iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src).slice(0, 10); } catch (e) {}
  out.href = location.href.split('?')[0];
  return JSON.stringify(out);
})()"""


def redact_url(url):
    try:
        p = urlsplit(url or "")
        if not p.query:
            return url
        q = [(k, f"redacted-{len(v)}" if any(t in k.lower() for t in SECRET_QUERY) else v)
             for k, v in parse_qsl(p.query, keep_blank_values=True)]
        return urlunsplit(p._replace(query=urlencode(q)))
    except Exception:
        return url


class Probe:
    def __init__(self, port, match, api, out_dir):
        self.port, self.match, self.api = port, match, api
        os.makedirs(out_dir, exist_ok=True)
        self.base = os.path.join(out_dir, time.strftime("probe_%Y%m%d-%H%M%S"))
        self.path = self.base + ".jsonl"
        self.fp = open(self.path, "a", encoding="utf-8")
        self.lock = threading.Lock()
        self.stats = Counter()
        self.next_id = 0
        self.pending = {}          # id -> [Event, result]
        self.attached = {}         # targetId -> sessionId
        self.ws_url = {}           # requestId -> url
        self.api_req = {}          # requestId -> record
        self.stop = threading.Event()

    # ── plumbing ──
    def write(self, rec):
        rec["ts"] = round(time.time(), 3)
        with self.lock:
            self.fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self.fp.flush()

    def send(self, method, params=None, sid=None, wait=True, timeout=15):
        with self.lock:
            self.next_id += 1
            mid = self.next_id
        msg = {"id": mid, "method": method, "params": params or {}}
        if sid:
            msg["sessionId"] = sid
        slot = [threading.Event(), None]
        if wait:
            self.pending[mid] = slot
        self.ws.send(json.dumps(msg))
        if not wait:
            return None
        if not slot[0].wait(timeout):
            self.pending.pop(mid, None)
            raise TimeoutError(method)
        res = slot[1]
        if "error" in res:
            raise RuntimeError(f"{method}: {res['error']}")
        return res.get("result") or {}

    def async_call(self, fn, *args):
        threading.Thread(target=self._guard, args=(fn,) + args, daemon=True).start()

    def _guard(self, fn, *args):
        try:
            fn(*args)
        except Exception as exc:
            self.write({"kind": "probe_error", "where": fn.__name__, "error": str(exc)})

    # ── lifecycle ──
    def start(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=5) as r:
            ver = json.load(r)
        self.ws = websocket.create_connection(ver["webSocketDebuggerUrl"], timeout=None,
                                              suppress_origin=True)
        threading.Thread(target=self.reader, daemon=True).start()
        self.send("Target.setDiscoverTargets", {"discover": True})
        infos = self.send("Target.getTargets").get("targetInfos", [])
        self.write({"kind": "probe_start", "browser": ver.get("Browser"), "port": self.port,
                    "match": self.match, "pages": [redact_url(i.get("url", "")) for i in infos
                                                   if i.get("type") == "page"]})
        for info in infos:
            self.maybe_attach(info)
        return ver.get("Browser")

    def reader(self):
        while not self.stop.is_set():
            try:
                raw = self.ws.recv()
            except Exception as exc:
                if not self.stop.is_set():
                    self.write({"kind": "cdp_disconnected", "error": str(exc)})
                    print(f"\n[probe] connection to Chrome lost: {exc}")
                    self.stop.set()
                return
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if "id" in msg:
                slot = self.pending.pop(msg["id"], None)
                if slot:
                    slot[1] = msg
                    slot[0].set()
                continue
            try:
                self.on_event(msg.get("method", ""), msg.get("params") or {}, msg.get("sessionId"))
            except Exception as exc:
                self.write({"kind": "probe_error", "where": msg.get("method"), "error": str(exc)})

    # ── targets ──
    def wanted(self, url):
        return any(m in (url or "") for m in self.match)

    def maybe_attach(self, info):
        tid, ttype, url = info.get("targetId"), info.get("type"), info.get("url", "")
        if not tid or tid in self.attached:
            return
        if not (ttype in ("page", "service_worker", "shared_worker") and self.wanted(url)):
            return
        self.attached[tid] = ""
        self.async_call(self._attach, tid, ttype, url)

    def _attach(self, tid, ttype, url):
        try:
            sid = self.send("Target.attachToTarget", {"targetId": tid, "flatten": True}).get("sessionId")
        except Exception as exc:
            self.attached.pop(tid, None)
            self.write({"kind": "attach_failed", "url": redact_url(url), "error": str(exc)})
            return
        self.attached[tid] = sid
        self.prepare(sid, ttype, url)
        if ttype == "page":
            time.sleep(3)
            self.snapshot(sid, url)
            self.inspect_globals(sid, url, "after_load")
            time.sleep(25)   # the chat app loads its bundles late
            self.inspect_globals(sid, url, "after_30s")

    def _inspect_later(self, sid, url):
        time.sleep(5)
        self.inspect_globals(sid, url, "iframe")

    def prepare(self, sid, ttype, url):
        try:
            self.send("Network.enable", {"maxPostDataSize": 65536}, sid)
        except Exception as exc:
            self.write({"kind": "network_enable_failed", "type": ttype, "error": str(exc)})
        try:
            self.send("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False,
                                               "flatten": True}, sid)
        except Exception:
            pass
        self.write({"kind": "attached", "type": ttype, "url": redact_url(url), "sid": sid})
        self.stats[f"attached_{ttype}"] += 1
        print(f"[probe] watching {ttype}: {redact_url(url)[:100]}")

    def inspect_globals(self, sid, url, when):
        try:
            r = self.send("Runtime.evaluate", {"expression": GLOBALS_JS, "returnByValue": True}, sid, timeout=15)
            found = json.loads((r.get("result") or {}).get("value") or "{}")
        except Exception as exc:
            self.write({"kind": "page_globals_failed", "url": redact_url(url), "when": when, "error": str(exc)})
            return
        self.write({"kind": "page_globals", "url": redact_url(url), "when": when, **found})
        print(f"[probe] {when} {found.get('href', '')[:70]}: window.__mms={found.get('mms_type')} "
              f"__mms.fetch={found.get('mms_fetch_type')} globals={len(found.get('globals') or [])}")

    def snapshot(self, sid, url):
        try:
            r = self.send("Runtime.evaluate", {"expression": "document.documentElement.outerHTML",
                                               "returnByValue": True}, sid, timeout=30)
            html = (r.get("result") or {}).get("value") or ""
            self.stats["dom_snapshots"] += 1
            path = f"{self.base}_dom{self.stats['dom_snapshots']}.html"
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"<!-- {redact_url(url)} -->\n{html}")
            self.write({"kind": "dom_snapshot", "url": redact_url(url), "file": path, "bytes": len(html)})
        except Exception as exc:
            self.write({"kind": "dom_snapshot_failed", "error": str(exc)})

    # ── events ──
    def on_event(self, m, p, sid):
        if m in ("Target.targetCreated", "Target.targetInfoChanged"):
            self.maybe_attach(p.get("targetInfo") or {})
        elif m == "Target.attachedToTarget":
            info, s = p.get("targetInfo") or {}, p.get("sessionId")
            tid = info.get("targetId")
            if s and tid and tid not in self.attached:
                self.attached[tid] = s
                self.async_call(self.prepare, s, info.get("type", ""), info.get("url", ""))
                if info.get("type") == "iframe":
                    self.async_call(self._inspect_later, s, info.get("url", ""))
        elif m == "Network.webSocketCreated":
            rid = p.get("requestId", "")
            self.ws_url[rid] = redact_url(p.get("url", ""))
            self.stats["ws_created"] += 1
            self.write({"kind": "ws_created", "rid": rid, "url": self.ws_url[rid], "sid": sid,
                        "initiator": (p.get("initiator") or {}).get("type")})
            print(f"[probe] socket opened: {self.ws_url[rid][:100]}")
        elif m == "Network.webSocketWillSendHandshakeRequest":
            self.write({"kind": "ws_handshake", "rid": p.get("requestId"),
                        "url": self.ws_url.get(p.get("requestId"), ""),
                        "headers": redact_headers((p.get("request") or {}).get("headers"))})
        elif m == "Network.webSocketHandshakeResponseReceived":
            r = p.get("response") or {}
            self.write({"kind": "ws_handshake_response", "rid": p.get("requestId"),
                        "status": r.get("status"), "headers": redact_headers(r.get("headers"))})
        elif m in ("Network.webSocketFrameReceived", "Network.webSocketFrameSent"):
            d = "recv" if m.endswith("Received") else "sent"
            r, rid = p.get("response") or {}, p.get("requestId", "")
            self.stats[f"ws_{d}"] += 1
            self.write({"kind": "ws_frame", "dir": d, "rid": rid, "url": self.ws_url.get(rid, ""),
                        "opcode": r.get("opcode"), "mask": r.get("mask"),
                        "payload": r.get("payloadData", ""), "sid": sid})
        elif m == "Network.webSocketFrameError":
            self.write({"kind": "ws_error", "rid": p.get("requestId"), "error": p.get("errorMessage")})
        elif m == "Network.webSocketClosed":
            rid = p.get("requestId", "")
            self.write({"kind": "ws_closed", "rid": rid, "url": self.ws_url.get(rid, "")})
        elif m == "Network.requestWillBeSent":
            req, url = p.get("request") or {}, (p.get("request") or {}).get("url", "")
            base = url.split("?", 1)[0].lower()
            if p.get("type") in ("XHR", "Fetch", None) and not base.endswith(STATIC) \
                    and any(a in url for a in self.api):
                self.api_req[p.get("requestId", "")] = {
                    "kind": "api", "method": req.get("method"), "url": redact_url(url), "sid": sid,
                    "request_headers": redact_headers(req.get("headers")),
                    "request_body": redact_body(req.get("postData"))}
        elif m == "Network.responseReceived":
            rec = self.api_req.get(p.get("requestId", ""))
            if rec is not None:
                r = p.get("response") or {}
                rec.update(status=r.get("status"), mime=r.get("mimeType"),
                           response_headers=redact_headers(r.get("headers")))
        elif m == "Network.loadingFinished":
            rid = p.get("requestId", "")
            rec = self.api_req.pop(rid, None)
            if rec is not None:
                self.async_call(self.finish_api, rid, rec, sid)

    def finish_api(self, rid, rec, sid):
        if any(k in str(rec.get("mime") or "") for k in TEXTUAL):
            try:
                b = self.send("Network.getResponseBody", {"requestId": rid}, sid)
                data = b.get("body") or ""
                rec["response_body_b64" if b.get("base64Encoded") else "response_body"] = data[:BODY_LIMIT]
                rec["truncated"] = len(data) > BODY_LIMIT
            except Exception as exc:
                rec["response_body_error"] = str(exc)
        self.stats["api"] += 1
        self.write(rec)

    def close(self):
        self.stop.set()
        try:
            self.ws.close()
        except Exception:
            pass
        self.write({"kind": "probe_stop", "stats": dict(self.stats)})
        self.fp.close()


def shape(payload, opcode):
    if str(opcode) == "2":
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


def summarize(path):
    socks = defaultdict(lambda: {"recv": 0, "sent": 0, "shapes": Counter()})
    apis = Counter()
    page_globals = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("kind") == "ws_frame":
                s = socks[r.get("url") or r.get("rid")]
                s[r["dir"]] += 1
                s["shapes"][f"{r['dir']} {shape(r.get('payload', ''), r.get('opcode'))}"] += 1
            elif r.get("kind") == "api":
                apis[f"{r.get('method')} {str(r.get('url', '')).split('?', 1)[0]}"] += 1
            elif r.get("kind") == "page_globals":
                page_globals.append({k: r.get(k) for k in ("when", "href", "mms_type", "mms_fetch_type", "mms_keys")})
    return {"file": path, "page_globals": page_globals,
            "sockets": {u: {"recv": s["recv"], "sent": s["sent"], "shapes": s["shapes"].most_common(20)}
                        for u, s in socks.items()},
            "apis": apis.most_common(60)}


def main():
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Record a site's WebSocket + API traffic from a running Chrome.")
    ap.add_argument("--port", type=int, default=9228)
    ap.add_argument("--match", default="mms.pinduoduo.com",
                    help="comma-separated page URL substrings to attach to")
    ap.add_argument("--api", default="pinduoduo.com,yangkeduo.com",
                    help="comma-separated API URL substrings to record")
    ap.add_argument("--minutes", type=float, default=0, help="stop after this long (default: Ctrl+C)")
    ap.add_argument("--out", default=os.path.join(here, "pdd_probe_out"))
    a = ap.parse_args()

    probe = Probe(a.port, [x for x in a.match.split(",") if x], [x for x in a.api.split(",") if x], a.out)
    try:
        browser = probe.start()
    except Exception as exc:
        print(f"[probe] cannot reach Chrome on port {a.port}: {exc}\n"
              f"        Start Chrome with --remote-debugging-port={a.port} --user-data-dir=<a folder>, then retry.")
        input("Press Enter to exit...")
        return 1
    print(f"[probe] attached to {browser} on port {a.port}; recording to {probe.path}")
    if not probe.attached:
        print(f"[probe] no page matching {a.match!r} is open yet -- open the chat page; it is picked up automatically.")
    print("[probe] use the chat normally. Press Ctrl+C to stop.\n")
    deadline = time.time() + a.minutes * 60 if a.minutes else None
    try:
        while not probe.stop.is_set() and (deadline is None or time.time() < deadline):
            time.sleep(10)
            s = probe.stats
            print(f"  sockets={s['ws_created']} recv={s['ws_recv']} sent={s['ws_sent']} api={s['api']} "
                  f"pages={s['attached_page']} workers={s['attached_worker'] + s['attached_shared_worker'] + s['attached_service_worker']}")
    except KeyboardInterrupt:
        pass
    probe.close()
    summ = summarize(probe.path)
    with open(probe.base + "_summary.json", "w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, indent=2)
    print(f"\n[probe] saved: {probe.path}")
    for url, s in summ["sockets"].items():
        print(f"  socket {url[:90]}  recv={s['recv']} sent={s['sent']}")
        for sh, n in s["shapes"][:6]:
            print(f"      {n:5d}  {sh[:110]}")
    print(f"  API endpoints: {len(summ['apis'])}")
    for g in summ["page_globals"]:
        print(f"  page {g.get('when')}: {str(g.get('href'))[:70]}  __mms={g.get('mms_type')} "
              f"__mms.fetch={g.get('mms_fetch_type')}")
    print(f"\nSend the whole folder: {a.out}")
    if getattr(sys, "frozen", False):
        input("Press Enter to exit...")
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Build (dev machine):
#   python -m PyInstaller --onefile --console --name pdd_probe scripts/site_probe_standalone.py
