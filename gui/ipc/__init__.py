"""
IPC (Inter-Process Communication) 包
提供 Python 后端和 Web 前端之间的通信机制
"""


from .wc_service import IPCWCService
from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response
from . import handlers  # 确保常规 handlers 被导入
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