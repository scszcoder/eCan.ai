"""Business-outcome metering, shadow slice (2026-09-21).

Tier 1 bills per delivered reply instead of per token. The two things that can
silently make that wrong are both about WHERE the event is emitted, so they are
pinned here as source assertions rather than left to review:

  * emitting at `mark_real_reply_delivered` would bill ATTEMPTS — that call
    stamps "real reply in progress" BEFORE the send eval runs.
  * emitting on `_outcome.ok` alone would bill turns a HUMAN answered, because
    the human-intervention path also sets ok=True (reason
    `human_intervention_skip`).

The rest covers idempotency (one delivered turn, observed many times, must be
one billable row) and the platform-purity rule: no business meaning in platform
files.
"""

from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

RUNNER_SRC = Path("agent/ec_tasks/runner.py").read_text(encoding="utf-8")
METERING_SRC = Path("agent/ec_skills/metering.py").read_text(encoding="utf-8")
BRIDGE_SRC = Path(
    "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/runner_bridge.py"
).read_text(encoding="utf-8")


class EmissionPointTests(unittest.TestCase):
    """The delivery-confirmed point, and the two near-misses around it."""

    def test_emits_in_the_all_ok_branch(self) -> None:
        idx = RUNNER_SRC.find('_outcome.reason = "all_ok"')
        self.assertGreater(idx, -1, "the success branch moved")
        block = RUNNER_SRC[idx:idx + 1800]
        self.assertIn("billable_delivery_meter()", block)
        self.assertIn("metering", block)
        self.assertIn("billable_delivery_key(", block)

    def test_does_not_emit_at_the_in_progress_stamp(self) -> None:
        """mark_real_reply_delivered fires BEFORE the send eval — emitting
        there bills attempts, including ones that never reach the customer."""
        idx = RUNNER_SRC.find("mark_real_reply_delivered(")
        self.assertGreater(idx, -1)
        # Window covers that call site and its immediate handling.
        block = RUNNER_SRC[idx:idx + 1200]
        self.assertNotIn("metering.emit", block)
        self.assertNotIn("billable_delivery_meter", block)

    def test_human_answered_turn_is_not_billable(self) -> None:
        """The human-intervention path sets ok=True too; it must not emit."""
        idx = RUNNER_SRC.find('_outcome.reason = "human_intervention_skip"')
        self.assertGreater(idx, -1)
        block = RUNNER_SRC[max(0, idx - 1500):idx + 400]
        self.assertNotIn("metering.emit", block)
        self.assertNotIn("billable_delivery_meter", block)

    def test_emission_is_guarded(self) -> None:
        """Metering must never break the path it measures."""
        idx = RUNNER_SRC.find("billable_delivery_meter()")
        block = RUNNER_SRC[max(0, idx - 400):idx + 1200]
        self.assertIn("try:", block)
        self.assertIn("except Exception", block)


class PlatformPurityTests(unittest.TestCase):
    """Business meaning stays in the bundle (standing directive)."""

    def test_platform_files_name_no_site_and_no_meter_codes(self) -> None:
        for name, src in (("runner.py", RUNNER_SRC), ("metering.py", METERING_SRC)):
            with self.subTest(file=name):
                self.assertNotIn("feige", src.lower())
                self.assertNotIn("cs_chat", src)
                self.assertNotIn("message_replied", src)

    def test_the_bundle_owns_the_meter_identity(self) -> None:
        self.assertIn("def billable_delivery_meter", BRIDGE_SRC)
        self.assertIn('"cs_chat", "message_replied"', BRIDGE_SRC)
        self.assertIn("def billable_delivery_key", BRIDGE_SRC)

    def test_declared_in_the_manifest_with_a_written_definition(self) -> None:
        import yaml
        d = yaml.safe_load(Path(
            "agent/ec_skills/browser_use_extension/hooks/external/feige_chat/hook.yaml"
        ).read_text(encoding="utf-8"))
        meters = d.get("meters") or []
        self.assertTrue(meters, "bundle must declare its meters")
        m = meters[0]
        self.assertEqual((m["scenario_code"], m["meter_code"]), ("cs_chat", "message_replied"))
        # The NOT list is the contractual part — it is what a customer is shown.
        definition = m["billable_definition"]
        for excluded in ("过渡话术", "retries", "failed", "human"):
            self.assertIn(excluded, definition)


class IdempotencyKeyTests(unittest.TestCase):
    """One delivered turn = one billable event, however often it is observed."""

    def setUp(self) -> None:
        from agent.ec_skills.browser_use_extension.hooks.external.feige_chat import (
            runner_bridge, placeholder_config,
        )
        self.bridge = runner_bridge.FeigeRunnerBridge()
        self.cfg = placeholder_config
        self.cfg.invalidate()

    def test_key_is_stable_across_repeat_delivery(self) -> None:
        with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
            a = self.bridge.billable_delivery_key("客户01", "msg-1")
            b = self.bridge.billable_delivery_key("客户01", "msg-1")
        self.assertEqual(a, b)

    def test_key_separates_turns_customers_and_stores(self) -> None:
        with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
            base = self.bridge.billable_delivery_key("客户01", "msg-1")
            self.assertNotEqual(base, self.bridge.billable_delivery_key("客户01", "msg-2"))
            self.assertNotEqual(base, self.bridge.billable_delivery_key("客户02", "msg-1"))
        with mock.patch.object(self.cfg, "current_store_key", return_value="S2"):
            self.assertNotEqual(base, self.bridge.billable_delivery_key("客户01", "msg-1"))

    def test_key_carries_no_timestamp(self) -> None:
        """A time component would defeat the whole point under retry."""
        with mock.patch.object(self.cfg, "current_store_key", return_value="S1"):
            key = self.bridge.billable_delivery_key("客户01", "msg-1")
        self.assertEqual(key, "feige:S1:客户01:msg-1")

    def test_missing_msg_id_still_yields_a_usable_key(self) -> None:
        with mock.patch.object(self.cfg, "current_store_key", return_value=""):
            self.assertEqual(self.bridge.billable_delivery_key("客户01", ""), "feige:-:客户01:-")


class EmitApiTests(unittest.TestCase):
    """The generic emit surface."""

    def setUp(self) -> None:
        from agent.ec_skills import metering
        self.metering = metering

    def test_refuses_incomplete_events(self) -> None:
        for args in (("", "m"), ("s", "")):
            self.assertFalse(self.metering.emit(*args, idempotency_key="k"))
        self.assertFalse(self.metering.emit("s", "m", idempotency_key=""))

    def test_records_through_the_service_with_scope_attribution(self) -> None:
        svc = mock.Mock()
        svc.record_event.return_value = True
        scope = {"store_id": "S1", "agent_id": "A1", "task_id": "T1", "skill_id": "K1"}
        with mock.patch.object(self.metering, "_service", return_value=svc):
            with mock.patch.object(self.metering, "_scope", return_value=scope):
                ok = self.metering.emit(
                    "cs_chat", "message_replied",
                    idempotency_key="feige:S1:c:m",
                    evidence={"customer": "c"},
                    occurred_at=datetime(2026, 9, 21, 12, 0, 0),
                )
        self.assertTrue(ok)
        row = svc.record_event.call_args[0][0]
        self.assertEqual(row["scenario_code"], "cs_chat")
        self.assertEqual(row["idempotency_key"], "feige:S1:c:m")
        self.assertEqual(row["store_id"], "S1")
        self.assertEqual(row["agent_id"], "A1")
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["quantity"], 1)
        self.assertIn("customer", row["evidence"])   # serialised to JSON text

    def test_duplicate_is_reported_as_not_new_not_an_error(self) -> None:
        svc = mock.Mock()
        svc.record_event.return_value = False      # unique index said "known"
        with mock.patch.object(self.metering, "_service", return_value=svc):
            self.assertFalse(self.metering.emit("s", "m", idempotency_key="k"))

    def test_never_raises_into_the_delivery_path(self) -> None:
        with mock.patch.object(self.metering, "_service", side_effect=RuntimeError("db gone")):
            self.assertFalse(self.metering.emit("s", "m", idempotency_key="k"))

    def test_no_db_still_leaves_a_trace(self) -> None:
        """A shadow-mode run on a machine without a DB must not be silently
        unmeasured — the log line is the fallback record."""
        with mock.patch.object(self.metering, "_service", return_value=None):
            with mock.patch.object(self.metering.logger, "info") as info:
                self.metering.emit("cs_chat", "message_replied", idempotency_key="k")
        self.assertTrue(any("not persisted" in str(c) for c in info.call_args_list))


class SchemaTests(unittest.TestCase):
    def test_model_matches_the_cloud_row_shape(self) -> None:
        from agent.db.models import UsageEvent
        cols = {c.name for c in UsageEvent.__table__.columns}
        for required in (
            "idempotency_key", "scenario_code", "meter_code", "quantity",
            "owner", "store_id", "agent_id", "task_id", "skill_id", "vehicle_id",
            "occurred_at", "reported_at", "status", "evidence", "cost_basis", "source",
        ):
            self.assertIn(required, cols)

    def test_idempotency_key_is_unique(self) -> None:
        from agent.db.models import UsageEvent
        self.assertTrue(UsageEvent.__table__.columns["idempotency_key"].unique)

    def test_migration_is_registered(self) -> None:
        from agent.db.migrations.migration_config import (
            get_latest_version, VERSION_HISTORY, VERSION_DEPENDENCIES,
        )
        self.assertEqual(get_latest_version(), "3.1.6")
        self.assertIn("3.1.6", VERSION_HISTORY)
        self.assertEqual(VERSION_DEPENDENCIES["3.1.6"], "3.1.5")
        manager = Path("agent/db/migrations/migration_manager.py").read_text(encoding="utf-8")
        self.assertIn('"3.1.6": "migration_315_to_316"', manager)


class MigrationOnExistingDbTests(unittest.TestCase):
    """The migration has to run on a customer's populated DB, not just a fresh
    one. If it fails there the feature records nothing and says nothing."""

    def _db(self):
        import tempfile, pathlib
        from sqlalchemy import create_engine, text
        db = pathlib.Path(tempfile.mkdtemp(prefix="mig_test_")) / "existing.db"
        engine = create_engine(f"sqlite:///{db}")
        with engine.begin() as c:   # an install that already has data
            c.execute(text("CREATE TABLE token_usage (id VARCHAR(64) PRIMARY KEY, cost_usd FLOAT)"))
            c.execute(text("INSERT INTO token_usage VALUES ('t1', 0.0042)"))
        return engine

    def test_upgrades_twice_without_damage(self) -> None:
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        from agent.db.migrations.versions.migration_315_to_316 import Migration_315_to_316

        engine = self._db()
        mig = Migration_315_to_316(engine=engine)
        Session = sessionmaker(bind=engine)

        for _ in range(2):          # re-running a migration must be safe
            session = Session()
            try:
                self.assertTrue(mig.validate_preconditions(session))
                self.assertTrue(mig.upgrade(session))
                self.assertTrue(mig.validate_postconditions(session))
            finally:
                session.close()

        with engine.begin() as c:
            self.assertEqual(c.execute(text("SELECT COUNT(*) FROM token_usage")).scalar(), 1)
            cols = {r[1] for r in c.execute(text("PRAGMA table_info(usage_event)")).fetchall()}
        for required in ("idempotency_key", "scenario_code", "meter_code", "store_id",
                         "occurred_at", "status", "evidence", "cost_basis", "source"):
            self.assertIn(required, cols)

    def test_migrated_schema_enforces_idempotency(self) -> None:
        """The unique index must exist in the SHIPPED DDL, not only on the model."""
        from sqlalchemy import text
        from sqlalchemy.orm import sessionmaker
        from agent.db.migrations.versions.migration_315_to_316 import Migration_315_to_316

        engine = self._db()
        session = sessionmaker(bind=engine)()
        try:
            Migration_315_to_316(engine=engine).upgrade(session)
        finally:
            session.close()

        insert = ("INSERT INTO usage_event (id, idempotency_key, scenario_code, meter_code,"
                  " quantity, occurred_at, status, source) VALUES"
                  " ('{i}','same-key','cs_chat','message_replied',1,'2026-09-21','pending','client')")
        with engine.begin() as c:
            c.execute(text(insert.format(i="a")))
        with self.assertRaises(Exception):
            with engine.begin() as c:
                c.execute(text(insert.format(i="b")))


class PluginPanelCspTests(unittest.TestCase):
    """plugin_gui_server serves panels with `script-src 'self'`, so an inline
    <script> never executes in the packaged app — the page renders its shell,
    makes no bridge call, and logs nothing. That is exactly how the 过渡话术
    panel reached a customer looking empty. Panel logic must live in a .js file.
    """

    GUI = Path("agent/ec_skills/browser_use_extension/hooks/external/feige_chat/gui")

    def test_csp_still_forbids_inline_scripts(self) -> None:
        """If this ever gains 'unsafe-inline', the guard below is pointless —
        but weakening it for every installed plugin is not the fix we want."""
        src = Path(
            "agent/ec_skills/browser_use_extension/plugin_gui_server.py"
        ).read_text(encoding="utf-8")
        i = src.find("_DEFAULT_CSP")
        csp = src[i:i + 700]
        script_src = [l for l in csp.splitlines() if "script-src" in l][0]
        # However the source is expressed ('self' then, an explicit origin now),
        # inline must stay out — that is what keeps panel logic in .js files.
        self.assertNotIn("unsafe-inline", script_src)

    def test_no_panel_ships_an_inline_script(self) -> None:
        import re
        for page in sorted(self.GUI.glob("*.html")):
            with self.subTest(page=page.name):
                html = page.read_text(encoding="utf-8")
                inline = [
                    b for b in re.findall(
                        r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S
                    ) if b.strip()
                ]
                self.assertEqual(
                    inline, [],
                    f"{page.name} has an inline <script>; it will be CSP-blocked "
                    f"and the panel will look empty. Move it to a .js file.",
                )

    def test_every_panel_loads_the_bridge_and_its_own_logic(self) -> None:
        import re
        for page in sorted(self.GUI.glob("*.html")):
            with self.subTest(page=page.name):
                html = page.read_text(encoding="utf-8")
                srcs = re.findall(r'<script[^>]*\bsrc="([^"]+)"', html)
                self.assertIn("bridge.js", srcs)
                self.assertIn(f"{page.stem}.js", srcs)
                self.assertTrue((self.GUI / f"{page.stem}.js").is_file())

    def test_panel_logic_keeps_the_placeholder_section(self) -> None:
        js = (self.GUI / "config.js").read_text(encoding="utf-8")
        for needed in ("placeholder_texts", "PH_STORE_PREFIX", "storeSel", "phSave"):
            self.assertIn(needed, js)


class ServiceResolutionTests(unittest.TestCase):
    """How metering reaches the DB. The first version imported a module-level
    `ec_db_mgr` that does not exist, so every emit on the 0.9.98m customer build
    logged "(not persisted: no DB)" and the shadow run recorded NOTHING. The
    services are attributes on the manager behind AppContext."""

    def setUp(self) -> None:
        from agent.ec_skills import metering
        self.metering = metering

    def test_resolves_through_app_context(self) -> None:
        mgr = mock.Mock()
        mgr.usage_event_service = mock.sentinel.svc
        with mock.patch("app_context.AppContext.get_ec_db_mgr", return_value=mgr):
            self.assertIs(self.metering._service(), mock.sentinel.svc)

    def test_no_manager_degrades_quietly(self) -> None:
        with mock.patch("app_context.AppContext.get_ec_db_mgr", return_value=None):
            self.assertIsNone(self.metering._service())
            self.assertFalse(
                self.metering.emit("cs_chat", "message_replied", idempotency_key="k")
            )

    def test_manager_without_the_service_degrades_quietly(self) -> None:
        mgr = mock.Mock(spec=[])       # no usage_event_service attribute
        with mock.patch("app_context.AppContext.get_ec_db_mgr", return_value=mgr):
            self.assertIsNone(self.metering._service())

    def test_db_manager_registers_the_service(self) -> None:
        """Regression guard: metering is only as good as this attribute."""
        src = Path("agent/db/ec_db_mgr.py").read_text(encoding="utf-8")
        self.assertIn("self.usage_event_service = DBUsageEventService(", src)
        self.assertIn("from .services.db_usage_event_service import DBUsageEventService", src)


class PluginGuiCspOriginTests(unittest.TestCase):
    """The host mounts panels with sandbox="allow-scripts" and no
    allow-same-origin, so the document has an OPAQUE origin and CSP 'self'
    matches nothing — which blocks bridge.js too, not just inline code."""

    SRC = Path("agent/ec_skills/browser_use_extension/plugin_gui_server.py")

    def test_frame_ancestors_lists_schemes_not_just_star(self) -> None:
        """The packaged app loads its UI from file:///.../index.html, so our
        ancestor's scheme is `file:`. CSP3 `*` matches only network schemes
        (http/https/ws/wss) or the resource's own, so a bare `*` refuses the
        frame in a packaged build while working under `pnpm dev` over http.
        That difference is the entire "blank after install" report."""
        src = self.SRC.read_text(encoding="utf-8")
        i = src.find("_DEFAULT_CSP")
        csp = src[i:i + 1800]
        fa = [l for l in csp.splitlines()
              if l.strip().startswith('"frame-ancestors')][0]
        self.assertIn("file:", fa)
        self.assertIn("http:", fa)

    def test_csp_names_an_origin_rather_than_self(self) -> None:
        src = self.SRC.read_text(encoding="utf-8")
        i = src.find("_DEFAULT_CSP")
        csp = src[i:i + 700]
        self.assertIn("script-src {origin}", csp)
        self.assertNotIn("'self'", csp)

    def test_served_header_substitutes_the_real_port(self) -> None:
        import urllib.request
        from agent.ec_skills.browser_use_extension import plugin_gui_server as g
        port = g.start()
        try:
            url = g.get_gui_url("feige_chat", "config_panel")
            self.assertTrue(url)
            with urllib.request.urlopen(url) as r:
                csp = r.headers.get("Content-Security-Policy")
            self.assertIn(f"script-src http://127.0.0.1:{port}", csp)
            self.assertNotIn("'self'", csp)
        finally:
            g.stop()


if __name__ == "__main__":
    unittest.main()
