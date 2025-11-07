"""
Database chat service for managing chat conversations, members, and messages.

This module provides the DBChatService class which handles all chat-related
database operations including creating chats, managing members, and
handling messages with various content types.
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import select
import os
import json
import uuid
import time as time_module
import copy

from app_context import AppContext
from ..core import Chat, Member, Message, Attachment, ChatNotification, Base
from ..utils import ContentSchema
from .base_service import BaseService
from utils.logger_helper import logger_helper as logger


class DBChatService(BaseService):
    """
    Database chat system service class providing all chat-related operations.

    This service handles chat conversations, members, messages, and notifications
    with support for various content types and database operations.
    """

    def __init__(self, engine=None, session=None):
        """
        Initialize chat service.

        Args:
            engine: SQLAlchemy engine instance (required)
            session: SQLAlchemy session instance (optional)
        """
        super().__init__(engine, session)

    def session_scope(self):
        """
        Provide a transactional scope around a series of operations.

        Yields:
            Session: SQLAlchemy session instance
        """
        # Use BaseService's session management
        return super().session_scope()



    def create_chat(
        self,
        members: list,              # Required, list of members
        name: str,                  # Required, chat name
        type: str = "user-agent",  # Optional, chat type, default user-agent
        avatar: str = None,         # Optional, chat avatar
        lastMsg: str = None,        # Optional, last message content
        lastMsgTime: int = None,    # Optional, last message timestamp
        unread: int = 0,            # Optional, unread count, default 0
        pinned: bool = False,       # Optional, whether pinned, default False
        muted: bool = False,        # Optional, whether muted, default False
        ext: dict = None,           # Optional, extension fields, default empty dict
        id: str = None,             # Optional, chat ID, auto-generated if not provided
        agent_id: str = None        # Optional, associated agent ID
    ) -> Dict[str, Any]:
        """
        Create a new chat conversation.
        
        Args:
            members (list): List of chat members
            name (str): Chat name
            type (str): Chat type, defaults to "user-agent"
            avatar (str, optional): Chat avatar URL
            lastMsg (str, optional): Last message content
            lastMsgTime (int, optional): Last message timestamp
            unread (int): Unread message count, defaults to 0
            pinned (bool): Whether chat is pinned, defaults to False
            muted (bool): Whether chat is muted, defaults to False
            ext (dict, optional): Extended attributes
            id (str, optional): Chat ID, auto-generated if not provided
            
        Returns:
            dict: Standard response with success status and data
        """
        ext = {} if ext is None else ext
        with self.session_scope() as session:
            try:
                input_member_ids = set(str(m['userId']) for m in members)
                logger.info(f"[create_chat] Checking for duplicate chat with members: {input_member_ids}, type: {type}")
                candidate_chats = session.query(Chat).filter(Chat.type == type).all()
                logger.info(f"[create_chat] Found {len(candidate_chats)} candidate chats of type '{type}'")
                for chat in candidate_chats:
                    db_member_ids = set(str(m.userId) for m in chat.members)
                    # logger.debug(f"[create_chat] Comparing with chat {chat.id}, members: {db_member_ids}")
                    if db_member_ids == input_member_ids:
                        logger.info(f"[create_chat] Duplicate found! Returning existing chat: {chat.id}")
                        return {
                            "success": False,
                            "id": chat.id,
                            "data": chat.to_dict(deep=True),
                            "error": f"Chat with same members already exists: {chat.id}"
                        }
                
                logger.info(f"[create_chat] No duplicate found, creating new chat with members: {input_member_ids}")

                chat_id = id or f"chat-{str(int(time_module.time() * 1000))[-6:]}"
                chat = Chat(
                    id=chat_id,
                    type=type,
                    name=name,
                    avatar=avatar,
                    agent_id=agent_id,
                    lastMsg=lastMsg,
                    lastMsgTime=lastMsgTime,
                    unread=unread,
                    pinned=pinned,
                    muted=muted,
                    ext=ext
                )

                for m in members:
                    member = Member(
                        chatId=chat_id,
                        userId=m["userId"],
                        role=m["role"],
                        name=m["name"],
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
        """
        Add a message to a chat conversation.
        
        Args:
            chatId (str): Chat ID
            role (str): Message role (user, assistant, system)
            content (Any): Message content
            senderId (str): Sender ID
            createAt (int): Creation timestamp
            id (str, optional): Message ID, auto-generated if not provided
            status (str): Message status, defaults to "complete"
            senderName (str, optional): Sender name
            time (int, optional): Message time
            ext (dict, optional): Extended attributes
            attachments (list, optional): Message attachments
            
        Returns:
            dict: Standard response with success status and data
        """
        t_add_msg_start = time_module.time()
        logger.debug(f"[db_chat_service] add_message: {chatId}, {role}, {content}, {senderId}, {createAt}, {id}, {status}, {senderName}, {time}, {ext}, {attachments}")
        
        t_db_start = time_module.time()
        with self.session_scope() as session:
            t_session = time_module.time()
            chat = session.get(Chat, chatId)
            logger.debug(f"[PERF] add_message - session.get(Chat): {time_module.time()-t_session:.3f}s")
            if not chat:
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": f"Chat {chatId} not found"
                }

            message_id = id or str(uuid.uuid4())
            message = Message(
                id=message_id,
                chatId=chatId,
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

            if attachments:
                for att in attachments:
                    attachment_obj = Attachment(
                        uid=att.get("uid", str(uuid.uuid4())),
                        messageId=message_id,
                        name=att["name"],
                        status=att["status"],
                        url=att.get("url"),
                        size=att.get("size"),
                        type=att.get("type"),
                        ext=att.get("ext")
                    )
                    message.attachments.append(attachment_obj)

            # Update chat.lastMsg and lastMsgTime
            chat.lastMsg = json.dumps(content, ensure_ascii=False)
            chat.lastMsgTime = createAt
            
            # Only increment unread count when receiving messages from others
            # User's own messages (role="user") should not increment unread
            if role != "user":
                chat.unread = (chat.unread or 0) + 1
                logger.debug(f"[add_message] Incremented unread for chat {chatId}, role={role}, new unread={chat.unread}")
            else:
                logger.debug(f"[add_message] Not incrementing unread for user message in chat {chatId}")
            chat.messages.append(message)
            session.add(message)
            t_flush = time_module.time()
            session.flush()
            logger.debug(f"[PERF] add_message - session.flush: {time_module.time()-t_flush:.3f}s")
            logger.debug(f"[PERF] add_message - DB operations: {time_module.time()-t_db_start:.3f}s")
            logger.debug(f"[PERF] add_message - TOTAL: {time_module.time()-t_add_msg_start:.3f}s")
            return {
                "success": True,
                "id": message.id,
                "data": message.to_dict(deep=True),
                "error": None
            }

    def dispatch_add_message(self, chatId, args: dict) -> dict:
        """
        Dispatch message addition based on content type.
        
        Args:
            chatId (str): Chat ID
            args (dict): Message arguments
            
        Returns:
            dict: Standard response from add_message methods
        """
        t_dispatch_start = time_module.time()
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
        if isinstance(createAt, list) and len(createAt) > 0:
            createAt = createAt[0]
        elif createAt is None:
            createAt = int(time_module.time() * 1000)

        # Normalize fields that must be scalars for DB binding
        if isinstance(senderId, list):
            senderId = senderId[0] if senderId else None
        if isinstance(senderName, list):
            senderName = senderName[0] if senderName else None
        if isinstance(status, list):
            status = status[0] if status else None

        if isinstance(content, dict) and 'type' in content:
            content_type = content.get('type')
            if content_type == 'form':
                result = self.add_form_message(
                    chatId=chatId, role=role, text=content.get('text', ''), form=content.get('form', {}),
                    senderId=senderId, createAt=createAt, id=messageId, status=status,
                    senderName=senderName, time=time_, ext=ext, attachments=attachments)
            elif content_type == 'notification':
                result = self.add_notification_message(
                    chatId=chatId, notification=content.get('notification', {}),
                    senderId=senderId, createAt=createAt, id=messageId, status=status,
                    senderName=senderName, time=time_, ext=ext, attachments=attachments)
            else:
                result = self.add_message(
                    chatId=chatId, role=role, content=content, senderId=senderId, createAt=createAt,
                    id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
        else:
            result = self.add_text_message(
                chatId=chatId, role=role, text=str(content), senderId=senderId, createAt=createAt,
                id=messageId, status=status, senderName=senderName, time=time_, ext=ext, attachments=attachments)
        
        logger.debug(f"[PERF] dispatch_add_message - TOTAL: {time_module.time()-t_dispatch_start:.3f}s")
        return result

    def add_text_message(self, chatId: str, role: str, text: str, senderId: str = None, createAt: int = None, **kwargs):
        """Add a text message to the chat."""
        content = ContentSchema.create_text(text)
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=content, 
            senderId=senderId or role, 
            createAt=createAt or int(time_module.time()*1000), 
            **kwargs
        )

    def add_form_message(self, chatId: str, role: str, text: str, form: dict, senderId: str = None, createAt: int = None, **kwargs):
        """Add a form message to the chat."""
        content = ContentSchema.create_form(text, form)
        logger.debug(f"[db_chat_service] add_form_message: {chatId}, {role}, {content}, {senderId}, {createAt}, {kwargs}")
        return self.add_message(
            chatId=chatId, 
            role=role, 
            content=content, 
            senderId=senderId or role, 
            createAt=createAt or int(time_module.time()*1000), 
            **kwargs
        )

    def add_notification_message(self, chatId: str, notification: dict = "",
                               senderId: str = "system", createAt: int = None, **kwargs):
        """Add a notification message to the chat."""
        title = notification.get('title', 'Notification')
        logger.debug(f"[db_chat_service] Final notification params - title: '{title}', notification: '{notification}'")
            
        notification_content = ContentSchema.create_notification(title, notification)
        logger.debug(f"[db_chat_service] Created notification content: {notification_content}")

        # Add message to database
        result = self.add_message(
            chatId=chatId,
            role="system",
            content=notification_content,
            senderId=senderId,
            createAt=createAt or int(time_module.time()*1000),
            **kwargs
        )
        logger.debug(f"[db_chat_service] add_notification_message result: {result}")
        return result

    def query_messages_by_chat(
        self,
        chatId: str,
        limit: int = 20,
        offset: int = 0,
        reverse: bool = False
    ) -> Dict[str, Any]:
        """
        Query messages by chat ID with pagination.
        
        Args:
            chatId (str): Chat ID
            limit (int): Number of messages to return, defaults to 20
            offset (int): Starting offset, defaults to 0
            reverse (bool): Whether to reverse order, defaults to False
            
        Returns:
            dict: Standard response with message list
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

    def get_chat_by_id(
        self, 
        chat_id: str, 
        deep: bool = False
    ) -> Dict[str, Any]:
        """
        Get chat by ID.
        
        Args:
            chat_id (str): Chat ID
            deep (bool): Whether to include members and messages
            
        Returns:
            dict: Standard response with chat data
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

    def query_chats_by_user(self, userId: Optional[str] = None, deep: bool = False) -> Dict[str, Any]:
        """
        Query chats by user ID.
        
        Args:
            userId (str, optional): User ID
            deep (bool): Whether to include messages
            
        Returns:
            dict: Standard response with chat list
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

    def search_chats_by_message_content(
        self, 
        userId: Optional[str] = None, 
        searchText: Optional[str] = None,
        deep: bool = False
    ) -> Dict[str, Any]:
        """
        Search chats by message content for a specific user.
        
        This method finds all chats where:
        1. The user is a member (via userId)
        2. Any message in the chat contains the search text
        
        Args:
            userId (str, optional): User ID to filter chats
            searchText (str, optional): Text to search in message content
            deep (bool): Whether to include messages in response
            
        Returns:
            dict: Standard response with filtered chat list
        """
        if not userId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "userId is required"
            }
        
        if not searchText or not searchText.strip():
            # If no search text, return all chats for the user
            return self.query_chats_by_user(userId=userId, deep=deep)
        
        with self.session_scope() as session:
            try:
                # Find all chats where user is a member
                user_chats_stmt = select(Chat).join(Member).where(Member.userId == userId)
                user_chats = session.execute(user_chats_stmt).scalars().all()
                
                # Filter chats that have messages containing the search text
                matching_chats = []
                search_lower = searchText.lower().strip()
                
                logger.debug(f"[search_chats] Total user chats: {len(user_chats)}, searching for: '{search_lower}'")
                
                for chat in user_chats:
                    # Query messages for this chat
                    messages_stmt = select(Message).where(Message.chatId == chat.id)
                    messages = session.execute(messages_stmt).scalars().all()
                    
                    logger.trace(f"[search_chats] Chat {chat.id}: {len(messages)} messages")
                    
                    # Check if any message contains the search text
                    has_match = False
                    for msg in messages:
                        if msg.content:
                            # Handle different content types
                            searchable_text = ""
                            
                            if isinstance(msg.content, str):
                                searchable_text = msg.content
                            elif isinstance(msg.content, dict):
                                # 提取所有可能包含文本的字段
                                text_fields = []
                                
                                # 主要文本字段
                                if msg.content.get('text'):
                                    text_fields.append(str(msg.content.get('text')))
                                if msg.content.get('content'):
                                    text_fields.append(str(msg.content.get('content')))
                                
                                # form 字段（递归提取所有文本）
                                if msg.content.get('form'):
                                    form_data = msg.content.get('form')
                                    if isinstance(form_data, dict):
                                        # 递归提取 form 中的所有字符串值
                                        def extract_strings(obj):
                                            if isinstance(obj, str):
                                                return [obj]
                                            elif isinstance(obj, dict):
                                                result = []
                                                for v in obj.values():
                                                    result.extend(extract_strings(v))
                                                return result
                                            elif isinstance(obj, list):
                                                result = []
                                                for item in obj:
                                                    result.extend(extract_strings(item))
                                                return result
                                            else:
                                                return [str(obj)] if obj is not None else []
                                        
                                        text_fields.extend(extract_strings(form_data))
                                    elif isinstance(form_data, str):
                                        text_fields.append(form_data)
                                
                                # 其他可能的文本字段
                                for field in ['title', 'description', 'label', 'value', 'message']:
                                    if msg.content.get(field):
                                        text_fields.append(str(msg.content.get(field)))
                                
                                # 合并所有文本字段
                                searchable_text = ' '.join(filter(None, text_fields))
                            
                            # 模糊匹配
                            if searchable_text and search_lower in searchable_text.lower():
                                logger.debug(f"[search_chats] Match found in chat {chat.id}, searchable_text: {searchable_text[:100]}...")
                                has_match = True
                                break
                    
                    if has_match:
                        matching_chats.append(chat)
                    else:
                        logger.info(f"[search_chats] No match in chat {chat.id}")
                
                logger.info(f"[search_chats_by_message_content] Found {len(matching_chats)} chats matching '{searchText}' for user {userId}")
                
                return {
                    "success": True,
                    "id": None,
                    "data": [chat.to_dict(deep=deep) for chat in matching_chats],
                    "error": None
                }
            except Exception as e:
                logger.error(f"[search_chats_by_message_content] Error: {e}")
                return {
                    "success": False,
                    "id": None,
                    "data": None,
                    "error": str(e)
                }

    def delete_chat(self, chatId: str) -> Dict[str, Any]:
        """
        Delete a chat and all related data.
        
        Args:
            chatId (str): Chat ID
            
        Returns:
            dict: Standard response
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
        Mark messages as read and update chat unread count.
        
        只标记 isRead=False 的消息，并更新对应 chat 的 unread 计数。
        
        Args:
            messageIds (list): List of message IDs
            userId (str): User ID
            
        Returns:
            dict: Standard response with {
                "updated_ids": [实际更新的消息ID],
                "chat_updates": {chatId: unread_count_decreased}
            }
        """
        if not messageIds or not userId:
            return {
                "success": False,
                "id": None,
                "data": None,
                "error": "message_ids and user_id are required"
            }
        
        with self.session_scope() as session:
            # 统计每个 chat 需要减少的 unread 数量
            chat_unread_decrease = {}
            updated_ids = []
            
            for message_id in messageIds:
                message = session.get(Message, message_id)
                if not message:
                    logger.debug(f"[mark_message_as_read] Message {message_id} not found")
                    continue
                
                # 只处理未读消息
                if not message.isRead:
                    message.isRead = True
                    updated_ids.append(message_id)
                    
                    # 统计该 chat 的未读数减少
                    chat_id = message.chatId
                    chat_unread_decrease[chat_id] = chat_unread_decrease.get(chat_id, 0) + 1
                    
                    logger.debug(f"[mark_message_as_read] Marked message {message_id} as read in chat {chat_id}")
            
            # 批量更新 chat 的 unread 计数
            for chat_id, decrease_count in chat_unread_decrease.items():
                chat = session.get(Chat, chat_id)
                if chat:
                    old_unread = chat.unread
                    chat.unread = max(0, chat.unread - decrease_count)
                    logger.info(f"[mark_message_as_read] Chat {chat_id} unread: {old_unread} -> {chat.unread} (-{decrease_count})")
            
            session.flush()
            
            logger.info(f"[mark_message_as_read] Updated {len(updated_ids)} messages across {len(chat_unread_decrease)} chats")
            
            return {
                "success": True,
                "id": None,
                "data": {
                    "updated_ids": updated_ids,
                    "chat_updates": chat_unread_decrease
                },
                "error": None
            }

    def set_chat_unread(self, chatId: str, unread: int = 0) -> Dict[str, Any]:
        """
        Set chat unread count.
        
        Args:
            chatId (str): Chat ID
            unread (int): Unread count, defaults to 0
            
        Returns:
            dict: Standard response
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

    def submit_form(self, chatId: str, messageId: str, formId: str, formData: dict) -> Dict[str, Any]:
        """
        Submit form data and update message content.
        
        Args:
            chatId (str): Chat ID
            messageId (str): Message ID
            formId (str): Form ID
            formData (dict): Form data
            
        Returns:
            dict: Standard response
        """
        if not chatId or not messageId or not formId or formData is None:
            return {
                "success": False,
                "error": "chatId, messageId, formId, formData are required",
                "data": None
            }
        with self.session_scope() as session:
            message = session.get(Message, messageId)
            if not message or message.chatId != chatId:
                return {
                    "success": False,
                    "error": "Message does not exist or does not belong to specified chat",
                    "data": None
                }
            content = message.content
            if not isinstance(content, dict) or content.get('type') != 'form':
                return {
                    "success": False,
                    "error": "Message type is not form",
                    "data": None
                }
            # Replace content['form']
            content['form'] = formData
            message.content = copy.deepcopy(content)  # Ensure SQLAlchemy detects the change
            session.flush()
            return {
                "success": True,
                "data": message.to_dict(deep=True),
                "error": None
            }

    def delete_message(self, chatId: str, messageId: str) -> Dict[str, Any]:
        """
        Delete a message from the chat.
        
        Args:
            chatId (str): Chat ID
            messageId (str): Message ID to delete
            
        Returns:
            dict: Standard response with deleted message data
        """
        if not chatId or not messageId:
            return {
                "success": False,
                "error": "chatId and messageId are required",
                "data": None
            }
        
        try:
            with self.session_scope() as session:
                # Find the message to delete
                message = session.query(Message).filter(
                    Message.id == messageId,
                    Message.chatId == chatId
                ).first()
                
                if not message:
                    return {
                        "success": False,
                        "error": f"Message with id {messageId} not found in chat {chatId}",
                        "data": None
                    }
                
                # Store message data before deletion for response
                message_data = message.to_dict(deep=True)
                
                # Delete associated attachments first (if any)
                session.query(Attachment).filter(Attachment.messageId == messageId).delete()
                
                # Delete the message
                session.delete(message)
                session.commit()
                
                logger.info(f"[db_chat_service] Message {messageId} deleted from chat {chatId}")
                
                return {
                    "success": True,
                    "data": message_data,
                    "error": None
                }
                
        except Exception as e:
            logger.error(f"[db_chat_service] Error deleting message {messageId}: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "data": None
            }

    def add_chat_notification(self, chatId: str, content: dict, timestamp: int, isRead: bool = False, uid: str = None) -> dict:
        """
        Add a chat notification.
        
        Args:
            chatId (str): Chat ID
            content (dict): Notification content
            timestamp (int): Notification timestamp
            isRead (bool): Whether notification is read
            uid (str, optional): Notification UID
            
        Returns:
            dict: Standard response
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
        Query chat notifications with pagination.
        
        Args:
            chatId (str): Chat ID
            limit (int): Number of notifications to return
            offset (int): Starting offset
            reverse (bool): Whether to reverse order
            
        Returns:
            dict: Standard response with notification list
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

    def push_message_to_chat(self, chatId, msg: dict):
        """Push message to chat and frontend."""
        logger.debug("[db_chat_service] push message to front", chatId, msg)
        content = msg.get('content')
        createAt = msg.get('createAt')

        db_result = self.dispatch_add_message(chatId, msg)
        logger.info(f"[db_chat_service] push message to db_result: {db_result}")

        # Push to frontend
        web_gui = AppContext.get_web_gui()
        # Push actual data after database write
        if db_result and isinstance(db_result, dict) and 'data' in db_result:
            logger.debug("[db_chat_service] push chat message content:", chatId, db_result['data'])
            web_gui.get_ipc_api().push_chat_message(chatId, db_result['data'])
        else:
            logger.error(f"[db_chat_service] message insert db failed{chatId}, {msg.get('id')}")

    def push_notification_to_chat(self, chatId, notif: dict):
        """Push notification to chat and frontend."""
        logger.debug("[db_chat_service] push notification to front", notif)

        db_result = self.add_chat_notification(chatId, notif, int(time_module.time() * 1000))
        logger.info(f"[db_chat_service] push notification to db_result: {db_result}")
        # Push to frontend
        web_gui = AppContext.get_web_gui()
        # Push actual data after database write
        if db_result and isinstance(db_result, dict) and 'data' in db_result:
            logger.debug("[db_chat_service] push chat notification content:", db_result['data'])
            web_gui.get_ipc_api().push_chat_notification(chatId, db_result['data'])
