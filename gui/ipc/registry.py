"""
IPC 处理器注册器模块
提供 IPC 处理器的注册、查找和管理功能
"""

from typing import Any, Dict, Optional, Callable, TypeVar, cast, ClassVar, Protocol, Union
from functools import wraps
from .types import IPCRequest, create_error_response
from utils.logger_helper import logger_helper
import json

logger = logger_helper.logger

# 定义处理器类型
class IPCServiceProtocol(Protocol):
    """IPC 服务协议，定义处理器所需的 IPC 服务接口"""
    pass

# 定义处理器函数类型
HandlerFunc = Callable[[IPCRequest, Optional[Any]], str]
ServiceHandlerFunc = Callable[[IPCServiceProtocol, IPCRequest, Optional[Any]], str]
HandlerType = TypeVar('HandlerType', HandlerFunc, ServiceHandlerFunc)

class IPCHandlerRegistry:
    """IPC 处理器注册器
    
    用于注册和管理 IPC 请求处理器，提供装饰器接口用于注册处理器，
    并提供查找和列出已注册处理器的功能。
    """
    
    _handlers: ClassVar[Dict[str, HandlerType]] = {}
    
    @classmethod
    def register(cls, method: str) -> Callable[[HandlerType], HandlerType]:
        """注册处理器装饰器
        
        用于注册处理特定 IPC 方法的处理器函数。装饰器会自动处理请求验证、
        错误处理和日志记录。
        
        Args:
            method: 要处理的方法名
            
        Returns:
            Callable: 装饰器函数
            
        Example:
            # 不需要访问 IPC 服务的处理器
            @IPCHandlerRegistry.register('get_config')
            def handle_get_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
                # 处理逻辑
                pass
                
            # 需要访问 IPC 服务的处理器
            @IPCHandlerRegistry.register('notify_event')
            def handle_notify_event(self: IPCService, request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
                # 处理逻辑
                pass
        """
        def decorator(func: HandlerType) -> HandlerType:
            @wraps(func)
            def wrapper(self_or_request: Union[IPCServiceProtocol, IPCRequest], 
                       request_or_params: Union[IPCRequest, Optional[Any]], 
                       params: Optional[Any] = None) -> str:
                try:
                    # 判断是否是服务处理器
                    is_service_handler = len(func.__annotations__) > 2
                    
                    # 获取实际的请求和参数
                    if is_service_handler:
                        self = self_or_request
                        request = request_or_params
                    else:
                        request = self_or_request
                        params = request_or_params
                    
                    # 验证请求参数
                    if not isinstance(request, dict):
                        logger.error(f"Invalid request format for method {method}")
                        return json.dumps(create_error_response(
                            request,
                            'INVALID_REQUEST',
                            "Invalid request format"
                        ))
                    
                    # 调用处理器
                    logger.debug(f"Calling handler for method {method}")
                    if is_service_handler:
                        return func(self, request, params)
                    else:
                        return func(request, params)
                except Exception as e:
                    logger.error(f"Error in handler {method}: {e}")
                    return json.dumps(create_error_response(
                        request,
                        'HANDLER_ERROR',
                        f"Error in handler {method}: {str(e)}"
                    ))
            
            # 注册处理器
            if method in cls._handlers:
                logger.warning(f"Handler for method {method} already exists, overwriting")
            cls._handlers[method] = cast(HandlerType, wrapper)
            logger.info(f"Registered handler for method {method}")
            return cast(HandlerType, wrapper)
        return decorator
    
    @classmethod
    def get_handler(cls, method: str) -> Optional[HandlerType]:
        """获取处理器
        
        根据方法名获取对应的处理器函数。
        
        Args:
            method: 方法名
            
        Returns:
            Optional[HandlerType]: 处理器函数，如果未找到则返回 None
        """
        handler = cls._handlers.get(method)
        if handler is None:
            logger.warning(f"No handler found for method {method}")
        return handler
    
    @classmethod
    def list_handlers(cls) -> Dict[str, str]:
        """列出所有已注册的处理器
        
        返回所有已注册处理器的名称和函数名的映射。
        
        Returns:
            Dict[str, str]: 处理器名称到处理器函数的映射
        """
        handlers = {name: func.__name__ for name, func in cls._handlers.items()}
        logger.debug(f"Listed {len(handlers)} handlers")
        return handlers
    
    @classmethod
    def clear_handlers(cls) -> None:
        """清除所有已注册的处理器
        
        用于测试或重置处理器注册表。
        """
        cls._handlers.clear()
        logger.info("Cleared all handlers") 