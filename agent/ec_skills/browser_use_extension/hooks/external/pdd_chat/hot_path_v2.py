"""The two pieces of the direct-delivery path the platform takes from a bundle.

``agent/ec_tasks/runner.py`` builds its outcome with ``HotPathOutcomeV2`` and
waits for the typing lock with ``_acquire_typing_lock`` -- same names and
semantics as the Feige bundle, so the platform needs no site branch.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from utils.logger_helper import logger_helper as logger

TYPING_LOCK_WAIT_ATTEMPTS = 24
TYPING_LOCK_WAIT_INTERVAL_S = 0.5


@dataclass
class HotPathOutcomeV2:
    ok: bool = False
    reason: str = ""
    typing_acquired: bool = False
    last_tool_error: str = ""
    actions_attempted: int = 0
    extras: dict = field(default_factory=dict)


async def _acquire_typing_lock(typing_lock, customer_key: str, node_name: str,
                               session_key=None) -> bool:
    """Bounded wait for the reply box (~12 s), never blocking the loop.
    *session_key*: the store (its browser session) whose reply box it is."""
    if not customer_key:
        return False
    for _ in range(TYPING_LOCK_WAIT_ATTEMPTS):
        if typing_lock.try_acquire(customer_key, session_key):
            return True
        await asyncio.sleep(TYPING_LOCK_WAIT_INTERVAL_S)
    logger.warning(f"[PDD] typing lock busy for {customer_key!r} "
                   f"(holder={typing_lock.holder(session_key)!r}), node={node_name}")
    return False
