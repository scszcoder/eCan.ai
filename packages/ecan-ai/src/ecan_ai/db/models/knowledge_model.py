"""
Agent knowledge database models.

This module contains database models for agent knowledge management:
- DBAgentKnowledge: Agent knowledge model
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentKnowledge(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent knowledge with standard design"""
    __tablename__ = 'agent_knowledges'

    # Primary key
    id = Column(String(64), primary_key=True)

    # Basic knowledge information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Knowledge properties
    knowledge_type = Column(String(64))      # document, database, api, etc.
    version = Column(String(64))             # current version
    path = Column(Text)                      # knowledge source path or URL
    level = Column(Integer, default=1)       # complexity level 1-5

    # Knowledge content
    content = Column(Text)                   # knowledge content or summary
    tags = Column(JSON)                      # List[str] - knowledge tags
    categories = Column(JSON)                # List[str] - knowledge categories

    # Knowledge configuration
    config = Column(JSON)                    # knowledge configuration
    access_methods = Column(JSON)            # List[str] - how to access this knowledge
    limitations = Column(JSON)               # List[str] - knowledge limitations

    # Access and pricing
    public = Column(Boolean, default=False)  # public availability
    rentable = Column(Boolean, default=False) # can be rented
    price = Column(Float, default=0.0)       # price per access
    price_model = Column(String(32))         # free, per_access, subscription

    # Knowledge status
    status = Column(String(32), default='active')  # active, inactive, deprecated

    # Metadata and settings
    settings = Column(JSON)  # flexible settings storage

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # Include association details through backref relationships
            if hasattr(self, 'skill_knowledges') and self.skill_knowledges:
                d['skills'] = [assoc.to_dict(deep=False) for assoc in self.skill_knowledges]
        return d
