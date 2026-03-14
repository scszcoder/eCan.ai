"""
Telegram channel adapter using the Bot API (long polling mode).

Requires: pip install python-telegram-bot
Config keys:
  bot_token       — (required) Telegram Bot API token from @BotFather
  allowed_chat_ids — (optional) list of chat IDs to accept messages from; empty = accept all
  polling_timeout  — (optional) long-poll timeout in seconds, default 30
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


class TelegramChannel(ChannelPlugin):
    _channel_id = "telegram"

    def __init__(self):
        self._bot = None
        self._bot_token: str = ""
        self._allowed_chat_ids: List[str] = []
        self._polling_timeout: int = 30
        self._default_agent_id: Optional[str] = None
        self._bot_info: Optional[dict] = None
        self._last_update_id: int = 0

    @property
    def channel_id(self) -> str:
        return "telegram"

    @property
    def display_name(self) -> str:
        return "Telegram"

    # ---- lifecycle ----

    def configure(self, config: dict) -> None:
        self._bot_token = config.get("bot_token", "")
        if not self._bot_token:
            raise ValueError("Telegram config requires 'bot_token'")

        self._allowed_chat_ids = [
            str(cid) for cid in config.get("allowed_chat_ids", [])
        ]
        self._polling_timeout = config.get("polling_timeout", 30)
        self._default_agent_id = config.get("default_agent_id")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        """Long-polling loop using requests (no async dependency)."""
        import requests

        base_url = f"https://api.telegram.org/bot{self._bot_token}"

        # Fetch bot info
        try:
            me = requests.get(f"{base_url}/getMe", timeout=10).json()
            if me.get("ok"):
                self._bot_info = me["result"]
                logger.info(
                    f"[Telegram] Bot connected: @{self._bot_info.get('username')}"
                )
        except Exception as exc:
            logger.error(f"[Telegram] getMe failed: {exc}")
            raise

        while not stop_event.is_set():
            try:
                params = {
                    "timeout": self._polling_timeout,
                    "allowed_updates": '["message"]',
                }
                if self._last_update_id:
                    params["offset"] = self._last_update_id + 1

                resp = requests.get(
                    f"{base_url}/getUpdates",
                    params=params,
                    timeout=self._polling_timeout + 10,
                )
                data = resp.json()

                if not data.get("ok"):
                    logger.warning(f"[Telegram] getUpdates error: {data}")
                    stop_event.wait(5)
                    continue

                for update in data.get("result", []):
                    self._last_update_id = update["update_id"]
                    message = update.get("message")
                    if not message:
                        continue

                    chat = message.get("chat", {})
                    chat_id_str = str(chat.get("id", ""))

                    # Filter by allowed_chat_ids
                    if self._allowed_chat_ids and chat_id_str not in self._allowed_chat_ids:
                        logger.debug(f"[Telegram] Ignoring message from chat {chat_id_str} (not in allowlist)")
                        continue

                    cm = self._normalize(message)
                    if cm:
                        on_message(cm)

            except requests.exceptions.Timeout:
                continue  # normal for long polling
            except Exception as exc:
                logger.error(f"[Telegram] Polling error: {exc}")
                stop_event.wait(3)

    def stop(self) -> None:
        pass  # stop_event handles it; requests timeout will break the loop

    # ---- outbound ----

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        base_url = f"https://api.telegram.org/bot{self._bot_token}"

        try:
            if message.media_url:
                return self._send_media(base_url, chat_id, message)

            payload = {
                "chat_id": chat_id,
                "text": message.text or "(empty)",
                "parse_mode": "Markdown",
            }
            if message.reply_to_id:
                payload["reply_to_message_id"] = message.reply_to_id

            resp = requests.post(f"{base_url}/sendMessage", json=payload, timeout=15)
            data = resp.json()

            if data.get("ok"):
                return SendResult(
                    success=True,
                    message_id=str(data["result"]["message_id"]),
                    raw=data,
                )
            else:
                return SendResult(success=False, error=data.get("description", str(data)), raw=data)

        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    def _send_media(self, base_url: str, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        media_type = (message.media_type or "file").lower()
        method_map = {
            "image": "sendPhoto",
            "photo": "sendPhoto",
            "audio": "sendAudio",
            "video": "sendVideo",
            "file": "sendDocument",
            "document": "sendDocument",
        }
        method = method_map.get(media_type, "sendDocument")
        field_map = {
            "sendPhoto": "photo",
            "sendAudio": "audio",
            "sendVideo": "video",
            "sendDocument": "document",
        }
        field_name = field_map[method]

        payload = {
            "chat_id": chat_id,
            field_name: message.media_url,
        }
        if message.caption:
            payload["caption"] = message.caption

        try:
            resp = requests.post(f"{base_url}/{method}", json=payload, timeout=30)
            data = resp.json()
            if data.get("ok"):
                return SendResult(success=True, message_id=str(data["result"]["message_id"]), raw=data)
            else:
                return SendResult(success=False, error=data.get("description", str(data)), raw=data)
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    # ---- helpers ----

    def _normalize(self, message: dict) -> Optional[ChannelMessage]:
        """Convert a Telegram message dict to ChannelMessage."""
        text = message.get("text", "")
        caption = message.get("caption", "")
        content = text or caption

        if not content and not self._has_media(message):
            return None  # skip non-text, non-media messages

        chat = message.get("chat", {})
        sender = message.get("from", {})

        attachments = self._extract_attachments(message)

        return ChannelMessage(
            channel_id="telegram",
            account_id=str(self._bot_info.get("id", "")) if self._bot_info else "",
            sender_id=str(sender.get("id", "")),
            sender_name=(
                sender.get("first_name", "") +
                (" " + sender.get("last_name", "") if sender.get("last_name") else "")
            ).strip() or sender.get("username", "unknown"),
            chat_id=str(chat.get("id", "")),
            content=content,
            attachments=attachments,
            thread_id=str(message.get("message_thread_id", "")) or None,
            reply_to_id=str(message.get("reply_to_message", {}).get("message_id", "")) or None,
            raw=message,
            timestamp=float(message.get("date", time.time())),
            message_id=str(message.get("message_id", "")),
            target_agent_id=self._default_agent_id,
        )

    def _has_media(self, message: dict) -> bool:
        return any(
            key in message
            for key in ("photo", "audio", "video", "document", "voice", "sticker")
        )

    def _extract_attachments(self, message: dict) -> list:
        attachments = []
        if "photo" in message:
            # Telegram sends multiple sizes; take the largest
            photo = message["photo"][-1] if message["photo"] else {}
            attachments.append({
                "type": "image",
                "file_id": photo.get("file_id"),
                "file_size": photo.get("file_size"),
            })
        for key in ("document", "audio", "video", "voice"):
            if key in message:
                item = message[key]
                attachments.append({
                    "type": key,
                    "file_id": item.get("file_id"),
                    "file_name": item.get("file_name", ""),
                    "mime_type": item.get("mime_type", ""),
                    "file_size": item.get("file_size"),
                })
        return attachments

    def get_status_extra(self) -> dict:
        info = {}
        if self._bot_info:
            info["bot_username"] = self._bot_info.get("username", "")
        return info


# Auto-register on import
ChannelRegistry().register(TelegramChannel)
