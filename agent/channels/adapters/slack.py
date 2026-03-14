"""
Slack channel adapter — Socket Mode via slack-bolt.

Requires: ``slack-bolt``, ``slack-sdk`` (in requirements-base.txt).
Config keys: ``bot_token``, ``app_token``, ``allowed_channels`` (optional list),
             ``default_agent_id`` (optional).
"""
from __future__ import annotations

import logging
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


class SlackPlugin(ChannelPlugin):
    channel_type = "slack"

    def __init__(self):
        self._bot_token: str = ""
        self._app_token: str = ""
        self._allowed: Optional[List[str]] = None
        self._default_agent_id: Optional[str] = None
        self._handler = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._bot_token = config.get("bot_token", "")
        self._app_token = config.get("app_token", "")
        if not self._bot_token or not self._app_token:
            raise ValueError("Slack bot_token and app_token are required")
        allowed = config.get("allowed_channels")
        self._allowed = [str(c) for c in allowed] if allowed else None
        self._default_agent_id = config.get("default_agent_id") or None

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        app = App(token=self._bot_token)

        @app.message("")
        def handle_message(message, say):
            channel = message.get("channel", "")
            if self._allowed and channel not in self._allowed:
                return
            cm = ChannelMessage(
                channel_id="slack",
                chat_id=channel,
                sender_id=message.get("user", ""),
                sender_name=message.get("user", ""),
                text=message.get("text", ""),
                message_type=MessageType.TEXT,
                raw=message,
                timestamp=float(message.get("ts", time.time())),
                message_id=message.get("ts", ""),
                thread_id=message.get("thread_ts"),
            )
            try:
                on_message(cm)
            except Exception as e:
                logger.error(f"[Slack] on_message error: {e}")

        self._handler = SocketModeHandler(app, self._app_token)
        logger.info("[Slack] Starting Socket Mode handler")
        # Start in a non-blocking way and wait for stop_event
        self._handler.connect()
        stop_event.wait()
        logger.info("[Slack] Stop event received, disconnecting")

    def stop(self) -> None:
        if self._handler:
            try:
                self._handler.close()
            except Exception as e:
                logger.debug(f"[Slack] Error closing handler: {e}")
            self._handler = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        from slack_sdk import WebClient

        client = WebClient(token=self._bot_token)
        try:
            kwargs: Dict[str, Any] = {
                "channel": chat_id,
                "text": message.text,
            }
            if message.thread_id:
                kwargs["thread_ts"] = message.thread_id
            resp = client.chat_postMessage(**kwargs)
            return SendResult(
                success=resp["ok"],
                message_id=resp.get("ts"),
                raw=resp.data,
            )
        except Exception as e:
            return SendResult(success=False, error=str(e))


# Auto-register
ChannelRegistry.register("slack", SlackPlugin)
