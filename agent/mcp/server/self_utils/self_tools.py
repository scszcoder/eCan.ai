"""
Self Tools - MCP tools for agent self-introspection and task management.

Tools:
- describe_self: Returns structured JSON of agent description (skills, tasks)
- start_task_using_skill: Start a new task using a specified skill
- stop_task_using_skill: Stop a running task
- schedule_task: Schedule a task to run at specified times

Naming convention follows server.py and tool_schemas.py patterns.
"""

import json
import time
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id
from app_context import AppContext
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Tool Implementations ====================

def describe_self(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get a structured JSON description of the agent including all skills and tasks.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with optional 'agent_id'
        
    Returns:
        Structured dict with agent description:
        {
            "agent_id": str,
            "agent_name": str,
            "agent_description": str,
            "skills": [
                {
                    "id": str,
                    "name": str,
                    "description": str,
                    "type": str,
                    "enabled": bool
                }
            ],
            "tasks": {
                "running": [...],
                "pending": [...],
                "completed": [...],
                "failed": [...]
            },
            "status": str,
            "timestamp": int
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        
        # Get agent by ID or use first available agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            # Try to get from mainwin
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Build agent description
        result = {
            "agent_id": agent_id,
            "agent_name": getattr(getattr(agent, 'card', None), 'name', 'Unknown'),
            "agent_description": getattr(getattr(agent, 'card', None), 'description', ''),
            "skills": [],
            "tasks": {
                "running": [],
                "pending": [],
                "completed": [],
                "failed": []
            },
            "status": getattr(agent, 'status', 'unknown'),
            "timestamp": int(time.time() * 1000)
        }
        
        # Collect skills information
        skills = getattr(agent, 'skills', []) or []
        for skill in skills:
            skill_info = {
                "id": getattr(skill, 'id', '') or getattr(skill, 'name', 'unknown'),
                "name": getattr(skill, 'name', 'Unknown'),
                "description": getattr(skill, 'description', ''),
                "type": getattr(skill, 'type', 'unknown'),
                "enabled": getattr(skill, 'enabled', True)
            }
            # Add skill tags if available
            if hasattr(skill, 'tags') and skill.tags:
                skill_info["tags"] = skill.tags
            result["skills"].append(skill_info)
        
        # Collect tasks information
        tasks = getattr(agent, 'tasks', []) or []
        for task in tasks:
            task_info = {
                "id": getattr(task, 'id', 'unknown'),
                "name": getattr(task, 'name', 'Unknown'),
                "skill_name": getattr(getattr(task, 'skill', None), 'name', 'unknown'),
                "state": "unknown",
                "created_at": None,
                "run_id": getattr(task, 'run_id', None)
            }
            
            # Get task state
            task_status = getattr(task, 'status', None)
            if task_status:
                state = getattr(task_status, 'state', None)
                if state:
                    task_info["state"] = state.value if hasattr(state, 'value') else str(state)
            
            # Get schedule info if available
            schedule = getattr(task, 'schedule', None)
            if schedule:
                task_info["schedule"] = {
                    "next_run": getattr(schedule, 'next_run', None),
                    "repeat_type": getattr(schedule, 'repeat_type', None)
                }
            
            # Categorize task by state
            state_str = task_info["state"].lower() if task_info["state"] else "unknown"
            if state_str in ("working", "running", "in_progress"):
                result["tasks"]["running"].append(task_info)
            elif state_str in ("pending", "scheduled", "queued", "unknown"):
                result["tasks"]["pending"].append(task_info)
            elif state_str in ("completed", "done", "success"):
                result["tasks"]["completed"].append(task_info)
            elif state_str in ("failed", "error", "canceled"):
                result["tasks"]["failed"].append(task_info)
            else:
                result["tasks"]["pending"].append(task_info)
        
        logger.info(f"[describe_self] Agent {agent_id}: {len(result['skills'])} skills, "
                   f"{len(result['tasks']['running'])} running tasks")
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorDescribeSelf")
        logger.error(err_trace)
        return {
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


def start_task_using_skill(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Start a new task using a specified skill.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional, uses first agent if not provided)
            - skill_name: str (required) - Name of the skill to use
            - task_name: str (optional) - Custom name for the task
            - initial_state: dict (optional) - Initial state for the task
            
    Returns:
        Dict with task start result:
        {
            "success": bool,
            "task_id": str,
            "task_name": str,
            "skill_name": str,
            "message": str,
            "timestamp": int
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        skill_name = config.get("skill_name", "")
        task_name = config.get("task_name", "")
        initial_state = config.get("initial_state", {})
        
        if not skill_name:
            return {
                "success": False,
                "error": "skill_name is required",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {
                "success": False,
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Find the skill
        skills = getattr(agent, 'skills', []) or []
        target_skill = None
        for skill in skills:
            if getattr(skill, 'name', '') == skill_name or getattr(skill, 'id', '') == skill_name:
                target_skill = skill
                break
        
        if not target_skill:
            available_skills = [getattr(s, 'name', 'unknown') for s in skills]
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found. Available skills: {available_skills}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Create and start task
        from agent.ec_tasks import ManagedTask
        import uuid
        
        task_id = str(uuid.uuid4())
        if not task_name:
            task_name = f"{skill_name}_task_{task_id[:8]}"
        
        # Create managed task with proper trigger and run_id
        import uuid as uuid_module
        run_id = str(uuid_module.uuid4())
        
        new_task = ManagedTask(
            id=task_id,
            run_id=run_id,
            name=task_name,
            skill=target_skill,
            trigger="interaction",  # MCP tool invocation is an interaction trigger
            metadata={"initial_state": initial_state} if initial_state else {}
        )
        
        # Add task to agent
        if not hasattr(agent, 'tasks') or agent.tasks is None:
            agent.tasks = []
        agent.tasks.append(new_task)
        
        # Start the task via runner (like ec_agent.py does)
        runner = getattr(agent, 'runner', None)
        if runner:
            from concurrent.futures import ThreadPoolExecutor
            try:
                # Get or create thread pool executor
                thread_pool = getattr(agent, 'thread_pool_executor', None)
                if not thread_pool:
                    thread_pool = ThreadPoolExecutor(max_workers=4)
                
                # Launch via runner.launch_unified_run (the proper way)
                future = thread_pool.submit(
                    runner.launch_unified_run,
                    new_task,
                    "interaction"  # trigger_type
                )
                
                # Register active task if agent supports it
                if hasattr(agent, 'active_tasks') and hasattr(agent, 'task_lock'):
                    with agent.task_lock:
                        agent.active_tasks[run_id] = future
                
                logger.info(f"[start_task_using_skill] Task {task_id} submitted to runner, run_id={run_id}")
            except Exception as launch_err:
                logger.error(f"[start_task_using_skill] Could not launch task: {launch_err}")
                return {
                    "success": False,
                    "error": f"Failed to launch task: {launch_err}",
                    "timestamp": int(time.time() * 1000)
                }
        else:
            logger.warning(f"[start_task_using_skill] No runner available for agent {agent_id}")
        
        result = {
            "success": True,
            "task_id": task_id,
            "task_name": task_name,
            "skill_name": skill_name,
            "agent_id": agent_id,
            "message": f"Task '{task_name}' created using skill '{skill_name}'",
            "timestamp": int(time.time() * 1000)
        }
        
        logger.info(f"[start_task_using_skill] Started task {task_id} with skill {skill_name}")
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStartTaskUsingSkill")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


def stop_task_using_skill(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop a running task.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional, uses first agent if not provided)
            - task_id: str (required) - ID of the task to stop
            - force: bool (optional) - Force stop even if task is in critical section
            
    Returns:
        Dict with task stop result:
        {
            "success": bool,
            "task_id": str,
            "previous_state": str,
            "message": str,
            "timestamp": int
        }
    """
    try:
        agent_id = config.get("agent_id", "")
        task_id = config.get("task_id", "")
        force = config.get("force", False)
        
        if not task_id:
            return {
                "success": False,
                "error": "task_id is required",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {
                "success": False,
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Find the task
        tasks = getattr(agent, 'tasks', []) or []
        target_task = None
        for task in tasks:
            if getattr(task, 'id', '') == task_id or getattr(task, 'run_id', '') == task_id:
                target_task = task
                break
        
        if not target_task:
            return {
                "success": False,
                "error": f"Task '{task_id}' not found",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get previous state
        previous_state = "unknown"
        task_status = getattr(target_task, 'status', None)
        if task_status:
            state = getattr(task_status, 'state', None)
            if state:
                previous_state = state.value if hasattr(state, 'value') else str(state)
        
        # Cancel the task
        cancelled = False
        
        # Try cancellation event
        if hasattr(target_task, 'cancellation_event'):
            target_task.cancellation_event.set()
            cancelled = True
            logger.info(f"[stop_task_using_skill] Set cancellation event for task {task_id}")
        
        # Try cancel method
        if hasattr(target_task, 'cancel') and callable(target_task.cancel):
            target_task.cancel()
            cancelled = True
            logger.info(f"[stop_task_using_skill] Called cancel() for task {task_id}")
        
        # Update task state
        from agent.a2a.common.types import TaskState
        if task_status and hasattr(task_status, 'state'):
            task_status.state = TaskState.CANCELED
        
        # Remove from active tasks if using runner
        runner = getattr(agent, 'runner', None)
        if runner and hasattr(runner, 'active_tasks'):
            if task_id in runner.active_tasks:
                del runner.active_tasks[task_id]
        
        result = {
            "success": True,
            "task_id": task_id,
            "task_name": getattr(target_task, 'name', 'Unknown'),
            "previous_state": previous_state,
            "agent_id": agent_id,
            "message": f"Task '{task_id}' has been stopped",
            "timestamp": int(time.time() * 1000)
        }
        
        logger.info(f"[stop_task_using_skill] Stopped task {task_id}, previous state: {previous_state}")
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStopTaskUsingSkill")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


def schedule_task(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Schedule a task to run at specified times using a skill.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - agent_id: str (optional, uses first agent if not provided)
            - skill_name: str (required) - Name of the skill to use
            - task_name: str (optional) - Custom name for the task
            - initial_state: dict (optional) - Initial state for the task
            - schedule: dict (required) - Schedule configuration:
                - repeat_type: str - One of: "none", "by seconds", "by minutes", 
                                     "by hours", "by days", "by weeks", "by months", "by years"
                - repeat_number: int - Number of units between runs (e.g., 2 for every 2 hours)
                - start_date_time: str - Start datetime (format: "YYYY-MM-DD HH:MM:SS:fff")
                - end_date_time: str (optional) - End datetime, defaults to 10 years from now
                - time_out: int (optional) - Timeout in seconds, default 120
            
    Returns:
        Dict with task scheduling result:
        {
            "success": bool,
            "task_id": str,
            "task_name": str,
            "schedule": dict,
            "message": str,
            "timestamp": int
        }
    """
    from datetime import datetime, timedelta
    from agent.ec_tasks import ManagedTask, TaskSchedule, RepeatType
    from agent.ec_tasks.models import TaskStatus, TaskState
    
    try:
        agent_id = config.get("agent_id", "")
        skill_name = config.get("skill_name", "")
        task_name = config.get("task_name", "")
        initial_state = config.get("initial_state", {})
        schedule_config = config.get("schedule", {})
        
        if not skill_name:
            return {
                "success": False,
                "error": "skill_name is required",
                "timestamp": int(time.time() * 1000)
            }
        
        if not schedule_config:
            return {
                "success": False,
                "error": "schedule configuration is required",
                "timestamp": int(time.time() * 1000)
            }
        
        # Get agent
        agent = None
        if agent_id:
            agent = get_agent_by_id(agent_id)
        else:
            if hasattr(mainwin, 'agents') and mainwin.agents:
                agent = mainwin.agents[0]
                agent_id = getattr(getattr(agent, 'card', None), 'id', 'unknown')
        
        if not agent:
            return {
                "success": False,
                "error": f"Agent not found: {agent_id}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Find the skill
        skills = getattr(agent, 'skills', []) or []
        target_skill = None
        for skill in skills:
            if getattr(skill, 'name', '') == skill_name:
                target_skill = skill
                break
        
        if not target_skill:
            available_skills = [getattr(s, 'name', 'unknown') for s in skills]
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found. Available: {available_skills}",
                "timestamp": int(time.time() * 1000)
            }
        
        # Parse repeat_type
        repeat_type_str = schedule_config.get("repeat_type", "none").lower().strip()
        repeat_type_map = {
            "none": RepeatType.NONE,
            "by seconds": RepeatType.BY_SECONDS,
            "by_seconds": RepeatType.BY_SECONDS,
            "seconds": RepeatType.BY_SECONDS,
            "by minutes": RepeatType.BY_MINUTES,
            "by_minutes": RepeatType.BY_MINUTES,
            "minutes": RepeatType.BY_MINUTES,
            "by hours": RepeatType.BY_HOURS,
            "by_hours": RepeatType.BY_HOURS,
            "hours": RepeatType.BY_HOURS,
            "hourly": RepeatType.BY_HOURS,
            "by days": RepeatType.BY_DAYS,
            "by_days": RepeatType.BY_DAYS,
            "days": RepeatType.BY_DAYS,
            "daily": RepeatType.BY_DAYS,
            "by weeks": RepeatType.BY_WEEKS,
            "by_weeks": RepeatType.BY_WEEKS,
            "weeks": RepeatType.BY_WEEKS,
            "weekly": RepeatType.BY_WEEKS,
            "by months": RepeatType.BY_MONTHS,
            "by_months": RepeatType.BY_MONTHS,
            "months": RepeatType.BY_MONTHS,
            "monthly": RepeatType.BY_MONTHS,
            "by years": RepeatType.BY_YEARS,
            "by_years": RepeatType.BY_YEARS,
            "years": RepeatType.BY_YEARS,
            "yearly": RepeatType.BY_YEARS,
        }
        
        repeat_type = repeat_type_map.get(repeat_type_str, RepeatType.NONE)
        repeat_number = int(schedule_config.get("repeat_number", 1))
        
        # Parse datetime format - support multiple formats
        datetime_fmt = "%Y-%m-%d %H:%M:%S:%f"
        datetime_fmt_alt = "%Y-%m-%d %H:%M:%S"
        
        def parse_datetime(dt_str: str, default: datetime) -> str:
            """Parse datetime string and return in standard format."""
            if not dt_str:
                return default.strftime(datetime_fmt)[:-3] + "000"  # Ensure :fff format
            try:
                # Try standard format first
                dt = datetime.strptime(dt_str, datetime_fmt)
                return dt_str
            except ValueError:
                pass
            try:
                # Try without microseconds
                dt = datetime.strptime(dt_str, datetime_fmt_alt)
                return dt.strftime(datetime_fmt)[:-3] + "000"
            except ValueError:
                pass
            try:
                # Try ISO format
                dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
                return dt.strftime(datetime_fmt)[:-3] + "000"
            except ValueError:
                pass
            # Return default
            return default.strftime(datetime_fmt)[:-3] + "000"
        
        now = datetime.now()
        default_end = now + timedelta(days=365 * 10)  # 10 years from now
        
        start_date_time = parse_datetime(schedule_config.get("start_date_time", ""), now)
        end_date_time = parse_datetime(schedule_config.get("end_date_time", ""), default_end)
        time_out = int(schedule_config.get("time_out", 120))
        
        # Create TaskSchedule
        task_schedule = TaskSchedule(
            repeat_type=repeat_type,
            repeat_number=repeat_number,
            repeat_unit=repeat_type_str,
            start_date_time=start_date_time,
            end_date_time=end_date_time,
            time_out=time_out
        )
        
        # Generate task name if not provided
        if not task_name:
            task_name = f"Scheduled_{skill_name}_{int(time.time())}"
        
        # Create the task
        import uuid
        task_id = str(uuid.uuid4())[:8]
        task_state = initial_state or {"top": "ready"}
        status = TaskStatus(state=TaskState.SUBMITTED)
        
        new_task = ManagedTask(
            id=task_id,
            name=task_name,
            description=f"Scheduled task using skill '{skill_name}'",
            source="mcp_tool",
            status=status,
            sessionId="",
            skill=target_skill,
            metadata={"state": task_state},
            state=task_state,
            resume_from="",
            trigger="schedule",
            schedule=task_schedule
        )
        
        # Add task to agent's task list
        if not hasattr(agent, 'tasks') or agent.tasks is None:
            agent.tasks = []
        agent.tasks.append(new_task)
        
        # Also register with TaskRunner if available
        task_runner = getattr(agent, 'task_runner', None)
        if task_runner and hasattr(task_runner, 'tasks'):
            task_runner.tasks[task_id] = new_task
            logger.info(f"[schedule_task] Registered task {task_id} with TaskRunner")
        
        result = {
            "success": True,
            "task_id": task_id,
            "task_name": task_name,
            "skill_name": skill_name,
            "schedule": {
                "repeat_type": repeat_type.value,
                "repeat_number": repeat_number,
                "start_date_time": start_date_time,
                "end_date_time": end_date_time,
                "time_out": time_out
            },
            "message": f"Task '{task_name}' scheduled successfully with {repeat_type.value} interval",
            "timestamp": int(time.time() * 1000)
        }
        
        logger.info(f"[schedule_task] Created scheduled task: {task_name} (id={task_id}), schedule={repeat_type.value} every {repeat_number}")
        return result
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorScheduleTask")
        logger.error(err_trace)
        return {
            "success": False,
            "error": err_trace,
            "timestamp": int(time.time() * 1000)
        }


# ==================== Tool Schema Functions ====================

def add_describe_self_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add describe_self tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="describe_self",
        description=(
            "<category>Agent</category><sub-category>Self</sub-category>"
            "Get a structured JSON description of the agent including all skills (with descriptions) "
            "and all tasks (running, pending, completed, failed). Useful for agent self-introspection "
            "and capability discovery."
        ),
        inputSchema={
            "type": "object",
            "required": [],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID to describe. If not provided, uses the first available agent."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_start_task_using_skill_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add start_task_using_skill tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="start_task_using_skill",
        description=(
            "<category>Agent</category><sub-category>Task</sub-category>"
            "Start a new task using a specified skill. The skill must be available on the agent. "
            "Returns the task ID and status."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["skill_name"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID. If not provided, uses the first available agent."
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill to use for the task."
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Optional custom name for the task."
                        },
                        "initial_state": {
                            "type": "object",
                            "description": "Optional initial state/parameters for the task."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_stop_task_using_skill_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add stop_task_using_skill tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="stop_task_using_skill",
        description=(
            "<category>Agent</category><sub-category>Task</sub-category>"
            "Stop a running task by its task ID. The task will be cancelled and its state updated."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["task_id"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID. If not provided, uses the first available agent."
                        },
                        "task_id": {
                            "type": "string",
                            "description": "ID of the task to stop."
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Force stop even if task is in a critical section. Default: false."
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


def add_schedule_task_tool_schema(tool_schemas: List[types.Tool]) -> None:
    """Add schedule_task tool schema to the tool schemas list."""
    tool_schema = types.Tool(
        name="schedule_task",
        description=(
            "<category>Agent</category><sub-category>Task</sub-category>"
            "Schedule a task to run at specified times using a skill. "
            "Supports various repeat intervals: seconds, minutes, hours, days, weeks, months, years. "
            "The task will be automatically triggered by the scheduler at the specified times."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": ["skill_name", "schedule"],
                    "properties": {
                        "agent_id": {
                            "type": "string",
                            "description": "Agent ID. If not provided, uses the first available agent."
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill to use for the scheduled task."
                        },
                        "task_name": {
                            "type": "string",
                            "description": "Optional custom name for the task."
                        },
                        "initial_state": {
                            "type": "object",
                            "description": "Optional initial state/parameters for the task."
                        },
                        "schedule": {
                            "type": "object",
                            "required": ["repeat_type"],
                            "description": "Schedule configuration for the task.",
                            "properties": {
                                "repeat_type": {
                                    "type": "string",
                                    "enum": ["none", "seconds", "minutes", "hours", "daily", "weekly", "monthly", "yearly"],
                                    "description": "How often to repeat: 'none' (one-time), 'seconds', 'minutes', 'hours', 'daily', 'weekly', 'monthly', 'yearly'."
                                },
                                "repeat_number": {
                                    "type": "integer",
                                    "description": "Number of units between runs. E.g., 2 with 'hours' means every 2 hours. Default: 1."
                                },
                                "start_date_time": {
                                    "type": "string",
                                    "description": "Start datetime in format 'YYYY-MM-DD HH:MM:SS' or ISO format. Default: now."
                                },
                                "end_date_time": {
                                    "type": "string",
                                    "description": "End datetime. Default: 10 years from now."
                                },
                                "time_out": {
                                    "type": "integer",
                                    "description": "Timeout in seconds for each task run. Default: 120."
                                }
                            }
                        }
                    }
                }
            }
        }
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for Server ====================

async def async_describe_self(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for describe_self tool."""
    try:
        input_config = args.get('input', {})
        result = describe_self(mainwin, input_config)
        
        msg = f"Agent description retrieved successfully"
        if "error" in result:
            msg = f"Error: {result['error']}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"agent_description": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncDescribeSelf")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_start_task_using_skill(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for start_task_using_skill tool."""
    try:
        input_config = args.get('input', {})
        result = start_task_using_skill(mainwin, input_config)
        
        if result.get("success"):
            msg = result.get("message", "Task started successfully")
        else:
            msg = f"Failed to start task: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncStartTaskUsingSkill")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_stop_task_using_skill(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for stop_task_using_skill tool."""
    try:
        input_config = args.get('input', {})
        result = stop_task_using_skill(mainwin, input_config)
        
        if result.get("success"):
            msg = result.get("message", "Task stopped successfully")
        else:
            msg = f"Failed to stop task: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncStopTaskUsingSkill")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]


async def async_schedule_task(mainwin, args: Dict[str, Any]) -> List[TextContent]:
    """Async wrapper for schedule_task tool."""
    try:
        input_config = args.get('input', {})
        result = schedule_task(mainwin, input_config)
        
        if result.get("success"):
            msg = result.get("message", "Task scheduled successfully")
        else:
            msg = f"Failed to schedule task: {result.get('error', 'Unknown error')}"
        
        text_result = TextContent(type="text", text=msg)
        text_result.meta = {"task_result": result}
        return [text_result]
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncScheduleTask")
        logger.error(err_trace)
        return [TextContent(type="text", text=err_trace)]
