"""
Channel Bridge — converts between channel messages and the internal agent pipeline.

Inbound:  ChannelMessage → req dict → runner.sync_task_wait_in_line("channel_message", req)
Outbound: state dict (with channel metadata in attributes) → channel_manager.send()
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, Optional

from agent.channels.base import ChannelMessage, OutboundMessage

logger = logging.getLogger(__name__)


class ChannelBridge:
    """
    Bridges external channel adapters to the eCan.ai agent pipeline.

    *mainwin*: reference to the MainWindow (for agent lookup).
    *channel_manager*: reference set after construction (circular dep).
    """

    def __init__(self, mainwin: Any, channel_manager: Any):
        self._mainwin = mainwin
        self._channel_manager = channel_manager

    # -- inbound ---------------------------------------------------------------

    def dispatch_inbound(self, msg: ChannelMessage) -> None:
        """
        Convert a ChannelMessage to the internal ``req`` dict and dispatch
        it to the first available agent's runner.
        """
        try:
            req = self._channel_message_to_req(msg)
            agent = self._pick_agent(msg)
            if agent is None:
                logger.warning(f"[ChannelBridge] No agent available for channel message from {msg.channel_id}")
                return
            runner = getattr(agent, "runner", None)
            if runner is None:
                logger.warning(f"[ChannelBridge] Agent {agent.card.name} has no runner")
                return
            runner.sync_task_wait_in_line("channel_message", req)
            logger.info(f"[ChannelBridge] Dispatched channel_message from {msg.channel_id}:{msg.chat_id}")
        except Exception as e:
            logger.error(f"[ChannelBridge] dispatch_inbound error: {e}")

    def _channel_message_to_req(self, msg: ChannelMessage) -> Dict[str, Any]:
        """Build the internal ``req`` dict from a ChannelMessage."""
        internal_chat_id = f"ch:{msg.channel_id}:{msg.chat_id}"
        msg_id = msg.message_id or str(uuid.uuid4())
        return {
            "id": msg_id,
            "method": "channel_message",
            "params": {
                "chatId": internal_chat_id,
                "senderId": msg.sender_id,
                "senderName": msg.sender_name,
                "content": {
                    "type": msg.message_type.value if hasattr(msg.message_type, "value") else str(msg.message_type),
                    "text": msg.text,
                },
                "attachments": msg.attachments or [],
                "createAt": int(msg.timestamp * 1000),
                # Channel routing metadata — propagated into state by resume.py
                "channel_id": msg.channel_id,
                "channel_chat_id": msg.chat_id,
                "channel_sender_id": msg.sender_id,
                "channel_message_id": msg.message_id,
                "channel_thread_id": msg.thread_id or "",
                "channel_account_id": msg.metadata.get("account_id", ""),
            },
        }

    def _pick_agent(self, msg: ChannelMessage) -> Any:
        """Resolve which agent should handle this channel message."""
        agents = getattr(self._mainwin, "agents", [])
        if not agents:
            return None

        # If the channel config specifies a default agent, try that first
        if self._channel_manager:
            plugin = self._channel_manager.get_channel(msg.channel_id)
            if plugin:
                default_agent_id = getattr(plugin, "_default_agent_id", None)
                if default_agent_id:
                    for a in agents:
                        if getattr(a, "id", None) == default_agent_id:
                            if getattr(a, "runner", None):
                                return a

        # Fallback: first agent with a runner
        for a in agents:
            if getattr(a, "runner", None):
                return a
        return None

    # -- outbound --------------------------------------------------------------

    def route_reply(self, state: Dict[str, Any], text: str) -> Optional[bool]:
        """
        Check whether *state* originated from an external channel.
        If so, send the reply through the channel manager and return True.
        Returns None if this is a normal GUI conversation.
        """
        attrs = state.get("attributes", {})
        channel_id = attrs.get("channel_id")
        if not channel_id or channel_id == "webchat":
            return None  # not a channel message — let caller fall through to GUI

        channel_chat_id = attrs.get("channel_chat_id", "")
        if not channel_chat_id:
            # Try to extract from internal chat_id format "ch:<channel>:<platform_id>"
            chat_id = attrs.get("chat_id", "")
            if chat_id.startswith("ch:"):
                parts = chat_id.split(":", 2)
                if len(parts) == 3:
                    channel_chat_id = parts[2]

        if not channel_chat_id:
            logger.warning(f"[ChannelBridge] Cannot route reply: no channel_chat_id for channel={channel_id}")
            return None

        thread_id = attrs.get("channel_thread_id", "")
        outbound = OutboundMessage(text=text, thread_id=thread_id if thread_id else None)

        if self._channel_manager is None:
            logger.warning("[ChannelBridge] No channel manager available for outbound routing")
            return None

        result = self._channel_manager.send(channel_id, channel_chat_id, outbound)
        if result.success:
            logger.info(f"[ChannelBridge] Reply sent via {channel_id} to {channel_chat_id}")
            return True
        else:
            logger.error(f"[ChannelBridge] Failed to send reply via {channel_id}: {result.error}")
            return None
