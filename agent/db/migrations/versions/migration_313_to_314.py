"""
Migration from version 3.1.3 to 3.1.4
Add cloud_id field to support UUID format cloud skill IDs
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_313_to_314(BaseMigration):
    """Migration to add cloud_id field for UUID format cloud skill IDs"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.4"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.3"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add cloud_id field to support UUID format cloud skill IDs"

    def upgrade(self, session):
        """Add cloud_id column to agent_skills table"""
        logger.info("[Migration 3.1.3→3.1.4] Starting upgrade...")

        try:
            # Check if cloud_id column already exists
            if self.column_exists('agent_skills', 'cloud_id'):
                logger.info("[Migration 3.1.3→3.1.4] cloud_id column already exists, skipping")
                return True

            # Add cloud_id column
            add_column_sql = """
                ALTER TABLE agent_skills ADD COLUMN cloud_id VARCHAR(64)
            """
            session.execute(text(add_column_sql))
            session.commit()
            logger.info("[Migration 3.1.3→3.1.4] Added cloud_id column to agent_skills")

            logger.info("[Migration 3.1.3→3.1.4] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.3→3.1.4] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.3→3.1.4] Checking preconditions...")

        if not self.table_exists('agent_skills'):
            logger.error("[Migration 3.1.3→3.1.4] ❌ Precondition failed: agent_skills table does not exist")
            return False

        logger.info("[Migration 3.1.3→3.1.4] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.3→3.1.4] Checking postconditions...")

        if self.column_exists('agent_skills', 'cloud_id'):
            logger.info("[Migration 3.1.3→3.1.4] ✅ Validation successful - cloud_id column exists")
            return True
        else:
            logger.error("[Migration 3.1.3→3.1.4] ❌ Postcondition failed - cloud_id column not found")
            return False
