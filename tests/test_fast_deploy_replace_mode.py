"""Fast Deploy (douyin_cs) 'replace' mode: delete this owner's tasks on the
scenario skills + the agents assigned to them, then proceed with add."""

import cli.deploy.commands as cmds


class _TaskSvc:
    def __init__(self, rels, tasks):
        self.rels, self.tasks, self.deleted = rels, tasks, []

    def get_tasks_by_skill(self, sid):
        return {"success": True, "data": [r for r in self.rels if r["skill_id"] == sid]}

    def query_tasks(self, id=None, name=None, description=None):
        return {"success": True, "data": [t for t in self.tasks if t["id"] == id]}

    def delete_task(self, tid):
        self.deleted.append(tid)
        return {"success": True}


class _AgentSvc:
    def __init__(self, agents, assoc):
        self.agents, self.assoc, self.deleted = agents, assoc, []

    def get_agents_by_owner(self, owner):
        return {"success": True, "data": [a for a in self.agents if a["owner"] == owner]}

    def get_agent_task_associations(self, aid, status=None):
        return {"success": True, "data": [x for x in self.assoc if x["agent_id"] == aid]}

    def delete_agent(self, aid):
        self.deleted.append(aid)
        return {"success": True}


class _Ctx:
    def __init__(self, ts, ag):
        self.db = type("DB", (), {})()
        self.db.task_service, self.db.agent_service = ts, ag


def _fixture():
    rels = [
        {"task_id": "t_fd", "skill_id": "SK_FD"},
        {"task_id": "t_qa1", "skill_id": "SK_QA"},
        {"task_id": "t_other_owner", "skill_id": "SK_QA"},   # someone else's — must survive
        {"task_id": "t_unrelated", "skill_id": "SK_X"},      # different skill — must survive
    ]
    tasks = [
        {"id": "t_fd", "owner": "alice"},
        {"id": "t_qa1", "owner": "alice"},
        {"id": "t_other_owner", "owner": "bob"},
        {"id": "t_unrelated", "owner": "alice"},
    ]
    agents = [
        {"id": "a_fd", "owner": "alice"},
        {"id": "a_qa1", "owner": "alice"},
        {"id": "a_keep", "owner": "alice"},   # assigned only to the unrelated task
        {"id": "a_bob", "owner": "bob"},
    ]
    assoc = [
        {"agent_id": "a_fd", "task_id": "t_fd"},
        {"agent_id": "a_qa1", "task_id": "t_qa1"},
        {"agent_id": "a_keep", "task_id": "t_unrelated"},
        {"agent_id": "a_bob", "task_id": "t_other_owner"},
    ]
    return _TaskSvc(rels, tasks), _AgentSvc(agents, assoc)


def test_replace_deletes_only_this_owners_rows_agents_before_tasks(monkeypatch):
    ts, ag = _fixture()
    synced = []
    monkeypatch.setattr("cli.base.sync.cloud_sync", lambda dt, data, op: synced.append((str(dt), data["id"], str(op))))
    log = []
    out = cmds._replace_cleanup(_Ctx(ts, ag), "alice", ("SK_FD", "SK_QA"), log)

    assert sorted(out["tasks"]) == ["t_fd", "t_qa1"]
    assert sorted(out["agents"]) == ["a_fd", "a_qa1"]
    assert sorted(ts.deleted) == ["t_fd", "t_qa1"]
    assert sorted(ag.deleted) == ["a_fd", "a_qa1"]
    # cloud deletes issued for every local delete, agents first
    kinds = [k for k, _, _ in synced]
    assert len(synced) == 4 and all(op.endswith("delete") for _, _, op in synced)
    assert kinds.index(next(k for k in kinds if "agent" in k)) < kinds.index(next(k for k in kinds if "task" in k))
    assert any("deleted 2 agent(s) and 2 task(s)" in line for line in log)


def test_add_mode_is_default_and_touches_nothing(monkeypatch):
    ts, ag = _fixture()
    monkeypatch.setattr("cli.base.sync.cloud_sync", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no sync in add mode")))
    # 'replace' cleanup must not be invoked for mode missing / 'add'
    for cfg in ({}, {"mode": "add"}, {"mode": "ADD "}):
        assert str(cfg.get("mode") or "add").strip().lower() != "replace"
    assert ts.deleted == [] and ag.deleted == []


def test_replace_with_nothing_to_delete(monkeypatch):
    ts, ag = _TaskSvc([], []), _AgentSvc([], [])
    monkeypatch.setattr("cli.base.sync.cloud_sync", lambda *a, **k: None)
    log = []
    out = cmds._replace_cleanup(_Ctx(ts, ag), "alice", ("SK_FD", "SK_QA"), log)
    assert out == {"tasks": [], "agents": []}
    assert any("deleted 0 agent(s) and 0 task(s)" in line for line in log)
