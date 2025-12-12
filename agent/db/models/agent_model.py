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
import uuid


class DBAgent(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agents with standard design"""
    __tablename__ = 'agents'

    # Primary key with auto-generation
    id = Column(String(64), primary_key=True, default=lambda: f"agent_{uuid.uuid4().hex[:16]}")

    # Basic agent information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Agent profile
    gender = Column(String(16), default='gender_options.male')  # male, female, other
    title = Column(JSON)  # job titles (array of strings)
    rank = Column(String(64))    # seniority level
    birthday = Column(String(32))  # birth date

    # Agent hierarchy and relationships
    supervisor_id = Column(String(64), ForeignKey('agents.id'), nullable=True)

    # Agent characteristics
    personalities = Column(JSON)  # List[str] - personality traits (concise naming)
    capabilities = Column(JSON)   # List[str] - agent capabilities

    # Agent configuration
    status = Column(String(32), default='active')    # active, inactive, suspended
    version = Column(String(64))                     # agent version
    url = Column(String(512))                        # agent endpoint URL
    vehicle_id = Column(String(64))                  # vehicle where agent is deployed/stored

    # Avatar configuration - Foreign key to avatar_resources table
    avatar_resource_id = Column(String(64), ForeignKey('avatar_resources.id'), nullable=True)

    # Extra data - flexible JSON storage for additional data
    extra_data = Column(JSON)

    # Relationships
    supervisor = relationship("DBAgent", remote_side=[id], backref="subordinates")
    avatar_resource = relationship("DBAvatarResource", foreign_keys=[avatar_resource_id], backref="agents")

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        import json
        d = super().to_dict()
        
        # Parse JSON string fields back to arrays/objects for frontend
        json_fields = ['personalities', 'title', 'extra_data']  # Use personalities (unified naming)
        for field in json_fields:
            if field in d and isinstance(d[field], str):
                try:
                    d[field] = json.loads(d[field])
                except:
                    # If parsing fails, keep as is
                    pass
        
        # Always extract org_id from org_rels (even if deep=False)
        if hasattr(self, 'org_rels') and self.org_rels and len(self.org_rels) > 0:
            d['org_id'] = self.org_rels[0].org_id
        
        if deep:
            # Include supervisor details
            if self.supervisor:
                d['supervisor'] = self.supervisor.to_dict(deep=False)
            # Include avatar resource details
            if self.avatar_resource:
                d['avatar_resource'] = self.avatar_resource.to_dict(deep=False)
            # Include association details through backref relationships (use correct backref names)
            if hasattr(self, 'org_rels') and self.org_rels:
                d['organizations'] = [assoc.to_dict(deep=False) for assoc in self.org_rels]
                # Extract primary org_id from first organization (for frontend compatibility)
                if len(self.org_rels) > 0:
                    d['org_id'] = self.org_rels[0].org_id  # org_id is the organization ID in the relationship
            # For skills and tasks, return the actual skill/task objects, not the relationship objects
            # Skip relationships where the skill/task object doesn't exist (orphaned foreign keys)
            if hasattr(self, 'skill_rels') and self.skill_rels:
                d['skills'] = [assoc.skill.to_dict(deep=False) for assoc in self.skill_rels if assoc.skill]
            if hasattr(self, 'task_rels') and self.task_rels:
                d['tasks'] = [assoc.task.to_dict(deep=False) for assoc in self.task_rels if assoc.task]
        
        return d


# Import the separated models to maintain relationships
from .task_model import DBAgentTask
from .tool_model import DBAgentTool  
from .knowledge_model import DBAgentKnowledge
from .vehicle_model import DBAgentVehicle
from .avatar_model import DBAvatarResource
