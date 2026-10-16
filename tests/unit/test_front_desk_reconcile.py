"""Pure front-desk reconciliation planner (one front desk per store)."""

from agent.ec_agents.store_overview import (
    is_front_desk_name, plan_front_desk_reconcile, plan_qa_rewire,
)


def test_is_front_desk_name():
    assert is_front_desk_name("飞鸽客服前台001")
    assert is_front_desk_name("前台-店B")
    assert not is_front_desk_name("飞鸽客服应答001")
    assert not is_front_desk_name("")


def _fd(store_id, agent_id, agent_name, task_name):
    return {"store_id": store_id, "agent_id": agent_id, "agent_name": agent_name,
            "task_id": f"t_{agent_id}", "task_name": task_name}


def test_single_front_desk_is_not_flagged():
    fds = [_fd("douyin-店A", "a1", "前台-店A", "前台-店A")]
    assert plan_front_desk_reconcile(fds, {"douyin-店A": "店A"}) == []


def test_legacy_plus_scoped_recommends_keeping_the_scoped_one():
    fds = [
        _fd("douyin-店B", "legacy", "前台小张", "飞鸽客服前台001"),
        _fd("douyin-店B", "scoped", "前台-店B", "前台-店B"),
    ]
    plans = plan_front_desk_reconcile(fds, {"douyin-店B": "店B"})
    assert len(plans) == 1
    p = plans[0]
    assert p["ambiguous"] is False
    assert p["keep"]["agent_id"] == "scoped"
    assert [r["agent_id"] for r in p["retire"]] == ["legacy"]


def test_ambiguous_when_no_store_scoped_front_desk():
    # Two generic front desks, neither carries the store's display name.
    fds = [
        _fd("douyin-店C", "a1", "前台小张", "飞鸽客服前台001"),
        _fd("douyin-店C", "a2", "前台小李", "飞鸽客服前台002"),
    ]
    plans = plan_front_desk_reconcile(fds, {"douyin-店C": "店C"})
    assert len(plans) == 1
    assert plans[0]["ambiguous"] is True
    assert plans[0]["keep"] is None
    assert plans[0]["retire"] == []


def test_several_tasks_one_agent_is_not_a_duplicate():
    # One agent, two front-desk tasks (e.g. 前台 + 商品导出 both named 前台…) → not a dup.
    fds = [
        _fd("douyin-店A", "a1", "前台-店A", "前台-店A"),
        _fd("douyin-店A", "a1", "前台-店A", "前台商品导出-店A"),
    ]
    assert plan_front_desk_reconcile(fds, {"douyin-店A": "店A"}) == []


# ── plan_qa_rewire: Q&A pool pointed at a dead front desk id ──────────────────

def _qa(store_id, task_id, task_name, fda):
    return {"store_id": store_id, "task_id": task_id, "task_name": task_name,
            "front_desk_agent_id": fda}


def test_stale_qa_wiring_is_repointed_to_live_front_desk():
    # 店B's live front desk is 7ca0, but its Q&A still waits on a573 (a dead id).
    fds = [_fd("douyin-店B", "7ca0", "前台-店B", "前台-店B")]
    qa = [_qa("douyin-店B", "q1", "飞鸽客服应答004", "a573"),
          _qa("douyin-店B", "q2", "飞鸽客服应答005", "a573")]
    out = plan_qa_rewire(fds, qa, {"douyin-店B": "店B"})
    assert {r["task_id"] for r in out} == {"q1", "q2"}
    assert all(r["from"] == "a573" and r["to"] == "7ca0" and r["to_name"] == "前台-店B" for r in out)


def test_correctly_wired_qa_is_not_touched():
    fds = [_fd("douyin-店B", "7ca0", "前台-店B", "前台-店B")]
    qa = [_qa("douyin-店B", "q1", "飞鸽客服应答001", "7ca0")]
    assert plan_qa_rewire(fds, qa, {"douyin-店B": "店B"}) == []


def test_shared_pool_qa_is_skipped():
    # A comma list = a shared Q&A pool; re-pointing would need a human.
    fds = [_fd("douyin-店B", "7ca0", "前台-店B", "前台-店B")]
    qa = [_qa("douyin-店B", "q1", "飞鸽客服应答共享001", "7ca0,1c11")]
    assert plan_qa_rewire(fds, qa, {"douyin-店B": "店B"}) == []


def test_ambiguous_store_qa_is_skipped():
    # Two generic front desks, no store-scoped one → live FD unresolvable → skip.
    fds = [_fd("douyin-店C", "a1", "前台小张", "飞鸽客服前台001"),
           _fd("douyin-店C", "a2", "前台小李", "飞鸽客服前台002")]
    qa = [_qa("douyin-店C", "q1", "飞鸽客服应答001", "dead")]
    assert plan_qa_rewire(fds, qa, {"douyin-店C": "店C"}) == []
