"""Out-of-band signal for direct-delivery drift recovery.

When ``DIRECT-DELIVERY`` exhausts drift retries for a Q&A reply,
``pend_event_node`` preserves the response_text in ``state["input"]``
as a fallback so HOT-PATH-B can retry the typed delivery.  But it also
needs to tell HOT-PATH-B "this is not a normal ``a2a_response`` — treat
the matching payload as a ``chat_message`` so the typed-delivery rule
fires."

The natural place for that signal is the langgraph ``state`` dict, but
the langgraph state pipeline strips unknown keys between
``pend_event_node`` exit and the ``before_session_setup_hook`` entry
(confirmed live 2026-05-19 18:53 via diagnostic probe: marker present
at pend_event exit, ``marker_in_keys=False`` at HOT-PATH-B entry,
``state_id`` differs).

This module-level dict acts as the out-of-band channel.  The marker is
keyed by customer (Feige customer_name / customer_id) and consumed
one-shot by HOT-PATH-B.  TTL-evicted to prevent unbounded growth if a
mark is never consumed (e.g., HOT-PATH-B never runs for that customer
again).
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("eCan")

_LOCK = threading.Lock()
_PENDING: dict[str, dict] = {}
# TTL: long enough to survive a slow langgraph cycle + Q&A retry under
# flood (15-30s observed), short enough that a stale mark from a prior
# customer turn doesn't trigger on a fresh question minutes later.
_TTL_S = 60.0

# 2026-05-19 Bug 2 fix: recovery-in-flight tracking.  When HOT-PATH-B
# consumes a drift-recovery pending mark and forces evt_type=chat_message,
# the downstream feige_send_message flow's _verify_reply_source_turn
# (hot_path.py:484-495) can still abort with
# 'active_customer_drifted_during_source_verify' if the sidebar shuffled
# mid-flight.  Under flood that abort drops the reply (PreDispatch's
# "re-dispatch on next event" recovery rarely fires in time).  We mark
# the customer as "recovery in flight" when the override fires, and the
# source-verify check uses that signal to apply a longer wait + more
# attempts before giving up.
_RECOVERY_IN_FLIGHT: dict[str, float] = {}
_RECOVERY_IN_FLIGHT_TTL_S = 30.0


def mark_drift_recovery_pending(
    customer_key: str,
    *,
    source_msg_id: str = "",
    response_text: str = "",
) -> None:
    """Record that a drift-failed reply for ``customer_key`` needs HOT-PATH-B retry."""
    if not customer_key:
        return
    with _LOCK:
        _PENDING[customer_key] = {
            "ts": time.time(),
            "source_msg_id": source_msg_id or "",
            "response_text": response_text or "",
        }
    logger.info(
        f"[drift_recovery_signal] mark cust={customer_key!r} "
        f"source_msg_id={source_msg_id!r} len={len(response_text or '')}"
    )


def consume_drift_recovery_pending(customer_key: str) -> Optional[dict]:
    """Pop and return the pending drift-recovery record for ``customer_key``.

    Returns ``None`` if no record exists or the record is expired.  Always
    sweeps expired entries first so the dict stays bounded.
    """
    if not customer_key:
        return None
    now = time.time()
    with _LOCK:
        expired = [k for k, v in _PENDING.items() if now - v["ts"] > _TTL_S]
        for k in expired:
            _PENDING.pop(k, None)
        return _PENDING.pop(customer_key, None)


def peek_drift_recovery_pending(customer_key: str) -> Optional[dict]:
    """Non-destructive peek — useful for assertions / logging only."""
    if not customer_key:
        return None
    with _LOCK:
        return _PENDING.get(customer_key)


def mark_recovery_in_flight(customer_key: str) -> None:
    """Mark a customer as having a drift-recovery delivery in flight.

    Set by HOT-PATH-B's override block when it forces evt_type to
    ``chat_message``.  Read by ``_verify_reply_source_turn`` in
    ``hot_path.py`` to soften the active-customer-drift abort, giving
    Feige's sidebar more time to settle before declaring drift fatal.
    """
    if not customer_key:
        return
    with _LOCK:
        _RECOVERY_IN_FLIGHT[customer_key] = time.time()


def is_recovery_in_flight(customer_key: str) -> bool:
    """Return True if ``customer_key`` had a recovery override fire recently."""
    if not customer_key:
        return False
    now = time.time()
    with _LOCK:
        # Sweep expired entries
        expired = [
            k for k, ts in _RECOVERY_IN_FLIGHT.items()
            if now - ts > _RECOVERY_IN_FLIGHT_TTL_S
        ]
        for k in expired:
            _RECOVERY_IN_FLIGHT.pop(k, None)
        return customer_key in _RECOVERY_IN_FLIGHT


def clear_recovery_in_flight(customer_key: str) -> None:
    """Clear the recovery-in-flight mark (e.g. after successful delivery)."""
    if not customer_key:
        return
    with _LOCK:
        _RECOVERY_IN_FLIGHT.pop(customer_key, None)


__all__ = [
    "mark_drift_recovery_pending",
    "consume_drift_recovery_pending",
    "peek_drift_recovery_pending",
    "mark_recovery_in_flight",
    "is_recovery_in_flight",
    "clear_recovery_in_flight",
]
