"""Our replies to a card:<talk> turn reach the next Q&A turn of that conversation
(11-05 17:11: a card, then "纯棉的吧？" on another Q&A task -> cotton answered twice)."""
from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    actionable_items as ai, dispatch_state as ds, ws_session)


def test_card_reply_kept_and_bridged(monkeypatch):
    monkeypatch.setattr(ai, "_agent_recent_replies", {})
    ds.remember_agent_reply("card:777", "您好，这款是纯棉长袖T恤。")
    assert ai.get_recent_agent_replies("card:777") == ["您好，这款是纯棉长袖T恤。"]
    monkeypatch.setattr(ws_session, "talk_for_name", lambda name: "777" if name == "陆地飞鱼" else "")
    ds.remember_agent_reply("陆地飞鱼", "夏天穿很合适哦。")
    assert ai.get_recent_agent_replies("陆地飞鱼") == ["您好，这款是纯棉长袖T恤。", "夏天穿很合适哦。"]
    assert ai.get_recent_agent_replies("别人") == []
