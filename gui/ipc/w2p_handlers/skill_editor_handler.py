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
from gui.ipc.context_bridge import get_handler_context

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

        ctx = get_handler_context(request, params)
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
        results = run_dev_skill(ctx.main_window, skill)
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

        ctx = get_handler_context(request, params)
        results = cancel_run_dev_skill(ctx.main_window)
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

        ctx = get_handler_context(request, params)
        results = pause_run_dev_skill(ctx.main_window)
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

        ctx = get_handler_context(request, params)
        results = resume_run_dev_skill(ctx.main_window)
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

        ctx = get_handler_context(request, params)
        results = step_run_dev_skill(ctx.main_window)
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

        ctx = get_handler_context(request, params)
        owner = params["username"]
        bps = [params["node_name"]]
        results = set_bps_dev_skill(ctx.main_window, bps)
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

        ctx = get_handler_context(request, params)
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

        results = clear_bps_dev_skill(ctx.main_window, bps)
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
        ctx = get_handler_context(request, params)
        agents: List[Dict[str, str]] = []

        if ctx:
            for ag in ctx.get_agents() or []:
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
        ctx = get_handler_context(request, params)
        queues: List[Dict[str, str]] = []

        if ctx:
            for ag in ctx.get_agents() or []:
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

        ctx = get_handler_context(request, params)
        # node_schemas is accessed via ctx property for desktop compatibility
        node_schemas = ctx.main_window.node_schemas if hasattr(ctx, 'ctx') and ctx.main_window else {}
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


@IPCHandlerRegistry.handler('sim_timer_event')
def handle_sim_timer_event(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Simulate a Timer Event trigger."""
    try:
        logger.info('[SIM][BE] sim_timer_event received')
        # TODO: Implement actual logic
        return create_success_response(request, {'ok': True, 'event': 'timer'})
    except Exception as e:
        logger.error(f"Error in sim_timer_event: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SIM_TIMER_ERROR', str(e))


@IPCHandlerRegistry.handler('sim_websocket_event')
def handle_sim_websocket_event(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Simulate a Websocket Event trigger."""
    try:
        logger.info('[SIM][BE] sim_websocket_event received')
        # TODO: Implement actual logic
        return create_success_response(request, {'ok': True, 'event': 'websocket'})
    except Exception as e:
        logger.error(f"Error in sim_websocket_event: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SIM_WEBSOCKET_ERROR', str(e))


@IPCHandlerRegistry.handler('sim_sse_event')
def handle_sim_sse_event(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Simulate an SSE Event trigger."""
    try:
        logger.info('[SIM][BE] sim_sse_event received')
        # TODO: Implement actual logic
        return create_success_response(request, {'ok': True, 'event': 'sse'})
    except Exception as e:
        logger.error(f"Error in sim_sse_event: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SIM_SSE_ERROR', str(e))


@IPCHandlerRegistry.handler('sim_webhook_event')
def handle_sim_webhook_event(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Simulate a Webhook Event trigger."""
    try:
        logger.info('[SIM][BE] sim_webhook_event received')
        # TODO: Implement actual logic
        return create_success_response(request, {'ok': True, 'event': 'webhook'})
    except Exception as e:
        logger.error(f"Error in sim_webhook_event: {e} {traceback.format_exc()}")
        return create_error_response(request, 'SIM_WEBHOOK_ERROR', str(e))


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
        ctx = get_handler_context(request, params)
        
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
                from config.app_info import app_info
                base_dir = Path(app_info.appdata_path)
                skill_file = base_dir / skill_file
            
            # Check if skillName changed - need to rename directory and files
            new_skill_name = skill_info.get('skillName', '')
            renamed = False
            new_file_path = None
            
            if new_skill_name and skill_file.exists():
                # Extract current skill name from path
                # Path format: .../xxx_skill/diagram_dir/xxx_skill.json
                current_file_stem = skill_file.stem  # e.g., "ff_skill"
                
                # Normalize names for comparison (both should end with _skill)
                expected_new_stem = new_skill_name if new_skill_name.endswith('_skill') else f"{new_skill_name}_skill"
                
                if current_file_stem != expected_new_stem:
                    logger.info(f"[AutoSave] Skill name changed: {current_file_stem} -> {expected_new_stem}")
                    
                    # Rename directory and files
                    try:
                        diagram_dir = skill_file.parent  # diagram_dir/
                        old_skill_root = diagram_dir.parent  # xxx_skill/
                        parent_of_skill_root = old_skill_root.parent  # my_skills/ or custom dir
                        
                        # New paths
                        new_skill_root = parent_of_skill_root / f"{expected_new_stem}"
                        new_diagram_dir = new_skill_root / "diagram_dir"
                        new_skill_file = new_diagram_dir / f"{expected_new_stem}.json"
                        new_bundle_file = new_diagram_dir / f"{expected_new_stem}_bundle.json"
                        
                        # Check if target already exists
                        if new_skill_root.exists() and new_skill_root != old_skill_root:
                            logger.warning(f"[AutoSave] Cannot rename: target directory already exists: {new_skill_root}")
                        else:
                            # Rename the skill root directory
                            if old_skill_root != new_skill_root:
                                import shutil
                                shutil.move(str(old_skill_root), str(new_skill_root))
                                logger.info(f"[AutoSave] Renamed directory: {old_skill_root} -> {new_skill_root}")
                            
                            # Rename files inside diagram_dir
                            old_json = new_diagram_dir / f"{current_file_stem}.json"
                            old_bundle = new_diagram_dir / f"{current_file_stem}_bundle.json"
                            
                            if old_json.exists() and old_json != new_skill_file:
                                old_json.rename(new_skill_file)
                                logger.info(f"[AutoSave] Renamed file: {old_json.name} -> {new_skill_file.name}")
                            
                            if old_bundle.exists() and old_bundle != new_bundle_file:
                                old_bundle.rename(new_bundle_file)
                                logger.info(f"[AutoSave] Renamed bundle: {old_bundle.name} -> {new_bundle_file.name}")
                            
                            # Update skill_file to new path
                            skill_file = new_skill_file
                            new_file_path = str(new_skill_file)
                            renamed = True
                            
                            # Update database record and in-memory skill
                            try:
                                if ctx:
                                    old_dir_name = old_skill_root.name  # e.g., "ff2_skill"
                                    old_base_name = old_dir_name.replace('_skill', '') if old_dir_name.endswith('_skill') else old_dir_name
                                    new_base_name = expected_new_stem.replace('_skill', '') if expected_new_stem.endswith('_skill') else expected_new_stem
                                    
                                    logger.info(f"[AutoSave] Looking for skill: old_dir={old_dir_name}, old_base={old_base_name}")
                                    
                                    # Update database
                                    db_updated = False
                                    if ctx.get_ec_db_mgr():
                                        skill_service = ctx.get_ec_db_mgr().get_skill_service()
                                        if skill_service:
                                            # Find skill by old path using search_skills
                                            all_skills = skill_service.search_skills()  # Returns list directly
                                            logger.info(f"[AutoSave] Found {len(all_skills)} skills in database")
                                            for skill in all_skills:
                                                skill_path = skill.get('path', '')
                                                skill_name_db = skill.get('name', '')
                                                if skill_path and old_dir_name in skill_path:
                                                    skill_id = skill.get('id')
                                                    update_result = skill_service.update_skill(skill_id, {
                                                        'name': expected_new_stem,
                                                        'path': str(new_skill_file),
                                                    })
                                                    if update_result.get('success'):
                                                        logger.info(f"[AutoSave] ✅ Database updated (ID: {skill_id})")
                                                        db_updated = True
                                                    else:
                                                        logger.warning(f"[AutoSave] ⚠️ Failed to update database: {update_result.get('error')}")
                                                    break
                                            if not db_updated:
                                                logger.info(f"[AutoSave] No matching skill found in database for path containing: {old_dir_name}")
                                    
                                    # Update in-memory skill list
                                    mem_updated = False
                                    if ctx.get_agent_skills():
                                        logger.info(f"[AutoSave] Found {len(ctx.get_agent_skills() or [])} skills in memory")
                                        for mem_skill in (ctx.get_agent_skills() or []):
                                            if hasattr(mem_skill, 'name'):
                                                skill_name = mem_skill.name
                                                skill_path = getattr(mem_skill, 'path', '')
                                                # Match by name or path
                                                name_match = skill_name == old_dir_name or skill_name == old_base_name
                                                path_match = skill_path and old_dir_name in skill_path
                                                
                                                if name_match or path_match:
                                                    old_skill_name = skill_name
                                                    # Keep the same format (with or without _skill)
                                                    if skill_name.endswith('_skill'):
                                                        mem_skill.name = expected_new_stem
                                                    else:
                                                        mem_skill.name = new_base_name
                                                    if hasattr(mem_skill, 'path'):
                                                        mem_skill.path = str(new_skill_file)
                                                    logger.info(f"[AutoSave] ✅ In-memory skill updated: {old_skill_name} -> {mem_skill.name}")
                                                    mem_updated = True
                                                    break
                                        
                                        if not mem_updated:
                                            # Skill not in memory - load and add it
                                            skill_names = [getattr(s, 'name', 'N/A') for s in (ctx.get_agent_skills() or [])]
                                            logger.info(f"[AutoSave] No matching skill in memory. Looking for: {old_dir_name} or {old_base_name}")
                                            logger.info(f"[AutoSave] Available skills: {skill_names[:10]}...")
                                            
                                            # Load the renamed skill into memory
                                            try:
                                                from agent.ec_skills.build_agent_skills import load_from_diagram
                                                new_skill = load_from_diagram(Path(str(new_skill_file)))
                                                if new_skill:
                                                    agent_skills = ctx.get_agent_skills()
                                                    if agent_skills is not None:
                                                        agent_skills.append(new_skill)
                                                    logger.info(f"[AutoSave] ✅ New skill added to memory: {new_skill.name}")
                                                    mem_updated = True
                                            except Exception as load_err:
                                                logger.warning(f"[AutoSave] ⚠️ Failed to load skill into memory: {load_err}")
                                    else:
                                        logger.warning(f"[AutoSave] No agent_skills in memory")
                            except Exception as db_err:
                                logger.warning(f"[AutoSave] ⚠️ Error updating database/memory: {db_err}")
                            
                    except Exception as rename_err:
                        logger.error(f"[AutoSave] Failed to rename skill: {rename_err}")
                        # Continue with original path
            
            # Allow saving to new files (don't require file to exist)
            # This enables "Save As" functionality
            
            # AutoSave: Write directly to file WITHOUT syncing to cloud/database
            # This is just a local cache to prevent data loss
            # Real sync happens only when user explicitly clicks "Save"
            try:
                os.makedirs(skill_file.parent, exist_ok=True)
                with open(skill_file, 'w', encoding='utf-8') as sf:
                    json.dump(skill_info, sf, indent=2, ensure_ascii=False)
                logger.info(f"[AutoSave] Cached to local file: {skill_file} (no cloud sync)")
            except Exception as write_error:
                logger.error(f"[AutoSave] Failed to write file: {write_error}")
                return create_error_response(request, 'WRITE_ERROR', f"Failed to write file: {str(write_error)}")
            
            # Save bundle file (always save if we have sheets data)
            bundle_file_saved = False
            bundle_file = skill_file.parent / f"{skill_file.stem}_bundle.json"
            logger.debug(f"[AutoSave] sheets_data keys: {list(sheets_data.keys()) if sheets_data else 'None'}")
            if sheets_data:
                try:
                    bundle_data = _build_bundle_data(sheets_data)
                    with open(bundle_file, 'w', encoding='utf-8') as bf:
                        json.dump(bundle_data, bf, indent=2, ensure_ascii=False)
                    logger.info(f"[AutoSave] Saved to bundle file: {bundle_file} ({len(bundle_data.get('sheets', []))} sheets)")
                    bundle_file_saved = True
                except Exception as bundle_error:
                    logger.warning(f"[AutoSave] Failed to save bundle: {bundle_error}")
            
            # Update recent files list
            skill_name = skill_info.get('skillName', Path(current_file_path).stem)
            _update_recent_files(str(skill_file), skill_name)
            
            response_data = {
                'success': True,
                'filePath': str(skill_file),
                'bundleFileSynced': bundle_file_saved,
                'message': 'Skill saved successfully'
            }
            
            # If renamed, include new path info for frontend to update
            if renamed and new_file_path:
                response_data['renamed'] = True
                response_data['newFilePath'] = new_file_path
                response_data['message'] = f'Skill renamed and saved successfully'
            
            return create_success_response(request, response_data)
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


def _build_bundle_data(sheets_data: Dict[str, Any]) -> Dict[str, Any]:
    """Build bundle data from sheets store format.
    
    Args:
        sheets_data: Sheets data from frontend store
        
    Returns:
        Bundle data in the format expected by the skill editor
    """
    sheets_dict = sheets_data.get('sheets', {})
    order = sheets_data.get('order', [])
    open_tabs = sheets_data.get('openTabs', [])
    active_sheet_id = sheets_data.get('activeSheetId')
    
    # Build sheets array in order
    sheets_array = []
    for sheet_id in order:
        if sheet_id in sheets_dict:
            sheet = sheets_dict[sheet_id]
            sheets_array.append(sheet)
            # Log sheet document summary for debugging
            doc = sheet.get('document', {})
            node_count = len(doc.get('nodes', []))
            edge_count = len(doc.get('edges', []))
            logger.debug(f"[AutoSave] Sheet '{sheet_id}' ({sheet.get('name', 'unnamed')}): {node_count} nodes, {edge_count} edges")
    
    # Add any sheets not in order (shouldn't happen but be safe)
    for sheet_id, sheet in sheets_dict.items():
        if sheet_id not in order:
            sheets_array.append(sheet)
    
    # Determine main sheet id (first in order or 'main')
    main_sheet_id = order[0] if order else 'main'
    
    return {
        "mainSheetId": main_sheet_id,
        "sheets": sheets_array,
        "openTabs": open_tabs,
        "activeSheetId": active_sheet_id,
    }


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
        cache_dir = _get_editor_data_directory()
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

