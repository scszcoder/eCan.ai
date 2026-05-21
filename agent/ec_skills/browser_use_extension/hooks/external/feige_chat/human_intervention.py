"""Human-intervention state tracking (mt017, 2026-05-21).

When the human customer-service agent jumps into Feige and types a reply
directly to a customer, eCan must:

1. **Detect it** — agent bubble appears that we did NOT type ourselves
   (i.e., not in :mod:`dispatch_state.recent_agent_replies_by_customer`)
2. **Abort if in-flight** — cancel any pending placeholder timer for that
   customer and skip any Q&A bot reply that arrives later (already
   answered by human)
3. **No-op if our reply already typed** — too late to take back; just
   record the human action so future turns know

This module owns the state.  Detection lives in
``pre_dispatch_enrich.enrich_item`` (which already scrapes the chat
thread); the abort hook fires automatically when the customer is marked
handled (direct-delivery worker + PreDispatch consult
``is_human_handled_recent`` before doing work).
"""
from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger("eCan")

# Per-customer "human typed a reply at this wall-clock" timestamps.
# TTL keeps the state bounded; after expiry, the customer's automation
# resumes.  A second human reply re-stamps the entry.
_HUMAN_HANDLED_AT: dict[str, float] = {}
# Optional: the agent-bubble msg_id we observed as human-typed (for
# diagnostic and to suppress detection from re-firing on the same bubble
# in subsequent scrapes).
_HUMAN_HANDLED_MSG_ID: dict[str, str] = {}
HUMAN_HANDLED_TTL_S: float = 120.0

_LOCK = threading.Lock()


def mark_handled(
    customer_key: str,
    msg_id: str = "",
    *,
    source: str = "",
) -> None:
    """Record that a human typed a reply for ``customer_key``.

    Called from the chat-thread scraper when it detects an agent bubble
    whose text isn't in our recent-agent-reply ledger.  Idempotent —
    re-marking the same customer just refreshes the timestamp.
    """
    if not customer_key:
        return
    cust = str(customer_key)
    now = time.time()
    with _LOCK:
        _HUMAN_HANDLED_AT[cust] = now
        if msg_id:
            _HUMAN_HANDLED_MSG_ID[cust] = str(msg_id)
    logger.info(
        f"[HUMAN-INTERVENTION] cust={cust!r} marked human-handled "
        f"msg_id=...{(msg_id or '')[-8:]} source={source!r} "
        f"ttl={HUMAN_HANDLED_TTL_S}s"
    )


def is_handled_recent(customer_key: str) -> bool:
    """Returns True if a human reply was detected for ``customer_key``
    within the last ``HUMAN_HANDLED_TTL_S`` seconds."""
    if not customer_key:
        return False
    with _LOCK:
        ts = _HUMAN_HANDLED_AT.get(str(customer_key), 0.0)
    if ts <= 0.0:
        return False
    return (time.time() - ts) <= HUMAN_HANDLED_TTL_S


def get_handled_msg_id(customer_key: str) -> str:
    """Returns the msg_id of the most-recently-observed human bubble for
    this customer (within TTL), or empty string."""
    if not customer_key:
        return ""
    if not is_handled_recent(customer_key):
        return ""
    with _LOCK:
        return _HUMAN_HANDLED_MSG_ID.get(str(customer_key), "")


def clear(customer_key: str) -> None:
    """Manually clear a customer's human-handled state.  Useful if the
    operator wants to resume automation immediately rather than waiting
    for TTL to expire."""
    if not customer_key:
        return
    cust = str(customer_key)
    with _LOCK:
        _HUMAN_HANDLED_AT.pop(cust, None)
        _HUMAN_HANDLED_MSG_ID.pop(cust, None)


def snapshot() -> dict:
    """JSON-safe snapshot for diagnostics / IPC."""
    now = time.time()
    cutoff = now - HUMAN_HANDLED_TTL_S
    with _LOCK:
        return {
            "ttl_s": HUMAN_HANDLED_TTL_S,
            "active": {
                cust: {
                    "ts": ts,
                    "age_s": round(now - ts, 1),
                    "msg_id": _HUMAN_HANDLED_MSG_ID.get(cust, ""),
                }
                for cust, ts in _HUMAN_HANDLED_AT.items()
                if ts >= cutoff
            },
        }


__all__ = [
    "HUMAN_HANDLED_TTL_S",
    "mark_handled",
    "is_handled_recent",
    "get_handled_msg_id",
    "clear",
    "snapshot",
]
