"""
IPC API Management Module
Provides unified Python to Web calling interface

Push events (backend-to-frontend) are now routed via WebSocket when available,
with IPC as fallback for desktop mode.
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, List
from dataclasses import dataclass
import os
from .types import IPCResponse
from utils.logger_helper import logger_helper as logger
import gui.ipc.w2p_handlers
# Ensure context handlers are registered
import gui.ipc.context_handlers  # noqa: F401


def _should_use_websocket() -> bool:
    """Check if we should use WebSocket for push events."""
    # Use WebSocket when IPC mode is OFF (HTTP+WS mode)
    ipc_mode = os.getenv("VITE_IPC_MODE", "").lower()
    return ipc_mode not in ('1', 'true', 'yes', 'on')


def _get_ws_manager():
    """Get the WebSocket manager instance."""
    try:
        from gui.LocalServer import app_ws_manager
        return app_ws_manager
    except ImportError:
        return None


# Define generic type
T = TypeVar('T')
@dataclass
class APIResponse(Generic[T]):
    """API response wrapper class"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

class IPCAPI:
    """IPC API management class (singleton pattern)"""

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, ipc_wc_service=None):
        """
        Initialize IPC API (WebSocket-only mode)

        Args:
            ipc_wc_service: Deprecated, ignored. Kept for signature compatibility.
        """
        if not self._initialized:
            self._initialized = True
            logger.info("IPC API initialized")

    @classmethod
    def get_instance(cls) -> 'IPCAPI':
        """
        Get IPCAPI singleton instance. Auto-initializes if needed.

        Returns:
            IPCAPI: IPCAPI instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _convert_response(
        self,
        response: IPCResponse,
        callback: Optional[Callable[[APIResponse[T]], None]] = None
    ) -> None:
        """
        Convert IPC response to API response and invoke callback

        Args:
            response: IPC response object
            callback: Callback function
        """
        if not callback:
            return

        try:
            if response['status'] == 'success':
                callback(APIResponse(success=True, data=response['result']))
            else:
                error_msg = response['error']['message'] if response['error'] else 'Unknown error'
                callback(APIResponse(success=False, error=error_msg))
        except Exception as e:
            logger.error(f"Error in response callback: {e}")
            callback(APIResponse(success=False, error=str(e)))

    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        data:  Optional[list[Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[APIResponse[T]], None]] = None,
        channel_id: Optional[str] = None
    ) -> None:
        """
        Send request - broadcasts via WebSocket.
        Push events from backend to frontend are delivered via the local WebSocket.

        Args:
            method: Method name
            params: Request parameters
            data: Request data (for some methods)
            meta: Metadata
            callback: Callback function (called with success response immediately since WS is fire-and-forget)
            channel_id: Optional WebSocket channel ID for targeted broadcasting
        """
        # Broadcast via WebSocket to all connected clients
        try:
            ws_mgr = _get_ws_manager()
            if ws_mgr:
                payload = params or {}
                if data is not None:
                    payload = data if isinstance(data, dict) else {'data': data}
                ws_mgr.broadcast_sync(method, payload, channel_id=channel_id)
                # Invoke callback with success since WS broadcast is fire-and-forget
                if callback:
                    callback(APIResponse(success=True, data=True))
            else:
                logger.warning(f"[IPCAPI] No WebSocket manager available, dropping push: {method}")
                if callback:
                    callback(APIResponse(success=False, error='No WebSocket manager available'))
        except Exception as e:
            logger.error(f"[IPCAPI] Error broadcasting push event {method}: {e}")
            if callback:
                callback(APIResponse(success=False, error=str(e)))

    def update_org_agents(
            self,
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Notify frontend to refresh organization and agent data

        Args:
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_org_agents', params={}, callback=callback)

    def update_agents_scenes(
            self,
            agents_scenes: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update agents scenes

        Args:
            agents_scenes: agents
                { agent_id: { scenes: [ {id, gif, script, audio, description}....]},....}
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_agents_scenes', data=agents_scenes, callback=callback)

    def push_chat_message(
        self,
        chatId: str,
        message: dict,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push a single chat message to specified session
        Args:
            chatId: Session ID
            message: Message content (Message object or dict, must conform to backend schema)
            callback: Callback function, receives APIResponse[bool]
        """
        params = {'chatId': chatId, 'message': message}
        self._send_request('push_chat_message', params, callback=callback, channel_id=f'chat:{chatId}')

    def push_chat_notification(
        self,
        chatId: str,
        content: dict,
        isRead: bool = False,
        timestamp: int = None,
        uid: str = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push a single chat notification to specified session
        Args:
            chatId: Session ID
            content: Notification content (dict, must conform to backend schema)
            isRead: Whether it has been read
            timestamp: Notification timestamp
            uid: Notification unique ID
            callback: Callback function, receives APIResponse[bool]
        """
        params = {'chatId': chatId, 'content': content, 'isRead': isRead, 'timestamp': timestamp, 'uid': uid}
        self._send_request('push_chat_notification', params, callback=callback, channel_id=f'chat:{chatId}')

    def update_run_stat(
        self,
        agent_task_id: str,
        current_node: str,
        status: str,
        langgraph_state: dict,
        timestamp: int = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update skill run statistics
        Args:
            agent_task_id: task ID
            langgraph_state: {status, node_name, node_state}
            timestamp: Notification timestamp
            callback: Callback function, receives APIResponse[bool]
        """
        try:
            from utils.data_uri_sanitizer import sanitize_data_uris, data_uri_stats
            stats = data_uri_stats(langgraph_state)
            if stats.get("count"):
                logger.info(
                    "[data-uri-mitigation] ipc_run_stat_state_sanitized "
                    "task=%s node=%s status=%s data_uri_count=%d data_uri_bytes=%d max_string_len=%d",
                    agent_task_id,
                    current_node,
                    status,
                    stats.get("count", 0),
                    stats.get("bytes", 0),
                    stats.get("max_string_len", 0),
                )
            safe_state = sanitize_data_uris(langgraph_state, max_string_chars=4000)
        except Exception:
            safe_state = str(langgraph_state)[:4000] if langgraph_state is not None else None
        node_state = {
            "summary": True,
            "keys": list(safe_state.keys()) if isinstance(safe_state, dict) else [],
            "status": status,
            "currentNode": current_node,
        }

        # Include both snake_case and camelCase for compatibility with different frontends
        params = {
            'agentTaskId': agent_task_id,
            # snake_case (legacy/current handlers)
            'current_node': current_node,
            'nodeState': node_state,
            # camelCase (new handlers)
            'currentNode': current_node,
            'langgraphState': safe_state,
            'status': status,
            'timestamp': timestamp,
        }
        try:
            # Only log at DEBUG level for routine status updates
            try:
                node_keys = list(langgraph_state.keys()) if isinstance(langgraph_state, dict) else []
            except Exception:
                node_keys = []
            logger.debug(f"[BE] update_skill_run_stat: task={agent_task_id}, node={current_node}, status={status}")
        except Exception:
            pass
        
        self._send_request('update_skill_run_stat', params, callback=callback, channel_id=f'task:{agent_task_id}')

    def update_task_stat(
        self,
        agent_task_id: str,
        langgraph_state: dict,
        timestamp: int = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update task statistics
        Args:
            agent_task_id: task ID
            langgraph_state: {status, node_name, node_state}
            timestamp: Notification timestamp
            callback: Callback function, receives APIResponse[bool]
        """
        params = {
            'agentTaskId': agent_task_id,
            'langgraphState': langgraph_state,
            'timestamp': timestamp,
        }
        self._send_request('update_tasks_stat', params, callback=callback, channel_id=f'task:{agent_task_id}')

    def get_editor_agents(
        self,
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        """Fetch agents list (plus default 'human') for the Skill Editor node editor dropdowns.

        Returns via callback an APIResponse with data schema:
          { "agents": [{id, name, kind}], "defaults": {"top": "human"} }
        """
        self._send_request('get_editor_agents', {}, callback=callback)

    def get_editor_pending_sources(
        self,
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        """Fetch queues and events the Skill Editor can pend on.

        Returns via callback an APIResponse with data schema:
          { "queues": [{id, name}], "events": [{id, name}] }
        """
        self._send_request('get_editor_pending_sources', {}, callback=callback)

    def update_screens(
        self,
        screens_data: Dict[str, Any],
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update avatar screens/scenes data for the event-driven avatar system
        
        Args:
            screens_data: Dictionary containing screen/scene data for agents
                Expected format: {
                    "agents": {
                        "agent_id": {
                            "scenes": [
                                {
                                    "id": "scene_id",
                                    "name": "Scene Name", 
                                    "clips": [
                                        {
                                            "id": "clip_id",
                                            "mediaUrl": "path/to/media.gif",
                                            "caption": "Scene caption",
                                            "duration": 3000,
                                            "triggers": ["timer", "action"],
                                            "priority": "medium"
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                }
            callback: Callback function receiving APIResponse[bool]
        """
        self._send_request('update_screens', screens_data, callback=callback)

    def push_onboarding_message(
        self,
        onboarding_type: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Push an onboarding/guide instruction to the frontend
        Uses standard request format (method: 'onboarding_message')
        Frontend decides how to display based on onboarding_type
        
        Interface Definition (Standard IPC Request):
        {
            'type': 'request',
            'method': 'onboarding_message',
            'params': {
                'onboardingType': str,  // e.g., 'llm_provider_config'
                'context': dict         // Optional context data
            },
            'id': str  // Unique request ID
        }
        
        Args:
            onboarding_type: Type of onboarding instruction (e.g., 'llm_provider_config')
            context: Optional context data for frontend (e.g., suggested action paths)
                Frontend will determine UI, text, and behavior based on onboarding_type
        """
        def onboarding_callback(response: APIResponse) -> None:
            """Callback for onboarding message request"""
            if response.success:
                logger.trace(f"[IPCAPI] Onboarding message sent successfully: {onboarding_type}")
            else:
                logger.debug(f"[IPCAPI] Onboarding message send failed: {response.error}")
        
        # Use standard send_request with callback
        self._send_request(
            'onboarding_message',
            params={
                'onboardingType': onboarding_type,
                'context': context or {}
            },
            callback=onboarding_callback
        )


    def send_skill_editor_log(
            self,
            level: str,
            text: str
    ) -> None:
        """
        Send skill editor log message to frontend
        
        Frontend expects message format:
        {
            'type': 'request',
            'method': 'skill_editor_log',
            'params': {
                'level': str,  // e.g., 'llm_provider_config'
                'text': str         // Optional context data
            },
            'id': str  // Unique request ID
        }

        Args:
            level: Type of message (e.g., 'log/warning/error')
            text: whatever log text message (e.g., )
        """
        def log_callback(response: APIResponse) -> None:
            """Callback for skill editor log request"""
            if response.success:
                logger.trace(f"[IPCAPI] Skill editor log sent successfully: {level}")
            else:
                logger.debug(f"[IPCAPI] Skill editor log send failed: {response.error}")
        
        # Use standard send_request with callback
        self._send_request(
            'skill_editor_log',
            params={
                'type': level,
                'text': text
            },
            callback=log_callback
        )

    def push_lightrag_chunk(
        self,
        stream_id: str,
        chunk_data: Any,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push LightRAG stream chunk to frontend
        Args:
            stream_id: Stream ID
            chunk_data: Chunk data
            callback: Callback function
        """
        self._send_request('lightrag.queryStream.chunk', {
            'id': stream_id,
            'chunk': chunk_data
        }, callback=callback, channel_id=f'lightrag:{stream_id}')

    def push_lightrag_done(
        self,
        stream_id: str,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push LightRAG stream done event
        Args:
            stream_id: Stream ID
            callback: Callback function
        """
        self._send_request('lightrag.queryStream.done', {
            'id': stream_id
        }, callback=callback, channel_id=f'lightrag:{stream_id}')

    def push_lightrag_error(
        self,
        stream_id: str,
        error: str,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push LightRAG stream error event
        Args:
            stream_id: Stream ID
            error: Error message
            callback: Callback function
        """
        self._send_request('lightrag.queryStream.error', {
            'id': stream_id,
            'error': error
        }, callback=callback, channel_id=f'lightrag:{stream_id}')

    # ============================================================
    # Skill Editor Chat Streaming
    # ============================================================

    def push_skill_editor_chat_chunk(
        self,
        session_id: str,
        message_id: str,
        chunk: str,
        chunk_index: int,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push skill editor chat stream chunk to frontend
        Args:
            session_id: Chat session ID
            message_id: Message ID being streamed
            chunk: Chunk content
            chunk_index: Chunk index
            callback: Callback function
        """
        logger.debug(f"[IPCAPI] push_skill_editor_chat_chunk: session={session_id}, msg={message_id}, chunk_idx={chunk_index}, chunk_len={len(chunk)}")
        self._send_request('skill_editor.chat.stream_chunk', {
            'sessionId': session_id,
            'messageId': message_id,
            'chunk': chunk,
            'chunkIndex': chunk_index,
            'index': chunk_index  # Keep for backward compatibility
        }, callback=callback, channel_id=f'session:{session_id}')

    def push_skill_editor_chat_done(
        self,
        session_id: str,
        message_id: str,
        full_content: str,
        extra: Optional[Dict] = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push skill editor chat stream done event
        Args:
            session_id: Chat session ID
            message_id: Message ID that finished streaming
            full_content: Complete message content
            extra: Optional full subscription payload (clarification, a2ui, plan, etc.)
            callback: Callback function
        """
        logger.info(f"[IPCAPI] push_skill_editor_chat_done: session={session_id}, msg={message_id}, content_len={len(full_content)}")
        data: Dict = {
            'sessionId': session_id,
            'messageId': message_id,
            'fullContent': full_content
        }
        # Merge additional structured fields from the subscription payload
        # so the frontend can extract clarification / a2ui / plan / state.
        if extra and isinstance(extra, dict):
            for key in ('clarification', 'a2ui', 'plan', 'state', 'intent',
                        'flowgram', 'validation', 'sessionName', 'message',
                        # Cloud-proposed CLI command (agent/task/prompt CRUD) — the
                        # frontend renders the interactive CommandCard from these.
                        'cli_command', 'proposal', 'requires_confirmation', 'client_os'):
                if key in extra and extra[key] is not None:
                    data[key] = extra[key]
        self._send_request('skill_editor.chat.stream_end', data,
                           callback=callback, channel_id=f'session:{session_id}')

    def push_skill_editor_chat_error(
        self,
        session_id: str,
        error_code: str,
        error_message: str,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push skill editor chat error event
        Args:
            session_id: Chat session ID
            error_code: Error code
            error_message: Error message
            callback: Callback function
        """
        logger.error(f"[IPCAPI] push_skill_editor_chat_error: session={session_id}, code={error_code}, message={error_message}")
        self._send_request('skill_editor.chat.error', {
            'sessionId': session_id,
            'code': error_code,
            'message': error_message
        }, callback=callback, channel_id=f'session:{session_id}')

    def _publish_skill_editor_event(
        self,
        session_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """Broadcast a skill editor event to frontend listeners."""
        logger.info(f"[IPCAPI] publish_skill_editor_event: session={session_id}, type={event_type}")
        logger.debug(f"[IPCAPI] Event payload: {payload}")
        self._send_request(
            'skill_editor.event',
            params={
                'sessionId': session_id,
                'type': event_type,
                'payload': payload,
            },
            channel_id=f'session:{session_id}'
        )

    def push_skill_editor_canvas_command(
        self,
        session_id: str,
        command_type: str,
        payload: Dict[str, Any],
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push canvas command to frontend skill editor
        Args:
            session_id: Chat session ID
            command_type: Command type (e.g., 'canvas.add_node')
            payload: Command payload
            callback: Callback function
        """
        logger.info(f"[IPCAPI] push_skill_editor_canvas_command: session={session_id}, type={command_type}")
        logger.debug(f"[IPCAPI] Canvas command payload: {payload}")

        # Broadcast event for V2 frontend
        try:
            self._publish_skill_editor_event(session_id, command_type, payload)
        except Exception as event_err:
            logger.warning(f"[IPCAPI] Failed to publish skill editor event: {event_err}")

        # Keep legacy request for backward compatibility (older clients)
        try:
            self._send_request('skill_editor.canvas.command', {
                'sessionId': session_id,
                'type': command_type,
                'payload': payload
            }, callback=callback)
        except Exception as legacy_err:
            logger.debug(f"[IPCAPI] Legacy canvas command send failed: {legacy_err}")

    # ============================================================
    # Context Management
    # ============================================================

    def push_contexts(
        self,
        method: str,
        contexts: List[Dict[str, Any]],
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Push contexts to frontend
        
        Args:
            method: Method name (e.g., 'send_all_contexts', 'update_contexts')
            contexts: Context data list or single context dict
            callback: Callback function
        """
        self._send_request(method, {'contexts': contexts}, callback=callback)
