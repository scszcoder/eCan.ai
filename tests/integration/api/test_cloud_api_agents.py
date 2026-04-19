"""Integration tests for Cloud API - Agent entity CRUD."""

import pytest

pytestmark = pytest.mark.integration


class TestCloudAgentAPI:
    """Integration tests for Agent API using CloudAPIMockServer."""

    def test_add_agent(self, cloud_mock):
        """Adding an agent stores it in mock storage."""
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="Test Agent Add")
        response = cloud_mock.mock_add_agents(session=None, agents=[agent])

        assert response["success"] is True
        assert response["count"] == 1
        storage = cloud_mock.get_storage()
        assert len(storage["agents"]) == 1
        assert storage["agents"][0]["name"] == "Test Agent Add"

    def test_get_agents_empty(self, cloud_mock):
        """Querying agents before adding any returns empty list."""
        response = cloud_mock.mock_get_agents(session=None, token="fake")
        assert response["data"]["agents"] == []

    def test_get_agents_after_add(self, cloud_mock):
        """Querying agents after adding returns stored agents."""
        from tests.framework.data_factory import AgentFactory

        agents = AgentFactory.create_batch(3)
        cloud_mock.mock_add_agents(session=None, agents=agents)

        response = cloud_mock.mock_get_agents(session=None, token="fake")
        assert len(response["data"]["agents"]) == 3

    def test_update_agent(self, cloud_mock):
        """Updating an agent modifies its fields."""
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="Original Name")
        cloud_mock.mock_add_agents(session=None, agents=[agent])

        agent["name"] = "Updated Name"
        response = cloud_mock.mock_update_agents(session=None, agents=[agent])

        assert response["success"] is True
        storage = cloud_mock.get_storage()
        assert storage["agents"][0]["name"] == "Updated Name"

    def test_remove_agent(self, cloud_mock):
        """Removing an agent deletes it from storage."""
        from tests.framework.data_factory import AgentFactory

        agent = AgentFactory.create(name="To Delete")
        cloud_mock.mock_add_agents(session=None, agents=[agent])

        response = cloud_mock.mock_remove_agents(session=None, agent_ids=[{"id": agent["id"]}])
        assert response["success"] is True

        storage = cloud_mock.get_storage()
        assert len(storage["agents"]) == 0

    def test_full_agent_crud_cycle(self, cloud_mock):
        """Full CRUD: create → read → update → delete."""
        from tests.framework.data_factory import AgentFactory

        # Create
        agent = AgentFactory.create(name="CRUD Test Agent")
        add_resp = cloud_mock.mock_add_agents(session=None, agents=[agent])
        assert add_resp["success"] is True

        # Read
        get_resp = cloud_mock.mock_get_agents(session=None, token="fake")
        assert len(get_resp["data"]["agents"]) == 1

        # Update
        agent["description"] = "Updated description"
        update_resp = cloud_mock.mock_update_agents(session=None, agents=[agent])
        assert update_resp["success"] is True

        # Verify update
        get_resp2 = cloud_mock.mock_get_agents(session=None, token="fake")
        assert get_resp2["data"]["agents"][0]["description"] == "Updated description"

        # Delete
        delete_resp = cloud_mock.mock_remove_agents(session=None, agent_ids=[{"id": agent["id"]}])
        assert delete_resp["success"] is True

        # Verify deletion
        get_resp3 = cloud_mock.mock_get_agents(session=None, token="fake")
        assert len(get_resp3["data"]["agents"]) == 0
