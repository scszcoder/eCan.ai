"""
IPC (Inter-Process Communication) Package
Provides communication mechanism between Python backend and Web frontend
"""


from .wc_service import IPCWCService
from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response
from . import handlers  # Ensure regular handlers are imported

__all__ = [
    'IPCWCService',
    'IPCAPI',
    'IPCRequest',
    'IPCResponse',
    'create_request',
    'create_error_response',
    'create_success_response'
]