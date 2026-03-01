"""
Task MCP Tools - MCP tools for launching and managing agent tasks.

Tools:
- launch_agent_task: Launch an existing or new agent task, enqueue inputs.
- create_agent_task_with_skill: Create a new task from a skill and start its loop.
- schedule_agent_task: Create a scheduled task from a skill.
- delete_agent_task: Remove a task from the agent.
- stop_agent_task: Cancel / stop a running task.

Naming convention follows self_tools.py and tool_schemas.py patterns.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Tool Implementations ====================

def launch_agent_task(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Launch an agent task.

    Resolution order:
      1. If task_id is provided, find the existing task directly.
      2. If task_name is provided, find the first task whose name matches.
      3. If neither matches but skill_name or skill_id is provided,
         create a new task using that skill.

    Once the target task is resolved, a message carrying task_inputs is
    placed on the task's queue so the execution loop picks it up.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional, uses first agent if not provided)
            - task_id: str (optional) - ID of an existing task to launch
            - task_name: str (optional) - Name of an existing task to launch
            - skill_name: str (optional) - Skill name to find task or create new one
            - skill_id: str (optional) - Skill ID to find task or create new one
            - task_inputs: dict (optional) - JSON inputs to inject into the task

    Returns:
        Dict with launch result:
        {
            "success": bool,
            "task_id": str,
            "run_id": str,
            "task_name": str,
            "created": bool,
            "message": str,
            "timestamp": int
        }
        The run_id uniquely identifies this invocation and can be used
        to poll / subscribe for status updates.
    """
    try:
        agent_id = config.get("agent_id", "")
        task_id = config.get("task_id", "")
        task_name = config.get("task_name", "")
        skill_name = config.get("skill_name", "")
        skill_id = config.get("skill_id", "")
        task_inputs = config.get("task_inputs") or {}

        # Lineage fields for nested task progress tracking
        correlation_id = config.get("correlation_id", "")
        parent_run_id = config.get("parent_run_id", "")
        parent_depth = int(config.get("parent_depth", 0) or 0)

        # --- Resolve agent ---
        agent = _resolve_agent(mainwin, agent_id)
        if agent is None:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = getattr(getattr(agent, "card", None), "id", "") or agent_id

        # --- Resolve target task ---
        target_task, created = _resolve_or_create_task(
            agent, task_id=task_id, task_name=task_name,
            skill_name=skill_name, skill_id=skill_id,
        )

        if target_task is None:
            return _error(
                "Could not resolve a task. Provide a valid task_id, task_name, "
                "or skill_name/skill_id to create a new one."
            )

        resolved_task_id = getattr(target_task, "id", "")
        resolved_task_name = getattr(target_task, "name", "")

        # For new tasks: stamp run_id and start execution loop.
        # For existing tasks: the runner already owns the run_id — just send a message.
        if created:
            run_id = str(uuid.uuid4())
            target_task.run_id = run_id
            _start_task_loop(agent, target_task)
        else:
            run_id = getattr(target_task, "run_id", "") or ""

        # --- Build lineage for nested task progress ---
        # If no correlation_id provided, this task is the root of a new chain
        effective_corr_id = correlation_id or run_id
        child_depth = (parent_depth + 1) if parent_run_id else 0
        lineage = {
            "correlation_id": effective_corr_id,
            "parent_run_id": parent_run_id,
            "depth": child_depth,
        }

        # Store lineage on task metadata so executor/runtime can access it
        if not hasattr(target_task, "metadata") or target_task.metadata is None:
            target_task.metadata = {}
        target_task.metadata["lineage"] = lineage

        # Register with the progress bus
        try:
            from .task_progress_bus import TaskProgressBus
            bus = TaskProgressBus.get_instance()
            bus.register_task(
                correlation_id=effective_corr_id,
                run_id=run_id,
                parent_run_id=parent_run_id,
                task_id=resolved_task_id,
                task_name=resolved_task_name,
                depth=child_depth,
            )
        except Exception as e:
            logger.debug(f"[launch_agent_task] Failed to register with progress bus: {e}")

        # --- Enqueue task_inputs as a message on the task's queue ---
        message_id = str(uuid.uuid4())
        _enqueue_task_inputs(target_task, task_inputs, message_id, lineage=lineage)

        return {
            "success": True,
            "task_id": resolved_task_id,
            "run_id": run_id,
            "correlation_id": effective_corr_id,
            "message_id": message_id,
            "task_name": resolved_task_name,
            "agent_id": agent_id,
            "created": created,
            "depth": child_depth,
            "message": (
                f"Task '{resolved_task_name}' "
                f"{'created and started' if created else 'message enqueued'}"
                f" (run_id={run_id}, message_id={message_id})"
                f"{' with inputs' if task_inputs else ''}"
            ),
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorLaunchAgentTask")
        logger.error(err_trace)
        return _error(err_trace)


# ==================== Internal Helpers ====================

def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg, "timestamp": int(time.time() * 1000)}


def _resolve_agent(mainwin, agent_id: str):
    """Resolve agent by ID or fall back to the first available agent."""
    if agent_id:
        return get_agent_by_id(agent_id)
    if hasattr(mainwin, "agents") and mainwin.agents:
        return mainwin.agents[0]
    return None


def _resolve_or_create_task(agent, *, task_id, task_name, skill_name, skill_id):
    """
    Find an existing task or create a new one.

    Returns:
        (ManagedTask | None, created: bool)
    """
    tasks = getattr(agent, "tasks", []) or []

    # 1. By task_id
    if task_id:
        for t in tasks:
            if getattr(t, "id", "") == task_id:
                logger.info(f"[launch_agent_task] Found task by id: {task_id}")
                return t, False

    # 2. By task_name
    if task_name:
        task_name_lower = task_name.lower()
        for t in tasks:
            if (getattr(t, "name", "") or "").lower() == task_name_lower:
                logger.info(f"[launch_agent_task] Found task by name: {t.name}")
                return t, False

    # 3. Find task whose skill matches skill_name / skill_id
    if skill_name or skill_id:
        for t in tasks:
            sk = getattr(t, "skill", None)
            if sk is None:
                continue
            if skill_name and getattr(sk, "name", "") == skill_name:
                logger.info(f"[launch_agent_task] Found task by skill name: {skill_name}")
                return t, False
            if skill_id and getattr(sk, "id", "") == skill_id:
                logger.info(f"[launch_agent_task] Found task by skill id: {skill_id}")
                return t, False

    # 4. No existing task — create a new one if we can resolve a skill
    skill = _resolve_skill(agent, skill_name, skill_id)
    if skill is None:
        return None, False

    return _create_task(agent, skill, task_name), True


def _resolve_skill(agent, skill_name: str, skill_id: str):
    """Find a skill on the agent by name or id."""
    skills = getattr(agent, "skills", []) or []
    for sk in skills:
        if skill_name and getattr(sk, "name", "") == skill_name:
            return sk
        if skill_id and getattr(sk, "id", "") == skill_id:
            return sk
    available = [getattr(s, "name", "?") for s in skills]
    logger.warning(
        f"[launch_agent_task] Skill not found (name={skill_name!r}, id={skill_id!r}). "
        f"Available: {available}"
    )
    return None


def _create_task(agent, skill, task_name: str, *, trigger: str = "message", initial_state: Optional[dict] = None):
    """Create a new ManagedTask attached to the agent."""
    from agent.ec_tasks.models import ManagedTask
    from a2a.types import TaskState, TaskStatus as A2ATaskStatus

    new_id = str(uuid.uuid4())
    skill_name = getattr(skill, "name", "unknown")
    name = task_name or f"{skill_name}_task_{new_id[:8]}"
    task_state = initial_state or {}

    task = ManagedTask(
        id=new_id,
        run_id=str(uuid.uuid4()),
        name=name,
        description=f"Created via MCP tool using skill '{skill_name}'",
        source="mcp_tool",
        status=A2ATaskStatus(state=TaskState.submitted),
        sessionId="",
        skill=skill,
        metadata={"initial_state": task_state} if task_state else {},
        state=task_state,
        resume_from="",
        trigger=trigger,
        agent_id=getattr(getattr(agent, "card", None), "id", "") or "",
    )

    if getattr(agent, "tasks", None) is None:
        agent.tasks = []
    agent.tasks.append(task)

    logger.info(f"[task_mcp_tools] Created new task: {name} (id={new_id}, trigger={trigger})")
    return task


def _start_task_loop(agent, task, *, trigger_types: Optional[List[str]] = None):
    """Submit the task's execution loop to the agent's thread pool."""
    runner = getattr(agent, "runner", None)
    if not runner:
        logger.warning("[task_mcp_tools] No runner on agent, cannot start execution loop")
        return

    if trigger_types is None:
        trigger_types = ["message"]

    from concurrent.futures import ThreadPoolExecutor

    mainwin = getattr(agent, "mainwin", None)
    thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
    if not thread_pool:
        thread_pool = getattr(agent, "thread_pool_executor", None)
    if not thread_pool:
        thread_pool = ThreadPoolExecutor(max_workers=4)

    try:
        future = thread_pool.submit(runner.launch_unified_run, task, trigger_types)
        if hasattr(agent, "active_tasks") and hasattr(agent, "task_lock"):
            with agent.task_lock:
                agent.active_tasks[task.run_id] = future
        logger.info(f"[task_mcp_tools] Execution loop started for task: {task.name}, triggers={trigger_types}")
    except Exception as e:
        logger.error(f"[task_mcp_tools] Failed to start execution loop: {e}")


def _find_task(agent, task_id: str, task_name: str):
    """Find a task on the agent by id or name."""
    tasks = getattr(agent, "tasks", []) or []
    if task_id:
        for t in tasks:
            if getattr(t, "id", "") == task_id or getattr(t, "run_id", "") == task_id:
                return t
    if task_name:
        task_name_lower = task_name.lower()
        for t in tasks:
            if (getattr(t, "name", "") or "").lower() == task_name_lower:
                return t
    return None


def _cancel_task(agent, task):
    """Cancel a task: set cancellation event, update state, remove from active_tasks."""
    from a2a.types import TaskState

    task_id = getattr(task, "id", "")
    run_id = getattr(task, "run_id", "")

    # Set cancellation event
    if hasattr(task, "cancellation_event"):
        task.cancellation_event.set()
        logger.info(f"[task_mcp_tools] Set cancellation event for task {task_id}")

    # Call cancel() if available
    if hasattr(task, "cancel") and callable(task.cancel):
        task.cancel()

    # Update task state
    task_status = getattr(task, "status", None)
    if task_status and hasattr(task_status, "state"):
        task_status.state = TaskState.canceled

    # Remove from active_tasks
    if hasattr(agent, "active_tasks") and hasattr(agent, "task_lock"):
        with agent.task_lock:
            agent.active_tasks.pop(run_id, None)
            agent.active_tasks.pop(task_id, None)

    logger.info(f"[task_mcp_tools] Cancelled task: {getattr(task, 'name', task_id)}")


def _parse_datetime(dt_str: str, default) -> str:
    """Parse a datetime string into standard format 'YYYY-MM-DD HH:MM:SS:fff'."""
    from datetime import datetime

    fmt = "%Y-%m-%d %H:%M:%S:%f"
    fmt_alt = "%Y-%m-%d %H:%M:%S"

    def _to_fmt(dt):
        return dt.strftime(fmt)[:-3] + "000"

    if not dt_str:
        return _to_fmt(default)

    for f in (fmt, fmt_alt):
        try:
            return _to_fmt(datetime.strptime(dt_str, f))
        except ValueError:
            pass
    try:
        return _to_fmt(datetime.fromisoformat(dt_str.replace("Z", "+00:00")))
    except ValueError:
        pass

    return _to_fmt(default)


def _enqueue_task_inputs(task, task_inputs: dict, run_id: str, lineage: Optional[dict] = None):
    """Put a launch message on the task's queue."""
    queue = getattr(task, "queue", None)
    if queue is None:
        logger.warning(f"[launch_agent_task] Task {task.name} has no queue, skipping enqueue")
        return

    from a2a.types import MessageSendParams, Message, TextPart

    message_id = str(uuid.uuid4())
    metadata = {
        "mtype": "launch_task",
        "run_id": run_id,
        "task_id": getattr(task, "id", ""),
        "task_name": getattr(task, "name", ""),
        "task_inputs": task_inputs,
    }
    if lineage:
        metadata["lineage"] = lineage
    msg = MessageSendParams(
        id=str(uuid.uuid4()),
        message=Message(
            messageId=message_id,
            role="user",
            parts=[TextPart(type="text", text=json.dumps(task_inputs) if task_inputs else "launch")],
        ),
        metadata=metadata,
    )

    try:
        queue.put_nowait(msg)
        logger.info(f"[launch_agent_task] Enqueued launch message for task: {task.name}")
    except Exception as e:
        logger.error(f"[launch_agent_task] Failed to enqueue message: {e}")


def create_agent_task_with_skill(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new agent task from a skill and start its execution loop.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional)
            - skill_name: str (required) - Name of the skill
            - skill_id: str (optional) - ID of the skill (alternative to skill_name)
            - task_name: str (optional) - Custom name for the task
            - trigger: str (optional) - Trigger type: "message" (default), "auto", "schedule"
            - initial_state: dict (optional) - Initial state for the task

    Returns:
        Dict with creation result including task_id and run_id.
    """
    try:
        agent_id = config.get("agent_id", "")
        skill_name = config.get("skill_name", "")
        skill_id = config.get("skill_id", "")
        task_name = config.get("task_name", "")
        trigger = config.get("trigger", "message")
        initial_state = config.get("initial_state", {})

        if not skill_name and not skill_id:
            return _error("skill_name or skill_id is required")

        agent = _resolve_agent(mainwin, agent_id)
        if agent is None:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = getattr(getattr(agent, "card", None), "id", "") or agent_id

        skill = _resolve_skill(agent, skill_name, skill_id)
        if skill is None:
            available = [getattr(s, "name", "?") for s in (getattr(agent, "skills", []) or [])]
            return _error(f"Skill not found (name={skill_name!r}, id={skill_id!r}). Available: {available}")

        task = _create_task(agent, skill, task_name, trigger=trigger, initial_state=initial_state)
        run_id = str(uuid.uuid4())
        task.run_id = run_id

        _start_task_loop(agent, task)

        return {
            "success": True,
            "task_id": task.id,
            "run_id": run_id,
            "task_name": task.name,
            "skill_name": getattr(skill, "name", ""),
            "trigger": trigger,
            "agent_id": agent_id,
            "message": f"Task '{task.name}' created with skill '{getattr(skill, 'name', '')}' (trigger={trigger})",
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorCreateAgentTaskWithSkill")
        logger.error(err_trace)
        return _error(err_trace)


def schedule_agent_task(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a scheduled task from a skill.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional)
            - skill_name: str (required)
            - skill_id: str (optional)
            - task_name: str (optional)
            - initial_state: dict (optional)
            - schedule: dict (required) with:
                - repeat_type: str ("none","seconds","minutes","hours","daily","weekly","monthly","yearly")
                - repeat_number: int (default 1)
                - start_date_time: str (ISO or "YYYY-MM-DD HH:MM:SS")
                - end_date_time: str (optional, default 10 years)
                - time_out: int (optional, default 120)

    Returns:
        Dict with task_id, schedule info, etc.
    """
    from datetime import datetime, timedelta
    from agent.ec_tasks import ManagedTask, TaskSchedule, RepeatType
    from agent.ec_tasks.models import TaskStatus, TaskState

    try:
        agent_id = config.get("agent_id", "")
        skill_name = config.get("skill_name", "")
        skill_id = config.get("skill_id", "")
        task_name = config.get("task_name", "")
        initial_state = config.get("initial_state", {})
        schedule_config = config.get("schedule", {})

        if not skill_name and not skill_id:
            return _error("skill_name or skill_id is required")
        if not schedule_config:
            return _error("schedule configuration is required")

        agent = _resolve_agent(mainwin, agent_id)
        if agent is None:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = getattr(getattr(agent, "card", None), "id", "") or agent_id

        skill = _resolve_skill(agent, skill_name, skill_id)
        if skill is None:
            available = [getattr(s, "name", "?") for s in (getattr(agent, "skills", []) or [])]
            return _error(f"Skill not found (name={skill_name!r}, id={skill_id!r}). Available: {available}")

        # Parse repeat_type
        repeat_type_str = schedule_config.get("repeat_type", "none").lower().strip()
        repeat_type_map = {
            "none": RepeatType.NONE,
            "seconds": RepeatType.BY_SECONDS, "by_seconds": RepeatType.BY_SECONDS, "by seconds": RepeatType.BY_SECONDS,
            "minutes": RepeatType.BY_MINUTES, "by_minutes": RepeatType.BY_MINUTES, "by minutes": RepeatType.BY_MINUTES,
            "hours": RepeatType.BY_HOURS, "by_hours": RepeatType.BY_HOURS, "by hours": RepeatType.BY_HOURS, "hourly": RepeatType.BY_HOURS,
            "days": RepeatType.BY_DAYS, "by_days": RepeatType.BY_DAYS, "by days": RepeatType.BY_DAYS, "daily": RepeatType.BY_DAYS,
            "weeks": RepeatType.BY_WEEKS, "by_weeks": RepeatType.BY_WEEKS, "by weeks": RepeatType.BY_WEEKS, "weekly": RepeatType.BY_WEEKS,
            "months": RepeatType.BY_MONTHS, "by_months": RepeatType.BY_MONTHS, "by months": RepeatType.BY_MONTHS, "monthly": RepeatType.BY_MONTHS,
            "years": RepeatType.BY_YEARS, "by_years": RepeatType.BY_YEARS, "by years": RepeatType.BY_YEARS, "yearly": RepeatType.BY_YEARS,
        }
        repeat_type = repeat_type_map.get(repeat_type_str, RepeatType.NONE)
        repeat_number = int(schedule_config.get("repeat_number", 1))

        # Parse datetimes
        now = datetime.now()
        default_end = now + timedelta(days=365 * 10)
        start_dt = _parse_datetime(schedule_config.get("start_date_time", ""), now)
        end_dt = _parse_datetime(schedule_config.get("end_date_time", ""), default_end)
        time_out = int(schedule_config.get("time_out", 120))

        task_schedule = TaskSchedule(
            repeat_type=repeat_type,
            repeat_number=repeat_number,
            repeat_unit=repeat_type_str,
            start_date_time=start_dt,
            end_date_time=end_dt,
            time_out=time_out,
        )

        resolved_skill_name = getattr(skill, "name", "unknown")
        new_id = str(uuid.uuid4())
        name = task_name or f"Scheduled_{resolved_skill_name}_{new_id[:8]}"
        task_state = initial_state or {"top": "ready"}

        task = ManagedTask(
            id=new_id,
            run_id=str(uuid.uuid4()),
            name=name,
            description=f"Scheduled task using skill '{resolved_skill_name}'",
            source="mcp_tool",
            status=TaskStatus(state=TaskState.submitted),
            sessionId="",
            skill=skill,
            metadata={"state": task_state},
            state=task_state,
            resume_from="",
            trigger="schedule",
            schedule=task_schedule,
            agent_id=agent_id,
        )

        if getattr(agent, "tasks", None) is None:
            agent.tasks = []
        agent.tasks.append(task)

        # Start execution loop so scheduler can pick it up
        _start_task_loop(agent, task, trigger_types=["schedule"])

        logger.info(f"[schedule_agent_task] Created: {name} (id={new_id}), {repeat_type.value} every {repeat_number}")

        return {
            "success": True,
            "task_id": new_id,
            "task_name": name,
            "skill_name": resolved_skill_name,
            "agent_id": agent_id,
            "schedule": {
                "repeat_type": repeat_type.value,
                "repeat_number": repeat_number,
                "start_date_time": start_dt,
                "end_date_time": end_dt,
                "time_out": time_out,
            },
            "message": f"Task '{name}' scheduled ({repeat_type.value} every {repeat_number})",
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorScheduleAgentTask")
        logger.error(err_trace)
        return _error(err_trace)


def delete_agent_task(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Delete (remove) a task from the agent.  Stops it first if running.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional)
            - task_id: str (optional) - ID of the task to delete
            - task_name: str (optional) - Name of the task to delete

    Returns:
        Dict with deletion result.
    """
    try:
        agent_id = config.get("agent_id", "")
        task_id = config.get("task_id", "")
        task_name = config.get("task_name", "")

        if not task_id and not task_name:
            return _error("task_id or task_name is required")

        agent = _resolve_agent(mainwin, agent_id)
        if agent is None:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = getattr(getattr(agent, "card", None), "id", "") or agent_id

        target_task = _find_task(agent, task_id, task_name)
        if target_task is None:
            return _error(f"Task not found (id={task_id!r}, name={task_name!r})")

        resolved_id = getattr(target_task, "id", "")
        resolved_name = getattr(target_task, "name", "")
        resolved_run_id = getattr(target_task, "run_id", "")

        # Stop the task first
        _cancel_task(agent, target_task)

        # Remove from agent.tasks
        tasks = getattr(agent, "tasks", []) or []
        try:
            tasks.remove(target_task)
            logger.info(f"[delete_agent_task] Removed task: {resolved_name} (id={resolved_id})")
        except ValueError:
            logger.warning(f"[delete_agent_task] Task not in agent.tasks list: {resolved_id}")

        return {
            "success": True,
            "task_id": resolved_id,
            "task_name": resolved_name,
            "agent_id": agent_id,
            "message": f"Task '{resolved_name}' deleted",
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorDeleteAgentTask")
        logger.error(err_trace)
        return _error(err_trace)


def stop_agent_task(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop / cancel a running task.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional)
            - task_id: str (optional) - ID of the task to stop
            - task_name: str (optional) - Name of the task to stop
            - force: bool (optional) - Force stop even in critical section

    Returns:
        Dict with stop result including previous state.
    """
    try:
        agent_id = config.get("agent_id", "")
        task_id = config.get("task_id", "")
        task_name = config.get("task_name", "")
        force = config.get("force", False)

        if not task_id and not task_name:
            return _error("task_id or task_name is required")

        agent = _resolve_agent(mainwin, agent_id)
        if agent is None:
            return _error(f"Agent not found: {agent_id or '(default)'}")

        agent_id = getattr(getattr(agent, "card", None), "id", "") or agent_id

        target_task = _find_task(agent, task_id, task_name)
        if target_task is None:
            return _error(f"Task not found (id={task_id!r}, name={task_name!r})")

        resolved_id = getattr(target_task, "id", "")
        resolved_name = getattr(target_task, "name", "")

        # Capture previous state
        previous_state = "unknown"
        task_status = getattr(target_task, "status", None)
        if task_status:
            st = getattr(task_status, "state", None)
            if st:
                previous_state = st.value if hasattr(st, "value") else str(st)

        _cancel_task(agent, target_task)

        return {
            "success": True,
            "task_id": resolved_id,
            "task_name": resolved_name,
            "previous_state": previous_state,
            "agent_id": agent_id,
            "message": f"Task '{resolved_name}' stopped (was {previous_state})",
            "timestamp": int(time.time() * 1000),
        }

    except Exception as e:
        err_trace = get_traceback(e, "ErrorStopAgentTask")
        logger.error(err_trace)
        return _error(err_trace)


# ==================== Tool Schema ====================

def add_launch_agent_task_tool_schema(tool_schemas: list):
    """Register the launch_agent_task MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="launch_agent_task",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Launch an agent task. Can target an existing task by task_id or task_name, "
            "or create a new task from a skill. Optionally injects task_inputs into the "
            "task queue to provide initial data. Returns a run_id that uniquely identifies "
            "this invocation and can be used to poll or subscribe for status updates."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent. Optional — defaults to the first available agent.",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "ID of an existing task to launch.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Name of an existing task to launch.",
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill. Used to find an existing task or create a new one.",
                        },
                        "skill_id": {
                            "type": "string",
                            "description": "ID of the skill. Used to find an existing task or create a new one.",
                        },
                        "task_inputs": {
                            "type": "object",
                            "description": "JSON object of inputs/parameters to inject into the task.",
                        },
                        "correlation_id": {
                            "type": "string",
                            "description": "Correlation ID for tracking nested task chains. If omitted, the new task becomes the root of its own chain.",
                        },
                        "parent_run_id": {
                            "type": "string",
                            "description": "Run ID of the parent task that is launching this one. Used for lineage tracking.",
                        },
                        "parent_depth": {
                            "type": "integer",
                            "description": "Nesting depth of the parent task (0 = root). The child will be depth+1.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_create_agent_task_with_skill_tool_schema(tool_schemas: list):
    """Register the create_agent_task_with_skill MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="create_agent_task_with_skill",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Create a new agent task from a skill and start its execution loop. "
            "Returns task_id and run_id for tracking."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent. Optional — defaults to the first available agent.",
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill to use. Required if skill_id not provided.",
                        },
                        "skill_id": {
                            "type": "string",
                            "description": "ID of the skill to use. Alternative to skill_name.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Custom name for the task. Auto-generated if not provided.",
                        },
                        "trigger": {
                            "type": "string",
                            "enum": ["message", "auto", "schedule"],
                            "description": "Trigger type for the task. Default: 'message'.",
                        },
                        "initial_state": {
                            "type": "object",
                            "description": "Optional initial state/parameters for the task.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_schedule_agent_task_tool_schema(tool_schemas: list):
    """Register the schedule_agent_task MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="schedule_agent_task",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Create a scheduled task from a skill. Supports repeat intervals: "
            "seconds, minutes, hours, daily, weekly, monthly, yearly."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["schedule"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent. Optional.",
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill. Required if skill_id not provided.",
                        },
                        "skill_id": {
                            "type": "string",
                            "description": "ID of the skill. Alternative to skill_name.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Custom name for the task.",
                        },
                        "initial_state": {
                            "type": "object",
                            "description": "Optional initial state for the task.",
                        },
                        "schedule": {
                            "type": "object",
                            "required": ["repeat_type"],
                            "description": "Schedule configuration.",
                            "properties": {
                                "repeat_type": {
                                    "type": "string",
                                    "enum": ["none", "seconds", "minutes", "hours", "daily", "weekly", "monthly", "yearly"],
                                    "description": "How often to repeat.",
                                },
                                "repeat_number": {
                                    "type": "integer",
                                    "description": "Units between runs. Default: 1.",
                                },
                                "start_date_time": {
                                    "type": "string",
                                    "description": "Start datetime (ISO or 'YYYY-MM-DD HH:MM:SS'). Default: now.",
                                },
                                "end_date_time": {
                                    "type": "string",
                                    "description": "End datetime. Default: 10 years from now.",
                                },
                                "time_out": {
                                    "type": "integer",
                                    "description": "Timeout in seconds per run. Default: 120.",
                                },
                            },
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_delete_agent_task_tool_schema(tool_schemas: list):
    """Register the delete_agent_task MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="delete_agent_task",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Delete (remove) a task from the agent. Stops the task first if running."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent. Optional.",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "ID of the task to delete.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Name of the task to delete.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_stop_agent_task_tool_schema(tool_schemas: list):
    """Register the stop_agent_task MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="stop_agent_task",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Stop / cancel a running task. Returns the previous state of the task."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "ID of the agent. Optional.",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "ID of the task to stop.",
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Name of the task to stop.",
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Force stop even in critical section. Default: false.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for Server ====================

async def async_launch_agent_task(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for launch_agent_task tool."""
    try:
        input_config = args.get("input", {})
        result = launch_agent_task(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Task launched successfully")
        else:
            msg = f"Failed to launch task: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncLaunchAgentTask")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_create_agent_task_with_skill(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for create_agent_task_with_skill tool."""
    try:
        input_config = args.get("input", {})
        result = create_agent_task_with_skill(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Task created successfully")
        else:
            msg = f"Failed to create task: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncCreateAgentTaskWithSkill")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_schedule_agent_task(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for schedule_agent_task tool."""
    try:
        input_config = args.get("input", {})
        result = schedule_agent_task(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Task scheduled successfully")
        else:
            msg = f"Failed to schedule task: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncScheduleAgentTask")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_delete_agent_task(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for delete_agent_task tool."""
    try:
        input_config = args.get("input", {})
        result = delete_agent_task(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Task deleted successfully")
        else:
            msg = f"Failed to delete task: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDeleteAgentTask")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_stop_agent_task(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for stop_agent_task tool."""
    try:
        input_config = args.get("input", {})
        result = stop_agent_task(mainwin, input_config)

        if result.get("success"):
            msg = result.get("message", "Task stopped successfully")
        else:
            msg = f"Failed to stop task: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncStopAgentTask")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


# ==================== Task Progress Visibility ====================

def get_task_progress(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get progress of a launched task and its entire nested chain.

    Can query by:
      - run_id: Get status of a specific task run
      - correlation_id: Get status of an entire task chain (all nested tasks)

    Returns live snapshots of all tasks in the chain, their current node,
    status, and recent progress events.

    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - run_id: str (optional) - specific task run to query
            - correlation_id: str (optional) - entire chain to query
            - include_events: bool (optional) - include recent events (default True)
            - event_limit: int (optional) - max events to return (default 20)

    Returns:
        Dict with progress information.
    """
    try:
        run_id = config.get("run_id", "")
        correlation_id = config.get("correlation_id", "")
        include_events = config.get("include_events", True)
        event_limit = int(config.get("event_limit", 20) or 20)

        if not run_id and not correlation_id:
            return _error("run_id or correlation_id is required")

        from .task_progress_bus import TaskProgressBus
        bus = TaskProgressBus.get_instance()

        # If only run_id provided, get single task snapshot
        if run_id and not correlation_id:
            snapshot = bus.get_task_snapshot(run_id)
            if snapshot is None:
                return _error(f"No task found with run_id={run_id!r}")

            result = {
                "success": True,
                "task": snapshot,
                "overall_status": snapshot.get("status", "unknown"),
                "timestamp": int(time.time() * 1000),
            }
            if include_events:
                # Try to find correlation_id from snapshot context
                corr = correlation_id
                if not corr:
                    # Look up correlation from the snapshot's chain membership
                    with bus._bus_lock:
                        for c_id, run_ids in bus._chain.items():
                            if run_id in run_ids:
                                corr = c_id
                                break
                if corr:
                    result["recent_events"] = bus.get_history(corr, limit=event_limit)
            return result

        # correlation_id provided — get full chain
        chain_status = bus.get_chain_status(correlation_id)
        chain_status["success"] = True
        chain_status["timestamp"] = int(time.time() * 1000)

        if not include_events:
            chain_status.pop("recent_events", None)
        elif event_limit and "recent_events" in chain_status:
            chain_status["recent_events"] = chain_status["recent_events"][-event_limit:]

        return chain_status

    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetTaskProgress")
        logger.error(err_trace)
        return _error(err_trace)


def add_get_task_progress_tool_schema(tool_schemas: list):
    """Register the get_task_progress MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="get_task_progress",
        description=(
            "<category>Agent</category><sub-category>Task Management</sub-category>"
            "Get the progress of a launched task and its nested sub-tasks. "
            "Query by run_id for a single task or correlation_id for the entire chain. "
            "Returns current node, status, child tasks, and recent events."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "run_id": {
                            "type": "string",
                            "description": "Run ID of a specific task to query (returned by launch_agent_task).",
                        },
                        "correlation_id": {
                            "type": "string",
                            "description": "Correlation ID for the entire task chain (returned by launch_agent_task).",
                        },
                        "include_events": {
                            "type": "boolean",
                            "description": "Include recent progress events. Default: true.",
                        },
                        "event_limit": {
                            "type": "integer",
                            "description": "Max number of recent events to return. Default: 20.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


async def async_get_task_progress(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for get_task_progress tool."""
    try:
        input_config = args.get("input", {})
        result = get_task_progress(mainwin, input_config)

        if result.get("success"):
            msg = json.dumps(result, default=str, ensure_ascii=False)
        else:
            msg = f"Failed to get task progress: {result.get('error', 'Unknown error')}"

        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]

    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncGetTaskProgress")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
