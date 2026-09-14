"""A turn reports the answer, not a LangGraph state dump.

Sending 你好 from the test chat page produced the right answer and showed the
customer a state dump instead:

    ActionMessage: action: mcp call to send_chat; result:
      ❌ Failed to send message: Either recipient_agent_id or recipient_agent_name is required

Two facts collide. A chat skill answers by calling `send_chat` and then loops
back to `pend_event`, so the run's return value is the interrupt rather than the
reply. And `send_chat` is agent-to-agent — a web visitor has no agent id, so the
call fails and the answer never leaves the graph.

For a serving turn the turn's own `result` IS the delivery channel, so the text
is taken from the message the skill tried to send. The fixtures below are the
shapes from that real run.
"""

import json

import pytest

from agent.cloud_worker.cn_serve import _reply_text_from_state, _turn_result


ANSWER = "您好，在的，请问有什么可以帮您？"


class _Msg:
    """Stands in for an AIMessage: only `.content` is read."""
    def __init__(self, content):
        self.content = content


class _Snapshot:
    def __init__(self, values):
        self.values = values


def _send_chat_message(response_text=ANSWER):
    """The nested envelope exactly as the skill emits it."""
    inner = json.dumps({
        "customer_id": "<customer_id>",
        "customer_name": "<customer_name>",
        "response_text": response_text,
    }, ensure_ascii=False)
    return json.dumps({
        "tool_name": "send_chat",
        "tool_input": {"input": {
            "sender_agent_id": "", "recipient_agent_id": "", "message": inner}},
    }, ensure_ascii=False)


def _parked(history):
    return {
        "success": False,
        "step": {"__interrupt__": ({"i_tag": "pend_event_sVz3K"},)},
        "cp": _Snapshot({"input": "你好", "history": history}),
    }


def test_the_answer_is_pulled_out_of_the_send_chat_envelope():
    result = _parked([
        _Msg("你好"),
        _Msg('{"needs_rag": false, "category": "greeting"}'),
        _Msg(_send_chat_message()),
    ])

    assert _reply_text_from_state(result) == ANSWER


def test_the_turn_reports_the_answer_rather_than_the_interrupt():
    """The customer-visible outcome — the whole point."""
    result = _parked([_Msg(_send_chat_message())])

    assert _turn_result(result) == {"text": ANSWER}


def test_the_newest_answer_wins_over_an_earlier_one():
    """A multi-pass loop leaves several send_chat messages in history."""
    result = _parked([
        _Msg(_send_chat_message("第一次回复")),
        _Msg(_send_chat_message("最新回复")),
    ])

    assert _reply_text_from_state(result) == "最新回复"


def test_a_classifier_message_is_not_mistaken_for_the_answer():
    """`{"needs_rag": ...}` is JSON and has no reply text; keep looking."""
    result = _parked([
        _Msg(_send_chat_message()),
        _Msg('{"needs_rag": false, "category": "greeting"}'),
    ])

    assert _reply_text_from_state(result) == ANSWER


def test_a_skill_that_answers_in_plain_json_is_also_read():
    result = _parked([_Msg(json.dumps({"response_text": "直接回复"}, ensure_ascii=False))])

    assert _reply_text_from_state(result) == "直接回复"


def test_prompts_are_used_when_there_is_no_history():
    result = {
        "success": False,
        "step": {"__interrupt__": ()},
        "cp": _Snapshot({"prompts": [_Msg(_send_chat_message())]}),
    }

    assert _reply_text_from_state(result) == ANSWER


@pytest.mark.parametrize("result", [
    None,
    {},
    {"success": True},
    {"cp": None},
    {"cp": _Snapshot({"history": []})},
    {"cp": _Snapshot({"history": [_Msg("not json at all")]})},
    "a string",
])
def test_nothing_to_report_is_empty_rather_than_a_guess(result):
    assert _reply_text_from_state(result) == ""


def test_a_run_with_no_answer_still_reports_its_shape():
    """A turn that genuinely failed must say why, not show an empty bubble."""
    failed = {"success": False, "error": "boom"}

    assert _turn_result(failed) == failed


def test_a_normal_dict_result_is_passed_through():
    done = {"answer": "hi", "usage": {"in": 10}}

    assert _turn_result(done) == done


def test_malformed_inner_json_falls_back_to_the_raw_message():
    """Better a slightly wrong reply than none: the text is still in there."""
    envelope = json.dumps({
        "tool_name": "send_chat",
        "tool_input": {"input": {"message": "not json but readable"}},
    }, ensure_ascii=False)

    assert _reply_text_from_state(_parked([_Msg(envelope)])) == "not json but readable"
