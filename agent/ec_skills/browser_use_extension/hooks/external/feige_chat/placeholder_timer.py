"""Placeholder-timer guardrail (Phase 3.5, 2026-05-21).

Background
----------
Feige's seller dashboard tracks a "未回复" red-flag against the store's
performance score when a customer message goes unanswered beyond the
service-level deadline (~30 seconds).  Under heavy 20-customer floods,
even with the multi-tab pool, tail customers can wait 60s+ for the
first real Q&A reply — well past the deadline.

This module provides a guardrail: after PreDispatch dispatches a
customer's question, arm a per-(customer, source_msg_id) timer.  If
the real reply isn't typed within ``FEIGE_PLACEHOLDER_TIMEOUT_S``,
type a brief stand-by like "您好，稍等一下哦~" so Feige's red-flag
clock resets.  Re-arm up to ``FEIGE_PLACEHOLDER_MAX`` times.

Why this works (now that we have the pool)
-------------------------------------------
Pre-multitab attempts at this idea ran into typing-lock contention:
placeholders fought with real replies for the same typing-lock, so
under load placeholders were as delayed as the replies they were
supposed to prevent.

With the multi-tab pool:
* Placeholders enter the SAME direct-delivery worker queue as real
  replies and get pool-tab routing.
* Different pool tabs type concurrently, so a placeholder for
  customer X doesn't delay a real reply for customer Y.
* The pool's ``in_use`` flag is per-tab, so placeholders and real
  replies for DIFFERENT customers don't block each other.

Lifecycle
---------
1. PreDispatch dispatches customer X's question → ``arm(X, msg_id)``
2. Sweeper task ticks every ``SWEEP_INTERVAL_S`` seconds.
3. For entries past their deadline:
     - synthesize a fake reply payload with a short stand-by text
     - submit through ``runner._submit_loop_direct_delivery`` (same
       path real replies use, so pool routing kicks in)
     - increment placeholder count, set next deadline
     - stop after ``MAX`` placeholders to avoid spam
4. When direct-delivery successfully types the REAL reply, the
   runner's ``_outcome.ok = True`` branch calls ``cancel(X, msg_id)``
   to remove the entry from the timer registry.

Failure modes handled
---------------------
* Real reply never arrives (Q&A bot crashed): max=3 placeholders
  fire, then we give up silently.  Customer sees "稍等" / "再稍等" /
  "马上就好" and no more — better than no acknowledgement at all.
* Customer asks 2 questions back-to-back: each turn has its own
  (customer, source_msg_id) entry; cancelling one doesn't affect
  the other.
* Real reply was dropped due to drift / bypass: placeholders still
  fire on schedule, giving the user feedback while drift_recovery_signal
  retries the real delivery.

Adapting to other platforms
---------------------------
The text variations (``_PLACEHOLDER_TEXTS``) are Chinese, tuned for
Feige's customer base.  For another platform, copy this module and
swap the text list.  The mechanism (per-turn timer registry + periodic
sweep + queue-submit) is platform-agnostic.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("eCan")


# Different text per attempt so the recent-sends dedup cache doesn't
# suppress the second/third attempt as a near-duplicate.  Ordered by
# escalation tone: gentle → reassuring → apologetic.
_PLACEHOLDER_TEXTS = [
    "您好，稍等一下哦~",
    "再稍等一下，马上回复",
    "实在抱歉，正在为您查询",
]


@dataclass
class _TimerEntry:
    customer_key: str
    source_msg_id: str
    armed_at: float
    deadline_at: float
    placeholders_typed: int = 0
    cancelled: bool = False


# Module-level registry — process-wide
_REGISTRY: dict[tuple[str, str], _TimerEntry] = {}
_REGISTRY_LOCK = threading.Lock()


def _make_key(customer_key: str, source_msg_id: str) -> tuple[str, str]:
    """Key by (customer, source_msg_id).  Source_msg_id may be empty —
    that's still a valid key since the same customer's earlier turn
    (with a different/no msg_id) is tracked separately."""
    return (str(customer_key or ""), str(source_msg_id or ""))


def arm(customer_key: str, source_msg_id: str = "", *, timeout_s: float) -> None:
    """Record a dispatched turn so the sweeper can fire a placeholder
    if its deadline passes without a real reply.

    Called by PreDispatch right after it confirms the question went
    out to the Q&A bot.  Idempotent — re-arming the same key resets
    the deadline (useful for multi-attempt drift recovery).
    """
    if not customer_key or timeout_s <= 0:
        return
    now = time.time()
    key = _make_key(customer_key, source_msg_id)
    with _REGISTRY_LOCK:
        entry = _REGISTRY.get(key)
        if entry is None:
            entry = _TimerEntry(
                customer_key=str(customer_key),
                source_msg_id=str(source_msg_id or ""),
                armed_at=now,
                deadline_at=now + timeout_s,
            )
            _REGISTRY[key] = entry
        else:
            # Re-arm: reset deadline but preserve placeholder count so
            # we don't spam endlessly on rapid re-dispatch.
            entry.deadline_at = now + timeout_s
            entry.cancelled = False
    logger.debug(
        f"[placeholder_timer] armed cust={customer_key!r} "
        f"source_msg_id={source_msg_id!r} timeout={timeout_s}s"
    )


def cancel(customer_key: str, source_msg_id: str = "") -> bool:
    """Cancel the timer for ``(customer_key, source_msg_id)``.

    Called by the direct-delivery worker when the real reply succeeds.
    Returns True if a timer was active.
    """
    if not customer_key:
        return False
    key = _make_key(customer_key, source_msg_id)
    with _REGISTRY_LOCK:
        entry = _REGISTRY.pop(key, None)
    if entry is not None:
        elapsed = time.time() - entry.armed_at
        logger.debug(
            f"[placeholder_timer] cancelled cust={customer_key!r} "
            f"source_msg_id={source_msg_id!r} "
            f"elapsed={elapsed:.1f}s "
            f"placeholders_typed={entry.placeholders_typed}"
        )
        return True
    return False


def cancel_any_for_customer(customer_key: str) -> int:
    """Cancel ALL timers for ``customer_key`` regardless of source_msg_id.

    Useful when source_msg_id is unknown at cancel time (e.g., the
    reply payload doesn't carry it back).  Returns count cancelled.
    """
    if not customer_key:
        return 0
    cancelled = 0
    with _REGISTRY_LOCK:
        for k in list(_REGISTRY.keys()):
            if k[0] == customer_key:
                _REGISTRY.pop(k, None)
                cancelled += 1
    if cancelled:
        logger.debug(
            f"[placeholder_timer] cancelled {cancelled} timers for "
            f"cust={customer_key!r}"
        )
    return cancelled


@dataclass
class ExpiredEntry:
    customer_key: str
    source_msg_id: str
    placeholders_typed: int
    placeholder_text: str  # next text to type
    is_final: bool         # True if this will be the LAST placeholder


def claim_expired(
    *,
    max_placeholders: int,
    rearm_s: float,
) -> list[ExpiredEntry]:
    """Atomically claim entries whose deadline has passed.

    Returns the entries to type as placeholders.  Each claimed entry's
    deadline is bumped by ``rearm_s`` and its placeholder count is
    incremented in-place; if the new count reaches ``max_placeholders``,
    the entry is removed from the registry (no more placeholders will
    fire — the customer either gets the real reply or stays silent).
    """
    now = time.time()
    out: list[ExpiredEntry] = []
    with _REGISTRY_LOCK:
        for k, entry in list(_REGISTRY.items()):
            if entry.cancelled or entry.deadline_at > now:
                continue
            if entry.placeholders_typed >= max_placeholders:
                # Exhausted — remove silently
                _REGISTRY.pop(k, None)
                continue
            text_idx = min(entry.placeholders_typed, len(_PLACEHOLDER_TEXTS) - 1)
            text = _PLACEHOLDER_TEXTS[text_idx]
            entry.placeholders_typed += 1
            entry.deadline_at = now + rearm_s
            is_final = entry.placeholders_typed >= max_placeholders
            out.append(
                ExpiredEntry(
                    customer_key=entry.customer_key,
                    source_msg_id=entry.source_msg_id,
                    placeholders_typed=entry.placeholders_typed,
                    placeholder_text=text,
                    is_final=is_final,
                )
            )
            if is_final:
                # Remove now — caller will type but we won't fire again
                _REGISTRY.pop(k, None)
    return out


def snapshot() -> dict:
    """Return a JSON-safe snapshot for diagnostics / IPC."""
    with _REGISTRY_LOCK:
        return {
            "size": len(_REGISTRY),
            "entries": [
                {
                    "customer": e.customer_key,
                    "source_msg_id": e.source_msg_id,
                    "armed_at": e.armed_at,
                    "deadline_at": e.deadline_at,
                    "placeholders_typed": e.placeholders_typed,
                }
                for e in _REGISTRY.values()
            ],
        }


async def sweep_loop_async(
    *,
    timeout_s: float,
    max_placeholders: int,
    rearm_s: float,
    interval_s: float,
    placeholder_submitter,
) -> None:
    """Background coroutine — periodically checks for expired timers
    and submits placeholder sends via ``placeholder_submitter``.

    ``placeholder_submitter(customer_key, source_msg_id, text)`` is a
    callable that submits a synthetic reply through the same path real
    replies use (the runner's direct-delivery submit).  Wired in
    ``dom_assets`` at pool-init time so this module stays free of
    runner.py imports (avoiding circular deps).

    Quietly exits if cancelled (e.g., on app shutdown).
    """
    import asyncio as _asyncio

    if timeout_s <= 0 or interval_s <= 0:
        logger.info(
            "[placeholder_timer] sweeper not started — timeout=%s interval=%s",
            timeout_s, interval_s,
        )
        return
    logger.info(
        f"[placeholder_timer] sweeper started: timeout={timeout_s}s "
        f"max={max_placeholders} rearm={rearm_s}s interval={interval_s}s"
    )
    while True:
        try:
            await _asyncio.sleep(interval_s)
            expired = claim_expired(
                max_placeholders=max_placeholders, rearm_s=rearm_s
            )
            for entry in expired:
                try:
                    submitted = placeholder_submitter(
                        entry.customer_key,
                        entry.source_msg_id,
                        entry.placeholder_text,
                    )
                    logger.info(
                        f"[placeholder_timer] fired placeholder #{entry.placeholders_typed}"
                        f"{' (FINAL)' if entry.is_final else ''} "
                        f"cust={entry.customer_key!r} "
                        f"text={entry.placeholder_text!r} "
                        f"submitted={submitted}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[placeholder_timer] placeholder submit failed for "
                        f"cust={entry.customer_key!r}: {e}"
                    )
        except _asyncio.CancelledError:
            logger.info("[placeholder_timer] sweeper cancelled")
            return
        except Exception as e:
            logger.warning(f"[placeholder_timer] sweep tick failed: {e}")


__all__ = [
    "arm",
    "cancel",
    "cancel_any_for_customer",
    "claim_expired",
    "snapshot",
    "sweep_loop_async",
    "ExpiredEntry",
]
