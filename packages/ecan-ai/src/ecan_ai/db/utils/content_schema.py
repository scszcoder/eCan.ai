"""
Content schema definitions for chat messages.

This module defines the content types and schema for different
types of chat messages including text, code, forms, etc.
"""

from enum import Enum
from typing import List, Dict, Any, Optional


class ContentType(str, Enum):
    """Message content type enumeration."""
    TEXT = "text"
    IMAGE = "image_url"
    FILE = "file_url"
    CODE = "code"
    SYSTEM = "system"
    FORM = "form"
    NOTIFICATION = "notification"
    CARD = "card"
    MARKDOWN = "markdown"
    TABLE = "table"


class ContentSchema:
    """Content schema factory for different message types."""
    
    @staticmethod
    def create_text(text: str) -> Dict[str, Any]:
        """
        Create text content.
        
        Args:
            text (str): Text content
            
        Returns:
            dict: Text content schema
        """
        return {"type": ContentType.TEXT.value, "text": text}

    @staticmethod
    def create_code(code: str, language: str = "python") -> Dict[str, Any]:
        """
        Create code content with syntax highlighting.
        
        Args:
            code (str): Code content
            language (str): Programming language for syntax highlighting
            
        Returns:
            dict: Code content schema
        """
        return {"type": ContentType.CODE.value, "code": {"lang": language, "value": code}}

    @staticmethod
    def create_form(text: str, form: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create form content for data collection.
        
        Args:
            text (str): Form description text
            form (dict): Form fields configuration
            
        Returns:
            dict: Form content schema
        """
        return {
            "type": ContentType.FORM.value,
            "text": text,
            "form": form
        }

    @staticmethod
    def create_system(text: str, level: str = "info") -> Dict[str, Any]:
        """
        Create system message content.
        
        Args:
            text (str): System message text
            level (str): Message level (info, warning, error, success)
            
        Returns:
            dict: System message content schema
        """
        return {
            "type": ContentType.SYSTEM.value,
            "system": {
                "text": text,
                "level": level
            }
        }

    @staticmethod
    def create_notification(title: Optional[str] = None, content: Optional[str] = None) -> Dict[str, Any]:
        """
        Create notification message content.
        
        Args:
            title (str, optional): Notification title
            content (str, optional): Notification content
            
        Returns:
            dict: Notification content schema
        """
        return {
            "type": ContentType.NOTIFICATION.value,
            "notification": {
                "title": title or "Notification",
                "content": content or ""
            }
        }

    @staticmethod
    def create_card(title: str, content: str, actions: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Create card content with title, content and action buttons.
        
        Args:
            title (str): Card title
            content (str): Card content
            actions (list, optional): Action buttons configuration
            
        Returns:
            dict: Card content schema
        """
        return {
            "type": ContentType.CARD.value,
            "card": {
                "title": title,
                "content": content,
                "actions": actions or []
            }
        }

    @staticmethod
    def create_markdown(content: str) -> Dict[str, Any]:
        """
        Create Markdown content for rich text display.
        
        Args:
            content (str): Markdown content
            
        Returns:
            dict: Markdown content schema
        """
        return {
            "type": ContentType.MARKDOWN.value,
            "markdown": content
        }

    @staticmethod
    def create_table(headers: List[str], rows: List[List[Any]]) -> Dict[str, Any]:
        """
        Create table content for structured data display.
        
        Args:
            headers (list): Table headers
            rows (list): Table rows data
            
        Returns:
            dict: Table content schema
        """
        return {
            "type": ContentType.TABLE.value,
            "table": {
                "headers": headers,
                "rows": rows
            }
        }
