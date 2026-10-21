"""Retention for a long unattended run: chat messages / notifications older
than 90 days and generated media older than 60 days are removed; everything
newer, the chats themselves, and bookkeeping files stay."""
import os
import time

import pytest
from sqlalchemy import create_engine

from agent.db.core import Base, Message, ChatNotification, Attachment
from agent.db.services.db_chat_service import DBChatService
from utils import data_retention as dr

DAY_MS = 86400 * 1000


@pytest.fixture
def svc():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = DBChatService(engine=engine)
    assert s.create_chat(members=[{"userId": "u", "role": "user", "name": "u"}], name="c", id="chat-1")["success"]
    now = int(time.time() * 1000)
    with s.session_scope() as session:
        for mid, age_days in (("old", 120), ("edge", 89), ("new", 1)):
            session.add(Message(id=mid, chatId="chat-1", role="user", content={"type": "text", "text": mid},
                                senderId="u", status="complete", createAt=now - age_days * DAY_MS))
        session.flush()
        session.add(Attachment(uid="att-old", messageId="old", name="a.png", status="done"))
        session.add(Attachment(uid="att-new", messageId="new", name="b.png", status="done"))
    s.add_chat_notification("chat-1", {"x": 1}, now - 100 * DAY_MS, uid="n-old")
    s.add_chat_notification("chat-1", {"x": 2}, now - 5 * DAY_MS, uid="n-new")
    return s


def test_chat_older_than_90_days_is_removed(svc):
    res = svc.prune_older_than(90)
    assert res == {"messages": 1, "attachments": 1, "notifications": 1}
    with svc.session_scope() as s:
        assert sorted(m.id for m in s.query(Message).all()) == ["edge", "new"]
        assert [a.uid for a in s.query(Attachment).all()] == ["att-new"]
        assert [n.uid for n in s.query(ChatNotification).all()] == ["n-new"]
    assert svc.get_chat_by_id("chat-1")["success"]                # the chat itself stays


def test_media_older_than_60_days_is_removed(tmp_path):
    old = tmp_path / "received" / "old.png"
    old.parent.mkdir()
    old.write_bytes(b"x")
    new = tmp_path / "new.png"
    new.write_bytes(b"x")
    keep = tmp_path / "pending_media_jobs.json"
    keep.write_text("{}")
    past = time.time() - 61 * 86400
    os.utime(old, (past, past))
    os.utime(keep, (past, past))
    assert dr.prune_media(str(tmp_path), 60) == 1
    assert not old.exists() and not old.parent.exists()           # emptied folder removed too
    assert new.exists() and keep.exists()


def test_run_once_uses_the_policy(svc, tmp_path):
    res = dr.run_once(svc, str(tmp_path))
    assert res["messages"] == 1 and res["media_files"] == 0
