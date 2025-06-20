from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

Base = declarative_base()

class DBVersion(Base):
    __tablename__ = 'db_version'
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(32), nullable=False, unique=True, index=True)
    description = Column(String(255))
    upgraded_at = Column(DateTime, default=datetime.utcnow)

    @classmethod
    def get_current_version(cls, session):
        return session.query(cls).order_by(cls.upgraded_at.desc()).first()

    @classmethod
    def upgrade_version(cls, session, version: str, description: str = None):
        new_version = cls(version=version, description=description)
        session.add(new_version)
        session.commit()
        return new_version 