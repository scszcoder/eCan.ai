"""
IPC 处理器注册器模块
统一的IPC请求处理器注册、管理和中间件系统
"""

from typing import Any, Dict, Optional, Callable, TypeVar, ClassVar, Tuple, Literal, Set
from functools import wraps
from .types import IPCRequest, IPCResponse, create_error_response, create_success_response
from .token_manager import token_manager
from utils.logger_helper import logger_helper as logger
from app_context import AppContext

# 定义处理器函数类型
SyncHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]
BackgroundHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]

HandlerType = TypeVar('HandlerType')

class IPCHandlerRegistry:
    """统一的IPC处理器注册和中间件系统

    提供处理器注册、中间件验证、白名单管理的统一接口
    所有注册的处理器自动应用token验证和系统检查
    """

    _handlers: ClassVar[Dict[str, SyncHandlerFunc]] = {}
    _background_handlers: ClassVar[Dict[str, BackgroundHandlerFunc]] = {}

    # 性能优化：缓存系统就绪状态
    _system_ready_cache: ClassVar[Optional[bool]] = None
    _system_ready_cache_time: ClassVar[float] = 0
    _system_ready_cache_ttl: ClassVar[float] = 30.0  # 默认缓存30秒
    _system_ready_short_ttl: ClassVar[float] = 5.0   # 系统未就绪时的短缓存时间

    # 白名单：跳过token验证和系统检查的方法
    _whitelist: ClassVar[Set[str]] = {
        'login', 'signup', 'refresh_token', 'get_system_status',
        'ping', 'health_check', 'get_version', 'forgot_password',
        'confirm_forgot_password', 'google_login', 'get_last_login',
        'get_initialization_progress',  # 允许在系统未就绪时检查初始化进度
        'skill_editor.get_node_state_schema',  # Allow schema retrieval pre-auth/init for editor boot
    }
    
    @classmethod
    def get_whitelist(cls) -> Set[str]:
        """获取当前白名单"""
        return cls._whitelist.copy()

    @classmethod
    def clear_system_ready_cache(cls):
        """清理系统就绪状态缓存（在系统状态变化时调用）"""
        cls._system_ready_cache = None
        cls._system_ready_cache_time = 0
        logger.debug("[registry] System ready cache cleared")

    @classmethod
    def force_system_ready(cls, ready: bool = True):
        """强制设置系统就绪状态（用于系统初始化完成时）"""
        import time
        cls._system_ready_cache = ready
        cls._system_ready_cache_time = time.time()
        logger.info(f"[registry] System ready status forced to: {ready}")

    @classmethod
    def set_cache_ttl(cls, ready_ttl: float = 30.0, not_ready_ttl: float = 5.0):
        """动态调整缓存TTL

        Args:
            ready_ttl: 系统就绪时的缓存时间（秒）
            not_ready_ttl: 系统未就绪时的缓存时间（秒）
        """
        cls._system_ready_cache_ttl = ready_ttl
        cls._system_ready_short_ttl = not_ready_ttl
        logger.info(f"[registry] Cache TTL updated: ready={ready_ttl}s, not_ready={not_ready_ttl}s")

    @classmethod
    def get_cache_info(cls) -> dict:
        """获取缓存状态信息"""
        import time
        current_time = time.time()

        if cls._system_ready_cache is None:
            return {
                "cached": False,
                "status": None,
                "age": 0,
                "ttl": cls._system_ready_cache_ttl,
                "expires_in": 0
            }

        age = current_time - cls._system_ready_cache_time
        effective_ttl = cls._system_ready_cache_ttl if cls._system_ready_cache else cls._system_ready_short_ttl
        expires_in = max(0, effective_ttl - age)

        return {
            "cached": True,
            "status": cls._system_ready_cache,
            "age": age,
            "ttl": effective_ttl,
            "expires_in": expires_in,
            "valid": expires_in > 0
        }
    
    @classmethod
    def add_to_whitelist(cls, method: str) -> None:
        """添加方法到白名单"""
        cls._whitelist.add(method)
        logger.info(f"[IPCRegistry] Added {method} to whitelist")
    
    @classmethod
    def remove_from_whitelist(cls, method: str) -> None:
        """从白名单移除方法"""
        cls._whitelist.discard(method)
        logger.info(f"[IPCRegistry] Removed {method} from whitelist")
    
    @classmethod
    def _validate_token(cls, request: IPCRequest, params: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """验证token（优化版本）

        Returns:
            Tuple[bool, Optional[str]]: (是否有效, 错误信息)
        """
        try:
            # 优化：快速路径 - 直接从 params 获取 token
            token = None
            if params and isinstance(params, dict):
                token = params.get('token')
                if token:
                    # 快速验证路径
                    if token_manager.validate_token(token):
                        return True, None
                    else:
                        return False, "INVALID_TOKEN"

            # 备用路径：从请求中查找 token
            if isinstance(request, dict):
                # 优先检查顶级 token 字段
                token = request.get('token')
                if not token:
                    # 再检查 args 中的 token
                    args = request.get('args', {})
                    if isinstance(args, dict):
                        token = args.get('token')

            if not token:
                return False, "TOKEN_REQUIRED"

            # 使用token_manager验证token
            if token_manager.validate_token(token):
                return True, None
            else:
                return False, "INVALID_TOKEN"

        except Exception as e:
            logger.error(f"[registry] Error validating token: {e}")
            return False, "TOKEN_VALIDATION_ERROR"
    
    @classmethod
    def _check_system_ready(cls) -> Tuple[bool, Optional[str]]:
        """立即检查系统是否已准备就绪（带智能缓存优化）

        Returns:
            Tuple[bool, Optional[str]]: (是否就绪, 错误信息)
        """
        import time

        try:
            current_time = time.time()

            # 检查缓存是否有效（使用动态TTL）
            if cls._system_ready_cache is not None:
                # 根据缓存状态选择不同的TTL
                effective_ttl = cls._system_ready_cache_ttl if cls._system_ready_cache else cls._system_ready_short_ttl

                if current_time - cls._system_ready_cache_time < effective_ttl:
                    # 使用缓存结果，不更新时间戳
                    if cls._system_ready_cache:
                        return True, None
                    else:
                        return False, "SYSTEM_NOT_READY"

            # 缓存过期或不存在，重新检查
            main_window = AppContext.get_main_window()

            if main_window is None:
                # 系统未就绪时使用较短的缓存时间（5秒）
                cls._system_ready_cache = False
                cls._system_ready_cache_time = current_time
                logger.debug("[Registry] MainWindow not available yet")
                return False, "MAIN_WINDOW_NOT_AVAILABLE"

            # 立即检查系统状态，不等待
            is_ready = main_window.get_main_window_safely()

            # 智能缓存：根据状态设置不同的缓存时间
            if is_ready:
                # 系统就绪时使用长缓存（30秒）
                cls._system_ready_cache = True
                cls._system_ready_cache_time = current_time
                return True, None
            else:
                # 系统未就绪时使用短缓存（5秒），因为状态可能快速变化
                cls._system_ready_cache = False
                cls._system_ready_cache_time = current_time
                logger.debug("[Registry] MainWindow not fully initialized yet")
                return False, "SYSTEM_NOT_READY"

        except Exception as e:
            # 异常情况下不缓存，直接返回
            logger.error(f"[registry] Error checking system readiness: {e}")
            return False, "SYSTEM_CHECK_ERROR"
    
    @classmethod
    def _apply_middleware(cls, method: str, request: IPCRequest, params: Optional[Dict[str, Any]]) -> Optional[IPCResponse]:
        """应用中间件检查（优化版本）

        Args:
            method: 方法名
            request: IPC请求对象
            params: 请求参数

        Returns:
            Optional[IPCResponse]: 如果检查失败返回错误响应，否则返回None
        """
        # 快速路径：检查是否在白名单中
        if method in cls._whitelist:
            # 减少日志输出以提高性能
            return None

        # 确保请求对象有必需的字段
        if 'id' not in request:
            request['id'] = f"middleware_check_{method}"

        # 优化：先检查系统就绪状态（通常更快，且有缓存）
        system_ready, system_error = cls._check_system_ready()
        if not system_ready:
            # 减少日志输出以提高性能，只在需要时记录
            logger.debug(f"[registry] System not ready for method {method}: {system_error}")
            return create_error_response(
                request,
                system_error or 'SYSTEM_NOT_READY',
                f"System not ready for method {method}"
            )

        # Token验证（放在系统检查之后，因为系统未就绪时无需验证token）
        token_valid, token_error = cls._validate_token(request, params)
        if not token_valid:
            logger.warning(f"[registry] Token validation failed for method {method}: {token_error}")
            return create_error_response(
                request,
                token_error or 'TOKEN_INVALID',
                f"Token validation failed for method {method}"
            )

        return None
    
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
                    
                    # 应用中间件逻辑
                    middleware_response = cls._apply_middleware(method, request, params)
                    if middleware_response:
                        return middleware_response
                    
                    # 调用处理器
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
            
            # logger.info(f"[registry] Registered sync handler for method: {method}")
            return func
            
        return decorator
    
    @classmethod
    def background_handler(cls, method: str) -> Callable[[Callable], Callable]:
        """后台处理器注册装饰器 (用于耗时、阻塞的任务)"""
        def decorator(func: BackgroundHandlerFunc) -> BackgroundHandlerFunc:
            
            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
                try:
                    # 验证请求参数
                    if not isinstance(request, dict):
                        logger.error(f"[registry] Invalid request format for background method {method}")
                        return create_error_response(
                            request or {},
                            'INVALID_REQUEST',
                            "Invalid request format"
                        )
                    
                    # 应用中间件逻辑
                    middleware_response = cls._apply_middleware(method, request, params)
                    if middleware_response:
                        return middleware_response
                    
                    # 调用处理器
                    logger.debug(f"[registry] Calling background handler for method {method}")
                    return func(request, params)
                    
                except Exception as e:
                    logger.error(f"[registry] Error in background handler {method}: {e}", exc_info=True)
                    return create_error_response(
                        request or {},
                        'HANDLER_ERROR',
                        f"Error in background handler {method}: {str(e)}"
                    )
                    
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
            # logger.debug(f"[registry] Found sync handler for method: {method}")
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
        # logger.debug(f"[registry] Listed handlers: {handlers}")
        return handlers
    
    @classmethod
    def clear_handlers(cls) -> None:
        """清除所有已注册的处理器"""
        cls._handlers.clear()
        cls._background_handlers.clear()
        logger.info("[registry] Cleared all handlers") 