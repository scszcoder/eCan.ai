"""
Migration from version 3.0.5 to 3.0.6
Add missing columns to association tables
"""

from sqlalchemy import text
from ..base_migration import BaseMigration
import logging

logger = logging.getLogger(__name__)


class Migration_305_to_306(BaseMigration):
    """Migration to add missing columns to association tables"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.0.6"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.5"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Add join_date/leave_date to agent_org_rels and usage statistics to agent_skill_rels"
    
    def upgrade(self, session):
        """Add missing columns to association tables"""
        logger.info("[Migration 3.0.5→3.0.6] Starting upgrade...")
        
        try:
            # Add columns to agent_org_rels
            self._add_columns_to_table(
                table_name='agent_org_rels',
                columns={
                    'join_date': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'leave_date': 'TIMESTAMP'
                }
            )
            
            # Add columns to agent_skill_rels
            self._add_columns_to_table(
                table_name='agent_skill_rels',
                columns={
                    'usage_count': 'INTEGER DEFAULT 0',
                    'success_rate': 'REAL DEFAULT 0.0',
                    'last_used': 'TIMESTAMP',
                    'is_favorite': 'INTEGER DEFAULT 0',
                    'priority': 'INTEGER DEFAULT 0'
                }
            )
            
            logger.info("[Migration 3.0.5→3.0.6] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.5→3.0.6] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Remove added columns (not supported in SQLite)"""
        logger.info("[Migration 3.0.6→3.0.5] Starting downgrade...")
        logger.warning("[Migration] SQLite doesn't support DROP COLUMN. Added columns will remain but won't be used.")
        return True
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.5→3.0.6] Validating migration...")
        
        try:
            # Validate agent_org_rels columns
            if not self._validate_table_columns('agent_org_rels', ['join_date', 'leave_date']):
                return False
            
            # Validate agent_skill_rels columns
            if not self._validate_table_columns('agent_skill_rels', ['usage_count', 'success_rate', 'last_used', 'is_favorite', 'priority']):
                return False
            
            logger.info("[Migration 3.0.5→3.0.6] ✅ Validation successful")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.5→3.0.6] ❌ Validation failed: {e}", exc_info=True)
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

