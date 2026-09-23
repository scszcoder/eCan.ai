"""Phase C — the store dimension on cost.

``token_usage`` could say what a month cost but not what a STORE cost: its only
attribution was ``source_id`` (whatever the call site happened to pass) and
``user_email`` (one customer across all their stores). A customer running
several 飞鸽 stores on one machine needs the split to price a store, spot the
one burning tokens, and eventually cap it.

The three columns mirror ``usage_event``'s, so cost and outcome finally join on
one dimension — cost per delivered reply, per store.

The load-bearing property is that attribution is read from the run scope at
RECORD time, not threaded through call sites: concurrent runs each see their
own ContextVar, so a busy store cannot be billed for a quiet one's tokens.
"""

import os
import tempfile
import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from utils.log_scope import scope as log_scope, attribution_headers
from agent.ec_skills.token_tracker import _run_attribution


class RunAttributionTests(unittest.TestCase):
    def test_reads_the_active_run_scope(self):
        with log_scope(store_id="lands_flying_fish", agent_id="a1", task_id="t1"):
            self.assertEqual(
                _run_attribution(),
                {"store_id": "lands_flying_fish", "agent_id": "a1", "task_id": "t1"},
            )

    def test_absent_scope_yields_nulls(self):
        # NULL is meaningful: "recorded before stores were distinguished".
        self.assertEqual(
            _run_attribution(),
            {"store_id": None, "agent_id": None, "task_id": None},
        )

    def test_blank_values_become_null_not_empty_string(self):
        # "" would look like a real store in a GROUP BY.
        with log_scope(store_id="", agent_id="  ", task_id="t1"):
            got = _run_attribution()
        self.assertIsNone(got["store_id"])
        self.assertIsNone(got["agent_id"])
        self.assertEqual(got["task_id"], "t1")

    def test_scopes_do_not_leak_across_runs(self):
        with log_scope(store_id="store_a"):
            self.assertEqual(_run_attribution()["store_id"], "store_a")
        self.assertIsNone(_run_attribution()["store_id"])

    def test_nested_scope_wins(self):
        with log_scope(store_id="store_a"):
            with log_scope(store_id="store_b"):
                self.assertEqual(_run_attribution()["store_id"], "store_b")
            self.assertEqual(_run_attribution()["store_id"], "store_a")


class AttributionHeaderTests(unittest.TestCase):
    def test_store_id_reaches_the_proxy(self):
        # Without this the backend can bill an account but never a store, and
        # per-store quota has nothing to key on.
        with log_scope(store_id="lands_flying_fish"):
            self.assertEqual(
                attribution_headers().get("X-Ecan-Store-Id"), "lands_flying_fish"
            )

    def test_absent_store_sends_no_header(self):
        with log_scope(agent_id="a1"):
            self.assertNotIn("X-Ecan-Store-Id", attribution_headers())


class TokenUsagePersistenceTests(unittest.TestCase):
    """Against real SQLite — the columns must actually round-trip."""

    def setUp(self):
        from agent.db.models.token_usage_model import TokenUsage
        from agent.db.models.base_model import BaseModel

        self.tmp = tempfile.mkdtemp()
        self.engine = create_engine(f"sqlite:///{os.path.join(self.tmp, 'u.db')}")
        TokenUsage.__table__.create(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def _service(self):
        from agent.db.services.db_token_usage_service import DBTokenUsageService
        return DBTokenUsageService(engine=self.engine)

    def test_records_the_store_dimension(self):
        self._service().record_usage(
            source_type="skill_llm_node", vendor="openai", model="gpt-4",
            input_tokens=100, output_tokens=50, cost_usd=0.01,
            store_id="lands_flying_fish", agent_id="a1", task_id="t1",
        )
        with self.engine.connect() as c:
            row = c.execute(text(
                "SELECT store_id, agent_id, task_id, total_tokens FROM token_usage"
            )).fetchone()
        self.assertEqual(tuple(row), ("lands_flying_fish", "a1", "t1", 150))

    def test_omitting_them_is_still_valid(self):
        # Every existing call site passes none of these and must keep working.
        self._service().record_usage(
            source_type="mcp_rag", vendor="openai", model="text-embedding-3",
            input_tokens=10, output_tokens=0, cost_usd=0.0001,
        )
        with self.engine.connect() as c:
            row = c.execute(text("SELECT store_id, total_tokens FROM token_usage")).fetchone()
        self.assertEqual(tuple(row), (None, 10))

    def test_two_stores_are_separable(self):
        svc = self._service()
        for store, tokens in (("store_a", 100), ("store_b", 300), ("store_a", 200)):
            svc.record_usage(
                source_type="skill_llm_node", vendor="openai", model="gpt-4",
                input_tokens=tokens, output_tokens=0, cost_usd=0.01,
                store_id=store,
            )
        with self.engine.connect() as c:
            rows = dict(c.execute(text(
                "SELECT store_id, SUM(total_tokens) FROM token_usage GROUP BY store_id"
            )).fetchall())
        self.assertEqual(rows, {"store_a": 300, "store_b": 300})


class MigrationTests(unittest.TestCase):
    """The migration must run on a POPULATED table, twice, losing nothing."""

    _PRE_MIGRATION_DDL = """
    CREATE TABLE token_usage (
      id VARCHAR PRIMARY KEY, source_type VARCHAR NOT NULL, source_id VARCHAR,
      source_name VARCHAR, user_email VARCHAR, session_id VARCHAR,
      vendor VARCHAR NOT NULL, model VARCHAR NOT NULL,
      input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
      total_tokens INTEGER NOT NULL DEFAULT 0, cost_usd FLOAT NOT NULL DEFAULT 0.0,
      usage_timestamp DATETIME NOT NULL, node_type VARCHAR, operation VARCHAR,
      start_time DATETIME, end_time DATETIME, duration_ms INTEGER, skill_name VARCHAR,
      created_at DATETIME, updated_at DATETIME)
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.engine = create_engine(f"sqlite:///{os.path.join(self.tmp, 'm.db')}")
        with self.engine.begin() as c:
            c.execute(text(self._PRE_MIGRATION_DDL))
            c.execute(text(
                "INSERT INTO token_usage (id,source_type,vendor,model,input_tokens,"
                "output_tokens,total_tokens,cost_usd,usage_timestamp) VALUES "
                "('r1','skill_llm_node','openai','gpt-4',100,50,150,0.01,'2026-09-01 10:00:00')"
            ))
        self.Session = sessionmaker(bind=self.engine)

    def _run_once(self):
        from agent.db.migrations.versions.migration_316_to_317 import Migration_316_to_317
        m = Migration_316_to_317(engine=self.engine)
        with self.Session() as ses:
            self.assertTrue(m.validate_preconditions(ses))
            m.upgrade(ses)
            self.assertTrue(m.validate_postconditions(ses))

    def test_adds_the_columns_and_keeps_existing_rows(self):
        self._run_once()
        with self.engine.connect() as c:
            cols = {r[1] for r in c.execute(text("PRAGMA table_info(token_usage)"))}
            row = c.execute(text(
                "SELECT total_tokens, store_id FROM token_usage WHERE id='r1'"
            )).fetchone()
        self.assertTrue({"store_id", "agent_id", "task_id"} <= cols)
        # No backfill: there is nothing in an old row to recover a store from,
        # and inventing one would corrupt the very comparison this enables.
        self.assertEqual(tuple(row), (150, None))

    def test_is_idempotent(self):
        self._run_once()
        self._run_once()
        with self.engine.connect() as c:
            cols = [r[1] for r in c.execute(text("PRAGMA table_info(token_usage)"))]
        self.assertEqual(cols.count("store_id"), 1)

    def test_creates_the_indexes(self):
        self._run_once()
        with self.engine.connect() as c:
            idx = {r[1] for r in c.execute(text("PRAGMA index_list(token_usage)"))}
        self.assertTrue(
            {"idx_token_usage_store", "idx_token_usage_agent", "idx_token_usage_task"} <= idx
        )

    def test_registered_in_the_migration_chain(self):
        from agent.db.migrations import migration_config as cfg
        self.assertEqual(cfg.LATEST_DATABASE_VERSION, "3.1.7")
        self.assertIn("3.1.7", cfg.VERSION_HISTORY)
        self.assertEqual(cfg.VERSION_DEPENDENCIES["3.1.7"], "3.1.6")

    def test_model_and_migration_agree(self):
        # Drift here means a fresh install and an upgraded one disagree.
        from agent.db.models.token_usage_model import TokenUsage
        model_cols = set(TokenUsage.__table__.columns.keys())
        self.assertTrue({"store_id", "agent_id", "task_id"} <= model_cols)


class TrackerEndToEndTests(unittest.TestCase):
    """The whole path: an LLM response recorded inside a run scope lands in the
    DB carrying that scope's store. Pieces passing individually is not the
    claim -- the claim is that the tracker actually reads the scope."""

    def setUp(self):
        from agent.db.models.token_usage_model import TokenUsage
        from agent.db.services.db_token_usage_service import DBTokenUsageService
        from agent.ec_skills.token_tracker import TokenTracker

        self.tmp = tempfile.mkdtemp()
        self.engine = create_engine(f"sqlite:///{os.path.join(self.tmp, 'e2e.db')}")
        TokenUsage.__table__.create(self.engine)

        self.tracker = TokenTracker()
        self._saved = getattr(self.tracker, "_token_service", None)
        self.tracker._token_service = DBTokenUsageService(engine=self.engine)

    def tearDown(self):
        self.tracker._token_service = self._saved

    class _Response:
        """Minimal LangChain-shaped response with usage metadata."""
        def __init__(self):
            self.usage_metadata = {"input_tokens": 120, "output_tokens": 30}
            self.response_metadata = {"model_name": "gpt-4"}
            self.content = "hi"

    def test_store_from_the_run_scope_reaches_the_database(self):
        with log_scope(store_id="lands_flying_fish", agent_id="a1", task_id="t1"):
            ok = self.tracker.record_llm_usage(
                self._Response(), source_type="skill_llm_node", skill_name="qa"
            )
        self.assertTrue(ok, "usage was not recorded at all")
        with self.engine.connect() as c:
            row = c.execute(text(
                "SELECT store_id, agent_id, task_id FROM token_usage"
            )).fetchone()
        self.assertEqual(tuple(row), ("lands_flying_fish", "a1", "t1"))

    def test_without_a_scope_the_row_is_still_written(self):
        # Attribution is never worth losing a usage row over.
        ok = self.tracker.record_llm_usage(
            self._Response(), source_type="skill_llm_node", skill_name="qa"
        )
        self.assertTrue(ok)
        with self.engine.connect() as c:
            row = c.execute(text("SELECT store_id, total_tokens FROM token_usage")).fetchone()
        self.assertEqual(tuple(row), (None, 150))


class DispatchPayloadTests(unittest.TestCase):
    def _payload(self):
        from agent.ec_skills.node_runtime.frontdesk_dispatch import (
            _build_assignment_payload, DispatchConfig,
        )
        item = {"customer_id": "c1", "session_id": "s1", "last_message": "hi"}
        return _build_assignment_payload(item, "", DispatchConfig())

    def test_carries_the_senders_store(self):
        with log_scope(store_id="lands_flying_fish"):
            self.assertEqual(self._payload().get("store_id"), "lands_flying_fish")

    def test_omitted_when_the_sender_has_no_store(self):
        # A worker that never sees the key behaves exactly as before.
        self.assertNotIn("store_id", self._payload())


if __name__ == "__main__":
    unittest.main()
