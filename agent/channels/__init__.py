"""
agent.channels — Multi-channel communication architecture.

Three-layer design:
  Layer 1: Channel Adapters (base.py + adapters/)
  Layer 2: Channel Manager (channel_manager.py)
  Layer 3: Bridge to agent pipeline (bridge.py)
"""
from agent.channels.base import (
    ChannelMessage,
    ChannelPlugin,
    ChannelStatus,
    MessageType,
    OutboundMessage,
    SendResult,
)
from agent.channels.bridge import ChannelBridge
from agent.channels.channel_manager import ChannelManager
from agent.channels.registry import ChannelRegistry

__all__ = [
    "ChannelPlugin",
    "ChannelMessage",
    "OutboundMessage",
    "SendResult",
    "ChannelStatus",
    "MessageType",
    "ChannelRegistry",
    "ChannelManager",
    "ChannelBridge",
]
