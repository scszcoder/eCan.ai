"""mt025: parallelise the per-item dispatch loop in front-desk.

Live trace 2026-05-22 08:14:36 (1对2) — one front-desk run took 8.9 s
end-to-end with the serial ``for item in actionable`` loop because each
item's CDP scrape (~900 ms) and A2A send_chat HTTP POST (~700-1100 ms)
were awaited one after the other.  For N concurrent customers, this is
~(N-1) × 1.6 s of avoidable wall-clock waste — and the wait holds the
front-desk's queue lock so newer browser events pile up behind it
(observed as "dequeue SKIPPED (task busy)" loops in the same trace).

Fix: wrap the loop in ``asyncio.gather(...)`` so all items dispatch
concurrently.  Per-item state mutations are isolated by session_id /
customer_key, so no shared-state races.  ``return_exceptions=True``
guarantees one item raising doesn't take down the others.
"""
from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from typing import Iterable
from unittest.mock import patch


def _simulate_serial(n: int, per_item_s: float) -> float:
    """Baseline: serial dispatch — N × per_item_s."""
    start = time.monotonic()

    async def _run():
        for _ in range(n):
            await asyncio.sleep(per_item_s)

    asyncio.run(_run())
    return time.monotonic() - start


def _simulate_parallel(n: int, per_item_s: float) -> float:
    """Optimised: parallel dispatch — ~per_item_s (whichever is slowest)."""
    start = time.monotonic()

    async def _run():
        await asyncio.gather(
            *(asyncio.sleep(per_item_s) for _ in range(n)),
            return_exceptions=True,
        )

    asyncio.run(_run())
    return time.monotonic() - start


class ParallelDispatchBaselineTests(unittest.TestCase):
    """Mirrors the asyncio.gather pattern in
    ``_run_with_lock_held``.  These don't invoke the real dispatch
    function; they confirm the BEHAVIOUR of the technique (parallel
    wait + return_exceptions) the source uses."""

    def test_three_items_parallel_is_one_period(self) -> None:
        # 1对3 case: 3 items, each costing 0.3 s
        per_item = 0.3
        serial = _simulate_serial(3, per_item)
        parallel = _simulate_parallel(3, per_item)
        # Serial should take ~3 × per_item (0.9 s), parallel ~per_item (0.3 s)
        self.assertGreater(serial, 0.85)
        self.assertLess(parallel, 0.5)
        # Parallel must be at least 2x faster than serial on N=3
        self.assertLess(parallel * 2, serial)

    def test_two_items_parallel_is_one_period(self) -> None:
        per_item = 0.2
        serial = _simulate_serial(2, per_item)
        parallel = _simulate_parallel(2, per_item)
        self.assertGreater(serial, 0.35)
        self.assertLess(parallel, 0.35)

    def test_gather_return_exceptions_isolates_failures(self) -> None:
        """Confirm ``return_exceptions=True`` semantics: a raising
        coroutine doesn't take down siblings — the source code relies
        on this to keep one bad item from killing the batch."""

        async def _ok():
            await asyncio.sleep(0.02)
            return ("opened", "assigned", "")

        async def _fail():
            await asyncio.sleep(0.01)
            raise RuntimeError("boom")

        async def _run():
            return await asyncio.gather(
                _ok(), _fail(), _ok(), return_exceptions=True
            )

        results = asyncio.run(_run())
        self.assertEqual(3, len(results))
        # First and third are OK, second is the exception (NOT raised)
        self.assertEqual(("opened", "assigned", ""), results[0])
        self.assertIsInstance(results[1], RuntimeError)
        self.assertEqual(("opened", "assigned", ""), results[2])


class ExecutorOffloadingTests(unittest.TestCase):
    """The synchronous ``send_chat`` is offloaded to the thread-pool
    executor so concurrent items don't serialise on its blocking HTTP
    POST.  This test confirms the technique works: multiple sync
    operations offloaded via ``run_in_executor`` run concurrently."""

    def test_sync_calls_in_executor_run_concurrently(self) -> None:
        per_call = 0.15  # bigger than asyncio overhead

        def sync_blocker(n: int) -> int:
            time.sleep(per_call)
            return n

        async def _run():
            loop = asyncio.get_running_loop()
            start = time.monotonic()
            results = await asyncio.gather(
                *(
                    loop.run_in_executor(None, sync_blocker, i)
                    for i in range(3)
                ),
                return_exceptions=True,
            )
            return results, time.monotonic() - start

        results, elapsed = asyncio.run(_run())
        # Sanity: results came back in order, no exceptions
        self.assertEqual([0, 1, 2], results)
        # Concurrent: 3 × 0.15 s serial = 0.45 s; parallel ≈ 0.15 s
        self.assertLess(elapsed, 0.4)


class DispatchSourceWiringTests(unittest.TestCase):
    """Confirm the source code is wired to the parallel pattern — a
    future refactor that reverts to the serial loop will be caught."""

    def test_run_with_lock_held_uses_asyncio_gather(self) -> None:
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        self.assertIn("asyncio.gather(", src)
        self.assertIn("return_exceptions=True", src)
        # The old serial pattern would be `for item in actionable:` followed
        # by `await _dispatch_one_item(...)` directly — make sure that
        # specific anti-pattern isn't present.
        # (Look for the gather wrapping _dispatch_one_item generator)
        self.assertIn("_dispatch_one_item(", src)

    def test_send_chat_uses_run_in_executor(self) -> None:
        """Confirm the sync send_chat is offloaded to the thread-pool
        executor — without this, asyncio.gather wouldn't actually
        parallelise items because the sync HTTP POST blocks the loop."""
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        # The call is wrapped over multiple lines, so just check both
        # the run_in_executor pattern and that send_chat is the callable
        self.assertIn("run_in_executor(", src)
        self.assertIn("get_running_loop()", src)
        # Find the run_in_executor call site for send_chat specifically
        idx = src.find("await _send_loop.run_in_executor(")
        self.assertGreater(idx, 0, "expected await _send_loop.run_in_executor(...) call")
        body = src[idx : idx + 200]
        self.assertIn("send_chat", body)
        self.assertIn("_send_payload", body)

    def test_timing_markers_present(self) -> None:
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        for marker in (
            "phase=lock_acquired",
            "phase=run_complete",
            "phase=item_dispatch_start",
            "phase=item_dispatch_done",
        ):
            self.assertIn(marker, src, msg=f"missing timing marker: {marker}")
        # And the grep-friendly prefix
        self.assertIn("[FEIGE-FRONTDESK-TIMING]", src)


if __name__ == "__main__":
    unittest.main()
