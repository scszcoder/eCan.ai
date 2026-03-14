"""
Discord channel adapter — Gateway bot via discord.py.

Requires: ``discord.py`` (in requirements-base.txt).
Config keys: ``bot_token``, ``allowed_channel_ids`` (optional list of int),
             ``default_agent_id`` (optional).

Uses discord.py's Gateway connection (WebSocket) to receive messages and
the REST API to send replies. No public endpoint required.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from threading import Event
from typing import Any, Callable, Dict, List, Optional

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    MessageType,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)


class DiscordPlugin(ChannelPlugin):
    channel_type = "discord"

    def __init__(self):
        self._bot_token: str = ""
        self._allowed_channels: Optional[List[int]] = None
        self._default_agent_id: Optional[str] = None
        self._client = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._bot_token = config.get("bot_token", "")
        if not self._bot_token:
            raise ValueError("Discord bot_token is required")
        allowed = config.get("allowed_channel_ids")
        self._allowed_channels = [int(c) for c in allowed] if allowed else None
        self._default_agent_id = config.get("default_agent_id") or None

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        import discord

        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True

        client = discord.Client(intents=intents)
        self._client = client
        plugin = self

        @client.event
        async def on_ready():
            logger.info(f"[Discord] Bot connected as {client.user}")

        @client.event
        async def on_message(message: discord.Message):
            # Ignore own messages
            if message.author == client.user:
                return
            # Ignore bots
            if message.author.bot:
                return
            # Channel filter
            if plugin._allowed_channels and message.channel.id not in plugin._allowed_channels:
                return

            attachments = []
            msg_type = MessageType.TEXT
            for att in message.attachments:
                att_dict = {
                    "type": _discord_content_type(att.content_type or ""),
                    "url": att.url,
                    "filename": att.filename,
                    "size": att.size,
                }
                attachments.append(att_dict)
                if att.content_type and att.content_type.startswith("image"):
                    msg_type = MessageType.IMAGE
                elif att.content_type and att.content_type.startswith("video"):
                    msg_type = MessageType.VIDEO
                elif att.content_type and att.content_type.startswith("audio"):
                    msg_type = MessageType.AUDIO
                else:
                    msg_type = MessageType.FILE

            # If text is present but there are also attachments, keep TEXT type
            if message.content and attachments:
                msg_type = MessageType.TEXT

            thread_id = None
            if isinstance(message.channel, discord.Thread):
                thread_id = str(message.channel.id)

            cm = ChannelMessage(
                channel_id="discord",
                chat_id=str(message.channel.id),
                sender_id=str(message.author.id),
                sender_name=message.author.display_name or message.author.name,
                text=message.content or "",
                message_type=msg_type if not message.content else MessageType.TEXT,
                attachments=attachments,
                raw={
                    "id": str(message.id),
                    "guild_id": str(message.guild.id) if message.guild else None,
                    "channel_id": str(message.channel.id),
                },
                timestamp=message.created_at.timestamp(),
                message_id=str(message.id),
                thread_id=thread_id,
                metadata={
                    "guild_id": str(message.guild.id) if message.guild else "",
                    "guild_name": message.guild.name if message.guild else "",
                    "channel_name": getattr(message.channel, "name", ""),
                },
            )
            try:
                on_message(cm)
            except Exception as e:
                logger.error(f"[Discord] on_message callback error: {e}")

        # Run the discord client in its own event loop
        self._loop = asyncio.new_event_loop()

        def _run():
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(client.start(self._bot_token))
            except Exception as e:
                if not stop_event.is_set():
                    logger.error(f"[Discord] Client error: {e}")
            finally:
                try:
                    self._loop.run_until_complete(client.close())
                except Exception:
                    pass
                self._loop.close()

        bot_thread = threading.Thread(target=_run, daemon=True, name="discord-bot-inner")
        bot_thread.start()

        logger.info("[Discord] Bot starting, waiting for stop event")
        stop_event.wait()

        # Trigger graceful shutdown
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(client.close(), self._loop)
        bot_thread.join(timeout=10)
        logger.info("[Discord] Bot stopped")

    def stop(self) -> None:
        if self._client and self._loop and self._loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self._client.close(), self._loop)
            except Exception as e:
                logger.debug(f"[Discord] Error closing client: {e}")
        self._client = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a message to a Discord channel by its ID."""
        if not self._client or not self._loop or self._loop.is_closed():
            return SendResult(success=False, error="Discord client not running")

        async def _send():
            channel = self._client.get_channel(int(chat_id))
            if channel is None:
                # Try fetching if not in cache
                try:
                    channel = await self._client.fetch_channel(int(chat_id))
                except Exception as e:
                    return SendResult(success=False, error=f"Channel not found: {e}")

            kwargs = {"content": message.text}
            if message.reply_to:
                try:
                    ref_msg = await channel.fetch_message(int(message.reply_to))
                    kwargs["reference"] = ref_msg
                except Exception:
                    pass  # couldn't find message to reply to, send normally

            sent = await channel.send(**kwargs)
            return SendResult(success=True, message_id=str(sent.id))

        try:
            future = asyncio.run_coroutine_threadsafe(_send(), self._loop)
            return future.result(timeout=15)
        except Exception as e:
            return SendResult(success=False, error=str(e))


def _discord_content_type(ct: str) -> str:
    if ct.startswith("image"):
        return "image"
    if ct.startswith("video"):
        return "video"
    if ct.startswith("audio"):
        return "audio"
    return "file"


# Auto-register
ChannelRegistry.register("discord", DiscordPlugin)
