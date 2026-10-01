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
    """Background memory-scan → attribute → dispatch loop."""

    def __init__(self, dispatch_fn=None):
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._last_learn = 0.0
        # Override for tests / the reliability gate; defaults to the real
        # agent-pipeline injection.
        self._dispatch = dispatch_fn or inject_item
        self.stats = {"scans": 0, "candidates": 0, "dispatched": 0, "learned": 0}

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
            return
        self._last_learn = now
        try:
            from agent.mcp.server.qianniu import qianniu_ocr
            ocr_data = qianniu_ocr.ocr_qianniu_window()
            if not ocr_data or not qianniu_ocr.transcript_contains(ocr_data, text):
                return
            name = qianniu_ocr.read_header_name(ocr_data)
            if name and name_map.learn(sender_id, name):
                self.stats["learned"] += 1
        except Exception as exc:
            logger.debug(f"[QIANNIU-MEM] learn pass skipped: {exc}")

    def _scan_once(self, pid: int) -> None:
        self.stats["scans"] += 1
        candidates: list = []
        for data in mem.scan_strings(pid, mem_locator.region_has_messages):
            candidates.extend(mem_locator.extract_candidates(data))
        if not candidates:
            return
        self.stats["candidates"] += len(candidates)
        seller = mem_locator.seller_id_of(candidates)
        for cand in candidates:
            # Skip seller's own outgoing messages: a candidate whose only id is
            # the seller id is not a buyer turn.
            if seller and cand.sender_ids == {seller}:
                continue
            item = item_for(cand, seller)
            if not self._first_time(item["identity_key"]):
                continue
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
                            f"to {n} runner(s): {item['last_message'][:40]!r}")
            except Exception as exc:
                logger.warning(f"[QIANNIU-MEM] dispatch failed: {exc}")

    def _loop(self) -> None:
        logger.info("[QIANNIU-MEM] observer loop started")
        while not self._stop.is_set():
            try:
                pid = mem.find_pid_by_process_name(_PROC_NAME) or 0
                if pid:
                    self._scan_once(pid)
                else:
                    logger.debug("[QIANNIU-MEM] AliWorkbench not running; idle")
            except Exception as exc:
                logger.warning(f"[QIANNIU-MEM] scan error: {exc}")
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
