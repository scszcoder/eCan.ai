"""为店铺运行一次: run a store-scoped skill once for one store (agent/ec_tasks/one_off.py).

The ``ecan skills run-for-store`` CLI command and the Skills page button both
call these handlers.
"""
from typing import Any, Dict, Optional

from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from utils.logger_helper import logger_helper as logger


def _mainwin():
    from app_context import AppContext
    return AppContext.get_main_window()


def _store_names(mainwin) -> Dict[str, str]:
    try:
        return {str(s.get("id")): str(s.get("name") or s.get("id"))
                for s in (mainwin.ec_db_mgr.store_service.list_stores() or [])}
    except Exception:
        return {}


@IPCHandlerRegistry.handler('skills.store_hosts')
def handle_store_hosts(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Stores a skill can be run once for: those whose agent runs in the app."""
    try:
        from agent.ec_tasks.one_off import store_hosts
        mw = _mainwin()
        names = _store_names(mw)
        hosts = [{**h, "store_name": names.get(h["store_id"], h["store_id"])} for h in store_hosts(mw)]
        return create_success_response(request, {"stores": hosts})
    except Exception as e:
        return create_error_response(request, 'STORE_HOSTS_ERROR', str(e))


@IPCHandlerRegistry.handler('skills.run_for_store')
def handle_run_for_store(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Queue one run of a skill for a store. Params: skill (id or name), store_id,
    test (optional: a trial run, its listed products are not billed)."""
    p = params or {}
    skill, store_id = str(p.get('skill') or p.get('skill_id') or ''), str(p.get('store_id') or '')
    if not skill or not store_id:
        return create_error_response(request, 'INVALID_PARAMS', 'skill and store_id are required')
    try:
        from agent.ec_tasks.one_off import run_for_store
        res = run_for_store(_mainwin(), skill, store_id, test=bool(p.get('test')))
        res["store_name"] = _store_names(_mainwin()).get(store_id, store_id)
        return create_success_response(request, res)
    except ValueError as e:
        return create_error_response(request, 'NOT_FOUND', str(e))
    except Exception as e:
        logger.warning(f"[one-off] run_for_store failed: {e}")
        return create_error_response(request, 'RUN_FOR_STORE_ERROR', str(e))
