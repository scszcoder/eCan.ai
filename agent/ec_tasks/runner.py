"""
Task Runner - Core task management and execution loop.

This module provides the main TaskRunner class that manages:
- Task registration and lifecycle
- Execution loops for different trigger types
- Event routing
- Task persistence
"""

import asyncio
import concurrent.futures
import json
import os
import shutil
import tempfile
import threading
import time
import traceback
import uuid
from pathlib import Path
from queue import Queue, Empty
from typing import Any, Dict, Generic, List, Optional, Tuple, TypeVar, TYPE_CHECKING

from a2a.types import TaskState, Message, TextPart, MessageSendParams, TaskStatus as A2ATaskStatus
from agent.ec_skills.llm_utils.llm_utils import send_response_back
from agent.ec_skills.prep_skills_run import prep_skills_run
from langgraph.types import Command

from .resume import build_general_resume_payload, normalize_event, _safe_get
from pydantic import TypeAdapter

from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

from .models import ManagedTask, PriorityType
from .scheduler import find_tasks_ready_to_run
from .message_sender import ChatMessageSender, MessageType
from .dev_runner import DevRunner
from .executor import TaskExecutor, _create_message
from .timer_service import get_timer_service, TimerService

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent
    from agent.ec_skill import EC_Skill
    from a2a.types import Task

Context = TypeVar('Context')

# Timeouts and polling intervals
DEV_EVENT_TIMEOUT_SEC = int(os.getenv("DEV_EVENT_TIMEOUT_SEC", "300"))
DEV_EVENT_POLL_INTERVAL_SEC = float(os.getenv("DEV_EVENT_POLL_INTERVAL_SEC", "0.5"))
RUN_EVENT_TIMEOUT_SEC = int(os.getenv("RUN_EVENT_TIMEOUT_SEC", "600"))


class TaskRunnerRegistry:
    """Global registry for TaskRunner instances to allow coordinated shutdown."""
    _runners: List["TaskRunner"] = []
    
    @classmethod
    def register(cls, runner: "TaskRunner"):
        try:
            if runner not in cls._runners:
                cls._runners.append(runner)
        except Exception:
            pass
    
    @classmethod
    def unregister(cls, runner: "TaskRunner"):
        try:
            if runner in cls._runners:
                cls._runners.remove(runner)
        except Exception:
            pass
    
    @classmethod
    def stop_all(cls):
        for r in list(cls._runners):
            try:
                r.stop()
            except Exception:
                pass


class TaskRunner(Generic[Context]):
    """
    Main task runner that manages task execution.
    
    Responsibilities:
    - Task registration and lifecycle management
    - Execution loop for different trigger types
    - Event routing to appropriate tasks
    - Task persistence (save/load)
    """
    
    def __init__(self, agent: "EC_Agent"):
        """
        Initialize the task runner.
        
        Args:
            agent: The agent that owns this runner.
        """
        self.agent = agent
        self.tasks: Dict[str, ManagedTask] = {}
        
        # Skill execution thread pool
        self._skill_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=20,
            thread_name_prefix="SkillExec"
        )
        
        # Per-task state for concurrent execution
        self._task_states: Dict[str, dict] = {}
        
        # Dev runner for debugging
        self.dev_runner = DevRunner()
        
        # Running tasks list
        self.running_tasks: List[asyncio.Task] = []
        
        # Persistence directory
        self.save_dir = os.path.join(agent.mainwin.my_ecb_data_homepath, "task_saves")
        os.makedirs(self.save_dir, exist_ok=True)
        
        # Global event routing config (agent-level, not per-skill)
        self._global_event_routing: Dict[str, dict] = self._load_global_event_routing()
        
        # Stop event for shutdown
        self._stop_event = threading.Event()
        
        # Message sender
        self._message_sender: Optional[ChatMessageSender] = None
        
        # Register with global registry
        TaskRunnerRegistry.register(self)
    
    # ==================== Properties ====================
    
    @property
    def bp_manager(self):
        """Backward compatibility: access breakpoint manager via dev_runner."""
        return self.dev_runner.bp_manager
    
    @property
    def _dev_task(self):
        """Backward compatibility: access dev task via dev_runner."""
        return self.dev_runner.current_task
    
    @_dev_task.setter
    def _dev_task(self, value):
        """Backward compatibility: set dev task via dev_runner."""
        if value is None:
            self.dev_runner.clear_dev_task()
        else:
            self.dev_runner.set_dev_task(value)
    
    # ==================== Message Sender ====================
    
    def _get_message_sender(self) -> ChatMessageSender:
        """Get or create message sender."""
        if self._message_sender is None:
            self._message_sender = ChatMessageSender(self.agent)
        return self._message_sender
    
    def sendChatMessageToGUI(self, sender_agent, chatId, msg):
        """Send a text message to GUI. Backward compatible."""
        logger.debug(f"sendChatMessageToGUI: {msg}")
        sender = ChatMessageSender(sender_agent)
        sender.send_text(chatId, msg)
    
    def sendChatFormToGUI(self, sender_agent, chatId, chatData):
        """Send a form message to GUI. Backward compatible."""
        logger.debug(f"sendChatFormToGUI: {chatData}")
        sender = ChatMessageSender(sender_agent)
        sender.send_form(chatId, chatData)
    
    def sendChatNotificationToGUI(self, sender_agent, chatId, chatData):
        """Send a notification to GUI. Backward compatible."""
        logger.debug(f"sendChatNotificationToGUI: {chatData}")
        sender = ChatMessageSender(sender_agent)
        sender.send_notification(chatId, chatData)
    
    # ==================== Dev Run Controls (Delegated) ====================
    
    def set_bps_dev_skill(self, bps: Optional[List[str]]) -> dict:
        """Set breakpoints for dev skill run."""
        return self.dev_runner.set_breakpoints(bps)
    
    def clear_bps_dev_skill(self, bps: Optional[List[str]] = None) -> dict:
        """Clear breakpoints."""
        return self.dev_runner.clear_breakpoints(bps)
    
    def launch_dev_run(self, init_state: dict, dev_task: ManagedTask) -> dict:
        """Launch a dev run via the unified execution loop."""
        try:
            # Truncate screenshot data for logging
            try:
                from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
                log_init_state = truncate_screenshot_for_logging(init_state)
            except Exception:
                log_init_state = str(init_state)[:500] + "..."
            logger.debug(f"[TaskRunner][launch_dev_run] init_state: {log_init_state}")
            dev_init_state = init_state or {}
            try:
                if isinstance(dev_init_state.get("messages"), list) and not dev_init_state["messages"]:
                    dev_init_state = dict(dev_init_state)
                    dev_init_state.pop("messages", None)
            except Exception:
                pass

            final_state = self._prepare_dev_state(dev_task, msg=None, dev_init_state=dev_init_state)
        except Exception as e:
            logger.error(get_traceback(e, "ErrorPrepareDevStateForDevRun"))
            final_state = init_state or {}

        launch_result = self.dev_runner.launch_dev_run(final_state, dev_task)
        if not launch_result.get("success"):
            return launch_result

        # Reset per-task state tracking for dev runs before entering loop
        self._task_states[dev_task.id] = {
            "justStarted": True,
            "dev_auto_started": False,
            "pending_since": None,
        }

        # Kick off the unified runner in dev mode with prepared state
        self.launch_unified_run(
            task2run=dev_task,
            trigger_type="dev",
            dev_init_state=final_state,
            dev_single_run=True,
        )

        return {"success": True}
    
    def resume_dev_run(self) -> dict:
        """Resume a paused dev run."""
        return self.dev_runner.resume_dev_run()
    
    def pause_dev_run(self) -> dict:
        """Pause the current dev run."""
        return self.dev_runner.pause_dev_run()
    
    def step_dev_run(self) -> dict:
        """Single-step the dev run."""
        return self.dev_runner.step_dev_run()
    
    def cancel_dev_run(self) -> dict:
        """Cancel the current dev run."""
        return self.dev_runner.cancel_dev_run()
    
    def _get_serializable_state(self, task, config) -> dict:
        """Get serializable state from task."""
        return self.dev_runner.get_serializable_state(config)
    
    # ==================== Lifecycle Management ====================
    
    def stop(self):
        """Signal all loops to exit and notify running tasks to shut down."""
        try:
            self._stop_event.set()
            
            # Get agent name safely
            agent_name = self._get_agent_name()
            logger.info(f"[TaskRunner] Stop event set for agent {agent_name}")
            
            # Stop all ManagedTask instances
            self._stop_managed_tasks()
            
            # Notify agent tasks' queues
            self._notify_task_queues_shutdown()
            
        except Exception as e:
            logger.debug(f"[TaskRunner] Error in stop method: {e}")
    
    def _get_agent_name(self) -> str:
        """Safely get agent name."""
        agent_card = getattr(self.agent, 'card', None)
        if agent_card:
            if hasattr(agent_card, 'name'):
                return agent_card.name
            elif isinstance(agent_card, dict):
                return agent_card.get('name', 'unknown')
        return 'unknown'
    
    def _stop_managed_tasks(self):
        """Stop all managed tasks."""
        from .pending_events import cancel_task_async_operations
        
        try:
            for task_id, managed_task in self.tasks.items():
                try:
                    if managed_task:
                        # Cancel pending async operations first
                        cancel_task_async_operations(managed_task)
                        managed_task.cancel()
                        managed_task.exit()
                        logger.debug(f"[TaskRunner] Stopped managed task: {task_id}")
                except Exception as e:
                    logger.debug(f"[TaskRunner] Error stopping managed task {task_id}: {e}")
        except Exception as e:
            logger.debug(f"[TaskRunner] Error stopping managed tasks: {e}")
    
    def _notify_task_queues_shutdown(self):
        """Notify running task queues to shut down."""
        try:
            for t in getattr(self.agent, "tasks", []) or []:
                try:
                    if not t:
                        continue
                    st = getattr(getattr(t, "status", None), "state", None)
                    if st in (TaskState.submitted, TaskState.working):
                        q = getattr(t, "queue", None)
                        if q is not None:
                            try:
                                q.put_nowait({"__shutdown__": True})
                            except Exception:
                                try:
                                    q.put({"__shutdown__": True})
                                except Exception:
                                    pass
                except Exception:
                    pass
        except Exception:
            pass
    
    def close(self):
        """Close the runner and unregister."""
        self.stop()
        TaskRunnerRegistry.unregister(self)
    
    def assign_agent(self, agent: "EC_Agent"):
        """Assign a new agent to this runner."""
        self.agent = agent
    
    # ==================== Task Management ====================
    
    async def create_task(
        self,
        skill: "EC_Skill",
        state: dict,
        session_id: Optional[str] = None,
        resume_from: Optional[str] = None,
        trigger: Optional[str] = None
    ) -> str:
        """
        Create a new managed task.
        
        Args:
            skill: The skill to execute.
            state: Initial state for the task.
            session_id: Optional session ID.
            resume_from: Optional resume point.
            trigger: Optional trigger type.
            
        Returns:
            The task ID.
        """
        task_id = str(uuid.uuid4())
        
        # Validate skill
        if skill is None:
            logger.error("[SKILL_MISSING] Attempting to create task with skill=None!")
            raise ValueError("Cannot create task with None skill")
        
        logger.info(f"[TASK_CREATE] Creating task {task_id} with skill: {skill.name if hasattr(skill, 'name') else 'UNKNOWN'}")
        
        if not hasattr(skill, 'runnable') or skill.runnable is None:
            logger.warning(f"[SKILL_WARNING] Skill has runnable=None at task creation")
        
        task = ManagedTask(
            id=task_id,
            sessionId=session_id,
            skill=skill,
            metadata={"state": state},
            state=state,
            resume_from=resume_from,
            trigger=trigger,
            name=skill.name if hasattr(skill, 'name') else 'unnamed_task',
            description=""
        )
        
        self.tasks[task_id] = task
        return task_id
    
    async def run_task(self, task_id: str):
        """Run a task by ID."""
        tbr_task = next((task for task in self.agent.tasks if task and task.id == task_id), None)
        if tbr_task:
            if tbr_task.status.state not in (TaskState.working, TaskState.input_required):
                logger.info(f"Starting task: {tbr_task.status.state}")
                executor = TaskExecutor(tbr_task)
                await executor.astream_run()
            else:
                logger.warning("Task already running or waiting for input")
    
    async def run_all_tasks(self):
        """Run all tasks with proper cleanup."""
        import inspect
        
        self.running_tasks = []
        
        for t in self.agent.tasks:
            if t and callable(t.task):
                try:
                    coro = t.task()
                    if inspect.isawaitable(coro):
                        self.running_tasks.append(coro)
                except TypeError as e:
                    logger.error(f"Task requires arguments: {e}")
            elif inspect.isawaitable(t.task):
                self.running_tasks.append(t.task)
        
        if not self.running_tasks:
            logger.warning("No running tasks")
            return
        
        logger.info(f"Running {len(self.running_tasks)} tasks")
        
        try:
            results = await asyncio.gather(*self.running_tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Task {i} failed: {result}")
        except Exception as e:
            logger.error(f"run_all_tasks failed: {e}")
        finally:
            self.running_tasks.clear()
    
    async def pause_task(self, task_id: str):
        """Pause a task."""
        task = self.tasks[task_id]
        task.pause()
        task.status.state = TaskState.input_required
    
    async def resume_task(self, task_id: str):
        """Resume a paused task."""
        task = self.tasks[task_id]
        task.resume()
        task.status.state = TaskState.working
    
    async def cancel_task(self, task_id: str, timeout: float = 5.0):
        """Cancel a task and clean up resources."""
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # Check terminal state
        terminal_states = (TaskState.completed, TaskState.failed, TaskState.canceled)
        if task.status.state in terminal_states:
            return
        
        try:
            # Cancel asyncio task
            if task.task:
                task.task.cancel()
                try:
                    await asyncio.wait_for(task.task, timeout=timeout)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Cancel pending async operations and their timers
            from .pending_events import cancel_task_async_operations
            cancel_task_async_operations(task)
            
            # Update status
            task.status.state = TaskState.canceled
            task.status.message = "Task cancelled by user"
            
            # Cleanup
            if hasattr(task, 'cleanup') and callable(task.cleanup):
                task.cleanup()
            if hasattr(task, 'exit') and callable(task.exit):
                task.exit()
            
            # Clear queue
            if hasattr(task, 'queue') and task.queue:
                while not task.queue.empty():
                    try:
                        task.queue.get_nowait()
                    except Empty:
                        break
            
            logger.info(f"Task {task_id} cancelled successfully")
            
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            raise
    
    async def schedule_task(self, task_id: str, delay: int) -> asyncio.Task:
        """Schedule a task to run after a delay."""
        async def _delayed_run():
            try:
                await asyncio.sleep(delay)
                if task_id in self.tasks:
                    task = self.tasks[task_id]
                    if task.status.state != TaskState.canceled:
                        await self.run_task(task_id)
            except asyncio.CancelledError:
                logger.info(f"Scheduled task {task_id} cancelled")
                raise
        
        return asyncio.create_task(_delayed_run())
    
    # ==================== Task Persistence ====================
    
    def save_task(self, task_id: str):
        """Save task to disk with atomic write."""
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        save_dir = Path(self.save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        target_file = save_dir / f"{task_id}.json"
        temp_file = None
        
        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=save_dir,
                prefix=f"{task_id}_",
                suffix=".json.tmp",
                delete=False,
                encoding='utf-8'
            ) as f:
                temp_file = f.name
                json_data = task.model_dump_json(indent=2)
                f.write(json_data)
                f.flush()
                os.fsync(f.fileno())
            
            shutil.move(temp_file, target_file)
            logger.debug(f"Task {task_id} saved to {target_file}")
            
        except Exception as e:
            if temp_file and os.path.exists(temp_file):
                os.remove(temp_file)
            raise IOError(f"Failed to save task {task_id}: {e}")
    
    def load_task(self, task_id: str, skill: "EC_Skill") -> ManagedTask:
        """Load task from disk."""
        file_path = Path(self.save_dir) / f"{task_id}.json"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Task file not found: {task_id}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            raw = f.read()
        
        if not raw.strip():
            raise ValueError(f"Task file is empty: {task_id}")
        
        from a2a.types import Task
        base_task = TypeAdapter(Task).validate_json(raw)
        task = ManagedTask(**base_task.model_dump(), skill=skill)
        
        self.tasks[task_id] = task
        return task
    
    # ==================== Event Routing ====================
    
    def _load_global_event_routing(self) -> Dict[str, dict]:
        """Load global event routing config from agent_files/event_routing.json.
        
        Falls back to the bundled default file if no user-level override exists.
        Returns the 'event_routing' dict from the JSON file.
        """
        # 1. User-level override: <data_home>/event_routing.json
        user_path = os.path.join(self.agent.mainwin.my_ecb_data_homepath, "event_routing.json")
        # 2. Bundled default: agent/agent_files/event_routing.json
        default_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "agent_files", "event_routing.json")
        
        for path in (user_path, default_path):
            try:
                if os.path.isfile(path):
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    routing = data.get("event_routing", {})
                    if isinstance(routing, dict) and routing:
                        logger.info(f"[EventRouting] Loaded global event routing from {path} ({len(routing)} rules)")
                        return routing
            except Exception as e:
                logger.warning(f"[EventRouting] Failed to load {path}: {e}")
        
        logger.warning("[EventRouting] No global event_routing.json found, using empty routing")
        return {}
    
    def _save_global_event_routing(self, routing: Dict[str, dict]) -> bool:
        """Save global event routing config to user data directory."""
        user_path = os.path.join(self.agent.mainwin.my_ecb_data_homepath, "event_routing.json")
        try:
            data = {"event_routing": routing}
            os.makedirs(os.path.dirname(user_path), exist_ok=True)
            with open(user_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self._global_event_routing = routing
            logger.info(f"[EventRouting] Saved global event routing to {user_path}")
            return True
        except Exception as e:
            logger.error(f"[EventRouting] Failed to save event routing: {e}")
            return False
    
    def reload_event_routing(self) -> None:
        """Reload global event routing config from disk."""
        self._global_event_routing = self._load_global_event_routing()
    
    def _extract_event_types_from_skill(self, skill) -> List[Dict[str, Any]]:
        """Extract all event types and their match_fields from a skill's pend_event nodes.
        
        Inspects the skill's diagram (flowgram) for pend_event_node type nodes
        and collects their eventType, pendingSources, and matchFields configuration.
        
        Returns:
            List of dicts, each with:
              - event_type (str): The event type string
              - match_fields (list): Array of {event_path, task_path} from the node config
        """
        results: List[Dict[str, Any]] = []
        try:
            diagram = getattr(skill, "diagram", None)
            if not isinstance(diagram, dict):
                return results
            
            # Get nodes from workFlow or top-level
            wf = diagram.get("workFlow") or diagram
            nodes = wf.get("nodes") or diagram.get("nodes") or []
            
            def _collect_all_nodes(node_list: list) -> list:
                """Recursively collect all nodes, including those nested in blocks (loop, conditional)."""
                all_nodes = []
                for node in node_list:
                    if not isinstance(node, dict):
                        continue
                    all_nodes.append(node)
                    # Recurse into blocks (loop nodes, conditional nodes, etc.)
                    blocks = node.get("blocks") or []
                    if isinstance(blocks, list):
                        all_nodes.extend(_collect_all_nodes(blocks))
                return all_nodes
            
            all_nodes = _collect_all_nodes(nodes)
            
            for node in all_nodes:
                if not isinstance(node, dict):
                    continue
                ntype = node.get("type") or ""
                if ntype != "pend_event_node":
                    continue
                
                node_data = node.get("data") or node
                inputs = node_data.get("inputsValues") or {}
                
                # Extract match_fields from the node (shared across all event types in this node)
                mf_raw = (inputs.get("matchFields") or {}).get("content") or []
                match_fields = []
                if isinstance(mf_raw, list):
                    for mf in mf_raw:
                        if isinstance(mf, dict):
                            ep = (mf.get("event_path") or "").strip()
                            tp = (mf.get("task_path") or "").strip()
                            if ep:  # event_path is required; task_path can be blank
                                match_fields.append({"event_path": ep, "task_path": tp})
                
                # Main event type
                main_et = (inputs.get("eventType") or {}).get("content")
                if isinstance(main_et, str) and main_et.strip():
                    results.append({"event_type": main_et.strip(), "match_fields": match_fields})
                
                # Additional pending sources
                pending_raw = (inputs.get("pendingSources") or {}).get("content") or []
                if isinstance(pending_raw, list):
                    for src in pending_raw:
                        if isinstance(src, str) and src.strip():
                            results.append({"event_type": src.strip(), "match_fields": match_fields})
                        elif isinstance(src, dict):
                            st = (src.get("type") or "").strip()
                            if st:
                                results.append({"event_type": st, "match_fields": match_fields})
        except Exception as e:
            logger.debug(f"[EventRouting] Error extracting event types from skill: {e}")
        
        # Deduplicate by event_type while preserving order (keep first occurrence)
        seen = set()
        unique = []
        for entry in results:
            et = entry["event_type"]
            if et not in seen:
                seen.add(et)
                unique.append(entry)
        return unique
    
    def _amend_event_routing_for_task(self, task: ManagedTask) -> None:
        """Amend global event routing with entries for a task's pending event nodes.
        
        Called at task launch time. Inspects the task's skill for pend_event nodes,
        extracts the event types and match_fields they expect, and adds routing
        entries to the global config.
        
        If the node has match_fields configured, uses match_fields-based routing.
        Otherwise falls back to routing_key: command.run_id for dynamic matching.
        
        Skips event types that already have a routing rule in the global config.
        """
        skill = getattr(task, "skill", None)
        if not skill:
            return
        
        try:
            event_entries = self._extract_event_types_from_skill(skill)
            if not event_entries:
                return
            
            amended = False
            for entry in event_entries:
                et = entry["event_type"]
                node_match_fields = entry.get("match_fields") or []
                
                if et in self._global_event_routing:
                    logger.debug(f"[EventRouting] Event type '{et}' already has a routing rule, skipping")
                    continue
                
                rule: Dict[str, Any] = {
                    "task_selector": f"id:{task.id}",
                    "queue": "",
                    "_auto_added_by_task": task.id,
                    "_auto_added_by_skill": getattr(skill, "name", ""),
                }
                
                if node_match_fields:
                    # Use match_fields from the node config for declarative matching
                    rule["match_fields"] = node_match_fields
                    rule["match_mode"] = "all"
                    logger.info(
                        f"[EventRouting] Added match_fields routing rule: event '{et}' -> "
                        f"task '{task.name}' ({len(node_match_fields)} fields)"
                    )
                else:
                    # Fallback: match by run_id
                    rule["routing_key"] = "command.run_id"
                    logger.info(
                        f"[EventRouting] Added routing_key rule: event '{et}' -> task '{task.name}' (id={task.id})"
                    )
                
                self._global_event_routing[et] = rule
                amended = True
            
            if amended:
                logger.info(
                    f"[EventRouting] Amended global routing with {len(event_entries)} event types "
                    f"from skill '{getattr(skill, 'name', '')}' for task '{task.name}'"
                )
        except Exception as e:
            logger.warning(f"[EventRouting] Failed to amend routing for task '{task.name}': {e}")
    
    def _extract_nested_value(self, data: Any, key_path: str) -> Any:
        """
        Extract a value from nested dict/object using dot notation.
        E.g., "command.run_id" extracts data["command"]["run_id"] or data.command.run_id
        """
        try:
            parts = key_path.split(".")
            current = data
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                elif hasattr(current, "model_dump"):
                    current = current.model_dump().get(part)
                else:
                    return None
                if current is None:
                    return None
            return current
        except Exception:
            return None

    def _extract_task_value(self, task: ManagedTask, key_path: str) -> Any:
        """Extract a value from a ManagedTask using dot notation.
        
        Supports paths like:
          - "id", "name", "run_id"           → direct task fields
          - "state.account_id"               → task.state dict
          - "state.cloud_run_id"             → task.state dict
          - "skill.id", "skill.name"         → task.skill fields
        """
        try:
            parts = key_path.split(".")
            first = parts[0]
            
            # Resolve the root object
            if first == "state":
                current = task.state or {}
                parts = parts[1:]
            elif first == "skill":
                current = getattr(task, "skill", None)
                if current is None:
                    return None
                parts = parts[1:]
            else:
                current = task
            
            # Walk the remaining path
            for part in parts:
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                elif hasattr(current, "model_dump"):
                    current = current.model_dump().get(part)
                else:
                    return None
                if current is None:
                    return None
            return current
        except Exception:
            return None
    
    @staticmethod
    def _apply_match_transform(value: Any, transform: str) -> Any:
        """Apply a transform to a value before comparison.
        
        Supported transforms:
          - "lowercase" / "lower"   → str.lower()
          - "uppercase" / "upper"   → str.upper()
          - "strip"                 → str.strip()
          - "to_string" / "str"     → str()
          - "to_int" / "int"        → int()
          - "prefix:X"              → remove prefix X from string
          - "suffix:X"              → remove suffix X from string
        """
        if value is None or not transform:
            return value
        try:
            t = transform.strip().lower()
            sv = str(value) if not isinstance(value, str) else value
            
            if t in ("lowercase", "lower"):
                return sv.lower()
            elif t in ("uppercase", "upper"):
                return sv.upper()
            elif t == "strip":
                return sv.strip()
            elif t in ("to_string", "str"):
                return str(value)
            elif t in ("to_int", "int"):
                return int(value)
            elif t.startswith("prefix:"):
                prefix = transform.split(":", 1)[1]
                return sv[len(prefix):] if sv.startswith(prefix) else sv
            elif t.startswith("suffix:"):
                suffix = transform.split(":", 1)[1]
                return sv[:-len(suffix)] if sv.endswith(suffix) else sv
            else:
                return value
        except Exception:
            return value
    
    def _evaluate_match_fields(self, match_fields: list, match_mode: str,
                               request: Any, task: ManagedTask) -> bool:
        """Evaluate match_fields rules against a request and task.
        
        Args:
            match_fields: List of {event_path, task_path, transform?} dicts.
            match_mode: "all" (every pair must match) or "any" (at least one).
            request: The incoming event/request object.
            task: The candidate ManagedTask.
            
        Returns:
            True if the task matches according to match_mode.
        """
        if not match_fields:
            return False
        
        results = []
        for mf in match_fields:
            if not isinstance(mf, dict):
                continue
            event_path = mf.get("event_path") or ""
            task_path = mf.get("task_path") or ""
            transform = mf.get("transform") or ""
            
            if not event_path or not task_path:
                continue
            
            event_val = self._extract_nested_value(request, event_path)
            task_val = self._extract_task_value(task, task_path)
            
            # Apply transform to both sides
            if transform:
                event_val = self._apply_match_transform(event_val, transform)
                task_val = self._apply_match_transform(task_val, transform)
            
            matched = (event_val is not None and task_val is not None
                       and str(event_val) == str(task_val))
            results.append(matched)
            logger.debug(
                f"[ROUTING] match_field: event.{event_path}={event_val} vs task.{task_path}={task_val} "
                f"→ {'✅' if matched else '❌'}"
            )
        
        if not results:
            return False
        
        if match_mode == "any":
            return any(results)
        return all(results)  # default: "all"
    
    def _resolve_event_routing(self, event_type: str, request: Any, source: str = "") -> Optional[Tuple[ManagedTask, dict]]:
        """
        Route an event to a task using the global agent-level event routing config.
        
        The global config (event_routing.json) maps event types to routing rules.
        Each rule supports three matching strategies (evaluated in order):
        
          1. match_fields: Array of {event_path, task_path, transform?} pairs.
             Extracts values from the event and task, optionally transforms them,
             and compares. match_mode ("all"|"any") controls AND/OR logic.
          2. routing_key: Legacy shorthand — extracts a value from the request
             and compares against well-known task fields (id, cloud_run_id, skill.id).
          3. task_selector: Static match by task name or id (e.g. "name_contains:chatter").
        
        Args:
            event_type: Type of event (e.g. "human_chat", "web_hook").
            request: The request object.
            source: Optional source identifier.
            
        Returns:
            Tuple of (matching ManagedTask, routing rule dict) or None.
        """
        try:
            event = normalize_event(event_type, request, src=source)
            etype = event.get("type") or event_type
        except Exception:
            event = None
            etype = event_type
        
        logger.debug(f"[ROUTING] normalized event: {etype}")
        
        try:
            # Look up rule in global routing table
            rule = self._global_event_routing.get(etype)
            if not isinstance(rule, dict):
                logger.debug(f"[ROUTING] No global routing rule for event type '{etype}'")
                return None
            
            tasks_list = getattr(self.agent, "tasks", []) or []
            logger.info(f"[ROUTING] Routing event '{etype}' — {len(tasks_list)} tasks available")
            
            # 1. match_fields: declarative multi-field matching
            # Uses normalized event envelope so event_path is consistent
            # (e.g. "data.metadata.params.chatId", "context.senderId")
            match_fields = rule.get("match_fields")
            if isinstance(match_fields, list) and match_fields:
                match_mode = rule.get("match_mode", "all")
                # Prefer normalized event; fall back to raw request
                event_data = event if isinstance(event, dict) else request
                for t in tasks_list:
                    if not t:
                        continue
                    if self._evaluate_match_fields(match_fields, match_mode, event_data, t):
                        logger.info(f"[ROUTING] ✅ Matched task via match_fields: {t.name}, id={t.id}")
                        return (t, rule)
                logger.debug(f"[ROUTING] ❌ No task matched via match_fields for event '{etype}'")
            
            # 2. routing_key: legacy shorthand for dynamic matching
            # Try normalized event first, then raw request for backward compat
            routing_key = rule.get("routing_key")
            if routing_key:
                key_value = None
                if isinstance(event, dict):
                    key_value = self._extract_nested_value(event, routing_key)
                if key_value is None:
                    key_value = self._extract_nested_value(request, routing_key)
                if key_value:
                    logger.debug(f"[ROUTING] routing_key '{routing_key}' = '{key_value}'")
                    for t in tasks_list:
                        if not t:
                            continue
                        # Match by run_id (task.id or cloud_run_id)
                        if "run_id" in routing_key:
                            if str(t.id) == str(key_value):
                                logger.info(f"[ROUTING] ✅ Matched task by run_id: {t.name}, id={t.id}")
                                return (t, rule)
                            cloud_run_id = (t.state or {}).get("cloud_run_id")
                            if cloud_run_id and str(cloud_run_id) == str(key_value):
                                logger.info(f"[ROUTING] ✅ Matched task by cloud_run_id: {t.name}")
                                return (t, rule)
                        # Match by skill_id
                        if "skill_id" in routing_key:
                            skill = getattr(t, "skill", None)
                            if skill and str(getattr(skill, "id", "")) == str(key_value):
                                logger.info(f"[ROUTING] ✅ Matched task by skill_id: {t.name}")
                                return (t, rule)
            
            # 3. Static matching via task_selector (fallback)
            selector = rule.get("task_selector") or ""
            if selector:
                for t in tasks_list:
                    if not t:
                        continue
                    if self._evaluate_selector(selector, t):
                        logger.info(f"[ROUTING] ✅ Matched task via selector '{selector}': {t.name}, id={t.id}")
                        return (t, rule)
                logger.debug(f"[ROUTING] ❌ No task matched selector '{selector}' for event '{etype}'")
            else:
                if not match_fields and not routing_key:
                    logger.debug(f"[ROUTING] No matching strategy in rule for event '{etype}'")
                    
        except Exception as e:
            logger.error(get_traceback(e, "ErrorResolveEventRouting"))
        
        return None
    
    def _evaluate_selector(self, selector: str, task: ManagedTask) -> bool:
        """Evaluate a task selector against a task."""
        try:
            if selector.startswith("id:"):
                task_id = selector.split(":", 1)[1].strip()
                return (task.id or "").strip() == task_id
            elif selector.startswith("name:"):
                name = selector.split(":", 1)[1].strip().lower()
                task_name = (task.name or "").strip().lower()
                skill_name = (getattr(task.skill, "name", "") or "").strip().lower()
                return task_name == name or skill_name == name
            elif selector.startswith("name_contains:"):
                needle = selector.split(":", 1)[1].strip().lower()
                return needle in (task.name or "").lower()
            else:
                return True  # No selector = match
        except Exception:
            return False
    
    # ==================== Task Finding ====================
    
    def find_chatter_tasks(self) -> Optional[ManagedTask]:
        """Find a chat task (task name contains 'chat')."""
        found = [task for task in self.agent.tasks if 'chat' in task.name.lower()]
        if found:
            logger.debug(f"[find_chatter_tasks] Found: {found[0].id}")
            return found[0]
        logger.error("NO chatter tasks found!")
        return None

    def _ensure_chatter_task(self) -> Optional[ManagedTask]:
        """Ensure the agent has a chatter task for routing human_chat/a2a events."""
        existing = self.find_chatter_tasks()
        if existing:
            return existing

        skills = getattr(self.agent, "skills", []) or []
        chat_candidates = [sk for sk in skills if sk and "chat" in (getattr(sk, "name", "")).lower()]
        if not chat_candidates:
            logger.error("[ensure_chatter_task] No chat skill found; cannot auto-create chatter task")
            return None
        # Prefer a skill that has a compiled runnable
        chatter_skill = next((sk for sk in chat_candidates if getattr(sk, "runnable", None) is not None), None)
        if not chatter_skill:
            logger.error(f"[ensure_chatter_task] Found {len(chat_candidates)} chat skill(s) but none have a compiled runnable: "
                         f"{[getattr(sk, 'name', '?') for sk in chat_candidates]}")
            return None

        task_id = f"auto-chatter-{uuid.uuid4()}"
        task = ManagedTask(
            id=task_id,
            context_id=task_id,
            name=f"chat:Auto Chatter Task ({getattr(chatter_skill, 'name', 'chatter')})",
            description="Auto-created chatter task for routing",
            source="code",
            status=A2ATaskStatus(state=TaskState.submitted),
            sessionId="",
            skill=chatter_skill,
            metadata={"state": {"top": "ready"}},
            state={"top": "ready"},
            resume_from="",
            trigger="message",
            agent_id=getattr(getattr(self.agent, "card", None), "id", "") or "",
        )

        if getattr(self.agent, "tasks", None) is None:
            self.agent.tasks = []
        self.agent.tasks.append(task)
        logger.info(f"[ensure_chatter_task] Auto-created chatter task: {task.name}")

        # Start the execution loop for this new task so it can consume from its queue
        try:
            mainwin = getattr(self.agent, "mainwin", None)
            thread_pool = getattr(mainwin, "threadPoolExecutor", None) if mainwin else None
            if thread_pool and hasattr(task, "run_id") and task.run_id:
                future = thread_pool.submit(self.launch_unified_run, task, ["message"])
                if hasattr(self.agent, "active_tasks") and hasattr(self.agent, "task_lock"):
                    with self.agent.task_lock:
                        self.agent.active_tasks[task.run_id] = future
                logger.info(f"[ensure_chatter_task] Started execution loop for task: {task.name}, run_id={task.run_id}")
            else:
                logger.warning(f"[ensure_chatter_task] Could not start execution loop (no thread pool or run_id)")
        except Exception as e:
            logger.error(f"[ensure_chatter_task] Failed to start execution loop: {e}")

        return task
    
    def find_suitable_tasks(self, msg) -> List[ManagedTask]:
        """Find suitable tasks for a message."""
        found = []
        msg_js = json.loads(msg["message"])
        
        if msg_js['metadata']["mtype"] == "send_task":
            name_filter = (((msg_js.get('metadata') or {}).get('task') or {}).get('name') or '')
            found = [task for task in self.agent.tasks if name_filter.lower() in (task.name or "").lower()]
        elif msg_js['metadata']["mtype"] == "send_chat":
            found = [task for task in self.agent.tasks if "chat" in (task.name or "").lower()]
        
        return found
    
    # ==================== Queue Management ====================
    
    def sync_task_wait_in_line(self, event_type: str, request: Any, source: str = "", async_response: bool = None):
        """
        Queue a task/message for processing.
        
        Args:
            event_type: Type of event.
            request: The request object.
            source: Optional source identifier.
            async_response: If True, response via A2A; if False, via waiter.
        """
        try:
            logger.debug(f"sync task waiting: {event_type}, {self.agent.card.name}")
            
            # Handle async callback events (from webhooks/SSE)
            if event_type == "async_callback":
                self._route_async_callback(request)
                return
            
            # Attach async_response to request
            if async_response is not None:
                try:
                    if hasattr(request, 'params') and request.params:
                        if not request.params.metadata:
                            request.params.metadata = {}
                        request.params.metadata["async_response"] = async_response
                except Exception:
                    pass
            
            # Route to target task
            routing_result = self._resolve_event_routing(event_type, request, source)
            if routing_result:
                target_task, rule = routing_result
                if not hasattr(target_task, "queue") or target_task.queue is None:
                    logger.error(f"[QUEUE] Target task has no queue: {target_task.name}")
                    return
                
                try:
                    target_task.queue.put_nowait(request)
                    logger.info(f"[QUEUE] Message queued for task={target_task.name}")
                except Exception as e:
                    logger.error(f"[QUEUE] Failed to enqueue: {e}")
            else:
                if event_type in {"human_chat", "a2a"}:
                    fallback_task = self._ensure_chatter_task()
                    if fallback_task and getattr(fallback_task, "queue", None) is not None:
                        try:
                            fallback_task.queue.put_nowait(request)
                            logger.info(f"[QUEUE] Message queued for fallback task={fallback_task.name}")
                            return
                        except Exception as e:
                            logger.error(f"[QUEUE] Failed to enqueue to fallback chatter task: {e}")
                logger.error(f"[QUEUE] No target task for event: {event_type}")
                
        except Exception as e:
            logger.error(get_traceback(e, "ErrorWaitInLine"))
    
    def _route_async_callback(self, request: Any) -> bool:
        """
        Route an async callback event to the correct task.
        
        Uses the correlation_id to find the target task.
        
        Args:
            request: The callback request (dict with correlation_id, result, error)
            
        Returns:
            True if routed successfully, False otherwise
        """
        from .pending_events import parse_correlation_id, build_callback_event
        
        try:
            # Extract correlation_id from request
            if isinstance(request, dict):
                correlation_id = request.get("correlation_id")
                result = request.get("result")
                error = request.get("error")
            else:
                correlation_id = getattr(request, "correlation_id", None)
                result = getattr(request, "result", None)
                error = getattr(request, "error", None)
            
            if not correlation_id:
                logger.error("[CALLBACK] No correlation_id in request")
                return False
            
            # Parse task_id from correlation_id
            task_id, _ = parse_correlation_id(correlation_id)
            if not task_id:
                logger.error(f"[CALLBACK] Invalid correlation_id format: {correlation_id}")
                return False
            
            # Find the task
            target_task = self._find_task_by_id(task_id)
            if not target_task:
                logger.error(f"[CALLBACK] Task not found: {task_id}")
                return False
            
            if not target_task.queue:
                logger.error(f"[CALLBACK] Task has no queue: {task_id}")
                return False
            
            # Build and queue the callback event
            event = build_callback_event(correlation_id, result, error)
            target_task.queue.put(event)
            
            logger.info(f"[CALLBACK] Routed callback {correlation_id} to task {task_id}")
            return True
            
        except Exception as e:
            logger.error(f"[CALLBACK] Error routing callback: {e}")
            return False
    
    def _find_task_by_id(self, task_id: str) -> Optional[ManagedTask]:
        """
        Find a task by its ID or run_id.
        
        Searches both self.tasks and agent.tasks.
        
        Args:
            task_id: The task ID or run_id to find
            
        Returns:
            The ManagedTask if found, None otherwise
        """
        # Check local tasks dict first
        if task_id in self.tasks:
            return self.tasks[task_id]
        
        # Check agent.tasks list (match by id or run_id)
        try:
            for t in getattr(self.agent, "tasks", []) or []:
                if t and (getattr(t, "id", None) == task_id or getattr(t, "run_id", None) == task_id):
                    return t
        except Exception:
            pass
        
        return None
    
    def route_webhook_callback(
        self,
        correlation_id: str,
        result: Any = None,
        error: Optional[str] = None
    ) -> bool:
        """
        Public API for routing webhook callbacks.
        
        Call this from your webhook endpoint handler.
        
        Args:
            correlation_id: The operation's correlation ID
            result: Success result (if any)
            error: Error message (if failed)
            
        Returns:
            True if routed successfully, False otherwise
        """
        request = {
            "correlation_id": correlation_id,
            "result": result,
            "error": error,
        }
        return self._route_async_callback(request)
    
    # ==================== Resume Payload Building ====================
    
    def _extract_text_from_message(self, message) -> str:
        """Extract text from a Message object."""
        try:
            parts = getattr(message, "parts", None)
            if not parts and isinstance(message, dict):
                parts = message.get("parts")
            if not parts:
                return getattr(message, "text", "") if hasattr(message, "text") else str(message or "")
            
            texts = []
            for p in parts:
                ptype = getattr(p, "type", None) or (p.get("type") if isinstance(p, dict) else None)
                if ptype == "text":
                    txt = getattr(p, "text", None) or (p.get("text") if isinstance(p, dict) else None)
                    if txt:
                        texts.append(txt)
            return "\n".join(texts)
        except Exception:
            return ""
    
    def _build_resume_payload(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build a resume payload from incoming message."""
        # Try V2 path first
        try:
            use_v2 = os.getenv("RESUME_PAYLOAD_V2", "true").lower() in ("1", "true", "yes", "on")
            if use_v2:
                return self._build_resume_payload_v2(task, msg)
        except Exception as e:
            logger.debug(f"V2 resume payload failed, falling back: {e}")
        
        # Legacy behavior
        return self._build_resume_payload_legacy(task, msg)
    
    def _build_resume_payload_v2(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build resume payload using V2 logic."""
        resume_payload, resume_cp, state_patch = build_general_resume_payload(task, msg)
        
        # Merge state_patch into task.metadata["state"]
        if isinstance(state_patch, dict) and state_patch:
            cur_state = task.metadata.get("state") if isinstance(task.metadata, dict) else None
            if isinstance(cur_state, dict):
                merged = self._deep_merge(cur_state, state_patch)
                
                # Sync chatId
                self._sync_chat_id_in_messages(merged)
                
                task.metadata["state"] = merged
                
                # Update checkpoint values
                self._update_checkpoint_values(resume_cp, merged)
        
        # Include state_patch in resume payload
        if isinstance(resume_payload, dict) and isinstance(state_patch, dict):
            resume_payload["_state_patch"] = state_patch
        
        return resume_payload, resume_cp
    
    def _deep_merge(self, base: dict, override: dict) -> dict:
        """Deep merge two dictionaries."""
        out = dict(base)
        for k, v in override.items():
            if k in out and isinstance(out[k], dict) and isinstance(v, dict):
                out[k] = self._deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    
    def _sync_chat_id_in_messages(self, merged: dict):
        """Sync chatId from attributes.params to messages[1]."""
        try:
            new_chat_id = _safe_get(merged, "attributes.params.chatId")
            
            if not new_chat_id:
                params = merged.get("attributes", {}).get("params")
                if hasattr(params, 'metadata') and isinstance(params.metadata, dict):
                    metadata_params = params.metadata.get("params", {})
                    if isinstance(metadata_params, dict):
                        new_chat_id = metadata_params.get("chatId")
            
            if new_chat_id and isinstance(merged.get("messages"), list) and len(merged["messages"]) > 1:
                old_chat_id = merged["messages"][1]
                if old_chat_id != new_chat_id:
                    logger.info(f"Syncing chatId: {old_chat_id} -> {new_chat_id}")
                    merged["messages"][1] = new_chat_id
        except Exception as e:
            logger.error(f"Failed to sync chatId: {e}")
    
    def _update_checkpoint_values(self, resume_cp: Any, merged: dict):
        """Update checkpoint values with merged state."""
        try:
            if hasattr(resume_cp, "values"):
                vals = getattr(resume_cp, "values")
                if isinstance(vals, dict):
                    vals.clear()
                    vals.update(merged)
            elif isinstance(resume_cp, dict):
                resume_cp["values"] = merged
        except Exception as e:
            logger.debug(f"Failed to update checkpoint values: {e}")
    
    def _build_resume_payload_legacy(self, task: ManagedTask, msg: Any) -> Tuple[Dict[str, Any], Any]:
        """Build resume payload using legacy logic."""
        try:
            if hasattr(msg, "params"):
                message = getattr(msg.params, "message", None)
                metadata = getattr(msg.params, "metadata", {}) or {}
            elif isinstance(msg, dict):
                message = msg.get("params", {}).get("message") or msg.get("message")
                metadata = msg.get("params", {}).get("metadata", {}) or msg.get("metadata", {}) or {}
            else:
                message, metadata = None, {}
            
            human_text = self._extract_text_from_message(message) if message else ""
            qa_form = metadata.get("qa_form_to_agent") or metadata.get("qa_form") or {}
            notification = metadata.get("notification_to_agent") or metadata.get("notification") or {}
            
            payload = {
                "human_text": human_text,
                "qa_form_to_agent": qa_form,
                "notification_to_agent": notification,
            }
            
            pending_tag = metadata.get("i_tag")
            resume_cp = task.pop_checkpoint_by_tag(pending_tag) if pending_tag else None
            
            if resume_cp:
                resume_cp = resume_cp.get("checkpoint")
            
            return payload, resume_cp
            
        except Exception:
            return {"human_text": ""}, None
    
    # ==================== Unified Execution Loop ====================
    
    def launch_unified_run(
        self,
        task2run: Optional[ManagedTask] = None,
        trigger_type: "str | List[str]" = "queue",
        *,
        dev_init_state: Optional[dict] = None,
        dev_single_run: bool = False
    ):
        """
        Unified task execution loop supporting all trigger types.
        
        Args:
            task2run: ManagedTask to execute.
            trigger_type: str or list of str, e.g. "schedule", ["schedule", "message"]
                          Supported values: "schedule", "message", "auto", "dev"
                          Legacy values (a2a_queue, chat_queue, interaction) are
                          treated as "message".
            dev_init_state: Initial state for dev runs.
            dev_single_run: If True, exit after one run.
        """
        # Normalize trigger_type to a list
        if isinstance(trigger_type, str):
            triggers = [trigger_type]
        else:
            triggers = list(trigger_type)
        
        logger.info(f"[WORKER] launch_unified_run: triggers={triggers}, agent={self.agent.card.name}")
        
        if "dev" in triggers:
            self._dev_exit_requested = False
        
        current_task = task2run
        consecutive_errors = 0
        consecutive_validation_failures = 0
        max_errors = 10
        max_validation_failures = 5
        loop_count = 0
        
        # Cache agent type check
        is_twin_agent = "Twin" in self.agent.card.name
        
        while not self._stop_event.is_set():
            # Check task cancellation
            if current_task and current_task.is_cancelled():
                logger.info(f"[WORKER] Task {current_task.name} cancelled")
                break
            
            loop_count += 1
            msg = None
            message_taken = False
            
            try:
                # Get next work item
                current_task, msg, message_taken = self._get_next_work_item(
                    triggers, current_task, task2run, loop_count, is_twin_agent, dev_init_state
                )
                
                if current_task is None:
                    if self._stop_event.wait(timeout=0.5):
                        break
                    continue
                
                if msg is None and "schedule" not in triggers:
                    if self._stop_event.wait(timeout=0.5):
                        break
                    continue
                
                # Handle shutdown signal
                if isinstance(msg, dict) and msg.get("__shutdown__"):
                    logger.info("[WORKER] Shutdown signal received")
                    break
                
                # Validate task
                if not self._validate_task_for_execution(current_task):
                    consecutive_validation_failures += 1
                    if consecutive_validation_failures >= max_validation_failures:
                        logger.error(f"[WORKER] Task '{current_task.name}' failed validation {consecutive_validation_failures} times, stopping execution loop")
                        break
                    backoff = min(2 ** consecutive_validation_failures, 30)
                    if self._stop_event.wait(timeout=backoff):
                        break
                    continue
                
                # Determine the effective trigger for this execution
                effective_trigger = triggers[0] if len(triggers) == 1 else (msg or {}).get("__trigger_source__", triggers[0]) if isinstance(msg, dict) else triggers[0]
                
                # Submit execution
                self._submit_task_execution(current_task, msg, effective_trigger, dev_init_state)
                
                consecutive_errors = 0
                consecutive_validation_failures = 0
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(get_traceback(e, f"ErrorUnifiedRun[{triggers}]"))
                
                if consecutive_errors >= max_errors:
                    logger.error(f"Too many errors ({max_errors}), stopping")
                    break
                
                if self._stop_event.wait(timeout=min(consecutive_errors, 10)):
                    break
            
            finally:
                # Mark queue task done
                if message_taken and current_task and current_task.queue:
                    try:
                        current_task.queue.task_done()
                    except Exception:
                        pass
            
            # Dev single-run exit check
            if "dev" in triggers and dev_single_run:
                if getattr(self, "_dev_exit_requested", False):
                    break
            
            # Loop delay
            if self._stop_event.wait(timeout=1.0):
                break
        
        logger.info(f"[WORKER] Exiting: triggers={triggers}")
    
    def _get_next_work_item(
        self,
        triggers: List[str],
        current_task: Optional[ManagedTask],
        task2run: Optional[ManagedTask],
        loop_count: int,
        is_twin_agent: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[ManagedTask], Any, bool]:
        """
        Get the next work item by checking all trigger sources.
        
        For multi-trigger tasks (e.g. ["schedule", "message"]), each source
        is checked in priority order per iteration:
          1. Dev kickoff (if "dev" in triggers)
          2. Schedule check (if "schedule" in triggers) — non-blocking
          3. Queue poll (if any queue-based trigger) — short timeout
        
        Returns:
            Tuple of (task, message, message_taken_from_queue)
        """
        has_schedule = "schedule" in triggers
        has_dev = "dev" in triggers
        has_auto = "auto" in triggers
        # Consolidate all message-based triggers (message, a2a_queue, chat_queue, interaction) into one
        has_message = "message" in triggers or any(t in triggers for t in ("a2a_queue", "chat_queue", "interaction"))
        has_queue = has_message or has_dev
        
        # --- Dev mode: initial kickoff ---
        if has_dev and current_task:
            if current_task.id not in self._task_states:
                self._task_states[current_task.id] = {'justStarted': True}
            
            state = self._task_states[current_task.id]
            if state.get('justStarted', True) and not state.get('dev_auto_started'):
                state['dev_auto_started'] = True
                return current_task, {"__dev_kickoff__": True, "__trigger_source__": "dev"}, False
        
        # --- Auto trigger: fire once on startup ---
        if has_auto and current_task:
            if current_task.id not in self._task_states:
                self._task_states[current_task.id] = {'justStarted': True}
            
            state = self._task_states[current_task.id]
            if not state.get('auto_started'):
                state['auto_started'] = True
                return current_task, {"__auto_kickoff__": True, "__trigger_source__": "auto"}, False
        
        # --- Schedule check (non-blocking) ---
        if has_schedule:
            sched_task = find_tasks_ready_to_run(self.agent.tasks)
            if sched_task:
                return sched_task, {"__trigger_source__": "schedule"}, False
        
        # --- Message queue triggers ---
        if has_queue and current_task:
            try:
                timeout = DEV_EVENT_POLL_INTERVAL_SEC if has_dev else 0.5
                msg = current_task.queue.get(timeout=timeout)
                
                # Tag the message with trigger source
                if isinstance(msg, dict):
                    msg["__trigger_source__"] = "message"
                
                return current_task, msg, True
                
            except Empty:
                # Check timeout for pending tasks
                primary_trigger = "dev" if has_dev else "message" if has_message else triggers[0]
                self._check_pending_timeout(current_task, primary_trigger)
                
                # For schedule-only: already checked above, return None
                # For multi-trigger with schedule: no queue msg, no schedule ready
                return current_task, None, False
        
        # Schedule-only or auto-only path: already checked above, nothing ready
        if has_schedule or has_auto:
            return None, None, False
        
        return None, None, False
    
    def _check_pending_timeout(self, task: ManagedTask, trigger_type: str):
        """Check if a pending task has timed out."""
        try:
            state = self._task_states.get(task.id, {})
            pending_since = state.get('pending_since')
            
            if not pending_since:
                return
            
            elapsed = time.time() - pending_since
            
            if trigger_type == "dev":
                if elapsed > DEV_EVENT_TIMEOUT_SEC:
                    from gui.ipc.api import IPCAPI
                    ipc = IPCAPI.get_instance()
                    msg = f"[DEV] Timeout after {DEV_EVENT_TIMEOUT_SEC}s waiting for resume event"
                    logger.error(msg)
                    ipc.send_skill_editor_log("error", msg)
                    task.status.state = TaskState.failed
                    state['last_response'] = {"success": False, "error": "TimeoutWaitingForEvent"}
                    state['pending_since'] = None  # Clear so timeout only fires once
                    self._dev_exit_requested = True
            else:
                if elapsed > RUN_EVENT_TIMEOUT_SEC:
                    logger.error(f"[RUN] Timeout after {RUN_EVENT_TIMEOUT_SEC}s")
                    task.status.state = TaskState.failed
                    state['justStarted'] = True
                    state['pending_since'] = None
                    
        except Exception:
            pass
    
    def _validate_task_for_execution(self, task: ManagedTask) -> bool:
        """Validate a task is ready for execution.
        
        A task's cloud run characteristics are determined by its associated skill.
        A task without a skill cannot be scheduled or launched.
        """
        logger.info(f"[VALIDATE] Task: {task.id}, name: {task.name}")
        
        # Stop tasks that have hit max consecutive failures
        if hasattr(task, 'is_max_failures_reached') and task.is_max_failures_reached():
            logger.warning(f"[VALIDATE] Task '{task.name}' reached max failures ({task.consecutive_failures}), skipping")
            return False
        
        if task.skill is None:
            logger.error(f"[SKILL_MISSING] Task '{task.name}' (id={task.id}) has no skill attached — cannot determine execution mode. Skipping.")
            raise ValueError(f"Task '{task.name}' has no skill attached and cannot be scheduled or launched.")
        
        # Pure cloud tasks don't need a local runnable
        if self._is_pure_cloud_task(task) or self._is_hybrid_cloud_task(task):
            return True
        
        # Local tasks require a runnable
        if not hasattr(task.skill, 'runnable') or task.skill.runnable is None:
            logger.error(f"[SKILL_MISSING] Task '{task.name}' skill has runnable=None!")
            return False
        
        return True
    
    def _submit_task_execution(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        dev_init_state: Optional[dict]
    ):
        """Submit task execution to thread pool."""
        # Extract waiter task ID
        waiter_task_id = self._extract_waiter_task_id(msg)
        
        # Initialize task state
        if task.id not in self._task_states:
            self._task_states[task.id] = {'justStarted': True}
        
        is_initial_run = self._task_states[task.id]['justStarted']
        
        # Determine cloud execution mode
        is_hybrid = self._is_hybrid_cloud_task(task)
        is_pure_cloud = self._is_pure_cloud_task(task)
        
        # Pure cloud + schedule: cloud scheduler handles it, nothing to do locally
        if is_pure_cloud and trigger_type == "schedule":
            logger.info(f"[SUBMIT] Pure cloud task '{task.name}' with schedule trigger — cloud scheduler handles, skipping local execution")
            return
        
        # Amend global event routing with entries from this task's skill
        try:
            self._amend_event_routing_for_task(task)
        except Exception as e:
            logger.warning(f"[SUBMIT] Failed to amend event routing for task={task.name}: {e}")
        
        # Create execution function
        def _execute():
            if is_hybrid:
                return self._execute_hybrid_cloud_task(task, msg, trigger_type, is_initial_run, dev_init_state)
            if is_pure_cloud:
                return self._execute_pure_cloud_task(task, trigger_type)
            return self._execute_skill(task, msg, trigger_type, is_initial_run, dev_init_state)
        
        # Create callback
        def _on_complete(future):
            self._on_skill_complete(future, task, waiter_task_id, trigger_type)
        
        # Submit
        task_state = self._task_states.setdefault(task.id, {})
        task_state['pending_since'] = None
        future = self._skill_executor.submit(_execute)
        future.add_done_callback(_on_complete)
        
        task_mode = "hybrid" if is_hybrid else ("pure_cloud" if is_pure_cloud else "local")
        logger.info(f"[SUBMIT] Skill execution submitted for task={task.name} (mode={task_mode})")
    
    def _is_hybrid_cloud_task(self, task: ManagedTask) -> bool:
        """Check if a task uses a hybrid cloud skill."""
        skill = task.skill
        if skill is None:
            return False
        run_in_cloud = getattr(skill, 'run_in_cloud', False)
        hybrid_mode = getattr(skill, 'hybrid_cloud_mode', False)
        return bool(run_in_cloud and hybrid_mode)
    
    def _is_pure_cloud_task(self, task: ManagedTask) -> bool:
        """Check if a task is a pure cloud task (run_in_cloud but NOT hybrid)."""
        skill = task.skill
        if skill is None:
            return False
        run_in_cloud = getattr(skill, 'run_in_cloud', False)
        hybrid_mode = getattr(skill, 'hybrid_cloud_mode', False)
        return bool(run_in_cloud and not hybrid_mode)
    
    def _execute_pure_cloud_task(
        self,
        task: ManagedTask,
        trigger_type: str,
    ) -> Tuple[Optional[dict], bool]:
        """
        Execute a pure cloud task on-demand by calling runCloudTasks.
        
        For scheduled pure cloud tasks the cloud scheduler handles execution
        directly — this method is only called for on-demand triggers
        (message, interaction, etc.).
        """
        import requests

        skill_name = getattr(task.skill, 'name', 'unknown') if task.skill else 'unknown'
        logger.info(f"[PureCloud] Launching cloud task on-demand: task={task.name}, skill={skill_name}, trigger={trigger_type}")

        try:
            from app_context import AppContext
            from config.app_settings import get_appsync_endpoint

            login = AppContext.get_login()
            if not login or not login.access_token:
                logger.error("[PureCloud] Not authenticated — no access token")
                return {"success": False, "error": "Not authenticated"}, True

            token = login.access_token
            endpoint = get_appsync_endpoint()
        except Exception as e:
            logger.error(f"[PureCloud] Failed to get auth credentials: {e}")
            return {"success": False, "error": f"Auth error: {e}"}, True

        try:
            from agent.cloud_api.cloud_api import run_cloud_tasks

            session = requests.Session()
            result = run_cloud_tasks(session, token, [task.id], endpoint=endpoint)

            if not result.get("success"):
                error_msg = result.get("error", "runCloudTasks failed")
                logger.error(f"[PureCloud] runCloudTasks failed: {error_msg}")
                return {"success": False, "error": error_msg}, True

            run_ids = result.get("run_ids", {})
            cloud_run_id = run_ids.get(task.id) or next(iter(run_ids.values()), None)
            logger.info(f"[PureCloud] Cloud task launched: run_id={cloud_run_id}")

            # Start onTaskStatus subscription for this cloud run
            if cloud_run_id:
                try:
                    self._start_task_status_subscription(task, cloud_run_id)
                except Exception as e:
                    logger.warning(f"[TaskStatus] Could not start subscription for pure cloud task={task.name}: {e}")

            task.state["cloud_run_id"] = cloud_run_id
            return {"success": True, "cloud_run_id": cloud_run_id}, True
        except Exception as e:
            logger.error(f"[PureCloud] Error calling runCloudTasks: {e}")
            logger.error(traceback.format_exc())
            return {"success": False, "error": f"runCloudTasks error: {e}"}, True
    
    def _execute_hybrid_cloud_task(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        is_initial_run: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[dict], bool]:
        """
        Execute a hybrid cloud task:
        1. Poll queryCloudTaskRunId until the cloud task's runID is available
        2. Start onPassiveCommand WebSocket subscription with matching runID/clientID
        3. Execute the local helper skill (langgraph-based workflow)
        
        The cloud task and local helper are scheduled to run at the same time,
        but the local side waits for the cloud task to start first.
        """
        import socket
        import requests

        skill = task.skill
        skill_name = getattr(skill, 'name', 'unknown')
        logger.info(f"[HybridCloud] Starting hybrid cloud execution for task={task.name}, skill={skill_name}")

        # Get auth credentials
        try:
            from app_context import AppContext
            from config.app_settings import get_appsync_endpoint

            login = AppContext.get_login()
            if not login or not login.access_token:
                logger.error("[HybridCloud] Not authenticated - no access token")
                return {"success": False, "error": "Not authenticated"}, True

            token = login.access_token
            endpoint = get_appsync_endpoint()
            username = login.auth_manager.current_user if login.auth_manager else "unknown"
            host_name = socket.gethostname()
        except Exception as e:
            logger.error(f"[HybridCloud] Failed to get auth credentials: {e}")
            return {"success": False, "error": f"Auth error: {e}"}, True

        # Step 1: Obtain cloud task's runID
        # - Schedule trigger: cloud task is already running, poll for its runID
        # - On-demand trigger (message/interaction): launch cloud task now via runCloudTasks, get runID directly
        session = requests.Session()
        cloud_run_id = None

        if trigger_type == "schedule":
            logger.info(f"[HybridCloud] Step 1: Polling for cloud runID (task_id={task.id}, host={host_name})")
            try:
                from agent.cloud_api.cloud_api import query_cloud_task_run_id_with_retry

                run_id_result = query_cloud_task_run_id_with_retry(
                    session, token, task.id, host_name,
                    meta_data={"owner": username},
                    endpoint=endpoint,
                    max_wait_seconds=120,
                    poll_interval=5,
                )

                if not run_id_result.get("success"):
                    error_msg = run_id_result.get("error", "Failed to get cloud runID")
                    logger.error(f"[HybridCloud] Failed to get cloud runID: {error_msg}")
                    return {"success": False, "error": error_msg}, True

                cloud_run_id = run_id_result["run_id"]
                logger.info(f"[HybridCloud] Got cloud runID via polling: {cloud_run_id}")
            except Exception as e:
                logger.error(f"[HybridCloud] Error polling for cloud runID: {e}")
                logger.error(traceback.format_exc())
                return {"success": False, "error": f"RunID poll error: {e}"}, True
        else:
            # On-demand: launch cloud task and get runID from response
            logger.info(f"[HybridCloud] Step 1: Launching cloud task via runCloudTasks (task_id={task.id}, trigger={trigger_type})")
            try:
                from agent.cloud_api.cloud_api import run_cloud_tasks

                result = run_cloud_tasks(session, token, [task.id], endpoint=endpoint)

                if not result.get("success"):
                    error_msg = result.get("error", "runCloudTasks failed")
                    logger.error(f"[HybridCloud] runCloudTasks failed: {error_msg}")
                    return {"success": False, "error": error_msg}, True

                run_ids = result.get("run_ids", {})
                cloud_run_id = run_ids.get(task.id)
                if not cloud_run_id:
                    # Try first available run_id if task.id key doesn't match exactly
                    cloud_run_id = next(iter(run_ids.values()), None)

                if not cloud_run_id:
                    logger.error(f"[HybridCloud] runCloudTasks returned no runID for task {task.id}")
                    return {"success": False, "error": "No runID in runCloudTasks response"}, True

                logger.info(f"[HybridCloud] Got cloud runID from runCloudTasks: {cloud_run_id}")
            except Exception as e:
                logger.error(f"[HybridCloud] Error calling runCloudTasks: {e}")
                logger.error(traceback.format_exc())
                return {"success": False, "error": f"runCloudTasks error: {e}"}, True

        # Step 2a: Start onTaskStatus subscription for this cloud run
        try:
            self._start_task_status_subscription(task, cloud_run_id)
        except Exception as e:
            logger.warning(f"[TaskStatus] Could not start subscription for hybrid task={task.name}: {e}")

        # Step 2b: Start passive command subscription
        client_id = self._get_client_id()
        logger.info(f"[HybridCloud] Step 2: Starting passive command subscription (run_id={cloud_run_id}, client_id={client_id})")
        try:
            self._start_hybrid_passive_subscription(token, endpoint, cloud_run_id, client_id)
            logger.info(f"[HybridCloud] Passive subscription started successfully")
        except Exception as e:
            logger.warning(f"[HybridCloud] Failed to start passive subscription (continuing anyway): {e}")

        # Step 3: Store cloud run_id on task for the helper skill to use
        task.state["cloud_run_id"] = cloud_run_id
        task.state["is_hybrid_cloud"] = True
        task.state["client_id"] = client_id

        # Step 4: Execute the local helper skill normally
        logger.info(f"[HybridCloud] Step 3: Executing local helper skill: {skill_name}")
        return self._execute_skill(task, msg, trigger_type, is_initial_run, dev_init_state)
    
    def _get_client_id(self) -> str:
        """Get the client ID (acctSiteID) for passive command subscription."""
        try:
            mainwin = self.agent.mainwin
            if hasattr(mainwin, 'getAcctSiteID'):
                cid = mainwin.getAcctSiteID()
                if cid:
                    return cid
        except Exception:
            pass
        import socket
        return f"client-{socket.gethostname()}"
    
    def _start_hybrid_passive_subscription(self, token: str, endpoint: str, run_id: str, client_id: str) -> None:
        """Start onPassiveCommand WebSocket subscription for hybrid cloud execution."""
        try:
            from agent.ec_skills.browser_use_extension.passive_command_service import PassiveCommandService
            from agent.ec_skills.browser_use_extension.appsync_passive_client import (
                AppSyncPassiveClientConfig,
                _derive_realtime_endpoint,
                _derive_api_host,
            )

            mainwin = self.agent.mainwin
            http_endpoint = endpoint or mainwin.getWanApiEndpoint()
            ws_endpoint = getattr(mainwin, 'getWSApiEndpoint', lambda: None)() or _derive_realtime_endpoint(http_endpoint)
            api_host = getattr(mainwin, 'getWSApiHost', lambda: None)() or _derive_api_host(http_endpoint, ws_endpoint)

            config = AppSyncPassiveClientConfig(
                http_endpoint=http_endpoint,
                ws_endpoint=ws_endpoint,
                api_host=api_host,
                auth_token=token,
                run_id=run_id,
                client_id=client_id,
            )

            route_fn = getattr(mainwin, '_route_passive_command_to_task', None)
            if not route_fn:
                logger.warning("[HybridCloud] No _route_passive_command_to_task on mainwin")
                return

            service = PassiveCommandService(config=config, route_command=route_fn)

            import asyncio as _asyncio

            async def _start():
                await service.start()

            loop = getattr(mainwin, '_async_loop', None)
            if loop and loop.is_running():
                _asyncio.run_coroutine_threadsafe(_start(), loop)
            else:
                def _run():
                    _asyncio.run(_start())
                t = threading.Thread(target=_run, daemon=True)
                t.start()

            logger.info(f"[HybridCloud] Passive subscription started: client_id={client_id}, run_id={run_id}")
        except Exception as e:
            logger.error(f"[HybridCloud] Failed to start passive subscription: {e}")
            logger.error(traceback.format_exc())
    
    def _start_task_status_subscription(self, task: ManagedTask, run_id: str) -> None:
        """Start onTaskStatus WebSocket subscription for a running task.
        
        Called after obtaining the runId for any task type (local, cloud, hybrid).
        Uses the runId as the 'runner' parameter so the subscription receives
        status updates specific to this task run.
        """
        try:
            from app_context import AppContext
            from agent.cloud_api.cloud_api import get_appsync_endpoint
            from .appsync_pubsub import AppSyncApiKeyConfig, subscribe_task_status

            login = AppContext.get_login()
            if not login or not login.access_token:
                logger.warning(f"[TaskStatus] Not authenticated, skipping onTaskStatus subscription for run_id={run_id}")
                return

            mainwin = self.agent.mainwin
            endpoint = get_appsync_endpoint()
            api_key = ""
            if hasattr(mainwin, 'getWanApiKey'):
                api_key = mainwin.getWanApiKey() or ""

            if not endpoint:
                logger.warning(f"[TaskStatus] No AppSync endpoint, skipping onTaskStatus subscription for run_id={run_id}")
                return

            config = AppSyncApiKeyConfig(
                http_endpoint=endpoint,
                api_key=api_key,
                auth_token=login.access_token,
            )

            task_ref = task  # capture for callback closure

            async def _on_envelope(envelope: dict):
                self._on_task_status_envelope(task_ref, envelope)

            async def _run_subscription():
                await subscribe_task_status(
                    config=config,
                    runner=run_id,
                    on_envelope=_on_envelope,
                    max_retries=10,
                )

            import asyncio as _asyncio

            loop = getattr(mainwin, '_async_loop', None)
            if loop and loop.is_running():
                _asyncio.run_coroutine_threadsafe(_run_subscription(), loop)
            else:
                def _run():
                    _asyncio.run(_run_subscription())
                t = threading.Thread(target=_run, daemon=True)
                t.start()

            logger.info(f"[TaskStatus] onTaskStatus subscription started: task={task.name}, run_id={run_id}")
        except Exception as e:
            logger.warning(f"[TaskStatus] Failed to start onTaskStatus subscription for run_id={run_id}: {e}")
            logger.debug(traceback.format_exc())

    def _on_task_status_envelope(self, task: ManagedTask, envelope: dict) -> None:
        """Handle an onTaskStatus WebSocket message for a task run.
        
        Envelope fields: id, runID, runner, error, success, status, timestamp
        """
        try:
            run_id = envelope.get("runID") or envelope.get("run_id") or ""
            success = envelope.get("success")
            error = envelope.get("error")
            status = envelope.get("status")

            logger.info(
                f"[TaskStatus] Received status update: task={task.name}, "
                f"run_id={run_id}, success={success}, status={status}, error={error}"
            )

            # Store latest cloud status on task state for visibility
            task.state["last_cloud_status"] = {
                "run_id": run_id,
                "success": success,
                "error": error,
                "status": status,
                "timestamp": envelope.get("timestamp"),
            }

            # If the cloud side reports failure, log it prominently
            if success is False and error:
                logger.error(f"[TaskStatus] Cloud-side failure for task={task.name}: {error}")

        except Exception as e:
            logger.warning(f"[TaskStatus] Error processing status envelope: {e}")

    def _extract_waiter_task_id(self, msg: Any) -> Optional[str]:
        """Extract waiter task ID from message."""
        try:
            if msg and hasattr(msg, 'params') and hasattr(msg.params, 'id'):
                return msg.params.id
            if msg and isinstance(msg, dict):
                attrs = msg.get('attributes')
                if isinstance(attrs, dict) and attrs.get('params'):
                    params = attrs['params']
                    return params.id if hasattr(params, 'id') else params.get('id')
                return msg.get('params', {}).get('id') or msg.get('id')
        except Exception:
            pass
        return None
    
    def _execute_skill(
        self,
        task: ManagedTask,
        msg: Any,
        trigger_type: str,
        is_initial_run: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[dict], bool]:
        """Execute a skill and return result.
        
        Uses hybrid async/sync execution with automatic fallback.
        Async mode can be controlled via:
        - Environment variable: ECAN_ASYNC_EXECUTION=true/false
        - Task metadata: task.metadata.get("use_async", True)
        """
        try:
            from .executor import execute_task_hybrid

            # Start onTaskStatus subscription for this task run
            try:
                self._start_task_status_subscription(task, task.run_id)
            except Exception as e:
                logger.warning(f"[TaskStatus] Could not start subscription for local task={task.name}: {e}")

            def _is_retryable_error_text(error_text: str) -> bool:
                et = (error_text or "").lower()
                return any(
                    k in et
                    for k in (
                        "error code: 503",
                        " error code: 503",
                        "503",
                        "service unavailable",
                        "rate limit",
                        "429",
                        "timeout",
                        "api connection",
                        "apiconnectionerror",
                        "temporarily unavailable",
                        "internalservererror",
                    )
                )

            def _extract_error_text(resp: Any) -> str:
                if isinstance(resp, dict):
                    return str(resp.get("Error") or resp.get("error") or resp.get("message") or "")
                return str(resp or "")
            
            # Determine if async execution should be used
            # Can be disabled per-task or globally via env var
            use_async = task.metadata.get("use_async", True)
            
            # Dev mode defaults to sync for easier debugging (can be overridden)
            if trigger_type == "dev":
                use_async = task.metadata.get("use_async", False)
            
            if is_initial_run:
                # Prepare state
                if trigger_type == "dev" and isinstance(dev_init_state, dict):
                    final_state = self._prepare_dev_state(task, msg, dev_init_state)
                else:
                    final_state = prep_skills_run(task.skill, self.agent, task.id, msg, None)

                task.metadata["state"] = final_state

                max_retries = int(task.metadata.get("retry_max", 2) or 2)
                retry_base_delay = float(task.metadata.get("retry_delay", 1.0) or 1.0)
                retry_backoff = float(task.metadata.get("retry_backoff", 2.0) or 2.0)

                response = None
                for attempt in range(max_retries + 1):
                    response = execute_task_hybrid(task, final_state, use_async=use_async)
                    if isinstance(response, dict) and response.get("success") is False:
                        err_text = _extract_error_text(response)
                        if attempt < max_retries and _is_retryable_error_text(err_text):
                            delay = retry_base_delay * (retry_backoff ** attempt)
                            logger.warning(
                                f"[EXECUTOR] Retryable failure (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s: {err_text}"
                            )
                            time.sleep(delay)
                            continue
                    break

                return response, True
            else:
                # Resume run
                resume_payload, cp = self._build_resume_payload(task, msg)
                resume_cmd = Command(resume=resume_payload)

                resume_tag = None
                if isinstance(resume_payload, dict):
                    resume_tag = resume_payload.get("_resuming_from")
                if not resume_tag and cp:
                    resume_tag = _safe_get(cp, "values.attributes.i_tag") or _safe_get(cp, "values.attributes.tag")

                resume_context = None
                if resume_tag:
                    resume_context = {"skip_bp_once": [resume_tag]}

                max_retries = int(task.metadata.get("retry_max", 2) or 2)
                retry_base_delay = float(task.metadata.get("retry_delay", 1.0) or 1.0)
                retry_backoff = float(task.metadata.get("retry_backoff", 2.0) or 2.0)

                response = None
                for attempt in range(max_retries + 1):
                    if cp:
                        response = execute_task_hybrid(
                            task,
                            resume_cmd,
                            use_async=use_async,
                            checkpoint=cp,
                            context=resume_context,
                        )
                    else:
                        response = execute_task_hybrid(
                            task,
                            resume_cmd,
                            use_async=use_async,
                            context=resume_context,
                        )

                    if isinstance(response, dict) and response.get("success") is False:
                        err_text = _extract_error_text(response)
                        if attempt < max_retries and _is_retryable_error_text(err_text):
                            delay = retry_base_delay * (retry_backoff ** attempt)
                            logger.warning(
                                f"[EXECUTOR] Retryable failure (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s: {err_text}"
                            )
                            time.sleep(delay)
                            continue
                    break

                return response, False
                
        except Exception as e:
            logger.error(f"[EXECUTOR] Failed: {e}")
            logger.error(traceback.format_exc())
            return None, True
    
    def _prepare_dev_state(self, task: ManagedTask, msg: Any, dev_init_state: dict) -> dict:
        """Prepare state for dev run."""
        prepared_state = None
        try:
            prep_msg = msg if msg not in (None, {"__dev_kickoff__": True}) else None
            prepared_state = prep_skills_run(task.skill, self.agent, task.id, prep_msg, None)
        except Exception as e:
            logger.error(f"[DEV] prep_skills_run failed: {e}")
        
        final_state = {}
        if isinstance(prepared_state, dict):
            final_state = prepared_state
        if isinstance(dev_init_state, dict):
            final_state = self._deep_merge(final_state, dev_init_state)
        
        return final_state or task.metadata.get("state", {})
    
    def _log_task_node_timings(self, task: "ManagedTask", waiter_task_id: Optional[str], response: Any) -> None:
        try:
            cp = None
            values = None
            if isinstance(response, dict):
                cp = response.get("cp")
            if cp is not None and hasattr(cp, "values"):
                values = getattr(cp, "values", None)
            if values is None:
                values = task.metadata.get("state")

            if not isinstance(values, dict):
                return

            attrs = values.get("attributes")
            timings = attrs.get("__node_timings__") if isinstance(attrs, dict) else None
            if not (isinstance(timings, list) and timings):
                return

            total_ms = 0
            status_cnt = {}
            cleaned = []
            for t in timings:
                if not isinstance(t, dict):
                    continue
                dms = int(t.get("duration_ms") or 0)
                total_ms += max(dms, 0)
                st = str(t.get("status") or "")
                status_cnt[st] = status_cnt.get(st, 0) + 1
                cleaned.append(t)

            cleaned.sort(key=lambda x: int(x.get("duration_ms") or 0), reverse=True)
            topn = cleaned[:10]
            logger.info(
                f"[PERF][TASK] task={getattr(task, 'name', '')} waiter={waiter_task_id} "
                f"nodes={len(cleaned)} total_node_time={total_ms}ms status={status_cnt}"
            )
            for i, t in enumerate(topn, 1):
                logger.info(
                    f"[PERF][TASK][TOP{i}] {t.get('skill')}::{t.get('node')} "
                    f"status={t.get('status')} duration_ms={t.get('duration_ms')}"
                )
        except Exception:
            pass
    
    def _on_skill_complete(
        self,
        future: concurrent.futures.Future,
        task: ManagedTask,
        waiter_task_id: Optional[str],
        trigger_type: str
    ):
        """Handle skill execution completion."""
        try:
            response, was_initial = future.result()

            # Distinguish real failures from interrupts: an interrupt returns
            # success=False but carries __interrupt__ in the step dict and has
            # no Error/error key.  Let interrupts fall through to the handler
            # below so the loop stays alive waiting for resume events.
            _step_data = response.get("step") if isinstance(response, dict) else None
            _is_interrupt = isinstance(_step_data, dict) and "__interrupt__" in _step_data
            if isinstance(response, dict) and response.get("success") is False and not _is_interrupt:
                err_text = str(response.get("Error") or response.get("error") or response)
                logger.error(f"[COMPLETE] Skill failed for waiter={waiter_task_id}: {err_text}")
                try:
                    task.status.state = TaskState.failed
                    task.status.message = _create_message("agent", err_text)
                except Exception:
                    pass

                # Track consecutive failures on the task
                if hasattr(task, 'record_failure'):
                    fail_count = task.record_failure()
                    if hasattr(task, 'is_max_failures_reached') and task.is_max_failures_reached():
                        logger.error(f"[COMPLETE] Task '{task.name}' reached max failures ({fail_count}), will not be re-submitted")

                if trigger_type == "schedule":
                    from datetime import datetime
                    task.last_run_datetime = datetime.now()
                    task.already_run_flag = True
                    logger.warning(f"[SCHEDULE] Task '{task.name}' failed, updated last_run_datetime")
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError(err_text))
                elif trigger_type == "message" and waiter_task_id:
                    self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, response)
                return

            # Reset failure counter on success
            if hasattr(task, 'reset_failures'):
                task.reset_failures()
            logger.info(f"[COMPLETE] Skill completed for waiter={waiter_task_id}")

            self._log_task_node_timings(task, waiter_task_id, response)
            
            # Check for interrupt
            task_interrupted = False
            if response:
                step = response.get('step') or {}
                current_state = response.get('cp')
                
                if isinstance(step, dict) and '__interrupt__' in step:
                    task_interrupted = True
                    # Note: send_response_back removed here — chat_node now sends
                    # the LLM response directly to GUI via ChatMessageSender.
                    # Keeping the interrupt detection for task state management.
            
            # Update task state
            state = self._task_states.setdefault(task.id, {})
            state['justStarted'] = not task_interrupted
            if task_interrupted:
                state['pending_since'] = time.time()
            else:
                state['pending_since'] = None
                if trigger_type == "dev":
                    self._dev_exit_requested = True
            
            # Update scheduling state for scheduled tasks (only on successful completion)
            if trigger_type == "schedule" and not task_interrupted:
                from datetime import datetime
                task.last_run_datetime = datetime.now()
                task.already_run_flag = True
                logger.info(f"[SCHEDULE] Task '{task.name}' completed, updated last_run_datetime")
            
            # Resolve waiter
            if trigger_type == "schedule":
                if response:
                    self.agent.a2a_server.task_manager.set_result(task.id, response)
                else:
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError("Task failed"))
            elif trigger_type == "message" and waiter_task_id:
                self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, response)
                
        except Exception as e:
            logger.error(f"[COMPLETE] Callback error: {e}")
            logger.error(traceback.format_exc())
            
            # IMPORTANT: Set already_run_flag even on failure to prevent infinite retries
            # The task will be retried in the next schedule cycle (e.g., tomorrow for daily tasks)
            if trigger_type == "schedule":
                from datetime import datetime
                task.last_run_datetime = datetime.now()
                task.already_run_flag = True
                logger.warning(f"[SCHEDULE] Task '{task.name}' failed but marked as run to prevent infinite retries")
    
    # ==================== Deprecated Methods ====================
    
    def launch_scheduled_run(self, task=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="schedule")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='schedule')")
        self.launch_unified_run(task2run=task, trigger_type="schedule")
    
    def launch_reacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="message")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='message')")
        self.launch_unified_run(task2run=task2run, trigger_type="message")
    
    def launch_interacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="message")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='message')")
        self.launch_unified_run(task2run=task2run, trigger_type="message")
    
    def update_event_handler(self, event_type="", event_queue=None):
        """DEPRECATED: No-op for backward compatibility."""
        pass
    
    async def step_task(self, task_id: str):
        """Step through a task one node at a time."""
        task = self.tasks[task_id]
        task.status.state = TaskState.working
        task.pause_event.set()
        
        async def one_step():
            async for step in task.graph.astream(task.state):
                task.metadata["state"] = step
                task.status.state = TaskState.unknown
                task.pause_event.clear()
                break
        
        task.task = asyncio.create_task(one_step())
    
    async def run_until_node(self, task_id: str, target_node: str):
        """Run task until reaching a specific node."""
        task = self.tasks[task_id]
        task.status.state = TaskState.working
        
        async def runner():
            async for step in task.graph.astream(task.state):
                await task.pause_event.wait()
                task.state = step
                if step.get("current_node") == target_node:
                    task.status.state = TaskState.input_required
                    task.pause_event.clear()
                    return
            task.status.state = TaskState.completed
        
        task.task = asyncio.create_task(runner())
    
    async def resume_on_external_event(self, task_id: str, injected_state: dict):
        """Resume task with external event data."""
        from a2a.types import Part
        task = self.tasks[task_id]
        if task.status.message:
            task.status.message.parts.append(Part(type="text", text=str(injected_state)))
        await self.resume_task(task_id)
