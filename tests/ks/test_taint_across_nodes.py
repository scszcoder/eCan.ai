"""The private-data mark must survive LangGraph node boundaries.

rag-enterprise review 2026-10-10: the mark was a top-level state key that
StateGraph(NodeState) drops between nodes, so the next LLM node saw an
untainted state and private knowledge could go to a cloud model.
"""
from types import SimpleNamespace

import pytest
from langgraph.graph import END, START, StateGraph

from agent.ec_skill import NodeState
from knowledge.ks import taint


def test_mark_survives_to_the_next_node():
    seen = {}

    def rag_node(state):
        taint.mark(state, "private")
        return state

    def llm_node(state):
        seen["tainted"] = taint.is_tainted(state)
        return state

    g = StateGraph(NodeState)
    g.add_node("rag", rag_node)
    g.add_node("llm", llm_node)
    g.add_edge(START, "rag")
    g.add_edge("rag", "llm")
    g.add_edge("llm", END)
    g.compile().invoke({"attributes": {}, "result": {}})
    assert seen["tainted"] is True


def test_private_mark_is_not_downgraded():
    st = {"attributes": {}}
    taint.mark(st, "private")
    taint.mark(st, "public")
    assert taint.is_tainted(st)


def test_check_llm_blocks_cloud_and_allows_private_host(monkeypatch):
    monkeypatch.setenv("ECAN_KS_TAINT_GUARD", "1")
    st = {"attributes": {}}
    taint.mark(st, "private")
    with pytest.raises(taint.PrivateDataBlocked):
        taint.check_llm(st, SimpleNamespace(openai_api_base="https://api.openai.com/v1"), "openai", "n")
    taint.check_llm(st, SimpleNamespace(openai_api_base="http://192.168.1.20:8000/v1"), "vllm", "n")


def test_endpoint_found_through_fallback_wrapper():
    inner = SimpleNamespace(openai_api_base="http://10.0.0.5:8000/v1")
    wrapped = SimpleNamespace(runnable=SimpleNamespace(bound=inner))
    assert taint.llm_endpoint(wrapped) == "http://10.0.0.5:8000/v1"
