"""mt028 — text-baseline + typed-text guard for front-desk dom-echo.

Live flood test 2026-05-22 13:46 cascaded 客户16/18/19 into 3-5 wasted
dispatches each because yesterday's bot reply text was still in their
chat DOM after process restart.  The in-memory dom-echo ledgers
(``auto_dispatch_last_agent_reply``, ``recent_agent_replies_by_customer``)
were empty for the fresh process, so PreDispatch dispatched the stale
reply text as today's customer question.  The bot replied to its own
yesterday-reply, supersede fired, more dispatches went out, cascade.

Fix: mt028 extends mt021's msg_id baseline + mt024's typed-msg-id set
to also track TEXT:

  * ``_BASELINE_AGENT_TEXT`` — set on first scrape per customer
    alongside ``_BASELINE_AGENT_MSG_ID``
  * ``_TYPED_AGENT_TEXTS`` — no-TTL per-customer set of agent-bubble
    texts WE typed (registered on every verified send)

Both consulted by:
  * frontdesk_dispatch.py supersede / inflight-echo guards
  * pre_dispatch_enrich.py pre-scrape dom-echo guards
"""
from __future__ import annotations

import unittest

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_intervention as _hi,
)


CUST = "客户16"


class BaselineTextTests(unittest.TestCase):
    def setUp(self) -> None:
        _hi._BASELINE_AGENT_TEXT.clear()

    def tearDown(self) -> None:
        _hi._BASELINE_AGENT_TEXT.clear()

    def test_get_returns_empty_when_unset(self) -> None:
        self.assertEqual("", _hi.get_baseline_text(CUST))

    def test_set_then_get_roundtrip(self) -> None:
        _hi.set_baseline_text(CUST, "您好，男装XL码一般适合身高178-182cm")
        self.assertEqual(
            "您好，男装XL码一般适合身高178-182cm",
            _hi.get_baseline_text(CUST),
        )

    def test_set_per_customer_isolation(self) -> None:
        _hi.set_baseline_text(CUST, "A")
        _hi.set_baseline_text("客户18", "B")
        self.assertEqual("A", _hi.get_baseline_text(CUST))
        self.assertEqual("B", _hi.get_baseline_text("客户18"))

    def test_set_empty_key_is_noop(self) -> None:
        _hi.set_baseline_text("", "anything")
        self.assertEqual("", _hi.get_baseline_text(""))


class TypedTextTests(unittest.TestCase):
    def setUp(self) -> None:
        _hi._TYPED_AGENT_TEXTS.clear()
        _hi._TYPED_AGENT_TEXTS_ORDER.clear()

    def tearDown(self) -> None:
        _hi._TYPED_AGENT_TEXTS.clear()
        _hi._TYPED_AGENT_TEXTS_ORDER.clear()

    def test_unrecorded_text_is_unknown(self) -> None:
        self.assertFalse(_hi.is_known_typed_text(CUST, "您好，男装XL码"))

    def test_record_then_check_roundtrip(self) -> None:
        _hi.record_typed_text(CUST, "您好，男装XL码一般适合身高178-182cm")
        self.assertTrue(_hi.is_known_typed_text(
            CUST, "您好，男装XL码一般适合身高178-182cm",
        ))

    def test_per_customer_isolation(self) -> None:
        _hi.record_typed_text(CUST, "Reply A")
        self.assertFalse(_hi.is_known_typed_text("客户99", "Reply A"))

    def test_whitespace_trimmed_on_compare(self) -> None:
        _hi.record_typed_text(CUST, "  trimmed  ")
        self.assertTrue(_hi.is_known_typed_text(CUST, "trimmed"))
        self.assertTrue(_hi.is_known_typed_text(CUST, "  trimmed  "))

    def test_dup_record_no_growth(self) -> None:
        for _ in range(5):
            _hi.record_typed_text(CUST, "same text")
        self.assertEqual(1, len(_hi._TYPED_AGENT_TEXTS[CUST]))
        self.assertEqual(1, len(_hi._TYPED_AGENT_TEXTS_ORDER[CUST]))

    def test_cap_evicts_oldest(self) -> None:
        cap = _hi._TYPED_AGENT_TEXTS_CAP
        for i in range(cap + 5):
            _hi.record_typed_text(CUST, f"text-{i}")
        for i in range(5):
            self.assertFalse(_hi.is_known_typed_text(CUST, f"text-{i}"))
        for i in range(5, cap + 5):
            self.assertTrue(_hi.is_known_typed_text(CUST, f"text-{i}"))

    def test_empty_inputs_safe(self) -> None:
        _hi.record_typed_text("", "x")
        _hi.record_typed_text(CUST, "")
        _hi.record_typed_text("", "")
        self.assertFalse(_hi.is_known_typed_text(CUST, ""))


class Mt029PreRegistrationWiringTests(unittest.TestCase):
    """mt029 fix: placeholder send + direct-delivery pre-register the
    text in the no-TTL typed-text set BEFORE the feige_send_message
    await.  Without this, a CancelledError during the await (supersede
    or stale_reply) leaves the bubble in the DOM but Python state
    unrecorded → mt017 mis-fires on the next scrape.

    Also: mt017 detection (pre_dispatch_enrich) consults
    is_known_typed_text as a back-stop to is_known_typed_msg_id."""

    def test_runner_placeholder_pre_registers_text(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
        # The pre-registration must be present in the placeholder send
        # code path (search for the mt029 marker + the call)
        self.assertIn("mt029", src)
        self.assertIn("record_typed_text(customer_key, text)", src)
        # The pre-registration must come BEFORE the await on send
        ph_idx = src.find("await _ph_invoke(_send_fn, _send_params)")
        pre_idx = src.find("record_typed_text(customer_key, text)")
        self.assertGreater(ph_idx, 0)
        self.assertGreater(pre_idx, 0)
        self.assertLess(
            pre_idx, ph_idx,
            "placeholder pre-registration must come BEFORE the send await"
        )

    def test_runner_direct_delivery_pre_registers_text(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
        # The direct-delivery pre-record path should also register
        # via record_typed_text (alongside remember_agent_reply)
        idx = src.find("Pre-recorded last_agent_reply")
        self.assertGreater(idx, 0)
        body = src[idx : idx + 2000]
        self.assertIn("record_typed_text(", body)
        self.assertIn("_customer_name, _response_text", body)

    def test_pre_dispatch_enrich_mt017_consults_typed_text(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        # mt017 detection must check is_known_typed_text in addition
        # to is_known_typed_msg_id, so a cancelled-mid-flight placeholder
        # (text in DOM but msg_id never recorded) is still recognised
        # as ours by text.
        self.assertIn("is_known_typed_text(customer_key, _lab_text)", src)


class SourceWiringTests(unittest.TestCase):
    """Confirm the new helpers are wired into the dom-echo paths
    that need them (front-desk + pre-dispatch enrich + extension
    tools service)."""

    def test_pre_dispatch_enrich_calls_set_baseline_text(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        # The baseline TEXT must be set alongside the baseline MSG_ID
        self.assertIn("set_baseline_text(customer_key, _lab_text)", src)

    def test_pre_dispatch_enrich_consults_baseline_in_dom_echo(self) -> None:
        from pathlib import Path
        src = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
        ).read_text(encoding="utf-8")
        self.assertIn("get_baseline_text(customer_key)", src)
        self.assertIn("is_known_typed_text(customer_key", src)
        self.assertIn("baseline_text_pre_scrape", src)
        self.assertIn("typed_text_pre_scrape", src)

    def test_frontdesk_dispatch_consults_baseline_in_supersede(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_skills/node_runtime/frontdesk_dispatch.py").read_text(encoding="utf-8")
        self.assertIn("get_baseline_text(customer_key)", src)
        self.assertIn("is_known_typed_text(customer_key", src)
        self.assertIn("inflight baseline-text", src)
        self.assertIn("inflight typed-text", src)

    def test_extension_tools_records_typed_text(self) -> None:
        from pathlib import Path
        src = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/site_tools.py").read_text(encoding="utf-8")
        self.assertIn("record_typed_text(", src)
        self.assertIn("_verified_text", src)


if __name__ == "__main__":
    unittest.main()
