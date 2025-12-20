"""
Migration from version 3.0.1 to 3.0.2

This migration adds the extra_data column to the agents table:
- extra_data (JSON) - for storing structured data like vehicle_id, notes, preferences

This replaces the reserved 'metadata' field name with 'extra_data' to avoid
SQLAlchemy conflicts.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration301To302(BaseMigration):
    """Migration from 3.0.1 to 3.0.2 - Add extra_data column to agents table"""
    
    @property
    def version(self) -> str:
        return "3.0.2"
    
    @property
    def previous_version(self) -> str:
        return "3.0.1"
    
    @property
    def description(self) -> str:
        return "Add extra_data column to agents table for structured data storage"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the migration to 3.0.2.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if agents table exists
            if not self.table_exists('agents'):
                logger.error("agents table does not exist, cannot apply migration")
                return False
            
            # Add extra_data column to agents table
            if not self._add_extra_data_column(session):
                return False
            
            logger.info("Successfully completed migration to 3.0.2")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate to 3.0.2: {e}")
            return False
    
    def _add_extra_data_column(self, session: Session) -> bool:
        """Add extra_data column to agents table"""
        try:
            # Check if column already exists
            if self.column_exists('agents', 'extra_data'):
                logger.info("extra_data column already exists in agents table")
                return True
            
            # Add the column
            sql = "ALTER TABLE agents ADD COLUMN extra_data JSON"
            
            # Execute with retry logic for better reliability
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if not self.execute_sql(session, sql):
                        if attempt < max_retries - 1:
                            logger.warning(f"Failed to add extra_data column, retrying... (attempt {attempt + 1})")
                            session.rollback()
                            import time
                            time.sleep(1)
                            continue
                        return False
                    break
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.warning(f"Exception adding extra_data column, retrying... (attempt {attempt + 1}): {e}")
                        session.rollback()
                        import time
                        time.sleep(1)
                        continue
                    raise e
            
            logger.info("Added extra_data column to agents table")
            
            # Flush the changes
            session.flush()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add extra_data column to agents table: {e}")
            session.rollback()
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that all migration changes were applied successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        # Flush session to ensure all changes are committed
        session.flush()
        
        # Check that extra_data column exists in agents table
        try:
            from sqlalchemy import text
            result = session.execute(text("PRAGMA table_info(agents)"))
            columns = [row[1] for row in result.fetchall()]
            
            if 'extra_data' not in columns:
                logger.error("Required column extra_data missing from agents table")
                logger.debug(f"Available columns: {columns}")
                return False
            
            logger.info("All postconditions validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate postconditions: {e}")
            return False
    
    def downgrade(self, session: Session) -> bool:
        """
        Downgrade from 3.0.2 to 3.0.1.
        
        Note: SQLite doesn't support dropping columns, so this is a no-op.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.warning("Downgrade from 3.0.2 to 3.0.1: SQLite doesn't support dropping columns")
        logger.info("Downgrade completed (extra_data column preserved)")
        return True

