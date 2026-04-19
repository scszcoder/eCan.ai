"""Integration tests for Cloud API - Task entity CRUD."""

import pytest

pytestmark = pytest.mark.integration


class TestCloudTaskAPI:
    """Integration tests for Task API using CloudAPIMockServer."""

    def test_add_task(self, cloud_mock):
        """Adding a task stores it in mock storage."""
        from tests.framework.data_factory import TaskFactory

        task = TaskFactory.create(name="Test Task")
        response = cloud_mock.mock_add_tasks(session=None, tasks=[task])

        assert response["success"] is True
        assert response["count"] == 1
        assert len(cloud_mock.get_storage()["tasks"]) == 1

    def test_full_task_crud_cycle(self, cloud_mock):
        """Full CRUD cycle for tasks."""
        from tests.framework.data_factory import TaskFactory

        task = TaskFactory.create(name="CRUD Task", status="pending")
        cloud_mock.mock_add_tasks(session=None, tasks=[task])

        # Update
        task["status"] = "running"
        cloud_mock.mock_update_tasks(session=None, tasks=[task])

        # Verify
        resp = cloud_mock.mock_get_tasks(session=None, token="fake")
        assert resp["data"]["tasks"][0]["status"] == "running"

        # Delete
        cloud_mock.mock_remove_tasks(session=None, task_ids=[{"id": task["id"]}])
        resp2 = cloud_mock.mock_get_tasks(session=None, token="fake")
        assert len(resp2["data"]["tasks"]) == 0


class TestCloudToolAPI:
    """Integration tests for Tool API using CloudAPIMockServer."""

    def test_add_tool(self, cloud_mock):
        """Adding a tool stores it in mock storage."""
        from tests.framework.data_factory import ToolFactory

        tool = ToolFactory.create(name="Test Tool", tool_type="mcp")
        response = cloud_mock.mock_add_tools(session=None, tools=[tool])

        assert response["success"] is True
        assert len(cloud_mock.get_storage()["tools"]) == 1

    def test_tool_lifecycle(self, cloud_mock):
        """Tool CRUD lifecycle."""
        from tests.framework.data_factory import ToolFactory

        tool = ToolFactory.create(name="Lifecycle Tool")
        cloud_mock.mock_add_tools(session=None, tools=[tool])

        resp = cloud_mock.mock_get_tools(session=None, token="fake")
        assert len(resp["data"]["tools"]) == 1

        cloud_mock.mock_remove_tools(session=None, tool_ids=[{"id": tool["id"]}])
        resp2 = cloud_mock.mock_get_tools(session=None, token="fake")
        assert len(resp2["data"]["tools"]) == 0
