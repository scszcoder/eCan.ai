"""A finished run's agent must not stay pinned by the current-agent ContextVar.

2026-10-14 chip-docs crawl: anyio caches each event loop's root task in a WeakKeyDictionary
whose value references the loop, so loops (and their root tasks) are never freed. The
ContextVar value set in that root task's context kept every finished browser-use agent
alive — 70 of them, ~3 GB."""
import asyncio
import gc
import weakref

import anyio.to_thread

from agent.ec_skills.browser_use_extension import extension_tools_service as ets


class _Agent:
    pass


def _run_in_fresh_loop(clear: bool) -> weakref.ref:
    async def run():
        agent = _Agent()
        ets.set_current_agent(agent)
        await anyio.to_thread.run_sync(lambda: None)  # anyio caches this task as the loop's root task
        if clear:
            ets.clear_current_agent(agent)
        return weakref.ref(agent)

    loop = asyncio.new_event_loop()
    try:
        ref = loop.run_until_complete(run())
    finally:
        loop.close()
    del loop
    gc.collect()
    return ref


def test_agent_pinned_without_clear():
    # Documents the leak this fix addresses; if anyio stops leaking loops this can go.
    assert _run_in_fresh_loop(clear=False)() is not None


def test_cleared_agent_is_freed():
    assert _run_in_fresh_loop(clear=True)() is None


def test_clear_leaves_another_runs_agent_alone():
    mine, other = _Agent(), _Agent()
    ets.set_current_agent(other)
    ets.clear_current_agent(mine)
    assert ets.get_current_agent() is other
