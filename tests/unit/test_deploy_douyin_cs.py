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
def _patch_environment(tmp_path):
    # getECBotDataHome patched so _write_run_env never touches real appdata.
    with patch.object(dc, "_missing_system_prompts", return_value=[]), \
         patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
               return_value="veh-local"), \
         patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
        yield


class TestDeployDouyinCs:
    CFG = {"store_urls": ["https://shopA.example.com"], "qa_agents": 3}

    def test_creates_tasks_agents_referencing_shared_skills(self):
        ctx = _make_ctx()
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        # 3 QA tasks + 1 FD task; NO skills created
        assert plan == {"agents": 4, "skills": 0, "tasks": 4}
        assert created["skills"] == []

        # Front-desk task is created FIRST — the Q&A tasks carry its agent id.
        task_names = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert task_names == ["飞鸽客服前台001", "飞鸽客服应答001", "飞鸽客服应答002", "飞鸽客服应答003"]
        for c in ctx.db.task_service.add_task.call_args_list:
            assert c.args[0]["trigger"] == "auto"
            assert c.args[0]["settings"]["task_vars"]["store_url"] == "https://shopA.example.com"

        # task→skill links reference the SHARED skill ids
        link_skills = [c.args[1] for c in ctx.db.task_service.add_skill_to_task.call_args_list]
        assert link_skills == [FD_SKILL, QA_SKILL, QA_SKILL, QA_SKILL]

    def test_qa_tasks_carry_front_desk_agent_id(self):
        """The shared Q&A skill's pend_event filters on {{front_desk_agent_id}};
        each Q&A task must carry the freshly created front-desk agent's id in
        task_vars (the FD agent is created before any Q&A task exists)."""
        ctx = _make_ctx()
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        calls = ctx.db.task_service.add_task.call_args_list
        fd_call, qa_calls = calls[0], calls[1:]
        # First created agent (agent_1) is 前台小张
        first_agent = ctx.db.agent_service.create_agent_from_data.call_args_list[0]
        assert first_agent.args[0]["name"] == "前台小张"
        assert "front_desk_agent_id" not in fd_call.args[0]["settings"]["task_vars"]
        for c in qa_calls:
            assert c.args[0]["settings"]["task_vars"]["front_desk_agent_id"] == "agent_1"

    def test_agents_names_org_and_vehicle(self):
        ctx = _make_ctx()
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        agent_payloads = [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]
        fd_agent, qa_agents = agent_payloads[0], agent_payloads[1:]

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

    def test_all_four_prompts_verified(self):
        """The recipe verifies 应答0 + 社交应答0 + RAG路由分类0 (QA skill)
        and 前台0 (FD skill)."""
        ctx = _make_ctx()
        with patch.object(dc, "_prompt_visible", return_value=True) as pv:
            dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        checked = [c.args[0] for c in pv.call_args_list]
        assert checked == [dc._DDCS_QA_PROMPT_ID, dc._DDCS_QA_SOCIAL_PROMPT_ID,
                           dc._DDCS_QA_RAG_PROMPT_ID, dc._DDCS_FD_PROMPT_ID]

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


class TestFeigeRunEnv:
    """The recipe persists the validated Feige runtime flags to
    <appdata>/run.env (loaded by main.py at startup; OS env wins)."""

    def test_writes_all_flags_to_new_file(self, tmp_path):
        log = []
        with patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
            dc._write_run_env(dc._DDCS_FEIGE_ENV, log)
        content = (tmp_path / "run.env").read_text(encoding="utf-8")
        assert "ECAN_FEIGE_WS=1" in content
        assert "ECAN_FEIGE_QA_MAX_CONCURRENCY=3" in content
        assert "DIRECT_FEIGE_JOB_TIMEOUT_S=15" in content
        assert f"{len(dc._DDCS_FEIGE_ENV)} new flag(s)" in log[0]

    def test_existing_values_survive_redeploy(self, tmp_path):
        (tmp_path / "run.env").write_text(
            "ECAN_FEIGE_QA_MAX_CONCURRENCY=9\n", encoding="utf-8")
        log = []
        with patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
            dc._write_run_env(dc._DDCS_FEIGE_ENV, log)
        content = (tmp_path / "run.env").read_text(encoding="utf-8")
        assert "ECAN_FEIGE_QA_MAX_CONCURRENCY=9" in content   # hand-tune kept
        assert "ECAN_FEIGE_QA_MAX_CONCURRENCY=3" not in content
        assert "ECAN_FEIGE_WS=1" in content                    # missing keys added

    def test_deploy_writes_run_env(self, tmp_path):
        ctx = _make_ctx()
        with patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
            _, log, _ = dc._deploy_douyin_cs(TestDeployDouyinCs.CFG, ctx, "buyer@x")
        assert (tmp_path / "run.env").exists()
        assert any("Runtime env" in line for line in log)


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
