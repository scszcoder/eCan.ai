"""
Channel Manager — lifecycle controller for channel adapters.

Manages starting, stopping, restarting channels in dedicated threads,
tracks status per channel, and implements exponential backoff on crash.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    ChannelStatus,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Restart policy
# ---------------------------------------------------------------------------

@dataclass
class RestartPolicy:
    max_retries: int = 5
    base_delay: float = 2.0
    max_delay: float = 60.0
    backoff_factor: float = 2.0


# ---------------------------------------------------------------------------
# Per-channel runtime state
# ---------------------------------------------------------------------------

@dataclass
class _ChannelRuntime:
    channel_id: str
    plugin: ChannelPlugin
    config: Dict[str, Any]
    status: ChannelStatus = ChannelStatus.IDLE
    thread: Optional[threading.Thread] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    restart_count: int = 0
    last_error: Optional[str] = None


# ---------------------------------------------------------------------------
# Channel Manager
# ---------------------------------------------------------------------------

class ChannelManager:
    """
    Lifecycle manager for channel plugins.

    Usage::

        mgr = ChannelManager(on_message=bridge.dispatch_inbound)
        mgr.load_config(Path("agent/agent_files/channels.json"))
        mgr.start_all()
        ...
        mgr.stop_all()
    """

    def __init__(
        self,
        on_message: Callable[[ChannelMessage], None],
        restart_policy: Optional[RestartPolicy] = None,
    ):
        self._on_message = on_message
        self._policy = restart_policy or RestartPolicy()
        self._channels: Dict[str, _ChannelRuntime] = {}
        self._lock = threading.Lock()

    # -- config ----------------------------------------------------------------

    def load_config(self, config_path: Path) -> None:
        """Load channel configurations from a JSON file."""
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except FileNotFoundError:
            logger.warning(f"[ChannelManager] Config not found: {config_path}")
            return
        except json.JSONDecodeError as e:
            logger.error(f"[ChannelManager] Invalid JSON in {config_path}: {e}")
            return

        channels_cfg = raw.get("channels", raw)
        if isinstance(channels_cfg, dict):
            for channel_id, cfg in channels_cfg.items():
                if not cfg.get("enabled", False):
                    logger.debug(f"[ChannelManager] Channel {channel_id} disabled, skipping")
                    continue
                self._register_channel(channel_id, cfg)

    def _register_channel(self, channel_id: str, config: Dict[str, Any]) -> None:
        plugin_cls = ChannelRegistry.get(channel_id)
        if plugin_cls is None:
            logger.warning(f"[ChannelManager] No adapter registered for '{channel_id}'")
            return
        plugin = plugin_cls()
        try:
            plugin.configure(config)
        except Exception as e:
            logger.error(f"[ChannelManager] Failed to configure {channel_id}: {e}")
            return
        with self._lock:
            self._channels[channel_id] = _ChannelRuntime(
                channel_id=channel_id,
                plugin=plugin,
                config=config,
            )
        logger.info(f"[ChannelManager] Channel registered: {channel_id}")

    # -- lifecycle -------------------------------------------------------------

    def start_all(self) -> None:
        with self._lock:
            for cid in list(self._channels):
                self._start_channel_locked(cid)

    def start_channel(self, channel_id: str) -> None:
        with self._lock:
            self._start_channel_locked(channel_id)

    def _start_channel_locked(self, channel_id: str) -> None:
        rt = self._channels.get(channel_id)
        if rt is None:
            logger.warning(f"[ChannelManager] Unknown channel: {channel_id}")
            return
        if rt.status == ChannelStatus.RUNNING:
            return

        # Join any previous thread on this slot before replacing it,
        # otherwise restart storms accumulate zombie channel-* threads.
        if rt.thread and rt.thread.is_alive():
            logger.warning(
                f"[ChannelManager] Previous thread for {channel_id} still "
                "alive; joining before restart"
            )
            rt.stop_event.set()
            rt.thread.join(timeout=5)
        rt.thread = None

        rt.stop_event.clear()
        rt.status = ChannelStatus.STARTING
        rt.thread = threading.Thread(
            target=self._run_channel,
            args=(channel_id,),
            name=f"channel-{channel_id}",
            daemon=True,
        )
        rt.thread.start()
        logger.info(f"[ChannelManager] Started channel thread: {channel_id}")

    def stop_channel(self, channel_id: str) -> None:
        with self._lock:
            rt = self._channels.get(channel_id)
            if rt is None:
                return
            rt.status = ChannelStatus.STOPPING
            rt.stop_event.set()
        # Let plugin do extra cleanup
        try:
            rt.plugin.stop()
        except Exception as e:
            logger.debug(f"[ChannelManager] Error stopping {channel_id}: {e}")
        # Wait briefly for thread to exit
        if rt.thread and rt.thread.is_alive():
            rt.thread.join(timeout=5)
        with self._lock:
            rt.status = ChannelStatus.STOPPED
        logger.info(f"[ChannelManager] Stopped channel: {channel_id}")

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self._channels)
        for cid in ids:
            self.stop_channel(cid)

    # -- channel thread --------------------------------------------------------

    def _run_channel(self, channel_id: str) -> None:
        rt = self._channels[channel_id]
        try:
            rt.status = ChannelStatus.RUNNING
            rt.plugin.start(self._on_message, rt.stop_event)
        except Exception as e:
            rt.last_error = str(e)
            logger.error(f"[ChannelManager] Channel {channel_id} crashed: {e}")
            if not rt.stop_event.is_set():
                rt.status = ChannelStatus.ERROR
                self._maybe_restart(channel_id)
                return
        rt.status = ChannelStatus.STOPPED

    def _maybe_restart(self, channel_id: str) -> None:
        rt = self._channels.get(channel_id)
        if rt is None or rt.stop_event.is_set():
            return
        if rt.restart_count >= self._policy.max_retries:
            logger.error(f"[ChannelManager] {channel_id} exceeded max retries ({self._policy.max_retries})")
            return
        delay = min(
            self._policy.base_delay * (self._policy.backoff_factor ** rt.restart_count),
            self._policy.max_delay,
        )
        rt.restart_count += 1
        logger.info(f"[ChannelManager] Restarting {channel_id} in {delay:.1f}s (attempt {rt.restart_count})")
        time.sleep(delay)
        if not rt.stop_event.is_set():
            with self._lock:
                self._start_channel_locked(channel_id)

    # -- sending ---------------------------------------------------------------

    def send(self, channel_id: str, chat_id: str, message: OutboundMessage) -> SendResult:
        rt = self._channels.get(channel_id)
        if rt is None:
            return SendResult(success=False, error=f"Unknown channel: {channel_id}")
        if rt.status != ChannelStatus.RUNNING:
            return SendResult(success=False, error=f"Channel {channel_id} is {rt.status}")
        try:
            return rt.plugin.send(chat_id, message)
        except Exception as e:
            logger.error(f"[ChannelManager] Send failed on {channel_id}: {e}")
            return SendResult(success=False, error=str(e))

    def send_text(self, channel_id: str, chat_id: str, text: str) -> SendResult:
        return self.send(channel_id, chat_id, OutboundMessage(text=text))

    # -- status ----------------------------------------------------------------

    def get_status(self, channel_id: str) -> Optional[ChannelStatus]:
        rt = self._channels.get(channel_id)
        return rt.status if rt else None

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        result = {}
        for cid, rt in self._channels.items():
            result[cid] = {
                "status": rt.status.value,
                "restart_count": rt.restart_count,
                "last_error": rt.last_error,
            }
        return result

    def get_channel(self, channel_id: str) -> Optional[ChannelPlugin]:
        rt = self._channels.get(channel_id)
        return rt.plugin if rt else None
