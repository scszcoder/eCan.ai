"""千牛 memory observer — the inbound leg.

Continuously scans AliWorkbench memory (read-only), attributes each buyer
message by sender id, and injects it into the SAME dispatch pipeline the
browser sites use — by emitting the identical ``browser_event`` envelope
(``_build_normalized_browser_event`` tolerates ``session=None``) and calling
``event_monitor._dispatch_to_runners``. Downstream PreDispatch / dedup /
front-desk / Q&A are therefore unchanged; only the detection source differs.

Runs in a background thread (memory scanning is blocking CPU work) started from
the bundle's ``register()`` when ``ECAN_LIVE_CHAT_SITE`` names qianniu_chat.
Lifecycle gate: ``ECAN_QIANNIU_OBSERVER`` (default on when the bundle registers).
"""
from __future__ import annotations

import json
import os
import threading
import time
from collections import OrderedDict
from typing import Optional

from utils.logger_helper import logger_helper as logger
from utils import win_process_memory as mem

from . import mem_locator, name_map

_PROC_NAME = "AliWorkbench"
_SEEN_MAX = 2000
_LABEL = "qianniu_chat"
_LEARN_THROTTLE_S = 5.0
_HEARTBEAT_S = 300.0
_NOBODY_RETRY_S = 120.0   # keep re-dispatching a message no runner took (startup)
_PRODUCT_TTL_MS = 3 * 3600 * 1000   # a product card older than this no longer frames the chat
_COLD_SWEEP_DELAY_S = 20.0          # let the front desk register before reading waiting chats

def _backstop_interval_s() -> float:
    """Seconds between list-only backstop passes (ECAN_QIANNIU_BACKSTOP_S, 0 = off)."""
    try:
        return max(0.0, float(os.environ.get("ECAN_QIANNIU_BACKSTOP_S", "90")))
    except ValueError:
        return 90.0

# 千牛 platform notices that arrive as ordinary-looking message objects in the
# buyer's conversation (alpha 2026-10-07: "【即将超时】您即将超超20分钟未回复买家，
# 请您尽快妥善处理买家问题。若消极接待行为属实…" was dispatched as a buyer
# question). Never answer them. Keyword-based like the 飞鸽 front desk's filter;
# replace with a msgType rule once "new message object" logs show the values.
_SYSTEM_NOTICE_MARKERS = ("【即将超时】", "未回复买家", "消极接待", "系统关闭会话", "客服超时",
                          # msgType 129 entry notice (alpha 2026-10-07): not a question
                          "当前用户来自")


def _is_system_notice(text: str) -> bool:
    t = text or ""
    return any(m in t for m in _SYSTEM_NOTICE_MARKERS)


# ── Our own sends (alpha 2026-10-07) ─────────────────────────────────────────
# A reply we type into 千牛 lands in memory as a message object WITHOUT the
# outgoing markers (no ccode / sendStatus), from the store's own sender id --
# so it looked like a new buyer message, was dispatched, answered and sent
# again: a self-echo loop. qianniu_send records every text it sends; a memory
# message matching one of them is ours, and its sender is the store itself.
_SENT_TTL_S = 600.0
_sent_texts: "OrderedDict[str, float]" = OrderedDict()
_sent_lock = threading.Lock()


def _norm_text(text: str) -> str:
    return "".join((text or "").split())


def record_sent(text: str) -> None:
    """Called by qianniu_send after a successful send."""
    key = _norm_text(text)
    if not key:
        return
    with _sent_lock:
        _sent_texts[key] = time.monotonic()
        while len(_sent_texts) > 200:
            _sent_texts.popitem(last=False)


def _is_our_send(text: str) -> bool:
    key = _norm_text(text)
    if not key:
        return False
    now = time.monotonic()
    with _sent_lock:
        ts = _sent_texts.get(key)
        return ts is not None and now - ts <= _SENT_TTL_S


def _preview_core(text: str) -> str:
    """A list preview without the ellipsis 千牛 adds when it truncates."""
    return _norm_text(text).rstrip(".…。")


def _is_our_send_preview(preview: str) -> bool:
    """True when a (possibly truncated) list preview is the start of a text we
    sent recently -- the store spoke last, nothing to check."""
    core = _preview_core(preview)
    if len(core) < 4:
        return False
    now = time.monotonic()
    with _sent_lock:
        return any(k.startswith(core) and now - ts <= _SENT_TTL_S for k, ts in _sent_texts.items())


def _qianniu_pids() -> list:
    """Every AliWorkbench.exe pid, the ROOT process first.

    千牛 runs two or more AliWorkbench.exe (a main process with child processes,
    plus AliRender.exe renderers). The chat messages live in the root one --
    probe run 2026-09-30: every hit was in the parent pid, none in its child --
    and psutil lists by pid, so "the first AliWorkbench" was often the child:
    the 0.9.99x alpha scanned it for 8 hours and saw nothing.
    """
    try:
        import psutil
    except Exception:
        pid = mem.find_pid_by_process_name(_PROC_NAME)
        return [pid] if pid else []
    low = _PROC_NAME.lower()
    parent_of = {}
    for proc in psutil.process_iter(["pid", "ppid", "name"]):
        try:
            if (proc.info.get("name") or "").lower() in (low, low + ".exe"):
                parent_of[int(proc.info["pid"])] = int(proc.info.get("ppid") or 0)
        except Exception:
            continue
    roots = sorted(pid for pid, ppid in parent_of.items() if ppid not in parent_of)
    return roots + sorted(pid for pid in parent_of if pid not in roots)


# ── FIND mode (diagnostic; the standalone bot's --find/--probe, in the app) ──
# ECAN_QIANNIU_FIND="有樱桃味牙线吗" (several: separate with |) makes every scan
# look for that exact text in BOTH encodings and log, on change, how 千牛 holds
# it: whether a "sender" message object is nearby, which message keys surround
# it, and one context dump. It answers "the buyer's message landed but was not
# detected" in one run: text-only (no structure), structured-but-classed-
# outgoing, or not in this process at all.
_FIND_KEYS = ("sender", "targetId", "content", "ccode", "cid", "conversationCode",
              "conversationId", "messageId", "sendTime", "selfStatus", "summary",
              "msgType", "lastMessage", "unread", "nick", "receiver", "layoutJson")


def _find_needles() -> list:
    raw = os.environ.get("ECAN_QIANNIU_FIND", "").strip()
    return [(t, t.encode("utf-8"), t.encode("utf-16-le"))
            for t in (x.strip() for x in raw.split("|")) if t]


def _printable(s: str) -> str:
    return s.translate({c: "." for c in range(0x20) if c not in (0x09, 0x0a)})


def _find_in_slice(data: bytes, needles: list, finds: dict) -> None:
    for text, n8, n16 in needles:
        for enc, needle in (("utf-8", n8), ("utf-16-le", n16)):
            cursor = 0
            while True:
                i = data.find(needle, cursor)
                if i < 0:
                    break
                cursor = i + len(needle)
                f = finds.setdefault(text, {"utf-8": 0, "utf-16-le": 0, "sender_near": 0,
                                            "in_object": 0, "in_message_object": 0,
                                            "object_keys": set(), "keys": set(),
                                            "sample": "", "sample_in_object": ""})
                f[enc] += 1
                span = 4000 if enc == "utf-8" else 8000
                near = data[max(0, i - span):i + span]
                for k in _FIND_KEYS:
                    if f'"{k}"'.encode(enc) in near:
                        f["keys"].add(k)
                if '"sender"'.encode(enc) in near:
                    f["sender_near"] += 1
                # Definitive: is the text INSIDE a JSON object, and is that object a
                # message (has "sender")? "Nearby" alone can be a neighbouring object.
                obj = _enclosing_object(data, i, len(needle), enc)
                if obj is not None:
                    f["in_object"] += 1
                    f["object_keys"].update(str(k) for k in list(obj.keys())[:30])
                    if "sender" in obj:
                        f["in_message_object"] += 1
                lo = max(0, i - 600)
                if enc == "utf-16-le" and (i - lo) % 2:
                    lo += 1
                ctx = f"[{enc}] " + _printable(data[lo:i + len(needle) + 600].decode(enc, "replace"))[:900]
                if not f["sample"]:
                    f["sample"] = ctx
                if obj is not None and not f["sample_in_object"]:
                    f["sample_in_object"] = (f"[{enc}] object keys={sorted(str(k) for k in obj)[:30]} "
                                             f"sender={obj.get('sender')!r}"[:900])


def _enclosing_object(data: bytes, i: int, n: int, enc: str):
    """The smallest JSON object enclosing the bytes at [i, i+n), or None."""
    lo = max(0, i - 8192)
    if enc == "utf-16-le" and (i - lo) % 2:
        lo += 1
    raw = data[lo:min(len(data), i + n + 8192)]
    try:
        decoded = raw.decode(enc, "replace")
        at = len(raw[:i - lo].decode(enc, "replace"))
    except Exception:
        return None
    for obj in mem_locator._objs_in_window(decoded, at):
        return obj
    return None


def _direction_reason(cand, seller: Optional[str]) -> str:
    if _is_our_send(cand.text):
        return "our own sent reply"
    raw = cand.raw if isinstance(cand.raw, dict) else {}
    cid = raw.get("cid") if isinstance(raw.get("cid"), dict) else {}
    why = [k for k, on in (("cid.ccode", bool(cid.get("ccode"))), ("ccode", bool(raw.get("ccode"))),
                           ("sendStatus", "sendStatus" in raw), ("progress", "progress" in raw)) if on]
    if why:
        return "outgoing marker: " + ",".join(why)
    if seller and cand.uid == seller:
        return "sender is the store id"
    return "no outgoing marker"


def learn_enabled() -> bool:
    return os.environ.get("ECAN_QIANNIU_LEARN", "1") != "0"


def _poll_interval_s() -> float:
    try:
        return max(1.0, float(os.environ.get("ECAN_QIANNIU_POLL_S", "") or 3.0))
    except (TypeError, ValueError):
        return 3.0


def item_for(cand: "mem_locator.MsgCandidate", seller_id: Optional[str],
             display_name: str = "") -> dict:
    """Build the front-desk item dict (same shape pdd_chat/ws_observer emits)."""
    buyer_ids = sorted(cand.sender_ids - ({seller_id} if seller_id else set()))
    uid = buyer_ids[0] if buyer_ids else (next(iter(cand.sender_ids), "") if cand.sender_ids else "")
    text = cand.text
    msg_id = cand.msg_id or f"mem:{uid}:{text[:24]}"
    display_name = display_name or name_map.name_for(uid)
    return {
        "customer_name": uid, "name": uid, "session_id": uid, "customer_id": uid,
        "talk_id": uid,
        "customer_display_name": display_name or "",
        "last_message": text, "latest_message": text,
        "msg_id": msg_id, "latest_message_msg_id": msg_id,
        "identity_key": f"{uid}|{msg_id}",
        "unread_badge": "1",
        "source": "qianniu_mem",
        "message_kind": "text",
    }


def route_ready() -> bool:
    """True once some agent runner routes browser_event:qianniu_chat to a task
    (the 天猫 front desk has registered). Runners that merely RECEIVE the event
    log "No target task found" and drop it, yet were counted as reached (yo
    alpha: a cold-start dispatch 33 s before the front desk started was lost).
    Unknown (no app context) counts as ready."""
    try:
        from app_context import AppContext
        mw = AppContext.get_main_window()
        agents = getattr(mw, "agents", None)
        if not agents:
            return True
        key = f"browser_event:{_LABEL}"
        return any(key in (getattr(getattr(ag, "runner", None), "_global_event_routing", None) or {})
                   for ag in agents)
    except Exception:
        return True


def inject_item(item: dict, target_agent_id: str = "") -> int:
    """Emit the browser-event envelope and dispatch to agent runners.

    Returns the number of runners reached (0 if none / app not up yet / no task
    routes 千牛 events yet -- the caller retries).
    """
    if not route_ready():
        return 0
    from agent.ec_skills.browser_use_extension.event_monitor import (
        _build_normalized_browser_event, _dispatch_to_runners,
    )
    payload = {"items": [item], "key_field": "identity_key"}
    sub_id = f"qianniu_mem:{item.get('identity_key', '')}"
    params = {
        "url": "", "method": "MEM_SCAN", "status": 200,
        "body": json.dumps(payload, ensure_ascii=False),
        "rule": _LABEL, "detection": "qianniu_mem", "customer_count": 1,
    }
    norm = _build_normalized_browser_event(
        session=None, monitor_id=_LABEL, label=_LABEL,
        source_type="qianniu_mem", params_obj=params, sub_id=sub_id, scope="process",
    )
    evt = {
        "type": "browser_event", "sub_type": _LABEL, "sub_id": sub_id,
        "event_method": "MEM.scan", "domain": "MEM",
        "event": norm, "params": params,
    }
    return _dispatch_to_runners(_LABEL, evt, target_agent_id=target_agent_id)


class QianniuMemObserver:
    """Background memory-scan → attribute → dispatch loop.

    Logging (INFO unless noted) is designed so a silent run can be read from the
    log alone: process changes, the first scan of each process (full counters),
    every dispatch / baseline / stale skip, learn-pass outcomes, open failures
    (once per pid), and a heartbeat every ``_HEARTBEAT_S`` with the last scan's
    counters plus cumulative event counts.
    """

    def __init__(self, dispatch_fn=None):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._last_learn = 0.0
        # Override for tests / the reliability gate; defaults to the real
        # agent-pipeline injection.
        self._dispatch = dispatch_fn or inject_item
        # Cumulative counts of NEW events only (memory is rescanned every poll,
        # so per-scan totals live in self.last_scan, never summed here).
        self.stats = {"scans": 0, "scan_errors": 0, "baseline_seen": 0, "stale_skipped": 0,
                      "new_incoming": 0, "dispatched": 0, "dispatched_to_nobody": 0,
                      "learn_attempts": 0, "learned": 0}
        self.last_scan: dict = {}
        self._scan_ms: list = []   # recent scan durations, for the heartbeat
        self._pids = None          # None: the first pass always logs what it found
        self._hit_pid = 0          # the process messages were last found in; scanned first
        self._scanned_pids: set = set()
        self._open_failed: set = set()
        self._baselined = False
        self._pass_ok = False      # a scan in the current pass read 千牛 without error
        self._shape: dict = {}     # pid -> last scan's extraction counts (log on change)
        self._cards_seen: set = set()
        self._objs_seen: "OrderedDict[str, int]" = OrderedDict()
        self._needles = _find_needles()
        self._find_state: dict = {}   # (pid, text) -> last reported summary
        if self._needles:
            logger.info(f"[QIANNIU-MEM] FIND mode: searching memory for "
                        f"{[t for t, _a, _b in self._needles]} every scan (ECAN_QIANNIU_FIND)")
        self._started_ms = int(time.time() * 1000)
        self._last_heartbeat = 0.0
        self._last_seller = None
        self._nobody_since: dict = {}   # identity_key -> first time no runner took it
        self._product_by_buyer: dict = {}   # buyer uid -> (sendTime ms, "[商品卡片] …")
        self._cold_started = False
        self._dispatched_texts: list = []   # (normalized text, ts) the memory path dispatched

    def _note_product(self, card: dict, seller: Optional[str]) -> None:
        """Remember each buyer's NEWEST product card (link card or 「当前用户来自
        商品详情页」) -- the product their "这款…" questions are about."""
        product, uid = card.get("product") or "", str(card.get("sender") or "")
        if not product or not uid or uid == seller or uid == name_map.store_self_id():
            return
        st = card.get("sendTime") if isinstance(card.get("sendTime"), int) else 0
        prev = self._product_by_buyer.get(uid)
        if prev is None or st >= prev[0]:
            self._product_by_buyer[uid] = (st, product)

    def product_for(self, uid: str) -> str:
        """The buyer's latest product card line, if seen within _PRODUCT_TTL_MS."""
        hit = self._product_by_buyer.get(str(uid or ""))
        if not hit:
            return ""
        st, product = hit
        return product if not st or time.time() * 1000 - st <= _PRODUCT_TTL_MS else ""

    def _first_time(self, key: str) -> bool:
        if not key or key in self._seen:
            return False
        self._seen[key] = time.time()
        while len(self._seen) > _SEEN_MAX:
            self._seen.popitem(last=False)
        return True

    def _learn_pass(self, sender_id: str, text: str) -> None:
        """Throttled content-join: OCR the window; if *text* is on screen, the
        chat header names *sender_id*'s buyer — learn the mapping. This is the
        only bridge from a memory sender id to the display name needed to open a
        conversation (v15: the active id is not in memory)."""
        if not learn_enabled() or name_map.name_for(sender_id):
            return
        # A short message ("人工", "在吗") is on many chats' screens: it cannot
        # prove which chat is open (0.9.99ym: "人工" -> name "0.00元"). Checked
        # before the ~7 s screen read.
        if len("".join((text or "").split())) < 4:
            logger.info(f"[QIANNIU-MEM] learn buyer={sender_id!r}: message {text!r} too short "
                        f"to identify the open chat; not learning a name from it")
            return
        now = time.monotonic()
        if now - self._last_learn < _LEARN_THROTTLE_S:
            logger.debug(f"[QIANNIU-MEM] learn throttled for buyer={sender_id!r}")
            return
        self._last_learn = now
        self.stats["learn_attempts"] += 1
        try:
            from agent.mcp.server.qianniu import qianniu_ocr
            ocr_data = qianniu_ocr.ocr_qianniu_window()
            if not ocr_data:
                logger.info(f"[QIANNIU-MEM] learn buyer={sender_id!r}: OCR returned nothing")
                return
            if not qianniu_ocr.transcript_contains(ocr_data, text):
                logger.info(f"[QIANNIU-MEM] learn buyer={sender_id!r}: message {text[:20]!r} "
                            f"not in the open chat (another conversation is open)")
                return
            name = qianniu_ocr.read_header_name(ocr_data)
            if not name:
                logger.info(f"[QIANNIU-MEM] learn buyer={sender_id!r}: message on screen but no "
                            f"header name; header band={qianniu_ocr.header_band_texts(ocr_data)[:8]}")
                return
            band = [f"{t}@{xy}" for t, xy in qianniu_ocr.header_band_items(ocr_data)[:10]]
            if name_map.learn(sender_id, name):
                self.stats["learned"] += 1
                logger.info(f"[QIANNIU-MEM] learned buyer={sender_id!r} -> name={name!r} "
                            f"(header band: {band})")
            else:
                logger.info(f"[QIANNIU-MEM] learn buyer={sender_id!r}: kept no name from {name!r} "
                            f"(header band: {band})")
        except Exception as exc:
            logger.warning(f"[QIANNIU-MEM] learn pass failed for buyer={sender_id!r}: {exc}")

    def _send_ms(self, cand) -> Optional[int]:
        st = cand.send_time
        if not isinstance(st, int) or st <= 0:
            return None
        return st if st > 10 ** 12 else st * 1000

    def _report_finds(self, pid: int, needles: list, finds: dict) -> None:
        """Log FIND results for *pid* when they change (and the dump once)."""
        for text, _n8, _n16 in needles:
            f = finds.get(text)
            # Change key = what the text IS in, not raw hit counts (those drift every
            # scan as memory churns; 0.9.99yc logged a FIND line every 4 s).
            summary = ((f["in_message_object"], f["in_object"] - f["in_message_object"],
                        f["utf-8"] + f["utf-16-le"] > f["in_object"], tuple(sorted(f["keys"])))
                       if f else None)
            key = (pid, text)
            if self._find_state.get(key) == summary:
                continue
            first = key not in self._find_state
            self._find_state[key] = summary
            if not f:
                if not first:
                    logger.info(f"[QIANNIU-MEM] FIND {text!r}: no longer in pid {pid}")
                continue
            logger.info(f"[QIANNIU-MEM] FIND {text!r} in pid {pid}: utf8_hits={f['utf-8']} "
                        f"utf16_hits={f['utf-16-le']} inside_message_object={f['in_message_object']} "
                        f"inside_other_object={f['in_object'] - f['in_message_object']} "
                        f"bare_text={f['utf-8'] + f['utf-16-le'] - f['in_object']} "
                        f"object_keys={sorted(f['object_keys'])[:40]} keys_nearby={sorted(f['keys'])}")
            if f["sample_in_object"] and (pid, text, "dump_obj") not in self._find_state:
                self._find_state[(pid, text, "dump_obj")] = True
                logger.info(f"[QIANNIU-MEM] FIND {text!r} enclosing object: {f['sample_in_object']}")
            if (pid, text, "dump") not in self._find_state:
                self._find_state[(pid, text, "dump")] = True
                logger.info(f"[QIANNIU-MEM] FIND {text!r} context: {f['sample']}")

    def _is_stale(self, cand) -> bool:
        """Sent before this observer started (with a minute's grace): history
        that loaded into memory later (e.g. a conversation the seller opened),
        not a new buyer turn."""
        ms = self._send_ms(cand)
        return ms is not None and ms < self._started_ms - 60_000

    def _is_fresh(self, cand) -> bool:
        """Known to be sent after this observer started (minus the grace)."""
        ms = self._send_ms(cand)
        return ms is not None and ms >= self._started_ms - 60_000

    def _scan_once(self, pid: int) -> bool:
        """Scan one process; True when it holds chat messages."""
        self.stats["scans"] += 1
        t0 = time.monotonic()
        mstats: dict = {}
        xstats: dict = {}
        candidates: list = []
        finds: dict = {}
        needles = self._needles

        def wanted(data: bytes) -> bool:
            return mem_locator.region_has_messages(data) or any(
                n8 in data or n16 in data for _t, n8, n16 in needles)

        try:
            for data in mem.scan_strings(pid, wanted, stats=mstats):
                if needles:
                    _find_in_slice(data, needles, finds)
                    if not mem_locator.region_has_messages(data):
                        continue          # a FIND-only slice: no message objects to carve
                candidates.extend(mem_locator.extract_candidates(data, stats=xstats))
        except OSError as exc:
            self.stats["scan_errors"] += 1
            if pid not in self._open_failed:
                self._open_failed.add(pid)
                logger.warning(f"[QIANNIU-MEM] cannot read pid {pid}: {exc} "
                               f"(logged once per pid; access denied = eCan needs the same "
                               f"or higher privilege than 千牛)")
            return False
        self._pass_ok = True
        ms = int((time.monotonic() - t0) * 1000)
        self._scan_ms = (self._scan_ms + [ms])[-100:]
        # Our own sent reply in memory names the store's sender id (bot rule).
        for cand in candidates:
            if cand.uid and _is_our_send(cand.text):
                name_map.learn_store_self_id(cand.uid)
        seller = (mem_locator.seller_id_of(candidates) if candidates else None) or \
            (name_map.store_self_id() or None)
        incoming = [c for c in candidates
                    if mem_locator.is_incoming(c, seller) and not _is_our_send(c.text)]
        extract = {k: v for k, v in xstats.items() if isinstance(v, int)}
        self.last_scan = {"pid": pid, "ms": ms, **mstats, "extract": extract,
                          "candidates": len(candidates), "incoming_in_memory": len(incoming),
                          "outgoing_in_memory": len(candidates) - len(incoming)}
        shape = (tuple(sorted(extract.items())), len(incoming))
        if pid not in self._scanned_pids:
            self._scanned_pids.add(pid)
            samples = {k: v for k, v in xstats.items() if k.startswith("sample_")}
            logger.info(f"[QIANNIU-MEM] first scan of pid {pid}: {self.last_scan}"
                        + (f" dropped-object example keys={samples}" if samples else ""))
        elif shape != self._shape.get(pid):
            # On change only: a message arriving in ANY form (even one dropped as a
            # card) leaves a trace, so "nothing arrived" is provable from the log.
            logger.info(f"[QIANNIU-MEM] memory changed in pid {pid}: extract={extract} "
                        f"incoming_in_memory={len(incoming)} (was {self._shape.get(pid)})")
        self._shape[pid] = shape
        for card in xstats.get("ui_cards") or []:
            key = card.get("msg_id") or f"{card.get('sender')}|{card.get('summary')}"
            if key not in self._cards_seen:
                self._cards_seen.add(key)
                product = card.get("product") or ""
                logger.info(f"[QIANNIU-MEM] card in memory (not answered): msgType={card.get('msgType')!r} "
                            f"templateId={card.get('templateId')!r} sender={card.get('sender')!r} "
                            f"sendTime={card.get('sendTime')!r} summary={card.get('summary')!r} "
                            + (f"product={product!r}" if product else
                               f"no product read; payload={card.get('payload_sample')!r}"))
            self._note_product(card, seller)
        if needles:
            self._report_finds(pid, needles, finds)
        # Every message object, either direction, once: an incoming buyer message
        # that is classed OUTGOING is dropped silently otherwise.
        for cand in candidates:
            key = f"{cand.uid}|{cand.msg_id or cand.text[:24]}"
            if key in self._objs_seen:
                continue
            self._objs_seen[key] = 1
            while len(self._objs_seen) > _SEEN_MAX:
                self._objs_seen.popitem(last=False)
            if self._baselined:   # the baseline line already summarises the start
                logger.info(f"[QIANNIU-MEM] new message object: dir="
                            f"{'IN' if any(c is cand for c in incoming) else 'OUT'} "
                            f"({_direction_reason(cand, seller)}) uid={cand.uid!r} msg={cand.msg_id!r} "
                            f"msgType={(cand.raw or {}).get('msgType')!r} "
                            f"sendTime={cand.send_time} text={cand.text[:30]!r}")
        if not candidates:
            return False
        if seller != self._last_seller:
            self._last_seller = seller
            logger.info(f"[QIANNIU-MEM] seller id in memory: {seller!r} "
                        f"(None = not resolvable; direction then comes from ccode/sendStatus)")

        # Cold start: what is in memory on the FIRST pass is history (already
        # answered, or not ours to answer now). Mark it seen without dispatching
        # -- otherwise the first scan replies to every old buyer message at once.
        # Taken once, on the first successful pass even if it found nothing
        # (_scan_pass); a message sent after this run started is never history.
        # (0.9.99ya took it on the first pass WITH messages, so the first real
        # new message of an empty start was swallowed -- alpha 2026-10-07.)
        if not self._baselined:
            self._baselined = True
            seen_now, kept = 0, []
            for cand in incoming:
                if self._is_fresh(cand):
                    kept.append(cand)      # a new turn: dispatched below
                    continue
                if self._first_time(item_for(cand, seller)["identity_key"]):
                    seen_now += 1
            self.stats["baseline_seen"] += seen_now
            sample = [(c.uid, c.text[:20], c.send_time) for c in incoming[-3:]]
            logger.info(f"[QIANNIU-MEM] baseline: {seen_now} buyer message(s) already in memory "
                        f"marked seen, NOT answered; {len(kept)} sent after start will be "
                        f"answered (latest uid/text/sendTime: {sample})")

        to_learn = []
        for cand in incoming:
            item = item_for(cand, seller)
            # The product the buyer is looking at -- the front-desk prep passes
            # it to Q&A as "[商品卡片] …" (飞鸽's format). latest_message stays the
            # buyer's own text: the send check matches it on screen.
            item["product_card"] = self.product_for(item["customer_id"])
            if not self._first_time(item["identity_key"]):
                continue
            if _is_system_notice(cand.text):
                # 「当前用户来自 商品详情页」 carries the product the buyer is
                # looking at; keep it for their next question (yp alpha: the
                # notice was dropped whole, the question went out product=None,
                # and Q&A asked for a card the buyer had already sent).
                notice_product = mem_locator.extract_product(cand.raw or {})
                if notice_product:
                    self._note_product({"product": notice_product, "sender": item["customer_id"],
                                        "sendTime": cand.send_time}, seller)
                    logger.info(f"[QIANNIU-MEM] product from notice for buyer={item['customer_name']!r}: "
                                f"{notice_product[:60]!r}")
                elif "当前用户来自" in (cand.text or ""):
                    logger.info(f"[QIANNIU-MEM] notice without a readable product; raw keys="
                                f"{sorted((cand.raw or {}).keys())[:20]}")
                self.stats["system_notice_skipped"] = self.stats.get("system_notice_skipped", 0) + 1
                logger.info(f"[QIANNIU-MEM] skip 千牛 system notice msg={item['msg_id']!r} "
                            f"msgType={(cand.raw or {}).get('msgType')!r}: {item['last_message'][:30]!r}")
                continue
            if self._is_stale(cand):
                self.stats["stale_skipped"] += 1
                logger.info(f"[QIANNIU-MEM] skip stale buyer={item['customer_name']!r} "
                            f"msg={item['msg_id']!r} sendTime={cand.send_time} "
                            f"(before this run started): {item['last_message'][:30]!r}")
                continue
            self.stats["new_incoming"] += 1
            # Learn an unknown buyer's display name from the screen AFTER
            # dispatching: the learn pass is a ~6-8 s OCR, and it used to delay
            # every new buyer's first message by that much (alpha 2026-10-07).
            # The send identifies the chat by the message text, not the name.
            if not item["customer_display_name"]:
                to_learn.append((item["customer_name"], item["last_message"]))
            key = item["identity_key"]
            retrying = key in self._nobody_since
            try:
                n = self._dispatch(item)
                if n or not retrying:
                    self.stats["dispatched"] += 1
                    logger.info(f"[QIANNIU-MEM] dispatched buyer={item['customer_name']!r} "
                                f"name={item['customer_display_name']!r} msg={item['msg_id']!r} "
                                f"sendTime={cand.send_time} to {n} runner(s)"
                                f"{' (retry)' if retrying else ''}: {item['last_message'][:40]!r}"
                                f" product={item['product_card'][:60] or None!r}")
                if n:
                    self._nobody_since.pop(key, None)
                    self._note_dispatched_text(item["last_message"])
                    continue
                # Nobody listening yet -- at startup the observer is up before the
                # front desk registers its rule (alpha 2026-10-07: the first message
                # went to 0 runners and was never answered). Un-see it so the next
                # scans retry, for up to _NOBODY_RETRY_S.
                first = self._nobody_since.setdefault(key, time.time())
                if time.time() - first < _NOBODY_RETRY_S:
                    self._seen.pop(key, None)
                    if not retrying:
                        logger.warning(f"[QIANNIU-MEM] no agent runner received it yet; retrying for "
                                       f"{_NOBODY_RETRY_S:.0f}s (front desk still starting?)")
                else:
                    self._nobody_since.pop(key, None)
                    self.stats["dispatched_to_nobody"] += 1
                    logger.warning(f"[QIANNIU-MEM] no agent runner received msg={item['msg_id']!r} in "
                                   f"{_NOBODY_RETRY_S:.0f}s -- is the 天猫客服 front desk deployed and running?")
            except Exception as exc:
                logger.warning(f"[QIANNIU-MEM] dispatch failed: {exc}")
        # The front desk's reply prep reads the name from name_map later.
        for sender_id, text in to_learn:
            self._learn_pass(sender_id, text)
        return True

    def _scan_pass(self) -> None:
        """One poll: find the 千牛 processes, scan the one holding messages."""
        pids = _qianniu_pids()
        if pids != self._pids:
            # INFO on change only: a silent observer must be tellable from an absent 千牛.
            if pids:
                logger.info(f"[QIANNIU-MEM] 千牛 processes: root={pids[0]} others={pids[1:]}")
            else:
                logger.info("[QIANNIU-MEM] 千牛 (AliWorkbench) not running; waiting")
            self._pids = pids
        order = ([self._hit_pid] if self._hit_pid in pids else []) + \
            [p for p in pids if p != self._hit_pid]
        self._pass_ok = False
        try:
            for pid in order:
                if self._scan_once(pid):
                    if pid != self._hit_pid:
                        logger.info(f"[QIANNIU-MEM] chat messages found in pid {pid}")
                        self._hit_pid = pid
                    return
            if pids and self._hit_pid:
                logger.info(f"[QIANNIU-MEM] no chat messages in any 千牛 process this pass "
                            f"(were in pid {self._hit_pid})")
                self._hit_pid = 0
        finally:
            # The first pass that read 千牛 without error IS the baseline, even
            # when it found no buyer message: everything after it is new.
            if not self._baselined and self._pass_ok:
                self._baselined = True
                logger.info("[QIANNIU-MEM] baseline: 0 buyer messages in memory at start; "
                            "every new buyer message from now on is answered")
            if self._baselined and not self._cold_started:
                self._cold_started = True
                self._start_cold_sweep()

    # ── Cold start: chats already waiting when eCan started ─────────────────
    def _note_dispatched_text(self, text: str) -> None:
        self._dispatched_texts.append((_norm_text(text), time.time()))
        del self._dispatched_texts[:-200]

    def _already_handled(self, _name: str, text: str) -> bool:
        """True if the memory path dispatched this text (same 6-char prefix)
        in the last 30 min -- the sweep must not answer it a second time."""
        probe, cutoff = _preview_core(text)[:6], time.time() - 1800
        return bool(probe) and any(t.startswith(probe) or probe.startswith(t[:6])
                                   for t, ts in self._dispatched_texts if ts >= cutoff and t)

    def _cold_dispatch(self, name: str, text: str) -> None:
        """Dispatch a waiting chat found on screen. The memory sender id is
        unknown for it; the learned one is used when the name maps to one."""
        uid = name_map.id_for(name) or f"qnname:{name}"
        msg_id = f"cold:{uid}:{_norm_text(text)[:24]}"
        item = {
            "customer_name": uid, "name": uid, "session_id": uid, "customer_id": uid, "talk_id": uid,
            "customer_display_name": name,
            "last_message": text, "latest_message": text,
            "msg_id": msg_id, "latest_message_msg_id": msg_id,
            "identity_key": f"{uid}|{msg_id}", "unread_badge": "1",
            "source": "qianniu_coldstart", "message_kind": "text",
            "product_card": self.product_for(uid),
        }
        for attempt in range(1, 13):           # the front desk may still be starting
            n = self._dispatch(item)
            if n:
                self._note_dispatched_text(text)
                logger.info(f"[QIANNIU-COLD] dispatched buyer={name!r} (id {uid!r}) to {n} runner(s): "
                            f"{text[:40]!r} product={item['product_card'][:60] or None!r}")
                return
            time.sleep(10)
        logger.warning(f"[QIANNIU-COLD] no agent runner took buyer={name!r}'s waiting message in 120 s")

    def _start_cold_sweep(self) -> None:
        if os.environ.get("ECAN_QIANNIU_COLDSTART", "1") == "0":
            logger.info("[QIANNIU-COLD] cold-start sweep off (ECAN_QIANNIU_COLDSTART=0)")
            return

        def run():
            if self._stop.wait(_COLD_SWEEP_DELAY_S):
                return
            # Wait for the 天猫 front desk to route 千牛 events: answering a waiting
            # chat before it listens loses the message (yo alpha).
            waited = 0.0
            while not route_ready() and waited < 180:
                if self._stop.wait(5):
                    return
                waited += 5
            logger.info(f"[QIANNIU-COLD] front desk {'ready' if route_ready() else 'NOT ready'} "
                        f"after {waited:.0f}s; sweeping")
            try:
                from agent.mcp.server.qianniu.qianniu_tools import cold_start_sweep
                cold_start_sweep(self._cold_dispatch, self._already_handled)
            except Exception as exc:
                logger.warning(f"[QIANNIU-COLD] sweep failed: {exc}")
            self._backstop_loop()
        threading.Thread(target=run, name="qianniu-coldstart", daemon=True).start()
        logger.info(f"[QIANNIU-COLD] cold-start sweep in {_COLD_SWEEP_DELAY_S:.0f}s: chats that were "
                    f"already waiting are read from the screen")

    def _backstop_loop(self) -> None:
        """List-only OCR every ECAN_QIANNIU_BACKSTOP_S: answers a buyer message
        the memory observer never saw (see qianniu_tools.backstop_sweep)."""
        interval = _backstop_interval_s()
        if interval <= 0:
            logger.info("[QIANNIU-BACKSTOP] off (ECAN_QIANNIU_BACKSTOP_S=0)")
            return
        logger.info(f"[QIANNIU-BACKSTOP] on: 正在接待 list checked every {interval:.0f}s")
        from agent.mcp.server.qianniu.qianniu_tools import backstop_sweep
        checked: set = set()
        while not self._stop.wait(interval):
            if not route_ready():
                continue
            try:
                backstop_sweep(self._cold_dispatch, self._already_handled,
                               _is_our_send_preview, checked)
            except Exception as exc:
                logger.warning(f"[QIANNIU-BACKSTOP] pass failed: {exc}")
            if len(checked) > 500:
                checked.clear()

    def _heartbeat(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat >= _HEARTBEAT_S:
            self._last_heartbeat = now
            ms = self._scan_ms
            timing = (f"scan_ms avg={sum(ms) // len(ms)} max={max(ms)}" if ms else "scan_ms n/a")
            logger.info(f"[QIANNIU-MEM] heartbeat pids={self._pids} msg_pid={self._hit_pid or None} "
                        f"{timing} stats={self.stats} last_scan={self.last_scan}")

    def _loop(self) -> None:
        logger.info(f"[QIANNIU-MEM] observer loop started (poll {_poll_interval_s()}s, "
                    f"learn={'on' if learn_enabled() else 'off'})")
        while not self._stop.is_set():
            try:
                self._scan_pass()
            except Exception as exc:
                self.stats["scan_errors"] += 1
                logger.warning(f"[QIANNIU-MEM] scan error: {exc}")
            self._heartbeat()
            self._stop.wait(_poll_interval_s())
        logger.info(f"[QIANNIU-MEM] observer loop stopped: {self.stats}")

    def start(self) -> bool:
        if not mem.available():
            logger.warning("[QIANNIU-MEM] process-memory reading unavailable on this OS; observer not started")
            return False
        if self._thread and self._thread.is_alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="QianniuMemObserver", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()


_OBSERVER = QianniuMemObserver()


def get_observer() -> QianniuMemObserver:
    return _OBSERVER


def observer_enabled() -> bool:
    return os.environ.get("ECAN_QIANNIU_OBSERVER", "1") != "0"
