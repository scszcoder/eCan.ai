"""
A2A Task Executor - Adapter between a2a-sdk and ec_tasks.

This module provides a thin adapter layer that:
1. Implements the a2a-sdk AgentExecutor interface
2. Delegates execution to the existing TaskRunner
3. Bridges a2a EventQueue with existing waiter/future pattern
"""

import asyncio
import time
import traceback
from typing import Any, Dict, Optional, TYPE_CHECKING

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import (
    InvalidParamsError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_agent_text_message, new_task
from a2a.utils.errors import ServerError

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent


# Supported content types for this executor
SUPPORTED_CONTENT_TYPES = ["text", "text/plain", "json", "file"]


class A2ATaskExecutor(AgentExecutor):
    """
    Adapter that bridges a2a-sdk's AgentExecutor interface with ec_tasks.
    
    This executor:
    - Receives requests from DefaultRequestHandler
    - Converts them to the format expected by TaskRunner
    - Delegates to TaskRunner.sync_task_wait_in_line()
    - Waits for completion using the existing waiter/future pattern
    - Reports results back via a2a EventQueue
    """
    
    def __init__(self, agent: "EC_Agent" = None):
        """
        Initialize the executor.
        
        Args:
            agent: The EC_Agent instance (can be attached later via attach_agent)
        """
        self._agent = agent
        self._futures: Dict[str, asyncio.Future] = {}
        
        # Task timeout configuration
        self._default_task_timeout_seconds = 180  # 3 minutes default
        self._task_start_times: Dict[str, float] = {}
    
    def attach_agent(self, agent: "EC_Agent"):
        """Attach an agent to this executor."""
        self._agent = agent
    
    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Execute the agent's logic for a given request context.
        
        This method:
        1. Validates the request
        2. Creates/updates task in event queue
        3. Routes to TaskRunner based on message type
        4. Waits for completion or handles async response
        5. Reports result via TaskUpdater
        
        Args:
            context: The request context containing message, task_id, etc.
            event_queue: The queue to publish events to.
        """
        if self._agent is None:
            raise ServerError(error=InvalidParamsError(message="Agent not attached"))
        
        t_start = time.time()
        logger.info(f"[A2A] Receiving incoming request to agent: {self._agent.card.name}")
        
        # Get or create task
        task = context.current_task
        if not task:
            task = new_task(context.message)
            await event_queue.enqueue_event(task)
        
        task_id = task.id
        context_id = task.context_id
        
        # Create TaskUpdater for status updates
        updater = TaskUpdater(event_queue, task_id, context_id)
        
        # Update status to working
        await updater.update_status(TaskState.working)
        
        try:
            # Extract message type from metadata
            mtype = "unknown"
            if context.message and context.message.metadata:
                mtype = context.message.metadata.get("mtype", "unknown")
            
            logger.debug(f"[A2A] Message type: {mtype}, task_id: {task_id}")
            
            # Determine async_response mode
            async_response = self._determine_async_response(context, mtype)
            
            # Build a request-like object for TaskRunner compatibility
            request = self._build_request_object(context, task_id)
            
            # Record task start time
            self._task_start_times[task_id] = time.time()
            
            # Route to TaskRunner based on message type
            if mtype == "send_task":
                logger.info("[A2A] Task wait in line")
                self._agent.runner.sync_task_wait_in_line(
                    "a2a", request, async_response=async_response
                )
            elif "send_chat" in mtype:
                logger.info("[A2A] Chat wait in line")
                if mtype == "send_chat":
                    self._agent.runner.sync_task_wait_in_line(
                        "human_chat", request, async_response=async_response
                    )
                elif mtype == "dev_send_chat":
                    logger.debug("[A2A] Human chat for development task")
                    self._agent.runner.sync_task_wait_in_line(
                        "dev_human_chat", request, async_response=async_response
                    )
            else:
                logger.warning(f"[A2A] Unknown message type: {mtype}")
            
            # For async mode, return immediately (response via separate A2A request)
            if async_response:
                logger.info(f"[A2A] Async mode: task_id={task_id}, returning immediately")
                # Task continues in background, no completion event here
                return
            
            # For sync mode, wait for completion
            waiter = self._create_waiter(task_id)
            timeout_seconds = self._default_task_timeout_seconds
            
            try:
                result = await asyncio.wait_for(waiter, timeout=timeout_seconds)
                
                execution_time = time.time() - self._task_start_times.get(task_id, time.time())
                self._task_start_times.pop(task_id, None)
                
                logger.info(f"[A2A] Task completed in {execution_time:.2f}s")
                
                # Extract result content
                result_text = self._extract_result_text(result)
                
                # Add artifact and complete
                await updater.add_artifact(
                    [Part(root=TextPart(text=result_text))],
                    name="result",
                )
                await updater.complete()
                
            except asyncio.TimeoutError:
                execution_time = time.time() - self._task_start_times.get(task_id, time.time())
                logger.warning(f"[A2A] Timeout after {execution_time:.2f}s")
                
                # Clean up
                self._task_start_times.pop(task_id, None)
                self._futures.pop(task_id, None)
                
                # Report failure
                await updater.update_status(
                    TaskState.failed,
                    new_agent_text_message(
                        f"Timeout after {timeout_seconds}s",
                        context_id,
                        task_id,
                    ),
                    final=True,
                )
                
        except Exception as e:
            logger.error(f"[A2A] Error executing task: {e}")
            logger.error(traceback.format_exc())
            
            # Clean up
            self._futures.pop(task_id, None)
            self._task_start_times.pop(task_id, None)
            
            # Report failure
            await updater.update_status(
                TaskState.failed,
                new_agent_text_message(str(e), context_id, task_id),
                final=True,
            )
    
    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue,
    ) -> None:
        """
        Request the agent to cancel an ongoing task.
        
        Args:
            context: The request context containing the task ID to cancel.
            event_queue: The queue to publish the cancellation status update to.
        """
        task_id = context.task_id
        
        if task_id:
            # Cancel the waiter if exists
            future = self._futures.pop(task_id, None)
            if future and not future.done():
                future.cancel()
            
            # Try to cancel via TaskRunner
            if self._agent and self._agent.runner:
                try:
                    await self._agent.runner.cancel_task(task_id)
                except Exception as e:
                    logger.warning(f"[A2A] Failed to cancel task {task_id}: {e}")
            
            # Report cancellation
            updater = TaskUpdater(
                event_queue,
                task_id,
                context.context_id or task_id,
            )
            await updater.update_status(TaskState.canceled, final=True)
        else:
            raise ServerError(error=UnsupportedOperationError())
    
    # ==================== Waiter/Future Pattern ====================
    
    def _create_waiter(self, task_id: str) -> asyncio.Future:
        """Create a waiter future for sync response."""
        loop = asyncio.get_event_loop()
        fut = loop.create_future()
        self._futures[task_id] = fut
        return fut
    
    def resolve_waiter(self, task_id: str, result: Any):
        """
        Resolve the waiter future for the given task_id.
        
        This method is called by TaskRunner when execution completes.
        Idempotent - can be called multiple times safely.
        """
        logger.debug(f"[A2A] resolve_waiter called for task_id={task_id}")
        future = self._futures.get(task_id)
        if future and not future.done():
            logger.info(f"[A2A] Waiter resolved for task_id={task_id}")
            future.set_result(result)
            self._futures.pop(task_id, None)
        elif future:
            logger.debug(f"[A2A] Future already done for task_id={task_id}")
            self._futures.pop(task_id, None)
        else:
            logger.debug(f"[A2A] No future found for task_id={task_id}")
    
    def set_result(self, task_id: str, result: Any):
        """Alias for resolve_waiter for backward compatibility."""
        self.resolve_waiter(task_id, result)
    
    def set_exception(self, task_id: str, exc: Exception):
        """
        Set exception for a task.
        
        Idempotent - can be called multiple times safely.
        """
        logger.debug(f"[A2A] set_exception called for task_id={task_id}")
        future = self._futures.get(task_id)
        if future and not future.done():
            logger.error(f"[A2A] Exception set for task_id={task_id}: {exc}")
            future.set_exception(exc)
            self._futures.pop(task_id, None)
        elif future:
            logger.debug(f"[A2A] Future already done for task_id={task_id}")
            self._futures.pop(task_id, None)
    
    # ==================== Helper Methods ====================
    
    def _determine_async_response(self, context: RequestContext, mtype: str) -> bool:
        """
        Determine if response should be async.
        
        Priority:
        1. Explicit metadata setting
        2. Default based on message type (chat=async, task=sync)
        """
        async_response = None
        
        # Check explicit metadata
        if context.params and hasattr(context.params, 'metadata') and context.params.metadata:
            async_response = context.params.metadata.get("async_response")
        
        # Default based on message type
        if async_response is None:
            if "send_chat" in mtype:
                async_response = True  # Chat messages default to async
            else:
                async_response = False  # Other messages default to sync
        
        logger.debug(f"[A2A] async_response={async_response} (mtype={mtype})")
        return async_response
    
    def _build_request_object(self, context: RequestContext, task_id: str) -> Any:
        """
        Build a request-like object compatible with TaskRunner.
        
        Creates a simple object that mimics the old SendTaskRequest structure.
        """
        class RequestParams:
            def __init__(self, ctx: RequestContext, tid: str):
                self.id = tid
                self.sessionId = ctx.context_id or tid
                self.message = ctx.message
                self.metadata = ctx.params.metadata if ctx.params else {}
                self.acceptedOutputModes = SUPPORTED_CONTENT_TYPES
                self.pushNotification = None
                self.historyLength = None
        
        class Request:
            def __init__(self, ctx: RequestContext, tid: str):
                self.id = tid
                self.params = RequestParams(ctx, tid)
        
        return Request(context, task_id)
    
    def _extract_result_text(self, result: Any) -> str:
        """Extract text content from execution result."""
        if result is None:
            return "Task completed"
        
        if isinstance(result, str):
            return result
        
        if isinstance(result, dict):
            # Try common result patterns
            if "content" in result:
                return str(result["content"])
            if "text" in result:
                return str(result["text"])
            if "message" in result:
                return str(result["message"])
            if "step" in result:
                step = result["step"]
                if isinstance(step, dict) and "content" in step:
                    return str(step["content"])
            # Fallback to string representation
            return str(result)
        
        return str(result)
