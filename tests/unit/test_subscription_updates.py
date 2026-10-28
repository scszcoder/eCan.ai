"""Subscribed skills/prompts auto-update (2026-10-10).

Power-up refreshes prompts too; a 30-min background check applies updates to
idle skills and leaves the rest as a reminder. "Idle" looks at every task on
the skill: status, pending async events, queued messages and its schedule.
"""
from datetime import datetime, timedelta
from queue import Queue
from types import SimpleNamespace

import pytest
from a2a.types import TaskState

import gui.ipc.w2p_handlers.subscription_update_handler as su
from agent.ec_tasks.models import PendingEventStatus, RepeatType


def _task(state=TaskState.completed, name="t", skill=None, **kw):
    return SimpleNamespace(name=name, skill=skill, status=SimpleNamespace(state=state),
                           pending_events=kw.get("pending", {}), queue=kw.get("queue"),
                           schedule=kw.get("schedule"), trigger=kw.get("trigger", []))


def _sched(next_in_s=None, repeat=RepeatType.BY_MINUTES):
    return SimpleNamespace(repeat_type=repeat, next_in_s=next_in_s)


@pytest.fixture
def fake_next_runtime(monkeypatch):
    import agent.ec_tasks.scheduler as sch
    def nxt(schedule):
        when = datetime.now() + timedelta(seconds=schedule.next_in_s)
        return when, schedule.next_in_s <= 0
    monkeypatch.setattr(sch, "get_next_runtime", nxt)


class TestIdle:
    def test_running_or_waiting_for_input_is_busy(self):
        assert "working" in su._task_busy_reason(_task(TaskState.working))
        assert "input-required" in su._task_busy_reason(_task(TaskState.input_required))
        assert su._task_busy_reason(_task(TaskState.completed)) == ""

    def test_pending_async_event_is_busy(self):
        ev = SimpleNamespace(status=PendingEventStatus.PENDING)
        assert "async event" in su._task_busy_reason(_task(pending={"e": ev}))
        done = SimpleNamespace(status=PendingEventStatus.COMPLETED)
        assert su._task_busy_reason(_task(pending={"e": done})) == ""

    def test_queued_message_is_busy(self):
        q = Queue()
        q.put("hi")
        assert "queued" in su._task_busy_reason(_task(queue=q, trigger=["message"]))
        assert su._task_busy_reason(_task(queue=Queue(), trigger=["message"])) == ""

    def test_schedule_due_soon_is_busy(self, fake_next_runtime):
        assert "scheduled" in su._task_busy_reason(_task(schedule=_sched(60), trigger=["schedule"]))
        assert "scheduled" in su._task_busy_reason(_task(schedule=_sched(0), trigger=["schedule"]))
        assert su._task_busy_reason(_task(schedule=_sched(3600), trigger=["schedule"])) == ""

    def test_schedule_ignored_when_not_schedule_triggered_or_never_repeats(self, fake_next_runtime):
        assert su._task_busy_reason(_task(schedule=_sched(60), trigger=["message"])) == ""
        assert su._task_busy_reason(_task(schedule=_sched(60, RepeatType.NONE), trigger=["schedule"])) == ""

    def test_skill_busy_checks_agent_and_runner_tasks(self):
        sk = SimpleNamespace(id="s1", name="front")
        idle = _task(skill=sk, name="a")
        running = _task(TaskState.working, skill=sk, name="b")
        agent = SimpleNamespace(tasks=[idle], runner=SimpleNamespace(tasks={"b": running}))
        mw = SimpleNamespace(agents=[agent])
        assert "task 'b'" in su.skill_busy_reason(mw, "s1", "front")
        assert su.skill_busy_reason(mw, "other", "other") == ""


class TestBackgroundCheck:
    @pytest.fixture(autouse=True)
    def _reset(self):
        su._state.update(items=[], running=False, next_check=0.0, checked_at=0.0)
        yield
        su._state.update(items=[], running=False, next_check=0.0)

    def test_idle_skill_updates_busy_skill_waits(self, monkeypatch):
        items = [{"skill_id": "s1", "name": "idle", "skill_newer": True, "prompts": []},
                 {"skill_id": "s2", "name": "busy", "skill_newer": False, "prompts": ["pr-1"]}]
        monkeypatch.setattr(su, "check_subscribed_updates", lambda mw: list(items))
        monkeypatch.setattr(su, "skill_busy_reason", lambda mw, sid, n: "task 'x': status working" if sid == "s2" else "")
        applied, pushed = [], []
        monkeypatch.setattr(su, "apply_update", lambda mw, it: applied.append(it["skill_id"]) or {"ok": True})
        monkeypatch.setattr(su, "_push", lambda items, applied: pushed.append((items, applied)))
        out = su.run_background_check(object())
        assert applied == ["s1"]
        assert [i["skill_id"] for i in out["items"]] == ["s2"] and out["items"][0]["busy"]
        assert pushed and pushed[0][1][0]["skill_id"] == "s1"
        assert not su.background_check_due()            # next check one interval later

    def test_failed_apply_stays_as_reminder(self, monkeypatch):
        monkeypatch.setattr(su, "check_subscribed_updates",
                            lambda mw: [{"skill_id": "s1", "name": "x", "skill_newer": True, "prompts": []}])
        monkeypatch.setattr(su, "skill_busy_reason", lambda *a: "")
        monkeypatch.setattr(su, "apply_update", lambda mw, it: {"ok": False, "error": "offline"})
        monkeypatch.setattr(su, "_push", lambda *a: None)
        out = su.run_background_check(object())
        assert out["items"][0]["error"] == "offline" and not out["applied"]

    def test_overlapping_checks_are_skipped(self):
        su._state["running"] = True
        assert su.run_background_check(object()) == {"skipped": "check already running"}


class TestPromptCompare:
    def test_changed_prompts_compares_author_copy_with_subscribed_copy(self, monkeypatch):
        cloud = {"pr-1": {"id": "pr-1", "text": "v2"}, "pr-2": {"id": "pr-2", "text": "same"}, "pr-3": {"id": "pr-3"}}
        local = {"pr-1": {"id": "pr-1", "text": "v1"}, "pr-2": {"text": "same", "id": "pr-2"}}
        monkeypatch.setattr(su, "_prompt_ids", lambda row: ["pr-1", "pr-2", "pr-3"])
        monkeypatch.setattr(su, "_cloud_prompt", lambda ctx, pid, author: cloud.get(pid))
        monkeypatch.setattr(su, "_local_subscribed_prompt", lambda pid: local.get(pid))
        # pr-1 differs, pr-2 is the same (key order ignored), pr-3 is missing locally
        assert su._changed_prompts({}, {"owner": "author"}) == ["pr-1", "pr-3"]


def test_a_wechat_authors_own_skills_are_not_subscriptions(monkeypatch):
    # 2026-10-22: "me" is the bare openid; the author's rows say wechat_<openid>
    # (and ...@local). They were taken for subscriptions and their prompts were
    # overwritten into subscribed_prompts.
    import types
    from gui.ipc.w2p_handlers import subscription_update_handler as su
    oid = "o3YBk2dxaRe3LKqJXCf5z3PfvD5M"
    rows = [{"id": "a", "owner": f"wechat_{oid}"}, {"id": "b", "owner": f"wechat_{oid}@local"},
            {"id": "c", "owner": oid}, {"id": "d", "owner": "another_author"}]
    svc = types.SimpleNamespace(query_skills=lambda: {"success": True, "data": rows})
    mainwin = types.SimpleNamespace(ec_db_mgr=types.SimpleNamespace(skill_service=svc), user="")
    monkeypatch.setattr(su, "_me", lambda mw: oid)
    assert [r["id"] for r in su._subscribed_rows(mainwin)] == ["d"]
