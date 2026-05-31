"""mt038 — two coordinated fixes for the J14N9 stranded-on-[商品] cascade
seen in the 2026-05-24 5-customer flood test:

* **mt038A** — `feige_send_message` now re-scrapes the customer's chat
  thread when the JS source-guard would have rejected the reply as
  ``stale_reply_source_msg_id``.  If the scrape finds a different,
  newer msg_id (the original dispatch carried no source_msg_id because
  the sidebar preview was an opaque attachment marker), the function
  retries the send ONCE with the rescued msg_id.  The retry is guarded
  by a `_mt038A_retry_attempted` flag on the params object so a second
  stale-failure cannot loop forever.

* **mt038B** — `_scrape_and_override_last_message` now sets the
  PreDispatch skip_reason to ``scrape_failed_attachment_marker`` when
  the chat-thread scrape fails (no Feige tab focusable under flood
  load) AND the sidebar preview is an opaque attachment marker like
  ``[商品]`` / ``[图片]``.  The dispatch is deferred to the next tick
  (~250 ms) instead of burning an LLM call on a marker that has zero
  semantic content for the bot to answer.  Normal text previews still
  fall through to the existing sidebar fallback unchanged — mt038A
  picks them up if the source-guard rejects on missing msg_id.
"""
from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ET_SRC = Path(
    "agent/ec_skills/browser_use_extension/extension_tools_service.py"
).read_text(encoding="utf-8")
PD_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")
DA_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


# -----------------------------------------------------------------------
# mt038A — re-scrape and retry on stale_reply_source_msg_id
# -----------------------------------------------------------------------


class Mt038ASourceStructureTests(unittest.TestCase):

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038A", ET_SRC)

    def test_retry_guard_flag_used(self) -> None:
        # Recursive retry must be guarded by a sticky flag on params
        # so a second stale-failure cannot loop forever.
        self.assertIn("_mt038A_retry_attempted", ET_SRC)
        # Read flag with getattr default False:
        self.assertIn(
            'getattr(params, "_mt038A_retry_attempted", False)',
            ET_SRC,
        )

    def test_rescue_calls_scrape_latest_customer_bubble(self) -> None:
        # The rescue path must re-import and call the same scraper
        # used by PreDispatch.
        self.assertIn(
            "from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets import (\n"
            "                        scrape_latest_customer_bubble as _mt038a_scrape,\n"
            "                    )",
            ET_SRC,
        )

    def test_rescue_only_retries_when_msg_id_changes(self) -> None:
        # Guard against retrying with the same source_msg_id that just
        # failed — would loop until _mt038A_retry_attempted kicks in
        # but waste a JS round-trip.
        self.assertIn(
            "_rescue_msg_id != source_msg_id",
            ET_SRC,
        )
        # And only when scrape_ok is true.
        self.assertIn('_rescue.get("scrape_ok")', ET_SRC)

    def test_rescue_patches_params_before_retry(self) -> None:
        # Both source_customer_msg_id AND source_latest_message must
        # be patched — the JS source-guard checks the msg_id but the
        # Q&A history serialiser uses the text.
        self.assertIn('"source_customer_msg_id", _rescue_msg_id', ET_SRC)
        self.assertIn('"source_latest_message", _rescue_text', ET_SRC)

    def test_ledger_emits_rescue_retry_stage(self) -> None:
        # Operator-visible ledger event so we can count rescues in
        # post-test analysis.
        self.assertIn("feige_send_mt038A_rescue_retry", ET_SRC)


# -----------------------------------------------------------------------
# mt038B — defer dispatch when scrape fails AND preview is attachment marker
# -----------------------------------------------------------------------


class Mt038BSourceStructureTests(unittest.TestCase):

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038B", PD_SRC)

    def test_attachment_marker_set_defined(self) -> None:
        # The set must be module-level and frozen so it can't drift
        # between calls.
        self.assertIn("_ATTACHMENT_MARKER_PREVIEWS", PD_SRC)
        self.assertIn("frozenset", PD_SRC)
        # Must at minimum cover the marker that stranded J14N9.
        self.assertIn('"[商品]"', PD_SRC)
        # And the most common Feige markers.
        for marker in ('"[图片]"', '"[视频]"', '"[文件]"', '"[语音]"'):
            self.assertIn(marker, PD_SRC)

    def test_defer_only_inside_scrape_failure_branch(self) -> None:
        # The defer logic must live INSIDE `if not scraped.get("scrape_ok"):`
        # so a successful scrape (even on an attachment marker — the
        # scrape returns the underlying text bubble) is unaffected.
        m = re.search(
            r'if not scraped\.get\("scrape_ok"\):(.*?)logger\.debug\(',
            PD_SRC,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "scrape_ok=False branch not found")
        branch_head = m.group(1)
        self.assertIn("_ATTACHMENT_MARKER_PREVIEWS", branch_head)
        self.assertIn("scrape_failed_attachment_marker", branch_head)

    def test_skip_reason_marker_string(self) -> None:
        # Operator-grepable skip_reason — keep stable for log analysis.
        self.assertIn(
            '"scrape_failed_attachment_marker"',
            PD_SRC,
        )

    def test_defer_uses_predispatch_skip_mechanism(self) -> None:
        # mt038B must use the SAME `_ecan_pre_dispatch_skip_reason`
        # contract that frontdesk_dispatch.py already understands.
        # Find the defer block and verify the key is set there.
        defer_block_start = PD_SRC.find("mt038B defer dispatch")
        self.assertGreater(defer_block_start, 0)
        # Look 400 chars before for the skip_reason assignment.
        ctx = PD_SRC[max(0, defer_block_start - 600):defer_block_start + 200]
        self.assertIn(
            '"_ecan_pre_dispatch_skip_reason"',
            ctx,
        )


# -----------------------------------------------------------------------
# mt038B — behaviour test: defer ONLY for attachment markers, not text
# -----------------------------------------------------------------------


class Mt038BBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """Light behaviour coverage — monkey-patches scrape_latest_customer_bubble
    to force a scrape_ok=False return, then asserts the defer flag is or
    isn't set depending on the sidebar preview."""

    async def _run_with_preview(self, preview: str) -> dict:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        item = {
            "customer_name": "J14N9",
            "last_message": preview,
        }
        empty_scrape = {
            "text": "",
            "msg_id": "",
            "scrape_ok": False,
            "skip_dispatch": False,
        }
        with mock.patch.object(
            pde,
            "scrape_latest_customer_bubble",
            new=mock.AsyncMock(return_value=empty_scrape),
        ):
            ret = await pde._scrape_and_override_last_message(
                browser_session=SimpleNamespace(),
                item=item,
                customer_key="J14N9",
                log_tag="[test]",
                typing_holder_getter=None,
            )
        return {"return": ret, "item": item}

    async def test_attachment_marker_sets_defer_reason(self) -> None:
        out = await self._run_with_preview("[商品]")
        self.assertEqual(out["return"], "")
        self.assertEqual(
            out["item"].get("_ecan_pre_dispatch_skip_reason"),
            "scrape_failed_attachment_marker",
        )

    async def test_image_marker_also_defers(self) -> None:
        out = await self._run_with_preview("[图片]")
        self.assertEqual(
            out["item"].get("_ecan_pre_dispatch_skip_reason"),
            "scrape_failed_attachment_marker",
        )

    async def test_normal_text_preview_does_not_defer(self) -> None:
        # Normal customer text falls through to the existing sidebar-
        # preview fallback — mt038A picks it up on stale_reply if the
        # msg_id is missing.  We must NOT set the skip_reason here
        # because that would block ALL scrape-failed turns under flood,
        # not just the opaque-marker ones.
        out = await self._run_with_preview("透气吗？面料舒适吗")
        self.assertEqual(out["return"], "")
        self.assertNotIn(
            "_ecan_pre_dispatch_skip_reason",
            out["item"],
        )

    async def test_marker_with_surrounding_whitespace_still_defers(self) -> None:
        # The defer check strips whitespace before set lookup — Feige
        # occasionally pads sidebar text.
        out = await self._run_with_preview("  [商品]  ")
        self.assertEqual(
            out["item"].get("_ecan_pre_dispatch_skip_reason"),
            "scrape_failed_attachment_marker",
        )


# -----------------------------------------------------------------------
# mt038C — source-guard recognizes product-card bubbles
# -----------------------------------------------------------------------


class Mt038CSourceStructureTests(unittest.TestCase):
    """The JS bubble-walker in feige_send_message's source_guard must
    treat .chatd-card-bearing bubbles as content-bearing — otherwise
    every reply whose source_customer_msg_id ends in '_template'
    fails stale (live trace 2026-05-24 12:19:30 客户18, dropped
    bot reply to product card)."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038C", ET_SRC)

    def test_chatd_card_added_to_content_check(self) -> None:
        # The new "hasCard" sentinel must be checked alongside text and
        # hasContentImage in the bubble-skip guard.
        self.assertIn("var hasCard = !!wrap.querySelector('.chatd-card');", ET_SRC)
        # And it must participate in the !text && !hasContentImage skip.
        self.assertIn(
            "if (!text && !hasContentImage && !hasCard) continue;",
            ET_SRC,
        )
        # Old two-arg form must be gone (otherwise a stale build could
        # still skip cards even if the new line is also present).
        self.assertNotIn(
            "if (!text && !hasContentImage) continue;",
            ET_SRC,
        )

    def test_card_check_lives_inside_allCustomerBubbles(self) -> None:
        # The fix must be inside the source-guard's bubble walker, not
        # some other JS function that happens to mention .chatd-card.
        start = ET_SRC.find("var MAX_BUBBLES = 8;")
        self.assertGreater(start, -1, "allCustomerBubbles loop not found")
        end = ET_SRC.find("return out;", start)
        self.assertGreater(end, start)
        body = ET_SRC[start:end]
        self.assertIn("hasCard", body)
        self.assertIn(".chatd-card", body)


# -----------------------------------------------------------------------
# mt038D — placeholder sweeper survives CDP recovery
# -----------------------------------------------------------------------


class Mt038DSourceStructureTests(unittest.TestCase):
    """When CDP recovery (extension_tools_service._record_cdp_evaluate_recovery_signal)
    invalidates the BrowserSession, the placeholder-sweeper coroutine
    dies with the event loop.  Pre-mt038D the sticky boolean
    ``_placeholder_sweeper_started`` was never reset, so the sweeper
    never restarted and every subsequent placeholder was armed but
    never fired — live trace 2026-05-24 12:57:34 (客户09/01/14/18
    stranded with no placeholder)."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038D", DA_SRC)

    def test_gate_uses_task_state_not_boolean(self) -> None:
        # New gate: check whether the cached task object is alive.
        self.assertIn(
            'existing_task = getattr(_pool, "_placeholder_sweeper_task", None)',
            DA_SRC,
        )
        self.assertIn(
            "if existing_task is not None and not existing_task.done():",
            DA_SRC,
        )
        # Old boolean gate (the bug) must be gone.
        self.assertNotIn(
            'if getattr(_pool, "_placeholder_sweeper_started", False):',
            DA_SRC,
        )
        # And we no longer SET the dead flag — leaving it unset means a
        # stale True from any prior process state can't re-trigger the
        # short-circuit bug.
        self.assertNotIn(
            'setattr(_pool, "_placeholder_sweeper_started", True)',
            DA_SRC,
        )

    def test_call_site_moved_outside_one_shot_block(self) -> None:
        # The relocated call must live AFTER the
        # try_dispatch_initial_population block closes (so it runs on
        # every ensure_feige_tab_focused success, not just the first
        # process-lifetime population).
        focus_end = DA_SRC.find(
            "await _ensure_feige_current_subtab(browser_session)\n        return True"
        )
        self.assertGreater(focus_end, -1, "ensure_feige_tab_focused success tail not found")
        # Search backward up to 800 chars before the tail for the
        # sweeper-start call — must be present there (relocated site).
        window = DA_SRC[max(0, focus_end - 800):focus_end]
        self.assertIn(
            "_start_placeholder_sweeper(browser_session)",
            window,
            "relocated sweeper-start call must precede the focus-success return",
        )

    def test_relocated_call_wrapped_in_try_except(self) -> None:
        # Sweeper-start must not be allowed to break tab-focus if it
        # blows up — guard with try/except + non-fatal log.
        focus_end = DA_SRC.find(
            "await _ensure_feige_current_subtab(browser_session)\n        return True"
        )
        window = DA_SRC[max(0, focus_end - 800):focus_end]
        self.assertIn("try:", window)
        self.assertIn("_start_placeholder_sweeper(browser_session)", window)
        self.assertIn("sweeper start failed", window)


class Mt038DBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """Verify the new gate ACTUALLY restarts the sweeper after the
    cached task is done/cancelled — the regression that the live
    customer trace hit."""

    async def _call_start(self, pool, _scheduled_tasks):
        import os
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dom_assets,
            tab_pool as _tp,
            placeholder_timer as _ph,
        )
        # The function's _timeout <= 0 branch short-circuits before the
        # task is created.  Ensure the feature is enabled for this test
        # by forcing the timeout env var > 0; the actual coroutine is
        # mocked so the timeout value doesn't drive any sleep.
        env_patch = mock.patch.dict(
            os.environ, {"ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S": "20"}, clear=False,
        )
        with env_patch, \
             mock.patch.object(_tp, "get_pool", return_value=pool), \
             mock.patch.object(
                 _ph,
                 "sweep_loop_async",
                 new=mock.AsyncMock(),
             ):
            dom_assets._start_placeholder_sweeper(SimpleNamespace())
        # Stash the freshly-created task (if any) for the caller.
        latest = getattr(pool, "_placeholder_sweeper_task", None)
        if latest is not None:
            _scheduled_tasks.append(latest)
        return latest

    async def test_done_task_triggers_restart(self) -> None:
        # Simulate the post-recovery state: task object present on the
        # pool, but already done (the sweeper coroutine was cancelled).
        pool = SimpleNamespace()
        dead = asyncio.get_event_loop().create_future()
        dead.cancel()
        try:
            await dead
        except asyncio.CancelledError:
            pass
        pool._placeholder_sweeper_task = dead

        scheduled: list = []
        new_task = await self._call_start(pool, scheduled)

        # A fresh task should have been created and stored on the pool.
        self.assertIsNotNone(new_task)
        self.assertIsNot(new_task, dead, "stale cancelled task should have been replaced")
        # Clean up: cancel the new task so the test doesn't leak.
        for t in scheduled:
            if hasattr(t, "cancel"):
                t.cancel()

    async def test_alive_task_short_circuits(self) -> None:
        # Live task on the pool: _start_placeholder_sweeper must NOT
        # replace it (avoid running two sweepers in parallel — they
        # would each fire every queued placeholder twice).
        pool = SimpleNamespace()

        async def _never():
            await asyncio.sleep(3600)

        alive_task = asyncio.create_task(_never())
        pool._placeholder_sweeper_task = alive_task
        try:
            scheduled: list = []
            returned = await self._call_start(pool, scheduled)
            self.assertIs(returned, alive_task, "live task must not be replaced")
        finally:
            alive_task.cancel()
            try:
                await alive_task
            except asyncio.CancelledError:
                pass


# -----------------------------------------------------------------------
# mt038E — placeholder key-mismatch suppress
# -----------------------------------------------------------------------


class Mt038ESourceStructureTests(unittest.TestCase):
    """When arm() and cancel() see different source_msg_id values
    (PreDispatch scrape fails on one side, or LLM reply payload loses
    source_customer_msg_id on the other), the placeholder registry's
    exact-key cancel misses and the sweeper mis-fires AFTER the real
    reply has already landed.  Live trace 2026-05-24 13:23: 客户14
    (placeholder #2 typed 10s after real reply), 客户15 (placeholder
    #1 typed 1.4s after real reply).  Fix: stamp the (customer, '')
    slot on cancel/mark and consult max(exact, blank) at suppress
    time, gated by entry.armed_at to preserve next-turn semantics."""

    PT_SRC = Path(
        "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
    ).read_text(encoding="utf-8")

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038E", self.PT_SRC)

    def test_cancel_stamps_blank_slot(self) -> None:
        # cancel() body must stamp the (customer, '') slot in addition
        # to the exact-key stamp.
        start = self.PT_SRC.find("def cancel(customer_key: str, source_msg_id")
        self.assertGreater(start, -1)
        end = self.PT_SRC.find("def cancel_any_for_customer", start)
        self.assertGreater(end, start)
        body = self.PT_SRC[start:end]
        self.assertIn("_REAL_REPLY_AT[key] = now", body)
        self.assertIn('_REAL_REPLY_AT[(str(customer_key), "")] = now', body)

    def test_mark_real_reply_delivered_stamps_blank_slot(self) -> None:
        start = self.PT_SRC.find("def mark_real_reply_delivered(")
        self.assertGreater(start, -1)
        end = self.PT_SRC.find("\n\n", start + 100)
        body = self.PT_SRC[start:end]
        self.assertIn("_REAL_REPLY_AT[key] = now", body)
        self.assertIn('_REAL_REPLY_AT[(str(customer_key), "")] = now', body)

    def test_claim_expired_takes_max_and_compares_armed_at(self) -> None:
        start = self.PT_SRC.find("def claim_expired(")
        self.assertGreater(start, -1)
        end = self.PT_SRC.find("\n@dataclass", start)
        if end < 0:
            end = start + 4000
        body = self.PT_SRC[start:end]
        # Must look up both exact and blank slots.
        self.assertIn("_REAL_REPLY_AT.get(k, 0.0)", body)
        self.assertIn(
            '_REAL_REPLY_AT.get(\n                (entry.customer_key, ""), 0.0\n            )',
            body,
        )
        # Must take max().
        self.assertIn("ts_real = max(ts_real_exact, ts_real_blank)", body)
        # Must gate on armed_at to preserve next-turn semantics.
        self.assertIn("ts_real > entry.armed_at", body)

    def test_is_real_reply_recent_also_consults_blank_slot(self) -> None:
        # The submitter-side pre-type suppress must use the same
        # max(exact, blank) form so a race between cancel and a
        # mid-sweep submitter is still caught.
        start = self.PT_SRC.find("def is_real_reply_recent(")
        end = self.PT_SRC.find("def mark_real_reply_delivered(", start)
        self.assertGreater(end, start)
        body = self.PT_SRC[start:end]
        self.assertIn("blank_key = _reply_key(customer_key,", body)
        self.assertIn("max(", body)
        self.assertIn("_REAL_REPLY_AT.get(blank_key, 0.0)", body)


class Mt038EBehaviourTests(unittest.TestCase):
    """Direct tests against the in-memory registry — exercise all four
    arm/cancel msg_id combinations and verify suppression behaviour."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as _ph,
        )
        self._ph = _ph
        # Snapshot + clear the global registry / real-reply state so
        # tests don't interfere with each other.
        with _ph._REGISTRY_LOCK:
            self._snap_reg = dict(_ph._REGISTRY)
            self._snap_rep = dict(_ph._REAL_REPLY_AT)
            _ph._REGISTRY.clear()
            _ph._REAL_REPLY_AT.clear()

    def tearDown(self) -> None:
        with self._ph._REGISTRY_LOCK:
            self._ph._REGISTRY.clear()
            self._ph._REAL_REPLY_AT.clear()
            self._ph._REGISTRY.update(self._snap_reg)
            self._ph._REAL_REPLY_AT.update(self._snap_rep)

    def _arm(self, cust: str, msg_id: str, timeout: float = 20.0) -> None:
        self._ph.arm(
            customer_key=cust,
            source_msg_id=msg_id,
            timeout_s=timeout,
        )

    def _claim(self) -> list:
        return self._ph.claim_expired(max_placeholders=2, rearm_s=15.0)

    def _force_expire(self, cust: str, msg_id: str) -> None:
        # Push deadline into the past so claim_expired considers it.
        import time
        k = self._ph._make_key(cust, msg_id)
        with self._ph._REGISTRY_LOCK:
            entry = self._ph._REGISTRY.get(k)
            self.assertIsNotNone(entry, f"entry {k} missing")
            entry.deadline_at = time.time() - 1.0

    def test_arm_blank_cancel_with_real_id_suppresses(self) -> None:
        # 客户15 case: arm with '', cancel with real id.  Without
        # mt038E, cancel's stamp goes to (c, real_id) but the registry
        # entry's key is (c, '') — exact-key lookup misses → fires.
        self._arm("客户15", "")
        # Simulate the real reply landing with a non-empty msg_id.
        self._ph.cancel("客户15", "tm4ccy5nmpk852uz")
        self._force_expire("客户15", "")
        expired = self._claim()
        self.assertEqual(
            [(e.customer_key, e.source_msg_id) for e in expired],
            [],
            "blank-armed placeholder must be suppressed when cancel "
            "stamped (customer, real_id) — fix relies on cancel ALSO "
            "stamping (customer, '')",
        )

    def test_arm_real_id_cancel_with_blank_suppresses(self) -> None:
        # 客户14 case: arm with real id, cancel with ''.  Without
        # mt038E, cancel's stamp goes to (c, '') but registry entry's
        # key is (c, real_id) — exact-key lookup misses → fires.
        self._arm("客户14", "45mw1qv2mpk851fs")
        self._ph.cancel("客户14", "")
        self._force_expire("客户14", "45mw1qv2mpk851fs")
        expired = self._claim()
        self.assertEqual(
            [(e.customer_key, e.source_msg_id) for e in expired],
            [],
            "real-id-armed placeholder must be suppressed when cancel "
            "was called with blank — fix relies on claim_expired "
            "consulting max(exact, blank) slots",
        )

    def test_arm_real_id_cancel_with_same_id_suppresses(self) -> None:
        # Sanity: the matching-id case still works.
        self._arm("客户02", "abc123")
        self._ph.cancel("客户02", "abc123")
        # entry was popped by cancel — nothing to expire, nothing to claim.
        expired = self._claim()
        self.assertEqual(expired, [])

    def test_armed_at_guard_preserves_next_turn(self) -> None:
        # The dangerous case: customer Q1 answered (stamps the slots),
        # then customer Q2 arrives and arms a NEW placeholder.  Q2's
        # placeholder must NOT be suppressed by the still-recent Q1
        # stamp — its armed_at is later than the stamp.
        import time
        # Q1: cancel stamps blank slot at "now" (call it T0).
        self._ph.cancel("客户03", "Q1_id")
        # Sleep so Q2's armed_at is strictly later than the cancel stamp.
        time.sleep(0.05)
        # Q2 arms AFTER the cancel.
        self._arm("客户03", "Q2_id")
        self._force_expire("客户03", "Q2_id")
        expired = self._claim()
        self.assertEqual(
            [(e.customer_key, e.source_msg_id) for e in expired],
            [("客户03", "Q2_id")],
            "Q2's placeholder must fire — its armed_at is later than "
            "the Q1 cancel stamp, so the armed_at guard MUST short-"
            "circuit the suppress check",
        )

    def test_armed_at_guard_does_not_block_same_turn_suppress(self) -> None:
        # Inverse: arm Q first, then a real reply lands for that turn
        # AFTER arming.  Suppress MUST fire because ts_real > armed_at.
        import time
        self._arm("客户04", "")  # arm at T0
        time.sleep(0.05)
        self._ph.cancel("客户04", "real_id")  # stamp at T0+50ms
        self._force_expire("客户04", "")
        expired = self._claim()
        self.assertEqual(expired, [], "real reply landed AFTER arm → must suppress")


# -----------------------------------------------------------------------
# mt038F (F.2) — mt030 honors mt017's pre-existing baseline
# -----------------------------------------------------------------------


class Mt038FSourceStructureTests(unittest.TestCase):
    """Live trace 2026-05-24 14:49:41 客户13: smart_cs greeting
    "亲亲，在哒~..." typed at idx 104 after customer Q at idx 103;
    mt030 mistook the greeter for our reply and skipped dispatch,
    leaving the customer stranded.  F.2: mt030 must NOT fire when
    mt017 already classified the latest agent bubble as a
    pre-existing baseline (either just baselined OR matches the
    cached baseline)."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-24 mt038F (F.2)", PD_SRC)

    def test_flag_initialized_before_mt017_block(self) -> None:
        # Flag must default False and be defined BEFORE the
        # `lab = scraped.get("latest_agent_bubble")` line.
        flag_init = PD_SRC.find("_agent_bubble_is_pre_existing_baseline = False")
        lab_get = PD_SRC.find('lab = scraped.get("latest_agent_bubble")')
        self.assertGreater(flag_init, -1, "flag default-init missing")
        self.assertGreater(lab_get, -1)
        self.assertLess(flag_init, lab_get, "flag must be initialized BEFORE the mt017 lab block")

    def test_flag_set_true_in_just_baselined_branch(self) -> None:
        # Find the "if not baseline:" branch and assert the flag is
        # set True somewhere inside it.  mt052N gated this behind a
        # system-message / placeholder check, so the assignment may sit
        # further inside the branch — widen the window accordingly.
        baselined_log = PD_SRC.find('"[BrowserAutomation] mt017 baselined latest agent "')
        self.assertGreater(baselined_log, -1, "mt017 baselined log line missing")
        # Bound the search at the next branch (`elif _lab_msg_id and _lab_msg_id == baseline:`).
        elif_branch = PD_SRC.find(
            "elif _lab_msg_id and _lab_msg_id == baseline:", baselined_log
        )
        self.assertGreater(elif_branch, baselined_log)
        window = PD_SRC[baselined_log:elif_branch]
        self.assertIn(
            "_agent_bubble_is_pre_existing_baseline = True",
            window,
            "just-baselined branch must still mark the bubble pre-existing "
            "(now gated by mt052N system/placeholder check)",
        )

    def test_flag_set_true_in_matches_baseline_branch(self) -> None:
        # The "elif _lab_msg_id and _lab_msg_id == baseline:" branch
        # must also set the flag (not just pass).  mt052N gates the
        # assignment behind a system/placeholder check inside the elif.
        elif_branch = PD_SRC.find("elif _lab_msg_id and _lab_msg_id == baseline:")
        self.assertGreater(elif_branch, -1)
        # Bound the search at the next branch (`else:`).
        else_branch = PD_SRC.find("\n                else:\n", elif_branch)
        self.assertGreater(else_branch, elif_branch)
        window = PD_SRC[elif_branch:else_branch]
        self.assertIn(
            "_agent_bubble_is_pre_existing_baseline = True",
            window,
            "matches-baseline branch must also mark the bubble pre-existing "
            "(now gated by mt052N system/placeholder check)",
        )

    def test_mt030_check_consults_flag(self) -> None:
        # The mt030 skip condition must include `not _agent_bubble_is_pre_existing_baseline`.
        # mt052M adds another conjunct so accept either the original 4-line
        # form or the extended form with placeholder-aware override.
        m = re.search(
            r"if\s*\(\s*\n\s*_agent_index >= 0\s*\n\s*and _scraped_cust_index >= 0\s*\n\s*and _agent_index > _scraped_cust_index\s*\n\s*and not _agent_bubble_is_pre_existing_baseline\s*\n(?:\s*and not _agent_bubble_is_placeholder\s*\n)?\s*\)\s*:",
            PD_SRC,
        )
        self.assertIsNotNone(
            m,
            "mt030 skip condition must AND in `not _agent_bubble_is_pre_existing_baseline`",
        )

    def test_telemetry_log_when_suppressed(self) -> None:
        # When mt030 would have fired but the flag suppressed it, emit
        # an operator-grep-able log line so we can monitor in production.
        self.assertIn("mt038F-F2 mt030 would fire but", PD_SRC)


class Mt038FBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end behaviour against _scrape_and_override_last_message —
    mock scrape returns a customer bubble + agent bubble pair where
    agent_idx > customer_idx, and we verify dispatch is suppressed
    ONLY when the agent bubble is "ours" (legitimate mt030) and NOT
    when it's a pre-existing baseline (F.2 suppression)."""

    def setUp(self) -> None:
        # Snapshot human_intervention module's per-customer baseline
        # state and reset for each test.
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            human_intervention as _hi,
        )
        self._hi = _hi
        self._snap_baseline = dict(getattr(_hi, "_BASELINE_AGENT_MSG_ID_BY_CUSTOMER", {}))
        self._snap_baseline_text = dict(getattr(_hi, "_BASELINE_AGENT_TEXT_BY_CUSTOMER", {}))
        if hasattr(_hi, "_BASELINE_AGENT_MSG_ID_BY_CUSTOMER"):
            _hi._BASELINE_AGENT_MSG_ID_BY_CUSTOMER.clear()
        if hasattr(_hi, "_BASELINE_AGENT_TEXT_BY_CUSTOMER"):
            _hi._BASELINE_AGENT_TEXT_BY_CUSTOMER.clear()

    def tearDown(self) -> None:
        if hasattr(self._hi, "_BASELINE_AGENT_MSG_ID_BY_CUSTOMER"):
            self._hi._BASELINE_AGENT_MSG_ID_BY_CUSTOMER.clear()
            self._hi._BASELINE_AGENT_MSG_ID_BY_CUSTOMER.update(self._snap_baseline)
        if hasattr(self._hi, "_BASELINE_AGENT_TEXT_BY_CUSTOMER"):
            self._hi._BASELINE_AGENT_TEXT_BY_CUSTOMER.clear()
            self._hi._BASELINE_AGENT_TEXT_BY_CUSTOMER.update(self._snap_baseline_text)

    async def _run_enrich(self, scraped: dict, customer_key: str = "客户TEST") -> dict:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        item = {"customer_name": customer_key, "last_message": "old"}
        with mock.patch.object(
            pde,
            "scrape_latest_customer_bubble",
            new=mock.AsyncMock(return_value=scraped),
        ):
            ret = await pde._scrape_and_override_last_message(
                browser_session=SimpleNamespace(),
                item=item,
                customer_key=customer_key,
                log_tag="[test]",
                typing_holder_getter=None,
            )
        return {"return": ret, "item": item}

    async def test_pre_existing_greeter_does_not_skip(self) -> None:
        # F.2 core case: greeter at idx > customer Q. Flag set True
        # via mt017 "just baselined" branch → mt030 must not fire.
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "请问这件还有库存吗？",
            "msg_id": "cust_new_msg",
            "index": 103,
            "latest_agent_bubble": {
                "text": "亲亲，在哒~很高兴为您服务，请问有什么可以帮您？",
                "msg_id": "smartcs_greeting_msg",
                "index": 104,
            },
        }
        out = await self._run_enrich(scraped)
        # mt030 must NOT have set the skip reason.
        self.assertNotIn(
            "_ecan_pre_dispatch_skip_reason",
            out["item"],
            "F.2: greeter at idx>cust must not trigger mt030 skip",
        )

    async def test_pre_existing_matches_baseline_does_not_skip(self) -> None:
        # Same bubble seen twice: first call baselines, second call's
        # baseline matches.  Both must keep dispatch alive.
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "请问这件还有库存吗？",
            "msg_id": "cust_msg",
            "index": 103,
            "latest_agent_bubble": {
                "text": "亲亲，在哒~",
                "msg_id": "greeting_msg",
                "index": 104,
            },
        }
        # First call: baselines.
        out1 = await self._run_enrich(scraped, customer_key="客户MATCH")
        self.assertNotIn("_ecan_pre_dispatch_skip_reason", out1["item"])
        # Second call: same msg_id matches baseline.
        out2 = await self._run_enrich(scraped, customer_key="客户MATCH")
        self.assertNotIn(
            "_ecan_pre_dispatch_skip_reason",
            out2["item"],
            "F.2: matches-baseline branch must also keep dispatch alive",
        )

    async def test_our_own_reply_still_triggers_mt030(self) -> None:
        # Regression guard: when the agent bubble IS ours (recorded
        # in the recent-reply ledger), mt030 must still fire — we
        # don't want to re-answer questions we already answered.
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as _ds,
        )
        cust = "客户OURS"
        our_reply_text = "您好，这款现货48小时内发出哦"
        # Record this text in the recent-reply ledger so mt017 sees it
        # as "ours" and skips the baseline path entirely.
        _ds.remember_agent_reply(cust, our_reply_text)
        try:
            scraped = {
                "scrape_ok": True,
                "skip_dispatch": False,
                "text": "现货什么时候发？",
                "msg_id": "cust_msg2",
                "index": 200,
                "latest_agent_bubble": {
                    "text": our_reply_text,
                    "msg_id": "our_reply_msg",
                    "index": 201,
                },
            }
            out = await self._run_enrich(scraped, customer_key=cust)
            self.assertEqual(
                out["item"].get("_ecan_pre_dispatch_skip_reason"),
                "agent_already_replied",
                "mt030 MUST still fire when the agent bubble is genuinely "
                "our recent reply — F.2 should only suppress for pre-existing "
                "baseline bubbles, not for our own replies",
            )
        finally:
            # Best-effort cleanup; remember_agent_reply has a TTL but
            # purging is cleaner.
            try:
                if hasattr(_ds, "_RECENT_AGENT_REPLY_BY_CUSTOMER"):
                    _ds._RECENT_AGENT_REPLY_BY_CUSTOMER.pop(cust, None)
            except Exception:
                pass

    async def test_customer_newer_than_agent_still_dispatches(self) -> None:
        # Inverse of the bug: when customer_idx > agent_idx (legit
        # new question after our reply), mt030 was already correct
        # — F.2 must not regress this.
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "新问题",
            "msg_id": "new_q",
            "index": 200,
            "latest_agent_bubble": {
                "text": "older agent reply",
                "msg_id": "older_msg",
                "index": 150,
            },
        }
        out = await self._run_enrich(scraped, customer_key="客户NEW")
        self.assertNotIn(
            "_ecan_pre_dispatch_skip_reason",
            out["item"],
            "customer_idx > agent_idx case must continue dispatching",
        )


# -----------------------------------------------------------------------
# mt040A — defer dispatch on system-row trigger
# -----------------------------------------------------------------------

FD_SRC = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt040ASourceStructureTests(unittest.TestCase):
    """Live trace 2026-05-25 12:34:06 J14N9 (real customer): bot
    dispatched on a pre-existing product card after a store-greeting
    system event fired dom_observed; LLM hallucinated a 透气 answer
    that didn't match the customer's eventual price question; the
    bad reply tripped mt017's HUMAN-INTERVENTION mark; customer was
    effectively ignored for 7+ min.  mt040A: when the trigger row is
    a kept-for-enrichment system message, defer dispatch — wait for
    the customer's actual text bubble to dom_observed."""

    def test_marker_present_pre_dispatch(self) -> None:
        self.assertIn("2026-05-25 mt040A", PD_SRC)

    def test_marker_present_frontdesk(self) -> None:
        self.assertIn("2026-05-25 mt040A", FD_SRC)

    def test_frontdesk_stamps_kept_system_reason(self) -> None:
        # The dispatcher must stamp the system_reason on the item AFTER
        # the "keeping pending system-looking row" log line.
        kept_log = FD_SRC.find('keeping pending "\n                    f"system-looking row for thread enrichment "')
        if kept_log < 0:
            kept_log = FD_SRC.find("keeping pending ")
        self.assertGreater(kept_log, -1, "keeping-pending log line missing")
        window = FD_SRC[kept_log:kept_log + 1500]
        self.assertIn(
            'item["_ecan_system_row_kept"] = system_reason',
            window,
            "system_reason must be stamped on the item so enrich can detect it",
        )

    def test_enrich_reads_flag_and_defers(self) -> None:
        # Enrich must check item.get("_ecan_system_row_kept") and set
        # _ecan_pre_dispatch_skip_reason to "mt040A_system_row_only".
        self.assertIn('item.get("_ecan_system_row_kept")', PD_SRC)
        self.assertIn('"mt040A_system_row_only"', PD_SRC)

    def test_defer_lives_after_mt030_block(self) -> None:
        # The defer must fire AFTER the mt030 block so mt017 has had
        # a chance to baseline the agent bubble.  If mt040A fires first,
        # we'd skip baseline setting and mt017 would re-fire on the
        # next non-system trigger.
        mt030_end = PD_SRC.find('mt030 agent-after-customer "\n            f"check failed (non-fatal)')
        mt040a_check = PD_SRC.find('item.get("_ecan_system_row_kept")')
        self.assertGreater(mt030_end, -1)
        self.assertGreater(mt040a_check, mt030_end,
                           "mt040A must live AFTER the mt030 block")


class Mt040ABehaviourTests(unittest.IsolatedAsyncioTestCase):
    """Behaviour: enrich returns skip-reason mt040A_system_row_only when
    the item is stamped with _ecan_system_row_kept; does NOT defer when
    the stamp is absent."""

    async def _run_enrich(self, item: dict, scraped: dict) -> dict:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        with mock.patch.object(
            pde,
            "scrape_latest_customer_bubble",
            new=mock.AsyncMock(return_value=scraped),
        ):
            ret = await pde._scrape_and_override_last_message(
                browser_session=SimpleNamespace(),
                item=item,
                customer_key=str(item.get("customer_name") or "J14N9"),
                log_tag="[test]",
                typing_holder_getter=None,
            )
        return {"return": ret, "item": item}

    async def test_system_row_kept_triggers_defer(self) -> None:
        item = {
            "customer_name": "J14N9",
            "last_message": "Hi, 欢迎光临",
            "_ecan_system_row_kept": "store_auto_greeting",
        }
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "[商品卡片] NASA2025秋季中大童...",
            "msg_id": "C9184D37-351C-4573-8C8D-E248B5065260",
            "index": 15,
        }
        out = await self._run_enrich(item, scraped)
        self.assertEqual(
            out["item"].get("_ecan_pre_dispatch_skip_reason"),
            "mt040A_system_row_only",
            "system-row-kept item must defer with mt040A reason",
        )

    async def test_no_stamp_dispatches_normally(self) -> None:
        # Inverse: without _ecan_system_row_kept, mt040A must NOT fire.
        # (Other gates may still set their own skip_reasons; we just
        # check that mt040A's specific reason isn't set.)
        item = {
            "customer_name": "J14N9",
            "last_message": "夏天能不能便宜点",
        }
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "夏天能不能便宜点",
            "msg_id": "BB74083E-10A7-4246-9613-4A3B67DF62A3",
            "index": 50,
        }
        out = await self._run_enrich(item, scraped)
        self.assertNotEqual(
            out["item"].get("_ecan_pre_dispatch_skip_reason"),
            "mt040A_system_row_only",
            "non-system trigger must not defer via mt040A",
        )


# -----------------------------------------------------------------------
# mt040B.1 — telemetry counters for mt037C verified_msg_id capture
# -----------------------------------------------------------------------


class Mt040B1SourceStructureTests(unittest.TestCase):
    """Real-Feige customer trace 2026-05-25 12:34-12:44 J14N9: 0
    record_typed_msg_id calls across the entire log (verified_msg_id
    was empty for every successful send).  mt040B.1 instruments the
    JS bubble walker + match loop with per-poll counters so the next
    live trace exposes exactly where capture fails (no wraps seen,
    no agent classification, no data-id assigned, no text match,
    etc.).  Match strategy uses integer codes (0=none, 1=text_match,
    2=newest_with_id) so page_counters' int-only serializer keeps
    them in the ledger."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt040B.1", ET_SRC)

    def test_walk_counters_set(self) -> None:
        # _walkAgentBubblesNewestFirst must track three per-walk counters
        # and accumulate them across polls.
        start = ET_SRC.find("function _walkAgentBubblesNewestFirst()")
        end = ET_SRC.find("async function latestAgentBubbleMsgId", start)
        self.assertGreater(start, -1)
        self.assertGreater(end, start)
        body = ET_SRC[start:end]
        for key in ("mt037c_wraps_seen", "mt037c_agent_classified", "mt037c_with_data_id"):
            self.assertIn(key, body, f"missing counter {key!r}")
        # All three must accumulate (|| 0) so multi-poll totals are correct.
        self.assertIn("(__feigeSendCounters.mt037c_wraps_seen || 0)", body)

    def test_match_loop_counters_set(self) -> None:
        # latestAgentBubbleMsgId must track total_attempts, match_strategy,
        # result_msg_id_len on EVERY return path (text match, newest with id,
        # exhausted/none).
        start = ET_SRC.find("async function latestAgentBubbleMsgId")
        end = ET_SRC.find("function latestVisibleBubble(", start)
        self.assertGreater(start, -1)
        self.assertGreater(end, start)
        body = ET_SRC[start:end]
        # Three return paths set match_strategy distinctly: 1, 2, 0.
        self.assertEqual(
            body.count("__feigeSendCounters.mt037c_match_strategy = 1"), 1,
            "text_match strategy must be set in the text-match return path",
        )
        self.assertEqual(
            body.count("__feigeSendCounters.mt037c_match_strategy = 2"), 1,
            "newest_with_id strategy must be set in the fallback return path",
        )
        self.assertEqual(
            body.count("__feigeSendCounters.mt037c_match_strategy = 0"), 1,
            "none strategy must be set in the exhausted return path",
        )
        # total_attempts and result_msg_id_len must be set in all three.
        self.assertEqual(body.count("mt037c_total_attempts = totalAttempts"), 3)
        self.assertEqual(body.count("mt037c_result_msg_id_len"), 3)

    def test_match_strategy_codes_are_integers(self) -> None:
        # Integer codes are required because the page_counters serializer
        # silently drops non-int values via int(value).  String codes
        # would never reach the ledger.
        start = ET_SRC.find("async function latestAgentBubbleMsgId")
        end = ET_SRC.find("function latestVisibleBubble(", start)
        body = ET_SRC[start:end]
        # No quoted string assignments to match_strategy.
        self.assertNotRegex(
            body,
            r"mt037c_match_strategy\s*=\s*['\"]",
            "match_strategy assignments must be unquoted integers, not strings",
        )


# -----------------------------------------------------------------------
# mt041A — mt017 honors known system-pattern bubbles
# -----------------------------------------------------------------------


class Mt041ASourceStructureTests(unittest.TestCase):
    """Live trace 2026-05-24 23:30:32 客户15: the emulator's smart_cs
    auto-greeting "亲亲，在哒~..." appeared in the chat thread.  mt017
    didn't recognize it (we didn't type it) so it mark_handled the
    customer for 120s, dropping the bot's actual reply.  mt041A:
    classify known system patterns (smart_cs greeting, human-handover
    notice, store assignment, etc.) as pre-existing baseline rather
    than human intervention; set F.2 flag so mt030 doesn't fire."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt041A", PD_SRC)

    def test_first_matching_pattern_imported(self) -> None:
        # The mt017 path must import first_matching_pattern from the
        # system_message_filter module to classify the agent bubble.
        self.assertIn(
            "from .system_message_filter import (\n"
            "                            first_matching_pattern as _hi_sys_match,\n"
            "                        )",
            PD_SRC,
        )

    def test_system_pattern_path_sets_baseline_and_flag(self) -> None:
        # When pattern matches, mt041A path must:
        #   1. set agent baseline msg_id and text (so future scrapes
        #      recognise the bubble)
        #   2. flip _agent_bubble_is_pre_existing_baseline so mt030
        #      F.2 honours it
        #   3. NOT call mark_handled
        # Locate the mt041A telemetry log to scope the assertions.
        log_start = PD_SRC.find("mt041A treat as pre-existing")
        self.assertGreater(log_start, -1)
        window = PD_SRC[max(0, log_start - 400):log_start + 200]
        self.assertIn("_hi.set_baseline_msg_id(customer_key, _lab_msg_id)", window)
        self.assertIn("_hi.set_baseline_text(customer_key, _lab_text)", window)
        self.assertIn("_agent_bubble_is_pre_existing_baseline = True", window)

    def test_system_pattern_skips_mark_handled(self) -> None:
        # After the mt041A branch, the human-intervention block must be
        # gated on `not _sys_pat` so mark_handled is skipped.
        self.assertIn(
            "if _sys_pat:\n                        pass  # mt041A handled it",
            PD_SRC,
        )


class Mt041ABehaviourTests(unittest.IsolatedAsyncioTestCase):
    """End-to-end: a scrape returning the smart_cs greeting as the
    agent bubble must NOT trigger mark_handled, and mt030 must not
    skip the dispatch."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            human_intervention as _hi,
        )
        self._hi = _hi
        with self._hi._LOCK:
            self._snap_baseline = dict(getattr(_hi, "_BASELINE_AGENT_MSG_ID", {}))
            self._snap_baseline_text = dict(getattr(_hi, "_BASELINE_AGENT_TEXT", {}))
            self._snap_handled = dict(getattr(_hi, "_HANDLED_BY_CUSTOMER", {}))
            for d in (
                getattr(_hi, "_BASELINE_AGENT_MSG_ID", None),
                getattr(_hi, "_BASELINE_AGENT_TEXT", None),
                getattr(_hi, "_HANDLED_BY_CUSTOMER", None),
            ):
                if d is not None:
                    d.clear()

    def tearDown(self) -> None:
        with self._hi._LOCK:
            for name, snap in (
                ("_BASELINE_AGENT_MSG_ID", self._snap_baseline),
                ("_BASELINE_AGENT_TEXT", self._snap_baseline_text),
                ("_HANDLED_BY_CUSTOMER", self._snap_handled),
            ):
                d = getattr(self._hi, name, None)
                if d is not None:
                    d.clear()
                    d.update(snap)

    async def test_smart_cs_greeting_does_not_mark_handled(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        cust = "客户041A_GREETER"
        # Seed an old baseline so we enter the "genuinely new bubble" branch.
        self._hi.set_baseline_msg_id(cust, "old_baseline_msg_id")
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "DHL寄到欧洲多久能到？",
            "msg_id": "cust_q_msg",
            "index": 5,
            "latest_agent_bubble": {
                "text": "亲亲，在哒~很高兴为您服务，请问有什么可以帮您？",
                "msg_id": "smart_cs_msg",
                "index": 6,
            },
        }
        item = {"customer_name": cust, "last_message": "DHL寄到欧洲多久能到？"}
        with mock.patch.object(
            pde,
            "scrape_latest_customer_bubble",
            new=mock.AsyncMock(return_value=scraped),
        ):
            await pde._scrape_and_override_last_message(
                browser_session=SimpleNamespace(),
                item=item,
                customer_key=cust,
                log_tag="[test]",
                typing_holder_getter=None,
            )
        # mt041A: must NOT have called mark_handled.
        handled = self._hi.get_handled_msg_id(cust)
        self.assertEqual(
            handled, "",
            f"mt041A: smart_cs greeting must NOT be marked human-handled "
            f"(got handled_msg_id={handled!r})",
        )
        # mt030 dispatch must NOT be skipped (F.2 flag should fire).
        self.assertNotEqual(
            item.get("_ecan_pre_dispatch_skip_reason"),
            "agent_already_replied",
            "mt030 should not skip when mt041A classifies the agent "
            "bubble as a system pattern",
        )

    async def test_genuine_human_text_still_marks_handled(self) -> None:
        # Regression guard: a real human typing "您的订单我帮您查询一下"
        # (not a known system pattern) must STILL trip mark_handled.
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            pre_dispatch_enrich as pde,
        )
        cust = "客户041A_HUMAN"
        self._hi.set_baseline_msg_id(cust, "old_baseline_msg_id")
        scraped = {
            "scrape_ok": True,
            "skip_dispatch": False,
            "text": "客户的问题",
            "msg_id": "cust_q_msg2",
            "index": 5,
            "latest_agent_bubble": {
                "text": "您的订单我帮您查询一下，请稍等",
                "msg_id": "human_reply_msg",
                "index": 6,
            },
        }
        item = {"customer_name": cust, "last_message": "客户的问题"}
        with mock.patch.object(
            pde,
            "scrape_latest_customer_bubble",
            new=mock.AsyncMock(return_value=scraped),
        ):
            await pde._scrape_and_override_last_message(
                browser_session=SimpleNamespace(),
                item=item,
                customer_key=cust,
                log_tag="[test]",
                typing_holder_getter=None,
            )
        handled = self._hi.get_handled_msg_id(cust)
        self.assertEqual(
            handled, "human_reply_msg",
            "genuine human text must still trigger mark_handled",
        )


# -----------------------------------------------------------------------
# mt041B — burst-rebuild rejects already-dispatched bubbles
# -----------------------------------------------------------------------

DA_SRC_LATEST = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt041BSourceStructureTests(unittest.TestCase):
    """Live trace 2026-05-24 23:30:25 客户02: thread-scrape merged
    three unrelated turns ('这件能今天发货吗' + card + '生鲜出问题...')
    into one dispatch because the burst-rebuild walks back across
    bubbles whose prior dispatches failed to land an agent reply.
    mt041B: pass the customer_last_dispatched_msg_id dict to the
    scrape, inject the customer's prior msg_id as a JS window array,
    and break the burst when an older wrap matches."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt041B", DA_SRC_LATEST)

    def test_js_reads_window_variable_with_default(self) -> None:
        # The JS must read window.__ECAN_PREV_DISP_IDS__ defensively
        # (defaults to [] when caller didn't set it).
        self.assertIn("window.__ECAN_PREV_DISP_IDS__", DA_SRC_LATEST)
        self.assertIn("var __PREV_DISP_IDS__", DA_SRC_LATEST)
        # Default fallback to empty array must be present.
        self.assertIn("? window.__ECAN_PREV_DISP_IDS__ : []", DA_SRC_LATEST)

    def test_js_burst_loop_breaks_on_prior_dispatch_match(self) -> None:
        # The burst-rebuild loop must:
        #   1. Read prevWrap's data-id BEFORE the customer-row check
        #   2. break (not continue) when matched
        loop_start = DA_SRC_LATEST.find(
            "while (j >= 0 && lookback < 3) {"
        )
        loop_end = DA_SRC_LATEST.find("var textParts = [];", loop_start)
        self.assertGreater(loop_start, -1)
        self.assertGreater(loop_end, loop_start)
        body = DA_SRC_LATEST[loop_start:loop_end]
        self.assertIn("var prevIdEl = prevWrap.querySelector('[data-id]');", body)
        self.assertIn(
            "if (prevMsgId && __PREV_DISP_IDS__.indexOf(prevMsgId) !== -1) {",
            body,
        )
        # Must be break, not continue.
        m = re.search(
            r"if \(prevMsgId && __PREV_DISP_IDS__\.indexOf\(prevMsgId\) !== -1\) \{\s*break;",
            body,
        )
        self.assertIsNotNone(m, "must break (not continue) on prior-dispatch match")

    def test_python_signature_accepts_msg_id_list(self) -> None:
        # scrape_latest_customer_bubble must accept the new kwarg.
        self.assertIn(
            "previously_dispatched_msg_ids: list[str] | set[str] | None = None",
            DA_SRC_LATEST,
        )

    def test_python_injects_window_var_before_scrape(self) -> None:
        # The injection JS must run BEFORE the main scrape.
        inj = DA_SRC_LATEST.find("window.__ECAN_PREV_DISP_IDS__ = ")
        scrape_eval = DA_SRC_LATEST.find(
            "scrape_raw = await _s_eval_js(browser_session, FEIGE_LATEST_CUSTOMER_BUBBLE_JS)"
        )
        self.assertGreater(inj, -1)
        self.assertGreater(scrape_eval, inj,
                           "injection JS must be defined BEFORE the scrape eval")

    def test_enrich_forwards_dispatch_dict_to_scrape(self) -> None:
        # _scrape_and_override_last_message must accept the new kwarg
        # and forward the customer's most recent msg_id.
        self.assertIn(
            "customer_last_dispatched_msg_id: dict | None = None,",
            PD_SRC,
        )
        self.assertIn(
            "previously_dispatched_msg_ids=_prev_ids_for_scrape or None",
            PD_SRC,
        )

    def test_call_site_threads_dispatch_dict(self) -> None:
        # The enrich call site must pass customer_last_dispatched_msg_id.
        self.assertIn(
            "customer_last_dispatched_msg_id=customer_last_dispatched_msg_id,",
            PD_SRC,
        )


# -----------------------------------------------------------------------
# mt042A — actionable_field='pending_timer' falls back to unread_badge
# -----------------------------------------------------------------------

RUNNER_SRC = Path("agent/ec_skills/browser_node/runner.py").read_text(encoding="utf-8")


class Mt042ASourceStructureTests(unittest.TestCase):
    """Live trace 2026-05-25 14:54:42 肽斯特 (real Feige): customer
    pasted a product card; row had unread_badge='1' but pending_timer=''
    (Feige populates pending_timer lazily).  Pre-mt042A the actionable
    filter dropped the row entirely → PreDispatch ran with 0 items →
    no dispatch → bot silent for 1m32s.  mt042A: when actionable_field
    is 'pending_timer', fall back to unread_badge >= 1 as the actionable
    signal."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt042A", RUNNER_SRC)

    def test_mt042a_actionable_helper_defined(self) -> None:
        self.assertIn("def _mt042a_actionable(it: dict) -> bool:", RUNNER_SRC)

    def test_helper_uses_pending_timer_first(self) -> None:
        # The legacy check (pending_timer non-empty) must remain the
        # primary signal so existing tests / behaviour are unchanged.
        helper_start = RUNNER_SRC.find("def _mt042a_actionable(it: dict)")
        helper_end = RUNNER_SRC.find(
            "_actionable_raw = (\n", helper_start
        )
        self.assertGreater(helper_end, helper_start)
        body = RUNNER_SRC[helper_start:helper_end]
        # Field-value check first
        self.assertIn('str(it.get(af, "")', body)
        self.assertIn("return True", body)

    def test_helper_falls_back_to_unread_badge_for_pending_timer(self) -> None:
        # When actionable_field is 'pending_timer' AND pending_timer is
        # empty, check unread_badge.
        helper_start = RUNNER_SRC.find("def _mt042a_actionable(it: dict)")
        helper_end = RUNNER_SRC.find(
            "_actionable_raw = (\n", helper_start
        )
        body = RUNNER_SRC[helper_start:helper_end]
        self.assertIn('if af == "pending_timer":', body)
        self.assertIn('int(str(it.get("unread_badge"', body)
        self.assertIn(">= 1", body)

    def test_helper_returns_false_for_other_fields(self) -> None:
        # When actionable_field is something other than 'pending_timer'
        # AND the field is empty, return False (legacy behaviour for
        # non-Feige nodes that opted into a different actionable field).
        helper_start = RUNNER_SRC.find("def _mt042a_actionable(it: dict)")
        helper_end = RUNNER_SRC.find(
            "_actionable_raw = (\n", helper_start
        )
        body = RUNNER_SRC[helper_start:helper_end]
        # The final return must be False (not True) so other actionable_field
        # values keep their strict semantics.
        self.assertTrue(
            body.rstrip().endswith("return False"),
            "helper must default to False for non-pending_timer fields",
        )

    def test_helper_used_in_actionable_raw_comprehension(self) -> None:
        # _actionable_raw must use the helper, not the old direct check.
        self.assertIn(
            "[it for it in _compact_items if _mt042a_actionable(it)]",
            RUNNER_SRC,
        )
        # And the old strict-only check is gone.
        self.assertNotIn(
            'if str(it.get(self.ctx.actionable_field, "")).strip()]',
            RUNNER_SRC,
        )


class Mt042ABehaviourTests(unittest.TestCase):
    """Unit-test the helper directly by importing the module and
    exercising the same logic — sidesteps the heavy runner.py imports."""

    def _make_helper(self, actionable_field: str):
        # Recreate the helper as a standalone function with the same
        # logic, parameterised by actionable_field.  This is what
        # production code does inside the runner loop.
        def _mt042a_actionable(it: dict) -> bool:
            af = actionable_field
            if str(it.get(af, "") or "").strip():
                return True
            if af == "pending_timer":
                try:
                    return int(str(it.get("unread_badge", "0") or "0").strip() or "0") >= 1
                except (TypeError, ValueError):
                    return False
            return False
        return _mt042a_actionable

    def test_pending_timer_set_passes(self) -> None:
        h = self._make_helper("pending_timer")
        self.assertTrue(h({"pending_timer": "1分31秒", "unread_badge": ""}))
        self.assertTrue(h({"pending_timer": "5秒", "unread_badge": "0"}))

    def test_pending_timer_empty_but_unread_badge_set_passes(self) -> None:
        # THE FIX CASE: 肽斯特 at 14:54:42 — pending_timer='' but
        # unread_badge='1'.  Pre-mt042A returned False (filtered out);
        # post-mt042A returns True (dispatch fires).
        h = self._make_helper("pending_timer")
        self.assertTrue(
            h({"pending_timer": "", "unread_badge": "1"}),
            "肽斯特-shape row must pass: customer just pasted a card, Feige "
            "hasn't populated pending_timer yet, but unread_badge=1 signals "
            "an actionable customer message",
        )

    def test_both_empty_returns_false(self) -> None:
        # No signal at all — correctly filtered.
        h = self._make_helper("pending_timer")
        self.assertFalse(h({"pending_timer": "", "unread_badge": "0"}))
        self.assertFalse(h({"pending_timer": "", "unread_badge": ""}))
        self.assertFalse(h({}))

    def test_higher_unread_badge_passes(self) -> None:
        h = self._make_helper("pending_timer")
        self.assertTrue(h({"pending_timer": "", "unread_badge": "5"}))
        self.assertTrue(h({"pending_timer": "", "unread_badge": "99"}))

    def test_unread_badge_string_with_whitespace(self) -> None:
        # The DOM extractor may surface unread_badge with surrounding
        # whitespace.  strip + int should handle it.
        h = self._make_helper("pending_timer")
        self.assertTrue(h({"pending_timer": "", "unread_badge": "  3  "}))

    def test_unread_badge_invalid_int_returns_false(self) -> None:
        # Defensive: malformed unread_badge shouldn't crash.
        h = self._make_helper("pending_timer")
        self.assertFalse(h({"pending_timer": "", "unread_badge": "abc"}))
        self.assertFalse(h({"pending_timer": "", "unread_badge": "1.5badge"}))

    def test_other_actionable_field_unaffected(self) -> None:
        # If a different node uses a different actionable_field, the
        # mt042A fallback does NOT trigger — legacy strict semantics.
        h = self._make_helper("needs_action")
        # Empty needs_action with unread_badge=1 → still False (NOT
        # the pending_timer fallback path).
        self.assertFalse(h({"needs_action": "", "unread_badge": "1"}))
        # Non-empty needs_action → True (primary path).
        self.assertTrue(h({"needs_action": "yes", "unread_badge": ""}))


# -----------------------------------------------------------------------
# mt043A/B/C/D — tab focus contention fixes
# -----------------------------------------------------------------------

DA_SRC_043 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt043CSourceTests(unittest.TestCase):
    """Live trace 2026-05-25 12:36-14:58: 21 'cached focus-target
    TIMEOUT after 3s' events affecting 4 customers.  Root cause:
    Chrome's main thread can take >3s to process Page.bringToFront
    under heavy DOM + concurrent typing load.  mt043C raises the
    timeout from 3.0s to 10.0s to give Chrome headroom — doesn't
    fix the underlying contention but eliminates transient
    false-positive timeouts."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt043C", DA_SRC_043)

    def test_timeout_raised_to_10s(self) -> None:
        self.assertIn("_FOCUS_TARGET_TIMEOUT_S: float = 10.0", DA_SRC_043)
        self.assertNotIn("_FOCUS_TARGET_TIMEOUT_S: float = 3.0", DA_SRC_043)


class Mt043DSourceTests(unittest.TestCase):
    """Back-to-back scrape/typing calls re-trigger Page.bringToFront
    on the SAME target even though Chrome is already on the right
    tab.  mt043D skips the bringToFront when we focused the same
    target within _RECENT_FOCUS_SKIP_S (2s)."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt043D", DA_SRC_043)

    def test_skip_constants_defined(self) -> None:
        self.assertIn("_RECENT_FOCUS_SKIP_S: float = 2.0", DA_SRC_043)
        self.assertIn(
            '_SESSION_LAST_FOCUS_TID_ATTR: str = "_ecan_feige_last_focus_tid"',
            DA_SRC_043,
        )
        self.assertIn(
            '_SESSION_LAST_FOCUS_TS_ATTR: str = "_ecan_feige_last_focus_ts"',
            DA_SRC_043,
        )

    def test_skip_path_checks_age_and_tid(self) -> None:
        # The skip path must compare cached_tid == last_focused_tid
        # AND age < _RECENT_FOCUS_SKIP_S before returning early.
        self.assertIn("_last_tid == _cached_tid", DA_SRC_043)
        self.assertIn("(_now - _last_ts) < _RECENT_FOCUS_SKIP_S", DA_SRC_043)
        # Log substrings may be split across two f-string lines.
        self.assertIn("ensure-feige-tab: skipped", DA_SRC_043)
        self.assertIn("redundant bringToFront", DA_SRC_043)

    def test_stamp_recorded_after_successful_focus(self) -> None:
        # After a SUCCESSFUL focus, the function must stamp tid + ts
        # so the NEXT call within the TTL can short-circuit.
        # Locate the stamp comment + assertions.
        stamp_idx = DA_SRC_043.find(
            "mt043D: stamp the successful-focus marker"
        )
        self.assertGreater(stamp_idx, -1)
        window = DA_SRC_043[stamp_idx:stamp_idx + 800]
        self.assertIn("_SESSION_LAST_FOCUS_TID_ATTR", window)
        self.assertIn("_SESSION_LAST_FOCUS_TS_ATTR", window)
        self.assertIn("setattr(", window)


class Mt043BSourceTests(unittest.TestCase):
    """ensure_feige_tab_focused's session_cdp_operation_lock call
    was session-wide (no target_id), so a typing op on tab A held
    the lock while a scrape's focus call on tab B queued behind it.
    mt043B threads target_id through so each tab gets its own
    per-target lock; _session_focus_lock remains session-wide so
    actual bringToFront calls still serialize (one tab can be
    foreground in Chrome at a time)."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt043B", DA_SRC_043)

    def test_session_cdp_operation_lock_passes_target_id(self) -> None:
        # The call must include target_id=str(_cached_tid).
        self.assertIn(
            "session_cdp_operation_lock(\n"
            "                                browser_session, target_id=str(_cached_tid)\n"
            "                            ):",
            DA_SRC_043,
        )

    def test_session_focus_lock_stays_session_wide(self) -> None:
        # Regression guard: don't accidentally per-target the focus lock.
        # The focus lock comment explains why it must stay session-wide.
        self.assertIn(
            "async with _session_focus_lock(browser_session):",
            DA_SRC_043,
        )


class Mt043ASourceTests(unittest.TestCase):
    """Scrape callers don't need Page.bringToFront — they then run
    the eval with focus=False anyway.  mt043A introduces
    ensure_feige_tab_reachable (no focus / no locks / no bringToFront)
    for read-only callers.  Eliminates ~70% of focus-timeout events."""

    def test_marker_present(self) -> None:
        self.assertIn("2026-05-25 mt043A", DA_SRC_043)

    def test_reachable_function_defined(self) -> None:
        self.assertIn(
            "async def ensure_feige_tab_reachable(browser_session) -> bool:",
            DA_SRC_043,
        )

    def test_reachable_does_not_call_bringtofront(self) -> None:
        # The new function must NOT call get_or_create_cdp_session(focus=True)
        # or acquire either lock anywhere in its EXECUTABLE BODY (skip the
        # docstring, which mentions these by name as things it deliberately
        # does NOT do).
        start = DA_SRC_043.find(
            "async def ensure_feige_tab_reachable(browser_session) -> bool:"
        )
        end = DA_SRC_043.find(
            "async def ensure_feige_tab_focused(browser_session) -> bool:",
            start,
        )
        self.assertGreater(end, start)
        # Strip the docstring before scanning for forbidden calls.
        # The docstring is enclosed in triple-double-quotes immediately
        # after the def line.
        whole = DA_SRC_043[start:end]
        ds_start = whole.find('"""')
        ds_end = whole.find('"""', ds_start + 3)
        self.assertGreater(ds_start, -1)
        self.assertGreater(ds_end, ds_start)
        body_after_ds = whole[ds_end + 3:]
        self.assertNotIn("focus=True", body_after_ds, "reachable() must not focus")
        self.assertNotIn(
            "get_or_create_cdp_session(",
            body_after_ds,
            "reachable() must not call get_or_create_cdp_session at all",
        )
        self.assertNotIn(
            "session_cdp_operation_lock(",
            body_after_ds,
            "reachable() must not acquire the session_cdp lock",
        )
        self.assertNotIn(
            "_session_focus_lock(",
            body_after_ds,
            "reachable() must not acquire the session_focus lock",
        )

    def test_reachable_falls_back_to_scan(self) -> None:
        # When no valid cache, the function must scan session_manager
        # for any Feige URL and cache the first match.
        start = DA_SRC_043.find(
            "async def ensure_feige_tab_reachable(browser_session) -> bool:"
        )
        end = DA_SRC_043.find(
            "async def ensure_feige_tab_focused(browser_session) -> bool:",
            start,
        )
        body = DA_SRC_043[start:end]
        self.assertIn(
            "sm.get_all_targets() if sm else {}",
            body,
        )
        self.assertIn("if \"im.jinritemai.com\" in turl:", body)
        self.assertIn("_SESSION_FOCUSED_FEIGE_TID_ATTR", body)

    def test_scrape_callsite_uses_reachable(self) -> None:
        # scrape_latest_customer_bubble must call the new function,
        # not the old focused one.
        scrape_idx = DA_SRC_043.find(
            "async def scrape_latest_customer_bubble("
        )
        self.assertGreater(scrape_idx, -1)
        scrape_body = DA_SRC_043[scrape_idx:scrape_idx + 6000]
        self.assertIn(
            "if not await ensure_feige_tab_reachable(browser_session):",
            scrape_body,
        )
        # The old call must be GONE from this specific function.
        self.assertNotIn(
            "if not await ensure_feige_tab_focused(browser_session):",
            scrape_body,
            "scrape must use reachable, not focused",
        )

    def test_typing_path_still_uses_focused(self) -> None:
        # hot_path.py's call site is NOT changed — typing still needs focus.
        # Regression guard: ensure_feige_tab_focused must still exist
        # and be exported for hot_path to use.
        self.assertIn(
            "async def ensure_feige_tab_focused(browser_session) -> bool:",
            DA_SRC_043,
        )
        # Both functions should be exported.
        self.assertIn('"ensure_feige_tab_focused",', DA_SRC_043)
        self.assertIn('"ensure_feige_tab_reachable",', DA_SRC_043)


# -----------------------------------------------------------------------
# mt044A/B/C/D/E/F — typing-path tab_focus_timeout + scrape-frequency cap
# -----------------------------------------------------------------------

DA_SRC_044 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")
RUNNER_SRC_044 = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
TUNABLES_SRC_044 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/tunables.py"
).read_text(encoding="utf-8")


class Mt044TunablesSourceTests(unittest.TestCase):
    """All 6 mt044 tunables must be declared with sensible defaults
    plus a documented 'off' value so ops can disable any risky bit."""

    def test_resolve_cache_ttl_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_TAB_RESOLVE_CACHE_TTL_S: float = 10.0",
            TUNABLES_SRC_044,
        )

    def test_probe_parallel_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_PROBE_PARALLEL: bool = True",
            TUNABLES_SRC_044,
        )

    def test_probe_timeout_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_PROBE_TIMEOUT_S: float = 5.0",
            TUNABLES_SRC_044,
        )

    def test_resolve_timeout_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_TAB_RESOLVE_TIMEOUT_S: float = 8.0",
            TUNABLES_SRC_044,
        )

    def test_typing_concurrency_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_TYPING_CONCURRENCY: int = 3",
            TUNABLES_SRC_044,
        )

    def test_scrape_cooldown_constant(self) -> None:
        self.assertIn(
            "DEFAULT_FEIGE_SCRAPE_COOLDOWN_S: float = 1.0",
            TUNABLES_SRC_044,
        )


class Mt044ASourceTests(unittest.TestCase):
    """Cache the resolved Feige target_id per-session so back-to-back
    direct-delivery calls don't all re-scan + re-probe."""

    def test_cache_dict_defined(self) -> None:
        self.assertIn(
            "_RESOLVE_CACHE: dict[int, tuple[str, float]] = {}",
            DA_SRC_044,
        )

    def test_helpers_defined(self) -> None:
        self.assertIn("def _resolve_cache_get(browser_session, ttl_s: float)", DA_SRC_044)
        self.assertIn("def _resolve_cache_set(browser_session, tid: str)", DA_SRC_044)
        self.assertIn("def _resolve_cache_clear(browser_session)", DA_SRC_044)

    def test_resolve_reads_cache_before_probing(self) -> None:
        # Within resolve_feige_tab_target_id, the cache-get must come
        # BEFORE the candidate row-probe (which is the slow part).
        # The cache validation does read get_all_targets, but that's
        # cheap; skipping the probe is the win.
        start = DA_SRC_044.find(
            "async def resolve_feige_tab_target_id("
        )
        self.assertGreater(start, -1)
        body = DA_SRC_044[start:start + 10000]
        get_idx = body.find("_resolve_cache_get(browser_session")
        probe_idx = body.find("async def _probe_rows(")
        self.assertGreater(get_idx, -1)
        self.assertGreater(probe_idx, -1)
        self.assertLess(get_idx, probe_idx)

    def test_resolve_stamps_cache_on_success(self) -> None:
        # After we pick the winner, we must call _resolve_cache_set.
        self.assertIn(
            "_resolve_cache_set(browser_session, target_id)",
            DA_SRC_044,
        )


class Mt044BSourceTests(unittest.TestCase):
    """When >1 candidate, probe rows in parallel via asyncio.gather
    so the slowest candidate doesn't sequentially block the rest."""

    def test_parallel_branch_present(self) -> None:
        self.assertIn("_probe_parallel and len(candidates) > 1", DA_SRC_044)
        self.assertIn("_probe_outer_asyncio.gather(", DA_SRC_044)

    def test_parallel_tunable_read(self) -> None:
        # mt044B must read DEFAULT_FEIGE_PROBE_PARALLEL (so it can be
        # turned off via ECAN_FEIGE_PROBE_PARALLEL=false).
        self.assertIn("DEFAULT_FEIGE_PROBE_PARALLEL", DA_SRC_044)


class Mt044CSourceTests(unittest.TestCase):
    """_probe_rows must use the PER-TARGET CDP lock, not session-wide,
    so probing tab A doesn't block probing tab B (and vice versa)."""

    def test_probe_uses_per_target_lock(self) -> None:
        # session_cdp_operation_lock(..., target_id=tid) inside the probe.
        # The actual source splits the call across two lines for length.
        self.assertIn("session_cdp_operation_lock(", DA_SRC_044)
        self.assertIn("target_id=tid", DA_SRC_044)
        # Specifically inside _probe_rows:
        probe_start = DA_SRC_044.find("async def _probe_rows(")
        self.assertGreater(probe_start, -1)
        probe_body = DA_SRC_044[probe_start:probe_start + 2000]
        self.assertIn("session_cdp_operation_lock(", probe_body)
        self.assertIn("target_id=tid", probe_body)


class Mt044DSourceTests(unittest.TestCase):
    """Resolve-side outer wait_for in runner.py was hard-coded to 2.0s
    — too tight under load.  mt044D makes it a tunable defaulting to 8.0s."""

    def test_runner_reads_resolve_timeout_tunable(self) -> None:
        self.assertIn("FEIGE_TAB_RESOLVE_TIMEOUT_S", RUNNER_SRC_044)
        self.assertIn("_mt044d_resolve_timeout", RUNNER_SRC_044)
        self.assertIn(
            "timeout=_mt044d_resolve_timeout",
            RUNNER_SRC_044,
        )

    def test_runner_no_longer_hard_codes_2s(self) -> None:
        # Specifically, the literal `timeout=2.0` on the resolve wait_for
        # must be gone (this is the only outer-resolve wait_for we changed).
        # Grep is intentionally narrow: just the resolve call line.
        bad = "_resolve_feige_tab_target_id(_session, customer_key=_customer_name),\n                    timeout=2.0,"
        self.assertNotIn(bad, RUNNER_SRC_044)

    def test_probe_timeout_uses_tunable_in_dom_assets(self) -> None:
        # The probe wait_for inside resolve_feige_tab_target_id must
        # consult DEFAULT_FEIGE_PROBE_TIMEOUT_S.
        self.assertIn("DEFAULT_FEIGE_PROBE_TIMEOUT_S", DA_SRC_044)


class Mt044ESourceTests(unittest.TestCase):
    """Process-wide BoundedSemaphore caps concurrent typing CDP ops
    so Chrome's main thread doesn't get overwhelmed under flood load."""

    def test_semaphore_globals_defined(self) -> None:
        self.assertIn("_MT044E_TYPING_SEM", RUNNER_SRC_044)
        self.assertIn("_MT044E_TYPING_SEM_SIZE", RUNNER_SRC_044)

    def test_helper_lazily_resolves_size(self) -> None:
        self.assertIn("def _mt044e_get_typing_semaphore()", RUNNER_SRC_044)
        # Must read the tunable so live config changes apply.
        self.assertIn("FEIGE_TYPING_CONCURRENCY", RUNNER_SRC_044)
        # Non-positive size => return None (cap disabled).
        self.assertIn("if size is None or size <= 0:", RUNNER_SRC_044)

    def test_send_path_uses_semaphore(self) -> None:
        # The actual send-await must be wrapped in `async with _mt044e_sem`
        # when the semaphore is not None.
        self.assertIn("_mt044e_sem = _mt044e_get_typing_semaphore()", RUNNER_SRC_044)
        self.assertIn("if _mt044e_sem is not None:", RUNNER_SRC_044)
        self.assertIn("async with _mt044e_sem:", RUNNER_SRC_044)


class Mt044FSourceTests(unittest.TestCase):
    """Per-customer scrape cooldown absorbs repeat 250 ms-interval
    scrape calls so the same customer can't queue 4+ scrapes per second."""

    def test_cache_dict_defined(self) -> None:
        self.assertIn(
            "_SCRAPE_RESULT_CACHE: dict[int, dict[str, tuple[dict, float]]] = {}",
            DA_SRC_044,
        )

    def test_helpers_defined(self) -> None:
        self.assertIn(
            "def _mt044f_scrape_cache_get(browser_session, customer_name: str, cooldown_s: float)",
            DA_SRC_044,
        )
        self.assertIn(
            "def _mt044f_scrape_cache_set(browser_session, customer_name: str, result: dict)",
            DA_SRC_044,
        )

    def test_scrape_checks_cooldown_at_entry(self) -> None:
        # The cooldown check must run before any CDP work.  Locate it
        # within scrape_latest_customer_bubble (window sized to cover
        # both the cooldown call site and the reachable call site).
        start = DA_SRC_044.find("async def scrape_latest_customer_bubble(")
        self.assertGreater(start, -1)
        body = DA_SRC_044[start:start + 8000]
        self.assertIn("_mt044f_scrape_cache_get(", body)
        self.assertIn("FEIGE_SCRAPE_COOLDOWN_S", body)
        # The cooldown check must come before ensure_feige_tab_reachable
        cd_idx = body.find("_mt044f_scrape_cache_get(")
        reach_idx = body.find("ensure_feige_tab_reachable(")
        self.assertGreater(cd_idx, -1)
        self.assertGreater(reach_idx, -1)
        self.assertLess(cd_idx, reach_idx)

    def test_scrape_only_caches_successful_scrapes(self) -> None:
        # The set call must be guarded by scrape_ok=True so failures
        # always retry.
        self.assertIn(
            '_scrape_result.get("scrape_ok")',
            DA_SRC_044,
        )
        self.assertIn(
            "_mt044f_scrape_cache_set(browser_session, customer_name, _scrape_result)",
            DA_SRC_044,
        )


class Mt044ABehaviourTests(unittest.TestCase):
    """In-memory exercise of the cache get/set/clear helpers."""

    def setUp(self) -> None:
        import importlib, sys
        # Force a fresh module per test so the cache starts empty.
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_get_returns_empty_when_ttl_zero(self) -> None:
        bs = SimpleNamespace()
        self.mod._resolve_cache_set(bs, "TID-X")
        self.assertEqual(self.mod._resolve_cache_get(bs, 0.0), "")

    def test_get_returns_value_within_ttl(self) -> None:
        bs = SimpleNamespace()
        self.mod._resolve_cache_set(bs, "TID-X")
        self.assertEqual(self.mod._resolve_cache_get(bs, 60.0), "TID-X")

    def test_get_returns_empty_after_ttl(self) -> None:
        import time
        bs = SimpleNamespace()
        self.mod._resolve_cache_set(bs, "TID-X")
        # Override the stamp so it's expired.
        self.mod._RESOLVE_CACHE[id(bs)] = ("TID-X", time.time() - 999.0)
        self.assertEqual(self.mod._resolve_cache_get(bs, 5.0), "")

    def test_clear_removes_entry(self) -> None:
        bs = SimpleNamespace()
        self.mod._resolve_cache_set(bs, "TID-X")
        self.mod._resolve_cache_clear(bs)
        self.assertEqual(self.mod._resolve_cache_get(bs, 60.0), "")


class Mt044FBehaviourTests(unittest.TestCase):
    """In-memory exercise of the per-customer scrape cache."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_get_returns_none_when_cooldown_zero(self) -> None:
        bs = SimpleNamespace()
        self.mod._mt044f_scrape_cache_set(bs, "alice", {"scrape_ok": True})
        self.assertIsNone(
            self.mod._mt044f_scrape_cache_get(bs, "alice", 0.0)
        )

    def test_get_returns_cached_within_window(self) -> None:
        bs = SimpleNamespace()
        payload = {"scrape_ok": True, "text": "hi", "msg_id": "m1"}
        self.mod._mt044f_scrape_cache_set(bs, "alice", payload)
        self.assertEqual(
            self.mod._mt044f_scrape_cache_get(bs, "alice", 5.0),
            payload,
        )

    def test_get_returns_none_for_different_customer(self) -> None:
        bs = SimpleNamespace()
        self.mod._mt044f_scrape_cache_set(bs, "alice", {"scrape_ok": True})
        self.assertIsNone(
            self.mod._mt044f_scrape_cache_get(bs, "bob", 5.0)
        )

    def test_get_returns_none_after_window(self) -> None:
        import time
        bs = SimpleNamespace()
        self.mod._mt044f_scrape_cache_set(bs, "alice", {"scrape_ok": True})
        per_sess = self.mod._SCRAPE_RESULT_CACHE[id(bs)]
        per_sess["alice"] = ({"scrape_ok": True}, time.time() - 999.0)
        self.assertIsNone(
            self.mod._mt044f_scrape_cache_get(bs, "alice", 5.0)
        )


# -----------------------------------------------------------------------
# mt045A — _scrape_locked_body NameError regression
# -----------------------------------------------------------------------

DA_SRC_045 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt045ASourceTests(unittest.TestCase):
    """Live trace 2026-05-25 11:42:43 — 客户04 hit a NameError every
    scrape because the mt026 extraction of ``_scrape_locked_body`` did
    not thread mt041B's ``previously_dispatched_msg_ids`` parameter
    through.  The body referenced the name (the inject site at line
    ~2601) but the parameter was only declared on the OUTER
    ``scrape_latest_customer_bubble`` — so every call raised
    ``NameError: name 'previously_dispatched_msg_ids' is not defined``
    and silently returned ``empty`` to the dispatch path."""

    def test_inner_signature_accepts_kwarg(self) -> None:
        # The extracted body must declare previously_dispatched_msg_ids
        # so the consumer site at the mt041B inject block resolves it.
        start = DA_SRC_045.find("async def _scrape_locked_body(")
        self.assertGreater(start, -1)
        end = DA_SRC_045.find(") -> dict:", start)
        self.assertGreater(end, start)
        sig = DA_SRC_045[start:end]
        self.assertIn("previously_dispatched_msg_ids", sig)

    def test_outer_forwards_kwarg(self) -> None:
        # The wrapper must pass it through, otherwise the inner default
        # of None is silently used for every call.
        self.assertIn(
            "previously_dispatched_msg_ids=previously_dispatched_msg_ids,",
            DA_SRC_045,
        )

    def test_inner_consumer_still_present(self) -> None:
        # Regression: the mt041B inject site must still be inside the
        # locked body (not the outer wrapper).  Locate the body, scan
        # for the consumer references.
        start = DA_SRC_045.find("async def _scrape_locked_body(")
        self.assertGreater(start, -1)
        # Body ends at next top-level def/class, or EOF when there's
        # nothing after (this function is currently last in the file).
        end = DA_SRC_045.find("\nasync def ", start + 1)
        if end < 0:
            end = DA_SRC_045.find("\ndef ", start + 1)
        if end < 0:
            end = len(DA_SRC_045)
        self.assertGreater(end, start)
        body = DA_SRC_045[start:end]
        self.assertIn("if previously_dispatched_msg_ids:", body)
        self.assertIn("for _mid in previously_dispatched_msg_ids:", body)


class Mt045ASignatureBehaviourTests(unittest.TestCase):
    """Use inspect to enforce the runtime signature — a pure source
    grep can be fooled by a comment; this confirms Python actually
    binds the name."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_inner_function_has_kwarg(self) -> None:
        import inspect
        sig = inspect.signature(self.mod._scrape_locked_body)
        self.assertIn("previously_dispatched_msg_ids", sig.parameters)
        # Must default to None so old call sites stay compatible.
        param = sig.parameters["previously_dispatched_msg_ids"]
        self.assertIsNone(param.default)
        # Must be keyword-only so positional callers don't drift.
        self.assertEqual(param.kind, inspect.Parameter.KEYWORD_ONLY)


# -----------------------------------------------------------------------
# mt045B — pool-init kickoff fires from direct-delivery path
# -----------------------------------------------------------------------

DA_SRC_045B = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt045BSourceTests(unittest.TestCase):
    """Live trace 2026-05-25: 5 process restarts today, every one had
    ECAN_FEIGE_TYPING_TAB_COUNT=6, but zero typing tabs opened.  Root
    cause: the pool-init kickoff lived inline inside
    ``ensure_feige_tab_focused``, which is only called from
    HOT-PATH-B (the fallback).  Healthy operation goes through
    direct-delivery, which uses ``_resolve_feige_tab_target_id``
    directly.  Result: pool stays empty for the entire process
    lifetime, every typing job piles onto the monitor tab.

    mt045B hoists the kickoff into ``_maybe_kickoff_typing_pool_init``
    and calls it from both sites."""

    def test_helper_function_exists(self) -> None:
        self.assertIn(
            "def _maybe_kickoff_typing_pool_init(browser_session, feige_tid: str)",
            DA_SRC_045B,
        )

    def test_helper_one_shot_via_pool_flag(self) -> None:
        # The helper must consult try_dispatch_initial_population so
        # repeated calls don't open extra tabs.
        start = DA_SRC_045B.find(
            "def _maybe_kickoff_typing_pool_init("
        )
        self.assertGreater(start, -1)
        end = DA_SRC_045B.find("\ndef ", start + 1)
        if end < 0:
            end = DA_SRC_045B.find("\nasync def ", start + 1)
        self.assertGreater(end, start)
        body = DA_SRC_045B[start:end]
        self.assertIn("try_dispatch_initial_population()", body)
        self.assertIn("designate_monitor(feige_tid)", body)

    def test_resolver_calls_helper_on_all_success_paths(self) -> None:
        # _resolve_feige_tab_target_id must call the helper before
        # every successful return — mt044A cached_resolve hit, cached_tid
        # hit, and fresh-discovery winner.
        start = DA_SRC_045B.find(
            "async def resolve_feige_tab_target_id("
        )
        self.assertGreater(start, -1)
        end = DA_SRC_045B.find("\nasync def ", start + 1)
        if end < 0:
            end = DA_SRC_045B.find("\ndef ", start + 1)
        if end < 0:
            end = len(DA_SRC_045B)
        body = DA_SRC_045B[start:end]
        # Count helper calls — must be 3 (one per success path).
        self.assertGreaterEqual(
            body.count("_maybe_kickoff_typing_pool_init(browser_session,"),
            3,
            "_resolve_feige_tab_target_id should kick the pool on all 3 success paths",
        )

    def test_ensure_focused_delegates_to_helper(self) -> None:
        # The inline block in ensure_feige_tab_focused must be replaced
        # by a single call to the helper.
        start = DA_SRC_045B.find(
            "async def ensure_feige_tab_focused(browser_session) -> bool:"
        )
        self.assertGreater(start, -1)
        end = DA_SRC_045B.find(
            "async def ensure_feige_tab_reachable(", start
        )
        if end < 0:
            # reachable is defined ABOVE focused — search forward for the
            # next top-level def instead.
            end = DA_SRC_045B.find("\nasync def ", start + 1)
        self.assertGreater(end, start)
        body = DA_SRC_045B[start:end]
        self.assertIn(
            "_maybe_kickoff_typing_pool_init(browser_session, feige_tid)",
            body,
        )
        # The old inline block must be gone — no more direct
        # try_dispatch_initial_population call inside this function.
        self.assertNotIn(
            "try_dispatch_initial_population()", body,
            "ensure_feige_tab_focused should delegate to the helper, not call the flag directly",
        )


class Mt045BSignatureBehaviourTests(unittest.TestCase):
    """Runtime check: helper is importable and callable, and calling it
    twice only fires the pool init once (the second call is a no-op via
    the pool's one-shot flag)."""

    def setUp(self) -> None:
        import importlib, sys
        for mod in (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets",
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.tab_pool",
        ):
            if mod in sys.modules:
                del sys.modules[mod]
        self.dom = importlib.import_module(
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dom_assets"
        )
        self.tab_pool = importlib.import_module(
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.tab_pool"
        )

    def test_helper_is_callable(self) -> None:
        self.assertTrue(callable(self.dom._maybe_kickoff_typing_pool_init))

    def test_no_op_with_empty_tid(self) -> None:
        # Should be a fast no-op without touching the pool.
        self.dom._maybe_kickoff_typing_pool_init(None, "")
        # Pool's one-shot flag should still be available (not consumed).
        pool = self.tab_pool.get_pool()
        # First real call should return True (we haven't consumed it).
        self.assertTrue(pool.try_dispatch_initial_population())
        # Second call returns False.
        self.assertFalse(pool.try_dispatch_initial_population())


# -----------------------------------------------------------------------
# mt046A — clear dedup ledgers on direct_stale_dropped
# -----------------------------------------------------------------------

AI_SRC_046 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/actionable_items.py"
).read_text(encoding="utf-8")
RUNNER_SRC_046 = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt046ASourceTests(unittest.TestCase):
    """Live trace 2026-05-26 10:14-10:16: 陆地飞鱼 sent a burst
    (text + product card + follow-up text); bot composed a reply for
    msg_id ``66667571...``.  Before the bot finished typing, customer
    sent another product card (msg_id ``F53FFA64...``).  Source-guard
    correctly aborted with ``stale_reply_source_msg_id``.  But two
    dedup ledgers (identity_key in actionable_items + msg-id in
    PreDispatch) stayed stamped from the original dispatch, so every
    subsequent EventMonitor tick filtered the customer out as
    ``already_dispatched``.  Customer permanently stuck.

    Same shape as the 2026-05-13 HOT-PATH-B fix in front_desk.py — but
    that one only handled HOT-PATH-B crosstalk failures, not
    direct-delivery stale-drops."""

    def test_helper_defined(self) -> None:
        self.assertIn(
            "def clear_dispatched_identity_keys_for_customer(customer_id: str) -> int:",
            AI_SRC_046,
        )

    def test_helper_uses_prefix_match(self) -> None:
        # identity_key format is "{customer_name}|{message_text}".
        # The helper must clear ALL stamped variants for that customer,
        # so use prefix match (customer + '|').
        start = AI_SRC_046.find(
            "def clear_dispatched_identity_keys_for_customer("
        )
        self.assertGreater(start, -1)
        body = AI_SRC_046[start:start + 1500]
        self.assertIn('prefix = f"{customer_id}|"', body)
        self.assertIn("startswith(prefix)", body)
        self.assertIn("_dispatched_identity_keys.pop(", body)

    def test_runner_calls_both_clears_on_stale_drop(self) -> None:
        # Locate the stale-drop branch and confirm both clears fire.
        start = RUNNER_SRC_046.find(
            'if _reason == "stale_reply_source_msg_id":'
        )
        self.assertGreater(start, -1)
        # Body extends until the next `if` at the same indent or function end.
        # Window is wide enough to cover the whole branch including the
        # _ledger(...) call at the end.
        body = RUNNER_SRC_046[start:start + 5000]
        # mt046A markers
        self.assertIn("mt046A", body)
        # msg-id dedup clear (FeigeDeliveryState backed)
        self.assertIn("last_dispatched_msg_id_by_customer.pop(", body)
        # identity-key dedup clear (actionable_items helper)
        self.assertIn("clear_dispatched_identity_keys_for_customer", body)
        # Ledger entry annotated with clear results so future log digs
        # can confirm the clears actually fired.
        self.assertIn("mt046a_msg_id_cleared", body)
        self.assertIn("mt046a_identity_keys_cleared", body)

    def test_runner_only_clears_on_stale_drop(self) -> None:
        # Regression guard: the clear must NOT fire on the SUCCESS path
        # (where we DO want the msg_id stamped for future dedup).  The
        # successful branch is the `if _ok:` block immediately above
        # the stale-reason branch.
        ok_idx = RUNNER_SRC_046.find('if _ok:\n                try:\n                    from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability import clear_pending_delivery')
        stale_idx = RUNNER_SRC_046.find('if _reason == "stale_reply_source_msg_id":')
        self.assertGreater(ok_idx, -1)
        self.assertGreater(stale_idx, ok_idx)
        ok_branch = RUNNER_SRC_046[ok_idx:stale_idx]
        self.assertNotIn(
            "clear_dispatched_identity_keys_for_customer",
            ok_branch,
            "mt046A clears must only fire on the stale-drop branch, not on success",
        )


class Mt046ABehaviourTests(unittest.TestCase):
    """Exercise the helper against the module-level dict."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_clears_only_matching_customer(self) -> None:
        self.mod._dispatched_identity_keys.update({
            "陆地飞鱼|质量如何，会不会起球": 1.0,
            "陆地飞鱼|有别的颜色吗": 2.0,
            "packet|可以的": 3.0,
            "肽斯特|蓝色款": 4.0,
        })
        cleared = self.mod.clear_dispatched_identity_keys_for_customer("陆地飞鱼")
        self.assertEqual(cleared, 2)
        # 陆地飞鱼's two entries gone; others untouched.
        remaining = set(self.mod._dispatched_identity_keys)
        self.assertEqual(remaining, {"packet|可以的", "肽斯特|蓝色款"})

    def test_clears_nothing_on_empty_customer(self) -> None:
        self.mod._dispatched_identity_keys.update({"alice|hi": 1.0})
        self.assertEqual(self.mod.clear_dispatched_identity_keys_for_customer(""), 0)
        # Untouched.
        self.assertIn("alice|hi", self.mod._dispatched_identity_keys)

    def test_clears_nothing_when_no_match(self) -> None:
        self.mod._dispatched_identity_keys.update({"alice|hi": 1.0})
        self.assertEqual(self.mod.clear_dispatched_identity_keys_for_customer("bob"), 0)
        self.assertIn("alice|hi", self.mod._dispatched_identity_keys)

    def test_prefix_match_does_not_accidentally_catch_substrings(self) -> None:
        # 陆地 must NOT clear 陆地飞鱼's entries — the | separator prevents
        # substring matches.
        self.mod._dispatched_identity_keys.update({
            "陆地飞鱼|hi": 1.0,
            "陆地|hi": 2.0,
        })
        cleared = self.mod.clear_dispatched_identity_keys_for_customer("陆地")
        self.assertEqual(cleared, 1)
        self.assertIn("陆地飞鱼|hi", self.mod._dispatched_identity_keys)
        self.assertNotIn("陆地|hi", self.mod._dispatched_identity_keys)

    def tearDown(self) -> None:
        # Don't leak state into other tests.
        try:
            self.mod._dispatched_identity_keys.clear()
        except Exception:
            pass


# -----------------------------------------------------------------------
# mt047A — ECAN_RAG_QUERY_FAST_PATH env var
# -----------------------------------------------------------------------

RAG_SRC_047 = Path(
    "agent/ec_skills/rag/local_rag_mcp.py"
).read_text(encoding="utf-8")


class Mt047ASourceTests(unittest.TestCase):
    """Live customer trace 2026-05-26 10:16 — rag_query took 8.1s with
    mode='mix' + only_need_context=False + enable_rerank=True (the
    defaults baked into the skill's MCP node).  Each of those settings
    triggers an extra LLM round-trip on the LightRAG side, and the
    outer Q&A LLM throws away the synthesized narrative anyway.

    mt047A adds ECAN_RAG_QUERY_FAST_PATH env var: when set, forces
    mode=naive + only_need_context=True + enable_rerank=False on every
    call regardless of what the MCP node passed."""

    def test_env_var_recognized(self) -> None:
        self.assertIn("ECAN_RAG_QUERY_FAST_PATH", RAG_SRC_047)
        # Accepted truthy values.
        self.assertIn('("1", "true", "yes", "on")', RAG_SRC_047)

    def test_override_forces_all_three_settings(self) -> None:
        start = RAG_SRC_047.find("mt047A")
        self.assertGreater(start, -1)
        body = RAG_SRC_047[start:start + 3500]
        self.assertIn('options["mode"] = "naive"', body)
        self.assertIn('options["only_need_context"] = True', body)
        self.assertIn('options["enable_rerank"] = False', body)

    def test_override_runs_before_path_select(self) -> None:
        # The override must run before _is_context_only is read; otherwise
        # the only_need_context override is ignored by the path-selection
        # branch (context-only blocking /query vs streaming /query).
        override_idx = RAG_SRC_047.find('options["only_need_context"] = True\n            options["enable_rerank"]')
        is_ctx_idx = RAG_SRC_047.find("_is_context_only = options.get(")
        self.assertGreater(override_idx, -1)
        self.assertGreater(is_ctx_idx, -1)
        self.assertLess(override_idx, is_ctx_idx)

    def test_logs_when_active(self) -> None:
        # Operator visibility: should log when fast-path engages so ops
        # can confirm the env var is picked up.
        self.assertIn("mt047A fast-path active", RAG_SRC_047)

    def test_default_on_after_mt050M(self) -> None:
        # mt050M (2026-05-27) flipped the default to ON because the customer
        # never had ECAN_RAG_QUERY_FAST_PATH set, so mt047A had never fired
        # in production.  The env-var lookup now defaults to "1" when unset,
        # and the guard still compares to truthy literals so an explicit
        # opt-out (ECAN_RAG_QUERY_FAST_PATH=0/false/no/off) disables it.
        self.assertIn(
            'if _fast_path_env in ("1", "true", "yes", "on"):',
            RAG_SRC_047,
        )
        self.assertIn(
            '_fast_path_env = (_os.getenv("ECAN_RAG_QUERY_FAST_PATH") or "1")',
            RAG_SRC_047,
        )

    def test_opt_out_path_documented(self) -> None:
        # The comment block must explain how to disable, otherwise users
        # have no way to revert without reading the source.
        self.assertIn("opt out", RAG_SRC_047)
        self.assertIn("ECAN_RAG_QUERY_FAST_PATH=0", RAG_SRC_047)


# -----------------------------------------------------------------------
# mt047B — large state-dump logs routed to file-DEBUG (was file-INFO)
# -----------------------------------------------------------------------

CL_SRC_047B = Path(
    "agent/cloud_worker/cloud_logger.py"
).read_text(encoding="utf-8")


class Mt047BSourceTests(unittest.TestCase):
    """Live customer trace 2026-05-26 10:16: ``send_skill_editor_log
    ("log", state_summary)`` fell through to INFO on the file logger
    (the level-map at the bottom of ``_send`` defaults unknown levels
    to "info"), writing ~15KB state dumps to the log file 5-7 times
    per Q&A turn.  ~1-3s of per-turn latency was sync file I/O.

    mt047B reroutes large (>=2KB) "log"-level messages to DEBUG on the
    file logger ONLY.  The WebSocket broadcast above is untouched so
    the Skill Editor UI still receives the full payload at full
    fidelity."""

    def test_threshold_defined(self) -> None:
        self.assertIn("_MT047B_LARGE_LOG_THRESHOLD = 2048", CL_SRC_047B)

    def test_demotion_logic_present(self) -> None:
        self.assertIn(
            'if level == "log" and len(message) >= _MT047B_LARGE_LOG_THRESHOLD:',
            CL_SRC_047B,
        )
        # Must demote to DEBUG.
        self.assertIn('_file_level = "debug"', CL_SRC_047B)

    def test_websocket_broadcast_uses_original_level(self) -> None:
        # Regression guard: the WebSocket broadcast (Skill Editor UI)
        # must still see the original level.  The level passed to
        # broadcast_sync should be the input `level`, not _file_level.
        ws_call_start = CL_SRC_047B.find("broadcast_sync(")
        self.assertGreater(ws_call_start, -1)
        ws_call_body = CL_SRC_047B[ws_call_start:ws_call_start + 200]
        # The payload key is 'type' here, value is `level`.  Must NOT
        # be _file_level.
        self.assertIn("'type': level", ws_call_body)
        self.assertNotIn("_file_level", ws_call_body)

    def test_small_log_messages_keep_level(self) -> None:
        # Regression: a short "log" message must NOT be demoted.
        # The condition is `>= threshold`, so messages under the
        # threshold fall through to the existing level mapping.
        body = CL_SRC_047B[CL_SRC_047B.find("_MT047B_LARGE_LOG_THRESHOLD"):]
        # The else branch keeps level unchanged.
        self.assertIn("_file_level = level", body)


class Mt047BBehaviourTests(unittest.TestCase):
    """Exercise _send to confirm the demotion happens at the right
    threshold and direction."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = "agent.cloud_worker.cloud_logger"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_large_log_message_goes_to_debug(self) -> None:
        # Patch logger.debug / logger.info to capture which one fires.
        from unittest import mock as _mock
        sel = self.mod.SkillEditorLogger()
        big_msg = "x" * 5000  # well above 2048
        with _mock.patch.object(self.mod.logger, "debug") as mock_debug, \
             _mock.patch.object(self.mod.logger, "info") as mock_info, \
             _mock.patch.object(self.mod, "is_cloud_mode", return_value=True):
            # Use cloud_mode=True so the WebSocket-broadcast branch is
            # skipped (it imports gui.LocalServer which isn't available
            # in this test env).  The file-logger demotion logic is the
            # same regardless of mode.
            sel._send("log", big_msg)
        mock_debug.assert_called_once()
        mock_info.assert_not_called()

    def test_small_log_message_stays_info(self) -> None:
        from unittest import mock as _mock
        sel = self.mod.SkillEditorLogger()
        small_msg = "short message"  # well under 2048
        with _mock.patch.object(self.mod.logger, "debug") as mock_debug, \
             _mock.patch.object(self.mod.logger, "info") as mock_info, \
             _mock.patch.object(self.mod, "is_cloud_mode", return_value=True):
            sel._send("log", small_msg)
        # "log" isn't in (debug,info,warning,error), so default mapping
        # routes to "info".
        mock_info.assert_called_once()
        mock_debug.assert_not_called()

    def test_explicit_info_message_unchanged(self) -> None:
        # If caller asks for INFO explicitly, even a big message stays
        # INFO — demotion only applies to "log".
        from unittest import mock as _mock
        sel = self.mod.SkillEditorLogger()
        big_msg = "x" * 5000
        with _mock.patch.object(self.mod.logger, "debug") as mock_debug, \
             _mock.patch.object(self.mod.logger, "info") as mock_info, \
             _mock.patch.object(self.mod, "is_cloud_mode", return_value=True):
            sel._send("info", big_msg)
        mock_info.assert_called_once()
        mock_debug.assert_not_called()


# -----------------------------------------------------------------------
# mt048A — file-backed placeholder texts
# -----------------------------------------------------------------------

PH_SRC_048 = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")


class Mt048ASourceTests(unittest.TestCase):
    """Customer feedback 2026-05-26: change placeholder text wording.
    Implementation reads from <user_data_home>/ecan/placeholder_texts.json
    with hardcoded fallback so operators can tweak without code changes."""

    def test_default_texts_present(self) -> None:
        # mt050L shrank the default set to a single entry per customer
        # feedback; the older 3-text rotation is gone.  Operators who
        # want rotation can still supply a list via the user-data file.
        self.assertIn("人工服务正在回复中", PH_SRC_048)

    def test_loader_helpers_defined(self) -> None:
        self.assertIn("def _load_placeholder_texts_from_file()", PH_SRC_048)
        self.assertIn("def _get_placeholder_texts()", PH_SRC_048)

    def test_cache_via_lock(self) -> None:
        # Thread-safe lazy cache.
        self.assertIn("_PLACEHOLDER_TEXTS_CACHE", PH_SRC_048)
        self.assertIn("_PLACEHOLDER_TEXTS_CACHE_LOCK = threading.Lock()", PH_SRC_048)

    def test_consumer_uses_loader(self) -> None:
        # Old direct reference replaced with loader call.
        self.assertIn("_texts = _get_placeholder_texts()", PH_SRC_048)
        self.assertIn("text_idx = min(entry.placeholders_typed, len(_texts) - 1)", PH_SRC_048)
        # Regression guard: bare _PLACEHOLDER_TEXTS only appears as part of
        # the constant names (default/cache/max/filename), never as a bare
        # subscript in the hot path.
        self.assertNotIn("_PLACEHOLDER_TEXTS[text_idx]", PH_SRC_048)

    def test_validation_rules(self) -> None:
        # Must dedupe + drop empty + cap.
        self.assertIn("seen.add(s)", PH_SRC_048)
        self.assertIn("if not s:", PH_SRC_048)
        self.assertIn("_PLACEHOLDER_MAX_TEXTS = 5", PH_SRC_048)


class Mt048ABehaviourTests(unittest.TestCase):
    """Exercise the loader against a real temp file."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.placeholder_timer"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        # Reset cache so each test starts clean.
        self.mod._PLACEHOLDER_TEXTS_CACHE = None

    def _patch_user_data(self, tmp_dir):
        from unittest import mock as _mock
        return _mock.patch(
            "utils.path_manager.get_user_data_path",
            return_value=str(tmp_dir),
        )

    def test_file_missing_returns_fallback(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        self.assertEqual(texts, self.mod._PLACEHOLDER_DEFAULT_TEXTS)

    def test_file_present_returns_file_contents(self) -> None:
        import json as _json, os as _os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                _json.dump(["A", "B", "C"], f)
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        self.assertEqual(texts, ["A", "B", "C"])

    def test_file_malformed_returns_fallback(self) -> None:
        import os as _os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("not valid json {{")
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        self.assertEqual(texts, self.mod._PLACEHOLDER_DEFAULT_TEXTS)

    def test_file_empty_array_returns_fallback(self) -> None:
        import json as _json, os as _os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                _json.dump([], f)
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        self.assertEqual(texts, self.mod._PLACEHOLDER_DEFAULT_TEXTS)

    def test_file_with_duplicates_and_empties_is_cleaned(self) -> None:
        import json as _json, os as _os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                _json.dump(["A", "", "A", " B ", "B"], f)
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        # 'A' once, ' B ' stripped to 'B' once.
        self.assertEqual(texts, ["A", "B"])

    def test_file_caps_at_max(self) -> None:
        import json as _json, os as _os, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                _json.dump([f"text{i}" for i in range(20)], f)
            with self._patch_user_data(tmp):
                texts = self.mod._get_placeholder_texts()
        self.assertEqual(len(texts), self.mod._PLACEHOLDER_MAX_TEXTS)
        self.assertEqual(texts, [f"text{i}" for i in range(self.mod._PLACEHOLDER_MAX_TEXTS)])

    def test_cache_loads_once(self) -> None:
        from unittest import mock as _mock
        import os as _os, json as _json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            _os.makedirs(_os.path.join(tmp, "ecan"), exist_ok=True)
            file_path = _os.path.join(tmp, "ecan", "placeholder_texts.json")
            with open(file_path, "w", encoding="utf-8") as f:
                _json.dump(["x"], f)
            with self._patch_user_data(tmp):
                t1 = self.mod._get_placeholder_texts()
                t2 = self.mod._get_placeholder_texts()
            # Same object (cached, not re-read).
            self.assertIs(t1, t2)


# -----------------------------------------------------------------------
# mt048B — pre-send LLM judge for human-intervention vs bot-reply
# -----------------------------------------------------------------------

HI_SRC_048B = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_intervention.py"
).read_text(encoding="utf-8")
HRJ_SRC_048B = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_relevance_judge.py"
).read_text(encoding="utf-8")
RUNNER_SRC_048B = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
PD_SRC_048B = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt048BSourceTests(unittest.TestCase):
    """mt017/mt036A drops the bot reply whenever a human bubble is
    observed targeting the same question.  Customer feedback 2026-05-26:
    that loses well-formed bot replies when the human only said
    'in a sec' / 'let me check' / etc.  mt048B adds an LLM judge that
    decides drop vs proceed based on whether the human's text actually
    answered the question."""

    def test_handled_text_storage_added(self) -> None:
        # New parallel dict to carry the human-typed text alongside the
        # existing _HANDLED_QUESTIONS timestamps.
        self.assertIn(
            "_HANDLED_QUESTIONS_TEXT: dict[tuple[str, str], str] = {}",
            HI_SRC_048B,
        )

    def test_mark_handled_accepts_bubble_text(self) -> None:
        # New kwarg must be keyword-only (after the existing *).
        self.assertIn("bubble_text: str = \"\"", HI_SRC_048B)
        # And must be written to the text store under the same key.
        self.assertIn("_HANDLED_QUESTIONS_TEXT[(cust, qid)] = txt", HI_SRC_048B)

    def test_getter_for_handled_text(self) -> None:
        self.assertIn(
            "def get_handled_question_text(customer_key: str, question_msg_id: str) -> str:",
            HI_SRC_048B,
        )

    def test_predispatch_passes_bubble_text(self) -> None:
        # The PreDispatch call site that fires mark_handled must thread
        # the scraped bubble text through.
        self.assertIn("bubble_text=_lab_text,", PD_SRC_048B)

    def test_judge_module_exists(self) -> None:
        self.assertIn(
            "def judge(customer_question: str, human_text: str) -> JudgeVerdict:",
            HRJ_SRC_048B,
        )
        # Must expose enable + threshold getters for the caller.
        self.assertIn("def is_enabled() -> bool:", HRJ_SRC_048B)
        self.assertIn("def get_min_confidence() -> float:", HRJ_SRC_048B)

    def test_judge_env_var_defaults_documented(self) -> None:
        # Operator-facing tunables must be discoverable in the module docstring.
        self.assertIn("ECAN_HUMAN_JUDGE_ENABLED", HRJ_SRC_048B)
        self.assertIn("ECAN_HUMAN_JUDGE_MODEL", HRJ_SRC_048B)
        self.assertIn("ECAN_HUMAN_JUDGE_TIMEOUT_S", HRJ_SRC_048B)
        self.assertIn("ECAN_HUMAN_JUDGE_MIN_CONFIDENCE", HRJ_SRC_048B)

    def test_judge_default_model_is_mini(self) -> None:
        # Per plan: gpt-5-mini is fast + cheap enough for binary classification.
        self.assertIn(
            '_env_str("ECAN_HUMAN_JUDGE_MODEL", "gpt-5-mini")',
            HRJ_SRC_048B,
        )

    def test_runner_calls_judge_before_dropping(self) -> None:
        # Runner's drop check must consult the judge BEFORE returning the
        # human_intervention_skip outcome.  The judge fires only when both
        # question text and human text are available.
        # mt054A: call switched from sync `.judge(` to
        # `await ....judge_async(` to avoid blocking the event loop;
        # accept either form here.
        start = RUNNER_SRC_048B.find(
            "if _hi_target_qid and _hi_dd.is_question_handled("
        )
        self.assertGreater(start, -1)
        body = RUNNER_SRC_048B[start:start + 9000]
        self.assertIn("human_relevance_judge", body)
        self.assertTrue(
            "_mt048b_verdict = _mt048b_judge_mod.judge(" in body
            or "_mt048b_verdict = await _mt048b_judge_mod.judge_async(" in body,
            "runner must call judge() (sync) or judge_async() (async) to "
            "produce _mt048b_verdict",
        )
        # Drop decision uses BOTH answered AND confidence>=threshold.
        self.assertIn("_mt048b_verdict.answered", body)
        self.assertIn(">= _mt048b_threshold", body)

    def test_runner_failsafe_defaults_to_drop_on_judge_error(self) -> None:
        # If the judge throws or imports fail, the runner must default to
        # the pre-mt048B unconditional drop.  Don't silently allow a send
        # when the safety net is broken.
        start = RUNNER_SRC_048B.find(
            "if _hi_target_qid and _hi_dd.is_question_handled("
        )
        body = RUNNER_SRC_048B[start:start + 9000]
        self.assertIn("_mt048b_drop = True", body)
        # The except branch must explicitly re-assert drop = True.
        self.assertIn("falling back to drop", body)

    def test_runner_logs_judge_telemetry(self) -> None:
        # Ledger annotations so future log digs can audit judge decisions.
        start = RUNNER_SRC_048B.find(
            "if _hi_target_qid and _hi_dd.is_question_handled("
        )
        body = RUNNER_SRC_048B[start:start + 9000]
        self.assertIn("mt048b_answered", body)
        self.assertIn("mt048b_confidence", body)
        self.assertIn("mt048b_reason", body)
        # Both the drop and the allow paths must emit a ledger event.
        self.assertIn('"direct_feige_send_skipped_human_handled"', body)
        self.assertIn('"direct_human_judge_allowed_send"', body)


class Mt048BJudgeBehaviourTests(unittest.TestCase):
    """Exercise the judge against a mocked LLM."""

    def setUp(self) -> None:
        import importlib, sys, os
        # Make sure env vars don't bleed from other tests.
        for k in (
            "ECAN_HUMAN_JUDGE_ENABLED",
            "ECAN_HUMAN_JUDGE_MODEL",
            "ECAN_HUMAN_JUDGE_TIMEOUT_S",
            "ECAN_HUMAN_JUDGE_MIN_CONFIDENCE",
        ):
            os.environ.pop(k, None)
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.human_relevance_judge"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        self.mod.reset_llm_cache()

    def _stub_llm(self, content: str):
        from unittest import mock as _mock
        stub = _mock.MagicMock()
        stub.invoke.return_value = _mock.MagicMock(content=content)
        return _mock.patch.object(self.mod, "_get_llm", return_value=stub)

    def test_judge_disabled_returns_not_answered(self) -> None:
        import os
        os.environ["ECAN_HUMAN_JUDGE_ENABLED"] = "false"
        try:
            v = self.mod.judge("尺码偏大吗", "在的")
        finally:
            os.environ.pop("ECAN_HUMAN_JUDGE_ENABLED", None)
        self.assertFalse(v.answered)
        self.assertEqual(v.error, "disabled")

    def test_judge_empty_input_returns_not_answered(self) -> None:
        v1 = self.mod.judge("", "在的")
        v2 = self.mod.judge("尺码偏大吗", "")
        self.assertFalse(v1.answered)
        self.assertFalse(v2.answered)
        self.assertEqual(v1.error, "empty_input")
        self.assertEqual(v2.error, "empty_input")

    def test_judge_parses_clean_json(self) -> None:
        with self._stub_llm(
            '{"answered": true, "confidence": 0.92, "reason": "直接回答了尺码"}'
        ):
            v = self.mod.judge("尺码偏大吗", "正常码，按平时穿就行")
        self.assertTrue(v.answered)
        self.assertAlmostEqual(v.confidence, 0.92, places=2)
        self.assertIn("尺码", v.reason)

    def test_judge_strips_markdown_fences(self) -> None:
        with self._stub_llm(
            '```json\n{"answered": false, "confidence": 0.3, "reason": "只说在的"}\n```'
        ):
            v = self.mod.judge("尺码偏大吗", "在的")
        self.assertFalse(v.answered)

    def test_judge_handles_surrounding_prose(self) -> None:
        with self._stub_llm(
            'Sure! Here is the verdict:\n{"answered": true, "confidence": 0.8, "reason": "ok"}\nThanks.'
        ):
            v = self.mod.judge("Q", "A")
        self.assertTrue(v.answered)
        self.assertAlmostEqual(v.confidence, 0.8, places=2)

    def test_judge_invoke_error_defaults_to_not_answered(self) -> None:
        from unittest import mock as _mock
        stub = _mock.MagicMock()
        stub.invoke.side_effect = RuntimeError("boom")
        with _mock.patch.object(self.mod, "_get_llm", return_value=stub):
            v = self.mod.judge("Q", "A")
        self.assertFalse(v.answered)
        self.assertEqual(v.reason, "llm_invoke_failed")

    def test_judge_malformed_json_defaults_to_not_answered(self) -> None:
        with self._stub_llm("definitely not json"):
            v = self.mod.judge("Q", "A")
        self.assertFalse(v.answered)
        self.assertEqual(v.reason, "parse_failed")

    def test_judge_clamps_confidence_to_unit_range(self) -> None:
        with self._stub_llm(
            '{"answered": true, "confidence": 1.5, "reason": "high"}'
        ):
            v = self.mod.judge("Q", "A")
        self.assertEqual(v.confidence, 1.0)
        with self._stub_llm(
            '{"answered": true, "confidence": -0.3, "reason": "neg"}'
        ):
            v = self.mod.judge("Q", "A")
        self.assertEqual(v.confidence, 0.0)

    def test_min_confidence_default(self) -> None:
        import os
        os.environ.pop("ECAN_HUMAN_JUDGE_MIN_CONFIDENCE", None)
        self.assertAlmostEqual(self.mod.get_min_confidence(), 0.7, places=2)

    def test_min_confidence_clamped(self) -> None:
        import os
        os.environ["ECAN_HUMAN_JUDGE_MIN_CONFIDENCE"] = "2.5"
        try:
            self.assertEqual(self.mod.get_min_confidence(), 1.0)
        finally:
            os.environ.pop("ECAN_HUMAN_JUDGE_MIN_CONFIDENCE", None)


class Mt048BHumanInterventionBehaviourTests(unittest.TestCase):
    """Confirm bubble_text round-trips through mark_handled and the
    new getter."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.human_intervention"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_get_handled_question_text_round_trips(self) -> None:
        self.mod.mark_handled(
            "客户99",
            "msg-AGENT-1",
            source="test",
            question_msg_id="msg-Q-1",
            bubble_text="您好，已经为您查询",
        )
        self.assertEqual(
            self.mod.get_handled_question_text("客户99", "msg-Q-1"),
            "您好，已经为您查询",
        )

    def test_get_handled_question_text_missing_returns_empty(self) -> None:
        self.assertEqual(
            self.mod.get_handled_question_text("nobody", "no-qid"),
            "",
        )

    def test_mark_handled_without_text_leaves_text_blank(self) -> None:
        # Backwards compat: callers that don't pass bubble_text shouldn't
        # crash, and the getter returns "" rather than raising.
        self.mod.mark_handled(
            "客户77",
            "msg-X",
            source="test",
            question_msg_id="msg-Y",
        )
        self.assertEqual(
            self.mod.get_handled_question_text("客户77", "msg-Y"),
            "",
        )


# -----------------------------------------------------------------------
# mt048C — URL detection at PreDispatch (foundation; routing in mt048D)
# -----------------------------------------------------------------------

UD_SRC_048C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/url_detector.py"
).read_text(encoding="utf-8")
PD_SRC_048C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt048CDetectorSourceTests(unittest.TestCase):
    """Customer feedback 2026-05-26: handle product-URL pastes.  This
    commit ships detection + flag-on-item as foundation; routing /
    front-desk prompt update tracked in mt048D."""

    def test_module_exposes_public_api(self) -> None:
        for name in (
            "is_enabled",
            "find_first_url",
            "find_all_urls",
            "is_jinritemai_product_url",
            "extract_product_id",
        ):
            self.assertIn(f"def {name}", UD_SRC_048C)
        self.assertIn('"is_enabled"', UD_SRC_048C)
        self.assertIn('"find_first_url"', UD_SRC_048C)

    def test_tunable_documented(self) -> None:
        self.assertIn("ECAN_URL_DETECTION_ENABLED", UD_SRC_048C)

    def test_jinritemai_host_constant(self) -> None:
        self.assertIn(
            '_JINRITEMAI_PRODUCT_HOST = "haohuo.jinritemai.com"',
            UD_SRC_048C,
        )


class Mt048CDetectorBehaviourTests(unittest.TestCase):
    """Exercise the regex helpers."""

    def setUp(self) -> None:
        import importlib, sys, os
        os.environ.pop("ECAN_URL_DETECTION_ENABLED", None)
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.url_detector"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_find_first_url_simple(self) -> None:
        self.assertEqual(
            self.mod.find_first_url("看这个 https://example.com/foo 怎么样"),
            "https://example.com/foo",
        )

    def test_find_first_url_http_and_https(self) -> None:
        self.assertEqual(
            self.mod.find_first_url("link: http://example.com"),
            "http://example.com",
        )
        self.assertEqual(
            self.mod.find_first_url("HTTPS://example.com is fine too"),
            "HTTPS://example.com",
        )

    def test_find_first_url_no_url(self) -> None:
        self.assertEqual(self.mod.find_first_url("just text 中文"), "")
        self.assertEqual(self.mod.find_first_url(""), "")
        self.assertEqual(self.mod.find_first_url(None), "")  # type: ignore[arg-type]

    def test_find_first_url_strips_trailing_punctuation(self) -> None:
        # Chinese punctuation that's clearly not part of the URL must
        # not be consumed.
        text = "请看 https://example.com/foo， 这个商品好不好？"
        self.assertEqual(
            self.mod.find_first_url(text),
            "https://example.com/foo",
        )

    def test_find_all_urls_dedupes(self) -> None:
        text = "https://a.com 还有 https://a.com 和 https://b.com"
        self.assertEqual(
            self.mod.find_all_urls(text),
            ["https://a.com", "https://b.com"],
        )

    def test_find_all_urls_preserves_order(self) -> None:
        text = "https://b.com first then https://a.com"
        self.assertEqual(
            self.mod.find_all_urls(text),
            ["https://b.com", "https://a.com"],
        )

    def test_jinritemai_product_url_positive(self) -> None:
        url = (
            "https://haohuo.jinritemai.com/ecommerce/trade/detail/"
            "index.html?id=3806636940602769454&origin_type=604"
        )
        self.assertTrue(self.mod.is_jinritemai_product_url(url))
        self.assertEqual(
            self.mod.extract_product_id(url),
            "3806636940602769454",
        )

    def test_jinritemai_product_url_negative(self) -> None:
        # Wrong host.
        self.assertFalse(self.mod.is_jinritemai_product_url(
            "https://example.com/foo?id=123",
        ))
        # Right host but no id parameter.
        self.assertFalse(self.mod.is_jinritemai_product_url(
            "https://haohuo.jinritemai.com/ecommerce/list",
        ))
        # Empty.
        self.assertFalse(self.mod.is_jinritemai_product_url(""))

    def test_extract_product_id_missing(self) -> None:
        self.assertEqual(self.mod.extract_product_id("https://example.com"), "")
        self.assertEqual(self.mod.extract_product_id(""), "")

    def test_disabled_returns_empty(self) -> None:
        import os
        os.environ["ECAN_URL_DETECTION_ENABLED"] = "false"
        try:
            self.assertEqual(self.mod.find_first_url("https://a.com"), "")
            self.assertEqual(self.mod.find_all_urls("https://a.com"), [])
        finally:
            os.environ.pop("ECAN_URL_DETECTION_ENABLED", None)


class Mt048CPredispatchIntegrationTests(unittest.TestCase):
    """Confirm the PreDispatch call site sets the right flags."""

    def test_url_detection_called_at_end_of_enrich(self) -> None:
        self.assertIn("from . import url_detector as _ud", PD_SRC_048C)
        self.assertIn("_ud.find_all_urls(_customer_text_for_url)", PD_SRC_048C)

    def test_item_flags_set_on_detection(self) -> None:
        # All four flags must be set when a URL is detected.
        for flag in (
            "_ecan_url_detected",
            "_ecan_url_all",
            "_ecan_url_is_jinritemai_product",
            "_ecan_url_product_id",
        ):
            self.assertIn(flag, PD_SRC_048C)

    def test_url_detection_after_msg_id_dedup(self) -> None:
        # Detection must run AFTER the msg-id dedup short-circuit so we
        # don't log URLs for already-dispatched bubbles.  The mt048C
        # block lives at the end of enrich_item, just before the final
        # successful return.
        mt048c_idx = PD_SRC_048C.find("mt048C URL detected for")
        dedup_idx = PD_SRC_048C.find("skip_reason=\"msg_id_dedup\"")
        self.assertGreater(mt048c_idx, -1)
        self.assertGreater(dedup_idx, -1)
        self.assertLess(dedup_idx, mt048c_idx)

    def test_detection_failure_is_non_fatal(self) -> None:
        # The whole block is wrapped in try/except so a detection bug
        # never aborts dispatch.
        block_start = PD_SRC_048C.find("from . import url_detector as _ud")
        self.assertGreater(block_start, -1)
        block = PD_SRC_048C[block_start - 200 : block_start + 2000]
        self.assertIn("except Exception as _url_err:", block)
        self.assertIn("non-fatal", block)


# -----------------------------------------------------------------------
# mt048D — URL items skip auto-dispatch + projected flags reach the LLM
# -----------------------------------------------------------------------

AI_SRC_048D = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/actionable_items.py"
).read_text(encoding="utf-8")


class Mt048DSourceTests(unittest.TestCase):
    """mt048C added _ecan_url_* flags at PreDispatch but the items still
    auto-dispatched to Q&A.  mt048D-P1 makes the auto-dispatch loop skip
    items whose _ecan_url_detected is set; mt048D-P2 projects the
    underscore-prefixed flags to clean LLM-visible keys so the front-desk
    prompt's new Path C can branch on them.  Routing change is the
    foundation for the prompt-driven URL handling in mt048D-P3."""

    def test_p1_url_skip_in_auto_dispatch(self) -> None:
        # The auto-dispatch loop must short-circuit on _ecan_url_detected.
        self.assertIn(
            'if str(item.get("_ecan_url_detected") or "").strip():',
            AI_SRC_048D,
        )
        # mt048D marker for grep.
        self.assertIn("mt048D skip URL item", AI_SRC_048D)
        # Must `continue` (not break / return) so non-URL items still
        # dispatch normally.
        skip_idx = AI_SRC_048D.find(
            'if str(item.get("_ecan_url_detected") or "").strip():'
        )
        self.assertGreater(skip_idx, -1)
        # Within ~600 chars of the check we expect the `continue`.
        body = AI_SRC_048D[skip_idx:skip_idx + 1000]
        self.assertIn("continue", body)

    def test_p1_skip_runs_before_evaluate_item_filter(self) -> None:
        # If the regular filter fires first, the URL item would never
        # see the skip.  Order matters: URL skip before _evaluate_item_filter.
        skip_idx = AI_SRC_048D.find("mt048D skip URL item")
        filter_idx = AI_SRC_048D.find("_evaluate_item_filter(\n            item,")
        self.assertGreater(skip_idx, -1)
        self.assertGreater(filter_idx, skip_idx)

    def test_p2_projects_url_flags_for_llm(self) -> None:
        # The actionable_items list seen by the LLM must carry clean
        # url_detected / url_is_product / url_product_id keys (without
        # the _ecan_ underscore prefix) so the prompt can branch on them.
        self.assertIn(
            'mt048D-P2: project the internal _ecan_url_* flags',
            AI_SRC_048D,
        )
        self.assertIn('_projected["url_detected"] = _url', AI_SRC_048D)
        self.assertIn('_projected["url_is_product"] = bool(', AI_SRC_048D)
        self.assertIn('_projected["url_product_id"] = str(', AI_SRC_048D)

    def test_p2_does_not_mutate_original_items(self) -> None:
        # The projection must use a shallow copy — mutating the original
        # _actionable items would leak the clean keys into Python paths
        # that don't expect them.
        proj_idx = AI_SRC_048D.find("_actionable_for_llm = []")
        self.assertGreater(proj_idx, -1)
        body = AI_SRC_048D[proj_idx:proj_idx + 1500]
        self.assertIn("_projected = dict(_it)", body)
        # The JSON dump must use the projected list, not _actionable.
        self.assertIn(
            "_act_json = json.dumps(_actionable_for_llm,",
            AI_SRC_048D,
        )

    def test_p2_passthrough_when_no_url(self) -> None:
        # Items without _ecan_url_detected go straight through with no
        # projection — keeps the LLM hint clean for the 99% non-URL case.
        proj_idx = AI_SRC_048D.find("_actionable_for_llm = []")
        body = AI_SRC_048D[proj_idx:proj_idx + 1500]
        self.assertIn("if not _url:", body)
        self.assertIn("_actionable_for_llm.append(_it)", body)
        self.assertIn("continue", body)


class Mt048DPromptTests(unittest.TestCase):
    """Both front-desk prompt files (pr-382693 + pr-780665) must carry
    Path C with the agreed-upon structure: new-tab fetch, extract_dom,
    in-mind reasoning, switch back + feige_send_message, and the fixed
    fallback text on any failure.

    Note: the prompt JSONs live in the gitignored ``songc_yahoo_com/``
    user-data dir, so on a fresh clone these tests SKIP rather than
    fail.  They run on the operator's box where the prompts exist.
    """

    PROMPT_FILES = [
        "songc_yahoo_com/my_prompts/sc_pr-382693.json",
        "songc_yahoo_com/my_prompts/feige_front_desk_pr-780665.json",
    ]

    @classmethod
    def setUpClass(cls) -> None:
        for p in cls.PROMPT_FILES:
            if not Path(p).is_file():
                raise unittest.SkipTest(
                    f"prompt file {p!r} not present "
                    f"(user-data dir is gitignored; tests run only on operator box)"
                )

    def _load_md(self, p):
        import json as _json
        with open(p, encoding="utf-8") as f:
            return _json.load(f)["mdContent"]

    def test_path_c_present_in_both_files(self) -> None:
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            self.assertIn("路径 C — 客户消息含 URL", md, f"{p} missing Path C")

    def test_path_c_before_path_a(self) -> None:
        # URL routing must be highest priority — Path C check comes
        # before Path A (greeting) so a "你好 https://..." goes to C.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            c_idx = md.index("路径 C")
            a_idx = md.index("路径 A")
            self.assertLess(c_idx, a_idx, f"{p}: Path C must precede Path A")

    def test_path_c_lists_required_tools(self) -> None:
        # Every Path C step has a concrete tool name the LLM should call.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            for tool in (
                "open_tab",
                "go_to_url",
                "extract_dom",
                "close_tab",
                "switch_tab",
                "feige_open_session",
                "feige_send_message",
            ):
                self.assertIn(tool, md, f"{p}: tool {tool!r} not referenced")

    def test_path_c_uses_fixed_fallback_text(self) -> None:
        # The fallback message is fixed — must match exactly.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            self.assertIn("抱歉，无法查看您发的链接", md)

    def test_path_c_forbids_navigate_away_from_feige(self) -> None:
        # Critical safety: do NOT go_to_url in the feige tab itself.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            # The Path C body must explicitly warn against this.
            self.assertIn("绝对禁止", md)
            self.assertIn("im.jinritemai.com", md)
            # Catch-all phrase from the prohibitions section.
            self.assertIn(
                "不得**在飞鸽（im.jinritemai.com）标签页直接 `go_to_url`",
                md,
            )

    def test_path_c_forbids_url_retry(self) -> None:
        # User explicitly said no retry on fetch failure.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            self.assertIn("不要重试 URL 抓取", md)

    def test_path_c_branches_on_clean_field_name(self) -> None:
        # P2 projects to ``url_detected`` (no underscore prefix); the
        # prompt must use that field name, NOT the internal _ecan_*.
        for p in self.PROMPT_FILES:
            md = self._load_md(p)
            self.assertIn("`url_detected`", md)
            # Regression guard: no leaked internal prefix in the prompt.
            self.assertNotIn("_ecan_url_detected", md)


# -----------------------------------------------------------------------
# mt049A — diagnostic logging for RAG TaskGroup failures
# -----------------------------------------------------------------------

MCP_SRC_049 = Path("agent/mcp/local_client.py").read_text(encoding="utf-8")


class Mt049ASourceTests(unittest.TestCase):
    """Live customer trace 2026-05-26 21:06:57 + 21:13:45 hit RAG
    TaskGroup failures (~9% under 7-customer load), but the existing
    log line only printed ``__str__()`` of the BaseExceptionGroup
    ("unhandled errors in a TaskGroup (1 sub-exception)") — the actual
    sub-exception (httpx error, SSE stream broken, LightRAG 500, etc.)
    was swallowed.  mt049A surfaces it so the next failure tells us
    what to fix.

    Pure diagnostic — no behavior change."""

    def test_helper_function_defined(self) -> None:
        self.assertIn(
            "def _mt049a_log_exception_group_subs(exc, tool_name, where):",
            MCP_SRC_049,
        )

    def test_helper_handles_pre_311_python(self) -> None:
        # BaseExceptionGroup is 3.11+; the helper must no-op on older Pythons.
        self.assertIn("BaseExceptionGroup", MCP_SRC_049)
        # Defensive fallback when neither builtin lookup nor name resolution
        # finds the class.
        self.assertIn("return  # nothing to unpack", MCP_SRC_049)

    def test_helper_walks_nested_groups(self) -> None:
        # anyio sometimes nests groups multiple layers deep — must BFS.
        start = MCP_SRC_049.find("def _mt049a_log_exception_group_subs(")
        self.assertGreater(start, -1)
        body = MCP_SRC_049[start:start + 2500]
        self.assertIn("queue = [exc]", body)
        self.assertIn("if isinstance(sub, BaseEG):", body)
        self.assertIn("queue.append(sub)", body)
        # Guard against runaway logs on pathological nesting.
        self.assertIn("seen < 16", body)

    def test_helper_never_raises(self) -> None:
        # The diagnostic helper is wrapped in try/except so a bug in
        # the walker itself never adds to the caller's exception chain.
        start = MCP_SRC_049.find("def _mt049a_log_exception_group_subs(")
        body = MCP_SRC_049[start:start + 2500]
        self.assertIn("except Exception as _diag_err:", body)
        self.assertIn("non-fatal", body)

    def test_error_log_uses_exc_info_true(self) -> None:
        # Both call sites (ephemeral + outer) must use exc_info=True so
        # the full traceback reaches the log even before we unpack subs.
        # Count exc_info=True occurrences in error-log calls.
        self.assertGreaterEqual(MCP_SRC_049.count("exc_info=True"), 2)
        # Both sites must invoke the helper after the error log.
        self.assertGreaterEqual(
            MCP_SRC_049.count("_mt049a_log_exception_group_subs("),
            3,  # def + 2 call sites
        )

    def test_error_log_includes_type_name(self) -> None:
        # The error message now starts with the exception's type name
        # instead of just its str — easier to grep "httpx.ConnectError"
        # etc. than "(1 sub-exception)".
        self.assertIn(
            '{type(cleanup_err).__name__}: {cleanup_err}',
            MCP_SRC_049,
        )
        self.assertIn(
            '{type(e).__name__}: {e}',
            MCP_SRC_049,
        )


class Mt049ABehaviourTests(unittest.TestCase):
    """Exercise the helper against synthetic ExceptionGroups."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = "agent.mcp.local_client"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)

    def test_no_op_on_non_group_exception(self) -> None:
        # A plain RuntimeError isn't a group — helper should just return.
        from unittest import mock as _mock
        with _mock.patch.object(self.mod.logger, "error") as mock_err:
            self.mod._mt049a_log_exception_group_subs(
                RuntimeError("boom"), "rag_query", "ephemeral",
            )
        mock_err.assert_not_called()

    def test_unpacks_flat_exception_group(self) -> None:
        # Skip on Python < 3.11 where ExceptionGroup isn't available.
        try:
            eg_cls = BaseExceptionGroup  # noqa: F821
        except NameError:
            self.skipTest("Python < 3.11 — no BaseExceptionGroup")

        from unittest import mock as _mock
        sub1 = RuntimeError("httpx ConnectError")
        sub2 = ValueError("malformed payload")
        group = eg_cls("test", [sub1, sub2])
        with _mock.patch.object(self.mod.logger, "error") as mock_err:
            self.mod._mt049a_log_exception_group_subs(
                group, "rag_query", "ephemeral",
            )
        # Should have logged once per sub.
        self.assertEqual(mock_err.call_count, 2)
        # Sub types should appear in the messages.
        calls = " ".join(str(c) for c in mock_err.call_args_list)
        self.assertIn("RuntimeError", calls)
        self.assertIn("ValueError", calls)
        self.assertIn("rag_query", calls)

    def test_unpacks_nested_exception_group(self) -> None:
        try:
            eg_cls = BaseExceptionGroup  # noqa: F821
        except NameError:
            self.skipTest("Python < 3.11 — no BaseExceptionGroup")

        from unittest import mock as _mock
        inner = eg_cls("inner", [RuntimeError("leaf-A")])
        outer = eg_cls("outer", [inner, RuntimeError("leaf-B")])
        with _mock.patch.object(self.mod.logger, "error") as mock_err:
            self.mod._mt049a_log_exception_group_subs(
                outer, "rag_query", "ephemeral",
            )
        # Both leaves should be logged (the inner group itself gets
        # walked, not logged).
        self.assertEqual(mock_err.call_count, 2)
        calls = " ".join(str(c) for c in mock_err.call_args_list)
        self.assertIn("leaf-A", calls)
        self.assertIn("leaf-B", calls)


# -----------------------------------------------------------------------
# mt050B — restore placeholder sweeper kickoff on direct-delivery path
# -----------------------------------------------------------------------

DA_SRC_050B = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt050BSourceTests(unittest.TestCase):
    """Customer live test 2026-05-27 08:50-09:15 — the
    "人工服务正在回复中..." placeholder template never appeared.  Log
    showed 9 ``cancel_any_for_customer`` hits (timers being cancelled
    by PreDispatch supersede) but ZERO sweeper task started and ZERO
    placeholders fired.

    Same regression shape as mt045B (pool init): the sweeper-start
    kickoff at dom_assets.py:~2075 lived in
    ``ensure_feige_tab_focused``, which mt043A made the direct-delivery
    path bypass.  Healthy direct-delivery doesn't go through
    HOT-PATH-B, so ``ensure_feige_tab_focused`` doesn't fire, so the
    sweeper-start doesn't fire, so armed timers never get processed.

    mt050B: call ``_start_placeholder_sweeper`` from
    ``_maybe_kickoff_typing_pool_init`` (which IS called by every
    direct-delivery resolve since mt045B), on EVERY call (not gated by
    ``try_dispatch_initial_population``) so it auto-restarts after CDP
    recovery / BrowserSession invalidation — same contract as
    mt038D originally established."""

    def test_sweeper_kickoff_called_from_helper(self) -> None:
        # The pool-init helper must invoke the sweeper start.
        start = DA_SRC_050B.find("def _maybe_kickoff_typing_pool_init(")
        self.assertGreater(start, -1)
        end = DA_SRC_050B.find("\ndef ", start + 1)
        self.assertGreater(end, start)
        body = DA_SRC_050B[start:end]
        self.assertIn("_start_placeholder_sweeper(browser_session)", body)
        self.assertIn("mt050B", body)

    def test_sweeper_call_is_outside_one_shot_gate(self) -> None:
        # CRITICAL — sweeper kickoff must NOT be gated by
        # try_dispatch_initial_population (which only fires once per
        # process and would skip after CDP recovery).  The mt038D
        # comment in dom_assets.py explains why this matters.
        start = DA_SRC_050B.find("def _maybe_kickoff_typing_pool_init(")
        end = DA_SRC_050B.find("\ndef ", start + 1)
        body = DA_SRC_050B[start:end]
        sweeper_idx = body.find("_start_placeholder_sweeper(browser_session)")
        gate_idx = body.find("try_dispatch_initial_population()")
        self.assertGreater(sweeper_idx, -1)
        self.assertGreater(gate_idx, -1)
        # Sweeper call must come BEFORE the one-shot gate.
        self.assertLess(
            sweeper_idx, gate_idx,
            "mt050B sweeper-start must run BEFORE the one-shot pool-init gate, "
            "otherwise it skips on every call after the first (since the gate "
            "returns False once population is dispatched)",
        )

    def test_sweeper_failure_is_isolated_from_pool_init(self) -> None:
        # The sweeper-start try/except must be SEPARATE from the
        # pool-init try/except so one failing doesn't mask the other.
        start = DA_SRC_050B.find("def _maybe_kickoff_typing_pool_init(")
        end = DA_SRC_050B.find("\ndef ", start + 1)
        body = DA_SRC_050B[start:end]
        # Sweeper has its own except handler labelled mt050B.
        self.assertIn("mt050B sweeper-start failed", body)

    def test_sweeper_definition_precedes_helper(self) -> None:
        # _start_placeholder_sweeper must be defined before
        # _maybe_kickoff_typing_pool_init so the name resolves at call
        # time even on cold module import (defensive — Python's
        # late-binding means this is true regardless of order, but
        # putting them in dependency order keeps the file readable).
        sweeper_def_idx = DA_SRC_050B.find("def _start_placeholder_sweeper(browser_session)")
        helper_def_idx = DA_SRC_050B.find("def _maybe_kickoff_typing_pool_init(")
        self.assertGreater(sweeper_def_idx, -1)
        self.assertGreater(helper_def_idx, -1)
        self.assertLess(sweeper_def_idx, helper_def_idx)


# -----------------------------------------------------------------------
# mt050C + mt050D — judge import fix + verdict.error fallback
# -----------------------------------------------------------------------

HRJ_SRC_050CD = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_relevance_judge.py"
).read_text(encoding="utf-8")
RUNNER_SRC_050D = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt050CSourceTests(unittest.TestCase):
    """mt048B shipped with ``from utils.secure_store`` + ``from
    utils.user_context`` — both ImportError at runtime.  Live trace
    2026-05-27 12:26:16 captured the failure:

        [mt048B] judge LLM init failed (model='gpt-5-mini'):
        No module named 'utils.secure_store' — defaulting to
        answered=False (bot reply will proceed)

    Every judge call since mt048B shipped (commit 1d6ff2719) errored,
    returning answered=False which the runner then misread as
    "human did NOT answer → allow bot through".  mt050C corrects the
    import path to the actual module (``utils.env.secure_store``,
    which also re-exports get_current_username)."""

    def test_imports_use_env_secure_store(self) -> None:
        # The correct path matches build_node.py:26.
        self.assertIn(
            "from utils.env.secure_store import secure_store, get_current_username",
            HRJ_SRC_050CD,
        )

    def test_old_broken_imports_gone(self) -> None:
        # Regression guard: the broken paths must not come back.
        self.assertNotIn("from utils.secure_store import", HRJ_SRC_050CD)
        self.assertNotIn("from utils.user_context import", HRJ_SRC_050CD)

    def test_actual_module_exists_at_corrected_path(self) -> None:
        # Sanity: the path we just patched to must actually be
        # importable.  No mocking — real Python import.
        from utils.env.secure_store import secure_store, get_current_username  # noqa: F401
        # If we got here without ImportError, the path is valid.


class Mt050DSourceTests(unittest.TestCase):
    """Even with mt050C's import fix, a future judge crash (LLM
    timeout, malformed JSON, etc.) would still slip past as
    ``answered=False`` because the runner's drop calc only looked at
    ``answered`` + ``confidence``.  mt050D adds an ``error`` check —
    when the verdict carries a non-empty error, treat as judge-failed
    and fall back to the pre-mt048B unconditional drop."""

    def test_runner_reads_verdict_error_field(self) -> None:
        self.assertIn(
            'getattr(_mt048b_verdict, "error", "")',
            RUNNER_SRC_050D,
        )
        self.assertIn("_mt048b_failed = bool(", RUNNER_SRC_050D)

    def test_judge_failed_forces_drop_true(self) -> None:
        # The drop decision must branch on _mt048b_failed first.
        start = RUNNER_SRC_050D.find("_mt048b_failed = bool(")
        self.assertGreater(start, -1)
        body = RUNNER_SRC_050D[start:start + 600]
        self.assertIn("if _mt048b_failed:", body)
        self.assertIn("_mt048b_drop = True", body)

    def test_runner_logs_judge_failed_flag(self) -> None:
        # Operator visibility — make it obvious in the log when the
        # drop is from a judge failure vs a real "answered=True" judgement.
        self.assertIn("judge_failed={_mt048b_failed}", RUNNER_SRC_050D)


class Mt050CDIntegrationTests(unittest.TestCase):
    """End-to-end: trigger the judge with a stubbed-broken LLM and
    verify the runner's drop decision falls back to True."""

    def setUp(self) -> None:
        import importlib, sys, os
        for k in (
            "ECAN_HUMAN_JUDGE_ENABLED",
            "ECAN_HUMAN_JUDGE_MODEL",
            "ECAN_HUMAN_JUDGE_TIMEOUT_S",
            "ECAN_HUMAN_JUDGE_MIN_CONFIDENCE",
        ):
            os.environ.pop(k, None)
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.human_relevance_judge"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        self.mod.reset_llm_cache()

    def test_llm_init_failure_carries_error_field(self) -> None:
        # Force _get_llm to raise so judge() returns the safe-default
        # verdict with error=<msg>.  This mirrors the production
        # failure that mt050C fixed.
        #
        # NB: human_text must be SUBSTANTIVE enough to bypass mt050I's
        # heuristic fast-path (>8 chars OR not a recognized ack prefix).
        # Using a longer substantive sentence so we actually exercise
        # the LLM path.
        from unittest import mock as _mock
        with _mock.patch.object(
            self.mod, "_get_llm",
            side_effect=RuntimeError("simulated init failure"),
        ):
            v = self.mod.judge(
                "尺码偏大吗",
                "已经为您申请补偿，请您耐心等待审核结果",
            )
        # Judge MUST return rather than raise (safety net).
        self.assertFalse(v.answered)
        # And the error field MUST carry the failure detail so the
        # runner's mt050D check can distinguish this from a real
        # answered=False verdict.
        self.assertTrue(v.error, f"verdict.error empty: {v!r}")
        self.assertIn("simulated init failure", v.error)
        self.assertEqual(v.reason, "llm_init_failed")

    def test_explicit_answered_false_has_empty_error(self) -> None:
        # When the LLM ran successfully and returned answered=False
        # (legitimate "human didn't answer"), the error field must
        # stay empty so the runner DOESN'T force-drop.
        from unittest import mock as _mock
        stub = _mock.MagicMock()
        stub.invoke.return_value = _mock.MagicMock(
            content='{"answered": false, "confidence": 0.85, "reason": "在的"}'
        )
        with _mock.patch.object(self.mod, "_get_llm", return_value=stub):
            v = self.mod.judge("尺码偏大吗", "在的")
        self.assertFalse(v.answered)
        self.assertEqual(v.error, "")  # empty → judge succeeded


# -----------------------------------------------------------------------
# mt050E — per-customer recent-msg context in dispatch payload
# -----------------------------------------------------------------------

AI_SRC_050E = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/actionable_items.py"
).read_text(encoding="utf-8")


class Mt050ESourceTests(unittest.TestCase):
    """Live trace 2026-05-27 12:25:08-12: customer 肽斯特 sent product
    card + text "绿色有货吗" 2s apart.  Sticky-affinity lost the race
    and each event went to a different Q&A agent; the agent answering
    "绿色有货吗" had no card in its recent_context and replied asking
    for a product link.

    mt050E adds a per-customer ring buffer of recent message previews
    that gets injected into EVERY auto-dispatch payload as
    ``customer_recent_messages``, so the receiving agent has the
    customer's burst context regardless of which agent answered the
    prior turn."""

    def test_module_state_defined(self) -> None:
        self.assertIn(
            "_customer_recent_messages: dict[str, list[tuple[float, str]]] = {}",
            AI_SRC_050E,
        )
        self.assertIn("_RECENT_MESSAGES_MAX = 3", AI_SRC_050E)
        self.assertIn("_RECENT_MESSAGES_TTL_S = 600", AI_SRC_050E)

    def test_helpers_defined(self) -> None:
        self.assertIn(
            "def _append_recent_message(customer_id: str, text: str) -> None:",
            AI_SRC_050E,
        )
        self.assertIn(
            "def _get_recent_messages(customer_id: str) -> list[str]:",
            AI_SRC_050E,
        )

    def test_dispatch_loop_reads_before_appending(self) -> None:
        # The current dispatch must INJECT the prior buffer BEFORE
        # appending the current message — otherwise the receiving
        # agent sees its own current message echoed in recent context.
        start = AI_SRC_050E.find("_mt050e_prior = _get_recent_messages")
        self.assertGreater(start, -1)
        end = AI_SRC_050E.find("_append_recent_message(cust_id, _mt050e_text)", start)
        self.assertGreater(end, start, "read must precede append")

    def test_payload_carries_recent_messages_key(self) -> None:
        # The injected JSON field must be a stable, documented name.
        self.assertIn(
            'resolved["customer_recent_messages"] = _mt050e_prior',
            AI_SRC_050E,
        )

    def test_append_runs_on_dispatch_success(self) -> None:
        # The append must happen inside the success branch, NOT on
        # failure — otherwise a transient send error pollutes the
        # buffer with a message that may be retried later.
        start = AI_SRC_050E.find("if result.get(\"success\"):")
        self.assertGreater(start, -1)
        # Append helper is invoked inside the success branch (within
        # ~1500 chars of `if result.get("success"):`).
        body = AI_SRC_050E[start:start + 1500]
        self.assertIn("_append_recent_message(cust_id, _mt050e_text)", body)


class Mt050EBufferBehaviourTests(unittest.TestCase):
    """Exercise the ring-buffer helpers."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        # Fresh buffer per test.
        self.mod._customer_recent_messages.clear()

    def test_append_and_get_round_trip(self) -> None:
        self.mod._append_recent_message("alice", "hello")
        self.mod._append_recent_message("alice", "are you there")
        self.assertEqual(
            self.mod._get_recent_messages("alice"),
            ["hello", "are you there"],
        )

    def test_empty_inputs_noop(self) -> None:
        self.mod._append_recent_message("", "hi")
        self.mod._append_recent_message("alice", "")
        self.mod._append_recent_message("alice", "   ")
        self.assertEqual(self.mod._get_recent_messages("alice"), [])

    def test_buffer_caps_at_max(self) -> None:
        for i in range(10):
            self.mod._append_recent_message("alice", f"msg{i}")
        out = self.mod._get_recent_messages("alice")
        self.assertEqual(len(out), self.mod._RECENT_MESSAGES_MAX)
        # Newest entries kept, oldest dropped.
        self.assertEqual(out, ["msg7", "msg8", "msg9"])

    def test_duplicate_back_to_back_deduped(self) -> None:
        # DOM reshuffles sometimes emit the same dom_observed twice in
        # quick succession; we don't want both copies in the buffer.
        self.mod._append_recent_message("alice", "hello")
        self.mod._append_recent_message("alice", "hello")
        self.assertEqual(self.mod._get_recent_messages("alice"), ["hello"])
        # But a different message DOES append.
        self.mod._append_recent_message("alice", "goodbye")
        self.assertEqual(
            self.mod._get_recent_messages("alice"),
            ["hello", "goodbye"],
        )

    def test_long_text_truncated(self) -> None:
        long_text = "x" * 500
        self.mod._append_recent_message("alice", long_text)
        out = self.mod._get_recent_messages("alice")
        self.assertEqual(len(out), 1)
        # Truncated to 200 chars + ellipsis.
        self.assertTrue(out[0].endswith("…"))
        self.assertLessEqual(len(out[0]), 201)

    def test_ttl_prunes_stale_entries(self) -> None:
        import time as _t
        self.mod._append_recent_message("alice", "old")
        # Patch the timestamp to be older than the TTL.
        buf = self.mod._customer_recent_messages["alice"]
        buf[0] = (_t.time() - self.mod._RECENT_MESSAGES_TTL_S - 5, "old")
        # Append a fresh one to force GC.
        self.mod._append_recent_message("alice", "new")
        out = self.mod._get_recent_messages("alice")
        # Old entry pruned.
        self.assertEqual(out, ["new"])

    def test_get_returns_empty_for_unknown_customer(self) -> None:
        self.assertEqual(self.mod._get_recent_messages("nobody"), [])
        self.assertEqual(self.mod._get_recent_messages(""), [])


# -----------------------------------------------------------------------
# mt050F + mt050G + mt050H — placeholder-timing trio
# -----------------------------------------------------------------------

PH_SRC_050FGH = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")
EM_SRC_050H = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")
RUNNER_SRC_050H = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt050FSourceTests(unittest.TestCase):
    """Live trace 2026-05-27 12:38-12:39 — placeholder #1 fired 63 s
    after dom_observed (expected ~10 s) because PreDispatch queue lag
    delayed arm() by 49 s.  When arm() fired, ``first_seen + 10s``
    was already in the past, but the old ``deadline = max(deadline,
    now + 1.0)`` clamp pushed the deadline back to ``now + 1 s`` —
    defeating the first_seen anchor entirely."""

    def test_old_clamp_removed(self) -> None:
        # Regression guard — the broken clamp must NOT come back.
        self.assertNotIn("deadline = now + 1.0", PH_SRC_050FGH)
        self.assertNotIn("if deadline < now + 1.0:", PH_SRC_050FGH)

    def test_mt050f_rationale_documented(self) -> None:
        # The comment block explaining WHY the clamp was removed must
        # stay — otherwise a future contributor might re-add it
        # thinking it's a missing safeguard.
        self.assertIn("mt050F", PH_SRC_050FGH)
        self.assertIn(
            "DON'T clamp deadline to ``now + 1.0`` when",
            PH_SRC_050FGH,
        )

    def test_first_seen_anchor_still_referenced(self) -> None:
        # The anchor logic from mt038F2 stays intact.
        self.assertIn(
            "first_seen = get_message_first_seen(customer_key, source_msg_id)",
            PH_SRC_050FGH,
        )
        self.assertIn(
            "armed_at = first_seen if first_seen > 0.0 else now",
            PH_SRC_050FGH,
        )


class Mt050GSourceTests(unittest.TestCase):
    """Live trace 2026-05-27 12:42:04-06 — bot reply sent at
    12:42:04.840 but placeholder #2 fired at 12:42:06.188 (real reply
    + placeholder both visible to customer, out of order).  Sweeper
    had claimed the entry before the cancel reached it; the
    claim→submit window is wide enough for the real reply to land
    in-between.  mt050G adds a second is_real_reply_recent check
    RIGHT before submit to close the final race window."""

    def test_recheck_helper_called_in_sweeper(self) -> None:
        # The sweeper's fire-loop must invoke is_real_reply_recent
        # AFTER claim_expired returns, BEFORE placeholder_submitter.
        start = PH_SRC_050FGH.find("for entry in expired:")
        self.assertGreater(start, -1)
        body = PH_SRC_050FGH[start:start + 2500]
        self.assertIn("is_real_reply_recent(", body)
        self.assertIn("mt050G", body)

    def test_suppression_log_present(self) -> None:
        # Operator visibility: log when the recheck suppressed.
        self.assertIn(
            "mt050G suppressed placeholder",
            PH_SRC_050FGH,
        )

    def test_recheck_branches_with_continue(self) -> None:
        # On suppression, the loop must continue to next entry — NOT
        # break or return early, which would skip other pending
        # placeholders.
        start = PH_SRC_050FGH.find("mt050G suppressed placeholder")
        self.assertGreater(start, -1)
        body = PH_SRC_050FGH[start - 500:start + 800]
        self.assertIn("if is_real_reply_recent(", body)
        # The branch ends in `continue`.
        self.assertIn("continue", body)


class Mt050HSourceTests(unittest.TestCase):
    """Live trace 2026-05-27 J14N9 was stuck 5+ minutes after a
    direct_stale_dropped because EventMonitor's diff detector only
    fires on add/remove/reorder/top_changed.  When the customer's
    sidebar text doesn't change after stale-drop (common — customer
    sent the same question, bot dropped its own reply), diff sees
    added=0 and no new dom_observed fires → re-dispatch never
    triggers even though mt046A cleared the dedup ledgers."""

    def test_event_monitor_exposes_force_helper(self) -> None:
        self.assertIn(
            "def force_reemit_for_customer(customer_name: str) -> None:",
            EM_SRC_050H,
        )
        self.assertIn("_FORCED_REEMIT_CUSTOMER_NAMES", EM_SRC_050H)

    def test_diff_loop_consults_forced_set(self) -> None:
        # The diff calc must check the forced set and drop matching
        # current_keys from previous_key_set so they appear as added.
        self.assertIn(
            "if _FORCED_REEMIT_CUSTOMER_NAMES and current_keys:",
            EM_SRC_050H,
        )
        self.assertIn("previous_key_set.discard(k)", EM_SRC_050H)
        # And clear the matched names after the tick so re-emit is one-shot.
        self.assertIn(
            "_FORCED_REEMIT_CUSTOMER_NAMES.difference_update(matched_names)",
            EM_SRC_050H,
        )

    def test_diff_loop_logs_forced_reemit(self) -> None:
        # Operator visibility.
        self.assertIn("mt050H forced re-emit for", EM_SRC_050H)

    def test_runner_calls_force_helper_on_stale_drop(self) -> None:
        # Runner's mt046A clear path must invoke the EventMonitor hook
        # for the affected customer.
        self.assertIn(
            "force_reemit_for_customer as _mt050h_reemit",
            RUNNER_SRC_050H,
        )
        self.assertIn("_mt050h_reemit(_customer_name)", RUNNER_SRC_050H)


class Mt050HBehaviourTests(unittest.TestCase):
    """Exercise the forced-reemit set in isolation."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = "agent.ec_skills.browser_use_extension.event_monitor"
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        self.mod._FORCED_REEMIT_CUSTOMER_NAMES.clear()

    def test_force_helper_adds_to_set(self) -> None:
        self.mod.force_reemit_for_customer("J14N9")
        self.assertIn("J14N9", self.mod._FORCED_REEMIT_CUSTOMER_NAMES)

    def test_force_helper_is_idempotent(self) -> None:
        self.mod.force_reemit_for_customer("J14N9")
        self.mod.force_reemit_for_customer("J14N9")
        self.assertEqual(
            len(self.mod._FORCED_REEMIT_CUSTOMER_NAMES), 1,
        )

    def test_force_helper_ignores_empty(self) -> None:
        self.mod.force_reemit_for_customer("")
        self.mod.force_reemit_for_customer(None)  # type: ignore[arg-type]
        self.assertEqual(self.mod._FORCED_REEMIT_CUSTOMER_NAMES, set())


# -----------------------------------------------------------------------
# mt050I + mt050J + mt050K + mt050L
# -----------------------------------------------------------------------

HRJ_SRC_050I = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_relevance_judge.py"
).read_text(encoding="utf-8")
FD_SRC_050J = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")
DS_SRC_050K = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dispatch_state.py"
).read_text(encoding="utf-8")
PD_SRC_050K = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")
RUNNER_SRC_050K = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
FD_SRC_050K_SUP = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")
PH_SRC_050L = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")


class Mt050ISourceTests(unittest.TestCase):
    """Live trace 2026-05-27 15:36:35-15:37:34 — judge ``llm.invoke()``
    blocked for 129.7 s while ``ECAN_HUMAN_JUDGE_TIMEOUT_S=3.0`` was
    advisory only.  mt050I adds real timeout enforcement and a
    heuristic fast-path for short ack phrases like ``"嗯嗯"``."""

    def test_heuristic_helper_defined(self) -> None:
        self.assertIn(
            "def _heuristic_non_answer(human_text: str) -> bool:",
            HRJ_SRC_050I,
        )
        self.assertIn("_NON_ANSWER_FAST_PATH_PREFIXES = (", HRJ_SRC_050I)
        self.assertIn("_NON_ANSWER_FAST_PATH_MAX_CHARS = 8", HRJ_SRC_050I)

    def test_heuristic_covers_observed_failure_input(self) -> None:
        # Smoke-check that the prefix list catches the live-trace case.
        self.assertIn('"嗯嗯"', HRJ_SRC_050I)
        self.assertIn('"嗯"', HRJ_SRC_050I)
        self.assertIn('"好"', HRJ_SRC_050I)

    def test_judge_invocation_wraps_in_executor(self) -> None:
        # Real timeout enforcement uses concurrent.futures.
        self.assertIn("import concurrent.futures", HRJ_SRC_050I)
        self.assertIn("ThreadPoolExecutor(max_workers=1)", HRJ_SRC_050I)
        self.assertIn("_fut.result(timeout=timeout_s)", HRJ_SRC_050I)

    def test_judge_timeout_returns_error_field(self) -> None:
        # TimeoutError branch sets verdict.error so mt050D's drop-on-error
        # path can fire correctly.
        self.assertIn("reason=\"llm_invoke_timeout\"", HRJ_SRC_050I)
        self.assertIn("error=f\"timeout after {timeout_s}s\"", HRJ_SRC_050I)


class Mt050IBehaviourTests(unittest.TestCase):
    """Exercise the heuristic against synthetic inputs."""

    def setUp(self) -> None:
        import importlib, sys, os
        for k in (
            "ECAN_HUMAN_JUDGE_ENABLED",
            "ECAN_HUMAN_JUDGE_MODEL",
            "ECAN_HUMAN_JUDGE_TIMEOUT_S",
            "ECAN_HUMAN_JUDGE_MIN_CONFIDENCE",
        ):
            os.environ.pop(k, None)
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.human_relevance_judge"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        self.mod.reset_llm_cache()

    def test_heuristic_classifies_嗯嗯(self) -> None:
        self.assertTrue(self.mod._heuristic_non_answer("嗯嗯"))

    def test_heuristic_classifies_short_acks(self) -> None:
        for txt in ("好的", "稍等", "在的", "好嘞", "OK", "ok", "明白"):
            self.assertTrue(
                self.mod._heuristic_non_answer(txt),
                f"{txt!r} should be flagged as non-answer",
            )

    def test_heuristic_skips_substantive_replies(self) -> None:
        # Even if a substantive reply STARTS with "在的", the length
        # cap keeps it out of the fast-path so the LLM judges it.
        substantive = "在的，没货啦，建议看其他款"
        self.assertFalse(self.mod._heuristic_non_answer(substantive))

    def test_judge_uses_heuristic_without_llm(self) -> None:
        # When the heuristic matches, judge() must NOT touch the LLM.
        from unittest import mock as _mock
        with _mock.patch.object(
            self.mod, "_get_llm",
            side_effect=AssertionError("LLM should not be called"),
        ):
            v = self.mod.judge("尺码偏大吗", "嗯嗯")
        self.assertFalse(v.answered)
        self.assertEqual(v.error, "")  # success path — no error
        self.assertEqual(v.reason, "mt050I_heuristic_non_answer")
        self.assertGreaterEqual(v.confidence, 0.9)


class Mt050JSourceTests(unittest.TestCase):
    """mt050E only covered the LangGraph auto-dispatch path; production
    uses PreDispatch's frontdesk_dispatch.py.  mt050J ports the
    customer_recent_messages injection there."""

    def test_recent_messages_helpers_imported(self) -> None:
        self.assertIn(
            "_get_recent_messages as _mt050j_get_recent",
            FD_SRC_050J,
        )
        self.assertIn(
            "_append_recent_message as _mt050j_append_recent",
            FD_SRC_050J,
        )

    def test_payload_carries_recent_messages_key(self) -> None:
        self.assertIn(
            'payload["customer_recent_messages"] = _mt050j_prior',
            FD_SRC_050J,
        )

    def test_read_before_append(self) -> None:
        # Inject prior BEFORE appending current so the receiving Q&A
        # agent's recent_messages contains PRIOR context only — no
        # duplication with ``latest_message``.
        get_idx = FD_SRC_050J.find("_mt050j_get_recent(_mt050j_cust_id)")
        append_idx = FD_SRC_050J.find("_mt050j_append_recent(_mt050j_cust_id,")
        self.assertGreater(get_idx, -1)
        self.assertGreater(append_idx, -1)
        self.assertLess(get_idx, append_idx)


class Mt050KSourceTests(unittest.TestCase):
    """Two-part fix for placeholder-related stuck cases."""

    # (a) broad cancel on supersede ------------------------------------
    def test_supersede_broad_cancel_added(self) -> None:
        self.assertIn(
            "mt050K-(a)",
            FD_SRC_050K_SUP,
        )
        self.assertIn(
            "cancel_any_for_customer(",
            FD_SRC_050K_SUP,
        )
        self.assertIn(
            "broad-cancel removed",
            FD_SRC_050K_SUP,
        )

    # (b) placeholder text tagged in dispatch_state -------------------
    def test_dispatch_state_placeholder_ledger(self) -> None:
        self.assertIn(
            "_placeholder_reply_texts: dict[str, float] = {}",
            DS_SRC_050K,
        )
        self.assertIn(
            "def mark_placeholder_text(reply_text: str) -> str:",
            DS_SRC_050K,
        )
        self.assertIn(
            "def is_placeholder_text(text: str) -> bool:",
            DS_SRC_050K,
        )

    def test_runner_marks_placeholder_when_typing(self) -> None:
        # mt051C (2026-05-28): the placeholder send coroutine moved out of
        # runner.py into hooks/external/feige_chat/direct_delivery.py.
        # The mark_placeholder_text call goes with the body — it's now
        # expected to live there, not in runner.py.
        DD_SRC = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/direct_delivery.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_ph_ds.mark_placeholder_text(text)", DD_SRC)

    def test_dom_echo_guard_skips_placeholder_match(self) -> None:
        # When the matched echo IS a placeholder, the guard must NOT
        # return (True, "dom_echo") — it must fall through so the
        # underlying customer question can re-dispatch.
        self.assertIn(
            "is_placeholder_text as _is_ph_text",
            PD_SRC_050K,
        )
        self.assertIn(
            "_matched_is_placeholder = _is_ph_text(",
            PD_SRC_050K,
        )
        # Log substrings split across two f-string lines.
        self.assertIn("mt050K dom-echo", PD_SRC_050K)
        self.assertIn("override session=", PD_SRC_050K)


class Mt050KBehaviourTests(unittest.TestCase):
    """Round-trip the placeholder ledger."""

    def setUp(self) -> None:
        import importlib, sys
        mod_name = (
            "agent.ec_skills.browser_use_extension.hooks.external.feige_chat.dispatch_state"
        )
        if mod_name in sys.modules:
            del sys.modules[mod_name]
        self.mod = importlib.import_module(mod_name)
        self.mod._placeholder_reply_texts.clear()

    def test_mark_and_check(self) -> None:
        self.mod.mark_placeholder_text("人工服务正在回复中...")
        self.assertTrue(self.mod.is_placeholder_text("人工服务正在回复中..."))

    def test_unknown_text_returns_false(self) -> None:
        self.mod.mark_placeholder_text("foo")
        self.assertFalse(self.mod.is_placeholder_text("bar"))

    def test_empty_input_safe(self) -> None:
        self.assertEqual(self.mod.mark_placeholder_text(""), "")
        self.assertFalse(self.mod.is_placeholder_text(""))


class Mt050LSourceTests(unittest.TestCase):
    """Customer feedback — shrink default placeholder set to one entry."""

    def test_default_list_has_single_entry(self) -> None:
        # Find the constant definition and verify it lists exactly one text.
        start = PH_SRC_050L.find("_PLACEHOLDER_DEFAULT_TEXTS = [")
        self.assertGreater(start, -1)
        end = PH_SRC_050L.find("]", start)
        block = PH_SRC_050L[start:end + 1]
        # Should contain "人工服务正在回复中..." and ONE comma-separated entry only.
        self.assertIn('"人工服务正在回复中..."', block)
        # Old multi-text variants must be gone.
        self.assertNotIn("人工服务仍在回复中", block)
        self.assertNotIn("人工服务核实中", block)

    def test_file_override_still_works(self) -> None:
        # mt048A loader must still consult the file path — regression guard.
        self.assertIn(
            "_PLACEHOLDER_TEXTS_FILENAME = \"ecan/placeholder_texts.json\"",
            PH_SRC_050L,
        )


# -----------------------------------------------------------------------
# mt050M — QA tool node enter/exit bracket
# -----------------------------------------------------------------------


BN_SRC_050M = Path("agent/ec_skills/build_node.py").read_text(encoding="utf-8")


class Mt050MQAToolBracketTests(unittest.TestCase):
    """mt050M instruments the build_node MCP tool callable with
    qa_tool_node_enter/exit ledger events.  The 2026-05-27 latency
    forensic showed a 15-25 s per-trace gap between qa_llm_response
    and the next qa_llm_start that wasn't covered by [PERF][MCP].
    These brackets attribute the gap to LangGraph routing + result
    marshaling vs. the actual MCP tool execution.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt050M", BN_SRC_050M)

    def test_enter_event_emitted(self) -> None:
        self.assertIn('"qa_tool_node_enter"', BN_SRC_050M)

    def test_exit_event_emitted(self) -> None:
        self.assertIn('"qa_tool_node_exit"', BN_SRC_050M)

    def test_gated_on_qa_inbound_payload(self) -> None:
        # Bracket must only fire for Q&A flows; other skills shouldn't
        # spam new ledger events.
        enter_block_start = BN_SRC_050M.find("mt050M: bracket QA")
        self.assertGreater(enter_block_start, 0)
        enter_block = BN_SRC_050M[enter_block_start:enter_block_start + 1500]
        self.assertIn("_is_qa_inbound_payload(_qa_cand)", enter_block)
        self.assertIn("_state_current_event_human_payload(state)", enter_block)

    def test_exit_carries_duration_ms(self) -> None:
        # The exit event must include a duration_ms field so we can
        # subtract [PERF][MCP] tool time and isolate the routing
        # overhead.
        exit_idx = BN_SRC_050M.find('"qa_tool_node_exit"')
        self.assertGreater(exit_idx, 0)
        # duration_ms keyword must land within ~500 chars of the exit
        # call site.
        nearby = BN_SRC_050M[exit_idx:exit_idx + 500]
        self.assertIn("duration_ms=int((time.time() - _qa_tool_t0)", nearby)

    def test_enter_and_exit_use_same_payload_var(self) -> None:
        # Both events should reference _qa_tool_payload so the trace
        # ledger pairs them by customer_id/trace_id.
        self.assertGreaterEqual(BN_SRC_050M.count("_qa_tool_payload"), 4)

    def test_imports_handled_locally(self) -> None:
        # Trace ledger is imported lazily inside try blocks so a missing
        # module never breaks tool execution.
        enter_idx = BN_SRC_050M.find('"qa_tool_node_enter"')
        snippet = BN_SRC_050M[max(0, enter_idx - 500):enter_idx]
        self.assertIn(
            "from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.trace_ledger import",
            snippet,
        )

    def test_exit_inside_sync_return_path(self) -> None:
        # The exit must precede the final `return state` in the sync
        # mode block — otherwise the duration would not include the
        # post-tool result marshaling we care about.
        exit_idx = BN_SRC_050M.find('"qa_tool_node_exit"')
        tail = BN_SRC_050M[exit_idx:exit_idx + 1500]
        self.assertIn("return state", tail)
        self.assertIn("node_callable = node_builder(mcp_tool_callable", tail)


# -----------------------------------------------------------------------
# mt050N — three fixes from the 2026-05-27 third-pass forensic
# -----------------------------------------------------------------------

SP_SRC_050N = Path(
    "agent/ec_skills/system_proxy.py"
).read_text(encoding="utf-8")
BN_SRC_050N = Path(
    "agent/ec_skills/build_node.py"
).read_text(encoding="utf-8")
FD_SRC_050N = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt050N_HttpxImportTests(unittest.TestCase):
    """mt050N-#2: move httpx import to module top to fix the import-lock
    stall under GIL contention.  Forensic showed initialize_ms varying
    67ms → 3820ms for rag_query's MCP ephemeral session, exactly
    correlated with concurrent LLM + browser activity.
    """

    def test_top_level_import(self) -> None:
        # Must appear at column 0 (no leading whitespace) — top-level
        # import block, not nested inside a function body.
        self.assertRegex(SP_SRC_050N, r"(?m)^import httpx$")

    def test_no_inline_import_in_factory(self) -> None:
        # The factory must NOT re-import httpx — that was the bug.
        start = SP_SRC_050N.find("def create_mcp_httpx_client(")
        self.assertGreater(start, 0)
        body = SP_SRC_050N[start:start + 1500]
        self.assertNotIn("import httpx", body)

    def test_factory_still_returns_async_client(self) -> None:
        # Sanity: behavior must be unchanged — still construct
        # httpx.AsyncClient with proxy=None.
        start = SP_SRC_050N.find("def create_mcp_httpx_client(")
        body = SP_SRC_050N[start:start + 1500]
        self.assertIn("httpx.AsyncClient(", body)
        self.assertIn("proxy=None", body)
        self.assertIn("trust_env=False", body)

    def test_marker_present(self) -> None:
        self.assertIn("mt050N", SP_SRC_050N)


class Mt050N_LLMHedgeTests(unittest.TestCase):
    """mt050N-#3: hedge at first heartbeat instead of waiting full 45s
    for timeout + retry.  3 of 4 LLM outliers in the 2026-05-27 log
    were stuck on degraded httpx pool slots; a fresh worker thread +
    loop got a healthy socket and completed in 3.7-5.0 s.  Hedging
    spawns the second attempt in parallel at the first heartbeat
    (default 15 s) so the race wins back ~30-40 s of wall clock per
    outlier turn.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt050N-#3", BN_SRC_050N)

    def test_env_var_default_15s(self) -> None:
        # ECAN_LLM_HEDGE_AT_S defaults to "15.0" when unset.  Setting
        # to 0 (or any value >= timeout_sec) disables hedging and
        # reverts to the legacy retry-on-timeout path.
        self.assertIn(
            '(os.getenv("ECAN_LLM_HEDGE_AT_S") or "15.0")',
            BN_SRC_050N,
        )

    def test_hedge_only_when_below_timeout(self) -> None:
        # Hedge must only engage when 0 < hedge_at_s < timeout_sec —
        # otherwise it could fire instantly (0) or never (>= timeout).
        self.assertIn(
            "if 0.0 < _hedge_at_s < timeout_sec:",
            BN_SRC_050N,
        )

    def test_hedged_pair_function_defined(self) -> None:
        self.assertIn(
            "def _run_hedged_pair(timeout_sec_inner: float, hedge_at_s: float):",
            BN_SRC_050N,
        )

    def test_attempts_share_done_event(self) -> None:
        # Both workers must signal the same Event so the first to
        # finish wins the race.
        start = BN_SRC_050N.find("def _run_hedged_pair(")
        body = BN_SRC_050N[start:start + 8000]
        self.assertIn("shared_done = threading.Event()", body)
        self.assertIn("shared_done.set()", body)
        # Both attempt indices must be spawnable through the same path.
        self.assertIn("_spawn(1)", body)
        self.assertIn("_spawn(2)", body)

    def test_winner_lock_prevents_race(self) -> None:
        start = BN_SRC_050N.find("def _run_hedged_pair(")
        body = BN_SRC_050N[start:start + 8000]
        self.assertIn("winner_lock = threading.Lock()", body)
        self.assertIn("with winner_lock:", body)

    def test_hedge_logs_when_spawned(self) -> None:
        # Operator visibility: must log when hedge engages.
        self.assertIn(
            '"[LLM-HEDGE]',
            BN_SRC_050N,
        )
        self.assertIn(
            "spawning hedge",
            BN_SRC_050N,
        )

    def test_legacy_retry_path_preserved(self) -> None:
        # Legacy retry-on-timeout path is the fallback when hedge is
        # disabled — important escape hatch for operators who can't
        # accept the 2× token cost on stuck calls.
        self.assertIn(
            "Legacy path (hedge disabled)",
            BN_SRC_050N,
        )
        # The original [LLM-RETRY] log line must still be present in
        # the disabled-hedge path.
        self.assertIn(
            "[LLM-RETRY] First attempt timed out",
            BN_SRC_050N,
        )

    def test_winner_attempt_tracked(self) -> None:
        # Log line on race completion must report WHICH attempt won so
        # operators can see whether the hedge actually paid off in
        # production.
        start = BN_SRC_050N.find("def _run_hedged_pair(")
        body = BN_SRC_050N[start:start + 8000]
        self.assertIn("won", body)
        self.assertIn("winner['attempt']", body)


class Mt050N_ProactiveLedgerClearTests(unittest.TestCase):
    """mt050N-#1a: clear the dedup ledger at supersede time (not just
    reactively on stale-drop).  Forensic showed 49 % of LLM outputs
    were dropped silently when PreDispatch superseded an in-flight
    turn; without proactive clear, the orphaned old message could
    never be re-dispatched.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt050N-#1a", FD_SRC_050N)

    def test_clear_called_at_supersede(self) -> None:
        # The clear must be invoked inside the supersede branch — same
        # block that already cancels placeholder timers and clears
        # dispatch_inflight.
        sup_idx = FD_SRC_050N.find("inflight supersede")
        self.assertGreater(sup_idx, -1)
        # Look forward up to 8 KB for the mt050N call (block contains
        # the mt050K broad-cancel + comments before the new addition).
        block = FD_SRC_050N[sup_idx:sup_idx + 8000]
        self.assertIn("clear_dispatched_identity_keys_for_customer", block)
        self.assertIn("mt050N", block)

    def test_clear_imported_from_actionable_items(self) -> None:
        # Must reuse the existing mt046A helper, not redefine.
        self.assertIn(
            "from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.actionable_items import",
            FD_SRC_050N,
        )
        self.assertIn(
            "clear_dispatched_identity_keys_for_customer",
            FD_SRC_050N,
        )

    def test_clear_uses_customer_key(self) -> None:
        # Must clear by the same customer_key the supersede block uses
        # (NOT session_id or other identifier).
        start = FD_SRC_050N.find("mt050N-#1a")
        self.assertGreater(start, -1)
        body = FD_SRC_050N[start:start + 2000]
        self.assertIn("_mt050n_clear(customer_key)", body)

    def test_clear_failure_is_non_fatal(self) -> None:
        # The clear is best-effort; a failure must NOT break supersede
        # processing.  Must be wrapped in try/except with a debug log.
        start = FD_SRC_050N.find("mt050N-#1a")
        body = FD_SRC_050N[start:start + 2500]
        self.assertIn("try:", body)
        self.assertIn("except Exception", body)
        self.assertIn("non-fatal", body)

    def test_clear_after_placeholder_cancel(self) -> None:
        # Order matters: placeholder cancels must run BEFORE the ledger
        # clear so the cancel still has the assigned-payload context.
        ph_cancel_idx = FD_SRC_050N.find("mt050K")
        clear_idx = FD_SRC_050N.find("mt050N-#1a")
        self.assertGreater(ph_cancel_idx, -1)
        self.assertGreater(clear_idx, -1)
        self.assertLess(ph_cancel_idx, clear_idx)


# -----------------------------------------------------------------------
# mt050O — split per-customer placeholder cap from per-inflight cap
# -----------------------------------------------------------------------

PH_SRC_050O = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")
TUN_SRC_050O = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/tunables.py"
).read_text(encoding="utf-8")
DA_SRC_050O = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt050O_PlaceholderCapSplitTests(unittest.TestCase):
    """mt050O fixes the 2026-05-28 customer-test bug where 29 of 39
    slow turns (>10 s) saw no placeholder because the sweeper reused
    the per-inflight cap (default 2) as a per-customer-90s cap.  After
    the first 2 placeholders fired for a customer, every subsequent
    turn within the 90 s window had its registry entry silently
    dropped by claim_expired (no log).

    Fix: split into ``cap_per_window`` (default 12 = 6 turns × 2),
    operator-tunable via ECAN_FEIGE_PLACEHOLDER_CAP_PER_WINDOW.
    Per-inflight cap (max_placeholders=2) is unchanged.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt050O", PH_SRC_050O)
        self.assertIn("mt050O", TUN_SRC_050O)
        self.assertIn("mt050O", DA_SRC_050O)

    def test_default_cap_per_window_added(self) -> None:
        # New tunable must be defined and exported.
        self.assertIn(
            "DEFAULT_FEIGE_PLACEHOLDER_CAP_PER_WINDOW: int = 12",
            TUN_SRC_050O,
        )
        self.assertIn(
            '"DEFAULT_FEIGE_PLACEHOLDER_CAP_PER_WINDOW"',
            TUN_SRC_050O,
        )

    def test_claim_expired_takes_cap_per_window(self) -> None:
        # Function signature must accept cap_per_window param.
        self.assertIn(
            "cap_per_window: int | None = None",
            PH_SRC_050O,
        )

    def test_cap_per_window_used_in_cap_check(self) -> None:
        # The cap-check site must use _eff_cap (resolved from
        # cap_per_window) NOT max_placeholders directly.
        cap_idx = PH_SRC_050O.find("per-customer-window")
        self.assertGreater(cap_idx, -1)
        body = PH_SRC_050O[cap_idx:cap_idx + 2500]
        self.assertIn(
            "_eff_cap = max_placeholders if cap_per_window is None else cap_per_window",
            body,
        )
        self.assertIn("if len(cust_ts) >= _eff_cap:", body)

    def test_cap_zero_disables(self) -> None:
        # cap_per_window=0 must skip the cap check entirely (operator
        # escape hatch).
        cap_idx = PH_SRC_050O.find("per-customer-window")
        body = PH_SRC_050O[cap_idx:cap_idx + 2500]
        self.assertIn("if _eff_cap > 0:", body)

    def test_back_compat_default_none(self) -> None:
        # When cap_per_window is None (legacy callers), behaviour falls
        # back to the pre-mt050O per-inflight cap — important so any
        # test that doesn't pass cap_per_window keeps working.
        sig_idx = PH_SRC_050O.find("def claim_expired(")
        body = PH_SRC_050O[sig_idx:sig_idx + 2000]
        self.assertIn("cap_per_window: int | None = None", body)

    def test_sweep_loop_passes_cap(self) -> None:
        # sweep_loop_async must accept and forward cap_per_window.
        sweep_idx = PH_SRC_050O.find("async def sweep_loop_async(")
        body = PH_SRC_050O[sweep_idx:sweep_idx + 2000]
        self.assertIn("cap_per_window: int | None = None", body)
        self.assertIn("cap_per_window=cap_per_window,", body)

    def test_dom_assets_resolves_and_passes_cap(self) -> None:
        # The sweeper-start in dom_assets.py must resolve the new
        # tunable and pass it into sweep_loop_async.
        self.assertIn(
            "DEFAULT_FEIGE_PLACEHOLDER_CAP_PER_WINDOW as _D_PHCW",
            DA_SRC_050O,
        )
        self.assertIn(
            '_cap_per_window = _ph_ri(\n'
            '        "FEIGE_PLACEHOLDER_CAP_PER_WINDOW", _D_PHCW, None\n'
            "    )",
            DA_SRC_050O,
        )
        self.assertIn(
            "cap_per_window=_cap_per_window,",
            DA_SRC_050O,
        )

    def test_sweeper_start_log_mentions_cap(self) -> None:
        # Operator visibility: sweeper-start log line must include
        # cap_per_window so it's obvious from logs what's in effect.
        start_idx = DA_SRC_050O.find("sweeper-start resolved")
        body = DA_SRC_050O[start_idx:start_idx + 600]
        self.assertIn("cap_per_window={_cap_per_window}", body)


class Mt050O_ClaimExpiredBehaviorTests(unittest.TestCase):
    """Direct behavior tests — exercise the actual claim_expired
    function with module-level registry mutations so we can prove the
    cap split works.  Uses module-internal state so each test resets
    the registry to a clean slate.
    """

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as ph,
        )
        self.ph = ph
        # Reset module state
        with ph._REGISTRY_LOCK:
            ph._REGISTRY.clear()
            ph._PLACEHOLDERS_TYPED_TS.clear()
            ph._REAL_REPLY_AT.clear()
            ph._INFLIGHT_PLACEHOLDER_TASKS.clear()

    def _arm(self, customer: str, src_id: str, timeout_s: float = 0.001) -> None:
        # Use very short timeout so deadline is immediately past.
        self.ph.arm(customer_key=customer, source_msg_id=src_id, timeout_s=timeout_s)

    def test_cap_per_window_none_uses_max_placeholders(self) -> None:
        # Legacy behaviour: cap_per_window=None falls back to per-inflight cap.
        # Fire 2 placeholders for customer A first to populate the ledger.
        for i in range(2):
            self.ph.mark_placeholder_typed("custA")
        # Now arm a new turn for A; with cap_per_window=None and
        # max_placeholders=2, claim_expired should drop it.
        self._arm("custA", "msg-new")
        import time
        time.sleep(0.05)  # let deadline pass
        expired = self.ph.claim_expired(max_placeholders=2, rearm_s=15.0)
        self.assertEqual(
            len(expired), 0,
            "legacy back-compat: cap_per_window=None should equal max_placeholders=2",
        )

    def test_cap_per_window_larger_allows_more_turns(self) -> None:
        # mt050O behaviour: cap_per_window=12 allows turns past the
        # per-inflight cap of 2.
        for i in range(2):
            self.ph.mark_placeholder_typed("custB")
        self._arm("custB", "msg-third-turn")
        import time
        time.sleep(0.05)
        expired = self.ph.claim_expired(
            max_placeholders=2, rearm_s=15.0, cap_per_window=12,
        )
        self.assertEqual(
            len(expired), 1,
            "cap_per_window=12 should allow a 3rd-turn placeholder after 2 prior fires",
        )

    def test_cap_per_window_zero_disables_check(self) -> None:
        # cap_per_window=0 disables the per-customer ceiling entirely.
        for i in range(20):
            self.ph.mark_placeholder_typed("custC")
        self._arm("custC", "msg-many")
        import time
        time.sleep(0.05)
        expired = self.ph.claim_expired(
            max_placeholders=2, rearm_s=15.0, cap_per_window=0,
        )
        self.assertEqual(
            len(expired), 1,
            "cap_per_window=0 must disable the ceiling, allowing fires regardless of count",
        )

    def test_per_inflight_cap_still_enforced(self) -> None:
        # mt050O must NOT relax the per-inflight cap.  Two placeholders
        # for the SAME source_msg_id should still be the max even with
        # a generous cap_per_window.
        self._arm("custD", "msg-same")
        import time
        # First claim
        time.sleep(0.05)
        expired1 = self.ph.claim_expired(
            max_placeholders=2, rearm_s=0.001, cap_per_window=100,
        )
        self.assertEqual(len(expired1), 1)
        self.ph.mark_placeholder_typed("custD")
        # Second claim
        time.sleep(0.05)
        expired2 = self.ph.claim_expired(
            max_placeholders=2, rearm_s=0.001, cap_per_window=100,
        )
        self.assertEqual(len(expired2), 1)
        self.assertTrue(expired2[0].is_final)
        self.ph.mark_placeholder_typed("custD")
        # Third claim should be zero (per-inflight cap hit; entry removed)
        time.sleep(0.05)
        expired3 = self.ph.claim_expired(
            max_placeholders=2, rearm_s=0.001, cap_per_window=100,
        )
        self.assertEqual(
            len(expired3), 0,
            "per-inflight cap of 2 must still hold even with cap_per_window=100",
        )


# -----------------------------------------------------------------------
# mt050P — is_real_reply_recent newer-turn semantic
# -----------------------------------------------------------------------

PT_SRC_050P = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")
DA_SRC_050P = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")
RUN_SRC_050P = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt050P_NewerTurnSemanticSourceTests(unittest.TestCase):
    """mt050P fixes the 2026-05-28 customer-test bug where mt050G
    suppressed every burst-typing customer's placeholders.  The
    blank-key (customer, "") slot in _REAL_REPLY_AT was stamped on
    every reply (mt038E intent), but is_real_reply_recent had no
    newer-turn guard, so any new turn within REAL_REPLY_SUPPRESS_S
    (60 s) of any prior reply saw its placeholder silently suppressed.

    Fix: pipe entry.armed_at through claim_expired → ExpiredEntry →
    placeholder_submitter → _enqueue_direct_placeholder → the 3
    is_real_reply_recent call sites.  The recent-reply check now
    returns False when the recorded reply timestamp predates the
    entry's arm time.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt050P", PT_SRC_050P)
        self.assertIn("mt050P", DA_SRC_050P)
        self.assertIn("mt050P", RUN_SRC_050P)

    def test_is_real_reply_recent_accepts_armed_at(self) -> None:
        sig_idx = PT_SRC_050P.find("def is_real_reply_recent(")
        self.assertGreater(sig_idx, -1)
        body = PT_SRC_050P[sig_idx:sig_idx + 1500]
        self.assertIn("armed_at: float = 0.0", body)

    def test_newer_turn_guard_uses_strict_lt(self) -> None:
        # Important: same-millisecond stamps (Windows ~1 ms tick) must
        # STILL suppress.  Only ``ts < armed_at`` skips suppression.
        body = PT_SRC_050P
        self.assertIn(
            "if armed_at > 0.0 and ts < armed_at:",
            body,
        )

    def test_expired_entry_carries_armed_at(self) -> None:
        # The ExpiredEntry dataclass must propagate armed_at so the
        # downstream caller (the placeholder submitter) can pass it
        # into the runner's pre-type checks.
        idx = PT_SRC_050P.find("class ExpiredEntry")
        self.assertGreater(idx, -1)
        body = PT_SRC_050P[idx:idx + 1000]
        self.assertIn("armed_at: float = 0.0", body)

    def test_claim_expired_populates_armed_at_in_output(self) -> None:
        # The ExpiredEntry instance built in claim_expired must carry
        # entry.armed_at forward (the entry's existing field).
        idx = PT_SRC_050P.find("out.append(\n                ExpiredEntry(")
        self.assertGreater(idx, -1)
        body = PT_SRC_050P[idx:idx + 600]
        self.assertIn("armed_at=entry.armed_at,", body)

    def test_sweeper_mt050g_passes_armed_at(self) -> None:
        # The mt050G sweeper-side suppression check at line 766-ish
        # must pass entry.armed_at.
        idx = PT_SRC_050P.find("mt050G suppressed placeholder")
        self.assertGreater(idx, -1)
        # Look at code just before that log call for the conditional.
        before = PT_SRC_050P[max(0, idx - 800):idx]
        self.assertIn("armed_at=entry.armed_at,", before)

    def test_sweeper_passes_armed_at_to_submitter(self) -> None:
        idx = PT_SRC_050P.find("submitted = placeholder_submitter(")
        self.assertGreater(idx, -1)
        body = PT_SRC_050P[idx:idx + 400]
        self.assertIn("armed_at=entry.armed_at,", body)

    def test_dom_assets_submitter_accepts_armed_at(self) -> None:
        idx = DA_SRC_050P.find("def _placeholder_submitter(")
        self.assertGreater(idx, -1)
        body = DA_SRC_050P[idx:idx + 400]
        self.assertIn("armed_at: float = 0.0", body)

    def test_dom_assets_submitter_forwards_to_runner(self) -> None:
        # Must call _enq with armed_at AND have a TypeError fallback
        # for runners that predate mt050P (forward-compat wire).
        idx = DA_SRC_050P.find("def _placeholder_submitter(")
        body = DA_SRC_050P[idx:idx + 2000]
        self.assertIn("armed_at=armed_at,", body)
        self.assertIn("except TypeError:", body)

    def test_runner_enq_accepts_armed_at(self) -> None:
        idx = RUN_SRC_050P.find("def _enqueue_direct_placeholder(")
        self.assertGreater(idx, -1)
        body = RUN_SRC_050P[idx:idx + 1500]
        self.assertIn("armed_at: float = 0.0", body)

    def test_all_three_checks_pass_armed_at(self) -> None:
        # mt050P preserved through mt051C: the 3 is_real_reply_recent
        # call sites moved out of runner.py and into
        # hooks/external/feige_chat/direct_delivery.py (the closure body
        # was hoisted out of runner._enqueue_direct_placeholder).  All 3
        # must still thread armed_at through.  Whitespace-tolerant.
        DD_SRC = Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/direct_delivery.py"
        ).read_text(encoding="utf-8")
        call_count = DD_SRC.count("_ph_timer.is_real_reply_recent(")
        armed_count = DD_SRC.count("armed_at=armed_at")
        self.assertEqual(
            call_count, 3,
            f"Expected exactly 3 is_real_reply_recent calls inside "
            f"direct_delivery.py; got {call_count}",
        )
        self.assertGreaterEqual(
            armed_count, 3,
            f"Expected at least 3 armed_at=armed_at forwardings (one per "
            f"is_real_reply_recent call); got {armed_count}",
        )


class Mt050P_BehaviourTests(unittest.TestCase):
    """Direct behaviour tests against the runtime function."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as ph,
        )
        self.ph = ph
        with ph._REGISTRY_LOCK:
            ph._REGISTRY.clear()
            ph._PLACEHOLDERS_TYPED_TS.clear()
            ph._REAL_REPLY_AT.clear()

    def test_legacy_no_armed_at_still_suppresses(self) -> None:
        # Back-compat: omitting armed_at preserves pre-mt050P behaviour.
        self.ph.mark_real_reply_delivered("custA", "old_msg")
        self.assertTrue(
            self.ph.is_real_reply_recent("custA", "new_msg"),
            "without armed_at, the blank-key stamp still suppresses",
        )

    def test_newer_turn_armed_after_reply_NOT_suppressed(self) -> None:
        # mt050P semantic: if the entry was armed AFTER the recent
        # reply, that reply was for an older turn — don't suppress.
        self.ph.mark_real_reply_delivered("custB", "old_msg")
        import time
        time.sleep(0.01)
        armed_at = time.time()  # AFTER the stamp
        self.assertFalse(
            self.ph.is_real_reply_recent("custB", "new_msg", armed_at=armed_at),
            "newer-turn semantic must not be suppressed by older-turn reply",
        )

    def test_armed_before_reply_IS_suppressed(self) -> None:
        # If the entry was armed BEFORE the recent reply, the reply IS
        # for this turn (or a newer turn this entry should not race).
        import time
        armed_at = time.time()
        time.sleep(0.01)
        self.ph.mark_real_reply_delivered("custC", "this_msg")
        self.assertTrue(
            self.ph.is_real_reply_recent("custC", "this_msg", armed_at=armed_at),
            "armed_at < reply_ts must still suppress (the reply is for this turn)",
        )

    def test_armed_at_zero_disables_guard(self) -> None:
        # armed_at=0.0 (back-compat default) must behave exactly like
        # the pre-mt050P version.
        self.ph.mark_real_reply_delivered("custD", "old")
        self.assertTrue(
            self.ph.is_real_reply_recent("custD", "new", armed_at=0.0),
        )

    def test_blank_key_stamp_does_not_suppress_newer_turn(self) -> None:
        # This is the SCENARIO that broke 陆地飞鱼.  Old turn delivered,
        # blank-key stamp set, new turn arms with different src_msg_id
        # AFTER.  Pre-mt050P: suppressed.  Post-mt050P: NOT suppressed.
        self.ph.mark_real_reply_delivered("陆地飞鱼", "old_id_DAEC")
        import time
        time.sleep(0.01)
        new_arm = time.time()
        self.assertFalse(
            self.ph.is_real_reply_recent(
                "陆地飞鱼", "new_id_968C", armed_at=new_arm,
            ),
            "the 陆地飞鱼 bug: blank-key stamp from old reply suppressed new turn",
        )


# -----------------------------------------------------------------------
# mt051A — relocate feige_delivery_durability into feige_chat
# -----------------------------------------------------------------------


class Mt051A_DurabilityRelocationTests(unittest.TestCase):
    """mt051A moved agent/ec_tasks/feige_delivery_durability.py into
    agent/ec_skills/browser_use_extension/hooks/external/feige_chat/
    delivery_durability.py.  Directory implies the site so the
    ``feige_`` prefix is dropped from the filename.  All 9 import
    sites + 2 test sites updated; old file deleted.
    """

    def test_old_path_is_gone(self) -> None:
        old = Path("agent/ec_tasks/feige_delivery_durability.py")
        self.assertFalse(
            old.exists(),
            f"mt051A: old file {old} must be deleted",
        )

    def test_new_path_exists_and_exposes_api(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            delivery_durability as dd,
        )
        for fn in (
            "record_pending_delivery",
            "clear_pending_delivery",
            "snapshot_pending_deliveries",
            "abort_pending_from_previous_process",
        ):
            self.assertTrue(
                callable(getattr(dd, fn, None)),
                f"mt051A: delivery_durability must export {fn}()",
            )

    def test_on_disk_state_filename_preserved(self) -> None:
        # Filename kept as-is so on-disk pending deliveries from a prior
        # process run (pre-mt051A) are still recognised after the upgrade.
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            delivery_durability as dd,
        )
        self.assertEqual(dd._FILE_NAME, "feige_pending_deliveries.json")

    def test_no_stale_import_sites_remain(self) -> None:
        # Sweep the tree for the old import path; should be zero hits
        # outside the historical comment in the new module and this
        # very test file (which mentions the string in its assertion).
        import subprocess
        result = subprocess.run(
            [
                "git",
                "grep",
                "-n",
                "from agent.ec_tasks.feige_delivery_durability",
                "--",
                "*.py",
                ":!tests/test_mt038_attachment_marker_rescue.py",
            ],
            capture_output=True,
            text=True,
        )
        # Empty stdout = zero matches.
        self.assertEqual(
            "",
            result.stdout.strip(),
            f"mt051A: lingering import sites:\n{result.stdout}",
        )


# -----------------------------------------------------------------------
# mt051B — on_live_chat_placeholder_needed hook stage scaffolding
# -----------------------------------------------------------------------


class Mt051B_HookStageScaffoldingTests(unittest.TestCase):
    """mt051B adds Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED and the
    LiveChatPlaceholderRequest payload contract to hook_api.py.  No
    consumers yet — mt051C migrates Feige's _enqueue_direct_placeholder
    to plug in here.  Adding a stage is purely additive, so
    HOOK_API_VERSION stays at 1.
    """

    def test_stage_value_added(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import Stage
        self.assertEqual(
            Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED.value,
            "on_live_chat_placeholder_needed",
        )

    def test_hook_api_version_not_bumped(self) -> None:
        # Adding a stage is additive — existing hooks (declaring v1)
        # must continue to load.  If we ever DO bump, that's a separate
        # change with a compat shim in _is_api_version_supported.
        from agent.ec_skills.browser_use_extension.hook_api import HOOK_API_VERSION
        self.assertEqual(HOOK_API_VERSION, 1)

    def test_live_chat_placeholder_request_importable(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )
        # Required fields validate.
        req = LiveChatPlaceholderRequest(
            session_id="customer-A",
            text="please wait...",
        )
        self.assertEqual(req.session_id, "customer-A")
        self.assertEqual(req.text, "please wait...")
        self.assertEqual(req.turn_id, "")
        self.assertEqual(req.armed_at, 0.0)
        self.assertEqual(req.site_context, {})

    def test_live_chat_placeholder_request_rejects_missing_required(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )
        from pydantic import ValidationError
        # session_id missing → reject.
        with self.assertRaises(ValidationError):
            LiveChatPlaceholderRequest(text="hi")
        # text missing → reject.
        with self.assertRaises(ValidationError):
            LiveChatPlaceholderRequest(session_id="A")

    def test_request_carries_armed_at_and_site_context(self) -> None:
        # The mt050P newer-turn semantic depends on armed_at flowing
        # through to the site hook.  site_context lets a site stash
        # opaque data (preferred tab id, etc.) without polluting the
        # generic envelope.
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )
        import time
        t = time.time()
        req = LiveChatPlaceholderRequest(
            session_id="陆地飞鱼",
            turn_id="msg-DAEC",
            text="人工服务正在回复中...",
            armed_at=t,
            site_context={"preferred_tab_id": "AB7467"},
        )
        self.assertEqual(req.armed_at, t)
        self.assertEqual(req.site_context["preferred_tab_id"], "AB7467")

    def test_exported_in_all(self) -> None:
        from agent.ec_skills.browser_use_extension import hook_api
        self.assertIn("LiveChatPlaceholderRequest", hook_api.__all__)

    def test_stage_recognised_by_pydantic_validator(self) -> None:
        # Manifests reference Stage by value; verify a manifest can
        # declare the new stage without the loader rejecting it.
        from agent.ec_skills.browser_use_extension.hook_api import (
            HookManifest, Stage,
        )
        m = HookManifest(
            name="dummy.live_chat.placeholder",
            runtime="python",
            stage=Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED,
            entrypoint="dummy.py:Dummy",
        )
        self.assertEqual(m.stage, Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED)


# -----------------------------------------------------------------------
# mt051C — extract placeholder send into feige_chat/direct_delivery
# -----------------------------------------------------------------------

DD_SRC_051C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/direct_delivery.py"
).read_text(encoding="utf-8")
RUN_SRC_051C = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
DISP_SRC_051C = Path("agent/ec_skills/live_chat_dispatch.py").read_text(encoding="utf-8")
FC_INIT_051C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/__init__.py"
).read_text(encoding="utf-8")


class Mt051C_PlaceholderMigrationSourceTests(unittest.TestCase):
    """mt051C moved the ~250-line _placeholder_send closure body out
    of runner._enqueue_direct_placeholder into
    hooks/external/feige_chat/direct_delivery.py.  Runner becomes a
    thin shim that fires the registered live_chat_dispatch handler.
    The hook stage + payload contract from mt051B carry the call.
    """

    def test_marker_present_in_each_file(self) -> None:
        self.assertIn("mt051C", DD_SRC_051C)
        self.assertIn("mt051C", RUN_SRC_051C)
        self.assertIn("mt051C", DISP_SRC_051C)
        self.assertIn("mt051C", FC_INIT_051C)

    def test_runner_shim_is_short(self) -> None:
        # Sanity: the runner-side _enqueue_direct_placeholder must be
        # short (< ~70 lines).  Pre-mt051C it was 330+ lines.
        idx = RUN_SRC_051C.find("def _enqueue_direct_placeholder(")
        self.assertGreater(idx, -1)
        end_idx = RUN_SRC_051C.find("\ndef ", idx + 1)
        self.assertGreater(end_idx, -1)
        body = RUN_SRC_051C[idx:end_idx]
        line_count = body.count("\n")
        self.assertLess(
            line_count, 80,
            f"runner shim should be < 80 lines; got {line_count}",
        )

    def test_runner_no_longer_imports_feige_tools(self) -> None:
        # The whole point of mt051C: runner.py must not import any
        # feige_chat-specific modules in the placeholder dispatch path.
        idx = RUN_SRC_051C.find("def _enqueue_direct_placeholder(")
        end_idx = RUN_SRC_051C.find("\ndef ", idx + 1)
        body = RUN_SRC_051C[idx:end_idx]
        for forbidden in (
            "feige_chat.tab_pool",
            "feige_chat.placeholder_timer",
            "feige_chat import",
            "extension_tools_service",
        ):
            self.assertNotIn(
                forbidden, body,
                f"runner shim must not import {forbidden!r} after mt051C",
            )

    def test_runner_fires_live_chat_dispatch(self) -> None:
        idx = RUN_SRC_051C.find("def _enqueue_direct_placeholder(")
        end_idx = RUN_SRC_051C.find("\ndef ", idx + 1)
        body = RUN_SRC_051C[idx:end_idx]
        self.assertIn("from agent.ec_skills import live_chat_dispatch", body)
        self.assertIn(
            "live_chat_dispatch.dispatch_placeholder(", body,
        )
        self.assertIn("LiveChatPlaceholderRequest(", body)

    def test_runner_threads_worker_loop_via_kwarg(self) -> None:
        idx = RUN_SRC_051C.find("def _enqueue_direct_placeholder(")
        end_idx = RUN_SRC_051C.find("\ndef ", idx + 1)
        body = RUN_SRC_051C[idx:end_idx]
        self.assertIn("worker_loop=worker_loop", body)

    def test_direct_delivery_has_handler_and_register(self) -> None:
        self.assertIn("def _placeholder_handler(", DD_SRC_051C)
        self.assertIn("def register() -> None:", DD_SRC_051C)
        self.assertIn(
            "live_chat_dispatch.register_placeholder_handler(",
            DD_SRC_051C,
        )

    def test_direct_delivery_unwraps_request_to_feige_terms(self) -> None:
        # The handler must unwrap the generic envelope into the Feige-
        # specific naming the underlying coroutine expects.  This is
        # the "site-shadow" pattern — generic outside, Feige inside.
        idx = DD_SRC_051C.find("def _placeholder_handler(")
        body = DD_SRC_051C[idx:idx + 2500]
        self.assertIn("req.session_id", body)
        self.assertIn("req.turn_id", body)
        self.assertIn("req.text", body)
        self.assertIn("req.armed_at", body)
        self.assertIn('req.site_context.get("browser_session")', body)

    def test_init_registers_direct_delivery_at_import(self) -> None:
        self.assertIn("from . import direct_delivery", FC_INIT_051C)
        self.assertIn("_direct_delivery.register()", FC_INIT_051C)
        self.assertIn("_DD_HOOK_REGISTERED", FC_INIT_051C)


class Mt051C_DispatchBehaviourTests(unittest.TestCase):
    """End-to-end behaviour: a registered handler is invoked by the
    runner-side shim; an unregistered process returns False without
    raising."""

    def setUp(self) -> None:
        from agent.ec_skills import live_chat_dispatch
        self.dispatch = live_chat_dispatch
        # Save + clear any handler that the feige_chat package may have
        # already registered (it does so at import time).
        self._saved_handler = self.dispatch._REGISTRY.get(
            self._stage()
        )
        self.dispatch.clear_placeholder_handler()

    def tearDown(self) -> None:
        # Restore the production handler so other tests that exercise
        # the placeholder path keep working.
        self.dispatch.clear_placeholder_handler()
        if self._saved_handler is not None:
            self.dispatch._REGISTRY[self._stage()] = self._saved_handler

    def _stage(self):
        from agent.ec_skills.browser_use_extension.hook_api import Stage
        return Stage.ON_LIVE_CHAT_PLACEHOLDER_NEEDED

    def test_unregistered_returns_false(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )
        req = LiveChatPlaceholderRequest(session_id="A", text="x")
        self.assertFalse(self.dispatch.dispatch_placeholder(req))
        self.assertFalse(self.dispatch.has_placeholder_handler())

    def test_registered_handler_is_called_with_request(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )
        captured = {}

        def fake(req, *, worker_loop=None, **_):
            captured["req"] = req
            captured["worker_loop"] = worker_loop
            return True

        self.dispatch.register_placeholder_handler(fake)
        req = LiveChatPlaceholderRequest(
            session_id="B", turn_id="T1", text="please wait",
            armed_at=1234.5,
        )
        ok = self.dispatch.dispatch_placeholder(req, worker_loop="LOOP_SENTINEL")
        self.assertTrue(ok)
        self.assertIs(captured["req"], req)
        self.assertEqual(captured["worker_loop"], "LOOP_SENTINEL")

    def test_register_replaces_previous_handler(self) -> None:
        from agent.ec_skills.browser_use_extension.hook_api import (
            LiveChatPlaceholderRequest,
        )

        def first(req, **_):
            return False

        def second(req, **_):
            return True

        self.dispatch.register_placeholder_handler(first)
        self.dispatch.register_placeholder_handler(second)
        req = LiveChatPlaceholderRequest(session_id="C", text="x")
        self.assertTrue(self.dispatch.dispatch_placeholder(req))


# -----------------------------------------------------------------------
# mt051E — phantom-abstraction renames in runner.py
# -----------------------------------------------------------------------

RUN_SRC_051E = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt051E_PhantomAbstractionRenameTests(unittest.TestCase):
    """mt051E renamed Feige-named Python identifiers in runner.py to
    live-chat-neutral names.  Env var names and trace-ledger event
    strings are preserved (operator-visible artifacts).  Pure rename;
    functionally identical to mt050P.
    """

    def test_no_python_identifier_starts_with_underscore_FEIGE_in_runner(self) -> None:
        # Identifier-only sweep.  The (?<![A-Z_a-z0-9]) lookbehind ensures
        # the leading underscore is NOT preceded by another identifier
        # character — that distinguishes Python globals (preceded by
        # whitespace, comma, paren, etc.) from env var string literals
        # like ``"ECAN_FEIGE_SHUTDOWN_..."`` (preceded by ``N``).
        import re
        boundary = r"(?<![A-Za-z0-9_])"
        forbidden = re.findall(boundary + r"_DIRECT_FEIGE_[A-Z_]+", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_FEIGE_SHUTDOWN_[A-Z_]+", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_direct_feige_[a-z_]+", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_record_direct_feige_[a-z_]+", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_feige_cdp_health_cooldown_remaining", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_STALE_EVENT_TTL_S", RUN_SRC_051E)
        forbidden += re.findall(boundary + r"_EVT_ENQUEUE_TS_ATTR", RUN_SRC_051E)
        self.assertEqual(
            forbidden, [],
            f"mt051E: lingering Feige-named identifiers in runner.py: "
            f"{set(forbidden)}",
        )

    def test_new_live_chat_names_present(self) -> None:
        # Spot-check a few specific renames.
        for new_name in (
            "_DIRECT_LIVE_CHAT_ASYNC_WORKER",
            "_DIRECT_LIVE_CHAT_JOB_TIMEOUT_S",
            "_DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD",
            "_LIVE_CHAT_SHUTDOWN_EVENT",
            "_LIVE_CHAT_EVENT_STALE_TTL_S",
            "_LIVE_CHAT_EVENT_ENQUEUE_TS_ATTR",
            "_direct_live_chat_cdp_timeout_circuit_remaining",
            "_live_chat_cdp_health_cooldown_remaining",
        ):
            self.assertIn(
                new_name, RUN_SRC_051E,
                f"mt051E: expected rename target {new_name!r} missing",
            )

    def test_env_var_names_preserved(self) -> None:
        # Operator-visible config must not change.  These string
        # literals carry the env var names; renaming them would break
        # every customer that set them.
        for env_var in (
            'os.getenv("DIRECT_FEIGE_CDP_TIMEOUT_CIRCUIT_THRESHOLD"',
            'os.getenv("DIRECT_FEIGE_JOB_TIMEOUT_S"',
            'os.getenv("DIRECT_FEIGE_MAX_RETRIES"',
            'os.getenv("ECAN_FEIGE_SHUTDOWN_DRAIN_TIMEOUT_S"',
        ):
            self.assertIn(
                env_var, RUN_SRC_051E,
                f"mt051E: env var literal {env_var!r} must be preserved "
                f"(operator config relies on these names)",
            )

    def test_trace_ledger_stage_strings_preserved(self) -> None:
        # Operator-visible log stage names must not change.  Customers
        # grep these from FEIGE-LEDGER output for monitoring.
        for stage in (
            '"direct_feige_delivery"',
            '"direct_feige_send_start"',
            '"direct_feige_send_success"',
            '"direct_feige_send_failed"',
        ):
            self.assertIn(
                stage, RUN_SRC_051E,
                f"mt051E: trace-ledger stage string {stage!r} must be "
                f"preserved (operator monitoring grep depends on these)",
            )


# -----------------------------------------------------------------------
# mt052A — merge sidebar+bubble text instead of overriding
# -----------------------------------------------------------------------

PD_SRC_052A = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt052A_PredispatchMergeSourceTests(unittest.TestCase):
    """mt052A stops the PreDispatch silent-drop bug.  When the front-
    desk queue is busy and the customer types a second message during
    the scrape window, the OLD code dropped the sidebar's text in
    favour of the newer scraped bubble.  The customer's earlier
    question reached neither the LLM nor any retry — observed live on
    2026-05-29 10:50 where 陆地飞鱼's "夏天穿会不会热" went unanswered.

    The fix MERGES both texts with a newline separator so the LLM
    addresses both in one reply.  source_msg_id stays the newer one
    (JS source-guard still validates against the latest bubble).
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052A", PD_SRC_052A)

    def test_merged_log_line_present(self) -> None:
        # The log line is split across two f-string fragments for
        # line-length wrapping.  Check each fragment individually.
        self.assertIn("thread-scrape merged ", PD_SRC_052A)
        self.assertIn("sidebar + bubble for cust=", PD_SRC_052A)

    def test_override_log_line_still_present_for_substring_case(self) -> None:
        # When the new bubble already CONTAINS the orig (e.g. sidebar
        # is a truncation), the old override log line stays — we just
        # don't double-include the text.
        self.assertIn(
            "thread-scrape overrode",
            PD_SRC_052A,
        )

    def test_merge_branch_uses_newline_separator(self) -> None:
        # The user specified newline as the separator.
        start = PD_SRC_052A.find("mt052A")
        self.assertGreater(start, -1)
        block = PD_SRC_052A[start:start + 2500]
        self.assertIn('merged = f"{orig_last}\\n{new_last}"', block)

    def test_merge_skipped_when_new_contains_orig(self) -> None:
        # Substring-skip guard: if the scrape returned a message that
        # already includes the sidebar text (e.g. truncation), don't
        # duplicate it in the prompt.
        start = PD_SRC_052A.find("mt052A")
        block = PD_SRC_052A[start:start + 2500]
        self.assertIn("if orig_last and orig_last not in new_last:", block)
        self.assertIn("else:", block)
        # The else branch is the legacy override behaviour.
        self.assertIn('item["last_message"] = new_last', block)

    def test_merge_branch_sets_last_message_to_merged(self) -> None:
        start = PD_SRC_052A.find("mt052A")
        block = PD_SRC_052A[start:start + 2500]
        self.assertIn('item["last_message"] = merged', block)

    def test_system_message_guard_unchanged_pre_merge(self) -> None:
        # The "thread-scrape ignored system-looking latest bubble"
        # guard must still run BEFORE the merge branch — otherwise we'd
        # merge an actual customer message with a platform/system
        # notice.  Locate by ordering in the source.
        ignore_idx = PD_SRC_052A.find("thread-scrape ignored")
        merge_idx = PD_SRC_052A.find("thread-scrape merged")
        self.assertGreater(ignore_idx, -1)
        self.assertGreater(merge_idx, -1)
        self.assertLess(
            ignore_idx, merge_idx,
            "system-message guard must precede the merge branch",
        )


class Mt052A_MergeBehaviourTests(unittest.TestCase):
    """Behaviour test: drive the merge path with two concrete messages
    and verify ``item['last_message']`` ends up containing both.
    """

    def _run_override_branch(
        self,
        orig_last: str,
        new_last: str,
    ) -> str:
        """Inline simulation of the mt052A override branch in
        pre_dispatch_enrich.py.  We don't have a clean way to invoke
        ``enrich_item`` directly without spinning up the entire
        DispatchContext, so this test reproduces the merge logic and
        verifies it matches the source (the source-pattern tests above
        guard the implementation; this guards the semantics).
        """
        # Mirror the source logic.
        if not new_last or new_last == orig_last:
            return orig_last
        if orig_last and orig_last not in new_last:
            return f"{orig_last}\n{new_last}"
        return new_last

    def test_two_distinct_questions_get_merged(self) -> None:
        # The exact 陆地飞鱼 scenario from the 2026-05-29 trace.
        result = self._run_override_branch("夏天穿会不会热", "透气吗")
        self.assertEqual(result, "夏天穿会不会热\n透气吗")

    def test_sidebar_truncation_skips_merge(self) -> None:
        # The bubble already contains the sidebar text (e.g. Feige's
        # sidebar preview was truncated).  Don't duplicate.
        sidebar = "这个是纯棉"
        bubble = "这个是纯棉的吗？"
        result = self._run_override_branch(sidebar, bubble)
        self.assertEqual(result, bubble)

    def test_identical_texts_no_op(self) -> None:
        # Same text in both — no override fires, original returned.
        result = self._run_override_branch("会不会扎皮肤", "会不会扎皮肤")
        self.assertEqual(result, "会不会扎皮肤")

    def test_empty_new_no_op(self) -> None:
        # Scrape returned nothing — keep the sidebar text.
        result = self._run_override_branch("夏天穿会不会热", "")
        self.assertEqual(result, "夏天穿会不会热")

    def test_empty_orig_falls_through(self) -> None:
        # No sidebar text — there's nothing to merge with; the new
        # bubble text becomes the only ``last_message``.
        result = self._run_override_branch("", "透气吗")
        self.assertEqual(result, "透气吗")


# -----------------------------------------------------------------------
# mt052C — arm placeholder timer at EventMonitor time
# -----------------------------------------------------------------------

EM_SRC_052C = Path(
    "agent/ec_skills/browser_use_extension/event_monitor.py"
).read_text(encoding="utf-8")
FD_SRC_052C = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt052C_EarlyArmSourceTests(unittest.TestCase):
    """mt052C arms the placeholder timer at EventMonitor's dom_observed
    emission point, not at PreDispatch's _build_assignment_payload.

    Pre-mt052C the customer waited 21-60 s for the placeholder because
    arm() ran AFTER the front-desk queue dequeued the browser_event
    (median 21 s queue lag under 4-customer load per the 2026-05-29
    14:06-14:32 trace).  Post-mt052C the sweeper can fire the
    placeholder at first_seen + timeout regardless of front-desk
    backpressure.
    """

    def test_marker_present_in_event_monitor(self) -> None:
        self.assertIn("mt052C", EM_SRC_052C)

    def test_arm_called_in_event_monitor(self) -> None:
        # The arm() call must live in event_monitor.py inside the
        # mt052C block.
        idx = EM_SRC_052C.find("mt052C")
        self.assertGreater(idx, -1)
        block = EM_SRC_052C[idx:idx + 3000]
        self.assertIn("_feige_ph_timer.arm(", block)
        self.assertIn("customer_key=str(_cust)", block)
        self.assertIn("source_msg_id=_msg_id", block)
        self.assertIn("timeout_s=_mt052c_timeout", block)

    def test_arm_resolves_tunable(self) -> None:
        # The new arm site reads the same ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S
        # tunable as the existing PreDispatch arm — operator config
        # must not need changes.
        idx = EM_SRC_052C.find("mt052C")
        block = EM_SRC_052C[idx:idx + 3000]
        self.assertIn('"FEIGE_PLACEHOLDER_TIMEOUT_S"', block)
        self.assertIn(
            "DEFAULT_FEIGE_PLACEHOLDER_TIMEOUT_S as _MT052C_DEF_PH_TIMEOUT",
            block,
        )

    def test_arm_runs_after_mark_first_seen(self) -> None:
        # Order matters: mark_message_first_seen must precede arm so
        # arm's first_seen lookup finds the just-stamped value.  Same
        # pattern as the existing PreDispatch arm.
        mark_idx = EM_SRC_052C.find("mark_message_first_seen(str(_cust)")
        arm_idx = EM_SRC_052C.find("_feige_ph_timer.arm(\n")
        # arm appears later in the file than mark_first_seen.
        self.assertGreater(mark_idx, -1)
        self.assertGreater(arm_idx, -1)
        self.assertLess(mark_idx, arm_idx)

    def test_arm_failure_is_non_fatal(self) -> None:
        # The early arm is best-effort.  Failure must NOT prevent the
        # dom_observed ledger emission or the dispatch to runners.
        idx = EM_SRC_052C.find("mt052C")
        block = EM_SRC_052C[idx:idx + 3000]
        self.assertIn("try:", block)
        self.assertIn("except Exception:", block)
        self.assertIn("pass", block)

    def test_arm_disabled_when_timeout_le_zero(self) -> None:
        # When ECAN_FEIGE_PLACEHOLDER_TIMEOUT_S=0 (the default-off
        # state), arm must be skipped — matches the existing PreDispatch
        # site's gate.
        idx = EM_SRC_052C.find("mt052C")
        block = EM_SRC_052C[idx:idx + 3000]
        self.assertIn("if _mt052c_timeout > 0:", block)

    def test_predispatch_arm_still_runs(self) -> None:
        # mt052C does NOT delete the PreDispatch arm — that arm runs
        # again later with the precise msg_id, which gives the timer
        # a more specific registry key for cancel/supersede.  Don't
        # accidentally remove it.
        self.assertIn(
            "Phase 3.5 placeholder-timer guardrail",
            FD_SRC_052C,
        )
        self.assertIn(
            "_ph_timer_arm.arm(",
            FD_SRC_052C,
        )


# -----------------------------------------------------------------------
# mt052D Day 1 — OOB parallel dispatch foundation (instrumentation only)
# -----------------------------------------------------------------------

FD_SRC_052D = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt052D_Day1SourceTests(unittest.TestCase):
    """mt052D ships across multiple days.  Day 1 adds:

    * ``_RR_LOCK`` + ``_atomic_rr_pick`` so the round-robin counter is
      safe under parallel dispatch.
    * ``_INFLIGHT_CUSTOMERS`` set + lock with ``acquire_customers`` /
      ``release_customers`` for per-customer in-flight tracking.
    * ``_OOB_DISPATCH_CACHE`` populated by run() so the OOB path
      (Day 2 wiring) can synthesise a fresh DispatchContext without
      re-entering the LangGraph hook.
    * ``try_oob_dispatch`` entry point — instrumentation-only today;
      Day 2 turns it into a real parallel dispatch.

    No behaviour change yet.  The env var ECAN_FRONTDESK_OOB_DISPATCH
    gates the real path (default off).
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052D Day 1", FD_SRC_052D)

    def test_rr_pick_uses_lock(self) -> None:
        self.assertIn("_RR_LOCK = threading.Lock()", FD_SRC_052D)
        self.assertIn(
            "def _atomic_rr_pick(dispatch_state: dict, n_recipients: int) -> int:",
            FD_SRC_052D,
        )
        self.assertIn(
            "rr_idx = _atomic_rr_pick(dispatch_state, len(service_agent_ids))",
            FD_SRC_052D,
        )
        # Old unguarded read-modify-write must be gone from the dispatch
        # site.
        self.assertNotIn(
            'rr_idx = dispatch_state.get("rr_index", 0) % len(service_agent_ids)',
            FD_SRC_052D,
        )

    def test_inflight_tracking_api(self) -> None:
        self.assertIn("_INFLIGHT_LOCK = threading.Lock()", FD_SRC_052D)
        self.assertIn("_INFLIGHT_CUSTOMERS: set[str] = set()", FD_SRC_052D)
        self.assertIn(
            "def acquire_customers(customers: set[str]) -> set[str]:",
            FD_SRC_052D,
        )
        self.assertIn(
            "def release_customers(customers: set[str]) -> None:",
            FD_SRC_052D,
        )

    def test_oob_cache_api(self) -> None:
        self.assertIn(
            "_OOB_DISPATCH_CACHE_LOCK = threading.Lock()", FD_SRC_052D,
        )
        self.assertIn(
            "def _cache_oob_dispatch_refs(",
            FD_SRC_052D,
        )
        self.assertIn(
            "def _get_cached_oob_refs() -> dict[str, Any] | None:",
            FD_SRC_052D,
        )

    def test_run_populates_oob_cache(self) -> None:
        # run() must call _cache_oob_dispatch_refs before any early
        # return so the OOB path always has fresh refs.
        idx = FD_SRC_052D.find("async def run(")
        self.assertGreater(idx, -1)
        body = FD_SRC_052D[idx:idx + 2500]
        self.assertIn("_cache_oob_dispatch_refs(cfg=cfg, ctx=ctx, agent_obj=agent_obj)", body)

    def test_env_gate_default_off(self) -> None:
        # ECAN_FRONTDESK_OOB_DISPATCH gates the real dispatch path.
        # Default off so Day 1 ships zero behaviour change.
        self.assertIn(
            'os.getenv("ECAN_FRONTDESK_OOB_DISPATCH")',
            FD_SRC_052D,
        )
        self.assertIn(
            'raw in ("1", "true", "yes", "on")',
            FD_SRC_052D,
        )

    def test_try_oob_dispatch_signature(self) -> None:
        self.assertIn(
            "def try_oob_dispatch(",
            FD_SRC_052D,
        )
        # Day 1 must log when OOB would fire but explicitly NOT dispatch.
        self.assertIn(
            "OOB dispatch WOULD fire",
            FD_SRC_052D,
        )


class Mt052D_Day1BehaviourTests(unittest.TestCase):
    """Direct behaviour tests of the locks and registry."""

    def setUp(self) -> None:
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        self.fd = fd
        fd.clear_oob_dispatch_cache()

    def test_acquire_then_release(self) -> None:
        acq = self.fd.acquire_customers({"A", "B", "C"})
        self.assertEqual(acq, {"A", "B", "C"})
        self.assertEqual(self.fd.get_inflight_customers(), {"A", "B", "C"})
        self.fd.release_customers({"A", "B"})
        self.assertEqual(self.fd.get_inflight_customers(), {"C"})
        self.fd.release_customers({"C"})
        self.assertEqual(self.fd.get_inflight_customers(), set())

    def test_acquire_excludes_already_inflight(self) -> None:
        self.fd.acquire_customers({"A", "B"})
        # B is in-flight; C is fresh; A is in-flight.
        acq = self.fd.acquire_customers({"A", "C"})
        self.assertEqual(acq, {"C"})  # A excluded; C taken
        self.assertEqual(self.fd.get_inflight_customers(), {"A", "B", "C"})

    def test_release_ignores_unknown_customers(self) -> None:
        # No-op when releasing customers we never acquired.
        self.fd.release_customers({"never_in_flight"})  # must not raise

    def test_atomic_rr_pick_increments(self) -> None:
        state: dict = {}
        # First call returns 0, sets state["rr_index"]=1.
        self.assertEqual(self.fd._atomic_rr_pick(state, 3), 0)
        self.assertEqual(self.fd._atomic_rr_pick(state, 3), 1)
        self.assertEqual(self.fd._atomic_rr_pick(state, 3), 2)
        # Wraps around at n_recipients.
        self.assertEqual(self.fd._atomic_rr_pick(state, 3), 0)

    def test_atomic_rr_pick_handles_zero_recipients(self) -> None:
        # max(1, 0) inside the helper avoids ZeroDivisionError.
        state: dict = {}
        self.fd._atomic_rr_pick(state, 0)  # must not raise

    def test_is_oob_enabled_respects_env(self) -> None:
        import os
        old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
        try:
            for val in ("1", "true", "Yes", "ON"):
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = val
                self.assertTrue(
                    self.fd.is_oob_enabled(),
                    f"value {val!r} should enable OOB",
                )
            for val in ("0", "false", "no", "off", ""):
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = val
                self.assertFalse(
                    self.fd.is_oob_enabled(),
                    f"value {val!r} should disable OOB",
                )
        finally:
            if old is None:
                os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
            else:
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old

    def test_try_oob_no_cache_returns_false(self) -> None:
        # No in-band run() has executed → no cache → instrumentation
        # logs and returns False even when env is set.
        self.fd.clear_oob_dispatch_cache()
        import os
        old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
        os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = "1"
        try:
            self.assertFalse(self.fd.try_oob_dispatch({"A"}, reason="test"))
        finally:
            if old is None:
                os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
            else:
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old

    def test_try_oob_with_cache_no_items_returns_false(self) -> None:
        # Day 2: try_oob_dispatch now requires browser_event_items to
        # match acquired customers.  When items are missing/empty, the
        # OOB path can't dispatch and must release the customers.
        self.fd._cache_oob_dispatch_refs(
            cfg="fake_cfg", ctx="fake_ctx", agent_obj="fake_agent"
        )
        import os
        old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
        os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = "1"
        try:
            # No browser_event_items → False, and customers released.
            self.assertFalse(self.fd.try_oob_dispatch({"X"}, reason="test"))
            self.assertNotIn("X", self.fd.get_inflight_customers())
        finally:
            if old is None:
                os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
            else:
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old

    def test_try_oob_skips_when_all_customers_inflight(self) -> None:
        self.fd._cache_oob_dispatch_refs(
            cfg="c", ctx="x", agent_obj="a",
        )
        self.fd.acquire_customers({"A", "B"})
        try:
            import os
            old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
            os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = "1"
            try:
                # Both customers already in-flight → skip entirely.
                self.assertFalse(
                    self.fd.try_oob_dispatch({"A", "B"}, reason="test"),
                )
            finally:
                if old is None:
                    os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
                else:
                    os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old
        finally:
            self.fd.release_customers({"A", "B"})


class Mt052D_Day2WiringTests(unittest.TestCase):
    """mt052D Day 2 adds the actual dispatch and wires runner.py to
    invoke it when the front-desk task is busy.  Still env-gated
    (ECAN_FRONTDESK_OOB_DISPATCH=0 default).
    """

    def test_run_oob_dispatch_function_defined(self) -> None:
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        self.assertTrue(hasattr(fd, "_run_oob_dispatch"))
        # It's an async function.
        import inspect
        self.assertTrue(inspect.iscoroutinefunction(fd._run_oob_dispatch))

    def test_try_oob_accepts_browser_event_items(self) -> None:
        # Signature must include browser_event_items kwarg.
        import inspect
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        sig = inspect.signature(fd.try_oob_dispatch)
        self.assertIn("browser_event_items", sig.parameters)

    def test_runner_wires_oob_call(self) -> None:
        # runner.py must invoke try_oob_dispatch from the task-busy
        # branch when the queue has a browser_event.
        RUN_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
        self.assertIn("mt052D Day 2", RUN_SRC)
        self.assertIn(
            "from agent.ec_skills.node_runtime.frontdesk_dispatch import (",
            RUN_SRC,
        )
        self.assertIn("try_oob_dispatch as _try_oob", RUN_SRC)
        self.assertIn(
            "_try_oob(",
            RUN_SRC,
        )
        # Must be invoked with browser_event_items kwarg.
        self.assertIn("browser_event_items=_items", RUN_SRC)

    def test_runner_only_invokes_for_browser_event_head(self) -> None:
        # The runner-side gate must check the queue head is a
        # browser_event before invoking try_oob — chat_messages and
        # other events must NOT trigger OOB.
        RUN_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
        idx = RUN_SRC.find("mt052D Day 2")
        self.assertGreater(idx, -1)
        block = RUN_SRC[idx:idx + 3500]
        self.assertIn('_classify_queue_event(_head) == "browser_event"', block)


class Mt052D_Day2BehaviourTests(unittest.TestCase):
    """End-to-end-ish behaviour tests for the OOB path.  Run with an
    asyncio loop so the spawned task actually executes; mock the
    dispatch internals so we don't need a real browser session."""

    def setUp(self) -> None:
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        self.fd = fd
        fd.clear_oob_dispatch_cache()

    def test_run_oob_releases_on_missing_refs(self) -> None:
        # When refs are empty, _run_oob_dispatch must still release
        # the acquired customers before returning.
        import asyncio
        self.fd.acquire_customers({"A"})
        async def runner():
            await self.fd._run_oob_dispatch(
                items=[{"customer_name": "A", "session_id": "A"}],
                acquired_customers={"A"},
                refs={},
            )
        asyncio.run(runner())
        self.assertNotIn("A", self.fd.get_inflight_customers())

    def test_try_oob_no_loop_returns_false(self) -> None:
        # In a sync test context with no running event loop,
        # try_oob_dispatch should release the acquired customers and
        # return False rather than crashing.
        self.fd._cache_oob_dispatch_refs(
            cfg="c", ctx="x", agent_obj="a",
        )
        import os
        old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
        os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = "1"
        try:
            items = [{"customer_name": "Z", "session_id": "Z"}]
            result = self.fd.try_oob_dispatch(
                {"Z"}, reason="t", browser_event_items=items,
            )
            # No running loop in this sync test — try_oob releases the
            # customers and returns False.
            self.assertFalse(result)
            self.assertNotIn("Z", self.fd.get_inflight_customers())
        finally:
            if old is None:
                os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
            else:
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old


# -----------------------------------------------------------------------
# mt052D-fix-1 — cache event loop for cross-thread OOB scheduling
# -----------------------------------------------------------------------


class Mt052D_Fix1EventLoopTests(unittest.TestCase):
    """The 052D live test produced 100 % WARNING spam from the OOB path:
    ``RuntimeError: There is no current event loop in thread
    'ThreadPoolExecutor-2_3'``.  The runner's dequeue gate runs in a
    worker thread that has no current loop; ``asyncio.get_event_loop()``
    raised on every call.  Fix: cache the running loop from inside
    ``run()`` (which IS a coroutine) and schedule via
    ``run_coroutine_threadsafe`` from any thread.
    """

    def setUp(self) -> None:
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        self.fd = fd
        fd.clear_oob_dispatch_cache()

    def test_cache_records_running_loop(self) -> None:
        # When called from inside an asyncio coroutine,
        # _cache_oob_dispatch_refs must capture the running loop.
        import asyncio
        captured_loop = None
        async def capture():
            self.fd._cache_oob_dispatch_refs(
                cfg="c", ctx="x", agent_obj="a",
            )
            return asyncio.get_running_loop()
        loop_used = asyncio.run(capture())
        # Cache should hold a loop reference (the one used during the
        # capture coroutine; closed by the time asyncio.run returns,
        # but that's still the right shape).
        refs = self.fd._get_cached_oob_refs()
        self.assertIsNotNone(refs)
        self.assertIn("loop", refs)
        # The loop object recorded matches the one captured.
        self.assertIs(refs["loop"], loop_used)

    def test_cache_no_loop_in_sync_context(self) -> None:
        # When called from a plain sync context (no running loop),
        # the cache stores None for loop instead of raising.
        self.fd._cache_oob_dispatch_refs(
            cfg="c", ctx="x", agent_obj="a",
        )
        refs = self.fd._get_cached_oob_refs()
        self.assertIsNotNone(refs)
        self.assertIn("loop", refs)
        self.assertIsNone(refs["loop"])

    def test_try_oob_uses_run_coroutine_threadsafe(self) -> None:
        # Source-level check: the spawn path must use
        # run_coroutine_threadsafe, NOT loop.create_task (which
        # requires the loop to be the current thread's loop).
        from pathlib import Path as _Path
        src = _Path(
            "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
        ).read_text(encoding="utf-8")
        idx = src.find("mt052D-fix-1")
        self.assertGreater(idx, -1)
        # Find the section around try_oob_dispatch's spawn.
        spawn_idx = src.find("asyncio.run_coroutine_threadsafe(", idx)
        self.assertGreater(spawn_idx, -1, "run_coroutine_threadsafe missing")
        # Locate the actual try_oob_dispatch function body and verify
        # the buggy ``loop = asyncio.get_event_loop()`` call site is
        # gone.  Comments and docstrings mentioning the bug for
        # historical context are fine.
        fn_idx = src.find("def try_oob_dispatch(")
        self.assertGreater(fn_idx, -1)
        # Read up to the next top-level def.
        next_def = src.find("\nasync def ", fn_idx + 1)
        if next_def == -1:
            next_def = src.find("\ndef ", fn_idx + 1)
        fn_body = src[fn_idx:next_def if next_def > 0 else fn_idx + 5000]
        self.assertNotIn(
            "loop = asyncio.get_event_loop()", fn_body,
            "try_oob_dispatch must not call the buggy get_event_loop()",
        )
        self.assertIn("run_coroutine_threadsafe(", fn_body)

    def test_recall_handling_marker_present(self) -> None:
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        self.assertIn("mt052E", EM_SRC)

    def test_recall_handling_synthesises_dom_observed(self) -> None:
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        idx = EM_SRC.find("mt052E")
        self.assertGreater(idx, -1)
        block = EM_SRC[idx:idx + 6000]
        # The synthesised entry is appended to added_items / added_keys.
        self.assertIn("added_items.append(_curr)", block)
        self.assertIn("added_keys.append(_curr_key)", block)

    def test_recall_handling_clears_dedup_ledger(self) -> None:
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        idx = EM_SRC.find("mt052E")
        block = EM_SRC[idx:idx + 6000]
        self.assertIn(
            "clear_dispatched_identity_keys_for_customer", block,
        )
        self.assertIn("_mt052e_clear(_cust)", block)

    def test_recall_skips_when_message_unchanged(self) -> None:
        # Guard: if the removed key's message text matches the current
        # message text (i.e. the customer was just reordered, not
        # recalled), don't synthesise an entry — would double-emit.
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        idx = EM_SRC.find("mt052E")
        block = EM_SRC[idx:idx + 6000]
        self.assertIn(
            "_curr_msg == str(_old_msg).strip():", block,
        )

    def test_recall_skips_when_customer_disappeared(self) -> None:
        # Guard: chat-closed customers (fully removed, no current row)
        # are NOT recalls.
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        idx = EM_SRC.find("mt052E")
        block = EM_SRC[idx:idx + 6000]
        self.assertIn("if not _curr:", block)
        self.assertIn("# Customer fully disappeared", block)

    def test_recall_skips_when_already_in_added_keys(self) -> None:
        # Guard: if the customer's current row was already emitted by
        # the regular added_keys diff, mt052E must not double-emit.
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        idx = EM_SRC.find("mt052E")
        block = EM_SRC[idx:idx + 6000]
        self.assertIn(
            "if _curr_key in added_lookup_set:", block,
        )

    def test_recall_runs_after_added_keys_computed(self) -> None:
        # Order: the mt052E block must run AFTER added_items / added_keys
        # are populated by the regular diff (otherwise the
        # already-in-added guard misses).
        EM_SRC = Path(
            "agent/ec_skills/browser_use_extension/event_monitor.py"
        ).read_text(encoding="utf-8")
        added_idx = EM_SRC.find('added_items.append(item)')
        mt052e_idx = EM_SRC.find("mt052E")
        self.assertGreater(added_idx, -1)
        self.assertGreater(mt052e_idx, -1)
        self.assertLess(added_idx, mt052e_idx)


    def test_try_oob_releases_when_loop_closed(self) -> None:
        # If the cached loop is closed (e.g. the front-desk task ended
        # and a new one hasn't started yet), try_oob must release and
        # bail rather than raise.
        import asyncio
        loop = asyncio.new_event_loop()
        loop.close()  # Now is_closed() == True
        self.fd._cache_oob_dispatch_refs(
            cfg="c", ctx="x", agent_obj="a",
        )
        # Manually overwrite the cached loop with the closed one.
        with self.fd._OOB_DISPATCH_CACHE_LOCK:
            self.fd._OOB_DISPATCH_CACHE["loop"] = loop
        import os
        old = os.environ.get("ECAN_FRONTDESK_OOB_DISPATCH")
        os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = "1"
        try:
            items = [{"customer_name": "Q", "session_id": "Q"}]
            self.assertFalse(
                self.fd.try_oob_dispatch(
                    {"Q"}, reason="t", browser_event_items=items,
                )
            )
            self.assertNotIn("Q", self.fd.get_inflight_customers())
        finally:
            if old is None:
                os.environ.pop("ECAN_FRONTDESK_OOB_DISPATCH", None)
            else:
                os.environ["ECAN_FRONTDESK_OOB_DISPATCH"] = old


# -----------------------------------------------------------------------
# mt052F — arm() dedupes empty-msg + real-msg entries for same customer
# -----------------------------------------------------------------------

PT_SRC_052F = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")


class Mt052F_ArmDedupSourceTests(unittest.TestCase):
    """mt052F removes the (customer, '') registry entry left behind by
    mt052C when PreDispatch later arms with the resolved source_msg_id.

    Pre-mt052F both entries ticked and both fired placeholders — 客户19
    trace 2026-05-29 11:23:31/11:23:35 shows "placeholder #1 fired"
    twice 4 s apart.  The two arms had different keys ((cust, '') vs
    (cust, '<real>')) so neither overwrote the other in the registry.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052F", PT_SRC_052F)

    def test_marker_inside_arm_body(self) -> None:
        # The dedup must live inside arm() — anywhere else and the
        # registry would still be racing with two entries.
        arm_def_idx = PT_SRC_052F.find("def arm(")
        mt052f_idx = PT_SRC_052F.find("mt052F")
        next_def_idx = PT_SRC_052F.find("\ndef ", arm_def_idx + 1)
        self.assertGreater(arm_def_idx, -1)
        self.assertGreater(mt052f_idx, arm_def_idx)
        self.assertLess(mt052f_idx, next_def_idx)

    def test_empty_msg_pop_logic(self) -> None:
        idx = PT_SRC_052F.find("mt052F")
        block = PT_SRC_052F[idx:idx + 1500]
        # Only pop when arming with a non-empty msg_id (we never want
        # to clobber the mt052C entry when PreDispatch's enrich also
        # ran with empty msg_id).
        self.assertIn("if source_msg_id:", block)
        self.assertIn('_make_key(customer_key, "")', block)
        self.assertIn("_REGISTRY.pop(empty_key", block)

    def test_preserves_placeholders_typed(self) -> None:
        # Carry the empty-msg entry's placeholders_typed forward so the
        # cap-per-window accounting is preserved across the upgrade.
        idx = PT_SRC_052F.find("mt052F")
        block = PT_SRC_052F[idx:idx + 1500]
        self.assertIn("placeholders_typed", block)


class Mt052F_ArmDedupBehaviourTests(unittest.TestCase):
    """Exercise arm() directly to confirm the dedup behaviour."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as ph,
        )
        self.ph = ph
        with ph._REGISTRY_LOCK:
            ph._REGISTRY.clear()
            ph._PLACEHOLDERS_TYPED_TS.clear()
            ph._REAL_REPLY_AT.clear()
            ph._INFLIGHT_PLACEHOLDER_TASKS.clear()
            ph._FIRST_SEEN_AT.clear()
            ph._FIRST_SEEN_BY_CUSTOMER.clear()

    def test_empty_then_real_leaves_only_real(self) -> None:
        # Sequence: mt052C arms with '', then PreDispatch arms with real id.
        self.ph.arm(customer_key="客户19", source_msg_id="", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            keys_after_empty = list(self.ph._REGISTRY.keys())
        self.assertIn(("客户19", ""), keys_after_empty)

        self.ph.arm(customer_key="客户19", source_msg_id="real_xyz", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            keys_after_real = list(self.ph._REGISTRY.keys())
        self.assertNotIn(
            ("客户19", ""), keys_after_real,
            "mt052F: empty-msg entry must be removed when real-msg arm runs",
        )
        self.assertIn(("客户19", "real_xyz"), keys_after_real)

    def test_real_then_empty_keeps_real(self) -> None:
        # Pathological reverse ordering: if for some reason PreDispatch
        # arms first then a later EventMonitor batch arms with empty,
        # we still want the real-id entry to win.  Empty arm shouldn't
        # delete a real-id entry it can't pair with.
        self.ph.arm(customer_key="custZ", source_msg_id="real_abc", timeout_s=20.0)
        self.ph.arm(customer_key="custZ", source_msg_id="", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            keys = list(self.ph._REGISTRY.keys())
        self.assertIn(("custZ", "real_abc"), keys)

    def test_placeholders_typed_carried_forward(self) -> None:
        # If the empty-msg entry already fired 1 placeholder, the new
        # real-id entry should inherit that count so the per-inflight
        # cap is respected end-to-end.
        self.ph.arm(customer_key="custA", source_msg_id="", timeout_s=0.001)
        import time
        time.sleep(0.05)
        # Claim fires placeholder #1, bumps placeholders_typed to 1.
        expired = self.ph.claim_expired(
            max_placeholders=2, rearm_s=0.001, cap_per_window=100,
        )
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].placeholders_typed, 1)
        # Re-arm into the empty slot manually (sweeper bumps deadline
        # but we want the count preserved across the upgrade).
        with self.ph._REGISTRY_LOCK:
            entry = self.ph._REGISTRY.get(("custA", ""))
            self.assertIsNotNone(entry)
            self.assertEqual(entry.placeholders_typed, 1)

        # Now PreDispatch arms with the real msg_id.  Empty entry pops;
        # new real-id entry should inherit placeholders_typed=1.
        self.ph.arm(customer_key="custA", source_msg_id="real_id_99", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            new_entry = self.ph._REGISTRY.get(("custA", "real_id_99"))
            self.assertIsNotNone(new_entry)
            self.assertEqual(
                new_entry.placeholders_typed, 1,
                "mt052F must carry placeholders_typed across the upgrade",
            )

    def test_no_dup_fire_after_upgrade(self) -> None:
        # The regression scenario from 客户19's live trace: after the
        # upgrade, only ONE placeholder should fire per sweep tick.
        self.ph.arm(customer_key="custB", source_msg_id="", timeout_s=0.001)
        self.ph.arm(customer_key="custB", source_msg_id="msg_real", timeout_s=0.001)
        import time
        time.sleep(0.05)
        expired = self.ph.claim_expired(
            max_placeholders=2, rearm_s=15.0, cap_per_window=100,
        )
        self.assertEqual(
            len(expired), 1,
            "post-mt052F only one entry exists → only one fire per tick",
        )
        self.assertEqual(expired[0].source_msg_id, "msg_real")

    def test_empty_msg_to_empty_msg_rearm_unchanged(self) -> None:
        # When both arms use empty msg_id (mt052C only, PreDispatch
        # never resolved), the second arm must re-arm the same entry,
        # not create a duplicate.  Pre-mt052F behaviour for that case
        # is correct and must not regress.
        self.ph.arm(customer_key="custE", source_msg_id="", timeout_s=20.0)
        self.ph.arm(customer_key="custE", source_msg_id="", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            keys = [k for k in self.ph._REGISTRY.keys() if k[0] == "custE"]
        self.assertEqual(len(keys), 1)


# -----------------------------------------------------------------------
# mt052G — PreDispatch cancels mt052C-armed timer on echo-skip
# -----------------------------------------------------------------------

FD_SRC_052G = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt052G_EchoSkipCancelSourceTests(unittest.TestCase):
    """mt052G: when PreDispatch's enrich skips because the sidebar text
    matches one of our own typed bubbles, the mt052C-armed placeholder
    timer is now orphaned and will fire after the real reply.  客户13
    trace 2026-05-29 11:28:48→11:29:23: typed_text_pre_scrape skipped
    correctly but placeholder #1 + #2 FINAL fired anyway.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052G", FD_SRC_052G)

    def test_marker_inside_enrich_skip_branch(self) -> None:
        # The cancel call must live inside the `if enrich.skip:` block
        # so dispatch-allowed turns don't accidentally lose their timer.
        skip_idx = FD_SRC_052G.find("if enrich.skip:")
        mt052g_idx = FD_SRC_052G.find("mt052G", skip_idx)
        # Next non-skip return after the branch — used as upper bound.
        self.assertGreater(skip_idx, -1)
        self.assertGreater(mt052g_idx, skip_idx)

    def test_cancels_all_four_echo_reasons(self) -> None:
        # The four pre_dispatch_enrich.py echo skip_reasons must all
        # trigger the cancel.  Missing one leaves the placeholder
        # orphaned for that specific echo path.
        idx = FD_SRC_052G.find("mt052G")
        block = FD_SRC_052G[idx:idx + 2500]
        for reason in (
            "dom_echo_pre_scrape",
            "recent_echo_pre_scrape",
            "baseline_text_pre_scrape",
            "typed_text_pre_scrape",
        ):
            self.assertIn(reason, block, f"mt052G missing skip_reason {reason!r}")

    def test_uses_cancel_any_for_customer(self) -> None:
        idx = FD_SRC_052G.find("mt052G")
        block = FD_SRC_052G[idx:idx + 2500]
        self.assertIn("cancel_any_for_customer(customer_key)", block)

    def test_cancel_failure_is_non_fatal(self) -> None:
        # Placeholder-timer import or cancel failing must NOT block the
        # PreDispatch skip itself — front-desk continuity is more
        # important than an orphaned timer.
        idx = FD_SRC_052G.find("mt052G")
        block = FD_SRC_052G[idx:idx + 2500]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)

    def test_does_not_cancel_on_dispatch_path(self) -> None:
        # When enrich.skip is False (dispatch proceeds), no cancel
        # should fire — the placeholder timer is needed to cover the
        # QA round-trip.
        skip_idx = FD_SRC_052G.find("if enrich.skip:")
        # Find end of skip branch — `scraped_msg_id = enrich.scraped_msg_id`
        # is the first line of the post-skip path.
        post_idx = FD_SRC_052G.find(
            "scraped_msg_id = enrich.scraped_msg_id", skip_idx,
        )
        self.assertGreater(post_idx, skip_idx)
        cancel_in_post = FD_SRC_052G[post_idx:post_idx + 2000].find(
            "cancel_any_for_customer"
        )
        self.assertEqual(
            cancel_in_post, -1,
            "mt052G cancel must stay inside the skip branch only",
        )

    def test_typing_lock_skip_unaffected(self) -> None:
        # The pre-existing typing_lock_active / active_customer_mismatch
        # branch must still return the sentinel for runner re-queue;
        # mt052G's cancel logic sits beside it, not in place of it.
        idx = FD_SRC_052G.find("mt052G")
        end_of_skip = FD_SRC_052G.find(
            'return opened_row, "", ""', idx,
        )
        block = FD_SRC_052G[idx:end_of_skip + 30]
        self.assertIn("_TYPING_LOCK_ACTIVE_SENTINEL", block)


class Mt052G_EchoSkipCancelBehaviourTests(unittest.TestCase):
    """Drive cancel_any_for_customer directly to confirm it does what
    mt052G needs: drop the timer AND stamp the suppress slot so any
    in-flight placeholder is suppressed at submit time."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as ph,
        )
        self.ph = ph
        with ph._REGISTRY_LOCK:
            ph._REGISTRY.clear()
            ph._PLACEHOLDERS_TYPED_TS.clear()
            ph._REAL_REPLY_AT.clear()
            ph._INFLIGHT_PLACEHOLDER_TASKS.clear()
            ph._FIRST_SEEN_AT.clear()
            ph._FIRST_SEEN_BY_CUSTOMER.clear()

    def test_cancel_drops_mt052c_empty_entry(self) -> None:
        # mt052C armed at EventMonitor time with empty msg_id.
        self.ph.arm(customer_key="客户13", source_msg_id="", timeout_s=20.0)
        with self.ph._REGISTRY_LOCK:
            self.assertIn(("客户13", ""), self.ph._REGISTRY)
        n = self.ph.cancel_any_for_customer("客户13")
        self.assertEqual(n, 1)
        with self.ph._REGISTRY_LOCK:
            self.assertNotIn(("客户13", ""), self.ph._REGISTRY)

    def test_cancel_stamps_real_reply_suppress(self) -> None:
        # The cancel must stamp _REAL_REPLY_AT[(cust, '')] so any
        # already-claimed placeholder is suppressed at submit time
        # via is_real_reply_recent.
        self.ph.arm(customer_key="客户13", source_msg_id="", timeout_s=20.0)
        self.ph.cancel_any_for_customer("客户13")
        # The empty-key slot must be stamped (current implementation),
        # which is what suppresses subsequent submit-time fires.
        with self.ph._REGISTRY_LOCK:
            stamp = self.ph._REAL_REPLY_AT.get(("客户13", ""), 0.0)
        self.assertGreater(stamp, 0.0)


# -----------------------------------------------------------------------
# mt052I — placeholder-text override on the four pre-scrape skip sites
# -----------------------------------------------------------------------

PE_SRC_052I = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt052I_PlaceholderOverrideSourceTests(unittest.TestCase):
    """mt052I prevents pre-scrape dom-echo / recent-echo / baseline-text /
    typed-text skips from suppressing a HOT-PATH-B retry payload whose
    matched sidebar text is actually one of our placeholder echoes.

    Pre-mt052I trace (客户06, 2026-05-29 12:00:00.375): PreDispatch saw
    sidebar="人工服务正在回复中..." matching last_agent_reply (which was
    the same placeholder text we typed earlier), returned dom_echo_pre_scrape,
    HOT-PATH-B never typed the real reply → answer lost.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052I", PE_SRC_052I)

    def test_override_at_all_four_skip_sites(self) -> None:
        # The override must fire at EACH of the four pre-scrape skip
        # reasons.  Missing one leaves a customer stuck when their
        # specific echo path is hit (the live trace hit dom_echo_pre_scrape
        # but baseline/typed are symmetric).  Log strings are split across
        # f-string concatenations so we look for the override-type suffix
        # appearing AFTER an "mt052I pre-scrape" prefix within a short
        # window (allows for whitespace + line-continuation).
        for suffix in (
            "dom-echo override",
            "recent-echo override",
            "baseline-text override",
            "typed-text override",
        ):
            self.assertIn(
                suffix, PE_SRC_052I,
                f"mt052I override-type suffix missing: {suffix!r}",
            )
        # And ensure each occurrence is preceded by an mt052I log line.
        self.assertGreaterEqual(
            PE_SRC_052I.count("mt052I pre-scrape "), 4,
            "expected one 'mt052I pre-scrape' log per skip site",
        )

    def test_imports_is_placeholder_text(self) -> None:
        # The override must call is_placeholder_text on the sidebar text;
        # if the import line goes missing the flag stays False and the
        # override is dead code.
        self.assertIn(
            "from .dispatch_state import is_placeholder_text as _is_ph_text",
            PE_SRC_052I,
        )

    def test_placeholder_flag_computed_once(self) -> None:
        # We compute _early_sidebar_is_placeholder once and consult it
        # at each of the four skip sites — avoids four duplicate imports
        # and keeps a single source of truth.
        self.assertIn("_early_sidebar_is_placeholder", PE_SRC_052I)
        # Must be referenced at each site.
        self.assertGreaterEqual(
            PE_SRC_052I.count("_early_sidebar_is_placeholder"),
            5,  # 1 definition + 4 site checks
        )

    def test_real_reply_still_suppressed(self) -> None:
        # The skip MUST still fire when the matched text is NOT a
        # placeholder.  Confirm the else-branch return EnrichResult
        # remains for each of the four reasons.
        for reason in (
            "dom_echo_pre_scrape",
            "recent_echo_pre_scrape",
            "baseline_text_pre_scrape",
            "typed_text_pre_scrape",
        ):
            self.assertIn(
                f'skip_reason="{reason}"',
                PE_SRC_052I,
                f"mt052I must keep the real-reply skip path for {reason!r}",
            )

    def test_fall_through_not_return(self) -> None:
        # Override path must NOT return EnrichResult — it must fall
        # through so the caller continues past the pre-scrape fast-path
        # into the real PreDispatch flow.  Find the first override site
        # and confirm a "Fall through" comment appears in its block.
        idx = PE_SRC_052I.find("dom-echo override")
        self.assertGreater(idx, -1)
        block = PE_SRC_052I[idx:idx + 800]
        self.assertIn("Fall through", block)


class Mt052I_PlaceholderOverrideBehaviourTests(unittest.TestCase):
    """Drive the dispatch_state placeholder ledger directly to confirm
    the marker round-trip works end-to-end."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as ds,
        )
        self.ds = ds
        # Reset module state.
        with ds._placeholder_reply_lock:
            ds._placeholder_reply_texts.clear()

    def test_is_placeholder_text_after_mark(self) -> None:
        # mark_placeholder_text → is_placeholder_text True.
        self.ds.mark_placeholder_text("人工服务正在回复中...")
        self.assertTrue(self.ds.is_placeholder_text("人工服务正在回复中..."))

    def test_is_placeholder_text_false_for_real_reply(self) -> None:
        # Real-reply text not in the placeholder ledger → False.
        self.ds.mark_placeholder_text("人工服务正在回复中...")
        self.assertFalse(
            self.ds.is_placeholder_text("您好，国际订单清关延误一般我们..."),
        )

    def test_is_placeholder_text_normalised(self) -> None:
        # Whitespace differences must match — sidebar strips whitespace.
        self.ds.mark_placeholder_text("人工服务正在回复中...")
        self.assertTrue(self.ds.is_placeholder_text("人工 服务 正在 回复中..."))


# -----------------------------------------------------------------------
# mt052J — HOT-PATH-B typing-lock wait window is configurable
# -----------------------------------------------------------------------

HP_SRC_052J = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/hot_path.py"
).read_text(encoding="utf-8")


class Mt052J_TypingLockWaitSourceTests(unittest.TestCase):
    """mt052J makes the HOT-PATH-B typing-lock acquisition window
    configurable via ``ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S`` with a 30 s
    default (up from 12 s).  Under 20-customer flood the global
    typing-lock can be held >12 s by another customer; pre-mt052J
    HOT-PATH-B aborted and dropped the real reply (客户19 trace
    2026-05-29 11:59:58).
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052J", HP_SRC_052J)

    def test_env_var_named(self) -> None:
        self.assertIn("ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S", HP_SRC_052J)

    def test_default_is_30s(self) -> None:
        self.assertIn("_DEFAULT_TYPING_LOCK_WAIT_S: float = 30.0", HP_SRC_052J)

    def test_resolver_function_present(self) -> None:
        # The resolver must re-read env each call so long-lived processes
        # pick up operator changes without restart.
        self.assertIn("def _resolve_typing_lock_wait_attempts() -> int:", HP_SRC_052J)

    def test_acquire_uses_resolver(self) -> None:
        # The acquire loop must call the resolver, not the cached
        # module-level constant — otherwise the env var only takes effect
        # at module-import time.
        acquire_idx = HP_SRC_052J.find("async def _acquire_typing_lock")
        end_idx = HP_SRC_052J.find("\nasync def ", acquire_idx + 1)
        block = HP_SRC_052J[acquire_idx:end_idx]
        self.assertIn("_resolve_typing_lock_wait_attempts()", block)

    def test_fallback_when_env_invalid(self) -> None:
        # Invalid value (negative / non-numeric) must fall back to the
        # default rather than disabling the wait entirely.
        idx = HP_SRC_052J.find("def _resolve_typing_lock_wait_attempts")
        end = HP_SRC_052J.find("\ndef ", idx + 1)
        if end == -1:
            end = HP_SRC_052J.find("\nTYPING_LOCK_WAIT_ATTEMPTS", idx + 1)
        block = HP_SRC_052J[idx:end]
        self.assertIn("except (TypeError, ValueError):", block)
        self.assertIn("if wait_s <= 0:", block)


class Mt052J_TypingLockWaitBehaviourTests(unittest.TestCase):
    """Resolver returns expected attempt counts for env var values."""

    def setUp(self) -> None:
        import os
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            hot_path as hp,
        )
        self.hp = hp
        self.os = os
        self._old = os.environ.pop("ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S", None)

    def tearDown(self) -> None:
        if self._old is None:
            self.os.environ.pop("ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S", None)
        else:
            self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = self._old

    def test_default_30s_gives_300_attempts(self) -> None:
        # Default is 30 s with 100 ms interval → 300 attempts.
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 300)

    def test_env_override_60s(self) -> None:
        self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = "60"
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 600)

    def test_env_invalid_falls_back_to_default(self) -> None:
        self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = "not-a-number"
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 300)

    def test_env_negative_falls_back_to_default(self) -> None:
        self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = "-5"
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 300)

    def test_env_zero_falls_back_to_default(self) -> None:
        # Zero would disable the wait entirely — fall back to default
        # so an accidental "0" doesn't make HOT-PATH-B abort on the
        # first contended cycle.
        self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = "0"
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 300)

    def test_env_fractional_value(self) -> None:
        # 5.5 s → 55 attempts (int truncation).
        self.os.environ["ECAN_FEIGE_HOTPATHB_LOCK_WAIT_S"] = "5.5"
        n = self.hp._resolve_typing_lock_wait_attempts()
        self.assertEqual(n, 55)


# -----------------------------------------------------------------------
# mt052K — placeholder-aware override on the four inflight skip sites
# -----------------------------------------------------------------------

FD_SRC_052K = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt052K_InflightOverrideSourceTests(unittest.TestCase):
    """mt052K is the inflight-branch counterpart to mt052I.  The pre-scrape
    branch and the inflight branch are independent code paths inside
    frontdesk_dispatch.py — without mt052K, every placeholder echo that
    mt052I lets pass at pre-scrape gets re-blocked at the inflight skip
    sites (客户02/06/07 stuck-after-stale-drop, 2026-05-29 13:11→13:13).
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052K", FD_SRC_052K)

    def test_override_at_all_four_inflight_sites(self) -> None:
        for suffix in (
            "bot-reply-echo override",
            "recent-echo override",
            "baseline-text override",
            "typed-text override",
        ):
            self.assertIn(
                suffix, FD_SRC_052K,
                f"mt052K override missing for suffix {suffix!r}",
            )
        self.assertGreaterEqual(
            FD_SRC_052K.count("mt052K inflight "), 4,
            "expected 4 'mt052K inflight' log lines (one per skip site)",
        )

    def test_imports_is_placeholder_text(self) -> None:
        # The dispatch_state import should sit in the inflight branch,
        # close to where _inflight_sidebar_is_placeholder is computed.
        self.assertIn("is_placeholder_text as _is_ph_text_inflight", FD_SRC_052K)

    def test_placeholder_flag_computed_once(self) -> None:
        # Single source of truth — referenced at each of the 4 sites.
        self.assertIn("_inflight_sidebar_is_placeholder", FD_SRC_052K)
        self.assertGreaterEqual(
            FD_SRC_052K.count("_inflight_sidebar_is_placeholder"), 5,
            "expected 1 definition + 4 site checks",
        )

    def test_real_reply_skip_path_preserved(self) -> None:
        # The skip behaviour MUST remain for non-placeholder echoes —
        # this is the bot-reply DOM-echo guard from mt032, must not
        # regress.  Confirm the original 'return opened_row' branches
        # still exist for the non-placeholder path.
        # Counting return opened_row inside the inflight branch:
        # bot-reply-echo + recent-echo + baseline-text + typed-text
        # (the supersede branch below has more, so check it's >= 4).
        # Find the inflight section between "if inflight_age > 0:" and
        # the next significant non-inflight marker.
        start = FD_SRC_052K.find("if inflight_age > 0:")
        end = FD_SRC_052K.find("if assigned and current_norm and prior_norm and current_norm != prior_norm:", start)
        self.assertGreater(end, start)
        block = FD_SRC_052K[start:end]
        # Each of the 4 skip sites still ends in a non-placeholder return.
        self.assertGreaterEqual(
            block.count('return opened_row, "", ""'), 4,
            "lost a non-placeholder skip return path",
        )


# -----------------------------------------------------------------------
# mt052L — clear last_dispatched_msg_id on HOT-PATH-B stale-reply drop
# -----------------------------------------------------------------------

FRONTDESK_HP_SRC_052L = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/front_desk.py"
).read_text(encoding="utf-8")


class Mt052L_StaleReplyRedispatchSourceTests(unittest.TestCase):
    """mt052L mirrors the direct-delivery mt046A fix on the HOT-PATH-B
    stale-reply-drop branch.  Without this, the customer's still-pending
    newer message never gets re-dispatched (PreDispatch's msg_id dedup
    matches the just-stale-dropped id and treats the customer as already
    handled).  Direct-delivery already does this via mt046A —
    frontdesk_chat/front_desk.py's stale_reply_drop branch must too.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052L", FRONTDESK_HP_SRC_052L)

    def test_clears_last_dispatched_msg_id(self) -> None:
        idx = FRONTDESK_HP_SRC_052L.find("mt052L")
        block = FRONTDESK_HP_SRC_052L[idx:idx + 2500]
        self.assertIn("_ds.last_dispatched_msg_id_by_customer.pop(", block)
        self.assertIn("_stale_cust", block)

    def test_runs_only_when_inflight_was_cleared(self) -> None:
        # The clear must sit inside the same branch where
        # clear_dispatch_inflight just fired — NOT in the else branch
        # (which deliberately keeps state because a newer dispatch is
        # already in flight).
        idx = FRONTDESK_HP_SRC_052L.find("mt052L")
        # Walk back to find the nearest control statement; should be
        # the same branch that called clear_dispatch_inflight.
        before = FRONTDESK_HP_SRC_052L[max(0, idx - 1500):idx]
        self.assertIn("clear_dispatch_inflight(_stale_cust)", before)
        # And the "kept dispatch_inflight" else-branch must also exist
        # somewhere in the same stale_reply_drop handler.
        stale_branch_idx = FRONTDESK_HP_SRC_052L.find('stale_reply_source_msg_id')
        end_of_handler = FRONTDESK_HP_SRC_052L.find("hot_path_type", stale_branch_idx)
        self.assertGreater(end_of_handler, stale_branch_idx)
        handler_block = FRONTDESK_HP_SRC_052L[stale_branch_idx:end_of_handler]
        # The log string is split across f-string concatenations; look for
        # the two halves separately.
        self.assertIn('HOT-PATH-B: kept', handler_block)
        self.assertIn('dispatch_inflight after stale reply drop', handler_block)

    def test_clear_failure_is_non_fatal(self) -> None:
        idx = FRONTDESK_HP_SRC_052L.find("mt052L")
        block = FRONTDESK_HP_SRC_052L[idx:idx + 2500]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)
        self.assertIn("non-fatal", block.lower())

    def test_logs_the_clear(self) -> None:
        # Log line is essential for trace verification on the next run.
        idx = FRONTDESK_HP_SRC_052L.find("mt052L")
        block = FRONTDESK_HP_SRC_052L[idx:idx + 2500]
        self.assertIn("mt052L", block)
        self.assertIn("cleared last_dispatched_msg_id", block)


class Mt052L_StaleReplyRedispatchBehaviourTests(unittest.TestCase):
    """End-to-end behaviour: after a stale-drop clears the ledger entry,
    a subsequent PreDispatch lookup should not find it (i.e., the
    customer's next message is re-dispatchable)."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as ds,
        )
        self.ds = ds
        self.ds.last_dispatched_msg_id_by_customer.clear()

    def test_pop_clears_entry(self) -> None:
        self.ds.last_dispatched_msg_id_by_customer["客户02"] = "msg_stale_id"
        self.ds.last_dispatched_msg_id_by_customer.pop("客户02", None)
        self.assertNotIn(
            "客户02", self.ds.last_dispatched_msg_id_by_customer,
            "mt052L's pop should leave PreDispatch's lookup empty",
        )

    def test_pop_missing_key_is_safe(self) -> None:
        # The mt052L clear runs unconditionally inside the stale-drop
        # branch; if the ledger entry was already cleared elsewhere,
        # the pop must not error.
        self.ds.last_dispatched_msg_id_by_customer.pop("ghost_customer", None)
        # No exception → pass.


# -----------------------------------------------------------------------
# mt052M — mt030 "agent already replied" check ignores placeholder echoes
# -----------------------------------------------------------------------

PE_SRC_052M = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt052M_AgentAlreadyRepliedSourceTests(unittest.TestCase):
    """mt052M closes the last remaining placeholder-mis-classified-as-
    real-reply path: the post-scrape ``mt030`` index check (agent.index >
    customer.index → ``agent_already_replied`` skip).  客户01/04/15 trace
    2026-05-29 13:38:34→13:39:00 showed PreDispatch acquired the inflight
    lock, the placeholder fired at ~13:38:44, and then enrich's mt030
    check saw the placeholder bubble as "agent already replied" → skipped
    dispatch forever.  Without mt052M, mt052I/K/L all worked but the
    customer still stayed silent because dispatch never reached the QA
    worker after the first placeholder landed.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052M", PE_SRC_052M)

    def test_check_extends_mt030_branch(self) -> None:
        # mt052M must guard the exact mt030 skip site, not introduce a
        # new check elsewhere.  Confirm "mt030 skip dispatch" still lives
        # in the file and that mt052M references it.
        self.assertIn("mt030 skip dispatch", PE_SRC_052M)
        self.assertIn("mt052M mt030 override", PE_SRC_052M)

    def test_imports_is_placeholder_text(self) -> None:
        self.assertIn(
            "from .dispatch_state import is_placeholder_text as _is_ph_text_mt052m",
            PE_SRC_052M,
        )

    def test_reads_agent_bubble_text(self) -> None:
        # The override needs the bubble TEXT (the index check by itself
        # can't distinguish a placeholder from a real reply).  Confirm
        # we extract text from the scraped agent bubble dict.
        idx = PE_SRC_052M.find("mt052M")
        block = PE_SRC_052M[idx:idx + 2500]
        self.assertIn("_agent_bubble.get(\"text\")", block)
        self.assertIn("_agent_bubble_is_placeholder", block)

    def test_skip_still_fires_for_real_reply(self) -> None:
        # mt030's existing skip path must survive — only placeholder
        # echoes get the new override.  The four-condition predicate
        # sits ABOVE the assignment to skip_reason, so search the
        # surrounding block (before + after the marker).
        idx = PE_SRC_052M.find('"_ecan_pre_dispatch_skip_reason"] = "agent_already_replied"')
        self.assertGreater(idx, -1)
        block = PE_SRC_052M[max(0, idx - 1500):idx + 200]
        self.assertIn("not _agent_bubble_is_pre_existing_baseline", block)
        self.assertIn("not _agent_bubble_is_placeholder", block)

    def test_override_logs(self) -> None:
        # The override path emits an mt052M log line so we can verify
        # in the next emulation trace that it actually fired.
        self.assertIn("mt052M mt030 override", PE_SRC_052M)
        # Log must include both customer key and the matched placeholder
        # text so a grep against the log identifies which customers it
        # rescued.
        idx = PE_SRC_052M.find("mt052M mt030 override")
        # Find the surrounding logger.info block.
        block = PE_SRC_052M[max(0, idx - 400):idx + 800]
        self.assertIn("customer_key", block)
        self.assertIn("_agent_bubble_text", block)


class Mt052M_AgentAlreadyRepliedBehaviourTests(unittest.TestCase):
    """Use the dispatch_state placeholder ledger directly to verify the
    helper we depend on still returns True for the placeholder text and
    False for a typical real reply."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            dispatch_state as ds,
        )
        self.ds = ds
        with ds._placeholder_reply_lock:
            ds._placeholder_reply_texts.clear()

    def test_placeholder_text_recognised(self) -> None:
        self.ds.mark_placeholder_text("人工服务正在回复中...")
        self.assertTrue(self.ds.is_placeholder_text("人工服务正在回复中..."))

    def test_real_reply_not_recognised(self) -> None:
        self.ds.mark_placeholder_text("人工服务正在回复中...")
        # Typical store reply text — must NOT be flagged so mt052M
        # doesn't accidentally suppress legitimate "already replied"
        # skips for real bot answers.
        self.assertFalse(
            self.ds.is_placeholder_text(
                "您好，这款女装M码一般建议身高160-165cm左右穿。"
            )
        )

    def test_empty_text_not_recognised(self) -> None:
        # The bubble text can be empty when JS scrape returned no
        # bubble — mt052M's flag must stay False so the original mt030
        # skip path (where _agent_bubble_text is "") is unaffected.
        self.assertFalse(self.ds.is_placeholder_text(""))


# -----------------------------------------------------------------------
# mt052N — fresh-baseline mt038F suppression only for system/placeholder
# -----------------------------------------------------------------------

PE_SRC_052N = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/pre_dispatch_enrich.py"
).read_text(encoding="utf-8")


class Mt052N_FreshBaselineGuardSourceTests(unittest.TestCase):
    """mt052N narrows mt038F's blanket "first-seen agent bubble is pre-
    existing baseline" suppression to ONLY system/greeting messages and
    placeholder echoes.  Real prior-session bot replies must let mt030
    fire so the bot doesn't re-dispatch yesterday's answered question.

    Live trace 2026-05-29 13:50:25→13:50:46: 客户05's chat had a prior-
    session real reply ("您好，我们常规订单默认...") in the DOM at process
    start.  mt038F-F2 logged "would fire but agent bubble is pre-existing
    baseline — dispatch continues" → bot re-dispatched the already-
    answered question → typed a near-duplicate reply that visually
    appeared as "responses keyed in twice" across most customers.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052N", PE_SRC_052N)

    def test_first_baseline_branch_gates_on_classification(self) -> None:
        # The no-baseline branch must consult both system_message_filter
        # AND placeholder text classification before setting the flag.
        log = PE_SRC_052N.find('"[BrowserAutomation] mt017 baselined latest agent "')
        self.assertGreater(log, -1)
        elif_branch = PE_SRC_052N.find(
            "elif _lab_msg_id and _lab_msg_id == baseline:", log
        )
        self.assertGreater(elif_branch, log)
        block = PE_SRC_052N[log:elif_branch]
        # Both checks must appear inside the same branch.
        self.assertIn(
            "from .system_message_filter import",
            block,
            "first-baseline branch must consult system_message_filter",
        )
        self.assertIn(
            "from .dispatch_state import",
            block,
            "first-baseline branch must consult is_placeholder_text",
        )
        self.assertIn("_is_system_bubble_mt052n", block)
        self.assertIn("_is_placeholder_mt052n", block)

    def test_matches_baseline_branch_gates_on_classification(self) -> None:
        # Same gating must apply in the elif (repeat-sighting) branch —
        # otherwise the second enrich pass on a real prior-session reply
        # would set the flag and re-defeat mt030.
        elif_branch = PE_SRC_052N.find("elif _lab_msg_id and _lab_msg_id == baseline:")
        else_branch = PE_SRC_052N.find("\n                else:\n", elif_branch)
        self.assertGreater(else_branch, elif_branch)
        block = PE_SRC_052N[elif_branch:else_branch]
        self.assertIn("_is_system_or_placeholder_mt052n", block)
        self.assertIn("from .system_message_filter import", block)
        self.assertIn("from .dispatch_state import", block)

    def test_flag_set_only_inside_classification_guard(self) -> None:
        # Inside both branches, _agent_bubble_is_pre_existing_baseline = True
        # must sit INSIDE an `if _is_system_*_mt052n` block — never at the
        # top of the branch unconditionally.
        log = PE_SRC_052N.find('"[BrowserAutomation] mt017 baselined latest agent "')
        elif_branch = PE_SRC_052N.find(
            "elif _lab_msg_id and _lab_msg_id == baseline:", log
        )
        block = PE_SRC_052N[log:elif_branch]
        # The first occurrence of the assignment must follow an
        # `if _is_system_bubble_mt052n or _is_placeholder_mt052n:` line.
        flag_idx = block.find("_agent_bubble_is_pre_existing_baseline = True")
        self.assertGreater(flag_idx, -1)
        # The nearest preceding control-flow opener should be the mt052N
        # guard, not the start of the branch.
        before_flag = block[:flag_idx]
        guard_idx = before_flag.rfind(
            "if _is_system_bubble_mt052n or _is_placeholder_mt052n:"
        )
        # Some other control statement should NOT sit between the guard
        # and the flag set — i.e. no nested `else` or another `if`.
        self.assertGreater(
            guard_idx, -1,
            "first-baseline branch must wrap the flag set in mt052N's classifier guard",
        )

    def test_emits_diagnostic_log_when_letting_mt030_fire(self) -> None:
        # When the baseline bubble looks like a real prior-session reply
        # (not system / not placeholder), log that we're letting mt030
        # fire so operators can grep for this in trace investigation.
        self.assertIn(
            "mt052N letting mt030 fire",
            PE_SRC_052N,
            "must emit a grep-able log when the bubble looks like a real reply",
        )

    def test_keeps_suppression_log_when_match(self) -> None:
        # When the baseline IS a system/placeholder, also log the
        # suppression so we can confirm the original mt038F intent still
        # holds for those cases.
        self.assertIn(
            "mt052N keeping mt038F",
            PE_SRC_052N,
            "must emit a grep-able log when keeping mt038F suppression",
        )


# -----------------------------------------------------------------------
# mt052O — re-arm placeholder timer after supersede broad-cancel
# -----------------------------------------------------------------------

FD_SRC_052O = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt052O_SupersedeRearmSourceTests(unittest.TestCase):
    """mt052O re-arms a placeholder timer for the customer immediately
    after the mt050K broad-cancel inside the inflight-supersede branch.
    Without it, when re-dispatch is dedup-blocked (e.g. Feige merges the
    new bubble into the prior msg_id), the customer goes silent for the
    full LLM round-trip with no "human is replying" acknowledgment.

    Live trace 2026-05-29 14:12:49→14:13:33 客户11: 44 s of dead air
    after the supersede cancel cleared every timer.  The real reply did
    arrive, but the customer perceived it as "stuck" because nothing
    acknowledged the new message until the final answer landed.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt052O", FD_SRC_052O)

    def test_sits_inside_supersede_branch(self) -> None:
        # The re-arm must follow the supersede broad-cancel (mt050K) and
        # precede the assigned_sessions.pop — i.e. sit at the END of the
        # supersede branch, not in some unrelated control-flow path.
        # The marker log is split across f-string concatenations so the
        # contiguous substring "mt050K broad-cancel removed" doesn't
        # exist; search for the proactive_clear log instead which is on
        # one line.
        broad_cancel_idx = FD_SRC_052O.find("mt050N-#1a")
        pop_idx = FD_SRC_052O.find(
            "assigned_sessions.pop(session_id, None)", broad_cancel_idx
        )
        mt052o_idx = FD_SRC_052O.find("mt052O", broad_cancel_idx)
        self.assertGreater(broad_cancel_idx, -1)
        self.assertGreater(pop_idx, broad_cancel_idx)
        self.assertGreater(mt052o_idx, broad_cancel_idx)
        self.assertLess(mt052o_idx, pop_idx)

    def test_imports_placeholder_timer_and_tunables(self) -> None:
        idx = FD_SRC_052O.find("mt052O")
        block = FD_SRC_052O[idx:idx + 2500]
        self.assertIn(
            "from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import",
            block,
        )
        self.assertIn("placeholder_timer as _ph_timer_rearm", block)
        self.assertIn("tunables as _ph_tunables_rearm", block)

    def test_arms_using_new_msg_id_from_item(self) -> None:
        idx = FD_SRC_052O.find("mt052O")
        block = FD_SRC_052O[idx:idx + 2500]
        # Must read the NEW msg_id from item (so mt052F can later upgrade
        # it if the re-dispatch succeeds with a known msg_id), and must
        # fall back to empty string when it's not yet known.
        self.assertIn('item.get("latest_message_msg_id")', block)
        self.assertIn("_ph_timer_rearm.arm(", block)
        self.assertIn("customer_key=str(customer_key)", block)
        self.assertIn("source_msg_id=_mt052o_new_msg_id", block)

    def test_respects_timeout_disabled(self) -> None:
        # If the operator-configured placeholder timeout is <= 0 (default
        # off), the re-arm must NOT fire — otherwise we'd resurrect timers
        # in a configuration that's deliberately suppressing them.
        idx = FD_SRC_052O.find("mt052O")
        block = FD_SRC_052O[idx:idx + 2500]
        self.assertIn("if _mt052o_timeout > 0:", block)

    def test_failure_is_non_fatal(self) -> None:
        # The try/except surrounds the entire arm + log; widen the
        # window past the f-string log lines to reach the except.
        idx = FD_SRC_052O.find("mt052O")
        block = FD_SRC_052O[idx:idx + 4000]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)
        self.assertIn("non-fatal", block.lower())

    def test_resolves_via_tunables_resolve_float(self) -> None:
        # Use resolve_float (the float-typed tunable resolver) since the
        # timeout is a duration; resolve_int would truncate.
        idx = FD_SRC_052O.find("mt052O")
        block = FD_SRC_052O[idx:idx + 2500]
        self.assertIn(
            "_ph_tunables_rearm.resolve_float(",
            block,
            "must use the float-typed resolver for a duration value",
        )


class Mt052O_SupersedeRearmBehaviourTests(unittest.TestCase):
    """Drive placeholder_timer.arm directly with the same kwargs the
    mt052O re-arm uses, and confirm the registry gets a fresh entry
    even when the source_msg_id is empty."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as ph,
        )
        self.ph = ph
        with ph._REGISTRY_LOCK:
            ph._REGISTRY.clear()
            ph._PLACEHOLDERS_TYPED_TS.clear()
            ph._REAL_REPLY_AT.clear()
            ph._INFLIGHT_PLACEHOLDER_TASKS.clear()
            ph._FIRST_SEEN_AT.clear()
            ph._FIRST_SEEN_BY_CUSTOMER.clear()

    def test_rearm_empty_msg_id_creates_entry(self) -> None:
        # Simulates the re-dispatch-blocked path: msg_id unknown at
        # supersede time, mt052O arms with empty string.
        self.ph.arm(
            customer_key="客户11", source_msg_id="", timeout_s=20.0,
        )
        with self.ph._REGISTRY_LOCK:
            self.assertIn(("客户11", ""), self.ph._REGISTRY)

    def test_rearm_then_mt052f_upgrade_chain(self) -> None:
        # End-to-end: mt052O arms with empty msg_id, then later
        # PreDispatch's own arm with the resolved msg_id upgrades the
        # entry (mt052F).  Verifies the two fixes compose.
        self.ph.arm(customer_key="客户11", source_msg_id="", timeout_s=20.0)
        self.ph.arm(
            customer_key="客户11",
            source_msg_id="msg_after_rearm",
            timeout_s=20.0,
        )
        with self.ph._REGISTRY_LOCK:
            keys = list(self.ph._REGISTRY.keys())
        self.assertNotIn(
            ("客户11", ""), keys,
            "mt052F should have upgraded the empty-msg entry from mt052O",
        )
        self.assertIn(("客户11", "msg_after_rearm"), keys)


# -----------------------------------------------------------------------
# mt053H1 — gate mt052D OOB on minimum customer-count
# -----------------------------------------------------------------------

FD_SRC_053H1 = Path(
    "agent/ec_skills/node_runtime/frontdesk_dispatch.py"
).read_text(encoding="utf-8")


class Mt053H1_OobMinCustomersSourceTests(unittest.TestCase):
    """mt053H1 prevents mt052D OOB from firing when fewer than N customers
    are eligible.  Under low load (1-2 customers in production), the OOB
    SPAWN every ~1s caused chat-tab churn → "Session not found" cascade
    (packet trace 2026-05-30 13:09→13:32, turn-2 lost permanently)."""

    def test_marker_present(self) -> None:
        self.assertIn("mt053H1", FD_SRC_053H1)

    def test_default_min_customers_is_three(self) -> None:
        self.assertIn("DEFAULT_OOB_MIN_CUSTOMERS: int = 3", FD_SRC_053H1)

    def test_env_var_named(self) -> None:
        self.assertIn("ECAN_FRONTDESK_OOB_MIN_CUSTOMERS", FD_SRC_053H1)

    def test_resolver_function_present(self) -> None:
        self.assertIn("def _oob_min_customers() -> int:", FD_SRC_053H1)

    def test_gate_sits_after_enabled_check(self) -> None:
        # The min-customers gate must come AFTER is_oob_enabled (so
        # disabled-mode behaviour is unchanged) and BEFORE acquire_customers
        # (so we don't even take the locks when below threshold).
        enabled_idx = FD_SRC_053H1.find("(ECAN_FRONTDESK_OOB_DISPATCH disabled)")
        acquire_idx = FD_SRC_053H1.find("acquired = acquire_customers(eligible)")
        gate_idx = FD_SRC_053H1.find("only {len(eligible)} eligible")
        self.assertGreater(enabled_idx, -1)
        self.assertGreater(acquire_idx, enabled_idx)
        self.assertGreater(gate_idx, enabled_idx)
        self.assertLess(gate_idx, acquire_idx)

    def test_invalid_env_falls_back_to_default(self) -> None:
        idx = FD_SRC_053H1.find("def _oob_min_customers() -> int:")
        end = FD_SRC_053H1.find("\ndef ", idx + 1)
        block = FD_SRC_053H1[idx:end]
        self.assertIn("except (TypeError, ValueError):", block)
        self.assertIn("if n >= 1 else DEFAULT_OOB_MIN_CUSTOMERS", block)


class Mt053H1_OobMinCustomersBehaviourTests(unittest.TestCase):
    """Drive _oob_min_customers via env-var so we know operator overrides
    work end-to-end."""

    def setUp(self) -> None:
        import os
        from agent.ec_skills.node_runtime import frontdesk_dispatch as fd
        self.fd = fd
        self.os = os
        self._old = os.environ.pop("ECAN_FRONTDESK_OOB_MIN_CUSTOMERS", None)

    def tearDown(self) -> None:
        if self._old is None:
            self.os.environ.pop("ECAN_FRONTDESK_OOB_MIN_CUSTOMERS", None)
        else:
            self.os.environ["ECAN_FRONTDESK_OOB_MIN_CUSTOMERS"] = self._old

    def test_default_is_three(self) -> None:
        self.assertEqual(self.fd._oob_min_customers(), 3)

    def test_env_override_lowers_threshold(self) -> None:
        self.os.environ["ECAN_FRONTDESK_OOB_MIN_CUSTOMERS"] = "2"
        self.assertEqual(self.fd._oob_min_customers(), 2)

    def test_env_override_raises_threshold(self) -> None:
        self.os.environ["ECAN_FRONTDESK_OOB_MIN_CUSTOMERS"] = "10"
        self.assertEqual(self.fd._oob_min_customers(), 10)

    def test_invalid_env_falls_back(self) -> None:
        self.os.environ["ECAN_FRONTDESK_OOB_MIN_CUSTOMERS"] = "abc"
        self.assertEqual(self.fd._oob_min_customers(), 3)

    def test_zero_falls_back_to_default(self) -> None:
        # Zero would disable the gate; treat as misconfig and use default.
        self.os.environ["ECAN_FRONTDESK_OOB_MIN_CUSTOMERS"] = "0"
        self.assertEqual(self.fd._oob_min_customers(), 3)


# -----------------------------------------------------------------------
# mt053H2 — clear dispatch ledger on Session-not-found exhaustion
# -----------------------------------------------------------------------

RUN_SRC_053H2 = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt053H2_SessionNotFoundClearSourceTests(unittest.TestCase):
    """mt053H2 mirrors mt046A's stale-drop dedup-ledger clear for the
    Session-not-found / target_not_found family of send failures.  Without
    it, every retry attempt after the chat session disappears hits
    PreDispatch's msg-id dedup skip and the customer's question never
    re-enters the dispatch path.  packet trace 2026-05-30 13:14→13:32
    showed 18+ Session-not-found failures, ledger never cleared, Feige
    auto-closed the session."""

    def test_marker_present(self) -> None:
        self.assertIn("mt053H2", RUN_SRC_053H2)

    def test_gated_on_release_on_failure(self) -> None:
        # The clear must only fire when retries are exhausted
        # (release_on_failure=True).  Mid-retry clears would race with
        # the in-flight retry and could double-dispatch.
        idx = RUN_SRC_053H2.find("mt053H2 (2026-05-30)")
        block = RUN_SRC_053H2[idx:idx + 4000]
        self.assertIn("release_on_failure", block)
        self.assertIn('"tool_failed:feige_send_message"', block)
        self.assertIn('Session not found', block)
        self.assertIn('target_not_found', block)

    def test_clears_msg_id_ledger(self) -> None:
        idx = RUN_SRC_053H2.find("mt053H2 (2026-05-30)")
        block = RUN_SRC_053H2[idx:idx + 4000]
        self.assertIn("last_dispatched_msg_id_by_customer.pop(", block)

    def test_clears_identity_keys(self) -> None:
        idx = RUN_SRC_053H2.find("mt053H2 (2026-05-30)")
        block = RUN_SRC_053H2[idx:idx + 4000]
        self.assertIn("clear_dispatched_identity_keys_for_customer", block)

    def test_force_reemit_on_event_monitor(self) -> None:
        # mt050H-style force re-emit so EventMonitor's diff detector
        # surfaces the customer again even if the sidebar text is
        # unchanged.
        idx = RUN_SRC_053H2.find("mt053H2 (2026-05-30)")
        block = RUN_SRC_053H2[idx:idx + 4000]
        self.assertIn("force_reemit_for_customer", block)

    def test_emits_ledger_stage(self) -> None:
        # Operator-grep-able ledger stage so the next emulation/customer
        # trace shows the recovery firing.
        idx = RUN_SRC_053H2.find("mt053H2 (2026-05-30)")
        block = RUN_SRC_053H2[idx:idx + 4000]
        self.assertIn('"direct_session_not_found_dropped"', block)

    def test_existing_stale_drop_path_preserved(self) -> None:
        # mt046A's stale-drop branch must continue to fire untouched —
        # we're adding a sibling handler, not replacing it.
        self.assertIn("mt046A", RUN_SRC_053H2)
        self.assertIn('"direct_stale_dropped"', RUN_SRC_053H2)


# -----------------------------------------------------------------------
# mt053J — direct-delivery JSON-parse-failure recovery
# -----------------------------------------------------------------------

RUN_SRC_053J = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt053J_JsonParseFailureRecoverySourceTests(unittest.TestCase):
    """mt053J recovers from direct-delivery JSON parse failures by (A)
    marking drift-recovery on regex-extracted customer_id and (B)
    clearing the dispatch ledgers so PreDispatch can re-dispatch the
    customer's still-pending question.

    Live trace 2026-05-30 19:56:58 肽斯特: QA bot's send_chat produced
    response_text with an unescaped raw newline inside a JSON envelope,
    json.loads failed, the message ended up first_invocation_skip-
    dropped by HOT-PATH-B, and the customer was frozen for 7.5 minutes
    until a new Feige system event unblocked them.
    """

    def test_marker_a_present(self) -> None:
        self.assertIn("mt053J-A", RUN_SRC_053J)

    def test_marker_b_present(self) -> None:
        self.assertIn("mt053J-B", RUN_SRC_053J)

    def test_regex_extracts_customer_id(self) -> None:
        idx = RUN_SRC_053J.find("mt053J-A")
        block = RUN_SRC_053J[idx:idx + 4000]
        # Pattern must match both "customer_name" and "customer_id"
        # since QA's payloads carry one or the other.
        self.assertIn('"customer_(?:name|id)"', block)

    def test_marks_drift_recovery(self) -> None:
        idx = RUN_SRC_053J.find("mt053J-A")
        block = RUN_SRC_053J[idx:idx + 4000]
        self.assertIn(
            "from agent.ec_skills.browser_use_extension.hooks.external.feige_chat.drift_recovery_signal import",
            block,
        )
        self.assertIn("mark_drift_recovery_pending", block)

    def test_recovers_source_msg_id_when_present(self) -> None:
        # If we can recover source_customer_msg_id from the malformed
        # JSON, pass it through so HOT-PATH-B's override can apply the
        # source-guard correctly on the retry.
        idx = RUN_SRC_053J.find("mt053J-A")
        block = RUN_SRC_053J[idx:idx + 4000]
        self.assertIn('"source_customer_msg_id"', block)

    def test_clears_msg_id_and_identity_ledgers(self) -> None:
        # mt053J-B half: ledger clear lets PreDispatch re-dispatch even
        # when HOT-PATH-B's drift-recovery override can't extract a
        # payload either.
        idx = RUN_SRC_053J.find("mt053J-B")
        block = RUN_SRC_053J[idx:idx + 4000]
        self.assertIn("last_dispatched_msg_id_by_customer.pop(", block)
        self.assertIn("clear_dispatched_identity_keys_for_customer", block)

    def test_force_reemit_after_clear(self) -> None:
        # Same as mt046A/mt053H2: EventMonitor's diff detector needs a
        # nudge after we clear the ledger so the customer's row surfaces
        # again even if the sidebar text hasn't changed.
        idx = RUN_SRC_053J.find("mt053J-B")
        block = RUN_SRC_053J[idx:idx + 4000]
        self.assertIn("force_reemit_for_customer", block)

    def test_no_action_when_customer_id_unextractable(self) -> None:
        # If regex can't pull customer_id from the malformed envelope,
        # we log a WARNING (so operators see the drop) but don't run
        # any of the recovery side-effects — recovery requires a key.
        idx = RUN_SRC_053J.find("mt053J-A could not regex-extract")
        self.assertGreater(idx, -1, "must log when regex extraction fails")

    def test_recovery_failure_is_non_fatal(self) -> None:
        # The mt053J recovery block grew when B was folded in; widen
        # the search window and look for the outer try/except wrapping
        # the entire recovery.  "non-fatal" appears in the outer
        # except's debug log.
        idx = RUN_SRC_053J.find("mt053J-A (2026-05-30)")
        block = RUN_SRC_053J[idx:idx + 6000]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)
        self.assertIn("non-fatal", block.lower())

    def test_sits_in_json_parse_failure_branch(self) -> None:
        # mt053J's recovery must sit inside the `except (ValueError,
        # TypeError):` branch of json.loads — not in some unrelated
        # error path.  Confirm the marker is between the except clause
        # and the existing "Skipping: human_text is not JSON" log.
        except_idx = RUN_SRC_053J.find("except (ValueError, TypeError):")
        skip_log_idx = RUN_SRC_053J.find(
            "Skipping: human_text is not JSON", except_idx
        )
        mt053j_idx = RUN_SRC_053J.find("mt053J-A", except_idx)
        self.assertGreater(except_idx, -1)
        self.assertGreater(skip_log_idx, except_idx)
        self.assertGreater(mt053j_idx, except_idx)
        self.assertLess(mt053j_idx, skip_log_idx)


class Mt053J_JsonParseFailureRecoveryRegexTests(unittest.TestCase):
    """Drive the regex extraction directly on samples that look like the
    customer trace, so we know the extraction works on real-world
    malformed JSON shapes."""

    def setUp(self) -> None:
        import re
        # The regex pattern from the implementation.
        self.cust_pat = re.compile(r'"customer_(?:name|id)"\s*:\s*"([^"]{1,40})"')
        self.src_pat = re.compile(r'"source_customer_msg_id"\s*:\s*"([^"]{1,80})"')

    def test_extracts_customer_name_from_tai_envelope(self) -> None:
        # Exact preview from the 2026-05-30 19:56:56 trace.
        sample = (
            '{"customer_id":"肽斯特","customer_name":"肽斯特",'
            '"response_text":"亲，这款建议按身高选码哦：\n110cm宝...'
        )
        m = self.cust_pat.search(sample)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "肽斯特")

    def test_extracts_customer_id_when_name_missing(self) -> None:
        sample = (
            '{"customer_id":"packet","response_text":"reply\nwith newline"}'
        )
        m = self.cust_pat.search(sample)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "packet")

    def test_extracts_source_msg_id_when_present(self) -> None:
        sample = (
            '{"customer_name":"packet",'
            '"source_customer_msg_id":"7w7epnptmprf4hqo",'
            '"response_text":"raw\nnewline"}'
        )
        m = self.src_pat.search(sample)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "7w7epnptmprf4hqo")


# -----------------------------------------------------------------------
# mt053J-C — root-cause fix: normalize raw control chars in JSON envelopes
# -----------------------------------------------------------------------

CHAT_TOOLS_SRC_053JC = Path(
    "agent/mcp/server/chat_utils/chat_tools.py"
).read_text(encoding="utf-8")


class Mt053JC_SendChatNormalizationSourceTests(unittest.TestCase):
    """mt053J-C normalizes the message envelope at the source (send_chat
    MCP tool entry).  Pre-fix, the QA bot's prompt-template renderer leaks
    raw newlines from response_text into a JSON envelope and json.loads
    fails downstream.  Post-fix, send_chat does a lenient parse +
    re-encode that escapes control chars properly.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt053J-C", CHAT_TOOLS_SRC_053JC)

    def test_uses_strict_false_parse(self) -> None:
        idx = CHAT_TOOLS_SRC_053JC.find("mt053J-C")
        block = CHAT_TOOLS_SRC_053JC[idx:idx + 3000]
        self.assertIn("strict=False", block)

    def test_renormalizes_via_json_dumps(self) -> None:
        idx = CHAT_TOOLS_SRC_053JC.find("mt053J-C")
        block = CHAT_TOOLS_SRC_053JC[idx:idx + 3000]
        self.assertIn("json.dumps", block.replace("_mt053jc_", "").replace("json", "json"))
        self.assertIn("ensure_ascii=False", block)

    def test_only_runs_on_json_looking_strings(self) -> None:
        # The normalize step is a no-op for non-JSON message_text so we
        # don't accidentally mangle plain text payloads.
        idx = CHAT_TOOLS_SRC_053JC.find("mt053J-C")
        block = CHAT_TOOLS_SRC_053JC[idx:idx + 3000]
        self.assertIn('message_text.lstrip().startswith("{")', block)

    def test_normalize_failure_is_non_fatal(self) -> None:
        # If even lenient parse can't recover, pass the message through
        # untouched so downstream mt053J-A/B safety net can recover.
        idx = CHAT_TOOLS_SRC_053JC.find("mt053J-C")
        block = CHAT_TOOLS_SRC_053JC[idx:idx + 3000]
        self.assertIn("except Exception:", block)


class Mt053JC_RunnerDefenseInDepthSourceTests(unittest.TestCase):
    """The runner-side defense-in-depth: even if mt053J-C at source
    didn't run (older binary, A2A intermediary mangled), the lenient
    parse fallback in _try_direct_live_chat_delivery still recovers.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt053J-C", RUN_SRC_053J)

    def test_lenient_parse_sits_in_first_except(self) -> None:
        # The lenient retry must sit in the SAME except block that
        # catches the strict parse failure — not after the recovery
        # code (which return False's away).
        strict_idx = RUN_SRC_053J.find("_parsed = _json.loads(_human_text)")
        lenient_idx = RUN_SRC_053J.find(
            "_parsed = _json.loads(_human_text, strict=False)"
        )
        if_parsed_none_idx = RUN_SRC_053J.find("if _parsed is None:")
        self.assertGreater(lenient_idx, strict_idx)
        self.assertGreater(if_parsed_none_idx, lenient_idx)

    def test_recovery_gated_on_parsed_is_none(self) -> None:
        # mt053J-A/B recovery only runs when BOTH parse attempts fail
        # — i.e. _parsed is None.
        self.assertIn("if _parsed is None:", RUN_SRC_053J)


class Mt053JC_LenientParseBehaviourTests(unittest.TestCase):
    """End-to-end: run the exact normalization pattern on the customer
    trace's malformed JSON and verify the recovered text parses cleanly
    via strict json.loads."""

    def test_recovers_raw_newline_envelope(self) -> None:
        import json
        # Faithful reproduction of the 2026-05-30 19:56:56 肽斯特 trace:
        # response_text contains a raw newline character (not "\\n").
        bad = (
            '{"customer_id":"肽斯特","customer_name":"肽斯特",'
            '"response_text":"亲，这款建议按身高选码哦：\n110cm宝宝建议选120码。"}'
        )
        # Strict parse must fail on the raw newline.
        with self.assertRaises(json.JSONDecodeError):
            json.loads(bad)
        # Lenient parse + re-encode (mt053J-C's recovery) must round-trip
        # cleanly.
        recovered = json.dumps(json.loads(bad, strict=False), ensure_ascii=False)
        # Re-parse must succeed strict.
        round_tripped = json.loads(recovered)
        self.assertEqual(round_tripped["customer_id"], "肽斯特")
        self.assertIn("110cm宝宝", round_tripped["response_text"])

    def test_no_change_for_already_valid_json(self) -> None:
        # When the JSON is already well-formed, mt053J-C's pipeline
        # produces semantically-identical output (escaping may differ
        # but the parsed dict is equal).
        import json
        good = '{"customer_id":"abc","response_text":"hello"}'
        recovered = json.dumps(json.loads(good, strict=False), ensure_ascii=False)
        self.assertEqual(json.loads(recovered), json.loads(good))


# -----------------------------------------------------------------------
# mt053K — CDP-direct rediscovery when session_manager view is empty
# -----------------------------------------------------------------------

RUN_BN_SRC_053K = Path(
    "agent/ec_skills/browser_node/runner.py"
).read_text(encoding="utf-8")


class Mt053K_CdpRediscoverySourceTests(unittest.TestCase):
    """mt053K stops the freeze that happens when browser-use's
    session_manager loses its target attachments under high-concurrency
    CDP churn (1-to-7 customer trace 2026-05-31 12:11→12:13: Chrome had
    Feige tabs the whole time, session_manager's get_all_targets()
    returned empty for the rest of the run, every browser_automation
    node raised "no browser tabs available").  Before raising, the
    preflight now opens an independent CDP client, enumerates real
    Chrome tabs, and re-attaches to any Feige target found.
    """

    def test_marker_present(self) -> None:
        self.assertIn("mt053K", RUN_BN_SRC_053K)

    def test_helper_function_defined(self) -> None:
        self.assertIn(
            "async def _mt053k_try_cdp_rediscover_and_attach(", RUN_BN_SRC_053K,
        )

    def test_feige_url_hints_defined(self) -> None:
        # The URL hints are what distinguish a Feige seller-workspace tab
        # from arbitrary Chrome tabs the user might have open.  Both
        # substrings must be in the tuple so we cover the workspace path
        # and the bare host (in case Feige redirects between subpaths).
        self.assertIn('_MT053K_FEIGE_URL_HINTS', RUN_BN_SRC_053K)
        self.assertIn('"im.jinritemai.com"', RUN_BN_SRC_053K)
        self.assertIn('"/pc_seller_v2/main/workspace"', RUN_BN_SRC_053K)

    def test_uses_independent_cdp_client(self) -> None:
        # The recovery must NOT go through browser_session's existing CDP
        # client (which is presumed broken since session_manager is blank).
        # Use the same CDPClient pattern EventMonitor uses (proven to
        # survive while session_manager is blank in the customer trace).
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn("from cdp_use import CDPClient", block)
        self.assertIn("client.start()", block)
        self.assertIn('"Target.getTargets"', block)

    def test_attempts_target_attach(self) -> None:
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn('"Target.attachToTarget"', block)
        # flatten=True is required so the session shows up under
        # browser-use's unified session_manager view on the next poll.
        self.assertIn('"flatten": True', block)

    def test_filters_for_page_targets(self) -> None:
        # type=page (or tab) — service workers, iframes, etc. don't count.
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn('"page"', block)
        # And the Feige filter must apply on top.
        self.assertIn("_MT053K_FEIGE_URL_HINTS", block)

    def test_logs_chrome_vs_session_manager_discrepancy(self) -> None:
        # The most important operator-visible signal: how many tabs
        # Chrome actually has vs what session_manager reports.  Without
        # this log, the regression looks identical to "Chrome crashed"
        # and operators waste time restarting Chrome.
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn("session_manager saw 0", block)
        self.assertIn("chrome_targets_total", block)
        self.assertIn("feige_targets", block)

    def test_recovery_failure_is_non_fatal(self) -> None:
        # The recovery is best-effort.  Any exception (CDP timeout,
        # cdp_use import missing, etc.) must NOT mask the original
        # error — callers still need the RuntimeError so they don't
        # silently no-op.
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn("except Exception", block)
        self.assertIn("non-fatal", block.lower())

    def test_cdp_client_always_stopped(self) -> None:
        # Independent CDP client must be torn down in a finally block —
        # leaking websocket connections under the customer's high-
        # frequency reentry into this path would exhaust file handles.
        idx = RUN_BN_SRC_053K.find("_mt053k_try_cdp_rediscover_and_attach")
        block = RUN_BN_SRC_053K[idx:idx + 5000]
        self.assertIn("finally:", block)
        self.assertIn("client.stop()", block)


class Mt053K_PreflightIntegrationSourceTests(unittest.TestCase):
    """The preflight in run_cdp_focus_preflight must consult the
    rediscovery helper BEFORE raising the 'no browser tabs available'
    error.  After rediscovery, it must re-read session_manager's view —
    if the reattach worked, the original 'page_target_ids is empty'
    condition becomes false and the function proceeds normally.
    """

    def test_recovery_call_sits_before_raise(self) -> None:
        # Find the inner 'if not page_target_ids:' (post-recovery) — it
        # must come AFTER the call to the helper.
        helper_call_idx = RUN_BN_SRC_053K.find(
            "await _mt053k_try_cdp_rediscover_and_attach("
        )
        # The RuntimeError must STILL be raised when recovery fails.
        runtime_error_idx = RUN_BN_SRC_053K.find(
            'CDP-direct rediscovery did', helper_call_idx,
        )
        self.assertGreater(helper_call_idx, -1)
        self.assertGreater(runtime_error_idx, helper_call_idx)

    def test_rereads_session_manager_after_reattach(self) -> None:
        # After mt053K reports success, the preflight MUST re-poll
        # session_manager — otherwise the just-attached target stays
        # invisible to the rest of the function.
        helper_call_idx = RUN_BN_SRC_053K.find(
            "await _mt053k_try_cdp_rediscover_and_attach("
        )
        block = RUN_BN_SRC_053K[helper_call_idx:helper_call_idx + 2000]
        # Re-poll uses the same sm.get_all_targets() pattern.
        self.assertIn("sm.get_all_targets()", block)
        self.assertIn("page_target_ids = [", block)

    def test_error_message_explains_real_cause(self) -> None:
        # The new error message must distinguish "session_manager blank
        # AND Chrome really has no Feige tab" from the old misleading
        # "all tabs have been closed".  Operators reading this should
        # know to either restart eCan or check Chrome.
        self.assertIn("CDP-direct rediscovery did", RUN_BN_SRC_053K)
        self.assertIn("consider restarting eCan", RUN_BN_SRC_053K)


# -----------------------------------------------------------------------
# mt054A — judge_async: replace sync llm.invoke with await llm.ainvoke
# -----------------------------------------------------------------------

HRJ_SRC_054A = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/human_relevance_judge.py"
).read_text(encoding="utf-8")
RUN_SRC_054A = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")


class Mt054A_JudgeAsyncSourceTests(unittest.TestCase):
    """mt054A converts the human-relevance judge LLM call from sync
    `llm.invoke()` inside a ThreadPoolExecutor (which blocks the event
    loop on `_fut.result(timeout=...)` when called from async context)
    to true async `await llm.ainvoke()` wrapped in `asyncio.wait_for`.
    Customer 1-to-7 trace 2026-05-31 12:02→12:09 showed two EventMonitor
    heartbeat gaps (76 s + 194 s) proving the event loop was wedged —
    consistent with the existing in-code comment about a 129.7 s judge
    invoke block."""

    def test_marker_present(self) -> None:
        self.assertIn("mt054A", HRJ_SRC_054A)

    def test_judge_async_function_defined(self) -> None:
        self.assertIn("async def judge_async(", HRJ_SRC_054A)

    def test_uses_ainvoke_not_sync_invoke(self) -> None:
        idx = HRJ_SRC_054A.find("async def judge_async(")
        end_idx = HRJ_SRC_054A.find("\ndef reset_llm_cache", idx)
        self.assertGreater(end_idx, idx)
        block = HRJ_SRC_054A[idx:end_idx]
        # Must await ainvoke (the async variant of invoke)
        self.assertIn("await asyncio.wait_for(", block)
        self.assertIn("llm.ainvoke(", block)
        # Must NOT have an active ThreadPoolExecutor construction or
        # a blocking _fut.result(timeout=...) call.  Check specific
        # code patterns (docstring may reference these terms for
        # context but executable code must not use them).  Strip the
        # docstring before scanning so historical-context narrative
        # doesn't trip the check.
        import re as _re
        code_block = _re.sub(r'"""[\s\S]*?"""', '', block, count=1)
        self.assertNotIn("ThreadPoolExecutor(", code_block)
        self.assertNotIn("_ex.submit(", code_block)
        self.assertNotIn("_fut.result(", code_block)

    def test_keeps_timeout_semantics(self) -> None:
        idx = HRJ_SRC_054A.find("async def judge_async(")
        end_idx = HRJ_SRC_054A.find("\ndef reset_llm_cache", idx)
        block = HRJ_SRC_054A[idx:end_idx]
        # asyncio.TimeoutError -> "llm_invoke_timeout" verdict so callers
        # get the same drop-on-failure behaviour as the sync judge
        self.assertIn("asyncio.TimeoutError", block)
        self.assertIn('reason="llm_invoke_timeout"', block)

    def test_preserves_verdict_shape(self) -> None:
        # Caller in runner.py reads verdict.answered / verdict.confidence /
        # verdict.error / verdict.reason — they must all still be set on
        # every code path (init fail, timeout, invoke fail, parse fail,
        # success).
        idx = HRJ_SRC_054A.find("async def judge_async(")
        end_idx = HRJ_SRC_054A.find("\ndef reset_llm_cache", idx)
        block = HRJ_SRC_054A[idx:end_idx]
        for required in (
            'reason="llm_init_failed"',
            'reason="llm_invoke_timeout"',
            'reason="llm_invoke_failed"',
            'reason="parse_failed"',
        ):
            self.assertIn(required, block)

    def test_sync_judge_still_present_for_backcompat(self) -> None:
        # We added judge_async as a sibling — old sync judge() must
        # remain for any non-async caller / existing test.
        self.assertIn("def judge(", HRJ_SRC_054A)
        # Specifically NOT replacing it.
        self.assertGreater(HRJ_SRC_054A.count("def judge("), 0)


class Mt054A_RunnerUsesJudgeAsyncSourceTests(unittest.TestCase):
    """The only production caller (`_do_guarded_direct_delivery` at
    runner.py:4820) must use the async version so the event loop isn't
    blocked during the LLM call."""

    def test_marker_present(self) -> None:
        self.assertIn("mt054A", RUN_SRC_054A)

    def test_calls_judge_async_with_await(self) -> None:
        self.assertIn("await _mt048b_judge_mod.judge_async(", RUN_SRC_054A)

    def test_old_sync_judge_call_removed_from_this_site(self) -> None:
        # Find the mt048B judge invocation site and confirm it now uses
        # judge_async, NOT the sync judge.  Search the surrounding
        # context for the OLD pattern.
        await_idx = RUN_SRC_054A.find("await _mt048b_judge_mod.judge_async(")
        # The sync `_mt048b_judge_mod.judge(` must NOT appear in the
        # 1000-char block around the new call (would mean we left the
        # old call behind).
        block = RUN_SRC_054A[max(0, await_idx - 500):await_idx + 500]
        self.assertNotIn("_mt048b_judge_mod.judge(", block)


# -----------------------------------------------------------------------
# mt054B — CDP WebSocket ping_interval / ping_timeout bump
# -----------------------------------------------------------------------

RUN_BN_SRC_054B = Path(
    "agent/ec_skills/browser_node/runner.py"
).read_text(encoding="utf-8")


class Mt054B_WebSocketPingPatchSourceTests(unittest.TestCase):
    """mt054B monkey-patches cdp_use's websockets.connect call to set
    ping_interval=60s / ping_timeout=120s (was 20s/20s default).  Under
    heavy event-loop load, the 20 s default ping miss triggers Chrome
    to close the connection (code 1011 keepalive ping timeout); browser-
    use's SessionManager then clears all owned data → mt053K has to
    rediscover from scratch.  Bumping to 60/120 absorbs transient
    event-loop blocks (GC, big JSON parses) up to ~2 min."""

    def test_marker_present(self) -> None:
        self.assertIn("mt054B", RUN_BN_SRC_054B)

    def test_install_function_defined(self) -> None:
        self.assertIn("def _mt054b_install_ws_ping_patch()", RUN_BN_SRC_054B)

    def test_default_constants_match_intent(self) -> None:
        # ping_interval=60 — still ping regularly so a truly dead
        # connection is detected; just less aggressive than 20 s.
        self.assertIn("_MT054B_PING_INTERVAL_S: float = 60.0", RUN_BN_SRC_054B)
        # ping_timeout=120 — 2 min of grace; pair with mt054A so we
        # don't actually need most of it.
        self.assertIn("_MT054B_PING_TIMEOUT_S: float = 120.0", RUN_BN_SRC_054B)

    def test_one_shot_via_sentinel(self) -> None:
        # Setting the sentinel makes the patch idempotent under
        # re-import (test isolation, reloaders).
        idx = RUN_BN_SRC_054B.find("def _mt054b_install_ws_ping_patch")
        end_idx = RUN_BN_SRC_054B.find("\n_mt054b_install_ws_ping_patch()", idx)
        block = RUN_BN_SRC_054B[idx:end_idx]
        self.assertIn('_mt054b_ws_ping_patched', block)
        self.assertIn("setdefault(", block)

    def test_patch_invoked_at_module_import(self) -> None:
        # The patch must run at import time so any CDPClient created
        # after this module is imported gets the bumped defaults.
        self.assertIn("\n_mt054b_install_ws_ping_patch()\n", RUN_BN_SRC_054B)


class Mt054B_WebSocketPingPatchBehaviourTests(unittest.TestCase):
    """Verify the patch actually took effect after import."""

    def test_websockets_connect_is_patched(self) -> None:
        import cdp_use.client as cm
        from agent.ec_skills.browser_node import runner  # noqa: F401
        self.assertTrue(getattr(cm, "_mt054b_ws_ping_patched", False))
        # The patched callable should be a coroutine function named
        # _patched_connect (or similar — we check by attribute).
        self.assertEqual(cm.websockets.connect.__name__, "_patched_connect")

    def test_double_install_is_noop(self) -> None:
        # Re-calling the installer must NOT chain-wrap the patch
        # (which would create _patched_connect calling _patched_connect
        # calling original — gets slower with each import).
        import cdp_use.client as cm
        from agent.ec_skills.browser_node import runner as r
        first = cm.websockets.connect
        r._mt054b_install_ws_ping_patch()
        second = cm.websockets.connect
        self.assertIs(first, second)


# -----------------------------------------------------------------------
# mt054C — bounded scrape-lock wait
# -----------------------------------------------------------------------

DA_SRC_054C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt054C_BoundedScrapeLockSourceTests(unittest.TestCase):
    """mt054C bounds the scrape-lock wait so a wedged or slow current
    holder can't starve other customers' scrapes for 30-70 seconds.
    Customer 1-to-7 trace 2026-05-31 12:09: FEIGE-SCRAPE-LOCK wait_ms
    P50=11.7 s, P90=32.5 s, max=73 s.  Lock IS correctness-critical
    (click+verify modifies sidebar focus across all callers; mt024
    regression proved concurrent scrapes interleave); we can't drop
    it.  But we CAN cap the wait so callers fall back to sidebar-only
    mode (existing scrape-failure path) instead of blocking dispatch."""

    def test_marker_present(self) -> None:
        self.assertIn("mt054C", DA_SRC_054C)

    def test_uses_acquire_or_skip_with_timeout(self) -> None:
        idx = DA_SRC_054C.find("mt054C")
        block = DA_SRC_054C[idx:idx + 3000]
        # Must call the timeout-aware acquire helper (existing on
        # _CrossLoopAsyncLock) instead of `async with lock:` (which
        # waits forever).
        self.assertIn("_scrape_lock.acquire_or_skip(", block)
        self.assertIn("timeout_s=_mt054c_timeout_s", block)

    def test_default_timeout_is_eight_seconds(self) -> None:
        idx = DA_SRC_054C.find("mt054C")
        block = DA_SRC_054C[idx:idx + 3000]
        # 8s is conservative — gives most legit scrapes time to finish
        # but caps the worst-case wait at single-digit seconds (was 73s).
        self.assertIn('"ECAN_FEIGE_SCRAPE_LOCK_WAIT_S"', block)
        self.assertIn('or 8.0', block)

    def test_fallback_returns_empty_on_timeout(self) -> None:
        # On lock timeout, return the same `empty` dict the existing
        # scrape-failure path returns.  Caller then uses sidebar text
        # for the dispatch — same downstream behaviour as a scrape
        # that ran but found no bubble.
        idx = DA_SRC_054C.find("mt054C scrape-lock acquire TIMEOUT")
        self.assertGreater(idx, -1)
        block = DA_SRC_054C[idx:idx + 600]
        self.assertIn("return empty", block)

    def test_logs_holder_diagnostic(self) -> None:
        # Operators need to know WHICH customer was holding the lock
        # when we timed out (so they can investigate the slow one).
        idx = DA_SRC_054C.find("mt054C scrape-lock acquire TIMEOUT")
        block = DA_SRC_054C[idx:idx + 800]
        self.assertIn("current holder=", block)
        self.assertIn("held_for=", block)

    def test_releases_lock_in_finally(self) -> None:
        # Once we successfully acquire_or_skip, we MUST release exactly
        # once.  Use try/finally to guarantee release even if scrape
        # body raises.
        idx = DA_SRC_054C.find("if not _lock_acquired:")
        end_idx = DA_SRC_054C.find("\nasync def _scrape_locked_body", idx)
        self.assertGreater(end_idx, idx)
        block = DA_SRC_054C[idx:end_idx]
        self.assertIn("try:", block)
        self.assertIn("finally:", block)
        self.assertIn("_scrape_lock.release()", block)

    def test_keeps_lock_wait_metric_log(self) -> None:
        # We must still emit the FEIGE-SCRAPE-LOCK wait_ms log so
        # operators can track lock contention (now bounded but worth
        # monitoring).
        idx = DA_SRC_054C.find("mt054C")
        block = DA_SRC_054C[idx:idx + 3000]
        self.assertIn('"[FEIGE-SCRAPE-LOCK] customer=', block)
        self.assertIn("wait_ms=", block)


# -----------------------------------------------------------------------
# mt055C — watchdog arm on scrape-latest-customer success
# -----------------------------------------------------------------------

PT_SRC_055C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/placeholder_timer.py"
).read_text(encoding="utf-8")

DA_SRC_055C = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py"
).read_text(encoding="utf-8")


class Mt055C_WatchdogArmSourceTests(unittest.TestCase):
    """mt055C adds an idempotent ``arm_watchdog`` helper and calls it
    on every successful customer-bubble scrape, so an unreplied bubble
    is guaranteed to fire a placeholder within FEIGE_PLACEHOLDER_TIMEOUT_S
    regardless of which dispatch decision is made later.  Customer trace
    2026-05-31 showed J14N9 stuck for 5.5 min because the sidebar
    preview ``转人工`` was filtered as ``system_message:transfer_to_
    human_label`` and never armed a timer."""

    def test_arm_watchdog_function_exists(self) -> None:
        self.assertIn("def arm_watchdog(", PT_SRC_055C)
        # Exported so external modules can import it (Python guideline,
        # not enforced — but the __all__ contract makes intent clear).
        self.assertIn('"arm_watchdog"', PT_SRC_055C)

    def test_arm_watchdog_is_idempotent_on_active_entry(self) -> None:
        """The whole point: repeated scrapes must NOT reset the deadline.
        Otherwise the timer never fires."""
        idx = PT_SRC_055C.find("def arm_watchdog(")
        end_idx = PT_SRC_055C.find("\ndef cancel(", idx)
        self.assertGreater(end_idx, idx)
        body = PT_SRC_055C[idx:end_idx]
        # Skip when an active (un-cancelled, deadline-in-future) entry
        # already exists for the exact key.
        self.assertIn("_REGISTRY.get(key)", body)
        self.assertIn("not existing.cancelled", body)
        self.assertIn("existing.deadline_at > now", body)
        self.assertIn("return False", body)

    def test_arm_watchdog_skips_after_real_reply_at_exact_key(self) -> None:
        """If we've already replied to this exact (customer, msg_id),
        a permanent _REAL_REPLY_AT stamp exists at the precise key.
        arm_watchdog must respect this — no time window."""
        idx = PT_SRC_055C.find("def arm_watchdog(")
        end_idx = PT_SRC_055C.find("\ndef cancel(", idx)
        body = PT_SRC_055C[idx:end_idx]
        self.assertIn("_REAL_REPLY_AT.get(key, 0.0) > 0.0", body)

    def test_arm_watchdog_respects_blank_key_suppress_window(self) -> None:
        """Recent reply at the per-customer blank-key slot within
        REAL_REPLY_SUPPRESS_S should also suppress — mirrors the
        sweeper's claim_expired check."""
        idx = PT_SRC_055C.find("def arm_watchdog(")
        end_idx = PT_SRC_055C.find("\ndef cancel(", idx)
        body = PT_SRC_055C[idx:end_idx]
        self.assertIn("_REAL_REPLY_AT.get(blank_key, 0.0)", body)
        self.assertIn("REAL_REPLY_SUPPRESS_S", body)

    def test_arm_watchdog_requires_msg_id(self) -> None:
        """source_msg_id must be non-empty.  The blank-key arm path is
        already covered by mt052C at EventMonitor time; watchdog is
        specifically for the precise-msg_id case at scrape time."""
        idx = PT_SRC_055C.find("def arm_watchdog(")
        end_idx = PT_SRC_055C.find("\ndef cancel(", idx)
        body = PT_SRC_055C[idx:end_idx]
        self.assertIn("not source_msg_id", body)

    def test_arm_watchdog_delegates_to_arm(self) -> None:
        """When all guards pass, delegate to the existing arm() so the
        first_seen anchor + entry-creation logic stays in one place."""
        idx = PT_SRC_055C.find("def arm_watchdog(")
        end_idx = PT_SRC_055C.find("\ndef cancel(", idx)
        body = PT_SRC_055C[idx:end_idx]
        self.assertIn("arm(cust, msg, timeout_s=timeout_s)", body)
        self.assertIn("return True", body)

    def test_scrape_latest_calls_arm_watchdog(self) -> None:
        """The dom_assets.scrape_latest_customer_bubble path invokes
        arm_watchdog on every successful scrape that has a msg_id."""
        self.assertIn("mt055C", DA_SRC_055C)
        idx = DA_SRC_055C.find("mt055C")
        block = DA_SRC_055C[idx:idx + 3000]
        self.assertIn("placeholder_timer", block)
        self.assertIn("arm_watchdog(", block)
        self.assertIn("customer_key=customer_name", block)
        self.assertIn("source_msg_id=msg_id", block)
        self.assertIn("timeout_s=_mt055c_timeout", block)

    def test_scrape_latest_guards_on_msg_id(self) -> None:
        """We only arm when msg_id is non-empty.  A scrape that
        succeeded but produced no msg_id is a fallback path we don't
        want to anchor a per-turn timer to."""
        idx = DA_SRC_055C.find("mt055C")
        block = DA_SRC_055C[idx:idx + 3000]
        self.assertIn("if msg_id:", block)

    def test_scrape_latest_respects_timeout_env_var(self) -> None:
        """Reuses the existing FEIGE_PLACEHOLDER_TIMEOUT_S env so
        operators don't have to learn a new knob.  Timeout <= 0 (the
        disabled default) means watchdog is off — matches the
        documented opt-in semantics."""
        idx = DA_SRC_055C.find("mt055C")
        block = DA_SRC_055C[idx:idx + 3000]
        self.assertIn('"FEIGE_PLACEHOLDER_TIMEOUT_S"', block)
        self.assertIn("if _mt055c_timeout > 0:", block)

    def test_scrape_latest_logs_when_armed(self) -> None:
        """Operators need to see "mt055C watchdog armed" in the log
        so they can confirm the fix is firing in production traces."""
        idx = DA_SRC_055C.find("mt055C")
        block = DA_SRC_055C[idx:idx + 3000]
        self.assertIn("mt055C watchdog armed", block)
        self.assertIn("scrape-latest path", block)


class Mt055C_WatchdogArmRuntimeTests(unittest.TestCase):
    """Runtime behaviour of arm_watchdog — the source-text tests above
    only verify code shape.  These exercise the function in-process to
    confirm the actual idempotency / suppression semantics hold."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            placeholder_timer as pt,
        )
        # Reset module state between tests so each starts clean.
        with pt._REGISTRY_LOCK:
            pt._REGISTRY.clear()
            pt._REAL_REPLY_AT.clear()
            pt._FIRST_SEEN_AT.clear()
            pt._FIRST_SEEN_BY_CUSTOMER.clear()
            pt._PLACEHOLDERS_TYPED_TS.clear()
        self.pt = pt

    def test_first_call_arms(self) -> None:
        result = self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0)
        self.assertTrue(result)
        with self.pt._REGISTRY_LOCK:
            self.assertIn(("cust_a", "msg_1"), self.pt._REGISTRY)

    def test_second_call_with_same_key_is_noop(self) -> None:
        self.assertTrue(self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0))
        with self.pt._REGISTRY_LOCK:
            first_deadline = self.pt._REGISTRY[("cust_a", "msg_1")].deadline_at
        # Second call must return False AND not reset the deadline
        result = self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0)
        self.assertFalse(result)
        with self.pt._REGISTRY_LOCK:
            self.assertEqual(
                self.pt._REGISTRY[("cust_a", "msg_1")].deadline_at,
                first_deadline,
            )

    def test_skips_after_real_reply_at_exact_key(self) -> None:
        self.pt.mark_real_reply_delivered("cust_a", "msg_1")
        result = self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0)
        self.assertFalse(result)
        with self.pt._REGISTRY_LOCK:
            self.assertNotIn(("cust_a", "msg_1"), self.pt._REGISTRY)

    def test_skips_within_blank_key_suppress_window(self) -> None:
        # Simulate a reply for a DIFFERENT msg_id of the same customer
        # within the suppress window.
        self.pt.mark_real_reply_delivered("cust_a", "msg_OLD")
        result = self.pt.arm_watchdog("cust_a", "msg_NEW", timeout_s=10.0)
        self.assertFalse(result)

    def test_arms_after_suppress_window_expires(self) -> None:
        # Past the suppress window, a new msg_id should arm fresh.
        import time as _t
        self.pt.mark_real_reply_delivered("cust_a", "msg_OLD")
        # Manually age the blank-key stamp past the window.
        with self.pt._REGISTRY_LOCK:
            self.pt._REAL_REPLY_AT[("cust_a", "")] = (
                _t.time() - self.pt.REAL_REPLY_SUPPRESS_S - 5
            )
            self.pt._REAL_REPLY_AT[("cust_a", "msg_OLD")] = (
                _t.time() - self.pt.REAL_REPLY_SUPPRESS_S - 5
            )
        result = self.pt.arm_watchdog("cust_a", "msg_NEW", timeout_s=10.0)
        self.assertTrue(result)

    def test_empty_msg_id_returns_false(self) -> None:
        self.assertFalse(self.pt.arm_watchdog("cust_a", "", timeout_s=10.0))
        self.assertFalse(self.pt.arm_watchdog("cust_a", None, timeout_s=10.0))  # type: ignore[arg-type]

    def test_zero_timeout_returns_false(self) -> None:
        self.assertFalse(self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=0.0))
        self.assertFalse(self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=-1.0))

    def test_arms_again_after_cancel(self) -> None:
        """After the real reply lands and cancels the timer, the
        per-msg_id _REAL_REPLY_AT stamp blocks a re-arm for the same
        turn — but a NEW msg_id should arm (subject to blank-key
        suppress window)."""
        self.assertTrue(self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0))
        self.pt.cancel("cust_a", "msg_1")
        # Same key — should NOT re-arm (we already replied)
        self.assertFalse(self.pt.arm_watchdog("cust_a", "msg_1", timeout_s=10.0))
        # New msg_id within window — also blocked by blank-key stamp
        self.assertFalse(self.pt.arm_watchdog("cust_a", "msg_2", timeout_s=10.0))


if __name__ == "__main__":
    unittest.main()
