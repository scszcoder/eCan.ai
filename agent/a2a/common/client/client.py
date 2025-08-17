import httpx
from httpx_sse import connect_sse
from typing import Any, AsyncIterable
from agent.a2a.common.types import (
    AgentCard,
    GetTaskRequest,
    SendTaskRequest,
    SendTaskResponse,
    JSONRPCRequest,
    GetTaskResponse,
    CancelTaskResponse,
    CancelTaskRequest,
    SetTaskPushNotificationRequest,
    SetTaskPushNotificationResponse,
    GetTaskPushNotificationRequest,
    GetTaskPushNotificationResponse,
    A2AClientHTTPError,
    A2AClientJSONError,
    SendTaskStreamingRequest,
    SendTaskStreamingResponse,
)
import json
from utils.logger_helper import logger_helper as logger


class A2AClient:
    def __init__(self, agent_card: AgentCard = None, url: str = None):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide either agent_card or url")

    def set_recipient(self, agent_card: AgentCard = None, url: str = None):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide non empty recipient")

    async def send_task(self, payload: dict[str, Any]) -> SendTaskResponse:
        request = SendTaskRequest(params=payload)
        return SendTaskResponse(**await self._send_request(request))

    def sync_send_task(self, payload: dict[str, Any]) -> SendTaskResponse:
        request = SendTaskRequest(params=payload)
        return SendTaskResponse(**self._sync_send_request(request))

    async def send_task_streaming(
        self, payload: dict[str, Any]
    ) -> AsyncIterable[SendTaskStreamingResponse]:
        request = SendTaskStreamingRequest(params=payload)
        with httpx.Client(timeout=None) as client:
            with connect_sse(
                client, "POST", self.url, json=request.model_dump()
            ) as event_source:
                try:
                    for sse in event_source.iter_sse():
                        yield SendTaskStreamingResponse(**json.loads(sse.data))
                except json.JSONDecodeError as e:
                    raise A2AClientJSONError(str(e)) from e
                except httpx.RequestError as e:
                    raise A2AClientHTTPError(400, str(e)) from e

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            try:
                # Image generation could take time, adding timeout
                logger.debug("A2A URL:", self.url, request.model_dump())
                response = await client.post(
                    self.url, json=request.model_dump(), timeout=30
                )
                logger.debug("response recevied from server:", type(response), response)
                response.raise_for_status()
                logger.debug("etc response", response)
                return response.json()
            except httpx.HTTPStatusError as e:
                raise A2AClientHTTPError(e.response.status_code, str(e)) from e
            except json.JSONDecodeError as e:
                raise A2AClientJSONError(str(e)) from e

    def _sync_send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        with httpx.Client() as client:
            try:
                # Image generation could take time, adding timeout
                logger.debug("[SYNC] A2A URL:", self.url, request.model_dump())
                response = client.post(
                    self.url, json=request.model_dump(), timeout=30
                )
                logger.debug("[SYNC] response received from server:", type(response), response)
                
                # 检查响应状态码
                if response.status_code != 200:
                    logger.error(f"[SYNC] HTTP {response.status_code}: {response.text}")
                    raise A2AClientHTTPError(response.status_code, f"HTTP {response.status_code}: {response.text}")
                
                response.raise_for_status()
                logger.debug("[SYNC] response", response)
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"[SYNC] HTTP Status Error: {e.response.status_code} - {e.response.text}")
                raise A2AClientHTTPError(e.response.status_code, str(e)) from e
            except httpx.RequestError as e:
                logger.error(f"[SYNC] Request Error: {e}")
                raise A2AClientHTTPError(400, str(e)) from e
            except json.JSONDecodeError as e:
                logger.error(f"[SYNC] JSON Decode Error: {e}")
                raise A2AClientJSONError(str(e)) from e


    async def get_task(self, payload: dict[str, Any]) -> GetTaskResponse:
        request = GetTaskRequest(params=payload)
        return GetTaskResponse(**await self._send_request(request))

    async def cancel_task(self, payload: dict[str, Any]) -> CancelTaskResponse:
        request = CancelTaskRequest(params=payload)
        return CancelTaskResponse(**await self._send_request(request))

    async def set_task_callback(
        self, payload: dict[str, Any]
    ) -> SetTaskPushNotificationResponse:
        request = SetTaskPushNotificationRequest(params=payload)
        return SetTaskPushNotificationResponse(**await self._send_request(request))

    async def get_task_callback(
        self, payload: dict[str, Any]
    ) -> GetTaskPushNotificationResponse:
        request = GetTaskPushNotificationRequest(params=payload)
        return GetTaskPushNotificationResponse(**await self._send_request(request))
