from sqlalchemy import Column, Integer, DateTime, func
from sqlalchemy.orm import declarative_base, Session
from datetime import datetime
from typing import Dict, Any, Optional, List
from contextlib import contextmanager
from sqlalchemy import select
from .models import Base

class Entity(Base):
    """Base entity class for all database models"""
    __abstract__ = True

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_by_id(cls, session: Session, entity_id: int) -> Optional['Entity']:
        """Get entity by ID"""
        if not session:
            raise ValueError("Database session is required")
        stmt = select(cls).where(cls.id == entity_id)
        return session.execute(stmt).scalar_one_or_none()

    @classmethod
    def get_all(cls, session: Session) -> List['Entity']:
        """Get all entities"""
        if not session:
            raise ValueError("Database session is required")
        stmt = select(cls)
        return session.execute(stmt).scalars().all()

    @classmethod
    def create(cls, session: Session, **kwargs) -> 'Entity':
        """Create new entity"""
        if not session:
            raise ValueError("Database session is required")
        entity = cls(**kwargs)
        session.add(entity)
        session.commit()
        session.refresh(entity)
        return entity

    def update(self, session: Session, **kwargs) -> 'Entity':
        """Update entity attributes"""
        if not session:
            raise ValueError("Database session is required")
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        session.commit()
        session.refresh(self)
        return self

    def delete(self, session: Session) -> bool:
        """Delete entity"""
        if not session:
            raise ValueError("Database session is required")
        session.delete(self)
        session.commit()
        return True

    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary"""
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }

    @classmethod
    @contextmanager
    def session_scope(cls, session: Session):
        """Provide a transactional scope around a series of operations"""
        if not session:
            raise ValueError("Database session is required")
        try:
            yield session
            session.commit()
        except:
            session.rollback()
            raise 