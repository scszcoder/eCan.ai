"""
Context Bridge - Connects IPC Handlers to Context Providers

This module provides a bridge between the IPC handler system and the
context management system. It allows handlers to get the appropriate
context provider based on deployment mode and request context.

Usage in handlers:
    from gui.ipc.context_bridge import get_handler_context
    
    @IPCHandlerRegistry.handler('my_handler')
    def handle_my_request(request, params):
        ctx = get_handler_context(request, params)
        agents = ctx.get_agents()
        # ... rest of handler logic

This is the key integration point for Phase 3 of the web deployment migration.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import os
from threading import local

from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from gui.context.provider import ContextProvider


# Thread-local storage for request context
_request_context = local()


def get_deployment_mode() -> str:
    """Get current deployment mode"""
    return os.getenv("ECAN_MODE", "desktop")


def set_request_session_id(session_id: str) -> None:
    """
    Set the session ID for the current request (thread-local).
    
    This is called by the WebSocket server before invoking a handler,
    allowing the handler to access the correct user context.
    
    Args:
        session_id: The session ID for this request
    """
    _request_context.session_id = session_id


def get_request_session_id() -> Optional[str]:
    """
    Get the session ID for the current request.
    
    Returns:
        Session ID if set, None otherwise
    """
    return getattr(_request_context, 'session_id', None)


def clear_request_session_id() -> None:
    """Clear the session ID for the current request"""
    if hasattr(_request_context, 'session_id'):
        del _request_context.session_id


def get_handler_context(
    request: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> 'ContextProvider':
    """
    Get the appropriate context provider for the current handler invocation.
    
    This is the main function handlers should use to access user context.
    It automatically detects the deployment mode and returns the right provider.
    
    In desktop mode:
        Returns DesktopContextProvider (wraps MainWindow)
    
    In web mode:
        Returns WebContextProvider (wraps UserContext for the session)
        Session ID is obtained from:
        1. Thread-local storage (set by WebSocket server)
        2. Request params (if session_id is passed)
        3. Request meta (if session_id is in metadata)
    
    Args:
        request: The IPC request (optional, used to extract session_id in web mode)
        params: The request params (optional, used to extract session_id in web mode)
        
    Returns:
        ContextProvider instance
        
    Raises:
        RuntimeError: If in web mode and no session can be determined
    """
    mode = get_deployment_mode()
    
    if mode == "desktop":
        from gui.context.provider import DesktopContextProvider
        return DesktopContextProvider()
    
    # Web mode - need to find session_id
    session_id = _find_session_id(request, params)
    
    if not session_id:
        # This shouldn't happen in normal operation
        logger.error("[context_bridge] No session_id found in web mode")
        raise RuntimeError(
            "No session_id available. In web mode, requests must have a session context. "
            "Ensure the WebSocket server sets the session_id before invoking handlers."
        )
    
    from gui.context.provider import get_context_provider
    return get_context_provider(session_id)


def _find_session_id(
    request: Optional[Dict[str, Any]],
    params: Optional[Dict[str, Any]]
) -> Optional[str]:
    """
    Find session_id from various sources.
    
    Priority:
    1. Thread-local storage (set by transport layer)
    2. params.session_id
    3. request.meta.session_id
    """
    # 1. Thread-local (highest priority - set by transport)
    session_id = get_request_session_id()
    if session_id:
        return session_id
    
    # 2. From params
    if params and isinstance(params, dict):
        session_id = params.get('session_id')
        if session_id:
            return session_id
    
    # 3. From request meta
    if request and isinstance(request, dict):
        meta = request.get('meta', {})
        if isinstance(meta, dict):
            session_id = meta.get('session_id')
            if session_id:
                return session_id
    
    return None


# =============================================================================
# Convenience functions for common operations
# =============================================================================

def get_agents(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get agents from current context"""
    return get_handler_context(request, params).get_agents()


def get_agent_skills(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get agent skills from current context"""
    return get_handler_context(request, params).get_agent_skills()


def get_vehicles(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get vehicles from current context"""
    return get_handler_context(request, params).get_vehicles()


def get_config_manager(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get config manager from current context"""
    return get_handler_context(request, params).get_config_manager()


def get_auth_token(request: Optional[Dict] = None, params: Optional[Dict] = None) -> str:
    """Get auth token from current context"""
    return get_handler_context(request, params).get_auth_token()


def get_username(request: Optional[Dict] = None, params: Optional[Dict] = None) -> str:
    """Get username from current context"""
    return get_handler_context(request, params).get_username()


def get_ec_db_mgr(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get database manager from current context"""
    return get_handler_context(request, params).get_ec_db_mgr()


def get_db_chat_service(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get database chat service from current context"""
    return get_handler_context(request, params).get_db_chat_service()


def get_agent_tasks(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get agent tasks from current context"""
    return get_handler_context(request, params).get_agent_tasks()


def get_temp_dir(request: Optional[Dict] = None, params: Optional[Dict] = None) -> str:
    """Get temp directory from current context"""
    return get_handler_context(request, params).get_temp_dir()


def get_llm(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get LLM instance from current context"""
    return get_handler_context(request, params).get_llm()


def get_vehicle_service(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get vehicle service from current context"""
    return get_handler_context(request, params).get_vehicle_service()


def get_lightrag_server(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get LightRAG server from current context"""
    return get_handler_context(request, params).get_lightrag_server()


def get_mcp_tools_schemas(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """Get MCP tools schemas from current context"""
    return get_handler_context(request, params).get_mcp_tools_schemas()


# =============================================================================
# Legacy compatibility - get MainWindow in desktop mode
# =============================================================================

def get_main_window_compat(request: Optional[Dict] = None, params: Optional[Dict] = None):
    """
    Get MainWindow for legacy compatibility.
    
    In desktop mode: Returns the actual MainWindow
    In web mode: Returns None (handlers should use context provider instead)
    
    This is a transitional function. New code should use get_handler_context().
    """
    mode = get_deployment_mode()
    
    if mode == "desktop":
        from app_context import AppContext
        return AppContext.get_main_window()
    else:
        # In web mode, MainWindow doesn't exist
        # Handlers should be updated to use context provider
        logger.warning(
            "[context_bridge] get_main_window_compat called in web mode. "
            "This handler should be updated to use get_handler_context()."
        )
        return None
