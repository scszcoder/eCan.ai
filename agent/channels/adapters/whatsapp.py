"""
WhatsApp channel adapter — Business Cloud API with local webhook server.

Requires: ``requests`` (already in requirements-base.txt).
Config keys: ``phone_number_id``, ``access_token``, ``verify_token``,
             ``webhook_port`` (default 8443), ``default_agent_id`` (optional).
"""
from __future__ import annotations

import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Event, Thread
from typing import Any, Callable, Dict, Optional

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    MessageType,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)

_GRAPH_URL = "https://graph.facebook.com/v19.0/{phone_id}/messages"


class WhatsAppPlugin(ChannelPlugin):
    channel_type = "whatsapp"

    def __init__(self):
        self._phone_id: str = ""
        self._access_token: str = ""
        self._verify_token: str = ""
        self._webhook_port: int = 8443
        self._default_agent_id: Optional[str] = None
        self._server: Optional[HTTPServer] = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._phone_id = config.get("phone_number_id", "")
        self._access_token = config.get("access_token", "")
        self._verify_token = config.get("verify_token", "whatsapp_verify")
        self._webhook_port = int(config.get("webhook_port", 8443))
        self._default_agent_id = config.get("default_agent_id") or None
        if not self._phone_id or not self._access_token:
            raise ValueError("WhatsApp phone_number_id and access_token are required")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        plugin = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                """Webhook verification challenge."""
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(self.path).query)
                mode = qs.get("hub.mode", [None])[0]
                token = qs.get("hub.verify_token", [None])[0]
                challenge = qs.get("hub.challenge", [None])[0]
                if mode == "subscribe" and token == plugin._verify_token and challenge:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(challenge.encode())
                else:
                    self.send_response(403)
                    self.end_headers()

            def do_POST(self):
                """Receive inbound messages."""
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length)) if length else {}
                self.send_response(200)
                self.end_headers()
                try:
                    for entry in body.get("entry", []):
                        for change in entry.get("changes", []):
                            value = change.get("value", {})
                            for msg in value.get("messages", []):
                                cm = ChannelMessage(
                                    channel_id="whatsapp",
                                    chat_id=msg.get("from", ""),
                                    sender_id=msg.get("from", ""),
                                    sender_name=plugin._get_contact_name(value, msg.get("from", "")),
                                    text=msg.get("text", {}).get("body", ""),
                                    message_type=plugin._detect_type(msg),
                                    raw=msg,
                                    timestamp=float(msg.get("timestamp", time.time())),
                                    message_id=msg.get("id", ""),
                                )
                                on_message(cm)
                except Exception as e:
                    logger.error(f"[WhatsApp] Webhook processing error: {e}")

            def log_message(self, format, *args):
                pass  # suppress access logs

        self._server = HTTPServer(("0.0.0.0", self._webhook_port), Handler)
        self._server.timeout = 1
        logger.info(f"[WhatsApp] Webhook listening on port {self._webhook_port}")
        while not stop_event.is_set():
            self._server.handle_request()
        logger.info("[WhatsApp] Webhook server stopped")

    def stop(self) -> None:
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        url = _GRAPH_URL.format(phone_id=self._phone_id)
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "text",
            "text": {"body": message.text},
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()
            msg_id = ""
            msgs = data.get("messages", [])
            if msgs:
                msg_id = msgs[0].get("id", "")
            if resp.status_code in (200, 201):
                return SendResult(success=True, message_id=msg_id, raw=data)
            return SendResult(success=False, error=data.get("error", {}).get("message", str(data)), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    @staticmethod
    def _detect_type(msg: dict) -> MessageType:
        t = msg.get("type", "text")
        return {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "document": MessageType.FILE,
            "audio": MessageType.AUDIO,
            "video": MessageType.VIDEO,
            "sticker": MessageType.STICKER,
            "location": MessageType.LOCATION,
            "interactive": MessageType.INTERACTIVE,
        }.get(t, MessageType.UNKNOWN)

    @staticmethod
    def _get_contact_name(value: dict, wa_id: str) -> str:
        for contact in value.get("contacts", []):
            if contact.get("wa_id") == wa_id:
                profile = contact.get("profile", {})
                return profile.get("name", wa_id)
        return wa_id


# Auto-register
ChannelRegistry.register("whatsapp", WhatsAppPlugin)
