from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, BigInteger, Float
from agent.chats.chats_db import Base, ECBOT_CHAT_DB, Member, get_engine, get_session_factory
from datetime import datetime
from  agent.ec_skills.agent_skills_db import AgentSkill
# 统一 Base，所有表都继承这个 Base

# "agid": agent.card.id,
#                 "owner": mainwin.user,
#                 "gender": agent.gender,
#                 "organizations": agent.organizations,
#                 "rank": agent.rank,
#                 "supervisors": agent.supervisors,
#                 "subordinates": agent.subordinates,
#                 "title": agent.title,
#                 "personalities": agent.personalities,
#                 "birthday": agent.birthday,
#                 "name": agent.card.name,
#                 "status": agent.status,
#                 "metadata": json.dumps({"description": agent.card.description}),
#                 "vehicle": agent.vehicle,
#                 "skills": json.dumps([sk.id for sk in agent.skill_set]),
#                 "tasks": json.dumps([task.id for task in agent.tasks]),
#                 "knowledges": ""

class DBAgent(Base):
    __tablename__ = 'agents'
    id = Column(String(64), primary_key=True)
    agid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    gender = Column(String(2), nullable=False)
    title = Column(String(64), nullable=False)
    rank = Column(String(64), nullable=False)
    organizations = Column(String(1024), nullable=False)
    supervisors = Column(String(256), nullable=False)
    subordinates = Column(String(4096), nullable=False)
    personalities = Column(String(256), nullable=False)
    vehicle = Column(String(32), primary_key=True)
    status = Column(String(32), nullable=False)
    metadata = Column(JSON)
    birthday = Column(String(64), primary_key=True)
    skills = Column(JSON)
    tasks = Column(JSON)
    knowledges = Column(Text)

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return d


class DBAgentTask(Base):
    __tablename__ = 'agent_tasks'
    id = Column(String(64), primary_key=True)
    ataskid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    priority = Column(String(64), nullable=False)
    description = Column(String(32), primary_key=True)
    objectives = Column(JSON)
    schedule = Column(JSON)
    metadata = Column(JSON)
    trigger = Column(String(64), nullable=False)

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return d


class DBAgentTool(Base):
    __tablename__ = 'agent_tools'
    id = Column(String(64), primary_key=True)
    toolid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    priority = Column(String(64), nullable=False)
    description = Column(String(32), primary_key=True)
    protocol = Column(String(32), nullable=False)
    metadata = Column(JSON)
    link = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    price = Column(Float, nullable=False)

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return d


class DBAgentKnowledge(Base):
    __tablename__ = 'agent_knowledges'
    id = Column(String(64), primary_key=True)
    knid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    description = Column(String(32), primary_key=True)
    metadata = Column(JSON)
    rag = Column(String(128), nullable=False)
    status = Column(String(32), nullable=False)
    price = Column(Float, nullable=False)

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        return d


