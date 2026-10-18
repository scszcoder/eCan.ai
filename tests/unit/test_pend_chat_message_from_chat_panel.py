"""A chat_message pend_event (the skill editor's default; human_chat is labelled
legacy) must resume on a chat-panel reply, which arrives as event_type
send_chat -- but never on a message an AGENT sent, e.g. the chat window's
"Hello! How can I help you today?" greeting, which carries human=True /
senderType=human yet is posted as the agent.

Runs the real pend node inside a one-node LangGraph graph.
"""
from types import SimpleNamespace
from typing import Any, Dict, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.ec_skills import build_node as bn


class _S(TypedDict, total=False):
    input: str
    attributes: Dict[str, Any]
    messages: list
    history: list
    events: list
    result: Any
    tool_result: Any


def _graph(prompt="", skill="skill_t"):
    iv = {"eventType": {"type": "constant", "content": "chat_message"}}
    if prompt:
        iv["prompt"] = {"type": "constant", "content": prompt}
    node = bn.build_pend_event_node({"inputsValues": iv}, "pend_wait", skill, "owner_t", None)
    g = StateGraph(_S)
    rt = SimpleNamespace(context={})
    g.add_node("pend_wait", lambda st, config=None: node(st, runtime=rt, store=None))
    g.add_edge(START, "pend_wait")
    g.add_edge("pend_wait", END)
    return g.compile(checkpointer=MemorySaver())


def _payload(text, sender_id, sender_type):
    ctx = {"chatId": "chat-1", "senderId": sender_id, "senderType": sender_type, "transport": "gui"}
    return {"event": {"type": "send_chat", "tag": "pend_wait"}, "event_type": "send_chat",
            "_event_envelope": {"type": "send_chat", "data": {"human_text": text}, "context": ctx},
            "human_text": text, "_state_patch": {"attributes": {"chat_id": "chat-1"}}}


@pytest.fixture
def agents(monkeypatch):
    from agent import agent_service
    monkeypatch.setattr(agent_service, "get_agent_by_id",
                        lambda aid: object() if str(aid).startswith("agent_") else None)


def _run(payload):
    g = _graph()
    cfg = {"configurable": {"thread_id": "t1"}}
    first = g.invoke({"input": "", "attributes": {"chat_id": "chat-1"},
                      "messages": ["agent_self", "chat-1"], "history": [], "events": []}, cfg)
    assert "__interrupt__" in first
    return g.invoke(Command(resume=payload), cfg)


def test_chat_panel_reply_resumes(agents):
    out = _run(_payload("help me make an image", "system_wechat_user", "human"))
    assert "__interrupt__" not in out          # matched: the node finished


def test_agent_greeting_does_not_resume(agents):
    out = _run(_payload("Hello! How can I help you today?", "agent_1142d37f900742b0", "human"))
    assert "__interrupt__" in out              # still waiting for the real user


def test_question_is_not_resent_when_the_reply_resumes_the_node(agents, monkeypatch):
    # A resume re-runs the node from the top (LangGraph), including its "send
    # the question" step. However long the user took to answer, the question
    # they are answering must not be posted again; a NEW question must be.
    from agent.ec_tasks import message_sender
    sent = []
    monkeypatch.setattr(message_sender.ChatMessageSender, "__init__", lambda self, *a, **k: None)
    monkeypatch.setattr(message_sender.ChatMessageSender, "send_text",
                        lambda self, chat_id, text, *a, **k: sent.append(text))

    g = _graph(prompt="Which marketplace?", skill="skill_resend")
    cfg = {"configurable": {"thread_id": "t2"}}
    first = g.invoke({"input": "", "attributes": {"chat_id": "chat-1"},
                      "messages": ["agent_self", "chat-1"], "history": [], "events": []}, cfg)
    assert "__interrupt__" in first and sent == ["Which marketplace?"]
    assert first["__interrupt__"][0].value.get("prompt_delivered") is True

    out = g.invoke(Command(resume=_payload("Amazon US", "system_wechat_user", "human")), cfg)
    assert "__interrupt__" not in out
    assert sent == ["Which marketplace?"]      # not re-sent on resume

    g2 = _graph(prompt="Which output folder?", skill="skill_resend")
    g2.invoke({"input": "", "attributes": {"chat_id": "chat-1"},
               "messages": ["agent_self", "chat-1"], "history": [], "events": []},
              {"configurable": {"thread_id": "t3"}})
    assert sent == ["Which marketplace?", "Which output folder?"]   # a new question goes out
