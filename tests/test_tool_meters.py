"""MCP tool outcomes: declared by the tool, recorded by the platform, attributed to the store."""

import json
import unittest
from types import SimpleNamespace
from unittest import mock

from agent.mcp import tool_meters as tm


def _text(obj):
    return [SimpleNamespace(type="text", text=json.dumps(obj))]


class _Recorder:
    """Stands in for the usage-event DB service; keeps what metering.emit wrote."""

    def __init__(self):
        self.rows = []

    def record_event(self, row):
        if any(r["idempotency_key"] == row["idempotency_key"] for r in self.rows):
            return False
        self.rows.append(row)
        return True


class ToolMeterTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(tm._TOOL_METERS)
        tm._TOOL_METERS.clear()
        self.addCleanup(lambda: (tm._TOOL_METERS.clear(), tm._TOOL_METERS.update(self._saved)))
        tm.declare_tool_meter("create_listing", scenario_code="listing", meter_code="listing_created",
                              outcome_id_field="listing_id", display_name_zh="刊登商品",
                              display_name_en="Listing created", unit="个")
        self.db = _Recorder()
        p = mock.patch("agent.ec_skills.metering._service", return_value=self.db)
        p.start()
        self.addCleanup(p.stop)

    def test_a_successful_call_is_recorded_once_per_outcome(self):
        self.assertTrue(tm.record_tool_outcome("create_listing", _text({"listing_id": "L1"})))
        self.assertFalse(tm.record_tool_outcome("create_listing", _text({"listing_id": "L1"})),
                         "a retried call returning the same listing is not counted twice")
        self.assertEqual([r["idempotency_key"] for r in self.db.rows], ["tool:create_listing:L1"])
        self.assertEqual((self.db.rows[0]["scenario_code"], self.db.rows[0]["meter_code"]),
                         ("listing", "listing_created"))

    def test_errors_missing_ids_and_undeclared_tools_record_nothing(self):
        self.assertFalse(tm.record_tool_outcome("create_listing",
                                                {"isError": True, "content": [{"type": "text", "text": '{"listing_id": "L2"}'}]}))
        with mock.patch.object(tm.logger, "warning") as warn:
            self.assertFalse(tm.record_tool_outcome("create_listing", _text({"ok": True})))
        warn.assert_called_once()
        self.assertFalse(tm.record_tool_outcome("some_other_tool", _text({"listing_id": "L3"})))
        self.assertEqual(self.db.rows, [])

    def test_the_outcome_is_attributed_to_the_callers_store_across_the_hop(self):
        from utils.log_scope import scope
        with scope(store_id="shop-a", agent_id="ag1", task_id="t1", agent_name="not sent"):
            meta = tm.scope_meta()                       # client side
        self.assertEqual(meta, {tm.META_KEY: {"store_id": "shop-a", "agent_id": "ag1", "task_id": "t1"}})
        # server side: a fresh context with no scope of its own
        fields = tm.scope_from_meta(SimpleNamespace(**meta))
        with scope(**fields):
            tm.record_tool_outcome("create_listing", _text({"listing_id": "L9"}))
        row = self.db.rows[-1]
        self.assertEqual((row["store_id"], row["agent_id"], row["task_id"]), ("shop-a", "ag1", "t1"))

    def test_meta_accepts_only_attribution_fields(self):
        self.assertEqual(tm.scope_from_meta({tm.META_KEY: {"store_id": "s", "evil": "x"}}), {"store_id": "s"})
        self.assertEqual(tm.scope_from_meta(None), {})

    def test_the_stores_page_shows_tool_meters_by_name(self):
        from agent.ec_skills.meter_registry import describe
        d = describe("listing", "listing_created")
        self.assertEqual((d["display_name_zh"], d["source"]), ("刊登商品", "tool:create_listing"))

    def test_declaring_needs_an_outcome_id_field(self):
        with self.assertRaises(ValueError):
            tm.declare_tool_meter("x", scenario_code="a", meter_code="b", outcome_id_field="")


class CloudDirectTests(unittest.TestCase):
    def test_a_declared_tool_called_in_process_is_recorded_too(self):
        from agent.ec_skills import build_node as bn
        fake_mod = SimpleNamespace()

        async def create_listing(main_win, args):
            return _text({"listing_id": "L7"})
        fake_mod.create_listing = create_listing
        tm._TOOL_METERS["create_listing"] = {"scenario_code": "listing", "meter_code": "listing_created",
                                             "outcome_id_field": "listing_id"}
        self.addCleanup(tm._TOOL_METERS.pop, "create_listing", None)
        # record_tool_outcome is patched BEFORE import_module, which mock.patch
        # itself uses to resolve targets.
        with mock.patch("agent.mcp.tool_meters.record_tool_outcome") as rec, \
             mock.patch.dict(bn._CLOUD_TOOL_REGISTRY, {"create_listing": ("fake_mod", "create_listing")}), \
             mock.patch("importlib.import_module", return_value=fake_mod):
            import asyncio
            fn = bn._resolve_cloud_tool_func("create_listing")
            asyncio.run(fn(None, {}))
        rec.assert_called_once()
        self.assertEqual(rec.call_args.args[0], "create_listing")


class WiringTests(unittest.TestCase):
    def test_the_server_handler_restores_scope_and_records(self):
        from pathlib import Path
        src = Path("agent/mcp/server/server.py").read_text(encoding="utf-8")
        i = src.index("async def unified_tool_handler")
        body = src[i:i + 4000]
        self.assertIn("scope_from_meta(meca_mcp_server.request_context.meta)", body)
        self.assertLess(body.index("with _log_scope(**_scope_fields):"), body.index("record_tool_outcome(tool_name, toolResult)"))

    def test_the_client_sends_its_scope_as_meta(self):
        from pathlib import Path
        src = Path("agent/mcp/local_client.py").read_text(encoding="utf-8")
        self.assertIn("meta=scope_meta()", src)
        self.assertEqual(src.count("session.call_tool(tool_name, arguments, meta=meta)"), 2)


if __name__ == "__main__":
    unittest.main()
