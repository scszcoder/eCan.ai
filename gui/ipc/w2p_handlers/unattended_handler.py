"""Settings → unattended mode: start at Windows logon + restart on crash/hang
(utils/unattended.py, utils/app_watchdog.py)."""
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response


@IPCHandlerRegistry.handler('unattended.get')
def handle_get(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        from utils.unattended import status
        return create_success_response(request, status())
    except Exception as e:
        return create_error_response(request, 'UNATTENDED_ERROR', str(e))


@IPCHandlerRegistry.handler('unattended.set')
def handle_set(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        from utils.unattended import set_enabled, status
        res = set_enabled(bool((params or {}).get('enabled')))
        out = status()
        if res.get('error'):
            out['error'] = res['error']
        return create_success_response(request, out)
    except Exception as e:
        return create_error_response(request, 'UNATTENDED_ERROR', str(e))
