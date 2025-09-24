"""
Skill database models.

This module contains database models for skill management:
- DBAgentSkill: Agent skill model
"""

from sqlalchemy import Column, String, Integer, Boolean, Text, JSON, BigInteger
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentSkill(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent skills"""
    __tablename__ = 'agent_skills'

    # 重写 id 字段以保持与老表的兼容性
    id = Column(String(64), primary_key=True)
    askid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    description = Column(Text)
    version = Column(String(128), nullable=False)  # 改为 version，与 EC_Skill 一致
    path = Column(Text)
    level = Column(String(64))  # 改为 String，与 EC_Skill 一致 (entry/intermediate/advanced)
    config = Column(JSON)
    # 添加 EC_Skill 中的字段
    tags = Column(JSON)  # List[str] | None
    examples = Column(JSON)  # List[str] | None
    inputModes = Column(JSON)  # List[str] | None
    outputModes = Column(JSON)  # List[str] | None
    # 保留原有的扩展字段
    apps = Column(JSON)
    limitations = Column(JSON)
    price = Column(Integer, default=0)
    price_model = Column(Text)
    public = Column(Boolean, default=False)
    rentable = Column(Boolean, default=False)
    # Note: members relationship commented out due to missing foreign key
    # members = relationship('Member', back_populates='agent_skills', cascade='all, delete-orphan')

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # 可以在这里添加深度转换逻辑
            # d['members'] = [m.to_dict() for m in self.members]
            pass
        return d
