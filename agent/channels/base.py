"""
Channel Plugin base abstractions.

Defines the minimal contract every channel adapter must implement,
plus normalized message dataclasses shared across the architecture.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from threading import Event
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChannelStatus(str, Enum):
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    LOCATION = "location"
    STICKER = "sticker"
    INTERACTIVE = "interactive"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Normalized message dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ChannelMessage:
    """Normalized inbound message envelope from any channel."""
    channel_id: str                          # e.g. "telegram", "slack"
    chat_id: str                             # platform-specific conversation id
    sender_id: str                           # platform-specific sender id
    sender_name: str = ""
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    raw: Any = None                          # original platform payload
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    thread_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Normalized outbound message payload to send through a channel."""
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None           # message_id to reply to
    thread_id: Optional[str] = None


@dataclass
class SendResult:
    """Result of an outbound send attempt."""
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None
    raw: Any = None


# ---------------------------------------------------------------------------
# Capability Mixins (optional — adapters can declare extra capabilities)
# ---------------------------------------------------------------------------

class ThreadingCapable:
    """Marker: adapter supports threaded conversations."""
    pass


class MediaCapable:
    """Marker: adapter supports sending/receiving media."""
    pass


class GroupCapable:
    """Marker: adapter supports group conversations."""
    pass


class ReactionCapable:
    """Marker: adapter supports emoji reactions."""
    pass


# ---------------------------------------------------------------------------
# Channel Plugin ABC
# ---------------------------------------------------------------------------

class ChannelPlugin(ABC):
    """
    Minimal 4-method contract for a channel adapter.

    Lifecycle:
        configure(config)  →  start(on_message, stop_event)  →  stop()

    Sending:
        send(chat_id, message) → SendResult
    """

    # Subclasses set this; also used as registry key
    channel_type: str = ""

    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """
        Validate and store configuration (tokens, webhook URLs, etc.).
        Called once before start().
        """
        ...

    @abstractmethod
    def start(
        self,
        on_message: Callable[[ChannelMessage], None],
        stop_event: Event,
    ) -> None:
        """
        Begin listening for inbound messages.  **Blocks** until *stop_event*
        is set.  Must call *on_message* for every normalized inbound message.
        Runs inside a dedicated daemon thread managed by ChannelManager.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """
        Perform any cleanup beyond what *stop_event* already handles
        (close sockets, flush queues, etc.).
        """
        ...

    @abstractmethod
    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """
        Send an outbound message to *chat_id* on this channel.
        Returns a SendResult indicating success/failure.
        """
        ...

    # ---- convenience wrappers ------------------------------------------------

    def send_text(self, chat_id: str, text: str) -> SendResult:
        """Shorthand to send a plain-text message."""
        return self.send(chat_id, OutboundMessage(text=text))

    def send_media(self, chat_id: str, url: str, caption: str = "", media_type: str = "image") -> SendResult:
        """Shorthand to send a media message."""
        return self.send(chat_id, OutboundMessage(
            text=caption,
            message_type=MessageType.IMAGE,
            attachments=[{"type": media_type, "url": url}],
        ))
