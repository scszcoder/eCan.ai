import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


class CrashBoundaryTests(unittest.TestCase):
    def test_reports_previous_unexpected_process_boundary(self):
        from utils import crash_boundary as cb

        with tempfile.TemporaryDirectory() as td:
            hb = cb.heartbeat_path(td)
            hb.write_text(
                json.dumps(
                    {
                        "pid": 99999999,
                        "process_create_time": 1.0,
                        "updated_at": 10.0,
                        "updated_at_iso": "1970-01-01T00:00:10+00:00",
                        "phase": "feige:send",
                        "rss_mb": 6999.0,
                        "clean_exit": False,
                    }
                ),
                encoding="utf-8",
            )
            with patch.object(cb, "collect_windows_termination_evidence", return_value={"wer_reports": []}):
                report = cb.report_previous_process_boundary(td)

            self.assertTrue(report["unexpected"])
            self.assertEqual(report["reason"], "previous_process_died_unexpectedly")
            self.assertEqual(report["previous"]["phase"], "feige:send")
            self.assertTrue(cb.report_path(td).exists())

    def test_clean_exit_marker_suppresses_unexpected_report(self):
        from utils import crash_boundary as cb

        with tempfile.TemporaryDirectory() as td:
            monitor = cb.CrashBoundaryHeartbeat(log_dir=td, interval_s=60)
            monitor.write()
            monitor.stop("unit_test")
            report = cb.report_previous_process_boundary(td)

            self.assertFalse(report["unexpected"])


class FeigeDeliveryDurabilityTests(unittest.TestCase):
    def _payload(self):
        return {
            "customer_id": "CustomerA",
            "customer_name": "CustomerA",
            "response_text": "reply",
            "source_customer_msg_id": "msg-1",
        }

    def test_record_clear_and_startup_abort_pending_delivery(self):
        import agent.ec_skills.browser_use_extension.hooks.external.feige_chat.delivery_durability as fd

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pending.json"
            with patch.object(fd, "_state_path", return_value=path):
                key = fd.record_pending_delivery(self._payload(), source="unit")
                self.assertTrue(key)
                self.assertEqual(len(fd.snapshot_pending_deliveries()), 1)

                fd.clear_pending_delivery(self._payload())
                self.assertEqual(fd.snapshot_pending_deliveries(), [])

                fd.record_pending_delivery(self._payload(), source="unit")
                aborted = fd.abort_pending_from_previous_process("unit_previous_death")
                self.assertEqual(aborted, 1)
                self.assertEqual(fd.snapshot_pending_deliveries(), [])


class BrowserRecoveryTests(unittest.TestCase):
    def test_invalidate_browser_session_removes_cache_and_preserves_focus(self):
        from agent.ec_skills.browser_node import build_helpers as bh

        session = SimpleNamespace(id="s1", agent_focus_target_id="target-1234")
        old_sessions = dict(bh.cached_browser_sessions)
        old_focus = dict(bh.last_known_focus_target_ids)
        old_agents = dict(bh.cached_bu_agents)
        try:
            bh.cached_browser_sessions.clear()
            bh.last_known_focus_target_ids.clear()
            bh.cached_bu_agents.clear()
            bh.cached_browser_sessions["node:frontdesk"] = session
            bh.cached_bu_agents["node:frontdesk"] = object()

            removed = bh.invalidate_browser_session_for_recovery(
                session,
                reason="unit_cdp_timeout",
                stop_worker=False,
            )

            self.assertTrue(removed)
            self.assertNotIn("node:frontdesk", bh.cached_browser_sessions)
            self.assertNotIn("node:frontdesk", bh.cached_bu_agents)
            self.assertEqual(bh.last_known_focus_target_ids["node:frontdesk"], "target-1234")
            self.assertTrue(getattr(session, "_ecan_force_recreate"))
        finally:
            bh.cached_browser_sessions.clear()
            bh.cached_browser_sessions.update(old_sessions)
            bh.last_known_focus_target_ids.clear()
            bh.last_known_focus_target_ids.update(old_focus)
            bh.cached_bu_agents.clear()
            bh.cached_bu_agents.update(old_agents)

    def test_release_browser_cache_pressure_preserves_chat_scopes_until_critical(self):
        from agent.ec_skills.browser_node import build_helpers as bh

        old_sessions = dict(bh.cached_browser_sessions)
        try:
            bh.cached_browser_sessions.clear()
            bh.cached_browser_sessions["node:frontdesk"] = SimpleNamespace(id="node")
            bh.cached_browser_sessions["chat:customer"] = SimpleNamespace(id="chat")

            removed = bh.release_browser_cache_pressure("unit", aggressive=False)
            self.assertEqual(removed, 1)
            self.assertNotIn("node:frontdesk", bh.cached_browser_sessions)
            self.assertIn("chat:customer", bh.cached_browser_sessions)

            removed = bh.release_browser_cache_pressure("unit", aggressive=True)
            self.assertEqual(removed, 1)
            self.assertEqual(bh.cached_browser_sessions, {})
        finally:
            bh.cached_browser_sessions.clear()
            bh.cached_browser_sessions.update(old_sessions)


class CdpRecoverySignalTests(unittest.TestCase):
    def test_repeated_eval_timeouts_invalidate_browser_session(self):
        import agent.ec_skills.browser_use_extension.extension_tools_service as ets

        session = SimpleNamespace(id="s1")
        old_threshold = ets._CDP_EVALUATE_RECOVERY_THRESHOLD
        try:
            ets._CDP_EVALUATE_RECOVERY_THRESHOLD = 2
            ets._CDP_EVALUATE_TIMEOUT_RECOVERY.clear()
            with patch(
                "agent.ec_skills.browser_node.build_helpers.invalidate_browser_session_for_recovery",
                return_value=True,
            ) as mocked:
                ets._record_cdp_evaluate_recovery_signal(session, "generic_action", "Runtime.evaluate")
                mocked.assert_not_called()
                ets._record_cdp_evaluate_recovery_signal(session, "generic_action", "Runtime.evaluate")
                mocked.assert_called_once()
        finally:
            ets._CDP_EVALUATE_RECOVERY_THRESHOLD = old_threshold
            ets._CDP_EVALUATE_TIMEOUT_RECOVERY.clear()


    def test_feige_eval_timeout_invalidates_after_first_timeout_and_marks_health(self):
        import agent.ec_skills.browser_use_extension.extension_tools_service as ets

        session = SimpleNamespace(id="s1")
        old_feige_threshold = ets._LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD
        try:
            ets._LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD = 1
            ets._CDP_EVALUATE_TIMEOUT_RECOVERY.clear()
            ets.mark_live_chat_cdp_healthy()
            with patch(
                "agent.ec_skills.browser_node.build_helpers.invalidate_browser_session_for_recovery",
                return_value=True,
            ) as mocked:
                ets.mark_live_chat_cdp_unhealthy("unit", cooldown_s=5.0)
                ets._record_cdp_evaluate_recovery_signal(session, "feige_open_session", "Runtime.evaluate")
                mocked.assert_called_once()
                self.assertGreater(ets.live_chat_cdp_health_cooldown_remaining(), 0.0)
        finally:
            ets._LIVE_CHAT_CDP_EVALUATE_RECOVERY_THRESHOLD = old_feige_threshold
            ets._CDP_EVALUATE_TIMEOUT_RECOVERY.clear()
            ets.mark_live_chat_cdp_healthy()


class MemorySelfProtectionTests(unittest.TestCase):
    def test_high_rss_handler_releases_browser_cache_pressure(self):
        from utils.memory_monitor import MemoryMonitor

        monitor = MemoryMonitor(rss_protect_mb=1, rss_critical_mb=2)
        with patch(
            "agent.ec_skills.browser_node.build_helpers.release_browser_cache_pressure",
            return_value=3,
        ) as mocked:
            monitor._handle_high_rss(9000.0, critical=True)

        mocked.assert_called_once_with(reason="memory_critical", aggressive=True)

    def test_feige_high_rss_marks_cdp_unhealthy_and_releases_cache_pressure(self):
        from utils.memory_monitor import MemoryMonitor

        # The handler resolves the CDP-health marker through the live-chat
        # runner bridge; import the reference bundle so it is registered.
        import agent.ec_skills.browser_use_extension.hooks.external.feige_chat  # noqa: F401

        monitor = MemoryMonitor(rss_live_chat_protect_mb=1, rss_protect_mb=10, rss_critical_mb=20)
        with patch(
            "agent.ec_skills.browser_node.build_helpers.release_browser_cache_pressure",
            return_value=2,
        ) as mocked:
            with patch(
                "agent.ec_skills.browser_use_extension.extension_tools_service.mark_live_chat_cdp_unhealthy",
                return_value=5.0,
            ) as marker:
                monitor._handle_live_chat_high_rss(6500.0)

        mocked.assert_called_once_with(reason="memory_live_chat_protect", aggressive=False)
        marker.assert_called_once()


if __name__ == "__main__":
    unittest.main()
