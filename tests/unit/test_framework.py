"""Unit tests for data factory and test client."""

import pytest

pytestmark = pytest.mark.unit


class TestDataFactories:
    """Tests for test data factory classes."""

    def test_agent_factory_creates_valid_agent(self):
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="Test Agent")
        assert agent["name"] == "Test Agent"
        assert "id" in agent
        assert agent["id"].startswith("test_agent_")
        assert agent["owner"] == "unittest@test.com"
        assert agent["status"] == "active"

    def test_agent_factory_overrides(self):
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="Override", status="paused", custom_field="value")
        assert agent["name"] == "Override"
        assert agent["status"] == "paused"
        assert agent["custom_field"] == "value"

    def test_agent_factory_batch(self):
        from tests.framework.data_factory import AgentFactory

        agents = AgentFactory.create_batch(5)
        assert len(agents) == 5
        names = [a["name"] for a in agents]
        assert names.count("Test Agent") == 5
        # IDs should be unique
        ids = [a["id"] for a in agents]
        assert len(ids) == len(set(ids))

    def test_skill_factory_creates_valid_skill(self):
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create(name="My Skill")
        assert skill["name"] == "My Skill"
        assert "id" in skill
        assert "askid" in skill
        assert skill["flowgram"] == {}
        assert skill["public"] is False

    def test_skill_factory_with_flowgram(self):
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create_with_flowgram(name="Flow Skill")
        assert skill["name"] == "Flow Skill"
        assert "flowgram" in skill
        wf = skill["flowgram"]["workFlow"]
        assert "nodes" in wf
        assert "edges" in wf
        # Should have start and end nodes
        node_types = [n["type"] for n in wf["nodes"]]
        assert "start" in node_types
        assert "end" in node_types

    def test_task_factory(self):
        from tests.framework.data_factory import TaskFactory

        task = TaskFactory.create(name="My Task", task_type="analysis")
        assert task["name"] == "My Task"
        assert task["task_type"] == "analysis"
        assert "id" in task

    def test_tool_factory(self):
        from tests.framework.data_factory import ToolFactory

        tool = ToolFactory.create(name="My Tool", tool_type="browser")
        assert tool["name"] == "My Tool"
        assert tool["tool_type"] == "browser"
        assert "id" in tool

    def test_knowledge_factory(self):
        from tests.framework.data_factory import KnowledgeFactory

        knowledge = KnowledgeFactory.create(name="My Knowledge")
        assert knowledge["name"] == "My Knowledge"
        assert "id" in knowledge
        assert knowledge["knowledge_type"] == "general"

    def test_organization_factory(self):
        from tests.framework.data_factory import OrganizationFactory

        org = OrganizationFactory.create(name="My Org")
        assert org["name"] == "My Org"
        assert "id" in org
        assert org["org_type"] == "test"

    def test_avatar_factory(self):
        from tests.framework.data_factory import AvatarFactory

        avatar = AvatarFactory.create(name="My Avatar")
        assert avatar["name"] == "My Avatar"
        assert avatar["resource_type"] == "image"
        assert "id" in avatar

    def test_prompt_factory(self):
        from tests.framework.data_factory import PromptFactory

        prompt = PromptFactory.create(name="My Prompt", content="Hello, world!")
        # name is nested inside the prompt dict (AWSJSON field)
        assert prompt["prompt"]["name"] == "My Prompt"
        assert prompt["prompt"]["content"] == "Hello, world!"
        assert prompt["prompt"]["category"] == "test"
        assert "id" in prompt

    def test_vehicle_factory(self):
        from tests.framework.data_factory import VehicleFactory

        vehicle = VehicleFactory.create(name="My Vehicle")
        assert vehicle["name"] == "My Vehicle"
        assert "id" in vehicle
        assert vehicle["vehicle_type"] == "general"


class TestECTestClientDirectMode:
    """Tests for ECTestClient in direct transport mode."""

    def test_client_init(self):
        from tests.framework.test_client import ECTestClient

        client = ECTestClient(transport="direct")
        assert client._transport == "direct"
        assert client.session_id is None
        assert client.user_id is None

    def test_client_invalid_transport(self):
        from tests.framework.test_client import ECTestClient

        with pytest.raises(ValueError, match="Unknown transport"):
            ECTestClient(transport="invalid")

    def test_store_and_retrieve_responses(self):
        from tests.framework.test_client import ECTestClient

        client = ECTestClient(transport="direct")
        client.store_response("test_key", {"data": 123})
        assert client.get_stored_response("test_key") == {"data": 123}
        assert client.get_stored_response("missing", "default") == "default"

    def test_session_and_user_id_properties(self):
        from tests.framework.test_client import ECTestClient

        client = ECTestClient(transport="direct")
        assert client.session_id is None
        assert client.user_id is None

    def test_make_request_id_unique(self):
        from tests.framework.test_client import ECTestClient

        client = ECTestClient(transport="direct")
        ids = [client._make_request_id() for _ in range(100)]
        # All IDs should be unique
        assert len(ids) == len(set(ids))
        # All should start with "req_"
        assert all(i.startswith("req_") for i in ids)


class TestMockServer:
    """Tests for CloudAPIMockServer."""

    def test_mock_server_initial_storage(self):
        from tests.framework.mock_server import CloudAPIMockServer

        mock = CloudAPIMockServer()
        storage = mock.get_storage()
        assert isinstance(storage, dict)
        assert "agents" in storage
        assert storage["agents"] == []

    def test_mock_server_clear_storage(self):
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import AgentFactory

        mock = CloudAPIMockServer()
        agents = AgentFactory.create_batch(5)
        mock.mock_add_agents(None, agents)

        assert len(mock.get_storage()["agents"]) == 5
        mock.clear_storage()
        assert len(mock.get_storage()["agents"]) == 0

    def test_mock_server_error_injection(self):
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import AgentFactory

        class CustomError(Exception):
            pass

        mock = CloudAPIMockServer()
        mock.inject_error("agent_add", CustomError("boom"))

        with pytest.raises(CustomError, match="boom"):
            mock.mock_add_agents(None, [AgentFactory.create()])

    def test_mock_server_agent_operations(self):
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import AgentFactory

        mock = CloudAPIMockServer()
        agent = AgentFactory.create(name="Test Agent")

        # Add
        resp = mock.mock_add_agents(None, [agent])
        assert resp["success"] is True
        assert resp["count"] == 1

        # Get
        resp = mock.mock_get_agents(None, "token")
        assert len(resp["data"]["agents"]) == 1

        # Update
        agent["name"] = "Updated Name"
        resp = mock.mock_update_agents(None, [agent])
        assert resp["success"] is True
        assert mock.get_storage()["agents"][0]["name"] == "Updated Name"

        # Remove
        resp = mock.mock_remove_agents(None, [{"id": agent["id"]}])
        assert resp["success"] is True
        assert len(mock.get_storage()["agents"]) == 0

    def test_mock_server_skill_operations(self):
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import SkillFactory

        mock = CloudAPIMockServer()
        skill = SkillFactory.create(name="Test Skill")

        mock.mock_add_skills(None, [skill])
        resp = mock.mock_get_skills(None, "token")
        assert len(resp["data"]["skills"]) == 1

        mock.mock_remove_skills(None, [{"id": skill["id"]}])
        resp = mock.mock_get_skills(None, "token")
        assert len(resp["data"]["skills"]) == 0

    def test_mock_server_task_operations(self):
        from tests.framework.mock_server import CloudAPIMockServer
        from tests.framework.data_factory import TaskFactory

        mock = CloudAPIMockServer()
        tasks = TaskFactory.create_batch(3)
        mock.mock_add_tasks(None, tasks)

        resp = mock.mock_get_tasks(None, "token")
        assert len(resp["data"]["tasks"]) == 3

        for task in tasks:
            mock.mock_remove_tasks(None, [{"id": task["id"]}])

        resp = mock.mock_get_tasks(None, "token")
        assert len(resp["data"]["tasks"]) == 0

    def test_mock_server_account_info(self):
        from tests.framework.mock_server import CloudAPIMockServer

        mock = CloudAPIMockServer()
        resp = mock.mock_account_info(None, [])

        assert "data" in resp
        assert "account_info" in resp["data"]
        assert resp["data"]["account_info"]["username"] == "unittest@test.com"
