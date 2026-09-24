"""Cloud reporting for business-outcome metering (agent/ec_skills/metering_reporter.py).

metering.py records locally and must never fail the delivery path it measures.
This module ships those local rows to the cloud on its own schedule, and the
same non-negotiable applies one level up: a reporting failure — no DB, no
endpoint, signed out, network down, a server error, a partially-rejected
batch — must never raise, and must never lose an event. "Left pending" is
always the safe outcome; the server's idempotency_key dedupe is what makes
retrying it free.
"""

from __future__ import annotations

import unittest
from unittest import mock

from agent.ec_skills import metering_reporter as reporter


def _row(key: str, **overrides) -> dict:
    row = {
        "id": f"ue_{key}",
        "idempotency_key": key,
        "scenario_code": "cs_chat",
        "meter_code": "message_replied",
        "quantity": 1,
        "owner": "acct-1",
        "store_id": "S1",
        "agent_id": None,
        "task_id": None,
        "skill_id": "feige_chat",
        "vehicle_id": None,
        "occurred_at": "2026-09-22T12:00:00",
        "reported_at": None,
        "status": "pending",
        "evidence": '{"customer": "c1", "source_msg_id": "m1"}',
        "cost_basis": None,
        "source": "client",
    }
    row.update(overrides)
    return row


class NoServiceTests(unittest.TestCase):
    def test_no_db_manager_returns_zero_and_does_not_raise(self) -> None:
        with mock.patch.object(reporter, "_service", return_value=None):
            result = reporter.report_pending()
        self.assertEqual(result, {"sent": 0, "accepted": 0, "duplicates": 0, "rejected": 0, "left_pending": 0})

    def test_no_pending_rows_is_a_no_op(self) -> None:
        svc = mock.Mock()
        svc.get_unreported_events.return_value = []
        with mock.patch.object(reporter, "_service", return_value=svc):
            result = reporter.report_pending()
        self.assertEqual(result["sent"], 0)
        svc.mark_reported.assert_not_called()

    def test_read_failure_degrades_quietly(self) -> None:
        svc = mock.Mock()
        svc.get_unreported_events.side_effect = RuntimeError("db locked")
        with mock.patch.object(reporter, "_service", return_value=svc):
            result = reporter.report_pending()  # must not raise
        self.assertEqual(result["sent"], 0)


class TransportGuardTests(unittest.TestCase):
    """Every way the network step can fail must leave events local and unsent."""

    def setUp(self) -> None:
        self.svc = mock.Mock()
        self.svc.get_unreported_events.return_value = [_row("k1"), _row("k2")]
        self.service_patch = mock.patch.object(reporter, "_service", return_value=self.svc)
        self.service_patch.start()

    def tearDown(self) -> None:
        self.service_patch.stop()

    def test_no_endpoint_configured_leaves_batch_pending(self) -> None:
        with mock.patch.object(reporter, "_account_manager_url", return_value=""):
            result = reporter.report_pending()
        self.assertEqual(result["left_pending"], 2)
        self.svc.mark_reported.assert_not_called()

    def test_signed_out_leaves_batch_pending(self) -> None:
        with mock.patch.object(reporter, "_account_manager_url", return_value="https://x/ecbAccountManager"):
            with mock.patch.object(reporter, "_bearer_token", return_value=""):
                result = reporter.report_pending()
        self.assertEqual(result["left_pending"], 2)
        self.svc.mark_reported.assert_not_called()

    def test_network_error_leaves_batch_pending_and_does_not_raise(self) -> None:
        with mock.patch.object(reporter, "_account_manager_url", return_value="https://x/ecbAccountManager"):
            with mock.patch.object(reporter, "_bearer_token", return_value="tok"):
                with mock.patch.object(reporter, "_post", side_effect=OSError("network down")):
                    result = reporter.report_pending()  # must not raise
        self.assertEqual(result["left_pending"], 2)
        self.svc.mark_reported.assert_not_called()

    def test_server_error_status_leaves_batch_pending(self) -> None:
        with mock.patch.object(reporter, "_account_manager_url", return_value="https://x/ecbAccountManager"):
            with mock.patch.object(reporter, "_bearer_token", return_value="tok"):
                with mock.patch.object(reporter, "_post", return_value={"_http_status": 500, "success": False}):
                    result = reporter.report_pending()
        self.assertEqual(result["left_pending"], 2)
        self.svc.mark_reported.assert_not_called()


class HappyPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [_row("k1"), _row("k2"), _row("k3")]
        self.svc = mock.Mock()
        self.svc.get_unreported_events.return_value = self.rows
        self.svc.mark_reported.side_effect = lambda ids: len(ids)
        self.patches = [
            mock.patch.object(reporter, "_service", return_value=self.svc),
            mock.patch.object(reporter, "_account_manager_url", return_value="https://x/ecbAccountManager"),
            mock.patch.object(reporter, "_bearer_token", return_value="tok"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self) -> None:
        for p in self.patches:
            p.stop()

    def test_all_accepted_marks_every_row_reported(self) -> None:
        with mock.patch.object(reporter, "_post", return_value={"_http_status": 200, "success": True, "accepted": 3, "duplicates": 0, "rejected": []}):
            result = reporter.report_pending()
        self.assertEqual(result, {"sent": 3, "accepted": 3, "duplicates": 0, "rejected": 0, "left_pending": 0})
        self.svc.mark_reported.assert_called_once()
        self.assertEqual(sorted(self.svc.mark_reported.call_args[0][0]), ["ue_k1", "ue_k2", "ue_k3"])

    def test_duplicates_are_cleared_locally_same_as_accepted(self) -> None:
        """A duplicate means the CLOUD already has it — nothing left to send."""
        with mock.patch.object(reporter, "_post", return_value={"_http_status": 200, "success": True, "accepted": 1, "duplicates": 2, "rejected": []}):
            result = reporter.report_pending()
        self.assertEqual(result["left_pending"], 0)
        self.assertEqual(sorted(self.svc.mark_reported.call_args[0][0]), ["ue_k1", "ue_k2", "ue_k3"])

    def test_rejected_rows_are_not_marked_reported(self) -> None:
        with mock.patch.object(reporter, "_post", return_value={
            "_http_status": 200, "success": True, "accepted": 2, "duplicates": 0,
            "rejected": [{"idempotency_key": "k2", "reason": "unknown_meter"}],
        }):
            result = reporter.report_pending()
        self.assertEqual(result["rejected"], 1)
        self.assertEqual(result["left_pending"], 1)
        cleared = sorted(self.svc.mark_reported.call_args[0][0])
        self.assertEqual(cleared, ["ue_k1", "ue_k3"])
        self.assertNotIn("ue_k2", cleared)

    def test_wire_event_omits_account_id_server_resolves_from_the_token(self) -> None:
        captured = {}

        def fake_post(url, token, body):
            captured["body"] = body
            return {"_http_status": 200, "success": True, "accepted": 3, "duplicates": 0, "rejected": []}

        with mock.patch.object(reporter, "_post", side_effect=fake_post):
            reporter.report_pending()
        for ev in captured["body"]["events"]:
            self.assertNotIn("account_id", ev)
            self.assertNotIn("owner", ev)
        self.assertEqual(captured["body"]["action"], "report_usage_event")

    def test_evidence_json_text_is_parsed_back_to_an_object(self) -> None:
        captured = {}

        def fake_post(url, token, body):
            captured["body"] = body
            return {"_http_status": 200, "success": True, "accepted": 3, "duplicates": 0, "rejected": []}

        with mock.patch.object(reporter, "_post", side_effect=fake_post):
            reporter.report_pending()
        ev = captured["body"]["events"][0]
        self.assertEqual(ev["evidence"], {"customer": "c1", "source_msg_id": "m1"})


class LoopLifecycleTests(unittest.TestCase):
    def tearDown(self) -> None:
        reporter.stop()

    def test_start_is_idempotent(self) -> None:
        with mock.patch.object(reporter, "_run_loop"):
            t1 = reporter.start(interval_seconds=3600)
            t2 = reporter.start(interval_seconds=3600)
        self.assertIsNotNone(t1)
        self.assertIsNone(t2, "a second start() while already running must be a no-op")

    def test_stop_allows_a_fresh_start(self) -> None:
        with mock.patch.object(reporter, "_run_loop"):
            reporter.start(interval_seconds=3600)
            reporter.stop()
            t2 = reporter.start(interval_seconds=3600)
        self.assertIsNotNone(t2)


if __name__ == "__main__":
    unittest.main()
