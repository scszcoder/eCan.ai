"""Evicted browser-use agents are scrubbed (2026-10-14: the chip-docs crawler kept 70 evicted
agents alive at 2.9 GB, each pinning its history and per-step ActionModel classes)."""
import gc
import weakref

import pytest
from browser_use import Agent
from browser_use.llm.openai.chat import ChatOpenAI

from agent.ec_skills.browser_node import agent as bn_agent
from agent.ec_skills.browser_node import build_helpers as bh


class _Heavy:
    """Stands in for a per-step pydantic class / history payload."""


def _agent_with_heavy_state():
    agent = Agent(task="t", llm=ChatOpenAI(model="gpt-4o-mini", api_key="sk-test"))
    heavy = _Heavy()
    agent.AgentOutput = heavy
    return agent, weakref.ref(heavy)


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setattr(bh, "cached_bu_agents", {})
    monkeypatch.setattr(bh, "_cached_bu_agents_insertion_order", [])
    monkeypatch.setattr(bh, "_MAX_BU_AGENTS_CACHE_SIZE", 1)
    monkeypatch.setattr(bn_agent, "_DEFERRED_SCRUB", weakref.WeakSet())


def _cache(key, agent):
    bh.cached_bu_agents[key] = agent
    bh._cached_bu_agents_insertion_order.append(key)


def test_evicted_agent_held_elsewhere_releases_its_heavy_state(cache):
    agent, heavy = _agent_with_heavy_state()
    returned_history = agent.history
    returned_history.history.append("step-1")
    leak_holder = [agent]  # whatever keeps evicted agents alive in the app

    _cache("chat:a", agent)
    _cache("chat:b", object())
    bh._evict_bu_agent_if_needed()
    gc.collect()

    assert list(bh.cached_bu_agents) == ["chat:b"]
    assert heavy() is None
    assert leak_holder[0].history.history == []
    assert leak_holder[0].browser_session is None
    # Replaced, not cleared: a caller still reading the last run's history keeps it.
    assert returned_history.history == ["step-1"]


def test_agent_evicted_mid_run_is_scrubbed_only_after_its_run(cache, monkeypatch):
    agent, heavy = _agent_with_heavy_state()
    agent._ecan_run_active = True
    _cache("chat:a", agent)
    _cache("chat:b", object())
    bh._evict_bu_agent_if_needed()
    assert agent.AgentOutput is heavy()  # untouched while running

    agent._ecan_run_active = False
    agent._ecan_run_ended_at = 1000.0
    monkeypatch.setattr(bn_agent.time, "monotonic", lambda: 1000.0 + 10)
    bn_agent.scrub_deferred_bu_agents()
    assert agent.AgentOutput is heavy()  # caller may still be reading it

    monkeypatch.setattr(bn_agent.time, "monotonic", lambda: 1000.0 + 10_000)
    bn_agent.scrub_deferred_bu_agents()
    gc.collect()
    assert heavy() is None
    assert len(bn_agent._DEFERRED_SCRUB) == 0
