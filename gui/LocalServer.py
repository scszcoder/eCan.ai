import threading
import asyncio
import sys
import os
import traceback
import uuid
import json
import socket
import time
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
class SkillEditorWebSocketManager:
    """Manages WebSocket connections for skill editor streaming events."""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._connections: dict[str, set[WebSocket]] = {}  # channel_id -> set of websockets
                    cls._instance._all_connections: set[WebSocket] = set()
        return cls._instance
    
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
        logger.info(f"[SkillEditorWS] 🎨 Sending flowgram to session {session_id} ({len(flowgram.get('nodes', []))} nodes)")
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


# Global WebSocket manager instance
skill_editor_ws_manager = SkillEditorWebSocketManager()

static_dir = os.path.join(base_dir, 'agent', 'agent_files')
if not os.path.isdir(static_dir):
    # Handle path differences between development and bundled app: fallback to relative path
    alt_dir = os.path.join(os.getcwd(), 'agent', 'agent_files')
    if os.path.isdir(alt_dir):
        static_dir = alt_dir

# Endpoint to serve images
class RequestHandlers:
    """Encapsulates all request handling logic"""

    def __init__(self, main_win: 'MainWindow'):
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
        GraphQL endpoint for skill editor requests.
        Translates GraphQL queries/mutations to IPC handler calls.
        """
        try:
            body = await request.json()
            query = body.get('query', '')
            variables = body.get('variables', {})
            
            logger.info(f"[GraphQL] 📥 Received request: {query[:100]}...")
            
            # Parse the GraphQL operation to determine which IPC handler to call
            result = await self._handle_graphql_operation(query, variables)
            
            return JSONResponse({
                "data": result
            }, status_code=200)
            
        except Exception as e:
            logger.error(f"[GraphQL] Error handling request: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return JSONResponse({
                "errors": [{"message": str(e)}]
            }, status_code=200)  # GraphQL returns 200 even for errors

    async def _handle_graphql_operation(self, query: str, variables: dict):
        """
        Route GraphQL operations to appropriate IPC handlers.
        """
        from gui.ipc.w2p_handlers.skill_editor_chat_handler import (
            _chat_store, ChatMessage, ChatRole, _process_chat_message
        )
        from gui.ipc.w2p_handlers.node_state_schema_handler import NODE_STATE_JSON_SCHEMA
        import time
        import uuid
        
        query_lower = query.lower()
        
        # Node State Schema
        if 'getnodestateschema' in query_lower:
            return {
                "getNodeStateSchema": {
                    "schemaVersion": "1.0.0",
                    "schema": NODE_STATE_JSON_SCHEMA
                }
            }
        
        # Skill Editor Chat Operations
        elif 'getskilleditorchatsessions' in query_lower:
            # Get all chat sessions
            sessions = _chat_store.get_all_sessions()
            return {
                "getSkillEditorChatSessions": [s.to_dict() for s in sessions]
            }
        
        elif 'getskilleditorchathist' in query_lower:
            # Get chat history for a session
            session_id = variables.get('sessionId', '')
            limit = variables.get('limit')
            offset = variables.get('offset', 0)
            
            session = _chat_store.get_session(session_id)
            if not session:
                return {"getSkillEditorChatHistory": []}
            
            messages = session.messages[offset:]
            if limit:
                messages = messages[:limit]
            
            return {
                "getSkillEditorChatHistory": [
                    {
                        "id": m.id,
                        "role": m.role.value,
                        "content": m.content,
                        "timestamp": m.timestamp,
                        "attachments": m.attachments,
                        "metadata": m.metadata
                    }
                    for m in messages
                ]
            }
        
        elif 'createskilleditorchatsession' in query_lower:
            # Create a new chat session
            input_data = variables.get('input', {})
            name = input_data.get('name', 'New Chat')
            flowgram_id = input_data.get('flowgramId')
            
            session = _chat_store.create_session(name=name, flowgram_id=flowgram_id)
            return {
                "createSkillEditorChatSession": session.to_dict()
            }
        
        elif 'sendskilleditorchatmessage' in query_lower:
            # Send a chat message
            input_data = variables.get('input', {})
            session_id = input_data.get('sessionId')
            content = input_data.get('content', '')
            canvas_context = input_data.get('canvasContext')
            clarification_responses = input_data.get('clarificationResponses')
            
            session = _chat_store.get_session(session_id)
            if not session:
                session = _chat_store.create_session()
                session_id = session.id
            
            # Create user message
            user_message = ChatMessage(
                id=str(uuid.uuid4()),
                role=ChatRole.USER,
                content=content,
                timestamp=int(time.time() * 1000),
                attachments=input_data.get('attachments', []),
                metadata={
                    "canvasContext": canvas_context,
                    "clarificationResponses": clarification_responses
                }
            )
            _chat_store.add_message(session_id, user_message)
            
            # Process with LLM agent - use async version since we're in async context
            assistant_message_id = str(uuid.uuid4())
            chunk_index = [0]  # Use list to allow mutation in nested function
            
            async def on_event(event: dict):
                """Stream events via WebSocket."""
                try:
                    if not isinstance(event, dict):
                        return
                    event_type = event.get("type")
                    logger.debug(f"[GraphQL] 🔔 Agent event: type={event_type}")
                    
                    data = event.get("data") or {}
                    
                    # Handle flowgram events - send to canvas
                    if event_type == "flowgram":
                        flowgram_data = data
                        if flowgram_data:
                            logger.info(f"[GraphQL] 🎨 Sending flowgram to canvas via WebSocket")
                            await skill_editor_ws_manager.send_flowgram(
                                session_id=session_id,
                                flowgram=flowgram_data
                            )
                        return
                    
                    # Handle clarification events
                    if event_type == "clarification":
                        logger.info(f"[GraphQL] ❓ Sending clarification event via WebSocket")
                        await skill_editor_ws_manager.send_canvas_command(
                            session_id=session_id,
                            command_type="clarification",
                            payload={"questions": data.get("questions", [])}
                        )
                        return
                    
                    # Handle plan events
                    if event_type == "plan":
                        logger.info(f"[GraphQL] 📋 Sending plan event via WebSocket")
                        await skill_editor_ws_manager.send_canvas_command(
                            session_id=session_id,
                            command_type="plan",
                            payload={"plan": data}
                        )
                        return
                    
                    # Handle progress/chunk events - stream text
                    if event_type not in ["progress", "chunk"]:
                        return
                    
                    chunk_text = data.get("message") if event_type == "progress" else data.get("content")
                    
                    if not isinstance(chunk_text, str) or not chunk_text.strip():
                        return
                    
                    logger.debug(f"[GraphQL] 📤 Streaming chunk #{chunk_index[0]} ({len(chunk_text)} chars)")
                    await skill_editor_ws_manager.send_chat_chunk(
                        session_id=session_id,
                        message_id=assistant_message_id,
                        chunk=chunk_text,
                        chunk_index=chunk_index[0]
                    )
                    chunk_index[0] += 1
                except Exception as e:
                    logger.warning(f"[GraphQL] ❌ Error sending event via WebSocket: {e}")
            
            try:
                from agent.skill_editor import get_skill_editor_agent
                agent = get_skill_editor_agent()
                
                # Restore agent state from session
                if session.pipeline_state and session.pipeline_state != "idle":
                    agent.restore_state(
                        pipeline_state=session.pipeline_state,
                        current_plan=session.current_plan,
                        current_request=session.current_request
                    )
                
                # Call async method directly with streaming callback
                response = await agent.process_message(
                    message=content,
                    canvas_context=canvas_context,
                    session_id=session_id,
                    clarification_responses=clarification_responses,
                    on_event=on_event
                )
                
                agent_result = {
                    "message": response.message,
                    "intent": response.intent.value if response.intent else None,
                    "state": response.metadata.get("state", "complete") if response.metadata else "complete",
                }
                
                if response.clarification:
                    agent_result["clarification"] = [q.model_dump() for q in response.clarification]
                if response.plan:
                    agent_result["plan"] = response.plan.model_dump()
                if response.flowgram:
                    agent_result["flowgram"] = response.flowgram.model_dump()
                if response.validation:
                    agent_result["validation"] = response.validation.model_dump()
                
                # Save agent state back to session
                session.pipeline_state = agent.pipeline_state.value
                session.current_plan = agent.current_plan.model_dump() if agent.current_plan else None
                session.current_request = agent.current_request
                _chat_store.update_session(session)
                
            except Exception as e:
                logger.warning(f"[GraphQL] Agent processing failed, using fallback: {e}")
                # Fallback response
                agent_result = {
                    "message": "I'm here to help you build workflows. What would you like to create?",
                    "state": "complete"
                }
            
            # Create assistant message
            assistant_message = ChatMessage(
                id=assistant_message_id,  # Use the same ID we used for streaming
                role=ChatRole.ASSISTANT,
                content=agent_result.get("message", ""),
                timestamp=int(time.time() * 1000),
                metadata={
                    "state": agent_result.get("state"),
                    "intent": agent_result.get("intent"),
                }
            )
            _chat_store.add_message(session_id, assistant_message)
            
            # Send completion message via WebSocket
            await skill_editor_ws_manager.send_chat_done(
                session_id=session_id,
                message_id=assistant_message_id,
                full_content=agent_result.get("message", "")
            )
            
            return {
                "sendSkillEditorChatMessage": {
                    "message": {
                        "id": assistant_message.id,
                        "role": assistant_message.role.value,
                        "content": assistant_message.content,
                        "timestamp": assistant_message.timestamp,
                        "metadata": assistant_message.metadata
                    },
                    "sessionId": session_id,
                    "state": agent_result.get("state", "complete"),
                    "clarification": agent_result.get("clarification"),
                    "plan": agent_result.get("plan"),
                    "flowgram": agent_result.get("flowgram"),
                    "validation": agent_result.get("validation")
                }
            }
        
        elif 'cancelskilleditorchatgeneration' in query_lower:
            session_id = variables.get('sessionId', '')
            was_active = _chat_store.is_generation_active(session_id)
            _chat_store.set_generation_active(session_id, False)
            return {
                "cancelSkillEditorChatGeneration": was_active
            }
        
        elif 'deleteskilleditorchatsession' in query_lower:
            session_id = variables.get('sessionId', '')
            deleted = _chat_store.delete_session(session_id)
            return {
                "deleteSkillEditorChatSession": deleted
            }
        
        # Editor Cache Operations
        elif 'geteditorcache' in query_lower:
            # Return empty cache for now - can be enhanced later
            return {
                "getEditorCache": {
                    "cacheData": None,
                    "recentFiles": []
                }
            }
        
        elif 'saveeditorcache' in query_lower:
            # Accept but don't persist for now
            return {
                "saveEditorCache": {"success": True}
            }
        
        elif 'cleareditorcache' in query_lower:
            return {
                "clearEditorCache": True
            }
        
        # File Operations - direct file I/O
        elif 'openskillfile' in query_lower or 'readskillfile' in query_lower:
            file_path = variables.get('filePath', '')
            if not file_path:
                raise Exception("filePath is required")
            
            if not os.path.isabs(file_path):
                from config.app_info import app_info
                file_path = os.path.join(app_info.appdata_path, file_path)
            
            if not os.path.exists(file_path):
                raise Exception(f"File not found: {file_path}")
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            skill_name = variables.get('skillName') or file_name.replace('_skill.json', '').replace('.json', '')
            
            result = {
                "content": content,
                "filePath": file_path,
                "fileName": file_name,
                "fileSize": file_size,
                "skillName": skill_name
            }
            
            if 'openskillfile' in query_lower:
                return {"openSkillFile": result}
            else:
                return {"readSkillFile": result}
        
        elif 'writeskillfile' in query_lower:
            file_path = variables.get('filePath', '')
            content = variables.get('content', '')
            
            if not file_path:
                raise Exception("filePath is required")
            
            if not os.path.isabs(file_path):
                from config.app_info import app_info
                file_path = os.path.join(app_info.appdata_path, file_path)
            
            # Ensure directory exists
            dir_path = os.path.dirname(file_path)
            if dir_path:
                os.makedirs(dir_path, exist_ok=True)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return {"writeSkillFile": {"success": True, "filePath": file_path}}
        
        # LLM Provider Operations
        elif 'getllmproviders' in query_lower:
            try:
                from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
                from gui.ollama_utils import merge_ollama_models_to_providers
                
                llm_manager = get_llm_manager()
                providers = llm_manager.get_all_providers() if llm_manager else []
                providers = merge_ollama_models_to_providers(providers, provider_type='llm')
                
                return {
                    "getLlmProviders": {
                        "providers": providers,
                        "message": "LLM providers retrieved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting LLM providers: {e}")
                return {
                    "getLlmProviders": {
                        "providers": [],
                        "message": f"Error: {str(e)}"
                    }
                }
        
        elif 'getllmproviderswithcredentials' in query_lower:
            # This is used by skill editor to get providers with credential status
            try:
                from gui.ipc.w2p_handlers.llm_handler import get_llm_manager
                from gui.ollama_utils import merge_ollama_models_to_providers
                
                llm_manager = get_llm_manager()
                providers = llm_manager.get_all_providers() if llm_manager else []
                providers = merge_ollama_models_to_providers(providers, provider_type='llm')
                
                # Add credential status to each provider
                for provider in providers:
                    env_vars = provider.get('api_key_env_vars', [])
                    has_credentials = False
                    if env_vars and llm_manager:
                        for env_var in env_vars:
                            if llm_manager.get_api_key(env_var):
                                has_credentials = True
                                break
                    provider['has_credentials'] = has_credentials
                
                return {
                    "getLlmProvidersWithCredentials": {
                        "providers": providers,
                        "message": "LLM providers with credentials retrieved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting LLM providers with credentials: {e}")
                return {
                    "getLlmProvidersWithCredentials": {
                        "providers": [],
                        "message": f"Error: {str(e)}"
                    }
                }
        
        # Settings Operations
        elif 'getsettings' in query_lower:
            try:
                from gui.ipc.context_bridge import get_handler_context
                ctx = get_handler_context(None, None)
                if ctx and ctx.get_config_manager():
                    general_settings = ctx.get_config_manager().general_settings
                    settings = general_settings.data.copy() if general_settings else {}
                else:
                    settings = {}
                
                return {
                    "getSettings": {
                        "settings": settings,
                        "message": "Settings retrieved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting settings: {e}")
                return {
                    "getSettings": {
                        "settings": {},
                        "message": f"Error: {str(e)}"
                    }
                }
        
        elif 'savesettings' in query_lower:
            try:
                input_data = variables.get('input', {})
                settings_data = input_data.get('settings', {})
                
                from gui.ipc.context_bridge import get_handler_context
                ctx = get_handler_context(None, None)
                if ctx and ctx.get_config_manager():
                    general_settings = ctx.get_config_manager().general_settings
                    if general_settings:
                        for key, value in settings_data.items():
                            general_settings.set(key, value)
                        general_settings.save()
                
                return {
                    "saveSettings": {
                        "success": True,
                        "message": "Settings saved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error saving settings: {e}")
                return {
                    "saveSettings": {
                        "success": False,
                        "message": f"Error: {str(e)}"
                    }
                }
        
        # Initialization Progress
        elif 'getinitializationprogress' in query_lower:
            try:
                from app_context import AppContext
                main_window = AppContext.get_main_window()
                
                if main_window and hasattr(main_window, 'get_main_window_safely'):
                    is_ready = main_window.get_main_window_safely()
                else:
                    is_ready = main_window is not None
                
                return {
                    "getInitializationProgress": {
                        "ui_ready": is_ready,
                        "critical_services_ready": is_ready,
                        "async_init_complete": is_ready,
                        "fully_ready": is_ready,
                        "sync_init_complete": is_ready,
                        "message": "Ready" if is_ready else "Initializing..."
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting initialization progress: {e}")
                return {
                    "getInitializationProgress": {
                        "ui_ready": False,
                        "critical_services_ready": False,
                        "async_init_complete": False,
                        "fully_ready": False,
                        "sync_init_complete": False,
                        "message": f"Error: {str(e)}"
                    }
                }
        
        # Embedding Provider Operations
        elif 'getembeddingproviders' in query_lower:
            try:
                from gui.ipc.w2p_handlers.llm_handler import get_embedding_manager
                from gui.ollama_utils import merge_ollama_models_to_providers
                
                embedding_manager = get_embedding_manager()
                providers = embedding_manager.get_all_providers() if embedding_manager else []
                providers = merge_ollama_models_to_providers(providers, provider_type='embedding')
                
                return {
                    "getEmbeddingProviders": {
                        "providers": providers,
                        "message": "Embedding providers retrieved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting embedding providers: {e}")
                return {
                    "getEmbeddingProviders": {
                        "providers": [],
                        "message": f"Error: {str(e)}"
                    }
                }
        
        # Rerank Provider Operations
        elif 'getrerankproviders' in query_lower:
            try:
                from gui.ipc.w2p_handlers.llm_handler import get_rerank_manager
                
                rerank_manager = get_rerank_manager()
                providers = rerank_manager.get_all_providers() if rerank_manager else []
                
                return {
                    "getRerankProviders": {
                        "providers": providers,
                        "message": "Rerank providers retrieved successfully"
                    }
                }
            except Exception as e:
                logger.error(f"[GraphQL] Error getting rerank providers: {e}")
                return {
                    "getRerankProviders": {
                        "providers": [],
                        "message": f"Error: {str(e)}"
                    }
                }
        
        else:
            # Pass-through to IPC handlers for operations not handled above
            # This allows CRUD operations to use proven IPC handlers
            ipc_method = self._graphql_to_ipc_method(query_lower, variables)
            if ipc_method:
                logger.info(f"[GraphQL] Passing through to IPC handler: {ipc_method}")
                return await self._call_ipc_handler(ipc_method, variables, query_lower)
            
            logger.warning(f"[GraphQL] Unknown operation: {query[:200]}")
            raise Exception(f"Unknown GraphQL operation")
    
    def _graphql_to_ipc_method(self, query_lower: str, variables: dict) -> str:
        """Map GraphQL operation names to IPC method names."""
        # Map of GraphQL operation patterns to IPC methods
        mappings = {
            # Data fetch operations
            'getallmine': 'get_all',
            'getall': 'get_all',
            'getorgagenttree': 'get_all_org_agents',
            'getallorga': 'get_all_org_agents',
            'getorgs': 'get_orgs',
            'getagents': 'get_agents',
            'getagenttasks': 'get_agent_tasks',
            'getagentskills': 'get_agent_skills',
            'gettools': 'get_tools',
            'getvehicles': 'get_vehicles',
            'getwarehouses': 'get_warehouses',
            'getproducts': 'get_products',
            'getinventories': 'get_inventories',
            'getavailabletests': 'get_available_tests',
            # Agent CRUD
            'addagent': 'new_agent',
            'createagent': 'new_agent',
            'updateagent': 'save_agent',
            'saveagent': 'save_agent',
            'deleteagent': 'delete_agent',
            'removeagent': 'delete_agent',
            # Skill CRUD
            'addagentskill': 'new_agent_skill',
            'updateagentskill': 'save_agent_skill',
            'deleteagentskill': 'delete_agent_skill',
            'removeagentskill': 'delete_agent_skill',
            # Task CRUD
            'addagenttask': 'new_agent_task',
            'updateagenttask': 'save_agent_task',
            'deleteagenttask': 'delete_agent_task',
            'removeagenttask': 'delete_agent_task',
            # Tool CRUD
            'addagenttools': 'new_tools',
            'updateagenttools': 'save_tools',
            'deleteagenttools': 'delete_tools',
            'removeagenttools': 'delete_tools',
            # Knowledge CRUD
            'addagentknowledges': 'new_knowledges',
            'updateagentknowledges': 'save_knowledges',
            'deleteagentknowledges': 'delete_knowledges',
            'removeagentknowledges': 'delete_knowledges',
            # Org CRUD
            'addorgs': 'create_org',
            'createorg': 'create_org',
            'updateorgs': 'update_org',
            'updateorg': 'update_org',
            'deleteorgs': 'delete_org',
            'removeorgs': 'delete_org',
            # Vehicle CRUD
            'addvehicle': 'add_vehicle',
            'updatevehicle': 'update_vehicle',
            'deletevehicle': 'delete_vehicle',
            'removevehicle': 'delete_vehicle',
            # Prompt CRUD
            'addprompts': 'add_prompts',
            'updateprompts': 'update_prompts',
            'deleteprompts': 'remove_prompts',
            'removeprompts': 'remove_prompts',
            # Warehouse CRUD
            'addwarehouse': 'save_warehouse',
            'updatewarehouse': 'save_warehouse',
            'savewarehouse': 'save_warehouse',
            'deletewarehouse': 'delete_warehouse',
            'removewarehouse': 'delete_warehouse',
            # Product CRUD
            'addproduct': 'save_product',
            'updateproduct': 'save_product',
            'saveproduct': 'save_product',
            'deleteproduct': 'delete_product',
            'removeproduct': 'delete_product',
            # Inventory CRUD
            'addinventory': 'save_inventory',
            'updateinventory': 'save_inventory',
            'saveinventory': 'save_inventory',
            'deleteinventory': 'delete_inventory',
            'removeinventory': 'delete_inventory',
            # Label config
            'getlabelformats': 'label_config.get_all',
            'addlabelformat': 'label_config.save',
            'updatelabelformat': 'label_config.save',
            'deletelabelformat': 'label_config.delete',
            'removelabelformat': 'label_config.delete',
            # Simulation operations
            'setupsimstep': 'setup_sim_step',
            'stepsim': 'step_sim',
            'testlanggraph2flowgram': 'test_langgraph2flowgram',
            'simtimerevent': 'sim_timer_event',
            'simwebsocketevent': 'sim_websocket_event',
            'simsseevent': 'sim_sse_event',
            'simwebhookevent': 'sim_webhook_event',
            # Skill run operations
            'runskill': 'run_skill',
            'pauserunskill': 'pause_run_skill',
            'resumerunskill': 'resume_run_skill',
            'steprunskill': 'step_run_skill',
            'cancelrunskill': 'cancel_run_skill',
            'setskillbreakpoints': 'set_skill_breakpoints',
            'clearskillbreakpoints': 'clear_skill_breakpoints',
            'requestskillstate': 'request_skill_state',
            'injectskillstate': 'inject_skill_state',
            'loadskillschemas': 'load_skill_schemas',
        }
        
        for pattern, method in mappings.items():
            if pattern in query_lower:
                logger.debug(f"[GraphQL] Matched pattern '{pattern}' -> IPC method '{method}'")
                return method
        
        # Log unmatched query for debugging
        logger.debug(f"[GraphQL] No IPC method mapping found for query (first 500 chars): {query_lower[:500]}")
        return None
    
    async def _call_ipc_handler(self, method: str, variables: dict, query_lower: str):
        """Call an IPC handler and return the result in GraphQL format."""
        from gui.ipc.registry import IPCHandlerRegistry
        from gui.ipc.types import create_success_response
        
        handler_info = IPCHandlerRegistry.get_handler(method)
        if not handler_info:
            logger.warning(f"[GraphQL] No IPC handler found for method: {method}")
            raise Exception(f"No handler found for method: {method}")
        
        handler, handler_type = handler_info
        
        # Build IPC request object
        # Mark as local_server request to bypass token validation
        request = {
            'id': f'graphql_{method}_{id(variables)}',
            'method': method,
            'params': variables,
            'source': 'local_server',  # Marker for trusted local requests
        }
        
        try:
            # Call the handler
            if handler_type == 'background':
                # Run background handlers in thread pool
                import asyncio
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, handler, request, variables)
            else:
                response = handler(request, variables)
            
            # Convert IPC response to GraphQL format
            if response.get('status') == 'success':
                result = response.get('result', {})
                # Sanitize result to ensure JSON serializability
                result = self._json_safe(result)
                # Try to determine the GraphQL field name from the query
                field_name = self._extract_graphql_field(query_lower, method)
                return {field_name: result}
            else:
                error_msg = response.get('error', {}).get('message', 'Unknown error')
                raise Exception(error_msg)
                
        except Exception as e:
            logger.error(f"[GraphQL] Error calling IPC handler {method}: {e}")
            raise
    
    def _json_safe(self, value, depth=0):
        """Make a value JSON-safe by converting non-serializable objects to strings."""
        try:
            if depth > 10:
                return str(value)
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, dict):
                return {str(k): self._json_safe(v, depth + 1) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [self._json_safe(v, depth + 1) for v in value]
            # Pydantic models
            if hasattr(value, 'model_dump') and callable(getattr(value, 'model_dump')):
                try:
                    return self._json_safe(value.model_dump(mode="python"), depth + 1)
                except Exception:
                    pass
            # Objects with __dict__
            if hasattr(value, '__dict__'):
                try:
                    return self._json_safe(vars(value), depth + 1)
                except Exception:
                    pass
            # Fallback to string
            return str(value)
        except Exception:
            return '<unserializable>'
    
    def _extract_graphql_field(self, query_lower: str, method: str) -> str:
        """Extract the GraphQL field name from the query or derive from method."""
        # Common patterns: query GetAgents -> getAgents, mutation AddAgent -> addAgent
        import re
        
        # Try to find the operation name in the query
        # Pattern: query/mutation OperationName { fieldName { ... } }
        match = re.search(r'(?:query|mutation)\s+\w+\s*\{?\s*(\w+)', query_lower)
        if match:
            return match.group(1)
        
        # Fallback: convert method name to camelCase
        parts = method.split('_')
        return parts[0] + ''.join(p.capitalize() for p in parts[1:])

    async def gen_feedbacks(self, request):
        logger.info("serving gen_feedbacks.....")
        mids = request.query_params.get('mids', "-1")
        logger.info(f"mids: {mids}")
        data = run_on_main_thread(lambda: self.main_win.genFeedbacks(mids))
        return JSONResponse(data, status_code=200)

    async def get_mission_reports(self, request):
        start_date = request.query_params.get('start_date', "-1")
        end_date = request.query_params.get('end_date', "-1")
        data = run_on_main_thread(lambda: self.main_win.getRPAReports(start_date, end_date))
        return JSONResponse(data, status_code=200)

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

    async def stream(self, request):
        async def event_stream():
            while True:
                await asyncio.sleep(1)
                yield f"data: The current time is {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    async def sync_bots_missions(self, request):
        try:
            incoming_data = await request.json()
            logger.info(f"sync_bots_missions Received data: {incoming_data}")
            b_emails = incoming_data.get('bots', [])
            minfos = incoming_data.get('missions', [])
            m_asin_srcs = []
            for minfo in minfos:
                infos = minfo.split("|")
                m_asin_srcs.append({"asin": infos[0].strip(), "src": infos[1].strip()})
            bots_data = self.main_win.bot_service.find_bots_by_emails(b_emails)
            missions_data = self.main_win.mission_service.find_missions_by_asin_srcs(m_asin_srcs)
            result = {"bots": bots_data, "missions": missions_data}
            return JSONResponse({"status": "success", "result": result}, status_code=200)
        except Exception as e:
            ex_stat = f"ErrorFetchSchedule: {traceback.format_exc()} {str(e)}"
            logger.error(ex_stat)
            return JSONResponse({"status": "failure", "result": ex_stat}, status_code=500)

    async def get_skill_graph(self, request):
        # Default file path if not provided in query
        skg_file = request.query_params.get('file', 'skills/skill_graph.json')
        if not os.path.exists(skg_file):
            return JSONResponse({"error": f"Skill graph file not found: {skg_file}"}, status_code=404)

        try:
            with open(skg_file, "r", encoding="utf-8") as skf:
                skill_graph = json.load(skf)
            return JSONResponse(skill_graph)
        except Exception as e:
            logger.error(f"Error loading skill graph: {e}")
            return JSONResponse({"error": "Failed to load or parse skill graph."}, status_code=500)

    async def save_skill_graph(self, request):
        skg_file = request.query_params.get('file', 'skills/skill_graph.json')
        try:
            skill_graph = await request.json()
            with open(skg_file, "w") as outfile:
                json.dump(skill_graph, outfile, indent=4)
            return JSONResponse({"status": "success"}, status_code=200)
        except json.JSONDecodeError:
            return JSONResponse({"error": "Invalid JSON in request body."}, status_code=400)
        except Exception as e:
            error_message = f"ErrorSaveSkillGraph: {traceback.format_exc()} {str(e)}"
            logger.error(error_message)
            return JSONResponse({"error": "Failed to save skill graph."}, status_code=500)


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
            Route("/graphql", self.request_handlers.graphql_handler, methods=['POST']),
            WebSocketRoute("/ws/skill-editor", self.request_handlers.skill_editor_websocket),
            Route('/api/initialize', self.request_handlers.initialize, methods=['POST']),
            Route('/api/gen_feedbacks', self.request_handlers.gen_feedbacks, methods=['GET']),
            Route('/api/get_mission_reports', self.request_handlers.get_mission_reports, methods=['GET']),
            Route('/api/load_graph', self.request_handlers.get_skill_graph, methods=['GET']),
            Route('/api/stream', self.request_handlers.stream),
            Route('/api/sync_bots_missions', self.request_handlers.sync_bots_missions, methods=['POST']),
            Route('/api/save_graph', self.request_handlers.save_skill_graph, methods=['POST']),
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
        self.uvicorn_server = None
        self.server_thread = None

    def get_server_url(self) -> str:
        """Get local server URL"""
        port = int(self.main_win.get_local_server_port())
        return f"http://localhost:{port}"

    def get_api_url(self, endpoint: str) -> str:
        """Get complete URL for API endpoint"""
        return f"{self.get_server_url()}{endpoint}"

    def start_in_thread(self):
        """Start server in a separate thread"""
        port = int(self.main_win.get_local_server_port())

        # Optimization: Set higher thread priority for faster startup
        self.server_thread = threading.Thread(target=self._run_starlette, args=(port,))
        self.server_thread.daemon = False  # Allow proper cleanup instead of forced termination
        self.server_thread.start()
        logger.info(f"🚀 Optimized local server starting on port {port} in separate thread")

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
                    http="h11",
                    log_config=None,
                    workers=1,            # Single process mode
                    reload=False,         # Disable auto-reload
                    use_colors=False,     # Disable color output
                )
                server = uvicorn.Server(config)

                self.uvicorn_server = server
                logger.info(f"✅ Server configured, starting on {host_bind}:{port}")
                server.run()
                logger.info(f"✅ Uvicorn server exited normally on {host_bind}:{port}")
                last_err = None
                break
            except Exception as e1:
                last_err = str(e1)
                logger.warning(f"⚠️  Failed to bind {host_bind}:{port} - {e1}")
                continue

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
