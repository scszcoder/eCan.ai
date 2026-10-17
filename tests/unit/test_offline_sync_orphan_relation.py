"""Relationship ADDs whose parent is gone must not retry forever.

Customer run 2026-10-17 (build yao, CN/TCB): besides the agent.delete loop
fixed in e9abfa650, 4× agent_skill.add ("Skill not found") + 4× agent_task.add
("Agent not found") retried every auto-retry tick. On CN the backend reports a
missing parent as a plain GraphQL "Agent/Skill not found" — not the AWS
"foreign key constraint fails" text the parent-sync path keyed on — so these
fell through to a blind retry.

Fix: treat CN "not found" on a relationship row like an FK miss; then
  - parent deleted locally too  -> orphaned relation, discard (terminal);
  - parent still exists locally -> sync the parent first, retry the child.
"""
import agent.cloud_api.offline_sync_manager as osm_mod
from agent.cloud_api.constants import DataType


class _FakeQueue:
    def __init__(self, task):
        self.task = dict(task)
        self.succeeded, self.failed = [], []

    def get_pending_tasks(self, *a, **k):
        return [] if self.task is None else [dict(self.task)]

    def get_failed_tasks(self):
        return []

    def mark_success(self, tid):
        self.succeeded.append(tid)
        self.task = None

    def mark_failed(self, tid, err, max_retries=3, non_retryable=False):
        self.failed.append(tid)
        self.task = None


def _manager(queue, parent_exists):
    osm = osm_mod.OfflineSyncManager.__new__(osm_mod.OfflineSyncManager)
    osm.sync_queue = queue
    osm._session_state = "active"
    osm._sort_tasks_by_dependency = lambda tasks: tasks
    osm._parent_exists_locally = lambda dep, data: parent_exists
    return osm


def _run(osm, monkeypatch, service):
    monkeypatch.setattr(osm_mod, "get_cloud_service", lambda dt: service)
    return osm.sync_pending_queue(max_tasks=10, include_failed=False)


def test_cn_not_found_recognised_for_relationships_only():
    osm = osm_mod.OfflineSyncManager.__new__(osm_mod.OfflineSyncManager)
    fk = osm._check_foreign_key_error(["GraphQL Error: Agent not found"], "agent_task")
    assert fk and fk["dependency_type"] == DataType.AGENT
    fk = osm._check_foreign_key_error(["Skill not found"], "agent_skill")
    assert fk and fk["dependency_type"] == DataType.SKILL
    # Entities are not relationships: no parent to sync.
    assert osm._check_foreign_key_error(["Agent not found"], "agent") is None
    # Unrelated error stays unrecognised.
    assert osm._check_foreign_key_error(["Connection timed out"], "agent_task") is None


def test_orphan_relation_is_discarded_after_one_call(monkeypatch):
    calls = []

    class _Svc:
        def sync_to_cloud(self, items, operation=None, timeout=None):
            calls.append((operation, items[0]))
            return {"success": False, "errors": ["Agent not found"]}

    q = _FakeQueue({"id": "agent_task_add_1", "data_type": "agent_task",
                    "operation": "add", "data": {"agid": "agent_gone", "task_id": "t1"}})
    result = _run(_manager(q, parent_exists=False), monkeypatch, _Svc())

    assert q.succeeded == ["agent_task_add_1"] and not q.failed
    assert len(calls) == 1          # no parent ADD, no retry
    assert result["synced"] == 1


def test_parent_present_locally_syncs_parent_then_child(monkeypatch):
    calls = []

    class _Svc:
        def sync_to_cloud(self, items, operation=None, timeout=None):
            calls.append((str(operation), items[0].get("id") or items[0].get("skid")))
            # 1st: child fails (skill missing in cloud); 2nd: parent ADD ok; 3rd: child ok
            if len(calls) == 1:
                return {"success": False, "errors": ["Skill not found"]}
            return {"success": True, "errors": []}

    q = _FakeQueue({"id": "agent_skill_add_1", "data_type": "agent_skill",
                    "operation": "add", "data": {"agid": "a1", "skid": "sk1"}})
    osm = _manager(q, parent_exists=True)
    osm._extract_parent_data = lambda data, dep, ctype, task: {"id": "sk1", "name": "real skill"}
    _run(osm, monkeypatch, _Svc())

    assert [c[0] for c in calls] == ["add", "add", "add"]   # child, parent, child retry
    assert calls[1][1] == "sk1"
    assert q.succeeded == ["agent_skill_add_1"]


def test_unknown_parent_state_does_not_discard(monkeypatch):
    # Lookup inconclusive (None) -> never discard; fall through to parent sync.
    class _Svc:
        def sync_to_cloud(self, items, operation=None, timeout=None):
            return {"success": False, "errors": ["Agent not found"]}

    q = _FakeQueue({"id": "agent_task_add_2", "data_type": "agent_task",
                    "operation": "add", "data": {"agid": "a2"}})
    osm = _manager(q, parent_exists=None)
    osm._extract_parent_data = lambda *a: None
    _run(osm, monkeypatch, _Svc())

    assert q.succeeded == [] and q.failed == ["agent_task_add_2"]
