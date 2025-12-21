"""
Tests for Context Bridge (Phase 3)

These tests verify:
1. Context bridge correctly routes to desktop/web providers
2. Session ID extraction from various sources
3. Thread-local session context works correctly
4. Legacy compatibility functions work

Run tests:
    pytest gui/ipc/tests/test_context_bridge.py -v
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class TestContextBridge:
    """Test context bridge functionality"""
    
    def test_import_context_bridge(self):
        """Test context bridge can be imported"""
        from gui.ipc.context_bridge import (
            get_handler_context,
            get_deployment_mode,
            set_request_session_id,
            get_request_session_id,
            clear_request_session_id,
        )
        
        assert get_handler_context is not None
        assert get_deployment_mode is not None
    
    def test_desktop_mode_returns_desktop_provider(self, monkeypatch):
        """Test that desktop mode returns DesktopContextProvider"""
        monkeypatch.setenv("ECAN_MODE", "desktop")
        
        from gui.ipc.context_bridge import get_handler_context
        from gui.context.provider import DesktopContextProvider
        
        ctx = get_handler_context()
        assert isinstance(ctx, DesktopContextProvider)
    
    def test_web_mode_with_session(self, monkeypatch):
        """Test that web mode with session returns WebContextProvider"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_handler_context, set_request_session_id, clear_request_session_id
        from gui.context.provider import WebContextProvider
        from gui.context.session_manager import SessionManager
        
        # Create a session
        manager = SessionManager.get_instance()
        manager.reset()
        session_id = manager.create_session(user_id="test_user")
        
        try:
            # Set session in thread-local
            set_request_session_id(session_id)
            
            ctx = get_handler_context()
            assert isinstance(ctx, WebContextProvider)
        finally:
            clear_request_session_id()
            manager.reset()
    
    def test_web_mode_without_session_raises(self, monkeypatch):
        """Test that web mode without session raises error"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_handler_context, clear_request_session_id
        from gui.context.session_manager import SessionManager
        
        # Ensure no session
        clear_request_session_id()
        SessionManager.get_instance().reset()
        
        with pytest.raises(RuntimeError, match="No session_id available"):
            get_handler_context()


class TestSessionIdExtraction:
    """Test session ID extraction from various sources"""
    
    def test_session_from_thread_local(self, monkeypatch):
        """Test session ID from thread-local storage"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import (
            set_request_session_id,
            get_request_session_id,
            clear_request_session_id,
        )
        
        try:
            set_request_session_id("session_123")
            assert get_request_session_id() == "session_123"
        finally:
            clear_request_session_id()
            assert get_request_session_id() is None
    
    def test_session_from_params(self, monkeypatch):
        """Test session ID extraction from params"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_handler_context
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        manager.reset()
        session_id = manager.create_session(user_id="params_user")
        
        try:
            # Pass session_id in params
            ctx = get_handler_context(
                request={},
                params={"session_id": session_id}
            )
            assert ctx.get_user_id() == "params_user"
        finally:
            manager.reset()
    
    def test_session_from_request_meta(self, monkeypatch):
        """Test session ID extraction from request meta"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_handler_context
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        manager.reset()
        session_id = manager.create_session(user_id="meta_user")
        
        try:
            # Pass session_id in request meta
            ctx = get_handler_context(
                request={"meta": {"session_id": session_id}},
                params={}
            )
            assert ctx.get_user_id() == "meta_user"
        finally:
            manager.reset()


class TestConvenienceFunctions:
    """Test convenience functions"""
    
    def test_get_agents_desktop(self, monkeypatch):
        """Test get_agents in desktop mode"""
        monkeypatch.setenv("ECAN_MODE", "desktop")
        
        from gui.ipc.context_bridge import get_agents
        
        # Should return empty list (no MainWindow in test)
        agents = get_agents()
        assert agents == []
    
    def test_get_auth_token_desktop(self, monkeypatch):
        """Test get_auth_token in desktop mode"""
        monkeypatch.setenv("ECAN_MODE", "desktop")
        
        from gui.ipc.context_bridge import get_auth_token
        
        # Should return empty string (no MainWindow in test)
        token = get_auth_token()
        assert token == ""
    
    def test_get_agents_web(self, monkeypatch):
        """Test get_agents in web mode with session"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_agents, set_request_session_id, clear_request_session_id
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        manager.reset()
        session_id = manager.create_session(user_id="web_user")
        
        # Add a mock agent to the context
        ctx = manager.get_context(session_id)
        
        class MockAgent:
            def __init__(self):
                self.card = type('Card', (), {'id': 'agent_1'})()
        
        ctx.agents = [MockAgent()]
        
        try:
            set_request_session_id(session_id)
            agents = get_agents()
            assert len(agents) == 1
        finally:
            clear_request_session_id()
            manager.reset()


class TestLegacyCompatibility:
    """Test legacy compatibility functions"""
    
    def test_get_main_window_compat_desktop(self, monkeypatch):
        """Test get_main_window_compat in desktop mode"""
        monkeypatch.setenv("ECAN_MODE", "desktop")
        
        from gui.ipc.context_bridge import get_main_window_compat
        
        # In test environment without Qt, returns None
        # But importantly, it doesn't crash
        result = get_main_window_compat()
        # Result is None because MainWindow isn't available in tests
        assert result is None
    
    def test_get_main_window_compat_web(self, monkeypatch):
        """Test get_main_window_compat in web mode returns None"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.ipc.context_bridge import get_main_window_compat
        
        # In web mode, should return None (MainWindow doesn't exist)
        result = get_main_window_compat()
        assert result is None


class TestThreadSafety:
    """Test thread-local session context"""
    
    def test_thread_local_isolation(self):
        """Test that session IDs are isolated between threads"""
        import threading
        import time
        
        from gui.ipc.context_bridge import (
            set_request_session_id,
            get_request_session_id,
            clear_request_session_id,
        )
        
        results = {}
        
        def thread_func(thread_id, session_id):
            set_request_session_id(session_id)
            time.sleep(0.01)  # Small delay to allow interleaving
            results[thread_id] = get_request_session_id()
            clear_request_session_id()
        
        # Create threads with different session IDs
        t1 = threading.Thread(target=thread_func, args=(1, "session_A"))
        t2 = threading.Thread(target=thread_func, args=(2, "session_B"))
        
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        
        # Each thread should see its own session ID
        assert results[1] == "session_A"
        assert results[2] == "session_B"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
