"""A fresh machine (e.g. a new Platoon) fills its own database from the cloud copy."""

import asyncio
import json
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
                          fetch_cloud_task_skill_links=lambda ctx: ts,
                          hydrate_prompts=lambda: {"added": []},
                          hydrate_skill_files=lambda ctx: {"downloaded": []})


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
    with _cloud():
        ch.hydrate_local_db_from_cloud(mainwin)          # what MainWindow does first
    with patch.object(cat, "_build_local_agent_tasks_async", new=lambda mw: _noop()):
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


class TestFilesAFreshMachineNeeds:
    def test_missing_prompts_written_and_newer_cloud_copies_refresh_older_ones(self):
        """Newer-wins: a prompt with no local file is added; an existing local
        prompt is refreshed only when the cloud copy is strictly newer by its
        own lastModified. Equal or older cloud copies are left alone (no churn)."""
        written = []
        cloud = [
            {"id": "pr-1", "title": "a", "lastModified": "2026-01-01T00:00:00"},  # equal  -> skip
            {"id": "pr-2", "title": "b", "lastModified": "2026-01-01T00:00:00"},  # missing-> add
            {"id": "pr-3", "title": "c", "lastModified": "2026-02-01T00:00:00"},  # newer  -> update
            {"id": "pr-4", "title": "d", "lastModified": "2025-01-01T00:00:00"},  # older  -> skip
        ]
        local = {"pr-1": "2026-01-01T00:00:00",
                 "pr-3": "2026-01-15T00:00:00",
                 "pr-4": "2026-06-01T00:00:00"}
        with patch("gui.ipc.w2p_handlers.prompt_cloud_sync.fetch_cloud_prompts", return_value=cloud), \
             patch.object(ch, "_local_prompt_content_times", return_value=dict(local)), \
             patch.object(ch, "_restore_prompt_last_modified", lambda *a, **k: None), \
             patch("gui.ipc.w2p_handlers.prompt_handler._write_prompt_to_file",
                   side_effect=lambda p: written.append(p["id"]) or p):
            out = ch.hydrate_prompts()
        assert out == {"added": ["pr-2"], "updated": ["pr-3"]}
        assert written == ["pr-2", "pr-3"]

    def test_only_own_skills_without_a_folder_are_downloaded(self, tmp_path):
        have = tmp_path / "有_skill"
        have.mkdir()
        rows = [{"id": "s1", "name": "有"}, {"id": "s2", "name": "缺"},
                {"id": "s3", "name": "租", "source": "subscribed"},
                {"id": "s4", "name": "外", "source": "external"}]
        fetched = []

        def resolve(sk):
            p = tmp_path / f"{sk['name']}_skill"
            return p if p.is_dir() else None

        def download(sk, **kw):
            fetched.append(sk["name"])
            (tmp_path / f"{sk['name']}_skill").mkdir()

        with patch("agent.cloud_api.cloud_api.send_get_agent_skills_request_to_cloud", return_value=rows), \
             patch("gui.ipc.w2p_handlers.skill_file_sync._resolve_skill_dir", side_effect=resolve), \
             patch("gui.ipc.w2p_handlers.skill_file_sync.download_skill_files_from_cloud", side_effect=download):
            out = ch.hydrate_skill_files(("s", "t", "e"), wait_s=5)
        # 有 exists with no version JSON (legacy/un-versioned) -> left alone;
        # 缺 is missing -> downloaded; subscribed/external -> ignored.
        assert fetched == ["缺"]
        assert out == {"downloaded": ["缺"], "updated": [], "backed_up": [], "missing": []}

    def test_a_newer_cloud_version_refreshes_a_timestamped_folder_after_backup(self, tmp_path):
        """An own skill already on the save-timestamp scheme is refreshed when
        the cloud version is strictly newer, and its folder is backed up first."""
        from utils.skill_version import new_skill_version
        have = tmp_path / "有_skill"
        have.mkdir()
        (have / "marker.txt").write_text("local work", encoding="utf-8")
        local_v = "250101000000000"           # old timestamp version
        cloud_v = new_skill_version(local_v)   # strictly newer timestamp
        rows = [{"id": "s1", "name": "有", "version": cloud_v}]
        fetched = []

        def resolve(sk):
            p = tmp_path / f"{sk['name']}_skill"
            return p if p.is_dir() else None

        def download(sk, **kw):
            fetched.append(sk["name"])

        with patch("agent.cloud_api.cloud_api.send_get_agent_skills_request_to_cloud", return_value=rows), \
             patch("gui.ipc.w2p_handlers.skill_file_sync._resolve_skill_dir", side_effect=resolve), \
             patch("gui.ipc.w2p_handlers.skill_file_sync.download_skill_files_from_cloud", side_effect=download), \
             patch.object(ch, "_local_skill_version", return_value=local_v):
            out = ch.hydrate_skill_files(("s", "t", "e"), wait_s=5)
        assert fetched == ["有"]
        assert out["downloaded"] == [] and out["updated"] == ["有"]
        assert len(out["backed_up"]) == 1
        backups = [p for p in tmp_path.iterdir() if p.name.startswith("有_skill.bak-")]
        assert len(backups) == 1 and (backups[0] / "marker.txt").read_text(encoding="utf-8") == "local work"

    def test_a_legacy_versioned_own_skill_is_never_auto_overwritten(self, tmp_path):
        """A local skill on a legacy version ("1.0.0") is left alone even when
        the cloud has a timestamp version that sorts newer -- it may be an
        actively-edited working copy, so we never clobber it on startup."""
        have = tmp_path / "有_skill"
        have.mkdir()
        rows = [{"id": "s1", "name": "有", "version": "250101000000000"}]
        fetched = []

        def resolve(sk):
            p = tmp_path / f"{sk['name']}_skill"
            return p if p.is_dir() else None

        with patch("agent.cloud_api.cloud_api.send_get_agent_skills_request_to_cloud", return_value=rows), \
             patch("gui.ipc.w2p_handlers.skill_file_sync._resolve_skill_dir", side_effect=resolve), \
             patch("gui.ipc.w2p_handlers.skill_file_sync.download_skill_files_from_cloud",
                   side_effect=lambda sk, **kw: fetched.append(sk["name"])), \
             patch.object(ch, "_local_skill_version", return_value="1.0.0"):
            out = ch.hydrate_skill_files(("s", "t", "e"), wait_s=5)
        assert fetched == [] and out == {"downloaded": [], "updated": [], "backed_up": []}
        assert not any(p.name.startswith("有_skill.bak-") for p in tmp_path.iterdir())


def test_from_cloud_keeps_required_fields():
    """cloud_required_fields are defaults for to_cloud; from_cloud must keep
    them (2026-10-09: task `name` was dropped, so hydrate stored no tasks)."""
    from agent.cloud_api.schema_registry import get_schema_registry
    from agent.cloud_api.constants import DataType
    t = get_schema_registry().get_schema(DataType.TASK).from_cloud(
        {"id": "task_1", "name": "chip_docs_crawl_1", "trigger_type": "message"})
    assert t["id"] == "task_1" and t["name"] == "chip_docs_crawl_1"


# ── a skill whose files archive never uploaded is rebuilt from its record ──

def _record(**kw):
    rec = {"id": "skill_1", "name": "amazon_after_sales", "source": "ui", "version": "1.0.0",
           "description": "d", "owner": "o@example.com",
           "diagram": json.dumps({"nodes": [{"id": "start_0", "type": "start"}], "edges": []}),
           "config": json.dumps({"run_mode": "developing", "skill_mapping": {"event_data_mapping": {"x": 1}}})}
    rec.update(kw)
    return rec


def test_a_ui_skill_is_rebuilt_from_its_record(tmp_path):
    from agent.ec_agents.cloud_hydrate import _materialize_from_record
    root = _materialize_from_record(_record(), tmp_path)
    core = json.loads((root / "diagram_dir" / "amazon_after_sales_skill.json").read_text(encoding="utf-8"))
    assert root.name == "amazon_after_sales_skill"
    assert core["skillId"] == "skill_1" and core["workFlow"]["nodes"][0]["type"] == "start"
    assert core["run_mode"] == "developing"
    mapping = json.loads((root / "data_mapping.json").read_text(encoding="utf-8"))
    assert mapping["event_data_mapping"] == {"x": 1} and "released" in mapping


def test_code_skills_and_existing_folders_are_left_alone(tmp_path):
    from agent.ec_agents.cloud_hydrate import _materialize_from_record
    assert _materialize_from_record(_record(source="code"), tmp_path) is None
    assert _materialize_from_record(_record(diagram=""), tmp_path) is None
    (tmp_path / "amazon_after_sales_skill").mkdir()
    assert _materialize_from_record(_record(), tmp_path) is None
