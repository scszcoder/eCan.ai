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

from agent.a2a.common.types import TaskState, Message, TextPart, TaskSendParams
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
from .executor import TaskExecutor

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent
    from agent.ec_skill import EC_Skill
    from agent.a2a.common.types import Task

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
            logger.debug(f"[TaskRunner][launch_dev_run] init_state: {init_state}")
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
        try:
            for task_id, managed_task in self.tasks.items():
                try:
                    if managed_task:
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
                    if st in (TaskState.SUBMITTED, TaskState.WORKING):
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
            if tbr_task.status.state not in (TaskState.WORKING, TaskState.INPUT_REQUIRED):
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
        task.status.state = TaskState.INPUT_REQUIRED
    
    async def resume_task(self, task_id: str):
        """Resume a paused task."""
        task = self.tasks[task_id]
        task.resume()
        task.status.state = TaskState.WORKING
    
    async def cancel_task(self, task_id: str, timeout: float = 5.0):
        """Cancel a task and clean up resources."""
        if task_id not in self.tasks:
            raise KeyError(f"Task {task_id} not found")
        
        task = self.tasks[task_id]
        
        # Check terminal state
        terminal_states = (TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED)
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
            
            # Update status
            task.status.state = TaskState.CANCELED
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
                    if task.status.state != TaskState.CANCELED:
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
        
        from agent.a2a.common.types import Task
        base_task = TypeAdapter(Task).validate_json(raw)
        task = ManagedTask(**base_task.model_dump(), skill=skill)
        
        self.tasks[task_id] = task
        return task
    
    # ==================== Event Routing ====================
    
    def _resolve_event_routing(self, event_type: str, request: Any, source: str = "") -> Optional[ManagedTask]:
        """
        Use skill mapping DSL to route events to tasks.
        
        Args:
            event_type: Type of event.
            request: The request object.
            source: Optional source identifier.
            
        Returns:
            The matching ManagedTask or None.
        """
        try:
            event = normalize_event(event_type, request, src=source)
            etype = event.get("type") or event_type
        except Exception:
            etype = event_type
        
        logger.debug(f"normalized event: {etype}, {event}")
        
        try:
            tasks_list = getattr(self.agent, "tasks", []) or []
            logger.info(f"[ROUTING] Agent {self.agent.card.name} has {len(tasks_list)} tasks")
            
            for t in tasks_list:
                if not t or not getattr(t, "skill", None):
                    continue
                
                skill = t.skill
                rules = getattr(skill, "mapping_rules", None)
                
                if not isinstance(rules, dict):
                    continue
                
                # Get event_routing from rules
                event_routing = rules.get("event_routing")
                if not isinstance(event_routing, dict):
                    run_mode = getattr(skill, "run_mode", None)
                    if run_mode and isinstance(rules.get(run_mode), dict):
                        event_routing = rules.get(run_mode, {}).get("event_routing")
                
                if not isinstance(event_routing, dict):
                    continue
                
                rule = event_routing.get(etype)
                if not isinstance(rule, dict):
                    continue
                
                # Evaluate selector
                selector = rule.get("task_selector") or ""
                if self._evaluate_selector(selector, t):
                    logger.info(f"[ROUTING] Matched task: {t.name}, id={t.id}")
                    return t
                    
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
        """Find a chatter task."""
        found = [task for task in self.agent.tasks if 'chatter' in task.name.lower()]
        if found:
            logger.debug(f"[find_chatter_tasks] Found: {found[0].id}")
            return found[0]
        logger.error("NO chatter tasks found!")
        return None
    
    def find_suitable_tasks(self, msg) -> List[ManagedTask]:
        """Find suitable tasks for a message."""
        found = []
        msg_js = json.loads(msg["message"])
        
        if msg_js['metadata']["mtype"] == "send_task":
            name_filter = (((msg_js.get('metadata') or {}).get('task') or {}).get('name') or '')
            found = [task for task in self.agent.tasks if name_filter.lower() in (task.name or "").lower()]
        elif msg_js['metadata']["mtype"] == "send_chat":
            found = [task for task in self.agent.tasks if "chatter task" in (task.name or "").lower()]
        
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
            target_task = self._resolve_event_routing(event_type, request, source)
            if target_task:
                if not hasattr(target_task, "queue") or target_task.queue is None:
                    logger.error(f"[QUEUE] Target task has no queue: {target_task.name}")
                    return
                
                try:
                    target_task.queue.put_nowait(request)
                    logger.info(f"[QUEUE] Message queued for task={target_task.name}")
                except Exception as e:
                    logger.error(f"[QUEUE] Failed to enqueue: {e}")
            else:
                logger.error(f"[QUEUE] No target task for event: {event_type}")
                
        except Exception as e:
            logger.error(get_traceback(e, "ErrorWaitInLine"))
    
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
        trigger_type: str = "queue",
        *,
        dev_init_state: Optional[dict] = None,
        dev_single_run: bool = False
    ):
        """
        Unified task execution loop supporting all trigger types.
        
        Args:
            task2run: ManagedTask to execute.
            trigger_type: "schedule" | "a2a_queue" | "chat_queue" | "dev"
            dev_init_state: Initial state for dev runs.
            dev_single_run: If True, exit after one run.
        """
        logger.info(f"[WORKER] launch_unified_run: trigger={trigger_type}, agent={self.agent.card.name}")
        
        if trigger_type == "dev":
            self._dev_exit_requested = False
        
        current_task = task2run
        consecutive_errors = 0
        max_errors = 10
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
                    trigger_type, current_task, task2run, loop_count, is_twin_agent, dev_init_state
                )
                
                if current_task is None:
                    if self._stop_event.wait(timeout=0.5):
                        break
                    continue
                
                if msg is None and trigger_type != "schedule":
                    if self._stop_event.wait(timeout=0.5):
                        break
                    continue
                
                # Handle shutdown signal
                if isinstance(msg, dict) and msg.get("__shutdown__"):
                    logger.info("[WORKER] Shutdown signal received")
                    break
                
                # Validate task
                if not self._validate_task_for_execution(current_task):
                    continue
                
                # Submit execution
                self._submit_task_execution(current_task, msg, trigger_type, dev_init_state)
                
                consecutive_errors = 0
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(get_traceback(e, f"ErrorUnifiedRun[{trigger_type}]"))
                
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
            if trigger_type == "dev" and dev_single_run:
                if getattr(self, "_dev_exit_requested", False):
                    break
            
            # Loop delay
            if self._stop_event.wait(timeout=1.0):
                break
        
        logger.info(f"[WORKER] Exiting: trigger={trigger_type}")
    
    def _get_next_work_item(
        self,
        trigger_type: str,
        current_task: Optional[ManagedTask],
        task2run: Optional[ManagedTask],
        loop_count: int,
        is_twin_agent: bool,
        dev_init_state: Optional[dict]
    ) -> Tuple[Optional[ManagedTask], Any, bool]:
        """
        Get the next work item based on trigger type.
        
        Returns:
            Tuple of (task, message, message_taken_from_queue)
        """
        if trigger_type == "schedule":
            task = find_tasks_ready_to_run(self.agent.tasks)
            return task, None, False
        
        if trigger_type in ("a2a_queue", "chat_queue", "message", "dev"):
            if not current_task:
                return None, None, False
            
            # Dev mode: initial kickoff
            if trigger_type == "dev":
                if current_task.id not in self._task_states:
                    self._task_states[current_task.id] = {'justStarted': True}
                
                state = self._task_states[current_task.id]
                if state.get('justStarted', True) and not state.get('dev_auto_started'):
                    state['dev_auto_started'] = True
                    return current_task, {"__dev_kickoff__": True}, False
            
            # Try to get from queue
            try:
                timeout = 0.5 if trigger_type != "dev" else DEV_EVENT_POLL_INTERVAL_SEC
                msg = current_task.queue.get(timeout=timeout)
                
                # Handle chat_queue task finding
                if trigger_type == "chat_queue":
                    chatter = self.find_chatter_tasks()
                    if chatter:
                        current_task = chatter
                
                return current_task, msg, True
                
            except Empty:
                # Check timeout for pending tasks
                self._check_pending_timeout(current_task, trigger_type)
                return current_task, None, False
        
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
                    msg = f"[DEV] Timeout after {DEV_EVENT_TIMEOUT_SEC}s"
                    logger.error(msg)
                    ipc.send_skill_editor_log("error", msg)
                    task.status.state = TaskState.FAILED
                    state['last_response'] = {"success": False, "error": "TimeoutWaitingForEvent"}
                    self._dev_exit_requested = True
            else:
                if elapsed > RUN_EVENT_TIMEOUT_SEC:
                    logger.error(f"[RUN] Timeout after {RUN_EVENT_TIMEOUT_SEC}s")
                    task.status.state = TaskState.FAILED
                    state['justStarted'] = True
                    state['pending_since'] = None
                    
        except Exception:
            pass
    
    def _validate_task_for_execution(self, task: ManagedTask) -> bool:
        """Validate a task is ready for execution."""
        logger.info(f"[VALIDATE] Task: {task.id}, name: {task.name}")
        
        if task.skill is None:
            logger.error(f"[SKILL_MISSING] Task {task.id} has skill=None!")
            return False
        
        if not hasattr(task.skill, 'runnable') or task.skill.runnable is None:
            logger.error(f"[SKILL_MISSING] Skill has runnable=None!")
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
        
        # Create execution function
        def _execute():
            return self._execute_skill(task, msg, trigger_type, is_initial_run, dev_init_state)
        
        # Create callback
        def _on_complete(future):
            self._on_skill_complete(future, task, waiter_task_id, trigger_type)
        
        # Submit
        task_state = self._task_states.setdefault(task.id, {})
        task_state['pending_since'] = None
        future = self._skill_executor.submit(_execute)
        future.add_done_callback(_on_complete)
        
        logger.info(f"[SUBMIT] Skill execution submitted for task={task.name}")
    
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
        """Execute a skill and return result."""
        try:
            executor = TaskExecutor(task)
            
            if is_initial_run:
                # Prepare state
                if trigger_type == "dev" and isinstance(dev_init_state, dict):
                    final_state = self._prepare_dev_state(task, msg, dev_init_state)
                else:
                    final_state = prep_skills_run(task.skill, self.agent, task.id, msg, None)
                
                task.metadata["state"] = final_state
                response = executor.stream_run(final_state)
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

                if cp:
                    response = executor.stream_run(
                        resume_cmd,
                        checkpoint=cp,
                        context=resume_context,
                    )
                else:
                    response = executor.stream_run(
                        resume_cmd,
                        context=resume_context,
                    )
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
            logger.info(f"[COMPLETE] Skill completed for waiter={waiter_task_id}")
            
            # Check for interrupt
            task_interrupted = False
            if response:
                step = response.get('step') or {}
                current_state = response.get('cp')
                
                if isinstance(step, dict) and '__interrupt__' in step:
                    task_interrupted = True
                    interrupt_obj = step["__interrupt__"][0]
                    if "prompt_to_human" in interrupt_obj.value or "prompt_to_agent" in interrupt_obj.value:
                        try:
                            chatId = current_state.values.get("messages")[1]
                            if chatId:
                                send_response_back(current_state.values)
                        except Exception:
                            pass
            
            # Update task state
            state = self._task_states.setdefault(task.id, {})
            state['justStarted'] = not task_interrupted
            if task_interrupted:
                state['pending_since'] = time.time()
            else:
                state['pending_since'] = None
                if trigger_type == "dev":
                    self._dev_exit_requested = True
            
            # Resolve waiter
            if trigger_type == "schedule":
                if response:
                    self.agent.a2a_server.task_manager.set_result(task.id, response)
                else:
                    self.agent.a2a_server.task_manager.set_exception(task.id, RuntimeError("Task failed"))
            elif trigger_type in ("a2a_queue", "chat_queue") and waiter_task_id:
                self.agent.a2a_server.task_manager.resolve_waiter(waiter_task_id, response)
                
        except Exception as e:
            logger.error(f"[COMPLETE] Callback error: {e}")
            logger.error(traceback.format_exc())
    
    # ==================== Deprecated Methods ====================
    
    def launch_scheduled_run(self, task=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="schedule")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='schedule')")
        self.launch_unified_run(task2run=task, trigger_type="schedule")
    
    def launch_reacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="a2a_queue")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='a2a_queue')")
        self.launch_unified_run(task2run=task2run, trigger_type="a2a_queue")
    
    def launch_interacted_run(self, task2run=None):
        """DEPRECATED: Use launch_unified_run(trigger_type="chat_queue")."""
        logger.warning("[DEPRECATED] Use launch_unified_run(trigger_type='chat_queue')")
        self.launch_unified_run(task2run=task2run, trigger_type="chat_queue")
    
    def update_event_handler(self, event_type="", event_queue=None):
        """DEPRECATED: No-op for backward compatibility."""
        pass
    
    async def step_task(self, task_id: str):
        """Step through a task one node at a time."""
        task = self.tasks[task_id]
        task.status.state = TaskState.WORKING
        task.pause_event.set()
        
        async def one_step():
            async for step in task.graph.astream(task.state):
                task.metadata["state"] = step
                task.status.state = TaskState.UNKNOWN
                task.pause_event.clear()
                break
        
        task.task = asyncio.create_task(one_step())
    
    async def run_until_node(self, task_id: str, target_node: str):
        """Run task until reaching a specific node."""
        task = self.tasks[task_id]
        task.status.state = TaskState.WORKING
        
        async def runner():
            async for step in task.graph.astream(task.state):
                await task.pause_event.wait()
                task.state = step
                if step.get("current_node") == target_node:
                    task.status.state = TaskState.INPUT_REQUIRED
                    task.pause_event.clear()
                    return
            task.status.state = TaskState.COMPLETED
        
        task.task = asyncio.create_task(runner())
    
    async def resume_on_external_event(self, task_id: str, injected_state: dict):
        """Resume task with external event data."""
        from agent.a2a.common.types import Part
        task = self.tasks[task_id]
        if task.status.message:
            task.status.message.parts.append(Part(type="text", text=str(injected_state)))
        await self.resume_task(task_id)
