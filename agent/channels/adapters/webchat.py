"""
WebChat channel adapter — wraps the existing GUI chat pipeline.

This adapter doesn't run its own monitor; the existing GUI IPC path
(handle_send_chat → gui_a2a_send_chat) already handles inbound.

The adapter is registered so that:
  - ChannelManager.get_all_statuses() includes webchat
  - Outbound routing can identify "webchat" as a known channel (and skip
    external routing, falling through to the normal GUI push path)
"""

from __future__ import annotations

from threading import Event
from typing import Callable, Optional

from utils.logger_helper import logger_helper as logger

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry


class WebChatChannel(ChannelPlugin):
    _channel_id = "webchat"

    def __init__(self):
        self._default_agent_id: Optional[str] = None

    @property
    def channel_id(self) -> str:
        return "webchat"

    @property
    def display_name(self) -> str:
        return "Web Chat (GUI)"

    def configure(self, config: dict) -> None:
        self._default_agent_id = config.get("default_agent_id")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        # WebChat doesn't have its own monitor — the existing IPC path
        # (handle_send_chat) is the inbound source.  Just block until stopped.
        logger.info("[WebChat] Adapter active (inbound handled by existing IPC path)")
        stop_event.wait()

    def stop(self) -> None:
        pass

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        # Outbound for webchat goes through the existing ChatMessageSender /
        # db_chat_service.push_message_to_chat path, NOT through this adapter.
        # This method is here only for completeness.
        try:
            from app_context import AppContext
            from agent.ec_tasks.message_sender import ChatMessageSender

            mainwin = AppContext.get_main_window()
            sender = ChatMessageSender()
            ok = sender.send_text(chat_id, message.text)
            return SendResult(success=ok)
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    def get_status_extra(self) -> dict:
        return {"note": "Inbound handled by existing IPC path"}


# Auto-register on import
ChannelRegistry().register(WebChatChannel)
