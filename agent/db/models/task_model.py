"""
Agent task database models.

This module contains database models for agent task management:
- DBAgentTask: Agent task model
"""

import uuid
from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentTask(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent tasks with standard design"""
    __tablename__ = 'agent_tasks'

    # Primary key with auto-generation
    id = Column(String(64), primary_key=True, default=lambda: f"task_{uuid.uuid4().hex[:16]}")

    # Basic task information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Task assignment (removed direct foreign keys, use association tables instead)
    # Note: agent assignment now handled through DBAgentTaskRel
    org_id = Column(String(64), ForeignKey('agent_orgs.id'), nullable=True)

    # Task properties
    priority = Column(String(32), default='medium')  # low, medium, high, urgent
    status = Column(String(32), default='pending')   # pending, running, completed, failed, cancelled
    task_type = Column(String(64))                   # task category/type

    # Task execution
    objectives = Column(JSON)    # List of objectives
    schedule = Column(JSON)      # Schedule configuration
    trigger = Column(String(64)) # trigger type: manual, scheduled, event

    # Task results
    progress = Column(Float, default=0.0)  # 0.0 to 1.0
    result = Column(JSON)                  # execution result
    error_message = Column(Text)           # error details if failed

    # Metadata and settings
    settings = Column(JSON)  # flexible settings storage

    # Relationships
    organization = relationship("DBAgentOrg", backref="tasks")
    # Note: agent relationship now handled through DBAgentTaskRel

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        # Database records are always UI-created (code-based tasks are not stored in DB)
        d['source'] = 'ui'
        if deep:
            # Include organization details
            if self.organization:
                d['organization'] = self.organization.to_dict(deep=False)
            # Include association details through backref relationships
            if hasattr(self, 'agent_tasks_rel') and self.agent_tasks_rel:
                d['agent_executions'] = [assoc.to_dict(deep=False) for assoc in self.agent_tasks_rel]
            if hasattr(self, 'task_skills') and self.task_skills:
                d['skills'] = [assoc.to_dict(deep=False) for assoc in self.task_skills]
        return d
