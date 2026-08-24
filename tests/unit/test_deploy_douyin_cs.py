"""Tests for the real 抖店客服 (douyin_cs) Fast Deploy recipe.

Covers the shared-skill deployment in cli/deploy/commands.py:
- visibility checks for the two published skills and their prompts
- N Q&A tasks 飞鸽客服应答00N + 1 front-desk task 飞鸽客服前台001, trigger
  "auto", referencing the shared skills (no clones)
- store_url propagated via settings.task_vars
- agents 客服小X (unique pool names) + 前台小张, Sales org, local vehicle
- error paths abort with clear messages
"""

from unittest.mock import MagicMock, patch

import pytest

from cli.deploy import commands as dc


QA_SKILL = dc._DDCS_QA_SKILL_ID
FD_SKILL = dc._DDCS_FD_SKILL_ID


def _make_ctx(*, missing_skill=None, org_rows=None):
    ctx = MagicMock()

    def get_skill_by_id(sid):
        if sid == missing_skill:
            return {"success": False, "data": None}
        return {"success": True, "data": {
            "id": sid, "name": "skill", "owner": "buyer@x",
            "config": {"skill_owner": "author@x"},
        }}

    ctx.db.skill_service.get_skill_by_id.side_effect = get_skill_by_id
    ctx.db.org_service.search_orgs.return_value = {
        "success": True,
        "data": org_rows if org_rows is not None else [{"id": "org_sales", "name": "Sales"}],
    }
    ctx.db.org_service.add_org.return_value = {"success": True, "id": "org_new"}

    task_counter = {"n": 0}

    def add_task(data):
        task_counter["n"] += 1
        return {"success": True, "id": f"task_{task_counter['n']}", "data": None}

    ctx.db.task_service.add_task.side_effect = add_task
    ctx.db.task_service.add_skill_to_task.return_value = {"success": True}

    agent_counter = {"n": 0}

    def create_agent(data, owner):
        agent_counter["n"] += 1
        return {"success": True, "id": f"agent_{agent_counter['n']}"}

    ctx.db.agent_service.create_agent_from_data.side_effect = create_agent
    return ctx


@pytest.fixture(autouse=True)
def _patch_environment():
    with patch.object(dc, "_missing_system_prompts", return_value=[]), \
         patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
               return_value="veh-local"):
        yield


class TestDeployDouyinCs:
    CFG = {"store_urls": ["https://shopA.example.com"], "qa_agents": 3}

    def test_creates_tasks_agents_referencing_shared_skills(self):
        ctx = _make_ctx()
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        # 3 QA tasks + 1 FD task; NO skills created
        assert plan == {"agents": 4, "skills": 0, "tasks": 4}
        assert created["skills"] == []

        task_names = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert task_names == ["飞鸽客服应答001", "飞鸽客服应答002", "飞鸽客服应答003", "飞鸽客服前台001"]
        for c in ctx.db.task_service.add_task.call_args_list:
            assert c.args[0]["trigger"] == "auto"
            assert c.args[0]["settings"]["task_vars"]["store_url"] == "https://shopA.example.com"

        # task→skill links reference the SHARED skill ids
        link_skills = [c.args[1] for c in ctx.db.task_service.add_skill_to_task.call_args_list]
        assert link_skills == [QA_SKILL, QA_SKILL, QA_SKILL, FD_SKILL]

    def test_agents_names_org_and_vehicle(self):
        ctx = _make_ctx()
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        agent_payloads = [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]
        qa_agents, fd_agent = agent_payloads[:-1], agent_payloads[-1]

        assert fd_agent["name"] == "前台小张"
        assert all(a["name"].startswith("客服小") for a in qa_agents)
        assert len({a["name"] for a in qa_agents}) == len(qa_agents)  # unique names
        for a in agent_payloads:
            assert a["org_id"] == "org_sales"
            assert a["vehicle_id"] == "veh-local"
            assert len(a["tasks"]) == 1
        assert {a["skills"][0] for a in qa_agents} == {QA_SKILL}
        assert fd_agent["skills"] == [FD_SKILL]

    def test_missing_skill_aborts_with_subscribe_hint(self):
        ctx = _make_ctx(missing_skill=QA_SKILL)
        with pytest.raises(RuntimeError, match="not visible.*subscribe"):
            dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        ctx.db.task_service.add_task.assert_not_called()

    def test_missing_prompt_aborts(self):
        ctx = _make_ctx()
        with patch.object(dc, "_missing_system_prompts", return_value=[dc._DDCS_QA_PROMPT_ID]), \
             patch.object(dc, "_prompt_visible", return_value=False):
            with pytest.raises(RuntimeError, match="Prompt .* is not visible"):
                dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        ctx.db.task_service.add_task.assert_not_called()

    def test_sales_org_created_when_absent(self):
        ctx = _make_ctx(org_rows=[])
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        assert ctx.db.org_service.add_org.call_args.args[0]["name"] == "Sales"
        payloads = [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]
        assert all(p["org_id"] == "org_new" for p in payloads)

    def test_task_skill_link_failure_aborts(self):
        ctx = _make_ctx()
        ctx.db.task_service.add_skill_to_task.return_value = {"success": False, "error": "boom"}
        with pytest.raises(RuntimeError, match="link task"):
            dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")


class TestDrawQaNames:
    def test_unique_within_pool(self):
        names = dc._draw_qa_names(10)
        assert len(names) == len(set(names)) == 10

    def test_overflow_beyond_pool(self):
        n = len(dc._DDCS_QA_NAME_POOL) + 5
        names = dc._draw_qa_names(n)
        assert len(names) == len(set(names)) == n


class TestPromptAuthorResolution:
    def test_author_prefers_config_skill_owner(self):
        assert dc._skill_author({"owner": "buyer@x", "config": {"skill_owner": "author@x"}}) == "author@x"
        assert dc._skill_author({"owner": "buyer@x", "config": {}}) == "buyer@x"
