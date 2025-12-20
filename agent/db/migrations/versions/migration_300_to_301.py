"""
Migration from version 3.0.0 to 3.0.1

This migration fixes the agent_orgs table by adding missing columns:
- settings (JSON) - for flexible organization settings
- ext (TEXT) - for extensible data storage

This is a patch migration to fix incomplete 3.0.0 migration.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration300To301(BaseMigration):
    """Migration from 3.0.0 to 3.0.1 - Fix agent_orgs table"""
    
    @property
    def version(self) -> str:
        return "3.0.1"
    
    @property
    def previous_version(self) -> str:
        return "3.0.0"
    
    @property
    def description(self) -> str:
        return "Fix agent_orgs table by adding missing settings and ext columns"
    
    def upgrade(self, session: Session) -> bool:
        """
        Perform the migration to 3.0.1.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if agent_orgs table exists
            if not self.table_exists('agent_orgs'):
                logger.error("agent_orgs table does not exist, cannot apply patch migration")
                return False
            
            # Add missing columns to agent_orgs table
            if not self._add_missing_columns_to_agent_orgs(session):
                return False
            
            logger.info("Successfully completed migration to 3.0.1")
            return True
            
        except Exception as e:
            logger.error(f"Failed to migrate to 3.0.1: {e}")
            return False
    
    def _add_missing_columns_to_agent_orgs(self, session: Session) -> bool:
        """Add missing columns to agent_orgs table"""
        try:
            # Check which columns are missing
            missing_columns = []
            
            if not self.column_exists('agent_orgs', 'settings'):
                missing_columns.append(('settings', 'JSON'))
            
            if not self.column_exists('agent_orgs', 'ext'):
                missing_columns.append(('ext', 'TEXT'))
            
            if not missing_columns:
                logger.info("All required columns already exist in agent_orgs table")
                return True
            
            # Add missing columns
            for column_name, column_type in missing_columns:
                sql = f"ALTER TABLE agent_orgs ADD COLUMN {column_name} {column_type}"
                
                # Execute with retry logic for better reliability
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if not self.execute_sql(session, sql):
                            if attempt < max_retries - 1:
                                logger.warning(f"Failed to add {column_name} column, retrying... (attempt {attempt + 1})")
                                session.rollback()
                                import time
                                time.sleep(1)
                                continue
                            return False
                        break
                    except Exception as e:
                        if attempt < max_retries - 1:
                            logger.warning(f"Exception adding {column_name} column, retrying... (attempt {attempt + 1}): {e}")
                            session.rollback()
                            import time
                            time.sleep(1)
                            continue
                        raise e
                
                logger.info(f"Added {column_name} column to agent_orgs table")
            
            # Flush the changes
            session.flush()
            
            logger.info("All missing columns added to agent_orgs table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add missing columns to agent_orgs table: {e}")
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
        
        # Check that all required columns exist in agent_orgs table
        required_columns = ['settings', 'ext']
        
        try:
            from sqlalchemy import text
            result = session.execute(text("PRAGMA table_info(agent_orgs)"))
            columns = [row[1] for row in result.fetchall()]
            
            for column_name in required_columns:
                if column_name not in columns:
                    logger.error(f"Required column {column_name} missing from agent_orgs table")
                    logger.debug(f"Available columns: {columns}")
                    return False
            
            logger.info("All postconditions validated successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to validate postconditions: {e}")
            return False
    
    def downgrade(self, session: Session) -> bool:
        """
        Downgrade from 3.0.1 to 3.0.0.
        
        Note: SQLite doesn't support dropping columns, so this is a no-op.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.warning("Downgrade from 3.0.1 to 3.0.0: SQLite doesn't support dropping columns")
        logger.info("Downgrade completed (columns preserved)")
        return True
