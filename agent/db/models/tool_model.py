"""
Agent tool database models.

This module contains database models for agent tool management:
- DBAgentTool: Agent tool model
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class DBAgentTool(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for agent tools with standard design"""
    __tablename__ = 'agent_tools'

    # Primary key
    id = Column(String(64), primary_key=True)

    # Basic tool information
    name = Column(String(128), nullable=False)
    description = Column(Text)
    owner = Column(String(128), nullable=False)

    # Tool properties
    tool_type = Column(String(64))           # tool category
    version = Column(String(64))             # current version
    path = Column(Text)                      # tool path or URL
    level = Column(Integer, default=1)       # complexity level 1-5

    # Tool configuration
    config = Column(JSON)                    # tool configuration
    capabilities = Column(JSON)              # List[str] - what the tool can do
    limitations = Column(JSON)               # List[str] - tool limitations
    dependencies = Column(JSON)              # List[str] - required dependencies

    # Access and pricing
    public = Column(Boolean, default=False)  # public availability
    rentable = Column(Boolean, default=False) # can be rented
    price = Column(Float, default=0.0)       # price per use
    price_model = Column(String(32))         # free, per_use, subscription

    # Tool status
    status = Column(String(32), default='active')  # active, inactive, deprecated

    # Metadata and settings
    settings = Column(JSON)  # flexible settings storage

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        if deep:
            # Include association details through backref relationships
            if hasattr(self, 'skill_tools') and self.skill_tools:
                d['skills'] = [assoc.to_dict(deep=False) for assoc in self.skill_tools]
        return d
