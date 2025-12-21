"""
IPC Transport Abstraction Layer

Provides a unified interface for different transport mechanisms:
- QtWebChannelTransport: For desktop Qt application
- WebSocketTransport: For web server deployment

This abstraction allows the same handlers to work with both transports.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, Callable
from .types import IPCRequest, IPCResponse


class IPCTransport(ABC):
    """Abstract base class for IPC transport mechanisms.
    
    All transport implementations must provide these methods to enable
    bidirectional communication between frontend and backend.
    """
    
    @abstractmethod
    def send_to_frontend(self, message: dict) -> None:
        """Send a message to the frontend.
        
        Args:
            message: Dictionary to be JSON-serialized and sent
        """
        pass
    
    @abstractmethod
    def set_message_handler(self, handler: Callable[[str], str]) -> None:
        """Set the handler for incoming messages from frontend.
        
        Args:
            handler: Function that takes a JSON string and returns a JSON response string
        """
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start the transport (connect, listen, etc.)"""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the transport and cleanup resources"""
        pass
    
    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected and ready"""
        pass


class TransportManager:
    """Manages the active transport and provides a unified interface.
    
    This is a singleton that holds the current transport instance.
    Handlers and other components use this to send messages without
    knowing which transport is active.
    """
    
    _instance: Optional['TransportManager'] = None
    _transport: Optional[IPCTransport] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> 'TransportManager':
        """Get the singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def set_transport(self, transport: IPCTransport) -> None:
        """Set the active transport.
        
        Args:
            transport: The transport instance to use
        """
        if self._transport is not None:
            self._transport.stop()
        self._transport = transport
    
    def get_transport(self) -> Optional[IPCTransport]:
        """Get the current transport"""
        return self._transport
    
    def send_to_frontend(self, message: dict) -> None:
        """Send a message via the active transport.
        
        Args:
            message: Dictionary to send
            
        Raises:
            RuntimeError: If no transport is configured
        """
        if self._transport is None:
            raise RuntimeError("No transport configured")
        self._transport.send_to_frontend(message)
    
    @property
    def is_connected(self) -> bool:
        """Check if transport is connected"""
        return self._transport is not None and self._transport.is_connected
