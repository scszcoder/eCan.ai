"""A user's rating / comment on a result-panel item is stored on that
notification (content["feedback"][item_key]) and survives a re-read."""
import pytest
from sqlalchemy import create_engine

from agent.db.core import Base
from agent.db.services.db_chat_service import DBChatService


@pytest.fixture
def svc():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = DBChatService(engine=engine)
    chat = s.create_chat(members=[{"userId": "u", "role": "user", "name": "u"}], name="c", id="chat-1")
    assert chat["success"], chat
    n = s.add_chat_notification("chat-1", {"content": {"type": "notification", "notification": {"Items": []}}}, 1, uid="n1")
    assert n["success"]
    return s


def _feedback(svc):
    rows = svc.query_chat_notifications("chat-1")["data"]
    return rows[0]["content"].get("feedback")


def test_feedback_is_stored_per_item_and_merged(svc):
    assert svc.set_notification_feedback("n1", "pi001-main", {"thumb": "up", "stars": 4})["success"]
    assert svc.set_notification_feedback("n1", "pi001-main", {"comment": "background lighter"})["success"]
    assert svc.set_notification_feedback("n1", "pi002-side", {"thumb": "down"})["success"]
    fb = _feedback(svc)
    assert fb["pi001-main"]["thumb"] == "up" and fb["pi001-main"]["stars"] == 4
    assert fb["pi001-main"]["comment"] == "background lighter" and fb["pi001-main"]["updatedAt"]
    assert fb["pi002-side"]["thumb"] == "down"
    # the notification body itself is untouched
    rows = svc.query_chat_notifications("chat-1")["data"]
    assert rows[0]["content"]["content"]["notification"] == {"Items": []}


def test_unknown_notification_or_bad_input(svc):
    assert not svc.set_notification_feedback("nope", "x", {"stars": 1})["success"]
    assert not svc.set_notification_feedback("n1", "", {"stars": 1})["success"]
    assert not svc.set_notification_feedback("n1", "x", "bad")["success"]
