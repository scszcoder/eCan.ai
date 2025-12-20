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
from .migrations.migration_config import LATEST_DATABASE_VERSION
from .services.db_agent_service import DBAgentService
from .services.db_org_service import DBOrgService
from .services.db_skill_service import DBSkillService
from .services.db_chat_service import DBChatService
from .services.db_task_service import DBTaskService
from .services.db_avatar_service import DBAvatarService
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
            db_path (str, optional): Database directory path, defaults to current directory
            auto_migrate (bool): Whether to automatically run migrations, defaults to True
        """
        if db_path:
            self.db_path = os.path.join(db_path, ECAN_BASE_DB)
        else:
            self.db_path = ECAN_BASE_DB
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
                
                # Always ensure tables exist and version record is created
                # Check if tables actually exist (migration might have been skipped)
                if not self._tables_exist():
                    logger.info("[ECDBMgr] Tables not found, creating them now...")
                    create_all_tables(self.db_path)
                
                # Now ensure version record exists (after tables are confirmed to exist)
                self._ensure_version_record()
            else:
                # If auto_migrate is disabled, just create tables
                logger.info("[ECDBMgr] Auto-migrate disabled, creating database tables...")
                create_all_tables(self.db_path)
                # Ensure version record exists
                self._ensure_version_record()
            
            self._initialized = True
            logger.info("[ECDBMgr] Database initialization completed successfully")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Database initialization failed: {e}")
            return False
    
    def _tables_exist(self) -> bool:
        """
        Check if database tables exist.
        
        Returns:
            bool: True if tables exist, False otherwise
        """
        try:
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            table_names = inspector.get_table_names()
            
            # Check for essential tables
            essential_tables = ['db_version', 'chats', 'users']
            for table in essential_tables:
                if table not in table_names:
                    return False
            
            logger.info(f"[ECDBMgr] Found {len(table_names)} tables in database")
            return True
            
        except Exception as e:
            logger.error(f"[ECDBMgr] Failed to check table existence: {e}")
            return False

    def _ensure_version_record(self) -> bool:
        """
        Ensure that a version record exists in the database.
        This is called after table creation.
        
        Returns:
            bool: True if version record exists or was created successfully
        """
        try:
            session = self.SessionFactory()
            try:
                # Use direct SQL to check and create version record
                from sqlalchemy import text
                
                # Check if version record already exists
                result = session.execute(text("SELECT COUNT(*) FROM db_version")).fetchone()
                if result and result[0] > 0:
                    logger.info("[ECDBMgr] Version record already exists")
                    return True
                
                # Create version record for latest version using direct SQL
                latest_version = LATEST_DATABASE_VERSION
                import uuid
                from datetime import datetime
                
                version_id = str(uuid.uuid4())
                now = datetime.utcnow()
                
                session.execute(text("""
                    INSERT INTO db_version (id, version, description, upgraded_at, created_at, updated_at)
                    VALUES (:id, :version, :description, :upgraded_at, :created_at, :updated_at)
                """), {
                    'id': version_id,
                    'version': latest_version,
                    'description': 'Fresh database initialization',
                    'upgraded_at': now,
                    'created_at': now,
                    'updated_at': now
                })
                
                session.commit()
                logger.info(f"[ECDBMgr] Created version record: {latest_version}")
                return True
                
            finally:
                session.close()
                
        except Exception as e:
            logger.error(f"[ECDBMgr] Failed to ensure version record: {e}")
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

            # Migrate directly to latest version, version check handled internally
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
            self.avatar_service = DBAvatarService(engine=self.engine)
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
            
            # Migration information - avoid creating new MigrationManager during initialization
            if self._initialized:
                try:
                    # Check if we can safely access the database
                    with self.get_session() as session:
                        # Simple version check without creating new MigrationManager
                        from .models import DBVersion
                        version_record = DBVersion.get_current_version(session)
                        if version_record:
                            info["database_version"] = version_record.version
                        else:
                            info["database_version"] = "No version record found"
                except Exception as e:
                    info["database_version"] = f"Error: {e}"
            
        except Exception as e:
            info["error"] = str(e)
        
        return info


def initialize_ecan_database(db_dir: str = None, auto_migrate: bool = True) -> ECDBMgr:
    """
    Initialize eCan database system.

    This is the main entry point for database initialization.
    Creates a new database manager instance (not singleton).

    Args:
        db_dir (str, optional): Database directory path
        auto_migrate (bool): Whether to automatically run migrations

    Returns:
        ECDBMgr: initialized database manager
    """
    logger.info("[ECDBMgr] Initializing eCan database system...")
    db_manager = ECDBMgr(db_dir, auto_migrate)

    # Log database information
    info = db_manager.get_database_info()
    logger.info(f"[ECDBMgr] Database info: {info}")

    return db_manager

