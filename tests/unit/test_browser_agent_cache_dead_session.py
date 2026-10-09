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
