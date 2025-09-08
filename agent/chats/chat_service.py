from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select

from app_context import AppContext
from .chats_db import Chat, Member, Message, Attachment, get_engine, get_session_factory, Base, ChatNotification
from contextlib import contextmanager
import threading
import weakref
import os
import json
import uuid
import time
from .chat_utils import ContentSchema
from utils.logger_helper import logger_helper as logger


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
            # 新增：自动插入初始 db_version 记录并执行数据库升级
            try:
                from agent.chats.db_migration import DBMigration
                migrator = DBMigration(db_path)
                # 确保有 db_version 表和初始记录
                migrator.get_current_version()
                migrator.upgrade_to_version('2.0.0', description='自动升级到2.0.0，添加chat_notification表')
            except Exception as e:
                logger.error(f"[DBMigration] 数据库升级失败: {e}")
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
                    logger.error(f"[ChatService] 导入演示数据失败: {e}")
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
        logger.debug(f"chat_service.add_message: {chatId}, {role}, {content}, {senderId}, {createAt}, {id}, {status}, {senderName}, {time}, {ext}, {attachments}")
        """向会话添加消息及附件，必传 chat_id、role、content、senderId、createAt，返回标准化结构"""
        if not chatId or not role or content is None or not senderId or not createAt:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "Missing required fields: chatId, role, content, senderId, createAt"
            }
        # 简化可选参数补全
        id = str(uuid.uuid4()) if id is None else id
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
            # 更新chat.lastMsg和lastMsgTime
            chat.lastMsg = json.dumps(content, ensure_ascii=False)
            chat.lastMsgTime = createAt
            # 新增消息未读，chat.unread +1
            chat.unread = (chat.unread or 0) + 1
            logger.debug(f"chat.unread: {message}")
            chat.messages.append(message)
            session.add(message)
            session.flush()
            return {
                "success": True,
                "id": message.id,
                "data": message.to_dict(deep=True),
                "error": None
            }

    # 新增辅助方法，支持各种内容类型
    def add_text_message(self, chatId: str, role: str, text: str, senderId: str, createAt: int = None, **kwargs):
        """添加纯文本消息的便捷方法"""
        content = ContentSchema.create_text(text)
        logger.debug(f"chat_service.add_text_message: {chatId}, {role}, {text}, {content}, {senderId}, {createAt}, {kwargs}")
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=content, 
            senderId=senderId, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )

    def add_form_message(self, chatId: str, role: str, form: dict, senderId: str = None, createAt: int = None, **kwargs):
        """添加表单消息的便捷方法，直接使用 form 字典生成 content，不做字段解析"""
        content = {"type": "form", "form": form}
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=content, 
            senderId=senderId or role, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )

    def add_code_message(self, chatId: str, role: str, code: str, language: str = "python", 
                        senderId: str = None, createAt: int = None, **kwargs):
        """添加代码消息的便捷方法"""
        content = ContentSchema.create_code(code, language)
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=content, 
            senderId=senderId or role, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )

    def add_system_message(self, chatId: str, text: str, level: str = "info", 
                          senderId: str = "system", createAt: int = None, **kwargs):
        """添加系统消息的便捷方法"""
        content = ContentSchema.create_system(text, level)
        return self.add_message(
            chatId=chatId, 
            role="system", 
            content=content, 
            senderId=senderId, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )
        
    def add_notification_message(self, chatId: str, notification: dict = "",
                               senderId: str = "system", createAt: int = None, **kwargs):

        title = notification.get('title', 'Notification')
        logger.debug(f"Final notification params - title: '{title}', notification: '{notification}'")
            
        notification_content = ContentSchema.create_notification(title, notification)
        logger.debug(f"Created notification content: {notification_content}")

        # 添加消息到数据库
        result = self.add_message(
            chatId=chatId,
            role="system",
            content=notification_content,
            senderId=senderId,
            createAt=createAt or int(time.time()*1000),
            **kwargs
        )
        logger.debug(f"add_notification_message result: {result}")
        return result

    def add_card_message(self, chatId: str, role: str, title: str, content: str, actions: list = None,
                        senderId: str = None, createAt: int = None, **kwargs):
        """添加卡片消息的便捷方法"""
        card_content = ContentSchema.create_card(title, content, actions)
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=card_content, 
            senderId=senderId or role, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )
        
    def add_markdown_message(self, chatId: str, role: str, markdown: str, 
                           senderId: str = None, createAt: int = None, **kwargs):
        """添加Markdown消息的便捷方法"""
        md_content = ContentSchema.create_markdown(markdown)
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=md_content, 
            senderId=senderId or role, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )
        
    def add_table_message(self, chatId: str, role: str, headers: list, rows: list, 
                         senderId: str = None, createAt: int = None, **kwargs):
        """添加表格消息的便捷方法"""
        table_content = ContentSchema.create_table(headers, rows)
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=table_content, 
            senderId=senderId or role, 
            createAt=createAt or int(time.time()*1000), 
            **kwargs
        )

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
                logger.error(f"Error importing chat: {str(e)}")
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

    def get_chat_by_id(
        self, 
        chat_id: str, 
        deep: bool = False
    ) -> Dict[str, Any]:
        """
        根据 chatId 查询会话详情
        
        Args:
            chat_id: 会话ID
            deep: 是否深度查询（包含成员和消息）
            
        Returns:
            标准返回结构，data为会话详情
        """
        if not chat_id:
            return {
                "success": False,
                "data": None,
                "error": "chat_id is required"
            }
            
        with self.session_scope() as session:
            try:
                chat = session.query(Chat).filter(Chat.id == chat_id).first()
                if not chat:
                    return {
                        "success": False,
                        "data": None,
                        "error": f"Chat with id {chat_id} not found"
                    }
                
                return {
                    "success": True,
                    "data": chat.to_dict(deep=deep),
                    "error": None
                }
                
            except Exception as e:
                return {
                    "success": False,
                    "data": None,
                    "error": str(e)
                }

    def submit_form(self, chatId: str, messageId: str, formId: str, formData: dict) -> Dict[str, Any]:
        """
        处理表单提交：将 formData 更新到指定消息的 content['form'] 字段（整体替换），其余内容保持不变
        """
        if not chatId or not messageId or not formId or formData is None:
            return {
                "success": False,
                "error": "chatId, messageId, formId, formData 必填",
                "data": None
            }
        with self.session_scope() as session:
            message = session.get(Message, messageId)
            if not message or message.chatId != chatId:
                return {
                    "success": False,
                    "error": f"Message {messageId} not found in chat {chatId}",
                    "data": None
                }
            # 只处理 type=form 的消息
            import copy
            content = copy.deepcopy(message.content) if message.content else {}
            if not isinstance(content, dict) or content.get('type') != 'form':
                return {
                    "success": False,
                    "error": "消息类型不是表单(form)",
                    "data": None
                }
            # 替换 content['form']
            content['form'] = formData
            message.content = copy.deepcopy(content)  # 关键：赋值新对象，确保 SQLAlchemy 检测到变更
            session.flush()
            return {
                "success": True,
                "data": message.to_dict(deep=True),
                "error": None
            }

    def delete_message(self, chatId: str, messageId: str) -> Dict[str, Any]:
        """
        删除指定 chatId 下的 messageId 消息及其附件。
        参数：chatId, messageId（均必需）
        返回：标准结构
        """
        if not chatId or not messageId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "chatId and messageId are required"
            }
        with self.session_scope() as session:
            message = session.get(Message, messageId)
            if not message or message.chatId != chatId:
                return {
                    "success": False,
                    "id": messageId,
                    "data": None,
                    "error": f"Message {messageId} not found in chat {chatId}"
                }
            # 删除消息（附件自动级联删除）
            session.delete(message)
            session.flush()
            return {
                "success": True,
                "id": messageId,
                "data": None,
                "error": None
            }

    def add_chat_notification(self, chatId: str, content: dict, timestamp: int, isRead: bool = False, uid: str = None) -> dict:
        """
        保存一条 chat_notification 记录。
        """
        if not chatId or content is None or timestamp is None:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "chatId, content, timestamp are required"
            }
        uid = uid or str(uuid.uuid4())
        with self.session_scope() as session:
            chat = session.get(Chat, chatId)
            if not chat:
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": f"Chat {chatId} not found"
                }
            notif = ChatNotification(
                uid=uid,
                chatId=chatId,
                content=content,
                timestamp=timestamp,
                isRead=isRead
            )
            session.add(notif)
            session.flush()
            return {
                "success": True,
                "id": notif.uid,
                "data": notif.to_dict(),
                "error": None
            }

    def query_chat_notifications(self, chatId: str, limit: int = 20, offset: int = 0, reverse: bool = False) -> dict:
        """
        按 chatId 查询 chat_notification，支持翻页。
        """
        if not chatId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "chatId is required"
            }
        with self.session_scope() as session:
            query = session.query(ChatNotification).filter(ChatNotification.chatId == chatId)
            if reverse:
                query = query.order_by(ChatNotification.timestamp.desc())
            else:
                query = query.order_by(ChatNotification.timestamp.asc())
            chat_notifications = query.offset(offset).limit(limit).all()
            return {
                "success": True,
                "id": chatId,
                "data": [n.to_dict() for n in chat_notifications],
                "error": None
            }

    def set_chat_unread(self, chatId: str, unread: int = 0) -> Dict[str, Any]:
        """
        设置指定 chat 的未读数为指定值（通常为 0）。
        参数：chatId（必需），unread（可选，默认0）
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
            chat.unread = unread
            session.flush()
            return {
                "success": True,
                "id": chatId,
                "data": chat.to_dict(),
                "error": None
            }

    def dispatch_add_message(self, chatId, args: dict) -> dict:
        """根据 content.type 分发到 chat_service 的不同 add_xxx_message 方法"""
        content = args.get('content')
        chatId = chatId if chatId is not None else args.get('chatId')
        role = args.get('role')
        senderId = args.get('senderId')
        createAt = args.get('createAt')
        messageId = args.get('id')
        status = args.get('status')
        senderName = args.get('senderName')
        time_ = args.get('time')
        ext = args.get('ext')
        attachments = args.get('attachments')

        # Ensure createAt is an integer, not a list
        if isinstance(createAt, list) and createAt:
            createAt = createAt[0]
        if isinstance(senderId, list) and senderId:
            senderId = senderId[0]
        if isinstance(senderName, list) and senderName:
            senderName = senderName[0]
        if isinstance(status, list) and status:
            status = status[0]

        # 类型分发
        if isinstance(content, dict):
            msg_type = content.get('type')
            if msg_type == 'text':
                return self.add_text_message(
                    chatId=chatId, role=role, text=content.get('text', ''), senderId=senderId, createAt=createAt,
                    id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif msg_type == 'form':
                form = content.get('form', {})
                return self.add_form_message(
                    chatId=chatId, role=role, form=form, senderId=senderId,
                    createAt=createAt, id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif msg_type == 'code':
                code = content.get('code', {})
                return self.add_code_message(
                    chatId=chatId, role=role, code=code.get('value', ''), language=code.get('lang', 'python'),
                    senderId=senderId, createAt=createAt, id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif msg_type == 'system':
                system = content.get('system', {})
                return self.add_system_message(
                    chatId=chatId, text=system.get('text', ''), level=system.get('level', 'info'),
                    senderId=senderId, createAt=createAt, id=messageId, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'notification':
                notification = content.get('notification', {})
                return self.add_notification_message(
                    chatId=chatId,
                    notification=notification,
                    senderId=senderId, createAt=createAt, id=messageId, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'card':
                card = content.get('card', {})
                return self.add_card_message(
                    chatId=chatId, role=role, title=card.get('title', ''), content=card.get('content', ''),
                    actions=card.get('actions', []), senderId=senderId, createAt=createAt, id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif msg_type == 'markdown':
                return self.add_markdown_message(
                    chatId=chatId, role=role, markdown=content.get('markdown', ''), senderId=senderId, createAt=createAt,
                    id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif msg_type == 'table':
                table = content.get('table', {})
                return self.add_table_message(
                    chatId=chatId, role=role, headers=table.get('headers', []), rows=table.get('rows', []),
                    senderId=senderId, createAt=createAt, id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
            else:
                return self.add_message(
                    chatId=chatId, role=role, content=content, senderId=senderId, createAt=createAt,
                    id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
        else:
            return self.add_text_message(
                chatId=chatId, role=role, text=str(content), senderId=senderId, createAt=createAt,
                id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)

    def push_message_to_chat(self, chatId, msg: dict):
        logger.debug("push message to front", msg)
        content = msg.get('content')
        createAt = msg.get('createAt')

        db_result = self.dispatch_add_message(chatId, msg)
        logger.info(f"push message to db_result: {db_result}")

        # Push to frontend
        web_gui = AppContext.get_web_gui()
        # Push actual data after database write
        if db_result and isinstance(db_result, dict) and 'data' in db_result:
            logger.debug("push chat message content:", db_result['data'])
            web_gui.get_ipc_api().push_chat_message(chatId, db_result['data'])
        else:
            logger.error(f"message insert db failed{chatId}, {msg.get('id')}")

    def push_notification_to_chat(self, chatId, notif: dict):
        logger.debug("push notification to front", notif)

        db_result = self.add_chat_notification(chatId, notif, int(time.time() * 1000))
        logger.info(f"push notification to db_result: {db_result}")
        # Push to frontend
        web_gui = AppContext.get_web_gui()
        # Push actual data after database write
        if db_result and isinstance(db_result, dict) and 'data' in db_result:
            logger.debug("push chat notification content:", db_result['data'])
            web_gui.get_ipc_api().push_chat_notification(chatId, db_result['data'])