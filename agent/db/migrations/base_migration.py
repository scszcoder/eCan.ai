"""
Base migration class for database schema changes.

This module provides the base class that all migration scripts should inherit from.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import Engine
from utils.logger_helper import logger_helper as logger


class BaseMigration(ABC):
    """
    Base class for all database migrations.
    
    Each migration script should inherit from this class and implement
    the required methods for upgrading and downgrading the database.
    """
    
    def __init__(self, engine: Engine):
        """
        Initialize the migration.
        
        Args:
            engine: SQLAlchemy engine instance
        """
        self.engine = engine
        
    @property
    @abstractmethod
    def version(self) -> str:
        """
        The target version this migration upgrades to.
        
        Returns:
            str: Version string (e.g., "2.0.0")
        """
        pass
    
    @property
    @abstractmethod
    def previous_version(self) -> str:
        """
        The version this migration upgrades from.
        
        Returns:
            str: Previous version string (e.g., "1.0.0")
        """
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """
        Human-readable description of what this migration does.
        
        Returns:
            str: Migration description
        """
        pass
    
    @abstractmethod
    def upgrade(self, session: Session) -> bool:
        """
        Perform the database upgrade.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if upgrade successful, False otherwise
        """
        pass
    
    def downgrade(self, session: Session) -> bool:
        """
        Perform the database downgrade (optional).
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if downgrade successful, False otherwise
        """
        logger.warning(f"Downgrade not implemented for migration {self.version}")
        return False
    
    def validate_preconditions(self, session: Session) -> bool:
        """
        Validate that preconditions for this migration are met.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if preconditions are met, False otherwise
        """
        return True
    
    def validate_postconditions(self, session: Session) -> bool:
        """
        Validate that the migration was applied successfully.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            bool: True if postconditions are met, False otherwise
        """
        return True
    
    def get_migration_info(self) -> Dict[str, Any]:
        """
        Get information about this migration.
        
        Returns:
            dict: Migration information
        """
        return {
            'version': self.version,
            'previous_version': self.previous_version,
            'description': self.description,
            'class_name': self.__class__.__name__
        }
    
    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.
        
        Args:
            table_name: Name of the table to check
            
        Returns:
            bool: True if table exists, False otherwise
        """
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()
    
    def column_exists(self, table_name: str, column_name: str) -> bool:
        """
        Check if a column exists in a table.
        
        Args:
            table_name: Name of the table
            column_name: Name of the column
            
        Returns:
            bool: True if column exists, False otherwise
        """
        from sqlalchemy import inspect
        inspector = inspect(self.engine)
        try:
            columns = [col['name'] for col in inspector.get_columns(table_name)]
            return column_name in columns
        except Exception:
            return False
    
    def execute_sql(self, session: Session, sql: str, params: Optional[Dict] = None) -> bool:
        """
        Execute raw SQL with error handling.
        
        Args:
            session: SQLAlchemy session
            sql: SQL statement to execute
            params: Optional parameters for the SQL statement
            
        Returns:
            bool: True if execution successful, False otherwise
        """
        try:
            from sqlalchemy import text
            if params:
                session.execute(text(sql), params)
            else:
                session.execute(text(sql))
            return True
        except Exception as e:
            logger.error(f"Failed to execute SQL: {sql}, Error: {e}")
            return False
    
    def execute_with_engine(self, sql: str, params: Optional[Dict] = None) -> bool:
        """
        Execute raw SQL using engine.connect() - use only when session is not available.
        
        Warning: Prefer using session.execute_sql() instead to avoid database locks.
        
        Args:
            sql: SQL statement to execute
            params: Optional parameters for the SQL statement
            
        Returns:
            bool: True if execution successful, False otherwise
        """
        try:
            from sqlalchemy import text
            with self.engine.connect() as conn:
                if params:
                    conn.execute(text(sql), params)
                else:
                    conn.execute(text(sql))
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to execute SQL with engine: {sql}, Error: {e}")
            return False
    
    def ensure_table_exists(self, session: Session, table_name: str, create_sql: str) -> bool:
        """
        Ensure a table exists, creating it if necessary.
        
        Args:
            session: SQLAlchemy session
            table_name: Name of the table to check/create
            create_sql: CREATE TABLE SQL statement
            
        Returns:
            bool: True if table exists or was created successfully
        """
        if self.table_exists(table_name):
            logger.debug(f"Table '{table_name}' already exists, skipping creation")
            return True
        
        try:
            from sqlalchemy import text
            logger.info(f"Creating missing table '{table_name}'...")
            session.execute(text(create_sql))
            session.commit()
            logger.info(f"Table '{table_name}' created successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to create table '{table_name}': {e}")
            return False
    
    def ensure_column_exists(self, session: Session, table_name: str, column_name: str, column_def: str) -> bool:
        """
        Ensure a column exists in a table, adding it if necessary.
        
        Args:
            session: SQLAlchemy session
            table_name: Name of the table
            column_name: Name of the column to check/add
            column_def: Column definition (e.g., "VARCHAR(64)")
            
        Returns:
            bool: True if column exists or was added successfully
        """
        if self.column_exists(table_name, column_name):
            logger.debug(f"Column '{table_name}.{column_name}' already exists, skipping")
            return True
        
        try:
            from sqlalchemy import text
            alter_sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}"
            logger.info(f"Adding missing column '{table_name}.{column_name}'...")
            session.execute(text(alter_sql))
            session.commit()
            logger.info(f"Column '{table_name}.{column_name}' added successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to add column '{table_name}.{column_name}': {e}")
            return False
