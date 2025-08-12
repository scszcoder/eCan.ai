from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, BigInteger
from agent.chats.chats_db import Base, ECBOT_CHAT_DB, Member, get_engine, get_session_factory
from datetime import datetime

# 统一 Base，所有表都继承这个 Base

class DBAgentSkill(Base):
    __tablename__ = 'agent_skills'
    id = Column(String(64), primary_key=True)
    askid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    description = Column(Text)
    latest_version = Column(String(128), nullable=False)
    path = Column(Text)
    level = Column(Integer)
    config = Column(JSON)
    apps = Column(JSON)
    limitations = Column(JSON)
    price = Column(Integer, default=0)
    price_model = Column(Text)
    public = Column(Boolean, default=False)
    rentable = Column(Boolean, default=False)
    members = relationship('Member', back_populates='agent_skills', cascade='all, delete-orphan')

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if deep:
            d['members'] = [m.to_dict() for m in self.members]
        return d

