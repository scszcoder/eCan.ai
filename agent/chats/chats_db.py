from sqlalchemy import create_engine, Column, String, Integer, Boolean, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

ECBOT_CHAT_DB = "ecbot_chat.db"
Base = declarative_base()

class DBVersion(Base):
    __tablename__ = 'db_version'
    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(32), nullable=False)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class Chat(Base):
    __tablename__ = 'chats'
    id = Column(String(64), primary_key=True)
    type = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    avatar = Column(String(255))
    lastMsg = Column(Text)
    lastMsgTime = Column(Integer)
    unread = Column(Integer, default=0)
    pinned = Column(Boolean, default=False)
    muted = Column(Boolean, default=False)
    ext = Column(JSON)
    members = relationship('Member', back_populates='chat', cascade='all, delete-orphan')
    messages = relationship('Message', back_populates='chat', cascade='all, delete-orphan')

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if deep:
            d['members'] = [m.to_dict() for m in self.members]
            d['messages'] = [msg.to_dict(deep=True) for msg in self.messages]
        return d

class Member(Base):
    __tablename__ = 'members'
    chatId = Column(String(64), ForeignKey('chats.id'), primary_key=True)
    userId = Column(String(64), primary_key=True)
    role = Column(String(32), nullable=False)
    name = Column(String(100), nullable=False)
    avatar = Column(String(255))
    status = Column(String(16))
    ext = Column(JSON)
    agentName = Column(String(100))
    chat = relationship('Chat', back_populates='members')

    def to_dict(self, deep=False):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

class Message(Base):
    __tablename__ = 'messages'
    id = Column(String(64), primary_key=True)
    chatId = Column(String(64), ForeignKey('chats.id'), nullable=False)
    role = Column(String(32), nullable=False)
    createAt = Column(Integer, nullable=False)
    content = Column(JSON, nullable=False)
    status = Column(String(16), nullable=False)
    senderId = Column(String(64))
    senderName = Column(String(100))
    time = Column(Integer)
    ext = Column(JSON)
    isRead = Column(Boolean, default=False)
    chat = relationship('Chat', back_populates='messages')
    attachments = relationship('Attachment', back_populates='message', cascade='all, delete-orphan')

    def to_dict(self, deep=False):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        if deep:
            d['attachments'] = [att.to_dict() for att in self.attachments]
        return d

class Attachment(Base):
    __tablename__ = 'attachments'
    uid = Column(String(64), primary_key=True)
    messageId = Column(String(64), ForeignKey('messages.id'), nullable=False)
    name = Column(String(255), nullable=False)
    status = Column(String(32), nullable=False)
    url = Column(String(512))
    size = Column(Integer)
    type = Column(String(64))
    ext = Column(JSON)
    message = relationship('Message', back_populates='attachments')

    def to_dict(self, deep=False):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

def get_engine(db_path: str = ECBOT_CHAT_DB):
    return create_engine(f'sqlite:///{db_path}', pool_pre_ping=True, connect_args={'check_same_thread': False})

def get_session_factory(db_path: str = ECBOT_CHAT_DB):
    engine = get_engine(db_path)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)