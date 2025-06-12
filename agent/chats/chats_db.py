from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, ForeignKey, Text,
    DateTime, func, Index, event, LargeBinary, Enum
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import os
from typing import List, Optional, Dict, Any
import json
from contextlib import contextmanager
import threading
import time


# Constants
MAX_TOTAL_MESSAGES  = 10000  # Maximum messages before cleanup

MAX_MESSAGES_PER_CONVERSATION = 1000  # Maximum messages before cleanup
SESSION_TIMEOUT_MINUTES = 15  # Minutes of inactivity before new session
EDIT_WINDOW_MINUTES = 5  # Time window to edit messages
MESSAGE_CLEANUP_BATCH_SIZE = 100  # Number of messages to delete when cleaning up

# Database setup
Base = declarative_base()
engine = create_engine(
    os.getenv('DATABASE_URL', 'sqlite:///chat_app.db'),
    pool_pre_ping=True,
    connect_args={'check_same_thread': False}  # Only for SQLite
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)


class MessageStatus(PyEnum):
    SENDING = "sending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class MessageType(PyEnum):
    TEXT = "text"
    HTML = "html"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    FILE = "file"
    SYSTEM = "system"


class ChatUser(Base):
    __tablename__ = 'chat_users'

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100))
    avatar_url = Column(String(255))
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    sent_messages = relationship("Message", back_populates="sender")
    message_reads = relationship("MessageRead", back_populates="user")
    memberships = relationship("ConversationMember", back_populates="user")


class Conversation(Base):
    __tablename__ = 'conversations'

    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    is_group = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    avatar_url = Column(String(255))
    description = Column(Text)

    # Relationships
    members = relationship("ConversationMember", back_populates="conversation", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="conversation", cascade="all, delete-orphan")

    def get_active_session(self) -> 'ChatSession':
        """Get or create active session for this conversation"""
        session = db_session()
        active_session = session.query(ChatSession).filter(
            ChatSession.conversation_id == self.id,
            ChatSession.ended_at.is_(None)
        ).first()

        if not active_session:
            active_session = ChatSession(conversation_id=self.id)
            session.add(active_session)
            session.commit()

        return active_session


class ChatSession(Base):
    __tablename__ = 'chat_sessions'

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)

    # Relationships
    conversation = relationship("Conversation", back_populates="sessions")
    messages = relationship("Message", back_populates="session")


class ConversationMember(Base):
    __tablename__ = 'conversation_members'
    __table_args__ = (
        Index('idx_conversation_member', 'conversation_id', 'user_id', unique=True),
    )

    conversation_id = Column(Integer, ForeignKey('conversations.id'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    role = Column(String(20), default='member')  # 'admin', 'moderator', 'member'
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_at = Column(DateTime)

    # Relationships
    user = relationship("User", back_populates="memberships")
    conversation = relationship("Conversation", back_populates="members")


class Message(Base):
    __tablename__ = 'messages'
    __table_args__ = (
        Index('idx_conversation_created', 'conversation_id', 'created_at'),
    )

    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey('chat_sessions.id'), nullable=True)
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    parent_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    content = Column(Text)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.SENDING, nullable=False)
    is_edited = Column(Boolean, default=False)
    is_retracted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    metadata_ = Column('metadata', Text)  # For additional metadata like reactions, mentions, etc.

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="sent_messages")
    parent = relationship("Message", remote_side=[id], backref="replies")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")
    reads = relationship("MessageRead", back_populates="message", cascade="all, delete-orphan")
    session = relationship("ChatSession", back_populates="messages")

    @property
    def is_editable(self) -> bool:
        """Check if the message is still editable (within the edit window)"""
        return (datetime.utcnow() - self.created_at) < timedelta(minutes=EDIT_WINDOW_MINUTES)

    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return {
            'id': self.id,
            'conversation_id': self.conversation_id,
            'session_id': self.session_id,
            'sender_id': self.sender_id,
            'content': self.content,
            'message_type': self.message_type.value,
            'status': self.status.value,
            'is_edited': self.is_edited,
            'is_retracted': self.is_retracted,
            'created_at': self.created_at.isoformat(),
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'attachments': [a.to_dict() for a in self.attachments]
        }


class Attachment(Base):
    __tablename__ = 'attachments'

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer)  # in bytes
    mime_type = Column(String(100))
    file_path = Column(String(512))  # Path to stored file
    thumbnail_path = Column(String(512))  # For images/videos
    width = Column(Integer)  # For images/videos
    height = Column(Integer)  # For images/videos
    duration = Column(Integer)  # For audio/video in seconds
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    message = relationship("Message", back_populates="attachments")

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'file_name': self.file_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'url': f"/attachments/{self.id}/{self.file_name}",
            'thumbnail_url': f"/attachments/thumbnails/{self.id}/{self.file_name}" if self.thumbnail_path else None,
            'width': self.width,
            'height': self.height,
            'duration': self.duration
        }


class MessageRead(Base):
    __tablename__ = 'message_reads'
    __table_args__ = (
        Index('idx_message_read', 'message_id', 'user_id', unique=True),
    )

    message_id = Column(Integer, ForeignKey('messages.id'), primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), primary_key=True)
    read_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    message = relationship("Message", back_populates="reads")
    user = relationship("User", back_populates="message_reads")



# Update the check_message_limit function
@event.listens_for(Message, 'after_insert')
def check_message_limit(mapper, connection, target):
    """Enforce message limits per conversation and globally"""
    session = db_session()
    try:
        # 1. Check and enforce per-conversation limit
        conversation_count = session.query(func.count(Message.id)) \
            .filter(Message.conversation_id == target.conversation_id) \
            .scalar()

        if conversation_count > MAX_MESSAGES_PER_CONVERSATION:
            # Delete oldest messages in this conversation
            oldest_messages = session.query(Message.id) \
                .filter(Message.conversation_id == target.conversation_id) \
                .order_by(Message.created_at.asc()) \
                .limit(conversation_count - MAX_MESSAGES_PER_CONVERSATION + 1) \
                .subquery()

            session.query(Message) \
                .filter(Message.id.in_(oldest_messages)) \
                .delete(synchronize_session=False)

        # 2. Check and enforce global message limit
        total_count = session.query(func.count(Message.id)).scalar()
        if total_count > MAX_TOTAL_MESSAGES:
            # Calculate how many messages to delete
            delete_count = total_count - MAX_TOTAL_MESSAGES + MESSAGE_CLEANUP_BATCH_SIZE
            delete_count = min(delete_count, MESSAGE_CLEANUP_BATCH_SIZE)

            if delete_count > 0:
                # Get IDs of oldest messages to delete
                oldest_message_ids = session.query(Message.id) \
                    .order_by(Message.created_at.asc()) \
                    .limit(delete_count) \
                    .all()

                # Convert list of tuples to list of IDs
                oldest_message_ids = [msg_id for (msg_id,) in oldest_message_ids]

                # Delete the messages
                session.query(Message) \
                    .filter(Message.id.in_(oldest_message_ids)) \
                    .delete(synchronize_session=False)

        session.commit()

    except Exception as e:
        session.rollback()
        logger.error(f"Error in check_message_limit: {str(e)}")
        raise
    finally:
        session.close()


# Add this helper function for manual cleanup
def cleanup_old_messages(batch_size: int = MESSAGE_CLEANUP_BATCH_SIZE) -> int:
    """
    Manually clean up old messages to maintain database size.
    Returns the number of messages deleted.
    """
    session = db_session()
    try:
        # Get total count
        total_count = session.query(func.count(Message.id)).scalar()

        if total_count <= MAX_TOTAL_MESSAGES:
            return 0

        # Calculate how many to delete
        delete_count = min(total_count - MAX_TOTAL_MESSAGES + batch_size, batch_size)

        if delete_count <= 0:
            return 0

        # Get and delete oldest messages
        oldest_message_ids = session.query(Message.id) \
            .order_by(Message.created_at.asc()) \
            .limit(delete_count) \
            .all()

        oldest_message_ids = [msg_id for (msg_id,) in oldest_message_ids]

        deleted_count = session.query(Message) \
            .filter(Message.id.in_(oldest_message_ids)) \
            .delete(synchronize_session=False)

        session.commit()
        return deleted_count

    except Exception as e:
        session.rollback()
        logger.error(f"Error in cleanup_old_messages: {str(e)}")
        return 0
    finally:
        session.close()


@event.listens_for(Message, 'before_insert')
def set_message_session(mapper, connection, target):
    """Set the session for new messages"""
    if not target.session_id:
        session = db_session()
        try:
            # Get or create active session
            active_session = session.query(ChatSession) \
                .filter(
                ChatSession.conversation_id == target.conversation_id,
                ChatSession.ended_at.is_(None)
            ) \
                .first()

            if not active_session:
                # Check last message time to determine if new session is needed
                last_message = session.query(Message) \
                    .filter(Message.conversation_id == target.conversation_id) \
                    .order_by(Message.created_at.desc()) \
                    .first()

                if last_message and (datetime.utcnow() - last_message.created_at) < timedelta(
                        minutes=SESSION_TIMEOUT_MINUTES):
                    # Use the same session as last message
                    target.session_id = last_message.session_id
                else:
                    # Create new session
                    active_session = ChatSession(conversation_id=target.conversation_id)
                    session.add(active_session)
                    session.flush()  # Get the ID
                    target.session_id = active_session.id
            else:
                target.session_id = active_session.id

            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

def periodic_cleanup(interval_minutes=60):
    while True:
        try:
            deleted = cleanup_old_messages()
            if deleted > 0:
                logger.info(f"Cleaned up {deleted} old messages")
        except Exception as e:
            logger.error(f"Error during periodic cleanup: {e}")
        time.sleep(interval_minutes * 60)

# # Start cleanup thread
# cleanup_thread = threading.Thread(target=periodic_cleanup, daemon=True)
# cleanup_thread.start()

def get_chats_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


# Example usage
def init_chats_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized successfully!")