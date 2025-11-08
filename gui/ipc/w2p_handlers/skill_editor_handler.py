from typing import Any, Optional, Dict
import os
import json
from pathlib import Path

from gui.ipc.types import IPCRequest, IPCResponse, create_success_response, create_error_response
from gui.ipc.registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
import traceback
from app_context import AppContext

# @IPCHandlerRegistry.handler('run_skill')
# def handle_run_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
#     """Handle run skill workflow

#     Validate user credentials and return access token.

#     Args:
#         request: IPC request object
#         params: Request parameters, must contain 'username' and 'skill' fields
#                skill is JSON data where diagram is the flowchart JSON representation

#     Returns:
#         JSON formatted response message
#     """
#     try:
#         logger.debug(f"Get run skill handler called with request: {request}")

#         user = request["params"]["username"]
#         skill_info = request["params"]["skill"]
#         login: Login = AppContext.login

#         # Lazy import of heavy module
#         from agent.ec_skills.dev_utils.skill_dev_utils import run_dev_skill
#         results = run_dev_skill(login.main_win, skill_info)

#         return create_success_response(request, {
#             "results": results,
#             'message': "Run skill starts successful" if results["success"] else "Start skill run failed"
#         })

#     except Exception as e:
#         logger.error(f"Error in run skill handler: {e} {traceback.format_exc()}")
#         return create_error_response(
#             request,
#             'LOGIN_ERROR',
#             f"Error during start skill run: {str(e)}"
#         )


@IPCHandlerRegistry.handler('run_skill')
def handle_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        request_str = str(request)
        truncated_request = request_str[:300] + "..." if len(request_str) > 300 else request_str
        logger.debug(f"Get start skill run handler called with request: {truncated_request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import run_dev_skill

        main_window = AppContext.get_main_window()
        # Prefer params['skill'] (sent by FE) over legacy request.meta key
        skill_src = "params.skill" if isinstance(params, dict) and params.get("skill") is not None else "meta.skill_flowgram"
        skill = (params or {}).get("skill") if skill_src == "params.skill" else request.meta.get("skill_flowgram")
        logger.debug(f"[IPC][run_skill] skill source used: {skill_src}")
        try:
            diagram = (skill or {}).get("diagram") or {}
            wf = diagram.get("workFlow") or {}
            bundle = (diagram.get("bundle") or {}).get("sheets") or []
            logger.debug(f"[IPC][run_skill] incoming diagram.workFlow: nodes={len(wf.get('nodes', []))} edges={len(wf.get('edges', []))}")
            logger.debug(f"[IPC][run_skill] incoming diagram.bundle.sheets: count={len(bundle)} names={[ (s.get('name') or s.get('id')) for s in bundle if isinstance(s, dict) ]}")
        except Exception as _e:
            logger.debug(f"[IPC][run_skill] payload debug logging failed: {_e}")
        results = run_dev_skill(main_window, skill)
        return create_success_response(request, {
            "results": results,
            'message': "Start skill run successful" if results["success"] else "Start skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in run skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during start skill run: {str(e)}"
        )


@IPCHandlerRegistry.handler('cancel_run_skill')
def handle_cancel_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get cancel skill run called with request: {request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import cancel_run_dev_skill

        main_window = AppContext.get_main_window()
        results = cancel_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Cancelling skill run successful" if results["success"] else "Cancelling skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in cancel skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during cancelling skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('pause_run_skill')
def handle_pause_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get pause skill run request: {request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import pause_run_dev_skill

        main_window = AppContext.get_main_window()
        results = pause_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Get pause skill run successful" if results["success"] else "Pausing skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in pausing skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during pausing skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('resume_run_skill')
def handle_resume_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get resume skill run called with request: {request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import resume_run_dev_skill

        main_window = AppContext.get_main_window()
        results = resume_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "Resume skill run successful" if results["success"] else "Pausing skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in resume skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during resuming skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('step_run_skill')
def handle_step_run_skill(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get single step skill run called with request: {request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import step_run_dev_skill

        main_window = AppContext.get_main_window()
        results = step_run_dev_skill(main_window)
        return create_success_response(request, {
            "results": results,
            "message": "single step skill run successful" if results["success"] else "Single Stepping skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in single step skill run handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error single stepping skill run: {str(e)}"
        )

@IPCHandlerRegistry.handler('set_skill_breakpoints')
def handle_set_skill_breakpoints(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get setting skill breakpoints with request: {request}")

        # Lazy import to avoid slow startup
        from agent.ec_skills.dev_utils.skill_dev_utils import set_bps_dev_skill

        main_window = AppContext.get_main_window()
        owner = params["username"]
        bps = [params["node_name"]]
        results = set_bps_dev_skill(main_window, bps)
        results = {"success": True}
        return create_success_response(request, {
            "results": results,
            "message": "Setting skill breakpoints successful" if results["success"] else "Setting skill breakpoints failed"
        })

    except Exception as e:
        logger.error(f"Error in setting skill breakpoints handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during setting skill breakpoints: {str(e)}"
        )

@IPCHandlerRegistry.handler('clear_skill_breakpoints')
def handle_clear_skill_breakpoints(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get clearing skill breakpoints with request: {request}")

        # Lazy import to avoid slow startup; reuse dev utils clear implementation
        from agent.ec_skills.dev_utils.skill_dev_utils import clear_bps_dev_skill

        main_win = AppContext.get_main_window()
        owner = (params or {}).get("username")
        node_name = (params or {}).get("node_name")
        # Normalize node_name parameter to a list
        if isinstance(node_name, list):
            bps = node_name
        elif isinstance(node_name, str) and node_name:
            bps = [node_name]
        else:
            bps = []

        try:
            logger.info(f"[TaskRunner] Clearing breakpoints -> request nodes: {bps}")
        except Exception:
            pass

        results = clear_bps_dev_skill(main_win, bps)
        return create_success_response(request, {
            "results": results,
            'message': 'Clear skill breakpoints successful' if results.get('success') else 'Clear skill breakpoints failed'
        })

    except Exception as e:
        logger.error(f"Error in get available tests handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during clearning skill breakpoints: {str(e)}"
        )


@IPCHandlerRegistry.handler('request_skill_state')
def handle_request_skill_state(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get current skill run state: {request}")

        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'Request skill state successful'
        })

    except Exception as e:
        logger.error(f"Error in getting skill state handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during getting current skill state: {str(e)}"
        )

@IPCHandlerRegistry.handler('inject_skill_state')
def handle_inject_skill_state(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"injecting skill state: {request}")

        return create_success_response(request, {
            "tests": ["test1", "test2", "test3"],
            'message': 'Get available tests successful'
        })

    except Exception as e:
        logger.error(f"Error in inject skill state handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during injecting skill state: {str(e)}"
        )


@IPCHandlerRegistry.handler('load_skill_schemas')
def handle_load_skill_schemas(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handle get available test items request

    Args:
        request: IPC request object
        params: None

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"loading skill schemas: {request}")

        main_win = AppContext.get_main_window()
        node_schemas = main_win.node_schemas
        return create_success_response(request, {
            "node_schemas": node_schemas,
            'message': 'Load skill schemas successful'
        })

    except Exception as e:
        logger.error(f"Error in loading skill schemas handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during loading skill schemas: {str(e)}"
        )

# ----------------------
# Step-sim debug handlers
# ----------------------

@IPCHandlerRegistry.handler('setup_sim_step')
def handle_setup_sim_step(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Cache the provided sheets bundle and set current node to Start. Push initial run-status."""
    try:
        logger.info('[SIM][BE] setup_sim_step received')
        global _SIM_BUNDLE, _SIM_CURRENT_SHEET_ID, _SIM_CURRENT_NODE_ID, _SIM_COUNTER
        if not params or 'bundle' not in params:
            logger.warning('[SIM][BE] setup_sim_step missing bundle param')
            return create_error_response(request, 'INVALID_PARAMS', 'bundle is required')
        bundle = params['bundle']
        if not isinstance(bundle, dict) or 'sheets' not in bundle:
            logger.warning('[SIM][BE] setup_sim_step invalid bundle format')
            return create_error_response(request, 'INVALID_PARAMS', 'invalid bundle')

        _SIM_BUNDLE = bundle
        sheets = {s['id']: s for s in bundle.get('sheets', []) if isinstance(s, dict) and s.get('id')}
        # choose main or first
        main_id = bundle.get('mainSheetId') or (bundle.get('activeSheetId') if bundle.get('activeSheetId') in sheets else None)
        if not main_id and sheets:
            main_id = next(iter(sheets.keys()))
        _SIM_CURRENT_SHEET_ID = main_id

        # find a Start node on that sheet
        doc = (sheets.get(main_id) or {}).get('document') or {}
        nodes = doc.get('nodes', []) or []
        start_node = None
        for n in nodes:
            try:
                if n and (n.get('type') == 'start' or (n.get('data', {}).get('isStart') is True)):
                    start_node = n
                    break
            except Exception:
                pass
        # Fallback: choose node with no incoming edges
        if not start_node and nodes:
            try:
                edges = [e for e in (doc.get('edges', []) or []) if isinstance(e, dict)]
                def get_id(ref: Any) -> Optional[str]:
                    if ref is None:
                        return None
                    if isinstance(ref, str):
                        return ref
                    if isinstance(ref, dict):
                        return ref.get('id') or ref.get('nodeId') or ref.get('node')
                    return None
                incoming = set()
                for e in edges:
                    to_ref = e.get('to') or e.get('target')
                    to_id = get_id(to_ref)
                    if to_id:
                        incoming.add(to_id)
                for n in nodes:
                    nid = n.get('id')
                    if nid and nid not in incoming:
                        start_node = n
                        break
            except Exception as _e:
                logger.debug(f"[SIM][BE] setup_sim_step fallback start detection error: {_e}")
        if not start_node and nodes:
            start_node = nodes[0]
        _SIM_CURRENT_NODE_ID = (start_node or {}).get('id')
        _SIM_COUNTER = 0

        logger.info(f"[SIM][BE] setup_sim_step chosen sheet={_SIM_CURRENT_SHEET_ID}, node={_SIM_CURRENT_NODE_ID}")
        # push run status
        try:
            from gui.ipc.api import IPCAPI  # lazy import to avoid circular import
            ipc = IPCAPI.get_instance()
            ipc.update_run_stat(
                agent_task_id='sim',
                current_node=_SIM_CURRENT_NODE_ID or '',
                status='running',
                langgraph_state={
                    'nodeState': {'attributes': {'counter': _SIM_COUNTER}},
                },
                timestamp=None,
                callback=None,
            )
        except Exception as e:
            logger.warning(f"[setup_sim_step] failed to push run status: {e}")

        logger.info('[SIM][BE] setup_sim_step completed')
        return create_success_response(request, {'ok': True, 'current_sheet': _SIM_CURRENT_SHEET_ID, 'current_node': _SIM_CURRENT_NODE_ID})
    except Exception as e:
        logger.error(f"Error in setup_sim_step: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SETUP_SIM_ERROR', str(e))


@IPCHandlerRegistry.handler('step_sim')
def handle_step_sim(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Advance to the next node (first outgoing edge) and push run-status update with counter++."""
    try:
        logger.info('[SIM][BE] step_sim received')
        global _SIM_BUNDLE, _SIM_CURRENT_SHEET_ID, _SIM_CURRENT_NODE_ID, _SIM_COUNTER
        if not _SIM_BUNDLE or not _SIM_CURRENT_SHEET_ID:
            logger.warning('[SIM][BE] step_sim called before setup')
            return create_error_response(request, 'SIM_NOT_READY', 'Call setup_sim_step first')

        sheets = {s['id']: s for s in _SIM_BUNDLE.get('sheets', []) if isinstance(s, dict) and s.get('id')}
        sheet = sheets.get(_SIM_CURRENT_SHEET_ID) or {}
        doc = sheet.get('document') or {}
        nodes = {n.get('id'): n for n in (doc.get('nodes', []) or []) if isinstance(n, dict) and n.get('id')}
        edges = [e for e in (doc.get('edges', []) or []) if isinstance(e, dict)]

        curr = _SIM_CURRENT_NODE_ID
        next_id = None
        # helper to normalize node id from various schemas
        def norm_id(ref: Any) -> Optional[str]:
            if ref is None:
                return None
            if isinstance(ref, str):
                return ref
            if isinstance(ref, dict):
                # direct id fields
                direct = ref.get('id') or ref.get('nodeId')
                if isinstance(direct, str):
                    return direct
                # nested under 'node' or 'source'/'target' object
                node_ref = ref.get('node') or ref.get('source') or ref.get('target')
                if isinstance(node_ref, str):
                    return node_ref
                if isinstance(node_ref, dict):
                    nid = node_ref.get('id') or node_ref.get('nodeId')
                    if isinstance(nid, str):
                        return nid
                # some schemas use {'entity': {id}}
                entity_ref = ref.get('entity')
                if isinstance(entity_ref, dict):
                    nid = entity_ref.get('id') or entity_ref.get('nodeId')
                    if isinstance(nid, str):
                        return nid
            return None
        def get_endpoints(e: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
            # Try common schemas in order
            candidates = [
                (e.get('from'), e.get('to')),
                (e.get('source'), e.get('target')),
                ({'id': e.get('fromId')} if e.get('fromId') else None, {'id': e.get('toId')} if e.get('toId') else None),
                ({'id': e.get('sourceId')} if e.get('sourceId') else None, {'id': e.get('targetId')} if e.get('targetId') else None),
                # Flowgram uppercase style
                ({'id': e.get('sourceNodeID')} if e.get('sourceNodeID') else None, {'id': e.get('targetNodeID')} if e.get('targetNodeID') else None),
                ({'id': e.get('start')} if e.get('start') else None, {'id': e.get('end')} if e.get('end') else None),
            ]
            for frm_ref, to_ref in candidates:
                fid = norm_id(frm_ref)
                tid = norm_id(to_ref)
                if fid or tid:
                    return fid, tid
            return None, None

        # find first outgoing edge
        for e in edges:
            try:
                from_id, to_id = get_endpoints(e)
                if from_id == curr and to_id:
                    next_id = to_id
                    break
            except Exception as _e:
                logger.debug(f"[SIM][BE] step_sim edge parse error: {_e}")

        # if no outgoing, mark completed
        status = 'running'
        if next_id and next_id in nodes:
            _SIM_CURRENT_NODE_ID = next_id
        else:
            # Log diagnostic info to help FE understand why not advancing
            try:
                logger.info(f"[SIM][BE] no outgoing from {curr}. nodes={len(nodes)} edges={len(edges)}")
                sample = []
                for e in edges[:5]:
                    sample.append({
                        'from': (e.get('from') or e.get('source') or e.get('sourceNodeID')),
                        'to': (e.get('to') or e.get('target') or e.get('targetNodeID')),
                        'sourcePort': (e.get('sourcePort') or e.get('sourcePortID')),
                        'targetPort': (e.get('targetPort') or e.get('targetPortID')),
                    })
                logger.info(f"[SIM][BE] edge samples: {sample}")
                edge_keys = [list(e.keys()) for e in edges[:5]]
                logger.info(f"[SIM][BE] edge keys samples: {edge_keys}")
            except Exception:
                pass
            status = 'completed'

        _SIM_COUNTER += 1
        logger.info(f"[SIM][BE] step_sim curr={curr} next={_SIM_CURRENT_NODE_ID} status={status} counter={_SIM_COUNTER}")

        try:
            from gui.ipc.api import IPCAPI  # lazy import to avoid circular import
            ipc = IPCAPI.get_instance()
            ipc.update_run_stat(
                agent_task_id='sim',
                current_node=_SIM_CURRENT_NODE_ID or '',
                status=status,
                langgraph_state={
                    'nodeState': {'attributes': {'counter': _SIM_COUNTER}},
                },
                timestamp=None,
                callback=None,
            )
        except Exception as e:
            logger.warning(f"[step_sim] failed to push run status: {e}")

        logger.info('[SIM][BE] step_sim completed')
        return create_success_response(request, {'ok': True, 'current_node': _SIM_CURRENT_NODE_ID, 'status': status, 'counter': _SIM_COUNTER})
    except Exception as e:
        logger.error(f"Error in step_sim: {e} {traceback.format_exc()}")
        return create_error_response(request, 'STEP_SIM_ERROR', str(e))


@IPCHandlerRegistry.handler('test_langgraph2flowgram')
def handle_test_langgraph2flowgram(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Build a tiny LangGraph on backend and export it to flowgram test files."""
    try:
        from agent.ec_skills.langgraph2flowgram import test_langgraph2flowgram
        result = test_langgraph2flowgram()
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"Error in test_langgraph2flowgram: {e} {traceback.format_exc()}")
        return create_error_response(request, 'TEST_LG2FG_ERROR', str(e))


# ----------------------
# Skill Editor Cache Handlers
# ----------------------

def _get_cache_directory() -> Path:
    """Get the cache directory path in appdata.
    
    Returns:
        Path: Cache directory path (e.g., ~/Library/Application Support/eCan/skill-editor-cache)
    """
    try:
        # Use app_info.appdata_path as base directory
        from config.app_info import app_info
        
        base_dir = Path(app_info.appdata_path)
        cache_dir = base_dir / 'skill-editor-cache'
        
        # Create directory if it doesn't exist
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[EditorCache] Cache directory: {cache_dir}")
        return cache_dir
    except Exception as e:
        logger.error(f"[EditorCache] Failed to get cache directory: {e}")
        # Fallback to temp directory
        import tempfile
        fallback = Path(tempfile.gettempdir()) / 'eCan' / 'skill-editor-cache'
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(f"[EditorCache] Using fallback cache directory: {fallback}")
        return fallback


@IPCHandlerRegistry.handler('save_editor_cache')
def handle_save_editor_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save skill editor cache data to local storage.
    
    Args:
        request: IPC request object
        params: Cache data to save
        
    Returns:
        IPCResponse: Success or error response
    """
    try:
        logger.debug("[EditorCache] Saving editor cache")
        
        if not params or 'cacheData' not in params:
            return create_error_response(request, 'INVALID_PARAMS', 'cacheData is required')
        
        cache_data = params['cacheData']
        
        # Get cache directory
        cache_dir = _get_cache_directory()
        cache_file = cache_dir / 'editor-cache.json'
        
        # Save cache data to file
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"[EditorCache] Cache saved successfully to {cache_file}")
        logger.debug(f"[EditorCache] Cache data: hasSkillInfo={bool(cache_data.get('skillInfo'))}, "
                    f"sheetsCount={len(cache_data.get('sheets', {}).get('sheets', {}))}, "
                    f"timestamp={cache_data.get('timestamp')}")
        
        return create_success_response(request, {
            'success': True,
            'filePath': str(cache_file),
            'message': 'Editor cache saved successfully'
        })
        
    except Exception as e:
        logger.error(f"[EditorCache] Error saving cache: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SAVE_CACHE_ERROR', f"Failed to save cache: {str(e)}")


@IPCHandlerRegistry.handler('load_editor_cache')
def handle_load_editor_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Load skill editor cache data from local storage.
    
    Args:
        request: IPC request object
        params: Optional parameters
        
    Returns:
        IPCResponse: Cache data or error response
    """
    try:
        logger.debug("[EditorCache] Loading editor cache")
        
        # Get cache directory
        cache_dir = _get_cache_directory()
        cache_file = cache_dir / 'editor-cache.json'
        
        # Check if cache file exists
        if not cache_file.exists():
            logger.info("[EditorCache] No cache file found")
            return create_success_response(request, {
                'success': True,
                'cacheData': None,
                'message': 'No cache data found'
            })
        
        # Load cache data from file
        with open(cache_file, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        logger.info(f"[EditorCache] Cache loaded successfully from {cache_file}")
        logger.debug(f"[EditorCache] Cache data: hasSkillInfo={bool(cache_data.get('skillInfo'))}, "
                    f"sheetsCount={len(cache_data.get('sheets', {}).get('sheets', {}))}, "
                    f"timestamp={cache_data.get('timestamp')}")
        
        return create_success_response(request, {
            'success': True,
            'cacheData': cache_data,
            'filePath': str(cache_file),
            'message': 'Editor cache loaded successfully'
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"[EditorCache] Invalid JSON in cache file: {e}")
        return create_error_response(request, 'INVALID_CACHE_DATA', f"Cache file is corrupted: {str(e)}")
    except Exception as e:
        logger.error(f"[EditorCache] Error loading cache: {e} {traceback.format_exc()}")
        return create_error_response(request, 'LOAD_CACHE_ERROR', f"Failed to load cache: {str(e)}")


@IPCHandlerRegistry.handler('clear_editor_cache')
def handle_clear_editor_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Clear skill editor cache data from local storage.
    
    Args:
        request: IPC request object
        params: Optional parameters
        
    Returns:
        IPCResponse: Success or error response
    """
    try:
        logger.debug("[EditorCache] Clearing editor cache")
        
        # Get cache directory
        cache_dir = _get_cache_directory()
        cache_file = cache_dir / 'editor-cache.json'
        
        # Delete cache file if it exists
        if cache_file.exists():
            cache_file.unlink()
            logger.info(f"[EditorCache] Cache file deleted: {cache_file}")
        else:
            logger.info("[EditorCache] No cache file to delete")
        
        return create_success_response(request, {
            'success': True,
            'message': 'Editor cache cleared successfully'
        })
        
    except Exception as e:
        logger.error(f"[EditorCache] Error clearing cache: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLEAR_CACHE_ERROR', f"Failed to clear cache: {str(e)}")

