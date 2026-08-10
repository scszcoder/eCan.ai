"""
统一端点配置层 — CN/Intl 共用代码

设计原则:
  - 所有端点从 apps/{app_id}/config/auth_config.yml 读取,无硬编码
  - 单一代码路径,CN/Intl 执行逻辑完全一致,仅配置不同
  - 字段名统一: APPSYNC.GRAPHQL_ENDPOINT / APPSYNC.WS_ENDPOINT / APPSYNC.API_KEY

配置文件结构:
  apps/cn/config/auth_config.yml:
    APPSYNC:
      GRAPHQL_ENDPOINT: https://{env_id}.service.tcloudbase.com/api/graphql
      WS_ENDPOINT:      wss://{env_id}.service.tcloudbase.com/ws
      API_KEY:          ""

  apps/intl/config/auth_config.yml:
    APPSYNC:
      GRAPHQL_ENDPOINT: https://{id}.appsync-api.{region}.amazonaws.com/graphql
      WS_ENDPOINT:      (留空,自动推导)
      API_KEY:          ""

使用方式:
  from agent.cloud_api.endpoints import CloudEndpointConfig
  cfg = CloudEndpointConfig()
  http_url = cfg.graphql_endpoint        # str
  ws_url   = cfg.ws_endpoint            # str
  api_key  = cfg.api_key               # str (may be empty)
  host     = cfg.host                   # str
"""

from __future__ import annotations

import os
import ssl
import certifi
import base64
import json
import asyncio
import aiohttp
import websocket as ws_client_module
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field
from utils.logger_helper import logger_helper as logger

# Apply nest_asyncio for Python 3.11+ nested event loops
try:
    import nest_asyncio
    nest_asyncio.apply()
except ImportError:
    pass


# =============================================================================
# Dataclass
# =============================================================================

@dataclass
class CloudEndpointConfig:
    """
    统一端点配置。

    CN (ECAN_APP_ID=cn):
      - GRAPHQL_ENDPOINT: TCB GraphQL HTTP URL
      - SSE_ENDPOINT:     TCB SSE 实时推送 URL (替代旧的 WebSocket)
      - API_KEY:          TCB API Key (may be empty, uses JWT Bearer auth)
      - 认证: Bearer token via Authorization header 或 token query param

    Intl (ECAN_APP_ID=intl):
      - GRAPHQL_ENDPOINT: AWS AppSync HTTP URL
      - WS_ENDPOINT:      自动推导 (appsync-api → appsync-realtime-api)
      - API_KEY:           AWS API Key (优先,否则用 Cognito JWT)
      - 认证: Authorization: <jwt> header 或 x-api-key header
    """
    # Module-level: lazily read at first access
    _app_id: str = field(default=None, repr=False)
    _cfg: Any = field(default=None, repr=False)
    _graphql_endpoint: Optional[str] = field(default=None, repr=False)
    _ws_endpoint: Optional[str] = field(default=None, repr=False)
    _api_key: Optional[str] = field(default=None, repr=False)
    _region: Optional[str] = field(default=None, repr=False)

    @property
    def app_id(self) -> str:
        if self._app_id is None:
            object.__setattr__(self, '_app_id', os.getenv("ECAN_APP_ID", "intl"))
        return self._app_id

    @app_id.setter
    def app_id(self, value: str) -> None:
        object.__setattr__(self, '_app_id', value)

    def _ensure_cfg(self) -> None:
        """Lazily load auth config once."""
        if self._cfg is not None:
            return
        try:
            from auth.auth_config import AuthConfig
            object.__setattr__(self, '_cfg', AuthConfig)
        except Exception:
            object.__setattr__(self, '_cfg', None)

    @property
    def graphql_endpoint(self) -> str:
        """HTTP GraphQL 端点 URL。"""
        self._ensure_cfg()
        if self._graphql_endpoint:
            return self._graphql_endpoint

        if self._cfg is None:
            return ""

        try:
            raw = self._cfg.APPSYNC.GRAPHQL_ENDPOINT or ""
        except AttributeError:
            raw = ""

        self._graphql_endpoint = raw.strip()
        return self._graphql_endpoint

    @property
    def ws_endpoint(self) -> str:
        """WebSocket 实时订阅端点 URL。

        CN (TCB): 返回自建 graphql-ws 兼容 WS 服务 (wss://.../ws)
        Intl (AppSync): 自动推导 appsync-realtime-api

        The CN endpoint is fully compatible with the graphql-ws subprotocol so
        any standard client (e.g. Python `websockets` with subprotocols=['graphql-ws'])
        can connect unchanged.
        """
        self._ensure_cfg()
        if self._ws_endpoint:
            return self._ws_endpoint

        if self._cfg is None:
            return ""

        # CN (TCB): 优先显式 WS_ENDPOINT, 否则从 GRAPHQL_ENDPOINT 推导为 /ws
        if self.is_cn:
            try:
                raw = self._cfg.APPSYNC.WS_ENDPOINT or ""
            except AttributeError:
                raw = ""
            if raw.strip():
                self._ws_endpoint = raw.strip()
                return self._ws_endpoint
            graphql = self.graphql_endpoint
            if graphql:
                self._ws_endpoint = graphql.replace('/api/graphql', '/ws')
            return self._ws_endpoint

        # Intl (AppSync): 优先使用显式配置的 WS_ENDPOINT
        try:
            raw = self._cfg.APPSYNC.WS_ENDPOINT or ""
        except AttributeError:
            raw = ""
        if raw.strip():
            self._ws_endpoint = raw.strip()
            return self._ws_endpoint

        # 从 GRAPHQL_ENDPOINT 推导
        graphql = self.graphql_endpoint
        if not graphql:
            return ""

        # appsync-api → appsync-realtime-api, https → wss
        ws = graphql
        if 'appsync-api' in ws:
            ws = ws.replace('appsync-api', 'appsync-realtime-api', 1)
        if ws.startswith('https://'):
            ws = 'wss://' + ws[8:]
        self._ws_endpoint = ws

        return self._ws_endpoint

    @property
    def api_key(self) -> str:
        """API Key (可能为空字符串)。"""
        self._ensure_cfg()
        if self._api_key is not None:
            return self._api_key

        if self._cfg is None:
            self._api_key = ""
            return ""

        try:
            raw = self._cfg.APPSYNC.API_KEY or ""
        except AttributeError:
            raw = ""
        self._api_key = raw.strip()
        return self._api_key

    @property
    def host(self) -> str:
        """WebSocket Host (用于 header 认证)。"""
        parsed = urlparse(self.ws_endpoint)
        return parsed.netloc

    @property
    def region(self) -> str:
        """云区域标识。"""
        self._ensure_cfg()
        if self._region:
            return self._region

        if self._cfg is None:
            self._region = "ap-shanghai" if self.is_cn else "us-east-1"
            return self._region

        try:
            raw = self._cfg.APPSYNC.REGION or ""
        except AttributeError:
            raw = ""
        self._region = raw.strip() or ("ap-shanghai" if self.is_cn else "us-east-1")
        return self._region

    @property
    def is_cn(self) -> bool:
        """是否 CN 版本。"""
        return self.app_id == 'cn'

    # -------------------------------------------------------------------------
    # Header building
    # -------------------------------------------------------------------------

    def build_http_headers(self, token: str) -> Dict[str, str]:
        """构建 HTTP GraphQL 请求 header。"""
        headers: Dict[str, str] = {
            'Content-Type': 'application/json',
            'cache-control': 'no-cache',
        }
        if self.is_cn:
            # CN: Bearer token in Authorization header
            if token:
                headers['Authorization'] = token
        else:
            # Intl: API Key优先,否则 Bearer token
            if self.api_key:
                headers['x-api-key'] = self.api_key
            elif token:
                headers['Authorization'] = token
        return headers

    def build_ws_url(self, token: str) -> str:
        """构建带认证的 WebSocket 连接 URL。

        CN (TCB):  返回 wss://.../ws (graphql-ws 兼容)
        Intl (AppSync): header base64 编码到 query string
        """
        if self.is_cn:
            # 自建 graphql-ws 兼容 WS, token 作为 ?token= 兜底
            return _tcb_ws_url(self.ws_endpoint, token)
        else:
            # AppSync: Authorization header base64 in query string
            headers = {'host': self.host}
            if self.api_key:
                headers['x-api-key'] = self.api_key
            elif token:
                headers['Authorization'] = token
            return _appsync_ws_url(self.ws_endpoint, headers)

    # -------------------------------------------------------------------------
    # HTTP GraphQL
    # -------------------------------------------------------------------------

    def graphql_request(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        token: str = "",
    ) -> Dict[str, Any]:
        """执行 GraphQL HTTP 请求(同步)。"""
        import requests
        headers = self.build_http_headers(token)
        try:
            resp = requests.post(
                self.graphql_endpoint,
                headers=headers,
                json={'query': query, 'variables': variables or {}},
                timeout=30,
            )
            return resp.json()
        except Exception as e:
            logger.error(f"[CloudEndpoint] GraphQL request failed: {e}")
            raise

    async def graphql_request_async(
        self,
        query: str,
        variables: Optional[Dict[str, Any]] = None,
        token: str = "",
    ) -> Dict[str, Any]:
        """执行 GraphQL HTTP 请求(异步)。"""
        headers = self.build_http_headers(token)
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.post(
                    self.graphql_endpoint,
                    headers=headers,
                    json={'query': query, 'variables': variables or {}},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    return await resp.json()
        except Exception as e:
            logger.error(f"[CloudEndpoint] GraphQL async request failed: {e}")
            raise

    # -------------------------------------------------------------------------
    # WebSocket Subscription
    # -------------------------------------------------------------------------

    def subscribe(
        self,
        subscription_query: str,
        variables: Optional[Dict[str, Any]],
        token: str,
        on_message: Callable[[Dict[str, Any]], None],
        max_retries: int = 50,
    ) -> None:
        """启动 WebSocket 订阅(后台线程,同步调用)。

        Args:
            subscription_query: GraphQL subscription 字符串
            variables:          GraphQL variables
            token:             认证 token
            on_message:        收到消息时的回调函数(dict)
            max_retries:       最大重试次数
        """
        if self.is_cn:
            _tcb_subscribe(
                self.ws_endpoint,
                token,
                subscription_query,
                variables,
                on_message,
                max_retries,
            )
        else:
            _appsync_subscribe(
                self.ws_endpoint,
                self.host,
                self.api_key,
                token,
                subscription_query,
                variables,
                on_message,
                max_retries,
            )


# =============================================================================
# Private helpers
# =============================================================================

# -------------------------------------------------------------------------
# TCB WebSocket URL Builder (CN)
# -------------------------------------------------------------------------

def _tcb_ws_url(base_ws: str, token: str) -> str:
    """Build TCB WebSocket URL with token as query parameter."""
    parsed = urlparse(base_ws)
    query = dict(parse_qsl(parsed.query))
    query['token'] = token
    return urlunparse((
        parsed.scheme.replace('https', 'wss'),
        parsed.netloc,
        parsed.path,
        parsed.params,
        urlencode(query),
        parsed.fragment
    ))


def _appsync_ws_url(base_ws: str, headers: Dict[str, str]) -> str:
    """Build AppSync WebSocket URL with auth headers base64-encoded in query string."""
    # Filter out content-type (not used in WS auth)
    filtered = {k: v for k, v in headers.items() if k.lower() != 'content-type'}
    header_b64 = base64.b64encode(json.dumps(filtered).encode('utf-8')).decode('utf-8')
    return f"{base_ws}?header={header_b64}&payload=e30="


# -------------------------------------------------------------------------
# AppSync WebSocket Subscription (Intl)
# -------------------------------------------------------------------------

def _appsync_subscribe(
    ws_endpoint: str,
    host: str,
    api_key: str,
    token: str,
    subscription_query: str,
    variables: Optional[Dict[str, Any]],
    on_message: Callable[[Dict[str, Any]], None],
    max_retries: int,
) -> None:
    """Intl: Subscribe via AWS AppSync using graphql-ws protocol."""
    sub_id = f"appsync-sub-{id(on_message)}"

    headers = {'host': host}
    if api_key:
        headers['x-api-key'] = api_key
    elif token:
        headers['Authorization'] = token

    ws_url = _appsync_ws_url(ws_endpoint, headers)

    # Build subscription payload matching AppSync graphql-ws protocol
    sub_payload = json.dumps({
        'query': subscription_query,
        'variables': variables or {},
    })
    start_msg = json.dumps({
        'id': sub_id,
        'payload': {
            'data': sub_payload,
            'extensions': {'authorization': headers},
        },
        'type': 'start',
    })

    retry_count = [0]

    def _on_message(ws, msg):
        try:
            data = json.loads(msg)
        except Exception:
            return

        msg_type = data.get('type', '')
        if msg_type == 'ka':
            return

        if msg_type == 'data':
            inner = (data.get('payload') or {}).get('data') or {}
            for key, value in inner.items():
                try:
                    on_message(value)
                except Exception as e:
                    logger.debug(f"[AppSync:sub] callback error: {e}")

    def _on_open(ws):
        logger.info(f"[AppSync:sub] Connected, sending connection_init")
        ws.send(json.dumps({'type': 'connection_init'}))

    def _run():
        ws = ws_client_module.WebSocketApp(
            ws_url,
            on_message=_on_message,
            subprotocols=['graphql-ws'],
        )
        ws.on_open = _on_open

        # Send start after connection_ack (proper graphql-ws handshake)
        connection_acked = [False]
        original_on_message = _on_message

        def _on_message_with_ack(ws, msg):
            try:
                data = json.loads(msg)
            except Exception:
                return

            if data.get('type') == 'connection_ack':
                logger.info(f"[AppSync:sub] connection_ack, sending start")
                connection_acked[0] = True
                ws.send(start_msg)
                return

            original_on_message(ws, msg)

        ws.on_message = _on_message_with_ack
        ws.run_forever(
            sslopt={"ca_certs": certifi.where()},
        )

    import threading
    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


# =============================================================================
# Singleton instance
# =============================================================================

# Lazy singleton — only created when first accessed
_instance: Optional[CloudEndpointConfig] = None


def get_endpoint_config() -> CloudEndpointConfig:
    """获取全局 CloudEndpointConfig 单例。"""
    global _instance
    if _instance is None:
        _instance = CloudEndpointConfig()
    return _instance
