"""
IPC (Inter-Process Communication) 包
提供 Python 后端和 Web 前端之间的通信机制
"""

from .service import IPCService
from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response

__all__ = [
    'IPCService',
    'IPCAPI',
    'IPCRequest',
    'IPCResponse',
    'create_request',
    'create_error_response',
    'create_success_response'
] 