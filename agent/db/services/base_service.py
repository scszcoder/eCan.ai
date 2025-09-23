"""
Base service class for database operations.

This module provides the base service class with common database
operations and session management functionality.
"""

from contextlib import contextmanager
from sqlalchemy.orm import sessionmaker
from typing import Optional, Any
from ..core import get_engine, get_session_factory, Base
from .singleton import SingletonMeta


class BaseService(metaclass=SingletonMeta):
    """
    Base service class for database operations.
    
    Provides common functionality for database services including
    session management and basic CRUD operations.
    """
    
    def __init__(self, db_path: str = None, engine=None, session=None):
        """
        Initialize base service.
        
        Args:
            db_path (str, optional): Database file path
            engine: SQLAlchemy engine instance
            session: SQLAlchemy session instance
        """
        if session is not None:
            self.SessionFactory = lambda: session
        elif engine is not None:
            self.engine = engine
            self.SessionFactory = sessionmaker(bind=engine)
            Base.metadata.create_all(engine)
        elif db_path is not None:
            self.engine = get_engine(db_path)
            self.SessionFactory = get_session_factory(db_path)
            Base.metadata.create_all(self.engine)
        else:
            raise ValueError("Must provide db_path, engine or session")

    @contextmanager
    def session_scope(self):
        """
        Provide a transactional scope around a series of operations.
        
        Yields:
            Session: SQLAlchemy session instance
        """
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            
    def create_entity(self, model_class, **kwargs) -> dict:
        """
        Create a new entity.
        
        Args:
            model_class: SQLAlchemy model class
            **kwargs: Entity attributes
            
        Returns:
            dict: Standard response with success status and data
        """
        with self.session_scope() as session:
            try:
                entity = model_class(**kwargs)
                session.add(entity)
                session.flush()
                return {
                    "success": True,
                    "id": getattr(entity, 'id', None),
                    "data": entity.to_dict() if hasattr(entity, 'to_dict') else None,
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": str(e)
                }
                
    def get_entity_by_id(self, model_class, entity_id: Any) -> dict:
        """
        Get entity by ID.
        
        Args:
            model_class: SQLAlchemy model class
            entity_id: Entity ID
            
        Returns:
            dict: Standard response with success status and data
        """
        with self.session_scope() as session:
            try:
                entity = session.get(model_class, entity_id)
                if not entity:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Entity with id {entity_id} not found"
                    }
                return {
                    "success": True,
                    "data": entity.to_dict() if hasattr(entity, 'to_dict') else None,
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "data": None,
                    "error": str(e)
                }
                
    def update_entity(self, model_class, entity_id: Any, **kwargs) -> dict:
        """
        Update entity by ID.
        
        Args:
            model_class: SQLAlchemy model class
            entity_id: Entity ID
            **kwargs: Updated attributes
            
        Returns:
            dict: Standard response with success status and data
        """
        with self.session_scope() as session:
            try:
                entity = session.get(model_class, entity_id)
                if not entity:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Entity with id {entity_id} not found"
                    }
                    
                for key, value in kwargs.items():
                    if hasattr(entity, key):
                        setattr(entity, key, value)
                        
                session.flush()
                return {
                    "success": True,
                    "data": entity.to_dict() if hasattr(entity, 'to_dict') else None,
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "data": None,
                    "error": str(e)
                }
                
    def delete_entity(self, model_class, entity_id: Any) -> dict:
        """
        Delete entity by ID.
        
        Args:
            model_class: SQLAlchemy model class
            entity_id: Entity ID
            
        Returns:
            dict: Standard response with success status
        """
        with self.session_scope() as session:
            try:
                entity = session.get(model_class, entity_id)
                if not entity:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Entity with id {entity_id} not found"
                    }
                    
                session.delete(entity)
                session.flush()
                return {
                    "success": True,
                    "data": None,
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "data": None,
                    "error": str(e)
                }
