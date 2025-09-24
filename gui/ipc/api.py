"""
IPC API 管理模块
提供统一的 Python 到 Web 的调用接口
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, List
from dataclasses import dataclass
from .types import IPCResponse
from .wc_service import IPCWCService
from utils.logger_helper import logger_helper as logger
import gui.ipc.w2p_handlers


# 定义泛型类型
T = TypeVar('T')

@dataclass
class APIResponse(Generic[T]):
    """API 响应包装类"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

class IPCAPI:
    """IPC API 管理类（单例模式）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, ipc_wc_service: Optional[IPCWCService] = None):
        """
        初始化 IPC API
        
        Args:
            ipc_wc_service: IPC 服务实例（可选，如果已初始化则忽略）
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
        获取 IPCAPI 单例实例
        
        Returns:
            IPCAPI: IPCAPI 实例
            
        Raises:
            RuntimeError: 如果实例尚未初始化
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
        将 IPC 响应转换为 API 响应并调用回调
        
        Args:
            response: IPC 响应对象
            callback: 回调函数
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
        发送请求
        
        Args:
            method: 方法名
            params: 请求参数
            meta: 元数据
            callback: 回调函数
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
        获取配置
        
        Args:
            key: 配置键
            callback: 回调函数，接收 APIResponse[Dict[str, Any]]
        """
        self._send_request('get_config', {'key': key}, callback=callback)
    
    def set_config(
        self,
        key: str,
        value: Any,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置
        
        Args:
            key: 配置键
            value: 配置值
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('set_config', {'key': key, 'value': value}, callback=callback)

    def refresh_dashboard(
        self,
        data: Dict[str, Any],
        callback: Optional[Callable[[APIResponse[Dict[str, Any]]], None]] = None
    ) -> None:
        """
        刷新仪表盘数据
        
        Args:
            data: 包含以下字段的字典
                - overview: 概览数据
                - statistics: 统计数据
                - recentActivities: 最近活动数
                - quickActions: 快速操作数
            callback: 回调函数，接收 APIResponse[Dict[str, Any]]
        """
        self._send_request('refresh_dashboard', data, callback=callback)

    def update_agents(
            self,
            agents: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            agents: agents
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_agents', data=agents, callback=callback)

    def update_agents_scenes(
            self,
            agents_scenes: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            agents_scenes: agents
                { agent_id: { scenes: [ {id, gif, script, audio, description}....]},....}
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_agents_scenes', data=agents_scenes, callback=callback)


    def update_skills(
            self,
            skills: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            skills: skill sets
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_skills', data=skills, callback=callback)

    def update_tasks(
            self,
            tasks: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            tasks: work to be done
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_tasks', data=tasks, callback=callback)


    def update_tools(
            self,
            tools: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            tasks: work to be done
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_tools', data=tools, callback=callback)



    def update_settings(
            self,
            settings: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            settings: 配置值
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_settings', data=settings, callback=callback)


    def update_knowledge(
            self,
            knowledge: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            knowledge: list of knowledge points (RAG vector DB table?)
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_knowledge', data=knowledge, callback=callback)


    def update_chats(
            self,
            chats: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            chats: Chat值
            callback: 回调函数，接收 APIResponse[bool]
        """
        print("about to send chat data to GUI::", chats)
        self._send_request('update_chats', {'chats': chats}, callback=callback)

    def update_vehicles(
            self,
            vehicles: List[Any],
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            chats: Chat值
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_vehicles', data=vehicles, callback=callback)

    def update_all(
            self,
            all: Any,
            callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        设置配置

        Args:
            chats: Chat值
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('update_all', data=all, callback=callback)

    def push_chat_message(
        self,
        chatId: str,
        message: dict,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        推送单条聊天消息到指定会话
        Args:
            chatId: 会话ID
            message: 消息内容（Message 对象或 dict，需符合后端 schema）
            callback: 回调函数，接收 APIResponse[bool]
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
        推送单条聊天消息到指定会话
        Args:
            chatId: 会话ID
            content: 通知内容（dict，需符合后端 schema）
            isRead: 是否已读
            timestamp: 通知时间戳
            uid: 通知唯一ID
            callback: 回调函数，接收 APIResponse[bool]
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
        推送单条聊天消息到指定会话
        Args:
            agent_task_id: task ID
            langgraph_state: {status, node_name, node_state}
            timestamp: 通知时间戳
            callback: 回调函数，接收 APIResponse[bool]
        """
        params = {'agentTaskId': agent_task_id, "current_node": current_node, "status": status, 'nodeState': langgraph_state, 'timestamp': timestamp}
        self._send_request('update_skill_run_stat', params, callback=callback)

    def update_task_stat(
        self,
        agent_task_id: str,
        langgraph_state: dict,
        timestamp: int = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        推送单条聊天消息到指定会话
        Args:
            agent_task_id: task ID
            langgraph_state: {status, node_name, node_state}
            timestamp: 通知时间戳
            callback: 回调函数，接收 APIResponse[bool]
        """
        params = {'agentTaskId': agent_task_id, 'langgraphState': langgraph_state, 'isRead': isRead, 'timestamp': timestamp, 'uid': uid}
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

    def trigger_scene_event(
        self,
        agent_id: str,
        event_type: str,
        event_data: Optional[Dict[str, Any]] = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        Trigger a scene event for a specific agent in the event-driven avatar system
        
        Args:
            agent_id: ID of the agent to trigger the event for
            event_type: Type of event to trigger (timer, action, thought-change, error, 
                       interaction, status-change, emotion, custom)
            event_data: Optional additional data for the event
                Expected format: {
                    "priority": "high|medium|low",
                    "context": "additional context",
                    "metadata": {...}
                }
            callback: Callback function receiving APIResponse[bool]
        """
        params = {
            'agentId': agent_id,
            'eventType': event_type,
            'eventData': event_data or {}
        }
        self._send_request('trigger_scene_event', params, callback=callback)