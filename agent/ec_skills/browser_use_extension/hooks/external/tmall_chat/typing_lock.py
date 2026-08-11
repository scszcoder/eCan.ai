"""Process-wide typing lock for Qianniu DOM sends.

Lean Phase 1 port of the Feige typing-lock concept: every DOM
type-and-send is serialized through one asyncio lock so two concurrent
replies can never interleave keystrokes into the same compose box (the
Qianniu workbench, like Feige, is one SPA with one active thread).

Interface mirrors the subset ``site_tools`` needs.  The lock carries an
owner label + acquisition timestamp for diagnosability, and a TTL
breaker: if a holder has kept it past ``ECAN_TMALL_TYPING_LOCK_TTL_S``
(default 30 s — a dead coroutine, not a slow send), the next acquirer
steals it rather than deadlocking the send lane.

Feige lesson respected (ws175 dispatch-lock deadlock): everything here is
``asyncio``-native — no ``threading.Lock`` is ever held across an await,
and nothing synchronous blocks the CDP-handler loop.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Optional

from utils.logger_helper import logger_helper as logger

_lock = asyncio.Lock()
_owner: str = ""
_acquired_at: float = 0.0

_DEFAULT_TTL_S = 30.0


def _ttl_s() -> float:
    try:
        return float(os.environ.get("ECAN_TMALL_TYPING_LOCK_TTL_S", "") or _DEFAULT_TTL_S)
    except (TypeError, ValueError):
        return _DEFAULT_TTL_S


def holder() -> str:
    """Current owner label ('' when free)."""
    return _owner if _lock.locked() else ""


async def acquire(owner: str, timeout_s: float = 10.0) -> bool:
    """Acquire the typing lock; True on success.

    On timeout, if the current holder has exceeded the TTL, the lock is
    presumed leaked and stolen (logged loudly); otherwise returns False.
    """
    global _owner, _acquired_at
    try:
        await asyncio.wait_for(_lock.acquire(), timeout=timeout_s)
        _owner, _acquired_at = str(owner or "?"), time.monotonic()
        return True
    except asyncio.TimeoutError:
        held_for = time.monotonic() - _acquired_at if _acquired_at else 0.0
        if _lock.locked() and held_for > _ttl_s():
            logger.warning(
                f"[TMALL-TYPING-LOCK] stealing lock from {_owner!r} "
                f"(held {held_for:.1f}s > ttl {_ttl_s():.0f}s) for {owner!r}"
            )
            _owner, _acquired_at = str(owner or "?"), time.monotonic()
            return True
        logger.warning(
            f"[TMALL-TYPING-LOCK] acquire timeout after {timeout_s:.1f}s "
            f"(holder={_owner!r} held {held_for:.1f}s) for {owner!r}"
        )
        return False


def release(owner: str) -> None:
    """Release the lock if *owner* still holds it (steal-safe)."""
    global _owner, _acquired_at
    if not _lock.locked():
        return
    if _owner and owner and _owner != owner:
        # Lock was stolen from us after a TTL breach — the thief owns it now.
        logger.debug(
            f"[TMALL-TYPING-LOCK] release skipped: {owner!r} no longer owner "
            f"(current={_owner!r})"
        )
        return
    _owner, _acquired_at = "", 0.0
    try:
        _lock.release()
    except RuntimeError:
        pass
