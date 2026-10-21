"""The QA-pending duplicate guard (alpha 2026-10-21, 抖店 single store): the
answer to "是亲肤面料吗" was word for word the previous turn's answer
("这边帮您核实一下面料信息，稍后回复您。") and was suppressed as a retry, while
that previous answer -- delivered by the runner's direct delivery -- never
released its lock. The buyer got nothing."""
from unittest.mock import patch

from agent.mcp.server.chat_utils import chat_tools as ct

REPLY = "这边帮您核实一下面料信息，稍后回复您。"


def _reply(question):
    return {"customer_id": "肽斯特", "response_text": REPLY, "source_latest_message": question}


def test_a_retry_of_the_same_turn_is_still_a_duplicate():
    assert ct._qa_reply_hash(_reply("这件衣服面料舒服吗")) == ct._qa_reply_hash(_reply("这件衣服面料舒服吗"))


def test_the_same_words_for_a_new_question_are_not_a_duplicate():
    first, second = ct._qa_reply_hash(_reply("这件衣服面料舒服吗")), ct._qa_reply_hash(_reply("是亲肤面料吗"))
    assert first != second
    ct._qa_response_pending_lock.clear()
    ct.mark_qa_response_pending("fd", "肽斯特", first)
    with patch.object(ct, "_offdom_send_lane_active", return_value=True):
        assert ct._check_qa_response_pending("fd", "肽斯特", incoming_content_hash=second) == 0.0
    ct._qa_response_pending_lock.clear()


def test_same_reply_same_question_within_ttl_is_skipped():
    h = ct._qa_reply_hash(_reply("这件衣服面料舒服吗"))
    ct._qa_response_pending_lock.clear()
    ct.mark_qa_response_pending("fd", "肽斯特", h)
    assert ct._check_qa_response_pending("fd", "肽斯特", incoming_content_hash=h) > 0
    ct.clear_qa_response_pending("fd", "肽斯特")                # what direct delivery now does
    assert ct._check_qa_response_pending("fd", "肽斯特", incoming_content_hash=h) == 0.0
