"""
IPC 处理器注册器模块
提供 IPC 请求处理器的注册、查找和管理功能
"""

from typing import Any, Dict, Optional, Callable, TypeVar, cast, ClassVar
from functools import wraps
from .types import IPCRequest, create_error_response
from utils.logger_helper import logger_helper
import json

logger = logger_helper.logger

# 定义处理器函数类型
HandlerFunc = Callable[[IPCRequest, Optional[Any], Optional[Any]], str]
HandlerType = TypeVar('HandlerType', bound=HandlerFunc)

class IPCHandlerRegistry:
    """IPC 处理器注册器
    
    用于注册和管理 IPC 请求处理器，提供装饰器接口用于注册处理器，
    并提供查找和列出已注册处理器的功能。
    """
    
    _handlers: ClassVar[Dict[str, HandlerType]] = {}
    
    @classmethod
    def handler(cls, method: str) -> Callable[[HandlerType], HandlerType]:
        """处理器注册装饰器
        
        用于注册处理特定 IPC 方法的处理器函数。
        
        Args:
            method: 要处理的方法名
            
        Returns:
            Callable: 装饰器函数
            
        Example:
            @IPCHandlerRegistry.handler('login')
            def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> str:
                # 处理逻辑
                pass
        """
        def decorator(func: HandlerType) -> HandlerType:
            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]], py_login: Optional[Any]) -> str:
                """处理器包装函数
                
                Args:
                    request: IPC 请求对象
                    params: 请求参数
                    
                Returns:
                    str: JSON 格式的响应消息
                """
                try:
                    # 验证请求参数
                    if not isinstance(request, dict):
                        logger.error(f"Invalid request format for method {method}")
                        return json.dumps(create_error_response(
                            request or {},
                            'INVALID_REQUEST',
                            "Invalid request format"
                        ))
                    
                    # 调用处理器
                    logger.debug(f"Calling handler for method {method}")
                    return func(request, params, py_login)
                    
                except Exception as e:
                    logger.error(f"Error in handler {method}: {e}")
                    return json.dumps(create_error_response(
                        request or {},
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
    def list_handlers(cls) -> list[str]:
        """列出所有已注册的处理器
        
        返回所有已注册处理器的方法名列表。
        
        Returns:
            list[str]: 已注册处理器的方法名列表
        """
        handlers = list(cls._handlers.keys())
        logger.debug(f"Listed {len(handlers)} handlers")
        return handlers
    
    @classmethod
    def clear_handlers(cls) -> None:
        """清除所有已注册的处理器
        
        用于测试或重置处理器注册表。
        """
        cls._handlers.clear()
        logger.info("Cleared all handlers") 