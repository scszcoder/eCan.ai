import asyncio

from bubus import BaseEvent, EventBus

from agent.ec_skills.browser_node.build_helpers import pending_browser_work


class SlowEvent(BaseEvent):
    pass


def test_a_stuck_start_names_where_the_event_bus_is_waiting():
    # 2026-11-27: store browser starts timed out after a restart and the log did not say
    # what start() was waiting for.
    async def run():
        async def handler(event):
            await asyncio.sleep(5)
        bus = EventBus()
        bus.on(SlowEvent, handler)
        bus.dispatch(SlowEvent())
        await asyncio.sleep(0.3)
        return pending_browser_work()

    assert "bubus/service.py" in asyncio.run(run())


def test_nothing_pending_says_none():
    async def run():
        return pending_browser_work()
    assert asyncio.run(run()) == "none"
