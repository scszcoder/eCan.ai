"""
Telegram channel adapter — Bot API long polling.

Requires: ``requests`` (already in requirements-base.txt).
Config keys: ``bot_token``, ``allowed_chat_ids`` (optional list),
             ``default_agent_id`` (optional).
"""
from __future__ import annotations

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

from utils.logger_helper import logger_helper as logger

_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramPlugin(ChannelPlugin):
    channel_type = "telegram"

    def __init__(self):
        self._token: str = ""
        self._allowed: Optional[List[str]] = None
        self._default_agent_id: Optional[str] = None
        self._offset: int = 0
        # Exponential backoff state for polling errors
        self._poll_error_delay: float = 1.0  # seconds
        self._poll_error_max_delay: float = 64.0  # seconds

    def configure(self, config: Dict[str, Any]) -> None:
        self._token = config.get("bot_token", "")
        if not self._token:
            raise ValueError("Telegram bot_token is required")
        # Reject obvious placeholder tokens so the poller doesn't spin
        # with 35-second connect timeouts, wasting a thread and GIL time.
        _placeholder_tokens = {"YOUR_BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN", ""}
        if self._token in _placeholder_tokens or self._token.startswith("YOUR_"):
            raise ValueError(
                f"Telegram bot_token is a placeholder ('{self._token}'). "
                "Set a real token or disable the Telegram channel."
            )
        allowed = config.get("allowed_chat_ids")
        self._allowed = [str(c) for c in allowed] if allowed else None
        self._default_agent_id = config.get("default_agent_id") or None

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        import requests

        logger.info("[Telegram] Starting long-polling loop")
        while not stop_event.is_set():
            try:
                resp = requests.get(
                    _API.format(token=self._token, method="getUpdates"),
                    params={"offset": self._offset, "timeout": 30},
                    timeout=35,
                )
                if resp.status_code != 200:
                    logger.warning(f"[Telegram] API error {resp.status_code}")
                    time.sleep(2)
                    continue
                data = resp.json()
                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    msg = update.get("message") or update.get("edited_message")
                    if not msg:
                        continue
                    chat_id = str(msg["chat"]["id"])
                    if self._allowed and chat_id not in self._allowed:
                        continue
                    cm = ChannelMessage(
                        channel_id="telegram",
                        chat_id=chat_id,
                        sender_id=str(msg["from"]["id"]),
                        sender_name=msg["from"].get("first_name", ""),
                        text=msg.get("text", ""),
                        message_type=self._detect_type(msg),
                        attachments=self._extract_attachments(msg),
                        raw=msg,
                        timestamp=float(msg.get("date", time.time())),
                        message_id=str(msg["message_id"]),
                    )
                    try:
                        on_message(cm)
                    except Exception as e:
                        logger.error(f"[Telegram] on_message error: {e}")
                # Success: reset backoff delay
                self._poll_error_delay = 1.0
            except Exception as e:
                if not stop_event.is_set():
                    logger.warning(f"[Telegram] Poll error: {e} — backing off for {self._poll_error_delay:.1f}s")
                    time.sleep(self._poll_error_delay)
                    # Exponential backoff: double delay, capped at max_delay
                    self._poll_error_delay = min(
                        self._poll_error_delay * 2,
                        self._poll_error_max_delay
                    )
        logger.info("[Telegram] Polling loop exited")

    def stop(self) -> None:
        pass  # stop_event handles it

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        try:
            if message.attachments:
                return self._send_media(chat_id, message)
            resp = requests.post(
                _API.format(token=self._token, method="sendMessage"),
                json={
                    "chat_id": chat_id,
                    "text": message.text,
                    "parse_mode": "Markdown",
                },
                timeout=15,
            )
            data = resp.json()
            if data.get("ok"):
                return SendResult(success=True, message_id=str(data["result"]["message_id"]), raw=data)
            return SendResult(success=False, error=data.get("description", "Unknown"), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _send_media(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        att = message.attachments[0]
        media_type = att.get("type", "photo")
        method_map = {"image": "sendPhoto", "photo": "sendPhoto", "document": "sendDocument",
                      "audio": "sendAudio", "video": "sendVideo", "voice": "sendVoice"}
        method = method_map.get(media_type, "sendDocument")
        field = "photo" if "photo" in method.lower() else media_type
        try:
            resp = requests.post(
                _API.format(token=self._token, method=method),
                json={"chat_id": chat_id, field: att.get("url", ""), "caption": message.text},
                timeout=30,
            )
            data = resp.json()
            if data.get("ok"):
                return SendResult(success=True, message_id=str(data["result"]["message_id"]), raw=data)
            return SendResult(success=False, error=data.get("description", "Unknown"), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    @staticmethod
    def _detect_type(msg: dict) -> MessageType:
        if "photo" in msg:
            return MessageType.IMAGE
        if "document" in msg:
            return MessageType.FILE
        if "audio" in msg or "voice" in msg:
            return MessageType.AUDIO
        if "video" in msg:
            return MessageType.VIDEO
        if "sticker" in msg:
            return MessageType.STICKER
        if "location" in msg:
            return MessageType.LOCATION
        return MessageType.TEXT

    @staticmethod
    def _extract_attachments(msg: dict) -> list:
        attachments = []
        if "photo" in msg:
            best = max(msg["photo"], key=lambda p: p.get("file_size", 0))
            attachments.append({"type": "image", "file_id": best["file_id"]})
        for key in ("document", "audio", "voice", "video"):
            if key in msg:
                attachments.append({"type": key, "file_id": msg[key]["file_id"]})
        return attachments


# Auto-register
ChannelRegistry.register("telegram", TelegramPlugin)
