"""
Migration from version 3.1.1 to 3.1.2
Add skill_files column to skill_history table for full directory snapshots
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_311_to_312(BaseMigration):
    """Migration to add skill_files JSON column to skill_history table"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.2"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.1"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add skill_files JSON column to skill_history table for full skill directory snapshots"

    def upgrade(self, session):
        """Add skill_files column to skill_history table"""
        logger.info("[Migration 3.1.1→3.1.2] Starting upgrade...")

        try:
            if self.column_exists('skill_history', 'skill_files'):
                logger.info("[Migration 3.1.1→3.1.2] skill_files column already exists, skipping")
                return True

            add_column_sql = """
                ALTER TABLE skill_history ADD COLUMN skill_files JSON
            """
            session.execute(text(add_column_sql))
            session.commit()
            logger.info("[Migration 3.1.1→3.1.2] Added skill_files column to skill_history")

            logger.info("[Migration 3.1.1→3.1.2] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.1→3.1.2] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.1→3.1.2] Checking preconditions...")

        if not self.table_exists('skill_history'):
            logger.error("[Migration 3.1.1→3.1.2] ❌ Precondition failed: skill_history table does not exist")
            return False

        logger.info("[Migration 3.1.1→3.1.2] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.1→3.1.2] Checking postconditions...")

        if self.column_exists('skill_history', 'skill_files'):
            logger.info("[Migration 3.1.1→3.1.2] ✅ Validation successful - skill_files column exists")
            return True
        else:
            logger.error("[Migration 3.1.1→3.1.2] ❌ Postcondition failed - skill_files column not found")
            return False
