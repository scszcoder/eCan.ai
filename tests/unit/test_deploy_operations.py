"""Fast Deploy 运营 (store operations): a task + agent per role skill
<platform>_<role>_0; after-sales on the panel's schedule, the rest on a chat
message; a missing role skill stops the deploy before anything is created."""

from unittest.mock import patch

import pytest

from cli.deploy import commands as dc
from tests.unit.test_deploy_douyin_cs import FakeProfiles, _make_ctx

ROLES = [r for r, _, _ in dc._OPS_ROLES]
CFG = {"store_id": "ebay-shop", "schedule": {"start": "2026-09-29T01:00:00.000Z", "every": 30, "unit": "minutes"}}


@pytest.fixture(autouse=True)
def _env(tmp_path):
    with patch.object(dc, "_profile_registry", return_value=FakeProfiles()), \
         patch("config.envi.getECBotDataHome", return_value=str(tmp_path)):
        yield


def _ctx(skill_names):
    ctx = _make_ctx()
    ctx.db.store_service.get_store.return_value = {
        "store_id": "ebay-shop", "name": "店E", "platform": "ebay",
        "store_urls": ["https://www.ebay.com/sh/ovw"]}
    rows = {n: {"id": f"sk_{n}", "name": n, "config": {}} for n in skill_names}
    ctx.db.skill_service.query_skills.side_effect = lambda name=None, **kw: {
        "success": True, "data": [rows[name]] if name in rows else []}
    return ctx


def _tasks(ctx):
    return [c.args[0] for c in ctx.db.task_service.add_task.call_args_list]


def test_a_task_and_agent_per_role():
    ctx = _ctx([f"ebay_{r}_0" for r in ROLES])
    plan, log, created = dc._deploy_operations(CFG, ctx, "me", "ebay_ops")
    assert plan["agents"] == plan["tasks"] == 7
    tasks = _tasks(ctx)
    linked = [c.args[1] for c in ctx.db.task_service.add_skill_to_task.call_args_list]
    assert linked == [f"sk_ebay_{r}_0" for r in ROLES]
    by_skill = dict(zip(linked, tasks))
    after = by_skill["sk_ebay_after_sales_0"]
    assert after["trigger"] == "schedule"
    assert after["schedule"]["repeat_type"] == "by minutes" and after["schedule"]["repeat_number"] == 30
    assert after["schedule"]["start_date_time"] == "2026-09-29T01:00:00.000Z"
    for r in ROLES:
        if r != "after_sales":
            assert by_skill[f"sk_ebay_{r}_0"]["trigger"] == "message"
            assert "schedule" not in by_skill[f"sk_ebay_{r}_0"]
    # every task is the store's: its id, URL and login profile
    for t in tasks:
        assert t["settings"]["task_vars"]["store_id"] == "ebay-shop"
        assert t["settings"]["browser_identity"]["browser_profile_id"]
    # the manager knows who to message
    mgr_vars = by_skill["sk_ebay_manage_0"]["settings"]["task_vars"]
    assert set(k for k in mgr_vars if k.endswith("_agent_id")) == {f"{r}_agent_id" for r in ROLES if r != "manage"}


def test_a_missing_role_skill_stops_before_anything_is_created():
    ctx = _ctx([f"ebay_{r}_0" for r in ROLES if r not in ("research", "manage")])
    with pytest.raises(RuntimeError, match="ebay_research_0, ebay_manage_0"):
        dc._deploy_operations(CFG, ctx, "me", "ebay_ops")
    ctx.db.task_service.add_task.assert_not_called()
    ctx.db.agent_service.create_agent_from_data.assert_not_called()


def test_only_the_exact_name_counts():
    # ebay_after_sales0 (no underscore) is not ebay_after_sales_0
    ctx = _ctx(["ebay_after_sales0"] + [f"ebay_{r}_0" for r in ROLES if r != "after_sales"])
    with pytest.raises(RuntimeError, match="ebay_after_sales_0"):
        dc._deploy_operations(CFG, ctx, "me", "ebay_ops")


def test_the_schedule_is_required():
    ctx = _ctx([f"ebay_{r}_0" for r in ROLES])
    with pytest.raises(RuntimeError, match="schedule"):
        dc._deploy_operations({"store_id": "ebay-shop"}, ctx, "me", "ebay_ops")
    ctx.db.task_service.add_task.assert_not_called()


def test_a_store_of_another_platform_is_refused():
    ctx = _ctx([f"ebay_{r}_0" for r in ROLES])
    ctx.db.store_service.get_store.return_value = {"store_id": "ebay-shop", "platform": "amazon",
                                                   "store_urls": ["https://x"]}
    with pytest.raises(RuntimeError, match="is a amazon store"):
        dc._deploy_operations(CFG, ctx, "me", "ebay_ops")
