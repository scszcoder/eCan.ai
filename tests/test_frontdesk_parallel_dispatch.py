"""mt026: REVERTED mt025 parallelisation; tests now guard the rollback.

mt025 wrapped the items loop in ``asyncio.gather`` to parallelise
per-item dispatch.  Live flood test (runlogs/eCan.log 21:29:06+)
showed the concurrent scrapes raced on sidebar focus: each item
clicks its customer's sidebar row, the LAST click wins, and every
other item's active-customer verification fails with
``active_customer_mismatch sidebar='客户18'(class-active)``.
Worse, the saturated browser session caused DIRECT-DELIVERY to hit
``tab_focus_timeout`` and drop 客户05 / 客户14 / 客户18's REAL
replies (``direct_delivery_requeue_exhausted``).

Rollback retains the ``[FEIGE-FRONTDESK-TIMING]`` markers (harmless)
and the asyncio.gather/return_exceptions/run_in_executor SIMULATION
tests (they prove the technique behaves the way the source comment
references) — but the source itself is back to serial.

A safe parallelisation requires a per-front-desk-tab scrape lock;
deferred until that's designed.
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
    """Confirm the source code stays on the SERIAL items-loop pattern
    until a future commit ships proper scrape-phase locking.  These
    asserts catch an accidental re-introduction of the unsafe parallel
    pattern that mt025 had to revert."""

    def test_run_with_lock_held_stays_serial(self) -> None:
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        # The serial pattern: a plain `for item in actionable:` followed
        # by `opened, assigned, failure = await _dispatch_one_item(...)`
        self.assertIn("for item in actionable:", src)
        self.assertIn("_dispatch_one_item(", src)
        # The unsafe parallel pattern (asyncio.gather over
        # _dispatch_one_item) MUST NOT be present.  Look for the
        # specific signature so the simulation test using gather in this
        # file doesn't false-positive.
        self.assertNotIn(
            "asyncio.gather(\n        *(\n            _dispatch_one_item(",
            src,
        )

    def test_send_chat_stays_synchronous(self) -> None:
        """run_in_executor wrapper would only help when paired with
        gather; with the serial loop reverted, send_chat is sync again.
        This guard catches accidental re-introduction of executor
        offloading without re-introducing the gather."""
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        # The await on run_in_executor for send_chat shouldn't be there
        self.assertNotIn("run_in_executor(\n                None, send_chat,", src)
        self.assertNotIn("await _send_loop.run_in_executor(", src)

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
