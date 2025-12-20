"""
Base model class for all database models.

This module provides the base model class with common functionality
for all database models in the eCan.ai system.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text, JSON
from datetime import datetime
import uuid

# Import the unified Base from core
from ..core.base import Base


class BaseModel(Base):
    """
    Abstract base model class for all database models.
    
    Provides common fields and functionality that all models should have:
    - Primary key (id)
    - Creation timestamp (created_at)
    - Update timestamp (updated_at)
    - Common utility methods
    """
    __abstract__ = True
    
    # Common fields for all models
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def to_dict(self) -> dict:
        """
        Convert model instance to dictionary.
        
        Returns:
            dict: Dictionary representation of the model
        """
        result = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = int(value.timestamp() * 1000)  # Convert to milliseconds
            result[column.name] = value
        return result
    
    def update_from_dict(self, data: dict):
        """
        Update model instance from dictionary.
        
        Args:
            data (dict): Dictionary with field values to update
        """
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        """String representation of the model."""
        return f"<{self.__class__.__name__}(id='{self.id}')>"


class TimestampMixin:
    """
    Mixin class for models that need timestamp fields.
    
    Provides created_at and updated_at fields with automatic management.
    """
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class SoftDeleteMixin:
    """
    Mixin class for models that support soft deletion.
    
    Provides deleted_at field and is_deleted property.
    """
    deleted_at = Column(DateTime, nullable=True)
    
    @property
    def is_deleted(self) -> bool:
        """Check if the record is soft deleted."""
        return self.deleted_at is not None
    
    def soft_delete(self):
        """Mark the record as deleted."""
        self.deleted_at = datetime.utcnow()
    
    def restore(self):
        """Restore a soft deleted record."""
        self.deleted_at = None


class ExtensibleMixin:
    """
    Mixin class for models that need extensible JSON fields.
    
    Provides ext field for storing additional data as JSON.
    """
    ext = Column(JSON, nullable=True, comment="Extension field for additional data")
    
    def set_ext_field(self, key: str, value):
        """Set a value in the extension field."""
        if self.ext is None:
            self.ext = {}
        self.ext[key] = value
    
    def get_ext_field(self, key: str, default=None):
        """Get a value from the extension field."""
        if self.ext is None:
            return default
        return self.ext.get(key, default)
    
    def remove_ext_field(self, key: str):
        """Remove a field from the extension field."""
        if self.ext and key in self.ext:
            del self.ext[key]
