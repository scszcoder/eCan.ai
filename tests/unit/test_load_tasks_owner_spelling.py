"""Startup must load a WeChat user's GUI-created tasks.

MainWindow.user is ``wechat_<openid>@local`` but the task editor saves the bare
``wechat_<openid>``. The strict owner match dropped those tasks, so their
agents started with trigger-less stubs and a chat never resumed its parked run.
"""
import asyncio
from types import SimpleNamespace

from agent.ec_agents import create_agent_tasks as cat


def _main_win(rows, user):
    svc = SimpleNamespace(query_tasks=lambda *a, **k: {"success": True, "data": rows})
    return SimpleNamespace(user=user, ec_db_mgr=SimpleNamespace(task_service=svc))


def test_both_owner_spellings_load_and_others_do_not(monkeypatch):
    monkeypatch.setattr(cat, "_convert_db_agent_task_to_object",
                        lambda d, mw: SimpleNamespace(id=d["id"], name=d["name"]))
    rows = [
        {"id": "t1", "name": "fast_deploy", "owner": "wechat_abc@local"},
        {"id": "t2", "name": "gui_created", "owner": "wechat_abc"},
        {"id": "t3", "name": "someone_else", "owner": "wechat_zzz"},
    ]
    got = asyncio.run(cat._load_agent_tasks_from_database_async(_main_win(rows, "wechat_abc@local")))
    assert sorted(t.id for t in got) == ["t1", "t2"]


def test_email_login_unchanged(monkeypatch):
    monkeypatch.setattr(cat, "_convert_db_agent_task_to_object",
                        lambda d, mw: SimpleNamespace(id=d["id"], name=d["name"]))
    rows = [{"id": "t1", "name": "a", "owner": "me@example.com"},
            {"id": "t2", "name": "b", "owner": "you@example.com"}]
    got = asyncio.run(cat._load_agent_tasks_from_database_async(_main_win(rows, "me@example.com")))
    assert [t.id for t in got] == ["t1"]
