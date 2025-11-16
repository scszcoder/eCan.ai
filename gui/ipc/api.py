"""
IPC API Management Module
Provides unified Python to Web calling interface
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, List
from dataclasses import dataclass
from .types import IPCResponse
from .wc_service import IPCWCService
from utils.logger_helper import logger_helper as logger
import gui.ipc.w2p_handlers
# Ensure context handlers are registered
import gui.ipc.context_handlers  # noqa: F401


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

    def __init__(self, ipc_wc_service: Optional[IPCWCService] = None):
        """
        Initialize IPC API

        Args:
            ipc_wc_service: IPC service instance (optional, ignored if already initialized)
        """
        if not self._initialized:
            if ipc_wc_service is None:
                raise ValueError("IPC service must be provided for first initialization")
            self._ipc_wc_service: IPCWCService = ipc_wc_service
            self._initialized = True
            logger.info("IPC API initialized")

    @classmethod
    def get_instance(cls) -> 'IPCAPI':
        """
        Get IPCAPI singleton instance

        Returns:
            IPCAPI: IPCAPI instance

        Raises:
            RuntimeError: If instance has not been initialized yet
        """
        if cls._instance is None:
            raise RuntimeError("IPCAPI has not been initialized. Call IPCAPI(ipc_webchannel_service) first.")
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
        callback: Optional[Callable[[APIResponse[T]], None]] = None
    ) -> None:
        """
        Send request

        Args:
            method: Method name
            params: Request parameters
            meta: Metadata
            callback: Callback function
        """
        def ipc_response_callback(response: IPCResponse) -> None:
            self._convert_response(response, callback)

        self._ipc_wc_service.send_request(method, params, meta, ipc_response_callback)

    def get_config(
        self,
        key: str,
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        """
        Get configuration

        Args:
            key: Configuration key
            callback: Callback function, receives APIResponse[Dict[str, Any]]
        """
        self._send_request('get_config', {'key': key}, callback=callback)

    def update_org_agents(self,
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        logger.info("[IPCAPI] update_org_agents")
        self._send_request('update_org_agents', callback=callback)

    def set_config(
        self,
        key: str,
        value: Any,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Set configuration

        Args:
            key: Configuration key
            value: Configuration value
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('set_config', {'key': key, 'value': value}, callback=callback)

    def refresh_dashboard(
        self,
        data: Dict[str, Any],
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        """
        Refresh dashboard data

        Args:
            data: Dictionary containing the following fields
                - overview: Overview data
                - statistics: Statistics data
                - recentActivities: Recent activities count
                - quickActions: Quick actions count
            callback: Callback function, receives APIResponse[Dict[str, Any]]
        """
        self._send_request('refresh_dashboard', data, callback=callback)

    def update_agents(
            self,
            agents: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update agents

        Args:
            agents: agents
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_agents', data=agents, callback=callback)

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


    def update_skills(
            self,
            skills: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update skills

        Args:
            skills: skill sets
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_skills', data=skills, callback=callback)

    def update_tasks(
            self,
            tasks: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update tasks

        Args:
            tasks: work to be done
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_tasks', data=tasks, callback=callback)


    def update_tools(
            self,
            tools: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update tools

        Args:
            tasks: work to be done
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_tools', data=tools, callback=callback)



    def update_settings(
            self,
            settings: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update settings

        Args:
            settings: Configuration value
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_settings', data=settings, callback=callback)


    def update_knowledge(
            self,
            knowledge: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update knowledge

        Args:
            knowledge: list of knowledge points (RAG vector DB table?)
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_knowledge', data=knowledge, callback=callback)


    def update_chats(
            self,
            chats: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update chats

        Args:
            chats: Chat value
            callback: Callback function, receives APIResponse[bool]
        """
        print("about to send chat data to GUI::", chats)
        self._send_request('update_chats', {'chats': chats}, callback=callback)

    def update_vehicles(
            self,
            vehicles: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update vehicles

        Args:
            chats: Chat value
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_vehicles', data=vehicles, callback=callback)

    def update_all(
            self,
            all: Any,
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Update all

        Args:
            chats: Chat value
            callback: Callback function, receives APIResponse[bool]
        """
        self._send_request('update_all', data=all, callback=callback)

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
        self._send_request('push_chat_message', params, callback=callback)

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
        self._send_request('push_chat_notification', params, callback=callback)

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
        # Make nodeState JSON-safe to avoid serialization errors (e.g., CallToolResult)
        def _json_safe(value, depth=0):
            try:
                # Prevent extremely deep recursion
                if depth > 6:
                    return str(value)
                if value is None or isinstance(value, (str, int, float, bool)):
                    return value
                if isinstance(value, dict):
                    safe_dict = {}
                    for k, v in value.items():
                        # ensure keys are strings
                        key = str(k)
                        safe_dict[key] = _json_safe(v, depth + 1)
                    return safe_dict
                if isinstance(value, (list, tuple, set)):
                    return [_json_safe(v, depth + 1) for v in value]
                # objects with __dict__ (pydantic, dataclasses, etc.)
                if hasattr(value, 'model_dump') and callable(getattr(value, 'model_dump')):
                    try:
                        return _json_safe(value.model_dump(mode="python"), depth + 1)
                    except Exception:
                        pass
                if hasattr(value, '__dict__'):
                    try:
                        return _json_safe(vars(value), depth + 1)
                    except Exception:
                        pass
                # Fallback to string representation
                return str(value)
            except Exception:
                try:
                    return str(value)
                except Exception:
                    return '<unserializable>'

        safe_state = _json_safe(langgraph_state)

        # Include both snake_case and camelCase for compatibility with different frontends
        params = {
            'agentTaskId': agent_task_id,
            # snake_case (legacy/current handlers)
            'current_node': current_node,
            'nodeState': safe_state,
            # camelCase (new handlers)
            'currentNode': current_node,
            'langgraphState': safe_state,
            'status': status,
            'timestamp': timestamp,
        }
        try:
            # Clear, distinguishable backend log for IPC emission
            try:
                node_keys = list(langgraph_state.keys()) if isinstance(langgraph_state, dict) else []
            except Exception:
                node_keys = []
            logger.info(f"[SIM][BE][IPC] sending update_skill_run_stat: agentTaskId={agent_task_id}, current_node={current_node}, status={status}, nodeState.keys={node_keys}")
        except Exception:
            pass
        self._send_request('update_skill_run_stat', params, callback=callback)

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
        self._send_request('update_tasks_stat', params, callback=callback)

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
