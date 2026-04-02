"""
Channel IPC handlers — manage messaging channel config and lifecycle.

Exposed methods:
    get_channels              — return all channel configs + live status
    save_channel_config       — write channels.json and hot-reload
    start_channel             — start an individual channel
    stop_channel              — stop an individual channel
    get_whatsapp_qr           — proxy the QR code from the Baileys bridge
    send_channel_message      — send a text message through a channel (for testing)
    get_channel_test_messages — return buffered inbound messages for the test panel
"""
import json
import time
import traceback
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from app_context import AppContext
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

# ---------------------------------------------------------------------------
# In-memory ring buffer for test-panel message monitoring
# Holds the last 200 inbound messages across all channels.
# Populated by hooking into ChannelBridge.dispatch_inbound via install_test_tap().
# ---------------------------------------------------------------------------

_TEST_BUFFER: deque = deque(maxlen=200)
_TEST_TAP_INSTALLED = False


def _tap_fn(msg: Any) -> None:
    """The actual tap function appended to bridge._inbound_taps."""
    try:
        _TEST_BUFFER.append({
            "channel_id":   msg.channel_id,
            "chat_id":      msg.chat_id,
            "sender_id":    msg.sender_id,
            "sender_name":  msg.sender_name,
            "text":         msg.text,
            "message_type": msg.message_type.value if hasattr(msg.message_type, "value") else str(msg.message_type),
            "timestamp":    float(msg.timestamp) if isinstance(msg.timestamp, (int, float)) else time.time(),
            "received_at":  time.time(),  # wall-clock time we captured it, used for since_ts filtering
            "message_id":   msg.message_id,
        })
    except Exception:
        pass


def install_test_tap() -> None:
    """
    Register _tap_fn into ChannelBridge._inbound_taps.
    dispatch_inbound() iterates this list on every inbound message, so the
    tap works regardless of when it is registered relative to app startup.
    Safe to call multiple times — idempotent.
    """
    global _TEST_TAP_INSTALLED
    if _TEST_TAP_INSTALLED:
        return
    try:
        from agent.channels.bridge import register_inbound_tap
        register_inbound_tap(_tap_fn)
        _TEST_TAP_INSTALLED = True
        logger.info("[channel_handler] Test tap registered in ChannelBridge._inbound_taps")
    except Exception as e:
        logger.warning(f"[channel_handler] Could not install test tap: {e}")

# Eagerly install the tap at import time so inbound messages are captured
# even before the frontend opens the test panel and starts polling.
install_test_tap()

_CHANNELS_JSON = Path(__file__).resolve().parents[3] / "agent" / "agent_files" / "channels.json"


def _get_channel_manager():
    """Return the ChannelManager instance from the main window, or None."""
    main = AppContext.get_main_window()
    if main is None:
        return None
    return getattr(main, "channel_manager", None)


def _load_channels_json() -> Dict[str, Any]:
    try:
        with open(_CHANNELS_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"channels": {}}


def _save_channels_json(data: Dict[str, Any]) -> None:
    _CHANNELS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(_CHANNELS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# get_channels
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("get_channels")
def handle_get_channels(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return all channel configs from channels.json plus live runtime status."""
    try:
        raw = _load_channels_json()
        channels_cfg: Dict[str, Any] = raw.get("channels", raw)

        mgr = _get_channel_manager()
        live_status: Dict[str, Any] = mgr.get_all_status() if mgr else {}

        result = {}
        for cid, cfg in channels_cfg.items():
            status_info = live_status.get(cid, {})
            result[cid] = {
                "config": cfg,
                "status": status_info.get("status", "stopped"),
                "restart_count": status_info.get("restart_count", 0),
                "last_error": status_info.get("last_error"),
            }

        return create_success_response(request, {"channels": result})
    except Exception as e:
        logger.error(f"[channel_handler] get_channels error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "CHANNEL_ERROR", str(e))


# ---------------------------------------------------------------------------
# save_channel_config
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("save_channel_config")
def handle_save_channel_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Persist channels.json and hot-reload the changed channel.

    params:
        channel_id  — channel key, e.g. "whatsapp_baileys"
        config      — dict with the channel configuration fields
    """
    try:
        p = params or {}
        channel_id: str = p.get("channel_id", "")
        new_cfg: Dict[str, Any] = p.get("config", {})

        if not channel_id:
            return create_error_response(request, "INVALID_PARAMS", "channel_id is required")

        raw = _load_channels_json()
        if "channels" not in raw:
            raw["channels"] = {}
        raw["channels"][channel_id] = new_cfg
        _save_channels_json(raw)
        logger.info(f"[channel_handler] Saved config for channel: {channel_id}")

        # Hot-reload: stop old instance, re-register, start if enabled
        mgr = _get_channel_manager()
        if mgr:
            try:
                # Stop existing channel if running
                if channel_id in mgr._channels:
                    mgr.stop_channel(channel_id)
                    with mgr._lock:
                        del mgr._channels[channel_id]

                # Re-register and start if enabled
                if new_cfg.get("enabled", False):
                    mgr._register_channel(channel_id, new_cfg)
                    mgr.start_channel(channel_id)
                    logger.info(f"[channel_handler] Hot-reloaded and started channel: {channel_id}")
                else:
                    logger.info(f"[channel_handler] Channel {channel_id} disabled — not starting")
            except Exception as reload_err:
                logger.warning(f"[channel_handler] Hot-reload warning for {channel_id}: {reload_err}")

        return create_success_response(request, {"saved": True, "channel_id": channel_id})
    except Exception as e:
        logger.error(f"[channel_handler] save_channel_config error: {e}\n{traceback.format_exc()}")
        return create_error_response(request, "CHANNEL_SAVE_ERROR", str(e))


# ---------------------------------------------------------------------------
# start_channel / stop_channel
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("start_channel")
def handle_start_channel(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Start a single channel by channel_id."""
    try:
        channel_id: str = (params or {}).get("channel_id", "")
        if not channel_id:
            return create_error_response(request, "INVALID_PARAMS", "channel_id is required")

        mgr = _get_channel_manager()
        if mgr is None:
            return create_error_response(request, "NO_CHANNEL_MANAGER", "Channel manager not available")

        if channel_id not in mgr._channels:
            # Try to register it from the saved config
            raw = _load_channels_json()
            cfg = raw.get("channels", {}).get(channel_id)
            if not cfg:
                return create_error_response(request, "UNKNOWN_CHANNEL", f"No config for channel: {channel_id}")
            mgr._register_channel(channel_id, cfg)

        mgr.start_channel(channel_id)
        return create_success_response(request, {"started": True, "channel_id": channel_id})
    except Exception as e:
        logger.error(f"[channel_handler] start_channel error: {e}")
        return create_error_response(request, "CHANNEL_START_ERROR", str(e))


@IPCHandlerRegistry.handler("stop_channel")
def handle_stop_channel(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Stop a single channel by channel_id."""
    try:
        channel_id: str = (params or {}).get("channel_id", "")
        if not channel_id:
            return create_error_response(request, "INVALID_PARAMS", "channel_id is required")

        mgr = _get_channel_manager()
        if mgr is None:
            return create_error_response(request, "NO_CHANNEL_MANAGER", "Channel manager not available")

        mgr.stop_channel(channel_id)
        return create_success_response(request, {"stopped": True, "channel_id": channel_id})
    except Exception as e:
        logger.error(f"[channel_handler] stop_channel error: {e}")
        return create_error_response(request, "CHANNEL_STOP_ERROR", str(e))


# ---------------------------------------------------------------------------
# get_whatsapp_qr
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("get_whatsapp_qr")
def handle_get_whatsapp_qr(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Return the current WhatsApp Baileys QR code as base64 PNG.
    Proxies to the Node bridge via the Python adapter.

    params:
        channel_id  — optional, defaults to "whatsapp_baileys"
    """
    try:
        channel_id = (params or {}).get("channel_id", "whatsapp_baileys")
        mgr = _get_channel_manager()
        if mgr is None:
            return create_error_response(request, "NO_CHANNEL_MANAGER", "Channel manager not available")

        plugin = mgr.get_channel(channel_id)
        if plugin is None:
            return create_error_response(request, "UNKNOWN_CHANNEL", f"Channel not registered: {channel_id}")

        # The Baileys adapter exposes get_qr() and get_bridge_status()
        qr_b64 = None
        bridge_status = None
        if hasattr(plugin, "get_qr"):
            qr_b64 = plugin.get_qr()
        if hasattr(plugin, "get_bridge_status"):
            bridge_status = plugin.get_bridge_status()

        return create_success_response(request, {
            "qr_base64": qr_b64,
            "bridge_status": bridge_status,
        })
    except Exception as e:
        logger.error(f"[channel_handler] get_whatsapp_qr error: {e}")
        return create_error_response(request, "QR_ERROR", str(e))


# ---------------------------------------------------------------------------
# send_channel_message  (for skill-editor test panel)
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("send_channel_message")
def handle_send_channel_message(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Send a text message through a channel — used by the test panel.

    params:
        channel_id  — e.g. "whatsapp_baileys", "telegram"
        chat_id     — recipient JID / chat ID
        text        — message body
    """
    try:
        p = params or {}
        channel_id: str = p.get("channel_id", "")
        chat_id: str    = p.get("chat_id", "")
        text: str       = p.get("text", "")

        if not channel_id:
            return create_error_response(request, "INVALID_PARAMS", "channel_id is required")
        if not chat_id:
            return create_error_response(request, "INVALID_PARAMS", "chat_id is required")
        if not text:
            return create_error_response(request, "INVALID_PARAMS", "text is required")

        mgr = _get_channel_manager()
        if mgr is None:
            return create_error_response(request, "NO_CHANNEL_MANAGER", "Channel manager not available")

        install_test_tap()  # idempotent — registers tap into ChannelBridge global list

        # Resolve the JID so the frontend can confirm the actual recipient
        plugin = mgr.get_channel(channel_id)
        resolved_jid = chat_id
        if plugin and hasattr(plugin, "_normalize_jid"):
            resolved_jid = plugin._normalize_jid(chat_id)

        result = mgr.send_text(channel_id, chat_id, text)
        if result.success:
            return create_success_response(request, {
                "sent": True,
                "message_id": result.message_id,
                "resolved_jid": resolved_jid,
            })
        else:
            return create_error_response(request, "SEND_FAILED",
                f"Send to {resolved_jid} failed: {result.error or 'unknown error'}")
    except Exception as e:
        logger.error(f"[channel_handler] send_channel_message error: {e}")
        return create_error_response(request, "SEND_ERROR", str(e))


# ---------------------------------------------------------------------------
# get_channel_test_messages  (for skill-editor test panel)
# ---------------------------------------------------------------------------

@IPCHandlerRegistry.handler("get_channel_test_messages")
def handle_get_channel_test_messages(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Return buffered inbound messages for the test panel.

    params:
        channel_id  — optional filter; omit to get messages from all channels
        since_ts    — optional float Unix timestamp; only return messages after this time
    """
    try:
        p = params or {}
        channel_filter: str    = p.get("channel_id", "")
        since_ts: float        = float(p.get("since_ts", 0) or 0)

        install_test_tap()  # idempotent

        msgs: List[Dict[str, Any]] = [
            m for m in _TEST_BUFFER
            if (not channel_filter or m["channel_id"] == channel_filter)
            and m.get("received_at", m["timestamp"]) > since_ts
        ]
        return create_success_response(request, {"messages": msgs})
    except Exception as e:
        logger.error(f"[channel_handler] get_channel_test_messages error: {e}")
        return create_error_response(request, "GET_MESSAGES_ERROR", str(e))
