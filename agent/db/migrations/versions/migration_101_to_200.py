"""
Migration from version 1.0.1 to 2.0.0

This migration creates the chat_notification table for system notifications.
"""

from sqlalchemy.orm import Session
from sqlalchemy import MetaData, Table, Column, String, Integer, JSON, Boolean, ForeignKey

from ..base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger


class Migration101To200(BaseMigration):
    """Migration from 1.0.1 to 2.0.0"""
    
    @property
    def version(self) -> str:
        return "2.0.0"
    
    @property
    def previous_version(self) -> str:
        return "1.0.1"
    
    @property
    def description(self) -> str:
        return "Create chat_notification table for system notifications"
    
    def upgrade(self, session: Session) -> bool:
        """
        Create chat_notification table.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if table already exists
            if self.table_exists('chat_notification'):
                logger.info("Table chat_notification already exists")
                return True
            
            # Create the table
            metadata = MetaData()
            chat_notification = Table(
                'chat_notification',
                metadata,
                Column('uid', String(64), primary_key=True),
                Column('chatId', String(64), ForeignKey('chats.id'), nullable=False),
                Column('content', JSON, nullable=False),
                Column('timestamp', Integer, nullable=False),
                Column('isRead', Boolean, default=False)
            )
            
            metadata.create_all(self.engine, tables=[chat_notification])
            
            logger.info("Successfully created chat_notification table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create chat_notification table: {e}")
            return False
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that the chat_notification table was created successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if validation passes, False otherwise
        """
        return self.table_exists('chat_notification')
    
    def downgrade(self, session: Session) -> bool:
        """
        Drop chat_notification table.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if not self.table_exists('chat_notification'):
                logger.info("Table chat_notification doesn't exist, nothing to drop")
                return True
            
            sql = "DROP TABLE chat_notification"
            if not self.execute_sql(session, sql):
                return False
            
            logger.info("Successfully dropped chat_notification table")
            return True
            
        except Exception as e:
            logger.error(f"Failed to drop chat_notification table: {e}")
            return False
