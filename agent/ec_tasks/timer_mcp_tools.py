"""
Timer MCP Tools - MCP tools for managing named repeating interval timers.

Tools:
- add_timer: Create and start a named repeating timer
- remove_timer: Stop and remove a timer by ID or name
- update_timer: Update a timer's period and/or repeat count
- list_timers: List all repeating timers for the current agent

Timers fire periodically and generate "timer" events that are routed
through the agent's event routing system to resume pend_event nodes.
"""

import json
import time
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Helpers ====================

def _resolve_agent(mainwin, agent_id: str = ""):
    """Resolve an agent from mainwin by ID, or return the first available agent."""
    if agent_id:
        agent = get_agent_by_id(agent_id)
        if agent:
            return agent
    if hasattr(mainwin, "agents") and mainwin.agents:
        return mainwin.agents[0]
    return None


def _get_agent_id(agent) -> str:
    """Extract agent ID from agent object."""
    return getattr(getattr(agent, "card", None), "id", "") or ""


def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg, "timestamp": int(time.time() * 1000)}


def _ok(msg: str, **extra) -> Dict[str, Any]:
    result = {"success": True, "message": msg, "timestamp": int(time.time() * 1000)}
    result.update(extra)
    return result


# ==================== Timer Event Dispatch ====================

def _make_timer_event_callback(agent):
    """
    Create a callback function that dispatches timer events through
    the agent's event routing system when a repeating timer fires.

    Broadcasts the timer event to ALL agent runners (not just the creating
    agent's runner).  Each agent has its own runner with its own
    ``_global_event_routing`` dict, so the timer event must reach the runner
    that actually has a matching routing rule (e.g. a dev task running on
    agent A while the timer was created under agent B).
    """
    def _on_timer_fire(handle):
        try:
            timer_event = {
                "type": "timer",
                "timer_name": handle.timer_name,
                "timer_id": handle.timer_id,
                "fire_count": handle.fire_count,
                "agent_id": handle.agent_id,
                "timestamp": int(time.time() * 1000),
            }

            # Collect all runners from every agent in the application
            from app_context import AppContext
            runners = []
            try:
                mw = AppContext.get_main_window()
                if mw and hasattr(mw, "agents"):
                    for ag in (mw.agents or []):
                        r = getattr(ag, "runner", None)
                        if r:
                            runners.append(r)
            except Exception:
                pass

            # Fallback: if we couldn't enumerate agents, use the creating agent
            if not runners:
                r = getattr(agent, "runner", None)
                if r:
                    runners.append(r)

            if not runners:
                logger.warning(f"[TIMER_TOOL] No runners available, cannot dispatch timer event for '{handle.timer_name}'")
                return

            dispatched = 0
            for runner in runners:
                try:
                    runner.sync_task_wait_in_line("timer", timer_event, source="timer_service")
                    dispatched += 1
                except Exception as re:
                    logger.debug(f"[TIMER_TOOL] Runner dispatch failed: {re}")

            logger.debug(
                f"[TIMER_TOOL] Dispatched timer event '{handle.timer_name}' "
                f"(fire #{handle.fire_count}) to {dispatched}/{len(runners)} agent runner(s)"
            )
        except Exception as e:
            logger.error(f"[TIMER_TOOL] Failed to dispatch timer event: {e}")

    return _on_timer_fire


# ==================== Tool Implementations ====================

def add_timer(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create and start a named repeating interval timer.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
            timer_name: str (required),
            timer_id: str (optional),
            period_ms: int (required),
            repeat_count: int (optional, default -1),
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        timer_name = config.get("timer_name", "").strip()
        timer_id = config.get("timer_id", "").strip() or None
        period_ms = config.get("period_ms")
        repeat_count = config.get("repeat_count", -1)

        if not timer_name:
            return _error("timer_name is required")
        if not period_ms or int(period_ms) <= 0:
            return _error("period_ms must be a positive integer")

        period_ms = int(period_ms)
        repeat_count = int(repeat_count)

        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = _get_agent_id(agent)

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        # If a timer with the same name already exists, update its params,
        # stop it, and restart it fresh (idempotent create-or-update).
        existing = ts.find_repeating_timer_by_name(timer_name, agent_id)
        if existing:
            updated = ts.update_repeating_timer(
                timer_id=existing.timer_id,
                period_ms=period_ms,
                repeat_count=repeat_count,
            )
            if updated:
                return _ok(
                    f"Timer '{timer_name}' already existed (id={existing.timer_id}) — "
                    f"updated and restarted (period={period_ms}ms, repeat={repeat_count})",
                    timer=updated.to_dict(),
                )
            # Fallthrough: update failed (e.g. removed between check and update),
            # create a new one below.

        callback = _make_timer_event_callback(agent)
        handle = ts.add_repeating_timer(
            timer_name=timer_name,
            agent_id=agent_id,
            period_ms=period_ms,
            repeat_count=repeat_count,
            callback=callback,
            timer_id=timer_id,
        )

        return _ok(
            f"Timer '{timer_name}' created and started (period={period_ms}ms, repeat={repeat_count})",
            timer=handle.to_dict(),
        )

    except Exception as e:
        err = get_traceback(e, "ErrorAddTimer")
        logger.error(err)
        return _error(err)


def remove_timer(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop and remove a repeating timer by ID or name.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
            timer_id: str (optional),
            timer_name: str (optional),
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        timer_id = config.get("timer_id", "").strip()
        timer_name = config.get("timer_name", "").strip()

        if not timer_id and not timer_name:
            return _error("Either timer_id or timer_name must be provided")

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        # Resolve by ID first
        if timer_id:
            removed = ts.remove_repeating_timer(timer_id)
            if removed:
                return _ok(f"Timer removed (id={timer_id})")
            return _error(f"Timer not found: id={timer_id}")

        # Resolve by name (need agent context)
        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = _get_agent_id(agent)
        handle = ts.find_repeating_timer_by_name(timer_name, agent_id)
        if handle:
            ts.remove_repeating_timer(handle.timer_id)
            return _ok(f"Timer '{timer_name}' removed (id={handle.timer_id})")

        return _error(f"Timer not found: name='{timer_name}' for agent {agent_id}")

    except Exception as e:
        err = get_traceback(e, "ErrorRemoveTimer")
        logger.error(err)
        return _error(err)


def update_timer(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update a repeating timer's period and/or repeat count.

    Args:
        mainwin: Main window instance
        config: {
            timer_id: str (required),
            period_ms: int (optional),
            repeat_count: int (optional),
        }
    """
    try:
        timer_id = config.get("timer_id", "").strip()
        period_ms = config.get("period_ms")
        repeat_count = config.get("repeat_count")

        if not timer_id:
            return _error("timer_id is required")

        if period_ms is not None:
            period_ms = int(period_ms)
            if period_ms <= 0:
                return _error("period_ms must be a positive integer")

        if repeat_count is not None:
            repeat_count = int(repeat_count)

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        handle = ts.update_repeating_timer(
            timer_id=timer_id,
            period_ms=period_ms,
            repeat_count=repeat_count,
        )

        if handle:
            return _ok(
                f"Timer '{handle.timer_name}' updated "
                f"(period={handle.period_ms}ms, repeat={handle.repeat_count})",
                timer=handle.to_dict(),
            )
        return _error(f"Timer not found: id={timer_id}")

    except Exception as e:
        err = get_traceback(e, "ErrorUpdateTimer")
        logger.error(err)
        return _error(err)


def list_timers(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all repeating timers for the current agent.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
        }
    """
    try:
        agent_id = config.get("agent_id", "")

        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = _get_agent_id(agent)

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        timers = ts.list_repeating_timers(agent_id=agent_id)
        timer_list = [h.to_dict() for h in timers]

        return _ok(
            f"Found {len(timer_list)} timer(s) for agent {agent_id}",
            timers=timer_list,
        )

    except Exception as e:
        err = get_traceback(e, "ErrorListTimers")
        logger.error(err)
        return _error(err)


def pause_timer(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Pause a repeating timer so it stops firing events.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
            timer_id: str (optional),
            timer_name: str (optional),
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        timer_id = config.get("timer_id", "").strip()
        timer_name = config.get("timer_name", "").strip()

        if not timer_id and not timer_name:
            return _error("Either timer_id or timer_name must be provided")

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        # Resolve by ID first
        if timer_id:
            handle = ts.pause_repeating_timer(timer_id)
            if handle:
                return _ok(f"Timer '{handle.timer_name}' paused (id={timer_id})", timer=handle.to_dict())
            return _error(f"Timer not found: id={timer_id}")

        # Resolve by name
        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = _get_agent_id(agent)
        handle = ts.find_repeating_timer_by_name(timer_name, agent_id)
        if handle:
            handle.pause()
            return _ok(f"Timer '{timer_name}' paused (id={handle.timer_id})", timer=handle.to_dict())

        return _error(f"Timer not found: name='{timer_name}' for agent {agent_id}")

    except Exception as e:
        err = get_traceback(e, "ErrorPauseTimer")
        logger.error(err)
        return _error(err)


def resume_timer(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resume a previously paused repeating timer.

    Args:
        mainwin: Main window instance
        config: {
            agent_id: str (optional),
            timer_id: str (optional),
            timer_name: str (optional),
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        timer_id = config.get("timer_id", "").strip()
        timer_name = config.get("timer_name", "").strip()

        if not timer_id and not timer_name:
            return _error("Either timer_id or timer_name must be provided")

        from agent.ec_tasks.timer_service import get_timer_service
        ts = get_timer_service()

        # Resolve by ID first
        if timer_id:
            handle = ts.resume_repeating_timer(timer_id)
            if handle:
                return _ok(f"Timer '{handle.timer_name}' resumed (id={timer_id})", timer=handle.to_dict())
            return _error(f"Timer not found: id={timer_id}")

        # Resolve by name
        agent = _resolve_agent(mainwin, agent_id)
        if not agent:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = _get_agent_id(agent)
        handle = ts.find_repeating_timer_by_name(timer_name, agent_id)
        if handle:
            handle.resume()
            return _ok(f"Timer '{timer_name}' resumed (id={handle.timer_id})", timer=handle.to_dict())

        return _error(f"Timer not found: name='{timer_name}' for agent {agent_id}")

    except Exception as e:
        err = get_traceback(e, "ErrorResumeTimer")
        logger.error(err)
        return _error(err)


# ==================== Async Wrappers for Server ====================

async def async_add_timer(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for add_timer tool."""
    try:
        input_config = args.get("input", args)
        result = add_timer(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Timer created successfully")
        else:
            msg = f"Failed to create timer: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncAddTimer")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_remove_timer(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for remove_timer tool."""
    try:
        input_config = args.get("input", args)
        result = remove_timer(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Timer removed successfully")
        else:
            msg = f"Failed to remove timer: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncRemoveTimer")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_update_timer(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for update_timer tool."""
    try:
        input_config = args.get("input", args)
        result = update_timer(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Timer updated successfully")
        else:
            msg = f"Failed to update timer: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncUpdateTimer")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_list_timers(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for list_timers tool."""
    try:
        input_config = args.get("input", args)
        result = list_timers(mainwin, input_config)

        if result.get("success"):
            timers = result.get("timers", [])
            if timers:
                lines = [f"Found {len(timers)} timer(s):"]
                for t in timers:
                    status = "active" if t.get("active") else "stopped"
                    lines.append(
                        f"  - {t['timer_name']} (id={t['timer_id']}, "
                        f"period={t['period_ms']}ms, repeat={t['repeat_count']}, "
                        f"fired={t['fire_count']}, {status})"
                    )
                msg = "\n".join(lines)
            else:
                msg = "No timers found for this agent."
        else:
            msg = f"Failed to list timers: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncListTimers")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_pause_timer(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for pause_timer tool."""
    try:
        input_config = args.get("input", args)
        result = pause_timer(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Timer paused successfully")
        else:
            msg = f"Failed to pause timer: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncPauseTimer")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_resume_timer(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for resume_timer tool."""
    try:
        input_config = args.get("input", args)
        result = resume_timer(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Timer resumed successfully")
        else:
            msg = f"Failed to resume timer: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"timer_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncResumeTimer")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
