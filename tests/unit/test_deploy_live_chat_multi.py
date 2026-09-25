"""Fast Deploy: Pinduoduo (pdd_cs) and several stores on one machine with a shared Q&A pool."""

import os
from unittest.mock import MagicMock, patch

import pytest

from cli.deploy import commands as dc
from tests.unit.test_deploy_douyin_cs import _make_ctx


@pytest.fixture(autouse=True)
def _env(tmp_path):
    with patch.object(dc, "_missing_system_prompts", return_value=[]), \
         patch("agent.ec_agents.vehicle_affinity.resolve_local_vehicle_id", return_value="veh-local"), \
         patch("config.envi.getECBotDataHome", return_value=str(tmp_path)), \
         patch.dict(os.environ, {}, clear=False):
        yield tmp_path


def _tasks(ctx):
    return [c.args[0] for c in ctx.db.task_service.add_task.call_args_list]


def _agents(ctx):
    return [c.args[0] for c in ctx.db.agent_service.create_agent_from_data.call_args_list]


class TestPinduoduoSingleStore:
    def test_uses_the_pdd_skills_and_switches_the_site_on(self, _env):
        ctx = _make_ctx()
        plan, log, created = dc._deploy_live_chat(
            {"store_urls": ["https://mms.pinduoduo.com/chat-merchant/index.html"], "qa_agents": 2,
             "store_id": "pdd-shop1"}, ctx, "me", dc._PDD_PROFILE)
        assert plan == {"agents": 3, "skills": 0, "tasks": 3}
        names = [t["name"] for t in _tasks(ctx)]
        assert names == ["拼多多客服前台001", "拼多多客服应答001", "拼多多客服应答002"]
        linked = {c.args[1] for c in ctx.db.task_service.add_skill_to_task.call_args_list}
        assert linked == {dc._PDD_PROFILE.fd_skill_id, dc._PDD_PROFILE.qa_skill_id}
        run_env = (_env / "run.env").read_text(encoding="utf-8")
        assert "ECAN_LIVE_CHAT_SITE=pdd_chat" in run_env
        assert "ECAN_FEIGE_WS" not in run_env, "Feige flags stay out of a Pinduoduo deploy"

    def test_the_site_switch_replaces_an_old_value(self, _env):
        (_env / "run.env").write_text("ECAN_LIVE_CHAT_SITE=feige_chat\nOTHER=1\n", encoding="utf-8")
        dc._set_run_env({"ECAN_LIVE_CHAT_SITE": "pdd_chat"}, [])
        text = (_env / "run.env").read_text(encoding="utf-8")
        assert "ECAN_LIVE_CHAT_SITE=pdd_chat" in text and "feige_chat" not in text and "OTHER=1" in text

    def test_an_unpublished_skill_is_found_by_its_exact_name(self):
        ctx = _make_ctx(missing_skill=dc._PDD_PROFILE.qa_skill_id)
        ctx.db.skill_service.query_skills.return_value = {"success": True, "data": [
            {"id": "skill_local_copy", "name": "拼多多客服问答00", "config": {}},
            {"id": "skill_other", "name": "拼多多客服问答00-旧", "config": {}}]}
        row = dc._find_skill(ctx, dc._PDD_PROFILE, "qa")
        assert row["id"] == "skill_local_copy"


def _store_ctx(stores):
    ctx = _make_ctx()
    recs = {s["store_id"]: dict(s) for s in stores}
    ctx.db.store_service.get_store.side_effect = lambda sid: recs.get(sid)
    ctx.db.store_service.upsert_store.side_effect = lambda d: recs[d["store_id"]].update(d) or {"success": True}
    return ctx, recs


class _Registry:
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


class TestSeveralStoresOneMachine:
    STORES = [
        {"store_id": "douyin-店A", "name": "店A", "platform": "douyin",
         "store_urls": ["https://im.jinritemai.com/pc_seller_v2/main/workspace"],
         "browser_profile_id": "a-login"},
        {"store_id": "douyin-店B", "name": "店B", "platform": "douyin", "store_urls": []},
    ]

    def _run(self, cfg, registry):
        ctx, recs = _store_ctx(self.STORES)
        with patch.object(dc, "_profile_registry", return_value=registry):
            out = dc._deploy_live_chat_multi(cfg, ctx, "me", dc._DDCS_PROFILE)
        return (ctx, recs) + out

    def test_a_front_desk_per_store_and_one_shared_pool(self):
        reg = _Registry({"a-login": {"id": "a-login", "login_state": "ok"}})
        ctx, recs, plan, log, created = self._run(
            {"stores": ["douyin-店A", "douyin-店B"], "qa_agents": 3}, reg)
        tasks = _tasks(ctx)
        fds = [t for t in tasks if t["name"].startswith("飞鸽客服前台-")]
        pool = [t for t in tasks if "共享" in t["name"]]
        assert [t["name"] for t in fds] == ["飞鸽客服前台-店A", "飞鸽客服前台-店B"]
        assert len(pool) == 3
        # each front desk is its store's, in its store's own login
        assert fds[0]["settings"]["task_vars"]["store_id"] == "douyin-店A"
        assert fds[0]["settings"]["browser_identity"] == {"browser_profile_id": "a-login"}
        assert fds[1]["settings"]["task_vars"]["store_id"] == "douyin-店B"
        # the pool accepts BOTH front desks and belongs to no single store
        fd_agents = [a for a in _agents(ctx) if a["name"].startswith("前台-")]
        assert len(fd_agents) == 2
        senders = pool[0]["settings"]["task_vars"]["front_desk_agent_id"].split(",")
        assert len(senders) == 2
        assert "store_id" not in pool[0]["settings"]["task_vars"]
        # front desks follow store placement; the pool is pinned here
        assert all("vehicle_id" not in a for a in fd_agents)
        qa_agents = [a for a in _agents(ctx) if a["name"].startswith("客服小")]
        assert len(qa_agents) == 3 and all(a["vehicle_id"] == "veh-local" for a in qa_agents)
        assert plan["stores"] == 2

    def test_a_store_without_a_login_gets_one_and_is_reported(self):
        reg = _Registry({"a-login": {"id": "a-login", "login_state": "ok"}})
        ctx, recs, plan, log, created = self._run({"stores": ["douyin-店A", "douyin-店B"], "qa_agents": 1}, reg)
        new_id = recs["douyin-店B"]["browser_profile_id"]
        assert new_id in reg.profiles and new_id.endswith("-login")
        assert all(ord(c) < 128 for c in new_id), "profile ids must be ASCII"
        assert [x["store_id"] for x in plan["needs_login"]] == ["douyin-店B"]

    def test_unknown_or_foreign_stores_are_refused(self):
        with pytest.raises(RuntimeError, match="not in the store list"):
            self._run({"stores": ["nope"], "qa_agents": 1}, _Registry())
        ctx, _ = _store_ctx([{"store_id": "pdd-x", "name": "x", "platform": "pinduoduo"}])
        with pytest.raises(RuntimeError, match="is a pinduoduo store"):
            dc._deploy_live_chat_multi({"stores": ["pdd-x"], "qa_agents": 1}, ctx, "me", dc._DDCS_PROFILE)

    def test_nothing_picked_is_refused(self):
        with pytest.raises(RuntimeError, match="at least one store"):
            dc._deploy_live_chat_multi({"stores": [], "qa_agents": 2}, MagicMock(), "me", dc._DDCS_PROFILE)


def test_login_profile_ids_are_ascii_and_stable():
    a = dc._login_profile_id("douyin-店A")
    assert a == dc._login_profile_id("douyin-店A") and a != dc._login_profile_id("douyin-店B")
    assert all(ord(c) < 128 for c in a)
