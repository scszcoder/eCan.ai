"""
WhatsApp channel adapter using the WhatsApp Business Cloud API.

Requires: pip install requests (already available)
Config keys:
  phone_number_id  — (required) WhatsApp Business phone number ID
  access_token     — (required) permanent or long-lived access token
  verify_token     — (required) webhook verification token (you choose this)
  webhook_port     — (optional) local port for webhook server, default 8443
  webhook_path     — (optional) URL path, default "/webhook/whatsapp"
  allowed_numbers  — (optional) list of phone numbers to accept; empty = accept all
  default_agent_id — (optional) agent ID to route messages to
  api_version      — (optional) Graph API version, default "v21.0"

WhatsApp requires a publicly accessible webhook. For development, use ngrok
or similar to tunnel to the local webhook_port.
"""

from __future__ import annotations

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Event, Thread
from typing import Callable, List, Optional
from urllib.parse import parse_qs, urlparse

from utils.logger_helper import logger_helper as logger

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry


class WhatsAppChannel(ChannelPlugin):
    _channel_id = "whatsapp"

    def __init__(self):
        self._phone_number_id: str = ""
        self._access_token: str = ""
        self._verify_token: str = ""
        self._webhook_port: int = 8443
        self._webhook_path: str = "/webhook/whatsapp"
        self._allowed_numbers: List[str] = []
        self._default_agent_id: Optional[str] = None
        self._api_version: str = "v21.0"
        self._server: Optional[HTTPServer] = None
        self._on_message: Optional[Callable] = None

    @property
    def channel_id(self) -> str:
        return "whatsapp"

    @property
    def display_name(self) -> str:
        return "WhatsApp"

    # ---- lifecycle ----

    def configure(self, config: dict) -> None:
        self._phone_number_id = config.get("phone_number_id", "")
        self._access_token = config.get("access_token", "")
        self._verify_token = config.get("verify_token", "")

        if not self._phone_number_id:
            raise ValueError("WhatsApp config requires 'phone_number_id'")
        if not self._access_token:
            raise ValueError("WhatsApp config requires 'access_token'")
        if not self._verify_token:
            raise ValueError("WhatsApp config requires 'verify_token'")

        self._webhook_port = config.get("webhook_port", 8443)
        self._webhook_path = config.get("webhook_path", "/webhook/whatsapp")
        self._allowed_numbers = [str(n) for n in config.get("allowed_numbers", [])]
        self._default_agent_id = config.get("default_agent_id")
        self._api_version = config.get("api_version", "v21.0")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        self._on_message = on_message

        # Build a webhook HTTP server
        channel_ref = self

        class WebhookHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                """Webhook verification (Meta sends a GET with hub.challenge)."""
                parsed = urlparse(self.path)
                qs = parse_qs(parsed.query)

                mode = qs.get("hub.mode", [None])[0]
                token = qs.get("hub.verify_token", [None])[0]
                challenge = qs.get("hub.challenge", [None])[0]

                if mode == "subscribe" and token == channel_ref._verify_token and challenge:
                    logger.info("[WhatsApp] Webhook verified successfully")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(challenge.encode("utf-8"))
                else:
                    logger.warning("[WhatsApp] Webhook verification failed")
                    self.send_response(403)
                    self.end_headers()

            def do_POST(self):
                """Receive inbound messages."""
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)

                # Always respond 200 quickly to Meta
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')

                try:
                    payload = json.loads(body)
                    channel_ref._process_webhook(payload)
                except Exception as exc:
                    logger.error(f"[WhatsApp] Webhook processing error: {exc}")

            def log_message(self, format, *args):
                pass  # suppress default HTTP server logging

        self._server = HTTPServer(("0.0.0.0", self._webhook_port), WebhookHandler)
        logger.info(
            f"[WhatsApp] Webhook server listening on port {self._webhook_port} "
            f"at {self._webhook_path}"
        )

        # Run server in a sub-thread so we can watch stop_event
        server_thread = Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="whatsapp-webhook",
        )
        server_thread.start()

        # Block until stop_event
        stop_event.wait()

        self._server.shutdown()

    def stop(self) -> None:
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass

    # ---- outbound ----

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        url = (
            f"https://graph.facebook.com/{self._api_version}/"
            f"{self._phone_number_id}/messages"
        )
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

        if message.media_url:
            return self._send_media(url, headers, chat_id, message)

        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": "text",
            "text": {"body": message.text or "(empty)"},
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=15)
            data = resp.json()

            messages = data.get("messages", [])
            if messages:
                return SendResult(
                    success=True,
                    message_id=messages[0].get("id"),
                    raw=data,
                )
            else:
                error = data.get("error", {}).get("message", str(data))
                return SendResult(success=False, error=error, raw=data)

        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    def _send_media(
        self, url: str, headers: dict, chat_id: str, message: OutboundMessage
    ) -> SendResult:
        import requests

        media_type = (message.media_type or "document").lower()
        type_map = {"photo": "image", "picture": "image"}
        wa_type = type_map.get(media_type, media_type)

        payload = {
            "messaging_product": "whatsapp",
            "to": chat_id,
            "type": wa_type,
            wa_type: {"link": message.media_url},
        }
        if message.caption:
            payload[wa_type]["caption"] = message.caption

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            data = resp.json()
            messages = data.get("messages", [])
            if messages:
                return SendResult(success=True, message_id=messages[0].get("id"), raw=data)
            else:
                error = data.get("error", {}).get("message", str(data))
                return SendResult(success=False, error=error, raw=data)
        except Exception as exc:
            return SendResult(success=False, error=str(exc))

    # ---- webhook processing ----

    def _process_webhook(self, payload: dict) -> None:
        """Parse WhatsApp Cloud API webhook payload and dispatch messages."""
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if value.get("messaging_product") != "whatsapp":
                    continue

                contacts = {c["wa_id"]: c.get("profile", {}).get("name", c["wa_id"])
                            for c in value.get("contacts", [])}

                for msg in value.get("messages", []):
                    sender_wa_id = msg.get("from", "")

                    # Filter by allowed numbers
                    if self._allowed_numbers and sender_wa_id not in self._allowed_numbers:
                        continue

                    cm = self._normalize(msg, contacts, value.get("metadata", {}))
                    if cm and self._on_message:
                        self._on_message(cm)

    def _normalize(self, msg: dict, contacts: dict, metadata: dict) -> Optional[ChannelMessage]:
        """Convert a WhatsApp message object to ChannelMessage."""
        msg_type = msg.get("type", "")
        sender_wa_id = msg.get("from", "")
        sender_name = contacts.get(sender_wa_id, sender_wa_id)

        # Extract text
        text = ""
        if msg_type == "text":
            text = msg.get("text", {}).get("body", "")
        elif msg_type == "image":
            text = msg.get("image", {}).get("caption", "[image]")
        elif msg_type == "audio":
            text = "[audio message]"
        elif msg_type == "video":
            text = msg.get("video", {}).get("caption", "[video]")
        elif msg_type == "document":
            text = msg.get("document", {}).get("caption", "[document]")
        elif msg_type == "reaction":
            return None  # skip reactions
        elif msg_type == "sticker":
            text = "[sticker]"
        else:
            text = f"[{msg_type}]"

        # Extract attachments
        attachments = []
        for media_key in ("image", "audio", "video", "document"):
            media = msg.get(media_key)
            if media:
                attachments.append({
                    "type": media_key,
                    "media_id": media.get("id", ""),
                    "mime_type": media.get("mime_type", ""),
                    "caption": media.get("caption", ""),
                })

        return ChannelMessage(
            channel_id="whatsapp",
            account_id=metadata.get("phone_number_id", self._phone_number_id),
            sender_id=sender_wa_id,
            sender_name=sender_name,
            chat_id=sender_wa_id,  # WhatsApp: chat_id = sender phone number for 1:1
            content=text,
            attachments=attachments,
            raw=msg,
            timestamp=float(msg.get("timestamp", time.time())),
            message_id=msg.get("id", ""),
            target_agent_id=self._default_agent_id,
        )

    def get_status_extra(self) -> dict:
        return {
            "phone_number_id": self._phone_number_id,
            "webhook_port": self._webhook_port,
        }


# Auto-register on import
ChannelRegistry().register(WhatsAppChannel)
