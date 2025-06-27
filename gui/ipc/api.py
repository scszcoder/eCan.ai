"""
IPC API 管理模块
提供统一的 Python 到 Web 的调用接口
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, List
from dataclasses import dataclass
from .types import IPCResponse
from .service import IPCService
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
    
    def __init__(self, ipc_service: Optional[IPCService] = None):
        """
        初始化 IPC API
        
        Args:
            ipc_service: IPC 服务实例（可选，如果已初始化则忽略）
        """
        if not self._initialized:
            if ipc_service is None:
                raise ValueError("IPC service must be provided for first initialization")
            self._ipc_service: IPCService = ipc_service
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
            raise RuntimeError("IPCAPI has not been initialized. Call IPCAPI(ipc_service) first.")
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
            
        self._ipc_service.send_request(method, params, meta, ipc_response_callback)
    
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


# 使用示例
"""
# 获取 IPC API 单例实例
ipc_api = IPCAPI.get_instance()

# 获取配置示例
def handle_config(response: APIResponse[Any]):
    if response.success:
        print(f"Config value: {response.data}")
    else:
        print(f"Error: {response.error}")

ipc_api.get_config('some_key', handle_config)

# 设置配置示例
def handle_set_config(response: APIResponse[bool]):
    if response.success:
        print("Config updated successfully")
    else:
        print(f"Error: {response.error}")

ipc_api.set_config('some_key', 'some_value', handle_set_config)

# 刷新仪表盘数据示例
def handle_dashboard_update(response: APIResponse[Dict[str, Any]]):
    if response.success:
        print(f"Dashboard data updated: {response.data}")
    else:
        print(f"Error updating dashboard: {response.error}")

# 使用随机数据更新仪表盘
import random
dashboard_data = {
    'overview': random.randint(10, 100),
    'statistics': random.randint(5, 50),
    'recentActivities': random.randint(20, 200),
    'quickActions': random.randint(1, 30)
}
ipc_api.refresh_dashboard(dashboard_data, handle_dashboard_update)

# 使用定时器定期更新仪表盘数据
from PySide6.QtCore import QTimer

def setup_dashboard_timer():
    timer = QTimer()
    def update_dashboard():
        dashboard_data = {
            'overview': random.randint(10, 100),
            'statistics': random.randint(5, 50),
            'recentActivities': random.randint(20, 200),
            'quickActions': random.randint(1, 30)
        }
        ipc_api.refresh_dashboard(dashboard_data, handle_dashboard_update)
    
    timer.timeout.connect(update_dashboard)
    timer.start(5000)  # 每5秒更新一次
    return timer
""" 