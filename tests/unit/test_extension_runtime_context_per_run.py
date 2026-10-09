"""Concurrent browser runs must each see their own agent / runtime context.

2026-10-09: three crawler agents ran at once; the runtime context was one
module global, so ChipCrawler3's bu_send_chat went out as ChipCrawler2.
"""
import asyncio

from agent.ec_skills.browser_use_extension import extension_tools_service as ets


def test_concurrent_runs_keep_their_own_context():
    async def run(agent_id, delay):
        ets.set_current_agent(agent_id)
        ets.set_current_runtime_context(agent_id=agent_id)
        await asyncio.sleep(delay)  # let the other run set its context meanwhile
        return ets.get_current_runtime_context()["agent_id"], ets.get_current_agent()

    async def main():
        return await asyncio.gather(run("crawler_2", 0.05), run("crawler_3", 0.01))

    assert asyncio.run(main()) == [("crawler_2", "crawler_2"), ("crawler_3", "crawler_3")]


def test_outside_a_run_falls_back_to_last_set():
    ets.set_current_runtime_context(agent_id="global_one")
    assert ets.get_current_runtime_context()["agent_id"] == "global_one"
