"""A front desk's round that delivered a Q&A reply never sends its result back to the Q&A
(11-05 17:35: the stale {"stale_resume_reset": true} result was answered as a buyer question)."""
import json

from agent.ec_skills.llm_utils.llm_utils import _round_delivered_a_reply


def _state(human_text):
    return {"events": [{"event_type": "a2a_response", "data": {"human_text": human_text}}]}


def test_delivery_round_detected():
    reply = {"customer_id": "c1", "customer_name": "c1", "response_text": "夏天穿很合适哦。",
             "source_customer_msg_id": "m1", "source_latest_message": "夏天穿合适不"}
    assert _round_delivered_a_reply(_state(json.dumps(reply, ensure_ascii=False)))


def test_buyer_dispatch_to_qa_is_not_a_delivery():
    ask = {"customer_id": "card:1", "session_id": "s", "chat_url": "u", "latest_message": "纯棉的吧？"}
    assert not _round_delivered_a_reply(_state(json.dumps(ask, ensure_ascii=False)))


def test_echo_payload_and_odd_inputs():
    assert not _round_delivered_a_reply(_state('{"all_done": false, "work_done": false, "stale_resume_reset": true}'))
    assert not _round_delivered_a_reply(_state("hello"))
    assert not _round_delivered_a_reply({"events": []})
    assert not _round_delivered_a_reply({})
    assert not _round_delivered_a_reply(_state(json.dumps({"customer_id": "c1", "response_text": "  "})))
