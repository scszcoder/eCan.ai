"""The app and the CLI share offline_sync_queue/*.json. A save must keep what
the other process queued, and must not resurrect what this process removed.

2026-10-08: the CLI queued 8 agent/task items while the app was running; the
app's next save rewrote the file from its in-memory list and they were lost."""
import json

from agent.cloud_api.offline_sync_queue import OfflineSyncQueue


def test_a_save_keeps_tasks_another_process_queued(tmp_path):
    app, cli = OfflineSyncQueue(tmp_path), OfflineSyncQueue(tmp_path)
    a = app.add("skill", {"id": "skill_1"})
    c1 = cli.add("task", {"id": "task_1"})
    c2 = cli.add("agent", {"id": "agent_1"})
    app.mark_failed(a, "backend down")                     # app saves from its own memory
    ids = {t["id"] for t in json.loads((tmp_path / "pending_sync.json").read_text(encoding="utf-8"))}
    assert {a, c1, c2} <= ids


def test_the_app_syncs_what_the_cli_queued_without_a_restart(tmp_path):
    app, cli = OfflineSyncQueue(tmp_path), OfflineSyncQueue(tmp_path)
    c = cli.add("task", {"id": "task_1"})
    assert [t["id"] for t in app.get_pending_tasks()] == [c]


def test_a_synced_task_is_not_brought_back_by_a_merge(tmp_path):
    app, cli = OfflineSyncQueue(tmp_path), OfflineSyncQueue(tmp_path)
    c = cli.add("task", {"id": "task_1"})
    app.get_pending_tasks()
    app.mark_success(c)                                    # app synced it
    cli.add("agent", {"id": "agent_1"})                    # cli still had it in memory
    pending = [t["id"] for t in app.get_pending_tasks()]
    assert c not in pending and len(pending) == 1


def test_ids_are_unique_across_processes_in_the_same_millisecond(tmp_path):
    q1, q2 = OfflineSyncQueue(tmp_path), OfflineSyncQueue(tmp_path)
    ids = [q1.add("task", {"id": str(i)}) for i in range(20)] + [q2.add("task", {"id": "x"})]
    assert len(set(ids)) == len(ids)


def test_removing_a_resource_drops_what_the_cli_queued_for_it(tmp_path):
    # 2026-10-11: the CLI queued an agent add; the app deleted the agent (and
    # cleared its own queue for it); the merged-in stale add re-created it.
    app, cli = OfflineSyncQueue(tmp_path), OfflineSyncQueue(tmp_path)
    app.get_pending_tasks()
    cli.add("agent", {"id": "agent_1"})
    assert app.remove_tasks_by_resource("agent", "agent_1") == 1
    assert app.get_pending_tasks() == []
    cli.add("task", {"id": "task_9"})                       # cli saves again from its memory
    assert [t["data"]["id"] for t in app.get_pending_tasks()] == ["task_9"]
