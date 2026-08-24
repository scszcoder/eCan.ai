"""Tests for the customer-side skill store fix (2026-08-24).

queryAgentSkills is OWNER-SCOPED, so the old get_public_skills (filtering
the caller's own list) could never show ANOTHER author's published skills —
customers saw an empty store, and subscribe_to_skill couldn't find the
target ("Skill not found in cloud"). The fix queries the real public
catalog (CN: queryAgentSkills input:{isPublic:true}; AWS fallback:
getPublicSkills) and teaches the subscribe lookup to search it.
"""

from unittest.mock import MagicMock, patch

import pytest

import gui.ipc.w2p_handlers.skill_handler as sh
from agent.cloud_api.cloud_api import gen_get_agent_skills_string


AUTHOR = "wechat_b603a407904569a4ea88f9ac"
CUSTOMER = "wechat_94ef25fd457d171c19a8158a"

FD_SKILL = {"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
            "owner": AUTHOR, "public": True, "rentable": True, "price": 0}
OWN_SKILL = {"id": "skill_own", "name": "mine", "owner": CUSTOMER, "public": False}


class TestQueryGeneration:
    def test_default_query_scopes_to_owner(self):
        q = gen_get_agent_skills_string()
        assert "queryAgentSkills(input: {})" in q

    def test_public_catalog_query_sets_is_public(self):
        q = gen_get_agent_skills_string(public_catalog=True)
        assert "queryAgentSkills(input: {isPublic: true})" in q


class TestFindCloudSkillForSubscribe:
    def test_found_in_own_list(self):
        with patch.object(sh, "_fetch_cloud_skills", return_value=[OWN_SKILL]) as fetch:
            target = sh._find_cloud_skill_for_subscribe(None, None, "skill_own")
        assert target is OWN_SKILL
        assert fetch.call_count == 1  # no catalog lookup needed

    def test_falls_back_to_public_catalog(self):
        """The customer incident: another author's store skill is only
        findable in the public catalog."""
        def fetch(request, params, public_catalog=False):
            return [FD_SKILL] if public_catalog else [OWN_SKILL]

        with patch.object(sh, "_fetch_cloud_skills", side_effect=fetch):
            target = sh._find_cloud_skill_for_subscribe(None, None, "skill_71209937ed7449bf")
        assert target is FD_SKILL

    def test_not_found_anywhere(self):
        with patch.object(sh, "_fetch_cloud_skills", return_value=[]):
            assert sh._find_cloud_skill_for_subscribe(None, None, "nope") is None

    def test_catalog_error_returns_none_not_raise(self):
        def fetch(request, params, public_catalog=False):
            if public_catalog:
                raise RuntimeError("validation failed")
            return []

        with patch.object(sh, "_fetch_cloud_skills", side_effect=fetch):
            assert sh._find_cloud_skill_for_subscribe(None, None, "x") is None
