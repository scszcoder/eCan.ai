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
from datetime import datetime
import json

from utils.logger_helper import logger_helper as logger


class AgentTaskManager(InMemoryTaskManager):
    def __init__(self, notification_sender_auth: PushNotificationSenderAuth):
        super().__init__()
        self._agent = None
        self._futures: Dict[str, asyncio.Future] = {}
        self.notification_sender_auth = notification_sender_auth

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
        future = self._futures.pop(task_id, None)
        if future and not future.done():
            print("FUTURE COMPLETED....", result)
            future.set_result(result)

    async def on_send_task(self, request: SendTaskRequest) -> SendTaskResponse:
        """Handles the 'send task' request."""
        print("RECEIVING INCOMING A2A REQUEST:", request, "to:", self._agent.card.name)
        # INCOMING
        # REQUEST: jsonrpc = '2.0'
        # id = 'f4c7470def10498d9963b2b85bd16c62'
        # method = 'tasks/send'
        # params = TaskSendParams(id='task-001X', sessionId='sess-abc', message=Message(role='user', parts=[
        #     TextPart(type='text', text='Summarize this report', metadata=None)], metadata=None),
        #                         acceptedOutputModes=['json'], pushNotification=None, historyLength=None, metadata=None)
        print("task id:", request.params.id, request.params.sessionId, request.params.metadata)
        validation_error = self._validate_request(request)
        if validation_error:
            print("VALIDATION ERROR:", validation_error)
            return SendTaskResponse(id=request.id, error=validation_error.error)
        
        if request.params.pushNotification:
            if not await self.set_push_notification_info(request.params.id, request.params.pushNotification):
                return SendTaskResponse(id=request.id, error=InvalidParamsError(message="Push notification URL is invalid"))

        await self.upsert_task(request.params)
        task = await self.update_store(
            request.params.id, TaskStatus(state=TaskState.WORKING), None
        )
        await self.send_task_notification(task)

        task_send_params: TaskSendParams = request.params
        query = self._get_user_query(task_send_params)
        try:
            task_id = request.params.id

            waiter = self.create_waiter(task_id)
            print("created waiter....", request)
            msg_js = request.params.message  # need , encoding='utf-8'?
            print("meta type:", msg_js.metadata["mtype"])
            if msg_js.metadata["mtype"] == "send_task":
                logger.info("task wait in line")
                # agent_wait_response = await self._agent.runner.task_wait_in_line(request)
                agent_wait_response = self._agent.runner.sync_task_wait_in_line(request)
            elif msg_js.metadata["mtype"] == "send_chat":
                logger.info("chat wait in line")
                # agent_wait_response = await self._agent.runner.chat_wait_in_line(request)
                agent_wait_response = self._agent.runner.sync_chat_wait_in_line(request)
            else:
                agent_wait_response = {}

            print("waiting for runner response......", agent_wait_response)
            try:
                # 2. Wait with timeout
                result = await asyncio.wait_for(waiter, timeout=3)
                print("waiter run result......", result, type(result))
                task_stat = TaskStatus(
                    state=TaskState.COMPLETED,
                )
                print("task_stat", task_stat, type(task_stat))
                task_result = Task(
                    id=str(),
                    sessionId="",
                    status=task_stat,
                    artifacts=None,
                    history=None,
                    metadata=None
                )
                server_response = SendTaskResponse(id=request.params.id, result=task_result)
                print("about to return server response", type(server_response), server_response)
                return server_response

            except asyncio.TimeoutError:
                return SendTaskResponse(
                    id=request.params.id,
                    error=InternalError(message="Timeout waiting for task result")
                )


            # Notify
            # task = self._agent.scheduler.tasks[task_id]
            # await self.send_task_notification(task)
            # return SendTaskResponse(id=request.id, result={"task_id": task_id})

            # agent_response = self._agent.invoke(query, task_send_params.sessionId)
        except Exception as e:
            logger.error(f"Error invoking agent: {e}")
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
            logger.error(f"Error in SSE stream: {e}")
            print(traceback.format_exc())
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
        return fut

    def set_result(self, task_id: str, result):
        fut = self._futures.pop(task_id, None)
        if fut and not fut.done():
            fut.set_result(result)

    def set_exception(self, task_id: str, exc: Exception):
        fut = self._futures.pop(task_id, None)
        if fut and not fut.done():
            fut.set_exception(exc)