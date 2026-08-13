"""mt023 #1: stale_reply ledger-clear unsticks customer after rejection.

Live trace 2026-05-22 08:19:23-08:22:34 (陆地飞鱼) — bot's outgoing
reply was rejected at delivery with ``stale_reply_source_msg_id``
because the customer had typed a follow-up bubble between dispatch and
delivery.  The customer's new bubble then sat un-answered for 173 s
because PreDispatch's recent-echo guard kept skipping with
``echo='您好，稍等一下哦~'`` — the placeholder text was still in the
``recent_agent_replies_by_customer`` ledger from the rejected turn.

Fix: when ``feige_send_message`` returns ``stale_reply_source_msg_id``,
the handler in ``extension_tools_service.py`` now calls
``dispatch_state.clear_recent_replies(customer)`` to wipe the orphan
placeholder so the next PreDispatch cycle can re-dispatch the
customer's new bubble normally.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    dispatch_state as _ds,
)


CUST = "陆地飞鱼"


class ClearRecentRepliesTests(unittest.TestCase):
    def setUp(self) -> None:
        _ds.recent_agent_replies_by_customer.clear()
        _ds.last_agent_reply_by_customer.clear()

    def tearDown(self) -> None:
        _ds.recent_agent_replies_by_customer.clear()
        _ds.last_agent_reply_by_customer.clear()

    def test_clear_drops_multi_slot_entries(self) -> None:
        _ds.remember_agent_reply(CUST, "您好，稍等一下哦~")
        _ds.remember_agent_reply(CUST, "您好，欢迎光临！请问您想咨询...")
        # Sanity: ledger now has hits for the recent texts
        self.assertTrue(_ds.matches_recent_agent_reply(CUST, "您好，稍等一下哦~"))
        _ds.clear_recent_replies(CUST)
        # After clear, neither text should match
        self.assertFalse(_ds.matches_recent_agent_reply(CUST, "您好，稍等一下哦~"))
        self.assertFalse(_ds.matches_recent_agent_reply(CUST, "您好，欢迎光临！请问您想咨询..."))

    def test_clear_drops_last_agent_reply_single_slot(self) -> None:
        _ds.remember_agent_reply(CUST, "您好，稍等一下哦~")
        # _fingerprint normalises the customer key, so look it up the same way
        self.assertIn(
            _ds._fingerprint(CUST, "x")[0],
            _ds.last_agent_reply_by_customer,
        )
        _ds.clear_recent_replies(CUST)
        self.assertNotIn(
            _ds._fingerprint(CUST, "x")[0],
            _ds.last_agent_reply_by_customer,
        )

    def test_clear_isolated_per_customer(self) -> None:
        other = "肽斯特"
        _ds.remember_agent_reply(CUST, "您好，稍等一下哦~")
        _ds.remember_agent_reply(other, "您好，稍等一下哦~")
        _ds.clear_recent_replies(CUST)
        self.assertTrue(_ds.matches_recent_agent_reply(other, "您好，稍等一下哦~"))
        self.assertFalse(_ds.matches_recent_agent_reply(CUST, "您好，稍等一下哦~"))

    def test_clear_empty_or_missing_safe(self) -> None:
        # Should not raise even with no prior data
        _ds.clear_recent_replies(CUST)
        _ds.clear_recent_replies("")
        _ds.clear_recent_replies(None)  # type: ignore[arg-type]


class HandlerCallsClearOnStaleReplyTests(unittest.TestCase):
    """Confirm the stale_reply branch in extension_tools_service.py is
    actually wired to call ``clear_recent_replies`` — a future refactor
    that drops the call will be caught here."""

    def test_handler_imports_dispatch_state(self) -> None:
        src = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/site_tools.py").read_text(encoding="utf-8")
        # Find the stale_reply branch
        idx = src.find('"stale_reply_source_msg_id" in str(err)')
        self.assertGreater(idx, 0)
        # The next 2 KB should contain the clear_recent_replies call
        body = src[idx : idx + 2048]
        self.assertIn("clear_recent_replies", body)
        self.assertIn("cancel_any_for_customer", body)


if __name__ == "__main__":
    unittest.main()
