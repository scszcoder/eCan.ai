"""
Agent database models.

This module contains database models for agent management:
- DBAgent: Main agent model
- Association tables for agent relationships
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin
from datetime import datetime


class DBAgent(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agents with standard design"""
    __tablename__ = 'agents'

    # Primary key
    id = Column(String(64), primary_key=True)

    # Basic agent information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Agent profile
    gender = Column(String(16))  # male, female, other
    title = Column(String(128))  # job title
    rank = Column(String(64))    # seniority level
    birthday = Column(String(32))  # birth date

    # Agent hierarchy and relationships
    supervisor_id = Column(String(64), ForeignKey('agents.id'), nullable=True)
    # Note: subordinate_ids and peer_ids removed - use relationships instead

    # Agent characteristics
    personality_traits = Column(JSON)  # List[str] - personality traits
    capabilities = Column(JSON)        # List[str] - agent capabilities
    # Note: skills field removed - use agent_skills relationship instead

    # Agent configuration
    status = Column(String(32), default='active')    # active, inactive, suspended
    version = Column(String(64))                     # agent version
    url = Column(String(512))                        # agent endpoint URL

    # Metadata and settings
    settings = Column(JSON)  # flexible settings storage

    # Relationships
    supervisor = relationship("DBAgent", remote_side=[id], backref="subordinates")

    # Association relationships (using new association models)
    # Note: These will be accessed through the association models for rich relationship data

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # Include supervisor details
            if self.supervisor:
                d['supervisor'] = self.supervisor.to_dict(deep=False)
            # Include association details through backref relationships
            if hasattr(self, 'agent_orgs') and self.agent_orgs:
                d['organizations'] = [assoc.to_dict(deep=False) for assoc in self.agent_orgs]
            if hasattr(self, 'agent_skills_rel') and self.agent_skills_rel:
                d['skills'] = [assoc.to_dict(deep=False) for assoc in self.agent_skills_rel]
            if hasattr(self, 'agent_tasks_rel') and self.agent_tasks_rel:
                d['task_executions'] = [assoc.to_dict(deep=False) for assoc in self.agent_tasks_rel]
        return d


# Import the separated models to maintain relationships
from .task_model import DBAgentTask
from .tool_model import DBAgentTool  
from .knowledge_model import DBAgentKnowledge
from .vehicle_model import DBAgentVehicle
