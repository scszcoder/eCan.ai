"""
Dev Runner - Development and debugging support for tasks.

This module handles:
- Breakpoint management
- Dev run execution
- Step/pause/resume controls
- Skill editor integration
"""

import traceback
from queue import Queue
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from langgraph.types import Command

from a2a.types import TaskState
from agent.ec_skills.dev_defs import BreakpointManager
from agent.cloud_worker.cloud_logger import send_skill_editor_log
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

if TYPE_CHECKING:
    from .models import ManagedTask
    from .executor import TaskExecutor


def _send_skill_editor_log(level: str, msg: str):
    """
    Send log to skill editor.
    
    Works in both desktop (IPC) and cloud (AppSync) modes.
    The cloud_logger module handles mode detection internally.
    """
    try:
        send_skill_editor_log(level, msg)
    except Exception:
        pass


class DevRunner:
    """
    Development runner for skill debugging.
    
    Provides breakpoint management and step-by-step execution
    for the skill editor.
    """
    
    def __init__(self):
        """Initialize the dev runner."""
        self.bp_manager = BreakpointManager()
        self._dev_task: Optional["ManagedTask"] = None
    
    # ==================== Breakpoint Management ====================
    
    def set_breakpoints(self, breakpoints: Optional[List[str]]) -> Dict[str, Any]:
        """
        Set breakpoints for the current dev skill run.
        
        Args:
            breakpoints: List of node names to break on.
            
        Returns:
            Dict with success flag and current breakpoints.
        """
        try:
            nodes = breakpoints or []
            if not isinstance(nodes, list):
                nodes = [str(nodes)]
            bp_list = [str(n) for n in nodes]
            
            logger.debug(f"[DevRunner] set_breakpoints called with: {bp_list}")
            self.bp_manager.set_breakpoints(bp_list)
            
            current = self.bp_manager.get_breakpoints()
            logger.info(f"[DevRunner] Breakpoints set -> now: {current}")
            
            return {"success": True, "breakpoints": current}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def clear_breakpoints(self, breakpoints: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Clear specific breakpoints, or all if none provided.
        
        Args:
            breakpoints: Optional list of breakpoints to clear.
            
        Returns:
            Dict with success flag and current breakpoints.
        """
        try:
            if breakpoints:
                to_clear = [str(n) for n in breakpoints]
                logger.debug(f"[DevRunner] clear_breakpoints called with: {to_clear}")
                self.bp_manager.clear_breakpoints(to_clear)
            else:
                logger.debug("[DevRunner] clear_breakpoints called with: ALL")
                self.bp_manager.clear_all()
            
            current = self.bp_manager.get_breakpoints()
            logger.info(f"[DevRunner] Breakpoints cleared -> now: {current}")
            
            return {"success": True, "breakpoints": current}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_breakpoints(self) -> List[str]:
        """Get current breakpoints."""
        return self.bp_manager.get_breakpoints()
    
    # ==================== Dev Task Management ====================
    
    @property
    def current_task(self) -> Optional["ManagedTask"]:
        """Get the current dev task."""
        return self._dev_task
    
    def set_dev_task(self, task: "ManagedTask"):
        """Set the current dev task."""
        self._dev_task = task
    
    def clear_dev_task(self):
        """Clear the current dev task."""
        self._dev_task = None
    
    # ==================== Dev Run Controls ====================
    
    def launch_dev_run(self, init_state: dict, dev_task: "ManagedTask") -> Dict[str, Any]:
        """Record initial dev state and delegate execution to TaskRunner."""
        try:
            log_msg = "[DevRunner][launch_dev_run] starting (delegated to TaskRunner)..."
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)

            self._dev_task = dev_task

            # Ensure task has required primitives
            self._prepare_dev_task(dev_task)

            dev_task.metadata.setdefault("state", {})
            dev_task.metadata["state"].update(init_state or {})

            return {"success": True}

        except Exception as e:
            err_msg = get_traceback(e, "ErrorLaunchDevRun")
            logger.error(err_msg)
            _send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}
    
    def _prepare_dev_task(self, task: "ManagedTask"):
        """Prepare a task for dev run."""
        try:
            task.pause_event.set()
        except Exception:
            pass
        
        # Note: Do NOT set task.status.state = TaskState.working here!
        # The guard in _submit_task_execution checks for working state to prevent
        # duplicate execution. Setting it before submission causes the guard to
        # block the task from running at all.
        
        if not hasattr(task, "queue") or task.queue is None:
            try:
                logger.info("[DevRunner] Creating queue for dev_task")
                task.queue = Queue()
            except Exception:
                pass
    
    def resume_dev_run(self) -> Dict[str, Any]:
        """
        Resume a paused dev run.
        
        Returns:
            Result dictionary.
        """
        try:
            log_msg = "resume_dev_run..."
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            
            # Get last checkpoint
            cps = getattr(self._dev_task, "checkpoint_nodes", None) or []
            if not cps:
                return {"success": False, "error": "No checkpoint to resume from"}
            
            last = cps[-1] or {}
            tag = last.get("tag") or last.get("i_tag") or ""
            checkpoint = last.get("checkpoint")
            
            if not checkpoint:
                return {"success": False, "error": "Missing checkpoint object"}
            
            # Build resume payload
            resume_payload = {"_resuming_from": tag} if tag else {}
            
            # Set flag on checkpoint state
            self._inject_resume_flag(checkpoint, tag)
            
            # Update task status
            if hasattr(self._dev_task, "status"):
                try:
                    self._dev_task.status.state = TaskState.working
                except Exception:
                    pass
            
            # Resume context: skip the current paused node once
            ctx = {"skip_bp_once": [tag]} if tag else {"skip_bp_once": []}
            
            # Get thread ID from checkpoint
            saved_cfg = self._get_resume_config(checkpoint)
            
            log_msg = f"[resume_dev_run] ctx={ctx}, resume_payload={resume_payload}"
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            # Execute resume
            from .executor import TaskExecutor
            executor = TaskExecutor(self._dev_task)
            result = executor.stream_run(
                Command(resume=resume_payload),
                checkpoint=checkpoint,
                context=ctx,
                config=saved_cfg
            )
            
            return {"success": True, "result": result}
            
        except Exception as e:
            err_msg = get_traceback(e, "ErrorResumeDevRun")
            logger.error(err_msg)
            _send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}
    
    def pause_dev_run(self) -> Dict[str, Any]:
        """
        Pause the current dev run.
        
        Returns:
            Result dictionary.
        """
        try:
            log_msg = "pause_dev_run..."
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            
            try:
                self._dev_task.pause_event.clear()
            except Exception:
                pass
            
            if hasattr(self._dev_task, "status"):
                try:
                    self._dev_task.status.state = TaskState.input_required
                except Exception:
                    pass
            
            return {"success": True}
            
        except Exception as e:
            err_msg = get_traceback(e, "ErrorPauseDevRun")
            logger.error(err_msg)
            _send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}
    
    def step_dev_run(self) -> Dict[str, Any]:
        """
        Single-step: resume from last checkpoint and pause at next node.
        
        Returns:
            Result dictionary.
        """
        try:
            if self._dev_task is None:
                return {"success": False, "error": "No dev run task"}
            
            cps = getattr(self._dev_task, "checkpoint_nodes", None) or []
            if not cps:
                return {"success": False, "error": "No checkpoint to step from"}
            
            last = cps[-1] or {}
            tag = last.get("tag") or last.get("i_tag") or ""
            checkpoint = last.get("checkpoint")
            
            if not checkpoint:
                return {"success": False, "error": "Missing checkpoint object"}
            
            # Build resume payload
            resume_payload = {"_resuming_from": tag} if tag else {}
            
            log_msg = f"step_dev_run resume tag: {tag}"
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            # Set flag on checkpoint state
            self._inject_resume_flag(checkpoint, tag)
            
            # Update task status
            if hasattr(self._dev_task, "status"):
                try:
                    self._dev_task.status.state = TaskState.working
                except Exception:
                    pass
            
            # Step context: skip current node, pause at next
            ctx = {
                "skip_bp_once": [tag] if tag else [],
                "step_once": True,
                "step_from": tag or ""
            }
            
            # Get thread ID from checkpoint
            saved_cfg = self._get_resume_config(checkpoint)
            
            log_msg = f"[step_dev_run] ctx={ctx}, resume_payload={resume_payload}"
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            # Execute step
            from .executor import TaskExecutor
            executor = TaskExecutor(self._dev_task)
            result = executor.stream_run(
                Command(resume=resume_payload),
                checkpoint=checkpoint,
                context=ctx,
                config=saved_cfg
            )
            
            return {"success": True, "result": result}
            
        except Exception as e:
            err_msg = get_traceback(e, "ErrorStepDevRun")
            logger.error(err_msg)
            _send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}
    
    def cancel_dev_run(self) -> Dict[str, Any]:
        """
        Cancel the current dev run.
        
        Returns:
            Result dictionary.
        """
        try:
            if self._dev_task is None:
                log_msg = "task already done! (_dev_task is None)"
                logger.debug(log_msg)
                _send_skill_editor_log("log", log_msg)
            else:
                log_msg = "task to be cancelled."
                logger.debug(log_msg)
                _send_skill_editor_log("log", log_msg)
                
                # Cancel the ManagedTask
                # This will:
                # 1. Set cancellation_event (for execution loops to check)
                # 2. Try to cancel the Future (if not yet started)
                # 3. Cancel asyncio Task (if applicable)
                try:
                    if hasattr(self._dev_task, "stop"):
                        self._dev_task.stop(reason="dev_stop", force=True)
                    elif hasattr(self._dev_task, "cancel"):
                        # Backward compatibility fallback
                        self._dev_task.cancel()
                        if hasattr(self._dev_task, "exit"):
                            self._dev_task.exit()
                except Exception as e:
                    logger.warning(f"[DevRunner] ⚠️ Error calling stop/cancel on ManagedTask: {e}")

                # IMPORTANT: Do NOT clear _dev_task immediately.
                # Some nodes (e.g. browser-use / LLM calls) can block for a while,
                # and execution may continue until they return to the task loop.
                # Keeping the reference allows repeated "stop" clicks to keep sending
                # cancel signals instead of incorrectly reporting "task already done".
                try:
                    fut = getattr(self._dev_task, "future", None)
                    task_obj = getattr(self._dev_task, "task", None)
                    future_done = fut.done() if fut is not None and hasattr(fut, "done") else False
                    async_done = task_obj.done() if task_obj is not None and hasattr(task_obj, "done") else False
                    if future_done or async_done:
                        self._dev_task = None
                        logger.debug("[DevRunner] Cleared dev task reference after confirmed completion")
                except Exception:
                    # Keep reference on any uncertainty; safer for repeated cancellation.
                    pass
            
            # Send status update to frontend via unified API
            try:
                from gui.ipc.api import IPCAPI
                ipc_api = IPCAPI.get_instance()
                ipc_api.update_run_stat(
                    agent_task_id="0123456789",
                    current_node="",
                    status="cancelled",
                    langgraph_state={}
                )
            except Exception as e:
                logger.debug(f"Failed to send status update via IPCAPI: {e}")
            
            return {"success": True}
            
        except Exception as e:
            err_msg = get_traceback(e, "ErrorCancelDevRun")
            logger.error(err_msg)
            _send_skill_editor_log("error", err_msg)
            return {"success": False, "error": err_msg}
    
    # ==================== Helper Methods ====================
    
    def _inject_resume_flag(self, checkpoint: Any, tag: str):
        """Inject resume flag into checkpoint values."""
        try:
            vals = getattr(checkpoint, "values", None)
            if isinstance(vals, dict) and tag:
                vals["_resuming_from"] = tag
                if not isinstance(vals.get("attributes"), dict):
                    vals["attributes"] = {}
        except Exception:
            pass
    
    def _get_resume_config(self, checkpoint: Any) -> dict:
        """Get config for resume with thread ID from checkpoint."""
        tid = None
        try:
            tid = (getattr(checkpoint, "config", {}) or {}).get("configurable", {}).get("thread_id")
        except Exception:
            pass
        
        saved_cfg = getattr(self._dev_task, "metadata", {}).get("config") or {}
        saved_cfg.setdefault("configurable", {})
        
        if tid:
            saved_cfg["configurable"]["thread_id"] = tid
        
        return saved_cfg
    
    def get_serializable_state(self, config: dict) -> dict:
        """
        Get JSON-serializable state from the current dev task.
        
        Args:
            config: Config for getting state.
            
        Returns:
            State values dict.
        """
        try:
            if self._dev_task is None:
                return {}
            
            clean_state = self._dev_task.skill.runnable.get_state(config=config)
            
            log_msg = f"get_serializable_state: {clean_state}"
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            if hasattr(clean_state, "values") and isinstance(clean_state.values, dict):
                return clean_state.values
            return {}
            
        except Exception as e:
            err_msg = get_traceback(e, "ErrorGetSerializableState")
            logger.warning(err_msg)
            _send_skill_editor_log("warning", err_msg)
            return {}
