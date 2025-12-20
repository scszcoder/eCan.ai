"""
Migration from version 1.0.0 to 1.0.1

This migration adds the upgraded_at column to the db_version table.
"""

from sqlalchemy.orm import Session
from sqlalchemy import text

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration001To101(BaseMigration):
    """Migration from 1.0.0 to 1.0.1"""
    
    @property
    def version(self) -> str:
        return "1.0.1"
    
    @property
    def previous_version(self) -> str:
        return "1.0.0"
    
    @property
    def description(self) -> str:
        return "Add upgraded_at column to db_version table"
    
    def upgrade(self, session: Session) -> bool:
        """
        Add upgraded_at column to db_version table.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if column already exists
            if self.column_exists('db_version', 'upgraded_at'):
                logger.info("Column upgraded_at already exists in db_version table")
                return True
            
            # Add the column
            sql = "ALTER TABLE db_version ADD COLUMN upgraded_at DATETIME"
            if not self.execute_sql(session, sql):
                return False
            
            logger.info("Successfully added upgraded_at column to db_version table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add upgraded_at column: {e}")
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that the upgraded_at column was added successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        return self.column_exists('db_version', 'upgraded_at')
    
    def downgrade(self, session: Session) -> bool:
        """
        Remove upgraded_at column from db_version table.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # SQLite doesn't support DROP COLUMN, so we skip downgrade
            logger.warning("SQLite doesn't support DROP COLUMN, skipping downgrade")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove upgraded_at column: {e}")
            return False
