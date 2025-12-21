"""
SessionManager - Multi-User Session Management

Manages user sessions and their associated UserContext instances.
This is the central registry for all active user sessions in web deployment mode.

Features:
- Create/destroy sessions on login/logout
- Session timeout and cleanup
- Map WebSocket connections to sessions
- Thread-safe session access
"""

from __future__ import annotations
from typing import Dict, Optional, Set, Callable, Any
from datetime import datetime, timedelta
from threading import Lock
import asyncio

from .user_context import UserContext
from utils.logger_helper import logger_helper as logger


class SessionManager:
    """
    Manages user sessions for multi-user web deployment.
    
    This is a singleton that maintains all active user sessions.
    Each session has a unique session_id and an associated UserContext.
    
    Usage:
        manager = SessionManager.get_instance()
        
        # Create session on login
        session_id = manager.create_session(user_id, username, auth_token)
        
        # Get context for a session
        context = manager.get_context(session_id)
        
        # Destroy session on logout
        manager.destroy_session(session_id)
    """
    
    _instance: Optional['SessionManager'] = None
    _lock: Lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Session storage
        self._sessions: Dict[str, UserContext] = {}
        self._user_to_session: Dict[str, str] = {}  # user_id -> session_id (latest)
        self._connection_to_session: Dict[str, str] = {}  # connection_id -> session_id
        
        # Session configuration
        self._session_timeout: timedelta = timedelta(hours=24)
        self._cleanup_interval: int = 300  # seconds
        
        # Callbacks
        self._on_session_created: Optional[Callable[[str, UserContext], None]] = None
        self._on_session_destroyed: Optional[Callable[[str], None]] = None
        
        # Cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        
        logger.info("[SessionManager] Initialized")
    
    @classmethod
    def get_instance(cls) -> 'SessionManager':
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    # ==========================================================================
    # Session Lifecycle
    # ==========================================================================
    
    def create_session(
        self,
        user_id: str,
        username: str = "",
        auth_token: str = "",
        session_id: Optional[str] = None
    ) -> str:
        """
        Create a new session for a user.
        
        Args:
            user_id: Unique user identifier
            username: Display username
            auth_token: Authentication token
            session_id: Optional specific session ID (auto-generated if not provided)
            
        Returns:
            The session ID
        """
        # Create context
        context = UserContext(
            user_id=user_id,
            username=username,
            auth_token=auth_token,
        )
        
        if session_id:
            context.session_id = session_id
        
        session_id = context.session_id
        
        with self._lock:
            # Store session
            self._sessions[session_id] = context
            self._user_to_session[user_id] = session_id
        
        logger.info(f"[SessionManager] Created session {session_id} for user {user_id}")
        
        # Notify callback
        if self._on_session_created:
            try:
                self._on_session_created(session_id, context)
            except Exception as e:
                logger.error(f"[SessionManager] Error in session created callback: {e}")
        
        return session_id
    
    def destroy_session(self, session_id: str) -> bool:
        """
        Destroy a session and cleanup resources.
        
        Args:
            session_id: The session to destroy
            
        Returns:
            True if session was found and destroyed
        """
        with self._lock:
            context = self._sessions.pop(session_id, None)
            
            if context:
                # Remove from user mapping
                if self._user_to_session.get(context.user_id) == session_id:
                    del self._user_to_session[context.user_id]
                
                # Remove connection mappings
                connections_to_remove = [
                    conn_id for conn_id, sess_id in self._connection_to_session.items()
                    if sess_id == session_id
                ]
                for conn_id in connections_to_remove:
                    del self._connection_to_session[conn_id]
        
        if context:
            logger.info(f"[SessionManager] Destroyed session {session_id}")
            
            # Notify callback
            if self._on_session_destroyed:
                try:
                    self._on_session_destroyed(session_id)
                except Exception as e:
                    logger.error(f"[SessionManager] Error in session destroyed callback: {e}")
            
            return True
        
        return False
    
    # ==========================================================================
    # Session Access
    # ==========================================================================
    
    def get_context(self, session_id: str) -> Optional[UserContext]:
        """
        Get the UserContext for a session.
        
        Args:
            session_id: The session ID
            
        Returns:
            UserContext if found, None otherwise
        """
        context = self._sessions.get(session_id)
        if context:
            context.update_activity()
        return context
    
    def get_context_by_user(self, user_id: str) -> Optional[UserContext]:
        """
        Get the UserContext for a user (latest session).
        
        Args:
            user_id: The user ID
            
        Returns:
            UserContext if found, None otherwise
        """
        session_id = self._user_to_session.get(user_id)
        if session_id:
            return self.get_context(session_id)
        return None
    
    def get_context_by_connection(self, connection_id: str) -> Optional[UserContext]:
        """
        Get the UserContext for a WebSocket connection.
        
        Args:
            connection_id: The connection ID
            
        Returns:
            UserContext if found, None otherwise
        """
        session_id = self._connection_to_session.get(connection_id)
        if session_id:
            return self.get_context(session_id)
        return None
    
    def get_session_id_by_connection(self, connection_id: str) -> Optional[str]:
        """Get session ID for a connection"""
        return self._connection_to_session.get(connection_id)
    
    # ==========================================================================
    # Connection Management
    # ==========================================================================
    
    def bind_connection(self, connection_id: str, session_id: str) -> bool:
        """
        Bind a WebSocket connection to a session.
        
        Args:
            connection_id: The connection ID
            session_id: The session ID
            
        Returns:
            True if session exists and binding succeeded
        """
        if session_id not in self._sessions:
            logger.warning(f"[SessionManager] Cannot bind connection to unknown session: {session_id}")
            return False
        
        with self._lock:
            self._connection_to_session[connection_id] = session_id
        
        logger.debug(f"[SessionManager] Bound connection {connection_id} to session {session_id}")
        return True
    
    def unbind_connection(self, connection_id: str) -> Optional[str]:
        """
        Unbind a WebSocket connection.
        
        Args:
            connection_id: The connection ID
            
        Returns:
            The session ID that was unbound, or None
        """
        with self._lock:
            session_id = self._connection_to_session.pop(connection_id, None)
        
        if session_id:
            logger.debug(f"[SessionManager] Unbound connection {connection_id} from session {session_id}")
        
        return session_id
    
    # ==========================================================================
    # Session Queries
    # ==========================================================================
    
    def get_all_sessions(self) -> Dict[str, UserContext]:
        """Get all active sessions (copy)"""
        return dict(self._sessions)
    
    def get_session_count(self) -> int:
        """Get number of active sessions"""
        return len(self._sessions)
    
    def get_user_count(self) -> int:
        """Get number of unique users with sessions"""
        return len(self._user_to_session)
    
    def has_session(self, session_id: str) -> bool:
        """Check if a session exists"""
        return session_id in self._sessions
    
    def get_sessions_for_user(self, user_id: str) -> list[str]:
        """Get all session IDs for a user"""
        return [
            sid for sid, ctx in self._sessions.items()
            if ctx.user_id == user_id
        ]
    
    # ==========================================================================
    # Session Cleanup
    # ==========================================================================
    
    def cleanup_expired_sessions(self) -> int:
        """
        Remove sessions that have exceeded the timeout.
        
        Returns:
            Number of sessions cleaned up
        """
        now = datetime.now()
        expired = []
        
        with self._lock:
            for session_id, context in self._sessions.items():
                if now - context.last_activity > self._session_timeout:
                    expired.append(session_id)
        
        for session_id in expired:
            self.destroy_session(session_id)
        
        if expired:
            logger.info(f"[SessionManager] Cleaned up {len(expired)} expired sessions")
        
        return len(expired)
    
    async def start_cleanup_task(self) -> None:
        """Start the background cleanup task"""
        if self._cleanup_task is not None:
            return
        
        async def cleanup_loop():
            while True:
                await asyncio.sleep(self._cleanup_interval)
                try:
                    self.cleanup_expired_sessions()
                except Exception as e:
                    logger.error(f"[SessionManager] Cleanup error: {e}")
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("[SessionManager] Started cleanup task")
    
    def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
            logger.info("[SessionManager] Stopped cleanup task")
    
    # ==========================================================================
    # Configuration
    # ==========================================================================
    
    def set_session_timeout(self, timeout: timedelta) -> None:
        """Set the session timeout duration"""
        self._session_timeout = timeout
        logger.info(f"[SessionManager] Session timeout set to {timeout}")
    
    def set_cleanup_interval(self, interval_seconds: int) -> None:
        """Set the cleanup interval in seconds"""
        self._cleanup_interval = interval_seconds
        logger.info(f"[SessionManager] Cleanup interval set to {interval_seconds}s")
    
    def set_callbacks(
        self,
        on_created: Optional[Callable[[str, UserContext], None]] = None,
        on_destroyed: Optional[Callable[[str], None]] = None
    ) -> None:
        """Set session lifecycle callbacks"""
        self._on_session_created = on_created
        self._on_session_destroyed = on_destroyed
    
    # ==========================================================================
    # Reset (for testing)
    # ==========================================================================
    
    def reset(self) -> None:
        """Reset all sessions (for testing only)"""
        with self._lock:
            self._sessions.clear()
            self._user_to_session.clear()
            self._connection_to_session.clear()
        logger.info("[SessionManager] Reset all sessions")
