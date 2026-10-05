"""A customer who opened with a product card keeps the synthetic identity
card:<talk> (sticky). Their later TEXT messages must still take the WS text
fast path: routing only knows real names, so the lookup missed, the DOM scrape
read the not-yet-rendered thread and mt030 skipped the new question as already
answered -- 50-60s replies until the backstop caught it (customer run 99v)."""

import time

import pytest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import ws_session as wss

TALK = "7693103563316266287"


@pytest.fixture
def thread(monkeypatch):
    now = int(time.time() * 1000)
    monkeypatch.setattr(wss, "_thread", {TALK: {
        "cust": {"type": "text", "text": "会不会透气，会不会扎皮肤", "cmid": "1878199487524923", "ts": now},
        "agent": {"text": "正常洗涤一般不会明显掉色", "cmid": "a1", "ts": now - 60_000, "is_ours": True},
    }})
    return now


def test_card_identity_reads_its_own_conversation(thread):
    hit = wss.ws_text_scrape(f"card:{TALK}")
    assert hit and hit["text"] == "会不会透气，会不会扎皮肤" and hit["msg_id"] == "1878199487524923"
    assert hit["latest_agent_bubble"]["index"] == -1     # our last reply is OLDER: unanswered


def test_unknown_real_name_still_falls_back_to_dom(thread):
    assert wss.ws_text_scrape("某个陌生人") is None


def test_snapshot_also_resolves_card_identity(thread):
    snap = wss.ws_thread_snapshot(f"card:{TALK}")
    assert snap
