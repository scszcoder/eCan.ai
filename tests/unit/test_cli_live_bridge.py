"""The CLI talking to the running app: discovery file, client, live commands,
and task edits routed through the app."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from utils import local_api


# ── discovery file + key ─────────────────────────────────────────────────────

@pytest.fixture
def api_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(local_api, "_folder", lambda: str(tmp_path / "local_api"))
    monkeypatch.delenv("ECAN_LOCAL_API", raising=False)
    yield tmp_path / "local_api"
    local_api._secret = None


def test_publish_find_withdraw(api_dir):
    secret = local_api.publish(5123)
    info = local_api.find_running()
    assert info["port"] == 5123 and info["secret"] == secret and info["pid"] == os.getpid()
    assert local_api.is_local_secret(secret)
    assert not local_api.is_local_secret("x" + secret)
    assert not local_api.is_local_secret(None)
    local_api.withdraw()
    assert local_api.find_running() is None
    assert not local_api.is_local_secret(secret)


def test_new_start_new_secret(api_dir):
    first = local_api.publish(5123)
    second = local_api.publish(5123)
    assert first != second
    assert not local_api.is_local_secret(first) and local_api.is_local_secret(second)


def test_dead_process_is_not_running(api_dir):
    local_api.publish(5123)
    with patch.object(local_api, "_alive", return_value=False):
        assert local_api.find_running() is None


def test_withdraw_leaves_another_process_file(api_dir):
    local_api.publish(5123)
    path = local_api.discovery_path()
    data = json.load(open(path, encoding="utf-8"))
    data["pid"] = data["pid"] + 1
    json.dump(data, open(path, "w", encoding="utf-8"))
    local_api.withdraw()
    assert os.path.exists(path)


def test_kill_switch(api_dir, monkeypatch):
    monkeypatch.setenv("ECAN_LOCAL_API", "0")
    assert local_api.publish(5123) is None
    assert local_api.find_running() is None


# ── client ───────────────────────────────────────────────────────────────────

def _resp(body, status=200):
    r = MagicMock(status_code=status)
    r.json.return_value = body
    return r


def test_call_success_and_error():
    from cli.base import app_client
    with patch.object(app_client, "find_app", return_value={"port": 5001, "secret": "s"}), \
         patch("requests.post", return_value=_resp({"data": {"get_agent_pools": {"pools": {}}}})) as post:
        assert app_client.call("get_agent_pools") == {"pools": {}}
        kw = post.call_args.kwargs
        assert post.call_args.args[0] == "http://127.0.0.1:5001/graphql"
        assert kw["json"]["extensions"] == {"method": "get_agent_pools"}
        assert kw["headers"]["Authorization"] == "Bearer s"
    err = {"errors": [{"message": "no pool", "extensions": {"code": "POOL_NOT_FOUND"}}]}
    with patch.object(app_client, "find_app", return_value={"port": 5001, "secret": "s"}), \
         patch("requests.post", return_value=_resp(err)):
        with pytest.raises(app_client.AppCallError) as e:
            app_client.call("set_agent_pool_pin", {"agent_id": "x", "size": 2})
        assert e.value.code == "POOL_NOT_FOUND"


def test_call_not_running():
    import requests
    from cli.base import app_client
    with patch.object(app_client, "find_app", return_value=None):
        with pytest.raises(app_client.AppNotRunning):
            app_client.call("get_agent_pools")
    with patch.object(app_client, "find_app", return_value={"port": 5001, "secret": "s"}), \
         patch("requests.post", side_effect=requests.exceptions.ConnectionError()):
        with pytest.raises(app_client.AppNotRunning):
            app_client.call("get_agent_pools")


def test_same_user():
    from cli.base import app_client
    with patch.object(app_client, "call", return_value={"username": "Me@x.com"}):
        assert app_client.same_user("me@x.com")
        assert not app_client.same_user("other@x.com")
        assert not app_client.same_user(None)
    with patch.object(app_client, "call", side_effect=app_client.AppNotRunning("no")):
        assert not app_client.same_user("me@x.com")


# ── live CLI commands ────────────────────────────────────────────────────────

@pytest.fixture
def cli(monkeypatch):
    ctx = MagicMock(username="me@x.com")
    ctx.require_auth.return_value = None
    out = MagicMock()
    calls = []
    replies = {}

    def fake_call(method, params=None, timeout=30.0):
        calls.append((method, params))
        r = replies.get(method)
        if isinstance(r, Exception):
            raise r
        return r
    patches = [
        patch("cli.agents.commands.get_context", return_value=ctx),
        patch("cli.tasks.commands.get_context", return_value=ctx),
        patch("cli.base.context.get_context", return_value=ctx),
        patch("cli.agents.commands.get_output", return_value=out),
        patch("cli.tasks.commands.get_output", return_value=out),
        patch("cli.base.app_client.call", side_effect=fake_call),
        patch("cli.base.resolve.resolve_entity_id", side_effect=lambda svc, ident, kind: ident),
    ]
    for p in patches:
        p.start()
    yield ctx, out, calls, replies
    for p in patches:
        p.stop()


POOL = {"settings": {"min": 2, "max": 4, "idle_minutes": 10}, "pinned": 3, "active_count": 3, "scaling": True,
        "wait_p50_s": 1.0, "wait_p90_s": 2.0, "turns_last_hour": 5,
        "members": [{"id": "qa1", "name": "A", "active": True, "running": True, "load": 1}]}


def test_agents_pool_pin(cli):
    from cli.agents.commands import pool
    ctx, out, calls, replies = cli
    replies["set_agent_pool_pin"] = {"pool": POOL}
    r = CliRunner().invoke(pool, ["fd1", "--pin", "3"])
    assert r.exit_code == 0, r.output
    assert calls == [("set_agent_pool_pin", {"agent_id": "fd1", "size": 3})]
    replies["set_agent_pool_pin"] = {"pool": POOL}
    assert CliRunner().invoke(pool, ["fd1", "--unpin"]).exit_code == 0
    assert calls[-1] == ("set_agent_pool_pin", {"agent_id": "fd1", "size": None})


def test_agents_pool_bad_args(cli):
    from cli.agents.commands import pool
    ctx, out, calls, replies = cli
    assert CliRunner().invoke(pool, ["--pin", "2"]).exit_code == 1
    assert CliRunner().invoke(pool, ["fd1", "--pin", "0"]).exit_code == 1
    assert CliRunner().invoke(pool, ["fd1", "--pin", "2", "--unpin"]).exit_code == 1
    assert calls == []


def test_agents_pool_list_json(cli):
    from cli.agents.commands import pool
    ctx, out, calls, replies = cli
    replies["get_agent_pools"] = {"pools": {"fd1": POOL}}
    assert CliRunner().invoke(pool, ["-f", "json"]).exit_code == 0
    assert out.json.call_args[0][0] == {"pools": {"fd1": POOL}}


def test_app_not_running_message(cli):
    from cli.agents.commands import pool
    from cli.base.app_client import AppNotRunning
    ctx, out, calls, replies = cli
    replies["get_agent_pools"] = AppNotRunning("eCan is not running")
    assert CliRunner().invoke(pool, []).exit_code == 1
    assert "Start eCan first" in out.error.call_args[0][0]


def test_tasks_execute_queues_one_run(cli):
    from cli.tasks.commands import execute
    ctx, out, calls, replies = cli
    replies["launch_agent_task"] = {"success": True, "task_name": "Daily", "run_id": "r1"}
    r = CliRunner().invoke(execute, ["t1", "--input", "day=mon"])
    assert r.exit_code == 0, r.output
    assert calls == [("launch_agent_task", {"task_id": "t1", "task_inputs": {"day": "mon"}})]


def test_agents_stop_and_monitor(cli):
    from cli.agents.commands import monitor, stop
    ctx, out, calls, replies = cli
    replies["set_agent_enabled"] = {"runtime_status": "disabled"}
    assert CliRunner().invoke(stop, ["a1"]).exit_code == 0
    assert calls[-1] == ("set_agent_enabled", {"agent_id": "a1", "enabled": False})
    replies["get_all_agents_runtime_status"] = {"agents": [{"agent_id": "a1", "runtime_status": "working"}]}
    assert CliRunner().invoke(monitor, []).exit_code == 0
    assert out.table.call_args[0][2][0][2] == "working"


def test_tasks_locks_and_state(cli):
    from cli.tasks.commands import locks, state
    ctx, out, calls, replies = cli
    replies["get_resource_locks"] = {"enabled": True, "held": {"agent:a/browser:p1": {"holder": "t1", "count": 1}},
                                     "waiting": [{"holder": "t2", "label": "report", "keys": ["agent:a/browser:p1"],
                                                  "class": "scheduled", "since": 0}]}
    assert CliRunner().invoke(locks, []).exit_code == 0
    assert out.table.call_count == 2
    replies["get_task_run_states"] = {"states": {"t2": {"last_missed": {"due_at": "09:00"}}}}
    ctx.db.task_service.get_task_by_id.return_value = {"data": {"name": "report"}}
    assert CliRunner().invoke(state, []).exit_code == 0
    row = out.table.call_args[0][2][0]
    assert row[1] == "report" and row[2] == "missed a run"


# ── task edits through the app ───────────────────────────────────────────────

def test_update_goes_through_app_with_full_record(cli, monkeypatch):
    from cli.tasks.commands import update
    ctx, out, calls, replies = cli
    monkeypatch.delenv("ECAN_CLI_DIRECT_DB", raising=False)
    replies["get_cli_session"] = {"username": "me@x.com"}
    replies["save_agent_task"] = {"task_id": "fd"}
    ctx.db.task_service.get_task_by_id.return_value = {"success": True, "data": {
        "id": "fd", "name": "前台001", "description": None, "trigger": "message", "org_id": "o1",
        "objectives": ["x"], "metadata": {"pool": {"min": 2, "max": 8}, "task_vars": {"a": "1"}}}}
    ctx.db.task_service.get_task_skills.return_value = {"success": True, "data": [{"skill_id": "s1"}]}
    r = CliRunner().invoke(update, ["fd", "--pool-min", "4", "--pool-max", "4"])
    assert r.exit_code == 0, r.output
    method, params = calls[-1]
    assert method == "save_agent_task"
    rec = params["task_info"]
    assert rec["skill_ids"] == ["s1"] and rec["org_id"] == "o1" and rec["trigger"] == "message"
    assert rec["objectives"] == ["x"] and "description" not in rec
    assert rec["metadata"] == {"pool": {"min": 4, "max": 4}, "task_vars": {"a": "1"}}
    ctx.db.task_service.update_task.assert_not_called()


def test_other_user_app_means_direct_db(cli, monkeypatch):
    from cli.tasks.commands import update
    ctx, out, calls, replies = cli
    monkeypatch.delenv("ECAN_CLI_DIRECT_DB", raising=False)
    replies["get_cli_session"] = {"username": "someone@else.com"}
    ctx.db.task_service.get_task_by_id.return_value = {"success": True, "data": {"metadata": {}}}
    ctx.db.task_service.update_task.return_value = {"success": True, "data": None}
    with patch("cli.base.sync.cloud_sync"):
        assert CliRunner().invoke(update, ["t", "--run-once"]).exit_code == 0
    ctx.db.task_service.update_task.assert_called_once()
    assert [c[0] for c in calls] == ["get_cli_session"]


def test_add_and_remove_through_app(cli, monkeypatch):
    from cli.tasks.commands import add, remove
    ctx, out, calls, replies = cli
    monkeypatch.delenv("ECAN_CLI_DIRECT_DB", raising=False)
    replies["get_cli_session"] = {"username": "me@x.com"}
    replies["new_agent_task"] = {"task_id": "t9"}
    r = CliRunner().invoke(add, ["-n", "export", "--skill", "s1", "--run-once"])
    assert r.exit_code == 0, r.output
    info = calls[-1][1]["task_info"]
    assert calls[-1][0] == "new_agent_task" and info["skill_ids"] == ["s1"]
    assert info["metadata"] == {"run_once": True} and "settings" not in info
    replies["delete_agent_task"] = {"task_id": "t9"}
    assert CliRunner().invoke(remove, ["t9", "-f"]).exit_code == 0
    assert calls[-1] == ("delete_agent_task", {"task_id": "t9"})
    ctx.db.task_service.add_task.assert_not_called()
    ctx.db.task_service.delete_task.assert_not_called()


def test_agent_update_and_remove_through_app(cli, monkeypatch):
    from cli.agents.commands import remove, update
    ctx, out, calls, replies = cli
    monkeypatch.delenv("ECAN_CLI_DIRECT_DB", raising=False)
    replies["get_cli_session"] = {"username": "me@x.com"}
    replies["save_agent"] = {"agents": []}
    assert CliRunner().invoke(update, ["a1", "--name", "New"]).exit_code == 0
    assert calls[-1] == ("save_agent", {"username": "me@x.com", "agent": [{"id": "a1", "name": "New"}]})
    replies["delete_agent"] = {"message": "ok"}
    assert CliRunner().invoke(remove, ["a1", "-f"]).exit_code == 0
    assert calls[-1] == ("delete_agent", {"username": "me@x.com", "agent_id": "a1"})
    ctx.db.agent_service.update_agent.assert_not_called()
    ctx.db.agent_service.delete_agent.assert_not_called()


def test_token_is_redacted_in_logged_requests(api_dir):
    # LocalServer imports the whole server stack; the class is tiny, so check it in isolation.
    src = open("gui/LocalServer.py", encoding="utf-8").read()
    start = src.index("class RedactedToken(str):")
    ns = {}
    exec(src[start:src.index("\n\n\n", start)], ns)
    secret = local_api.publish(5123)
    tok = ns["RedactedToken"](secret)
    assert secret not in repr({"token": tok}) and "***" in f"{ {'token': tok} }"
    assert tok == secret and local_api.is_local_secret(tok)
