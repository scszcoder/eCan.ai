"""send_chat gets a lane for the serving turn.

A web visitor has no agent id, so `send_chat` rejected the reply on an A2A
precondition that ran before any lane was chosen:

    ❌ Failed to send message: Either recipient_agent_id or
       recipient_agent_name is required

`send_chat` was never purely agent-to-agent — it already routes between the A2A
lane and the off-DOM live-chat lanes Feige uses. What was missing is a lane for
the serving turn, where the destination is the TURN rather than an agent.

The lane is deliberately narrow: no recipient at all, AND a turn open to collect
the reply. A Feige reply names its recipient and never reaches it, which is what
keeps the battle-tested lanes untouched.
"""

import json
import threading

import pytest

from agent.ec_skills import serving_reply


ANSWER = "您好，在的，请问有什么可以帮您？"


def _envelope(response_text=ANSWER):
    """The live-chat reply envelope the skill emits."""
    return json.dumps({
        "customer_id": "<customer_id>",
        "customer_name": "<customer_name>",
        "response_text": response_text,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

def test_no_turn_means_no_lane():
    assert serving_reply.serving_turn_active() is False
    assert serving_reply.record_reply("anything") is False
    assert serving_reply.current_text() == ""


def test_a_turn_collects_its_reply():
    with serving_reply.turn_replies() as window:
        assert serving_reply.serving_turn_active() is True
        assert serving_reply.record_reply(ANSWER) is True
        assert window.text == ANSWER


def test_the_window_closes_with_the_turn():
    with serving_reply.turn_replies():
        pass
    assert serving_reply.serving_turn_active() is False


def test_two_messages_in_one_turn_are_both_kept():
    """Dropping the first would be a reply the customer never sees."""
    with serving_reply.turn_replies() as window:
        serving_reply.record_reply("第一句")
        serving_reply.record_reply("第二句")

    assert window.replies == ["第一句", "第二句"]
    assert window.text == "第一句\n\n第二句"


@pytest.mark.parametrize("junk", ["", "   ", None, 123, {"a": 1}])
def test_nothing_worth_saying_is_not_recorded(junk):
    with serving_reply.turn_replies() as window:
        serving_reply.record_reply(junk)
    assert window.replies == []


def test_concurrent_turns_do_not_answer_each_others_visitors():
    """The whole reason this is a ContextVar rather than a global.

    A pod runs several turns at once; a shared slot would let one turn's answer
    be reported to another turn's visitor — worse than not answering.
    """
    seen = {}

    def _turn(name):
        import contextvars
        def _run():
            with serving_reply.turn_replies() as w:
                serving_reply.record_reply(f"answer-{name}")
                seen[name] = w.text
        # A Task/to_thread copies the context; mimic that.
        contextvars.copy_context().run(_run)

    threads = [threading.Thread(target=_turn, args=(n,)) for n in ("a", "b", "c")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert seen == {"a": "answer-a", "b": "answer-b", "c": "answer-c"}


# ---------------------------------------------------------------------------
# The lane inside send_chat
# ---------------------------------------------------------------------------

def _send(**config):
    from agent.mcp.server.chat_utils.chat_tools import send_chat
    return send_chat(None, config)


def test_a_reply_with_no_recipient_is_delivered_to_the_turn():
    with serving_reply.turn_replies() as window:
        out = _send(sender_agent_id="agent_1", message=_envelope(), chat_id="turn_9")

    assert out.get("success") is True, out
    assert out.get("lane") == "serving_turn"
    assert window.text == ANSWER, "the answer, unwrapped from the envelope"


def test_prose_is_delivered_too():
    """A skill that answers without the live-chat envelope still has a reply."""
    with serving_reply.turn_replies() as window:
        out = _send(sender_agent_id="agent_1", message="就是这样", chat_id="turn_9")

    assert out.get("success") is True
    assert window.text == "就是这样"


def test_without_a_turn_the_a2a_requirement_still_applies():
    """Off the serving path nothing changes — this is the guard that keeps the
    Feige lanes honest about needing a recipient."""
    out = _send(sender_agent_id="agent_1", message=_envelope(), chat_id="c1")

    assert out.get("success") is False
    assert "recipient_agent_id" in str(out.get("error"))


def test_a_named_recipient_never_takes_the_serving_lane():
    """A Feige reply names its recipient, so it must not be diverted.

    It will fail here for want of a real app context, which is fine: what
    matters is that it is NOT answered by the serving lane.
    """
    with serving_reply.turn_replies() as window:
        out = _send(sender_agent_id="agent_1", recipient_agent_id="agent_2",
                    message=_envelope(), chat_id="c1")

    assert out.get("lane") != "serving_turn"
    assert window.replies == [], 'a message addressed to an agent must not be collected'


def test_a_missing_sender_is_still_refused():
    """The serving lane is not a way around the other preconditions."""
    with serving_reply.turn_replies():
        out = _send(message=_envelope(), chat_id="turn_9")

    assert out.get("success") is False
    assert "sender_agent_id" in str(out.get("error"))


# ---------------------------------------------------------------------------
# What the turn reports
# ---------------------------------------------------------------------------

def test_the_delivered_reply_wins_over_reading_it_back_from_state():
    """Taken from the call itself, not reconstructed from the final state."""
    from agent.cloud_worker.cn_serve import _turn_result

    parked = {"success": False, "step": {"__interrupt__": ()}}

    assert _turn_result(parked, ANSWER) == {"text": ANSWER}


def test_state_is_still_read_when_nothing_was_delivered():
    """The fallback: a reply sent from a raw thread never reaches the window."""
    from agent.cloud_worker.cn_serve import _turn_result

    class _Snap:
        def __init__(self, values):
            self.values = values

    class _Msg:
        def __init__(self, content):
            self.content = content

    envelope = json.dumps({
        "tool_name": "send_chat",
        "tool_input": {"input": {"message": _envelope()}},
    }, ensure_ascii=False)
    parked = {"success": False, "step": {}, "cp": _Snap({"history": [_Msg(envelope)]})}

    assert _turn_result(parked, "") == {"text": ANSWER}


@pytest.mark.parametrize("blank", ["", "   ", None])
def test_a_blank_delivery_does_not_shadow_the_fallback(blank):
    from agent.cloud_worker.cn_serve import _turn_result

    failed = {"success": False, "error": "boom"}

    assert _turn_result(failed, blank) == failed
