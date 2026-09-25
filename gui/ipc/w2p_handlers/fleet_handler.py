"""Fleet transfers: fetch another machine's logs, move a store with its login.

A thin window over ``agent.fleet.transfers``; see docs/FLEET_TRANSFER_DESIGN.md.
Background handlers: every call is at least one cloud round trip.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _mainwin():
    from app_context import AppContext
    mw = AppContext.get_main_window()
    if mw is None:
        raise RuntimeError("not signed in")
    return mw


def _call(request: IPCRequest, action: str, fn) -> IPCResponse:
    from agent.cloud_api.store_api import StoreApiError, StoreApiUnavailable
    from agent.fleet.transfers import TransferError
    try:
        return create_success_response(request, fn())
    except (ValueError, TransferError) as e:
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except StoreApiUnavailable as e:
        logger.warning(f"[fleet] {action} unavailable: {e}")
        return create_error_response(request, 'FLEET_API_UNAVAILABLE', str(e))
    except StoreApiError as e:
        logger.warning(f"[fleet] {action} refused: {e}")
        return create_error_response(request, 'FLEET_API_ERROR', str(e))
    except Exception as e:
        logger.error(f"[fleet] {action} failed: {e}")
        return create_error_response(request, 'FLEET_ERROR', f"{action} failed: {e}")


@IPCHandlerRegistry.background_handler('fleet.fetch_logs')
def handle_fetch_logs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """params: {vehicle_id, hours?}"""
    p = params or {}
    from agent.fleet import transfers
    return _call(request, 'fetch_logs', lambda: {'transfer': transfers.request_logs(
        _mainwin(), str(p.get('vehicle_id') or ''), float(p.get('hours') or 24))})


@IPCHandlerRegistry.background_handler('fleet.move_store')
def handle_move_store(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """params: {store_id, vehicle_id, confirmed, profile_id?}

    ``confirmed`` is checked here and again in ``request_store_move``: the page's
    warning dialog is what makes this a user-commanded copy of a live login.
    """
    p = params or {}
    if p.get('confirmed') is not True:
        return create_error_response(request, 'CONFIRMATION_REQUIRED',
                                     "moving a store's login must be confirmed")
    from agent.fleet import transfers
    return _call(request, 'move_store', lambda: {'transfer': transfers.request_store_move(
        _mainwin(), str(p.get('store_id') or ''), str(p.get('vehicle_id') or ''),
        confirmed=True, profile_id=str(p.get('profile_id') or ''))})


@IPCHandlerRegistry.background_handler('fleet.transfers')
def handle_transfers(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    from agent.fleet import transfers
    return _call(request, 'transfers', lambda: {'transfers': transfers.list_transfers(_mainwin())})


@IPCHandlerRegistry.handler('fleet.open_downloads')
def handle_open_downloads(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Open the folder fetched logs land in (or the one file, when given)."""
    from agent.fleet.transfers import downloads_dir
    folder = downloads_dir()
    target = str((params or {}).get('path') or '')
    try:
        if target and Path(target).resolve().parent != folder.resolve():
            target = ''     # only ever reveal files in the downloads folder
        if sys.platform.startswith('win'):
            if target:
                subprocess.Popen(['explorer', '/select,', target])
            else:
                os.startfile(str(folder))  # noqa: S606
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', target] if target else ['open', str(folder)])
        else:
            subprocess.Popen(['xdg-open', str(folder)])
        return create_success_response(request, {'folder': str(folder)})
    except Exception as e:
        return create_error_response(request, 'FLEET_ERROR', f"could not open {folder}: {e}")
