"""mt037 — three coordinated fixes for the EventMonitor stuck-CDP
loop and the broken ``verified_msg_id`` capture path:

* **mt037A** — when ``EventMonitor.check_now()`` times out, the next
  iteration must use a FRESH CDP client.  Pre-mt037A the same stuck
  client was retried 5 consecutive times producing the 5×8s = 40 s
  detection-blackout cluster seen at the customer's 2026-05-24
  13:31:36-13:32:28 trace (packet's 能包邮 question wasn't even
  observed for 59 s).  The fix calls ``_cleanup_monitor_cdp`` from
  the TimeoutError branch so the next ``_get_monitor_cdp`` opens a
  new WebSocket + reattaches to the target.

* **mt037B** — lower the DOM-check timeout floor from 8.0 s to 5.0 s.
  Combined with A, max detection lag drops from 40+ s clusters to a
  single 5 s timeout before the CDP gets recycled.

* **mt037C** — rewrite ``latestAgentBubbleMsgId()`` in the
  ``feige_send_message`` JS to:
    (1) recognise agent bubbles via EITHER ``messageIsMe`` OR row
        ``flexDirection: row-reverse`` (the same dual-test the
        working dom_assets.py chat-thread scraper uses)
    (2) prefer the bubble whose text matches the ``text`` we just
        typed (whitespace-stripped, mt036B shape)
    (3) poll up to 5×100 ms for Feige's async ``data-id`` assignment
  Pre-mt037C the function returned '' for 57 of 57 sends in the
  customer's run, leaving ``record_typed_msg_id`` un-called.

The JS rewrite is hard to unit-test in isolation; these tests guard
the source structure to catch regressions.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path


EM_SRC = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")
ET_SRC = Path(
    "agent/ec_skills/browser_use_extension/extension_tools_service.py"
).read_text(encoding="utf-8")


# -----------------------------------------------------------------------
# mt037A — force-recycle CDP after TimeoutError
# -----------------------------------------------------------------------


class CDPRecycleOnTimeoutTests(unittest.TestCase):

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt037A", EM_SRC)

    def test_timeout_branch_calls_cleanup(self) -> None:
        # Locate the loop's TimeoutError branch and assert
        # _cleanup_monitor_cdp is called within it.
        loop_body = EM_SRC[EM_SRC.find("async def _run_loop"):]
        timeout_branch_start = loop_body.find("except asyncio.TimeoutError:")
        next_except = loop_body.find("except Exception as check_err", timeout_branch_start)
        self.assertGreater(timeout_branch_start, -1)
        self.assertGreater(next_except, timeout_branch_start)
        branch_body = loop_body[timeout_branch_start:next_except]
        self.assertIn(
            "_cleanup_monitor_cdp(self.state)",
            branch_body,
            "TimeoutError branch must force-recycle the monitor CDP client "
            "(otherwise the next iteration reuses the stuck client — the "
            "2026-05-24 13:31:36 → 13:32:28 5-consecutive-timeout cluster bug).",
        )

    def test_timeout_log_message_signals_recycle(self) -> None:
        # Operator-visible log should say "recycling CDP client" not the
        # old "continuing loop" so a grep of customer logs makes the
        # difference visible.
        self.assertIn('"recycling CDP client"', EM_SRC)


# -----------------------------------------------------------------------
# mt037B — DOM check timeout floor lowered to 5.0s
# -----------------------------------------------------------------------


class DOMCheckTimeoutFloorTests(unittest.TestCase):

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt037B", EM_SRC)

    def test_floor_is_five_not_eight(self) -> None:
        # check_timeout_s = max(interval_s * 20, 5.0)
        self.assertIn("max(interval_s * 20, 5.0)", EM_SRC)
        # And the old 8.0 floor is gone.
        # (Be specific: the floor is inside max(...); other 8.0 literals
        # in the file are unrelated.)
        m = re.search(r"max\(interval_s \* 20,\s*([\d.]+)\)", EM_SRC)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "5.0")


# -----------------------------------------------------------------------
# mt037C — latestAgentBubbleMsgId rewrite
# -----------------------------------------------------------------------


class LatestAgentBubbleMsgIdRewriteTests(unittest.TestCase):

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt037C", ET_SRC)

    def test_is_async_function(self) -> None:
        # The rewrite makes the function async (it polls with sleep).
        self.assertIn(
            "async function latestAgentBubbleMsgId()",
            ET_SRC,
            "mt037C makes latestAgentBubbleMsgId async (to allow brief "
            "polling for the data-id assignment race).",
        )

    def test_caller_awaits_msg_id(self) -> None:
        # The verify branch must await before serialising into finish().
        self.assertIn("var verifiedMsgId = await latestAgentBubbleMsgId()", ET_SRC)
        # And the finish() call uses the awaited value, not a fresh call.
        self.assertIn("verified_msg_id: verifiedMsgId", ET_SRC)
        # The old sync call form is gone.
        self.assertNotIn("verified_msg_id: latestAgentBubbleMsgId()", ET_SRC)

    def test_dual_agent_bubble_identifier(self) -> None:
        # _isAgentBubble accepts either flexDirection: row-reverse OR
        # messageIsMe — matches dom_assets.py's chat-thread scraper test.
        # Slice from the function definition to the next top-level
        # function (_bubbleTextOf) so we get the whole body.
        start = ET_SRC.find("function _isAgentBubble(wrap)")
        self.assertGreater(start, -1, "_isAgentBubble must be defined")
        end = ET_SRC.find("function _bubbleTextOf(", start)
        self.assertGreater(end, start)
        body = ET_SRC[start:end]
        self.assertIn("flexDirection", body)
        self.assertIn("messageIsMe", body)

    def test_text_match_preferred_over_newest(self) -> None:
        # The function must prefer text-matched bubble (the one we
        # just typed) before falling back to "newest with data-id".
        self.assertIn("_msgIdStripWs(text)", ET_SRC)
        self.assertIn("_msgIdStripWs(b.text) === expectedNorm", ET_SRC)

    def test_polls_for_data_id_assignment_race(self) -> None:
        # Up to 5 attempts with sleep(100) between them.
        body_start = ET_SRC.find("async function latestAgentBubbleMsgId")
        body_end = ET_SRC.find("\n  }\n", body_start)
        self.assertGreater(body_end, body_start)
        body = ET_SRC[body_start:body_end]
        self.assertIn("for (var attempt = 0; attempt < 5; attempt++)", body)
        self.assertIn("await sleep(100)", body)


class IntegrationGuardsTests(unittest.TestCase):
    """Quick checks that the changes hold together and don't regress
    the broader flow."""

    def test_python_extension_tools_still_reads_verified_msg_id(self) -> None:
        # The Python side that records record_typed_msg_id from the JS
        # response must still consume data.get("verified_msg_id").
        self.assertIn('data.get("verified_msg_id")', ET_SRC)
        # And still call record_typed_msg_id when non-empty.
        self.assertIn("record_typed_msg_id(", ET_SRC)


if __name__ == "__main__":
    unittest.main()
