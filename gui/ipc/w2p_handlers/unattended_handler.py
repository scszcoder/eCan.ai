"""Settings -> unattended mode: start at logon + restart on crash/hang
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
        params = params or {}
        enabled = bool(params.get('enabled'))
        # Only pass allow_in_dev when the UI actually sent it: None means
        # "keep whatever is stored", so an older frontend that omits the key
        # cannot silently clear the user's dev opt-in.
        allow_in_dev = params.get('allow_in_dev')
        res = set_enabled(enabled, None if allow_in_dev is None else bool(allow_in_dev))
        out = status()
        if res.get('error'):
            out['error'] = res['error']
        return create_success_response(request, out)
    except Exception as e:
        return create_error_response(request, 'UNATTENDED_ERROR', str(e))


@IPCHandlerRegistry.handler('unattended.reset_breaker')
def handle_reset_breaker(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Settings -> "give it another chance" after the watchdog gave up.

    Exists because "the switch is on but eCan never starts" is otherwise a
    dead end: the crash-loop breaker (utils/watchdog_breaker.py) stops
    relaunching once a build has proven it cannot start, and the user needs a
    way to say "I fixed it, try again". It is bounded by the same per-storm
    cap as any other launch, so it cannot be used to build a relaunch loop.
    """
    try:
        from utils.unattended import reset_watchdog_breaker, status
        reset_watchdog_breaker()
        return create_success_response(request, status())
    except Exception as e:
        return create_error_response(request, 'UNATTENDED_ERROR', str(e))
