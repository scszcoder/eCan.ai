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
