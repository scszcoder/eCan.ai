"""A fresh machine (e.g. a new Platoon) fills its own database from the cloud copy."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.db.ec_db_mgr import initialize_ecan_database
from agent.ec_agents import cloud_hydrate as ch

USER = "wechat_o3YB"


@pytest.fixture
def mainwin(tmp_path):
    db = initialize_ecan_database(str(tmp_path), auto_migrate=True)
    return SimpleNamespace(ec_db_mgr=db, user=USER, agent_skills=[], agent_tasks=[],
                           get_auth_token=lambda: "tok", getWanApiEndpoint=lambda: "https://x")


CLOUD_AGENTS = [{"id": "agent_fd", "name": "前台-店A", "owner": "o3YB", "vehicle_id": "veh-platoon"}]
CLOUD_TASKS = [{"id": "task_fd", "name": "飞鸽客服前台-店A", "owner": "o3YB", "priority": "mid",
                "description": None, "source": None,            # the cloud sends nulls
                "metadata": '{"task_vars": {"store_id": "douyin-店A"}}',
                "updated_at": "2026-09-25T10:00:00Z"}]
AT_LINKS = [{"agent_id": "agent_fd", "task_id": "task_fd"}]
TS_LINKS = [{"task_id": "task_fd", "skill_id": "skill_fd"}]


def _cloud(agents=CLOUD_AGENTS, tasks=CLOUD_TASKS, at=AT_LINKS, ts=TS_LINKS):
    return patch.multiple(ch, fetch_cloud_agents=lambda ctx: agents, fetch_cloud_tasks=lambda ctx: tasks,
                          fetch_cloud_agent_task_links=lambda ctx: at,
                          fetch_cloud_task_skill_links=lambda ctx: ts)


def test_an_empty_machine_gets_the_accounts_agents_tasks_and_links(mainwin):
    with _cloud():
        out = ch.hydrate_local_db_from_cloud(mainwin)
    assert out["ok"] and out["agents_added"] == 1 and out["tasks"]["added"] == 1
    db = mainwin.ec_db_mgr
    task = db.task_service.query_tasks(id="task_fd")["data"][0]
    assert task["owner"] == USER, "rows belong to this machine's user so its loaders see them"
    assert task["metadata"]["task_vars"]["store_id"] == "douyin-店A"
    assert [r["skill_id"] for r in db.task_service.get_task_skills("task_fd")["data"]] == ["skill_fd"]
    agents = db.agent_service.get_agents_by_owner(USER)["data"]
    assert [t["id"] for t in agents[0]["tasks"]] == ["task_fd"], "the agent finds its task locally"


def test_running_it_twice_changes_nothing(mainwin):
    with _cloud():
        ch.hydrate_local_db_from_cloud(mainwin)
        again = ch.hydrate_local_db_from_cloud(mainwin)
    assert again["agents_added"] == 0 and again["tasks"] == {"added": 0, "updated": 0, "updated_ids": []}
    assert again["agent_task_links_added"] == [] and again["task_skill_links_added"] == []


def test_a_newer_cloud_copy_updates_an_older_local_one_never_the_reverse(mainwin):
    with _cloud():
        ch.hydrate_local_db_from_cloud(mainwin)
    svc = mainwin.ec_db_mgr.task_service
    later = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    with _cloud(tasks=[dict(CLOUD_TASKS[0], name="renamed on the Commander", updated_at=later)]):
        out = ch.hydrate_local_db_from_cloud(mainwin)
    assert out["tasks"]["updated_ids"] == ["task_fd"]
    assert svc.query_tasks(id="task_fd")["data"][0]["name"] == "renamed on the Commander"
    # an OLDER cloud copy leaves the local edit alone
    svc.update_task("task_fd", {"name": "edited here"})
    with _cloud(tasks=[dict(CLOUD_TASKS[0], name="stale", updated_at="2020-01-01T00:00:00Z")]):
        ch.hydrate_local_db_from_cloud(mainwin)
    assert svc.query_tasks(id="task_fd")["data"][0]["name"] == "edited here"


def test_an_unreachable_cloud_leaves_the_local_database_as_it_is(mainwin):
    with _cloud(agents=None, tasks=None, at=None, ts=None):
        out = ch.hydrate_local_db_from_cloud(mainwin)
    assert out["ok"] and out["cloud"] == {"agents": None, "tasks": None,
                                          "agent_task_links": None, "task_skill_links": None}
    assert mainwin.ec_db_mgr.task_service.query_tasks()["data"] == []


def test_startup_builds_the_hydrated_task_from_the_local_database(mainwin):
    from agent.ec_agents import create_agent_tasks as cat
    with _cloud(), patch.object(cat, "_build_local_agent_tasks_async", new=lambda mw: _noop()):
        tasks = asyncio.run(cat.build_agent_tasks(mainwin))
    assert "飞鸽客服前台-店A" in [t.name for t in tasks]


async def _noop():
    return []


class TestRefreshWithoutRestart:
    def _app(self, mainwin, running_agents=(), tasks=()):
        launched = []
        mainwin.agents = list(running_agents)
        mainwin.agent_tasks = list(tasks)
        mainwin._launch_agents_async = lambda agents: launched.extend(agents)
        return launched

    def test_new_agents_and_tasks_join_the_running_app(self, mainwin):
        from gui.ipc.w2p_handlers import cloud_refresh_handler as h
        launched = self._app(mainwin)
        with _cloud():
            hydrated = ch.hydrate_local_db_from_cloud(mainwin)
        built = SimpleNamespace(card=SimpleNamespace(id="agent_fd", name="前台-店A"))
        with patch("agent.agent_converter.convert_agent_dict_to_ec_agent", return_value=built):
            out = asyncio.run(h._apply_in_app(mainwin, hydrated))
        assert out["agents_added"] == ["前台-店A"] and launched == [built]
        assert out["tasks_added"] == ["飞鸽客服前台-店A"]
        assert any("skill is not loaded" in n for n in out["needs_restart"])   # skill_fd not compiled here

    def test_what_a_running_agent_cannot_take_is_reported_not_forced(self, mainwin):
        from gui.ipc.w2p_handlers import cloud_refresh_handler as h
        running = SimpleNamespace(card=SimpleNamespace(id="agent_fd", name="前台-店A"))
        task = SimpleNamespace(id="task_fd", name="飞鸽客服前台-店A", skill=object())
        launched = self._app(mainwin, [running], [task])
        with _cloud():
            hydrated = ch.hydrate_local_db_from_cloud(mainwin)   # adds the link for the running agent
        out = asyncio.run(h._apply_in_app(mainwin, hydrated))
        assert out["agents_added"] == [] and launched == []
        assert any("agent_fd got task" in n for n in out["needs_restart"])
