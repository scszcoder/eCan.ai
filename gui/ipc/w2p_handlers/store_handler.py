"""Store handlers — where each store should run, and where it actually runs.

A thin window over ``agent.cloud_api.store_api``. The calls need the signed-in
session, which only the app holds, so this is the one place the owner can say
"store X runs on machine M" (``store_assign``) and see desired vs observed
placement side by side (``store_list``).

Registered as background handlers: each call is a network round trip of up to
20s, and must not run on the event loop.

A signed-out session or a cloud refusal is expected here, not a code bug, so it
is logged at WARNING and returned as a typed error the page can show.
"""

from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import (
    IPCRequest,
    IPCResponse,
    create_error_response,
    create_success_response,
)
from utils.logger_helper import logger_helper as logger


def _this_vehicle_id() -> str:
    """The id this machine's heartbeat registers — the one assign must use."""
    try:
        from app_context import AppContext
        from agent.ec_agents.vehicle_affinity import resolve_local_vehicle_id
        return resolve_local_vehicle_id(AppContext.get_main_window()) or ''
    except Exception as e:
        logger.warning(f"[store] could not resolve this machine's id: {e}")
        return ''


def _call(request: IPCRequest, action: str, fn) -> IPCResponse:
    from agent.cloud_api.store_api import StoreApiError, StoreApiUnavailable
    try:
        return create_success_response(request, fn())
    except ValueError as e:
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except StoreApiUnavailable as e:
        logger.warning(f"[store] {action} unavailable: {e}")
        return create_error_response(request, 'STORE_API_UNAVAILABLE', str(e))
    except StoreApiError as e:
        logger.warning(f"[store] {action} refused: {e}")
        return create_error_response(request, 'STORE_API_ERROR', str(e))
    except Exception as e:
        logger.error(f"[store] {action} failed: {e}")
        return create_error_response(request, 'STORE_ERROR', f"{action} failed: {e}")


@IPCHandlerRegistry.background_handler('store.list')
def handle_list(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Every store of this account, desired vs observed, plus this machine's id."""
    params = params or {}

    def run():
        from agent.cloud_api.store_api import store_list
        data = store_list(include_archived=bool(params.get('include_archived')))
        return {
            'stores': data.get('stores') or [],
            'needs_login': data.get('needsLogin', 0),
            'misplaced': data.get('misplaced', 0),
            'this_vehicle_id': _this_vehicle_id(),
        }
    return _call(request, 'store_list', run)


@IPCHandlerRegistry.background_handler('store.overview')
def handle_overview(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Every store with its placement AND its local picture, for the Stores page.

    Cloud (store_list): where it is assigned/running, login state, 30-day
    billed LLM cost. Local: the agents and tasks serving it and the outcomes
    recorded against it. A store known on only one side still shows, and a
    cloud that cannot be reached degrades to the local half with a reason.
    """
    params = params or {}
    try:
        from app_context import AppContext
        from agent.ec_agents.store_overview import local_store_overview
        mainwin = AppContext.get_main_window()
        local = local_store_overview(mainwin) if mainwin is not None else {}
    except Exception as e:
        logger.error(f"[store] local overview failed: {e}")
        local = {}

    cloud_rows, cloud_error = [], ''
    try:
        from agent.cloud_api.store_api import store_list
        cloud_rows = store_list(include_archived=bool(params.get('include_archived'))).get('stores') or []
    except Exception as e:
        cloud_error = str(e)
        logger.warning(f"[store] overview without cloud placement: {e}")

    # The local catalog: a record for every store we can see (seeded on first
    # sight), carrying the definition -- name, platform, URLs, login profile.
    catalog = {}
    try:
        from agent.ec_agents import store_catalog
        store_catalog.seed(mainwin, cloud_rows)
        catalog = {s['store_id']: s for s in mainwin.ec_db_mgr.store_service.list_stores(
            include_archived=bool(params.get('include_archived')))}
    except Exception as e:
        logger.warning(f"[store] catalog unavailable: {e}")

    empty_local = {'agents': [], 'tasks': [], 'meters': []}
    stores = []
    seen = set()
    for row in cloud_rows:
        sid = row.get('storeId')
        if not sid:
            continue
        seen.add(sid)
        stores.append({**row, 'local': local.get(sid, empty_local)})
    for sid, info in local.items():
        if sid not in seen:
            seen.add(sid)
            stores.append({'storeId': sid, 'status': 'active', 'local': info, 'cloudKnown': False})
    for sid, rec in catalog.items():
        if sid not in seen:
            stores.append({'storeId': sid, 'status': rec.get('status') or 'active',
                           'local': empty_local, 'cloudKnown': False})
    for s in stores:
        rec = catalog.get(s['storeId'])
        if rec:
            s['definition'] = {k: rec.get(k) for k in
                               ('name', 'platform', 'store_urls', 'browser_profile_id', 'source')}
            s['label'] = rec.get('name') or s.get('label')
            s['platform'] = s.get('platform') or rec.get('platform')
    return create_success_response(request, {
        'stores': stores,
        'this_vehicle_id': _this_vehicle_id(),
        'cloud_error': cloud_error,
    })


def _mainwin():
    from app_context import AppContext
    mw = AppContext.get_main_window()
    if mw is None:
        raise RuntimeError("the app is not ready yet")
    return mw


def _catalog_call(request: IPCRequest, action: str, fn) -> IPCResponse:
    try:
        return create_success_response(request, fn())
    except ValueError as e:
        return create_error_response(request, 'INVALID_PARAMS', str(e))
    except Exception as e:
        logger.error(f"[store] {action} failed: {e}")
        return create_error_response(request, 'STORE_ERROR', f"{action} failed: {e}")


@IPCHandlerRegistry.handler('store.catalog')
def handle_catalog(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """The local store definitions -- what Fast Deploy offers to deploy into."""
    def run():
        mw = _mainwin()
        from agent.ec_agents import store_catalog
        store_catalog.seed(mw)
        return {'stores': mw.ec_db_mgr.store_service.list_stores(
            include_archived=bool((params or {}).get('include_archived')))}
    return _catalog_call(request, 'store_catalog', run)


@IPCHandlerRegistry.background_handler('store.create')
def handle_create(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Define a store: {store_id, name, platform, store_urls, browser_profile_id, assign: here|none}."""
    def run():
        from agent.ec_agents import store_catalog
        return store_catalog.create_store(_mainwin(), params or {})
    return _catalog_call(request, 'store_create', run)


@IPCHandlerRegistry.handler('store.update')
def handle_update(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Edit a store's definition: {store_id, name?, platform?, store_urls?, browser_profile_id?}."""
    def run():
        from agent.ec_agents import store_catalog
        return store_catalog.update_store(_mainwin(), params or {})
    return _catalog_call(request, 'store_update', run)


@IPCHandlerRegistry.background_handler('store.assign')
def handle_assign(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Say where a store should run.

    ``this_machine: true`` assigns it here, resolved on the backend so the page
    never has to know the id; ``vehicle_id: null`` without it unassigns.
    """
    params = params or {}

    def run():
        from agent.cloud_api.store_api import store_assign
        if params.get('this_machine'):
            vehicle_id = _this_vehicle_id()
            if not vehicle_id:
                raise ValueError("this machine has no stable id yet; try again after it has signed in")
        else:
            vehicle_id = params.get('vehicle_id') or None
        data = store_assign(
            str(params.get('store_id') or ''), vehicle_id,
            platform=str(params.get('platform') or ''),
            label=str(params.get('label') or ''),
        )
        return {'store': data.get('store') or {}, 'warnings': data.get('warnings') or []}
    return _call(request, 'store_assign', run)


@IPCHandlerRegistry.background_handler('store.archive')
def handle_archive(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Hide a store from listings, or bring it back with ``restore: true``."""
    params = params or {}

    def run():
        from agent.cloud_api.store_api import store_archive
        return store_archive(str(params.get('store_id') or ''),
                             restore=bool(params.get('restore')))
    return _call(request, 'store_archive', run)
