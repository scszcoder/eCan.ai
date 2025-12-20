"""
Message-related database models.

This module contains all database models related to message functionality
including Message, Attachment, and related entities.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .base_model import BaseModel, TimestampMixin, ExtensibleMixin


class Message(BaseModel, ExtensibleMixin):
    """
    Message model representing a single message in a chat.
    
    Supports various message types including text, form, notification, etc.
    """
    __tablename__ = 'messages'
    
    # Foreign keys
    chatId = Column(String, ForeignKey('chats.id'), nullable=False, comment="Chat ID")
    
    # Message basic information (compatible with old schema)
    role = Column(String(32), nullable=False, comment="Message role")
    content = Column(JSON, nullable=False, comment="Message content as JSON")
    senderId = Column(String(64), nullable=True, comment="Sender user ID")
    senderName = Column(String(100), nullable=True, comment="Sender display name")
    
    # Message metadata (compatible with old schema)
    createAt = Column(Integer, nullable=False, comment="Creation timestamp (milliseconds)")
    time = Column(Integer, nullable=True, comment="Display time (milliseconds)")
    status = Column(String(16), nullable=False, comment="Message status")
    
    # Message state
    isRead = Column(Boolean, default=False, nullable=False, comment="Whether message is read")
    readAt = Column(Integer, nullable=True, comment="Read timestamp (milliseconds)")
    
    # Relationships
    chat = relationship("Chat", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Message(id='{self.id}', chatId='{self.chatId}', role='{self.role}')>"
    
    def to_dict(self, include_attachments=False, deep=False) -> dict:
        """
        Convert message to dictionary with optional attachment data.
        
        Args:
            include_attachments (bool): Whether to include attachment data
            deep (bool): Whether to include deep nested data (alias for include_attachments)
            
        Returns:
            dict: Message data as dictionary
        """
        result = super().to_dict()
        
        # If deep=True, include attachments
        if deep:
            include_attachments = True
        
        if include_attachments and self.attachments:
            result['attachments'] = [attachment.to_dict() for attachment in self.attachments]
        else:
            result['attachments'] = []
            
        return result
    
    def get_content_type(self) -> str:
        """Get the message content type."""
        if isinstance(self.content, dict):
            return self.content.get('type', 'unknown')
        return 'unknown'
    
    def get_text_content(self) -> str:
        """Get text content from the message."""
        if isinstance(self.content, dict):
            if self.content.get('type') == 'text':
                return self.content.get('text', '')
            elif self.content.get('type') == 'form':
                return self.content.get('text', '')
        return ''
    
    def is_text_message(self) -> bool:
        """Check if this is a text message."""
        return self.get_content_type() == 'text'
    
    def is_form_message(self) -> bool:
        """Check if this is a form message."""
        return self.get_content_type() == 'form'
    
    def is_notification_message(self) -> bool:
        """Check if this is a notification message."""
        return self.get_content_type() == 'notification'
    
    def mark_as_read(self, timestamp: int = None):
        """Mark message as read."""
        if timestamp is None:
            timestamp = int(datetime.utcnow().timestamp() * 1000)
        self.isRead = True
        self.readAt = timestamp
        self.updated_at = datetime.utcnow()
    
    def update_status(self, status: str):
        """Update message status."""
        self.status = status
        self.updated_at = datetime.utcnow()


class Attachment(BaseModel, ExtensibleMixin):
    """
    Attachment model representing files attached to messages.
    
    Supports various file types including images, documents, etc.
    Enhanced with modern BaseModel features while preserving old schema fields.
    """
    __tablename__ = 'attachments'
    
    # Old schema fields (preserved for compatibility)
    uid = Column(String(64), nullable=False, unique=True, comment="Legacy attachment UID for compatibility")
    messageId = Column(String(64), ForeignKey('messages.id'), nullable=False, comment="Message ID")
    
    # Attachment information (compatible with old schema)
    name = Column(String(255), nullable=False, comment="File name")
    status = Column(String(32), nullable=False, comment="Attachment status")
    url = Column(String(512), nullable=True, comment="File URL")
    size = Column(Integer, nullable=True, comment="File size in bytes")
    type = Column(String(64), nullable=True, comment="File type")
    
    # Relationships
    message = relationship("Message", back_populates="attachments")
    
    def __repr__(self):
        return f"<Attachment(id='{self.id}', uid='{self.uid}', name='{self.name}', type='{self.type}')>"
    
    def to_dict(self) -> dict:
        """Convert attachment to dictionary."""
        # Use BaseModel's to_dict() and it will include all fields automatically
        return super().to_dict()
    
    def is_image(self) -> bool:
        """Check if this attachment is an image."""
        image_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp']
        return self.type.lower() in image_types
    
    def is_document(self) -> bool:
        """Check if this attachment is a document."""
        doc_types = ['application/pdf', 'application/msword', 'text/plain', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']
        return self.type.lower() in doc_types
    
    def get_file_extension(self) -> str:
        """Get file extension from name."""
        if '.' in self.name:
            return self.name.split('.')[-1].lower()
        return ''
    
    def increment_download_count(self):
        """Increment the download count."""
        self.downloadCount += 1
        self.updated_at = datetime.utcnow()
    
    def get_size_formatted(self) -> str:
        """Get formatted file size string."""
        if not self.size:
            return 'Unknown'
        
        if self.size < 1024:
            return f"{self.size} B"
        elif self.size < 1024 * 1024:
            return f"{self.size / 1024:.1f} KB"
        elif self.size < 1024 * 1024 * 1024:
            return f"{self.size / (1024 * 1024):.1f} MB"
        else:
            return f"{self.size / (1024 * 1024 * 1024):.1f} GB"
