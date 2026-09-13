"""Per-pod concurrency in cn_serve.serve().

Why this file exists: `serve()` was `async for item: await handler(item)` —
strictly sequential. A turn is mostly spent awaiting an LLM, so a pod running
one at a time is idle for nearly all of its billed life, and serving N
concurrent conversations needs N pods. At 256 peak that is 256 pods against
roughly 8. The first test here fails outright against the sequential version.

Run: python -m pytest tests/test_serve_concurrency.py -q
"""
from __future__ import annotations

import asyncio

from agent.cloud_worker.cn_serve import Capacity, serve


async def _feed(items):
    for item in items:
        yield item


def _run(coro):
    return asyncio.run(coro)


def test_turns_run_concurrently_up_to_capacity():
    """Four turns, capacity 4, each 'awaiting an LLM' for 100ms.

    Sequential would take ~400ms. Concurrent takes ~100ms. The assertion is on
    observed overlap rather than wall clock alone, so a slow machine cannot make
    it pass for the wrong reason.
    """
    peak = 0
    current = 0

    async def handler(_item):
        nonlocal peak, current
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.1)          # stands in for the LLM call
        current -= 1

    stats = _run(serve(
        _feed(["a", "b", "c", "d"]),
        handler=handler,
        install_context=False,
        allow_ephemeral=True,
        capacity=Capacity(4),
    ))

    assert stats.completed == 4
    assert peak > 1, f"turns did not overlap (peak={peak}) — serve() is still sequential"
    assert peak <= 4


def test_concurrency_is_bounded_by_capacity():
    """Capacity 2 with 6 items must never have 3 in flight."""
    peak = 0
    current = 0

    async def handler(_item):
        nonlocal peak, current
        current += 1
        peak = max(peak, current)
        await asyncio.sleep(0.05)
        current -= 1

    stats = _run(serve(
        _feed([str(i) for i in range(6)]),
        handler=handler,
        install_context=False,
        allow_ephemeral=True,
        capacity=Capacity(2),
    ))

    assert stats.completed == 6
    assert peak <= 2, f"exceeded the advertised bound (peak={peak})"


def test_one_failing_turn_does_not_stop_the_others():
    """Per-item isolation has to survive the move to concurrency."""
    async def handler(item):
        await asyncio.sleep(0.01)
        if item == "bad":
            raise RuntimeError("boom")

    stats = _run(serve(
        _feed(["ok", "bad", "ok"]),
        handler=handler,
        install_context=False,
        allow_ephemeral=True,
        capacity=Capacity(3),
    ))

    assert stats.completed == 2
    assert stats.failed == 1


def test_serve_drains_inflight_turns_before_returning():
    """A turn accepted must finish — draining, not abandoning, on exit.

    Without the gather() in the finally block these tasks would be orphaned and
    the pod would report turns it never actually completed.
    """
    done = []

    async def handler(item):
        await asyncio.sleep(0.05)
        done.append(item)

    stats = _run(serve(
        _feed(["a", "b", "c"]),
        handler=handler,
        install_context=False,
        allow_ephemeral=True,
        capacity=Capacity(3),
    ))

    assert sorted(done) == ["a", "b", "c"]
    assert stats.completed == 3


def test_capacity_accounting():
    c = Capacity(2)
    assert c.free()
    c.take(); c.take()
    assert not c.free(), "capacity must refuse a third slot"
    c.give()
    assert c.free()
    c.give(); c.give()          # over-release must not go negative
    assert c.in_use == 0
    assert Capacity(0).limit == 1, "a zero/None limit must floor at 1, not deadlock"


# --- graceful shutdown -----------------------------------------------------

def test_shutdown_stops_accepting_but_finishes_in_flight():
    """SIGTERM means: stop claiming NOW, finish what you already hold.

    Without this the pod is killed mid-turn and the customer waits ~120s for the
    server's reaper to notice a stale heartbeat.
    """
    from agent.cloud_worker.cn_serve import Shutdown

    shutdown = Shutdown()
    started, finished = [], []

    async def handler(item):
        started.append(item)
        # Ask to stop while the first turn is still running.
        shutdown.request()
        await asyncio.sleep(0.05)
        finished.append(item)

    stats = _run(serve(
        _feed(["a", "b", "c"]),
        handler=handler,
        install_context=False,
        allow_ephemeral=True,
        capacity=Capacity(1),
        shutdown=shutdown,
    ))

    assert started == ["a"], f"kept accepting after shutdown: {started}"
    assert finished == ["a"], "abandoned an in-flight turn instead of draining it"
    assert stats.completed == 1


def test_fleet_intake_stops_claiming_on_shutdown():
    """The intake must stop CLAIMING immediately — a turn claimed by a dying pod
    is a turn nobody else can take until the reaper frees it."""
    from agent.cloud_worker.cn_serve import Shutdown, fleet_intake

    shutdown = Shutdown()
    claims = []

    class _Fleet:
        async def heartbeat_vehicle(self):
            return {}

        async def claim_turn(self):
            claims.append(1)
            return {"id": f"t{len(claims)}", "conversationId": "c", "input": "hi"}

    async def drive():
        got = []
        async for item in fleet_intake(_Fleet(), poll_interval=0.01, shutdown=shutdown):
            got.append(item)
            shutdown.request()          # stop after the first
        return got

    got = _run(drive())
    assert len(got) == 1, f"claimed {len(got)} turns after shutdown was requested"
