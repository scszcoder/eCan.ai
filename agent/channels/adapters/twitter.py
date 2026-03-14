"""
X (formerly Twitter) channel adapter — DM webhook + v2 API.

Requires: ``requests``, ``requests-oauthlib`` (both in requirements-base.txt).
Config keys: ``api_key``, ``api_secret``, ``access_token``, ``access_token_secret``,
             ``bearer_token``, ``webhook_port`` (default 8445),
             ``env_name`` (Account Activity API environment label),
             ``default_agent_id`` (optional).

This adapter listens for Direct Messages via the Account Activity API webhook
and sends replies via the X v2 DM endpoint. You need:
  1. An X Developer App with OAuth 1.0a credentials
  2. Account Activity API environment registered at developer.x.com
  3. The webhook URL (your server) registered and subscribed
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    MessageType,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)

_DM_SEND_URL = "https://api.x.com/2/dm_conversations/{conversation_id}/messages"
_DM_NEW_URL = "https://api.x.com/2/dm_conversations/with/{participant_id}/messages"


class TwitterPlugin(ChannelPlugin):
    channel_type = "twitter"

    def __init__(self):
        self._api_key: str = ""
        self._api_secret: str = ""
        self._access_token: str = ""
        self._access_token_secret: str = ""
        self._bearer_token: str = ""
        self._webhook_port: int = 8445
        self._env_name: str = "default"
        self._default_agent_id: Optional[str] = None
        self._server: Optional[HTTPServer] = None
        self._own_user_id: str = ""

    def configure(self, config: Dict[str, Any]) -> None:
        self._api_key = config.get("api_key", "")
        self._api_secret = config.get("api_secret", "")
        self._access_token = config.get("access_token", "")
        self._access_token_secret = config.get("access_token_secret", "")
        self._bearer_token = config.get("bearer_token", "")
        self._webhook_port = int(config.get("webhook_port", 8445))
        self._env_name = config.get("env_name", "default")
        self._default_agent_id = config.get("default_agent_id") or None
        if not self._api_key or not self._api_secret:
            raise ValueError("X/Twitter api_key and api_secret are required")
        if not self._access_token or not self._access_token_secret:
            raise ValueError("X/Twitter access_token and access_token_secret are required")

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: "Event") -> None:
        from threading import Event as _E
        plugin = self

        # Try to resolve own user_id for filtering self-sent DMs
        try:
            self._own_user_id = self._get_own_user_id()
            logger.info(f"[X/Twitter] Authenticated as user_id={self._own_user_id}")
        except Exception as e:
            logger.warning(f"[X/Twitter] Could not resolve own user_id: {e}")

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                """CRC challenge-response check for Account Activity API."""
                qs = parse_qs(urlparse(self.path).query)
                crc_token = qs.get("crc_token", [None])[0]
                if crc_token:
                    # Compute HMAC-SHA256 of crc_token with consumer secret
                    sha256_hash = hmac.new(
                        plugin._api_secret.encode("utf-8"),
                        crc_token.encode("utf-8"),
                        hashlib.sha256,
                    ).digest()
                    response_token = "sha256=" + base64.b64encode(sha256_hash).decode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"response_token": response_token}).encode())
                else:
                    self.send_response(200)
                    self.end_headers()

            def do_POST(self):
                """Receive Account Activity API events."""
                length = int(self.headers.get("Content-Length", 0))
                raw_body = self.rfile.read(length) if length else b""
                self.send_response(200)
                self.end_headers()

                try:
                    body = json.loads(raw_body) if raw_body else {}
                    # Direct Message events
                    dm_events = body.get("direct_message_events", [])
                    users = body.get("users", {})
                    for event in dm_events:
                        if event.get("type") != "message_create":
                            continue
                        msg_create = event.get("message_create", {})
                        sender_id = msg_create.get("sender_id", "")

                        # Skip messages from ourselves
                        if sender_id == plugin._own_user_id:
                            continue

                        target = msg_create.get("target", {})
                        recipient_id = target.get("recipient_id", "")
                        msg_data = msg_create.get("message_data", {})
                        text = msg_data.get("text", "")

                        # Build conversation_id (X uses sorted pair for 1:1 DMs)
                        pair = sorted([sender_id, recipient_id])
                        conversation_id = f"{pair[0]}-{pair[1]}"

                        # Sender info
                        sender_info = users.get(sender_id, {})
                        sender_name = sender_info.get("name", sender_info.get("screen_name", sender_id))

                        # Attachments
                        attachments = []
                        msg_type = MessageType.TEXT
                        attachment_data = msg_data.get("attachment", {})
                        if attachment_data:
                            media = attachment_data.get("media", {})
                            if media:
                                media_type = media.get("type", "photo")
                                attachments.append({
                                    "type": media_type,
                                    "url": media.get("media_url_https", media.get("media_url", "")),
                                    "media_id": str(media.get("id", "")),
                                })
                                if media_type == "photo":
                                    msg_type = MessageType.IMAGE
                                elif media_type == "video" or media_type == "animated_gif":
                                    msg_type = MessageType.VIDEO

                        cm = ChannelMessage(
                            channel_id="twitter",
                            chat_id=conversation_id,
                            sender_id=sender_id,
                            sender_name=sender_name,
                            text=text,
                            message_type=msg_type,
                            attachments=attachments,
                            raw=event,
                            timestamp=float(event.get("created_timestamp", time.time() * 1000)) / 1000.0,
                            message_id=event.get("id", ""),
                            metadata={
                                "recipient_id": recipient_id,
                                "sender_screen_name": sender_info.get("screen_name", ""),
                            },
                        )
                        on_message(cm)
                except Exception as e:
                    logger.error(f"[X/Twitter] Webhook processing error: {e}")

            def log_message(self, format, *args):
                pass  # suppress access logs

        self._server = HTTPServer(("0.0.0.0", self._webhook_port), Handler)
        self._server.timeout = 1
        logger.info(f"[X/Twitter] Webhook listening on port {self._webhook_port}")
        while not stop_event.is_set():
            self._server.handle_request()
        logger.info("[X/Twitter] Webhook server stopped")

    def stop(self) -> None:
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """
        Send a DM via X v2 API.

        chat_id can be either:
          - A conversation_id (e.g. "12345-67890" for existing conversation)
          - A participant user_id (for new conversation)
        """
        from requests_oauthlib import OAuth1Session

        oauth = OAuth1Session(
            self._api_key,
            client_secret=self._api_secret,
            resource_owner_key=self._access_token,
            resource_owner_secret=self._access_token_secret,
        )

        payload = {"text": message.text}

        try:
            # If chat_id contains a hyphen, treat as conversation_id
            if "-" in chat_id:
                url = _DM_SEND_URL.format(conversation_id=chat_id)
            else:
                # Treat as participant_id for new DM
                url = _DM_NEW_URL.format(participant_id=chat_id)

            resp = oauth.post(url, json=payload)
            data = resp.json() if resp.text else {}

            if resp.status_code in (200, 201):
                dm_event = data.get("dm_event", {})
                return SendResult(
                    success=True,
                    message_id=dm_event.get("dm_event_id", ""),
                    raw=data,
                )
            error = data.get("errors", [{}])[0] if data.get("errors") else data
            error_msg = error.get("message", str(data)) if isinstance(error, dict) else str(data)
            return SendResult(success=False, error=error_msg, raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _get_own_user_id(self) -> str:
        """Resolve the authenticated user's ID via v2 /users/me."""
        from requests_oauthlib import OAuth1Session

        oauth = OAuth1Session(
            self._api_key,
            client_secret=self._api_secret,
            resource_owner_key=self._access_token,
            resource_owner_secret=self._access_token_secret,
        )
        resp = oauth.get("https://api.x.com/2/users/me")
        data = resp.json()
        return data.get("data", {}).get("id", "")


# Auto-register
ChannelRegistry.register("twitter", TwitterPlugin)
