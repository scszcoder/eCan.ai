"""Integration tests for Cloud API - Skill entity CRUD."""

import pytest

pytestmark = pytest.mark.integration


class TestCloudSkillAPI:
    """Integration tests for Skill API using CloudAPIMockServer."""

    def test_add_skill(self, cloud_mock):
        """Adding a skill stores it in mock storage."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create(name="Test Skill Add")
        response = cloud_mock.mock_add_skills(session=None, skills=[skill])

        assert response["success"] is True
        assert response["count"] == 1
        storage = cloud_mock.get_storage()
        assert len(storage["skills"]) == 1

    def test_add_skill_with_flowgram(self, cloud_mock):
        """Adding a skill with flowgram data preserves flowgram content."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create_with_flowgram(name="Flowgram Skill")
        response = cloud_mock.mock_add_skills(session=None, skills=[skill])

        assert response["success"] is True
        storage = cloud_mock.get_storage()
        assert "flowgram" in storage["skills"][0]
        assert storage["skills"][0]["flowgram"] != {}

    def test_get_skills_empty(self, cloud_mock):
        """Querying skills before adding any returns empty list."""
        response = cloud_mock.mock_get_skills(session=None, token="fake")
        assert response["data"]["skills"] == []

    def test_get_skills_after_add(self, cloud_mock):
        """Querying skills after adding returns stored skills."""
        from tests.framework.data_factory import SkillFactory

        skills = SkillFactory.create_batch(5)
        cloud_mock.mock_add_skills(session=None, skills=skills)

        response = cloud_mock.mock_get_skills(session=None, token="fake")
        assert len(response["data"]["skills"]) == 5

    def test_update_skill(self, cloud_mock):
        """Updating a skill modifies its fields."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create(name="Original Skill Name", status="draft")
        cloud_mock.mock_add_skills(session=None, skills=[skill])

        skill["status"] = "published"
        response = cloud_mock.mock_update_skills(session=None, skills=[skill])

        assert response["success"] is True
        storage = cloud_mock.get_storage()
        assert storage["skills"][0]["status"] == "published"

    def test_remove_skill(self, cloud_mock):
        """Removing a skill deletes it from storage."""
        from tests.framework.data_factory import SkillFactory

        skill = SkillFactory.create(name="To Delete")
        cloud_mock.mock_add_skills(session=None, skills=[skill])
        assert len(cloud_mock.get_storage()["skills"]) == 1

        response = cloud_mock.mock_remove_skills(session=None, skill_ids=[{"id": skill["id"]}])
        assert response["success"] is True
        assert len(cloud_mock.get_storage()["skills"]) == 0

    def test_batch_add_skills(self, cloud_mock):
        """Batch adding multiple skills at once works correctly."""
        from tests.framework.data_factory import SkillFactory

        skills = [
            SkillFactory.create(name=f"Batch Skill {i}")
            for i in range(10)
        ]
        response = cloud_mock.mock_add_skills(session=None, skills=skills)

        assert response["success"] is True
        assert response["count"] == 10
        assert len(cloud_mock.get_storage()["skills"]) == 10

    def test_error_injection(self, cloud_mock):
        """Error injection causes the expected exception."""
        from tests.framework.data_factory import SkillFactory
        Ex = Exception

        cloud_mock.inject_error("skill_add", Ex("Injected error"))
        skill = SkillFactory.create()

        with pytest.raises(Ex, match="Injected error"):
            cloud_mock.mock_add_skills(session=None, skills=[skill])

    def test_account_info_mock(self, cloud_mock):
        """Account info mock returns valid structure."""
        response = cloud_mock.mock_account_info(session=None, acct_ops=[])

        assert "data" in response
        assert "account_info" in response["data"]
        acct = response["data"]["account_info"]
        assert "user_id" in acct
        assert "username" in acct
        assert "plan" in acct
