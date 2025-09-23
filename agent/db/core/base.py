"""
Database base configuration and connection management.

This module provides the fundamental database configuration,
connection management, and base classes for the eCan.ai database system.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from typing import Optional

# 统一 Base，所有表都继承这个 Base
Base = declarative_base()

# 默认数据库文件名
ECAN_BASE_DB = "ecan_base.db"


def get_engine(db_path: str = ECAN_BASE_DB):
    """
    Create and return a SQLAlchemy engine.
    
    Args:
        db_path (str): Database file path, defaults to ECAN_BASE_DB
        
    Returns:
        Engine: SQLAlchemy engine instance
    """
    return create_engine(
        f'sqlite:///{db_path}', 
        pool_pre_ping=True, 
        connect_args={'check_same_thread': False}
    )


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


def create_all_tables(db_path: str = ECAN_BASE_DB):
    """
    Create all database tables.
    
    Args:
        db_path (str): Database file path, defaults to ECAN_BASE_DB
    """
    # Import the Base with all registered models
    from ..models import Base as ModelsBase
    engine = get_engine(db_path)
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
