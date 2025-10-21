"""
IPC (Inter-Process Communication) Package
Provides communication mechanism between Python backend and Web frontend
"""


from .wc_service import IPCWCService
from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response
from . import handlers  # Ensure regular handlers are imported
# Also import file operation handlers so show_open_dialog/read/write are registered
from . import file_handlers  # noqa: F401

__all__ = [
    'IPCWCService',
    'IPCAPI',
    'IPCRequest',
    'IPCResponse',
    'create_request',
    'create_error_response',
    'create_success_response'
]