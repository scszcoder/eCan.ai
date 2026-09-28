"""Standalone site probe: attach to a Chrome (or a Chromium-based desktop app)
with a debugging port and record the site's WebSocket + API traffic.

No eCan install and no Python needed on the target machine when built as an
exe (see the bottom of this file). Same capture format as the in-app recorder
(agent/ec_skills/browser_use_extension/site_probe.py), so the same summarize /
decode tooling reads it.

    pdd_probe.exe                         # port 9228, Pinduoduo merchant pages
    pdd_probe.exe --port 9222 --minutes 20
    pdd_probe.exe --match mms.pinduoduo.com --api pinduoduo.com,yangkeduo.com

    qianniu_probe.exe                     # 千牛 / 淘宝店铺: asks how to open it
    qianniu_probe.exe --launch chrome     # own Chrome, opens 千牛网页版 -- just log in
    qianniu_probe.exe --launch app        # restart the 千牛 desktop client with a debug port

The site preset (``--site``) defaults from the exe's name (qianniu_probe.exe ->
qianniu), so the customer only double-clicks.

Chrome must have been started with a debugging port AND its own data folder
(Chrome 136+ ignores the port on the default profile), e.g.

    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" --remote-debugging-port=9228 --user-data-dir=C:\\chrome_data

Output: a folder next to the exe, pdd_probe_out\\<time>.jsonl plus DOM
snapshots and a summary. It holds real customer messages; cookie and auth
header values and token-like URL parameters are redacted.
"""

import argparse
import base64
import csv
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import websocket  # websocket-client

SECRET_HEADERS = {"cookie", "set-cookie", "authorization", "x-csrf-token", "anti-content",
                  "accesstoken", "access-token", "x-auth-token",
                  # Taobao / mtop request signing
                  "x-sign", "x-mini-wua", "x-sgext", "x-umt", "bx-ua", "bx-umidtoken", "x-xsrf-token"}
SECRET_QUERY = ("token", "sign", "ticket", "auth", "session", "cookie", "secret", "key",
                "_tk", "wua", "umt", "sgext", "umid")
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


SITES = {
    "pdd": {
        "match": "mms.pinduoduo.com",
        "api": "pinduoduo.com,yangkeduo.com",
        "globals": r"mms|anti|titan|pdd|captcha|webpack|chat|kefu|socket",
        "start_url": "https://mms.pinduoduo.com/chat-merchant/index.html",
        "app_exes": [],
        "ignore_ws": [],
    },
    # 千牛 (Qianniu) and 淘宝/天猫 seller pages: the web workbench, 卖家中心 and the
    # 旺旺 IM. Broad on purpose until a capture shows which hosts carry the chat;
    # alicdn.com is here for the workers/iframes the IM runs in.
    "qianniu": {
        "match": "taobao.com,tmall.com,alicdn.com,alibaba.com,1688.com,dingtalk.com",
        "api": "taobao.com,tmall.com,alibaba.com,alibaba-inc.com,dingtalk.com,alipay.com",
        "globals": r"mtop|^lib$|wangwang|^ww|^im|imsdk|aliim|tbim|accs|^qn|qianniu|niuyou|wkt|socket|chat|kefu|aplus|goldlog|webpack|dingtalk|lwp",
        "start_url": "https://myseller.taobao.com/home.htm",
        # analytics beacons (aplus/goldlog): a frame every few seconds, device ids, no chat
        "ignore_ws": ["mmstat.com"],
        "app_exes": [r"C:\Program Files (x86)\AliWorkBench\AliWorkBench.exe",
                     r"C:\Program Files\AliWorkBench\AliWorkBench.exe",
                     r"D:\Program Files (x86)\AliWorkBench\AliWorkBench.exe",
                     r"D:\AliWorkBench\AliWorkBench.exe"],
        "app_names": ["aliworkbench", "qianniu", "千牛"],
    },
}


# Read-only look at what the page exposes: page-level fetch/signing wrappers
# (window.__mms.fetch on the PDD backend; window.lib.mtop on Taobao pages) and
# globals whose names match the site's pattern. Only typeof / key names are
# read -- nothing is called.
GLOBALS_JS_TEMPLATE = r"""(() => {
  const w = window, out = {};
  try { out.mms_type = typeof w.__mms; } catch (e) { out.mms_type = 'err:' + e; }
  try { out.mms_keys = w.__mms ? Object.keys(w.__mms).slice(0, 60) : null; } catch (e) { out.mms_keys = 'err:' + e; }
  try { out.mms_fetch_type = typeof (w.__mms && w.__mms.fetch); } catch (e) { out.mms_fetch_type = 'err:' + e; }
  try { out.mms_fetch_src = (w.__mms && typeof w.__mms.fetch === 'function') ? String(w.__mms.fetch).slice(0, 400) : null; } catch (e) {}
  try { out.mtop_type = typeof (w.lib && w.lib.mtop); } catch (e) {}
  try { out.mtop_keys = (w.lib && w.lib.mtop) ? Object.keys(w.lib.mtop).slice(0, 40) : null; } catch (e) {}
  try {
    out.globals = Object.getOwnPropertyNames(w)
      .filter(n => /__GLOBALS_RE__/i.test(n))
      .slice(0, 120)
      .map(n => { let t; try { t = typeof w[n]; } catch (e) { t = 'err'; } return n + ':' + t; });
  } catch (e) { out.globals = 'err:' + e; }
  try { out.iframes = Array.from(document.querySelectorAll('iframe')).map(f => f.src).slice(0, 10); } catch (e) {}
  out.href = location.href.split('?')[0];
  return JSON.stringify(out);
})()"""
GLOBALS_JS = GLOBALS_JS_TEMPLATE.replace("__GLOBALS_RE__", SITES["pdd"]["globals"])


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
    def __init__(self, port, match, api, out_dir, globals_re=None, ignore_ws=()):
        self.port, self.match, self.api = port, match, api
        self.ignore_ws = tuple(ignore_ws or ())
        self.globals_js = GLOBALS_JS_TEMPLATE.replace("__GLOBALS_RE__", globals_re or SITES["pdd"]["globals"])
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
        if not self.match:  # desktop-app mode: the whole app is the site
            return not (url or "").startswith(("devtools://", "chrome-extension://"))
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
            r = self.send("Runtime.evaluate", {"expression": self.globals_js, "returnByValue": True}, sid, timeout=15)
            found = json.loads((r.get("result") or {}).get("value") or "{}")
        except Exception as exc:
            self.write({"kind": "page_globals_failed", "url": redact_url(url), "when": when, "error": str(exc)})
            return
        self.write({"kind": "page_globals", "url": redact_url(url), "when": when, **found})
        print(f"[probe] {when} {found.get('href', '')[:70]}: __mms={found.get('mms_type')} "
              f"lib.mtop={found.get('mtop_type')} globals={len(found.get('globals') or [])}")

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
            if self.ignore_ws and any(x in self.ws_url.get(rid, "") for x in self.ignore_ws):
                self.stats["ws_ignored"] += 1
                return
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
                page_globals.append({k: r.get(k) for k in ("when", "href", "mms_type", "mms_fetch_type",
                                                           "mms_keys", "mtop_type", "mtop_keys")})
    return {"file": path, "page_globals": page_globals,
            "sockets": {u: {"recv": s["recv"], "sent": s["sent"], "shapes": s["shapes"].most_common(20)}
                        for u, s in socks.items()},
            "apis": apis.most_common(60)}


# ── getting a debuggable browser ──────────────────────────────────────────

def cdp_up(port, timeout=1.5):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def wait_cdp(port, seconds):
    end = time.time() + seconds
    while time.time() < end:
        v = cdp_up(port)
        if v:
            return v
        time.sleep(1)
    return None


def find_chrome():
    cands = [os.path.expandvars(p) for p in (
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe")]
    return next((c for c in cands if os.path.isfile(c)), None)


def launch_chrome(port, profile_dir, url):
    """A Chrome of our own: debug port + its own profile (Chrome 136+ needs both)."""
    exe = find_chrome()
    if not exe:
        print("[probe] Chrome/Edge not found. Start Chrome yourself with "
              f"--remote-debugging-port={port} --user-data-dir=<a folder>, then run the probe again.")
        return False
    os.makedirs(profile_dir, exist_ok=True)
    subprocess.Popen([exe, f"--remote-debugging-port={port}", f"--user-data-dir={profile_dir}",
                      "--no-first-run", "--no-default-browser-check", url])
    print(f"[probe] started {os.path.basename(exe)} (own profile: {profile_dir})")
    return bool(wait_cdp(port, 30))


def _processes():
    """[(name, pid, exe_path)] via PowerShell; [] if unavailable."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-Process | Select-Object Name,Id,Path | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    rows = list(csv.reader(out.splitlines()))
    return [(r[0], int(r[1]), r[2]) for r in rows[1:] if len(r) >= 3 and r[1].isdigit()]


def _listening_ports(pids):
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    ports = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[3] == "LISTENING" and parts[4].isdigit() and int(parts[4]) in pids:
            if parts[1].startswith(("127.0.0.1:", "0.0.0.0:", "[::1]:")):
                ports.append(int(parts[1].rsplit(":", 1)[1]))
    return sorted(set(ports))


def _app_procs(site):
    """The site's desktop-client processes -- never this probe (qianniu_probe.exe matches "qianniu")."""
    names = [n.lower() for n in SITES[site].get("app_names", [])]
    me = os.getpid()
    return [p for p in _processes()
            if any(n in p[0].lower() for n in names) and "probe" not in p[0].lower() and p[1] != me]


def _open_devtools_port(procs):
    for p in _listening_ports({pid for _, pid, _ in procs}):
        v = cdp_up(p)
        if v:
            return p, v
    return None, None


def launch_app(site, port, app_exe, probe_log):
    """Restart the site's desktop client with a debug port; returns the port that answers, or None.

    First checks whether the running client ALREADY exposes a DevTools
    endpoint. Writes a verdict record either way -- that alone tells us
    whether the client can be probed.
    """
    procs = _app_procs(site)
    exe = app_exe or next((p[2] for p in procs if p[2] and p[2].lower().endswith(".exe")), None) \
        or next((c for c in SITES[site].get("app_exes", []) if os.path.isfile(c)), None)
    verdict = {"kind": "app_probe", "site": site, "exe": exe,
               "running": [[n, pid, path] for n, pid, path in procs]}
    p, v = _open_devtools_port(procs)
    if p:
        verdict.update(verdict="OPEN_ALREADY", port=p, browser=v.get("Browser"))
        probe_log(verdict)
        print(f"[probe] the running app already exposes DevTools on port {p}")
        return p
    if not exe:
        verdict.update(verdict="EXE_NOT_FOUND")
        probe_log(verdict)
        print("[probe] could not find the desktop client. Run again with --app-exe <path to its .exe>.")
        return None
    if procs:
        ans = input(f"[probe] the app is running ({len(procs)} processes). Close it and restart it in "
                    "probe mode? It reopens right away; you may need to log in again. [y/N] ").strip().lower()
        if ans not in ("y", "yes"):
            verdict.update(verdict="USER_DECLINED_RESTART")
            probe_log(verdict)
            return None
        for _, pid, _ in procs:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        time.sleep(3)
    subprocess.Popen([exe, f"--remote-debugging-port={port}", "--remote-allow-origins=*"])
    print(f"[probe] started {exe} with --remote-debugging-port={port}; waiting up to 60s (log in if asked) ...")
    v = wait_cdp(port, 60)
    if v:
        verdict.update(verdict="OPEN", port=port, browser=v.get("Browser"))
        probe_log(verdict)
        return port
    procs = _app_procs(site)
    p, v = _open_devtools_port(procs)   # a child process may have taken another port
    verdict["running_after"] = [[n, pid, path] for n, pid, path in procs]
    if p:
        verdict.update(verdict="OPEN_OTHER_PORT", port=p, browser=v.get("Browser"))
        probe_log(verdict)
        return p
    verdict.update(verdict="DEAD", note="the flag was passed but no DevTools port opened "
                                        "(hardened or non-Chromium client) -- use the web version")
    probe_log(verdict)
    print("[probe] VERDICT: the desktop client does not open a debug port. Use the web version: "
          "run again and choose [1] (or --launch chrome).")
    return None


# ── desktop-client diagnosis: can we reach its pages over DevTools at all? ──

# file name (lower) -> the web runtime it gives away
RUNTIME_MARKERS = {
    "libcef.dll": "cef", "cef.pak": "cef", "cef_100_percent.pak": "cef",
    "app.asar": "electron", "electron.asar": "electron",
    "webview2loader.dll": "webview2", "embeddedbrowserwebview.dll": "webview2",
    "qt5webenginecore.dll": "qtwebengine", "qt6webenginecore.dll": "qtwebengine",
    "qtwebengineprocess.exe": "qtwebengine",
    "mb.dll": "miniblink", "miniblink.dll": "miniblink", "wke.dll": "miniblink", "node.dll": "miniblink?",
    "nw.dll": "nwjs",
    "chrome_elf.dll": "chromium", "v8_context_snapshot.bin": "chromium", "icudtl.dat": "chromium",
}


def _process_table():
    """[{name, pid, ppid, path, cmd}] for every process (PowerShell CIM)."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object Name,ProcessId,ParentProcessId,"
             "ExecutablePath,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60).stdout
        rows = json.loads(out or "[]")
    except Exception:
        return []
    rows = rows if isinstance(rows, list) else [rows]
    return [{"name": r.get("Name") or "", "pid": r.get("ProcessId"), "ppid": r.get("ParentProcessId"),
             "path": r.get("ExecutablePath") or "", "cmd": (r.get("CommandLine") or "")[:600]}
            for r in rows]


def _app_tree(site, table=None):
    """The client's processes and all their descendants (WebView2/CEF children included)."""
    table = table if table is not None else _process_table()
    names = [n.lower() for n in SITES[site].get("app_names", [])]
    me = os.getpid()
    roots = {r["pid"] for r in table
             if any(n in r["name"].lower() for n in names) and "probe" not in r["name"].lower()
             and r["pid"] != me}
    tree, grew = set(roots), True
    while grew:
        grew = False
        for r in table:
            if r["ppid"] in tree and r["pid"] not in tree and r["pid"] != me:
                tree.add(r["pid"])
                grew = True
    return [r for r in table if r["pid"] in tree]


def _scan_install(exe):
    found, root = {}, os.path.dirname(exe or "")
    if not root or not os.path.isdir(root):
        return {"root": root, "runtimes": [], "markers": {}}
    base_depth = root.rstrip("\\/").count(os.sep)
    for d, dirs, files in os.walk(root):
        if d.count(os.sep) - base_depth >= 3:
            dirs[:] = []
        for f in files:
            kind = RUNTIME_MARKERS.get(f.lower())
            if kind:
                found.setdefault(kind, []).append(os.path.relpath(os.path.join(d, f), root))
    return {"root": root, "runtimes": sorted(found), "markers": {k: v[:5] for k, v in found.items()}}


def _kill_tree(site):
    for r in _app_tree(site):
        subprocess.run(["taskkill", "/PID", str(r["pid"]), "/T", "/F"], capture_output=True)
    time.sleep(3)


def _find_devtools(site, port):
    if cdp_up(port):
        return port
    for p in _listening_ports({r["pid"] for r in _app_tree(site)}):
        if cdp_up(p):
            return p
    return None


def diagnose_app(site, port, app_exe, wait_s=45):
    """Try every known way to open the client's DevTools; returns (port or None, report)."""
    table = _process_table()
    tree = _app_tree(site, table)
    exe = app_exe or next((r["path"] for r in tree if r["path"].lower().endswith(".exe")
                           and "--type=" not in r["cmd"]), None) \
        or next((c for c in SITES[site].get("app_exes", []) if os.path.isfile(c)), None)
    report = {"kind": "app_diag", "site": site, "exe": exe,
              "processes_before": tree, "install": _scan_install(exe), "attempts": []}
    rt = report["install"]["runtimes"]
    print(f"[diag] client exe: {exe}\n[diag] web runtime markers: {rt or 'none found'}")
    if tree:
        print(f"[diag] running now: {len(tree)} processes "
              f"({', '.join(sorted({r['name'] for r in tree}))})")
    p = _find_devtools(site, port)
    if p:
        report["verdict"] = f"OPEN_ALREADY:{p}"
        return p, report
    if not exe:
        report["verdict"] = "EXE_NOT_FOUND"
        print("[diag] could not find the client's exe -- run again with --app-exe <path>.")
        return None, report

    attempts = [("flag", [exe, f"--remote-debugging-port={port}", "--remote-allow-origins=*"], {})]
    attempts.append(("webview2_env", [exe], {
        "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS": f"--remote-debugging-port={port} --remote-allow-origins=*"}))
    if "electron" in rt:
        attempts.append(("electron_inspect", [exe, f"--remote-debugging-port={port}", f"--inspect={port + 1}"], {}))

    tried_inner = False
    i = 0
    while i < len(attempts):
        label, argv, env = attempts[i]
        i += 1
        _kill_tree(site)
        print(f"[diag] attempt '{label}': starting the client, waiting up to {wait_s}s (log in if asked) ...")
        try:
            subprocess.Popen(argv, env={**os.environ, **env} if env else None)
        except Exception as exc:
            report["attempts"].append({"label": label, "argv": argv, "error": str(exc)})
            continue
        found, end = None, time.time() + wait_s
        while time.time() < end and not found:
            time.sleep(3)
            found = _find_devtools(site, port) or (_find_devtools(site, port + 1) if label == "electron_inspect" else None)
        after = _app_tree(site)
        rec = {"label": label, "argv": argv, "env": env, "devtools_port": found,
               "processes": after,
               "flag_reached": [r["name"] for r in after if "remote-debugging-port" in r["cmd"]],
               "listening": _listening_ports({r["pid"] for r in after})}
        report["attempts"].append(rec)
        print(f"[diag]   -> devtools={'port ' + str(found) if found else 'no'}; "
              f"flag seen in: {rec['flag_reached'] or 'no process'}; ports={rec['listening'][:8]}")
        if found:
            report["verdict"] = f"OPEN:{label}:{found}"
            return found, report
        # a launcher shell hands off to another exe: retry the flag on the real one
        inner = next((r["path"] for r in after if r["path"] and "--type=" not in r["cmd"]
                      and os.path.normcase(r["path"]) != os.path.normcase(exe)
                      and r["path"].lower().endswith(".exe")), None)
        if inner and not tried_inner:
            tried_inner = True
            attempts.insert(i, ("inner_exe_flag",
                                [inner, f"--remote-debugging-port={port}", "--remote-allow-origins=*"], {}))
            print(f"[diag]   the client runs as another exe too: {inner} -- will try the flag on it")

    hint = {"miniblink": "renders with miniblink, which has no DevTools protocol",
            "miniblink?": "ships node.dll (maybe miniblink, which has no DevTools protocol)",
            "cef": "CEF with debugging compiled out or disabled by the app",
            "electron": "a hardened Electron build (debugging fuses off)",
            "webview2": "WebView2 with extra browser arguments blocked"}
    report["verdict"] = "DEAD"
    report["why"] = [hint[k] for k in rt if k in hint] or ["no known web runtime found in the install folder"]
    print(f"[diag] VERDICT: no DevTools endpoint could be opened. Likely: {'; '.join(report['why'])}.\n"
          "[diag] Record the web version instead (option 1).")
    _kill_tree(site)
    exe_to_restart = exe
    try:
        subprocess.Popen([exe_to_restart])   # leave the client running normally again
    except Exception:
        pass
    return None, report


def _site_from_name():
    name = os.path.basename(sys.executable if getattr(sys, "frozen", False) else sys.argv[0]).lower()
    return next((k for k in SITES if k in name), "pdd")


def _finish_prompt():
    if getattr(sys, "frozen", False):
        input("Press Enter to exit...")


def main():
    here = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description="Record a site's WebSocket + API traffic from a running Chrome.")
    ap.add_argument("--site", choices=sorted(SITES), default=_site_from_name(),
                    help="preset for --match/--api (default: from the exe name)")
    ap.add_argument("--port", type=int, default=9228)
    ap.add_argument("--match", default=None, help="comma-separated page URL substrings to attach to")
    ap.add_argument("--api", default=None, help="comma-separated API URL substrings to record")
    ap.add_argument("--launch", choices=("ask", "none", "chrome", "app", "diag"), default="ask",
                    help="when nothing listens on --port: start our own Chrome, or restart the "
                         "site's desktop client with a debug port (default: ask)")
    ap.add_argument("--app-exe", default="", help="path of the desktop client's .exe (app mode)")
    ap.add_argument("--start-url", default=None, help="page our Chrome opens (chrome mode)")
    ap.add_argument("--minutes", type=float, default=0, help="stop after this long (default: Ctrl+C)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    site = SITES[a.site]
    out = a.out or os.path.join(here, f"{a.site}_probe_out")
    match = a.match if a.match is not None else site["match"]
    api = a.api if a.api is not None else site["api"]
    early = []  # records made before the capture file exists

    port = a.port
    if not cdp_up(port):
        mode = a.launch
        if mode == "ask":
            opts = "[1] the web version, in a Chrome the probe opens"
            if site.get("app_names"):
                opts += ("\n        [2] the desktop client (restarts it once)"
                         "\n        [3] diagnose the desktop client (tries every known way; restarts it a few times)")
            ans = input(f"[probe] nothing is listening on port {port}. Record:\n        {opts}\n        [q] quit: ").strip()
            has_app = bool(site.get("app_names"))
            mode = {"1": "chrome", "2": "app" if has_app else "none", "3": "diag" if has_app else "none"}.get(ans, "none")
        if mode == "chrome":
            # the profile holds the seller's login -- keep it OUT of the folder that gets sent
            profile = os.path.join(os.path.dirname(os.path.abspath(out)), f"{a.site}_probe_chrome_profile")
            if not launch_chrome(port, profile, a.start_url or site["start_url"]):
                print("[probe] Chrome did not open its debug port.")
            else:
                print("[probe] log in to the seller account in that Chrome window, then open the chat.")
        elif mode == "diag":
            got = None
            if not _app_tree(a.site) or input("[probe] the diagnosis closes and restarts the desktop client "
                                              "up to 4 times (you may need to log in each time). Continue? "
                                              "[y/N] ").strip().lower() in ("y", "yes"):
                got, report = diagnose_app(a.site, port, a.app_exe)
                early.append(report)
            else:
                early.append({"kind": "app_diag", "verdict": "USER_DECLINED_RESTART"})
            if got:
                port, match = got, ""
            else:
                os.makedirs(out, exist_ok=True)
                path = os.path.join(out, time.strftime("app_diag_%Y%m%d-%H%M%S.json"))
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(early, f, ensure_ascii=False, indent=2)
                print(f"\n[probe] diagnosis saved: {path}\nSend the whole folder: {out}")
                _finish_prompt()
                return 1
        elif mode == "app":
            got = launch_app(a.site, port, a.app_exe, early.append)
            if got:
                port, match = got, ""   # the whole app is the site
            else:
                os.makedirs(out, exist_ok=True)
                path = os.path.join(out, time.strftime("app_verdict_%Y%m%d-%H%M%S.json"))
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(early, f, ensure_ascii=False, indent=2)
                print(f"\n[probe] verdict saved: {path}\nSend the whole folder: {out}")
                _finish_prompt()
                return 1

    probe = Probe(port, [x for x in match.split(",") if x], [x for x in api.split(",") if x], out,
                  globals_re=site["globals"], ignore_ws=site.get("ignore_ws"))
    for rec in early:
        probe.write(rec)
    try:
        browser = probe.start()
    except Exception as exc:
        print(f"[probe] cannot reach Chrome on port {port}: {exc}\n"
              f"        Start Chrome with --remote-debugging-port={port} --user-data-dir=<a folder>, then retry.")
        _finish_prompt()
        return 1
    print(f"[probe] site={a.site}; attached to {browser} on port {port}; recording to {probe.path}")
    if not probe.attached:
        print(f"[probe] no page matching {match!r} is open yet -- open the chat page; it is picked up automatically.")
    print("[probe] use the chat normally -- receive AND send a few messages. Press Ctrl+C to stop.\n")
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
              f"lib.mtop={g.get('mtop_type')}")
    print(f"\nSend the whole folder: {out}  (it holds real chat messages -- share it privately)")
    _finish_prompt()
    return 0


if __name__ == "__main__":
    sys.exit(main())

# Build (dev machine) -- the exe's name picks the site preset:
#   python -m PyInstaller --onefile --console --name pdd_probe scripts/site_probe_standalone.py
#   python -m PyInstaller --onefile --console --name qianniu_probe scripts/site_probe_standalone.py
