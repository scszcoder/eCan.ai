"""
Avatar resource database models.

This module contains database models for avatar resource management:
- DBAvatarResource: Avatar resource model for managing images and videos
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, JSON
from .base_model import BaseModel, TimestampMixin
import uuid


class DBAvatarResource(BaseModel, TimestampMixin):
    """Database model for avatar resources"""
    __tablename__ = 'avatar_resources'

    # Primary key with auto-generation
    id = Column(String(64), primary_key=True, default=lambda: f"avatar_{uuid.uuid4().hex[:16]}")

    # Resource type
    resource_type = Column(String(32), nullable=False)  # system, uploaded, generated
    
    # Resource name and description
    name = Column(String(128))                          # Resource name (e.g., "A001", "Professional Male")
    description = Column(String(512))                   # Resource description
    
    # File information
    image_path = Column(String(512))                    # Local image path
    video_path = Column(String(512))                    # Local video path
    image_hash = Column(String(64))                     # Image MD5 hash
    video_hash = Column(String(64))                     # Video MD5 hash
    
    # Cloud storage information
    cloud_image_url = Column(String(512))               # Cloud image URL
    cloud_video_url = Column(String(512))               # Cloud video URL
    cloud_image_key = Column(String(512))               # Cloud storage key for image
    cloud_video_key = Column(String(512))               # Cloud storage key for video
    cloud_synced = Column(Boolean, default=False)       # Whether synced to cloud
    
    # Metadata (using avatar_metadata to avoid SQLAlchemy reserved word)
    avatar_metadata = Column(JSON)                      # Detailed metadata
    # {
    #   "image_format": "png",
    #   "image_size": 12345,
    #   "image_width": 512,
    #   "image_height": 512,
    #   "video_format": "mp4",
    #   "video_size": 67890,
    #   "video_duration": 3.5,
    #   "video_fps": 30,
    #   "generation_model": "stable-diffusion-video",
    #   "generation_params": {...},
    #   "tags": ["professional", "male", "formal"],
    #   "thumbnail_path": "/path/to/thumbnail.png"
    # }
    
    # Usage statistics
    usage_count = Column(Integer, default=0)            # Usage count
    last_used_at = Column(DateTime)                     # Last used timestamp
    
    # Owner information
    owner = Column(String(128))                         # Owner username
    is_public = Column(Boolean, default=False)          # Whether public (for avatar marketplace)

    def to_dict(self, deep=False):
        """Convert model instance to dictionary"""
        import json
        d = super().to_dict()
        
        # Parse JSON string fields back to objects for frontend
        if 'avatar_metadata' in d and isinstance(d['avatar_metadata'], str):
            try:
                d['avatar_metadata'] = json.loads(d['avatar_metadata'])
            except:
                pass
        
        return d
