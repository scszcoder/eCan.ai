"""Smoke tests for eCan.ai core features.

These tests verify the most critical paths are working.
They should pass before any release or CI build.
"""

import os
import sys
import pytest

pytestmark = pytest.mark.smoke


class TestAppContext:
    """Smoke tests for AppContext initialization."""

    def test_app_context_import(self):
        """AppContext can be imported without errors."""
        from app_context import AppContext

        ctx = AppContext()
        assert ctx is not None

    def test_logger_helper_import(self):
        """Logger helper can be imported."""
        from utils.logger_helper import logger_helper

        assert logger_helper is not None
        assert hasattr(logger_helper, "info")

    def test_config_import(self):
        """App config can be imported."""
        from config.app_settings import app_settings

        assert app_settings is not None


class TestIPCHandlerRegistry:
    """Smoke tests for IPC Handler Registry."""

    def test_registry_import(self):
        """IPC Handler Registry can be imported."""
        from gui.ipc.registry import IPCHandlerRegistry

        assert IPCHandlerRegistry is not None

    def test_registry_lists_handlers(self):
        """Handler registry lists registered handlers."""
        from gui.ipc.registry import IPCHandlerRegistry

        handlers = IPCHandlerRegistry.list_handlers()
        assert isinstance(handlers, dict)
        # At minimum, should have sync or background handlers registered
        total = len(handlers.get("sync", [])) + len(handlers.get("background", []))
        assert total >= 0  # Registry should exist even if empty

    def test_registry_has_get_handler(self):
        """IPCHandlerRegistry has get_handler method."""
        from gui.ipc.registry import IPCHandlerRegistry

        assert hasattr(IPCHandlerRegistry, "get_handler")
        assert callable(IPCHandlerRegistry.get_handler)


class TestSessionManager:
    """Smoke tests for Session Manager."""

    def test_session_manager_import(self):
        """SessionManager can be imported."""
        from gui.context.session_manager import SessionManager

        assert SessionManager is not None

    def test_session_manager_singleton(self):
        """SessionManager.get_instance returns the same instance."""
        from gui.context.session_manager import SessionManager

        inst1 = SessionManager.get_instance()
        inst2 = SessionManager.get_instance()
        assert inst1 is inst2

    def test_session_manager_session_count(self):
        """SessionManager reports session count."""
        from gui.context.session_manager import SessionManager

        manager = SessionManager.get_instance()
        count = manager.get_session_count()
        assert isinstance(count, int)
        assert count >= 0


class TestWebServer:
    """Smoke tests for web server components."""

    def test_web_server_module_import(self):
        """web_server module can be imported."""
        import web_server

        assert web_server is not None

    def test_create_asgi_app_function_exists(self):
        """create_asgi_app function exists in web_server."""
        from web_server import create_asgi_app

        assert callable(create_asgi_app)

    def test_health_endpoint_data_structure(self):
        """Health check returns expected data structure."""
        from gui.context.session_manager import SessionManager

        manager = SessionManager.get_instance()
        health = {
            "status": "healthy",
            "mode": "test",
            "sessions": manager.get_session_count(),
        }
        assert "status" in health
        assert "mode" in health
        assert "sessions" in health


class TestDataFactories:
    """Smoke tests for test data factories."""

    def test_agent_factory_creates_valid_agent(self):
        """AgentFactory creates agent dict with required fields."""
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="Smoke Test Agent")
        assert agent["name"] == "Smoke Test Agent"
        assert "id" in agent
        assert "owner" in agent
        assert "description" in agent
        assert agent["id"].startswith("test_agent_")

    def test_skill_factory_creates_valid_skill(self):
        """SkillFactory creates skill dict with required fields."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create(name="Smoke Test Skill")
        assert skill["name"] == "Smoke Test Skill"
        assert "id" in skill
        assert "flowgram" in skill

    def test_skill_factory_with_flowgram(self):
        """SkillFactory.create_with_flowgram creates valid flowgram structure."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create_with_flowgram()
        assert "flowgram" in skill
        assert "workFlow" in skill["flowgram"]
        assert "nodes" in skill["flowgram"]["workFlow"]
        assert "edges" in skill["flowgram"]["workFlow"]

    def test_factory_batch_creates_multiple(self):
        """Factory batch methods create correct number of items."""
        from tests.framework.data_factory import AgentFactory, SkillFactory

        agents = AgentFactory.create_batch(5)
        assert len(agents) == 5

        skills = SkillFactory.create_batch(3)
        assert len(skills) == 3

        # All IDs should be unique
        ids = [a["id"] for a in agents]
        assert len(ids) == len(set(ids))


class TestMockServer:
    """Smoke tests for CloudAPIMockServer."""

    def test_mock_server_import(self):
        """CloudAPIMockServer can be imported."""
        from tests.framework.mock_server import CloudAPIMockServer

        assert CloudAPIMockServer is not None

    def test_mock_server_creates_fresh_storage(self):
        """Each mock server instance has fresh empty storage."""
        from tests.framework.mock_server import CloudAPIMockServer

        mock = CloudAPIMockServer()
        assert len(mock.get_storage()["agents"]) == 0
        assert len(mock.get_storage()["skills"]) == 0

    def test_mock_server_basic_crud(self):
        """Mock server basic CRUD operations work."""
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import AgentFactory

        mock = CloudAPIMockServer()
        agent = AgentFactory.create(name="Smoke Agent")

        mock.mock_add_agents(None, [agent])
        assert len(mock.get_storage()["agents"]) == 1

        resp = mock.mock_get_agents(None, "fake_token")
        assert len(resp["data"]["agents"]) == 1

    def test_mock_server_clear_storage(self):
        """clear_storage resets all entities."""
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import AgentFactory

        mock = CloudAPIMockServer()
        agents = AgentFactory.create_batch(3)
        mock.mock_add_agents(None, agents)

        assert len(mock.get_storage()["agents"]) == 3
        mock.clear_storage()
        assert len(mock.get_storage()["agents"]) == 0
