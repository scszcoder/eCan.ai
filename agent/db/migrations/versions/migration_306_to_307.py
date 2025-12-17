"""
Migration from version 3.0.6 to 3.0.7
Add 'source' column to agent_tasks table
"""

from sqlalchemy import text
from ..base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)


class Migration_306_to_307(BaseMigration):
    """Migration to add 'source' column to agent_tasks table"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.0.7"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.6"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Add source and metadata columns to agent_tasks table, add source to agent_skills"
    
    def upgrade(self, session):
        """Add source and metadata columns"""
        logger.info("[Migration 3.0.6→3.0.7] Starting upgrade...")
        
        try:
            # Add source and metadata columns to agent_tasks
            # source: 'ui', 'code', 'system', etc.
            # metadata: JSON field for flexible task configuration
            self._add_columns_to_table(
                table_name='agent_tasks',
                columns={
                    'source': "VARCHAR(32) DEFAULT 'ui'",
                    'metadata': "JSON"
                }
            )
            
            # Add source column to agent_skills
            self._add_columns_to_table(
                table_name='agent_skills',
                columns={
                    'source': "VARCHAR(32) DEFAULT 'ui'"
                }
            )
            
            logger.info("[Migration 3.0.6→3.0.7] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.6→3.0.7] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Remove added columns (not supported in SQLite)"""
        logger.info("[Migration 3.0.7→3.0.6] Starting downgrade...")
        logger.warning("[Migration] SQLite doesn't support DROP COLUMN. Added columns will remain but won't be used.")
        return True
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.6→3.0.7] Validating migration...")
        
        try:
            # Validate agent_tasks columns
            if not self._validate_table_columns('agent_tasks', ['source']):
                return False
            
            logger.info("[Migration 3.0.6→3.0.7] ✅ Validation successful")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.6→3.0.7] ❌ Validation failed: {e}", exc_info=True)
            return False
    
    # Helper methods
    def _add_columns_to_table(self, table_name: str, columns: dict):
        """Add multiple columns to a table if they don't exist
        
        Args:
            table_name: Name of the table
            columns: Dict of column_name -> column_definition
        """
        with self.engine.connect() as conn:
            # Get existing columns
            result = conn.execute(text(f"PRAGMA table_info({table_name})"))
            existing_columns = [row[1] for row in result.fetchall()]
            
            # Add missing columns
            for column_name, column_def in columns.items():
                if column_name not in existing_columns:
                    logger.info(f"[Migration] Adding column {column_name} to {table_name}...")
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"))
                    conn.commit()
                else:
                    logger.info(f"[Migration] Column {column_name} already exists in {table_name}, skipping")
    
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
            
            for column in required_columns:
                if column not in existing_columns:
                    logger.error(f"[Migration] Validation failed: Missing column {column} in {table_name}")
                    return False
            
            return True
