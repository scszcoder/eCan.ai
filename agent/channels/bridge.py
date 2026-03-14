"""
Layer 3: Bridge between channel adapters and the existing agent pipeline.

Inbound:  ChannelMessage → req dict → runner.sync_task_wait_in_line("channel_message", req)
Outbound: agent response state → detect channel origin → channel_manager.send()
"""

from __future__ import annotations

import time
import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from utils.logger_helper import logger_helper as logger

from agent.channels.base import ChannelMessage, OutboundMessage, SendResult

if TYPE_CHECKING:
    from agent.channels.channel_manager import ChannelManager


class ChannelBridge:
    """
    Bridges external channel messages into the eCan.ai agent pipeline
    and routes agent replies back to the originating channel.
    """

    def __init__(self, mainwin: Any, channel_manager: "ChannelManager"):
        self._mainwin = mainwin
        self._channel_manager = channel_manager

    # ------------------------------------------------------------------
    # Inbound: ChannelMessage → agent pipeline
    # ------------------------------------------------------------------

    def dispatch_inbound(self, msg: ChannelMessage) -> None:
        """
        Convert a ``ChannelMessage`` to the existing req dict format and
        dispatch it through the event routing system.

        This is the callback passed to ``ChannelManager`` / ``ChannelPlugin.start()``.
        """
        try:
            req = self._channel_message_to_req(msg)
            agent = self._resolve_target_agent(msg)

            if agent is None:
                logger.error(
                    f"[ChannelBridge] No target agent for channel={msg.channel_id}, "
                    f"chat={msg.chat_id}, sender={msg.sender_name}"
                )
                return

            runner = getattr(agent, "runner", None)
            if runner is None:
                logger.error(f"[ChannelBridge] Agent '{agent.card.name}' has no runner")
                return

            logger.info(
                f"[ChannelBridge] Dispatching inbound from {msg.channel_id}:{msg.chat_id} "
                f"→ agent '{agent.card.name}'"
            )
            runner.sync_task_wait_in_line("channel_message", req)

        except Exception as exc:
            logger.error(f"[ChannelBridge] dispatch_inbound failed: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # Outbound: agent state → channel send
    # ------------------------------------------------------------------

    def route_reply(self, state: dict, text: str) -> Optional[SendResult]:
        """
        Check if the current conversation originated from an external channel.
        If so, send the reply through that channel instead of the GUI.

        Returns ``SendResult`` if routed to a channel, or ``None`` if the
        message should go through the normal GUI path.
        """
        attrs = state.get("attributes", {})
        channel_id = attrs.get("channel_id")
        channel_chat_id = attrs.get("channel_chat_id")

        if not channel_id or channel_id == "webchat":
            return None  # not from an external channel — use normal GUI path

        reply_to = attrs.get("channel_message_id")
        thread_id = attrs.get("channel_thread_id")

        outbound = OutboundMessage(
            text=text,
            reply_to_id=reply_to,
            thread_id=thread_id,
        )

        logger.info(
            f"[ChannelBridge] Routing reply to channel={channel_id}, "
            f"chat={channel_chat_id}, len={len(text)}"
        )
        result = self._channel_manager.send(channel_id, channel_chat_id, outbound)

        if not result.success:
            logger.error(
                f"[ChannelBridge] Failed to send reply via {channel_id}: {result.error}"
            )
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _channel_message_to_req(self, msg: ChannelMessage) -> dict:
        """
        Convert a ``ChannelMessage`` into the ``req`` dict format that
        ``gui_a2a_send_chat`` and ``sync_task_wait_in_line`` expect.

        The key fields are:
          - params.chatId
          - params.senderId
          - params.content  (str or dict)
          - params.attachments
          - params.receiverId  (optional — for explicit agent routing)

        Plus channel metadata so the outbound bridge can route replies back.
        """
        # Build a stable internal chatId that encodes the channel origin.
        # Format: "ch:<channel_id>:<platform_chat_id>"
        internal_chat_id = f"ch:{msg.channel_id}:{msg.chat_id}"

        req: Dict[str, Any] = {
            "method": "send_chat",
            "params": {
                "chatId": internal_chat_id,
                "senderId": f"{msg.channel_id}:{msg.sender_id}",
                "senderName": msg.sender_name or msg.sender_id,
                "receiverId": msg.target_agent_id or "",
                "content": {
                    "type": "text",
                    "text": msg.content,
                },
                "attachments": msg.attachments,
                "createAt": int(msg.timestamp * 1000),
                "human": True,
                # Channel metadata — preserved in state for outbound routing
                "channel_id": msg.channel_id,
                "channel_chat_id": msg.chat_id,       # original platform chat id
                "channel_sender_id": msg.sender_id,
                "channel_message_id": msg.message_id,
                "channel_thread_id": msg.thread_id,
                "channel_account_id": msg.account_id,
            },
        }
        return req

    def _resolve_target_agent(self, msg: ChannelMessage):
        """Find the agent that should handle this channel message.

        Resolution order:
          1. ``msg.target_agent_id`` — explicit routing from channel config
          2. Default agent configured for this channel
          3. First agent with a runner (last resort)
        """
        agents = getattr(self._mainwin, "agents", [])

        # 1. Explicit target
        if msg.target_agent_id:
            for ag in agents:
                card = getattr(ag, "card", None)
                if card and card.id == msg.target_agent_id:
                    return ag

        # 2. Channel-level default agent (from channel config)
        channel_plugin = self._channel_manager.get_plugin(msg.channel_id)
        if channel_plugin:
            default_agent_id = getattr(channel_plugin, "_default_agent_id", None)
            if default_agent_id:
                for ag in agents:
                    card = getattr(ag, "card", None)
                    if card and card.id == default_agent_id:
                        return ag

        # 3. First agent with a runner
        for ag in agents:
            if hasattr(ag, "runner") and ag.runner:
                card = getattr(ag, "card", None)
                if card and card.name != "My Twin Agent":
                    return ag

        # absolute fallback
        for ag in agents:
            if hasattr(ag, "runner") and ag.runner:
                return ag

        return None
