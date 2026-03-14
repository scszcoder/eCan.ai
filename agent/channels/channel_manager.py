"""
Layer 2: Channel Manager — lifecycle controller.

Starts/stops channel adapters in dedicated threads, tracks runtime status,
and auto-restarts failed channels with exponential backoff.
"""

from __future__ import annotations

import json
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from utils.logger_helper import logger_helper as logger

from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    ChannelStatus,
    OutboundMessage,
    SendResult,
)
from agent.channels.registry import ChannelRegistry


# ---------------------------------------------------------------------------
# Restart policy
# ---------------------------------------------------------------------------

@dataclass
class RestartPolicy:
    max_retries: int = 5
    base_delay: float = 2.0        # seconds
    max_delay: float = 120.0       # seconds
    backoff_factor: float = 2.0


# ---------------------------------------------------------------------------
# Per-channel runtime state
# ---------------------------------------------------------------------------

@dataclass
class _ChannelRuntime:
    channel_id: str
    plugin: ChannelPlugin
    config: dict
    status: ChannelStatus = ChannelStatus.STOPPED
    thread: Optional[threading.Thread] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    last_start: Optional[float] = None
    last_stop: Optional[float] = None
    last_error: Optional[str] = None
    restart_count: int = 0


# ---------------------------------------------------------------------------
# Channel Manager
# ---------------------------------------------------------------------------

class ChannelManager:
    """
    Lifecycle manager for communication channels.

    Typical usage::

        mgr = ChannelManager(on_message=bridge.dispatch_inbound)
        mgr.load_config("agent/agent_files/channels.json")
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
        self._restart_policy = restart_policy or RestartPolicy()
        self._runtimes: Dict[str, _ChannelRuntime] = {}
        self._lock = threading.Lock()
        self._registry = ChannelRegistry()

    # ---- config ----

    def load_config(self, config_path: str | Path) -> None:
        """Load channel configs from a JSON file and register runtimes."""
        config_path = Path(config_path)
        if not config_path.exists():
            logger.info(f"[ChannelManager] No config file at {config_path} — no channels loaded")
            return

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                configs: dict = json.load(f)
        except Exception as exc:
            logger.error(f"[ChannelManager] Failed to read {config_path}: {exc}")
            return

        for channel_id, cfg in configs.items():
            if channel_id.startswith("_"):
                continue  # skip meta keys
            if not cfg.get("enabled", False):
                logger.debug(f"[ChannelManager] Channel '{channel_id}' disabled — skipping")
                continue
            self.register_channel(channel_id, cfg)

    def register_channel(self, channel_id: str, config: dict) -> bool:
        """Instantiate a plugin for *channel_id* and prepare it for start."""
        plugin_cls = self._registry.get(channel_id)
        if plugin_cls is None:
            logger.warning(f"[ChannelManager] No plugin registered for '{channel_id}'")
            return False

        try:
            plugin = plugin_cls()
            plugin.configure(config)
        except Exception as exc:
            logger.error(f"[ChannelManager] configure() failed for '{channel_id}': {exc}")
            return False

        with self._lock:
            self._runtimes[channel_id] = _ChannelRuntime(
                channel_id=channel_id,
                plugin=plugin,
                config=config,
            )
        logger.info(f"[ChannelManager] Channel '{channel_id}' registered")
        return True

    # ---- lifecycle ----

    def start_all(self) -> None:
        """Start all registered (and enabled) channels."""
        with self._lock:
            ids = list(self._runtimes.keys())
        for cid in ids:
            self.start_channel(cid)

    def stop_all(self) -> None:
        """Gracefully stop every running channel."""
        with self._lock:
            ids = list(self._runtimes.keys())
        for cid in ids:
            self.stop_channel(cid)

    def start_channel(self, channel_id: str) -> bool:
        with self._lock:
            rt = self._runtimes.get(channel_id)
            if rt is None:
                logger.warning(f"[ChannelManager] Unknown channel '{channel_id}'")
                return False
            if rt.status == ChannelStatus.RUNNING:
                logger.debug(f"[ChannelManager] '{channel_id}' already running")
                return True

            rt.stop_event.clear()
            rt.status = ChannelStatus.STARTING
            rt.last_start = time.time()

            t = threading.Thread(
                target=self._run_channel,
                args=(rt,),
                name=f"channel-{channel_id}",
                daemon=True,
            )
            rt.thread = t
            t.start()
        logger.info(f"[ChannelManager] Starting channel '{channel_id}'")
        return True

    def stop_channel(self, channel_id: str) -> None:
        with self._lock:
            rt = self._runtimes.get(channel_id)
            if rt is None:
                return
            if rt.status in (ChannelStatus.STOPPED, ChannelStatus.STOPPING):
                return
            rt.status = ChannelStatus.STOPPING

        rt.stop_event.set()
        try:
            rt.plugin.stop()
        except Exception as exc:
            logger.warning(f"[ChannelManager] stop() error for '{channel_id}': {exc}")

        if rt.thread and rt.thread.is_alive():
            rt.thread.join(timeout=10.0)

        with self._lock:
            rt.status = ChannelStatus.STOPPED
            rt.last_stop = time.time()
            rt.thread = None

        logger.info(f"[ChannelManager] Stopped channel '{channel_id}'")

    def restart_channel(self, channel_id: str) -> bool:
        self.stop_channel(channel_id)
        return self.start_channel(channel_id)

    # ---- status ----

    def get_status(self, channel_id: str) -> Optional[dict]:
        with self._lock:
            rt = self._runtimes.get(channel_id)
            if rt is None:
                return None
            extra = {}
            try:
                extra = rt.plugin.get_status_extra()
            except Exception:
                pass
            return {
                "channel_id": channel_id,
                "status": rt.status.value,
                "display_name": rt.plugin.display_name,
                "last_start": rt.last_start,
                "last_stop": rt.last_stop,
                "last_error": rt.last_error,
                "restart_count": rt.restart_count,
                **extra,
            }

    def get_all_statuses(self) -> List[dict]:
        with self._lock:
            ids = list(self._runtimes.keys())
        return [self.get_status(cid) for cid in ids if self.get_status(cid)]

    # ---- outbound ----

    def send(self, channel_id: str, chat_id: str, message: OutboundMessage) -> SendResult:
        """Send an outbound message through the named channel."""
        with self._lock:
            rt = self._runtimes.get(channel_id)
        if rt is None:
            return SendResult(success=False, error=f"Unknown channel: {channel_id}")
        if rt.status != ChannelStatus.RUNNING:
            return SendResult(success=False, error=f"Channel '{channel_id}' is not running (status={rt.status.value})")
        try:
            return rt.plugin.send(chat_id, message)
        except Exception as exc:
            logger.error(f"[ChannelManager] send() failed for '{channel_id}': {exc}")
            return SendResult(success=False, error=str(exc))

    def get_plugin(self, channel_id: str) -> Optional[ChannelPlugin]:
        with self._lock:
            rt = self._runtimes.get(channel_id)
            return rt.plugin if rt else None

    # ---- internal ----

    def _run_channel(self, rt: _ChannelRuntime) -> None:
        """Thread target — run the channel monitor with auto-restart."""
        policy = self._restart_policy
        attempt = 0

        while not rt.stop_event.is_set():
            try:
                with self._lock:
                    rt.status = ChannelStatus.RUNNING
                    rt.last_error = None
                logger.info(f"[ChannelManager] Channel '{rt.channel_id}' monitor started")

                rt.plugin.start(self._on_message, rt.stop_event)

                # start() returned normally — check if we should stop
                if rt.stop_event.is_set():
                    break
                # If start() returns without stop_event, treat as clean exit
                logger.info(f"[ChannelManager] Channel '{rt.channel_id}' monitor exited cleanly")
                break

            except Exception as exc:
                tb = traceback.format_exc()
                logger.error(f"[ChannelManager] Channel '{rt.channel_id}' crashed: {exc}\n{tb}")
                with self._lock:
                    rt.status = ChannelStatus.ERROR
                    rt.last_error = str(exc)
                    rt.restart_count += 1

                attempt += 1
                if attempt > policy.max_retries:
                    logger.error(
                        f"[ChannelManager] Channel '{rt.channel_id}' exceeded max retries "
                        f"({policy.max_retries}) — giving up"
                    )
                    break

                delay = min(
                    policy.base_delay * (policy.backoff_factor ** (attempt - 1)),
                    policy.max_delay,
                )
                logger.info(
                    f"[ChannelManager] Restarting '{rt.channel_id}' in {delay:.1f}s "
                    f"(attempt {attempt}/{policy.max_retries})"
                )
                rt.stop_event.wait(delay)
                if rt.stop_event.is_set():
                    break

                # Re-configure before restart in case config was updated
                try:
                    rt.plugin.configure(rt.config)
                except Exception as cfg_exc:
                    logger.error(f"[ChannelManager] Re-configure failed for '{rt.channel_id}': {cfg_exc}")
                    break

        with self._lock:
            if rt.status != ChannelStatus.STOPPED:
                rt.status = ChannelStatus.STOPPED
            rt.last_stop = time.time()
        logger.info(f"[ChannelManager] Channel '{rt.channel_id}' thread exiting")
