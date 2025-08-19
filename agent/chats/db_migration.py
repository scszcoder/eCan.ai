from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, MetaData, Table, Column, String, Integer, DateTime, JSON, Boolean
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from datetime import datetime
from agent.chats.chats_db import Base, DBVersion

from utils.logger_helper import logger_helper as logger

class DBMigration:
    """Database Migration Manager"""
    
    def __init__(self, db_path: str = None):
        """
        Initialize database migration manager
        
        Args:
            db_path (str, optional): Database file path
        """
        # Lazy import to avoid circular dependency
        from .chats_db import get_engine
        self.db_path = db_path
        self.engine = get_engine(db_path)
        self.Session = sessionmaker(bind=self.engine)
        
    def get_current_version(self) -> Optional[str]:
        """Get current database version, auto-insert 1.0.0 if none exists"""
        session = self.Session()
        try:
            version = DBVersion.get_current_version(session)
            if not version:
                # Auto-insert initial version
                DBVersion.upgrade_version(session, '1.0.0', description='Initial version')
                version = DBVersion.get_current_version(session)
            return version.version if version else '1.0.0'
        finally:
            session.close()
            
    def upgrade_to_version(self, target_version: str, description: str = None) -> bool:
        """
        Upgrade database to specified version
        
        Args:
            target_version (str): Target version number
            description (str, optional): Upgrade description
            
        Returns:
            bool: Whether upgrade was successful
        """
        current_version = self.get_current_version()
        if not current_version:
            logger.error("Unable to get current database version")
            return False
        
        # Version comparison, prohibit downgrade
        current_parts = [int(x) for x in current_version.split('.')]
        target_parts = [int(x) for x in target_version.split('.')]
        if current_parts > target_parts:
            logger.error(f"Downgrade not allowed: {current_version} -> {target_version}")
            return False
        
        # Get all available upgrade scripts
        upgrade_scripts = self._get_upgrade_scripts(current_version, target_version)
        if not upgrade_scripts:
            logger.info(f"Database is already at latest version {current_version}")
            return True
        
        session = self.Session()
        try:
            # Execute each upgrade script
            for script in upgrade_scripts:
                logger.info(f"Executing upgrade script: {script['version']} - {script['description']}")
                if not self._execute_upgrade_script(session, script):
                    session.rollback()
                    return False
            # Update version record
            DBVersion.upgrade_version(session, target_version, description)
            session.commit()
            logger.info(f"Database upgrade successful: {current_version} -> {target_version}")
            return True
        except Exception as e:
            session.rollback()
            logger.error(f"Database upgrade failed: {str(e)}")
            return False
        finally:
            session.close()
            
    def _get_upgrade_scripts(self, current_version: str, target_version: str) -> List[Dict[str, Any]]:
        """
        Get all upgrade scripts from current version to target version
        
        Args:
            current_version (str): Current version
            target_version (str): Target version
            
        Returns:
            List[Dict[str, Any]]: List of upgrade scripts
        """
        # Define all known upgrade paths
        upgrade_path = [
            ("1.0.0", "1.0.1"),
            ("1.0.1", "2.0.0"),
        ]
        # Generate all upgrade steps that need to be executed
        scripts = []
        version = current_version
        while version != target_version:
            for from_v, to_v in upgrade_path:
                if from_v == version:
                    scripts.append({
                        'version': to_v,
                        'description': f'Upgrade from {from_v} to {to_v}',
                        'upgrade_func': self._create_upgrade_function(from_v, to_v)
                    })
                    version = to_v
                    break
            else:
                # No next upgrade path found, target version is unreachable
                break
        return scripts
        
    def _execute_upgrade_script(self, session, script: Dict[str, Any]) -> bool:
        """
        Execute upgrade script
        
        Args:
            session: Database session
            script (Dict[str, Any]): Upgrade script information
            
        Returns:
            bool: Whether execution was successful
        """
        try:
            # Execute upgrade function
            script['upgrade_func'](session)
            return True
        except Exception as e:
            logger.error(f"Failed to execute upgrade script: {str(e)}")
            return False
            
    def _create_upgrade_function(self, from_version: str, to_version: str):
        """
        Create upgrade function
        """
        def upgrade_func(session):
            # Here implement specific database structure upgrade logic
            # For example: add new tables, modify table structure, etc.
            if from_version == "1.0.0" and to_version == "1.0.1":
                # Add upgraded_at field to db_version table (if it doesn't exist)
                with self.engine.connect() as conn:
                    result = conn.execute(text("PRAGMA table_info(db_version);"))
                    columns = [row[1] for row in result]
                    if "upgraded_at" not in columns:
                        conn.execute(text("ALTER TABLE db_version ADD COLUMN upgraded_at DATETIME;"))
            if from_version == "1.0.1" and to_version == "2.0.0":
                # Create chat_notification table
                metadata = MetaData()
                chat_notification = Table(
                    'chat_notification',
                    metadata,
                    Column('uid', String(64), primary_key=True),
                    Column('chatId', String(64), nullable=False),
                    Column('content', JSON, nullable=False),
                    Column('timestamp', Integer, nullable=False),
                    Column('isRead', Boolean, default=False)
                )
                metadata.create_all(self.engine, tables=[chat_notification])
            # Can continue to add more upgrade branches
        return upgrade_func
        
    def create_migration_script(self, version: str, description: str) -> str:
        """
        Create migration script template
        
        Args:
            version (str): Version number
            description (str): Description
            
        Returns:
            str: Migration script template
        """
        template = f"""from datetime import datetime
from sqlalchemy import Table, Column, String, Integer, DateTime, MetaData, JSON, Boolean

def upgrade(session, engine):
    \"\"\"
    Database upgrade script: {version}
    Description: {description}
    \"\"\"
    metadata = MetaData()
    
    # Add upgrade logic here
    # For example:
    # new_table = Table(
    #     'new_table',
    #     metadata,
    #     Column('id', Integer, primary_key=True),
    #     Column('name', String(50)),
    #     Column('created_at', DateTime, default=datetime.utcnow)
    # )
    # new_table.create(engine)
    
    return True
"""
        return template 