"""
IPC Handler Registry Module
Unified IPC request handler registration, management and middleware system
"""

from typing import Any, Dict, Optional, Callable, TypeVar, ClassVar, Tuple, Literal, Set
from functools import wraps
from .types import IPCRequest, IPCResponse, create_error_response, create_success_response
from .token_manager import token_manager
from utils.logger_helper import logger_helper as logger
from app_context import AppContext

# Define handler function types
SyncHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]
BackgroundHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]

HandlerType = TypeVar('HandlerType')

class IPCHandlerRegistry:
    """Unified IPC handler registration and middleware system

    Provides unified interface for handler registration, middleware validation, and whitelist management
    All registered handlers automatically apply token validation and system checks
    """

    _handlers: ClassVar[Dict[str, SyncHandlerFunc]] = {}
    _background_handlers: ClassVar[Dict[str, BackgroundHandlerFunc]] = {}
    _handlers_loaded: ClassVar[bool] = False  # Track if all handlers have been loaded

    # Performance optimization: cache system ready status
    _system_ready_cache: ClassVar[Optional[bool]] = None
    _system_ready_cache_time: ClassVar[float] = 0
    _system_ready_cache_ttl: ClassVar[float] = 30.0  # Default cache 30 seconds
    _system_ready_short_ttl: ClassVar[float] = 5.0   # Short cache time when system is not ready

    # Whitelist: methods that skip token validation and system checks
    _whitelist: ClassVar[Set[str]] = {
        'login', 'signup', 'refresh_token', 'get_system_status',
        'ping', 'health_check', 'get_version', 'forgot_password',
        'confirm_forgot_password', 'google_login', 'get_last_login',
        'logout',  # logout doesn't need token validation, as it may be called when token is invalid
        'get_initialization_progress',  # Allow checking initialization progress when system is not ready
        'skill_editor.get_node_state_schema',  # Allow schema retrieval pre-auth/init for editor boot
        # File operations should be usable early for local open/save
        'show_open_dialog', 'show_save_dialog', 'read_skill_file', 'write_skill_file', 'open_folder',
        # User preferences (language, theme) should be available before login
        'update_user_preferences',
        # Label config operations
        'label_config.get_all', 'label_config.save', 'label_config.delete', 'label_config.check_name',
    }

    @classmethod
    def get_whitelist(cls) -> Set[str]:
        """Get current whitelist"""
        return cls._whitelist.copy()

    @classmethod
    def clear_system_ready_cache(cls):
        """Clear system ready status cache (called when system status changes)"""
        cls._system_ready_cache = None
        cls._system_ready_cache_time = 0
        logger.debug("[registry] System ready cache cleared")

    @classmethod
    def force_system_ready(cls, ready: bool = True):
        """Force set system ready status (used when system initialization completes)"""
        import time
        cls._system_ready_cache = ready
        cls._system_ready_cache_time = time.time()
        logger.info(f"[registry] System ready status forced to: {ready}")

    @classmethod
    def set_cache_ttl(cls, ready_ttl: float = 30.0, not_ready_ttl: float = 5.0):
        """Dynamically adjust cache TTL

        Args:
            ready_ttl: Cache time when system is ready (seconds)
            not_ready_ttl: Cache time when system is not ready (seconds)
        """
        cls._system_ready_cache_ttl = ready_ttl
        cls._system_ready_short_ttl = not_ready_ttl
        logger.info(f"[registry] Cache TTL updated: ready={ready_ttl}s, not_ready={not_ready_ttl}s")

    @classmethod
    def get_cache_info(cls) -> dict:
        """Get cache status information"""
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
        """Add method to whitelist"""
        cls._whitelist.add(method)
        logger.info(f"[IPCRegistry] Added {method} to whitelist")

    @classmethod
    def remove_from_whitelist(cls, method: str) -> None:
        """Remove method from whitelist"""
        cls._whitelist.discard(method)
        logger.info(f"[IPCRegistry] Removed {method} from whitelist")

    @classmethod
    def _validate_token(cls, request: IPCRequest, params: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """Validate token (optimized version)

        Returns:
            Tuple[bool, Optional[str]]: (is valid, error message)
        """
        try:
            # Optimization: fast path - get token directly from params
            token = None
            if params and isinstance(params, dict):
                token = params.get('token')
                if token:
                    # Fast validation path
                    if token_manager.validate_token(token):
                        return True, None
                    else:
                        return False, "INVALID_TOKEN"

            # Fallback path: find token from request
            if isinstance(request, dict):
                # Check top-level token field first
                token = request.get('token')
                if not token:
                    # Then check token in args
                    args = request.get('args', {})
                    if isinstance(args, dict):
                        token = args.get('token')

            if not token:
                return False, "TOKEN_REQUIRED"

            # Use token_manager to validate token
            if token_manager.validate_token(token):
                return True, None
            else:
                return False, "INVALID_TOKEN"

        except Exception as e:
            logger.error(f"[registry] Error validating token: {e}")
            return False, "TOKEN_VALIDATION_ERROR"

    @classmethod
    def _check_system_ready(cls) -> Tuple[bool, Optional[str]]:
        """Immediately check if system is ready (with smart cache optimization)

        Returns:
            Tuple[bool, Optional[str]]: (is ready, error message)
        """
        import time

        try:
            current_time = time.time()

            # Check if cache is valid (using dynamic TTL)
            if cls._system_ready_cache is not None:
                # Choose different TTL based on cache status
                effective_ttl = cls._system_ready_cache_ttl if cls._system_ready_cache else cls._system_ready_short_ttl

                if current_time - cls._system_ready_cache_time < effective_ttl:
                    # Use cached result, don't update timestamp
                    if cls._system_ready_cache:
                        return True, None
                    else:
                        return False, "SYSTEM_NOT_READY"

            # Cache expired or doesn't exist, recheck
            main_window = AppContext.get_main_window()

            if main_window is None:
                # Use shorter cache time when system is not ready (5 seconds)
                cls._system_ready_cache = False
                cls._system_ready_cache_time = current_time
                logger.debug("[Registry] MainWindow not available yet")
                return False, "MAIN_WINDOW_NOT_AVAILABLE"

            # Check system status immediately, don't wait
            is_ready = main_window.get_main_window_safely()

            # Smart cache: set different cache time based on status
            if is_ready:
                # Use long cache when system is ready (30 seconds)
                cls._system_ready_cache = True
                cls._system_ready_cache_time = current_time
                return True, None
            else:
                # Use short cache when system is not ready (5 seconds), as status may change quickly
                cls._system_ready_cache = False
                cls._system_ready_cache_time = current_time
                logger.debug("[Registry] MainWindow not fully initialized yet")
                return False, "SYSTEM_NOT_READY"

        except Exception as e:
            # Don't cache in exception case, return directly
            logger.error(f"[registry] Error checking system readiness: {e}")
            return False, "SYSTEM_CHECK_ERROR"

    @classmethod
    def _apply_middleware(cls, method: str, request: IPCRequest, params: Optional[Dict[str, Any]]) -> Optional[IPCResponse]:
        """Apply middleware checks (optimized version)

        Args:
            method: Method name
            request: IPC request object
            params: Request parameters

        Returns:
            Optional[IPCResponse]: Returns error response if check fails, otherwise returns None
        """
        # Fast path: check if in whitelist
        if method in cls._whitelist:
            # Reduce log output to improve performance
            return None

        # Ensure request object has required fields
        if 'id' not in request:
            request['id'] = f"middleware_check_{method}"

        # Optimization: check system ready status first (usually faster, and has cache)
        system_ready, system_error = cls._check_system_ready()
        if not system_ready:
            # Reduce log output to improve performance, only log when needed
            logger.debug(f"[registry] System not ready for method {method}: {system_error}")
            return create_error_response(
                request,
                system_error or 'SYSTEM_NOT_READY',
                f"System not ready for method {method}"
            )

        # Token validation (after system check, as token validation is not needed when system is not ready)
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
        """Synchronous handler registration decorator (for fast, non-blocking tasks)"""
        def decorator(func: SyncHandlerFunc) -> SyncHandlerFunc:

            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
                """Synchronous handler wrapper function

                Args:
                    request: IPC request object
                    params: Request parameters

                Returns:
                    IPCResponse: Response object
                """
                try:
                    # Validate request parameters
                    if not isinstance(request, dict):
                        logger.error(f"[registry] Invalid request format for sync method {method}")
                        return create_error_response(
                            request or {},
                            'INVALID_REQUEST',
                            "Invalid request format"
                        )

                    # Apply middleware logic
                    middleware_response = cls._apply_middleware(method, request, params)
                    if middleware_response:
                        return middleware_response

                    # Call handler
                    logger.debug(f"[registry] Calling sync handler for method {method}")
                    return func(request, params)

                except Exception as e:
                    logger.error(f"[registry] Error in sync handler {method}: {e}", exc_info=True)
                    return create_error_response(
                        request or {},
                        'HANDLER_ERROR',
                        f"Error in sync handler {method}: {str(e)}"
                    )

            # Register handler
            if method in cls._handlers or method in cls._background_handlers:
                logger.warning(f"[registry] Handler for method {method} already exists, overwriting")

            cls._handlers[method] = wrapper

            # logger.info(f"[registry] Registered sync handler for method: {method}")
            return func

        return decorator

    @classmethod
    def background_handler(cls, method: str) -> Callable[[Callable], Callable]:
        """Background handler registration decorator (for time-consuming, blocking tasks)"""
        def decorator(func: BackgroundHandlerFunc) -> BackgroundHandlerFunc:

            @wraps(func)
            def wrapper(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
                try:
                    # Validate request parameters
                    if not isinstance(request, dict):
                        logger.error(f"[registry] Invalid request format for background method {method}")
                        return create_error_response(
                            request or {},
                            'INVALID_REQUEST',
                            "Invalid request format"
                        )

                    # Apply middleware logic
                    middleware_response = cls._apply_middleware(method, request, params)
                    if middleware_response:
                        return middleware_response

                    # Call handler
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
        """Get corresponding handler and type by method name"""
        if method in cls._handlers:
            # logger.debug(f"[registry] Found sync handler for method: {method}")
            return cls._handlers[method], 'sync'
        if method in cls._background_handlers:
            logger.debug(f"[registry] Found background handler for method: {method}")
            return cls._background_handlers[method], 'background'

        # Lazy load handlers if not found
        if not cls._handlers_loaded:
            logger.info("[registry] Lazy loading remaining handlers...")
            try:
                from gui.ipc.w2p_handlers import _ensure_handlers_loaded
                _ensure_handlers_loaded()
                cls._handlers_loaded = True
                
                # Try again after loading
                if method in cls._handlers:
                    return cls._handlers[method], 'sync'
                if method in cls._background_handlers:
                    return cls._background_handlers[method], 'background'
            except Exception as e:
                logger.error(f"[registry] Failed to lazy load handlers: {e}")

        logger.warning(f"No handler found for method {method}")
        return None

    @classmethod
    def list_handlers(cls) -> Dict[str, list[str]]:
        """List all registered handlers"""
        handlers = {
            "sync": list(cls._handlers.keys()),
            "background": list(cls._background_handlers.keys())
        }
        # logger.debug(f"[registry] Listed handlers: {handlers}")
        return handlers

    @classmethod
    def clear_handlers(cls) -> None:
        """Clear all registered handlers"""
        cls._handlers.clear()
        cls._background_handlers.clear()
        logger.info("[registry] Cleared all handlers")