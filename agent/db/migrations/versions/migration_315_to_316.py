"""
Migration from version 3.1.5 to 3.1.6
Add the usage_event table (billable business outcomes)

``token_usage`` records what a call cost us. This records what the customer got
— one delivered reply, one label printed — so an invoice can be denominated in
the customer's business instead of in tokens.

Created empty and written in shadow mode: rows accumulate, nothing is charged.
The table exists now so that the month of cost-per-outcome data needed to
validate a price starts accumulating before any price is committed to.

``idempotency_key`` is UNIQUE and that is the point of the table. One delivered
turn can be observed several times (retry, drift recovery, duplicate dispatch);
the index is what collapses those into a single billable row.
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


_TABLE = 'usage_event'

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS usage_event (
    id               VARCHAR(64) PRIMARY KEY,
    idempotency_key  VARCHAR(255) NOT NULL UNIQUE,
    scenario_code    VARCHAR(64) NOT NULL,
    meter_code       VARCHAR(64) NOT NULL,
    quantity         INTEGER NOT NULL DEFAULT 1,
    owner            VARCHAR(255),
    store_id         VARCHAR(255),
    agent_id         VARCHAR(255),
    task_id          VARCHAR(255),
    skill_id         VARCHAR(255),
    vehicle_id       VARCHAR(255),
    occurred_at      DATETIME NOT NULL,
    reported_at      DATETIME,
    status           VARCHAR(32) NOT NULL DEFAULT 'pending',
    evidence         TEXT,
    cost_basis       TEXT,
    source           VARCHAR(32) NOT NULL DEFAULT 'client',
    created_at       DATETIME,
    updated_at       DATETIME
)
"""

_INDEXES = (
    ("idx_usage_event_occurred", "usage_event(occurred_at)"),
    ("idx_usage_event_owner", "usage_event(owner)"),
    ("idx_usage_event_meter", "usage_event(scenario_code, meter_code)"),
    ("idx_usage_event_status", "usage_event(status)"),
    ("idx_usage_event_store", "usage_event(store_id)"),
)


class Migration_315_to_316(BaseMigration):
    """Migration to add the usage_event table"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.6"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.5"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add usage_event table for billable business outcomes (shadow mode)"

    def upgrade(self, session):
        """Create usage_event and its indexes"""
        logger.info("[Migration 3.1.5→3.1.6] Starting upgrade...")

        try:
            if self.table_exists(_TABLE):
                logger.info(f"[Migration 3.1.5→3.1.6] {_TABLE} already exists, skipping create")
            else:
                session.execute(text(_CREATE_SQL))
                logger.info(f"[Migration 3.1.5→3.1.6] Created {_TABLE}")

            for name, target in _INDEXES:
                session.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))
            logger.info(f"[Migration 3.1.5→3.1.6] Ensured {len(_INDEXES)} indexes")

            session.commit()
            logger.info("[Migration 3.1.5→3.1.6] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.5→3.1.6] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.5→3.1.6] Checking preconditions...")
        # Creating a fresh table has no precondition beyond a usable session;
        # re-running is safe because the create and the indexes are IF NOT EXISTS.
        logger.info("[Migration 3.1.5→3.1.6] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.5→3.1.6] Checking postconditions...")

        if not self.table_exists(_TABLE):
            logger.error(f"[Migration 3.1.5→3.1.6] ❌ Postcondition failed - {_TABLE} missing")
            return False

        logger.info(f"[Migration 3.1.5→3.1.6] ✅ Validation successful - {_TABLE} exists")
        return True
