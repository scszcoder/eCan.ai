"""
EC Database Manager - Unified database management for eCan.ai

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
    MigrationManager
)
from .services.db_agent_service import DBAgentService
from .services.db_org_service import DBOrgService
from .services.db_skill_service import DBSkillService
from .services.db_chat_service import DBChatService
from .services.db_task_service import DBTaskService
from utils.logger_helper import logger_helper as logger


class ECDBMgr:
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

        # Database services - will be initialized after database setup
        self.agent_service = None
        self.org_service = None
        self.skill_service = None
        self.chat_service = None
        self.task_service = None

        # Initialize database
        self.initialize_database()

        # Initialize all database services
        self._initialize_services()
    
    def initialize_database(self) -> bool:
        """
        Initialize database with tables and migrations.
        
        Returns:
            bool: True if initialization successful, False otherwise
        """
        try:
            logger.info(f"[ECDBMgr] Initializing database: {self.db_path}")
            
            # Create engine and session factory
            self.engine = get_engine(self.db_path)
            self.SessionFactory = get_session_factory(self.db_path)
            
            # Handle database schema initialization
            if self.auto_migrate:
                # Run migrations - this will automatically handle table creation
                logger.info("[ECDBMgr] Running database migrations...")
                migration_success = self._run_migrations()
                if not migration_success:
                    logger.warning("[ECDBMgr] Migration failed, falling back to table creation")
                    # Fallback: create tables if migration fails
                    logger.info("[ECDBMgr] Creating database tables as fallback...")
                    create_all_tables(self.db_path)
            else:
                # If auto_migrate is disabled, just create tables
                logger.info("[ECDBMgr] Auto-migrate disabled, creating database tables...")
                create_all_tables(self.db_path)
            
            self._initialized = True
            logger.info("[ECDBMgr] Database initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Database initialization failed: {e}")
            return False
    
    def _run_migrations(self) -> bool:
        """
        Run database migrations to latest version.
        
        Returns:
            bool: True if migrations successful, False otherwise
        """
        try:
            # Use new MigrationManager for automatic migration management
            migrator = MigrationManager(self.engine)
            current_version = migrator.get_current_version()
            logger.info(f"[ECDBMgr] Current database version: {current_version}")
            
            # Migrate to latest available version
            success = migrator.migrate_to_latest()
            if success:
                logger.info("[ECDBMgr] Database migrations completed successfully")
            else:
                logger.warning("[ECDBMgr] Database migrations failed or not needed")
            
            return success
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Database migration failed: {e}")
            return False

    def _initialize_services(self) -> bool:
        """
        Initialize all database services with unified engine and session.

        Returns:
            bool: True if services initialization successful, False otherwise
        """
        try:
            if not self._initialized:
                logger.warning("[ECDBMgr] Database not initialized, skipping services initialization")
                return False

            logger.info("[ECDBMgr] Initializing database services...")

            # Initialize all services with shared engine - direct instance creation
            self.agent_service = DBAgentService(engine=self.engine)
            self.org_service = DBOrgService(engine=self.engine)
            self.skill_service = DBSkillService(engine=self.engine)
            self.chat_service = DBChatService(engine=self.engine)
            self.task_service = DBTaskService(engine=self.engine)

            logger.info("[ECDBMgr] Initialized all database services as direct attributes")
            return True

        except Exception as e:
            logger.error(f"[ECDBMgr] Services initialization failed: {e}")
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

    def get_agent_service(self):
        """Get the agent database service."""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.agent_service

    def get_org_service(self):
        """Get the organization database service."""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.org_service

    def get_skill_service(self):
        """Get the skill database service."""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.skill_service

    def get_chat_service(self):
        """Get the chat database service."""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.chat_service

    def get_task_service(self):
        """Get the task database service."""
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return self.task_service

    def get_all_services(self) -> Dict[str, Any]:
        """
        Get all initialized database services.

        Returns:
            dict: Dictionary of all services
        """
        if not self._initialized:
            raise RuntimeError("Database manager not initialized")
        return {
            'agent': self.agent_service,
            'org': self.org_service,
            'skill': self.skill_service,
            'chat': self.chat_service,
            'task': self.task_service
        }
    
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
            logger.warning("[ECDBMgr] Resetting database - ALL DATA WILL BE LOST!")
            
            # Drop all tables
            drop_all_tables(self.db_path)
            logger.info("[ECDBMgr] All tables dropped")
            
            # Recreate tables
            create_all_tables(self.db_path)
            logger.info("[ECDBMgr] All tables recreated")
            
            # Run migrations
            if self.auto_migrate:
                self._run_migrations()
            
            logger.info("[ECDBMgr] Database reset completed")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Database reset failed: {e}")
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
                logger.error(f"[ECDBMgr] Source database not found: {self.db_path}")
                return False
            
            # Create backup directory if it doesn't exist
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            # Copy database file
            shutil.copy2(self.db_path, backup_path)
            logger.info(f"[ECDBMgr] Database backup created: {backup_path}")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Database backup failed: {e}")
            return False
    
    def close(self) -> bool:
        """
        Close database connections and clean up resources.
        
        This method should be called when the application is shutting down
        or when the user logs out.
        
        Returns:
            bool: True if cleanup successful, False otherwise
        """
        try:
            logger.info("[ECDBMgr] Closing database connections and cleaning up resources...")
            
            # Close all service connections if they have close methods
            services = [
                ('agent_service', self.agent_service),
                ('org_service', self.org_service), 
                ('skill_service', self.skill_service),
                ('chat_service', self.chat_service),
                ('task_service', self.task_service)
            ]
            
            for service_name, service in services:
                if service and hasattr(service, 'close'):
                    try:
                        service.close()
                        logger.debug(f"[ECDBMgr] Closed {service_name}")
                    except Exception as e:
                        logger.warning(f"[ECDBMgr] Failed to close {service_name}: {e}")
            
            # Dispose of the engine connection pool
            if hasattr(self, 'engine') and self.engine:
                try:
                    self.engine.dispose()
                    logger.info("[ECDBMgr] Database engine disposed")
                except Exception as e:
                    logger.warning(f"[ECDBMgr] Failed to dispose engine: {e}")
            
            # Clear references
            self.engine = None
            self.SessionFactory = None
            self.agent_service = None
            self.org_service = None
            self.skill_service = None
            self.chat_service = None
            self.task_service = None
            self._initialized = False
            
            logger.info("[ECDBMgr] Database manager closed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Failed to close database manager: {e}")
            return False
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close resources."""
        self.close()
    
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
                    migrator = MigrationManager(self.engine)
                    current_version = migrator.get_current_version()
                    info["database_version"] = current_version
                except Exception as e:
                    info["database_version"] = f"Error: {e}"
            
        except Exception as e:
            info["error"] = str(e)
        
        return info


def create_db_manager(db_dir: str = None, auto_migrate: bool = True) -> ECDBMgr:
    """
    Create a new database manager instance.
    
    Args:
        db_dir (str, optional): Database file directory
        auto_migrate (bool): Whether to automatically run migrations
    
    Returns:
        ECDBMgr: New database manager instance
    """
    if db_dir is None:
        db_path = ECAN_BASE_DB  # Use default database name in current directory
    else:
        db_path = os.path.join(db_dir, ECAN_BASE_DB)
    
    return ECDBMgr(db_path, auto_migrate)


def initialize_ecan_database(db_dir: str = None, auto_migrate: bool = True) -> ECDBMgr:
    """
    Initialize eCan database system.

    This is the main entry point for database initialization.
    Creates a new database manager instance (not singleton).

    Args:
        db_dir (str, optional): Database file dir
        auto_migrate (bool): Whether to automatically run migrations

    Returns:
        ECDBMgr: initialized database manager
    """
    logger.info("[ECDBMgr] Initializing eCan database system...")
    db_manager = create_db_manager(db_dir, auto_migrate)

    # Log database information
    info = db_manager.get_database_info()
    logger.info(f"[ECDBMgr] Database info: {info}")

    return db_manager


# Backward compatibility - deprecated
def get_db_manager(db_dir: str = None, auto_migrate: bool = True) -> ECDBMgr:
    """
    Deprecated: Use create_db_manager() instead.
    
    This function is kept for backward compatibility but will be removed in future versions.
    """
    logger.warning("[ECDBMgr] get_db_manager() is deprecated, use create_db_manager() instead")
    return create_db_manager(db_dir, auto_migrate)
