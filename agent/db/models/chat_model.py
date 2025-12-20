"""
Chat-related database models.

This module contains all database models related to chat functionality
including Chat, Member, and related entities.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class Chat(BaseModel, ExtensibleMixin):
    """
    Chat model representing a conversation.
    
    A chat can be between users, between user and agent, or group conversations.
    """
    __tablename__ = 'chats'
    
    # Chat basic information (compatible with old schema)
    type = Column(String(32), nullable=False, comment="Chat type")
    name = Column(String(100), nullable=False, comment="Chat display name")
    avatar = Column(String(255), nullable=True, comment="Chat avatar URL")
    
    # Agent association
    agent_id = Column(String(64), ForeignKey('agents.id'), nullable=True, comment="Associated agent ID")
    
    # Chat status and metadata
    lastMsg = Column(Text, nullable=True, comment="Last message content")
    lastMsgTime = Column(Integer, nullable=True, comment="Last message timestamp (milliseconds)")
    unread = Column(Integer, default=0, nullable=False, comment="Unread message count")
    pinned = Column(Boolean, default=False, nullable=False, comment="Whether chat is pinned")
    muted = Column(Boolean, default=False, nullable=False, comment="Whether chat is muted")
    
    # Relationships
    agent = relationship("DBAgent", backref="chats")
    members = relationship("Member", back_populates="chat", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    notifications = relationship("ChatNotification", back_populates="chat", cascade="all, delete-orphan", foreign_keys="ChatNotification.chatId")
    
    def __repr__(self):
        return f"<Chat(id='{self.id}', name='{self.name}', type='{self.type}')>"
    
    def to_dict(self, include_members=False, include_messages=False, deep=False) -> dict:
        """
        Convert chat to dictionary with optional related data.
        
        Args:
            include_members (bool): Whether to include member data
            include_messages (bool): Whether to include message data
            deep (bool): Whether to include deep nested data (alias for include_members and include_messages)
            
        Returns:
            dict: Chat data as dictionary
        """
        data = super().to_dict()
        
        # If deep=True, include both members and messages
        if deep:
            include_members = True
            include_messages = True
        
        if include_members:
            data['members'] = [member.to_dict() for member in self.members]
            
        if include_messages:
            data['messages'] = [message.to_dict() for message in self.messages]
        
        # Include agent information if available
        if deep and self.agent:
            data['agent'] = self.agent.to_dict(deep=False)
            
        return data
    
    def get_member_count(self) -> int:
        """Get the number of members in this chat."""
        return len(self.members) if self.members else 0

    def get_members(self) -> int:
        """Get the number of members in this chat."""
        return self.members if self.members else []
    
    def get_message_count(self) -> int:
        """Get the number of messages in this chat."""
        return len(self.messages) if self.messages else 0
    
    def is_group_chat(self) -> bool:
        """Check if this is a group chat."""
        return self.type == 'group' or self.get_member_count() > 2
    
    def update_last_message(self, message_content: str, timestamp: int):
        """Update the last message information."""
        self.lastMsg = message_content
        self.lastMsgTime = timestamp
        self.updated_at = datetime.utcnow()


class Member(BaseModel, ExtensibleMixin):
    """
    Chat member model representing a participant in a chat.

    Links users to chats with their role and status information.
    Enhanced with modern BaseModel features while preserving old schema fields.
    """
    __tablename__ = 'members'

    # Old schema fields (preserved for compatibility)
    chatId = Column(String(64), ForeignKey('chats.id'), nullable=False, comment="Chat ID")
    userId = Column(String(64), nullable=False, comment="User ID")
    
    # Add unique constraint for the old composite key behavior
    __table_args__ = (
        UniqueConstraint('chatId', 'userId', name='uq_member_chat_user'),
    )

    # Member information (compatible with old schema)
    role = Column(String(32), nullable=False, comment="Member role")
    name = Column(String(100), nullable=False, comment="Display name in this chat")
    avatar = Column(String(255), nullable=True, comment="Avatar URL")

    # Member status and additional fields (compatible with old schema)
    status = Column(String(16), nullable=True, comment="Member status")
    agentName = Column(String(100), nullable=True, comment="Agent name if member is an agent")
    
    # Relationships
    chat = relationship("Chat", back_populates="members")
    
    def __repr__(self):
        return f"<Member(userId='{self.userId}', chatId='{self.chatId}', role='{self.role}')>"
    
    def to_dict(self) -> dict:
        """Convert member to dictionary."""
        # Use BaseModel's to_dict() and it will include all fields automatically
        return super().to_dict()
    
    def is_admin(self) -> bool:
        """Check if this member is an admin."""
        return self.role == 'admin'
    
    def is_guest(self) -> bool:
        """Check if this member is a guest."""
        return self.role == 'guest'
    
    def mark_as_read(self, timestamp: int = None):
        """Mark messages as read up to the given timestamp."""
        # This method is kept for compatibility but doesn't update any fields
        # since the Member model doesn't have lastReadAt field in the old schema
        pass


class ChatNotification(BaseModel):
    """
    Chat notification model for system notifications within chats.
    
    Used for system messages, member join/leave notifications, etc.
    Enhanced with modern BaseModel features while preserving old schema fields.
    """
    __tablename__ = 'chat_notification'
    
    # Old schema fields (preserved for compatibility)
    uid = Column(String(64), nullable=False, unique=True, comment="Legacy notification UID for compatibility")
    chatId = Column(String(64), ForeignKey('chats.id'), nullable=False, comment="Chat ID")
    
    # Notification content (compatible with old schema)
    content = Column(JSON, nullable=False, comment="Notification content")
    timestamp = Column(Integer, nullable=False, comment="Notification timestamp")
    isRead = Column(Boolean, default=False, nullable=True, comment="Whether notification is read")
    
    # Relationships
    chat = relationship("Chat", back_populates="notifications")
    
    def __repr__(self):
        return f"<ChatNotification(id='{self.id}', uid='{self.uid}', chatId='{self.chatId}')>"
    
    def to_dict(self) -> dict:
        """Convert notification to dictionary."""
        # Use BaseModel's to_dict() and it will include all fields automatically
        return super().to_dict()
    
    def mark_as_read(self):
        """Mark notification as read."""
        self.isRead = True
        self.updated_at = datetime.utcnow()
