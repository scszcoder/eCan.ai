"""
Tests for Session Management (Phase 2)

These tests verify:
1. UserContext creation and state management
2. SessionManager session lifecycle
3. ContextProvider abstraction
4. Desktop mode still works

Run tests:
    pytest gui/context/tests/test_session_management.py -v
"""

import pytest
import sys
import os
import asyncio
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


class TestUserContext:
    """Test UserContext class"""
    
    def test_create_user_context(self):
        """Test basic UserContext creation"""
        from gui.context.user_context import UserContext
        
        ctx = UserContext(user_id="test_user_123")
        
        assert ctx.user_id == "test_user_123"
        assert ctx.session_id is not None
        assert len(ctx.session_id) == 36  # UUID format
        assert ctx.agents == []
        assert ctx.agent_skills == []
        assert ctx.is_dirty == False
    
    def test_user_context_with_data(self):
        """Test UserContext with initial data"""
        from gui.context.user_context import UserContext
        
        ctx = UserContext(
            user_id="user_456",
            username="testuser",
            auth_token="test_token_abc",
        )
        
        assert ctx.username == "testuser"
        assert ctx.get_auth_token() == "test_token_abc"
    
    def test_user_context_activity_tracking(self):
        """Test activity timestamp updates"""
        from gui.context.user_context import UserContext
        import time
        
        ctx = UserContext(user_id="user_789")
        initial_activity = ctx.last_activity
        
        time.sleep(0.01)  # Small delay
        ctx.update_activity()
        
        assert ctx.last_activity > initial_activity
    
    def test_user_context_dirty_tracking(self):
        """Test dirty flag for state changes"""
        from gui.context.user_context import UserContext
        
        ctx = UserContext(user_id="user_dirty")
        assert ctx.is_dirty == False
        
        ctx.set_auth_token("new_token")
        assert ctx.is_dirty == True
    
    def test_user_context_agent_management(self):
        """Test agent add/remove operations"""
        from gui.context.user_context import UserContext
        
        # Create a mock agent
        class MockAgent:
            def __init__(self, agent_id):
                self.card = type('Card', (), {'id': agent_id})()
                self.tasks = []
        
        ctx = UserContext(user_id="user_agents")
        
        # Add agent
        agent1 = MockAgent("agent_001")
        ctx.add_agent(agent1)
        assert len(ctx.agents) == 1
        assert ctx.is_dirty == True
        
        # Find agent
        found = ctx.get_agent_by_id("agent_001")
        assert found is agent1
        
        # Remove agent
        ctx.is_dirty = False
        removed = ctx.remove_agent("agent_001")
        assert removed == True
        assert len(ctx.agents) == 0
        assert ctx.is_dirty == True
    
    def test_user_context_serialization(self):
        """Test to_dict serialization"""
        from gui.context.user_context import UserContext
        
        ctx = UserContext(
            user_id="user_serial",
            username="serialuser",
        )
        
        data = ctx.to_dict()
        
        assert data["user_id"] == "user_serial"
        assert data["username"] == "serialuser"
        assert "session_id" in data
        assert "created_at" in data
    
    def test_user_context_wan_status(self):
        """Test WAN connection status methods"""
        from gui.context.user_context import UserContext
        
        ctx = UserContext(user_id="user_wan")
        
        assert ctx.is_wan_connected == False
        assert ctx.is_wan_msg_subscribed == False
        
        ctx.set_wan_connected(True)
        assert ctx.is_wan_connected == True
        
        ctx.set_wan_msg_subscribed(True)
        assert ctx.is_wan_msg_subscribed == True


class TestSessionManager:
    """Test SessionManager class"""
    
    @pytest.fixture(autouse=True)
    def reset_session_manager(self):
        """Reset SessionManager before each test"""
        from gui.context.session_manager import SessionManager
        manager = SessionManager.get_instance()
        manager.reset()
        yield
        manager.reset()
    
    def test_session_manager_singleton(self):
        """Test SessionManager is a singleton"""
        from gui.context.session_manager import SessionManager
        
        m1 = SessionManager.get_instance()
        m2 = SessionManager.get_instance()
        
        assert m1 is m2
    
    def test_create_session(self):
        """Test session creation"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        session_id = manager.create_session(
            user_id="user_create",
            username="createuser",
            auth_token="token_123"
        )
        
        assert session_id is not None
        assert manager.has_session(session_id)
        assert manager.get_session_count() == 1
    
    def test_get_context(self):
        """Test getting context by session ID"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        session_id = manager.create_session(
            user_id="user_get",
            username="getuser"
        )
        
        context = manager.get_context(session_id)
        
        assert context is not None
        assert context.user_id == "user_get"
        assert context.username == "getuser"
    
    def test_get_context_by_user(self):
        """Test getting context by user ID"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        manager.create_session(user_id="user_byuser", username="byuser")
        
        context = manager.get_context_by_user("user_byuser")
        
        assert context is not None
        assert context.username == "byuser"
    
    def test_destroy_session(self):
        """Test session destruction"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        session_id = manager.create_session(user_id="user_destroy")
        assert manager.has_session(session_id)
        
        result = manager.destroy_session(session_id)
        
        assert result == True
        assert not manager.has_session(session_id)
        assert manager.get_session_count() == 0
    
    def test_connection_binding(self):
        """Test WebSocket connection binding"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        session_id = manager.create_session(user_id="user_conn")
        
        # Bind connection
        result = manager.bind_connection("conn_123", session_id)
        assert result == True
        
        # Get context by connection
        context = manager.get_context_by_connection("conn_123")
        assert context is not None
        assert context.user_id == "user_conn"
        
        # Unbind connection
        unbound_session = manager.unbind_connection("conn_123")
        assert unbound_session == session_id
        
        # Connection should no longer resolve
        context = manager.get_context_by_connection("conn_123")
        assert context is None
    
    def test_multiple_sessions(self):
        """Test multiple concurrent sessions"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        s1 = manager.create_session(user_id="user_1", username="user1")
        s2 = manager.create_session(user_id="user_2", username="user2")
        s3 = manager.create_session(user_id="user_3", username="user3")
        
        assert manager.get_session_count() == 3
        assert manager.get_user_count() == 3
        
        # Each session has correct context
        assert manager.get_context(s1).username == "user1"
        assert manager.get_context(s2).username == "user2"
        assert manager.get_context(s3).username == "user3"
    
    def test_session_callbacks(self):
        """Test session lifecycle callbacks"""
        from gui.context.session_manager import SessionManager
        
        manager = SessionManager.get_instance()
        
        created_sessions = []
        destroyed_sessions = []
        
        def on_created(session_id, context):
            created_sessions.append(session_id)
        
        def on_destroyed(session_id):
            destroyed_sessions.append(session_id)
        
        manager.set_callbacks(on_created=on_created, on_destroyed=on_destroyed)
        
        session_id = manager.create_session(user_id="user_cb")
        assert session_id in created_sessions
        
        manager.destroy_session(session_id)
        assert session_id in destroyed_sessions


class TestContextProvider:
    """Test ContextProvider abstraction"""
    
    def test_desktop_context_provider_import(self):
        """Test DesktopContextProvider can be imported"""
        from gui.context.provider import DesktopContextProvider
        
        provider = DesktopContextProvider()
        assert provider is not None
    
    def test_web_context_provider(self):
        """Test WebContextProvider with UserContext"""
        from gui.context.provider import WebContextProvider
        from gui.context.user_context import UserContext
        
        ctx = UserContext(
            user_id="web_user",
            username="webuser",
            auth_token="web_token"
        )
        
        provider = WebContextProvider(ctx)
        
        assert provider.get_user_id() == "web_user"
        assert provider.get_username() == "webuser"
        assert provider.get_auth_token() == "web_token"
        assert provider.get_agents() == []
    
    def test_web_context_provider_agents(self):
        """Test WebContextProvider agent access"""
        from gui.context.provider import WebContextProvider
        from gui.context.user_context import UserContext
        
        # Mock agent
        class MockAgent:
            def __init__(self, agent_id):
                self.card = type('Card', (), {'id': agent_id})()
                self.tasks = ["task1", "task2"]
        
        ctx = UserContext(user_id="agent_user")
        ctx.agents = [MockAgent("a1"), MockAgent("a2")]
        
        provider = WebContextProvider(ctx)
        
        assert len(provider.get_agents()) == 2
        assert provider.get_agent_by_id("a1") is not None
        assert provider.get_agent_by_id("nonexistent") is None
    
    def test_get_context_provider_desktop_mode(self, monkeypatch):
        """Test get_context_provider in desktop mode"""
        monkeypatch.setenv("ECAN_MODE", "desktop")
        
        from gui.context.provider import get_context_provider, DesktopContextProvider
        
        provider = get_context_provider()
        
        assert isinstance(provider, DesktopContextProvider)
    
    def test_get_context_provider_web_mode(self, monkeypatch):
        """Test get_context_provider in web mode"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.context.provider import get_context_provider, WebContextProvider
        from gui.context.session_manager import SessionManager
        
        # Create a session first
        manager = SessionManager.get_instance()
        manager.reset()
        session_id = manager.create_session(user_id="web_mode_user")
        
        try:
            provider = get_context_provider(session_id)
            assert isinstance(provider, WebContextProvider)
        finally:
            manager.reset()
    
    def test_get_context_provider_web_mode_no_session(self, monkeypatch):
        """Test get_context_provider fails without session in web mode"""
        monkeypatch.setenv("ECAN_MODE", "web")
        
        from gui.context.provider import get_context_provider
        from gui.context.session_manager import SessionManager
        
        SessionManager.get_instance().reset()
        
        with pytest.raises(ValueError, match="session_id is required"):
            get_context_provider()
    
    def test_deployment_mode_detection(self, monkeypatch):
        """Test deployment mode detection"""
        from gui.context.provider import get_deployment_mode
        
        monkeypatch.setenv("ECAN_MODE", "desktop")
        assert get_deployment_mode() == "desktop"
        
        monkeypatch.setenv("ECAN_MODE", "web")
        assert get_deployment_mode() == "web"
        
        monkeypatch.delenv("ECAN_MODE", raising=False)
        assert get_deployment_mode() == "desktop"  # Default


class TestDesktopModeCompatibility:
    """Verify desktop mode still works after Phase 2 changes"""
    
    def test_desktop_provider_without_mainwindow(self):
        """Test DesktopContextProvider handles missing MainWindow gracefully"""
        from gui.context.provider import DesktopContextProvider
        
        provider = DesktopContextProvider()
        
        # Should return empty lists, not crash
        assert provider.get_agents() == []
        assert provider.get_agent_skills() == []
        assert provider.get_vehicles() == []
        assert provider.get_auth_token() == ""
    
    def test_context_package_imports(self):
        """Test all context package imports work"""
        from gui.context import (
            UserContext,
            SessionManager,
            ContextProvider,
            DesktopContextProvider,
            WebContextProvider,
            get_context_provider,
        )
        
        assert UserContext is not None
        assert SessionManager is not None
        assert ContextProvider is not None
        assert DesktopContextProvider is not None
        assert WebContextProvider is not None
        assert get_context_provider is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
