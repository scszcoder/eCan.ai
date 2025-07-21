"""
IPC (Inter-Process Communication) 包
提供 Python 后端和 Web 前端之间的通信机制
"""

from .webchannel_service import IPCWebChannelService
from .api import IPCAPI
from .types import IPCRequest, IPCResponse, create_request, create_error_response, create_success_response
from . import handlers  # 确保所有 handlers 被导入

__all__ = [
    'IPCWebChannelService',
    'IPCAPI',
    'IPCRequest',
    'IPCResponse',
    'create_request',
    'create_error_response',
    'create_success_response'
] 