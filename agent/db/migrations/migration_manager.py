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
from .migration_config import (
    get_latest_version, 
    is_version_supported, 
    get_version_path,
    version_to_tuple,
    compare_versions
)
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

        # Lazy loading: don't load all migration scripts during initialization
        # Only load relevant scripts when migration is actually needed

    def _load_migration(self, version: str) -> Optional[Type[BaseMigration]]:
        """
        Load migration script for specific version on demand.

        Args:
            version: Version number to load

        Returns:
            Optional[Type[BaseMigration]]: Migration class, returns None if loading fails
        """
        # If already loaded, return directly
        if version in self._migration_classes:
            return self._migration_classes[version]

        # Infer filename pattern based on version number
        version_patterns = {
            "1.0.1": "migration_001_to_101",
            "2.0.0": "migration_101_to_200",
            "3.0.0": "migration_200_to_300",
            "3.0.1": "migration_300_to_301",
            "3.0.2": "migration_301_to_302",
            "3.0.3": "migration_302_to_303",
            "3.0.4": "migration_303_to_304",
            "3.0.5": "migration_304_to_305",
            "3.0.6": "migration_305_to_306",
            "3.0.7": "migration_306_to_307"
        }
        
        module_name = version_patterns.get(version)
        if not module_name:
            logger.error(f"No migration module pattern found for version {version}")
            return None
        
        try:
            # Import specific migration module
            full_module_name = f"{self.migrations_package}.{module_name}"
            module = importlib.import_module(full_module_name)

            # Find migration class
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BaseMigration) and 
                    obj != BaseMigration and 
                    hasattr(obj, 'version')):
                    
                    try:
                        migration_instance = obj(self.engine)
                        if migration_instance.version == version:
                            self._migration_classes[version] = obj
                            logger.debug(f"Loaded migration: {version} from {module_name}")
                            return obj
                    except Exception as e:
                        logger.error(f"Failed to instantiate migration {name}: {e}")
            
            logger.error(f"No migration class found for version {version} in {module_name}")
            return None
            
        except Exception as e:
            logger.error(f"Failed to load migration module {module_name}: {e}")
            return None
    
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
        Get the latest available version from static configuration.
        
        Returns:
            str: Latest version string
        """
        return get_latest_version()
    
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
            
            # Check if db_version table exists before querying
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            table_names = inspector.get_table_names()
            
            if 'db_version' not in table_names:
                # Fresh database - no tables exist yet
                logger.debug("Fresh database detected (db_version table not found). This is normal for new installations.")
                raise Exception("Fresh database detected - needs initialization")
            
            # Try to get the version record (table exists, so this should work)
            try:
                version = DBVersion.get_current_version(session)
                if version:
                    return version.version
            except OperationalError as e:
                # Table exists but query failed - log and re-raise
                error_str = str(e)
                if 'no such table' in error_str.lower():
                    logger.debug("db_version table check passed but query failed - treating as fresh database")
                    raise Exception("Fresh database detected - needs initialization")
                raise
            
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
            # For fresh databases, this is expected - check if it's a missing table error
            error_str = str(e)
            if 'fresh database' in error_str.lower() or 'needs initialization' in error_str.lower():
                # This is a fresh database - already logged above, just re-raise
                pass
            elif 'no such table' in error_str.lower() or 'db_version' in error_str.lower():
                # This is a fresh database - log as debug
                logger.debug(f"Fresh database detected (db_version table not found). This is normal for new installations.")
            else:
                # Unexpected error - log with more detail
                logger.debug(f"Could not get current database version: {e}")
            # Re-raise the exception so migrate_to_latest can handle it properly
            raise
        finally:
            if session:
                session.close()
    
    def get_available_migrations(self) -> List[Dict[str, Any]]:
        """
        Get information about all available migrations from static configuration.
        
        Returns:
            List[Dict]: List of migration information
        """
        from .migration_config import VERSION_HISTORY, VERSION_DEPENDENCIES
        
        migrations_info = []
        for version in VERSION_HISTORY:
            if version == "1.0.0":  # Skip initial version
                continue
                
            migrations_info.append({
                'version': version,
                'previous_version': VERSION_DEPENDENCIES.get(version, '1.0.0'),
                'description': f'Migration to version {version}',
                'available': True
            })
        return migrations_info
    
    def get_migration_path(self, from_version: str, to_version: str) -> List[str]:
        """
        Get the migration path from one version to another using static configuration.
        
        Args:
            from_version: Starting version
            to_version: Target version
            
        Returns:
            List[str]: List of versions in the migration path
        """
        return get_version_path(from_version, to_version)
    
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
            
            # First, check if this is a completely fresh database (no tables at all)
            from sqlalchemy import inspect
            inspector = inspect(self.engine)
            existing_tables = inspector.get_table_names()
            
            if not existing_tables:
                # Completely fresh database: create all tables with latest schema and set version
                logger.info("Detected completely fresh database with no tables")
                from ..core import create_all_tables
                create_all_tables(self.engine)
                DBVersion.upgrade_version(session, target_version, description or 'Fresh database initialization')
                session.commit()
                logger.info(f"Initialized fresh database to version {target_version}")
                return True
            
            # Database has tables, check current version
            version_record = DBVersion.get_current_version(session)
            
            if not version_record:
                # Existing database without version record: assume it's at 1.0.0
                logger.info("Existing database without version record, assuming version 1.0.0")
                current_version = '1.0.0'
                DBVersion.upgrade_version(session, current_version, description='Initial version for existing database')
                session.commit()
            else:
                current_version = version_record.version
            
            if current_version == target_version:
                logger.info(f"Database is already at version {target_version}")
                # Still ensure all tables exist (for any missing tables)
                from ..core import create_all_tables
                create_all_tables(self.engine)
                return True

            # Use path calculation from config, avoiding loading all migration scripts
            migration_path = get_version_path(current_version, target_version)
            
            if not migration_path:
                logger.info(f"No migrations needed from {current_version} to {target_version}")
                # Still ensure all tables exist
                from ..core import create_all_tables
                create_all_tables(self.engine)
                return True
            
            logger.info(f"Migration path: {current_version} -> {' -> '.join(migration_path)}")
            
            # Execute migrations in order using the same session
            for version in migration_path:
                if not self._execute_migration(session, version):
                    session.rollback()
                    return False
            
            # After all migrations, ensure any missing tables are created
            try:
                from ..core import create_all_tables
                create_all_tables(self.engine)
            except Exception as e:
                logger.warning(f"Failed to create additional tables after migration: {e}")
                # Don't fail the migration for this
            
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
        # Use static config to get latest version, no need to load all migration scripts
        latest_version = self._get_latest_version()
        
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
                    logger.info("Detected fresh database with no tables. Creating latest schema directly (this is normal for new installations).")
                    
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
                        # Add detailed traceback for debugging
                        import traceback
                        logger.error(f"Full traceback:\n{traceback.format_exc()}")
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
                # Add detailed traceback for debugging
                import traceback
                logger.error(f"Full traceback:\n{traceback.format_exc()}")
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
        # Load migration script on demand
        migration_class = self._load_migration(version)
        if not migration_class:
            logger.error(f"Migration not found for version {version}")
            return False
        migration = migration_class(self.engine)
        
        logger.info(f"Executing migration to {version}: {migration.description}")
        
        # Create migration log entry
        migration_log = None
        try:
            from ..models import MigrationLog
            import time
            
            migration_log = MigrationLog(
                migration_name=f"migration_to_{version}",
                from_version=migration.previous_version,
                to_version=version,
                started_at=int(time.time() * 1000),
                status='running'
            )
            session.add(migration_log)
            session.flush()  # Get the ID but don't commit yet
            
        except Exception as e:
            logger.warning(f"Failed to create migration log: {e}")
        
        try:
            # Validate preconditions
            if not migration.validate_preconditions(session):
                logger.error(f"Preconditions failed for migration {version}")
                if migration_log:
                    migration_log.fail_migration("Preconditions validation failed")
                return False
            
            # Execute the migration
            if not migration.upgrade(session):
                logger.error(f"Migration upgrade failed for version {version}")
                if migration_log:
                    migration_log.fail_migration("Migration upgrade failed")
                return False
            
            # Validate postconditions
            if not migration.validate_postconditions(session):
                logger.error(f"Postconditions failed for migration {version}")
                if migration_log:
                    migration_log.fail_migration("Postconditions validation failed")
                return False
            
            # Mark migration as completed
            if migration_log:
                migration_log.complete_migration()
            
            logger.info(f"Successfully executed migration to {version}")
            return True
            
        except Exception as e:
            logger.error(f"Exception during migration {version}: {e}")
            if migration_log:
                migration_log.fail_migration(str(e))
            return False
    
    def _version_to_tuple(self, version: str) -> tuple:
        """
        Convert version string to tuple for comparison.
        
        Args:
            version: Version string like "1.0.0"
            
        Returns:
            tuple: Version as tuple like (1, 0, 0)
        """
        return version_to_tuple(version)
    
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

        # Use static config to get latest version
        latest_version = self._get_latest_version()
        
        return {
            'current_version': current_version,
            'latest_version': latest_version,
            'available_migrations': available_migrations,
            'needs_migration': current_version != latest_version,
            'migration_path': self.get_migration_path(current_version, latest_version) if current_version != latest_version else []
        }
