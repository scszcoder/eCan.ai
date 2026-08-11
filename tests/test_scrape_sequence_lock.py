"""mt027 (Tier 4) — scrape_sequence_lock serialises concurrent scrapes.

This is the lock that makes the parallel ``asyncio.gather`` over
``_dispatch_one_item`` (re-introduced after mt025 revert) safe:
without it, concurrent scrapes interleave their CDP click+verify
evaluates and the LAST click wins focus, breaking everyone else's
verify_customer_match (the 21:29:06 mt025-revert trace).

These tests don't stand up a real browser — they call
``scrape_sequence_lock`` directly and verify the documented semantics:
  * Same browser_session → same lock object → serialises
  * Different browser_sessions → different locks → don't block each other
  * Lock survives across acquires (no leak even on exception)
"""
from __future__ import annotations

import asyncio
import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dom_assets,
)


class _FakeSession:
    """Hashable, identity-distinct object that stands in for a real
    browser_session.  The lock keys by ``id(browser_session)`` so any
    object with a stable identity is fine."""
    pass


class ScrapeSequenceLockTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # Lock dict is module-level; clear so tests don't bleed into each other
        dom_assets._SCRAPE_SEQUENCE_LOCKS.clear()

    def tearDown(self) -> None:
        dom_assets._SCRAPE_SEQUENCE_LOCKS.clear()

    async def test_same_session_returns_same_lock(self) -> None:
        s = _FakeSession()
        lock_a = dom_assets.scrape_sequence_lock(s)
        lock_b = dom_assets.scrape_sequence_lock(s)
        self.assertIs(lock_a, lock_b)

    async def test_different_sessions_get_different_locks(self) -> None:
        s1 = _FakeSession()
        s2 = _FakeSession()
        self.assertIsNot(
            dom_assets.scrape_sequence_lock(s1),
            dom_assets.scrape_sequence_lock(s2),
        )

    async def test_concurrent_acquirers_serialise(self) -> None:
        """Two parallel coroutines acquiring the same lock must run
        their critical sections sequentially.  We instrument a counter
        that should never see overlap if serialised."""
        s = _FakeSession()
        lock = dom_assets.scrape_sequence_lock(s)
        active = 0
        max_active = 0
        ran = 0

        async def critical_section():
            nonlocal active, max_active, ran
            async with lock:
                active += 1
                max_active = max(max_active, active)
                # Brief work so concurrent attempts have time to pile up
                await asyncio.sleep(0.05)
                active -= 1
                ran += 1

        await asyncio.gather(*(critical_section() for _ in range(5)))
        self.assertEqual(5, ran)
        # If the lock works, only one coroutine is in the section at a time
        self.assertEqual(1, max_active)

    async def test_lock_releases_on_exception(self) -> None:
        """An exception inside the critical section must release the
        lock so the next acquirer isn't blocked forever."""
        s = _FakeSession()
        lock = dom_assets.scrape_sequence_lock(s)

        async def raises():
            async with lock:
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            await raises()
        # Subsequent acquire must succeed within a reasonable time
        try:
            async with asyncio.timeout(1.0):
                async with lock:
                    pass
        except AttributeError:
            # asyncio.timeout requires Python 3.11+; fall back
            await asyncio.wait_for(_take_lock(lock), timeout=1.0)


async def _take_lock(lock) -> None:
    async with lock:
        pass


class SourceWiringTests(unittest.TestCase):
    """Confirm the source code calls scrape_sequence_lock in
    scrape_latest_customer_bubble.  A future refactor that removes the
    lock call would silently re-introduce the mt024 focus race; this
    guard catches that."""

    def test_scrape_function_acquires_lock(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
        ).read_text(encoding="utf-8")
        # The lock must be acquired (async with) BEFORE the FEIGE_CLICK
        # JS eval inside scrape_latest_customer_bubble.
        self.assertIn("scrape_sequence_lock(browser_session)", src)
        self.assertIn("[FEIGE-SCRAPE-LOCK]", src)
        # The locked body helper exists
        self.assertIn("def _scrape_locked_body(", src)


if __name__ == "__main__":
    unittest.main()
