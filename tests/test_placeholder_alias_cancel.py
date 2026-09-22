"""ws194 — cancelling a placeholder must follow the CONVERSATION, not the name.

One conversation carries two customer_keys: the real nickname and the synthetic
``card:<talk_id>`` used before the row has a name. ws074 taught placeholder
DEDUP to collapse them; cancel never followed. Delivering under one identity
left the other's timer armed, and it fired a 过渡句 after the customer had
already been answered.

Reproduced from the 0.9.98m customer trace:

    09:36:34  answered    cust='card:7688166838034826525'
    09:36:56  placeholder cust='陆地飞鱼'            <- same conversation

The regression guard that matters just as much: on 2026-05-20
``cancel_any_for_customer`` semantics were REVERTED because cancelling
everything for a conversation let an older turn's reply kill the newest turn's
timer, leaving the customer with no acknowledgement. A different, non-blank
source_msg_id is a different turn and must survive.
"""

from __future__ import annotations

import importlib
import sys
import unittest
from unittest import mock

MOD = "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.placeholder_timer"

TALK = "7688166838034826525"
CARD = f"card:{TALK}"
NAME = "陆地飞鱼"
MSG = "380D48C2-A7EC-4952-AE74-F9C93B48992F"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        if MOD in sys.modules:
            del sys.modules[MOD]
        self.pt = importlib.import_module(MOD)
        self.pt._REGISTRY.clear()
        self.pt._REAL_REPLY_AT.clear()
        self.pt._INFLIGHT_PLACEHOLDER_TASKS.clear()
        # The bundle resolves a name -> talk via ws_session; pin it so the test
        # exercises OUR logic rather than live session state.
        patch = mock.patch.object(
            self.pt, "_ph_talk_id",
            side_effect=lambda c: TALK if c in (CARD, NAME) else f"talk-of-{c}",
        )
        patch.start()
        self.addCleanup(patch.stop)
        arm = mock.patch.object(self.pt, "_current_store_key", return_value="S1")
        arm.start()
        self.addCleanup(arm.stop)

    def _armed(self):
        return {(e.customer_key, e.source_msg_id) for e in self.pt._REGISTRY.values()}


class AliasCancelTests(_Base):
    def test_the_customer_trace(self) -> None:
        """Armed under the name, answered under the card: nothing must survive."""
        self.pt.arm(NAME, MSG, timeout_s=6.0)
        self.assertIn((NAME, MSG), self._armed())

        self.pt.cancel(CARD, MSG)          # reply delivered under the card key
        self.assertEqual(self._armed(), set(), "the name's timer survived the reply")

    def test_cancels_the_other_direction_too(self) -> None:
        self.pt.arm(CARD, MSG, timeout_s=6.0)
        self.pt.cancel(NAME, MSG)
        self.assertEqual(self._armed(), set())

    def test_blank_msg_id_on_either_side_still_matches(self) -> None:
        """mt052C arms before the id is known; mt038E cancels without one."""
        self.pt.arm(NAME, "", timeout_s=6.0)
        self.pt.cancel(CARD, MSG)
        self.assertEqual(self._armed(), set())

        self.pt.arm(NAME, MSG, timeout_s=6.0)
        self.pt.cancel(CARD, "")
        self.assertEqual(self._armed(), set())

    def test_stamps_suppression_so_a_claimed_placeholder_aborts(self) -> None:
        """A placeholder already claimed but not yet typed must be suppressed."""
        self.pt.arm(NAME, MSG, timeout_s=6.0)
        self.pt.cancel(CARD, MSG)
        self.assertTrue(self.pt.is_real_reply_recent(NAME, MSG))

    def test_cancels_an_inflight_alias_task(self) -> None:
        self.pt.arm(NAME, MSG, timeout_s=6.0)
        task = mock.Mock()
        self.pt._INFLIGHT_PLACEHOLDER_TASKS[self.pt._make_key(NAME, MSG)] = task
        self.pt.cancel(CARD, MSG)
        task.cancel.assert_called_once()


class NoOverCancelTests(_Base):
    """The 2026-05-20 revert, re-pinned."""

    def test_a_different_turn_on_the_same_conversation_survives(self) -> None:
        newer = "NEWER-MSG-ID"
        self.pt.arm(NAME, newer, timeout_s=6.0)
        self.pt.cancel(CARD, MSG)          # an OLDER turn's reply lands
        self.assertIn(
            (NAME, newer), self._armed(),
            "an older reply killed the newest turn's timer — the 2026-05-20 bug",
        )

    def test_a_different_conversation_is_untouched(self) -> None:
        self.pt.arm("童趣科普", "OTHER", timeout_s=6.0)
        self.pt.cancel(CARD, MSG)
        self.assertIn(("童趣科普", "OTHER"), self._armed())

    def test_unresolvable_talk_id_cancels_nothing_extra(self) -> None:
        with mock.patch.object(self.pt, "_ph_talk_id", return_value=""):
            self.pt.arm(NAME, MSG, timeout_s=6.0)
            self.pt.cancel(CARD, MSG)
        self.assertIn((NAME, MSG), self._armed())


class SafetyTests(_Base):
    def test_kill_switch_disables_it(self) -> None:
        with mock.patch.dict("os.environ", {"ECAN_FEIGE_PH_ALIAS_CANCEL": "0"}):
            self.pt.arm(NAME, MSG, timeout_s=6.0)
            self.pt.cancel(CARD, MSG)
        self.assertIn((NAME, MSG), self._armed())

    def test_default_is_on(self) -> None:
        import os
        os.environ.pop("ECAN_FEIGE_PH_ALIAS_CANCEL", None)
        self.assertTrue(self.pt._alias_cancel_enabled())

    def test_never_raises_into_the_delivery_path(self) -> None:
        self.pt.arm(NAME, MSG, timeout_s=6.0)
        with mock.patch.object(
            self.pt, "_cancel_conversation_aliases", side_effect=RuntimeError("boom")
        ):
            self.pt.cancel(CARD, MSG)      # must not raise

    def test_talk_ids_resolved_outside_the_registry_lock(self) -> None:
        """_ph_talk_id can reach into ws_session; holding the dispatch-path lock
        while doing that is how ws175 deadlocked."""
        seen = []
        real = self.pt._ph_talk_id

        def probe(c):
            seen.append(self.pt._REGISTRY_LOCK.locked())
            return TALK if c in (CARD, NAME) else f"talk-of-{c}"

        self.pt.arm(NAME, MSG, timeout_s=6.0)
        with mock.patch.object(self.pt, "_ph_talk_id", side_effect=probe):
            self.pt.cancel(CARD, MSG)
        self.assertTrue(seen, "talk resolution never ran")
        self.assertNotIn(True, seen, "_ph_talk_id ran while holding _REGISTRY_LOCK")


if __name__ == "__main__":
    unittest.main()
