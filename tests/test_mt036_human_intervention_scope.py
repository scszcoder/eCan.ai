"""mt036 — two coordinated fixes for the human_intervention_skip
false-positives that kept dropping legitimate bot replies in the
customer's mt035 run.

Background
----------
Customer 2026-05-24 11:34 trace (packet 能不能包邮):

  11:34:21  HUMAN-INTERVENTION cust='packet' msg_id=...673c40e5
            (mark fired because an agent bubble in the scrape was
             not recognised as one of our typed bubbles)
  11:34:41  ⛔ direct_feige_send_skipped_human_handled
            Generation A's perfectly-good reply DISCARDED
  11:39:32  re-dispatched (5 min wait)
  11:39:57  Generation B regenerated
  11:39:58  finally typed

The 673c40e5 bubble was actually OUR own 11:33:59 reply
"可以的，今天下单一般会尽快安排发货.\\n优惠这边需要看具体是哪一款衣服..."
— but ``record_typed_text`` stored it with ``.strip()`` only (preserving
the ``\\n``), and ``is_known_typed_text`` did exact-membership lookup
against the scraper's DOM text which has the ``\\n`` collapsed to
nothing.  Match failed → mark_handled fired → next legitimate reply
dropped via the 120 s blanket TTL.

Two fixes:

* **mt036A** — ``mark_handled`` records ``(customer, question_msg_id)``
  in a new scoped registry.  New ``is_question_handled`` check is used
  by the direct-delivery hot path; a mark for question X only drops a
  reply targeting X — replies for newer questions Y/Z proceed.  The
  Stage -1 blanket dispatch-time check in ``pre_dispatch_enrich`` is
  retired so dispatches keep flowing; correctness moves to
  delivery-time.

* **mt036B** — ``record_typed_text`` also stores a whitespace-stripped
  form (matching ``dispatch_state.normalize_reply_text``'s mt034 shape);
  ``is_known_typed_text`` matches against either form so the scraper's
  newline-collapsed DOM text finds the recorded reply.  This stops
  most mt017 false positives at the source.
"""
from __future__ import annotations

import re
import time
import unittest
from pathlib import Path

from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
    human_intervention as _hi,
)


# -----------------------------------------------------------------------
# mt036A — scoped mark_handled / is_question_handled
# -----------------------------------------------------------------------


class ScopedMarkTests(unittest.TestCase):
    """``mark_handled`` accepts ``question_msg_id`` and records into a
    scoped registry; ``is_question_handled`` returns True only for that
    specific question."""

    CUST = "packet_test"
    QID_A = "9034feca-question-A"
    QID_B = "f0f0f0f0-question-B"

    def setUp(self) -> None:
        _hi.clear(self.CUST)

    def tearDown(self) -> None:
        _hi.clear(self.CUST)

    def test_mark_with_question_then_query_same_question(self) -> None:
        _hi.mark_handled(
            self.CUST,
            "agent_msg_id_xyz",
            source="test",
            question_msg_id=self.QID_A,
        )
        self.assertTrue(_hi.is_question_handled(self.CUST, self.QID_A))

    def test_mark_for_A_does_NOT_block_B(self) -> None:
        """Core mt036A guarantee: mark on question A doesn't suppress
        bot replies to question B.  Pre-mt036A this was the bug."""
        _hi.mark_handled(
            self.CUST,
            "agent_bubble",
            source="test",
            question_msg_id=self.QID_A,
        )
        self.assertTrue(_hi.is_question_handled(self.CUST, self.QID_A))
        self.assertFalse(_hi.is_question_handled(self.CUST, self.QID_B))

    def test_blanket_still_works_for_legacy_callers(self) -> None:
        """The old is_handled_recent stays for callers that don't have
        a question_msg_id (observability, etc.).  It still flips True
        on any mark."""
        _hi.mark_handled(
            self.CUST,
            "agent_bubble",
            source="test",
            question_msg_id=self.QID_A,
        )
        self.assertTrue(_hi.is_handled_recent(self.CUST))

    def test_empty_question_id_returns_false(self) -> None:
        _hi.mark_handled(
            self.CUST,
            "agent_bubble",
            source="test",
            question_msg_id=self.QID_A,
        )
        self.assertFalse(_hi.is_question_handled(self.CUST, ""))
        self.assertFalse(_hi.is_question_handled(self.CUST, "   "))

    def test_empty_customer_returns_false(self) -> None:
        self.assertFalse(_hi.is_question_handled("", self.QID_A))

    def test_clear_drops_scoped_entries_too(self) -> None:
        _hi.mark_handled(
            self.CUST,
            "agent_bubble",
            source="test",
            question_msg_id=self.QID_A,
        )
        self.assertTrue(_hi.is_question_handled(self.CUST, self.QID_A))
        _hi.clear(self.CUST)
        self.assertFalse(_hi.is_question_handled(self.CUST, self.QID_A))
        self.assertFalse(_hi.is_handled_recent(self.CUST))

    def test_mark_without_question_id_works_as_before(self) -> None:
        # Backwards compat: callers that don't pass question_msg_id
        # only update the blanket _HUMAN_HANDLED_AT entry.  The scoped
        # check returns False — there's no question to scope to.
        _hi.mark_handled(self.CUST, "agent_bubble", source="legacy")
        self.assertTrue(_hi.is_handled_recent(self.CUST))
        self.assertFalse(_hi.is_question_handled(self.CUST, self.QID_A))


# -----------------------------------------------------------------------
# mt036B — whitespace-stripped is_known_typed_text
# -----------------------------------------------------------------------


class WhitespaceStrippedTypedTextTests(unittest.TestCase):
    """``record_typed_text`` stores both the legacy strip-only form and
    the whitespace-stripped form; ``is_known_typed_text`` matches against
    either.  This fixes the customer trace where the bot's recorded text
    contained ``\\n`` between paragraphs but the DOM scraper saw it
    without any whitespace at the line break."""

    CUST = "packet_test"

    def setUp(self) -> None:
        # Reset the customer's typed-text registry to a clean state.
        with _hi._LOCK:
            _hi._TYPED_AGENT_TEXTS.pop(self.CUST, None)
            _hi._TYPED_AGENT_TEXTS_ORDER.pop(self.CUST, None)

    def tearDown(self) -> None:
        with _hi._LOCK:
            _hi._TYPED_AGENT_TEXTS.pop(self.CUST, None)
            _hi._TYPED_AGENT_TEXTS_ORDER.pop(self.CUST, None)

    def test_multiline_reply_matched_by_collapsed_scrape(self) -> None:
        """The live trace text: bot stored with newlines, scraper
        returns it with newlines stripped → must still match."""
        bot_text = (
            "可以的，今天下单一般会尽快安排发货。\n"
            "优惠这边需要看具体是哪一款衣服，您把商品链接、图片或货号"
            "发我，我帮您确认有没有活动和优惠。"
        )
        scraper_text = (
            "可以的，今天下单一般会尽快安排发货。"
            "优惠这边需要看具体是哪一款衣服，您把商品链接、图片或货号"
            "发我，我帮您确认有没有活动和优惠。"
        )
        _hi.record_typed_text(self.CUST, bot_text)
        self.assertTrue(_hi.is_known_typed_text(self.CUST, scraper_text))

    def test_legacy_exact_match_still_works(self) -> None:
        bot_text = "hello world"
        _hi.record_typed_text(self.CUST, bot_text)
        self.assertTrue(_hi.is_known_typed_text(self.CUST, bot_text))

    def test_unrelated_text_does_not_match(self) -> None:
        _hi.record_typed_text(self.CUST, "我说的是A")
        self.assertFalse(_hi.is_known_typed_text(self.CUST, "我说的是B"))

    def test_internal_spaces_also_stripped(self) -> None:
        """The whitespace-strip normalisation matches mt034's:
        ALL whitespace (spaces, newlines, tabs) is removed."""
        _hi.record_typed_text(self.CUST, "hello   world\n\nfoo")
        # Scraper might collapse all of that to "helloworldfoo".
        self.assertTrue(_hi.is_known_typed_text(self.CUST, "helloworldfoo"))

    def test_empty_strings_safe(self) -> None:
        # record/check with empty input must not raise.
        _hi.record_typed_text(self.CUST, "")
        _hi.record_typed_text(self.CUST, "   ")
        self.assertFalse(_hi.is_known_typed_text(self.CUST, ""))


# -----------------------------------------------------------------------
# Source-level wiring tests
# -----------------------------------------------------------------------


class WiringTests(unittest.TestCase):
    """Catch accidental removal of the mt036 changes in future
    refactors by checking the source files for the marker strings."""

    PRE_DISPATCH_SRC = Path(
        "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
    ).read_text(encoding="utf-8")
    RUNNER_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
    HI_SRC = Path(
        "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py"
    ).read_text(encoding="utf-8")

    def test_mark_site_passes_question_msg_id(self) -> None:
        # pre_dispatch_enrich.py mark site now passes question_msg_id.
        self.assertIn("question_msg_id=_question_msg_id_for_mark", self.PRE_DISPATCH_SRC)
        self.assertIn("mt036A", self.PRE_DISPATCH_SRC)

    def test_runner_uses_is_question_handled(self) -> None:
        self.assertIn("is_question_handled", self.RUNNER_SRC)
        self.assertIn("mt036A", self.RUNNER_SRC)
        # And the legacy is_handled_recent call is GONE from the
        # direct-delivery branch.
        # (the only is_handled_recent reference allowed in runner.py
        # would be in a comment or unrelated path)
        # Specifically: the line that does the actual check at the
        # direct-delivery site uses is_question_handled.
        m = re.search(
            r"_hi_dd\.is_question_handled\(\s*_customer_name,\s*_hi_target_qid",
            self.RUNNER_SRC,
        )
        self.assertIsNotNone(m, "direct-delivery must call is_question_handled")

    def test_stage_minus1_check_neutralised(self) -> None:
        # The old blanket is_handled_recent return EnrichResult(skip=True)
        # is replaced by a pass/no-op so dispatches proceed.
        # Anchor: the comment marker
        self.assertIn(
            "Post-mt036A: REMOVED at this stage",
            self.PRE_DISPATCH_SRC,
        )

    def test_human_intervention_module_exports_new_api(self) -> None:
        self.assertIn('"is_question_handled"', self.HI_SRC)
        # The new dict that backs the scoped check
        self.assertIn("_HANDLED_QUESTIONS", self.HI_SRC)

    def test_record_typed_text_stores_normalised_form(self) -> None:
        self.assertIn("_normalize_for_typed_text", self.HI_SRC)
        self.assertIn("mt036B", self.HI_SRC)


# -----------------------------------------------------------------------
# Integration-ish: emulate the customer's exact 11:34 dropped-reply
# scenario at the human_intervention API surface.
# -----------------------------------------------------------------------


class CustomerTraceReplayTests(unittest.TestCase):
    """Replay the 2026-05-24 11:34 packet scenario at the
    human_intervention API surface: mark fires on agent bubble that
    *was actually ours*, and the bot's reply targets question A which
    *did not get marked*."""

    CUST = "packet_test_replay"
    PACKET_BAOYOU_QID = "9034feca-question-A"
    SOME_OTHER_QID = "f0f0f0f0-question-B"  # newer question

    def setUp(self) -> None:
        _hi.clear(self.CUST)
        with _hi._LOCK:
            _hi._TYPED_AGENT_TEXTS.pop(self.CUST, None)
            _hi._TYPED_AGENT_TEXTS_ORDER.pop(self.CUST, None)

    def tearDown(self) -> None:
        _hi.clear(self.CUST)
        with _hi._LOCK:
            _hi._TYPED_AGENT_TEXTS.pop(self.CUST, None)
            _hi._TYPED_AGENT_TEXTS_ORDER.pop(self.CUST, None)

    def test_mt036B_prevents_misfire_when_bubble_was_ours(self) -> None:
        """The original 11:33:59 bot reply (with \\n) was recorded.
        When the scraper's DOM extraction (no newline) is later
        checked, mt036B finds the match → mark_handled would NOT
        misfire in the first place."""
        bot_text = (
            "可以的，今天下单一般会尽快安排发货。\n"
            "优惠这边需要看具体是哪一款衣服..."
        )
        _hi.record_typed_text(self.CUST, bot_text)
        scraper_text = (
            "可以的，今天下单一般会尽快安排发货。"
            "优惠这边需要看具体是哪一款衣服..."
        )
        self.assertTrue(_hi.is_known_typed_text(self.CUST, scraper_text))

    def test_mt036A_prevents_drop_even_if_mark_misfired(self) -> None:
        """Belt-and-braces: even if mt036B's text match still missed
        (e.g. text changed enough), mt036A's scoping means a mark
        keyed against question A doesn't drop the bot's reply to
        question B."""
        _hi.mark_handled(
            self.CUST,
            "some_agent_bubble",
            source="thread_scrape",
            question_msg_id=self.PACKET_BAOYOU_QID,
        )
        # Bot's reply to a NEWER question — should NOT be dropped.
        self.assertFalse(
            _hi.is_question_handled(self.CUST, self.SOME_OTHER_QID),
        )
        # The original question IS marked.
        self.assertTrue(
            _hi.is_question_handled(self.CUST, self.PACKET_BAOYOU_QID),
        )


if __name__ == "__main__":
    unittest.main()
