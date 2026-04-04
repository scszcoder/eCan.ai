"""
WhatsApp Baileys adapter — connects to the local Node.js Baileys bridge.

The bridge (wabaileys-bridge/index.js) runs as a separate process and exposes:
  GET  /status   — connection status
  GET  /qr       — QR code base64 PNG
  POST /send     — send text  { jid, text }

Inbound messages arrive at a local Python HTTP webhook server that this
adapter starts on a configurable port (default: 5100).

Config keys (channels.json):
  bridge_url       — base URL of the Node bridge   (default: http://127.0.0.1:3210)
  webhook_port     — local port for inbound webhook (default: 5100)
  default_agent_id — agent that receives inbound messages
  bridge_env       — extra env vars forwarded when auto-starting the bridge
  auto_start_bridge — bool, start the Node bridge process automatically (default false)
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event
from typing import Any, Callable, Dict, Optional

import requests

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    MessageType,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Inbound webhook HTTP handler
# ---------------------------------------------------------------------------

class _WebhookHandler(BaseHTTPRequestHandler):
    """Tiny HTTP server that receives forwarded inbound messages from the Node bridge."""

    on_message_cb: Callable[[ChannelMessage], None] = None  # type: ignore[assignment]
    default_agent_id: Optional[str] = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            self.send_response(400)
            self.end_headers()
            return

        self.send_response(200)
        self.end_headers()

        if callable(self.on_message_cb):
            try:
                msg = ChannelMessage(
                    channel_id="whatsapp_baileys",
                    chat_id=payload.get("jid", ""),
                    sender_id=payload.get("sender_id", ""),
                    sender_name=payload.get("sender_name", ""),
                    text=payload.get("text", ""),
                    message_type=MessageType.TEXT if payload.get("message_type", "text") == "text" else MessageType.IMAGE,
                    raw=payload,
                    timestamp=payload.get("timestamp", time.time()),
                    metadata={"default_agent_id": self.default_agent_id} if self.default_agent_id else {},
                )
                self.on_message_cb(msg)
            except Exception as e:
                logger.error(f"[WaBaileys] Error handling inbound message: {e}")

    def log_message(self, fmt, *args):  # suppress default access log
        logger.debug(f"[WaBaileys webhook] {fmt % args}")


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class WhatsAppBaileysPlugin(ChannelPlugin):
    """
    WhatsApp channel via local Baileys Node.js bridge.
    No Meta/Facebook developer account required — uses QR pairing.
    """

    channel_type = "whatsapp_baileys"

    def __init__(self):
        self._bridge_url: str = "http://127.0.0.1:3210"
        self._webhook_port: int = 5100
        self._default_agent_id: Optional[str] = None
        self._auto_start_bridge: bool = False
        self._bridge_env: Dict[str, str] = {}
        self._bridge_proc: Optional[subprocess.Popen] = None
        self._webhook_server: Optional[HTTPServer] = None
        self._webhook_thread: Optional[threading.Thread] = None

    # -- ChannelPlugin interface -----------------------------------------------

    def configure(self, config: Dict[str, Any]) -> None:
        self._bridge_url = config.get("bridge_url", "http://127.0.0.1:3210").rstrip("/")
        self._webhook_port = int(config.get("webhook_port", 5100))
        self._default_agent_id = config.get("default_agent_id") or None
        self._auto_start_bridge = bool(config.get("auto_start_bridge", False))
        self._bridge_env = config.get("bridge_env", {})

    def start(self, on_message: Callable[[ChannelMessage], None], stop_event: Event) -> None:
        if self._auto_start_bridge:
            self._launch_bridge()

        self._start_webhook_server(on_message)

        logger.info(
            f"[WaBaileys] Started. Bridge={self._bridge_url}, webhook port={self._webhook_port}"
        )

        # Block until the channel manager signals us to stop
        while not stop_event.is_set():
            time.sleep(2)

    def stop(self) -> None:
        if self._webhook_server:
            try:
                self._webhook_server.shutdown()
            except Exception:
                pass
            self._webhook_server = None

        if self._bridge_proc and self._bridge_proc.poll() is None:
            try:
                self._bridge_proc.terminate()
                self._bridge_proc.wait(timeout=5)
            except Exception:
                pass
            self._bridge_proc = None

        logger.info("[WaBaileys] Stopped")

    def send(self, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send a text or media message via the Baileys bridge."""
        jid = self._normalize_jid(chat_id)
        try:
            if message.message_type in (MessageType.IMAGE, MessageType.VIDEO) and message.attachments:
                url = message.attachments[0].get("url", "")
                mimetype = message.attachments[0].get("mimetype", "image/jpeg")
                resp = requests.post(
                    f"{self._bridge_url}/send-media",
                    json={"jid": jid, "url": url, "caption": message.text, "mimetype": mimetype},
                    timeout=15,
                )
            else:
                resp = requests.post(
                    f"{self._bridge_url}/send",
                    json={"jid": jid, "text": message.text},
                    timeout=15,
                )
            resp.raise_for_status()
            data = resp.json()
            return SendResult(success=True, message_id=data.get("message_id"))
        except Exception as e:
            logger.error(f"[WaBaileys] Send failed for {jid}: {e}")
            return SendResult(success=False, error=str(e))

    # -- Extra capability: QR code fetch --------------------------------------

    def get_qr(self) -> Optional[str]:
        """Return the current QR code as base64 PNG, or None if already paired."""
        try:
            resp = requests.get(f"{self._bridge_url}/qr", timeout=5)
            if resp.status_code == 204:
                return None   # already connected
            return resp.json().get("qr_base64")
        except Exception as e:
            logger.warning(f"[WaBaileys] get_qr failed: {e}")
            return None

    def get_bridge_status(self) -> Dict[str, Any]:
        """Return status dict from the bridge {status, phone_number}."""
        try:
            resp = requests.get(f"{self._bridge_url}/status", timeout=5)
            return resp.json()
        except Exception as e:
            return {"status": "unreachable", "error": str(e)}

    # -- Internals ------------------------------------------------------------

    @staticmethod
    def _normalize_jid(chat_id: str) -> str:
        """Ensure chat_id is in Baileys JID format, e.g. 15551234567@s.whatsapp.net"""
        if "@" in chat_id:
            return chat_id
        digits = "".join(c for c in chat_id if c.isdigit())
        return f"{digits}@s.whatsapp.net"

    def _get_session_dir(self) -> Path:
        """Return a writable per-user path for WhatsApp session data."""
        import os, sys
        if sys.platform == "win32":
            base = Path(os.environ.get("APPDATA", Path.home())) / "eCan"
        elif sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / "eCan"
        else:
            base = Path.home() / ".config" / "ecan"
        session = base / "wa_session"
        session.mkdir(parents=True, exist_ok=True)
        return session

    def _launch_bridge(self) -> None:
        """Start the Baileys bridge as a subprocess.

        Packaged app: runs the pre-built standalone binary produced by
            `npm run build:win` (or build:mac-*/build:linux) located at
            wabaileys-bridge/dist/wa_bridge[.exe] next to the main executable.
        Development: falls back to `node index.js` in wabaileys-bridge/.
        """
        import os, sys

        port = self._bridge_url.rsplit(":", 1)[-1].split("/")[0]
        session_dir = self._get_session_dir()

        env = {
            "PORT": port,
            "WEBHOOK_URL": f"http://127.0.0.1:{self._webhook_port}/channel/whatsapp",
            "SESSION_DIR": str(session_dir),
            **self._bridge_env,
        }
        full_env = {**os.environ, **env}

        # --- Locate the bridge: bundled binary first, then dev source ----------
        exe_name = "wa_bridge.exe" if sys.platform == "win32" else (
            "wa_bridge_mac_arm64" if (sys.platform == "darwin" and
                                       __import__("platform").machine() == "arm64")
            else "wa_bridge_mac_x64" if sys.platform == "darwin"
            else "wa_bridge_linux"
        )

        if getattr(sys, "frozen", False):
            # PyInstaller: exe lives in Contents/MacOS/, Resources is at Contents/Resources/
            app_dir = Path(sys.executable).parent
            if sys.platform == "darwin":
                # macOS: Resources is a sibling of MacOS
                bundled = app_dir.parent / "Resources" / "wa_bridge" / exe_name
            elif sys.platform == "win32":
                # Windows: wa_bridge is next to the exe
                bundled = app_dir / "wa_bridge" / exe_name
            else:
                # Linux: wa_bridge is next to the exe
                bundled = app_dir / "wa_bridge" / exe_name
        else:
            app_dir = Path(__file__).resolve().parents[4]
            bundled = app_dir / "wabaileys-bridge" / "dist" / exe_name

        if bundled.exists():
            cmd = [str(bundled)]
            cwd = str(bundled.parent)
            logger.info(f"[WaBaileys] Using bundled bridge: {bundled}")
        else:
            # Development fallback — requires Node.js in PATH
            bridge_dir = Path(__file__).resolve().parents[4] / "wabaileys-bridge"
            if not (bridge_dir / "index.js").exists():
                logger.warning(f"[WaBaileys] Bridge not found at {bridge_dir}, skipping auto-start")
                return
            cmd = ["node", "index.js"]
            cwd = str(bridge_dir)
            logger.info(f"[WaBaileys] Using dev bridge (node index.js) at {bridge_dir}")

        try:
            self._bridge_proc = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=full_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
            logger.info(f"[WaBaileys] Bridge started (pid={self._bridge_proc.pid})")
            time.sleep(2)  # Give the bridge a moment to bind its port
        except FileNotFoundError:
            logger.error(f"[WaBaileys] Could not launch bridge — {cmd[0]} not found")
        except Exception as e:
            logger.error(f"[WaBaileys] Failed to start bridge: {e}")

    def _start_webhook_server(self, on_message: Callable[[ChannelMessage], None]) -> None:
        """Start the local HTTP server that receives forwarded inbound messages."""

        # Inject the callback into the handler class
        handler_cls = type(
            "_BoundHandler",
            (_WebhookHandler,),
            {
                "on_message_cb": staticmethod(on_message),
                "default_agent_id": self._default_agent_id,
            },
        )

        try:
            self._webhook_server = HTTPServer(("127.0.0.1", self._webhook_port), handler_cls)
        except OSError as e:
            logger.error(f"[WaBaileys] Cannot bind webhook on port {self._webhook_port}: {e}")
            return

        self._webhook_thread = threading.Thread(
            target=self._webhook_server.serve_forever,
            name="wa-baileys-webhook",
            daemon=True,
        )
        self._webhook_thread.start()
        logger.info(f"[WaBaileys] Webhook server listening on 127.0.0.1:{self._webhook_port}")


# ---------------------------------------------------------------------------
# Auto-register
# ---------------------------------------------------------------------------
ChannelRegistry.register("whatsapp_baileys", WhatsAppBaileysPlugin)
