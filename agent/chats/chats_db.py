from sqlalchemy import (
    create_engine, Column, Integer, String, Boolean, ForeignKey, Text,
    DateTime, func, Index, event, LargeBinary, Enum, select, UniqueConstraint
)
from sqlalchemy.orm import (
    relationship, sessionmaker, scoped_session, backref, remote,
    declarative_base, Session
)
from sqlalchemy.orm.properties import RelationshipProperty
from datetime import datetime, timedelta
from enum import Enum as PyEnum
import os
from typing import List, Optional, Dict, Any
import json
import threading
import time
from .models import Base, DBVersion
from .entity import Entity
from .db_migration import DBMigration

# Constants
MAX_TOTAL_MESSAGES = 10000
MAX_MESSAGES_PER_CONVERSATION = 1000
SESSION_TIMEOUT_MINUTES = 15
EDIT_WINDOW_MINUTES = 5
MESSAGE_CLEANUP_BATCH_SIZE = 100

# Default database path
DEFAULT_DB_PATH = 'chat_app.db'

def get_engine(db_path: str = None):
    """
    获取数据库引擎
    
    Args:
        db_path (str, optional): 数据库文件路径. 如果为None，则使用环境变量DATABASE_URL或默认路径.
    
    Returns:
        Engine: SQLAlchemy数据库引擎实例
    """
    if db_path is None:
        db_path = os.getenv('DATABASE_URL', f'sqlite:///{DEFAULT_DB_PATH}')
    elif not db_path.startswith('sqlite:///'):
        db_path = f'sqlite:///{db_path}'
        
    return create_engine(
        db_path,
        pool_pre_ping=True,
        connect_args={'check_same_thread': False}
    )

def get_session_factory(db_path: str = None):
    """
    获取会话工厂
    
    Args:
        db_path (str, optional): 数据库文件路径
    
    Returns:
        sessionmaker: SQLAlchemy会话工厂
    """
    engine = get_engine(db_path)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建会话工厂
SessionLocal = get_session_factory()

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

class ChatUser(Entity):
    __tablename__ = 'chat_users'

    username = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100))
    avatar_url = Column(String(255))
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime)

    # Relationships
    sent_messages = relationship("Message", back_populates="sender", lazy="dynamic")
    message_reads = relationship("MessageRead", back_populates="user", lazy="dynamic")
    memberships = relationship("ConversationMember", back_populates="user", lazy="dynamic")

    @classmethod
    def get_by_username(cls, session, username: str) -> Optional['ChatUser']:
        if not session:
            raise ValueError("Database session is required")
        stmt = select(cls).where(cls.username == username)
        return session.execute(stmt).scalar_one_or_none()

    def update_last_seen(self, session):
        if not session:
            raise ValueError("Database session is required")
        self.last_seen = datetime.utcnow()
        session.commit()

class Conversation(Entity):
    __tablename__ = 'conversations'

    name = Column(String(100))
    is_group = Column(Boolean, default=False)
    avatar_url = Column(String(255))
    description = Column(Text)

    # Relationships
    members = relationship("ConversationMember", back_populates="conversation", cascade="all, delete-orphan", lazy="dynamic")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", lazy="dynamic")
    sessions = relationship("ChatSession", back_populates="conversation", cascade="all, delete-orphan", lazy="dynamic")

    def get_active_session(self, session) -> 'ChatSession':
        if not session:
            raise ValueError("Database session is required")
        stmt = select(ChatSession).where(
            ChatSession.conversation_id == self.id,
            ChatSession.ended_at.is_(None)
        )
        active_session = session.execute(stmt).scalar_one_or_none()

        if not active_session:
            active_session = ChatSession.create(session, conversation_id=self.id)

        return active_session

    @classmethod
    def get_user_conversations(cls, session, user_id: int) -> List['Conversation']:
        if not session:
            raise ValueError("Database session is required")
        stmt = select(cls).join(ConversationMember).where(
            ConversationMember.user_id == user_id
        )
        return session.execute(stmt).scalars().all()

class ChatSession(Entity):
    __tablename__ = 'chat_sessions'

    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    ended_at = Column(DateTime)
    end_time = Column(DateTime)

    # Relationships
    conversation = relationship("Conversation", back_populates="sessions")
    messages = relationship("Message", back_populates="session", lazy="dynamic")

    def end_session(self, session):
        if not session:
            raise ValueError("Database session is required")
        self.ended_at = datetime.utcnow()
        self.end_time = self.ended_at
        session.commit()
        return None

class ConversationMember(Entity):
    __tablename__ = 'conversation_members'
    __table_args__ = (
        Index('idx_conversation_member', 'conversation_id', 'user_id', unique=True),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('chat_users.id'), nullable=False)
    role = Column(String(20), default='member')
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_at = Column(DateTime)

    # Relationships
    user = relationship("ChatUser", back_populates="memberships")
    conversation = relationship("Conversation", back_populates="members")

    def update_last_read(self, session):
        if not session:
            raise ValueError("Database session is required")
        self.last_read_at = datetime.utcnow()
        session.commit()

class Message(Entity):
    __tablename__ = 'messages'
    __table_args__ = (
        Index('idx_conversation_created', 'conversation_id', 'created_at'),
    )

    conversation_id = Column(Integer, ForeignKey('conversations.id'), nullable=False, index=True)
    session_id = Column(Integer, ForeignKey('chat_sessions.id'), nullable=True)
    sender_id = Column(Integer, ForeignKey('chat_users.id'), nullable=False)
    parent_id = Column(Integer, ForeignKey('messages.id'), nullable=True)
    content = Column(Text)
    message_type = Column(Enum(MessageType), default=MessageType.TEXT, nullable=False)
    status = Column(Enum(MessageStatus), default=MessageStatus.SENDING, nullable=False)
    is_edited = Column(Boolean, default=False)
    is_retracted = Column(Boolean, default=False)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    metadata_ = Column('metadata', Text)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("ChatUser", back_populates="sent_messages")
    parent = relationship(
        "Message",
        backref=backref("replies", lazy="dynamic"),
        primaryjoin="Message.parent_id == remote(Message.id)",
        lazy="joined"
    )
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan", lazy="dynamic")
    reads = relationship("MessageRead", back_populates="message", cascade="all, delete-orphan", lazy="dynamic")
    session = relationship("ChatSession", back_populates="messages")

    @property
    def is_editable(self) -> bool:
        return (datetime.utcnow() - self.created_at) < timedelta(minutes=EDIT_WINDOW_MINUTES)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data['attachments'] = [a.to_dict() for a in self.attachments]
        return data

    @classmethod
    def get_conversation_messages(cls, session, conversation_id: int, limit: int = 50, offset: int = 0) -> List['Message']:
        if not session:
            raise ValueError("Database session is required")
        stmt = select(cls).where(
            cls.conversation_id == conversation_id
        ).order_by(cls.created_at.desc()).offset(offset).limit(limit)
        return session.execute(stmt).scalars().all()

class Attachment(Entity):
    __tablename__ = 'attachments'

    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_size = Column(Integer)
    mime_type = Column(String(100))
    file_path = Column(String(512))
    thumbnail_path = Column(String(512))
    width = Column(Integer)
    height = Column(Integer)
    duration = Column(Integer)

    # Relationships
    message = relationship("Message", back_populates="attachments")

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'file_name': self.file_name,
            'file_size': self.file_size,
            'mime_type': self.mime_type,
            'file_path': self.file_path,
            'thumbnail_path': self.thumbnail_path,
            'width': self.width,
            'height': self.height,
            'duration': self.duration
        })
        return data

class MessageRead(Entity):
    __tablename__ = 'message_reads'
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey('messages.id'), nullable=False)
    user_id = Column(Integer, ForeignKey('chat_users.id'), nullable=False)
    read_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (
        UniqueConstraint('message_id', 'user_id', name='uix_message_user'),
    )

    # Relationships
    message = relationship("Message", back_populates="reads")
    user = relationship("ChatUser", back_populates="message_reads")

# Event listeners
# @event.listens_for(Message, 'after_insert')
# def check_message_limit(mapper, connection, target):
#     session = db_session()
#     ...

@event.listens_for(Message, 'before_insert')
def set_message_session(mapper, connection, target):
    if not target.session_id:
        # 使用当前连接创建会话
        session = Session(bind=connection)
        chat_session = ChatSession(
            conversation_id=target.conversation_id,
            started_at=datetime.now()
        )
        session.add(chat_session)
        session.flush()
        target.session_id = chat_session.id

def init_chats_db(db_path: str = None, target_version: str = "1.0.0"):
    """
    初始化数据库，并自动升级到目标版本
    
    Args:
        db_path (str, optional): 数据库文件路径
        target_version (str, optional): 目标数据库版本，默认1.0.0
    
    Returns:
        Engine: SQLAlchemy数据库引擎实例
    """
    engine = get_engine(db_path)
    # 创建所有表（如果不存在）
    Base.metadata.create_all(engine)
    # 初始化版本表
    Session = sessionmaker(bind=engine)
    session = Session()
    if not session.query(DBVersion).first():
        session.add(DBVersion(version="1.0.0", description="初始化版本"))
        session.commit()
    session.close()
    # 自动升级到目标版本
    if target_version and target_version != "1.0.0":
        migrator = DBMigration(db_path)
        migrator.upgrade_to_version(target_version, description=f"自动升级到{target_version}")
    return engine

# 在模块加载时初始化数据库
init_chats_db()