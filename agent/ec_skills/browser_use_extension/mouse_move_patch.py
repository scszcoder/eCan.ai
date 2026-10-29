"""Do not wait for Chrome to acknowledge a mouse move.

Chrome answers ``Input.dispatchMouseEvent(type=mouseMoved)`` only once the
page draws a frame, and a background tab draws none: the answer comes after
~5.2 s (KEN 2026-10-30, any page, with or without listeners). browser-use moves
the mouse before every click and awaits that answer with no timeout, so every
click in a tab behind the store's chat page took 5.9 s instead of ~0.6 s. The
move is still delivered, in order, before the press that follows; only the
wait is cut short.
"""
from __future__ import annotations

import asyncio

from utils.logger_helper import logger_helper as logger

MOVE_ACK_WAIT_S = 0.3
_installed = False


def install() -> bool:
    """Patch cdp_use's InputClient once. False when cdp_use is not importable."""
    global _installed
    if _installed:
        return True
    try:
        from cdp_use.cdp.input.library import InputClient
    except Exception as exc:
        logger.warning(f"[mouse-move-patch] cdp_use not importable: {exc}")
        return False
    original = InputClient.dispatchMouseEvent

    async def dispatchMouseEvent(self, params, session_id=None):
        if (params or {}).get("type") != "mouseMoved":
            return await original(self, params, session_id=session_id)
        sent = asyncio.ensure_future(original(self, params, session_id=session_id))
        try:
            return await asyncio.wait_for(asyncio.shield(sent), MOVE_ACK_WAIT_S)
        except asyncio.TimeoutError:
            # The late answer (or error) is collected and dropped.
            sent.add_done_callback(lambda t: t.cancelled() or t.exception())
            return {}

    InputClient.dispatchMouseEvent = dispatchMouseEvent
    _installed = True
    return True
