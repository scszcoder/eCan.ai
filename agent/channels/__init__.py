"""
Communications Channel Architecture for eCan.ai.

3-layer design:
  Layer 1: Channel Adapters (thin) — connect, listen, normalize, send
  Layer 2: Channel Manager (lifecycle) — start/stop/restart, status tracking
  Layer 3: Bridge to existing pipeline — ChannelMessage → req → event_routing → runner
"""

from agent.channels.base import (
    ChannelPlugin,
    ChannelMessage,
    OutboundMessage,
    SendResult,
    ChannelStatus,
)
from agent.channels.registry import ChannelRegistry
from agent.channels.channel_manager import ChannelManager
from agent.channels.bridge import ChannelBridge

__all__ = [
    "ChannelPlugin",
    "ChannelMessage",
    "OutboundMessage",
    "SendResult",
    "ChannelStatus",
    "ChannelRegistry",
    "ChannelManager",
    "ChannelBridge",
]
