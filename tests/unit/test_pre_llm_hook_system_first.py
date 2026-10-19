"""The pre-LLM hook puts the node's system prompt at the FRONT of a history
that already holds turns but no system prompt (a restored chat transcript, a
pend node's human message). Appended after them, the LLM node sent it twice --
prepended once and again mid-conversation."""
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.ec_skills.llm_hooks import llm_hooks as lh

PROMPTS = [("system", "You collect image requirements."), ("human", "{human_input}")]


@pytest.fixture(autouse=True)
def _agent(monkeypatch):
    monkeypatch.setattr(lh, "get_agent_by_id", lambda aid: SimpleNamespace(mainwin=None))


def _run(history, inp="make the background lighter"):
    st = {"messages": ["agent_li"], "input": inp, "history": list(history), "attributes": {}, "prompt_refs": {}}
    lh.standard_pre_llm_hook("ask1", ":skill:llm_reqCollector", None, st, "gui", PROMPTS)
    return st["history"]


def test_empty_history_unchanged_behaviour():
    h = _run([])
    assert [type(m) for m in h] == [SystemMessage, HumanMessage]
    assert h[1].content == "make the background lighter"


def test_system_prompt_goes_first_before_restored_turns():
    h = _run([AIMessage(content="Which product?"), HumanMessage(content="ABC perfume")])
    assert isinstance(h[0], SystemMessage) and h[0].content == "You collect image requirements."
    assert [m.content for m in h[1:]] == ["Which product?", "ABC perfume", "make the background lighter"]
    assert sum(isinstance(m, SystemMessage) for m in h) == 1


def test_history_with_a_system_prompt_is_appended_to_as_before():
    prior = [SystemMessage(content="You collect image requirements."), HumanMessage(content="hi"), AIMessage(content="hello")]
    h = _run(prior)
    assert sum(isinstance(m, SystemMessage) for m in h) == 1 and isinstance(h[0], SystemMessage)
    assert h[-1].content == "make the background lighter"
