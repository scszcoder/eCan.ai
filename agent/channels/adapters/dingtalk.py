"""
DingTalk (钉钉) channel adapter — Stream Mode via dingtalk-stream SDK.

Requires: ``dingtalk-stream`` (in requirements-base.txt).
Config keys: ``client_id`` (AppKey), ``client_secret`` (AppSecret),
             ``default_agent_id`` (optional).

DingTalk Stream mode is preferred over Webhook because it doesn't require
a public endpoint — the SDK maintains a long-lived WebSocket to DingTalk's
servers, similar to Slack Socket Mode.
"""
from __future__ import annotations

import json
import logging
import time
from threading import Event
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


class DingTalkPlugin(ChannelPlugin):
    channel_type = "dingtalk"

    def __init__(self):
        self._client_id: str = ""
        self._client_secret: str = ""
        self._default_agent_id: Optional[str] = None
        self._client = None

    def configure(self, config: Dict[str, Any]) -> None:
        self._client_id = config.get("client_id", "")
        self._client_secret = config.get("client_secret", "")
        if not self._client_id or not self._client_secret:
            raise ValueError("DingTalk client_id (AppKey) and client_secret (AppSecret) are required")
        self._default_agent_id = config.get("default_agent_id") or None

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        import dingtalk_stream
        from dingtalk_stream import AckMessage

        plugin = self

        class BotHandler(dingtalk_stream.ChatbotHandler):
            """Handle incoming robot messages via DingTalk Stream."""

            async def process(self, callback: dingtalk_stream.CallbackMessage):
                try:
                    incoming = json.loads(callback.data)
                    # DingTalk robot message fields
                    sender_id = incoming.get("senderStaffId") or incoming.get("senderId", "")
                    sender_nick = incoming.get("senderNick", "")
                    conversation_id = incoming.get("conversationId", "")
                    msg_type = incoming.get("msgtype", "text")
                    text = ""
                    if msg_type == "text":
                        text = incoming.get("text", {}).get("content", "").strip()
                    elif msg_type == "richText":
                        # richText contains a list of segments
                        for seg in incoming.get("content", {}).get("richText", []):
                            if seg.get("text"):
                                text += seg["text"]
                    msg_id = incoming.get("msgId", "")
                    is_group = incoming.get("conversationType") == "2"

                    cm = ChannelMessage(
                        channel_id="dingtalk",
                        chat_id=conversation_id,
                        sender_id=sender_id,
                        sender_name=sender_nick,
                        text=text,
                        message_type=plugin._detect_type(msg_type),
                        raw=incoming,
                        timestamp=float(incoming.get("createAt", time.time() * 1000)) / 1000.0,
                        message_id=msg_id,
                        metadata={
                            "is_group": is_group,
                            "conversation_type": incoming.get("conversationType", ""),
                            "chatbot_userid": incoming.get("chatbotUserId", ""),
                            "session_webhook": incoming.get("sessionWebhook", ""),
                            "session_webhook_expired_time": incoming.get("sessionWebhookExpiredTime", 0),
                        },
                    )
                    on_message(cm)
                except Exception as e:
                    logger.error(f"[DingTalk] Message processing error: {e}")

                return AckMessage.STATUS_OK, "OK"

        credential = dingtalk_stream.Credential(self._client_id, self._client_secret)
        self._client = dingtalk_stream.DingTalkStreamClient(credential)
        self._client.register_callback_handler(
            dingtalk_stream.ChatbotMessage.TOPIC,
            BotHandler(),
        )
        logger.info("[DingTalk] Starting Stream client")
        self._client.start_forever()
        # start_forever() blocks; if it returns, wait for stop_event
        stop_event.wait()
        logger.info("[DingTalk] Stream client stopped")

    def stop(self) -> None:
        if self._client:
            try:
                self._client.stop()
            except Exception as e:
                logger.debug(f"[DingTalk] Error stopping client: {e}")
            self._client = None

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """
        Send a message via DingTalk.

        For robot replies, the recommended approach is to use the sessionWebhook
        URL provided in the inbound message (stored in metadata). This avoids
        needing a separate access_token for the OpenAPI.

        If no webhook is available, we fall back to the OpenAPI endpoint.
        """
        import requests

        # Try sessionWebhook first (simplest, no extra auth needed)
        # The caller would need to pass it via message.metadata
        webhook_url = message.metadata.get("session_webhook", "")
        if webhook_url:
            return self._send_via_webhook(webhook_url, message)

        # Fallback: use OpenAPI (requires access_token)
        return self._send_via_openapi(chat_id, message)

    def _send_via_webhook(self, webhook_url: str, message: OutboundMessage) -> SendResult:
        import requests

        payload = {
            "msgtype": "text",
            "text": {"content": message.text},
        }
        try:
            resp = requests.post(webhook_url, json=payload, timeout=10)
            data = resp.json()
            if data.get("errcode", -1) == 0:
                return SendResult(success=True, raw=data)
            return SendResult(success=False, error=data.get("errmsg", str(data)), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    def _send_via_openapi(self, conversation_id: str, message: OutboundMessage) -> SendResult:
        """Send via DingTalk OpenAPI (requires obtaining access_token)."""
        import requests

        # Step 1: Get access_token
        try:
            token_resp = requests.post(
                "https://api.dingtalk.com/v1.0/oauth2/accessToken",
                json={"appKey": self._client_id, "appSecret": self._client_secret},
                timeout=10,
            )
            token_data = token_resp.json()
            access_token = token_data.get("accessToken", "")
            if not access_token:
                return SendResult(success=False, error=f"Failed to get access_token: {token_data}")
        except Exception as e:
            return SendResult(success=False, error=f"Token request failed: {e}")

        # Step 2: Send message to conversation
        try:
            resp = requests.post(
                "https://api.dingtalk.com/v1.0/robot/groupMessages/send",
                headers={"x-acs-dingtalk-access-token": access_token},
                json={
                    "msgParam": json.dumps({"content": message.text}),
                    "msgKey": "sampleText",
                    "openConversationId": conversation_id,
                },
                timeout=10,
            )
            data = resp.json()
            if resp.status_code == 200:
                return SendResult(success=True, message_id=data.get("processQueryKey", ""), raw=data)
            return SendResult(success=False, error=str(data), raw=data)
        except Exception as e:
            return SendResult(success=False, error=str(e))

    @staticmethod
    def _detect_type(msg_type: str) -> MessageType:
        return {
            "text": MessageType.TEXT,
            "picture": MessageType.IMAGE,
            "richText": MessageType.TEXT,
            "video": MessageType.VIDEO,
            "audio": MessageType.AUDIO,
            "file": MessageType.FILE,
        }.get(msg_type, MessageType.UNKNOWN)


# Auto-register
ChannelRegistry.register("dingtalk", DingTalkPlugin)
