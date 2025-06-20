from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from sqlalchemy.orm import Session, sessionmaker
from .chats_db import (
    ChatUser, Conversation, Message, ChatSession,
    ConversationMember, Attachment, MessageRead,
    MessageType, MessageStatus, SessionLocal, get_engine, get_session_factory, Base
)
from contextlib import contextmanager
import threading
from functools import wraps
import weakref


class SingletonMeta(type):
    """单例元类，提供线程安全的单例实现"""
    _instances = weakref.WeakValueDictionary()
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        # 使用数据库路径作为实例的唯一标识
        db_path = kwargs.get('db_path')
        engine = kwargs.get('engine')
        session = kwargs.get('session')
        
        # 生成唯一键
        if db_path:
            key = f"db_path_{db_path}"
        elif engine:
            key = f"engine_{id(engine)}"
        elif session:
            key = f"session_{id(session)}"
        else:
            key = "default"
            
        if key not in cls._instances:
            with cls._lock:
                if key not in cls._instances:
                    instance = super().__call__(*args, **kwargs)
                    cls._instances[key] = instance
        return cls._instances[key]


class ChatService(metaclass=SingletonMeta):
    """聊天系统服务类，提供所有聊天相关的操作接口"""

    def __init__(self, db_path: str = None, engine=None, session=None):
        """
        初始化聊天服务
        
        Args:
            db_path (str, optional): 数据库文件路径
            engine: SQLAlchemy引擎实例
            session: SQLAlchemy会话实例
        """
        if session is not None:
            self._session = session
        elif engine is not None:
            Session = sessionmaker(bind=engine)
            self._session = Session()
        elif db_path is not None:
            engine = get_engine(db_path)
            Session = get_session_factory(db_path)
            self._session = Session()
            # 确保数据库表已创建
            Base.metadata.create_all(engine)
        else:
            raise ValueError("Must provide db_path, engine or session")
        self._initialized = True
        self._lock = threading.Lock()

    @classmethod
    def initialize(cls, db_path: str = None) -> 'ChatService':
        """
        初始化聊天服务实例
        
        Args:
            db_path (str, optional): 数据库文件路径
            
        Returns:
            ChatService: 聊天服务实例
        """
        return cls(db_path=db_path)

    def _get_session(self) -> Session:
        """获取数据库会话，确保线程安全"""
        if not self._initialized or self._session is None:
            with self._lock:
                if not self._initialized or self._session is None:
                    try:
                        self._session = SessionLocal()
                        self._initialized = True
                    except Exception as e:
                        self._session = None
                        self._initialized = False
                        raise RuntimeError(f"Failed to initialize database session: {str(e)}")
        if self._session is None:
            raise RuntimeError("Database session is not initialized")
        return self._session

    def _close_session(self):
        """关闭数据库会话"""
        if self._session is not None:
            with self._lock:
                if self._session is not None:
                    try:
                        self._session.close()
                    except Exception:
                        pass
                    finally:
                        self._session = None
                        self._initialized = False

    @contextmanager
    def transaction(self):
        """事务管理器，确保线程安全"""
        session = self._get_session()
        if session is None:
            raise RuntimeError("Database session is not initialized")
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e

    def __del__(self):
        """清理资源"""
        self._close_session()

    def _ensure_session(self):
        """确保session已初始化"""
        if not self._initialized or self._session is None:
            self._initialize()
        if self._session is None:
            raise RuntimeError("Failed to initialize database session")

    # 用户相关操作
    def create_user(self, username: str, display_name: str, avatar_url: Optional[str] = None) -> ChatUser:
        """创建新用户"""
        self._ensure_session()
        with self.transaction() as session:
            user = ChatUser.create(session,
                username=username,
                display_name=display_name,
                avatar_url=avatar_url
            )
            session.refresh(user)
            return user

    def get_user(self, user_id: int) -> Optional[ChatUser]:
        """通过ID获取用户"""
        self._ensure_session()
        return ChatUser.get_by_id(self._get_session(), user_id)

    def get_user_by_username(self, username: str) -> Optional[ChatUser]:
        """通过用户名获取用户"""
        self._ensure_session()
        return ChatUser.get_by_username(self._get_session(), username)

    def update_user(self, user_id: int, **kwargs) -> Optional[ChatUser]:
        """更新用户信息"""
        self._ensure_session()
        user = self.get_user(user_id)
        if user:
            with self.transaction() as session:
                updated_user = user.update(session, **kwargs)
                session.refresh(updated_user)
                return updated_user
        return None

    def delete_user(self, user_id: int) -> bool:
        """删除用户"""
        self._ensure_session()
        user = self.get_user(user_id)
        if user:
            with self.transaction() as session:
                return user.delete(session)
        return False

    # 会话相关操作
    def create_conversation(self, name: str, is_group: bool = False,
                          description: Optional[str] = None) -> Conversation:
        """创建新会话"""
        self._ensure_session()
        with self.transaction() as session:
            conversation = Conversation.create(session,
                name=name,
                is_group=is_group,
                description=description
            )
            session.refresh(conversation)
            return conversation

    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """获取会话信息"""
        self._ensure_session()
        return Conversation.get_by_id(self._get_session(), conversation_id)

    def get_user_conversations(self, user_id: int) -> List[Conversation]:
        """获取用户的所有会话"""
        self._ensure_session()
        return Conversation.get_user_conversations(self._get_session(), user_id)

    def add_user_to_conversation(self, conversation_id: int, user_id: int,
                               role: str = 'member') -> Optional[ConversationMember]:
        """添加用户到会话"""
        self._ensure_session()
        with self.transaction() as session:
            member = ConversationMember.create(session,
                conversation_id=conversation_id,
                user_id=user_id,
                role=role
            )
            session.refresh(member)
            return member

    def remove_user_from_conversation(self, conversation_id: int, user_id: int) -> bool:
        """从会话中移除用户"""
        self._ensure_session()
        member = self._get_session().query(ConversationMember).filter(
            ConversationMember.conversation_id == conversation_id,
            ConversationMember.user_id == user_id
        ).first()
        if member:
            with self.transaction() as session:
                return member.delete(session)
        return False

    # 消息相关操作
    def send_message(self, conversation_id: int, sender_id: int, content: str,
                    message_type: MessageType = MessageType.TEXT,
                    parent_id: Optional[int] = None) -> Message:
        """发送消息"""
        with self._lock:
            with self.transaction() as session:
                return Message.create(session,
                    conversation_id=conversation_id,
                    sender_id=sender_id,
                    content=content,
                    message_type=message_type,
                    parent_id=parent_id
                )

    def get_conversation_messages(self, conversation_id: int, limit: int = 50,
                                offset: int = 0) -> List[Message]:
        """获取会话消息"""
        with self._lock:
            return Message.get_conversation_messages(
                self._get_session(),
                conversation_id=conversation_id,
                limit=limit,
                offset=offset
            )

    def edit_message(self, message_id: int, content: str) -> Optional[Message]:
        """编辑消息"""
        with self._lock:
            message = Message.get_by_id(self._get_session(), message_id)
            if message and message.is_editable:
                with self.transaction() as session:
                    return message.update(session, content=content, is_edited=True)
            return None

    def delete_message(self, message_id: int) -> bool:
        """删除消息"""
        with self._lock:
            message = Message.get_by_id(self._get_session(), message_id)
            if message:
                with self.transaction() as session:
                    return message.delete(session)
            return False

    # 附件相关操作
    def add_attachment(self, message_id: int, file_name: str, file_size: int,
                      mime_type: str, file_path: str) -> Attachment:
        """添加附件"""
        with self._lock:
            with self.transaction() as session:
                return Attachment.create(session,
                    message_id=message_id,
                    file_name=file_name,
                    file_size=file_size,
                    mime_type=mime_type,
                    file_path=file_path
                )

    def get_message_attachments(self, message_id: int) -> list:
        session = self._get_session()
        return session.query(Attachment).filter(Attachment.message_id == message_id).all()

    # 消息状态相关操作
    def update_message_status(self, message_id: int,
                            status: MessageStatus) -> Optional[Message]:
        """更新消息状态"""
        with self._lock:
            message = Message.get_by_id(self._get_session(), message_id)
            if message:
                with self.transaction() as session:
                    return message.update(session, status=status)
            return None

    def mark_message_as_read(self, message_id: int, user_id: int):
        with self._lock:
            with self.transaction() as session:
                read = session.query(MessageRead).filter_by(message_id=message_id, user_id=user_id).first()
                if not read:
                    read = MessageRead(
                        message_id=message_id,
                        user_id=user_id,
                        read_at=datetime.now()
                    )
                    session.add(read)
                    session.commit()
                return read

    def get_unread_messages(self, user_id: int, conversation_id: int) -> List[Message]:
        """获取未读消息"""
        with self._lock:
            return self._get_session().query(Message).filter(
                Message.conversation_id == conversation_id,
                ~Message.id.in_(
                    self._get_session().query(MessageRead.message_id)
                    .filter(MessageRead.user_id == user_id)
                )
            ).all()

    # 会话状态相关操作
    def get_active_session(self, conversation_id: int) -> Optional[ChatSession]:
        """获取活跃会话"""
        with self._lock:
            conversation = self.get_conversation(conversation_id)
            if conversation:
                return conversation.get_active_session(self._get_session())
            return None

    def end_session(self, session_id: int):
        session = self._get_session()
        chat_session = session.get(ChatSession, session_id)
        if chat_session and not chat_session.ended_at:
            chat_session.ended_at = datetime.now()
            session.commit()
        return None 