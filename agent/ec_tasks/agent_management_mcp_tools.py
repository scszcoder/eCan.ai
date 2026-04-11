"""
Agent Management MCP Tools - MCP tools for spawning and managing worker agents.

Tools:
- spawn_worker_agent: Spawn a worker agent with a skill to run in parallel
- stop_worker_agents: Stop one or more worker agents
- get_worker_agent_status: Get status of worker agents
- list_worker_agents: List all active worker agents

Category: Managerial (restricted to orchestrator/manager agents)

These tools enable parallel agent orchestration patterns like:
- Multi-customer chat handling (1 orchestrator + N workers)
- Parallel data processing (1 coordinator + N processors)
- Distributed task execution (1 manager + N executors)
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import mcp.types as types
from mcp.types import TextContent

from agent.agent_service import get_agent_by_id, register_agent, unregister_agent
from utils.logger_helper import logger_helper as logger, get_traceback


# ==================== Global Worker Registry ====================

# Track all spawned worker agents across the application
# Key: worker_id, Value: {"worker": EC_Agent, "spawned_by": agent_id, "spawned_at": timestamp, ...}
_WORKER_REGISTRY: Dict[str, dict] = {}


# ==================== Tool Implementations ====================

def spawn_worker_agent(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Spawn a worker agent with a skill to run in parallel.
    
    This creates a new EC_Agent instance, registers it globally, loads a skill,
    and starts the skill execution. The worker runs independently in parallel
    with the orchestrator agent.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - orchestrator_agent_id: str (optional) - ID of the orchestrator agent
            - worker_id: str (optional) - Custom ID for worker (auto-generated if not provided)
            - worker_name: str (optional) - Display name for worker
            - skill: dict (required) - Complete skill definition (nodes, edges, config)
            - skill_name: str (optional) - Name of existing skill to load
            - skill_id: str (optional) - ID of existing skill to load
            - timeout: int (optional) - Timeout in seconds (default: 60)
            - metadata: dict (optional) - Additional metadata to attach to worker
    
    Returns:
        Dict with spawn result:
        {
            "success": bool,
            "worker_id": str,
            "worker_name": str,
            "task_id": str,
            "run_id": str,
            "orchestrator_id": str,
            "message": str,
            "timestamp": int
        }
    """
    try:
        orchestrator_id = config.get("orchestrator_agent_id", "")
        worker_id = config.get("worker_id") or f"worker_{uuid.uuid4().hex[:8]}"
        worker_name = config.get("worker_name") or f"Worker {worker_id}"
        skill_dict = config.get("skill")
        skill_name = config.get("skill_name", "")
        skill_id = config.get("skill_id", "")
        timeout = int(config.get("timeout", 60))
        metadata = config.get("metadata", {})
        
        # Validate inputs
        if not skill_dict and not skill_name and not skill_id:
            return _error("Either 'skill' dict, 'skill_name', or 'skill_id' is required")
        
        # Resolve orchestrator agent
        orchestrator = _resolve_agent(mainwin, orchestrator_id)
        if orchestrator is None:
            return _error(f"Orchestrator agent not found: {orchestrator_id or '(default)'}")
        
        orchestrator_id = _get_agent_id(orchestrator)
        
        # Create worker agent instance
        from agent.ec_agent import EC_Agent
        
        worker = EC_Agent(
            id=worker_id,
            name=worker_name,
            mainwin=mainwin,
        )
        
        # Register worker globally so it can access shared resources (browser, etc.)
        register_agent(worker)
        
        logger.info(f"[AgentManagement] Created worker agent: {worker_id} (name={worker_name})")
        
        # Load or build skill
        if skill_dict:
            # Use provided skill dictionary
            skill = _dict_to_skill(skill_dict, worker)
        else:
            # Load existing skill from worker's skills
            skill = _resolve_skill(worker, skill_name, skill_id)
            if skill is None:
                # Try to load from orchestrator's skills
                skill = _resolve_skill(orchestrator, skill_name, skill_id)
                if skill is None:
                    unregister_agent(worker_id)
                    return _error(f"Skill not found (name={skill_name!r}, id={skill_id!r})")
        
        # Create and start task
        from agent.ec_tasks.models import ManagedTask, TaskStatus, TaskState
        
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        
        task = ManagedTask(
            id=task_id,
            run_id=run_id,
            name=f"{worker_name}_task",
            description=f"Worker task spawned by {orchestrator_id}",
            source="mcp_tool_spawn_worker",
            status=TaskStatus(state=TaskState.submitted),
            sessionId="",
            skill=skill,
            metadata={
                "orchestrator_id": orchestrator_id,
                "timeout": timeout,
                **metadata
            },
            state={},
            resume_from="",
            trigger="immediate",
            agent_id=worker_id,
        )
        
        if not hasattr(worker, "tasks") or worker.tasks is None:
            worker.tasks = []
        worker.tasks.append(task)
        
        # Start task execution
        _start_task_loop(worker, task)
        
        # Start chat event monitoring if chat_id and platform_id provided
        monitor_id = None
        if metadata.get('chat_id') and metadata.get('platform_id'):
            try:
                from agent.ec_tasks.chat_event_dispatcher import get_chat_event_dispatcher
                
                dispatcher = get_chat_event_dispatcher()
                
                def on_new_message(event: dict):
                    """Handle new message events for this worker."""
                    logger.info(
                        f"[WorkerAgent] New message for worker {worker_id}: "
                        f"chat_id={event.get('chat_id')}, source={event.get('source')}"
                    )
                    # Resume worker task if it's waiting for events
                    # This will be handled by the event routing system
                
                monitor_id = dispatcher.start_monitoring(
                    agent_id=worker_id,
                    platform_id=metadata['platform_id'],
                    cdp_client=metadata.get('cdp_client'),
                    browser_session=metadata.get('browser_session'),
                    on_new_message=on_new_message,
                    chat_id_filter=metadata['chat_id']
                )
                
                logger.info(
                    f"[AgentManagement] Started event monitoring for worker {worker_id} "
                    f"(platform={metadata['platform_id']}, chat_id={metadata['chat_id']}, "
                    f"monitor_id={monitor_id[:8] if monitor_id else 'none'})"
                )
            except Exception as e:
                logger.error(f"[AgentManagement] Failed to start event monitoring: {e}")
        
        # Register in worker registry
        _WORKER_REGISTRY[worker_id] = {
            "worker": worker,
            "worker_id": worker_id,
            "worker_name": worker_name,
            "orchestrator_id": orchestrator_id,
            "monitor_id": monitor_id,
            "task_id": task_id,
            "run_id": run_id,
            "spawned_at": time.time(),
            "timeout": timeout,
            "metadata": metadata,
            "status": "running",
        }
        
        logger.info(
            f"[AgentManagement] ✅ Spawned worker {worker_id} for orchestrator {orchestrator_id} "
            f"(task_id={task_id}, timeout={timeout}s)"
        )
        
        return {
            "success": True,
            "worker_id": worker_id,
            "worker_name": worker_name,
            "task_id": task_id,
            "run_id": run_id,
            "orchestrator_id": orchestrator_id,
            "message": f"Worker '{worker_name}' spawned successfully (task_id={task_id})",
            "timestamp": int(time.time() * 1000),
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorSpawnWorkerAgent")
        logger.error(err_trace)
        return _error(err_trace)


def stop_worker_agents(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Stop one or more worker agents.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - worker_ids: list[str] (optional) - List of worker IDs to stop
            - worker_id: str (optional) - Single worker ID to stop
            - orchestrator_agent_id: str (optional) - Stop all workers for this orchestrator
            - stop_all: bool (optional) - Stop all workers (use with caution)
    
    Returns:
        Dict with stop result:
        {
            "success": bool,
            "stopped_count": int,
            "stopped_workers": list[str],
            "message": str,
            "timestamp": int
        }
    """
    try:
        worker_ids = config.get("worker_ids", [])
        single_worker_id = config.get("worker_id", "")
        orchestrator_id = config.get("orchestrator_agent_id", "")
        stop_all = config.get("stop_all", False)
        
        # Build list of workers to stop
        to_stop = []
        
        if single_worker_id:
            to_stop.append(single_worker_id)
        
        if worker_ids:
            to_stop.extend(worker_ids)
        
        if orchestrator_id:
            # Stop all workers spawned by this orchestrator
            for wid, info in _WORKER_REGISTRY.items():
                if info.get("orchestrator_id") == orchestrator_id:
                    to_stop.append(wid)
        
        if stop_all:
            # Stop ALL workers
            to_stop = list(_WORKER_REGISTRY.keys())
        
        if not to_stop:
            return _error("No workers specified to stop. Provide worker_id, worker_ids, orchestrator_agent_id, or stop_all=true")
        
        # Stop each worker
        stopped = []
        for worker_id in to_stop:
            if worker_id not in _WORKER_REGISTRY:
                logger.warning(f"[AgentManagement] Worker {worker_id} not found in registry, skipping")
                continue
            
            info = _WORKER_REGISTRY[worker_id]
            worker = info["worker"]
            
            try:
                # Stop event monitoring if active
                monitor_id = info.get("monitor_id")
                if monitor_id:
                    try:
                        from agent.ec_tasks.chat_event_dispatcher import get_chat_event_dispatcher
                        dispatcher = get_chat_event_dispatcher()
                        dispatcher.stop_monitoring(monitor_id)
                        logger.info(f"[AgentManagement] Stopped event monitoring for worker {worker_id}")
                    except Exception as e:
                        logger.error(f"[AgentManagement] Failed to stop event monitoring: {e}")
                
                # Stop all tasks
                if hasattr(worker, "task_runner") and worker.task_runner:
                    worker.task_runner.stop_all_tasks()
                
                # Unregister agent
                unregister_agent(worker_id)
                
                # Remove from registry
                del _WORKER_REGISTRY[worker_id]
                
                stopped.append(worker_id)
                logger.info(f"[AgentManagement] 🛑 Stopped worker: {worker_id}")
                
            except Exception as e:
                logger.error(f"[AgentManagement] Error stopping worker {worker_id}: {e}")
        
        return {
            "success": True,
            "stopped_count": len(stopped),
            "stopped_workers": stopped,
            "message": f"Stopped {len(stopped)} worker(s)",
            "timestamp": int(time.time() * 1000),
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorStopWorkerAgents")
        logger.error(err_trace)
        return _error(err_trace)


def get_worker_agent_status(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Get status of worker agents.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - worker_ids: list[str] (optional) - List of worker IDs to check
            - worker_id: str (optional) - Single worker ID to check
            - orchestrator_agent_id: str (optional) - Check all workers for this orchestrator
    
    Returns:
        Dict with status information:
        {
            "success": bool,
            "workers": list[dict],  # List of worker status dicts
            "count": int,
            "timestamp": int
        }
    """
    try:
        worker_ids = config.get("worker_ids", [])
        single_worker_id = config.get("worker_id", "")
        orchestrator_id = config.get("orchestrator_agent_id", "")
        
        # Build list of workers to check
        to_check = []
        
        if single_worker_id:
            to_check.append(single_worker_id)
        
        if worker_ids:
            to_check.extend(worker_ids)
        
        if orchestrator_id:
            # Check all workers for this orchestrator
            for wid, info in _WORKER_REGISTRY.items():
                if info.get("orchestrator_id") == orchestrator_id:
                    to_check.append(wid)
        
        if not to_check:
            # Return all workers
            to_check = list(_WORKER_REGISTRY.keys())
        
        # Get status for each worker
        worker_statuses = []
        for worker_id in to_check:
            if worker_id not in _WORKER_REGISTRY:
                worker_statuses.append({
                    "worker_id": worker_id,
                    "status": "not_found",
                    "error": "Worker not in registry"
                })
                continue
            
            info = _WORKER_REGISTRY[worker_id]
            worker = info["worker"]
            task_id = info.get("task_id")
            
            # Check task status
            task_status = "unknown"
            task_state = "unknown"
            
            try:
                if hasattr(worker, "task_runner") and worker.task_runner:
                    task = worker.task_runner.tasks.get(task_id)
                    if task:
                        if hasattr(task, "status"):
                            state = task.status.state
                            task_state = state.value if hasattr(state, "value") else str(state)
                            
                            if task_state == "completed":
                                task_status = "completed"
                            elif task_state == "failed":
                                task_status = "failed"
                            elif task_state == "canceled":
                                task_status = "stopped"
                            else:
                                task_status = "running"
                    else:
                        task_status = "completed"  # Task no longer exists
            except Exception as e:
                logger.debug(f"[AgentManagement] Error checking status for {worker_id}: {e}")
            
            elapsed = time.time() - info["spawned_at"]
            
            worker_statuses.append({
                "worker_id": worker_id,
                "worker_name": info["worker_name"],
                "orchestrator_id": info["orchestrator_id"],
                "task_id": task_id,
                "run_id": info["run_id"],
                "status": task_status,
                "task_state": task_state,
                "elapsed_seconds": round(elapsed, 2),
                "timeout": info["timeout"],
                "metadata": info.get("metadata", {}),
            })
        
        return {
            "success": True,
            "workers": worker_statuses,
            "count": len(worker_statuses),
            "timestamp": int(time.time() * 1000),
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorGetWorkerAgentStatus")
        logger.error(err_trace)
        return _error(err_trace)


def list_worker_agents(mainwin, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    List all active worker agents.
    
    Args:
        mainwin: Main window instance
        config: Configuration dict with:
            - orchestrator_agent_id: str (optional) - Filter by orchestrator
            - include_completed: bool (optional) - Include completed workers (default: false)
    
    Returns:
        Dict with worker list:
        {
            "success": bool,
            "workers": list[dict],
            "active_count": int,
            "total_count": int,
            "timestamp": int
        }
    """
    try:
        orchestrator_id = config.get("orchestrator_agent_id", "")
        include_completed = config.get("include_completed", False)
        
        workers = []
        active_count = 0
        
        for worker_id, info in _WORKER_REGISTRY.items():
            # Filter by orchestrator if specified
            if orchestrator_id and info.get("orchestrator_id") != orchestrator_id:
                continue
            
            # Check if still active
            worker = info["worker"]
            task_id = info.get("task_id")
            is_active = False
            
            try:
                if hasattr(worker, "task_runner") and worker.task_runner:
                    task = worker.task_runner.tasks.get(task_id)
                    if task and hasattr(task, "status"):
                        state = task.status.state
                        state_str = state.value if hasattr(state, "value") else str(state)
                        is_active = state_str not in ("completed", "failed", "canceled")
            except Exception:
                pass
            
            if is_active:
                active_count += 1
            
            # Skip completed if not requested
            if not include_completed and not is_active:
                continue
            
            elapsed = time.time() - info["spawned_at"]
            
            workers.append({
                "worker_id": worker_id,
                "worker_name": info["worker_name"],
                "orchestrator_id": info["orchestrator_id"],
                "task_id": task_id,
                "is_active": is_active,
                "elapsed_seconds": round(elapsed, 2),
                "timeout": info["timeout"],
            })
        
        return {
            "success": True,
            "workers": workers,
            "active_count": active_count,
            "total_count": len(workers),
            "timestamp": int(time.time() * 1000),
        }
        
    except Exception as e:
        err_trace = get_traceback(e, "ErrorListWorkerAgents")
        logger.error(err_trace)
        return _error(err_trace)


# ==================== Internal Helpers ====================

def _error(msg: str) -> Dict[str, Any]:
    return {"success": False, "error": msg, "timestamp": int(time.time() * 1000)}


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


def _resolve_skill(agent, skill_name: str, skill_id: str):
    """Find a skill on the agent by name or id.

    Reloads from disk if the skill has a local file path, to pick up the latest changes.
    """
    skills = getattr(agent, "skills", []) or []
    for i, sk in enumerate(skills):
        if skill_name and getattr(sk, "name", "") != skill_name:
            if skill_id and getattr(sk, "id", "") != skill_id:
                continue
        # else matched

        skill_path = getattr(sk, "path", None) or ""
        if skill_path:
            from pathlib import Path
            p = Path(skill_path)
            if p.exists() and p.is_file() and p.suffix.lower() == ".json":
                # Only hot-reload if the skill is currently attached to an active task
                _in_use = False
                try:
                    from agent.ec_tasks.task_mcp_tools import _is_skill_in_use_by_active_task
                    _in_use = _is_skill_in_use_by_active_task(sk, mainwin)
                except Exception:
                    pass
                if not _in_use:
                    logger.debug(f"[_resolve_skill] Skill '{getattr(sk, 'name', '')}' not in active use, skipping reload")
                    # Return based on match type
                    if skill_name and getattr(sk, "name", "") == skill_name:
                        return sk
                    if skill_id and getattr(sk, "id", "") == skill_id:
                        return sk
                    return sk
                try:
                    from agent.ec_skills.build_agent_skills import load_skill_from_folder
                    _skill_root = p.parent.parent if p.parent.name == "diagram_dir" else p.parent
                    reloaded_sk = load_skill_from_folder(_skill_root, mainwin=None)
                    if reloaded_sk and getattr(reloaded_sk, "runnable", None) is not None:
                        skills[i] = reloaded_sk
                        logger.info(f"[_resolve_skill] ✅ Reloaded skill '{getattr(reloaded_sk, 'name', '')!r}'")
                        return reloaded_sk
                except Exception as e:
                    logger.warning(f"[_resolve_skill] ⚠️ Reload failed: {e}, using cached")

        if skill_name and getattr(sk, "name", "") == skill_name:
            return sk
        if skill_id and getattr(sk, "id", "") == skill_id:
            return sk
    return None


def _dict_to_skill(skill_dict: dict, agent):
    """Convert a skill dictionary to a Skill object."""
    from agent.ec_skill import Skill
    
    skill_id = skill_dict.get("id") or str(uuid.uuid4())
    skill_name = skill_dict.get("name", "worker_skill")
    
    skill = Skill(
        id=skill_id,
        name=skill_name,
        description=skill_dict.get("description", ""),
        config=skill_dict.get("config", {}),
        mapping_rules=skill_dict.get("mapping_rules", {}),
        owner=_get_agent_id(agent),
    )
    
    return skill


def _start_task_loop(agent, task):
    """Submit the task's execution loop to the agent's thread pool."""
    runner = getattr(agent, "runner", None)
    if not runner:
        logger.warning("[AgentManagement] No runner on agent, cannot start execution loop")
        return
    
    from concurrent.futures import ThreadPoolExecutor
    
    mainwin = getattr(agent, "mainwin", None)
    thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
    if not thread_pool:
        thread_pool = getattr(agent, "thread_pool_executor", None)
    
    # Use context manager if we need to create a temporary pool
    _pool_ctx = None
    if not thread_pool:
        _pool_ctx = ThreadPoolExecutor(max_workers=4)
        thread_pool = _pool_ctx
    
    try:
        future = thread_pool.submit(runner.launch_unified_run, task, ["immediate"])
        if hasattr(agent, "active_tasks") and hasattr(agent, "task_lock"):
            with agent.task_lock:
                agent.active_tasks[task.run_id] = future
        logger.info(f"[AgentManagement] Execution loop started for worker task: {task.name}")
    except Exception as e:
        logger.error(f"[AgentManagement] Failed to start execution loop: {e}")
    finally:
        if _pool_ctx:
            _pool_ctx.shutdown(wait=False)


# ==================== Tool Schemas ====================

def add_spawn_worker_agent_tool_schema(tool_schemas: list):
    """Register the spawn_worker_agent MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="spawn_worker_agent",
        description=(
            "<category>Managerial</category><sub-category>Agent Management</sub-category>"
            "Spawn a worker agent with a skill to run in parallel. Creates a new EC_Agent instance, "
            "registers it globally, and starts skill execution. The worker runs independently in parallel "
            "with the orchestrator agent. Use this for multi-customer chat, parallel data processing, "
            "distributed task execution, etc. Returns worker_id and task_id for tracking."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "orchestrator_agent_id": {
                            "type": "string",
                            "description": "ID of the orchestrator agent spawning this worker. Optional — defaults to current agent.",
                        },
                        "worker_id": {
                            "type": "string",
                            "description": "Custom ID for the worker agent. Auto-generated if not provided.",
                        },
                        "worker_name": {
                            "type": "string",
                            "description": "Display name for the worker agent.",
                        },
                        "skill": {
                            "type": "object",
                            "description": "Complete skill definition with nodes, edges, and config. Provide this OR skill_name/skill_id.",
                        },
                        "skill_name": {
                            "type": "string",
                            "description": "Name of an existing skill to load for the worker.",
                        },
                        "skill_id": {
                            "type": "string",
                            "description": "ID of an existing skill to load for the worker.",
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "Timeout in seconds for the worker task (default: 60).",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Additional metadata to attach to the worker (e.g., customer_id, job_id).",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_stop_worker_agents_tool_schema(tool_schemas: list):
    """Register the stop_worker_agents MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="stop_worker_agents",
        description=(
            "<category>Managerial</category><sub-category>Agent Management</sub-category>"
            "Stop one or more worker agents. Can stop by worker_id, list of worker_ids, "
            "all workers for an orchestrator, or all workers globally. Stops tasks and "
            "unregisters agents to free resources."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "worker_id": {
                            "type": "string",
                            "description": "Single worker ID to stop.",
                        },
                        "worker_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of worker IDs to stop.",
                        },
                        "orchestrator_agent_id": {
                            "type": "string",
                            "description": "Stop all workers spawned by this orchestrator.",
                        },
                        "stop_all": {
                            "type": "boolean",
                            "description": "Stop ALL workers globally (use with caution).",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_get_worker_agent_status_tool_schema(tool_schemas: list):
    """Register the get_worker_agent_status MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="get_worker_agent_status",
        description=(
            "<category>Managerial</category><sub-category>Agent Management</sub-category>"
            "Get status of worker agents. Returns detailed status including task state, "
            "elapsed time, and metadata. Can query by worker_id, list of worker_ids, "
            "or all workers for an orchestrator."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "worker_id": {
                            "type": "string",
                            "description": "Single worker ID to check status.",
                        },
                        "worker_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of worker IDs to check status.",
                        },
                        "orchestrator_agent_id": {
                            "type": "string",
                            "description": "Check status of all workers for this orchestrator.",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


def add_list_worker_agents_tool_schema(tool_schemas: list):
    """Register the list_worker_agents MCP tool schema."""
    tool_schema = types.Tool(
        _meta={"run_in_cloud": False},
        name="list_worker_agents",
        description=(
            "<category>Managerial</category><sub-category>Agent Management</sub-category>"
            "List all active worker agents. Can filter by orchestrator and optionally "
            "include completed workers. Returns summary with active count and total count."
        ),
        inputSchema={
            "type": "object",
            "required": ["input"],
            "properties": {
                "input": {
                    "type": "object",
                    "required": [],
                    "properties": {
                        "orchestrator_agent_id": {
                            "type": "string",
                            "description": "Filter workers by orchestrator agent ID.",
                        },
                        "include_completed": {
                            "type": "boolean",
                            "description": "Include completed workers in the list (default: false).",
                        },
                    },
                }
            },
        },
    )
    tool_schemas.append(tool_schema)


# ==================== Async Wrappers for MCP Server ====================

async def async_spawn_worker_agent(mainwin, args: Dict[str, Any]) -> list[TextContent]:
    """Async wrapper for spawn_worker_agent tool."""
    try:
        input_config = args.get("input", {})
        result = spawn_worker_agent(mainwin, input_config)
        
        if result.get("success"):
            msg = result.get("message", "Worker agent spawned successfully")
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            error = result.get("error", "Unknown error")
            return [TextContent(type="text", text=json.dumps({"error": error}, indent=2))]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncSpawnWorkerAgent")
        logger.error(err_trace)
        return [TextContent(type="text", text=json.dumps({"error": err_trace}, indent=2))]


async def async_stop_worker_agents(mainwin, args: Dict[str, Any]) -> list[TextContent]:
    """Async wrapper for stop_worker_agents tool."""
    try:
        input_config = args.get("input", {})
        result = stop_worker_agents(mainwin, input_config)
        
        if result.get("success"):
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            error = result.get("error", "Unknown error")
            return [TextContent(type="text", text=json.dumps({"error": error}, indent=2))]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncStopWorkerAgents")
        logger.error(err_trace)
        return [TextContent(type="text", text=json.dumps({"error": err_trace}, indent=2))]


async def async_get_worker_agent_status(mainwin, args: Dict[str, Any]) -> list[TextContent]:
    """Async wrapper for get_worker_agent_status tool."""
    try:
        input_config = args.get("input", {})
        result = get_worker_agent_status(mainwin, input_config)
        
        if result.get("success"):
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            error = result.get("error", "Unknown error")
            return [TextContent(type="text", text=json.dumps({"error": error}, indent=2))]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncGetWorkerAgentStatus")
        logger.error(err_trace)
        return [TextContent(type="text", text=json.dumps({"error": err_trace}, indent=2))]


async def async_list_worker_agents(mainwin, args: Dict[str, Any]) -> list[TextContent]:
    """Async wrapper for list_worker_agents tool."""
    try:
        input_config = args.get("input", {})
        result = list_worker_agents(mainwin, input_config)
        
        if result.get("success"):
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        else:
            error = result.get("error", "Unknown error")
            return [TextContent(type="text", text=json.dumps({"error": error}, indent=2))]
    except Exception as e:
        err_trace = get_traceback(e, "ErrorAsyncListWorkerAgents")
        logger.error(err_trace)
        return [TextContent(type="text", text=json.dumps({"error": err_trace}, indent=2))]
