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


def inject_item(item: dict, target_agent_id: str = "") -> int:
    """Emit the browser-event envelope and dispatch to agent runners.

    Returns the number of runners reached (0 if none / app not up yet).
    """
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
        self._started_ms = int(time.time() * 1000)
        self._last_heartbeat = 0.0
        self._last_seller = None

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
            if name_map.learn(sender_id, name):
                self.stats["learned"] += 1
                logger.info(f"[QIANNIU-MEM] learned buyer={sender_id!r} -> name={name!r}")
        except Exception as exc:
            logger.warning(f"[QIANNIU-MEM] learn pass failed for buyer={sender_id!r}: {exc}")

    def _is_stale(self, cand) -> bool:
        """Sent before this observer started (with a minute's grace): history
        that loaded into memory later (e.g. a conversation the seller opened),
        not a new buyer turn."""
        st = cand.send_time
        if not isinstance(st, int) or st <= 0:
            return False
        ms = st if st > 10 ** 12 else st * 1000
        return ms < self._started_ms - 60_000

    def _scan_once(self, pid: int) -> bool:
        """Scan one process; True when it holds chat messages."""
        self.stats["scans"] += 1
        t0 = time.monotonic()
        mstats: dict = {}
        xstats: dict = {}
        candidates: list = []
        try:
            for data in mem.scan_strings(pid, mem_locator.region_has_messages, stats=mstats):
                candidates.extend(mem_locator.extract_candidates(data, stats=xstats))
        except OSError as exc:
            self.stats["scan_errors"] += 1
            if pid not in self._open_failed:
                self._open_failed.add(pid)
                logger.warning(f"[QIANNIU-MEM] cannot read pid {pid}: {exc} "
                               f"(logged once per pid; access denied = eCan needs the same "
                               f"or higher privilege than 千牛)")
            return False
        ms = int((time.monotonic() - t0) * 1000)
        self._scan_ms = (self._scan_ms + [ms])[-100:]
        seller = mem_locator.seller_id_of(candidates) if candidates else None
        incoming = [c for c in candidates if mem_locator.is_incoming(c, seller)]
        self.last_scan = {"pid": pid, "ms": ms, **mstats,
                          "extract": {k: v for k, v in xstats.items() if k != "sample_no_text_keys"},
                          "candidates": len(candidates), "incoming_in_memory": len(incoming),
                          "outgoing_in_memory": len(candidates) - len(incoming)}
        if pid not in self._scanned_pids:
            self._scanned_pids.add(pid)
            logger.info(f"[QIANNIU-MEM] first scan of pid {pid}: {self.last_scan}"
                        + (f" no_text example keys={xstats['sample_no_text_keys']}"
                           if xstats.get("sample_no_text_keys") else ""))
        if not candidates:
            return False
        if seller != self._last_seller:
            self._last_seller = seller
            logger.info(f"[QIANNIU-MEM] seller id in memory: {seller!r} "
                        f"(None = not resolvable; direction then comes from ccode/sendStatus)")

        # Cold start: what is already in memory is history (already answered or
        # not ours to answer now). Mark it seen without dispatching -- otherwise
        # the first scan replies to every old buyer message at once.
        if not self._baselined:
            self._baselined = True
            fresh = 0
            for cand in incoming:
                if self._first_time(item_for(cand, seller)["identity_key"]):
                    fresh += 1
            self.stats["baseline_seen"] += fresh
            sample = [(c.uid, c.text[:20]) for c in incoming[-3:]]
            logger.info(f"[QIANNIU-MEM] baseline: {fresh} buyer message(s) already in memory "
                        f"marked seen, NOT answered (latest: {sample})")
            return True

        for cand in incoming:
            item = item_for(cand, seller)
            if not self._first_time(item["identity_key"]):
                continue
            if self._is_stale(cand):
                self.stats["stale_skipped"] += 1
                logger.info(f"[QIANNIU-MEM] skip stale buyer={item['customer_name']!r} "
                            f"msg={item['msg_id']!r} sendTime={cand.send_time} "
                            f"(before this run started): {item['last_message'][:30]!r}")
                continue
            self.stats["new_incoming"] += 1
            # Opportunistically learn this buyer's display name from the screen
            # (throttled) so hands-off conversation-open works later.
            if not item["customer_display_name"]:
                self._learn_pass(item["customer_name"], item["last_message"])
                learned = name_map.name_for(item["customer_name"])
                if learned:
                    item["customer_display_name"] = learned
            try:
                n = self._dispatch(item)
                self.stats["dispatched"] += 1
                logger.info(f"[QIANNIU-MEM] dispatched buyer={item['customer_name']!r} "
                            f"name={item['customer_display_name']!r} msg={item['msg_id']!r} "
                            f"sendTime={cand.send_time} to {n} runner(s): {item['last_message'][:40]!r}")
                if not n:
                    self.stats["dispatched_to_nobody"] += 1
                    logger.warning("[QIANNIU-MEM] no agent runner received it -- is the 天猫客服 "
                                   "front desk deployed and running?")
            except Exception as exc:
                logger.warning(f"[QIANNIU-MEM] dispatch failed: {exc}")
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
