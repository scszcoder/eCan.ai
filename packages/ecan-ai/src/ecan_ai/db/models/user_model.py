"""
User-related database models.

This module contains all database models related to user functionality
including User, UserProfile, and related entities.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON
from datetime import datetime
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin, SoftDeleteMixin


class User(BaseModel, ExtensibleMixin, SoftDeleteMixin):
    """
    User model representing a system user.
    
    This model stores basic user information and authentication data.
    """
    __tablename__ = 'users'
    
    # User basic information
    username = Column(String(100), unique=True, nullable=False, comment="Unique username")
    email = Column(String(255), unique=True, nullable=True, comment="User email address")
    display_name = Column(String(255), nullable=True, comment="Display name")
    avatar = Column(String(500), nullable=True, comment="Avatar URL")
    
    # User status
    is_active = Column(Boolean, default=True, nullable=False, comment="Whether user is active")
    is_verified = Column(Boolean, default=False, nullable=False, comment="Whether user is verified")
    last_login_at = Column(Integer, nullable=True, comment="Last login timestamp (milliseconds)")
    
    # User preferences
    language = Column(String(10), default='en', nullable=False, comment="Preferred language")
    timezone = Column(String(50), default='UTC', nullable=False, comment="User timezone")
    
    def __repr__(self):
        return f"<User(id='{self.id}', username='{self.username}')>"
    
    def to_dict(self, include_sensitive=False) -> dict:
        """
        Convert user to dictionary.
        
        Args:
            include_sensitive (bool): Whether to include sensitive information
            
        Returns:
            dict: User data as dictionary
        """
        result = super().to_dict()
        
        if not include_sensitive:
            # Remove sensitive fields from public representation
            sensitive_fields = ['email']
            for field in sensitive_fields:
                result.pop(field, None)
                
        return result
    
    def update_last_login(self, timestamp: int = None):
        """Update last login timestamp."""
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp() * 1000)
        self.last_login_at = timestamp
        self.updated_at = datetime.utcnow()
    
    def activate(self):
        """Activate the user account."""
        self.is_active = True
        self.updated_at = datetime.utcnow()
    
    def deactivate(self):
        """Deactivate the user account."""
        self.is_active = False
        self.updated_at = datetime.utcnow()
    
    def verify(self):
        """Mark user as verified."""
        self.is_verified = True
        self.updated_at = datetime.utcnow()


class UserProfile(BaseModel, ExtensibleMixin):
    """
    User profile model for extended user information.
    
    Stores additional user profile data that's not part of the core User model.
    """
    __tablename__ = 'user_profiles'
    
    # Foreign key
    user_id = Column(String, nullable=False, unique=True, comment="User ID")
    
    # Profile information
    first_name = Column(String(100), nullable=True, comment="First name")
    last_name = Column(String(100), nullable=True, comment="Last name")
    bio = Column(Text, nullable=True, comment="User biography")
    location = Column(String(255), nullable=True, comment="User location")
    website = Column(String(500), nullable=True, comment="User website")
    
    # Contact information
    phone = Column(String(20), nullable=True, comment="Phone number")
    
    # Profile settings
    is_public = Column(Boolean, default=True, nullable=False, comment="Whether profile is public")
    show_email = Column(Boolean, default=False, nullable=False, comment="Whether to show email publicly")
    
    def __repr__(self):
        return f"<UserProfile(id='{self.id}', user_id='{self.user_id}')>"
    
    def to_dict(self, include_private=False) -> dict:
        """
        Convert user profile to dictionary.
        
        Args:
            include_private (bool): Whether to include private information
            
        Returns:
            dict: User profile data as dictionary
        """
        result = super().to_dict()
        
        if not include_private:
            # Remove private fields if not requested
            private_fields = ['phone']
            for field in private_fields:
                result.pop(field, None)
                
        return result
    
    def get_full_name(self) -> str:
        """Get the full name of the user."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return ""
    
    def make_public(self):
        """Make the profile public."""
        self.is_public = True
        self.updated_at = datetime.utcnow()
    
    def make_private(self):
        """Make the profile private."""
        self.is_public = False
        self.updated_at = datetime.utcnow()


class UserSession(BaseModel):
    """
    User session model for tracking user sessions.
    
    Stores session information for authentication and security purposes.
    """
    __tablename__ = 'user_sessions'
    
    # Foreign key
    user_id = Column(String, nullable=False, comment="User ID")
    
    # Session information
    session_token = Column(String(255), unique=True, nullable=False, comment="Session token")
    device_info = Column(String(500), nullable=True, comment="Device information")
    ip_address = Column(String(45), nullable=True, comment="IP address")
    user_agent = Column(String(1000), nullable=True, comment="User agent string")
    
    # Session status
    is_active = Column(Boolean, default=True, nullable=False, comment="Whether session is active")
    expires_at = Column(Integer, nullable=False, comment="Session expiration timestamp (milliseconds)")
    last_activity_at = Column(Integer, nullable=True, comment="Last activity timestamp (milliseconds)")
    
    def __repr__(self):
        return f"<UserSession(id='{self.id}', user_id='{self.user_id}')>"
    
    def to_dict(self) -> dict:
        """Convert user session to dictionary."""
        result = super().to_dict()
        # Remove sensitive session token from public representation
        result.pop('session_token', None)
        return result
    
    def is_expired(self) -> bool:
        """Check if the session is expired."""
        current_time = int(datetime.utcnow().timestamp() * 1000)
        return current_time > self.expires_at
    
    def extend_session(self, duration_ms: int):
        """Extend the session expiration time."""
        current_time = int(datetime.utcnow().timestamp() * 1000)
        self.expires_at = current_time + duration_ms
        self.updated_at = datetime.utcnow()
    
    def update_activity(self, timestamp: int = None):
        """Update last activity timestamp."""
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp() * 1000)
        self.last_activity_at = timestamp
        self.updated_at = datetime.utcnow()
    
    def deactivate(self):
        """Deactivate the session."""
        self.is_active = False
        self.updated_at = datetime.utcnow()
