"""
Database core module.

This module contains the fundamental database components including
base configuration, models, and migration utilities.
"""

from .base import (
    Base,
    ECAN_BASE_DB,
    get_engine,
    get_session_factory,
    create_all_tables,
    drop_all_tables
)

from ..models import (
    DBVersion,
    Chat,
    Member,
    Message,
    Attachment,
    ChatNotification
)

from .migration import DBMigration

__all__ = [
    # Base configuration
    'Base',
    'ECAN_BASE_DB',
    'get_engine',
    'get_session_factory',
    'create_all_tables',
    'drop_all_tables',
    
    # Models
    'DBVersion',
    'Chat',
    'Member',
    'Message',
    'Attachment',
    'ChatNotification',
    
    # Migration
    'DBMigration'
]
