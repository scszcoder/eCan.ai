"""
Migration from version 3.0.9 to 3.1.0
Add timing columns to token_usage table for performance tracking
"""

from sqlalchemy import text
from ..base_migration import BaseMigration

from utils.logger_helper import logger_helper as logger


class Migration_309_to_310(BaseMigration):
    """Migration to add start_time, end_time, duration_ms, and skill_name columns to token_usage table"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.1.0"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.9"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Add start_time, end_time, duration_ms, and skill_name columns to token_usage table for timing and analytics support"
    
    def upgrade(self, session):
        """Add timing and skill_name columns to token_usage table"""
        logger.info("[Migration 3.0.9→3.1.0] Starting upgrade...")
        
        try:
            # Add timing columns and skill_name to token_usage table
            # Missing table will be created by _repair_missing_tables in MigrationManager
            self._add_columns_to_table(
                session,
                table_name='token_usage',
                columns={
                    'start_time': 'DATETIME',
                    'end_time': 'DATETIME',
                    'duration_ms': 'INTEGER',
                    'skill_name': 'VARCHAR'
                }
            )
            
            # Create indexes for better query performance
            self._create_indexes(session)
            
            logger.info("[Migration 3.0.9→3.1.0] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.9→3.1.0] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Remove added columns (not supported in SQLite)"""
        logger.info("[Migration 3.1.0→3.0.9] Starting downgrade...")
        logger.warning("[Migration] SQLite doesn't support DROP COLUMN. Added columns will remain but won't be used.")
        return True
    
    def validate_preconditions(self, session):
        """Validate preconditions before migration"""
        logger.info("[Migration 3.0.9→3.1.0] Validating preconditions...")
        # Table will be created if missing - no preconditions needed
        logger.info("[Migration 3.0.9→3.1.0] ✅ Preconditions validated")
        return True
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.9→3.1.0] Validating migration...")
        
        required_columns = ['start_time', 'end_time', 'duration_ms', 'skill_name']
        if not self._validate_table_columns(session, 'token_usage', required_columns):
            return False
        
        logger.info("[Migration 3.0.9→3.1.0] ✅ Validation successful")
        return True
    
    def _add_columns_to_table(self, session, table_name: str, columns: dict):
        """Add multiple columns to a table if they don't exist using session
        
        Args:
            session: SQLAlchemy session
            table_name: Name of the table
            columns: Dict of column_name -> column_definition
        """
        # Get existing columns
        result = session.execute(text(f"PRAGMA table_info({table_name})"))
        existing_columns = [row[1] for row in result.fetchall()]
        
        # Add missing columns
        for column_name, column_def in columns.items():
            if column_name not in existing_columns:
                logger.info(f"[Migration] Adding column {column_name} to {table_name}...")
                session.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                session.commit()
            else:
                logger.info(f"[Migration] Column {column_name} already exists in {table_name}, skipping")
    
    def _create_indexes(self, session):
        """Create indexes for the new columns if they don't exist"""
        indexes = [
            ('idx_token_usage_skill', 'token_usage', 'skill_name'),
            ('idx_token_usage_start_time', 'token_usage', 'start_time'),
        ]
        
        for index_name, table_name, column_name in indexes:
            try:
                session.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"))
                session.commit()
                logger.info(f"[Migration] Created index {index_name} on {table_name}({column_name})")
            except Exception as e:
                logger.debug(f"[Migration] Index {index_name} creation skipped: {e}")
    
    def _validate_table_columns(self, session, table_name: str, required_columns: list) -> bool:
        """Validate that a table has all required columns
        
        Args:
            session: SQLAlchemy session
            table_name: Name of the table
            required_columns: List of required column names
            
        Returns:
            bool: True if all columns exist
        """
        result = session.execute(text(f"PRAGMA table_info({table_name})"))
        existing_columns = [row[1] for row in result.fetchall()]
        
        for column in required_columns:
            if column not in existing_columns:
                logger.error(f"[Migration] Validation failed: Missing column {column} in {table_name}")
                return False
        
        return True
