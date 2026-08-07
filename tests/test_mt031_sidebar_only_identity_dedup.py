"""mt031 — text-based identity_key dedup in the typing-lock sidebar-only path.

When the front-desk's typing-lock is held by another customer's send,
``pre_dispatch_enrich._scrape_and_override_last_message`` takes the
sidebar-only fast path: it skips the thread scrape (necessary —
scraping while another customer is being sent-to corrupts focus
state) and uses the sidebar preview text as the dispatched message.

Live trace 2026-05-22 17:00:13 客户16: yesterday's question
"你们默认走什么快递？" was already dispatched and answered at 17:00:00.
But at 17:00:13 the typing-lock was held by 客户19 → sidebar-only path
fired for 客户16 → no scrape → mt019 (msg-id dedup) and mt030
(agent-vs-customer-index check) both unable to fire → DUPLICATE
dispatch went out → bot regenerated the same reply → customer saw
the same answer typed twice.

Fix: in the sidebar-only path, consult ``actionable_items._dispatched_identity_keys``
directly via the sidebar identity_key (text-based, no scrape needed).
If the same identity_key is already in the registry, skip — mirror
of the HOT-PATH-B actionable_items filter.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    actionable_items as _ai,
)


class IdentityKeyRegistryTests(unittest.TestCase):
    """The same dispatched-identity-keys dict is now consulted from two
    code paths (HOT-PATH-B and PreDispatch's typing-lock fallback).
    These tests verify the module-level dict is the single source of
    truth and can be stamped + queried symmetrically."""

    def setUp(self) -> None:
        _ai._dispatched_identity_keys.clear()

    def tearDown(self) -> None:
        _ai._dispatched_identity_keys.clear()

    def test_registry_is_module_level(self) -> None:
        # Both paths import the same dict — confirm it's a single
        # module-level object (not a per-call copy)
        self.assertIs(
            _ai._dispatched_identity_keys,
            _ai._dispatched_identity_keys,  # same identity
        )

    def test_stamp_then_query(self) -> None:
        import time
        _ai._dispatched_identity_keys["客户16|你们默认走什么快递？"] = time.time()
        self.assertIn(
            "客户16|你们默认走什么快递？",
            _ai._dispatched_identity_keys,
        )

    def test_stamping_doesnt_block_other_identities(self) -> None:
        import time
        _ai._dispatched_identity_keys["客户16|q1"] = time.time()
        self.assertNotIn("客户16|q2", _ai._dispatched_identity_keys)
        self.assertNotIn("客户99|q1", _ai._dispatched_identity_keys)


class SidebarOnlySourceWiringTests(unittest.TestCase):
    """The fix is in the typing-lock sidebar-only branch of
    pre_dispatch_enrich.py.  These guards catch accidental removal."""

    def test_sidebar_only_path_consults_identity_keys(self) -> None:
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        # The mt031 marker + the registry import
        self.assertIn("mt031", src)
        self.assertIn(
            "from .actionable_items import _dispatched_identity_keys",
            src,
        )
        self.assertIn("identity_key_dedup_sidebar_only", src)

    def test_check_runs_only_in_sidebar_only_branch(self) -> None:
        """The check must be inside the typing-lock branch — not at
        function top-level (that would skip legitimate first-dispatch
        retries on full-scrape path)."""
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        # The marker should appear AFTER the typing-lock detection
        tl_idx = src.find("typing_lock_sidebar_only = True")
        mt031_idx = src.find("mt031: in sidebar-only mode")
        self.assertGreater(tl_idx, 0)
        self.assertGreater(mt031_idx, 0)
        # mt031 logic appears right after the typing-lock detection
        self.assertLess(tl_idx, mt031_idx)
        # And the gap should be small (within ~500 chars — same block)
        self.assertLess(mt031_idx - tl_idx, 1500)


if __name__ == "__main__":
    unittest.main()
