"""
Task Executor - Execution logic for tasks.

This module handles the actual execution of tasks, including:
- Stream execution (sync and async)
- Config preparation
- State management during execution
- Interrupt handling
- IPC status updates
"""

import time
import traceback
import uuid
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from langgraph.types import Command

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from .models import ManagedTask


class TaskExecutor:
    """
    Executor for ManagedTask instances.
    
    Separates execution logic from the task data model.
    """
    
    def __init__(self, task: "ManagedTask"):
        """
        Initialize executor for a task.
        
        Args:
            task: The ManagedTask to execute.
        """
        self.task = task
    
    # ==================== Config Preparation ====================
    
    def prepare_config(self, config: Optional[dict] = None, context: Optional[dict] = None) -> Tuple[dict, dict]:
        """
        Prepare and normalize the config for stream execution.
        
        Args:
            config: Optional configuration dictionary.
            context: Optional runtime context.
            
        Returns:
            Tuple of (effective_config, context)
        """
        # Reuse a persistent config (thread_id) across runs; create and cache if missing
        effective_config = config or self.task.metadata.get("config")
        if effective_config is None:
            effective_config = {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),
                    "store": None
                }
            }
            self.task.metadata["config"] = effective_config
        
        # Ensure configurable dict exists
        effective_config.setdefault("configurable", {})
        
        # Set a higher recursion limit for workflows with loops (default is 25)
        # Each loop iteration can consume multiple steps (update, check, body nodes)
        effective_config.setdefault("recursion_limit", 200)
        
        # Create default context if not provided
        if context is None:
            context = {
                "id": str(uuid.uuid4()),
                "topic": "",
                "summary": "",
                "msg_thread_id": "",
                "tot_context": {},
                "app_context": {},
                "this_node": {"name": ""},
            }
        
        # Align config thread_id with context id
        effective_config["configurable"].setdefault("thread_id", context.get("id"))
        
        return effective_config, context
    
    def sync_state_identifiers(self, effective_config: dict, context: Optional[dict] = None):
        """
        Sync identifiers (thread_id, run_id) into task state attributes.
        
        This ensures hooks can access these IDs without touching runtime context.
        """
        try:
            cfg_thread_id = effective_config.get("configurable", {}).get("thread_id")
            if context:
                cfg_thread_id = cfg_thread_id or context.get("id")
            
            st = self.task.metadata.get("state") or {}
            attrs = st.get("attributes") or {}
            
            if "thread_id" not in attrs:
                attrs["thread_id"] = cfg_thread_id
            if "run_id" not in attrs:
                attrs["run_id"] = self.task.run_id
            
            st["attributes"] = attrs
            self.task.metadata["state"] = st
        except Exception:
            pass
    
    def normalize_form_data(self):
        """Normalize resume form data into state.metadata for downstream nodes."""
        try:
            st = self.task.metadata.get("state") or {}
            attrs = st.get("attributes") or {}
            meta = st.get("metadata") or {}
            
            # Check if already filled
            if "filled_parametric_filter" in meta:
                return
            
            # Try to extract from params.metadata.params.formData
            formData = (
                (((attrs.get("params") or {}).get("metadata") or {}).get("params") or {})
            ).get("formData")
            
            if formData:
                meta["filled_parametric_filter"] = formData
                st["metadata"] = meta
                self.task.metadata["state"] = st
                return
            
            # Fallback: check metadata.components[0].parametric_filters
            comps = meta.get("components") or []
            if isinstance(comps, list) and comps:
                pfs = comps[0].get("parametric_filters")
                if pfs:
                    meta["filled_parametric_filter"] = {"fields": pfs} if isinstance(pfs, list) else pfs
                    st["metadata"] = meta
                    self.task.metadata["state"] = st
        except Exception:
            pass
    
    # ==================== IPC Status Updates ====================
    
    def emit_run_status(self, status: str, node_name: str = "", state_values: Optional[dict] = None):
        """
        Emit run status update to GUI via IPC.
        
        Args:
            status: One of "running", "paused", "completed"
            node_name: Current node name (optional)
            state_values: LangGraph state values dict (optional)
        """
        try:
            from gui.ipc.api import IPCAPI
            ipc = IPCAPI.get_instance()
            ipc.update_run_stat(
                agent_task_id=self.task.run_id,
                current_node=node_name or "",
                status=status,
                langgraph_state=state_values or {},
                timestamp=int(time.time() * 1000)
            )
        except Exception:
            pass
    
    # ==================== State Helpers ====================
    
    def get_node_name_from_step(self, step: dict, effective_config: dict) -> str:
        """
        Extract current node name from step output or state.
        
        Args:
            step: Step output dict from stream.
            effective_config: Config for getting state.
            
        Returns:
            Node name string.
        """
        node_name = ""
        
        # Try from step metadata
        try:
            meta = step.get("__metadata__", {}) if isinstance(step, dict) else {}
            node_name = meta.get("langgraph_node") or meta.get("node") or ""
        except Exception:
            pass
        
        # Fallback: from state attributes
        if not node_name:
            try:
                st = self.task.skill.runnable.get_state(config=effective_config)
                st_js = st.values if hasattr(st, "values") else {}
                node_name = (
                    ((st_js or {}).get("attributes") or {})
                    .get("__this_node__", {})
                    .get("name") or ""
                )
            except Exception:
                pass
        
        # Final fallback: next node from state
        if not node_name:
            try:
                st = self.task.skill.runnable.get_state(config=effective_config)
                if hasattr(st, "next") and st.next:
                    node_name = st.next[0]
            except Exception:
                pass
        
        return node_name
    
    def get_state_values(self, effective_config: dict) -> dict:
        """
        Get current state values from LangGraph.
        
        Returns:
            State values dict or empty dict on error.
        """
        try:
            st = self.task.skill.runnable.get_state(config=effective_config)
            return st.values if hasattr(st, "values") else {}
        except Exception:
            return {}
    
    # ==================== Interrupt Handling ====================
    
    def handle_interrupt(self, step: dict, effective_config: dict) -> Tuple[str, Any]:
        """
        Handle interrupt in stream execution.
        
        Args:
            step: Step output containing __interrupt__.
            effective_config: Config for getting state.
            
        Returns:
            Tuple of (i_tag, checkpoint).
        """
        interrupt_obj = step["__interrupt__"][0]
        i_tag = interrupt_obj.value.get("i_tag", "")
        
        # Get checkpoint from LangGraph state
        current_checkpoint = self.task.skill.runnable.get_state(config=effective_config)
        
        # Store i_tag in checkpoint values
        try:
            current_checkpoint.values["attributes"]["i_tag"] = i_tag
        except Exception:
            pass
        
        # Add to checkpoint nodes
        self.task.add_checkpoint_node({"tag": i_tag, "checkpoint": current_checkpoint})
        
        # Emit paused status
        st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
        self.emit_run_status("paused", i_tag, st_js)
        
        return i_tag, current_checkpoint
    
    # ==================== Finalization ====================
    
    def finalize_run(self, success: bool, step: dict, current_checkpoint: Any, effective_config: dict) -> dict:
        """
        Finalize stream run and return result.
        
        Args:
            success: Whether run completed successfully.
            step: Last step output.
            current_checkpoint: Current checkpoint (may be None).
            effective_config: Config for getting state.
            
        Returns:
            Run result dict.
        """
        if not current_checkpoint:
            current_checkpoint = self.task.skill.runnable.get_state(config=effective_config)
        
        run_result = {"success": success, "step": step, "cp": current_checkpoint}
        
        # Emit completion status (only if truly completed, not paused)
        if success:
            st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
            self.emit_run_status("completed", "", st_js)
        
        return run_result
    
    # ==================== Validation ====================
    
    def validate_skill(self):
        """
        Validate that skill has a runnable.
        
        Raises:
            AttributeError: If skill has no runnable.
        """
        if not hasattr(self.task.skill, 'runnable') or self.task.skill.runnable is None:
            skill_name = self.task.skill.name if hasattr(self.task.skill, 'name') else 'UNKNOWN'
            logger.error(f"[SKILL_MISSING] Task {self.task.id} skill '{skill_name}' has runnable=None!")
            logger.error(f"[SKILL_MISSING] Skill type: {type(self.task.skill)}, Skill attributes: {dir(self.task.skill)}")
            raise AttributeError(f"Skill '{skill_name}' has no runnable")
    
    # ==================== Stream Execution ====================
    
    def stream_run(
        self,
        in_msg: Any = "",
        *,
        config: Optional[dict] = None,
        context: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run the task's skill with synchronous streaming support.
        
        Args:
            in_msg: Input message or state for the skill (can be Command for resume).
            config: Configuration dictionary for the runnable.
            context: Runtime context with step control flags.
            **kwargs: Additional arguments to pass to the runnable's stream method.
            
        Returns:
            Run result dictionary.
        """
        from agent.a2a.common.types import TaskState, Message, TextPart
        
        logger.debug(f"in_msg: {in_msg}, config: {config}, kwargs: {kwargs}")
        logger.debug(f"self.task.metadata: {self.task.metadata}")
        
        # Step 1: Prepare config and context
        effective_config, context = self.prepare_config(config, context)
        
        # Handle checkpoint kwarg
        if "checkpoint" in kwargs:
            effective_config["checkpoint"] = kwargs.pop("checkpoint")
        
        # Step 2: Sync state identifiers
        self.sync_state_identifiers(effective_config, context)
        
        # Step 3: Merge step/breakpoint control flags
        for key in ["step_once", "skip_bp_once", "step_from"]:
            if key in context:
                effective_config["configurable"][key] = context[key]
        
        # Step 4: Validate skill
        self.validate_skill()
        
        logger.debug(f"[SKILL_CHECK] Task {self.task.id} using skill: {self.task.skill.name}, runnable type: {type(self.task.skill.runnable)}")
        logger.debug(f"current langgraph run time state0: {self.task.skill.runnable.get_state(config=effective_config)}")
        
        # Step 5: Create stream generator
        if isinstance(in_msg, Command):
            logger.debug(f"effective config before resume: {effective_config}")
            agen = self.task.skill.runnable.stream(in_msg, config=effective_config, context=context, **kwargs)
        else:
            in_args = self.task.metadata.get("state", {})
            logger.debug(f"in_args: {in_args}")
            agen = self.task.skill.runnable.stream(in_args, config=effective_config, context=context, **kwargs)
        
        try:
            logger.debug(f"stream running skill: {self.task.skill.name}, {in_msg}")
            logger.debug(f"stream_run config: {effective_config}")
            logger.debug(f"current langgraph run time state2: {self.task.skill.runnable.get_state(config=effective_config)}")
            
            step = {}
            current_checkpoint = None
            
            # Step 6: Emit initial running status
            st0_js = self.get_state_values(effective_config)
            node0 = ""
            try:
                st0 = self.task.skill.runnable.get_state(config=effective_config)
                if hasattr(st0, "next") and st0.next:
                    node0 = st0.next[0]
            except Exception:
                pass
            self.emit_run_status("running", node0, st0_js)
            
            # Step 7: Process stream
            for step in agen:
                # Check for cancellation
                if self.task.cancellation_event.is_set():
                    logger.info(f"Task {self.task.name} ({self.task.run_id}) received cancellation signal. Stopping.")
                    self.task.status.state = TaskState.CANCELED
                    break
                
                # Update status message
                self.task.status.message = Message(
                    role="agent",
                    parts=[TextPart(type="text", text=str(step))]
                )
                
                # Emit running status with current node
                node_name = self.get_node_name_from_step(step, effective_config)
                st_js = self.get_state_values(effective_config)
                self.emit_run_status("running", node_name, st_js)
                
                # Check for interrupt/input required
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.task.status.state = TaskState.INPUT_REQUIRED
                    logger.debug(f"input required... {step}")
                    
                    if step.get("__interrupt__"):
                        i_tag, current_checkpoint = self.handle_interrupt(step, effective_config)
                        logger.debug(f"current checkpoint: {current_checkpoint}")
                    break
            
            # Step 8: Determine success and finalize
            if self.task.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.task.status.state = TaskState.COMPLETED
                logger.info("task completed...")
            
            run_result = self.finalize_run(success, step, current_checkpoint, effective_config)
            logger.debug(f"synced stream_run result: {run_result}")
            return run_result
        
        except Exception as e:
            ex_stat = "ErrorStreamRun:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}
        
        finally:
            if self.task.cancellation_event.is_set():
                self.task.status.state = TaskState.CANCELED
    
    async def astream_run(
        self,
        in_msg: Any = "",
        *,
        config: Optional[dict] = None,
        **kwargs
    ) -> dict:
        """
        Run the task's skill with async streaming support.
        
        Args:
            in_msg: Input message or state for the skill (can be Command for resume).
            config: Configuration dictionary for the runnable.
            **kwargs: Additional arguments to pass to the runnable's astream method.
            
        Returns:
            Run result dictionary.
        """
        from agent.a2a.common.types import TaskState, Message, TextPart
        
        # Step 1: Prepare config
        effective_config, _ = self.prepare_config(config)
        
        # Step 2: Sync state identifiers
        self.sync_state_identifiers(effective_config)
        
        # Step 3: Normalize form data for resume scenarios
        self.normalize_form_data()
        
        # Step 4: Create async stream generator
        if isinstance(in_msg, Command):
            agen = self.task.skill.runnable.astream(in_msg, config=effective_config, **kwargs)
        else:
            in_args = self.task.metadata.get("state", {})
            logger.debug(f"in_args: {in_args}")
            agen = self.task.skill.runnable.astream(in_args, config=effective_config, **kwargs)
        
        try:
            logger.debug(f"astream running skill: {self.task.skill.name}, {in_msg}")
            logger.debug(f"astream_run config: {effective_config}")
            
            step = {}
            current_checkpoint = None
            
            # Step 5: Emit initial running status
            st0_js = self.get_state_values(effective_config)
            node0 = ""
            try:
                st0 = self.task.skill.runnable.get_state(config=effective_config)
                if hasattr(st0, "next") and st0.next:
                    node0 = st0.next[0]
            except Exception:
                pass
            self.emit_run_status("running", node0, st0_js)
            
            # Step 6: Process async stream
            async for step in agen:
                logger.debug(f"async Step output: {step}")
                await self.task.pause_event.wait()
                
                # Update status message
                self.task.status.message = Message(
                    role="agent",
                    parts=[TextPart(type="text", text=str(step))]
                )
                
                # Emit running status with current node
                node_name = self.get_node_name_from_step(step, effective_config)
                st_js = self.get_state_values(effective_config)
                self.emit_run_status("running", node_name, st_js)
                
                # Check for interrupt/input required
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.task.status.state = TaskState.INPUT_REQUIRED
                    logger.debug(f"input required... {step}")
                    
                    if step.get("__interrupt__"):
                        i_tag, current_checkpoint = self.handle_interrupt(step, effective_config)
                    break
            
            # Step 7: Determine success and finalize
            if self.task.status.state == TaskState.INPUT_REQUIRED:
                success = False
            else:
                success = True
                self.task.status.state = TaskState.COMPLETED
                logger.info("task completed...")
            
            run_result = self.finalize_run(success, step, current_checkpoint, effective_config)
            logger.debug(f"astream_run result: {run_result}")
            return run_result
        
        except Exception as e:
            ex_stat = "ErrorAstreamRun:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}
        
        finally:
            if self.task.cancellation_event.is_set():
                self.task.status.state = TaskState.CANCELED
            try:
                await agen.aclose()
            except Exception:
                pass


# ==================== Convenience Functions ====================

def execute_task_stream(task: "ManagedTask", in_msg: Any = "", **kwargs) -> dict:
    """Execute a task using stream mode."""
    executor = TaskExecutor(task)
    return executor.stream_run(in_msg, **kwargs)


async def execute_task_astream(task: "ManagedTask", in_msg: Any = "", **kwargs) -> dict:
    """Execute a task using async stream mode."""
    executor = TaskExecutor(task)
    return await executor.astream_run(in_msg, **kwargs)


# ==================== Hybrid Async Execution ====================

def execute_task_hybrid(
    task: "ManagedTask",
    in_msg: Any = "",
    use_async: bool = True,
    **kwargs
) -> dict:
    """
    Execute a task with hybrid async/sync support.
    
    This function runs async execution in a new event loop within the current thread,
    with automatic fallback to sync execution if async fails.
    
    Args:
        task: The ManagedTask to execute.
        in_msg: Input message or state for the skill.
        use_async: If True, attempt async execution first. If False, use sync directly.
        **kwargs: Additional arguments to pass to the executor.
        
    Returns:
        Run result dictionary.
        
    Usage:
        # In ThreadPoolExecutor worker thread:
        result = execute_task_hybrid(task, state, use_async=True)
    """
    import asyncio
    import os
    
    # Check environment variable for async mode (can be overridden)
    env_async = os.getenv("ECAN_ASYNC_EXECUTION", "true").lower() in ("1", "true", "yes", "on")
    use_async = use_async and env_async
    
    executor = TaskExecutor(task)
    
    if not use_async:
        logger.debug("[HYBRID] Using sync execution (async disabled)")
        return executor.stream_run(in_msg, **kwargs)
    
    # Try async execution with fallback
    try:
        logger.debug("[HYBRID] Attempting async execution")
        
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                executor.astream_run(in_msg, **kwargs)
            )
            logger.debug("[HYBRID] Async execution completed successfully")
            return result
            
        finally:
            # Clean up the event loop
            try:
                # Cancel any pending tasks
                pending = asyncio.all_tasks(loop)
                for t in pending:
                    t.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                loop.close()
                
    except Exception as e:
        # Fallback to sync execution
        logger.warning(f"[HYBRID] Async execution failed, falling back to sync: {e}")
        return executor.stream_run(in_msg, **kwargs)
