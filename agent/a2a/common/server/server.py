from starlette.applications import Starlette
from starlette.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.requests import Request
from agent.a2a.common.types import (
    A2ARequest,
    JSONRPCResponse,
    InvalidRequestError,
    JSONParseError,
    GetTaskRequest,
    CancelTaskRequest,
    SendTaskRequest,
    SetTaskPushNotificationRequest,
    GetTaskPushNotificationRequest,
    InternalError,
    AgentCard,
    TaskResubscriptionRequest,
    SendTaskStreamingRequest,
)
from pydantic import ValidationError
import json
from typing import AsyncIterable, Any
from agent.a2a.common.server.task_manager import TaskManager

from utils.logger_helper import logger_helper as logger



class A2AServer:
    def __init__(
        self,
        host="0.0.0.0",
        port=5000,
        endpoint="/a2a/",
        agent_card: AgentCard = None,
        task_manager: TaskManager = None,
    ):
        self.host = host
        self.port = port
        self.endpoint = endpoint
        self.task_manager = task_manager
        self.agent_card = agent_card
        self.app = Starlette()
        self.app.add_route(self.endpoint, self._process_request, methods=["POST"])
        self.app.add_route(
            "/.well-known/agent.json", self._get_agent_card, methods=["GET"]
        )
        self.app.add_route("/ping", self._health_check, methods=["GET"])

    def start(self):
        """Start A2A server in daemon thread"""
        if self.agent_card is None:
            raise ValueError("agent_card is not defined")
        if self.task_manager is None:
            raise ValueError("request_handler is not defined")
        
        import uvicorn
        import asyncio
        
        try:
            config = uvicorn.Config(
                self.app,
                host=self.host or '127.0.0.1',
                port=self.port,
                log_level="warning",
                log_config=None
            )
            server = uvicorn.Server(config)
            
            # Disable signal handlers for daemon threads
            if hasattr(server, "install_signal_handlers"):
                server.install_signal_handlers = False
            
            # Run server with dedicated event loop
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(server.serve())
            
        except Exception as e:
            logger.error(f"A2A server failed on port {self.port}: {e}")
            raise

    def _health_check(self, request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok"})

    def _get_agent_card(self, request: Request) -> JSONResponse:
        return JSONResponse(self.agent_card.model_dump(exclude_none=True))

    async def _process_request(self, request: Request):
        try:
            body = await request.json()
            json_rpc_request = A2ARequest.validate_python(body)

            if isinstance(json_rpc_request, GetTaskRequest):
                result = await self.task_manager.on_get_task(json_rpc_request)
            elif isinstance(json_rpc_request, SendTaskRequest):
                result = await self.task_manager.on_send_task(json_rpc_request)
            elif isinstance(json_rpc_request, SendTaskStreamingRequest):
                result = await self.task_manager.on_send_task_subscribe(
                    json_rpc_request
                )
            elif isinstance(json_rpc_request, CancelTaskRequest):
                result = await self.task_manager.on_cancel_task(json_rpc_request)
            elif isinstance(json_rpc_request, SetTaskPushNotificationRequest):
                result = await self.task_manager.on_set_task_push_notification(json_rpc_request)
            elif isinstance(json_rpc_request, GetTaskPushNotificationRequest):
                result = await self.task_manager.on_get_task_push_notification(json_rpc_request)
            elif isinstance(json_rpc_request, TaskResubscriptionRequest):
                result = await self.task_manager.on_resubscribe_to_task(
                    json_rpc_request
                )
            else:
                logger.warning(f"Unexpected request type: {type(json_rpc_request)}")
                raise ValueError(f"Unexpected request type: {type(request)}")
            return self._create_response(result)

        except Exception as e:
            return self._handle_exception(e)

    def _handle_exception(self, e: Exception) -> JSONResponse:
        if isinstance(e, json.decoder.JSONDecodeError):
            json_rpc_error = JSONParseError()
        elif isinstance(e, ValidationError):
            json_rpc_error = InvalidRequestError(data=json.loads(e.json()))
        else:
            logger.error(f"Unhandled exception: {e}")
            json_rpc_error = InternalError()

        response = JSONRPCResponse(id=None, error=json_rpc_error)
        return JSONResponse(response.model_dump(exclude_none=True), status_code=400)

    def _create_response(self, result: Any) -> JSONResponse | EventSourceResponse:
        if isinstance(result, AsyncIterable):

            async def event_generator(result) -> AsyncIterable[dict[str, str]]:
                async for item in result:
                    yield {"data": item.model_dump_json(exclude_none=True)}

            return EventSourceResponse(event_generator(result))
        elif isinstance(result, JSONRPCResponse):
            return JSONResponse(result.model_dump(exclude_none=True))
        else:
            logger.error(f"Unexpected result type: {type(result)}")
            raise ValueError(f"Unexpected result type: {type(result)}")

    def attach_agent(self, agent):
        self.task_manager.attach_agent(agent)