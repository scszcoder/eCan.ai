"""mt030 — skip dispatch when agent bubble is more recent than the
latest customer bubble (i.e. the customer's last question has already
been answered).

Live trace 2026-05-22 16:06:37 客户18:
    customer bubble msg_id=mphi3s5y text='你们默认走什么快递？'
    latest agent bubble msg_id=mphi6dfv text='您好，我们默认一般是走中通快递哦...'

Both bubbles were from a prior session.  The fresh process had no
``customer_last_dispatched_msg_id`` for 客户18, so the existing mt019
dedup didn't fire.  We dispatched yesterday's question; bot generated
reply about 快递; reply landed at the same moment the customer typed
a NEW unrelated question about 退款 → customer was confused.

Fix: scrape returns both customer-bubble index and agent-bubble index
(positions in the chat-thread wrapper array, same monotonic order).
If ``agent.index > customer.index`` the agent already replied to the
latest customer question → skip dispatch.  Stateless and symmetric:
works equally well for stale bubbles from prior sessions OR a reply
we just typed seconds ago.
"""
from __future__ import annotations

import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_intervention as _hi,
)


CUST = "客户18"


class CustomerBaselineApiTests(unittest.TestCase):
    """The customer-bubble baseline dict + API is in place even though
    the current mt030 implementation uses the index-comparison approach
    instead.  Kept for future code that may want to remember the
    per-process baseline customer msg_id (e.g. for "this exact
    question was dispatched once already, even if the agent reply
    failed")."""

    def setUp(self) -> None:
        _hi._BASELINE_CUSTOMER_MSG_ID.clear()

    def tearDown(self) -> None:
        _hi._BASELINE_CUSTOMER_MSG_ID.clear()

    def test_get_returns_empty_when_unset(self) -> None:
        self.assertEqual("", _hi.get_baseline_customer_msg_id(CUST))

    def test_set_then_get_roundtrip(self) -> None:
        _hi.set_baseline_customer_msg_id(CUST, "mphi3s5y")
        self.assertEqual("mphi3s5y", _hi.get_baseline_customer_msg_id(CUST))

    def test_per_customer_isolation(self) -> None:
        _hi.set_baseline_customer_msg_id(CUST, "A")
        _hi.set_baseline_customer_msg_id("客户99", "B")
        self.assertEqual("A", _hi.get_baseline_customer_msg_id(CUST))
        self.assertEqual("B", _hi.get_baseline_customer_msg_id("客户99"))


class IndexComparisonLogicTests(unittest.TestCase):
    """Mirror the comparison logic in pre_dispatch_enrich so we can
    exercise it without standing up the full scrape stack."""

    @staticmethod
    def should_skip(agent_index: int, customer_index: int) -> bool:
        """Mirror of the mt030 rule.  agent_index < 0 means no agent
        bubble was found (e.g. brand new chat) → never skip.
        customer_index < 0 should never happen if scrape succeeded;
        treat as "don't skip" to avoid false positives.
        """
        if agent_index < 0:
            return False
        if customer_index < 0:
            return False
        return agent_index > customer_index

    def test_skip_when_agent_after_customer(self) -> None:
        # 客户18 trace: customer bubble at index 5, agent reply at 6
        self.assertTrue(self.should_skip(6, 5))

    def test_dispatch_when_customer_after_agent(self) -> None:
        # Customer just typed a new question after our reply
        self.assertFalse(self.should_skip(5, 6))

    def test_dispatch_when_no_agent_bubble(self) -> None:
        # Brand-new chat, no prior reply
        self.assertFalse(self.should_skip(-1, 3))

    def test_dispatch_when_customer_index_unknown(self) -> None:
        # Scrape didn't return a usable index — be conservative, dispatch
        self.assertFalse(self.should_skip(5, -1))

    def test_dispatch_when_indices_equal(self) -> None:
        # Same wrapper can't be both customer and agent; degenerate
        # case — treat as "no agent more recent" → dispatch.
        self.assertFalse(self.should_skip(5, 5))


class JsAndPythonWiringTests(unittest.TestCase):
    """Confirm the JS returns ``index`` on latest_agent_bubble and the
    Python side surfaces it, and pre_dispatch_enrich consults it.
    Catches accidental removal in a future refactor."""

    def test_js_includes_agent_bubble_index(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
        ).read_text(encoding="utf-8")
        self.assertIn("index: ai,", src)
        self.assertIn("mt030", src)

    def test_python_surfaces_agent_bubble_index(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
        ).read_text(encoding="utf-8")
        # The Python-side dict that wraps the JS payload must include
        # the index field.
        idx = src.find('out["latest_agent_bubble"] = {')
        self.assertGreater(idx, 0)
        body = src[idx : idx + 800]
        self.assertIn('"index":', body)

    def test_pre_dispatch_enrich_checks_index_comparison(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        # The agent-after-customer check must be present
        self.assertIn("mt030", src)
        self.assertIn("_agent_index > _scraped_cust_index", src)
        self.assertIn("agent_already_replied", src)


if __name__ == "__main__":
    unittest.main()
