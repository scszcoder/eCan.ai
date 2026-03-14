"""
Facebook Messenger channel adapter — Webhook + Graph API.

Requires: ``requests`` (already in requirements-base.txt).
Config keys: ``page_access_token``, ``verify_token``, ``app_secret`` (optional, for signature verification),
             ``webhook_port`` (default 8444), ``default_agent_id`` (optional).

Messenger uses a webhook for inbound messages and the Send API for outbound.
You must set up a Facebook App with Messenger Platform and subscribe to the
page's messages webhook pointing to this server.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
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

_SEND_API = "https://graph.facebook.com/v19.0/me/messages"


class MessengerPlugin(ChannelPlugin):
    channel_type = "messenger"

    def __init__(self):
        self._page_access_token: str = ""
        self._verify_token: str = ""
        self._app_secret: str = ""
        self._webhook_port: int = 8444
        self._default_agent_id: Optional[str] = None
        self._server: Optional[HTTPServer] = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._page_access_token = config.get("page_access_token", "")
        self._verify_token = config.get("verify_token", "messenger_verify")
        self._app_secret = config.get("app_secret", "")
        self._webhook_port = int(config.get("webhook_port", 8444))
        self._default_agent_id = config.get("default_agent_id") or None
        if not self._page_access_token:
            raise ValueError("Messenger page_access_token is required")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: "Event") -> None:
        from threading import Event as _E
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
                """Receive inbound messages from Messenger Platform."""
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length) if length else b""

                # Optional signature verification
                if plugin._app_secret:
                    sig_header = self.headers.get("X-Hub-Signature-256", "")
                    expected = "sha256=" + hmac.new(
                        plugin._app_secret.encode(), raw_body, hashlib.sha256
                    ).hexdigest()
                    if not hmac.compare_digest(sig_header, expected):
                        self.send_response(403)
                        self.end_headers()
                        return

                self.send_response(200)
                self.end_headers()

                try:
                    body = json.loads(raw_body) if raw_body else {}
                    if body.get("object") != "page":
                        return
                    for entry in body.get("entry", []):
                        for event in entry.get("messaging", []):
                            plugin._process_messaging_event(event, on_message)
                except Exception as e:
                    logger.error(f"[Messenger] Webhook processing error: {e}")

            def log_message(self, format, *args):
                pass  # suppress access logs

        self._server = HTTPServer(("0.0.0.0", self._webhook_port), Handler)
        self._server.timeout = 1
        logger.info(f"[Messenger] Webhook listening on port {self._webhook_port}")
        while not stop_event.is_set():
            self._server.handle_request()
        logger.info("[Messenger] Webhook server stopped")

    def _process_messaging_event(
        self, event: Dict[str, Any], on_message: Callable[[ChannelMessage], None]
    ) -> None:
        """Process a single messaging event from the webhook payload."""
        sender_id = event.get("sender", {}).get("id", "")
        if not sender_id:
            return

        # Skip delivery/read confirmations, echoes, etc.
        if event.get("delivery") or event.get("read"):
            return
        # Skip echo messages (messages sent by the page itself)
        msg_data = event.get("message", {})
        if msg_data.get("is_echo"):
            return

        # Postback events (button clicks)
        postback = event.get("postback")
        if postback:
            cm = ChannelMessage(
                channel_id="messenger",
                chat_id=sender_id,
                sender_id=sender_id,
                text=postback.get("payload", postback.get("title", "")),
                message_type=MessageType.INTERACTIVE,
                raw=event,
                timestamp=float(event.get("timestamp", time.time() * 1000)) / 1000.0,
                message_id=str(event.get("timestamp", "")),
            )
            on_message(cm)
            return

        # Standard message events
        if not msg_data:
            return

        text = msg_data.get("text", "")
        attachments = []
        msg_type = MessageType.TEXT

        for att in msg_data.get("attachments", []):
            att_type = att.get("type", "")
            payload = att.get("payload", {})
            attachments.append({
                "type": att_type,
                "url": payload.get("url", ""),
                "sticker_id": payload.get("sticker_id"),
            })
            if att_type == "image":
                msg_type = MessageType.IMAGE
            elif att_type == "video":
                msg_type = MessageType.VIDEO
            elif att_type == "audio":
                msg_type = MessageType.AUDIO
            elif att_type == "file":
                msg_type = MessageType.FILE
            elif att_type == "location":
                msg_type = MessageType.LOCATION
                attachments[-1]["coordinates"] = payload.get("coordinates", {})

        cm = ChannelMessage(
            channel_id="messenger",
            chat_id=sender_id,
            sender_id=sender_id,
            text=text,
            message_type=msg_type,
            attachments=attachments,
            raw=event,
            timestamp=float(event.get("timestamp", time.time() * 1000)) / 1000.0,
            message_id=msg_data.get("mid", ""),
        )
        on_message(cm)

    def stop(self) -> None:
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        import requests

        headers = {"Content-Type": "application/json"}
        params = {"access_token": self._page_access_token}

        # Build the message payload
        if message.attachments:
            att = message.attachments[0]
            payload = {
                "recipient": {"id": chat_id},
                "message": {
                    "attachment": {
                        "type": att.get("type", "image"),
                        "payload": {"url": att.get("url", ""), "is_reusable": True},
                    }
                },
            }
        else:
            payload = {
                "recipient": {"id": chat_id},
                "message": {"text": message.text},
            }

        try:
            resp = requests.post(
                _SEND_API,
                params=params,
                headers=headers,
                json=payload,
                timeout=15,
            )
            data = resp.json()
            if "message_id" in data:
                return SendResult(success=True, message_id=data["message_id"], raw=data)
            error_msg = data.get("error", {}).get("message", str(data))
            return SendResult(success=False, error=error_msg, raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))


# Auto-register
ChannelRegistry.register("messenger", MessengerPlugin)
