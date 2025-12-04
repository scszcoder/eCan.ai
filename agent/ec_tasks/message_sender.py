"""
Message Sender - Unified GUI message sending.

This module provides a unified interface for sending messages to the GUI,
eliminating duplicate code for different message types.
"""

import time
import traceback
import uuid
from typing import Any, Dict, Optional, Union, TYPE_CHECKING

from app_context import AppContext
from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from agent.ec_agent import EC_Agent


class MessageType:
    """Message content types."""
    TEXT = "text"
    FORM = "form"
    NOTIFICATION = "notification"
    CARD = "card"
    CODE = "code"


class ChatMessageSender:
    """
    Unified sender for chat messages to GUI.
    
    Consolidates sendChatMessageToGUI, sendChatFormToGUI, and 
    sendChatNotificationToGUI into a single interface.
    """
    
    def __init__(self, agent: Optional["EC_Agent"] = None):
        """
        Initialize the message sender.
        
        Args:
            agent: Optional agent reference for sender info.
        """
        self.agent = agent
    
    def send(
        self,
        chat_id: Union[str, list],
        content_type: str,
        content: Any,
        sender_id: Optional[str] = None,
        sender_name: Optional[str] = None,
        role: str = "agent",
        status: str = "sent"
    ) -> bool:
        """
        Send a message to the GUI.
        
        Args:
            chat_id: Target chat ID (or list with first element as ID).
            content_type: Type of content (text, form, notification, etc.).
            content: The content to send.
            sender_id: Optional sender ID (uses agent if not provided).
            sender_name: Optional sender name (uses agent if not provided).
            role: Message role (default: "agent").
            status: Message status (default: "sent").
            
        Returns:
            True if sent successfully, False otherwise.
        """
        try:
            # Normalize chat_id
            target_chat_id = chat_id[0] if isinstance(chat_id, list) else chat_id
            
            # Get sender info from agent if not provided
            if self.agent and not sender_id:
                sender_id = self.agent.card.id
            if self.agent and not sender_name:
                sender_name = self.agent.card.name
            
            # Build message data
            msg_data = self._build_message_data(
                content_type=content_type,
                content=content,
                sender_id=sender_id,
                sender_name=sender_name,
                role=role,
                status=status
            )
            
            # Push to chat service
            mainwin = AppContext.get_main_window()
            
            if content_type == MessageType.NOTIFICATION:
                mainwin.db_chat_service.push_notification_to_chat(target_chat_id, msg_data)
            else:
                mainwin.db_chat_service.push_message_to_chat(target_chat_id, msg_data)
            
            return True
            
        except Exception as e:
            ex_stat = f"ErrorSendChat2GUI[{content_type}]:" + traceback.format_exc() + " " + str(e)
            logger.error(ex_stat)
            return False
    
    def _build_message_data(
        self,
        content_type: str,
        content: Any,
        sender_id: Optional[str],
        sender_name: Optional[str],
        role: str,
        status: str
    ) -> Dict[str, Any]:
        """Build the message data structure."""
        msg_id = str(uuid.uuid4())
        
        # Build content based on type
        if content_type == MessageType.TEXT:
            # Extract text from dict if needed
            if isinstance(content, dict):
                text = content.get('llm_result', str(content))
            elif isinstance(content, str):
                text = content
            else:
                text = str(content)
            content_data = {"type": "text", "text": text}
        elif content_type == MessageType.FORM:
            content_data = {"type": "form", "form": content}
        elif content_type == MessageType.NOTIFICATION:
            content_data = {"type": "notification", "notification": content}
        elif content_type == MessageType.CARD:
            content_data = {"type": "card", "card": content}
        elif content_type == MessageType.CODE:
            content_data = {"type": "code", "code": content}
        else:
            # Generic content
            content_data = {"type": content_type, content_type: content}
        
        return {
            "role": role,
            "id": msg_id,
            "senderId": sender_id,
            "senderName": sender_name,
            "createAt": int(time.time() * 1000),
            "content": content_data,
            "status": status
        }
    
    # ==================== Convenience Methods ====================
    
    def send_text(self, chat_id: Union[str, list], text: str, **kwargs) -> bool:
        """Send a text message."""
        return self.send(chat_id, MessageType.TEXT, text, **kwargs)
    
    def send_form(self, chat_id: Union[str, list], form_data: Any, **kwargs) -> bool:
        """Send a form message."""
        return self.send(chat_id, MessageType.FORM, form_data, **kwargs)
    
    def send_notification(self, chat_id: Union[str, list], notification: Any, **kwargs) -> bool:
        """Send a notification message."""
        return self.send(chat_id, MessageType.NOTIFICATION, notification, **kwargs)
    
    def send_card(self, chat_id: Union[str, list], card_data: Any, **kwargs) -> bool:
        """Send a card message."""
        return self.send(chat_id, MessageType.CARD, card_data, **kwargs)
    
    def send_code(self, chat_id: Union[str, list], code_data: Any, **kwargs) -> bool:
        """Send a code message."""
        return self.send(chat_id, MessageType.CODE, code_data, **kwargs)


# ==================== Module-level Convenience Functions ====================

_default_sender: Optional[ChatMessageSender] = None


def get_message_sender(agent: Optional["EC_Agent"] = None) -> ChatMessageSender:
    """Get or create a message sender instance."""
    global _default_sender
    if agent:
        return ChatMessageSender(agent)
    if _default_sender is None:
        _default_sender = ChatMessageSender()
    return _default_sender


def send_chat_message(
    chat_id: Union[str, list],
    content_type: str,
    content: Any,
    agent: Optional["EC_Agent"] = None,
    **kwargs
) -> bool:
    """
    Send a chat message to the GUI.
    
    Args:
        chat_id: Target chat ID.
        content_type: Type of content.
        content: The content to send.
        agent: Optional agent for sender info.
        **kwargs: Additional arguments for the message.
        
    Returns:
        True if sent successfully.
    """
    sender = get_message_sender(agent)
    return sender.send(chat_id, content_type, content, **kwargs)
