"""
Chat service package.

This package provides chat-related functionality for the eCan.ai system.
It includes the chat service and utility functions for chat operations.
"""

# Lazy imports to avoid circular import issues
def __getattr__(name):
    if name == "gui_a2a_send_chat":
        from .chat_utils import gui_a2a_send_chat
        return gui_a2a_send_chat
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    'gui_a2a_send_chat'
]