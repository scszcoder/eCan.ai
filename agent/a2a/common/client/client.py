import httpx
from httpx_sse import connect_sse
from typing import Any, AsyncIterable
from urllib.parse import urlparse
import ipaddress
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
    def __init__(
        self,
        agent_card: AgentCard = None,
        url: str = None,
        timeout: httpx.Timeout | float | None = None,
    ):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide either agent_card or url")

        self._timeout = self._normalize_timeout(timeout)
        self._trust_env = not self._should_bypass_proxy(self.url)

    def set_recipient(self, agent_card: AgentCard = None, url: str = None):
        if agent_card:
            self.url = agent_card.url
        elif url:
            self.url = url
        else:
            raise ValueError("Must provide non empty recipient")

        self._trust_env = not self._should_bypass_proxy(self.url)

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
        with httpx.Client(timeout=None, trust_env=self._trust_env) as client:
            with connect_sse(
                client, "POST", self.url, json=request.model_dump()
            ) as event_source:
                try:
                    for sse in event_source.iter_sse():
                        yield SendTaskStreamingResponse(**json.loads(sse.data))
                except json.JSONDecodeError as e:
                    raise A2AClientJSONError(str(e)) from e
                except httpx.RequestError as e:
                    raise A2AClientHTTPError(503, str(e)) from e

    async def _send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout, trust_env=self._trust_env) as client:
            try:
                # Image generation could take time, adding timeout
                logger.debug("A2A URL:", self.url, request.model_dump())
                response = await client.post(
                    self.url, json=request.model_dump()
                )
                logger.debug("response recevied from server:", type(response), response)
                response.raise_for_status()
                logger.debug("etc response", response)
                return response.json()
            except httpx.HTTPStatusError as e:
                raise A2AClientHTTPError(e.response.status_code, str(e)) from e
            except httpx.ReadTimeout as e:
                timeout_value = getattr(self._timeout, "read", None) or getattr(
                    self._timeout, "timeout", None
                )
                logger.error(
                    f"[ASYNC] Request Timeout after {timeout_value if timeout_value is not None else 'configured'} seconds: {e}"
                )
                raise A2AClientHTTPError(504, "Request timed out") from e
            except httpx.RequestError as e:
                logger.error(f"[ASYNC] Request Error: {e}")
                raise A2AClientHTTPError(503, str(e)) from e
            except json.JSONDecodeError as e:
                raise A2AClientJSONError(str(e)) from e

    def _sync_send_request(self, request: JSONRPCRequest) -> dict[str, Any]:
        with httpx.Client(timeout=self._timeout, trust_env=self._trust_env) as client:
            try:
                # Image generation could take time, adding timeout
                logger.debug("[SYNC] A2A URL:", self.url, request.model_dump())
                response = client.post(
                    self.url, json=request.model_dump()
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
            except httpx.ReadTimeout as e:
                timeout_value = getattr(self._timeout, "read", None) or getattr(
                    self._timeout, "timeout", None
                )
                logger.error(
                    f"[SYNC] Request Timeout after {timeout_value if timeout_value is not None else 'configured'} seconds: {e}"
                )
                raise A2AClientHTTPError(504, "Request timed out") from e
            except httpx.RequestError as e:
                logger.error(f"[SYNC] Request Error: {e}")
                raise A2AClientHTTPError(503, str(e)) from e
            except json.JSONDecodeError as e:
                logger.error(f"[SYNC] JSON Decode Error: {e}")
                raise A2AClientJSONError(str(e)) from e

    @staticmethod
    def _normalize_timeout(timeout: httpx.Timeout | float | None) -> httpx.Timeout:
        if timeout is None:
            # read/write timeout should be >= EXTENDED_API_TIMEOUT for slow cloud APIs
            from config.constants import EXTENDED_API_TIMEOUT
            return httpx.Timeout(timeout=60.0, connect=10.0, read=EXTENDED_API_TIMEOUT + 10.0, write=EXTENDED_API_TIMEOUT + 10.0)
        if isinstance(timeout, (int, float)):
            return httpx.Timeout(timeout=timeout)
        if isinstance(timeout, httpx.Timeout):
            return timeout
        raise TypeError("timeout must be an httpx.Timeout instance, float, or None")

    @staticmethod
    def _should_bypass_proxy(url: str) -> bool:
        try:
            parsed = urlparse(url)
        except ValueError:
            return False

        host = parsed.hostname
        if not host:
            return False

        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback or ip.is_private or ip.is_link_local:
                return True
        except ValueError:
            # Non-IP hostnames - treat common local suffixes as bypass candidates
            local_suffixes = (".local", ".lan", ".home", ".internal")
            if host == "localhost" or host.endswith(local_suffixes):
                return True

        return False


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
