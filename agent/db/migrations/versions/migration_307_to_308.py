"""
Migration from version 3.0.7 to 3.0.8
Add default_input_modes and default_output_modes columns to agents table
"""

from sqlalchemy import text
from ..base_migration import BaseMigration
import json

from utils.logger_helper import logger_helper as logger


class Migration_307_to_308(BaseMigration):
    """Migration to add default_input_modes and default_output_modes to agents table"""
    
    @property
    def version(self) -> str:
        """Target version"""
        return "3.0.8"
    
    @property
    def previous_version(self) -> str:
        """Previous version"""
        return "3.0.7"
    
    @property
    def description(self) -> str:
        """Migration description"""
        return "Add default_input_modes and default_output_modes columns to agents table for a2a-sdk compatibility"
    
    def upgrade(self, session):
        """Add default_input_modes and default_output_modes columns"""
        logger.info("[Migration 3.0.7→3.0.8] Starting upgrade...")
        
        try:
            # Add default_input_modes and default_output_modes columns to agents table
            # These fields are required by a2a-sdk's AgentCard model
            # Default value is ['text'] for backward compatibility
            self._add_columns_to_table(
                session,
                table_name='agents',
                columns={
                    'default_input_modes': "JSON",
                    'default_output_modes': "JSON"
                }
            )
            
            # Update existing agents to have default values
            self._set_default_values_for_existing_agents(session)
            
            logger.info("[Migration 3.0.7→3.0.8] ✅ Upgrade completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.7→3.0.8] ❌ Upgrade failed: {e}", exc_info=True)
            raise
    
    def downgrade(self, session):
        """Remove added columns (not supported in SQLite)"""
        logger.info("[Migration 3.0.8→3.0.7] Starting downgrade...")
        logger.warning("[Migration] SQLite doesn't support DROP COLUMN. Added columns will remain but won't be used.")
        return True
    
    def validate_postconditions(self, session):
        """Validate the migration was successful"""
        logger.info("[Migration 3.0.7→3.0.8] Validating migration...")
        
        try:
            # Validate agents table has the new columns
            if not self._validate_table_columns(session, 'agents', ['default_input_modes', 'default_output_modes']):
                return False
            
            # Validate that existing agents have default values
            result = session.execute(text("""
                SELECT COUNT(*) FROM agents 
                WHERE default_input_modes IS NULL OR default_output_modes IS NULL
            """))
            null_count = result.scalar()
            
            if null_count > 0:
                logger.warning(f"[Migration] Found {null_count} agents with NULL default modes (will use code-level defaults)")
            
            logger.info("[Migration 3.0.7→3.0.8] ✅ Validation successful")
            return True
            
        except Exception as e:
            logger.error(f"[Migration 3.0.7→3.0.8] ❌ Validation failed: {e}", exc_info=True)
            return False
    
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
    
    def _set_default_values_for_existing_agents(self, session):
        """Set default values for existing agents that have NULL in the new columns
        
        Args:
            session: SQLAlchemy session
        """
        # Set default modes to match SUPPORTED_CONTENT_TYPES from code
        # This ensures database agents have the same capabilities as code-created agents
        default_modes = json.dumps(['text', 'text/plain', 'json', 'file'])
        
        logger.info("[Migration] Setting default values for existing agents...")
        
        # Update default_input_modes
        result = session.execute(text("""
            UPDATE agents 
            SET default_input_modes = :default_modes
            WHERE default_input_modes IS NULL
        """), {"default_modes": default_modes})
        updated_input = result.rowcount
        
        # Update default_output_modes
        result = session.execute(text("""
            UPDATE agents 
            SET default_output_modes = :default_modes
            WHERE default_output_modes IS NULL
        """), {"default_modes": default_modes})
        updated_output = result.rowcount
        
        session.commit()
        
        logger.info(f"[Migration] Updated {updated_input} agents with default_input_modes=['text']")
        logger.info(f"[Migration] Updated {updated_output} agents with default_output_modes=['text']")
    
    def _validate_table_columns(self, session, table_name: str, required_columns: list) -> bool:
        """Validate that a table has all required columns using session
        
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
