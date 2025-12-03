from typing import AsyncIterable, Dict, Any
from agent.a2a.common.types import (
    SendTaskRequest,
    TaskSendParams,
    Message,
    TaskStatus,
    Artifact,
    TextPart,
    TaskState,
    SendTaskResponse,
    InternalError,
    JSONRPCResponse,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    Task,
    TaskIdParams,
    PushNotificationConfig,
    SetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    TaskPushNotificationConfig,
    TaskNotFoundError,
    InvalidParamsError,
)
from agent.a2a.common.server.task_manager import InMemoryTaskManager
from agent.a2a.langgraph_agent.agent import ECRPAHelperAgent
from agent.a2a.common.utils.push_notification_auth import PushNotificationSenderAuth
import agent.a2a.common.server.utils as utils
from typing import Union
import asyncio
import logging
import traceback
from starlette.responses import JSONResponse
from datetime import datetime, timedelta
import json
import time

from utils.logger_helper import logger_helper as logger


class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, notification_sender_auth: PushNotificationSenderAuth):
        super().__init__()
        self._agent = None
        self._futures: Dict[str, asyncio.Future] = {}
        self.notification_sender_auth = notification_sender_auth
        # Configuration for task cleanup
        self._max_tasks = 10000  # Maximum number of tasks to keep in memory
        self._task_retention_hours = 24  # Keep completed tasks for 24 hours
        self._max_history_per_task = 1000  # Maximum history items per task
        self._cleanup_interval_seconds = 3600  # Run cleanup every hour
        self._last_cleanup_time = time.time()
        self._task_completion_times: Dict[str, float] = {}  # Track when tasks completed
        # Performance monitoring
        self._cleanup_stats = {
            'last_cleanup_duration': 0.0,
            'last_cleanup_removed': 0,
            'total_cleanups': 0
        }
        # Task timeout configuration
        self._default_task_timeout_seconds = 180  # 3 minutes default (increased from 60s)
        self._task_start_times: Dict[str, float] = {}  # Track when tasks started

    def attach_agent(self, agent):
        self._agent = agent

    async def _run_streaming_agent(self, request: SendTaskStreamingRequest):
        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)

        try:
            async for item in self._agent.stream(query, task_send_params.sessionId):
                is_task_complete = item["is_task_complete"]
                require_user_input = item["require_user_input"]
                artifact = None
                message = None
                parts = [{"type": "text", "text": item["content"]}]
                end_stream = False

                if not is_task_complete and not require_user_input:
                    task_state = TaskState.WORKING
                    message = Message(role="agent", parts=parts)
                elif require_user_input:
                    task_state = TaskState.INPUT_REQUIRED
                    message = Message(role="agent", parts=parts)
                    end_stream = True
                else:
                    task_state = TaskState.COMPLETED
                    artifact = Artifact(parts=parts, index=0, append=False)
                    end_stream = True

                task_status = TaskStatus(state=task_state, message=message)
                latest_task = await self.update_store(
                    task_send_params.id,
                    task_status,
                    None if artifact is None else [artifact],
                )
                await self.send_task_notification(latest_task)

                if artifact:
                    task_artifact_update_event = TaskArtifactUpdateEvent(
                        id=task_send_params.id, artifact=artifact
                    )
                    await self.enqueue_events_for_sse(
                        task_send_params.id, task_artifact_update_event
                    )                    
                    

                task_update_event = TaskStatusUpdateEvent(
                    id=task_send_params.id, status=task_status, final=end_stream
                )
                await self.enqueue_events_for_sse(
                    task_send_params.id, task_update_event
                )

        except Exception as e:
            logger.error(f"An error occurred while streaming the response: {e}")
            await self.enqueue_events_for_sse(
                task_send_params.id,
                InternalError(message=f"An error occurred while streaming the response: {e}")                
            )

    def _validate_request(
        self, request: Union[SendTaskRequest, SendTaskStreamingRequest]
    ) -> JSONRPCResponse | None:
        task_send_params: TaskSendParams = request.params
        if not utils.are_modalities_compatible(
            task_send_params.acceptedOutputModes, ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES
        ):
            logger.warning(
                "Unsupported output mode. Received %s, Support %s",
                task_send_params.acceptedOutputModes,
                ECRPAHelperAgent.SUPPORTED_CONTENT_TYPES,
            )
            return utils.new_incompatible_types_error(request.id)
        
        if task_send_params.pushNotification and not task_send_params.pushNotification.url:
            logger.warning("Push notification URL is missing")
            return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is missing"))
        
        return None

    def resolve_waiter(self, task_id: str, result: Any):
        """Resolve the waiter future for the given task_id. This method is idempotent - it can be called multiple times safely."""
        logger.debug(f"[A2A] resolve_waiter called for task_id={task_id}, active futures={list(self._futures.keys())}")
        future = self._futures.get(task_id, None)
        if future and not future.done():
            logger.info(f"[A2A] Waiter resolved successfully for task_id={task_id}")
            future.set_result(result)
            # Only remove the future after successfully resolving it
            self._futures.pop(task_id, None)
        elif future:
            # Future already done - this is expected if resolve_waiter was called multiple times
            logger.debug(f"[A2A] Future for task_id={task_id} already done, skipping (idempotent call)")
            # Remove the already-done future to clean up
            self._futures.pop(task_id, None)
        else:
            # No future found - this can happen if resolve_waiter was called multiple times or the task was already resolved
            logger.debug(f"[A2A] No future found for task_id={task_id}, may have been already resolved (idempotent call)")

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles the 'send task' request."""
        t_start = time.time()
        logger.info(f"[A2A] Receiving incoming request to agent: {self._agent.card.name}")
        logger.debug(f"[A2A] Request details - task_id: {request.params.id}, session_id: {request.params.sessionId}, metadata: {request.params.metadata}")
        
        validation_error = self._validate_request(request)
        if validation_error:
            logger.warning(f"[A2A] Validation error: {validation_error}")
            return SendTaskResponse(id=request.id, error=validation_error.error)
        
        if request.params.pushNotification:
            if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                return SendTaskResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid"))

        t0 = time.time()
        await self.upsert_task(request.params)
        task = await self.update_store(
            request.params.id, TaskStatus(state=TaskState.WORKING), None
        )
        await self.send_task_notification(task)
        logger.debug(f"[PERF] on_send_task - upsert+update+notify: {time.time()-t0:.3f}s")

        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            task_id = request.params.id

            waiter = self.create_waiter(task_id)
            logger.debug(f"[A2A] Created waiter for task_id: {task_id}")
            
            # Record task start time for performance monitoring
            self._task_start_times[task_id] = time.time()
            
            msg_js = request.params.message  # need , encoding='utf-8'?
            mtype = msg_js.metadata.get('mtype', 'unknown')
            logger.debug(f"[A2A] Message type: {mtype}")
            
            # Determine async_response mode:
            # 1. Check if explicitly set in metadata (highest priority)
            # 2. Default based on message type:
            #    - send_chat: async (response via new A2A request)
            #    - send_task: sync (response via waiter/HTTP response)
            # 
            # Node/skill designers can override by setting async_response in metadata
            async_response = None
            if request.params.metadata:
                async_response = request.params.metadata.get("async_response")
            
            # If not explicitly set, use default based on message type
            if async_response is None:
                if "send_chat" in mtype:
                    async_response = True  # Chat messages default to async
                else:
                    async_response = False  # Other messages default to sync
            
            logger.debug(f"[A2A] async_response={async_response} (mtype={mtype})")
            
            t1 = time.time()
            if mtype == "send_task":
                logger.info("task wait in line")
                agent_wait_response = self._agent.runner.sync_task_wait_in_line("a2a", request, async_response=async_response)
            elif "send_chat" in mtype:
                logger.info("chat wait in line")
                if mtype == "send_chat":
                    agent_wait_response = self._agent.runner.sync_task_wait_in_line("human_chat", request, async_response=async_response)
                elif mtype == "dev_send_chat":
                    logger.debug("human chat for development task......")
                    agent_wait_response = self._agent.runner.sync_task_wait_in_line("dev_human_chat", request, async_response=async_response)
                else:
                    agent_wait_response = {}
            else:
                agent_wait_response = {}
            logger.debug(f"[PERF] on_send_task - sync_task_wait_in_line: {time.time()-t1:.3f}s")

            logger.debug("[A2A] Task queued, response:", agent_wait_response)
            
            # For async mode, return immediately
            # The skill will send response back via a2a_send_chat_message_async
            if async_response:
                logger.info(f"[A2A] Async mode: task_id={task_id}, mtype={mtype}, returning immediately")
                task_stat = TaskStatus(state=TaskState.WORKING)
                task_result = Task(
                    id=str(task_id),
                    sessionId=request.params.sessionId,
                    status=task_stat,
                    artifacts=None,
                    history=None,
                    metadata=None
                )
                # Clean up waiter since we're not waiting
                self._futures.pop(task_id, None)
                self._task_start_times.pop(task_id, None)
                return SendTaskResponse(id=request.params.id, result=task_result)
            
            # If push notification is configured, return immediately and let task complete asynchronously
            if request.params.pushNotification:
                logger.info(f"[A2A] Push notification configured for task_id={task_id}, returning immediately (task will complete asynchronously)")
                # Return WORKING status immediately - task will notify via push notification when complete
                task_stat = TaskStatus(state=TaskState.WORKING)
                task_result = Task(
                    id=str(),
                    sessionId="",
                    status=task_stat,
                    artifacts=None,
                    history=None,
                    metadata=None
                )
                server_response = SendTaskResponse(id=request.params.id, result=task_result)
                logger.info(f"[A2A] Returning immediate response for task_id: {request.params.id}, status: {task_stat.state}")
                return server_response
            
            # Otherwise, wait for task completion with timeout
            # Use configurable timeout (default 5 minutes for LLM calls)
            timeout_seconds = self._default_task_timeout_seconds
            logger.debug(f"[A2A] Waiting for task completion with timeout={timeout_seconds}s")
            
            try:
                result = await asyncio.wait_for(waiter, timeout=timeout_seconds)
                
                # Calculate execution time
                execution_time = time.time() - self._task_start_times.get(task_id, time.time())
                wait_time = time.time() - t_start
                self._task_start_times.pop(task_id, None)
                
                logger.info(f"[A2A] Waiter completed successfully in {execution_time:.2f}s (total API time: {wait_time:.2f}s): {type(result)}")
                # Update store to COMPLETED so cleanup can track completion time
                task_stat = TaskStatus(state=TaskState.COMPLETED)
                await self.update_store(request.params.id, task_stat, None)
                logger.debug(f"[A2A] Task status updated in store: {task_stat.state}")
                task_result = Task(
                    id=str(),
                    sessionId="",
                    status=task_stat,
                    artifacts=None,
                    history=None,
                    metadata=None
                )
                server_response = SendTaskResponse(id=request.params.id, result=task_result)
                logger.info(f"[A2A] Returning response for task_id: {request.params.id}, status: {task_stat.state}")
                return server_response

            except asyncio.TimeoutError:
                execution_time = time.time() - self._task_start_times.get(task_id, time.time())
                logger.warning(f"[A2A] Timeout waiting for task result after {execution_time:.2f}s (timeout={timeout_seconds}s)")
                
                # Clean up tracking data to prevent memory leak
                self._task_start_times.pop(task_id, None)
                # Remove future from tracking - task continues but no one is waiting
                # resolve_waiter is idempotent and will handle the "no future found" case gracefully
                self._futures.pop(task_id, None)
                
                # Keep task running; return error to preserve API semantics
                logger.info(f"[A2A] Timeout response sent for task_id={task_id}, task continues in background")
                return SendTaskResponse(
                    id=request.params.id,
                    error=InternalError(message=f"Timeout waiting for task result after {timeout_seconds}s; task continues running")
                )


            # Notify
            # task = self._agent.scheduler.tasks[task_id]
            # await self.send_task_notification(task)
            # return SendTaskResponse(id=request.id, result={"task_id": task_id})

            # agent_response = self._agent.invoke(query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"Error invoking agent: {e}")
            # Clean up the future to prevent memory leak in case of exception
            fut = self._futures.pop(task_id, None)
            if fut and not fut.done():
                # Set exception on the future to prevent it from hanging
                try:
                    fut.set_exception(e)
                except Exception:
                    # Future might already be done, ignore
                    pass
            return SendTaskResponse(
                id=request.params.id,
                error=InternalError(message=str(e))
            )

        # notify the task requester
        return await self._process_agent_response(
            request, agent_response
        )

    async def on_send_task_subscribe(
        self, request: SendTaskStreamingRequest
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        try:
            error = self._validate_request(request)
            if error:
                return error

            await self.upsert_task(request.params)

            if request.params.pushNotification:
                if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                    return JSONRPCResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid"))


            task_id = self._agent.get_task_id_from_request(request.params)
            agent_response = await self._agent.runner.run_task(task_id)
            # asyncio.create_task(self._run_streaming_agent(request))

            task_send_params: TaskSendParams = request.params
            sse_event_queue = await self.setup_sse_consumer(task_send_params.id, False)

            async def stream():
                while True:
                    event = await sse_event_queue.get()
                    if isinstance(event, JSONRPCResponse):
                        yield SendTaskStreamingResponse(id=request.id, error=event.error)
                        break
                    yield SendTaskStreamingResponse(id=request.id, result=event)
                    if isinstance(event, TaskStatusUpdateEvent) and event.final:
                        break

            return stream()

            # return self.dequeue_events_for_sse(
            #     request.id, task_send_params.id, sse_event_queue
            # )
        except Exception as e:
            logger.error(f"[A2A] Error in SSE stream: {e}\n{traceback.format_exc()}")
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message="An error occurred while streaming the response"
                ),
            )

    async def _process_agent_response(
        self, request: SendTaskRequest, agent_response: dict
    ) -> SendTaskResponse:
        """Processes the agent's response and updates the task stores."""
        task_send_params: TaskSendParams = request.params
        task_id = task_send_params.id
        history_length = task_send_params.historyLength
        task_status = None

        parts = [{"type": "text", "text": agent_response["content"]}]
        artifact = None
        if agent_response["require_user_input"]:
            task_status = TaskStatus(
                state=TaskState.INPUT_REQUIRED,
                message=Message(role="agent", parts=parts),
            )
        else:
            task_status = TaskStatus(state=TaskState.COMPLETED)
            artifact = Artifact(parts=parts)
        task = await self.update_store(
            task_id, task_status, None if artifact is None else [artifact]
        )
        task_result = self.append_task_history(task, history_length)
        await self.send_task_notification(task)
        return SendTaskResponse(id=request.id, result=task_result)
    
    def _get_user_query(self, task_send_params: TaskSendParams) -> str:
        # params = TaskSendParams(id='task-001X', sessionId='sess-abc', message=Message(role='user', parts=[
        #     TextPart(type='text', text='Summarize this report', metadata=None)], metadata=None),
        #                         acceptedOutputModes=['json'], pushNotification=None, historyLength=None, metadata=None)
        # so in this case, it would return 'Summerize this report'
        part = task_send_params.message.parts[0]
        if not isinstance(part, TextPart):
            raise ValueError("Only text parts are supported")
        return part.text
    
    async def send_task_notification(self, task: Task):
        if not await self.has_push_notification_info(task.id):
            logger.info(f"No push notification info found for task {task.id}")
            return
        push_info = await self.get_push_notification_info(task.id)

        logger.info(f"Notifying for task {task.id} => {task.status.state}")
        await self.notification_sender_auth.send_push_notification(
            push_info.url,
            data=task.model_dump(exclude_none=True)
        )

    async def on_resubscribe_to_task(
        self, request
    ) -> AsyncIterable[SendTaskStreamingResponse] | JSONRPCResponse:
        task_id_params: TaskIdParams = request.params
        try:
            sse_event_queue = await self.setup_sse_consumer(task_id_params.id, True)
            return self.dequeue_events_for_sse(request.id, task_id_params.id, sse_event_queue)
        except Exception as e:
            logger.error(f"Error while reconnecting to SSE stream: {e}")
            return JSONRPCResponse(
                id=request.id,
                error=InternalError(
                    message=f"An error occurred while reconnecting to stream: {e}"
                ),
            )
    
    async def set_push_notification_info(self, task_id: str, push_notification_config: PushNotificationConfig):
        # Verify the ownership of notification URL by issuing a challenge request.
        is_verified = await self.notification_sender_auth.verify_push_notification_url(push_notification_config.url)
        if not is_verified:
            return False
        
        await super().set_push_notification_info(task_id, push_notification_config)
        return True

    def create_waiter(self, task_id: str) -> asyncio.Future:
        fut = asyncio.get_event_loop().create_future()
        self._futures[task_id] = fut
        # Trigger cleanup check if needed
        self._maybe_cleanup_tasks()
        return fut

    def _maybe_cleanup_tasks(self):
        """Periodically clean up old tasks to prevent memory leaks."""
        current_time = time.time()
        # Only run cleanup if enough time has passed
        if current_time - self._last_cleanup_time < self._cleanup_interval_seconds:
            return
        
        # Run cleanup in background to avoid blocking
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Schedule cleanup as a task
                asyncio.create_task(self._cleanup_tasks_async())
            else:
                # If no event loop is running, we can't schedule async cleanup
                # This should be rare, but we'll skip cleanup in this case
                logger.debug("[A2A] No running event loop for cleanup, skipping")
        except RuntimeError:
            # If no event loop exists, skip cleanup
            logger.debug("[A2A] No event loop for cleanup, skipping")
        
        self._last_cleanup_time = current_time

    async def _cleanup_tasks_async(self):
        """Clean up old and completed tasks to prevent memory leaks.
        
        Optimized to minimize lock holding time by:
        1. Quickly collecting task IDs to remove (in lock)
        2. Performing actual removal outside lock (minimal lock time)
        3. Processing history limits in batches
        """
        cleanup_start = time.time()
        try:
            current_time = time.time()
            retention_seconds = self._task_retention_hours * 3600
            tasks_to_remove = []
            tasks_for_history_trim = []
            
            # Phase 1: Quickly collect task IDs to remove (minimize lock time)
            phase1_start = time.time()
            async with self.lock:
                task_count = len(self.tasks)
                
                # 1. Collect expired completed tasks
                for task_id, task in self.tasks.items():
                    if task.status.state == TaskState.COMPLETED:
                        completion_time = self._task_completion_times.get(task_id, current_time)
                        if current_time - completion_time > retention_seconds:
                            tasks_to_remove.append(task_id)
                
                # 2. If still too many tasks, collect oldest completed tasks
                if task_count > self._max_tasks:
                    # Build list of completed tasks with completion times (single pass)
                    completed_tasks = []
                    for task_id, task in self.tasks.items():
                        if task.status.state == TaskState.COMPLETED and task_id not in tasks_to_remove:
                            completion_time = self._task_completion_times.get(task_id, 0)
                            completed_tasks.append((task_id, completion_time))
                    
                    # Sort and select oldest tasks
                    if completed_tasks:
                        completed_tasks.sort(key=lambda x: x[1])
                        excess_count = task_count - self._max_tasks
                        tasks_to_remove.extend(task_id for task_id, _ in completed_tasks[:excess_count])
                
                # 3. Collect tasks that need history trimming (outside lock)
                for task_id, task in self.tasks.items():
                    if task_id not in tasks_to_remove and task.history and len(task.history) > self._max_history_per_task:
                        tasks_for_history_trim.append(task_id)
            
            phase1_duration = time.time() - phase1_start
            
            # Phase 2: Remove tasks (minimal lock time per operation)
            phase2_start = time.time()
            if tasks_to_remove:
                async with self.lock:
                    for task_id in tasks_to_remove:
                        self.tasks.pop(task_id, None)
                        self._task_completion_times.pop(task_id, None)
                        self._task_start_times.pop(task_id, None)  # Clean up start times
                        self.push_notification_infos.pop(task_id, None)
                
                phase2_duration = time.time() - phase2_start
                logger.info(f"[A2A] Cleaned up {len(tasks_to_remove)} old tasks. Remaining: {len(self.tasks)}. "
                           f"Phase1: {phase1_duration:.3f}s, Phase2: {phase2_duration:.3f}s")
            else:
                phase2_duration = 0
            
            # Phase 3: Trim history in batches (minimize lock contention)
            phase3_start = time.time()
            if tasks_for_history_trim:
                # Process in batches to avoid long lock holds
                batch_size = 100
                trimmed_count = 0
                for i in range(0, len(tasks_for_history_trim), batch_size):
                    batch = tasks_for_history_trim[i:i + batch_size]
                    async with self.lock:
                        for task_id in batch:
                            task = self.tasks.get(task_id)
                            if task and task.history and len(task.history) > self._max_history_per_task:
                                task.history = task.history[-self._max_history_per_task:]
                                trimmed_count += 1
                
                phase3_duration = time.time() - phase3_start
                if trimmed_count > 0:
                    logger.debug(f"[A2A] Trimmed history for {trimmed_count} tasks. Phase3: {phase3_duration:.3f}s")
            else:
                phase3_duration = 0
            
            # Update stats
            total_duration = time.time() - cleanup_start
            self._cleanup_stats['last_cleanup_duration'] = total_duration
            self._cleanup_stats['last_cleanup_removed'] = len(tasks_to_remove)
            self._cleanup_stats['total_cleanups'] += 1
                    
        except Exception as e:
            logger.error(f"[A2A] Error during task cleanup: {e}")
            logger.error(traceback.format_exc())

    async def update_store(
        self, task_id: str, status: TaskStatus, artifacts: list[Artifact]
    ) -> Task:
        """Override to track task completion time for cleanup."""
        task = await super().update_store(task_id, status, artifacts)
        
        # Record completion time for cleanup
        if status.state == TaskState.COMPLETED:
            self._task_completion_times[task_id] = time.time()
            # Trigger cleanup check
            self._maybe_cleanup_tasks()
        
        return task

    def set_result(self, task_id: str, result):
        """Set result for scheduled tasks. This method is idempotent - it can be called multiple times safely."""
        logger.debug(f"[A2A] set_result called for task_id={task_id}")
        fut = self._futures.get(task_id, None)
        if fut and not fut.done():
            logger.info(f"[A2A] Result set successfully for task_id={task_id}")
            fut.set_result(result)
            # Only remove the future after successfully setting the result
            self._futures.pop(task_id, None)
        elif fut:
            # Future already done - this is expected if set_result was called multiple times
            logger.debug(f"[A2A] Future for task_id={task_id} already done in set_result, skipping (idempotent call)")
            # Remove the already-done future to clean up
            self._futures.pop(task_id, None)
        else:
            # No future found - this can happen if set_result was called multiple times or the task was already resolved
            logger.debug(f"[A2A] No future found for task_id={task_id} in set_result, may have been already resolved (idempotent call)")

    def set_exception(self, task_id: str, exc: Exception):
        """Set exception for scheduled tasks. This method is idempotent - it can be called multiple times safely."""
        logger.debug(f"[A2A] set_exception called for task_id={task_id}, exception={exc}")
        fut = self._futures.get(task_id, None)
        if fut and not fut.done():
            logger.error(f"[A2A] Exception set for task_id={task_id}: {exc}")
            fut.set_exception(exc)
            # Only remove the future after successfully setting the exception
            self._futures.pop(task_id, None)
        elif fut:
            # Future already done - this is expected if set_exception was called multiple times
            logger.debug(f"[A2A] Future for task_id={task_id} already done in set_exception, skipping (idempotent call)")
            # Remove the already-done future to clean up
            self._futures.pop(task_id, None)
        else:
            # No future found - this can happen if set_exception was called multiple times or the task was already resolved
            logger.debug(f"[A2A] No future found for task_id={task_id} in set_exception, may have been already resolved (idempotent call)")