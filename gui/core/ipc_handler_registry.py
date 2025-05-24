"""
IPC 处理器注册器模块
"""

from typing import Any, Dict, Optional, Callable, TypeVar, cast, ClassVar
from functools import wraps
from .ipc_types import IPCRequest
import json
from .ipc_types import create_error_response

# 定义处理器类型
HandlerType = TypeVar('HandlerType', bound=Callable[['IPCService', IPCRequest, Optional[Any]], str])

class IPCHandlerRegistry:
    """IPC 处理器注册器"""
    
    _handlers: ClassVar[Dict[str, HandlerType]] = {}
    
    @classmethod
    def register(cls, method: str) -> Callable[[HandlerType], HandlerType]:
        """注册处理器装饰器
        
        Args:
            method: 要处理的方法名
            
        Returns:
            Callable: 装饰器函数
        """
        def decorator(func: HandlerType) -> HandlerType:
            @wraps(func)
            def wrapper(self: 'IPCService', request: IPCRequest, params: Optional[Any]) -> str:
                try:
                    # 验证请求参数
                    if not isinstance(request, dict):
                        return json.dumps(create_error_response(
                            request,
                            'INVALID_REQUEST',
                            "Invalid request format"
                        ))
                    
                    # 调用处理器
                    return func(self, request, params)
                except Exception as e:
                    logger.error(f"Error in handler {method}: {e}")
                    return json.dumps(create_error_response(
                        request,
                        'HANDLER_ERROR',
                        f"Error in handler {method}: {str(e)}"
                    ))
            cls._handlers[method] = cast(HandlerType, wrapper)
            return cast(HandlerType, wrapper)
        return decorator
    
    @classmethod
    def get_handler(cls, method: str) -> Optional[HandlerType]:
        """获取处理器
        
        Args:
            method: 方法名
            
        Returns:
            Optional[HandlerType]: 处理器函数
        """
        return cls._handlers.get(method)
    
    @classmethod
    def list_handlers(cls) -> Dict[str, str]:
        """列出所有已注册的处理器
        
        Returns:
            Dict[str, str]: 处理器名称到处理器函数的映射
        """
        return {name: func.__name__ for name, func in cls._handlers.items()} 