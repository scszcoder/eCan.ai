import threading
import asyncio
import sys
import os
import traceback
import uuid
import json
import socket
import time
import sniffio
from typing import Optional
from starlette.applications import Starlette
import typing

from utils.logger_helper import logger_helper as logger
from utils.gui_dispatch import run_on_main_thread
from utils.app_env import get_app_id, is_cn as _is_cn

if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow

# ==================== Log Filter Configuration ====================
# 配置需要屏蔽的日志类型，减少日志噪音
LOG_FILTER_CONFIG = {
    # 包含这些关键字的消息类型会被屏蔽
    'contains': [
        'queryStream',      # 所有查询流相关消息（chunk, done, start等）
        'agentStream',      # Agent流式消息
        'skill_editor_log', # Skill编辑器日志，广播频繁且无意义
    ],
    # 以这些后缀结尾的消息类型会被屏蔽
    'endswith': [
        '.chunk',           # 所有chunk消息
        'Stream.chunk',     # 流式chunk消息
    ],
    # 完全匹配的消息类型会被屏蔽
    'exact': [
        # 'some.exact.type',  # 示例：精确匹配
    ]
}

def should_filter_log(msg_type: str) -> bool:
    """
    检查消息类型是否应该被过滤（屏蔽日志）
    
    Args:
        msg_type: 消息类型字符串
        
    Returns:
        True 表示应该屏蔽日志，False 表示应该记录日志
    """
    # 检查精确匹配
    if msg_type in LOG_FILTER_CONFIG['exact']:
        return True
    
    # 检查包含关键字
    for keyword in LOG_FILTER_CONFIG['contains']:
        if keyword in msg_type:
            return True
    
    # 检查后缀匹配
    for suffix in LOG_FILTER_CONFIG['endswith']:
        if msg_type.endswith(suffix):
            return True
    
    return False

from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route, Mount, WebSocketRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocket, WebSocketDisconnect
from starlette.requests import Request
import uvicorn

from agent.mcp.server.server import (
        handle_sse, sse_handle_messages, meca_mcp_server,
        meca_sse, meca_streamable_http, handle_streamable_http,
        session_manager, set_server_main_win
    )

# ==================== Environment Detection and Conditional Imports ====================

class MCPServerConfig:
    """Manages environment configuration and safely imports modules."""

    def __init__(self):
        self.is_frozen = getattr(sys, 'frozen', False)
        self.is_development = not self.is_frozen

        try:
            self.handle_sse = handle_sse
            self.sse_handle_messages = sse_handle_messages
            self.meca_mcp_server = meca_mcp_server
            self.meca_sse = meca_sse
            self.meca_streamable_http = meca_streamable_http
            self.handle_streamable_http = handle_streamable_http
            self.session_manager = session_manager
            self.set_server_main_win = set_server_main_win
            logger.info("✅ MCP modules imported successfully")
        except ImportError as e:
            logger.error(f"❌ Failed to import MCP modules: {e}. MCP features will be disabled.")

    def has_mcp_support(self):
        """Checks if essential MCP functionality is supported."""
        return self.session_manager is not None and self.handle_sse is not None

# Create a global instance for MCP server configuration and modules
mcp_server_config = MCPServerConfig()
response_dict = {}
IMAGE_FOLDER = os.path.abspath("run_images")  # Ensure this is your intended path
base_dir = getattr(sys, '_MEIPASS', os.getcwd())


# ==================== Skill Editor WebSocket Manager ====================
class AppWebSocketManager:
    """Manages WebSocket connections for all backend-to-frontend push events.
    
    Handles:
    - Skill editor streaming (chat chunks, canvas commands, flowgrams)
    - Data updates (agents, skills, tasks, tools, settings, etc.)
    - Chat messages and notifications
    - Skill run statistics
    - LightRAG streaming
    
    Memory leak prevention:
    - Periodic cleanup of stale connections
    - Maximum connections limit
    - Connection health checks
    """
    
    _instance = None
    _lock = threading.Lock()
    
    # Memory leak protection: limits
    _MAX_CONNECTIONS_PER_CHANNEL = 50
    _MAX_TOTAL_CONNECTIONS = 500
    _CLEANUP_INTERVAL_SEC = 60
    _CONNECTION_TIMEOUT_SEC = 300  # 5 minutes
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._connections: dict[str, set[WebSocket]] = {}  # channel_id -> set of websockets
                    cls._instance._all_connections: set[WebSocket] = set()
                    cls._instance._event_loop = None
                    cls._instance._connection_timestamps: dict[int, float] = {}  # Track connection time
                    cls._instance._cleanup_task = None
        return cls._instance
    
    def set_event_loop(self, loop):
        """Set the event loop for async operations from sync context."""
        self._event_loop = loop
        # Start periodic cleanup task
        self._start_periodic_cleanup()
    
    def _start_periodic_cleanup(self):
        """Start periodic cleanup of stale connections."""
        if self._cleanup_task is not None:
            return
        if self._event_loop and self._event_loop.is_running():
            import asyncio
            self._cleanup_task = self._event_loop.create_task(self._periodic_cleanup())
            logger.debug("[AppWS] Started periodic connection cleanup task")
    
    async def _periodic_cleanup(self):
        """Periodically clean up stale connections."""
        import asyncio
        import time
        while True:
            try:
                await asyncio.sleep(self._CLEANUP_INTERVAL_SEC)
                await self._cleanup_stale_connections()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[AppWS] Periodic cleanup error: {e}")
    
    async def _cleanup_stale_connections(self):
        """Clean up stale connections that may have been missed."""
        import time
        current_time = time.time()
        stale_ws_ids = []
        
        # Find stale connections
        for ws_id, timestamp in list(self._connection_timestamps.items()):
            if current_time - timestamp > self._CONNECTION_TIMEOUT_SEC:
                stale_ws_ids.append(ws_id)
        
        # Clean up stale connections
        cleaned = 0
        for ws_id in stale_ws_ids:
            for ws in list(self._all_connections):
                if id(ws) == ws_id:
                    try:
                        await ws.close()
                    except:
                        pass
                    self._all_connections.discard(ws)
                    self._connection_timestamps.pop(ws_id, None)
                    cleaned += 1
                    # Also remove from channel connections
                    for channel in self._connections:
                        self._connections[channel].discard(ws)
        
        if cleaned > 0:
            logger.info(f"[AppWS] Cleaned up {cleaned} stale connections")
        
        # Clean up empty channels
        empty_channels = [ch for ch, ws_set in self._connections.items() if not ws_set]
        for ch in empty_channels:
            del self._connections[ch]
        
        # Log current state
        total = len(self._all_connections)
        if total > self._MAX_TOTAL_CONNECTIONS:
            logger.warning(f"[AppWS] Connection count exceeds limit: {total} > {self._MAX_TOTAL_CONNECTIONS}")
        else:
            logger.debug(f"[AppWS] Connection state: {total} total, {len(self._connections)} channels")
    
    async def connect(self, websocket: WebSocket, channel_id: str = None):
        """Accept a new WebSocket connection."""
        # Memory leak protection: check limits
        total_connections = len(self._all_connections)
        if total_connections >= self._MAX_TOTAL_CONNECTIONS:
            logger.warning(f"[AppWS] Connection limit reached ({total_connections}), rejecting new connection")
            await websocket.close(code=1013, reason="Server at capacity")
            return
        
        if channel_id and channel_id in self._connections:
            channel_connections = len(self._connections[channel_id])
            if channel_connections >= self._MAX_CONNECTIONS_PER_CHANNEL:
                logger.warning(f"[AppWS] Channel {channel_id} connection limit reached ({channel_connections}), rejecting")
                await websocket.close(code=1013, reason="Channel at capacity")
                return
        
        await websocket.accept()
        self._all_connections.add(websocket)
        self._connection_timestamps[id(websocket)] = time.time()
        
        if channel_id:
            if channel_id not in self._connections:
                self._connections[channel_id] = set()
            self._connections[channel_id].add(websocket)
        
        logger.info(f"[SkillEditorWS] Client connected. Channel: {channel_id}, Total connections: {len(self._all_connections)}")
    
    def disconnect(self, websocket: WebSocket, channel_id: str = None):
        """Remove a WebSocket connection."""
        ws_id = id(websocket)
        self._all_connections.discard(websocket)
        self._connection_timestamps.pop(ws_id, None)
        if channel_id and channel_id in self._connections:
            self._connections[channel_id].discard(websocket)
            if not self._connections[channel_id]:
                del self._connections[channel_id]
        logger.info(f"[SkillEditorWS] Client disconnected. Total connections: {len(self._all_connections)}")
    
    async def shutdown(self):
        """Gracefully shutdown all connections."""
        logger.info(f"[AppWS] Shutting down {len(self._all_connections)} connections...")
        
        # Cancel cleanup task
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        
        # Close all connections
        for ws in list(self._all_connections):
            try:
                await ws.close()
            except Exception:
                pass
        
        # Clear all state
        self._all_connections.clear()
        self._connections.clear()
        self._connection_timestamps.clear()
        
        logger.info("[AppWS] All connections closed")
    
    async def broadcast(self, message: dict, channel_id: str = None):
        """Broadcast a message to all connections or a specific channel.
        If channel_id is given but has no subscribers, falls back to all connections.
        """
        message_str = json.dumps(message)
        msg_type = message.get('type', 'unknown')
        if msg_type == "update_skill_run_stat" and len(message_str) > 512 * 1024:
            try:
                original_len = len(message_str)
                from utils.data_uri_sanitizer import sanitize_data_uris
                message = sanitize_data_uris(message, max_string_chars=2000)
                message_str = json.dumps(message)
                logger.warning(
                    f"[data-uri-mitigation] websocket_payload_compacted "
                    f"type={msg_type} bytes={original_len}->{len(message_str)} "
                    f"channel={channel_id}"
                )
            except Exception as exc:
                logger.warning(f"[AppWS] Failed to compact oversized payload: {exc}")
        
        # Check if this message type should be filtered
        is_filtered = should_filter_log(msg_type)
        
        if channel_id and channel_id in self._connections and self._connections[channel_id]:
            targets = self._connections[channel_id]
            if not is_filtered:
                logger.info(f"[AppWS] 📤 broadcast: {msg_type} → channel '{channel_id}' ({len(targets)} subscribers)")
        else:
            targets = self._all_connections
            if not is_filtered:
                logger.info(f"[AppWS] 📤 broadcast: {msg_type} → ALL ({len(targets)} clients), channel_id={channel_id}")
        
        disconnected = []
        for websocket in targets:
            try:
                await websocket.send_text(message_str)
                if not is_filtered:
                    logger.debug(f"[AppWS] ✉️  sent {msg_type} ({len(message_str)} bytes) to ws={id(websocket)}, state={websocket.client_state}")
            except Exception as e:
                logger.warning(f"[AppWS] ❌ Failed to send {msg_type}: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws, channel_id)
        
        if not is_filtered:
            logger.debug(f"[AppWS] ✅ broadcast done: {msg_type}, sent to {len(targets) - len(disconnected)}/{len(targets)} clients")

    
    # ==================== Ad Banner Events ====================
    
    async def send_push_ad(self, banner_text: str = None, popup_html: str = None, duration_ms: int = 60000):
        """Push an ad banner to all clients."""
        logger.info(f"[AppWS] 📢 Pushing ad banner to all clients: banner={bool(banner_text)}, popup={bool(popup_html)}")
        await self.broadcast({
            "type": "push_ad",
            "eventType": "push_ad",
            "payload": {
                "bannerText": banner_text,
                "popupHtml": popup_html,
                "durationMs": duration_ms
            }
        })

    # Note: Chat, Skill Run, LightRAG, and UI event methods removed.
    # All these events are now handled via api.py's unified _send_request() method.
    
    # ==================== Sync Helper for IPCAPI ====================
    
    def broadcast_sync(self, event_type: str, payload: dict, channel_id: str = None):
        """Synchronous wrapper for broadcasting from IPCAPI (runs in thread)."""
        message = {
            "type": event_type,
            "eventType": event_type,
            "payload": payload
        }
        
        # Check if this event type should be filtered
        is_filtered = should_filter_log(event_type)
        
        if self._event_loop and self._event_loop.is_running():
            # Schedule the coroutine on the event loop (fire-and-forget)
            # Don't wait for completion to avoid blocking the caller thread
            import asyncio
            try:
                asyncio.run_coroutine_threadsafe(
                    self.broadcast(message, channel_id),
                    self._event_loop
                )
                if not is_filtered:
                    logger.debug(f"[AppWS] 📤 Broadcast scheduled: {event_type}, channel={channel_id}, clients={len(self._all_connections)}")
            except Exception as e:
                logger.warning(f"[AppWS] ❌ Failed to schedule broadcast for event {event_type}: {e}")
        else:
            logger.warning(f"[AppWS] ⚠️  No event loop available for broadcast_sync, event: {event_type}")


# Global WebSocket manager instance
app_ws_manager = AppWebSocketManager()
# Alias for backward compatibility
skill_editor_ws_manager = app_ws_manager

static_dir = os.path.join(base_dir, 'agent', 'agent_files')
if not os.path.isdir(static_dir):
    # Handle path differences between development and bundled app: fallback to relative path
    alt_dir = os.path.join(os.getcwd(), 'agent', 'agent_files')
    if os.path.isdir(alt_dir):
        static_dir = alt_dir

# Frontend static files directory (gui_v2/dist)
frontend_dist_dir = os.path.join(base_dir, 'gui_v2', 'dist')
if not os.path.isdir(frontend_dist_dir):
    # Fallback paths for different deployment scenarios
    alt_frontend_paths = [
        os.path.join(os.getcwd(), 'gui_v2', 'dist'),
        os.path.join(os.path.dirname(base_dir), 'gui_v2', 'dist'),
        os.path.join(base_dir, '..', 'gui_v2', 'dist')
    ]
    for alt_path in alt_frontend_paths:
        if os.path.isdir(alt_path):
            frontend_dist_dir = alt_path
            break

# Endpoint to serve images
class RequestHandlers:
    """Encapsulates all request handling logic"""

    def __init__(self, main_win: 'MainWindow' = None):
        self.main_win = main_win

    def set_main_win(self, main_win: 'MainWindow'):
        self.main_win = main_win

    async def skill_editor_websocket(self, websocket: WebSocket):
        """WebSocket endpoint for skill editor streaming events."""
        # Get channel_id from query params (e.g., session:xxx)
        channel_id = websocket.query_params.get('channel', None)
        
        await skill_editor_ws_manager.connect(websocket, channel_id)
        
        try:
            while True:
                # Keep connection alive and handle incoming messages
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                    msg_type = message.get('type', '')
                    
                    # Handle subscription to specific channels
                    if msg_type == 'subscribe':
                        new_channel = message.get('channel')
                        if new_channel:
                            if new_channel not in skill_editor_ws_manager._connections:
                                skill_editor_ws_manager._connections[new_channel] = set()
                            skill_editor_ws_manager._connections[new_channel].add(websocket)
                            logger.info(f"[SkillEditorWS] Subscribed to channel: {new_channel}")
                            await websocket.send_text(json.dumps({
                                "type": "subscribed",
                                "channel": new_channel
                            }))
                    
                    elif msg_type == 'unsubscribe':
                        old_channel = message.get('channel')
                        if old_channel and old_channel in skill_editor_ws_manager._connections:
                            skill_editor_ws_manager._connections[old_channel].discard(websocket)
                            logger.info(f"[SkillEditorWS] Unsubscribed from channel: {old_channel}")
                    
                    elif msg_type == 'ping':
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    
                except json.JSONDecodeError:
                    logger.warning(f"[SkillEditorWS] Invalid JSON received: {data[:100]}")
                    
        except WebSocketDisconnect:
            skill_editor_ws_manager.disconnect(websocket, channel_id)
        except Exception as e:
            logger.error(f"[SkillEditorWS] Error: {e}")
            skill_editor_ws_manager.disconnect(websocket, channel_id)

    async def serve_image(self, request):
        filename = request.path_params['filename']
        file_path = os.path.join(IMAGE_FOLDER, filename)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return JSONResponse({"error": "File not found."}, status_code=404)
    
    async def serve_avatar(self, request):
        """Serve avatar files (images and videos) from absolute path"""
        # Get file path from query parameter
        file_path = request.query_params.get('path', '')
        
        if not file_path:
            return JSONResponse({"error": "Missing 'path' parameter"}, status_code=400)
        
        # Security check: ensure file exists and is readable
        if not os.path.isfile(file_path):
            logger.warning(f"Avatar file not found: {file_path}")
            return JSONResponse({"error": "File not found"}, status_code=404)
        
        # Check if file is in allowed directories (resource/avatars)
        abs_path = os.path.abspath(file_path)
        allowed_dirs = [
            os.path.abspath('resource/avatars'),
            os.path.abspath(os.path.join(base_dir, 'resource/avatars'))
        ]
        
        if not any(abs_path.startswith(allowed_dir) for allowed_dir in allowed_dirs):
            logger.warning(f"Avatar file outside allowed directories: {file_path}")
            return JSONResponse({"error": "Access denied"}, status_code=403)
        
        return FileResponse(file_path)
    
    async def lightrag_rerank_proxy(self, request):
        """
        LightRAG Rerank Proxy - Handles all non-native rerank providers.

        Supports: Ollama, RyoAIS, Baidu, and other OpenAI-compatible providers.
        """
        from gui.lightrag_rerank_proxy import lightrag_rerank_proxy
        return await lightrag_rerank_proxy(request)

    async def graphql_handler(self, request):
        """
        GraphQL endpoint - Routes to IPCHandlerRegistry for unified handling.
        
        解析前端发送的 GraphQL 请求：
        - body.query: GraphQL query/mutation 字符串
        - body.variables: GraphQL 变量
        - body.extensions.method: IPC method 名称
        - body.extensions: 其他扩展参数
        
        提取 method 和参数后，直接调用对应的 IPC handler 处理请求。
        """
        try:
            # 解析 GraphQL 请求 body
            try:
                request_body = await request.json()
            except Exception as e:
                logger.error(f"[GraphQL] ❌ Invalid JSON body: {e}")
                return JSONResponse({
                    "errors": [{"message": "Invalid JSON body"}]
                }, status_code=200)

            graphql_query = request_body.get('query', '')
            graphql_variables = request_body.get('variables', {})
            extensions = request_body.get('extensions', {})

            if not isinstance(graphql_query, str):
                graphql_query = ''
            
            logger.info(f"[GraphQL] 📥 Received request")
            logger.debug(f"[GraphQL] Query: {graphql_query[:100]}...")
            logger.debug(f"[GraphQL] Variables: {graphql_variables}")
            logger.debug(f"[GraphQL] Extensions: {extensions}")
            
            # 从 extensions 中提取 method 和 operationName
            method = extensions.get('method')
            operation_name = request_body.get('operationName')
            
            if not operation_name and graphql_query.strip():
                operation_name = self._extract_graphql_operation_name(graphql_query)
            
            if not method:
                logger.error("[GraphQL] ❌ Could not extract method from extensions")
                return JSONResponse({
                    "errors": [{"message": "Could not extract method from extensions"}]
                }, status_code=200)
            
            logger.info(f"[GraphQL] 🎯 Method: {method}")
            if operation_name:
                logger.info(f"[GraphQL] 📋 OperationName: {operation_name}")
            
            # 合并参数：variables + extensions（排除 method 和 operationName）
            # GraphQL mutations often wrap params in 'input', unwrap if present
            if 'input' in graphql_variables and isinstance(graphql_variables.get('input'), dict):
                request_params = dict(graphql_variables['input'])
                # Preserve any top-level variables that aren't 'input'
                for k, v in graphql_variables.items():
                    if k != 'input':
                        request_params[k] = v
            else:
                request_params = dict(graphql_variables)

            # Extract token from Authorization header for validation
            # Token should NOT be injected into request_params to avoid polluting business data
            auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
            extracted_token = None
            if auth_header and isinstance(auth_header, str):
                parts = auth_header.split(' ', 1)
                if len(parts) == 2 and parts[0].lower() == 'bearer':
                    extracted_token = parts[1].strip()
            
            # 将 extensions 中的其他元数据合并进来（排除 method 和 operationName）
            for key, value in extensions.items():
                if key not in ('method', 'operationName'):
                    request_params[key] = value
            
            logger.info(f"[GraphQL] 📦 Parameters: {list(request_params.keys())}")
            
            # 使用 IPCHandlerRegistry 统一处理
            from gui.ipc.registry import IPCHandlerRegistry

            # Create IPC request with token separate from business params
            ipc_request = {
                'id': f'graphql_{method}',
                'method': method,
                'params': request_params,
                'source': 'graphql',
                'token': extracted_token  # Token for validation only, not in params
            }

            # IPCHandlerRegistry now automatically handles background handlers in thread pool
            # to avoid blocking the event loop (e.g., login, skill_editor.chat.send_message)
            result_data = await IPCHandlerRegistry.handle_graphql_request(method, request_params, ipc_request)
            
            # 使用 operation_name 作为响应的字段名（如果没有则使用 method）
            response_field_name = operation_name or method
            
            # 包装为 GraphQL 响应格式
            logger.info(f"[GraphQL] ✅ Success: {response_field_name}")
            return JSONResponse({
                "data": {response_field_name: result_data}
            }, status_code=200)
            
        except asyncio.CancelledError:
            # Expected during server shutdown - don't log as error
            logger.debug(f"[GraphQL] Request cancelled during shutdown: {method}")
            raise  # Re-raise to properly propagate cancellation
        except Exception as e:
            # Extract error code from error message if present
            error_message = str(e)
            error_code = getattr(e, "error_code", None) or "GRAPHQL_ERROR"
            error_details = getattr(e, "error_details", None)
            
            # Check if error message contains known error codes
            if error_code == "GRAPHQL_ERROR" and ("INVALID_TOKEN" in error_message or "Token validation failed" in error_message):
                error_code = "INVALID_TOKEN"
            elif error_code == "GRAPHQL_ERROR" and "TOKEN_REQUIRED" in error_message:
                error_code = "TOKEN_REQUIRED"
            elif error_code == "GRAPHQL_ERROR" and "SYSTEM_NOT_READY" in error_message:
                error_code = "SYSTEM_NOT_READY"
            
            # Log expected auth/system/login errors as warning without
            # traceback.  Log unexpected errors as error with traceback.
            #
            # ``LOGIN_FAILED`` was previously logged with a full
            # traceback (because the handler raised RuntimeError to
            # surface the error code, then LocalServer caught it and
            # unconditionally logged the traceback for any code not in
            # the early-exit list).  That produced scary red noise in
            # the user's console every time they typed the wrong
            # password, even though the GraphQL response correctly
            # surfaced ``code: LOGIN_FAILED`` to the frontend (see
            # terminals/7.txt:51-65).  Adding ``LOGIN_FAILED``,
            # ``CLOUDBASE_NOT_AVAILABLE``, ``INVALID_CREDENTIALS`` and
            # ``SMS_SEND_FAILED`` to the warning list keeps the noise
            # down without changing behaviour — the frontend still
            # gets the structured error code in the GraphQL response.
            #
            # ``PROVIDER_MODELS_ERROR`` is added here for the same
            # reason: the handler already classifies the upstream
            # 401/403/429 as a transient cloud-side response (see
            # ``SettingsHandler.handle_get_provider_models`` and the
            # matching branch in ``registry.handle_graphql_request``),
            # so re-emitting it as ERROR with a full traceback on every
            # rate-limited probe just floods the runlog. The frontend
            # receives the typed code via the GraphQL response and can
            # render its own UI hint.
            #
            # LightRAG ``GET_DOCUMENTS_ERROR`` (with a urllib3
            # "Connection refused" message) is handled the same way: the
            # 3-attempt client retry already absorbed the brief startup
            # race, the frontend's ``isConnectionErrorMessage()`` then
            # takes over with a 10×2s "Waiting for LightRAG server…"
            # loop, and re-dumping the urllib3 traceback here on every
            # poll just floods the runlog. The frontend still receives
            # the typed code via the GraphQL response.
            err_text_lower = error_message.lower()
            is_lightrag_unavailable = (
                error_code == "GET_DOCUMENTS_ERROR"
                and (
                    'connection refused' in err_text_lower
                    or 'failed to establish a new connection' in err_text_lower
                    or 'max retries exceeded' in err_text_lower
                )
            )
            if is_lightrag_unavailable:
                logger.warning(
                    f"[GraphQL] {error_code} for {method} (server unavailable, "
                    f"frontend will retry): {error_message}"
                )
            elif error_code in (
                "INVALID_TOKEN",
                "TOKEN_REQUIRED",
                "SYSTEM_NOT_READY",
                "LOGIN_FAILED",
                "CLOUDBASE_NOT_AVAILABLE",
                "INVALID_CREDENTIALS",
                "SMS_SEND_FAILED",
                "PROVIDER_MODELS_ERROR",
            ):
                logger.warning(f"[GraphQL] {error_code} for {method}: {error_message}")
            else:
                logger.error(f"[GraphQL] ❌ Error handling request: {e}")
                import traceback
                logger.error(traceback.format_exc())
            
            return JSONResponse({
                "errors": [{
                    "message": error_message,
                    "extensions": {"code": error_code, "details": error_details}
                }]
            }, status_code=200)  # GraphQL returns 200 even for errors
    
    def _extract_graphql_operation_name(self, graphql_query: str) -> Optional[str]:
        """从 GraphQL query/mutation 中提取操作名（对应后端 handler method）
        
        Examples:
            query { getAgents { ... } } -> 'getAgents'
            mutation { saveAgent(...) { ... } } -> 'saveAgent'
            query GetData { readSkillFile(...) { ... } } -> 'readSkillFile'
        """
        import re
        
        # 移除注释并规范化空白字符
        query_normalized = re.sub(r'#.*', '', graphql_query)
        query_normalized = ' '.join(query_normalized.split())

        # Some documents may start with fragment definitions.
        # To avoid mis-detecting fragment body fields (e.g. '{ id ... }') as operation name,
        # slice from the first real operation keyword (query/mutation) when present.
        op_kw = re.search(r'\b(query|mutation)\b', query_normalized, re.IGNORECASE)
        if op_kw:
            query_normalized = query_normalized[op_kw.start():]
        
        # 匹配 query/mutation 模式
        # 模式: (query|mutation) [可选的操作名] { 字段名
        match = re.search(r'(?:query|mutation)\s*(?:\w+\s*)?\{\s*(\w+)', query_normalized, re.IGNORECASE)
        if match:
            return match.group(1)
        
        # 降级方案：查找第一个大括号后的单词
        match = re.search(r'\{\s*(\w+)', query_normalized)
        if match:
            return match.group(1)
        
        return None

    async def post_data(self, request):
        incoming_data = await request.json()
        logger.info(f"Received data: {incoming_data}")
        task_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        response_dict[task_id] = future
        
        def _cleanup():
            response_dict.pop(task_id, None)
        
        run_on_main_thread(lambda: self.main_win.task_queue.put({
            "task_id": task_id,
            "data": incoming_data
        }))
        try:
            result = await asyncio.wait_for(future, timeout=30)
            _cleanup()  # Clean up on success
            return JSONResponse({"status": "success", "result": result})
        except asyncio.TimeoutError:
            _cleanup()  # Clean up on timeout
            logger.warning(f"[post_data] Request timed out after 30s, task_id={task_id}")
            return JSONResponse({"status": "error", "error": "Request timed out"}, status_code=504)
        except Exception as e:
            _cleanup()  # Clean up on error
            logger.error(f"[post_data] Request failed: {e}")
            return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

    async def initialize(self, request):
        # Perform whatever server-side initialization you want
        logger.info("initialize() called")
        response = {
            "protocolVersion": "1.0",
            "serverCapabilities": {}
        }
        return JSONResponse(response, status_code=200)


async def health_check(request):
    """Minimal health check endpoint"""
    logger.debug("health_check status returned................")
    return JSONResponse({"status": "ok"})


async def local_ws_test(request):
    """Test endpoint to publish test messages to all local WebSocket pub/sub channels.
    
    This broadcasts test messages to all connected WebSocket clients for each event type,
    allowing frontend developers to verify their subscription handlers are working.
    """
    import time
    timestamp = int(time.time() * 1000)
    test_id = f"test-{timestamp}"
    
    results = []
    
    try:
        # Test all pub/sub event types (matching api.py methods)
        test_events = [
            # Organization and agent updates
            ("update_org_agents", {}),
            # Chat events
            ("push_chat_message", {"chatId": test_id, "message": {"role": "system", "content": "Test message"}}),
            ("push_chat_notification", {"chatId": test_id, "content": {"text": "Test notification"}, "isRead": False, "timestamp": timestamp, "uid": test_id}),
            # Skill run events
            ("update_skill_run_stat", {"agentTaskId": test_id, "currentNode": "test_node", "current_node": "test_node", "status": "running", "langgraphState": {}, "nodeState": {}, "timestamp": timestamp}),
            ("update_tasks_stat", {"agentTaskId": test_id, "langgraphState": {"test": True}, "timestamp": timestamp}),
            # LightRAG events
            ("lightrag.queryStream.chunk", {"id": test_id, "chunk": "Test LightRAG chunk data"}),
            ("lightrag.queryStream.done", {"id": test_id}),
            ("lightrag.queryStream.error", {"id": test_id, "error": "Test error message"}),
            # Skill editor events
            ("skill_editor.chat.stream_chunk", {"sessionId": test_id, "messageId": f"msg-{test_id}", "chunk": "Test stream chunk", "chunkIndex": 0}),
            ("skill_editor.chat.stream_end", {"sessionId": test_id, "messageId": f"msg-{test_id}", "fullContent": "Test complete message"}),
            ("skill_editor.chat.error", {"sessionId": test_id, "code": "TEST_ERROR", "message": "Test error"}),
            ("skill_editor.event", {"sessionId": test_id, "type": "canvas_command", "payload": {"action": "test"}}),
        ]
        
        for event_type, payload in test_events:
            try:
                message = {
                    "type": event_type,
                    "eventType": event_type,
                    "payload": payload,
                    "_test": True,
                    "_testId": test_id,
                    "_timestamp": timestamp
                }
                await app_ws_manager.broadcast(message)
                results.append({"event": event_type, "status": "sent"})
                logger.info(f"[LocalWSTest] Sent test event: {event_type}")
            except Exception as e:
                results.append({"event": event_type, "status": "error", "error": str(e)})
                logger.error(f"[LocalWSTest] Error sending {event_type}: {e}")
        
        return JSONResponse({
            "status": "success",
            "testId": test_id,
            "timestamp": timestamp,
            "eventsSent": len([r for r in results if r["status"] == "sent"]),
            "eventsTotal": len(test_events),
            "results": results
        })
        
    except Exception as e:
        logger.error(f"[LocalWSTest] Error: {e}")
        import traceback
        return JSONResponse({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status_code=500)


async def test_ocr(request):
    """Test endpoint: captures current screen and runs OCR via readScreen8 / readRandomWindow8.
    Accepts optional JSON body: {"win_title_kw": "Weixin"} to target a specific window."""
    import traceback as tb
    try:
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return JSONResponse({"status": "error", "error": "MainWindow not available"}, status_code=500)

        # Parse optional request body
        win_title_kw = ""
        try:
            body = await request.json()
            win_title_kw = body.get("win_title_kw", "")
        except Exception:
            pass

        logger.info(f"[TestOCR] Starting OCR test, win_title_kw='{win_title_kw}'")

        # Reuse the same logic as MCP _screen_read helper
        from agent.ec_skills.ocr.image_prep import readRandomWindow8
        log_user = mainwin.user.replace("@", "_").replace(".", "_")
        session = mainwin.session
        token = mainwin.get_auth_token()
        mission = mainwin.getTrialRunMission()

        logger.info(f"[TestOCR] log_user={log_user}, session={type(session).__name__}, "
                     f"token_len={len(token) if isinstance(token, str) and token else 0}, mission={type(mission).__name__}")

        # Serialize with MCP _screen_read calls to prevent concurrent OCR requests
        from agent.mcp.server.server import _ocr_semaphore
        async with _ocr_semaphore:
            result = await readRandomWindow8(mission, win_title_kw, log_user, session, token)

        logger.info(f"[TestOCR] OCR completed. Result type={type(result).__name__}, "
                     f"items={len(result) if isinstance(result, list) else 'N/A'}")

        # Truncate result for JSON response (OCR data can be large)
        import json as _json
        result_str = _json.dumps(result, ensure_ascii=False, default=str)
        if len(result_str) > 5000:
            result_preview = result_str[:5000] + "... (truncated)"
        else:
            result_preview = result_str

        return JSONResponse({
            "status": "success",
            "win_title_kw": win_title_kw,
            "result_count": len(result) if isinstance(result, list) else 1,
            "result": result if isinstance(result, (list, dict)) else str(result),
        })
    except Exception as e:
        logger.error(f"[TestOCR] Error: {e}\n{tb.format_exc()}")
        return JSONResponse({"status": "error", "error": str(e), "traceback": tb.format_exc()}, status_code=500)


async def test_ocr_local(request):
    """Test endpoint: runs PaddleOCR locally on an image file.
    Accepts optional JSON body: {"image_path": "..."}.
    Defaults to ocr/test_image0.PNG relative to project root."""
    import traceback as tb
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            pass

        # Default image: <project_root>/ocr/test_image0.PNG
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_image = os.path.join(project_root, "ocr", "test_image0.PNG")
        image_path = body.get("image_path", default_image)

        max_long_side = int(body.get("max_long_side", 1500))
        logger.info(f"[TestOCRLocal] Running local PaddleOCR on: {image_path}, max_long_side={max_long_side}")

        import time as _time
        from PIL import Image as _PILImage
        from agent.mcp.server.local_ocr.paddle_ocr import run_ocr_on_image, scale_ocr_coordinates

        img = _PILImage.open(image_path)
        orig_w, orig_h = img.size
        scale_x, scale_y = 1.0, 1.0
        resized = False

        long_side = max(orig_w, orig_h)
        if max_long_side and long_side > max_long_side:
            ratio = max_long_side / long_side
            new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
            img = img.resize((new_w, new_h))
            scale_x = orig_w / new_w
            scale_y = orig_h / new_h
            resized = True
            # Save resized image to temp file
            import tempfile
            tmp_path = os.path.join(tempfile.gettempdir(), "test_ocr_local_resized.png")
            img.save(tmp_path)
            logger.info(f"[TestOCRLocal] Resized: ({orig_w},{orig_h}) -> ({new_w},{new_h}), "
                        f"scale=({scale_x:.3f},{scale_y:.3f})")
            image_path = tmp_path

        t0 = _time.perf_counter()
        result = run_ocr_on_image(image_path)
        elapsed_s = _time.perf_counter() - t0

        # Scale coordinates back to original resolution if resized
        if resized and result.get("status") == "success" and result.get("ocr_data"):
            result["ocr_data"] = scale_ocr_coordinates(result["ocr_data"], scale_x, scale_y)

        result["resize_info"] = {
            "original_size": [orig_w, orig_h],
            "resized": resized,
            "max_long_side": max_long_side,
            "scale": [round(scale_x, 3), round(scale_y, 3)] if resized else [1.0, 1.0],
            "ocr_elapsed_s": round(elapsed_s, 2),
        }

        logger.info(f"[TestOCRLocal] Done. status={result.get('status')}, "
                     f"items={len(result.get('results', []))}, elapsed={elapsed_s:.2f}s, resized={resized}")

        return JSONResponse(result)
    except Exception as e:
        logger.error(f"[TestOCRLocal] Error: {e}\n{tb.format_exc()}")
        return JSONResponse({"status": "error", "error": str(e), "traceback": tb.format_exc()}, status_code=500)


async def test_hybrid_cloud(request):
    """Test endpoint: directly calls launch_agent_task for test_hybrid_worker.
    Bypasses the LLM to test the hybrid cloud task plumbing end-to-end."""
    import time
    import traceback as tb
    try:
        from agent.ec_tasks.task_mcp_tools import launch_agent_task
        from app_context import AppContext
        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return JSONResponse({"status": "error", "error": "MainWindow not available"}, status_code=500)

        config = {"task_name": "test_hybrid_worker"}
        logger.info(f"[TestHybridCloud] Calling launch_agent_task with config={config}")
        result = launch_agent_task(mainwin, config)
        logger.info(f"[TestHybridCloud] Result: {result}")
        return JSONResponse({"status": "ok", "result": result})
    except Exception as e:
        logger.error(f"[TestHybridCloud] Error: {e}\n{tb.format_exc()}")
        return JSONResponse({"status": "error", "error": str(e), "traceback": tb.format_exc()}, status_code=500)


async def direct_service_assign(request):
    """Test endpoint: send direct customer-service assignment chat_message(s) from the live app process.

    Expected JSON body:
      {
        "sender_agent_id": "...",
        "recipient_agent_id": "...",
        "assignments": [
          {
            "session_id": "cust_xxx",
            "tab_id": "CDP_TARGET_ID",
            "chat_url": "http://127.0.0.1:9877/chat?session=cust_xxx",
            "customer_name": "Alice_xxx"
          }
        ]
      }
    """
    import traceback as tb
    try:
        body = {}
        try:
            body = await request.json()
        except Exception:
            body = {}

        from app_context import AppContext
        from agent.mcp.server.chat_utils.chat_tools import (
            send_chat,
            _get_agent_by_id,
            _get_all_agents,
            _build_chat_message,
        )

        mainwin = AppContext.get_main_window()
        if mainwin is None:
            return JSONResponse({"status": "error", "error": "MainWindow not available"}, status_code=500)

        requested_sender_agent_id = str(body.get("sender_agent_id") or "agent_48bdd65f982a4cdb").strip()
        recipient_agent_id = str(body.get("recipient_agent_id") or "agent_b31f281332104b93").strip()
        assignments = body.get("assignments") or []
        if not isinstance(assignments, list) or not assignments:
            return JSONResponse({"status": "error", "error": "No assignments provided"}, status_code=400)

        sender_agent_id = requested_sender_agent_id
        sender_agent = _get_agent_by_id(sender_agent_id, mainwin=mainwin) if sender_agent_id else None
        recipient_agent = _get_agent_by_id(recipient_agent_id, mainwin=mainwin) if recipient_agent_id else None
        if recipient_agent is None:
            return JSONResponse({
                "status": "error",
                "error": f"Recipient agent not found: {recipient_agent_id}",
            }, status_code=500)

        carrier_agent = sender_agent
        if sender_agent is None:
            live_agents = _get_all_agents(mainwin=mainwin)
            fallback_sender = next(
                (
                    ag for ag in live_agents
                    if ag.get("id")
                    and ag.get("id") != recipient_agent_id
                ),
                None,
            )
            if fallback_sender:
                sender_agent_id = str(fallback_sender.get("id") or "").strip()
                sender_agent = _get_agent_by_id(sender_agent_id, mainwin=mainwin)
                carrier_agent = sender_agent
                logger.warning(
                    f"[DirectServiceAssign] Requested sender '{requested_sender_agent_id}' not found; "
                    f"using fallback sender '{sender_agent_id}'"
                )
            else:
                sender_agent_id = requested_sender_agent_id or f"test_harness_sender_{uuid.uuid4().hex[:8]}"
                carrier_agent = recipient_agent
                logger.warning(
                    f"[DirectServiceAssign] No live sender available for requested sender "
                    f"'{requested_sender_agent_id}'. Using synthetic sender_id='{sender_agent_id}' "
                    f"via carrier agent '{getattr(getattr(recipient_agent, 'card', None), 'id', '') or recipient_agent_id}'"
                )

        logger.info(
            f"[DirectServiceAssign] Received {len(assignments)} assignment(s) "
            f"sender={sender_agent_id} recipient={recipient_agent_id}"
        )

        results = []
        ok_count = 0
        for item in assignments:
            if not isinstance(item, dict):
                continue
            payload = {
                "customer_id": str(item.get("session_id") or "").strip(),
                "session_id": str(item.get("session_id") or "").strip(),
                "tab_id": str(item.get("tab_id") or "").strip(),
                "chat_url": str(item.get("chat_url") or "").strip(),
                "customer_name": str(item.get("customer_name") or item.get("session_id") or "").strip(),
            }
            logger.info(f"[DirectServiceAssign] Sending payload: {payload}")
            if sender_agent is not None:
                result = send_chat(mainwin, {
                    "sender_agent_id": sender_agent_id,
                    "recipient_agent_id": recipient_agent_id,
                    "message": json.dumps(payload, ensure_ascii=False),
                    "message_type": "text",
                    "async_send": False,
                })
            else:
                synthetic_sender_name = "DirectAssignHarness"
                chat_message = _build_chat_message(
                    sender_agent_id=sender_agent_id,
                    chat_id=str(payload.get("session_id") or ""),
                    message_text=json.dumps(payload, ensure_ascii=False),
                    sender_name=synthetic_sender_name,
                    receiver_agent_id=recipient_agent_id,
                    message_type="text",
                    attachments=[],
                )
                response = carrier_agent.unified_send_chat_message(
                    recipient_id=recipient_agent_id,
                    message=chat_message,
                    use_wan_fallback=True,
                )
                result = {
                    "success": True,
                    "message_id": chat_message["messages"][2],
                    "chat_id": chat_message["messages"][1],
                    "recipient_id": recipient_agent_id,
                    "recipient_name": getattr(getattr(recipient_agent, "card", None), "name", "") or recipient_agent_id,
                    "async": False,
                    "message": f"Message sent to {getattr(getattr(recipient_agent, 'card', None), 'name', '') or recipient_agent_id}",
                    "timestamp": int(time.time() * 1000),
                    "transport_result": response,
                    "synthetic_sender": True,
                }
            merged = dict(item)
            merged["recipient_agent_id"] = recipient_agent_id
            merged.update(result or {})
            if merged.get("success"):
                ok_count += 1
            logger.info(f"[DirectServiceAssign] Result: {merged}")
            results.append(merged)

        return JSONResponse({
            "status": "ok",
            "success": ok_count == len(results),
            "count": len(results),
            "results": results,
        })
    except Exception as e:
        logger.error(f"[DirectServiceAssign] Error: {e}\n{tb.format_exc()}")
        return JSONResponse({"status": "error", "error": str(e), "traceback": tb.format_exc()}, status_code=500)


async def c2l_ws_test(request):
    """C2L (Cloud to Local) WebSocket Test endpoint.
    
    This sends a runTest mutation to cloud AppSync to test the cloud-to-local
    WebSocket push mechanism. The cloud should receive this request and can
    push messages back to the local client via WebSocket subscriptions.
    """
    import time
    import uuid
    import requests
    
    timestamp = int(time.time() * 1000)
    test_id = f"c2l-test-{timestamp}"
    
    try:
        # Get auth token from app context
        from config.app_settings import AppSettings
        
        main_window = AppSettings.get_main_window()
        
        if not main_window:
            return JSONResponse({
                "status": "error",
                "error": "MainWindow not available"
            }, status_code=500)
        
        token = main_window.get_auth_token()
        if not token:
            return JSONResponse({
                "status": "error",
                "error": "No authentication token available. Please log in."
            }, status_code=401)
        
        # Get the owner (username) for the subscription filter
        owner = main_window.getUser()
        if not owner:
            return JSONResponse({
                "status": "error",
                "error": "No owner/username available. Please log in."
            }, status_code=401)
        
        # Import cloud_api function
        from agent.cloud_api.cloud_api import send_run_test_to_cloud
        
        # Create test payload - include owner so cloud publishes to correct subscription
        import json as json_mod
        tests = [{
            "id": test_id,
            "name": "C2L_WS_TEST",
            "description": "",
            "input": json_mod.dumps({"owner": owner})
        }]
        
        # Create a session and send to cloud
        session = requests.Session()
        
        logger.info(f"[C2L-WS-Test] Sending test to cloud: {test_id}")
        result = send_run_test_to_cloud(session, token, tests)
        
        if result.get("success"):
            return JSONResponse({
                "status": "success",
                "testId": test_id,
                "timestamp": timestamp,
                "cloudResponse": result.get("data")
            })
        else:
            return JSONResponse({
                "status": "error",
                "testId": test_id,
                "errors": result.get("errors", [])
            }, status_code=500)
            
    except Exception as e:
        logger.error(f"[C2L-WS-Test] Error: {e}")
        import traceback
        return JSONResponse({
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status_code=500)


# Wrap the raw ASGI handler for POST
# messages_router = Router([
#     Route("/", endpoint=sse_handle_messages, methods=["POST"])
# ])
#
# sse_router = Router([
#     Route("/", endpoint=handle_sse, methods=["GET"])
# ==================== MCP Route Handling ====================
class MCPHandler:
    """MCP request handler."""

    _session_manager_initialized = False
    _session_manager_instance = None
    _session_manager_context = None

    @staticmethod
    async def cleanup():
        """Clean up MCP session manager resources.

        The StreamableHTTPSessionManager uses an async generator with a TaskGroup.
        We cannot call __aexit__ from a different task (causes RuntimeError).
        Instead, we try to gracefully close the async generator via aclose(),
        suppressing the expected TaskGroup error during shutdown.
        """
        ctx = MCPHandler._session_manager_context
        if ctx:
            logger.info("🧹 [MCP] Cleaning up session manager context...")
            MCPHandler._session_manager_context = None
            try:
                # Try to gracefully close the async generator
                await ctx.aclose()
                logger.info("✅ [MCP] Session manager context closed gracefully")
            except (RuntimeError, BaseExceptionGroup, GeneratorExit) as e:
                # Expected during shutdown: "Attempted to exit cancel scope in a different task"
                logger.debug(f"[MCP] Expected shutdown error (harmless): {type(e).__name__}")
            except Exception as e:
                logger.debug(f"[MCP] Error closing session manager context: {e}")

        if MCPHandler._session_manager_instance:
            logger.info("🧹 [MCP] Cleaning up session manager instance...")
            MCPHandler._session_manager_instance = None

        MCPHandler._session_manager_initialized = False
        logger.info("✅ [MCP] Handler cleanup completed")

    @staticmethod
    async def ensure_session_manager_initialized():
        """Ensures the session_manager is properly initialized."""
        if not MCPHandler._session_manager_initialized and mcp_server_config.session_manager:
            try:
                logger.info("🔧 [MCP] Initializing session manager...")
                from agent.mcp.server.server import StreamableHTTPSessionManager
                MCPHandler._session_manager_instance = StreamableHTTPSessionManager(
                    app=mcp_server_config.meca_mcp_server,
                    event_store=None,
                    json_response=True
                )

                # Initialize the new instance
                MCPHandler._session_manager_context = MCPHandler._session_manager_instance.run()
                await MCPHandler._session_manager_context.__aenter__()
                MCPHandler._session_manager_initialized = True
                logger.info("✅ [MCP] Session manager initialized successfully")
            except Exception as e:
                logger.error(f"❌ [MCP] Failed to initialize session manager: {e}")
                logger.error(f"❌ [MCP] Traceback: {traceback.format_exc()}")
                # Mark as attempted even if initialization fails, to avoid retries
                MCPHandler._session_manager_initialized = True

    @staticmethod
    async def handle_request(scope, receive, send):
        """Handles MCP requests."""
        if mcp_server_config.has_mcp_support():
            # Ensure session_manager is initialized
            await MCPHandler.ensure_session_manager_initialized()

            try:
                # Use our own session manager instance
                if MCPHandler._session_manager_instance:
                    await MCPHandler._session_manager_instance.handle_request(scope, receive, send)
                else:
                    # Fallback to the original session_manager if no instance exists
                    await mcp_server_config.session_manager.handle_request(scope, receive, send)
            except RuntimeError as e:
                if "Task group is not initialized" in str(e) or "can only be called once" in str(e):
                    logger.error("❌ [MCP] Session manager not properly initialized, falling back to error response")
                    await MCPHandler.create_unavailable_response(scope, receive, send)
                else:
                    raise
        else:
            # MCP modules unavailable: return an error message
            await MCPHandler.create_unavailable_response(scope, receive, send)

    @staticmethod
    async def create_unavailable_response(scope, receive, send):
        """Creates an MCP unavailable response."""
        from starlette.responses import JSONResponse

        reason = "PyInstaller environment with import issues" if mcp_server_config.is_frozen else "MCP modules not available"

        if scope["method"] == "GET":
            # SSE connection request
            response = JSONResponse(
                {"error": f"MCP SSE not available: {reason}"},
                status_code=503
            )
        else:
            # JSON-RPC request
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "error": {
                        "code": -32603,
                        "message": f"MCP functionality not available: {reason}. Please use the development environment or fix PyInstaller packaging."
                    }
                },
                status_code=503
            )

        await response(scope, receive, send)

# MCP ASGI Application
async def mcp_asgi(scope, receive, send):
    """MCP ASGI entry point."""
    await MCPHandler.handle_request(scope, receive, send)

# ==================== Route Configuration ====================
class RouteBuilder:
    """Route builder."""

    def __init__(self, request_handlers):
        self.request_handlers: RequestHandlers = request_handlers

    def get_base_routes(self):
        """Get base routes"""
        return [
            Mount("/mcp", app=mcp_asgi),
            Route("/healthz", health_check),
            Route("/health", health_check),  # Alias for frontend compatibility
            Route("/api/local-ws-test", local_ws_test, methods=['GET', 'POST']),
            Route("/api/test-ocr", test_ocr, methods=['GET', 'POST']),
            Route("/api/test-ocr-local", test_ocr_local, methods=['GET', 'POST']),
            Route("/api/test-hybrid-cloud", test_hybrid_cloud, methods=['GET', 'POST']),
            Route("/api/test-direct-service-assign", direct_service_assign, methods=['POST']),
            Route("/api/c2l-ws-test", c2l_ws_test, methods=['GET', 'POST']),
            Route("/graphql", self.request_handlers.graphql_handler, methods=['POST']),
            WebSocketRoute("/ws/skill-editor", self.request_handlers.skill_editor_websocket),
            Route('/api/initialize', self.request_handlers.initialize, methods=['POST']),
            Route('/api/avatar', self.request_handlers.serve_avatar, methods=['GET']),
            Route('/api/rerank', self.request_handlers.lightrag_rerank_proxy, methods=['POST'])
        ]

    def get_mcp_routes(self):
        """Get MCP related routes"""
        if not mcp_server_config.has_mcp_support():
            return []
        return [
            Mount("/sse", app=mcp_server_config.handle_sse),
            Mount("/messages/", app=mcp_server_config.meca_sse.handle_post_message),
            Mount("/mcp_messages/", app=mcp_server_config.meca_streamable_http.handle_request),
        ]

    def create_routes(self):
        """Create complete route list"""
        routes = self.get_base_routes()
        mcp_routes = self.get_mcp_routes()
        if mcp_routes:
            routes.extend(mcp_routes)
            logger.info("✅ Added MCP routes")
        else:
            logger.info("🔧 MCP routes not added (disabled or unsupported)")
        return routes

    @staticmethod
    def spa_fallback(frontend_dist_dir: str):
        """Create SPA fallback handler for client-side routing"""
        async def fallback_handler(request: Request):
            """Serve index.html for all unmatched GET routes (SPA fallback)"""
            # Only handle GET requests for HTML pages
            if request.method != 'GET':
                return JSONResponse({"error": "Method not allowed"}, status_code=405)
            
            # Check if request is for a file with extension (e.g., .js, .css, .png)
            # If so, return 404 instead of serving index.html
            path = request.url.path
            if '.' in path.split('/')[-1]:
                return JSONResponse({"error": "File not found"}, status_code=404)
            
            # Serve index.html for all other routes (SPA routes like /login, /agents, etc.)
            index_path = os.path.join(frontend_dist_dir, 'index.html')
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return JSONResponse({"error": "Frontend not found"}, status_code=404)
        return fallback_handler

# ==================== Application Creation ====================


class AppBuilder:
    """Starlette application builder"""

    @staticmethod
    def create_app(request_handlers):
        """Create Starlette application"""
        route_builder = RouteBuilder(request_handlers)
        routes = route_builder.create_routes()

        # Mount frontend static files and add SPA fallback
        # Order matters: API routes first, then static files, then SPA fallback
        if os.path.isdir(frontend_dist_dir):
            # Mount static assets directory
            assets_dir = os.path.join(frontend_dist_dir, 'assets')
            if os.path.isdir(assets_dir):
                routes.append(Mount('/assets', StaticFiles(directory=assets_dir), name='assets'))
            
            # Mount monaco-editor directory if exists
            monaco_dir = os.path.join(frontend_dist_dir, 'monaco-editor')
            if os.path.isdir(monaco_dir):
                routes.append(Mount('/monaco-editor', StaticFiles(directory=monaco_dir), name='monaco'))
            
            # Mount skills directory if exists
            skills_dir = os.path.join(frontend_dist_dir, 'skills')
            if os.path.isdir(skills_dir):
                routes.append(Mount('/skills', StaticFiles(directory=skills_dir), name='skills'))
            
            # Add catch-all route for SPA (must be last)
            # This handles all unmatched routes (including /, /login, /agents, etc.) by serving index.html
            routes.append(Route('/{path:path}', route_builder.spa_fallback(frontend_dist_dir)))
            
            logger.info(f"✅ Mounted frontend static files with SPA fallback from: {frontend_dist_dir}")
        else:
            logger.warning(f"⚠️ Frontend dist dir not found: {frontend_dist_dir}")
            # Fallback to agent files if frontend not available
            if os.path.isdir(static_dir):
                routes.append(Mount('/', StaticFiles(directory=static_dir, html=True), name='static'))
                logger.info(f"✅ Mounted agent static files from: {static_dir}")
            else:
                logger.warning(f"⚠️ Static dir missing, no static files mounted: {static_dir}")

        app_config = {
            'routes': routes,
            'debug': mcp_server_config.is_development
        }

        logger.info("🔧 Created Starlette app of LocalServer")
        app = Starlette(**app_config)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_methods=['*'],
            allow_headers=['*']
        )
        return app

# ==================== Server Startup ====================
class ServerOptimizer:
    """Server optimizer"""

    @staticmethod
    def setup_pyinstaller_environment():
        """Setup PyInstaller environment optimizations"""
        logger.info("🔧 Detected PyInstaller environment, applying optimizations...")

        # Event loop optimization
        ServerOptimizer._setup_event_loop()

        # Disable warnings
        ServerOptimizer._disable_warnings()

    @staticmethod
    def _hide_console_window_windows():
        """Best-effort hide any attached console window on Windows.
        This helps avoid a transient Python console flicker when starting background servers
        in packaged (PyInstaller) applications.
        """
        try:
            import sys
            if sys.platform != 'win32':
                return
            import ctypes
            user32 = ctypes.WinDLL('user32', use_last_error=True)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            GetConsoleWindow = kernel32.GetConsoleWindow
            GetConsoleWindow.restype = ctypes.c_void_p
            hwnd = GetConsoleWindow()
            if hwnd:
                # SW_HIDE = 0
                user32.ShowWindow(ctypes.c_void_p(hwnd), 0)
        except Exception:
            # Silent best-effort
            pass

    @staticmethod
    def _setup_event_loop():
        """Setup event loop"""
        import asyncio

        try:
            # Event loop policy is already set in main.py for the main process
            # No need to set it again here to avoid redundancy
            if os.name == 'nt':
                current_policy = asyncio.get_event_loop_policy()
                if isinstance(current_policy, asyncio.WindowsSelectorEventLoopPolicy):
                    logger.info("✅ WindowsSelectorEventLoopPolicy already set (from main.py)")
                else:
                    logger.info("ℹ️  Event loop policy will be handled by main process")
        except Exception as e:
            logger.warning(f"Failed to check event loop policy: {e}")

    @staticmethod
    def _disable_warnings():
        """Disable warnings that may cause issues"""
        import warnings
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        logger.debug("✅ Disabled deprecation warnings for PyInstaller")

# Global reference to allow graceful shutdown
class ServerManager:
    """Server manager for encapsulating server state and lifecycle"""

    def __init__(self, main_win: 'MainWindow'):
        self.main_win: MainWindow = main_win
        self.port = int(main_win.get_local_server_port())  # 初始化时保存端口
        self.uvicorn_server = None
        self.server_thread = None
        self.request_handlers = None
        self.server_ready = threading.Event()  # 服务器启动完成信号
        # Auto-restart plumbing: detect server-thread death and respawn.
        # The previous design had no liveness check, so once the uvicorn
        # server exited "normally" (e.g. after the MCP cancel-scope
        # RuntimeError swallowed by the legacy shutdown exception handler)
        # every subsequent GraphQL request from the frontend failed silently
        # and was logged as `[APIRouter] Local GraphQL error …` forever
        # (terminals/5.txt:1005-1027).
        self._health_monitor_thread: Optional[threading.Thread] = None
        self._shutdown_requested: bool = False
        self._restart_lock = threading.Lock()

    def get_server_url(self) -> str:
        """Get local server URL
        
        Returns:
            - Linux: http://<actual_ip>:<port> (for remote access)
            - macOS/Windows: http://localhost:<port> (local only)
        """
        port = int(self.main_win.get_local_server_port())
        
        # On Linux, return actual network IP for remote access
        import platform
        if platform.system().lower() == 'linux':
            try:
                import socket
                # Get actual network IP (not 127.0.0.1)
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect(("8.8.8.8", 80))  # Connect to Google DNS to get local IP
                local_ip = s.getsockname()[0]
                s.close()
                return f"http://{local_ip}:{port}"
            except Exception as e:
                logger.warning(f"Failed to get network IP on Linux: {e}, falling back to localhost")
                return f"http://localhost:{port}"
        
        # macOS/Windows: use localhost
        return f"http://localhost:{port}"

    def get_api_url(self, endpoint: str) -> str:
        """Get complete URL for API endpoint"""
        return f"{self.get_server_url()}{endpoint}"

    def start_in_thread(self):
        """Start server in a separate thread"""
        # Optimization: Set higher thread priority for faster startup
        self.server_thread = threading.Thread(target=self._run_starlette, args=(self.port,))
        self.server_thread.daemon = False  # Allow proper cleanup instead of forced termination
        self.server_thread.start()
        logger.info(f"🚀 Optimized local server starting on port {self.port} in separate thread")

        # 等待服务器就绪（最多 10 秒）
        if self.server_ready.wait(timeout=10):
            logger.info("[ServerManager] ✅ Server started successfully and event loop ready")
        else:
            logger.warning("[ServerManager] ⚠️ Server startup timeout after 10s")

        # 启动健康监控：发现 server thread 死亡后自动重启，避免
        # 前端 GraphQL 调用永远拿不到响应（terminals/5.txt:1005-1027）。
        # 注意 stop() 会设置 _shutdown_requested=True 来优雅退出监控。
        if self._health_monitor_thread is None or not self._health_monitor_thread.is_alive():
            self._shutdown_requested = False
            self._health_monitor_thread = threading.Thread(
                target=self._health_monitor_loop,
                name="LocalServerHealthMonitor",
                daemon=True,
            )
            self._health_monitor_thread.start()
            logger.debug("[ServerManager] Health monitor thread started")

    def stop(self):
        """Request Uvicorn server to shut down gracefully"""
        # Tell the health monitor to stop watching before we tear the server
        # down — otherwise it would treat this deliberate shutdown as an
        # unexpected death and respawn the server immediately.
        self._shutdown_requested = True

        if self.uvicorn_server:
            logger.info("Stopping local Starlette server...")

            # IMPORTANT: First signal the server to stop, then wait for thread completion
            # This is simpler and more reliable than complex async shutdown
            try:
                # Signal the server to stop gracefully
                self.uvicorn_server.should_exit = True
                logger.info("Server shutdown signal sent")

                # Wait for the server thread to complete
                self._sync_shutdown()

            except Exception as e:
                logger.error(f"Error during server shutdown: {e}")
                # Force shutdown as last resort
                self._force_shutdown()

            # Reset references
            self.uvicorn_server = None
            self.server_thread = None

            return True
        logger.warning("No active Uvicorn server to stop.")
        return False

    def _sync_shutdown(self):
        """Synchronous shutdown with optimized thread handling"""
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Waiting for server thread to finish...")
            
            # Use a shorter timeout and more aggressive approach
            self.server_thread.join(timeout=5.0)  # Reduced from 10s to 5s
            
            if self.server_thread.is_alive():
                logger.warning("Server thread did not finish within 5s, checking port release...")
                # Check if port is actually released even if thread is still alive
                port = int(self.main_win.get_local_server_port())
                if is_port_available("127.0.0.1", port):
                    logger.info("✅ Port released successfully despite thread still running")
                else:
                    logger.warning("⚠️  Port still occupied, may need force shutdown")
            else:
                logger.info("✅ Server thread finished successfully")

    def _force_shutdown(self):
        """Force shutdown as last resort"""
        logger.warning("Attempting force shutdown...")
        if self.server_thread and self.server_thread.is_alive():
            # This is not ideal, but sometimes necessary
            logger.warning("Force terminating server thread...")
            # Note: Python doesn't have thread.terminate(), so we rely on daemon behavior
            self.server_thread.daemon = True  # Convert to daemon for force termination

    # ------------------------------------------------------------------
    # Health monitor: detect unexpected server-thread death and respawn.
    # ------------------------------------------------------------------
    def _health_monitor_loop(self):
        """Watchdog thread: restart the Starlette server if its thread dies.

        Polls ``self.server_thread`` once per second.  When the thread exits
        without ``_shutdown_requested`` being set (i.e. an unexpected death —
        not a deliberate ``stop()`` call), the server is restarted in place so
        that the frontend's GraphQL calls keep working.
        """
        poll_interval = 1.0
        # Backing-off after consecutive restarts avoids tight loops if the
        # server crashes immediately on every start.  Caps at 30 seconds.
        consecutive_restarts = 0
        while not self._shutdown_requested:
            thread = self.server_thread
            if thread is None or not thread.is_alive():
                if self._shutdown_requested:
                    break
                # The server thread is gone but we weren't told to stop →
                # respawn it.  Guard against multiple health-monitor instances
                # racing by serialising through ``_restart_lock``.
                with self._restart_lock:
                    if self.server_thread is thread and not (
                        thread is not None and thread.is_alive()
                    ):
                        backoff = min(2 ** consecutive_restarts, 30)
                        if consecutive_restarts > 0:
                            logger.warning(
                                f"[ServerManager] ⚠️ Server thread died "
                                f"(restart #{consecutive_restarts}); "
                                f"restarting in {backoff}s"
                            )
                            # Sleep under the lock so concurrent monitors
                            # don't all sleep in parallel.
                            for _ in range(int(backoff)):
                                if self._shutdown_requested:
                                    return
                                time.sleep(1)
                        logger.error(
                            "[ServerManager] ❌ Local Starlette server died — "
                            "auto-restarting (was: 127.0.0.1:%d)" % self.port
                        )
                        self._restart_server()
                        consecutive_restarts += 1
                        continue
                    consecutive_restarts = 0
            else:
                consecutive_restarts = 0
            time.sleep(poll_interval)

    def _restart_server(self):
        """Spin up a fresh server thread, preserving the bound port."""
        # Clear the ready event so callers waiting on the next start block
        # until the new server is actually accepting connections.
        self.server_ready = threading.Event()
        self.uvicorn_server = None
        self.server_thread = threading.Thread(
            target=self._run_starlette, args=(self.port,)
        )
        self.server_thread.daemon = False
        self.server_thread.start()
        if self.server_ready.wait(timeout=10):
            logger.info(
                "[ServerManager] ✅ Auto-restarted Starlette server on "
                f"127.0.0.1:{self.port}"
            )
        else:
            logger.warning("[ServerManager] ⚠️ Auto-restart timed out after 10s")

    def _run_starlette(self, port=4668):
        """Optimized Starlette server startup method"""
        logger.info(f"🚀 Starting optimized Starlette server on port {port}")
        logger.info(f"Environment: {'PyInstaller' if mcp_server_config.is_frozen else 'Development'}")
        logger.info(f"MCP Support: {'Enabled' if mcp_server_config.has_mcp_support() else 'Disabled'}")

        if mcp_server_config.is_frozen:
            ServerOptimizer.setup_pyinstaller_environment()
            # Additionally, hide any console window to prevent transient flicker
            ServerOptimizer._hide_console_window_windows()

        # Pre-create components to reduce startup time
        request_handlers = RequestHandlers(self.main_win)
        self.request_handlers = request_handlers
        app = AppBuilder.create_app(request_handlers)

        # Platform-aware host binding strategy
        # Linux: Use 0.0.0.0 to support remote access (e.g., web deployment, Docker)
        # macOS/Windows: Use 127.0.0.1 for better security (desktop only)
        import platform
        system = platform.system().lower()
        
        # Check if remote access is enabled via environment variable
        allow_remote = os.getenv('ECAN_ALLOW_REMOTE', 'false').lower() == 'true'
        
        if system == 'linux':
            # Linux: Prioritize 0.0.0.0 for remote access support
            host_candidates = ["0.0.0.0", "127.0.0.1"]
            logger.info("🐧 Linux detected: Enabling remote access (0.0.0.0)")
        elif allow_remote:
            # Remote access enabled via ECAN_ALLOW_REMOTE=true
            host_candidates = ["0.0.0.0", "127.0.0.1"]
            logger.info(f"🖥️  Remote access enabled (ECAN_ALLOW_REMOTE=true): Using 0.0.0.0")
        else:
            # macOS/Windows: Prioritize 127.0.0.1 for security
            host_candidates = ["127.0.0.1", "0.0.0.0"]
            logger.info(f"🖥️  {system.capitalize()} detected: Using localhost binding (127.0.0.1)")

        last_err = None
        for host_bind in host_candidates:
            try:
                logger.info(f"⚡ Attempting fast startup on {host_bind}:{port}")

                # Optimized Uvicorn configuration - reduce startup overhead
                config = uvicorn.Config(
                    app=app,
                    host=host_bind,
                    port=port,
                    log_level="warning",  # Reduce log output
                    access_log=False,     # Disable access log
                    loop="asyncio",
                    # Use httptools in production for better performance, h11 in dev for debugging
                    http="h11" if mcp_server_config.is_development else "h11",  # h11 for compatibility
                    log_config=None,
                    workers=1,            # Single process mode
                    reload=False,         # Disable auto-reload
                    use_colors=False,     # Disable color output
                    # Timeout configuration
                    timeout_keep_alive=5,        # Keep-alive timeout (seconds)
                    timeout_graceful_shutdown=1, # Graceful shutdown timeout (reduced for faster logout)
                    # Concurrency limits - reduce for desktop app to prevent thread explosion
                    limit_concurrency=20,       # Max concurrent connections (reduced from 100)
                    limit_max_requests=1000,    # Recycle workers after N requests
                    # WebSocket configuration
                    ws_ping_interval=20,         # WebSocket ping interval (seconds)
                    ws_ping_timeout=20,          # WebSocket ping timeout (seconds)
                    ws_max_size=16777216,        # WebSocket max message size (16MB)
                    # Connection backlog
                    backlog=2048,                # Connection queue length
                )
                server = uvicorn.Server(config)

                self.uvicorn_server = server
                logger.info(f"✅ Server configured, starting on {host_bind}:{port}")
                
                # Run server with event loop capture for WebSocket broadcasting
                import asyncio
                async def serve_with_loop():
                    # Capture the event loop for WebSocket manager
                    loop = asyncio.get_running_loop()
                    app_ws_manager.set_event_loop(loop)
                    logger.info(f"[AppWS] Event loop captured for WebSocket broadcasting")
                    
                    # Fix sniffio AsyncLibraryNotFoundError by setting the async library context
                    # This is needed when uvicorn runs in a thread and FileResponse uses anyio
                    sniffio.current_async_library_cvar.set("asyncio")

                    # Suppress only the narrow set of harmless teardown signals
                    # that surface when MCP's StreamableHTTPSessionManager TaskGroup
                    # is unwound during event loop cleanup.
                    #
                    # Regression (2026-08-25): the previous version swallowed ANY
                    # exception whose repr contained "cancel scope", "StreamableHTTP",
                    # or "asyncgen".  The matching exception —
                    # `RuntimeError: Attempted to exit cancel scope in a different task`
                    # — actually tears down the entire asyncio task tree, which
                    # terminates the uvicorn server "normally" while requests are
                    # still in flight, and the eCan process never restarts it.  The
                    # frontend then logs `[APIRouter] Local GraphQL error …`
                    # forever (see terminals/5.txt:1005-1027).
                    #
                    # The safe swallow set is the trio of teardown signals that anyio
                    # produces when an async generator / TaskGroup is closed in a
                    # cooperating task — they are not actionable and re-raising them
                    # only clutters logs.
                    original_handler = loop.get_exception_handler()

                    _SAFE_TEARDOWN_TYPES = (
                        asyncio.CancelledError,
                        GeneratorExit,
                    )

                    def _is_safe_teardown(exc: BaseException, msg: str) -> bool:
                        if isinstance(exc, _SAFE_TEARDOWN_TYPES):
                            return True
                        # anyio's task group emits a BaseExceptionGroup whose
                        # children are CancelledError; treat those as safe.
                        if isinstance(exc, BaseExceptionGroup):
                            return all(
                                isinstance(c, _SAFE_TEARDOWN_TYPES)
                                or _is_safe_teardown(c, str(c))
                                for c in exc.exceptions
                            )
                        return False

                    def _shutdown_exception_handler(loop, context):
                        exc = context.get("exception")
                        msg = context.get("message", "")
                        if exc is not None and _is_safe_teardown(exc, msg):
                            logger.debug(
                                f"[MCP] Suppressed expected teardown signal: "
                                f"{type(exc).__name__}"
                            )
                            return
                        # Anything else — including the original
                        # "Attempted to exit cancel scope in a different task"
                        # RuntimeError — must propagate to the default handler so
                        # it shows up as a real error rather than silently killing
                        # the server.
                        if original_handler is not None:
                            original_handler(loop, context)
                        else:
                            loop.default_exception_handler(context)

                    loop.set_exception_handler(_shutdown_exception_handler)

                    # 标记服务器就绪
                    self.server_ready.set()
                    
                    # Log server access information
                    if host_bind == "0.0.0.0":
                        # Server is accessible from network
                        try:
                            import socket
                            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            s.connect(("8.8.8.8", 80))
                            local_ip = s.getsockname()[0]
                            s.close()
                            logger.info(f"🌐 Server accessible at:")
                            logger.info(f"   - Local:   http://localhost:{port}")
                            logger.info(f"   - Network: http://{local_ip}:{port}")
                        except Exception:
                            logger.info(f"🌐 Server accessible at: http://0.0.0.0:{port}")
                    else:
                        logger.info(f"🌐 Server accessible at: http://{host_bind}:{port}")
                    
                    await server.serve()
                
                asyncio.run(serve_with_loop())
                logger.info(f"✅ Uvicorn server exited normally on {host_bind}:{port}")
                last_err = None
                break
            except OSError as e:
                import errno
                if e.errno == errno.EADDRINUSE:
                    # 端口被占用，不要尝试其他 host
                    logger.error(f"❌ Port {port} is already in use")
                    raise RuntimeError(f"Port {port} is already in use") from e
                else:
                    # 其他网络错误，尝试下一个 host
                    last_err = str(e)
                    logger.warning(f"⚠️  Failed to bind {host_bind}:{port} - {e}")
                    continue
            except Exception as e:
                last_err = str(e)
                logger.error(f"❌ Unexpected error on {host_bind}:{port} - {e}")
                import traceback
                logger.error(traceback.format_exc())
                raise

        if last_err:
            logger.error(f"❌ All server startup attempts failed. Last error: {last_err}")
            raise RuntimeError(f"Server startup failed: {last_err}")

# ==================== Global Instance and Entry Point ====================

# Global server manager instance
server_manager_instance = None

def start_local_server_in_thread(mwin: 'MainWindow'):
    """Start local server"""
    global server_manager_instance
    if server_manager_instance is None:
        server_manager_instance = ServerManager(mwin)
        server_manager_instance.start_in_thread()
    else:
        server_manager_instance.main_win = mwin
        if getattr(server_manager_instance, 'request_handlers', None) is not None:
            try:
                server_manager_instance.request_handlers.set_main_win(mwin)
            except Exception:
                pass

    # MCP session warmup will be triggered by the first MCP call
    # We don't pre-warmup here because:
    # 1. The server runs in its own thread with its own event loop
    # 2. MCP calls happen in the main thread's event loop
    # 3. Creating session in wrong event loop causes call_tool to hang
    #
    # Instead, we set a flag to trigger warmup on first MCP call
    try:
        from agent.mcp.local_client import mark_needs_warmup
        mark_needs_warmup()
        logger.info("MCP session will be warmed up on first call")
    except Exception as e:
        logger.debug(f"MCP warmup flag not set: {e}")


class _EarlyMainWin:
    def __init__(self, port: int):
        self._local_server_port = str(port)

    def get_local_server_port(self):
        return self._local_server_port


def start_local_server_early(port: int = 4668):
    """Start local server without relying on MainWindow.

    This is intended to be called from main.py before WebGUI is created.
    MainWindow can be injected later by calling start_local_server_in_thread(main_win).
    """
    start_local_server_in_thread(_EarlyMainWin(int(port)))

def is_port_available(host: str, port: int) -> bool:
    """Check if port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            result = sock.connect_ex((host, port))
            return result != 0  # 0 means connection successful (port occupied)
    except Exception:
        return False

def wait_for_port_release(host: str, port: int, timeout: float = 10.0) -> bool:
    """Wait for port to be released"""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if is_port_available(host, port):
            logger.info(f"✅ Port {port} on {host} is now available")
            return True
        time.sleep(0.5)
    logger.warning(f"⚠️  Port {port} on {host} is still occupied after {timeout}s")
    return False

def stop_local_server():
    """Stop local server"""
    global server_manager_instance
    if server_manager_instance:
        result = server_manager_instance.stop()

        # Wait for port to be released
        if result:
            port = int(server_manager_instance.main_win.get_local_server_port())
            logger.info(f"Waiting for port {port} to be released...")
            wait_for_port_release("127.0.0.1", port, timeout=10.0)

        # Clear the global instance to allow clean restart
        server_manager_instance = None
        logger.info("✅ Global server manager instance cleared")
        return result
    return False
