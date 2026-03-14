"""
Channel plugin registry — singleton that discovers and stores adapter classes.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Dict, Optional, Type

logger = logging.getLogger(__name__)


class ChannelRegistry:
    """
    Singleton registry for ChannelPlugin implementations.

    Adapters auto-register themselves on import via ``register()``.
    ``discover_adapters()`` imports every module under ``agent.channels.adapters``
    so that side-effect registration happens automatically.
    """

    _instance: Optional["ChannelRegistry"] = None
    _plugins: Dict[str, Type] = {}

    def __new__(cls) -> "ChannelRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # -- explicit registration -------------------------------------------------

    @classmethod
    def register(cls, channel_type: str, plugin_class: Type) -> None:
        cls._plugins[channel_type] = plugin_class
        logger.debug(f"[ChannelRegistry] Registered adapter: {channel_type}")

    # -- lookup ----------------------------------------------------------------

    @classmethod
    def get(cls, channel_type: str) -> Optional[Type]:
        return cls._plugins.get(channel_type)

    @classmethod
    def all(cls) -> Dict[str, Type]:
        return dict(cls._plugins)

    # -- auto-discovery --------------------------------------------------------

    def discover_adapters(self) -> None:
        """Import all modules under ``agent.channels.adapters`` so adapters
        that call ``ChannelRegistry.register()`` at module level get picked up."""
        try:
            import agent.channels.adapters as pkg
            for importer, modname, ispkg in pkgutil.iter_modules(pkg.__path__):
                try:
                    importlib.import_module(f"agent.channels.adapters.{modname}")
                    logger.debug(f"[ChannelRegistry] Discovered adapter module: {modname}")
                except Exception as e:
                    logger.warning(f"[ChannelRegistry] Failed to import adapter {modname}: {e}")
        except Exception as e:
            logger.warning(f"[ChannelRegistry] Adapter discovery failed: {e}")
