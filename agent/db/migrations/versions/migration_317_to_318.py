"""
Migration from version 3.1.7 to 3.1.8
Add the store table (a store as a first-class record)

Until now a store existed only as the ``task_vars.store_id`` string on the
tasks serving it. Store-first creation -- define a store (name, platform, URLs,
login profile), then deploy agents into it -- needs somewhere to keep the store
itself. ``store_id`` is the same string task_vars, usage_event and token_usage
already carry, so existing rows join without a backfill.

Created empty. Existing stores are seeded at runtime (from task_vars and the
cloud registry, see agent/ec_agents/store_catalog.py), not here: a migration
runs before the cloud session exists and should not guess at data.
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


_TABLE = 'store'

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS store (
    id                  VARCHAR(64) PRIMARY KEY,
    store_id            VARCHAR(255) NOT NULL UNIQUE,
    owner               VARCHAR(255),
    name                VARCHAR(255) NOT NULL DEFAULT '',
    platform            VARCHAR(64) NOT NULL DEFAULT '',
    store_urls          TEXT,
    browser_profile_id  VARCHAR(255),
    status              VARCHAR(32) NOT NULL DEFAULT 'active',
    source              VARCHAR(32) NOT NULL DEFAULT 'ui',
    cloud_synced_at     DATETIME,
    created_at          DATETIME,
    updated_at          DATETIME
)
"""

_INDEXES = (
    ("idx_store_status", "store(status)"),
)


class Migration_317_to_318(BaseMigration):
    """Migration to add the store table"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.8"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.7"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add store table (store-first creation)"

    def upgrade(self, session):
        """Create store and its index"""
        logger.info("[Migration 3.1.7→3.1.8] Starting upgrade...")
        try:
            if self.table_exists(_TABLE):
                logger.info(f"[Migration 3.1.7→3.1.8] {_TABLE} already exists, skipping create")
            else:
                session.execute(text(_CREATE_SQL))
                logger.info(f"[Migration 3.1.7→3.1.8] Created {_TABLE}")

            for name, target in _INDEXES:
                session.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {target}"))

            session.commit()
            logger.info("[Migration 3.1.7→3.1.8] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.7→3.1.8] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        # A fresh table; re-running is safe because both statements are IF NOT EXISTS.
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        if not self.table_exists(_TABLE):
            logger.error(f"[Migration 3.1.7→3.1.8] ❌ Postcondition failed - {_TABLE} missing")
            return False
        return True
