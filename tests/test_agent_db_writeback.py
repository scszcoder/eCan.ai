"""MainWindow._update_local_db_agents: the startup write-back of merged agent
dicts into the local DB. It failed on every startup ('card' is an invalid
keyword argument for DBAgent) and rolled the whole batch back."""
from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import agent.db.models  # noqa: F401  (registers every table)
from agent.db.models.agent_model import DBAgent
from agent.db.models.base_model import BaseModel

ME = "wechat_me@local"


def _db():
    # one shared in-memory DB across threads (the write-back runs in an executor)
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    BaseModel.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    @contextmanager
    def session_scope():
        s = Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
    return Session, session_scope


def test_writeback(monkeypatch):
    from gui.MainGUI import MainWindow
    Session, scope = _db()
    with scope() as s:
        s.add(DBAgent(id="mine", name="old", owner=ME, description="local desc", title="店长"))
        s.add(DBAgent(id="theirs", name="x", owner="someone@else", description="keep"))

    fake = SimpleNamespace(user=ME, ec_db_mgr=SimpleNamespace(agent_service=SimpleNamespace(session_scope=scope)))
    merged = [
        # cloud row for an agent we have: real values win, missing (None) ones don't blank ours
        {"id": "mine", "name": "客服小晴", "owner": "bare_openid", "description": None, "title": "主管",
         "skills": [{"id": "s1", "name": "s1"}], "tasks": [], "card": {"url": "x"}},
        # another login's row with the same id space: not ours to rewrite
        {"id": "theirs", "name": "hijack", "description": "nope"},
        # new cloud agent: added, owned by this login, non-column keys ignored
        {"id": "new1", "name": "前台", "owner": "bare_openid", "tasks": [{"id": "t", "name": "t"}],
         "card": {}, "created_at": 1791698631164},
        # a row that cannot be stored must not undo the others
        {"id": "bad", "name": "坏", "created_at": "not-a-date"},
    ]
    asyncio.run(MainWindow._update_local_db_agents(fake, merged))

    s = Session()
    mine, theirs, new1 = (s.get(DBAgent, i) for i in ("mine", "theirs", "new1"))
    assert (mine.name, mine.title, mine.description, mine.owner) == ("客服小晴", "主管", "local desc", ME)
    assert (theirs.name, theirs.description) == ("x", "keep")
    assert new1 is not None and new1.owner == ME and new1.name == "前台"
    assert new1.created_at.year == 2026
