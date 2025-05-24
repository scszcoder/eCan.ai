"""
IPC API 管理模块
提供统一的 Python 到 Web 的调用接口
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Generic, Union
from dataclasses import dataclass
from .types import IPCRequest, IPCResponse, create_request, create_error_response
from .service import IPCService
from utils.logger_helper import logger_helper

logger = logger_helper.logger

# 定义泛型类型
T = TypeVar('T')

@dataclass
class APIResponse(Generic[T]):
    """API 响应包装类"""
    success: bool
    data: Optional[T] = None
    error: Optional[str] = None

class IPCAPI:
    """IPC API 管理类"""
    
    def __init__(self, ipc_service: IPCService):
        """
        初始化 IPC API
        
        Args:
            ipc_service: IPC 服务实例
        """
        self._ipc_service: IPCService = ipc_service
    
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
            if response.status == 'ok':
                callback(APIResponse(success=True, data=response.result))
            else:
                error_msg = response.error.message if response.error else 'Unknown error'
                callback(APIResponse(success=False, error=error_msg))
        except Exception as e:
            logger.error(f"Error in response callback: {e}")
            callback(APIResponse(success=False, error=str(e)))
    
    def _send_request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
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
       
    # 事件相关接口
    def notify_event(
        self,
        event: str,
        data: Optional[Any] = None,
        callback: Optional[Callable[[APIResponse[bool]], None]] = None
    ) -> None:
        """
        通知事件
        
        Args:
            event: 事件名
            data: 事件数据
            callback: 回调函数，接收 APIResponse[bool]
        """
        self._send_request('notify_event', {'event': event, 'data': data}, callback=callback)


# 使用示例
"""
# 创建 IPC API 实例
ipc_api = IPCAPI(ipc_service)

# 获取配置示例
def handle_config(response: APIResponse[Any]):
    if response.success:
        print(f"Config value: {response.data}")
    else:
        print(f"Error: {response.error}")

ipc_api.get_config('some_key', handle_config)

# 执行命令示例
def handle_command(response: APIResponse[Dict[str, Any]]):
    if response.success:
        print(f"Command result: {response.data}")
    else:
        print(f"Error: {response.error}")

ipc_api.execute_command('some_command', ['arg1', 'arg2'], handle_command)

# 通知事件示例
def handle_event(response: APIResponse[bool]):
    if response.success:
        print("Event processed successfully")
    else:
        print(f"Error: {response.error}")

ipc_api.notify_event('some_event', {'data': 'value'}, handle_event)
""" 