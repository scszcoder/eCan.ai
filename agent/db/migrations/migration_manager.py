"""
Migration manager for automatic database schema management.

This module provides the MigrationManager class that automatically discovers,
loads, and executes database migration scripts in the correct order.
"""

import os
import time
import importlib
import inspect
from typing import Dict, List, Type, Any, Optional
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from ..models import DBVersion
from .base_migration import BaseMigration
from utils.logger_helper import logger_helper as logger

class MigrationManager:
    """
    Manages database migrations with automatic discovery and execution.
    
    This class automatically scans for migration files, loads them,
    and executes them in the correct order based on version dependencies.
    """
    
    def __init__(self, engine: Engine, migrations_package: str = "agent.db.migrations.versions"):
        """
        Initialize the migration manager.
        
        Args:
            engine: SQLAlchemy engine instance
            migrations_package: Package path containing migration scripts
        """
        self.engine = engine
        self.Session = sessionmaker(bind=engine)
        self.migrations_package = migrations_package
        self._migration_classes: Dict[str, Type[BaseMigration]] = {}
        self._migration_graph: Dict[str, str] = {}  # version -> previous_version
        
        # Load all available migrations
        self._discover_migrations()
        self._build_migration_graph()
    
    def _discover_migrations(self) -> None:
        """
        Automatically discover and load all migration classes.
        """
        try:
            # Get the migrations/versions directory path
            migrations_dir = os.path.join(
                os.path.dirname(__file__), 
                "versions"
            )
            
            if not os.path.exists(migrations_dir):
                logger.warning(f"Migrations directory not found: {migrations_dir}")
                return
            
            # Scan for Python files in the versions directory
            for filename in os.listdir(migrations_dir):
                if filename.endswith('.py') and not filename.startswith('__'):
                    module_name = filename[:-3]  # Remove .py extension
                    
                    try:
                        # Import the migration module
                        full_module_name = f"{self.migrations_package}.{module_name}"
                        module = importlib.import_module(full_module_name)
                        
                        # Find migration classes in the module
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            if (issubclass(obj, BaseMigration) and 
                                obj != BaseMigration and 
                                hasattr(obj, 'version')):
                                
                                # Create instance to get version info
                                try:
                                    migration_instance = obj(self.engine)
                                    version = migration_instance.version
                                    self._migration_classes[version] = obj
                                    logger.debug(f"Loaded migration: {version} from {module_name}")
                                except Exception as e:
                                    logger.error(f"Failed to instantiate migration {name}: {e}")
                                    
                    except Exception as e:
                        logger.error(f"Failed to load migration module {module_name}: {e}")
                        
        except Exception as e:
            logger.error(f"Failed to discover migrations: {e}")
    
    def _build_migration_graph(self) -> None:
        """
        Build the migration dependency graph.
        """
        for version, migration_class in self._migration_classes.items():
            try:
                migration_instance = migration_class(self.engine)
                self._migration_graph[version] = migration_instance.previous_version
            except Exception as e:
                logger.error(f"Failed to build migration graph for {version}: {e}")
    
    def _is_fresh_database(self, session=None) -> bool:
        """
        Check if this is a fresh database installation.
        
        A database is considered fresh if:
        1. No tables exist at all, OR
        2. Core tables exist but have no data
        
        Args:
            session: Optional SQLAlchemy session to use
        
        Returns:
            bool: True if this is a fresh database, False otherwise
        """
        try:
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            table_names = inspector.get_table_names()
            
            # If no tables exist at all, it's definitely fresh
            if not table_names:
                logger.debug("No tables found - this is a fresh database")
                return True
            
            # Core tables that should exist in any database
            core_tables = {'db_version', 'chats', 'members', 'messages'}
            existing_core_tables = set(table_names) & core_tables
            
            # If we have very few core tables, it's likely fresh
            if len(existing_core_tables) < 2:
                logger.debug(f"Only {len(existing_core_tables)} core tables found - likely fresh database")
                return True
            
            # Check if tables are mostly empty (indicating fresh installation)
            # Use provided session or create a temporary one
            should_close_session = session is None
            if session is None:
                session = self.Session()
            
            try:
                # Check if chats table has any data
                if 'chats' in table_names:
                    try:
                        result = session.execute("SELECT COUNT(*) FROM chats").scalar()
                        if result > 0:
                            logger.debug(f"Found {result} records in chats table - not fresh")
                            return False
                    except Exception:
                        # Table might not be properly created yet
                        pass
                
                # Check if messages table has any data
                if 'messages' in table_names:
                    try:
                        result = session.execute("SELECT COUNT(*) FROM messages").scalar()
                        if result > 0:
                            logger.debug(f"Found {result} records in messages table - not fresh")
                            return False
                    except Exception:
                        # Table might not be properly created yet
                        pass
                
                # If tables exist but are empty, consider it fresh
                logger.debug("Tables exist but are empty - considering as fresh database")
                return True
                
            finally:
                if should_close_session:
                    session.close()
                
        except Exception as e:
            logger.debug(f"Error checking database freshness: {e}")
            # If we can't determine, assume it's fresh for new installations
            return True
    
    def _get_latest_version(self) -> str:
        """
        Get the latest available version from migrations.
        
        Returns:
            str: Latest version string
        """
        if not self._migration_classes:
            return '1.0.0'
        
        return max(
            self._migration_classes.keys(),
            key=self._version_to_tuple
        )
    
    def get_current_version(self) -> str:
        """
        Get the current database version.
        
        Returns:
            str: Current database version
        """
        session = None
        try:
            # Create session with simple retry
            for attempt in range(3):
                try:
                    session = self.Session()
                    break
                except OperationalError as e:
                    if attempt < 2:  # Retry up to 2 times
                        logger.warning(f"[MigrationManager] Session creation failed, retrying... ({e})")
                        time.sleep(0.3)
                    else:
                        raise e
            
            # Try to get the version record
            version = DBVersion.get_current_version(session)
            if version:
                return version.version
            
            # If no version record, check if this is a completely fresh database
            is_fresh = self._is_fresh_database(session)
            
            if is_fresh:
                # Fresh database: don't initialize here, let migrate_to_latest handle it
                raise Exception("Fresh database detected - needs initialization")
            else:
                # Existing database without version record: start from 1.0.0
                DBVersion.upgrade_version(session, '1.0.0', description='Initial version for existing database')
                session.commit()
                return '1.0.0'
                
        except Exception as e:
            logger.error(f"Failed to get current database version: {e}")
            # Re-raise the exception so migrate_to_latest can handle it properly
            raise
        finally:
            if session:
                session.close()
    
    def get_available_migrations(self) -> List[Dict[str, Any]]:
        """
        Get information about all available migrations.
        
        Returns:
            List[Dict]: List of migration information
        """
        migrations_info = []
        for version, migration_class in self._migration_classes.items():
            try:
                migration_instance = migration_class(self.engine)
                migrations_info.append(migration_instance.get_migration_info())
            except Exception as e:
                logger.error(f"Failed to get info for migration {version}: {e}")
        
        # Sort by version
        migrations_info.sort(key=lambda x: self._version_to_tuple(x['version']))
        return migrations_info
    
    def get_migration_path(self, from_version: str, to_version: str) -> List[str]:
        """
        Get the migration path from one version to another.
        
        Args:
            from_version: Starting version
            to_version: Target version
            
        Returns:
            List[str]: List of versions in the migration path
        """
        if from_version == to_version:
            return []
        
        # Build path using the migration graph
        path = []
        current = to_version
        
        # Traverse backwards to build the path
        while current != from_version and current in self._migration_graph:
            path.append(current)
            current = self._migration_graph[current]
        
        if current != from_version:
            raise ValueError(f"No migration path found from {from_version} to {to_version}")
        
        # Reverse to get forward path
        path.reverse()
        return path
    
    def migrate_to_version(self, target_version: str, description: Optional[str] = None) -> bool:
        """
        Migrate the database to a specific version.
        
        Args:
            target_version: Target version to migrate to
            description: Optional description for the migration
            
        Returns:
            bool: True if migration successful, False otherwise
        """
        # Use a single session for the entire migration process
        session = None
        try:
            # Ensure all tables are created first
            from ..core import create_all_tables
            create_all_tables(self.engine)
            
            # Create session with simple retry
            session = None
            for attempt in range(3):
                try:
                    session = self.Session()
                    break
                except OperationalError as e:
                    if attempt < 2:  # Retry up to 2 times
                        logger.warning(f"[MigrationManager] Session creation failed, retrying... ({e})")
                        time.sleep(0.5)
                    else:
                        raise e
            
            # Check current version using the same session
            is_fresh = self._is_fresh_database(session)
            version_record = DBVersion.get_current_version(session)
            
            if not version_record:
                if is_fresh:
                    # Fresh database: initialize directly to target version
                    DBVersion.upgrade_version(session, target_version, description or 'Fresh database initialization')
                    session.commit()
                    logger.info(f"Initialized fresh database to version {target_version}")
                    return True
                else:
                    # Existing database without version record: start from 1.0.0
                    current_version = '1.0.0'
                    DBVersion.upgrade_version(session, current_version, description='Initial version for existing database')
                    session.commit()
            else:
                current_version = version_record.version
            
            if current_version == target_version:
                logger.info(f"Database is already at version {target_version}")
                return True
            
            # Get migration path
            migration_path = self.get_migration_path(current_version, target_version)
            
            if not migration_path:
                logger.info(f"No migrations needed from {current_version} to {target_version}")
                return True
            
            logger.info(f"Migration path: {current_version} -> {' -> '.join(migration_path)}")
            
            # Execute migrations in order using the same session
            for version in migration_path:
                if not self._execute_migration(session, version):
                    session.rollback()
                    return False
            
            # Update final version
            DBVersion.upgrade_version(
                session, 
                target_version, 
                description or f"Migrated to version {target_version}"
            )
            session.commit()
            
            logger.info(f"Successfully migrated from {current_version} to {target_version}")
            return True
            
        except Exception as e:
            if session:
                session.rollback()
            logger.error(f"Migration failed: {e}")
            return False
        finally:
            if session:
                session.close()
    
    def migrate_to_latest(self) -> bool:
        """
        Migrate to the latest available version.
        
        Returns:
            bool: True if migration successful, False otherwise
        """
        if not self._migration_classes:
            logger.info("No migrations available")
            return True
        
        # Find the latest version
        latest_version = max(
            self._migration_classes.keys(),
            key=self._version_to_tuple
        )
        
        # Check current version first to avoid unnecessary migration attempts
        try:
            current_version = self.get_current_version()
            if current_version == latest_version:
                logger.info(f"Database is already at the latest version {latest_version}")
                return True
            
            logger.info(f"Migrating from {current_version} to {latest_version}")
            return self.migrate_to_version(latest_version, "Auto-migrate to latest version")
            
        except Exception as e:
            # Check if this is a fresh database (no tables at all)
            try:
                from sqlalchemy import inspect
                inspector = inspect(self.engine)
                table_names = inspector.get_table_names()
                
                if not table_names:
                    # Fresh database: create all tables directly without migration
                    logger.info("Detected fresh database with no tables. Creating latest schema directly.")
                    
                    # Use transaction to ensure atomicity
                    session = self.Session()
                    try:
                        # Create all tables first
                        from ..core import create_all_tables
                        create_all_tables(self.engine)
                        
                        # Verify tables were created
                        inspector = inspect(self.engine)
                        created_tables = inspector.get_table_names()
                        if not created_tables:
                            raise Exception("Failed to create database tables")
                        
                        # Create version record
                        from ..models import DBVersion
                        DBVersion.upgrade_version(session, latest_version, description='Fresh database initialization')
                        session.commit()
                        logger.info(f"Successfully initialized fresh database to latest version {latest_version} with {len(created_tables)} tables")
                        
                    except Exception as create_e:
                        session.rollback()
                        logger.error(f"Failed to initialize fresh database: {create_e}")
                        raise create_e
                    finally:
                        session.close()
                    
                    return True
                else:
                    # Database has tables but version check failed - skip migration
                    logger.warning("Database has tables but version check failed. Skipping migration.")
                    return True
                    
            except Exception as inspect_e:
                logger.error(f"Failed to inspect database: {inspect_e}")
                logger.warning("Skipping migration due to database access issues.")
                return True
    
    def _execute_migration(self, session: Session, version: str) -> bool:
        """
        Execute a specific migration.
        
        Args:
            session: Database session
            version: Version to migrate to
            
        Returns:
            bool: True if successful, False otherwise
        """
        if version not in self._migration_classes:
            logger.error(f"Migration not found for version {version}")
            return False
        
        migration_class = self._migration_classes[version]
        migration = migration_class(self.engine)
        
        logger.info(f"Executing migration to {version}: {migration.description}")
        
        try:
            # Validate preconditions
            if not migration.validate_preconditions(session):
                logger.error(f"Preconditions failed for migration {version}")
                return False
            
            # Execute the migration
            if not migration.upgrade(session):
                logger.error(f"Migration upgrade failed for version {version}")
                return False
            
            # Validate postconditions
            if not migration.validate_postconditions(session):
                logger.error(f"Postconditions failed for migration {version}")
                return False
            
            logger.info(f"Successfully executed migration to {version}")
            return True
            
        except Exception as e:
            logger.error(f"Exception during migration {version}: {e}")
            return False
    
    def _version_to_tuple(self, version: str) -> tuple:
        """
        Convert version string to tuple for comparison.
        
        Args:
            version: Version string (e.g., "2.1.0")
            
        Returns:
            tuple: Version as tuple (e.g., (2, 1, 0))
        """
        try:
            return tuple(int(x) for x in version.split('.'))
        except (ValueError, AttributeError):
            # Default to 1.0.0 if version parsing fails
            return (1, 0, 0)
    
    def get_migration_status(self) -> Dict[str, Any]:
        """
        Get current migration status and information.
        
        Returns:
            dict: Migration status information
        """
        try:
            current_version = self.get_current_version()
        except Exception as e:
            logger.error(f"Failed to get current version: {e}")
            current_version = '1.0.0'
        
        available_migrations = self.get_available_migrations()
        
        latest_version = max(
            self._migration_classes.keys(),
            key=self._version_to_tuple
        ) if self._migration_classes else current_version
        
        return {
            'current_version': current_version,
            'latest_version': latest_version,
            'available_migrations': available_migrations,
            'needs_migration': current_version != latest_version,
            'migration_path': self.get_migration_path(current_version, latest_version) if current_version != latest_version else []
        }
