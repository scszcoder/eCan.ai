"""
Slack channel adapter using the Socket Mode API.

Requires: pip install slack-bolt slack-sdk
Config keys:
  bot_token        — (required) Slack Bot User OAuth Token (xoxb-...)
  app_token        — (required) Slack App-Level Token for Socket Mode (xapp-...)
  allowed_channels — (optional) list of channel IDs to listen to; empty = accept all
  default_agent_id — (optional) agent ID to route messages to
"""

from __future__ import annotations

import time
from threading import Event
from typing import Callable, List, Optional

from utils.logger_helper import logger_helper as logger

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry


class SlackChannel(ChannelPlugin):
    _channel_id = "slack"

    def __init__(self):
        self._bot_token: str = ""
        self._app_token: str = ""
        self._allowed_channels: List[str] = []
        self._default_agent_id: Optional[str] = None
        self._bot_user_id: Optional[str] = None
        self._client = None         # slack_sdk.WebClient
        self._socket_handler = None  # slack_bolt.App

    @property
    def channel_id(self) -> str:
        return "slack"

    @property
    def display_name(self) -> str:
        return "Slack"

    # ---- lifecycle ----

    def configure(self, config: dict) -> None:
        self._bot_token = config.get("bot_token", "")
        self._app_token = config.get("app_token", "")
        if not self._bot_token:
            raise ValueError("Slack config requires 'bot_token' (xoxb-...)")
        if not self._app_token:
            raise ValueError("Slack config requires 'app_token' (xapp-...) for Socket Mode")

        self._allowed_channels = [str(c) for c in config.get("allowed_channels", [])]
        self._default_agent_id = config.get("default_agent_id")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
        from slack_sdk import WebClient

        self._client = WebClient(token=self._bot_token)

        # Get bot's own user ID to ignore its own messages
        try:
            auth_resp = self._client.auth_test()
            self._bot_user_id = auth_resp.get("user_id")
            logger.info(f"[Slack] Connected as bot user: {self._bot_user_id}")
        except Exception as exc:
            logger.error(f"[Slack] auth_test failed: {exc}")
            raise

        app = App(token=self._bot_token)
        self._socket_handler = SocketModeHandler(app, self._app_token)

        @app.event("message")
        def handle_message_events(event, say):
            self._on_slack_message(event, on_message)

        @app.event("app_mention")
        def handle_mention(event, say):
            self._on_slack_message(event, on_message)

        # SocketModeHandler.start() blocks — run it, but check stop_event
        # We start in a sub-thread so we can watch stop_event
        import threading

        handler_thread = threading.Thread(
            target=self._socket_handler.start,
            daemon=True,
            name="slack-socket-mode",
        )
        handler_thread.start()

        # Block until stop_event is set
        stop_event.wait()

        # Cleanup
        try:
            self._socket_handler.close()
        except Exception:
            pass

    def stop(self) -> None:
        if self._socket_handler:
            try:
                self._socket_handler.close()
            except Exception:
                pass

    # ---- outbound ----

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        if not self._client:
            return SendResult(success=False, error="Slack client not initialized")

        try:
            kwargs = {
                "channel": chat_id,
                "text": message.text or "(empty)",
            }
            if message.thread_id:
                kwargs["thread_ts"] = message.thread_id

            resp = self._client.chat_postMessage(**kwargs)

            if resp.get("ok"):
                return SendResult(
                    success=True,
                    message_id=resp.get("ts"),
                    raw=dict(resp),
                )
            else:
                return SendResult(
                    success=False,
                    error=resp.get("error", str(resp)),
                    raw=dict(resp),
                )

        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    # ---- helpers ----

    def _on_slack_message(
        self, event: dict, on_message: Callable[[ChannelMessage], None]
    ) -> None:
        # Ignore bot's own messages and message edits/deletes
        if event.get("user") == self._bot_user_id:
            return
        if event.get("subtype") in ("message_changed", "message_deleted", "bot_message"):
            return

        channel_id = event.get("channel", "")

        # Filter by allowed channels
        if self._allowed_channels and channel_id not in self._allowed_channels:
            return

        text = event.get("text", "")
        if not text:
            return

        # Resolve sender name (Slack events only include user ID)
        sender_id = event.get("user", "")
        sender_name = sender_id
        try:
            if self._client and sender_id:
                info = self._client.users_info(user=sender_id)
                profile = info.get("user", {}).get("profile", {})
                sender_name = (
                    profile.get("display_name") or
                    profile.get("real_name") or
                    sender_id
                )
        except Exception:
            pass

        # Extract attachments (files)
        attachments = []
        for f in event.get("files", []):
            attachments.append({
                "type": f.get("filetype", "file"),
                "name": f.get("name", ""),
                "url": f.get("url_private_download") or f.get("url_private", ""),
                "mime_type": f.get("mimetype", ""),
                "size": f.get("size", 0),
            })

        cm = ChannelMessage(
            channel_id="slack",
            account_id=self._bot_user_id or "",
            sender_id=sender_id,
            sender_name=sender_name,
            chat_id=channel_id,
            content=text,
            attachments=attachments,
            thread_id=event.get("thread_ts"),
            reply_to_id=None,
            raw=event,
            timestamp=float(event.get("ts", time.time())),
            message_id=event.get("ts", ""),
            target_agent_id=self._default_agent_id,
        )

        on_message(cm)

    def get_status_extra(self) -> dict:
        info = {}
        if self._bot_user_id:
            info["bot_user_id"] = self._bot_user_id
        return info


# Auto-register on import
ChannelRegistry().register(SlackChannel)
