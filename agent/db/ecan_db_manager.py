"""
eCan Database Manager - Unified database management for eCan.ai

This module provides a centralized database manager that handles
database initialization, migration, and connection management.
"""

import os
from typing import Optional, Dict, Any
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

from .core import (
    Base, 
    get_engine, 
    get_session_factory, 
    create_all_tables, 
    drop_all_tables,
    ECAN_BASE_DB,
    DBMigration
)
from .services import SingletonMeta
from utils.logger_helper import logger_helper as logger


class ECanDBManager(metaclass=SingletonMeta):
    """
    Unified database manager for eCan.ai system.
    
    This class provides centralized database management including:
    - Database initialization and table creation
    - Database migration management
    - Connection pooling and session management
    - Database health monitoring
    """
    
    def __init__(self, db_path: str = None, auto_migrate: bool = True):
        """
        Initialize eCan database manager.
        
        Args:
            db_path (str, optional): Database file path, defaults to ECAN_BASE_DB
            auto_migrate (bool): Whether to automatically run migrations, defaults to True
        """
        self.db_path = db_path or ECAN_BASE_DB
        self.auto_migrate = auto_migrate
        self.engine = None
        self.SessionFactory = None
        self._initialized = False
        
        # Initialize database
        self.initialize_database()
    
    def initialize_database(self) -> bool:
        """
        Initialize database with tables and migrations.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info(f"[ECanDBManager] Initializing database: {self.db_path}")
            
            # Create engine and session factory
            self.engine = get_engine(self.db_path)
            self.SessionFactory = get_session_factory(self.db_path)
            
            # Create all tables
            logger.info("[ECanDBManager] Creating database tables...")
            create_all_tables(self.db_path)
            
            # Run migrations if enabled
            if self.auto_migrate:
                logger.info("[ECanDBManager] Running database migrations...")
                self._run_migrations()
            
            self._initialized = True
            logger.info("[ECanDBManager] Database initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ECanDBManager] Database initialization failed: {e}")
            return False
    
    def _run_migrations(self) -> bool:
        """
        Run database migrations to latest version.
        
        Returns:
            bool: True if migrations successful, False otherwise
        """
        try:
            migrator = DBMigration(self.db_path)
            current_version = migrator.get_current_version()
            logger.info(f"[ECanDBManager] Current database version: {current_version}")
            
            # Upgrade to latest version (2.0.0)
            success = migrator.upgrade_to_version('2.0.0', 'Auto-upgrade to latest version')
            if success:
                logger.info("[ECanDBManager] Database migrations completed successfully")
            else:
                logger.warning("[ECanDBManager] Database migrations failed or not needed")
            
            return success
            
        except Exception as e:
            logger.error(f"[ECanDBManager] Database migration failed: {e}")
            return False
    
    @contextmanager
    def get_session(self):
        """
        Get a database session with automatic cleanup.
        
        Yields:
            Session: SQLAlchemy session instance
        """
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
            
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_engine(self):
        """
        Get the database engine.
        
        Returns:
            Engine: SQLAlchemy engine instance
        """
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.engine
    
    def get_session_factory(self):
        """
        Get the session factory.
        
        Returns:
            sessionmaker: SQLAlchemy session factory
        """
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.SessionFactory
    
    def health_check(self) -> Dict[str, Any]:
        """
        Perform database health check.
        
        Returns:
            dict: Health check results
        """
        try:
            with self.get_session() as session:
                # Test basic database connectivity
                from sqlalchemy import text
                result = session.execute(text("SELECT 1")).fetchone()
                
                # Check table existence
                from sqlalchemy import inspect
                inspector = inspect(self.engine)
                tables = inspector.get_table_names()
                
                return {
                    "status": "healthy",
                    "database_path": self.db_path,
                    "connection": "ok" if result else "failed",
                    "tables_count": len(tables),
                    "tables": tables,
                    "initialized": self._initialized
                }
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "database_path": self.db_path,
                "error": str(e),
                "initialized": self._initialized
            }
    
    def reset_database(self) -> bool:
        """
        Reset database by dropping and recreating all tables.
        
        WARNING: This will delete all data!
        
        Returns:
            bool: True if reset successful, False otherwise
        """
        try:
            logger.warning("[ECanDBManager] Resetting database - ALL DATA WILL BE LOST!")
            
            # Drop all tables
            drop_all_tables(self.db_path)
            logger.info("[ECanDBManager] All tables dropped")
            
            # Recreate tables
            create_all_tables(self.db_path)
            logger.info("[ECanDBManager] All tables recreated")
            
            # Run migrations
            if self.auto_migrate:
                self._run_migrations()
            
            logger.info("[ECanDBManager] Database reset completed")
            return True
            
        except Exception as e:
            logger.error(f"[ECanDBManager] Database reset failed: {e}")
            return False
    
    def backup_database(self, backup_path: str) -> bool:
        """
        Create a backup of the database.
        
        Args:
            backup_path (str): Path for the backup file
            
        Returns:
            bool: True if backup successful, False otherwise
        """
        try:
            import shutil
            
            if not os.path.exists(self.db_path):
                logger.error(f"[ECanDBManager] Source database not found: {self.db_path}")
                return False
            
            # Create backup directory if it doesn't exist
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"[ECanDBManager] Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"[ECanDBManager] Database backup failed: {e}")
            return False
    
    def get_database_info(self) -> Dict[str, Any]:
        """
        Get comprehensive database information.
        
        Returns:
            dict: Database information including size, tables, etc.
        """
        info = {
            "database_path": self.db_path,
            "initialized": self._initialized,
            "auto_migrate": self.auto_migrate
        }
        
        try:
            # File information
            if os.path.exists(self.db_path):
                stat = os.stat(self.db_path)
                info.update({
                    "file_size_bytes": stat.st_size,
                    "file_size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "last_modified": stat.st_mtime
                })
            
            # Database health
            health = self.health_check()
            info.update(health)
            
            # Migration information
            if self._initialized:
                try:
                    migrator = DBMigration(self.db_path)
                    current_version = migrator.get_current_version()
                    info["database_version"] = current_version
                except Exception as e:
                    info["database_version"] = f"Error: {e}"
            
        except Exception as e:
            info["error"] = str(e)
        
        return info


# Global database manager instance
_db_manager: Optional[ECanDBManager] = None


def get_db_manager(db_dir: str = None, auto_migrate: bool = True) -> ECanDBManager:
    """
    Get or create the global database manager instance.
    
    Args:
        db_dir (str, optional): Database file dir
        auto_migrate (bool): Whether to automatically run migrations
        
    Returns:
        ECanDBManager: Global database manager instance
    """
    global _db_manager
    
    if _db_manager is None:
        db_path = os.path.join(db_dir, ECAN_BASE_DB)
        _db_manager = ECanDBManager(db_path, auto_migrate)
    
    return _db_manager


def initialize_ecan_database(db_dir: str = None, auto_migrate: bool = True) -> ECanDBManager:
    """
    Initialize eCan database system.
    
    This is the main entry point for database initialization.
    Should be called once at application startup.
    
    Args:
        db_dir (str, optional): Database file dir
        auto_migrate (bool): Whether to automatically run migrations
        
    Returns:
        ECanDBManager: Initialized database manager
    """
    logger.info("[ECanDBManager] Initializing eCan database system...")
    db_manager = get_db_manager(db_dir, auto_migrate)
    
    # Log database information
    info = db_manager.get_database_info()
    logger.info(f"[ECanDBManager] Database info: {info}")
    
    return db_manager
