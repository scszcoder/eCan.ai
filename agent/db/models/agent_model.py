"""
Agent database models.

This module contains database models for agent management:
- DBAgent: Main agent model
- DBAgentTask: Agent task model
- DBAgentTool: Agent tool model
- DBAgentKnowledge: Agent knowledge model
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, BigInteger, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin
from datetime import datetime


class DBAgent(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agents"""
    __tablename__ = 'agents'

    # 重写 id 字段以保持与老表的兼容性
    id = Column(String(64), primary_key=True)

    # 老表的核心字段 - 保持兼容性
    agid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    gender = Column(String(2), nullable=False)
    title = Column(String(64), nullable=False)
    rank = Column(String(64), nullable=False)

    # 改为 JSON 类型以支持 List[str]，与 EC_Agent 保持一致
    organizations = Column(JSON, nullable=False)  # List[str]
    supervisors = Column(JSON, nullable=False)    # List[str]
    subordinates = Column(JSON, nullable=False)   # List[str]
    personalities = Column(JSON, nullable=False)  # List[str]

    vehicle = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False)
    agent_metadata = Column(JSON)
    birthday = Column(String(64), nullable=False)
    skills = Column(JSON)  # List[str] - skill IDs
    tasks = Column(JSON)   # List[str] - task IDs
    knowledges = Column(Text)

    # 添加 EC_Agent 中的其他字段
    peers = Column(JSON)   # List[str]
    description = Column(Text)  # Agent description
    url = Column(String(512))   # Agent URL
    version = Column(String(64))  # Agent version
    capabilities = Column(JSON)   # Agent capabilities

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        # 使用父类的 to_dict 方法，但保持兼容性
        d = super().to_dict()
        # 确保老字段的兼容性
        if deep:
            # 可以在这里添加深度转换逻辑
            pass
        return d


class DBAgentTask(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent tasks"""
    __tablename__ = 'agent_tasks'

    # 重写 id 字段以保持与老表的兼容性
    id = Column(String(64), primary_key=True)

    # 老表的核心字段 - 保持兼容性
    ataskid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    priority = Column(String(64), nullable=False)
    description = Column(Text)
    objectives = Column(JSON)
    schedule = Column(JSON)
    task_metadata = Column(JSON)
    trigger = Column(String(64), nullable=False)

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # 可以在这里添加深度转换逻辑
            pass
        return d


class DBAgentTool(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent tools"""
    __tablename__ = 'agent_tools'

    # 重写 id 字段以保持与老表的兼容性
    id = Column(String(64), primary_key=True)

    # 老表的核心字段 - 保持兼容性
    atoolid = Column(BigInteger, default=0)
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
    tool_metadata = Column(JSON)

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # 可以在这里添加深度转换逻辑
            pass
        return d


class DBAgentKnowledge(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent knowledge"""
    __tablename__ = 'agent_knowledges'

    # 重写 id 字段以保持与老表的兼容性
    id = Column(String(64), primary_key=True)

    # 老表的核心字段 - 保持兼容性
    aknowledgeid = Column(BigInteger, default=0)
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
    knowledge_metadata = Column(JSON)

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # 可以在这里添加深度转换逻辑
            pass
        return d
