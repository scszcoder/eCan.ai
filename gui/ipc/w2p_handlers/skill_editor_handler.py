from typing import Any, Optional, Dict, List
import os
import json
from pathlib import Path
from datetime import datetime

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


@IPCHandlerRegistry.handler('get_editor_agents')
def handle_get_editor_agents(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return simplified agent list for Skill Editor dropdowns.

    Schema:
      {
        "agents": [{
          id, name, kind,
          description, provider, url,
          orgId, status, title, rank,
          skillsCount, tasksCount,
          avatar
        }],
        "defaults": {"top": "human"}
      }
    """
    try:
        main_window = AppContext.get_main_window()
        agents: List[Dict[str, str]] = []

        if main_window and hasattr(main_window, 'agents'):
            for ag in getattr(main_window, 'agents', []) or []:
                try:
                    # Prefer unified serialization from EC_Agent.to_dict for field consistency
                    ag_dict = {}
                    try:
                        if hasattr(ag, 'to_dict') and callable(getattr(ag, 'to_dict')):
                            ag_dict = ag.to_dict(owner=None) or {}
                    except Exception:
                        ag_dict = {}

                    card = getattr(ag, 'card', None)
                    agid = ag_dict.get('id') or (getattr(card, 'id', None) if card else None)
                    agname = ag_dict.get('name') or (getattr(card, 'name', None) if card else None)
                    if isinstance(agid, str) and isinstance(agname, str) and agid and agname:
                        # Derive optional fields safely using serialized dict as primary source
                        description = ag_dict.get('description') or (getattr(card, 'description', None) if card else None) or ''
                        provider = getattr(card, 'provider', None) if card else None
                        url = getattr(card, 'url', None) if card else None
                        org_id = ag_dict.get('org_id', None)
                        status = ag_dict.get('status', None) or getattr(ag, 'status', None)
                        title = ag_dict.get('title', None) or getattr(ag, 'title', None)
                        rank = ag_dict.get('rank', None) or getattr(ag, 'rank', None)
                        skills_list = ag_dict.get('skills', []) or []
                        tasks_list = ag_dict.get('tasks', []) or []
                        skills_count = len(skills_list) if isinstance(skills_list, list) else 0
                        tasks_count = len(tasks_list) if isinstance(tasks_list, list) else 0
                        avatar = ag_dict.get('avatar') if isinstance(ag_dict.get('avatar', None), dict) else None

                        agents.append({
                            'id': agid,
                            'name': agname,
                            'kind': 'agent',
                            'description': description,
                            'provider': provider,
                            'url': url,
                            # Include both org_id (snake_case) and orgId (camelCase) for compatibility
                            'org_id': org_id,
                            'orgId': org_id,
                            'status': status,
                            'title': title,
                            'rank': rank,
                            'skillsCount': skills_count,
                            'tasksCount': tasks_count,
                            'avatar': avatar,
                        })
                except Exception:
                    # Skip malformed agent entries
                    continue

        # Always include default Human option on top
        result = {
            'agents': [{
                'id': 'human',
                'name': 'Human',
                'kind': 'human',
                'description': 'Human operator',
                'provider': None,
                'url': None,
                'orgId': None,
                'status': 'active',
                'title': None,
                'rank': None,
                'skillsCount': 0,
                'tasksCount': 0,
                'avatar': None,
            }] + agents,
            'defaults': {'top': 'human'}
        }
        logger.info(f"[Editor] get_editor_agents -> total={len(result['agents'])}")
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"[Editor] get_editor_agents error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'GET_EDITOR_AGENTS_ERROR', str(e))


@IPCHandlerRegistry.handler('get_editor_pending_sources')
def handle_get_editor_pending_sources(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Return queues and events the Skill Editor can pend on.

    Schema:
      { "queues": [{id, name}], "events": [{id, name}] }
    """
    try:
        main_window = AppContext.get_main_window()
        queues: List[Dict[str, str]] = []

        if main_window and hasattr(main_window, 'agents'):
            for ag in getattr(main_window, 'agents', []) or []:
                try:
                    card = getattr(ag, 'card', None)
                    agid = getattr(card, 'id', None)
                    agname = getattr(card, 'name', None) or 'Agent'
                    if not isinstance(agid, str) or not agid:
                        continue

                    # Detect available queues from runtime agent if present
                    chat_q = None
                    work_q = None
                    try:
                        chat_q = ag.get_chat_msg_queue()
                    except Exception:
                        pass
                    try:
                        work_q = ag.get_work_msg_queue()
                    except Exception:
                        pass

                    if chat_q is not None:
                        queues.append({'id': f'agent:{agid}:chat', 'name': f'{agname} Chat'})
                    if work_q is not None:
                        queues.append({'id': f'agent:{agid}:work', 'name': f'{agname} Work'})
                except Exception:
                    continue

        # Provide a minimal, sensible set of event types
        events: List[Dict[str, str]] = [
            {'id': 'human_chat', 'name': 'Human Chat'},
            {'id': 'agent_message', 'name': 'Agent Message'},
            {'id': 'timer', 'name': 'Timer'},
        ]

        result = {'queues': queues, 'events': events}
        logger.info(f"[Editor] get_editor_pending_sources -> queues={len(queues)} events={len(events)}")
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"[Editor] get_editor_pending_sources error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'GET_EDITOR_PENDING_SOURCES_ERROR', str(e))


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

def _get_editor_data_directory() -> Path:
    """Get the skill editor data directory path in user's data directory.
    
    Returns:
        Path: Data directory path for storing recent-files.json etc.
              e.g., ~/.eCan/<user>/skill-editor-data/
    """
    try:
        from utils.user_path_helper import ensure_user_data_dir
        
        # Get user-specific data directory with skill-editor-data subdirectory
        data_dir = ensure_user_data_dir(subdir='skill-editor-data')
        return Path(data_dir)
    except Exception as e:
        logger.error(f"[SkillEditor] Failed to get data directory: {e}")
        # Fallback to temp directory
        import tempfile
        fallback = Path(tempfile.gettempdir()) / 'eCan' / 'skill-editor-data'
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning(f"[SkillEditor] Using fallback directory: {fallback}")
        return fallback


def _get_recent_files_path() -> Path:
    """Get the path to the recent files JSON file."""
    data_dir = _get_editor_data_directory()
    return data_dir / 'recent-files.json'


def _load_recent_files() -> list:
    """Load recent files list from disk."""
    try:
        recent_files_path = _get_recent_files_path()
        if recent_files_path.exists():
            with open(recent_files_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"[RecentFiles] Failed to load: {e}")
    return []


def _save_recent_files(recent_files: list) -> None:
    """Save recent files list to disk."""
    try:
        recent_files_path = _get_recent_files_path()
        with open(recent_files_path, 'w', encoding='utf-8') as f:
            json.dump(recent_files, f, indent=2, ensure_ascii=False)
        logger.debug(f"[RecentFiles] Saved {len(recent_files)} files")
    except Exception as e:
        logger.warning(f"[RecentFiles] Failed to save: {e}")


def _update_recent_files(file_path: str, skill_name: str = None) -> list:
    """Update recent files list with a new/updated file. Returns updated list."""
    MAX_RECENT_FILES = 10
    
    recent_files = _load_recent_files()
    
    # Remove existing entry for this file path
    recent_files = [f for f in recent_files if f.get('filePath') != file_path]
    
    # Add new entry at the beginning
    new_entry = {
        'filePath': file_path,
        'fileName': Path(file_path).name,
        'skillName': skill_name or Path(file_path).stem,
        'lastOpened': datetime.now().isoformat(),
    }
    recent_files.insert(0, new_entry)
    
    # Keep only the most recent files
    recent_files = recent_files[:MAX_RECENT_FILES]
    
    # Save to disk
    _save_recent_files(recent_files)
    
    return recent_files


@IPCHandlerRegistry.handler('save_editor_cache')
def handle_save_editor_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save skill directly to file (NEW: no cache layer, direct file save).
    
    Args:
        request: IPC request object
        params: Cache data containing skillInfo, sheets, and currentFilePath
        
    Returns:
        IPCResponse: Success or error response
    """
    try:
        if not params or 'cacheData' not in params:
            return create_error_response(request, 'INVALID_PARAMS', 'cacheData is required')
        
        cache_data = params['cacheData']
        current_file_path = cache_data.get('currentFilePath')
        skill_info = cache_data.get('skillInfo')
        sheets_data = cache_data.get('sheets', {})
        
        # NEW ARCHITECTURE: Save directly to file, no cache layer
        if current_file_path and skill_info:
            skill_file = Path(current_file_path)
            
            # Convert relative path to absolute path
            if not skill_file.is_absolute():
                app_context = AppContext()
                base_dir = Path(app_context.get_app_dir())
                skill_file = base_dir / skill_file
            
            if not skill_file.exists():
                return create_error_response(request, 'FILE_NOT_FOUND', f'Skill file not found: {skill_file}')
            
            # Save main skill file
            with open(skill_file, 'w', encoding='utf-8') as sf:
                json.dump(skill_info, sf, indent=2, ensure_ascii=False)
            logger.info(f"[AutoSave] Saved to skill file: {skill_file}")
            
            # Save bundle file if it exists
            bundle_file_saved = False
            bundle_file = skill_file.parent / f"{skill_file.stem}_bundle.json"
            if bundle_file.exists() and sheets_data:
                try:
                    bundle_data = {
                        "sheets": sheets_data.get('sheets', {}),
                        "order": sheets_data.get('order', []),
                    }
                    with open(bundle_file, 'w', encoding='utf-8') as bf:
                        json.dump(bundle_data, bf, indent=2, ensure_ascii=False)
                    logger.info(f"[AutoSave] Saved to bundle file: {bundle_file}")
                    bundle_file_saved = True
                except Exception as bundle_error:
                    logger.warning(f"[AutoSave] Failed to save bundle: {bundle_error}")
            
            # Update recent files list
            skill_name = skill_info.get('skillName', Path(current_file_path).stem)
            _update_recent_files(str(skill_file), skill_name)
            
            return create_success_response(request, {
                'success': True,
                'filePath': str(skill_file),
                'bundleFileSynced': bundle_file_saved,
                'message': 'Skill saved successfully'
            })
        else:
            # No file path - this is a new unsaved skill, return success but don't save
            logger.debug("[AutoSave] No file path, skipping save (new unsaved skill)")
            return create_success_response(request, {
                'success': True,
                'message': 'New unsaved skill, no file to save'
            })
        
    except Exception as e:
        logger.error(f"[AutoSave] Error saving skill: {e}\n{traceback.format_exc()}")
        return create_error_response(request, 'SAVE_ERROR', f"Failed to save skill: {str(e)}")


@IPCHandlerRegistry.handler('load_editor_cache')
def handle_load_editor_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Load editor state including recent files list.
    
    Args:
        request: IPC request object
        params: Optional parameters
        
    Returns:
        IPCResponse: Recent files list for auto-loading
    """
    try:
        # Load recent files list from backend
        recent_files = _load_recent_files()
        logger.debug(f"[AutoLoad] Loaded {len(recent_files)} recent files")
        
        return create_success_response(request, {
            'success': True,
            'cacheData': None,  # No cache, load from file
            'recentFiles': recent_files,
            'message': f'Loaded {len(recent_files)} recent files'
        })
        
    except Exception as e:
        logger.error(f"[AutoLoad] Error: {e}")
        return create_error_response(request, 'LOAD_ERROR', str(e))


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

