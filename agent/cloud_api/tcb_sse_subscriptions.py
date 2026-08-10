"""
CN TCB SSE 订阅客户端 - 通用 SSE 实时订阅

提供与 AWS AppSync WebSocket 等效的功能：
- 自动重连
- 心跳保活
- 多 topic 订阅
"""

import asyncio
import json
import ssl
import certifi
import traceback
import threading
import time
from typing import Callable, Optional, Dict, Any, List
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import aiohttp
import websocket

from utils.logger_helper import logger_helper as logger


class TCPSSESubscription:
    """
    CN TCB SSE 订阅客户端
    
    功能等价于 AWS AppSync WebSocket 订阅:
    - 长连接保持
    - 自动重连 (指数退避)
    - 心跳/keep-alive
    - 消息路由到 topic 处理器
    """
    
    def __init__(
        self,
        *,
        sse_endpoint: str,
        auth_token: str,
        topic: str,
        target_param: str,  # e.g., "chatID", "channelId", "runId"
        target_value: str,
        on_message: Callable[[Dict[str, Any]], None],
        label: str = "TCPSSE",
        max_retries: int = 50,
        base_delay: float = 3.0,
    ):
        self._sse_endpoint = sse_endpoint
        self._auth_token = auth_token
        self._topic = topic
        self._target_param = target_param
        self._target_value = target_value
        self._on_message = on_message
        self._label = label
        self._max_retries = max_retries
        self._base_delay = base_delay
        
        self._stopped = False
        self._client: Optional[aiohttp.ClientSession] = None
        self._retry_count = 0
        self._connected = False
        
    def _build_url(self) -> str:
        """构建 SSE URL"""
        params = [
            ("topic", self._topic),
            (self._target_param, self._target_value),
        ]
        if self._auth_token:
            params.append(("token", self._auth_token))
        
        query = "&".join(f"{k}={v}" for k, v in params)
        base = self._sse_endpoint
        if "?" in base:
            return f"{base}&{query}"
        return f"{base}?{query}"
    
    def start(self) -> None:
        """启动 SSE 订阅 (在独立线程中运行)"""
        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._run_loop())
            except Exception as e:
                logger.error(f"[{self._label}] SSE thread error: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=_run, daemon=True, name=f"{self._label}-sse")
        thread.start()
        return thread
    
    async def _run_loop(self) -> None:
        """SSE 连接循环"""
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        timeout = aiohttp.ClientTimeout(total=0)
        
        while not self._stopped and self._retry_count < self._max_retries:
            try:
                url = self._build_url()
                logger.info(f"[{self._label}] Connecting to SSE: {url[:100]}")
                
                self._client = aiohttp.ClientSession()
                async with self._client.get(
                    url,
                    headers={
                        'Accept': 'text/event-stream',
                        'Cache-Control': 'no-cache',
                    },
                    timeout=timeout,
                    ssl=ssl_context,
                ) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.error(f"[{self._label}] SSE error: status={response.status} body={body[:200]}")
                        self._retry_count += 1
                        await self._sleep_backoff()
                        continue
                    
                    logger.info(f"[{self._label}] SSE connected")
                    self._connected = True
                    self._retry_count = 0
                    
                    current_event = None
                    async for line in response.content:
                        if self._stopped:
                            break
                        
                        line = line.decode('utf-8').strip()
                        if not line:
                            continue
                        
                        # SSE comment/ping
                        if line.startswith(':'):
                            if 'connected' in line.lower():
                                logger.debug(f"[{self._label}] {line}")
                            continue
                        
                        if line.startswith(': ping'):
                            continue
                        
                        # Event name
                        if line.startswith('event: '):
                            current_event = line[7:].strip()
                            continue
                        
                        # Data
                        if line.startswith('data: '):
                            if current_event == self._topic:
                                data_str = line[6:].strip()
                                try:
                                    data = json.loads(data_str)
                                    payload = data.get('payload', {})
                                    self._on_message(payload)
                                except json.JSONDecodeError:
                                    logger.warning(f"[{self._label}] Invalid JSON: {data_str[:100]}")
                            current_event = None
                            continue
                        
                        current_event = None
                        
            except asyncio.CancelledError:
                logger.info(f"[{self._label}] SSE cancelled")
                break
            except aiohttp.ClientError as e:
                logger.error(f"[{self._label}] SSE client error: {e}")
            except Exception as e:
                logger.error(f"[{self._label}] SSE error: {e}")
            finally:
                self._connected = False
                if self._client:
                    try:
                        await self._client.close()
                    except Exception:
                        pass
                    self._client = None
            
            if not self._stopped:
                self._retry_count += 1
                await self._sleep_backoff()
        
        if self._retry_count >= self._max_retries:
            logger.error(f"[{self._label}] Max retries ({self._max_retries}) reached")
    
    async def _sleep_backoff(self) -> None:
        """指数退避睡眠"""
        delay = min(self._base_delay * (2 ** (self._retry_count - 1)), 60)
        logger.info(f"[{self._label}] Retrying in {delay:.1f}s (attempt {self._retry_count})")
        await asyncio.sleep(delay)
    
    def stop(self) -> None:
        """停止订阅"""
        self._stopped = True
        if self._client:
            try:
                # 在同步上下文中无法直接 await，创建一个新事件循环来关闭
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._client.close())
                loop.close()
            except Exception:
                pass
            self._client = None
        logger.info(f"[{self._label}] Stopped")


# =============================================================================
# 便捷订阅函数 (与 AppSync 版本 API 兼容)
# =============================================================================

def subscribe_wan_chat_sse(
    chat_id: str,
    auth_token: str,
    ws_url: str,
    on_message_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅 WAN 聊天消息 (SSE 版本)
    
    对应 AppSync: onMessageReceived(chatID: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onMessageReceived",
        target_param="chatID",
        target_value=chat_id,
        on_message=on_message_callback,
        label="WanChat",
    )
    
    thread = client.start()
    return client, thread


def subscribe_a2a_chat_sse(
    channel_id: str,
    auth_token: str,
    ws_url: str,
    on_message_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅 A2A 聊天消息 (SSE 版本)
    
    对应 AppSync: onA2AMessageReceived(channelId: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onA2AMessageReceived",
        target_param="channelId",
        target_value=channel_id,
        on_message=on_message_callback,
        label="A2AChat",
    )
    
    thread = client.start()
    return client, thread


def subscribe_cloud_llm_task_sse(
    acct_site_id: str,
    auth_token: str,
    ws_url: str,
) -> tuple:
    """
    订阅云端 LLM 任务完成 (SSE 版本)
    
    对应 AppSync: onLongLLMTaskComplete(acctSiteID: String!)
    """
    from agent.cloud_api.cloud_api import handle_cloud_llm_result
    
    def on_message(payload):
        logger.debug(f"[CloudLLMTask:SSE] Received: {json.dumps(payload)[:200]}")
        handle_cloud_llm_result(payload)
    
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onLongLLMTaskComplete",
        target_param="acctSiteID",
        target_value=acct_site_id,
        on_message=on_message,
        label="CloudLLMTask",
    )
    
    thread = client.start()
    return client, thread


def subscribe_account_notifications_sse(
    owner: str,
    auth_token: str,
    ws_url: str,
    on_notification_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅账户通知 (SSE 版本)
    
    对应 AppSync: onAccountNotification(owner: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onAccountNotification",
        target_param="owner",
        target_value=owner,
        on_message=on_notification_callback,
        label="AccountNotification",
    )
    
    thread = client.start()
    return client, thread


def subscribe_scene_complete_sse(
    acct_site_id: str,
    auth_token: str,
    ws_url: str,
    on_scene_complete_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅场景完成事件 (SSE 版本)
    
    对应 AppSync: onSceneComplete(acctSiteID: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onSceneComplete",
        target_param="acctSiteID",
        target_value=acct_site_id,
        on_message=on_scene_complete_callback,
        label="SceneComplete",
    )
    
    thread = client.start()
    return client, thread


def subscribe_story_updates_sse(
    acct_site_id: str,
    auth_token: str,
    ws_url: str,
    on_story_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅故事更新 (SSE 版本)
    
    对应 AppSync: onStoryUpdate(acctSiteID: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onStoryUpdate",
        target_param="acctSiteID",
        target_value=acct_site_id,
        on_message=on_story_callback,
        label="StoryUpdate",
    )
    
    thread = client.start()
    return client, thread


def subscribe_agent_scene_events_sse(
    acct_site_id: str,
    auth_token: str,
    ws_url: str,
    on_scene_callback: Callable[[Dict[str, Any]], None],
    agent_id_filter: str = None,
) -> tuple:
    """
    订阅 Agent 场景事件 (SSE 版本)
    
    对应 AppSync: onAgentSceneEvent(acctSiteID: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    def filtered_callback(payload):
        if agent_id_filter:
            agent_id = payload.get('agentID', '')
            if agent_id_filter != agent_id:
                return
        on_scene_callback(payload)
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onAgentSceneEvent",
        target_param="acctSiteID",
        target_value=acct_site_id,
        on_message=filtered_callback,
        label="AgentSceneEvent",
    )
    
    thread = client.start()
    return client, thread


def subscribe_puzzle_results_sse(
    auth_token: str,
    ws_url: str,
    on_puzzle_result_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅谜题结果 (SSE 版本，广播 topic)
    
    对应 AppSync: onPuzzleResultReceived (无参数，广播)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onPuzzleResultReceived",
        target_param="pzid",  # 会自动使用 __global__
        target_value="*",
        on_message=on_puzzle_result_callback,
        label="PuzzleResult",
    )
    
    thread = client.start()
    return client, thread


def subscribe_task_status_sse(
    run_id: str,
    auth_token: str,
    ws_url: str,
    on_status_callback: Callable[[Dict[str, Any]], None],
) -> tuple:
    """
    订阅任务状态更新 (SSE 版本)
    
    对应 AppSync: onTaskStatus(runID: String!)
    """
    from agent.cloud_api.endpoints import get_endpoint_config
    cfg = get_endpoint_config()
    sse_endpoint = cfg.sse_endpoint
    
    client = TCPSSESubscription(
        sse_endpoint=sse_endpoint,
        auth_token=auth_token,
        topic="onTaskStatus",
        target_param="runID",
        target_value=run_id,
        on_message=on_status_callback,
        label="TaskStatus",
    )
    
    thread = client.start()
    return client, thread
