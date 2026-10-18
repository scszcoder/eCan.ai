"""Customer questions lost by the 抖店 front desk with two buyers (log 2026-10-18):

1. send_chat's auto-distribute overrode the pool's pick and rotated the turn to
   an agent of ANOTHER store sharing the skill; that agent's task drops it.
2. The card<->name twin guard dropped a real answer to a DIFFERENT question
   because the other identity had just been answered about something else.
3. ws160 folded an old, already-answered bubble into a card dispatch, so the
   Q&A answered the old question again.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import dispatch_state, pre_dispatch_enrich
from agent.mcp.server.chat_utils import chat_tools

FD = "agent_fd_douyin"
QA1, QA2 = "agent_qa_dy1", "agent_qa_dy2"
PDD_QA = "agent_qa_pdd"
AGENTS = [
    {"id": FD, "skills": ["飞鸽客服前台01"]},
    {"id": QA1, "skills": ["飞鸽客服问答00"]},
    {"id": QA2, "skills": ["飞鸽客服问答00"]},
    {"id": PDD_QA, "skills": ["飞鸽客服问答00"]},   # another store's Q&A, same skill
]


# ── 1. auto-distribute ───────────────────────────────────────────────────────

def test_pooled_front_desk_is_never_rotated():
    with patch("agent.ec_agents.agent_pool.pools", lambda: {FD: {"members": [QA1, QA2]}}):
        assert chat_tools._auto_distribute_peers(FD, QA1, AGENTS) == []


def test_unpooled_sender_rotates_only_to_its_own_listeners():
    with patch("agent.ec_agents.agent_pool.pools", lambda: {}), \
         patch("agent.ec_tasks.runner.find_my_listeners", lambda s: [QA1, QA2]):
        peers = [a["id"] for a in chat_tools._auto_distribute_peers(FD, QA1, AGENTS)]
    assert peers == [QA2]          # never the other store's PDD_QA


def test_no_listener_info_keeps_the_shared_skill_rule():
    with patch("agent.ec_agents.agent_pool.pools", lambda: {}), \
         patch("agent.ec_tasks.runner.find_my_listeners", lambda s: []):
        peers = sorted(a["id"] for a in chat_tools._auto_distribute_peers(FD, QA1, AGENTS))
    assert peers == sorted([QA2, PDD_QA])


# ── 2. twin guard ────────────────────────────────────────────────────────────

CARD, NAME = "card:7697891788232721690", "陆地飞鱼"
WSS = SimpleNamespace(name_for_talk=lambda t: NAME if t == CARD[5:] else "",
                      talk_for_name=lambda n: CARD[5:] if n == NAME else "")


def _twin(**kw):
    with patch("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.ws_session", WSS, create=True):
        return dispatch_state.cross_identity_twin(CARD, **kw)


def _reset():
    dispatch_state.recent_agent_replies_by_customer.clear()
    dispatch_state._reply_turns.clear()


def test_answer_to_a_different_question_is_not_a_twin():
    _reset()
    dispatch_state.remember_agent_reply(NAME, "这款券后立减10元，现在付款明天发货哦。",
                                        source_msg_id="2_d110_template", source_text="[商品卡片] 男童短袖球服套装")
    assert _twin(source_msg_id="643F5871", source_text="是不是透气？过敏吗") == ""


def test_same_turn_by_id_is_a_twin():
    _reset()
    dispatch_state.remember_agent_reply(NAME, "这款透气性不错。", source_msg_id="643F5871", source_text="是不是透气？过敏吗")
    assert _twin(source_msg_id="643F5871", source_text="是不是透气？过敏吗") == NAME


def test_same_turn_by_question_text_is_a_twin_even_with_card_text_folded_in():
    _reset()
    dispatch_state.remember_agent_reply(NAME, "这款透气性不错。", source_msg_id="id-name", source_text="是不是透气？过敏吗")
    assert _twin(source_msg_id="id-card", source_text="是不是透气？过敏吗\n[商品卡片] 男童短袖") == NAME


def test_no_turn_info_keeps_the_old_behaviour():
    _reset()
    dispatch_state.remember_agent_reply(NAME, "您好，这款篮球服是速干面料。")
    assert _twin() == NAME
    assert _twin(source_msg_id="x", source_text="别的问题") == NAME   # the other side's turn is unknown


# ── 3. ws160 bundled-text fold ───────────────────────────────────────────────

def _fold(bubble, last_dispatched=None):
    async def fake_scrape(*a, **k):
        return bubble
    item = {"last_message": "[商品卡片] 男童短袖 商品ID:1", "customer_name": "肽斯特"}
    with patch.object(pre_dispatch_enrich, "scrape_latest_customer_bubble", fake_scrape):
        asyncio.run(pre_dispatch_enrich._scrape_and_override_last_message(
            None, item, "肽斯特", "[t]", customer_last_dispatched_msg_id=last_dispatched))
    return item["latest_message"] if "latest_message" in item else item["last_message"]


def test_new_bundled_question_is_folded():
    out = _fold({"scrape_ok": True, "text": "这件面料怎么样，透气吗", "msg_id": "m2", "index": 7,
                 "latest_agent_bubble": {"index": 5, "text": "现在可以拍哦"}})
    assert out.startswith("这件面料怎么样，透气吗")


def test_already_answered_bubble_is_not_folded():
    out = _fold({"scrape_ok": True, "text": "你好 现在拍能发货吗", "msg_id": "m1", "index": 5,
                 "latest_agent_bubble": {"index": 6, "text": "现在可以拍，具体发货时效这边帮您核实下哦"}})
    assert out == "[商品卡片] 男童短袖 商品ID:1"


def test_bubble_dispatched_last_turn_is_not_folded():
    out = _fold({"scrape_ok": True, "text": "你好 现在拍能发货吗", "msg_id": "m1", "index": 5,
                 "latest_agent_bubble": {}}, last_dispatched={"肽斯特": "m1"})
    assert out == "[商品卡片] 男童短袖 商品ID:1"


def test_placeholder_reply_does_not_count_as_answered():
    # Patched by path: the fold imports it by name at call time.
    with patch("agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dispatch_state.is_placeholder_text",
               lambda t: True):
        out = _fold({"scrape_ok": True, "text": "这件面料怎么样，透气吗", "msg_id": "m2", "index": 5,
                     "latest_agent_bubble": {"index": 6, "text": "稍等一下哦~"}})
    assert out.startswith("这件面料怎么样，透气吗")
