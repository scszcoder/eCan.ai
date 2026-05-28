"""Source-level guards for the 2026-05-11 flood-test hardening:

Observed: a 20-customer flood (multi-modal messages) left ~13 customers
with no reply and ~1-minute first-response latency.  Root causes from
``runlogs/eCan.log`` (2026-05-11 16:11-16:13):

1. The pre-dispatch DOM scrape (``scrape_latest_customer_bubble``) and the
   ``feige_open_session`` / ``feige_list_sessions`` evals were called
   *without* a resolved ``target_id``, so each paid ~3s of ``session_ms``
   in browser-use's ``ensure_valid_focus`` round-trip — the single biggest
   latency item in the trace.
2. The scrape eval had no ``trace_label`` (``action=unknown``) so it got
   the tight 6s timeout instead of the 12s feige family timeout, and on
   timeout it called ``_record_cdp_evaluate_recovery_signal`` with the
   non-feige threshold (2) — two scrape timeouts invalidated the *shared*
   BrowserSession, producing ``missing_browser_session`` cascades that
   knocked out HOT-PATH-B direct delivery for every customer.
3. An 8s CDP-health cooldown + a 20s direct-delivery circuit (threshold 1)
   meant one slow send froze the whole delivery path.

Fixes asserted here:
* ``_evaluate_js`` gains a ``read_only`` param; read-only timeouts skip
  ``mark_feige_cdp_unhealthy`` and ``_record_cdp_evaluate_recovery_signal``.
* ``_evaluate_feige_js`` helper resolves the Feige target id and runs with
  ``focus=False``; ``feige_open_session`` / ``feige_list_sessions`` /
  ``feige_get_chat_thread`` use it.
* ``scrape_latest_customer_bubble`` and ``_ensure_feige_current_subtab``
  run their evals against the cached Feige target with
  ``trace_label="feige_scrape_bubble"`` / ``"feige_select_subtab"`` and
  ``read_only=True``.
* Recovery thresholds bumped (1/2 → 3), CDP-health cooldown 8s → 4s,
  direct-delivery circuit threshold 1 → 2 and cooldown 20s → 6s.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SVC = Path("agent/ec_skills/browser_use_extension/extension_tools_service.py")
_DOM = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/dom_assets.py")
_RUNNER = Path("agent/ec_tasks/runner.py")


class TestEvaluateJsReadOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = _SVC.read_text(encoding="utf-8")

    def _evaluate_js_body(self) -> str:
        i = self.svc.index("async def _evaluate_js(")
        j = self.svc.index("\nasync def ", i + 1)
        return self.svc[i:j]

    def test_signature_has_read_only(self):
        body = self._evaluate_js_body()
        self.assertIn("read_only: bool = False", body)

    def test_read_only_timeout_skips_unhealthy_and_recovery(self):
        body = self._evaluate_js_body()
        start = body.index("except asyncio.TimeoutError")
        end = body.index("raise TimeoutError(", start)
        handler = body[start:end]
        # The read-only branch must come before mark_feige_cdp_unhealthy /
        # _record_cdp_evaluate_recovery_signal, and those two must be in the
        # `else:` (i.e. NOT read-only) arm.
        self.assertIn("if read_only:", handler)
        self.assertIn("[CDP-EVAL][READ-ONLY-TIMEOUT]", handler)
        ro_idx = handler.index("if read_only:")
        unhealthy_idx = handler.index("mark_feige_cdp_unhealthy(")
        recovery_idx = handler.index("_record_cdp_evaluate_recovery_signal(")
        self.assertLess(ro_idx, unhealthy_idx)
        self.assertLess(ro_idx, recovery_idx)
        # And the else: that guards them sits between.
        else_after_ro = handler.index("else:", ro_idx)
        self.assertLess(else_after_ro, unhealthy_idx)
        self.assertLess(else_after_ro, recovery_idx)


class TestEvaluateFeigeJsHelper(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.svc = _SVC.read_text(encoding="utf-8")

    def test_helper_defined(self):
        self.assertIn("async def _evaluate_feige_js(", self.svc)

    def test_helper_resolves_target_and_uses_focus_false(self):
        i = self.svc.index("async def _evaluate_feige_js(")
        j = self.svc.index("\ndef ", i + 1)
        body = self.svc[i:j]
        self.assertIn("_resolve_feige_tab_target_id_bounded(browser_session)", body)
        self.assertIn("focus=False", body)
        self.assertIn('"fallback_target": True', body)

    def test_feige_tools_use_helper(self):
        # feige_open_session, feige_list_sessions, feige_get_chat_thread
        for fn in ("feige_open_session", "feige_list_sessions", "feige_get_chat_thread"):
            i = self.svc.index(f"async def {fn}(")
            j = self.svc.index("\nasync def ", i + 1) if "\nasync def " in self.svc[i + 1:] else len(self.svc)
            # find next top-level def of any kind
            k = self.svc.index("\n@custom_controller.action", i + 1) if "\n@custom_controller.action" in self.svc[i + 1:] else j
            body = self.svc[i:min(j, k) if k > i else j]
            self.assertIn("_evaluate_feige_js(", body, f"{fn} should call _evaluate_feige_js")

    def test_read_only_evals_marked(self):
        # feige_list_sessions / feige_get_chat_thread are reads → read_only=True
        for fn in ("feige_list_sessions", "feige_get_chat_thread"):
            i = self.svc.index(f"async def {fn}(")
            body = self.svc[i:i + 1500]
            self.assertIn("read_only=True", body, f"{fn} eval should be read_only=True")


class TestScrapePathHardening(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dom = _DOM.read_text(encoding="utf-8")

    def test_scrape_uses_cached_target_and_read_only(self):
        i = self.dom.index("async def scrape_latest_customer_bubble(")
        j = self.dom.index("\nasync def ", i + 1) if "\nasync def " in self.dom[i + 1:] else len(self.dom)
        body = self.dom[i:j]
        self.assertIn("_SESSION_FOCUSED_FEIGE_TID_ATTR", body)
        self.assertIn('trace_label="feige_scrape_bubble"', body)
        self.assertIn("read_only=True", body)
        self.assertIn("focus=False", body)

    def test_ensure_current_subtab_labeled_and_read_only(self):
        i = self.dom.index("async def _ensure_feige_current_subtab(")
        j = self.dom.index("\nasync def ", i + 1)
        body = self.dom[i:j]
        self.assertIn('trace_label="feige_select_subtab"', body)
        self.assertIn("read_only=True", body)


class TestHardenedConstants(unittest.TestCase):
    def test_recovery_thresholds_bumped(self):
        svc = _SVC.read_text(encoding="utf-8")
        self.assertIn('"ECAN_CDP_EVALUATE_RECOVERY_THRESHOLD", "3"', svc)
        self.assertIn('"ECAN_FEIGE_CDP_EVALUATE_RECOVERY_THRESHOLD", "3"', svc)

    def test_cdp_health_cooldown_reduced(self):
        svc = _SVC.read_text(encoding="utf-8")
        self.assertIn('"ECAN_FEIGE_CDP_HEALTH_COOLDOWN_S", "4.0"', svc)
        # Old 8.0 default must be gone.
        self.assertNotIn('"ECAN_FEIGE_CDP_HEALTH_COOLDOWN_S", "8.0"', svc)

    def test_direct_circuit_relaxed(self):
        runner = _RUNNER.read_text(encoding="utf-8")
        self.assertIn('"DIRECT_FEIGE_CDP_TIMEOUT_CIRCUIT_THRESHOLD", "2"', runner)
        self.assertIn('"DIRECT_FEIGE_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S", "6.0"', runner)
        self.assertNotIn('"DIRECT_FEIGE_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S", "20.0"', runner)


class TestRuntimeValuesLoaded(unittest.TestCase):
    """Confirm the constants actually evaluate to the new values (catches a
    typo in the env-default string that would silently fall through)."""

    def test_extension_tools_constants(self):
        import agent.ec_skills.browser_use_extension.extension_tools_service as ets
        self.assertEqual(ets._CDP_EVALUATE_RECOVERY_THRESHOLD, 3)
        self.assertEqual(ets._FEIGE_CDP_EVALUATE_RECOVERY_THRESHOLD, 3)
        self.assertEqual(ets._FEIGE_CDP_HEALTH_COOLDOWN_S, 4.0)

    def test_runner_circuit_constants(self):
        import agent.ec_tasks.runner as runner
        self.assertEqual(runner._DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_THRESHOLD, 2)
        self.assertEqual(runner._DIRECT_LIVE_CHAT_CDP_TIMEOUT_CIRCUIT_COOLDOWN_S, 6.0)


if __name__ == "__main__":
    unittest.main()
