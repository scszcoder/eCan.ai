"""
Context Management Package

Provides per-user context management for multi-user web deployment.
In desktop mode, a single context wraps MainWindow.
In web mode, each user session gets its own UserContext.

Usage:
    from gui.context import ContextProvider, get_context_provider
    
    # Get context for current request
    provider = get_context_provider(session_id)
    agents = provider.get_agents()
"""

from .user_context import UserContext
from .session_manager import SessionManager
from .provider import ContextProvider, DesktopContextProvider, WebContextProvider, get_context_provider

__all__ = [
    'UserContext',
    'SessionManager', 
    'ContextProvider',
    'DesktopContextProvider',
    'WebContextProvider',
    'get_context_provider',
]
