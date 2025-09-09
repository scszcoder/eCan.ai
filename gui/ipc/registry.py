"""
IPC 处理器注册器模块
提供 IPC 请求处理器的注册、查找和管理功能
"""

from typing import Any, Dict, Optional, Callable, TypeVar, ClassVar, Tuple, Literal
from functools import wraps
from .types import IPCRequest, IPCResponse, create_error_response
from utils.logger_helper import logger_helper as logger

# 定义处理器函数类型
SyncHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]
BackgroundHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]

HandlerType = TypeVar('HandlerType')

class IPCHandlerRegistry:
    """IPC 处理器注册器
    
    用于注册和管理 IPC 请求处理器，提供装饰器接口用于注册处理器，
    并提供查找和列出已注册处理器的功能。
    """
    
    _handlers: ClassVar[Dict[str, SyncHandlerFunc]] = {}
    _background_handlers: ClassVar[Dict[str, BackgroundHandlerFunc]] = {}
    
    @classmethod
    def handler(cls, method: str) -> Callable[[Callable], Callable]:
        """同步处理器注册装饰器 (用于快速、非阻塞的任务)"""
        def decorator(func: SyncHandlerFunc) -> SyncHandlerFunc:
            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
                """同步处理器包装函数
                
                Args:
                    request: IPC 请求对象
                    params: 请求参数
                    
                Returns:
                    IPCResponse: 响应对象
                """
                try:
                    # 验证请求参数
                    if not isinstance(request, dict):
                        logger.error(f"[registry] Invalid request format for sync method {method}")
                        return create_error_response(
                            request or {},
                            'INVALID_REQUEST',
                            "Invalid request format"
                        )
                    
                    # 调用同步处理器
                    logger.debug(f"[registry] Calling sync handler for method {method}")
                    return func(request, params)
                    
                except Exception as e:
                    logger.error(f"[registry] Error in sync handler {method}: {e}", exc_info=True)
                    return create_error_response(
                        request or {},
                        'HANDLER_ERROR',
                        f"Error in sync handler {method}: {str(e)}"
                    )

            # 注册处理器
            if method in cls._handlers or method in cls._background_handlers:
                logger.warning(f"[registry] Handler for method {method} already exists, overwriting")

            cls._handlers[method] = wrapper
            
            logger.info(f"[registry] Registered sync handler for method: {method}")
            return func
            
        return decorator
    
    @classmethod
    def background_handler(cls, method: str) -> Callable[[Callable], Callable]:
        """后台处理器注册装饰器 (用于耗时、阻塞的任务)"""
        def decorator(func: BackgroundHandlerFunc) -> BackgroundHandlerFunc:
            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
                try:
                    logger.debug(f"[registry] Calling background handler for method {method}")
                    return func(request, params)
                except Exception as e:
                    logger.error(f"[registry] Error in background handler {method}: {e}", exc_info=True)
                    return {"error": "HANDLER_ERROR", "message": str(e)}
            if method in cls._handlers or method in cls._background_handlers:
                logger.warning(f"[registry] Handler for method {method} already exists, overwriting")
            cls._background_handlers[method] = wrapper
            logger.info(f"[registry] Registered background handler for method: {method}")
            return func
        return decorator
    
    @classmethod
    def get_handler(cls, method: str) -> Optional[Tuple[Callable, Literal['sync', 'background']]]:
        """根据方法名获取对应的处理器和类型"""
        if method in cls._handlers:
            logger.debug(f"[registry] Found sync handler for method: {method}")
            return cls._handlers[method], 'sync'
        if method in cls._background_handlers:
            logger.debug(f"[registry] Found background handler for method: {method}")
            return cls._background_handlers[method], 'background'
        
        logger.warning(f"No handler found for method {method}")
        return None
    
    @classmethod
    def list_handlers(cls) -> Dict[str, list[str]]:
        """列出所有已注册的处理器"""
        handlers = {
            "sync": list(cls._handlers.keys()),
            "background": list(cls._background_handlers.keys())
        }
        logger.debug(f"[registry] Listed handlers: {handlers}")
        return handlers
    
    @classmethod
    def clear_handlers(cls) -> None:
        """清除所有已注册的处理器"""
        cls._handlers.clear()
        cls._background_handlers.clear()
        logger.info("[registry] Cleared all handlers") 