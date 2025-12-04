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

from agent.a2a.common.types import TaskState
from agent.ec_skills.dev_defs import BreakpointManager
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback

if TYPE_CHECKING:
    from .models import ManagedTask
    from .executor import TaskExecutor


def _get_ipc():
    """Lazy IPC instance getter to avoid initialization issues."""
    try:
        from gui.ipc.api import IPCAPI
        return IPCAPI.get_instance()
    except Exception:
        return None


def _send_skill_editor_log(level: str, msg: str):
    """Safely send log to skill editor."""
    ipc = _get_ipc()
    if ipc:
        try:
            ipc.send_skill_editor_log(level, msg)
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
        """
        Launch a development run for debugging.
        
        Args:
            init_state: Initial state for the run.
            dev_task: The task to run.
            
        Returns:
            Result dictionary.
        """
        try:
            log_msg = "launch_dev_run starting..."
            logger.info(log_msg)
            _send_skill_editor_log("log", log_msg)
            
            self._dev_task = dev_task
            
            # Ensure task is runnable
            self._prepare_dev_task(dev_task)
            
            # Execute the dev run
            from .executor import TaskExecutor
            executor = TaskExecutor(dev_task)
            
            # Set initial state
            dev_task.metadata["state"] = init_state
            
            result = executor.stream_run(init_state)
            
            logger.info(f"[DevRunner] Dev run completed: {result}")
            return {"success": True, "result": result}
            
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
        
        if hasattr(task, "status"):
            try:
                task.status.state = TaskState.WORKING
            except Exception:
                pass
        
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
                    self._dev_task.status.state = TaskState.WORKING
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
                    self._dev_task.status.state = TaskState.INPUT_REQUIRED
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
                    self._dev_task.status.state = TaskState.WORKING
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
                log_msg = "task already done!"
                logger.debug(log_msg)
                _send_skill_editor_log("log", log_msg)
                return {"success": True}
            
            try:
                log_msg = "task to be cancelled."
                logger.debug(log_msg)
                _send_skill_editor_log("log", log_msg)
                
                if hasattr(self._dev_task, "cancel"):
                    self._dev_task.cancel()
                if hasattr(self._dev_task, "exit"):
                    self._dev_task.exit()
            except Exception:
                pass
            
            self._dev_task = None
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
