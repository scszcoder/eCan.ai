"""
Layer 1: Channel Plugin Contract + Data Models.

Minimal 4-method ABC for channel adapters, plus normalized data classes
for inbound/outbound messages.
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
# Data models
# ---------------------------------------------------------------------------

class ChannelStatus(str, Enum):
    """Runtime status of a channel."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class ChannelMessage:
    """Normalized inbound message — every channel converts to this before
    entering the agent pipeline."""

    channel_id: str               # "telegram", "slack", "whatsapp", "webchat"
    account_id: str = ""          # multi-account support (bot username, workspace id, …)
    sender_id: str = ""           # platform-specific sender ID
    sender_name: str = ""         # display name
    chat_id: str = ""             # conversation / group / DM id on the platform
    content: str = ""             # text body
    attachments: List[dict] = field(default_factory=list)  # normalized attachment dicts
    thread_id: Optional[str] = None   # for threaded channels (Slack threads, etc.)
    reply_to_id: Optional[str] = None
    raw: dict = field(default_factory=dict)  # original platform payload (escape hatch)
    timestamp: float = field(default_factory=time.time)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Routing hints (populated by bridge or channel adapter)
    target_agent_id: Optional[str] = None  # explicit agent routing


@dataclass
class OutboundMessage:
    """Payload for sending a reply back through a channel."""
    text: str = ""
    media_url: Optional[str] = None
    media_type: Optional[str] = None   # "image", "audio", "video", "file"
    caption: Optional[str] = None
    reply_to_id: Optional[str] = None  # platform message id to reply to
    thread_id: Optional[str] = None
    extra: dict = field(default_factory=dict)  # channel-specific extras


@dataclass
class SendResult:
    """Result of an outbound send attempt."""
    success: bool = False
    message_id: Optional[str] = None   # platform-assigned message id
    error: Optional[str] = None
    raw: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Capability mixins (optional — channels implement only what they support)
# ---------------------------------------------------------------------------

class ThreadingCapable:
    """Mixin for channels that support threaded conversations."""

    def send_to_thread(
        self, chat_id: str, thread_id: str, message: OutboundMessage
    ) -> SendResult:
        raise NotImplementedError


class MediaCapable:
    """Mixin for channels that support media attachments."""

    def send_media(
        self, chat_id: str, media_url: str, caption: Optional[str] = None
    ) -> SendResult:
        raise NotImplementedError


class GroupCapable:
    """Mixin for channels that support group/channel listing."""

    def list_groups(self) -> List[dict]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Channel Plugin ABC — the minimal contract
# ---------------------------------------------------------------------------

class ChannelPlugin(ABC):
    """
    Minimal channel adapter contract.

    Implementors must provide exactly 4 methods:
      configure  — validate credentials, set up API client
      start      — long-running inbound listener (blocking; runs in its own thread)
      stop       — graceful shutdown (called from manager thread)
      send       — outbound message delivery

    The ``on_message`` callback passed to ``start()`` accepts a single
    ``ChannelMessage`` argument and bridges it into the agent pipeline.
    """

    # ---- identity ----
    @property
    @abstractmethod
    def channel_id(self) -> str:
        """Unique channel type identifier, e.g. 'telegram', 'slack'."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable name for UI."""
        return self.channel_id.title()

    # ---- lifecycle ----
    @abstractmethod
    def configure(self, config: dict) -> None:
        """Validate and apply configuration (tokens, webhook URLs, etc.).

        Should raise ``ValueError`` on invalid config.
        """
        ...

    @abstractmethod
    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        """Run the inbound monitor loop.

        This method is called in a dedicated daemon thread and should block
        until ``stop_event`` is set.  When the event fires, clean up and return.

        Args:
            on_message: Callback to invoke for each normalized inbound message.
            stop_event: ``threading.Event`` that signals the monitor to stop.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Perform any additional cleanup beyond what stop_event handles."""
        ...

    # ---- outbound ----
    @abstractmethod
    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send an outbound message to the given chat/conversation.

        Args:
            chat_id: Platform-specific conversation identifier.
            message: The outbound payload.

        Returns:
            ``SendResult`` with success flag and optional platform message id.
        """
        ...

    # ---- optional helpers ----
    def get_status_extra(self) -> dict:
        """Return channel-specific status info (bot username, webhook url, …)."""
        return {}
