"""
Skill database models.

This module contains database models for skill management:
- DBAgentSkill: Agent skill model
"""

import uuid
from sqlalchemy import Column, String, Integer, Boolean, Text, JSON, BigInteger
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentSkillView:
    """Typed accessor wrapper for DBAgentSkill dict payloads.

    This is primarily useful for code paths that operate on dict records
    returned by services (e.g., get_skills_by_owner) rather than ORM instances.
    """

    def __init__(self, data: dict | None):
        self._d = data if isinstance(data, dict) else {}

    def str(self, key: str, default: str = "") -> str:
        try:
            v = self._d.get(key, None)
            if v is None:
                return default
            return str(v)
        except Exception:
            return default

    def int(self, key: str, default: int = 0) -> int:
        v = self._d.get(key, None)
        if v is None:
            return default
        try:
            return int(v)
        except Exception:
            return default

    def bool(self, key: str, default: bool = False) -> bool:
        v = self._d.get(key, None)
        if v is None:
            return default
        if isinstance(v, bool):
            return v
        if isinstance(v, (int, float)):
            return bool(v)
        return default

    def list(self, key: str, default: list | None = None) -> list:
        v = self._d.get(key, None)
        if isinstance(v, list):
            return v
        if isinstance(v, tuple):
            return list(v)
        if v is None:
            return default if default is not None else []
        return default if default is not None else []

    def dict(self, key: str, default: dict | None = None) -> dict:
        v = self._d.get(key, None)
        if isinstance(v, dict):
            return v
        if v is None:
            return default if default is not None else {}
        return default if default is not None else {}

    def json(self, key: str, default: object | None = None) -> object:
        v = self._d.get(key, None)
        if isinstance(v, (dict, list)):
            return v
        if v is None:
            return default
        return default


class DBAgentSkill(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent skills"""
    __tablename__ = 'agent_skills'

    # ID field with auto-generation
    id = Column(String(64), primary_key=True, default=lambda: f"skill_{uuid.uuid4().hex[:16]}")
    askid = Column(BigInteger, default=0)
    name = Column(String(128), nullable=False)
    owner = Column(String(128), nullable=False)
    description = Column(Text)
    version = Column(String(128), nullable=False)  # Changed to version, consistent with EC_Skill
    path = Column(Text)
    source = Column(String(32), default='ui')  # ui, code, system
    level = Column(String(64))  # Changed to String, consistent with EC_Skill (entry/intermediate/advanced)
    config = Column(JSON)
    diagram = Column(JSON)  # Flowgram diagram data (nodes, edges, etc.)

    # Fields added from EC_Skill
    tags = Column(JSON)  # List[str] | None
    examples = Column(JSON)  # List[str] | None
    inputModes = Column(JSON)  # List[str] | None
    outputModes = Column(JSON)  # List[str] | None
    # Keep original extension fields
    apps = Column(JSON)
    limitations = Column(JSON)
    price = Column(Integer, default=0)
    price_model = Column(Text)
    public = Column(Boolean, default=False)
    rentable = Column(Boolean, default=False)
    # Note: members relationship commented out due to missing foreign key
    # members = relationship('Member', back_populates='agent_skills', cascade='all, delete-orphan')

    @staticmethod
    def view(data: dict | None) -> DBAgentSkillView:
        return DBAgentSkillView(data)

    def to_view(self) -> DBAgentSkillView:
        return DBAgentSkillView(self.to_dict(deep=False))

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
