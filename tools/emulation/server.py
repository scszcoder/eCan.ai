"""
Feige (飞鸽) emulation server.

A tiny stdlib-only web server that serves a single-page Feige chat-panel
emulation at

    http://127.0.0.1:9876/im.jinritemai.com/

The URL path contains "im.jinritemai.com" so the Browser-Automation node's
event-monitor urlPatterns matches without any hosts-file rewriting.

Run:
    python tools/emulation/server.py
    python tools/emulation/server.py --port 9876 --host 0.0.0.0
"""

import argparse
import copy
import http.server
import json
import socketserver
import struct
import subprocess
import sys
import zlib
from pathlib import Path
from urllib.parse import urlparse

EMU_ROOT = Path(__file__).resolve().parent
REPO_ROOT = EMU_ROOT.parent.parent
STATIC_DIR = EMU_ROOT / "static"
CONFIG_PATH = EMU_ROOT / "emulation_config.json"

# Real PNG captured from the live Feige site, dropped beside server.py
# by the operator.  Served verbatim at /sample0.png and also included
# in the image pool the front-end picks from for the "图文模式" buttons.
SAMPLE0_PATH = EMU_ROOT / "sample0.png"

DEFAULT_CONFIG = {
    "enabled": True,
    "preset": "realistic_site",
    "probability": 0.55,
    "send": {
        "blockClickMs": 1200,
        "delayAgentAppendMs": 1800,
        "neverAppendAgent": False,
    },
    "renderer": {
        "stallEnabled": True,
        "blockMs": 450,
        "intervalMs": 1800,
        "autoStopAfterMs": 180000,
    },
    "dom": {
        "selectorDelayMs": 12,
        "extraMessageRows": 240,
        "systemRows": 12,
        "churnEnabled": True,
        "churnIntervalMs": 1000,
        # Load-dependent scrape stall (2026-06-03 mt070 blackout repro). When
        # enabled, the page busy-waits inside scrape-signature querySelector
        # calls proportional to accumulated conversation volume + concurrent
        # active customers, so the eCan scrape Runtime.evaluate climbs to the
        # 5-28s range and blinds the co-located sidebar detector. Disabled by
        # default (no-op) so existing scenarios are unaffected.
        "scrapeStall": {
            "enabled": False,
            "baseMs": 120,
            "perMsgMs": 20,
            "perConvoMs": 500,
            "capMs": 30000,
        },
    },
    "focus": {
        "churnEnabled": True,
        "switchIntervalMs": 1500,
        "switchProbability": 0.18,
        "rerenderDuringSend": True,
        "removeComposeDuringSend": False,
        "removeComposeMs": 1200,
    },
    "harness": {
        "fakeRuntimeDelayMs": 7000,
        "fakeRuntimeNeverResolve": False,
        "cdpUseDelayMs": 7000,
        "cdpUseNeverRespond": False,
        "cdpUseLateResponseMs": 7000,
    },
    # ── Test-injection knobs read by the eCan app (opt-in) ─────────────
    # When the app runs with ECAN_EMULATION_TEST_FLAGS=1 it reads this
    # emulation_config.json file at every LLM call and injects matching
    # faults / behaviours. The knobs default to no-op so production runs
    # are unaffected when the env flag is unset.
    "llmFault": {
        # Probability in [0, 1] that the next LLM call synthesizes an
        # OpenAI 429 quota-exceeded error instead of going upstream.
        # Mirrors the customer's billing-exhausted live failure mode so
        # we can exercise the retry path locally.
        "inject429Probability": 0.0,
        # Optional explicit error mode: "429" (quota) or "connection"
        # (network reset). Used when inject429Probability > 0.
        "errorMode": "429",
    },
    # 2026-05-24 mt038: RAG fault injection (mt019/20 local repro).
    # Read by agent/ec_skills/rag/local_rag_mcp.py rag_query() at the
    # start of every call when ECAN_EMULATION_TEST_FLAGS=1.  mt019
    # capped rag_query at 10s; "hang" mode with hangSeconds > 10
    # exercises the timeout-fallback branch.  "error" raises
    # immediately to exercise the error-return path.
    "ragFault": {
        "injectProbability": 0.0,
        "mode": "hang",       # "hang" or "error"
        "hangSeconds": 30,    # only used by mode="hang"
    },
    "followUp": {
        # Number of follow-up questions each customer should send AFTER
        # their initial question, used by the "💬 多轮对话" stress button.
        # Set to 0 to disable (single-turn behavior).
        "rounds": 0,
        # Milliseconds to wait between sending each follow-up. The
        # follow-up still fires regardless of whether the bot replied
        # to the previous one — this matches real customers who don't
        # wait politely between questions.
        "intervalMs": 25000,
    },
}

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".json": "application/json; charset=utf-8",
}


def _deep_merge(base, incoming):
    out = copy.deepcopy(base)
    if not isinstance(incoming, dict):
        return out
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _read_config():
    if not CONFIG_PATH.is_file():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _deep_merge(DEFAULT_CONFIG, data)


def _write_config(config):
    data = _deep_merge(DEFAULT_CONFIG, config)
    CONFIG_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return data


# ════════════════════════════════════════════════════════════════════════
# Flood-test metrics oracle (2026-06-02)
# ════════════════════════════════════════════════════════════════════════
# The emulation page is the ground-truth observer of the flood test: it
# SENDS every customer query and RECEIVES every reply the eCan agent types
# back. The page POSTs two structured event types here as they happen:
#
#   {"mtype": "q_sent",    "cid", "cust", "text", "ts"}
#   {"mtype": "agent_msg", "cid", "cust", "text", "is_placeholder", "ts"}
#
# (ts is the browser Date.now() ms — both event types share the same clock,
# so all timing comparisons below are internally consistent.)
#
# A "run" brackets one flood round. The round-controller calls
# /api/emulation/run/start before the flood and /api/emulation/run/stop
# after the 3-minute window; on stop the server computes the four metrics
# and writes results/<run_id>.json.
#
# The four metrics (per the test spec):
#   1. answered_queries       — customer queries that got a real (non-placeholder) reply
#   2. placeholder_late       — queries where no agent msg (placeholder OR real)
#                               arrived within 35s of the query (clock reset by
#                               an intervening placeholder)
#   3. duplicate_responses    — real replies whose text repeats an earlier real
#                               reply to the SAME customer
#   4. placeholder_after_real — placeholders that arrive after the customer's
#                               real answer (with no new query in between)

import threading
import time as _time

RESULTS_DIR = EMU_ROOT / "results"
PLACEHOLDER_WINDOW_MS = 35000

_METRICS_LOCK = threading.Lock()
_RUN = {"run_id": None, "label": None, "started_at": None, "events": []}
_PENDING_CMD = {"cmd": None}


def _start_run(run_id, label=None):
    with _METRICS_LOCK:
        _RUN["run_id"] = run_id
        _RUN["label"] = label
        _RUN["started_at"] = int(_time.time() * 1000)
        _RUN["events"] = []
    return {"ok": True, "run_id": run_id}


def _record_event(ev):
    """Append a structured metric event if a run is active. Tolerant of
    missing fields so a malformed page event can never crash the server."""
    if not isinstance(ev, dict):
        return
    mtype = ev.get("mtype")
    if mtype not in ("q_sent", "agent_msg"):
        return
    with _METRICS_LOCK:
        if _RUN["run_id"] is None:
            return  # no active run — silently ignore
        _RUN["events"].append({
            "mtype": mtype,
            "cid": str(ev.get("cid") or ev.get("cust") or "?"),
            "cust": str(ev.get("cust") or ev.get("cid") or "?"),
            "text": str(ev.get("text") or ""),
            "is_placeholder": bool(ev.get("is_placeholder", False)),
            "ts": int(ev.get("ts") or 0),
        })


def _compute_report(run):
    events = sorted(run.get("events") or [], key=lambda e: e["ts"])
    by_cust = {}
    for e in events:
        by_cust.setdefault(e["cid"], []).append(e)

    answered = 0
    total_queries = 0
    placeholder_late = 0
    duplicate_responses = 0
    placeholder_after_real = 0
    per_customer = {}

    for cid, evs in by_cust.items():
        evs.sort(key=lambda e: e["ts"])
        q = 0          # queries for this customer
        c_answered = 0
        c_late = 0
        c_dup = 0
        c_pah = 0
        seen_real_texts = set()

        # ── metrics 1 & 3 & 4: single forward walk ──────────────────────
        last_query_ts = None
        last_real_ts = None
        # pending query awaiting a real reply (for "answered" attribution)
        awaiting_real = False
        for e in evs:
            if e["mtype"] == "q_sent":
                q += 1
                last_query_ts = e["ts"]
                awaiting_real = True
            else:  # agent_msg
                if e["is_placeholder"]:
                    # metric 4: placeholder after the real answer, no new query since
                    if last_real_ts is not None and (
                        last_query_ts is None or last_real_ts >= last_query_ts
                    ):
                        c_pah += 1
                else:
                    # real reply
                    if awaiting_real:
                        c_answered += 1
                        awaiting_real = False
                    last_real_ts = e["ts"]
                    # metric 3: duplicate real text to same customer
                    norm = " ".join(e["text"].split())
                    if norm and norm in seen_real_texts:
                        c_dup += 1
                    else:
                        seen_real_texts.add(norm)

        # ── metric 2: placeholder-late, timeline with 35s reset ─────────
        # The customer must see SOME agent message within 35s of their query;
        # an intervening placeholder buys another 35s. A miss is counted once
        # per blown deadline, then the deadline re-arms from the miss point so
        # one long silence isn't double-counted into oblivion.
        deadline = None
        for e in evs:
            ts = e["ts"]
            if deadline is not None and ts > deadline:
                # an informative event finally arrived, but too late
                c_late += 1
                deadline = None
            if e["mtype"] == "q_sent":
                deadline = ts + PLACEHOLDER_WINDOW_MS
            elif e["mtype"] == "agent_msg":
                if e["is_placeholder"]:
                    # placeholder satisfies the current deadline and re-arms it
                    if deadline is not None:
                        deadline = ts + PLACEHOLDER_WINDOW_MS
                else:
                    deadline = None  # real reply ends the wait
        # query left hanging past its deadline with nothing ever arriving
        if deadline is not None and (run.get("started_at") is not None):
            now_ms = int(_time.time() * 1000)
            if now_ms > deadline:
                c_late += 1

        answered += c_answered
        total_queries += q
        placeholder_late += c_late
        duplicate_responses += c_dup
        placeholder_after_real += c_pah
        per_customer[cid] = {
            "queries": q, "answered": c_answered, "late": c_late,
            "duplicates": c_dup, "placeholder_after_real": c_pah,
            "events": len(evs),
        }

    return {
        "run_id": run.get("run_id"),
        "label": run.get("label"),
        "started_at": run.get("started_at"),
        "computed_at": int(_time.time() * 1000),
        "customers": len(by_cust),
        "total_queries": total_queries,
        "metrics": {
            "answered_queries": answered,
            "placeholder_late": placeholder_late,
            "duplicate_responses": duplicate_responses,
            "placeholder_after_real": placeholder_after_real,
        },
        "event_count": len(events),
        "per_customer": per_customer,
    }


def _stop_run():
    with _METRICS_LOCK:
        run = copy.deepcopy(_RUN)
    report = _compute_report(run)
    # also keep the raw events alongside the report for offline re-analysis
    out = dict(report)
    out["events"] = run.get("events") or []
    try:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        rid = run.get("run_id") or f"run_{int(_time.time())}"
        safe = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in str(rid))
        (RESULTS_DIR / f"{safe}.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        report["written"] = str(RESULTS_DIR / f"{safe}.json")
    except Exception as exc:
        report["write_error"] = str(exc)
    with _METRICS_LOCK:
        _RUN["run_id"] = None  # end the run; further events ignored
    return report


def _set_pending_cmd(cmd):
    with _METRICS_LOCK:
        _PENDING_CMD["cmd"] = cmd


def _take_pending_cmd():
    with _METRICS_LOCK:
        cmd = _PENDING_CMD["cmd"]
        _PENDING_CMD["cmd"] = None
    return cmd


# ─────────── programmatic sample-product images ────────────────────────
# Three small, visually distinguishable PNGs the front-end serves to the
# customer-B "Send Image and Text {1,2,3}" buttons.  Each is a 240x320
# 8-bit RGB PNG with a solid background colour and a darker rectangular
# "label band" so a vision-capable LLM can describe more than just a
# colour — it sees a recognisable two-tone shape:
#
#   /sample-product/1  →  red T-shirt-ish     (background #d23434, band #6b1414)
#   /sample-product/2  →  blue pants-ish      (background #2f6bd9, band #143a78)
#   /sample-product/3  →  green sneaker-ish   (background #2eaa55, band #115b2c)
#
# Generated via stdlib zlib + struct so we don't require Pillow on the
# emulation server.  Cached in-process per (n, w, h) — generation is
# fast (<5ms for 240x320) so caching is just for politeness.

_PRODUCT_PALETTE = {
    1: ((210,  52,  52), (107,  20,  20), "tshirt"),  # red
    2: (( 47, 107, 217), ( 20,  58, 120), "pants"),   # blue
    3: (( 46, 170,  85), ( 17,  91,  44), "shoes"),   # green
}

_png_cache: dict[tuple[int, int, int], bytes] = {}


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _generate_sample_png(n: int, w: int = 240, h: int = 320) -> bytes:
    """Return a small RGB PNG that's visually distinct per ``n`` (1..3)."""
    cached = _png_cache.get((n, w, h))
    if cached is not None:
        return cached
    bg, band, _label = _PRODUCT_PALETTE.get(n, _PRODUCT_PALETTE[1])
    # Vertical layout: a centered horizontal band ~40% tall in the darker shade.
    band_y0 = int(h * 0.30)
    band_y1 = int(h * 0.70)
    bg_row = bytes(bg) * w
    band_row = bytes(band) * w
    raw = bytearray()
    for y in range(h):
        raw.append(0)  # PNG filter type "None"
        raw.extend(band_row if band_y0 <= y < band_y1 else bg_row)
    idat = zlib.compress(bytes(raw), level=6)
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)  # 8-bit, RGB
    out = (
        sig
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    _png_cache[(n, w, h)] = out
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    # ─── diagnostic sink ────────────────────────────────────────────────
    # ``POST /emu-log`` accepts a small JSON body from the front-end's
    # ``flog()`` helper and prints it to stderr with an ``[EMU]`` prefix.
    # This is the easiest way to see emulation-side activity (button
    # clicks, mode transitions, image bubbles emitted) when the eCan
    # app's ``browser_console.log`` tail can't see the emulation tab
    # (different origin — the tail only watches ``localhost:3000``).
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/emulation/config":
            try:
                body = self._read_json_body(64 * 1024)
                data = _write_config(body)
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "config": data})
            return
        if parsed.path == "/api/emulation/reset":
            data = _write_config(copy.deepcopy(DEFAULT_CONFIG))
            self._send_json({"ok": True, "config": data})
            return
        if parsed.path == "/api/emulation/run-harness":
            try:
                body = self._read_json_body(8 * 1024)
                result = self._run_harness(str(body.get("mode") or ""))
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json(result, status=200 if result.get("ok") else 400)
            return
        # ── flood-test metrics oracle endpoints ──────────────────────────
        if parsed.path == "/api/emulation/run/start":
            try:
                body = self._read_json_body(8 * 1024)
                rid = str(body.get("run_id") or f"run_{int(_time.time())}")
                result = _start_run(rid, body.get("label"))
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json(result)
            return
        if parsed.path == "/api/emulation/run/stop":
            try:
                report = _stop_run()
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True, "report": report})
            return
        if parsed.path == "/api/emulation/event":
            try:
                body = self._read_json_body(8 * 1024)
                _record_event(body)
            except Exception:
                pass  # never let a metric event fail loudly
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if parsed.path == "/api/emulation/flood":
            try:
                body = self._read_json_body(8 * 1024)
                n = int(body.get("n") or 20)
                _set_pending_cmd({
                    "cmd": "flood",
                    "n": max(1, min(200, n)),
                    "imagePct": int(body.get("imagePct") or 0),
                    "cardPct": int(body.get("cardPct") or 0),
                    # ramp knobs (2026-06-03 mt070 blackout repro) — staggered
                    # joins + per-customer follow-ups so threads grow over time.
                    "joinSpreadSec": int(body.get("joinSpreadSec") or 0),
                    "followUpRounds": int(body.get("followUpRounds") or 0),
                    "followUpIntervalMs": int(body.get("followUpIntervalMs") or 30000),
                    "ts": int(_time.time() * 1000),
                })
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=400)
                return
            self._send_json({"ok": True})
            return
        if parsed.path != "/emu-log":
            self.send_error(404, "not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        # Cap body at 8 KiB — these are tiny JSON blobs from flog().
        raw = self.rfile.read(min(length, 8 * 1024)) if length > 0 else b""
        try:
            body = raw.decode("utf-8", errors="replace")
        except Exception:
            body = repr(raw)
        sys.stderr.write("[feige-emu][EMU] %s - %s\n" % (self.address_string(), body))
        sys.stderr.flush()
        self.send_response(204)  # No Content
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path or "/"

        if path == "/api/emulation/config":
            self._send_json({"ok": True, "config": _read_config()})
            return

        # ── flood-test metrics oracle (GET) ──────────────────────────────
        if path == "/api/emulation/command":
            # The page polls this ~1/s; returns a pending command once then
            # clears it (so the same flood doesn't fire twice). ``run_active``
            # tells the page whether a metrics run is in progress — the page
            # gates the load-dependent scrapeStall on it so a leftover
            # ``scrapeStall.enabled`` config can NEVER busy-wait (freeze) a
            # manual session; the stall only applies between run/start and
            # run/stop.
            with _METRICS_LOCK:
                _active = _RUN["run_id"] is not None
            self._send_json({"ok": True, "command": _take_pending_cmd(), "run_active": _active})
            return
        if path == "/api/emulation/report":
            with _METRICS_LOCK:
                run = copy.deepcopy(_RUN)
            self._send_json({"ok": True, "report": _compute_report(run)})
            return

        if path in ("", "/"):
            self.send_response(302)
            self.send_header("Location", "/im.jinritemai.com/")
            self.end_headers()
            return

        if path.startswith("/im.jinritemai.com"):
            self._serve(STATIC_DIR / "index.html")
            return

        if path.startswith("/static/"):
            rel = path[len("/static/"):].lstrip("/")
            target = (STATIC_DIR / rel).resolve()
            static_root = STATIC_DIR.resolve()
            if static_root != target and static_root not in target.parents:
                self.send_error(403, "forbidden")
                return
            self._serve(target)
            return

        # /sample0.png — real PNG captured from the live Feige site and
        # placed beside server.py by the operator.  Served with a stable
        # cache header so reloads don't re-download on every click.
        if path == "/sample0.png":
            if not SAMPLE0_PATH.is_file():
                self.send_error(404, "sample0.png not present beside server.py")
                return
            data = SAMPLE0_PATH.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return

        # /sample-product/<n>[.png] — programmatic sample images (1..3).
        # Supports an optional .png suffix so the front-end ``<img src>``
        # looks like a real file URL to any naive scraper that filters by
        # extension.  Trailing query strings (?v=...) are ignored.
        if path.startswith("/sample-product/"):
            tail = path[len("/sample-product/"):]
            if tail.endswith(".png"):
                tail = tail[:-4]
            try:
                n = int(tail)
            except ValueError:
                self.send_error(404, "not found")
                return
            if n not in _PRODUCT_PALETTE:
                self.send_error(404, "unknown sample-product index")
                return
            data = _generate_sample_png(n)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(data)
            return

        self.send_error(404, "not found")

    def _serve(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self.send_error(404, "not found")
            return
        mime = _MIME.get(path.suffix.lower(), "application/octet-stream")
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _read_json_body(self, max_bytes):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(min(length, max_bytes)) if length > 0 else b"{}"
        if length > max_bytes:
            raise ValueError("request body too large")
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("json object expected")
        return data

    def _send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _run_harness(self, mode):
        scripts = {
            "fake-runtime": EMU_ROOT / "cdp_fake_harness.py",
            "cdp-use": EMU_ROOT / "cdp_use_harness.py",
        }
        script = scripts.get(mode)
        if script is None:
            return {"ok": False, "error": "unknown harness mode"}
        if not script.is_file():
            return {"ok": False, "error": f"missing harness script: {script.name}"}
        proc = subprocess.run(
            [sys.executable, str(script), "--config", str(CONFIG_PATH)],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            timeout=45,
        )
        return {
            "ok": proc.returncode == 0,
            "mode": mode,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
        }

    def log_message(self, fmt, *args):
        sys.stderr.write("[feige-emu] %s - %s\n" % (self.address_string(), fmt % args))


class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    p = argparse.ArgumentParser(description="Feige chat-panel emulation server.")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=9876)
    args = p.parse_args()

    url = f"http://{args.host}:{args.port}/im.jinritemai.com/"
    print(f"[feige-emu] listening on {url}", file=sys.stderr)
    print("[feige-emu] point your Chrome (launched with --remote-debugging-port=9228) here", file=sys.stderr)

    with ReusableTCPServer((args.host, args.port), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("[feige-emu] shutting down", file=sys.stderr)


if __name__ == "__main__":
    main()
