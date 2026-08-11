"""ws048: WS inbound-message watchdog backstop.

A WS frame is authoritative proof a real customer message arrived.  The
WS-DIRECT-QA dispatch (event_monitor `_ws_dispatch_fn` -> fire-and-forget
`create_task`) can silently drop a turn under load — no dispatch, no exception,
no fallback.  Confirmed live 2026-06-11: customer 童趣科普's "是全棉的吗？出汗多
会不会闷汗" arrived 13:06:49, produced ZERO downstream activity, and was only
answered ~4 minutes later when Feige's OWN server re-pushed the unanswered
message.  Our only recovery today is Feige choosing to re-push — luck, not design.

This module is the cause-agnostic safety net: it records every WS inbound and,
if NO outgoing frame is seen for that conversation within ``_REDISPATCH_AFTER_S``,
re-dispatches it through the same WS path.

DUPLICATE-SAFETY (the other top-priority bug — must never double-answer):
  * A true silent drop has ZERO outgoing activity — neither a real reply NOR a
    placeholder ("人工服务正在回复中…") ever goes out (the placeholder is armed at
    dispatch, which never happened).  So we clear a record the instant ANY
    outgoing chat frame is seen for its talk_id.  A turn that merely produced a
    placeholder, or a slow-but-alive answer, is therefore NEVER re-dispatched.
  * ``_REDISPATCH_AFTER_S`` defaults to 45s — longer than the worst observed
    healthy turn (~37s) — so a live-but-slow turn whose placeholder *failed to
    send* still isn't re-dispatched before it completes.
  * The re-dispatch goes through the normal path, whose recent-reply ledger is a
    second line of defence against an echo/duplicate.

Gated by ECAN_FEIGE_WS_WATCHDOG=1 (default OFF).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
import logging

logger = logging.getLogger("eCan")

_lock = threading.Lock()
# key (talk_id, msg_id) -> {talk, msg_id, cust, item, ts, attempts}
_pending: dict[tuple, dict] = {}
# talk_id -> last outgoing-activity ts (ANY chat frame: real reply or placeholder)
_outgoing_at: dict[str, float] = {}

_REDISPATCH_AFTER_S = float(os.environ.get("ECAN_FEIGE_WS_WATCHDOG_AFTER", "45") or "45")
_MAX_ATTEMPTS = int(os.environ.get("ECAN_FEIGE_WS_WATCHDOG_MAX", "2") or "2")
_GIVEUP_AFTER_S = _REDISPATCH_AFTER_S * (_MAX_ATTEMPTS + 2)
_SWEEP_INTERVAL_S = 8.0
_OUTGOING_TTL_S = 600.0

_redispatch_fn = None  # set by start(); takes one positional `item` dict
_loop_task = None


def enabled() -> bool:
    return os.environ.get("ECAN_FEIGE_WS_WATCHDOG", "") == "1"


def note_inbound(item: dict) -> None:
    """Record a WS-detected inbound customer message.  Idempotent per
    (talk_id, msg_id): a re-dispatch of the same item does NOT reset its
    attempt count."""
    if not enabled() or not isinstance(item, dict):
        return
    talk = str(item.get("talk_id") or "")
    msg_id = str(item.get("msg_id") or "")
    cust = str(item.get("customer_name") or item.get("customer_id") or "")
    if not talk or not cust:
        return
    now = time.time()
    with _lock:
        key = (talk, msg_id)
        if key not in _pending:
            _pending[key] = {
                "talk": talk, "msg_id": msg_id, "cust": cust,
                "item": dict(item), "ts": now, "attempts": 0,
            }


def note_outgoing(talk_id: str) -> None:
    """Any outgoing chat frame (real reply OR placeholder) for *talk_id* means
    the turn is alive — clear its pending records so it is never re-dispatched."""
    if not enabled():
        return
    talk = str(talk_id or "")
    if not talk:
        return
    now = time.time()
    with _lock:
        _outgoing_at[talk] = now
        for key in [k for k, r in _pending.items()
                    if r["talk"] == talk and r["ts"] <= now]:
            _pending.pop(key, None)


def _collect_due(now: float) -> list[dict]:
    due: list[dict] = []
    with _lock:
        # prune stale outgoing markers
        for t in [t for t, ts in _outgoing_at.items() if now - ts > _OUTGOING_TTL_S]:
            _outgoing_at.pop(t, None)
        for key, rec in list(_pending.items()):
            # alive: an outgoing frame landed after this inbound
            if _outgoing_at.get(rec["talk"], 0.0) >= rec["ts"]:
                _pending.pop(key, None)
                continue
            age = now - rec["ts"]
            if age > _GIVEUP_AFTER_S:
                logger.warning(
                    f"[WS-WATCHDOG] giving up on unanswered turn cust={rec['cust']!r} "
                    f"talk={rec['talk']} msg={rec['msg_id']} after {age:.0f}s, "
                    f"{rec['attempts']} retries")
                _pending.pop(key, None)
                continue
            if age >= _REDISPATCH_AFTER_S and rec["attempts"] < _MAX_ATTEMPTS:
                rec["attempts"] += 1
                rec["ts"] = now
                due.append(dict(rec["item"]))
                logger.warning(
                    f"[WS-WATCHDOG] re-dispatching SILENTLY-DROPPED turn "
                    f"cust={rec['cust']!r} talk={rec['talk']} msg={rec['msg_id']} "
                    f"attempt={rec['attempts']}/{_MAX_ATTEMPTS} (no outgoing in {age:.0f}s)")
    return due


async def _loop() -> None:
    while True:
        try:
            await asyncio.sleep(_SWEEP_INTERVAL_S)
            if not enabled():
                continue
            for item in _collect_due(time.time()):
                fn = _redispatch_fn
                if fn is None:
                    continue
                try:
                    fn(item)
                except Exception as _e:
                    logger.debug(f"[WS-WATCHDOG] redispatch error: {_e}")
        except asyncio.CancelledError:
            break
        except Exception as _e:
            logger.debug(f"[WS-WATCHDOG] loop error: {_e}")


def start(loop, redispatch_fn) -> None:
    """Register the re-dispatch callback and start the sweeper on *loop*.
    No-op when disabled or already running."""
    global _redispatch_fn, _loop_task
    if not enabled():
        return
    _redispatch_fn = redispatch_fn
    if _loop_task is None or _loop_task.done():
        _loop_task = loop.create_task(_loop())
        logger.info(
            f"[WS-WATCHDOG] started (re-dispatch after {_REDISPATCH_AFTER_S:.0f}s "
            f"of zero outgoing activity, max {_MAX_ATTEMPTS} attempts)")
