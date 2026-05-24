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


if __name__ == "__main__":
    unittest.main()
