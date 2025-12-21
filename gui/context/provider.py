"""
ContextProvider - Unified Interface for Context Access

Provides a unified interface for accessing user context, regardless of
whether we're in desktop mode (MainWindow) or web mode (UserContext).

This abstraction allows handlers to work with both modes without changes.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List, Any, Dict
import os

if TYPE_CHECKING:
    from .user_context import UserContext
    from gui.MainGUI import MainWindow

from utils.logger_helper import logger_helper as logger


# Deployment mode detection
def get_deployment_mode() -> str:
    """Get current deployment mode from environment"""
    return os.getenv("ECAN_MODE", "desktop")


class ContextProvider(ABC):
    """
    Abstract base class for context providers.
    
    This defines the interface that handlers use to access user data.
    Both DesktopContextProvider and WebContextProvider implement this.
    """
    
    @abstractmethod
    def get_agents(self) -> List[Any]:
        """Get list of user's agents"""
        pass
    
    @abstractmethod
    def get_agent_skills(self) -> List[Any]:
        """Get list of user's skills"""
        pass
    
    @abstractmethod
    def get_vehicles(self) -> List[Any]:
        """Get list of user's vehicles"""
        pass
    
    @abstractmethod
    def get_mcp_tools_schemas(self) -> List[Any]:
        """Get MCP tool schemas"""
        pass
    
    @abstractmethod
    def get_config_manager(self) -> Optional[Any]:
        """Get configuration manager"""
        pass
    
    @abstractmethod
    def get_auth_token(self) -> str:
        """Get current authentication token"""
        pass
    
    @abstractmethod
    def get_username(self) -> str:
        """Get current username"""
        pass
    
    @abstractmethod
    def get_user_id(self) -> str:
        """Get current user ID"""
        pass
    
    @abstractmethod
    def get_wan_chat_msg_queue(self) -> Any:
        """Get WAN chat message queue"""
        pass
    
    @abstractmethod
    def set_wan_connected(self, connected: bool) -> None:
        """Set WAN connection status"""
        pass
    
    @abstractmethod
    def set_wan_msg_subscribed(self, subscribed: bool) -> None:
        """Set WAN message subscription status"""
        pass
    
    @abstractmethod
    def get_ec_db_mgr(self) -> Optional[Any]:
        """Get database manager"""
        pass
    
    @abstractmethod
    def get_db_chat_service(self) -> Optional[Any]:
        """Get database chat service"""
        pass
    
    @abstractmethod
    def get_agent_tasks(self) -> List[Any]:
        """Get list of agent tasks"""
        pass
    
    @abstractmethod
    def get_temp_dir(self) -> str:
        """Get temporary directory path"""
        pass
    
    @abstractmethod
    def get_llm(self) -> Optional[Any]:
        """Get LLM instance"""
        pass
    
    @abstractmethod
    def get_vehicle_service(self) -> Optional[Any]:
        """Get vehicle service"""
        pass
    
    @abstractmethod
    def get_lightrag_server(self) -> Optional[Any]:
        """Get LightRAG server instance"""
        pass
    
    # ==========================================================================
    # Convenience methods (implemented in base class)
    # ==========================================================================
    
    def get_all_tasks(self) -> List[Any]:
        """Get all tasks from all agents"""
        all_tasks = []
        for agent in self.get_agents():
            if hasattr(agent, 'tasks'):
                all_tasks.extend(agent.tasks)
        return all_tasks
    
    def get_agent_by_id(self, agent_id: str) -> Optional[Any]:
        """Find agent by ID"""
        for agent in self.get_agents():
            if hasattr(agent, 'card') and hasattr(agent.card, 'id'):
                if agent.card.id == agent_id:
                    return agent
        return None


class DesktopContextProvider(ContextProvider):
    """
    Context provider for desktop mode.
    
    Wraps MainWindow to provide the ContextProvider interface.
    This is used when running as a desktop Qt application.
    """
    
    def __init__(self, main_window: Optional[MainWindow] = None):
        """
        Initialize desktop context provider.
        
        Args:
            main_window: MainWindow instance (if None, will get from AppContext)
        """
        self._main_window = main_window
    
    def _get_main_window(self) -> Optional[MainWindow]:
        """Get MainWindow, lazily loading from AppContext if needed"""
        if self._main_window is None:
            from app_context import AppContext
            self._main_window = AppContext.get_main_window()
        return self._main_window
    
    def get_agents(self) -> List[Any]:
        mw = self._get_main_window()
        return mw.agents if mw and hasattr(mw, 'agents') else []
    
    def get_agent_skills(self) -> List[Any]:
        mw = self._get_main_window()
        return mw.agent_skills if mw and hasattr(mw, 'agent_skills') else []
    
    def get_vehicles(self) -> List[Any]:
        mw = self._get_main_window()
        return mw.vehicles if mw and hasattr(mw, 'vehicles') else []
    
    def get_mcp_tools_schemas(self) -> List[Any]:
        mw = self._get_main_window()
        return mw.mcp_tools_schemas if mw and hasattr(mw, 'mcp_tools_schemas') else []
    
    def get_config_manager(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.config_manager if mw and hasattr(mw, 'config_manager') else None
    
    def get_auth_token(self) -> str:
        mw = self._get_main_window()
        if mw and hasattr(mw, 'get_auth_token'):
            return mw.get_auth_token() or ""
        return ""
    
    def get_username(self) -> str:
        mw = self._get_main_window()
        return mw.username if mw and hasattr(mw, 'username') else ""
    
    def get_user_id(self) -> str:
        # In desktop mode, username is the user ID
        return self.get_username()
    
    def get_wan_chat_msg_queue(self) -> Any:
        mw = self._get_main_window()
        return mw.wan_chat_msg_queue if mw and hasattr(mw, 'wan_chat_msg_queue') else None
    
    def set_wan_connected(self, connected: bool) -> None:
        mw = self._get_main_window()
        if mw and hasattr(mw, 'set_wan_connected'):
            mw.set_wan_connected(connected)
    
    def set_wan_msg_subscribed(self, subscribed: bool) -> None:
        mw = self._get_main_window()
        if mw and hasattr(mw, 'set_wan_msg_subscribed'):
            mw.set_wan_msg_subscribed(subscribed)
    
    def get_ec_db_mgr(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.ec_db_mgr if mw and hasattr(mw, 'ec_db_mgr') else None
    
    def get_db_chat_service(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.db_chat_service if mw and hasattr(mw, 'db_chat_service') else None
    
    def get_agent_tasks(self) -> List[Any]:
        mw = self._get_main_window()
        return mw.agent_tasks if mw and hasattr(mw, 'agent_tasks') else []
    
    def get_temp_dir(self) -> str:
        mw = self._get_main_window()
        return mw.temp_dir if mw and hasattr(mw, 'temp_dir') else ""
    
    def get_llm(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.llm if mw and hasattr(mw, 'llm') else None
    
    def get_vehicle_service(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.vehicle_service if mw and hasattr(mw, 'vehicle_service') else None
    
    def get_lightrag_server(self) -> Optional[Any]:
        mw = self._get_main_window()
        return mw.lightrag_server if mw and hasattr(mw, 'lightrag_server') else None
    
    # Desktop-specific: direct access to MainWindow for legacy code
    @property
    def main_window(self) -> Optional[MainWindow]:
        """Get the underlying MainWindow (for legacy compatibility)"""
        return self._get_main_window()


class WebContextProvider(ContextProvider):
    """
    Context provider for web mode.
    
    Wraps UserContext to provide the ContextProvider interface.
    This is used when running as a web server with multiple users.
    """
    
    def __init__(self, user_context: UserContext):
        """
        Initialize web context provider.
        
        Args:
            user_context: The UserContext for this session
        """
        self._context = user_context
    
    def get_agents(self) -> List[Any]:
        return self._context.agents
    
    def get_agent_skills(self) -> List[Any]:
        return self._context.agent_skills
    
    def get_vehicles(self) -> List[Any]:
        return self._context.vehicles
    
    def get_mcp_tools_schemas(self) -> List[Any]:
        return self._context.mcp_tools_schemas
    
    def get_config_manager(self) -> Optional[Any]:
        return self._context.config_manager
    
    def get_auth_token(self) -> str:
        return self._context.auth_token
    
    def get_username(self) -> str:
        return self._context.username
    
    def get_user_id(self) -> str:
        return self._context.user_id
    
    def get_wan_chat_msg_queue(self) -> Any:
        return self._context.wan_chat_msg_queue
    
    def set_wan_connected(self, connected: bool) -> None:
        self._context.set_wan_connected(connected)
    
    def set_wan_msg_subscribed(self, subscribed: bool) -> None:
        self._context.set_wan_msg_subscribed(subscribed)
    
    def get_ec_db_mgr(self) -> Optional[Any]:
        return self._context.ec_db_mgr
    
    def get_db_chat_service(self) -> Optional[Any]:
        return self._context.db_chat_service
    
    def get_agent_tasks(self) -> List[Any]:
        return self._context.agent_tasks
    
    def get_temp_dir(self) -> str:
        return self._context.temp_dir
    
    def get_llm(self) -> Optional[Any]:
        return self._context.llm
    
    def get_vehicle_service(self) -> Optional[Any]:
        return self._context.vehicle_service
    
    def get_lightrag_server(self) -> Optional[Any]:
        return self._context.lightrag_server
    
    # Web-specific: direct access to UserContext
    @property
    def user_context(self) -> UserContext:
        """Get the underlying UserContext"""
        return self._context


# =============================================================================
# Factory Function
# =============================================================================

def get_context_provider(session_id: Optional[str] = None) -> ContextProvider:
    """
    Get the appropriate context provider based on deployment mode.
    
    Args:
        session_id: Session ID (required in web mode, ignored in desktop mode)
        
    Returns:
        ContextProvider instance
        
    Raises:
        ValueError: If in web mode and session_id is not provided or invalid
    """
    mode = get_deployment_mode()
    
    if mode == "desktop":
        return DesktopContextProvider()
    else:
        # Web mode
        if not session_id:
            raise ValueError("session_id is required in web mode")
        
        from .session_manager import SessionManager
        manager = SessionManager.get_instance()
        context = manager.get_context(session_id)
        
        if not context:
            raise ValueError(f"No session found for session_id: {session_id}")
        
        return WebContextProvider(context)


def get_context_provider_for_connection(connection_id: str) -> Optional[ContextProvider]:
    """
    Get context provider for a WebSocket connection.
    
    Args:
        connection_id: The WebSocket connection ID
        
    Returns:
        ContextProvider if connection is bound to a session, None otherwise
    """
    mode = get_deployment_mode()
    
    if mode == "desktop":
        return DesktopContextProvider()
    else:
        from .session_manager import SessionManager
        manager = SessionManager.get_instance()
        context = manager.get_context_by_connection(connection_id)
        
        if context:
            return WebContextProvider(context)
        return None
