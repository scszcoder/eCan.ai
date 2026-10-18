"""A pend_event waiting for another agent's answer (a2a_response) must resume on
that answer when it arrives labelled chat_message -- the runner's
send_response_back reply carries no senderType, so normalize_event leaves it
as chat_message (2026-10-18: 做图经理小李 parked on pend_waitWang ignored
做图专家小王's finished result). A message from the user must still not wake it.

Runs the real pend node inside a one-node LangGraph graph.
"""
from types import SimpleNamespace
from typing import Any, Dict, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.ec_skills import build_node as bn

FINISH = '{"all_done": true, "passed": 1, "total_count": 1, "results_file": "C:\\\\tmp\\\\results.jsonl"}'


class _S(TypedDict, total=False):
    input: str
    attributes: Dict[str, Any]
    messages: list
    history: list
    events: list
    result: Any
    tool_result: Any


def _graph(event_type):
    iv = {"eventType": {"type": "constant", "content": event_type}}
    node = bn.build_pend_event_node({"inputsValues": iv}, "pend_waitWang", "skill_a2a", "owner_t", None)
    g = StateGraph(_S)
    rt = SimpleNamespace(context={})
    g.add_node("pend_waitWang", lambda st, config=None: node(st, runtime=rt, store=None))
    g.add_edge(START, "pend_waitWang")
    g.add_edge("pend_waitWang", END)
    return g.compile(checkpointer=MemorySaver())


def _payload(text, sender_id, event_type="chat_message"):
    # Shape from the log: normalize_event context with transport=a2a, senderType=''.
    ctx = {"chatId": "chat-4c00fe9c", "senderId": sender_id, "senderType": "", "transport": "a2a"}
    return {"event": {"type": event_type, "tag": "pend_reqAsk"}, "event_type": event_type,
            "_event_envelope": {"type": event_type, "source": sender_id, "data": {"human_text": text}, "context": ctx},
            "human_text": text, "_state_patch": {}}


@pytest.fixture
def agents(monkeypatch):
    from agent import agent_service
    monkeypatch.setattr(agent_service, "get_agent_by_id",
                        lambda aid: object() if str(aid).startswith("agent_") else None)


def _run(event_type, payload):
    g = _graph(event_type)
    cfg = {"configurable": {"thread_id": "t1"}}
    first = g.invoke({"input": "confirmed", "attributes": {}, "messages": ["agent_li", "chat-789821"],
                      "history": [], "events": []}, cfg)
    assert "__interrupt__" in first
    return g.invoke(Command(resume=payload), cfg)


def test_agent_reply_labelled_chat_message_resumes_an_a2a_response_pend(agents):
    out = _run("a2a_response", _payload(FINISH, "agent_5031518fc8804d1e"))
    assert "__interrupt__" not in out
    assert out["input"] == FINISH                     # the report step reads it here


def test_user_message_does_not_resume_an_a2a_response_pend(agents):
    out = _run("a2a_response", _payload("are you done?", "system_wechat_user", "send_chat"))
    assert "__interrupt__" in out


def test_a2a_task_result_pend_also_takes_a2a_response(agents):
    out = _run("a2a_task_result", _payload(FINISH, "agent_5031518fc8804d1e", "a2a_response"))
    assert "__interrupt__" not in out
