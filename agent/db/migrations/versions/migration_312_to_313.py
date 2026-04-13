"""
Migration from version 3.1.2 to 3.1.3
Fix duplicate skills: deduplicate by ID (keep first occurrence)
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_312_to_313(BaseMigration):
    """Migration to deduplicate existing skills by ID"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.3"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.2"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Deduplicate existing skills by ID (keep first occurrence)"

    def upgrade(self, session):
        """Deduplicate existing records by ID"""
        logger.info("[Migration 3.1.2→3.1.3] Starting upgrade...")

        try:
            # Find duplicate IDs and keep the first one (by rowid)
            # This SQL ensures we keep the record with the smallest rowid for each duplicate ID
            dedup_sql = text("""
                DELETE FROM agent_skills
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM agent_skills
                    GROUP BY id
                )
            """)

            result = session.execute(dedup_sql)
            deleted_count = result.rowcount
            logger.info(f"[Migration 3.1.2→3.1.3] Deleted {deleted_count} duplicate skill records")

            logger.info("[Migration 3.1.2→3.1.3] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.2→3.1.3] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.2→3.1.3] Checking preconditions...")

        if not self.table_exists('agent_skills'):
            logger.error("[Migration 3.1.2→3.1.3] ❌ Precondition failed: agent_skills table does not exist")
            return False

        logger.info("[Migration 3.1.2→3.1.3] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.2→3.1.3] Checking postconditions...")

        # Check that no duplicate IDs exist
        result = session.execute(text("""
            SELECT id, COUNT(*) as cnt
            FROM agent_skills
            WHERE id IS NOT NULL AND id != ''
            GROUP BY id
            HAVING cnt > 1
        """))
        duplicates = result.fetchall()

        if duplicates:
            logger.error(f"[Migration 3.1.2→3.1.3] ❌ Postcondition failed - found {len(duplicates)} duplicate IDs")
            for dup in duplicates:
                logger.error(f"  ID: {dup[0]}, Count: {dup[1]}")
            return False

        logger.info("[Migration 3.1.2→3.1.3] ✅ Validation successful - no duplicate IDs")
        return True
