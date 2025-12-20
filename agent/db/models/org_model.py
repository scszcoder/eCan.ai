"""
Organization database models.

This module contains database models for organization management:
- DBAgentOrg: Main organization model with hierarchical structure
"""

from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON, BigInteger, Float
from sqlalchemy.orm import relationship
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin
from datetime import datetime


class DBAgentOrg(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for organizations with hierarchical structure"""
    __tablename__ = 'agent_orgs'

    # Override the BaseModel id field with our specific requirements
    id = Column(String(64), primary_key=True, default=None)

    # Basic organization information
    name = Column(String(128), nullable=False)
    description = Column(Text)

    # Hierarchical structure
    parent_id = Column(String(64), ForeignKey('agent_orgs.id'), nullable=True)

    # Organization metadata
    org_type = Column(String(64), default='department')  # department, team, division, etc.
    level = Column(Integer, default=0)  # 0 = root, 1 = first level, etc.
    sort_order = Column(Integer, default=0)  # for ordering within same level

    # Status and settings
    status = Column(String(32), default='active')  # active, inactive, archived
    settings = Column(JSON)  # flexible settings storage

    # Relationships
    parent = relationship("DBAgentOrg", remote_side=[id], backref="children")

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        d = super().to_dict()
        # Add backward compatibility for organization_type field
        d['organization_type'] = d.get('org_type', 'department')
        if deep:
            # Include children in deep conversion
            d['children'] = [child.to_dict(deep=False) for child in self.children]
        return d

    def get_full_path(self):
        """Get full path from root to this organization"""
        path = []
        current = self
        while current:
            path.insert(0, current.name)
            current = current.parent
        return ' / '.join(path)

    def get_all_descendants(self):
        """Get all descendant organizations recursively"""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        return descendants

    def is_leaf(self):
        """Check if this organization is a leaf node (has no children)"""
        return len(self.children) == 0

    def get_depth(self):
        """Get the depth of this organization in the hierarchy"""
        depth = 0
        current = self.parent
        while current:
            depth += 1
            current = current.parent
        return depth

    def get_root(self):
        """Get the root organization of this hierarchy"""
        current = self
        while current.parent:
            current = current.parent
        return current

    def get_siblings(self):
        """Get all sibling organizations (same parent)"""
        if not self.parent:
            return []
        return [child for child in self.parent.children if child.id != self.id]

    def get_leaf_descendants(self):
        """Get all leaf node descendants"""
        leaves = []
        for child in self.children:
            if child.is_leaf():
                leaves.append(child)
            else:
                leaves.extend(child.get_leaf_descendants())
        return leaves

    def __repr__(self):
        return f"<DBAgentOrg(id='{self.id}', name='{self.name}', type='{self.org_type}')>"

    def __str__(self):
        return f"{self.name} ({self.org_type})"

