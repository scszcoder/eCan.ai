from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select
from .chats_db import Chat, Member, Message, Attachment, get_engine, get_session_factory, Base
from contextlib import contextmanager
import threading
import weakref
import os
import json
import logging


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
            self.SessionFactory = lambda: session
        elif engine is not None:
            self.SessionFactory = sessionmaker(bind=engine)
        elif db_path is not None:
            engine = get_engine(db_path)
            self.SessionFactory = get_session_factory(db_path)
            Base.metadata.create_all(engine)
        else:
            raise ValueError("Must provide db_path, engine or session")

    @contextmanager
    def session_scope(self):
        """事务管理器，确保线程安全"""
        session = self.SessionFactory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def initialize(cls, db_path: str = None, import_demo: bool = True) -> 'ChatService':
        """
        初始化聊天服务实例
        
        Args:
            db_path (str, optional): 数据库文件路径
            import_demo (bool, optional): 是否导入演示数据，默认 True
        Returns:
            ChatService: 聊天服务实例
        """
        service = cls(db_path=db_path)
        if import_demo and db_path is not None:
            demo_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'gui', 'ipc', 'w2p_handlers', 'chats_demo.json')
            if os.path.exists(demo_path):
                try:
                    with open(demo_path, 'r', encoding='utf-8') as f:
                        demo_chats = json.load(f)
                    if not service.query_chats_by_user():
                        service.import_demo_chats_from_json(demo_chats)
                except Exception as e:
                    print(f"[ChatService] 导入演示数据失败: {e}")
        return service

    def create_chat(
        self,
        members: list,              # 必须，成员列表
        name: str,                  # 必须，会话名称
        type: str = "user-agent",  # 可选，会话类型，默认 user-agent
        avatar: str = None,         # 可选，会话头像
        lastMsg: str = None,        # 可选，最后一条消息内容
        lastMsgTime: int = None,    # 可选，最后一条消息时间戳
        unread: int = 0,            # 可选，未读数，默认0
        pinned: bool = False,       # 可选，是否置顶，默认False
        muted: bool = False,        # 可选，是否静音，默认False
        ext: dict = None            # 可选，扩展字段，默认{}
    ) -> Dict[str, Any]:
        """
        创建会话及成员
        必须参数：members, name
        可选参数：type, avatar, lastMsg, lastMsgTime, unread, pinned, muted, ext
        """
        # 参数校验
        if not members or not name:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "Missing required fields: members, name"
            }
        # 简化可选参数补全
        type = "user-agent" if type is None else type
        avatar = "" if avatar is None else avatar
        lastMsg = "" if lastMsg is None else lastMsg
        lastMsgTime = 0 if lastMsgTime is None else lastMsgTime
        unread = 0 if unread is None else unread
        pinned = False if pinned is None else pinned
        muted = False if muted is None else muted
        ext = {} if ext is None else ext
        with self.session_scope() as session:
            try:
                input_member_ids = set(str(m['userId']) for m in members)
                candidate_chats = session.query(Chat).filter(Chat.type == type).all()
                for chat in candidate_chats:
                    db_member_ids = set(str(m.userId) for m in chat.members)
                    if db_member_ids == input_member_ids:
                        return {
                            "success": False,
                            "id": chat.id,
                            "data": chat.to_dict(deep=True),
                            "error": f"Chat with members {sorted(input_member_ids)} already exists"
                        }
                # 生成有规律的 chat_id
                max_id = 0
                for c in session.query(Chat).all():
                    if c.id and c.id.startswith('chat-'):
                        try:
                            num = int(c.id[5:])
                            if num > max_id:
                                max_id = num
                        except Exception:
                            continue
                chat_id = f"chat-{max_id+1:06d}"
                chat = Chat(
                    id=chat_id,
                    type=type,
                    name=name,
                    avatar=avatar,
                    lastMsg=lastMsg,
                    lastMsgTime=lastMsgTime,
                    unread=unread,
                    pinned=pinned,
                    muted=muted,
                    ext=ext
                )
                for m in members:
                    member = Member(
                        chatId=chat.id,
                        userId=m["userId"],
                        role=m.get("role", "user"),
                        name=m.get("name", m["userId"]),
                        avatar=m.get("avatar"),
                        status=m.get("status"),
                        ext=m.get("ext"),
                        agentName=m.get("agentName")
                    )
                    chat.members.append(member)
                session.add(chat)
                session.flush()
                return {
                    "success": True,
                    "id": chat.id,
                    "data": chat.to_dict(deep=True),
                    "error": None
                }
            except Exception as e:
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": str(e)
                }

    def add_message(
        self,
        chatId: str,
        role: str,
        content: Any,
        senderId: str,
        createAt: int,
        id: str = None,
        status: str = "complete",
        senderName: str = None,
        time: int = None,
        ext: dict = None,
        attachments: list = None
    ) -> Dict[str, Any]:
        """向会话添加消息及附件，必传 chat_id、role、content、senderId、createAt，返回标准化结构"""
        if not chatId or not role or content is None or not senderId or not createAt:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "Missing required fields: chatId, role, content, senderId, createAt"
            }
        # 简化可选参数补全
        id = f"msg-{createAt}" if id is None else id
        status = "complete" if status is None else status
        senderName = "" if senderName is None else senderName
        time = createAt if time is None else time
        ext = {} if ext is None else ext
        attachments = [] if attachments is None else attachments
        with self.session_scope() as session:
            chat = session.get(Chat, chatId)
            if not chat:
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": f"Chat {chatId} not found"
                }
            message = Message(
                id=id,
                chatId=chat.id,
                role=role,
                createAt=createAt,
                content=content,
                status=status,
                senderId=senderId,
                senderName=senderName,
                time=time,
                ext=ext,
                isRead=False
            )
            for att in attachments:
                attachment_obj = Attachment(
                    uid=att["uid"],
                    messageId=message.id,
                    name=att.get("name", "file"),
                    status=att.get("status", "done"),
                    url=att.get("url"),
                    size=att.get("size"),
                    type=att.get("type"),
                    ext=att.get("ext")
                )
                message.attachments.append(attachment_obj)
            chat.messages.append(message)
            # 新增消息未读，chat.unread +1
            chat.unread = (chat.unread or 0) + 1
            session.add(message)
            session.flush()
            return {
                "success": True,
                "id": message.id,
                "data": message.to_dict(deep=True),
                "error": None
            }

    def query_chats_by_user(self, userId: Optional[str] = None, deep: bool = False) -> Dict[str, Any]:
        """
        查询用户参与的所有会话（含成员，默认不含消息），如需消息请 deep=True。
        user_id 不能为空，否则返回错误。
        返回结构与其他接口保持一致。
        """
        if not userId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "userId is required"
            }
        with self.session_scope() as session:
            stmt = select(Chat).join(Member).where(Member.userId == userId)
            chats = session.execute(stmt).scalars().all()
            return {
                "success": True,
                "id": None,
                "data": [chat.to_dict(deep=deep) for chat in chats],
                "error": None
            }

    def import_demo_chats_from_json(self, demo_chats: List[Dict[str, Any]]) -> List[str]:
        """
        解析 json 数据并写入数据库表
        """
        imported_ids = []
        for ui_chat in demo_chats:
            try:
                self.create_chat(
                    members=ui_chat.get("members", []),
                    name=ui_chat.get("name"),
                    type=ui_chat.get("type"),
                    avatar=ui_chat.get("avatar"),
                    lastMsg=ui_chat.get("lastMsg"),
                    lastMsgTime=ui_chat.get("lastMsgTime"),
                    unread=ui_chat.get("unread", 0),
                    pinned=ui_chat.get("pinned", False),
                    muted=ui_chat.get("muted", False),
                    ext=ui_chat.get("ext", {})
                )
                for msg in ui_chat.get("messages", []):
                    self.add_message(
                        chat_id=msg.get("chatId", ui_chat["id"]),
                        role=msg["role"],
                        content=msg["content"],
                        senderId=msg.get("senderId", msg["role"]),
                        createAt=msg["createAt"],
                        id=msg.get("id"),
                        status=msg.get("status", "complete"),
                        senderName=msg.get("senderName"),
                        time=msg.get("time"),
                        ext=msg.get("ext"),
                        attachments=msg.get("attachments", [])
                    )
                imported_ids.append(ui_chat["id"])
            except Exception as e:
                print(f"Error importing chat: {str(e)}")
                continue
        return imported_ids

    def query_messages_by_chat(
        self,
        chatId: str,
        limit: int = 20,
        offset: int = 0,
        reverse: bool = False
    ) -> Dict[str, Any]:
        """
        查询指定 chatId 的消息列表，支持翻页。
        参数：
            chatId: 必需，会话ID
            limit: 可选，返回消息数量，默认20
            offset: 可选，起始偏移，默认0
            reverse: 可选，是否倒序，默认False
        返回：标准结构，data为消息列表
        """
        if not chatId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "chatId is required"
            }
        with self.session_scope() as session:
            chat = session.get(Chat, chatId)
            if not chat:
                return {
                    "success": False,
                    "id": chatId,
                    "data": None,
                    "error": f"Chat {chatId} not found"
                }
            query = session.query(Message).filter(Message.chatId == chatId)
            if reverse:
                query = query.order_by(Message.createAt.desc())
            else:
                query = query.order_by(Message.createAt.asc())
            messages = query.offset(offset).limit(limit).all()
            return {
                "success": True,
                "id": chatId,
                "data": [msg.to_dict(deep=True) for msg in messages],
                "error": None
            }

    def delete_chat(self, chatId: str) -> Dict[str, Any]:
        """
        删除指定 chatId 的会话及其相关的成员、消息、附件等数据。
        参数：chatId（必需）
        返回：标准结构
        """
        if not chatId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "chatId is required"
            }
        with self.session_scope() as session:
            chat = session.get(Chat, chatId)
            if not chat:
                return {
                    "success": False,
                    "id": chatId,
                    "data": None,
                    "error": f"Chat {chatId} not found"
                }
            session.delete(chat)
            session.flush()
            return {
                "success": True,
                "id": chatId,
                "data": None,
                "error": None
            }

    def mark_message_as_read(self, messageIds: list, userId: str) -> Dict[str, Any]:
        """
        批量将指定消息标记为已读，并同步更新 chat 的未读数。
        参数：messageIds（必需，list），userId（必需）
        返回：标准结构，data为已处理的 message_id 列表
        """
        if not messageIds or not userId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "message_ids and user_id are required"
            }
        updated_ids = []
        with self.session_scope() as session:
            for message_id in messageIds:
                message = session.get(Message, message_id)
                if not message:
                    continue
                if not message.isRead:
                    message.isRead = True
                    # 同步更新 chat 的未读数
                    chat = session.get(Chat, message.chatId)
                    if chat and chat.unread > 0:
                        chat.unread = max(0, chat.unread - 1)
                updated_ids.append(message_id)
            session.flush()
            return {
                "success": True,
                "id": None,
                "data": updated_ids,
                "error": None
            } 