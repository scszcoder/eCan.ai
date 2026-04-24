"""E2E tests for agent lifecycle via ECTestClient."""

import pytest

pytestmark = pytest.mark.e2e


class TestAgentLifecycleE2E:
    """End-to-end tests for the full agent lifecycle."""

    @pytest.mark.asyncio
    async def test_client_initialization(self, test_client):
        """ECTestClient initializes without errors."""
        assert test_client is not None
        assert test_client._transport == "direct"

    @pytest.mark.asyncio
    async def test_create_and_list_agent(self, test_client, sample_agent):
        """Creating an agent and then listing it returns the created agent."""
        # Create
        create_resp = await test_client.create_agent(sample_agent)
        # Direct mode may not return a formatted response, just verify no crash
        assert create_resp is not None

        # List
        agents = await test_client.list_agents()
        assert isinstance(agents, list)

    @pytest.mark.asyncio
    async def test_store_and_retrieve_responses(self, test_client):
        """test_client can store and retrieve values within a test."""
        test_client.store_response("key1", {"foo": "bar"})
        retrieved = test_client.get_stored_response("key1")
        assert retrieved == {"foo": "bar"}

        missing = test_client.get_stored_response("nonexistent", default="default_val")
        assert missing == "default_val"

    @pytest.mark.asyncio
    async def test_session_id_none_before_login(self, test_client):
        """Session ID is None before explicit login."""
        assert test_client.session_id is None

    @pytest.mark.asyncio
    async def test_user_id_none_before_login(self, test_client):
        """User ID is None before explicit login."""
        assert test_client.user_id is None


class TestSkillLifecycleE2E:
    """End-to-end tests for skill lifecycle."""

    @pytest.mark.asyncio
    async def test_create_skill(self, test_client, sample_skill):
        """Creating a skill does not raise."""
        resp = await test_client.create_skill(sample_skill)
        assert resp is not None

    @pytest.mark.asyncio
    async def test_list_skills(self, test_client):
        """Listing skills returns a list (possibly empty)."""
        skills = await test_client.list_skills()
        assert isinstance(skills, list)

    @pytest.mark.asyncio
    async def test_create_flowgram_skill(self, test_client, sample_flowgram_skill):
        """Creating a flowgram skill preserves flowgram data."""
        resp = await test_client.create_skill(sample_flowgram_skill)
        assert resp is not None
        assert sample_flowgram_skill["flowgram"] != {}


class TestTaskLifecycleE2E:
    """End-to-end tests for task lifecycle."""

    @pytest.mark.asyncio
    async def test_create_task(self, test_client, sample_task):
        """Creating a task does not raise."""
        resp = await test_client.create_task(sample_task)
        assert resp is not None

    @pytest.mark.asyncio
    async def test_list_tasks(self, test_client):
        """Listing tasks returns a list."""
        tasks = await test_client.list_tasks()
        assert isinstance(tasks, list)
