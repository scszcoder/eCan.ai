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

    def test_public_catalog_selects_is_public_field(self):
        """GraphQL returns ONLY selected fields — without selecting isPublic
        the catalog rows carry a null `public` and no alias to normalize
        from, so the store filter drops every row (2026-08-25 incident)."""
        q = gen_get_agent_skills_string(public_catalog=True)
        assert "isPublic" in q.split("{", 2)[2]  # in the selection set

    def test_own_skills_query_does_not_select_is_public(self):
        """The own-skills selection must stay AWS-compatible (no isPublic
        field on the AWS AgentSkill type)."""
        q = gen_get_agent_skills_string()
        assert "isPublic" not in q


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


class TestPublicFlagNormalization:
    """Customer incident 2026-08-25: the catalog returned 4 rows but the
    deployed SDL populated `isPublic` while `public` resolved null — the
    strict `public` filter dropped every row → empty store tab."""

    def _run_handler(self, rows):
        captured = {}
        with patch.object(sh, "resolve_username", return_value=CUSTOMER), \
             patch.object(sh, "_fetch_cloud_skills", return_value=rows), \
             patch.object(sh, "create_success_response",
                          side_effect=lambda req, data: captured.update(data) or captured):
            sh.handle_get_public_skills(MagicMock(), {"username": CUSTOMER})
        return captured.get("skills", [])

    def test_is_public_only_rows_pass_filter_and_normalize(self):
        rows = [{"id": "skill_71209937ed7449bf", "name": "飞鸽客服前台00",
                 "owner": AUTHOR, "public": None, "isPublic": True}]
        skills = self._run_handler(rows)
        assert len(skills) == 1
        assert skills[0]["public"] is True  # normalized for the frontend

    def test_snake_case_flag_accepted(self):
        rows = [{"id": "s1", "name": "n", "owner": AUTHOR, "is_public": True}]
        assert len(self._run_handler(rows)) == 1

    def test_non_public_rows_still_filtered(self):
        rows = [{"id": "s2", "name": "n", "owner": AUTHOR,
                 "public": None, "isPublic": False}]
        assert self._run_handler(rows) == []

    def test_own_skills_still_excluded(self):
        rows = [{"id": "s3", "name": "n", "owner": CUSTOMER, "isPublic": True}]
        assert self._run_handler(rows) == []


class TestUnsubscribeRemovesLocalRow:
    """v0.9.95l incident: unsubscribe showed success but 已订阅 came back
    after relogin — the local third-party row (the very thing
    get_subscribed_skill_ids derives 已订阅 from) was never deleted, and
    the rel soft-delete crashed on a bogus ECDBManager import."""

    def _unsubscribe(self, row_owner):
        service = MagicMock()
        service.get_skill_by_id.return_value = {
            "success": True,
            "data": {"id": "skill_x", "askid": "0", "name": "n", "owner": row_owner},
        }
        service.delete_skill.return_value = {"success": True}
        with patch.object(sh, "resolve_username", return_value=CUSTOMER), \
             patch.object(sh, "_get_skill_service", return_value=service), \
             patch.object(sh, "_soft_delete_agent_skill_rel", return_value={"success": True}), \
             patch.object(sh, "_remove_skill_from_memory"), \
             patch.object(sh, "_sync_skill_subscription_to_cloud", return_value=None), \
             patch.object(sh, "_SKILL_FILE_SYNC_AVAILABLE", False), \
             patch.object(sh, "create_success_response",
                          side_effect=lambda req, data: {"ok": True, **data}), \
             patch.object(sh, "create_error_response",
                          side_effect=lambda req, code, msg: {"error": code, "message": msg}):
            resp = sh.handle_unsubscribe_from_skill(MagicMock(), {"skillId": "skill_x",
                                                                 "username": CUSTOMER})
        return resp, service

    def test_third_party_row_deleted(self):
        resp, service = self._unsubscribe(row_owner=AUTHOR)
        assert resp.get("ok")
        service.delete_skill.assert_called_once_with("skill_x")

    def test_own_skill_rejected_and_not_deleted(self):
        resp, service = self._unsubscribe(row_owner=CUSTOMER)
        assert resp.get("error") == "UNSUBSCRIBE_OWN_SKILL"
        service.delete_skill.assert_not_called()

    def test_bogus_ecdbmanager_import_removed(self):
        import inspect
        src = inspect.getsource(sh._soft_delete_agent_skill_rel)
        assert "ECDBManager" not in src  # crashed every soft-delete on 95l

    def test_bogus_database_manager_import_removed(self):
        """v0.9.95m: _sync_cloud_tool_knowledge_rels imported the nonexistent
        agent.db.database_manager — dormant until the TCB subscribeToSkill
        mutation deployed, then it errored EVERY first subscribe (after the
        local row was already saved). The subscribe call site is also
        wrapped so rel-sync failures stay non-fatal."""
        import inspect
        src = inspect.getsource(sh._sync_cloud_tool_knowledge_rels)
        assert "database_manager" not in src and "DatabaseManager" not in src
        handler_src = inspect.getsource(sh.handle_subscribe_to_skill)
        idx = handler_src.find("_sync_cloud_tool_knowledge_rels(")
        assert idx != -1
        assert "try:" in handler_src[max(0, idx - 300):idx]  # wrapped non-fatal


class TestPaidSubscriptionGate:
    """Paid-skill subscribe gate: free = instant; paid rejects only when the
    fund is KNOWN and insufficient (unknown fund must not block — billing is
    enforced server-side and blocking on missing client data breaks flows)."""

    def _gate(self, target, fund):
        with patch.object(sh, "_account_fund", return_value=fund):
            return sh._check_paid_subscription(target)

    def test_free_skill_never_gated(self):
        assert self._gate({"price": 0}, fund=0) is None
        assert self._gate({"price": None}, fund=None) is None

    def test_paid_with_sufficient_fund_passes(self):
        assert self._gate({"price": 10}, fund=50.0) is None

    def test_paid_with_insufficient_fund_rejected(self):
        msg = self._gate({"price": 10}, fund=3.0)
        assert msg and "Insufficient funds" in msg and "¥10" in msg

    def test_paid_with_unknown_fund_passes(self):
        assert self._gate({"price": 10}, fund=None) is None


class TestAccountFundParsing:
    def _fund(self, info):
        ctx = MagicMock()
        ctx.main_window._account_info = info
        with patch.object(sh, "get_handler_context", return_value=ctx):
            return sh._account_fund()

    def test_flat_dict(self):
        assert self._fund({"fund": 25}) == 25.0

    def test_nested_accounts_list(self):
        assert self._fund({"accounts": [{"id": "a1", "fund": "12.5"}]}) == 12.5

    def test_unknown_shapes_return_none(self):
        assert self._fund(None) is None
        assert self._fund({"data": "oops"}) is None
