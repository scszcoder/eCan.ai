"""A looped new-chromium browser node must not reuse an agent whose browser
browser-use already closed (keep_alive off). 2026-10-09: chip-docs planner
round 2 failed 6x in 5 ms on "Expected at least one handler..." because the
cached agent's session was stopped at the end of round 1.
"""
import asyncio
from types import SimpleNamespace

from agent.ec_skills.browser_node import build_helpers as _bh
from agent.ec_skills.browser_node.runner import acquire_or_reuse_local_agent


class _FakeAgent:
    def __init__(self, task, llm, controller, keep_alive=False, **kw):
        self.task = task
        self.browser_session = SimpleNamespace(browser_profile=SimpleNamespace(keep_alive=keep_alive))


def _acquire(scope, keep_alive):
    return asyncio.run(acquire_or_reuse_local_agent(
        AgentClass=_FakeAgent, task="t", llm=None, controller=None,
        agent_kwargs={"keep_alive": keep_alive}, bu_scope_key=scope,
        cached_bu_agents=_bh.cached_bu_agents, loop_history_mode="clear",
        fp_profile=None, browser_session=None))


def test_closed_browser_agent_is_rebuilt(monkeypatch):
    monkeypatch.setattr("agent.ec_skills.browser_node.runner.reset_bu_agent_for_next_round",
                        lambda *a, **k: None)
    first = _acquire("test:dead_session", keep_alive=False)
    second = _acquire("test:dead_session", keep_alive=False)
    assert second is not first
    _bh.cached_bu_agents.pop("test:dead_session", None)


def test_kept_alive_agent_is_reused(monkeypatch):
    monkeypatch.setattr("agent.ec_skills.browser_node.runner.reset_bu_agent_for_next_round",
                        lambda *a, **k: None)
    first = _acquire("test:alive_session", keep_alive=True)
    second = _acquire("test:alive_session", keep_alive=True)
    assert second is first
    _bh.cached_bu_agents.pop("test:alive_session", None)


class _SettingsAgent(_FakeAgent):
    def __init__(self, task, llm, controller, **kw):
        super().__init__(task, llm, controller, **kw)
        self.llm = llm
        self.settings = SimpleNamespace(page_extraction_llm=llm)   # browser-use's default


def test_reused_agent_extracts_with_this_runs_model(monkeypatch):
    """2026-11-15 eBay research: extract kept the first run's model, whose
    cancellation event was set when that run ended, so every extract was cancelled."""
    monkeypatch.setattr("agent.ec_skills.browser_node.runner.reset_bu_agent_for_next_round",
                        lambda *a, **k: None)

    def acquire(llm):
        return asyncio.run(acquire_or_reuse_local_agent(
            AgentClass=_SettingsAgent, task="t", llm=llm, controller=None,
            agent_kwargs={"keep_alive": True}, bu_scope_key="test:extract_llm",
            cached_bu_agents=_bh.cached_bu_agents, loop_history_mode="clear",
            fp_profile=None, browser_session=None))

    first_llm, second_llm = object(), object()
    first = acquire(first_llm)
    second = acquire(second_llm)
    assert second is first
    assert second.llm is second_llm and second.settings.page_extraction_llm is second_llm
    _bh.cached_bu_agents.pop("test:extract_llm", None)
