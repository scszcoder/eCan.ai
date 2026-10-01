"""Store-Chrome watchdog for event-monitored browser runs.

A monitored front desk (Feige, 拼多多, ...) runs its browser-use agent once,
keeps the session alive, and then waits for its event monitors to deliver the
next customer message. If the store's Chrome dies in that wait, the monitors
die with it, no event ever arrives, and nothing re-enters the node -- the task
sits blind until someone restarts eCan (2026-09-30 customer log: 拼多多 Chrome
closed at 16:36:46, blind until 17:09).

The watchdog probes the session's CDP endpoint while the run waits. When the
browser stops answering it:

  1. stops the dead session's monitors (and with them the site's WS observer),
  2. shuts down the dead BrowserManager record (so its owner lookup cannot hand
     the dead browser back),
  3. rebuilds the node's browser through the runner's own setup path -- same
     profile, so cookies and the store login carry over; pre-run navigation
     back to the store URL; monitors restarted -- without running the agent.

Up to ``MAX_ATTEMPTS`` rebuilds with backoff, then ``chrome=dead`` on the
Agents page. It always relaunches while the agent is running (a closed window
and a crash look the same); stopping the agent, or its monitors, stands it
down. Site specifics stay in the bundles: the monitors re-arm their observers.

Off by default: set ``ECAN_BROWSER_WATCHDOG=1`` (run.env) to enable it.
"""

from __future__ import annotations

import asyncio
import os
import urllib.request
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional

from utils import agent_status as _agent_status
from utils.logger_helper import logger_helper as logger

MAX_ATTEMPTS = 3
PROBE_INTERVAL_S = 5.0
DEAD_AFTER_FAILED_PROBES = 2
BACKOFF_S = (5.0, 15.0, 30.0)


@dataclass
class _Watch:
    scope_key: str
    session: Any
    monitor_set_id: str
    agent_id: str
    mainwin: Any
    rebuild: Callable[[], Awaitable[bool]]
    task: Optional[asyncio.Task] = None


_watches: Dict[str, _Watch] = {}


def _cdp_url(session: Any) -> str:
    url = getattr(session, "cdp_url", None) or getattr(
        getattr(session, "browser_profile", None), "cdp_url", None)
    return str(url or "").rstrip("/")


def _cdp_answers(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url}/json/version", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _monitors_registered(monitor_set_id: str) -> bool:
    from agent.ec_skills.browser_use_extension import event_monitor
    return monitor_set_id in event_monitor._active_monitor_sets


def _agent_running(mainwin: Any, agent_id: str) -> bool:
    if not agent_id or mainwin is None:
        return True
    try:
        agents = mainwin.get_agents() if hasattr(mainwin, "get_agents") else getattr(mainwin, "agents", [])
        return any(str(getattr(getattr(a, "card", None), "id", "")) == agent_id for a in agents or [])
    except Exception:
        return True


def enabled() -> bool:
    """Off unless ``ECAN_BROWSER_WATCHDOG=1`` (run.env): not yet proven on a live
    front desk, and a false "dead" would relaunch a store's Chrome mid-chat."""
    return os.getenv("ECAN_BROWSER_WATCHDOG", "").strip().lower() in ("1", "true", "yes", "on")


def arm(*, scope_key: str, session: Any, monitor_set_id: str, agent_id: str,
        mainwin: Any, rebuild: Callable[[], Awaitable[bool]]) -> None:
    """Watch *session* for this scope. Idempotent: every event re-entry calls
    it; a watch already running on the same session only takes the fresh
    rebuild callable. Must be called on the session's event loop."""
    if not enabled() or not monitor_set_id or not _cdp_url(session):
        return
    w = _watches.get(scope_key)
    if w and w.session is session and w.task and not w.task.done():
        w.rebuild, w.monitor_set_id, w.agent_id = rebuild, monitor_set_id, agent_id
        return
    # A successful rebuild re-arms from inside the old watch task; that task
    # ends on its own once the rebuild returns, so it must not be cancelled.
    if w and w.task and not w.task.done() and w.task is not asyncio.current_task():
        w.task.cancel()
    w = _Watch(scope_key, session, monitor_set_id, agent_id, mainwin, rebuild)
    w.task = asyncio.get_running_loop().create_task(_watch(w))
    _watches[scope_key] = w
    logger.info(f"[BrowserWatchdog] armed scope={scope_key} cdp={_cdp_url(session)} "
                f"monitors={monitor_set_id}")


async def _watch(w: _Watch) -> None:
    cdp_url = _cdp_url(w.session)
    failed = 0
    while failed < DEAD_AFTER_FAILED_PROBES:
        await asyncio.sleep(PROBE_INTERVAL_S)
        if not _monitors_registered(w.monitor_set_id) or not _agent_running(w.mainwin, w.agent_id):
            logger.info(f"[BrowserWatchdog] stood down scope={w.scope_key} (monitors or agent stopped)")
            return
        failed = 0 if await asyncio.to_thread(_cdp_answers, cdp_url) else failed + 1

    logger.warning(f"[BrowserWatchdog] browser at {cdp_url} stopped answering "
                   f"(scope={w.scope_key}); recovering")
    await _drop_dead_session(w)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        _agent_status.report(w.agent_id or None, chrome="recovering", chrome_recover_attempt=attempt)
        await asyncio.sleep(BACKOFF_S[attempt - 1])
        if not _agent_running(w.mainwin, w.agent_id):
            logger.info(f"[BrowserWatchdog] agent stopped during recovery; giving up scope={w.scope_key}")
            return
        try:
            if await w.rebuild():
                logger.info(f"[BrowserWatchdog] recovered scope={w.scope_key} on attempt {attempt}")
                return
            logger.warning(f"[BrowserWatchdog] rebuild attempt {attempt}/{MAX_ATTEMPTS} did not "
                           f"restore the browser (scope={w.scope_key})")
        except Exception as exc:
            logger.warning(f"[BrowserWatchdog] rebuild attempt {attempt}/{MAX_ATTEMPTS} failed "
                           f"(scope={w.scope_key}): {exc}")
    _agent_status.report(w.agent_id or None, chrome="dead")
    logger.error(f"[BrowserWatchdog] gave up after {MAX_ATTEMPTS} attempts: the store browser "
                 f"for scope={w.scope_key} is down -- restart the agent to retry")


async def _drop_dead_session(w: _Watch) -> None:
    """Release everything still bound to the dead browser."""
    try:
        from agent.ec_skills.browser_use_extension.event_monitor_capability import (
            get_event_monitor_capability,
        )
        cap = get_event_monitor_capability(w.session, create=False)
        if cap:
            await cap.stop()
    except Exception as exc:
        logger.debug(f"[BrowserWatchdog] stopping dead monitors: {exc}")
    try:
        setattr(w.session, "_ecan_force_recreate", True)
        from agent.ec_skills.browser_node import build_helpers as _bh
        if _bh.cached_browser_sessions.get(w.scope_key) is w.session:
            _bh.cached_browser_sessions.pop(w.scope_key, None)
    except Exception as exc:
        logger.debug(f"[BrowserWatchdog] dropping cached session: {exc}")
    try:
        manager = getattr(w.mainwin, "browser_manager", None)
        for b in list(getattr(manager, "active_browsers", []) or []):
            if getattr(b, "browser_session", None) is w.session:
                await manager.shutdown_browser(b.id, force=True)
    except Exception as exc:
        logger.debug(f"[BrowserWatchdog] shutting down dead browser record: {exc}")
