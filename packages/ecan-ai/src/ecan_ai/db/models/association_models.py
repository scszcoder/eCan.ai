"""
Association table models for many-to-many relationships.

This module contains all association tables that define relationships between entities:
- DBAgentOrgRel: Agent-Organization relationship
- DBAgentSkillRel: Agent-Skill relationship
- DBAgentTaskRel: Agent-Task execution relationship
- DBSkillToolRel: Skill-Tool dependency relationship
- DBAgentSkillKnowledgeRel: Skill-Knowledge dependency relationship
- DBAgentTaskSkillRel: Task-Skill composition relationship
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, Float, UniqueConstraint
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin
from datetime import datetime, timezone
import uuid


class DBAgentOrgRel(BaseModel, TimestampMixin):
    """Agent-Organization relationship"""
    __tablename__ = 'agent_org_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_ao_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    agent_id = Column(String(64), ForeignKey('agents.id', ondelete='CASCADE'), nullable=False)
    org_id = Column(String(64), ForeignKey('agent_orgs.id', ondelete='CASCADE'), nullable=False)

    # Association metadata
    role = Column(String(64), default='member')          # member, manager, admin, owner
    status = Column(String(32), default='active')        # active, inactive, suspended
    join_date = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    leave_date = Column(DateTime, nullable=True)

    # Permissions and access
    permissions = Column(JSON)                            # List[str] - specific permissions
    access_level = Column(String(32), default='read')    # read, write, admin

    # Relationships
    agent = relationship("DBAgent", backref="org_rels")
    organization = relationship("DBAgentOrg", backref="agent_rels")

    # Unique constraint to prevent duplicate associations
    __table_args__ = (
        UniqueConstraint('agent_id', 'org_id', name='unique_agent_org'),
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.agent:
                d['agent'] = self.agent.to_dict(deep=False)
            if self.organization:
                d['organization'] = self.organization.to_dict(deep=False)
        return d


class DBAgentSkillRel(BaseModel, TimestampMixin):
    """Agent-Skill relationship"""
    __tablename__ = 'agent_skill_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_as_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    agent_id = Column(String(64), ForeignKey('agents.id', ondelete='CASCADE'), nullable=False)
    skill_id = Column(String(64), ForeignKey('agent_skills.id', ondelete='CASCADE'), nullable=False)

    # Skill proficiency and experience
    proficiency_level = Column(String(32), default='beginner')  # beginner, intermediate, advanced, expert
    experience_points = Column(Integer, default=0)              # skill experience points
    certification_level = Column(String(32))                    # certification level if any

    # Usage statistics
    usage_count = Column(Integer, default=0)                    # how many times used
    success_rate = Column(Float, default=0.0)                   # success rate 0.0-1.0
    last_used = Column(DateTime, nullable=True)                 # last usage timestamp

    # Status and preferences
    status = Column(String(32), default='active')               # active, inactive, learning
    is_favorite = Column(Boolean, default=False)                # favorite skill flag
    priority = Column(Integer, default=0)                       # priority for skill selection

    # Relationships
    agent = relationship("DBAgent", backref="skill_rels")
    skill = relationship("DBAgentSkill", backref="agent_rels")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('agent_id', 'skill_id', name='unique_agent_skill'),
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.agent:
                d['agent'] = self.agent.to_dict(deep=False)
            if self.skill:
                d['skill'] = self.skill.to_dict(deep=False)
        return d


class DBAgentTaskRel(BaseModel, TimestampMixin):
    """Agent-Task relationship"""
    __tablename__ = 'agent_task_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_at_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    agent_id = Column(String(64), ForeignKey('agents.id', ondelete='CASCADE'), nullable=False)
    task_id = Column(String(64), ForeignKey('agent_tasks.id', ondelete='CASCADE'), nullable=False)
    vehicle_id = Column(String(64), ForeignKey('agent_vehicles.id', ondelete='SET NULL'), nullable=True)

    # Execution status and state
    status = Column(String(32), default='pending')       # pending, running, completed, failed, cancelled, paused
    priority = Column(String(32), default='medium')      # low, medium, high, urgent
    progress = Column(Float, default=0.0)                # 0.0 to 1.0

    # Execution timing
    scheduled_start = Column(DateTime, nullable=True)    # when task is scheduled to start
    actual_start = Column(DateTime, nullable=True)       # when task actually started
    estimated_end = Column(DateTime, nullable=True)      # estimated completion time
    actual_end = Column(DateTime, nullable=True)         # actual completion time

    # Execution results
    result = Column(JSON)                                 # execution result data
    error_message = Column(Text)                          # error details if failed
    logs = Column(Text)                                   # execution logs

    # Resource usage
    cpu_usage = Column(Float)                             # CPU usage percentage
    memory_usage = Column(Float)                          # Memory usage in MB
    execution_time = Column(Float)                        # Total execution time in seconds

    # Metadata
    execution_context = Column(JSON)                      # execution context and parameters
    retry_count = Column(Integer, default=0)              # number of retries
    max_retries = Column(Integer, default=3)              # maximum allowed retries

    # Relationships
    agent = relationship("DBAgent", backref="task_rels")
    task = relationship("DBAgentTask", backref="agent_rels")
    vehicle = relationship("DBAgentVehicle", backref="task_rels")

    # Constraint: only one running status per agent-task combination
    __table_args__ = (
        # Note: We allow multiple records for same agent_id + task_id but only one can be 'running'
        # This will be enforced at application level
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.agent:
                d['agent'] = self.agent.to_dict(deep=False)
            if self.task:
                d['task'] = self.task.to_dict(deep=False)
            if self.vehicle:
                d['vehicle'] = self.vehicle.to_dict(deep=False)
        return d

    def is_running(self):
        """Check if task is currently running"""
        return self.status == 'running'

    def is_completed(self):
        """Check if task is completed (successfully or failed)"""
        return self.status in ['completed', 'failed', 'cancelled']

    def get_duration(self):
        """Get task execution duration in seconds"""
        if self.actual_start and self.actual_end:
            return (self.actual_end - self.actual_start).total_seconds()
        return None


class DBSkillToolRel(BaseModel, TimestampMixin):
    """Skill-Tool relationship"""
    __tablename__ = 'agent_skill_tool_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_st_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    skill_id = Column(String(64), ForeignKey('agent_skills.id', ondelete='CASCADE'), nullable=False)
    tool_id = Column(String(64), ForeignKey('agent_tools.id', ondelete='CASCADE'), nullable=False)

    # Dependency metadata
    dependency_type = Column(String(32), default='required')    # required, optional, recommended
    usage_frequency = Column(String(32), default='medium')      # low, medium, high
    importance = Column(Integer, default=1)                     # 1-5 importance level

    # Configuration and parameters
    tool_config = Column(JSON)                                  # tool-specific configuration for this skill
    parameters = Column(JSON)                                   # default parameters when using this tool

    # Usage statistics
    usage_count = Column(Integer, default=0)                    # how many times this tool was used by skill
    success_rate = Column(Float, default=0.0)                   # success rate when using this tool
    last_used = Column(DateTime, nullable=True)                 # last usage timestamp

    # Status
    status = Column(String(32), default='active')               # active, inactive, deprecated

    # Relationships
    skill = relationship("DBAgentSkill", backref="tool_rels")
    tool = relationship("DBAgentTool", backref="skill_rels")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('skill_id', 'tool_id', name='unique_skill_tool'),
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.skill:
                d['skill'] = self.skill.to_dict(deep=False)
            if self.tool:
                d['tool'] = self.tool.to_dict(deep=False)
        return d


class DBAgentSkillKnowledgeRel(BaseModel, TimestampMixin):
    """Skill-Knowledge relationship"""
    __tablename__ = 'agent_skill_knowledge_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_sk_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    skill_id = Column(String(64), ForeignKey('agent_skills.id', ondelete='CASCADE'), nullable=False)
    knowledge_id = Column(String(64), ForeignKey('agent_knowledges.id', ondelete='CASCADE'), nullable=False)

    # Dependency metadata
    dependency_type = Column(String(32), default='required')    # required, optional, recommended
    usage_frequency = Column(String(32), default='medium')      # low, medium, high
    importance = Column(Integer, default=1)                     # 1-5 importance level

    # Access and usage
    access_pattern = Column(String(32), default='read')         # read, write, read_write
    knowledge_scope = Column(JSON)                              # specific scope/sections of knowledge used

    # Usage statistics
    access_count = Column(Integer, default=0)                   # how many times accessed
    last_accessed = Column(DateTime, nullable=True)             # last access timestamp
    average_query_time = Column(Float, default=0.0)             # average query response time

    # Status
    status = Column(String(32), default='active')               # active, inactive, deprecated

    # Relationships
    skill = relationship("DBAgentSkill", backref="knowledge_rels")
    knowledge = relationship("DBAgentKnowledge", backref="skill_rels")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('skill_id', 'knowledge_id', name='unique_skill_knowledge'),
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.skill:
                d['skill'] = self.skill.to_dict(deep=False)
            if self.knowledge:
                d['knowledge'] = self.knowledge.to_dict(deep=False)
        return d


class DBAgentTaskSkillRel(BaseModel, TimestampMixin):
    """Task-Skill relationship"""
    __tablename__ = 'agent_task_skill_rels'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"rel_ts_{uuid.uuid4().hex[:16]}")

    # Foreign keys
    task_id = Column(String(64), ForeignKey('agent_tasks.id', ondelete='CASCADE'), nullable=False)
    skill_id = Column(String(64), ForeignKey('agent_skills.id', ondelete='CASCADE'), nullable=False)

    # Skill role in task
    role = Column(String(32), default='primary')                # primary, secondary, optional, fallback
    execution_order = Column(Integer, default=0)                # execution order within task
    is_required = Column(Boolean, default=True)                 # whether skill is required for task completion

    # Skill configuration for this task
    skill_config = Column(JSON)                                 # skill-specific configuration
    parameters = Column(JSON)                                   # parameters to pass to skill
    constraints = Column(JSON)                                  # constraints for skill execution

    # Execution planning
    estimated_duration = Column(Float)                          # estimated execution time in seconds
    estimated_cost = Column(Float)                              # estimated cost
    resource_requirements = Column(JSON)                        # required resources

    # Success criteria
    success_criteria = Column(JSON)                             # criteria for successful skill execution
    quality_threshold = Column(Float, default=0.8)              # minimum quality threshold

    # Status and results
    status = Column(String(32), default='pending')              # pending, running, completed, failed, skipped
    actual_duration = Column(Float)                             # actual execution time
    actual_cost = Column(Float)                                 # actual cost
    quality_score = Column(Float)                               # quality score of execution

    # Relationships
    task = relationship("DBAgentTask", backref="skill_rels")
    skill = relationship("DBAgentSkill", backref="task_rels")

    # Unique constraint
    __table_args__ = (
        UniqueConstraint('task_id', 'skill_id', name='unique_task_skill'),
    )

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            if self.task:
                d['task'] = self.task.to_dict(deep=False)
            if self.skill:
                d['skill'] = self.skill.to_dict(deep=False)
        return d

    def is_completed(self):
        """Check if skill execution is completed"""
        return self.status in ['completed', 'failed', 'skipped']

    def meets_quality_threshold(self):
        """Check if execution meets quality threshold"""
        return self.quality_score is not None and self.quality_score >= self.quality_threshold
