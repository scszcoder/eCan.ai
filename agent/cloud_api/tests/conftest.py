"""
Pytest Configuration and Fixtures for Cloud API Tests

Provides common fixtures for testing cloud API functions.
"""

import pytest
import requests
import uuid
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock


@pytest.fixture
def mock_session():
    """Create a mock requests session"""
    session = Mock(spec=requests.Session)
    return session


@pytest.fixture
def mock_token():
    """Create a mock authentication token"""
    return "mock_auth_token_for_testing_12345"


@pytest.fixture
def mock_endpoint():
    """Create a mock AppSync endpoint"""
    return "https://mock-appsync-endpoint.amazonaws.com/graphql"


@pytest.fixture
def sample_agent():
    """Create a sample agent data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "agid": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Agent",
        "title": "Test Title",
        "org_id": "org_123",
        "status": "active",
        "description": "A test agent for unit testing",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_skill():
    """Create a sample skill data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "askid": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Skill",
        "description": "A test skill for unit testing",
        "version": "1.0.0",
        "level": "intermediate",
        "status": "active",
        "public": False,
        "rentable": False,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_task():
    """Create a sample task data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "ataskid": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Task",
        "description": "A test task for unit testing",
        "org_id": "org_123",
        "status": "pending",
        "priority": "medium",
        "task_type": "automation",
        "progress": 0.0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_tool():
    """Create a sample tool data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "toolid": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Tool",
        "description": "A test tool for unit testing",
        "protocol": "mcp",
        "status": "active",
        "price": 0.0,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    }


@pytest.fixture
def sample_knowledge():
    """Create a sample knowledge data for testing"""
    return {
        "knId": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Knowledge",
        "description": "A test knowledge base for unit testing",
        "path": "/path/to/knowledge",
        "status": "active",
        "rag": "lightrag",
        "metadata": "{}",
    }


@pytest.fixture
def sample_avatar_resource():
    """Create a sample avatar resource data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "resource_type": "image",
        "name": "Test Avatar",
        "description": "A test avatar resource",
        "image_path": "/path/to/image.png",
        "video_path": "",
        "image_hash": "abc123",
        "video_hash": "",
        "cloud_image_url": "",
        "cloud_video_url": "",
        "cloud_synced": False,
        "avatar_metadata": {},
        "usage_count": 0,
        "is_public": False,
    }


@pytest.fixture
def sample_vehicle():
    """Create a sample vehicle data for testing"""
    return {
        "vid": 1,
        "vname": "TestMachine:win",
        "owner": "test_user@example.com",
        "status": "online",
        "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "functions": "buyer,seller",
        "agent_ids": "agent_1,agent_2",
        "hardware": "Intel Core i7",
        "software": "Windows 11",
        "ip": "192.168.1.100",
        "created_at": "",
    }


@pytest.fixture
def sample_organization():
    """Create a sample organization data for testing"""
    return {
        "id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "name": "Test Organization",
        "description": "A test organization for unit testing",
    }


@pytest.fixture
def sample_agent_skill_relation():
    """Create a sample agent-skill relation for testing"""
    return {
        "agid": str(uuid.uuid4()),
        "skid": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "status": "active",
        "proficiency": 80,
    }


@pytest.fixture
def sample_agent_task_relation():
    """Create a sample agent-task relation for testing"""
    return {
        "agid": str(uuid.uuid4()),
        "task_id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "status": "assigned",
    }


@pytest.fixture
def sample_agent_tool_relation():
    """Create a sample agent-tool relation for testing"""
    return {
        "agid": str(uuid.uuid4()),
        "tool_id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "permission": "read_write",
    }


@pytest.fixture
def sample_skill_tool_relation():
    """Create a sample skill-tool relation for testing"""
    return {
        "skill_id": str(uuid.uuid4()),
        "tool_id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "usage_type": "required",
        "required": True,
    }


@pytest.fixture
def sample_skill_knowledge_relation():
    """Create a sample skill-knowledge relation for testing"""
    return {
        "skill_id": str(uuid.uuid4()),
        "knowledge_id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "dependency_type": "primary",
        "importance": 5,
    }


@pytest.fixture
def sample_task_skill_relation():
    """Create a sample task-skill relation for testing"""
    return {
        "task_id": str(uuid.uuid4()),
        "skill_id": str(uuid.uuid4()),
        "owner": "test_user@example.com",
        "required": True,
        "proficiency_required": 70,
    }


@pytest.fixture
def mock_appsync_success_response():
    """Create a mock successful AppSync response"""
    return {
        "data": {
            "addAgents": '{"success": true, "count": 1}'
        }
    }


@pytest.fixture
def mock_appsync_error_response():
    """Create a mock error AppSync response"""
    return {
        "errors": [
            {
                "errorType": "ValidationError",
                "message": "Invalid input data"
            }
        ]
    }


@pytest.fixture
def mock_main_window():
    """Create a mock MainWindow for testing"""
    mock_win = MagicMock()
    mock_win.get_auth_token.return_value = "mock_auth_token"
    mock_win.getWanApiEndpoint.return_value = "https://mock-endpoint.amazonaws.com/graphql"
    mock_win.session = Mock(spec=requests.Session)
    return mock_win
