"""
Task Executor - Execution logic for tasks.

This module handles the actual execution of tasks, including:
- Stream execution (sync and async)
- Config preparation
- State management during execution
- Interrupt handling
- IPC status updates
"""

import asyncio
import os
import time
import traceback
import uuid
from queue import Empty
from typing import Any, Dict, Optional, Tuple, TYPE_CHECKING

from langgraph.types import Command

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from .models import ManagedTask

# Default timeout for waiting on pending events at workflow end
DEFAULT_PENDING_EVENTS_TIMEOUT = 300  # 5 minutes

# Maximum characters for verbose log output
MAX_LOG_CHARS = 1000
DEFAULT_RUN_STATUS_UPDATES_PER_SEC = 2.0
RUN_STATUS_PER_STEP_VALUES = {
    "per_step",
    "per-step",
    "every_step",
    "every-step",
    "unlimited",
    "unthrottled",
}


def _parse_run_status_updates_per_sec(value: Any) -> Optional[float]:
    if value is None:
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC
    try:
        text = str(value).strip().lower()
    except Exception:
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC
    if not text:
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC
    if text in RUN_STATUS_PER_STEP_VALUES:
        return None
    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC
    if parsed <= 0:
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC
    return parsed


def _truncate_for_log(obj: Any, max_chars: int = MAX_LOG_CHARS) -> str:
    """Truncate object representation for logging if it exceeds max_chars."""
    obj_str = str(obj)
    if len(obj_str) > max_chars:
        return obj_str[:max_chars] + f"... (truncated, total length: {len(obj_str)} chars)"
    return obj_str


def _summarize_step_for_status(step: Any, max_chars: int = 1200) -> str:
    try:
        from utils.data_uri_sanitizer import sanitize_data_uris
        safe_step = sanitize_data_uris(step, max_string_chars=max_chars)
    except Exception:
        safe_step = step
    text = str(safe_step)
    if len(text) > max_chars:
        return text[:max_chars] + f"... (truncated, total length: {len(text)} chars)"
    return text


def _create_message(role: str, text: str) -> "Message":
    """Create an A2A Message with required message_id field."""
    from a2a.types import Message, TextPart
    try:
        text = _summarize_step_for_status(text, max_chars=1200)
    except Exception:
        text = str(text)
    return Message(
        role=role,
        parts=[TextPart(type="text", text=text)],
        message_id=str(uuid.uuid4())
    )


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
        self._run_status_updates_per_sec = _parse_run_status_updates_per_sec(
            os.getenv(
                "ECAN_RUN_STATUS_UPDATES_PER_SEC",
                self._task_run_status_setting(),
            )
        )
        self._next_run_status_emit_at = 0.0

    # ==================== Resource Cleanup ====================

    def _clear_skill_module_caches(self):
        """Clear skill module caches and checkpoints after execution to prevent memory accumulation.

        IMPORTANT: when the task is currently INTERRUPTED (input_required) we
        must NOT clear the InMemorySaver checkpoints, because the executor
        relies on them to auto-resume the graph after a pend_event interrupt.
        Clearing the saver between the initial run and the resume call drops
        the in-flight checkpoint and forces LangGraph to restart the graph
        from scratch on resume — pend_event then interrupts again without
        ever consuming the resume payload, so the chat_message is silently
        lost and the LLM body of the loop is never reached.
        """
        try:
            # 1. Clear build_node module caches
            try:
                from agent.ec_skills.build_node import _clear_module_caches
                _clear_module_caches()
                logger.debug("[TaskExecutor] Cleared skill module caches")
            except (ImportError, TypeError):
                pass

            # 2. Clear the skill's InMemorySaver checkpoints to prevent unbounded growth.
            #    InMemorySaver stores every checkpoint in a dict keyed by thread_id.
            #    Without clearing, the checkpoint dict grows indefinitely across executions.
            #    Skip when the task is parked on an interrupt so the auto-resume
            #    path can find the saved checkpoint.
            try:
                from a2a.types import TaskState as _TaskState
                _is_interrupted = bool(
                    self.task
                    and getattr(self.task, "status", None) is not None
                    and getattr(self.task.status, "state", None) == _TaskState.input_required
                )
            except Exception:
                _is_interrupted = False

            if _is_interrupted:
                logger.debug(
                    "[TaskExecutor] Skipping InMemorySaver clear: task is parked on "
                    "interrupt (input_required); checkpoints are required for auto-resume"
                )
            elif self.task and hasattr(self.task, "skill") and self.task.skill:
                skill = self.task.skill
                if hasattr(skill, "runnable") and skill.runnable:
                    try:
                        saver = getattr(skill.runnable, "checkpointer", None)
                        if saver is not None:
                            # InMemorySaver has storage (defaultdict), writes (defaultdict), blobs (defaultdict)
                            # Each can be cleared via .clear() inherited from dict
                            cleared = 0
                            for attr in ("storage", "writes", "blobs"):
                                coll = getattr(saver, attr, None)
                                if coll is not None and hasattr(coll, "clear"):
                                    cleared += len(coll) if hasattr(coll, "__len__") else 0
                                    coll.clear()
                            if cleared > 0:
                                logger.debug(f"[TaskExecutor] Cleared {cleared} checkpoint entries from InMemorySaver")
                    except Exception as _ckpt_err:
                        logger.debug(f"[TaskExecutor] Failed to clear checkpoints: {_ckpt_err}")

            # 3. Force garbage collection to reclaim Python object memory
            import gc
            collected = gc.collect(2)  # full collection
            if collected > 0:
                logger.debug(f"[TaskExecutor] GC collected {collected} objects")
        except Exception as e:
            logger.debug(f"[TaskExecutor] Failed to clear caches: {e}")

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
        
        # Always inject task identifiers into context so node_builder broadcasts
        # on the same channel_id as the executor (fixes dual-channel issue).
        context.setdefault("run_id", getattr(self.task, "run_id", "") or "")
        context.setdefault("task_id", getattr(self.task, "id", "") or "")
        context.setdefault("task_name", getattr(self.task, "name", "") or "")

        # Inject task lineage into context for nested task progress tracking
        lineage = self.task.metadata.get("lineage") if hasattr(self.task, "metadata") and isinstance(self.task.metadata, dict) else None
        if isinstance(lineage, dict) and lineage.get("correlation_id"):
            context["lineage"] = lineage
        
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

    def _task_run_status_setting(self) -> Any:
        try:
            metadata = getattr(self.task, "metadata", None)
            if isinstance(metadata, dict):
                for key in (
                    "run_status_updates_per_sec",
                    "run_status_update_rate",
                    "run_status_mode",
                ):
                    if key in metadata:
                        return metadata.get(key)
        except Exception:
            pass
        return DEFAULT_RUN_STATUS_UPDATES_PER_SEC

    def _should_emit_run_status(self, status: str, *, force: bool = False) -> bool:
        if force or str(status or "").lower() != "running":
            return True
        rate = self._run_status_updates_per_sec
        if rate is None:
            return True
        now = time.monotonic()
        if now < self._next_run_status_emit_at:
            return False
        self._next_run_status_emit_at = now + (1.0 / max(rate, 0.001))
        return True
    
    def emit_run_status(
        self,
        status: str,
        node_name: str = "",
        state_values: Optional[dict] = None,
        *,
        force: bool = False,
    ) -> bool:
        """
        Emit run status update to GUI via IPC.
        
        Args:
            status: One of "running", "paused", "completed"
            node_name: Current node name (optional)
            state_values: LangGraph state values dict (optional)
        """
        if not self._should_emit_run_status(status, force=force):
            return False
        try:
            if state_values is not None:
                try:
                    from utils.data_uri_sanitizer import sanitize_data_uris, data_uri_stats
                    stats = data_uri_stats(state_values)
                    if stats.get("count"):
                        logger.warning(
                            f"[data-uri-mitigation] executor_run_status_state_sanitized "
                            f"data_uri_count={stats.get('count')} "
                            f"data_uri_bytes~={stats.get('bytes')} "
                            f"max_string_len={stats.get('max_string_len')}"
                        )
                    state_values = sanitize_data_uris(state_values)
                except Exception:
                    pass
            from gui.ipc.api import IPCAPI
            ipc = IPCAPI.get_instance()
            ipc.update_run_stat(
                agent_task_id=self.task.run_id,
                current_node=node_name or "",
                status=status,
                langgraph_state=state_values,
                timestamp=int(time.time() * 1000)
            )
            return True
        except Exception:
            return False
    
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
        
        # Try from step metadata (cheapest path - no state fetch needed)
        try:
            meta = step.get("__metadata__", {}) if isinstance(step, dict) else {}
            node_name = meta.get("langgraph_node") or meta.get("node") or ""
        except Exception:
            pass
        
        # Fallback: single get_state() call, check both attributes and next in one shot
        if not node_name:
            try:
                st = self.task.skill.runnable.get_state(config=effective_config)
                st_js = st.values if hasattr(st, "values") else {}
                node_name = (
                    ((st_js or {}).get("attributes") or {})
                    .get("__this_node__", {})
                    .get("name") or ""
                )
                if not node_name and hasattr(st, "next") and st.next:
                    node_name = st.next[0]
            except Exception:
                pass
        
        return node_name
    
    def is_step_node_output(self, step: dict) -> bool:
        """
        Check if a step contains the final output of a completed node.
        
        A step is considered a node output if it contains keys other than
        the special metadata/control keys (__metadata__, require_user_input, etc.).
        
        Args:
            step: Step output dict from stream.
            
        Returns:
            True if step contains node output, False otherwise.
        """
        return any(
            key for key in step.keys() 
            if key not in ['__metadata__', 'require_user_input', 'await_agent', '__interrupt__']
        )
    
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
        # Forward human-facing fields from interrupt info to GUI
        int_val = interrupt_obj.value
        for _f in ("prompt_to_human", "qa_form_to_human", "notification_to_human",
                    "event_type", "timer_name", "browser_event_label", "paused_at"):
            if _f in int_val and int_val[_f]:
                st_js[_f] = int_val[_f]
        self.emit_run_status("paused", i_tag, st_js, force=True)
        
        return i_tag, current_checkpoint
    
    # ==================== Finalization ====================
    
    def finalize_run(
        self,
        success: bool,
        step: dict,
        current_checkpoint: Any,
        effective_config: dict,
        terminal_status: str = "completed",
    ) -> dict:
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
        
        # Wait for pending async events before marking complete
        if success and self.task.has_pending_events():
            logger.info(f"[EXECUTOR] Waiting for {len(self.task.get_pending_events())} pending events")
            self._wait_for_pending_events(timeout=DEFAULT_PENDING_EVENTS_TIMEOUT)
        
        run_result = {
            "success": success,
            "step": step,
            "cp": current_checkpoint,
            "terminal_status": terminal_status,
        }
        
        # Include pending event results in the run result
        if self.task.pending_events:
            run_result["pending_event_results"] = self.task.get_all_pending_event_results()
        
        # Emit terminal status for frontend observability.
        if terminal_status and terminal_status != "paused":
            st_js = current_checkpoint.values if hasattr(current_checkpoint, "values") else {}
            self.emit_run_status(terminal_status, "", st_js, force=True)
        
        return run_result
    
    def _wait_for_pending_events(self, timeout: float = DEFAULT_PENDING_EVENTS_TIMEOUT):
        """
        Wait for all pending async operations to complete or timeout.
        
        This is the "completion gate" that blocks task completion until
        all fire-and-forget async operations have resolved.
        
        Args:
            timeout: Maximum seconds to wait for all events
        """
        from .pending_events import resolve_async_operation
        
        start = time.time()
        poll_interval = 0.5
        
        while self.task.has_pending_events():
            # Check cancellation
            if self.task.cancellation_event.is_set():
                logger.info("[EXECUTOR] Task cancelled, stopping pending event wait")
                self.task.cancel_all_pending_events()
                break
            
            # Check overall timeout
            elapsed = time.time() - start
            if elapsed > timeout:
                logger.warning(f"[EXECUTOR] Pending events wait timeout after {elapsed:.1f}s")
                self.task.cleanup_expired_events()
                break
            
            # Poll queue for callback/timeout events
            try:
                event = self.task.queue.get(timeout=poll_interval)
                
                if event.get("type") == "async_callback":
                    corr_id = event.get("correlation_id")
                    result = event.get("result")
                    error = event.get("error")
                    resolve_async_operation(self.task, corr_id, result=result, error=error)
                    logger.debug(f"[EXECUTOR] Resolved callback for {corr_id}")
                    
                elif event.get("type") == "async_timeout":
                    corr_id = event.get("correlation_id")
                    resolve_async_operation(self.task, corr_id, error="timeout")
                    logger.debug(f"[EXECUTOR] Resolved timeout for {corr_id}")
                    
                else:
                    # Put non-pending-event messages back (they're for the next run)
                    self.task.queue.put(event)
                    
            except Empty:
                # No events in queue, check for expired events
                expired = self.task.cleanup_expired_events()
                if expired:
                    logger.debug(f"[EXECUTOR] Cleaned up {len(expired)} expired events")
        
        pending_count = len(self.task.get_pending_events())
        if pending_count > 0:
            logger.warning(f"[EXECUTOR] Exiting wait with {pending_count} still pending")
        else:
            logger.info("[EXECUTOR] All pending events resolved")
    
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
        from a2a.types import TaskState, Message, TextPart
        
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
        
        # Register cancellation_event in global registry so browser automation nodes can find it
        from agent.ec_tasks import cancellation_registry
        cancellation_registry.register(self.task.id, self.task.cancellation_event)
        
        logger.debug(f"[SKILL_CHECK] Task {self.task.id} using skill: {self.task.skill.name}, runnable type: {type(self.task.skill.runnable)}")
        
        if not isinstance(in_msg, Command):
            in_args = self.task.metadata.get("state", {})
            logger.debug(f"in_args: {in_args}")
            agen = self.task.skill.runnable.stream(in_args, config=effective_config, context=context, **kwargs)
        else:
            logger.debug(f"effective config before resume: {effective_config}")
            agen = self.task.skill.runnable.stream(in_msg, config=effective_config, context=context, **kwargs)
        
        try:
            logger.debug(f"stream running skill: {self.task.skill.name}, {in_msg}")
            
            step = {}
            current_checkpoint = None
            
            # Step 6: Emit initial running status (single get_state() call)
            node0 = ""
            st0_js = {}
            try:
                st0 = self.task.skill.runnable.get_state(config=effective_config)
                st0_js = st0.values if hasattr(st0, "values") else {}
                if hasattr(st0, "next") and st0.next:
                    node0 = st0.next[0]
            except Exception:
                pass
            self.emit_run_status("running", node0, st0_js)
            
            # Step 7: Process stream
            for step in agen:
                # Debug logging guarded behind level check to avoid heavy truncation work
                if getattr(getattr(logger, "logger", None), "isEnabledFor", lambda *_: False)(10):  # logging.DEBUG == 10
                    try:
                        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
                        log_step_sync = truncate_screenshot_for_logging(step)
                        log_step_str = str(log_step_sync)
                        if len(log_step_str) > 1000:
                            log_step_str = log_step_str[:1000] + "..."
                        logger.debug(f"sync Step output: {log_step_str}")
                    except Exception:
                        pass
                
                # Check for cancellation
                if self.task.cancellation_event.is_set():
                    logger.info(f"Task {self.task.name} ({self.task.run_id}) received cancellation signal. Stopping.")
                    self.task.status.state = TaskState.canceled
                    break
                
                # Guardrail: Check max steps limit
                self.task.increment_step()
                if self.task.is_max_steps_reached():
                    logger.warning(f"[GUARDRAIL] Task {self.task.name} reached max_steps={self.task.max_steps}. Stopping.")
                    self.task.status.state = TaskState.completed
                    self.task.status.message = _create_message("agent", f"Reached maximum steps limit ({self.task.max_steps})")
                    break
                
                # Guardrail: Check max consecutive failures
                if self.task.is_max_failures_reached():
                    logger.error(f"[GUARDRAIL] Task {self.task.name} reached max_failures={self.task.max_failures}. Stopping.")
                    self.task.status.state = TaskState.failed
                    self.task.status.message = _create_message("agent", f"Stopped due to {self.task.max_failures} consecutive failures")
                    break
                
                # Update status message
                self.task.status.message = _create_message("agent", str(step))
                
                # Emit running status with current node.
                # Only fetch full state when a node has produced output (cheapest update path
                # for intermediate/metadata steps).
                node_name = self.get_node_name_from_step(step, effective_config)
                
                if self.is_step_node_output(step):
                    # Node completed - send full state so GUI reflects latest results
                    st_js = self.get_state_values(effective_config)
                    self.emit_run_status("running", node_name, st_js)
                else:
                    # Intermediate metadata step - send lightweight update without
                    # overwriting the frontend's cached node state with an empty dict.
                    self.emit_run_status("running", node_name, None)
                
                # Check for interrupt/input required
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.task.status.state = TaskState.input_required
                    logger.debug(f"input required... {step}")
                    
                    if step.get("__interrupt__"):
                        i_tag, current_checkpoint = self.handle_interrupt(step, effective_config)
                    break
            
            # Step 8: Determine terminal status and finalize
            terminal_status = "completed"
            if self.task.status.state == TaskState.input_required:
                success = False
                terminal_status = "paused"
            elif self.task.status.state == TaskState.canceled:
                success = False
                terminal_status = "cancelled"
                logger.info("task cancelled...")
            elif self.task.status.state == TaskState.failed:
                success = False
                terminal_status = "failed"
                logger.info("task failed...")
            else:
                success = True
                self.task.status.state = TaskState.completed
                logger.info("task completed...")
            
            run_result = self.finalize_run(
                success,
                step,
                current_checkpoint,
                effective_config,
                terminal_status=terminal_status,
            )
            logger.debug(f"synced stream_run result: {_truncate_for_log(run_result)}")
            return run_result
        
        except Exception as e:
            ex_stat = "ErrorStreamRun:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}
        
        finally:
            cancellation_registry.unregister(self.task.id)
            if self.task.cancellation_event.is_set():
                self.task.status.state = TaskState.canceled
            self._clear_skill_module_caches()

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
        from a2a.types import TaskState, Message, TextPart
        
        # Step 1: Prepare config and context
        context_from_kwargs = kwargs.pop("context", None)
        effective_config, context = self.prepare_config(config, context_from_kwargs)
        
        # Step 2: Sync state identifiers
        self.sync_state_identifiers(effective_config, context)
        
        # Step 3: Normalize form data for resume scenarios
        self.normalize_form_data()
        
        # Register cancellation_event in global registry so browser automation nodes can find it
        from agent.ec_tasks import cancellation_registry
        cancellation_registry.register(self.task.id, self.task.cancellation_event)
        
        # Step 4: Create async stream generator
        if isinstance(in_msg, Command):
            agen = self.task.skill.runnable.astream(in_msg, config=effective_config, context=context, **kwargs)
        else:
            in_args = self.task.metadata.get("state", {})
            logger.debug(f"in_args: {in_args}")
            agen = self.task.skill.runnable.astream(in_args, config=effective_config, context=context, **kwargs)
        
        try:
            logger.debug(f"astream running skill: {self.task.skill.name}, {in_msg}")
            logger.debug(f"astream_run config: {effective_config}")
            
            step = {}
            current_checkpoint = None
            
            # Step 5: Emit initial running status (single get_state() call)
            node0 = ""
            st0_js = {}
            try:
                st0 = self.task.skill.runnable.get_state(config=effective_config)
                st0_js = st0.values if hasattr(st0, "values") else {}
                if hasattr(st0, "next") and st0.next:
                    node0 = st0.next[0]
            except Exception:
                pass
            self.emit_run_status("running", node0, st0_js)
            
            # Step 6: Process async stream
            async for step in agen:
                # Debug logging guarded behind level check to avoid heavy truncation work
                if getattr(getattr(logger, "logger", None), "isEnabledFor", lambda *_: False)(10):  # logging.DEBUG == 10
                    try:
                        from agent.ec_skills.browser_use_extension.passive_utils import truncate_screenshot_for_logging
                        log_step = truncate_screenshot_for_logging(step)
                        log_step_str = str(log_step)
                        if len(log_step_str) > 1000:
                            log_step_str = log_step_str[:1000] + "..."
                        logger.debug(f"async Step output: {log_step_str}")
                    except Exception:
                        pass
                try:
                    await asyncio.wait_for(self.task.pause_event.wait(), timeout=0.1)
                except asyncio.TimeoutError:
                    pass
                
                # Check for cancellation
                if self.task.cancellation_event.is_set():
                    logger.info(f"Task {self.task.name} ({self.task.run_id}) received cancellation signal. Stopping.")
                    self.task.status.state = TaskState.canceled
                    break
                
                # Guardrail: Check max steps limit
                self.task.increment_step()
                if self.task.is_max_steps_reached():
                    logger.warning(f"[GUARDRAIL] Task {self.task.name} reached max_steps={self.task.max_steps}. Stopping.")
                    self.task.status.state = TaskState.completed
                    self.task.status.message = _create_message("agent", f"Reached maximum steps limit ({self.task.max_steps})")
                    break
                
                # Guardrail: Check max consecutive failures
                if self.task.is_max_failures_reached():
                    logger.error(f"[GUARDRAIL] Task {self.task.name} reached max_failures={self.task.max_failures}. Stopping.")
                    self.task.status.state = TaskState.failed
                    self.task.status.message = _create_message("agent", f"Stopped due to {self.task.max_failures} consecutive failures")
                    break
                
                # Update status message
                self.task.status.message = _create_message("agent", str(step))
                
                # Emit running status with current node.
                # Only fetch full state when a node has produced output (cheapest update path
                # for intermediate/metadata steps).
                node_name = self.get_node_name_from_step(step, effective_config)
                
                if self.is_step_node_output(step):
                    # Node completed - send full state so GUI reflects latest results
                    st_js = self.get_state_values(effective_config)
                    self.emit_run_status("running", node_name, st_js)
                else:
                    # Intermediate metadata step - send lightweight update without
                    # overwriting the frontend's cached node state with an empty dict.
                    self.emit_run_status("running", node_name, None)
                
                # Check for interrupt/input required
                if step.get("require_user_input") or step.get("await_agent") or step.get("__interrupt__"):
                    self.task.status.state = TaskState.input_required
                    logger.debug(f"input required... {step}")
                    
                    if step.get("__interrupt__"):
                        i_tag, current_checkpoint = self.handle_interrupt(step, effective_config)
                    break
            
            # Step 7: Determine terminal status and finalize
            terminal_status = "completed"
            if self.task.status.state == TaskState.input_required:
                success = False
                terminal_status = "paused"
            elif self.task.status.state == TaskState.canceled:
                success = False
                terminal_status = "cancelled"
                logger.info("task cancelled...")
            elif self.task.status.state == TaskState.failed:
                success = False
                terminal_status = "failed"
                logger.info("task failed...")
            else:
                success = True
                self.task.status.state = TaskState.completed
                logger.info("task completed...")
            
            run_result = self.finalize_run(
                success,
                step,
                current_checkpoint,
                effective_config,
                terminal_status=terminal_status,
            )
            logger.debug(f"astream_run result: {run_result}")
            return run_result
        
        except Exception as e:
            ex_stat = "ErrorAstreamRun:" + traceback.format_exc() + " " + str(e)
            logger.error(f"{ex_stat}")
            return {"success": False, "Error": ex_stat}
        
        finally:
            cancellation_registry.unregister(self.task.id)
            if self.task.cancellation_event.is_set():
                self.task.status.state = TaskState.canceled
            try:
                await agen.aclose()
            except Exception:
                pass
            self._clear_skill_module_caches()


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

    import threading as _th
    _hybrid_thr = _th.current_thread().name
    _task_name = getattr(task, 'name', '?')
    _task_run_id = getattr(task, 'run_id', '?')
    logger.info(f"[HYBRID] execute_task_hybrid called: task={_task_name}, run_id={_task_run_id}, thread={_hybrid_thr}, use_async={use_async}, executor_id={id(task)}")

    executor = TaskExecutor(task)

    if not use_async:
        logger.info(f"[HYBRID] Using SYNC execution: task={_task_name}, thread={_hybrid_thr}")
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
