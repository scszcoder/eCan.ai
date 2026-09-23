"""
Migration from version 3.1.6 to 3.1.7
Add store_id / agent_id / task_id to token_usage

``token_usage`` could already answer "what did this month cost?" but not "what
did THIS STORE cost?" — the only attribution it carried was ``source_id``,
which holds whatever the call site happened to pass (a skill id here, a task id
there), and ``user_email``, which is one customer across all of their stores.

A customer running several 飞鸽 stores on one machine needs the per-store split
to price a store, spot the one burning tokens, and eventually cap it. The same
three columns already exist on ``usage_event`` (3.1.5), so cost and outcome can
finally be joined on the same dimension: cost-per-delivered-reply *per store*.

Backfill is deliberately NOT attempted. Existing rows predate the dimension and
there is nothing in them to recover a store from; inventing one would corrupt
exactly the comparison the columns exist to support. They stay NULL and mean
"recorded before stores were distinguished".
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


_TABLE = 'token_usage'

# (column, DDL type) — added one at a time; SQLite has no multi-ADD.
_COLUMNS = (
    ('store_id', 'VARCHAR(255)'),
    ('agent_id', 'VARCHAR(255)'),
    ('task_id', 'VARCHAR(255)'),
)

_INDEXES = (
    ("idx_token_usage_store", "token_usage(store_id)"),
    ("idx_token_usage_agent", "token_usage(agent_id)"),
    ("idx_token_usage_task", "token_usage(task_id)"),
)


class Migration_316_to_317(BaseMigration):
    """Migration to add the store dimension to token_usage"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.7"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.6"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add store_id/agent_id/task_id to token_usage for per-store cost"

    def _existing_columns(self, session) -> set:
        rows = session.execute(text(f"PRAGMA table_info({_TABLE})")).fetchall()
        return {r[1] for r in rows}

    def upgrade(self, session):
        """Add the three attribution columns and their indexes"""
        logger.info("[Migration 3.1.6→3.1.7] Starting upgrade...")

        try:
            existing = self._existing_columns(session)
            added = 0
            for name, ddl in _COLUMNS:
                if name in existing:
                    logger.info(f"[Migration 3.1.6→3.1.7] {_TABLE}.{name} already present, skipping")
                    continue
                session.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN {name} {ddl}"))
                added += 1
            logger.info(f"[Migration 3.1.6→3.1.7] Added {added} column(s) to {_TABLE}")

            for name, target in _INDEXES:
                session.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))
            logger.info(f"[Migration 3.1.6→3.1.7] Ensured {len(_INDEXES)} indexes")

            session.commit()
            logger.info("[Migration 3.1.6→3.1.7] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.6→3.1.7] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.6→3.1.7] Checking preconditions...")

        if not self.table_exists(_TABLE):
            # A fresh database creates token_usage from the model, which already
            # declares these columns; there is nothing to alter.
            logger.info(f"[Migration 3.1.6→3.1.7] {_TABLE} absent — nothing to alter")
            return True

        logger.info("[Migration 3.1.6→3.1.7] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.6→3.1.7] Checking postconditions...")

        if not self.table_exists(_TABLE):
            logger.info(f"[Migration 3.1.6→3.1.7] {_TABLE} absent — nothing to verify")
            return True

        existing = self._existing_columns(session)
        missing = [name for name, _ in _COLUMNS if name not in existing]
        if missing:
            logger.error(
                f"[Migration 3.1.6→3.1.7] ❌ Postcondition failed - missing column(s): {missing}")
            return False

        logger.info("[Migration 3.1.6→3.1.7] ✅ Validation successful - all columns present")
        return True
