"""
Layer 1: Channel Plugin Registry.

Discovers and registers channel adapters.  Channels can be registered
explicitly or auto-discovered from the ``agent.channels.adapters`` package.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, Optional, Type

from utils.logger_helper import logger_helper as logger

from agent.channels.base import ChannelPlugin


class ChannelRegistry:
    """Singleton registry of available channel plugin classes."""

    _instance: Optional["ChannelRegistry"] = None
    _plugins: Dict[str, Type[ChannelPlugin]]

    def __new__(cls) -> "ChannelRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
        return cls._instance

    # ---- registration ----

    def register(self, plugin_cls: Type[ChannelPlugin]) -> None:
        """Register a channel plugin class by its ``channel_id``."""
        # Instantiate temporarily to read the channel_id property
        # (all adapters must be constructable with no args for registration)
        try:
            tmp = plugin_cls()
            cid = tmp.channel_id
        except Exception:
            # If the plugin can't be instantiated without args, read from class
            cid = getattr(plugin_cls, "_channel_id", None)
            if cid is None:
                raise ValueError(
                    f"Cannot determine channel_id for {plugin_cls.__name__}. "
                    "Set a _channel_id class attribute or make the class "
                    "instantiable with no arguments."
                )
        self._plugins[cid] = plugin_cls
        logger.info(f"[ChannelRegistry] Registered channel plugin: {cid} ({plugin_cls.__name__})")

    def unregister(self, channel_id: str) -> None:
        self._plugins.pop(channel_id, None)

    # ---- lookup ----

    def get(self, channel_id: str) -> Optional[Type[ChannelPlugin]]:
        return self._plugins.get(channel_id)

    def list_ids(self) -> list:
        return list(self._plugins.keys())

    def list_all(self) -> Dict[str, Type[ChannelPlugin]]:
        return dict(self._plugins)

    # ---- auto-discovery ----

    def discover_adapters(self) -> None:
        """Import all modules in ``agent.channels.adapters`` so that
        adapters that call ``ChannelRegistry().register(...)`` at module
        level are picked up automatically."""
        try:
            import agent.channels.adapters as pkg
            for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
                try:
                    importlib.import_module(f"agent.channels.adapters.{modname}")
                    logger.debug(f"[ChannelRegistry] Discovered adapter module: {modname}")
                except Exception as exc:
                    logger.warning(f"[ChannelRegistry] Failed to import adapter {modname}: {exc}")
        except ImportError:
            logger.debug("[ChannelRegistry] No adapters package found — skipping discovery")
