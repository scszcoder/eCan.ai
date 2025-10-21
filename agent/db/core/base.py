"""
Database base configuration and connection management.

This module provides the fundamental database configuration,
connection management, and base classes for the eCan.ai database system.
"""

import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Optional

# Unified Base, all tables inherit from this Base
Base = declarative_base()

# Default database filename
ECAN_BASE_DB = "ecan_base.db"


def get_engine(db_path: str = ECAN_BASE_DB):
    """
    Create and return a SQLAlchemy engine.
    
    Args:
        db_path (str): Database file path, defaults to ECAN_BASE_DB
        
    Returns:
        Engine: SQLAlchemy engine instance
    """
    # Ensure parent directory exists to avoid 'unable to open database file'
    try:
        abs_path = os.path.abspath(db_path)
        parent_dir = os.path.dirname(abs_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
    except Exception:
        # Don't block engine creation on directory check; SQLite will still error if invalid
        pass

    engine = create_engine(
        f'sqlite:///{db_path}',
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections every hour
        pool_size=5,        # Allow more connections for migration operations
        max_overflow=10,    # Allow overflow connections for concurrent operations
        pool_timeout=60,    # Wait up to 60 seconds for a connection
        connect_args={
            'check_same_thread': False,
            'timeout': 120,  # Increase timeout to 120 seconds for long-running operations
            'isolation_level': None,  # Use autocommit mode to reduce lock contention
        }
    )
    # Set SQLite pragmas for better concurrency using event listeners
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Set SQLite pragmas for better performance and concurrency."""
        try:
            cursor = dbapi_connection.cursor()
            # Set busy timeout to handle concurrent access
            cursor.execute("PRAGMA busy_timeout=60000")  # 60 seconds for migration operations
            # Enable WAL mode for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL")
            # Optimize for better performance
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA cache_size=10000")
            cursor.execute("PRAGMA temp_store=MEMORY")
            cursor.close()
        except Exception as e:
            # Don't let pragma setting failures block the connection
            pass
    
    return engine


def get_session_factory(db_path: str = ECAN_BASE_DB):
    """
    Create and return a SQLAlchemy session factory.
    
    Args:
        db_path (str): Database file path, defaults to ECAN_BASE_DB
    Returns:
        sessionmaker: SQLAlchemy session factory
    """
    engine = get_engine(db_path)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def create_all_tables(db_path_or_engine = ECAN_BASE_DB):
    """
    Create all database tables.
    
    Args:
        db_path_or_engine: Database file path (str) or SQLAlchemy engine instance
    """
    # Import the Base with all registered models
    from ..models import Base as ModelsBase
    
    # Support both engine instance and db_path string
    if hasattr(db_path_or_engine, 'execute'):
        # It's an engine instance
        engine = db_path_or_engine
    else:
        # It's a db_path string
        engine = get_engine(db_path_or_engine)
    
    ModelsBase.metadata.create_all(engine)


def drop_all_tables(db_path: str = ECAN_BASE_DB):
    """
    Drop all database tables.
    
    Args:
        db_path (str): Database file path, defaults to ECAN_BASE_DB
    """
    # Import the Base with all registered models
    from ..models import Base as ModelsBase
    engine = get_engine(db_path)
    ModelsBase.metadata.drop_all(engine)
