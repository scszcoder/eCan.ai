"""Desktop GUI side of the fleet feed: watch the account's machines, send them commands.

The web app talks to the cloud channels itself; the desktop GUI asks the backend
(agent/fleet/activity_feed.py), which subscribes to fleet.feed while a drawer is
open and relays each machine's message back as a 'fleet_feed' push.
"""

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger

_COMMANDS = {"snapshot", "ping", "log_start", "log_stop"}


def _push(body: dict) -> None:
    try:
        from gui.ipc.api import IPCAPI
        IPCAPI.get_instance().push_fleet_feed(body)
    except Exception as e:
        logger.debug(f"[fleet_feed] push to GUI failed: {e}")


@IPCHandlerRegistry.handler('fleet_feed.watch')
def handle_watch(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    try:
        from agent.fleet.activity_feed import get_feed
        get_feed().watch(bool((params or {}).get('on', True)), push=_push)
        return create_success_response(request, {"watching": bool((params or {}).get('on', True))})
    except Exception as e:
        return create_error_response(request, 'FLEET_FEED_ERROR', str(e))


@IPCHandlerRegistry.handler('fleet_feed.command')
def handle_command(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    p = params or {}
    cmd = str(p.get('cmd') or '')
    if cmd not in _COMMANDS:
        return create_error_response(request, 'INVALID_PARAMS', f"unknown command {cmd!r}")
    extra = {k: p[k] for k in ('ttl_s', 'level') if p.get(k) is not None}
    try:
        from agent.fleet.activity_feed import get_feed
        get_feed().command(cmd, str(p.get('machine') or '*'), **extra)
        return create_success_response(request, {"sent": cmd})
    except Exception as e:
        return create_error_response(request, 'FLEET_FEED_ERROR', str(e))
