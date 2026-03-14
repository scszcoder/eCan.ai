"""
WebChat channel adapter — wraps existing GUI chat pipeline.

This adapter is a no-op that registers itself so the ChannelManager
recognizes "webchat" as a valid channel type.  Inbound and outbound
messages for the GUI are already handled by the existing IPC/WS pipeline.
"""
from __future__ import annotations

import logging
from threading import Event
from typing import Any, Callable, Dict

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)


class WebChatPlugin(ChannelPlugin):
    channel_type = "webchat"

    def configure(self, config: Dict[str, Any]) -> None:
        pass  # no external configuration needed

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        # The existing GUI IPC pipeline handles inbound messages.
        # Just block until stopped so ChannelManager sees this as "running".
        logger.info("[WebChat] Adapter active (GUI IPC handles messages)")
        stop_event.wait()

    def stop(self) -> None:
        pass

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        # Outbound for webchat goes through ChatMessageSender / IPC, not here.
        return SendResult(success=True, message_id="gui")


# Auto-register
ChannelRegistry.register("webchat", WebChatPlugin)
