"""
Version and migration related database models.

This module contains database models for version control and migration tracking.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from datetime import datetime
from .base_model import BaseModel


class DBVersion(BaseModel):
    """
    Database version model for tracking schema versions.
    
    Used by the migration system to track the current database schema version.
    """
    __tablename__ = 'db_version'
    
    # Version information (compatible with old schema)
    version = Column(String(32), nullable=False, comment="Version string")
    description = Column(String(255), nullable=True, comment="Version description")
    
    # Migration metadata (compatible with old schema)
    upgraded_at = Column(DateTime, nullable=True, comment="Upgrade timestamp")
    
    def __repr__(self):
        return f"<DBVersion(id='{self.id}', version='{self.version}')>"
    
    def to_dict(self) -> dict:
        """Convert version to dictionary."""
        return super().to_dict()
    
    @classmethod
    def get_current_version(cls, session):
        """
        Get the current database version.
        
        Args:
            session: SQLAlchemy session
            
        Returns:
            DBVersion: Current version record or None
        """
        return session.query(cls).order_by(cls.created_at.desc()).first()
    
    @classmethod
    def set_current_version(cls, session, version: str, description: str = None):
        """
        Set a version as the current version.
        
        Args:
            session: SQLAlchemy session
            version (str): Version string
            description (str, optional): Version description
            
        Returns:
            DBVersion: The new current version record
        """
        # Check if version already exists
        existing = session.query(cls).filter_by(version=version).first()
        if existing:
            existing.upgraded_at = datetime.utcnow()
            if description:
                existing.description = description
            return existing
        
        # Create new version record
        new_version = cls(
            version=version,
            description=description,
            upgraded_at=datetime.utcnow()
        )
        session.add(new_version)
        return new_version
    
    @classmethod
    def upgrade_version(cls, session, version: str, description: str = None):
        """
        Upgrade to a new version (alias for set_current_version).
        
        Args:
            session: SQLAlchemy session
            version (str): Version string
            description (str, optional): Version description
            
        Returns:
            DBVersion: The new current version record
        """
        return cls.set_current_version(session, version, description)


class MigrationLog(BaseModel):
    """
    Migration log model for tracking migration execution history.
    
    Records detailed information about each migration execution.
    """
    __tablename__ = 'migration_logs'
    
    # Migration information
    migration_name = Column(String(255), nullable=False, comment="Migration name/identifier")
    from_version = Column(String(50), nullable=True, comment="Source version")
    to_version = Column(String(50), nullable=False, comment="Target version")
    
    # Execution details
    started_at = Column(Integer, nullable=False, comment="Migration start timestamp (milliseconds)")
    completed_at = Column(Integer, nullable=True, comment="Migration completion timestamp (milliseconds)")
    duration_ms = Column(Integer, nullable=True, comment="Migration duration in milliseconds")
    
    # Migration status
    status = Column(String(20), nullable=False, default='pending', comment="Migration status: pending, running, completed, failed")
    error_message = Column(Text, nullable=True, comment="Error message if migration failed")
    
    # Migration metadata
    sql_statements = Column(Text, nullable=True, comment="SQL statements executed")
    affected_tables = Column(String(1000), nullable=True, comment="Comma-separated list of affected tables")
    
    def __repr__(self):
        return f"<MigrationLog(id='{self.id}', migration_name='{self.migration_name}', status='{self.status}')>"
    
    def to_dict(self) -> dict:
        """Convert migration log to dictionary."""
        return super().to_dict()
    
    def start_migration(self):
        """Mark migration as started."""
        self.status = 'running'
        self.started_at = int(datetime.utcnow().timestamp() * 1000)
        self.updated_at = datetime.utcnow()
    
    def complete_migration(self):
        """Mark migration as completed."""
        current_time = int(datetime.utcnow().timestamp() * 1000)
        self.status = 'completed'
        self.completed_at = current_time
        if self.started_at:
            self.duration_ms = current_time - self.started_at
        self.updated_at = datetime.utcnow()
    
    def fail_migration(self, error_message: str):
        """Mark migration as failed."""
        current_time = int(datetime.utcnow().timestamp() * 1000)
        self.status = 'failed'
        self.completed_at = current_time
        self.error_message = error_message
        if self.started_at:
            self.duration_ms = current_time - self.started_at
        self.updated_at = datetime.utcnow()
    
    def get_duration_formatted(self) -> str:
        """Get formatted duration string."""
        if not self.duration_ms:
            return "Unknown"
        
        if self.duration_ms < 1000:
            return f"{self.duration_ms}ms"
        elif self.duration_ms < 60000:
            return f"{self.duration_ms / 1000:.1f}s"
        else:
            minutes = self.duration_ms // 60000
            seconds = (self.duration_ms % 60000) / 1000
            return f"{minutes}m {seconds:.1f}s"
