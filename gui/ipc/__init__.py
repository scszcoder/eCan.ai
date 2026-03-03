"""
IPC (Inter-Process Communication) Package
Provides communication mechanism between Python backend and Web frontend
Uses HTTP GraphQL for requests and WebSocket for push events
"""

from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response
from . import handlers  # Ensure regular handlers are imported

__all__ = [
    'IPCAPI',
    'IPCRequest',
    'IPCResponse',
    'create_request',
    'create_error_response',
    'create_success_response'
]