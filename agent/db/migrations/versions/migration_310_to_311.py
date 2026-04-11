"""
Migration from version 3.1.0 to 3.1.1
Add skill_history table for skill version history tracking
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_310_to_311(BaseMigration):
    """Migration to add skill_history table for skill version history"""

    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.1"

    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.1.0"

    @property
    def description(self) -> str:
        """Migration description"""
        return "Add skill_history table for tracking skill version history with automatic cleanup of old records"

    def upgrade(self, session):
        """Create skill_history table"""
        logger.info("[Migration 3.1.0→3.1.1] Starting upgrade...")

        try:
            # Check if table already exists
            if self.table_exists('skill_history'):
                logger.info("[Migration 3.1.0→3.1.1] skill_history table already exists, skipping creation")
                return True

            # Create skill_history table
            create_table_sql = """
                CREATE TABLE skill_history (
                    id VARCHAR(64) PRIMARY KEY,
                    skill_id VARCHAR(64) NOT NULL,
                    skill_name VARCHAR(128) NOT NULL,
                    owner VARCHAR(128) NOT NULL,
                    version VARCHAR(64) NOT NULL,
                    version_number INTEGER NOT NULL DEFAULT 1,
                    description TEXT,
                    version_label VARCHAR(128),
                    path TEXT,
                    source VARCHAR(32) DEFAULT 'ui',
                    level VARCHAR(64),
                    config JSON,
                    diagram JSON,
                    tags JSON,
                    skill_data JSON NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    change_summary TEXT,
                    save_type VARCHAR(32) DEFAULT 'manual',
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    ext JSON
                )
            """
            self._create_table('skill_history', create_table_sql)

            # Create indexes for common queries
            self._create_indexes()

            logger.info("[Migration 3.1.0→3.1.1] ✅ Upgrade completed successfully")
            return True

        except Exception as e:
            logger.error(f"[Migration 3.1.0→3.1.1] ❌ Upgrade failed: {e}")
            raise

    def validate_preconditions(self, session) -> bool:
        """Validate preconditions before migration"""
        logger.info("[Migration 3.1.0→3.1.1] Checking preconditions...")

        # Check that agent_skills table exists (we need this for the foreign key reference)
        if not self.table_exists('agent_skills'):
            logger.error("[Migration 3.1.0→3.1.1] ❌ Precondition failed: agent_skills table does not exist")
            return False

        logger.info("[Migration 3.1.0→3.1.1] ✅ Validation successful")
        return True

    def validate_postconditions(self, session) -> bool:
        """Validate postconditions after migration"""
        logger.info("[Migration 3.1.0→3.1.1] Checking postconditions...")

        # Verify table was created
        if not self.table_exists('skill_history'):
            logger.error("[Migration 3.1.0→3.1.1] ❌ Postcondition failed: skill_history table was not created")
            return False

        # Verify required columns exist
        required_columns = ['id', 'skill_id', 'skill_name', 'owner', 'version',
                         'version_number', 'skill_data', 'save_type', 'created_at', 'updated_at']
        for col in required_columns:
            if not self.column_exists('skill_history', col):
                logger.error(f"[Migration 3.1.0→3.1.1] ❌ Postcondition failed: column {col} does not exist")
                return False

        # Verify indexes were created
        expected_indexes = ['idx_skill_history_skill_id', 'idx_skill_history_skill_name',
                          'idx_skill_history_owner', 'idx_skill_history_created_at']
        for idx in expected_indexes:
            if not self._index_exists(idx):
                logger.warning(f"[Migration 3.1.0→3.1.1] ⚠️ Index {idx} was not created")

        logger.info("[Migration 3.1.0→3.1.1] ✅ Validation successful")
        return True

    def _create_table(self, table_name: str, create_sql: str):
        """Create a table if it doesn't exist

        Args:
            table_name: Name of the table to create
            create_sql: CREATE TABLE SQL statement
        """
        with self.engine.connect() as conn:
            if not self.table_exists(table_name):
                logger.info(f"[Migration] Creating table {table_name}...")
                conn.execute(text(create_sql))
                conn.commit()
                logger.info(f"[Migration] Table {table_name} created successfully")
            else:
                logger.info(f"[Migration] Table {table_name} already exists, skipping")

    def _create_indexes(self):
        """Create indexes for skill_history table"""
        indexes = [
            ('idx_skill_history_skill_id', 'skill_history', 'skill_id'),
            ('idx_skill_history_skill_name', 'skill_history', 'skill_name'),
            ('idx_skill_history_owner', 'skill_history', 'owner'),
            ('idx_skill_history_created_at', 'skill_history', 'created_at'),
            ('idx_skill_history_version_number', 'skill_history', 'skill_id, version_number'),
        ]

        with self.engine.connect() as conn:
            for index_name, table_name, columns in indexes:
                try:
                    conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({columns})"))
                    conn.commit()
                    logger.info(f"[Migration] Created index {index_name} on {table_name}({columns})")
                except Exception as e:
                    logger.debug(f"[Migration] Index {index_name} creation: {e}")

    def _index_exists(self, index_name: str) -> bool:
        """Check if an index exists

        Args:
            index_name: Name of the index to check

        Returns:
            bool: True if index exists
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"PRAGMA index_info({index_name})"))
                return len(result.fetchall()) > 0
        except Exception:
            return False

    def _validate_table_columns(self, table_name: str, required_columns: list) -> bool:
        """Validate that a table has all required columns

        Args:
            table_name: Name of the table
            required_columns: List of required column names

        Returns:
            bool: True if all columns exist
        """
        with self.engine.connect() as conn:
            result = conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing_columns = [row[1] for row in result.fetchall()]
            return all(col in existing_columns for col in required_columns)
