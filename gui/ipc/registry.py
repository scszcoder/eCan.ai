"""
IPC Handler Registry Module
Unified IPC request handler registration, management and middleware system
"""

from typing import Any, Dict, Optional, Callable, TypeVar, ClassVar, Tuple, Literal, Set
from functools import wraps
import os
from .types import IPCRequest, IPCResponse, create_error_response, create_success_response
from .token_manager import token_manager
from utils.logger_helper import logger_helper as logger
from app_context import AppContext

# Define handler function types
SyncHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]
BackgroundHandlerFunc = Callable[[IPCRequest, Optional[Any]], IPCResponse]

HandlerType = TypeVar('HandlerType')


def _find_session_id(request: Optional[Dict[str, Any]], params: Optional[Dict[str, Any]]) -> Optional[str]:
    """Extract session_id from params or request meta."""
    if params and isinstance(params, dict) and params.get('session_id'):
        return params['session_id']
    if request and isinstance(request, dict):
        meta = request.get('meta', {})
        if isinstance(meta, dict):
            return meta.get('session_id')
    return None

class IPCHandlerRegistry:
    """Unified IPC handler registration and middleware system

    Provides unified interface for handler registration, middleware validation, and whitelist management
    All registered handlers automatically apply token validation and system checks
    """

    _handlers: ClassVar[Dict[str, SyncHandlerFunc]] = {}
    _background_handlers: ClassVar[Dict[str, BackgroundHandlerFunc]] = {}
    _handlers_loaded: ClassVar[bool] = False  # Track if all handlers have been loaded
    
    # Unified deduplication mechanism
    _registered_methods: ClassVar[Set[str]] = set()  # Track all registered method names
    _registration_lock: ClassVar[bool] = False  # Lock to prevent concurrent registration

    # Performance optimization: cache system ready status
    _system_ready_cache: ClassVar[Optional[bool]] = None
    _system_ready_cache_time: ClassVar[float] = 0
    _system_ready_cache_ttl: ClassVar[float] = 30.0  # Default cache 30 seconds
    _system_ready_short_ttl: ClassVar[float] = 5.0   # Short cache time when system is not ready

    # Whitelist: methods that skip token validation and system checks
    _whitelist: ClassVar[Set[str]] = {
        'login', 'signup', 'refresh_token', 'get_system_status',
        'ping', 'health_check', 'get_version', 'forgot_password',
        'confirm_forgot_password', 'google_login', 'wechat_login', 'get_last_login',
        'save_login_info', 'clear_login_info',  # Allow saving/clearing login credentials for remember password feature
        'force_close_oauth_port_blocker',  # pre-login recovery: kill stale eCan.exe holding the OAuth port
        'logout',  # logout doesn't need token validation, as it may be called when token is invalid
        'get_initialization_progress',  # Allow checking initialization progress when system is not ready
        'skill_editor.get_node_state_schema',  # Allow schema retrieval pre-auth/init for editor boot
        'getAppConfig',  # Allow runtime app config fetch pre-auth (returns auth_type, endpoints, region)
        # File operations should be usable early for local open/save
        'show_open_dialog', 'show_save_dialog', 'read_skill_file', 'write_skill_file', 'open_folder',
        # User preferences (language, theme) should be available before login
        'update_user_preferences',
        # Label config operations
        'label_config.get_all', 'label_config.save', 'label_config.delete', 'label_config.check_name',
        # Token management operations - these handlers validate tokens themselves
        'auth.getTokenInfo', 'auth.refreshToken', 'auth.extendToken',
        # CN / CloudBase auth: all login / signup / phone flows run before a session exists,
        # so they cannot carry a token. Mirrors intl's `login`/`signup`/`google_login` policy.
        'cloudbase_check_config',
        'cloudbase_login',
        'cloudbase_signup',
        'cloudbase_signup_confirm',
        'cloudbase_phone_login',
        'cloudbase_phone_signup',
        'cloudbase_send_code',
        'cloudbase_verify_code',
        'cloudbase_forgot_password',
        'cloudbase_reset_password',
        'cloudbase_wechat_h5_login',
        'cloudbase_wechat_qr_login',
        'cloudbase_logout',
        'cloudbase_refresh_token',
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
    def _validate_token(cls, request: IPCRequest, params: Optional[Dict[str, Any]]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Validate token from request.token (standard approach)
        
        Token should be in request.token, extracted from HTTP Authorization header.
        No fallback to params to avoid masking issues.

        Returns:
            Tuple[bool, Optional[str]]: (is valid, error message)
        """
        try:
            # Get token from request.token (standard design)
            token = None
            if isinstance(request, dict):
                token = request.get('token')
            
            if not token:
                logger.warning(f"[registry] TOKEN_REQUIRED: No token in request.token")
                return False, "TOKEN_REQUIRED", None
            
            # Validate token
            if token_manager.validate_token(token):
                return True, None, None
            else:
                logger.warning(f"[registry] INVALID_TOKEN: Token validation failed for {token[:8]}...")
                return False, "INVALID_TOKEN", token_manager.get_invalid_token_reason(token)

        except Exception as e:
            logger.error(f"[registry] Error validating token: {e}")
            return False, "TOKEN_VALIDATION_ERROR", None

    @classmethod
    def _check_system_ready(cls) -> Tuple[bool, Optional[str]]:
        """Immediately check if system is ready (with smart cache optimization)

        Returns:
            Tuple[bool, Optional[str]]: (is ready, error message)
        """
        import time

        try:
            current_time = time.time()

            # In web mode we don't rely on Qt MainWindow; treat backend as ready
            if os.getenv("ECAN_MODE", "desktop") == "web":
                cls._system_ready_cache = True
                cls._system_ready_cache_time = current_time
                return True, None

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
        
        # Trust requests from local HTTP server (desktop mode)
        # These come from LocalServer.py which is only accessible on localhost
        if request.get('source') == 'local_server':
            logger.debug(f"[registry] Bypassing token validation for local_server request: {method}")
            return None

        # Ensure request object has required fields
        if 'id' not in request:
            request['id'] = f"middleware_check_{method}"

        # IMPORTANT: Token validation MUST come BEFORE system ready check
        # This ensures unauthenticated users see login prompt instead of "system not ready"
        
        # In web mode, allow authenticated session_id to bypass token requirement
        if os.getenv("ECAN_MODE", "desktop") == "web":
            session_id = _find_session_id(request, params)
            if session_id:
                try:
                    from gui.context.session_manager import SessionManager
                    if SessionManager.get_instance().get_context(session_id):
                        # Valid session, skip token validation
                        pass
                    else:
                        return create_error_response(
                            request,
                            'SESSION_NOT_FOUND',
                            f"Session {session_id} not found or expired"
                        )
                except Exception as e:
                    logger.error(f"[registry] Error validating session_id {session_id}: {e}")
            else:
                # No session_id in web mode, validate token
                token_valid, token_error, token_details = cls._validate_token(request, params)
                if not token_valid:
                    logger.warning(f"[registry] Token validation failed for method {method}: {token_error}")
                    return create_error_response(
                        request,
                        token_error or 'TOKEN_INVALID',
                        f"Token validation failed for method {method}",
                        token_details
                    )
        else:
            # Desktop mode: always validate token
            token_valid, token_error, token_details = cls._validate_token(request, params)
            if not token_valid:
                logger.warning(f"[registry] Token validation failed for method {method}: {token_error}")
                return create_error_response(
                    request,
                    token_error or 'TOKEN_INVALID',
                    f"Token validation failed for method {method}",
                    token_details
                )

        # Check system ready status AFTER token validation
        # This ensures authenticated users see appropriate initialization messages
        system_ready, system_error = cls._check_system_ready()
        if not system_ready:
            logger.debug(f"[registry] System not ready for method {method}: {system_error}")
            return create_error_response(
                request,
                system_error or 'SYSTEM_NOT_READY',
                f"System not ready for method {method}"
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

            # Use unified registration mechanism
            if not cls._register_method(method, 'sync'):
                return func

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

            # Use unified registration mechanism
            if not cls._register_method(method, 'background'):
                return func
            
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
        cls._registered_methods.clear()
        logger.info("[registry] Cleared all handlers")
    
    @classmethod
    def reset_registration_state(cls) -> None:
        """Reset registration state - useful when reloading handlers
        
        This should be called before reloading handler modules to allow re-registration.
        """
        cls._registered_methods.clear()
        cls._handlers_loaded = False
        logger.info("[registry] Reset registration state - handlers can be re-registered")
    
    @classmethod
    def is_method_registered(cls, method: str) -> bool:
        """Check if a method is already registered
        
        Args:
            method: Method name to check
            
        Returns:
            bool: True if method is already registered
        """
        return method in cls._registered_methods
    
    @classmethod
    def _register_method(cls, method: str, handler_type: str) -> bool:
        """Unified method registration with deduplication
        
        Args:
            method: Method name to register
            handler_type: Type of handler ('sync' or 'background')
            
        Returns:
            True if registration should proceed, False if already registered
        """
        # Check if method already registered
        if method in cls._registered_methods:
            logger.warning(f"[registry]  DUPLICATE REGISTRATION DETECTED: Method '{method}' (type: {handler_type}) already registered, skipping")
            import traceback
            logger.warning(f"[registry] Call stack:\n{''.join(traceback.format_stack()[-5:-1])}")
            return False
        
        # Check for type conflicts
        if method in cls._handlers and handler_type == 'background':
            logger.warning(f"[registry]  TYPE CONFLICT: Method '{method}' already registered as sync handler, cannot register as background")
            import traceback
            logger.warning(f"[registry] Call stack:\n{''.join(traceback.format_stack()[-5:-1])}")
            return False
        
        if method in cls._background_handlers and handler_type == 'sync':
            logger.warning(f"[registry]  TYPE CONFLICT: Method '{method}' already registered as background handler, cannot register as sync")
            import traceback
            logger.warning(f"[registry] Call stack:\n{''.join(traceback.format_stack()[-5:-1])}")
            return False
        
        # Mark as registered
        cls._registered_methods.add(method)
        return True

    @classmethod
    async def handle_graphql_request(cls, method: str, variables: Dict[str, Any], request: Optional[IPCRequest] = None) -> Any:
        """Handle GraphQL request from LocalServer or AppSync Lambda
        
        Converts GraphQL request to IPC format, processes it, and returns result directly.
        Background handlers are executed in a thread pool to avoid blocking.
        
        Args:
            method: API method name (e.g., 'readSkillFile', 'getAgents')
            variables: GraphQL variables/arguments
            request: Optional IPC request with token from Authorization header
            
        Returns:
            Direct result data (for GraphQL response wrapping)
            
        Raises:
            Exception: If handler execution fails (GraphQL will wrap as error)
        """
        try:
            # Ensure all handler modules are loaded before looking up
            from gui.ipc.w2p_handlers import _ensure_handlers_loaded
            _ensure_handlers_loaded()

            # Use the provided IPC request (contains token from Authorization header)
            ipc_request = request

            # Get handler
            handler_info = cls.get_handler(method)
            if not handler_info:
                logger.warning(f"[registry] No handler found for GraphQL method: {method}")
                raise RuntimeError(f"No handler registered for method: {method}")
            
            handler, handler_type = handler_info
            
            # Execute handler - background handlers run in thread pool to avoid blocking
            logger.debug(f"[registry] Executing {handler_type} handler for GraphQL method: {method}")
            
            if handler_type == 'background':
                # Run blocking handler in thread pool
                import asyncio
                loop = asyncio.get_event_loop()
                ipc_response = await loop.run_in_executor(None, handler, ipc_request, variables)
            else:
                # Sync handler runs directly
                ipc_response = handler(ipc_request, variables)
            
            # For GraphQL, return data directly or raise exception
            if ipc_response.get('status') == 'success':
                return ipc_response.get('result')
            else:
                error_info = ipc_response.get('error', {})
                error_message = error_info.get('message', 'Request failed')
                error_code = error_info.get('code', 'UNKNOWN_ERROR')
                error_details = error_info.get('details')

                # Transient / expected errors that callers handle gracefully
                # (rate limits, expired tokens, plan gating, partial server
                # failures). The handler already logged the upstream error;
                # we MUST NOT also emit an ERROR + stack trace here — that
                # floods runlogs on every 429/401 storm. Re-raise without
                # a stack trace so apiRouter can return a typed response.
                _TRANSIENT_ERROR_CODES = {
                    'PROVIDER_MODELS_ERROR',  # cloud 429/401 on /v1/models
                    'API_KEY_ERROR',          # myAPIKeygen partial / scoped failure
                }
                _is_transient_unavailable = (
                    'connection refused' in error_message.lower()
                    or 'failed to establish a new connection' in error_message.lower()
                    or 'max retries exceeded' in error_message.lower()
                )
                if error_code in _TRANSIENT_ERROR_CODES or _is_transient_unavailable:
                    logger.warning(
                        f"[registry] {error_code} for {method} (server unavailable, "
                        f"frontend will retry): {error_message}"
                    )
                else:
                    # Log the full error response for debugging
                    logger.error(f"[registry] Handler {method} returned error: code={error_code}, message={error_message}")
                    logger.error(f"[registry] Full error response: {ipc_response}")

                # Create exception with error code for proper handling. Use
                # the exception class — no stack trace is emitted because
                # the error is raised (and re-raised) by the same line.
                error = RuntimeError(error_message)
                error.error_code = error_code  # type: ignore
                error.error_details = error_details  # type: ignore
                raise error
                
        except Exception as e:
            # Use warning level for expected auth errors, error level for unexpected errors
            error_code = getattr(e, 'error_code', None)
            # LightRAG connection-refused: the 3-attempt retry in
            # ``LightragClient.get_documents_paginated`` already absorbed the
            # brief startup race after a restart. The frontend's
            # ``isConnectionErrorMessage()`` then takes over with its own
            # 10×2s "Waiting for LightRAG server…" retry. Re-emitting the
            # urllib3 traceback here only floods the runlog on every poll.
            err_text = str(e).lower()
            _is_transient_unavailable = (
                'connection refused' in err_text
                or 'failed to establish a new connection' in err_text
                or 'max retries exceeded' in err_text
            )
            if _is_transient_unavailable:
                logger.warning(
                    f"[registry] {error_code} for method {method} (server unavailable, "
                    f"frontend will retry): {e}"
                )
            elif error_code in ('INVALID_TOKEN', 'TOKEN_REQUIRED', 'SYSTEM_NOT_READY',
                              'LOGIN_FAILED', 'CLOUDBASE_NOT_AVAILABLE',
                              'INVALID_PARAMS', 'INVALID_CREDENTIALS', 'SMS_SEND_FAILED',
                              # Transient cloud-side responses (rate limit, expired
                              # key, plan gating). The handler already logged the
                              # upstream error; re-raising here would only emit a
                              # second stack trace.
                              'PROVIDER_MODELS_ERROR'):
                # Expected user-visible errors - log as warning without stack trace
                logger.warning(f"[registry] {error_code} for method {method}: {e}")
            else:
                # Unexpected errors - log as error with full stack trace
                logger.error(f"[registry] Error handling GraphQL request for {method}: {e}", exc_info=True)
            raise
