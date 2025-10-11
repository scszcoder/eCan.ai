"""
Skill database models.

This module contains database models for skill management:
- DBAgentSkill: Agent skill model
"""

import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, JSON, BigInteger
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentSkill(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent skills"""
    __tablename__ = 'agent_skills'

    # ID field with auto-generation
    id = Column(String(64), primary_key=True, default=lambda: f"skill_{uuid.uuid4().hex[:16]}")
    askid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    description = Column(Text)
    version = Column(String(128), nullable=False)  # 改为 version，与 EC_Skill 一致
    path = Column(Text)
    level = Column(String(64))  # 改为 String，与 EC_Skill 一致 (entry/intermediate/advanced)
    config = Column(JSON)
    diagram = Column(JSON)  # Flowgram diagram data (nodes, edges, etc.)
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
            # Include association details through backref relationships
            if hasattr(self, 'agent_skills_rel') and self.agent_skills_rel:
                d['agents'] = [assoc.to_dict(deep=False) for assoc in self.agent_skills_rel]
            if hasattr(self, 'skill_tools') and self.skill_tools:
                d['tools'] = [assoc.to_dict(deep=False) for assoc in self.skill_tools]
            if hasattr(self, 'skill_knowledges') and self.skill_knowledges:
                d['knowledges'] = [assoc.to_dict(deep=False) for assoc in self.skill_knowledges]
            if hasattr(self, 'task_skills') and self.task_skills:
                d['tasks'] = [assoc.to_dict(deep=False) for assoc in self.task_skills]
        return d
