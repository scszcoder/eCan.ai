"""
Global pytest fixtures for the eCan.ai testing framework.

Provides shared fixtures:
  - app_context: AppContext initialized for testing
  - cloud_mock: CloudAPIMockServer instance per test
  - test_client: ECTestClient in direct mode
  - sample_agents, sample_skills: Pre-generated test data
"""

import os
import sys

import pytest

# Fix sys.path at module level, BEFORE pytest can reset sys.path[0].
# __file__ is eCan.ai/tests/framework/conftest.py
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_UTILS_DIR = os.path.join(_PROJECT_ROOT, "utils")

_new_path = [_UTILS_DIR, _PROJECT_ROOT]
_seen = {_UTILS_DIR, _PROJECT_ROOT}
for p in sys.path:
    if p not in _seen and p != "":
        _new_path.append(p)
        _seen.add(p)
sys.path[:] = _new_path


# ============================================================================
# AppContext Fixture
# ============================================================================

@pytest.fixture(scope="session")
def project_root() -> str:
    """Return the project root directory."""
    return _PROJECT_ROOT


@pytest.fixture(scope="session")
def app_context():
    """
    Initialize AppContext for the test session.

    Sets up a minimal app context without requiring the full Qt GUI.
    Returns (AppContext, logger).
    """
    try:
        from app_context import AppContext
        from utils.logger_helper import logger_helper as logger

        ctx = AppContext()
        ctx.set_logger(logger)
        return ctx
    except ImportError as e:
        pytest.skip(f"Cannot import app_context: {e}")


# ============================================================================
# Cloud API Mock Fixture
# ============================================================================

@pytest.fixture
def cloud_mock():
    """
    Per-test CloudAPIMockServer instance.

    Each test gets a fresh mock server with empty storage.
    """
    from tests.framework.mock_server import CloudAPIMockServer

    mock = CloudAPIMockServer()
    yield mock
    mock.clear_storage()


# ============================================================================
# Test Client Fixture
# ============================================================================

@pytest.fixture
async def test_client():
    """
    Per-test ECTestClient in direct mode.

    Usage:
        async def test_something(test_client):
            await test_client.initialize()
            ...
    """
    from tests.framework.test_client import ECTestClient

    client = ECTestClient(transport="direct")
    await client.initialize()
    yield client
    await client.shutdown()


# ============================================================================
# Data Factory Fixtures
# ============================================================================

@pytest.fixture
def sample_agent():
    """A single sample agent dict."""
    from tests.framework.data_factory import AgentFactory

    return AgentFactory.create(name="Sample Agent")


@pytest.fixture
def sample_skill():
    """A single sample skill dict."""
    from tests.framework.data_factory import SkillFactory

    return SkillFactory.create(name="Sample Skill")


@pytest.fixture
def sample_task():
    """A single sample task dict."""
    from tests.framework.data_factory import TaskFactory

    return TaskFactory.create(name="Sample Task")


@pytest.fixture
def sample_agents():
    """A list of 3 sample agent dicts."""
    from tests.framework.data_factory import AgentFactory

    return AgentFactory.create_batch(3)


@pytest.fixture
def sample_skills():
    """A list of 3 sample skill dicts."""
    from tests.framework.data_factory import SkillFactory

    return SkillFactory.create_batch(3)


@pytest.fixture
def sample_flowgram_skill():
    """A skill with a valid flowgram workflow."""
    from tests.framework.data_factory import SkillFactory

    return SkillFactory.create_with_flowgram(name="Flowgram Skill")


# ============================================================================
# Environment Fixtures
# ============================================================================

@pytest.fixture
def mock_env(monkeypatch):
    """Set test-friendly environment variables."""
    monkeypatch.setenv("ECAN_MODE", "test")
    monkeypatch.setenv("ECAN_LOG_LEVEL", "WARNING")
    return monkeypatch


@pytest.fixture
def temp_data_dir(tmp_path):
    """A temporary directory for test data files."""
    data_dir = tmp_path / "test_data"
    data_dir.mkdir()
    return data_dir
