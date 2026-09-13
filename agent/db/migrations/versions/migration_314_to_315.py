"""
Migration from version 3.1.4 to 3.1.5
Add pod lifecycle columns to agent_vehicles (unified execution, C1)

A vehicle used to be a machine we discovered. Under unified execution it is
also a pod the customer creates and pays for, which needs three things the
machine model never had: whether it stays up (`lifecycle`), when it should be
scaled away if it does not (`idle_shutdown_minutes`), and how many of it the
customer wants (`desired_replicas`).

Desired state is deliberately separate from the observed columns already here
(`status`, `last_heartbeat`): the customer says how many replicas they want and
then watches the fleet converge. Collapsing the two would make a form that lies.
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


_COLUMNS = (
    # always_on | on_demand. Default preserves how every existing row behaves:
    # a discovered machine is simply there, which is what always_on describes.
    ("lifecycle", "VARCHAR(32)", "'always_on'"),
    # Only meaningful for on_demand. NULL = never idle-shutdown.
    ("idle_shutdown_minutes", "INTEGER", "NULL"),
    # How many of this pod the owner wants. 1 for anything that already exists.
    ("desired_replicas", "INTEGER", "1"),
)


class Migration_314_to_315(BaseMigration):
    """Migration to add pod lifecycle/desired-state columns to agent_vehicles"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.5"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.4"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add lifecycle, idle_shutdown_minutes and desired_replicas to agent_vehicles"

    def upgrade(self, session):
        """Add the pod columns to agent_vehicles"""
        logger.info("[Migration 3.1.4→3.1.5] Starting upgrade...")

        try:
            for name, sql_type, default in _COLUMNS:
                if self.column_exists('agent_vehicles', name):
                    logger.info(f"[Migration 3.1.4→3.1.5] {name} already exists, skipping")
                    continue
                default_clause = "" if default == "NULL" else f" DEFAULT {default}"
                session.execute(text(
                    f"ALTER TABLE agent_vehicles ADD COLUMN {name} {sql_type}{default_clause}"
                ))
                logger.info(f"[Migration 3.1.4→3.1.5] Added {name} to agent_vehicles")

            session.commit()
            logger.info("[Migration 3.1.4→3.1.5] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.4→3.1.5] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.4→3.1.5] Checking preconditions...")

        if not self.table_exists('agent_vehicles'):
            logger.error("[Migration 3.1.4→3.1.5] ❌ Precondition failed: agent_vehicles table does not exist")
            return False

        logger.info("[Migration 3.1.4→3.1.5] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.4→3.1.5] Checking postconditions...")

        missing = [n for n, _, _ in _COLUMNS if not self.column_exists('agent_vehicles', n)]
        if missing:
            logger.error(f"[Migration 3.1.4→3.1.5] ❌ Postcondition failed - missing columns: {missing}")
            return False

        logger.info("[Migration 3.1.4→3.1.5] ✅ Validation successful - pod columns exist")
        return True
