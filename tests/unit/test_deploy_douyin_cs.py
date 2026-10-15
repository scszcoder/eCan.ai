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
    # The store as created on the Stores page (no login profile yet).
    ctx.db.store_service.get_store.return_value = {
        "store_id": "shopA", "name": "shopA", "platform": "douyin",
        "store_urls": ["https://shopA.example.com"]}
    return ctx


class FakeProfiles:
    """Stands in for the fingerprint profile registry (no files touched)."""
    LOGIN_OK = "ok"

    def __init__(self, existing=None):
        self.profiles = dict(existing or {})

    def get_profile(self, pid):
        return self.profiles.get(pid)

    def login_state(self, pid):
        return {"state": (self.profiles.get(pid) or {}).get("login_state", "needs_login")}

    def make_profile(self, pid, **kw):
        return {"id": pid, **kw}

    def save_profile(self, prof, proxy_password=""):
        self.profiles[prof["id"]] = prof


@pytest.fixture(autouse=True)
def _patch_environment(tmp_path):
    # getECBotDataHome patched so _write_run_env never touches real appdata.
    real_missing = dc._missing_system_prompts  # for tests of the real scan
    with patch.object(dc, "_missing_system_prompts", return_value=[]), \
         patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id",
               return_value="veh-local"), \
         patch("config.envi.getECBotDataHome", return_value=str(tmp_path)), \
         patch.object(dc, "_profile_registry", return_value=FakeProfiles()):
        yield real_missing


class TestDeployDouyinCs:
    CFG = {"store_id": "shopA", "qa_agents": 3}

    def test_creates_tasks_agents_referencing_shared_skills(self):
        ctx = _make_ctx()
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        # 3 QA tasks + 1 FD task; NO skills created
        assert {k: plan[k] for k in ("agents", "skills", "tasks")} == {"agents": 4, "skills": 0, "tasks": 4}
        assert created["skills"] == []

        # Front-desk task is created FIRST — the Q&A tasks carry its agent id.
        task_names = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert task_names == ["飞鸽客服前台-shopA", "飞鸽客服应答001", "飞鸽客服应答002", "飞鸽客服应答003"]
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
        # First created agent (agent_1) is the store's front desk (store-scoped name)
        first_agent = ctx.db.agent_service.create_agent_from_data.call_args_list[0]
        assert first_agent.args[0]["name"] == "前台-shopA"
        assert "front_desk_agent_id" not in fd_call.args[0]["settings"]["task_vars"]
        for c in qa_calls:
            assert c.args[0]["settings"]["task_vars"]["front_desk_agent_id"] == "agent_1"
        # the front desk carries its Q&A pool's sizing; Q&A tasks don't
        n = len(qa_calls)
        assert fd_call.args[0]["settings"]["pool"] == {"min": min(2, n), "max": n, "idle_minutes": 10}
        assert all("pool" not in c.args[0]["settings"] for c in qa_calls)

    def test_agents_names_org_and_vehicle(self):
        ctx = _make_ctx()
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

        agent_payloads = [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]
        fd_agent, qa_agents = agent_payloads[0], agent_payloads[1:]

        assert fd_agent["name"] == "前台-shopA"
        assert all(a["name"].startswith("客服小") for a in qa_agents)
        assert len({a["name"] for a in qa_agents}) == len(qa_agents)  # unique names
        for a in agent_payloads:
            assert a["org_id"] == "org_sales"
            assert a["vehicle_id"] == "veh-local"  # unassigned store -> this machine
            assert len(a["tasks"]) == 1
        assert {a["skills"][0] for a in qa_agents} == {QA_SKILL}
        assert fd_agent["skills"] == [FD_SKILL]

    def test_agents_follow_the_stores_assigned_vehicle(self):
        ctx = _make_ctx()
        snap = {"stores": {"shopA": {"assigned": "veh-store"}}}
        with patch("agent.ec_agents.store_placement.refresh", return_value=snap):
            dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        payloads = [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]
        assert payloads and all(a["vehicle_id"] == "veh-store" for a in payloads)

    def test_a_store_id_is_required(self):
        ctx = _make_ctx()
        with pytest.raises(RuntimeError, match="store_id is required"):
            dc._deploy_douyin_cs({"qa_agents": 3}, ctx, "buyer@x")
        ctx.db.task_service.add_task.assert_not_called()

    def test_the_store_must_exist_on_the_stores_page(self):
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = None
        with pytest.raises(RuntimeError, match="create it on the Stores page"):
            dc._deploy_douyin_cs({**self.CFG, "mode": "replace"}, ctx, "buyer@x")
        ctx.db.task_service.add_task.assert_not_called()
        ctx.db.task_service.get_tasks_by_skill.assert_not_called()   # replace touched nothing

    def test_a_store_of_another_platform_is_refused(self):
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = {"store_id": "shopA", "platform": "pinduoduo",
                                                       "store_urls": ["https://x"]}
        with pytest.raises(RuntimeError, match="is a pinduoduo store"):
            dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")

    def test_a_store_without_a_url_uses_the_seller_workspace(self):
        # Fast Deploy 2026-10-10: the URL is optional -- the store id tells stores
        # apart and each signs in through its own profile.
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = {"store_id": "shopA", "platform": "douyin",
                                                       "store_urls": []}
        dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        for c in ctx.db.task_service.add_task.call_args_list:
            assert c.args[0]["settings"]["task_vars"]["store_url"] == dc._DEFAULT_STORE_URLS["douyin"]

    def test_a_store_without_a_login_profile_gets_one(self):
        ctx = _make_ctx()
        plan, log, _ = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        pid = dc._login_profile_id("shopA")
        for c in ctx.db.task_service.add_task.call_args_list:
            assert c.args[0]["settings"]["browser_identity"] == {"browser_profile_id": pid}
        ctx.db.store_service.upsert_store.assert_any_call({"store_id": "shopA", "browser_profile_id": pid})
        assert plan["needs_login"] == [{"store_id": "shopA", "store_name": "shopA", "profile_id": pid}]

    def test_a_signed_in_store_keeps_its_profile(self):
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = {"store_id": "shopA", "name": "店A",
                                                       "platform": "douyin",
                                                       "store_urls": ["https://shopA.example.com"],
                                                       "browser_profile_id": "a-login"}
        reg = FakeProfiles({"a-login": {"id": "a-login", "login_state": "ok"}})
        with patch.object(dc, "_profile_registry", return_value=reg):
            plan, _, _ = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        first = ctx.db.task_service.add_task.call_args_list[0].args[0]
        assert first["settings"]["browser_identity"] == {"browser_profile_id": "a-login"}
        assert plan["needs_login"] == []

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


class TestPromptStoresScanned:
    """v0.9.95q incident: a CUSTOMER machine has the 抖店客服 prompts only in
    subscribed_prompts/ (populated by subscribe-time download) — the
    visibility scan must include that store, not just my_prompts."""

    def test_subscribed_prompts_dir_counts(self, tmp_path, _patch_environment):
        import json as _json
        real_missing = _patch_environment  # the unpatched scanner
        (tmp_path / "my_prompts").mkdir()
        sub = tmp_path / "subscribed_prompts"
        sub.mkdir()
        (sub / "0_pr-287230.json").write_text(
            _json.dumps({"id": "pr-287230", "title": "x"}), encoding="utf-8")

        def fake_user_dir(user_email=None, subdir=None):
            return str(tmp_path / (subdir or ""))

        with patch("utils.user_path_helper.get_user_data_dir", side_effect=fake_user_dir), \
             patch("agent.ec_skills.prompt_loader.SAMPLE_PROMPTS_DIR", str(tmp_path / "none")):
            missing = real_missing(["pr-287230", "pr-999999"])
        assert missing == ["pr-999999"]


class TestLogUserIsTheExactDir:
    """The app hands its subprocess ECAN_LOG_USER = the user's dir name
    ('wechat_x_local'). Mapping it again ('..._local_local') missed every
    local prompt (2026-09-28: 拼多多 deploy refused pr-287230 though the file
    was right there)."""

    def test_prompts_in_the_log_users_dir_count(self, tmp_path, _patch_environment):
        import json as _json
        import os as _os
        real_missing = _patch_environment
        d = tmp_path / "wechat_abc_local" / "my_prompts"
        d.mkdir(parents=True)
        (d / "0_pr-287230.json").write_text(_json.dumps({"id": "pr-287230"}), encoding="utf-8")
        with patch("config.app_info.app_info.appdata_path", str(tmp_path), create=True), \
             patch.dict(_os.environ, {"ECAN_LOG_USER": "wechat_abc_local"}), \
             patch("agent.ec_skills.prompt_loader.SAMPLE_PROMPTS_DIR", str(tmp_path / "none")):
            assert real_missing(["pr-287230"]) == []


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


class TestErrorsInTheAppsLanguage:
    """The Fast Deploy panel shows these messages to the customer: Chinese on
    the CN build, English elsewhere."""

    def test_cn_build_gets_chinese(self):
        import os as _os
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = None
        with patch.dict(_os.environ, {"ECAN_APP_ID": "cn"}):
            with pytest.raises(RuntimeError, match="请先在店铺页面创建"):
                dc._deploy_douyin_cs(TestDeployDouyinCs.CFG, ctx, "buyer@x")

    def test_intl_build_gets_english(self):
        import os as _os
        ctx = _make_ctx()
        ctx.db.store_service.get_store.return_value = None
        with patch.dict(_os.environ, {"ECAN_APP_ID": "intl"}):
            with pytest.raises(RuntimeError, match="create it on the Stores page"):
                dc._deploy_douyin_cs(TestDeployDouyinCs.CFG, ctx, "buyer@x")


class TestProductExportOption:
    """fetch_catalog: a one-time background export task on the front desk."""

    CFG = {"store_id": "shopA", "qa_agents": 2, "fetch_catalog": True}

    def test_adds_the_export_task_to_the_front_desk(self):
        ctx = _make_ctx()
        ctx.db.skill_service.query_skills.return_value = {"success": True, "data": [
            {"id": "skill_export", "name": "抖店商品导出"}, {"id": "x", "name": "抖店商品导出 旧"}]}
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        tasks = [c.args[0] for c in ctx.db.task_service.add_task.call_args_list]
        export = [t for t in tasks if "商品导出" in t["name"]]
        assert len(export) == 1
        assert export[0]["name"] == "飞鸽客服前台商品导出-shopA"   # store-scoped
        s = export[0]["settings"]
        assert s["run_once"] is True and s["run_class"] == "background" and s["start_after_idle_min"] == 5
        # A busy front desk may never idle 5 min; the export still runs within the hour.
        assert s["start_after_idle_max_min"] == 60
        assert s["task_vars"]["store_id"] == "shopA" and s["browser_identity"]   # the store's own browser
        fd = ctx.db.agent_service.create_agent_from_data.call_args_list[0].args[0]
        assert fd["name"] == "前台-shopA" and len(fd["tasks"]) == 2 and "skill_export" in fd["skills"]
        assert any("商品导出" in line or "Product export" in line for line in log)

    def test_missing_skill_is_reported_not_fatal(self):
        ctx = _make_ctx()
        ctx.db.skill_service.query_skills.return_value = {"success": True, "data": []}
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        tasks = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert not any("商品导出" in n for n in tasks)
        assert any("抖店商品导出" in line for line in log)

    def test_off_by_request(self):
        ctx = _make_ctx()
        dc._deploy_douyin_cs({"store_id": "shopA", "qa_agents": 2}, ctx, "buyer@x")
        ctx.db.skill_service.query_skills.assert_not_called()


class TestPromoRefreshOption:
    """fetch_promos: a recurring background task that re-reads the store's
    current promotions every 30 min and overwrites its auto-applied snapshot."""

    CFG = {"store_id": "shopA", "qa_agents": 2, "fetch_promos": True}

    def test_adds_the_recurring_promo_task_to_the_front_desk(self):
        ctx = _make_ctx()
        ctx.db.skill_service.query_skills.return_value = {"success": True, "data": [
            {"id": "skill_promo", "name": "抖店营销导出"}]}
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        tasks = [c.args[0] for c in ctx.db.task_service.add_task.call_args_list]
        promo = [t for t in tasks if "活动刷新" in t["name"]]
        assert len(promo) == 1
        p = promo[0]
        assert p["name"] == "飞鸽客服前台活动刷新-shopA"   # store-scoped
        assert p["trigger"] == "schedule" and p["schedule"]["repeat_number"] == 30
        s = p["settings"]
        assert s["run_class"] == "background" and s.get("run_once") is None
        assert s["start_after_idle_min"] == 2 and s["start_after_idle_max_min"] == 10
        fd = ctx.db.agent_service.create_agent_from_data.call_args_list[0].args[0]
        assert "skill_promo" in fd["skills"]
        assert any("活动刷新" in line or "Promotions" in line for line in log)

    def test_missing_skill_is_reported_not_fatal(self):
        ctx = _make_ctx()
        ctx.db.skill_service.query_skills.return_value = {"success": True, "data": []}
        plan, log, created = dc._deploy_douyin_cs(self.CFG, ctx, "buyer@x")
        tasks = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert not any("活动刷新" in n for n in tasks)
        assert any("抖店营销导出" in line for line in log)

    def test_off_by_default(self):
        ctx = _make_ctx()
        dc._deploy_douyin_cs({"store_id": "shopA", "qa_agents": 2}, ctx, "buyer@x")
        tasks = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert not any("活动刷新" in n for n in tasks)


class TestSharedQaPool:
    """A second store's 客服 joins the Q&A agents of a store already deployed."""

    @staticmethod
    def _existing(ctx):
        rows = {
            "fdtA": {"id": "fdtA", "name": "飞鸽客服前台001",
                     "metadata": {"task_vars": {"store_id": "shopA"}, "pool": {"min": 2, "max": 2}}},
            "qa1": {"id": "qa1", "name": "飞鸽客服应答001", "metadata": {"task_vars": {
                "store_id": "shopA", "store_url": "u", "front_desk_agent_id": "fdA"}}},
            "qa2": {"id": "qa2", "name": "飞鸽客服应答002", "metadata": {"task_vars": {
                "store_id": "shopA", "front_desk_agent_id": "fdA"}}},
        }
        saved = {}

        def query_tasks(id=None, **kw):
            if id:
                return {"success": True, "data": [rows[id]] if id in rows else []}
            return {"success": True, "data": list(rows.values())}

        def update_task(tid, data):
            saved[tid] = data["settings"]
            rows[tid] = dict(rows[tid], metadata=data["settings"])
            return {"success": True}
        ctx.db.task_service.query_tasks.side_effect = query_tasks
        ctx.db.task_service.update_task.side_effect = update_task
        ctx.db.agent_service.get_agent_task_associations.side_effect = (
            lambda aid: {"data": [{"task_id": "fdtA"}] if aid == "fdA" else []})
        return saved

    def test_cs_pools_groups_front_desks_by_shared_qa(self):
        ctx = _make_ctx()
        self._existing(ctx)
        pools = dc.cs_pools(ctx, "douyin_cs")
        assert len(pools) == 1
        assert pools[0]["qa_count"] == 2 and pools[0]["front_desks"][0]["agent_id"] == "fdA"
        assert pools[0]["front_desks"][0]["store_id"] == "shopA"

    def test_second_store_joins_the_pool(self):
        ctx = _make_ctx()
        saved = self._existing(ctx)
        ctx.db.store_service.get_store.return_value = {
            "store_id": "shopB", "name": "shopB", "platform": "douyin", "store_urls": ["https://shopB.example.com"]}
        plan, log, created = dc._deploy_douyin_cs(
            {"store_id": "shopB", "share_with": "fdA", "qa_agents_extra": 1}, ctx, "buyer@x")
        assert plan["shared_pool"] is True
        names = [c.args[0]["name"] for c in ctx.db.task_service.add_task.call_args_list]
        assert names == ["飞鸽客服前台-shopB", "飞鸽客服应答共享003"]      # front desk B + 1 extra Q&A
        new_fd = ctx.db.agent_service.create_agent_from_data.call_args_list[0].args  # agent_1
        assert new_fd[0]["name"] == "前台-shopB"
        for tid in ("qa1", "qa2"):
            tv = saved[tid]["task_vars"]
            assert tv["front_desk_agent_id"] == "fdA,agent_1"
            assert "store_id" not in tv and "store_url" not in tv     # each turn names its store
        assert saved["fdtA"]["pool"]["max"] == 3                        # 2 existing + 1 new
        extra = ctx.db.task_service.add_task.call_args_list[1].args[0]["settings"]["task_vars"]
        assert extra == {"front_desk_agent_id": "fdA,agent_1"}
        assert set(created["updated_tasks"]) == {"qa1", "qa2", "fdtA"}

    def test_unknown_pool_fails_clearly(self):
        ctx = _make_ctx()
        self._existing(ctx)
        with pytest.raises(RuntimeError):
            dc._deploy_douyin_cs({"store_id": "shopA", "share_with": "nope"}, ctx, "buyer@x")
