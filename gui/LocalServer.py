import threading
import asyncio
import sys
import os
import traceback
import uuid
import json
import socket
import time
from typing import Optional
from starlette.applications import Starlette
import typing

from utils.logger_helper import logger_helper as logger
from utils.gui_dispatch import run_on_main_thread

if typing.TYPE_CHECKING:
    from gui.MainGUI import MainWindow

from starlette.applications import Starlette
from starlette.responses import JSONResponse, FileResponse, StreamingResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Route, Mount, WebSocketRoute
from starlette.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocket, WebSocketDisconnect
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
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._connections: dict[str, set[WebSocket]] = {}  # channel_id -> set of websockets
                    cls._instance._all_connections: set[WebSocket] = set()
                    cls._instance._event_loop = None
        return cls._instance
    
    def set_event_loop(self, loop):
        """Set the event loop for async operations from sync context."""
        self._event_loop = loop
    
    async def connect(self, websocket: WebSocket, channel_id: str = None):
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self._all_connections.add(websocket)
        if channel_id:
            if channel_id not in self._connections:
                self._connections[channel_id] = set()
            self._connections[channel_id].add(websocket)
        logger.info(f"[SkillEditorWS] Client connected. Channel: {channel_id}, Total connections: {len(self._all_connections)}")
    
    def disconnect(self, websocket: WebSocket, channel_id: str = None):
        """Remove a WebSocket connection."""
        self._all_connections.discard(websocket)
        if channel_id and channel_id in self._connections:
            self._connections[channel_id].discard(websocket)
            if not self._connections[channel_id]:
                del self._connections[channel_id]
        logger.info(f"[SkillEditorWS] Client disconnected. Total connections: {len(self._all_connections)}")
    
    async def broadcast(self, message: dict, channel_id: str = None):
        """Broadcast a message to all connections or a specific channel."""
        message_str = json.dumps(message)
        msg_type = message.get('type', 'unknown')
        
        if channel_id and channel_id in self._connections:
            targets = self._connections[channel_id]
        else:
            targets = self._all_connections
        
        logger.info(f"[SkillEditorWS] 📤 Broadcasting {msg_type} to {len(targets)} clients (channel: {channel_id})")
        
        disconnected = []
        for websocket in targets:
            try:
                await websocket.send_text(message_str)
            except Exception as e:
                logger.warning(f"[SkillEditorWS] ❌ Failed to send message: {e}")
                disconnected.append(websocket)
        
        # Clean up disconnected clients
        for ws in disconnected:
            self.disconnect(ws, channel_id)
    
    async def send_to_session(self, session_id: str, message: dict):
        """Send a message to a specific session channel."""
        await self.broadcast(message, channel_id=f"session:{session_id}")
    
    async def send_chat_chunk(self, session_id: str, message_id: str, chunk: str, chunk_index: int):
        """Send a chat streaming chunk."""
        logger.debug(f"[SkillEditorWS] 📝 Sending chunk #{chunk_index} for message {message_id[:8]}... ({len(chunk)} chars)")
        # Use same event type as AppSync for compatibility
        await self.send_to_session(session_id, {
            "type": "skill_editor.chat.stream_chunk",
            "eventType": "skill_editor.chat.stream_chunk",
            "sessionId": session_id,
            "messageId": message_id,
            "payload": {
                "chunk": chunk,
                "chunkIndex": chunk_index
            }
        })
    
    async def send_chat_done(self, session_id: str, message_id: str, full_content: str):
        """Send chat completion message."""
        logger.info(f"[SkillEditorWS] ✅ Sending done for message {message_id[:8]}... ({len(full_content)} chars total)")
        logger.info(f"[SkillEditorWS] ✅ full content:::{(full_content)}")
        # Use same event type as AppSync for compatibility
        await self.send_to_session(session_id, {
            "type": "skill_editor.chat.stream_end",
            "eventType": "skill_editor.chat.stream_end",
            "sessionId": session_id,
            "payload": {
                "messageId": message_id,
                "fullContent": full_content
            }
        })
    
    async def send_canvas_command(self, session_id: str, command_type: str, payload: dict):
        """Send a canvas command."""
        # Use same event type as AppSync for compatibility
        await self.send_to_session(session_id, {
            "type": "skill_editor.event",
            "eventType": "skill_editor.event",
            "sessionId": session_id,
            "payload": {
                "commandType": command_type,
                **payload
            }
        })
    
    async def send_flowgram(self, session_id: str, flowgram: dict):
        """Send a flowgram event to load on canvas."""
        logger.info(f"[AppWS] 🎨 Sending flowgram to session {session_id} ({len(flowgram.get('nodes', []))} nodes)")
        await self.send_to_session(session_id, {
            "type": "skill_editor.event",
            "eventType": "skill_editor.event",
            "sessionId": session_id,
            "payload": {
                "type": "canvas.load_flowgram_data",  # Event type for canvas handler
                "commandType": "load_flowgram",
                "flowgram": flowgram
            }
        })
    
    # ==================== Data Update Events ====================
    
    async def send_update_agents(self, agents: list):
        """Broadcast agents update to all clients."""
        await self.broadcast({
            "type": "update_agents",
            "eventType": "update_agents",
            "payload": {"agents": agents}
        })
    
    async def send_update_skills(self, skills: list):
        """Broadcast skills update to all clients."""
        await self.broadcast({
            "type": "update_skills",
            "eventType": "update_skills",
            "payload": {"skills": skills}
        })
    
    async def send_update_tasks(self, tasks: list):
        """Broadcast tasks update to all clients."""
        await self.broadcast({
            "type": "update_tasks",
            "eventType": "update_tasks",
            "payload": {"tasks": tasks}
        })
    
    async def send_update_tools(self, tools: list):
        """Broadcast tools update to all clients."""
        await self.broadcast({
            "type": "update_tools",
            "eventType": "update_tools",
            "payload": {"tools": tools}
        })
    
    async def send_update_settings(self, settings: dict):
        """Broadcast settings update to all clients."""
        await self.broadcast({
            "type": "update_settings",
            "eventType": "update_settings",
            "payload": {"settings": settings}
        })
    
    async def send_update_vehicles(self, vehicles: list):
        """Broadcast vehicles update to all clients."""
        await self.broadcast({
            "type": "update_vehicles",
            "eventType": "update_vehicles",
            "payload": {"vehicles": vehicles}
        })
    
    async def send_update_knowledge(self, knowledge: list):
        """Broadcast knowledge update to all clients."""
        await self.broadcast({
            "type": "update_knowledge",
            "eventType": "update_knowledge",
            "payload": {"knowledge": knowledge}
        })
    
    async def send_update_chats(self, chats: list):
        """Broadcast chats update to all clients."""
        await self.broadcast({
            "type": "update_chats",
            "eventType": "update_chats",
            "payload": {"chats": chats}
        })
    
    async def send_update_all(self, data: dict):
        """Broadcast full data update to all clients."""
        await self.broadcast({
            "type": "update_all",
            "eventType": "update_all",
            "payload": data
        })
    
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

    # ==================== Chat Events ====================
    
    async def send_push_chat_message(self, chat_id: str, message: dict):
        """Push a chat message to clients."""
        await self.broadcast({
            "type": "push_chat_message",
            "eventType": "push_chat_message",
            "payload": {"chatId": chat_id, "message": message}
        }, channel_id=f"chat:{chat_id}")
    
    async def send_push_chat_notification(self, chat_id: str, content: dict, is_read: bool, timestamp: int, uid: str):
        """Push a chat notification to clients."""
        await self.broadcast({
            "type": "push_chat_notification",
            "eventType": "push_chat_notification",
            "payload": {
                "chatId": chat_id,
                "content": content,
                "isRead": is_read,
                "timestamp": timestamp,
                "uid": uid
            }
        }, channel_id=f"chat:{chat_id}")
    
    # ==================== Skill Run Events ====================
    
    async def send_update_skill_run_stat(self, agent_task_id: str, current_node: str, status: str, langgraph_state: dict, timestamp: int = None):
        """Push skill run statistics update."""
        logger.debug(f"[AppWS] 📊 Sending skill run stat: task={agent_task_id}, node={current_node}, status={status}")
        await self.broadcast({
            "type": "update_skill_run_stat",
            "eventType": "update_skill_run_stat",
            "payload": {
                "agentTaskId": agent_task_id,
                "currentNode": current_node,
                "current_node": current_node,  # Legacy compatibility
                "status": status,
                "langgraphState": langgraph_state,
                "nodeState": langgraph_state,  # Legacy compatibility
                "timestamp": timestamp
            }
        }, channel_id=f"task:{agent_task_id}")
    
    async def send_update_task_stat(self, agent_task_id: str, langgraph_state: dict, timestamp: int = None):
        """Push task statistics update."""
        await self.broadcast({
            "type": "update_tasks_stat",
            "eventType": "update_tasks_stat",
            "payload": {
                "agentTaskId": agent_task_id,
                "langgraphState": langgraph_state,
                "timestamp": timestamp
            }
        }, channel_id=f"task:{agent_task_id}")
    
    # ==================== LightRAG Events ====================
    
    async def send_lightrag_chunk(self, stream_id: str, chunk_data: str):
        """Push LightRAG stream chunk."""
        await self.broadcast({
            "type": "lightrag.queryStream.chunk",
            "eventType": "lightrag.queryStream.chunk",
            "payload": {"id": stream_id, "chunk": chunk_data}
        }, channel_id=f"lightrag:{stream_id}")
    
    async def send_lightrag_done(self, stream_id: str):
        """Push LightRAG stream done event."""
        await self.broadcast({
            "type": "lightrag.queryStream.done",
            "eventType": "lightrag.queryStream.done",
            "payload": {"id": stream_id}
        }, channel_id=f"lightrag:{stream_id}")
    
    async def send_lightrag_error(self, stream_id: str, error: str):
        """Push LightRAG stream error event."""
        await self.broadcast({
            "type": "lightrag.queryStream.error",
            "eventType": "lightrag.queryStream.error",
            "payload": {"id": stream_id, "error": error}
        }, channel_id=f"lightrag:{stream_id}")
    
    # ==================== UI Events ====================
    
    async def send_refresh_dashboard(self, data: dict):
        """Push dashboard refresh event."""
        await self.broadcast({
            "type": "refresh_dashboard",
            "eventType": "refresh_dashboard",
            "payload": data
        })
    
    async def send_update_screens(self, screens: list):
        """Push screens update event."""
        await self.broadcast({
            "type": "update_screens",
            "eventType": "update_screens",
            "payload": {"screens": screens}
        })
    
    # ==================== Sync Helper for IPCAPI ====================
    
    def broadcast_sync(self, event_type: str, payload: dict, channel_id: str = None):
        """Synchronous wrapper for broadcasting from IPCAPI (runs in thread)."""
        message = {
            "type": event_type,
            "eventType": event_type,
            "payload": payload
        }
        
        if self._event_loop and self._event_loop.is_running():
            # Schedule the coroutine on the event loop
            import asyncio
            future = asyncio.run_coroutine_threadsafe(
                self.broadcast(message, channel_id),
                self._event_loop
            )
            try:
                # Wait briefly for completion (non-blocking for caller)
                future.result(timeout=0.5)
            except Exception as e:
                logger.warning(f"[AppWS] broadcast_sync timeout/error: {e}")
        else:
            logger.warning(f"[AppWS] No event loop available for broadcast_sync, event: {event_type}")


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
    
    async def ollama_rerank_proxy(self, request):
        """
        Ollama Rerank Proxy - Delegates to the ollama_proxy module.
        """
        from gui.ollama_proxy import ollama_rerank_proxy
        return await ollama_rerank_proxy(request)

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

            # Extract token from Authorization header (AppSync-style) and inject into params.token
            # so IPC registry can validate it.
            if 'token' not in request_params or not request_params.get('token'):
                auth_header = request.headers.get('authorization') or request.headers.get('Authorization')
                if auth_header and isinstance(auth_header, str):
                    parts = auth_header.split(' ', 1)
                    if len(parts) == 2 and parts[0].lower() == 'bearer':
                        bearer_token = parts[1].strip()
                        if bearer_token:
                            request_params['token'] = bearer_token
            
            # 将 extensions 中的其他参数也合并进来（排除 method 和 operationName）
            for key, value in extensions.items():
                if key not in ('method', 'operationName'):
                    request_params[key] = value
            
            logger.info(f"[GraphQL] 📦 Parameters: {list(request_params.keys())}")
            
            # 使用 IPCHandlerRegistry 统一处理
            from gui.ipc.registry import IPCHandlerRegistry
            result_data = IPCHandlerRegistry.handle_graphql_request(method, request_params)
            
            # 使用 operation_name 作为响应的字段名（如果没有则使用 method）
            response_field_name = operation_name or method
            
            # 包装为 GraphQL 响应格式
            logger.info(f"[GraphQL] ✅ Success: {response_field_name}")
            return JSONResponse({
                "data": {response_field_name: result_data}
            }, status_code=200)
            
        except Exception as e:
            logger.error(f"[GraphQL] ❌ Error handling request: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return JSONResponse({
                "errors": [{"message": str(e)}]
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
        run_on_main_thread(lambda: self.main_win.task_queue.put({
            "task_id": task_id,
            "data": incoming_data
        }))
        result = await asyncio.wait_for(future, timeout=30)
        return JSONResponse({"status": "success", "result": result})

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
        # Test all pub/sub event types
        test_events = [
            # Data update events
            ("update_agents", {"agents": [{"id": test_id, "name": "Test Agent", "status": "active"}]}),
            ("update_skills", {"skills": [{"id": test_id, "name": "Test Skill", "level": 1}]}),
            ("update_tasks", {"tasks": [{"id": test_id, "name": "Test Task", "status": "pending"}]}),
            ("update_tools", {"tools": [{"id": test_id, "name": "Test Tool", "tool_type": "test"}]}),
            ("update_settings", {"settings": {"test_key": "test_value", "timestamp": timestamp}}),
            ("update_vehicles", {"vehicles": [{"id": test_id, "name": "Test Vehicle", "status": "idle"}]}),
            ("update_knowledge", {"knowledge": [{"id": test_id, "name": "Test Knowledge", "type": "test"}]}),
            ("update_chats", {"chats": [{"id": test_id, "name": "Test Chat"}]}),
            ("update_all", {"test": True, "timestamp": timestamp}),
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
            ("skill_editor.chat.error", {"sessionId": test_id, "error": "Test error", "code": "TEST_ERROR"}),
            ("skill_editor.event", {"sessionId": test_id, "commandType": "test", "type": "canvas_command", "payload": {"action": "test"}}),
            # UI events
            ("refresh_dashboard", {"source": "local_ws_test", "timestamp": timestamp}),
            ("update_screens", {"screens": [{"id": test_id, "name": "Test Screen"}]}),
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
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
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
        owner = main_window.get_username()
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
        """Clean up MCP session manager resources."""
        try:
            if MCPHandler._session_manager_context:
                logger.info("🧹 [MCP] Cleaning up session manager context...")
                # Avoid __aexit__ in a different task - just reset the reference
                # The context manager will be cleaned up when the original task exits
                MCPHandler._session_manager_context = None
                logger.info("✅ [MCP] Session manager context cleaned up")
        except Exception as e:
            logger.debug(f"⚠️  [MCP] Error cleaning up session manager context: {e}")
        
        try:
            if MCPHandler._session_manager_instance:
                logger.info("🧹 [MCP] Cleaning up session manager instance...")
                # Reset the instance
                MCPHandler._session_manager_instance = None
                logger.info("✅ [MCP] Session manager instance cleaned up")
        except Exception as e:
            logger.warning(f"⚠️  [MCP] Error cleaning up session manager instance: {e}")
        
        # Reset initialization flag
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
            Route("/api/local-ws-test", local_ws_test, methods=['GET', 'POST']),
            Route("/api/c2l-ws-test", c2l_ws_test, methods=['GET', 'POST']),
            Route("/graphql", self.request_handlers.graphql_handler, methods=['POST']),
            WebSocketRoute("/ws/skill-editor", self.request_handlers.skill_editor_websocket),
            Route('/api/initialize', self.request_handlers.initialize, methods=['POST']),
            Route('/api/avatar', self.request_handlers.serve_avatar, methods=['GET']),
            Route('/api/rerank', self.request_handlers.ollama_rerank_proxy, methods=['POST'])
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
        return routes # ==================== Application Creation ====================


class AppBuilder:
    """Starlette application builder"""

    @staticmethod
    def create_app(request_handlers):
        """Create Starlette application"""
        route_builder = RouteBuilder(request_handlers)
        routes = route_builder.create_routes()

        if os.path.isdir(static_dir):
            routes.append(Mount('/', StaticFiles(directory=static_dir, html=True), name='static'))
        else:
            logger.warning(f"Static dir missing, skipping mount: {static_dir}")

        app_config = {
            'routes': routes,
            'debug': mcp_server_config.is_development
        }

        logger.info("🔧 Created Starlette app of LcoalServer")
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

    def get_server_url(self) -> str:
        """Get local server URL"""
        port = int(self.main_win.get_local_server_port())
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

    def stop(self):
        """Request Uvicorn server to shut down gracefully"""
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

        # Optimized host binding strategy - prioritize 127.0.0.1
        host_candidates = ["127.0.0.1", "0.0.0.0"]

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
                    timeout_graceful_shutdown=3, # Graceful shutdown timeout
                    # Concurrency limits
                    limit_concurrency=100,       # Max concurrent connections (desktop app)
                    limit_max_requests=None,     # No request limit (long-running)
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
                    
                    # 标记服务器就绪
                    self.server_ready.set()
                    
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
