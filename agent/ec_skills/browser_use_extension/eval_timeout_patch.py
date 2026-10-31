"""A page script may not run forever.

browser-use's ``evaluate`` action sends ``Runtime.evaluate`` with no time limit.
A model-written script that loops (walking a React fiber tree without a visited
set, 抖店 run 68, KEN 2026-10-31) froze the tab's renderer: the step timed out
after 180 s, every later page-state read timed out after 45 s, and the run died.

Chrome stops a script that runs longer than the call's ``timeout`` (ms) and the
page stays usable; an awaited promise is not cut short (verified on Chrome
2026-10-31). Every evaluate that sets no limit of its own now gets one, and the
agent is told plainly what happened instead of "Internal error".
"""
from __future__ import annotations

import time

from utils.logger_helper import logger_helper as logger

SCRIPT_TIMEOUT_MS = 30_000
_installed = False


class ScriptTimeout(RuntimeError):
    pass


def install() -> bool:
    """Patch cdp_use's RuntimeClient once. False when cdp_use is not importable."""
    global _installed
    if _installed:
        return True
    try:
        from cdp_use.cdp.runtime.library import RuntimeClient
    except Exception as exc:
        logger.warning(f"[eval-timeout-patch] cdp_use not importable: {exc}")
        return False
    original = RuntimeClient.evaluate

    async def evaluate(self, params, session_id=None):
        if not isinstance(params, dict) or "timeout" in params:
            return await original(self, params, session_id=session_id)
        t0 = time.monotonic()
        try:
            return await original(self, {**params, "timeout": SCRIPT_TIMEOUT_MS}, session_id=session_id)
        except RuntimeError as exc:
            if time.monotonic() - t0 < SCRIPT_TIMEOUT_MS / 1000 - 1:
                raise
            raise ScriptTimeout(
                f"the script ran longer than {SCRIPT_TIMEOUT_MS // 1000} s and was stopped "
                "(an endless loop?); the page is unchanged by the stop and still usable") from exc

    RuntimeClient.evaluate = evaluate
    _installed = True
    return True
