"""
Skill history database models.

This module contains database models for skill version history:
- DBSkillHistory: Stores complete snapshots of each skill save
"""

import uuid
from sqlalchemy import Column, String, Integer, BigInteger, Text, JSON
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


# Maximum number of history records to keep per skill
MAX_HISTORY_PER_SKILL = 100


class DBSkillHistory(BaseModel, TimestampMixin, ExtensibleMixin):
    """Database model for skill version history.

    Stores complete snapshots of each skill save, enabling:
    - Version history viewing
    - Old version restoration
    - Change tracking and diff
    """
    __tablename__ = 'skill_history'

    # Primary key
    id = Column(String(64), primary_key=True, default=lambda: f"hist_{uuid.uuid4().hex[:16]}")

    # Skill reference (foreign key to agent_skills.id)
    skill_id = Column(String(64), nullable=False, index=True)

    # Skill metadata (denormalized for easier querying without joins)
    skill_name = Column(String(128), nullable=False, index=True)
    owner = Column(String(128), nullable=False, index=True)

    # Version tracking
    version = Column(String(64), nullable=False)  # e.g., "1.0.0", "1.0.1"
    version_number = Column(Integer, nullable=False, default=1)  # Auto-incrementing integer

    # Basic skill fields (denormalized for quick access)
    description = Column(Text)
    version_label = Column(String(128))  # Optional version label like "v1", "beta"
    path = Column(Text)
    source = Column(String(32), default='ui')  # ui, code, system
    level = Column(String(64))  # entry, intermediate, advanced

    # Core data
    config = Column(JSON)      # Config JSON including cloud execution settings
    diagram = Column(JSON)     # Flowgram diagram data (nodes, edges, etc.)
    tags = Column(JSON)        # List[str] | None

    # Complete snapshot of all skill data + full directory contents (for full restoration)
    skill_data = Column(JSON, nullable=False)

    # Full directory snapshot (skill_files dir, code, mapping, etc.)
    skill_files = Column(JSON, nullable=True)

    # Metadata
    file_size = Column(Integer, default=0)  # Size in bytes
    change_summary = Column(Text)  # Auto-generated or user-provided change notes

    # Source of this history record
    save_type = Column(String(32), default='manual')  # manual, auto_save, restore, save_as

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        # Timestamps are normalized in BaseModel.to_dict (naive UTC-safe).
        return super().to_dict()

    def __repr__(self):
        return f"<DBSkillHistory(id='{self.id}', skill_id='{self.skill_id}', version='{self.version}', version_number={self.version_number})>"
