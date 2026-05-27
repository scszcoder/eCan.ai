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
        # set True somewhere inside it.
        baselined_log = PD_SRC.find('"[BrowserAutomation] mt017 baselined latest agent "')
        self.assertGreater(baselined_log, -1, "mt017 baselined log line missing")
        # Look 200 chars after the log for the flag assignment.
        window = PD_SRC[baselined_log:baselined_log + 600]
        self.assertIn(
            "_agent_bubble_is_pre_existing_baseline = True",
            window,
            "just-baselined branch must mark the bubble as pre-existing",
        )

    def test_flag_set_true_in_matches_baseline_branch(self) -> None:
        # The "elif _lab_msg_id and _lab_msg_id == baseline:" branch
        # must also set the flag (not just pass).
        elif_branch = PD_SRC.find("elif _lab_msg_id and _lab_msg_id == baseline:")
        self.assertGreater(elif_branch, -1)
        # Read the next 400 chars to capture the branch body.
        window = PD_SRC[elif_branch:elif_branch + 400]
        self.assertIn(
            "_agent_bubble_is_pre_existing_baseline = True",
            window,
            "matches-baseline branch must also mark the bubble pre-existing",
        )

    def test_mt030_check_consults_flag(self) -> None:
        # The mt030 skip condition must include `not <flag>`.
        m = re.search(
            r"if\s*\(\s*\n\s*_agent_index >= 0\s*\n\s*and _scraped_cust_index >= 0\s*\n\s*and _agent_index > _scraped_cust_index\s*\n\s*and not _agent_bubble_is_pre_existing_baseline\s*\n\s*\)\s*:",
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
        body = RUNNER_SRC_046[start:start + 3500]
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
        ok_idx = RUNNER_SRC_046.find('if _ok:\n                try:\n                    from agent.ec_tasks.feige_delivery_durability import clear_pending_delivery')
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
        body = RAG_SRC_047[start:start + 2000]
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

    def test_default_off(self) -> None:
        # No env var = no behaviour change.  The guard must compare to
        # truthy literals, NOT just any non-empty string (otherwise
        # ECAN_RAG_QUERY_FAST_PATH=false would also enable it).
        self.assertIn(
            'if _fast_path_env in ("1", "true", "yes", "on"):',
            RAG_SRC_047,
        )


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
        self.assertIn("人工服务正在回复中", PH_SRC_048)
        self.assertIn("人工服务仍在回复中，请稍等", PH_SRC_048)
        self.assertIn("人工服务核实中，马上回复您", PH_SRC_048)

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
        start = RUNNER_SRC_048B.find(
            "if _hi_target_qid and _hi_dd.is_question_handled("
        )
        self.assertGreater(start, -1)
        body = RUNNER_SRC_048B[start:start + 7000]
        self.assertIn("human_relevance_judge", body)
        self.assertIn("_mt048b_verdict = _mt048b_judge_mod.judge(", body)
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
        body = RUNNER_SRC_048B[start:start + 7000]
        self.assertIn("_mt048b_drop = True", body)
        # The except branch must explicitly re-assert drop = True.
        self.assertIn("falling back to drop", body)

    def test_runner_logs_judge_telemetry(self) -> None:
        # Ledger annotations so future log digs can audit judge decisions.
        start = RUNNER_SRC_048B.find(
            "if _hi_target_qid and _hi_dd.is_question_handled("
        )
        body = RUNNER_SRC_048B[start:start + 7000]
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


if __name__ == "__main__":
    unittest.main()
