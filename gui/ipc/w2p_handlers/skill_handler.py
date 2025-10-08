import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict, Tuple
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from gui.LoginoutGUI import Login
from utils.logger_helper import logger_helper as logger

# --- Simple in-memory simulation state for step-sim debug ---
_SIM_BUNDLE: Optional[Dict[str, Any]] = None
_SIM_CURRENT_SHEET_ID: Optional[str] = None
_SIM_CURRENT_NODE_ID: Optional[str] = None
_SIM_COUNTER: int = 0

# Whitelist the debug endpoints to avoid auth friction during editor testing
IPCHandlerRegistry.add_to_whitelist('setup_sim_step')
IPCHandlerRegistry.add_to_whitelist('step_sim')
IPCHandlerRegistry.add_to_whitelist('test_langgraph2flowgram')


@IPCHandlerRegistry.handler('get_skills')
def handle_get_skills(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get skills list, supports dual data sources: local database + cloud data

    On startup, prioritizes reading from local database, builds test skills in memory,
    then requests cloud data. If cloud data exists, it overwrites local data and updates database.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' field

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get skills handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        logger.info(f"Getting skills for user: {username}")

        # Read skill data directly from memory (build_agent_skills has completed all data integration)
        try:
            main_window = AppContext.get_main_window()
            memory_skills = main_window.agent_skills or []
            logger.info(f"Found {len(memory_skills)} skills in memory (mainwin.agent_skills)")

            # Convert memory skills to dictionary format
            skills_dicts = []
            for i, sk in enumerate(memory_skills):
                try:
                    sk_dict = sk.to_dict()
                    # Ensure necessary fields exist
                    sk_dict['owner'] = username
                    if 'id' not in sk_dict:
                        sk_dict['id'] = f"skill_{i}"
                    skills_dicts.append(sk_dict)
                    logger.debug(f"Converted skill: {sk_dict.get('name', 'NO NAME')}")
                except Exception as e:
                    logger.error(f"Failed to convert skill {i}: {e}")

            logger.info(f"Returning {len(skills_dicts)} skills to frontend")

            resultJS = {
                'skills': skills_dicts,
                'message': 'Get skills successful',
                'source': 'memory'
            }
            return create_success_response(request, resultJS)

        except Exception as e:
            logger.error(f"Failed to get skills from memory: {e}")
            # Return empty list as fallback
            return create_success_response(request, {
                'skills': [],
                'message': 'No skills available',
                'source': 'empty'
            })

    except Exception as e:
        logger.error(f"Error in get skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_SKILLS_ERROR',
            f"Error during get skills: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('save_skills')
def handle_save_skills(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle save skills request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Save skills handler called with request: {request}")
        logger.debug("save skills:" + str(params))
        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']


        logger.info(f"save skills successful for user: {username}")
        return create_success_response(request, {
            'message': 'Save skills successful'
        })

    except Exception as e:
        logger.error(f"Error in save skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save skills: {str(e)}"
        )


@IPCHandlerRegistry.handler('save_skill')
def handle_save_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle saving skill workflow to local database

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill_info' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Save skill handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'skill_info'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save skill: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        skill_info = data['skill_info']
        skill_id = skill_info.get('id')

        if not skill_id:
            return create_error_response(request, 'INVALID_PARAMS', 'Skill ID is required for save operation')

        logger.info(f"Saving skill for user: {username}, skill_id: {skill_id}")

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Prepare skill data
        skill_data = _prepare_skill_data(skill_info, username, skill_id)

        # Check if skill exists
        existing_skill = skill_service.get_skill_by_id(skill_id)

        if existing_skill.get('success') and existing_skill.get('data'):
            # Update existing skill
            logger.info(f"Updating existing skill: {skill_id}")
            result = skill_service.update_skill(skill_id, skill_data)
        else:
            # Create new skill
            logger.info(f"Creating new skill: {skill_id}")
            result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Get the actual skill_id from database response (in case it was generated)
            actual_skill_id = result.get('id', skill_id)
            logger.info(f"Skill saved successfully: {skill_data['name']} (ID: {actual_skill_id})")

            # Update memory
            _update_skill_in_memory(actual_skill_id, skill_data)

            # Create clean response
            clean_skill_data = _create_clean_skill_response(actual_skill_id, skill_data)

            return create_success_response(request, {
                'message': 'Save skill successful',
                'skill_id': actual_skill_id,
                'data': clean_skill_data
            })
        else:
            logger.error(f"Failed to save skill: {result.get('error')}")
            return create_error_response(
                request,
                'SAVE_SKILL_ERROR',
                f"Failed to save skill: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in save skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_SKILL_ERROR',
            f"Error during save skill: {str(e)}"
        )
    

@IPCHandlerRegistry.handler('run_skill')
def handle_run_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle run skill workflow

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill' fields
               skill is JSON data where diagram is the flowchart JSON representation

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Get run skill handler called with request: {request}")

        user = request["params"]["username"]
        skill_info = request["params"]["skill"]
        login: Login = AppContext.login

        # Lazy import of heavy module
        from agent.ec_skills.dev_utils.skill_dev_utils import run_dev_skill
        results = run_dev_skill(login.main_win, skill_info)

        return create_success_response(request, {
            "results": results,
            'message': "Run skill starts successful" if results["success"] else "Start skill run failed"
        })

    except Exception as e:
        logger.error(f"Error in run skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during start skill run: {str(e)}"
        )



@IPCHandlerRegistry.handler('new_skill')
def handle_new_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle creating new skill and saving to local database

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'skill_info' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Create new skill handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'skill_info'])
        if not is_valid:
            logger.warning(f"Invalid parameters for create skill: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        skill_info = data['skill_info']

        logger.info(f"Creating new skill for user: {username}")

        # Get database service
        skill_service = _get_skill_service()
        if not skill_service:
            return create_error_response(request, 'SERVICE_ERROR', 'Database service not available')

        # Prepare skill data (without ID - let database generate it)
        skill_data = _prepare_skill_data(skill_info, username, skill_id=None)

        # Create new skill in database
        logger.info(f"Creating new skill: {skill_data['name']}")
        result = skill_service.add_skill(skill_data)

        if result.get('success'):
            # Get the database-generated skill ID
            skill_id = result.get('id')
            if not skill_id:
                logger.error("Database did not return skill ID after creation")
                return create_error_response(
                    request,
                    'CREATE_SKILL_ERROR',
                    'Database did not return skill ID'
                )

            logger.info(f"Skill created successfully: {skill_data['name']} (ID: {skill_id})")

            # Update memory
            _update_skill_in_memory(skill_id, skill_data)

            # Create clean response
            clean_skill_data = _create_clean_skill_response(skill_id, skill_data)

            return create_success_response(request, {
                'message': 'Create skill successful',
                'skill_id': skill_id,
                'data': clean_skill_data
            })
        else:
            logger.error(f"Failed to create skill: {result.get('error')}")
            return create_error_response(
                request,
                'CREATE_SKILL_ERROR',
                f"Failed to create skill: {result.get('error')}"
            )

    except Exception as e:
        logger.error(f"Error in create skill handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'CREATE_SKILL_ERROR',
            f"Error during create skill: {str(e)}"
        )


@IPCHandlerRegistry.handler('new_skills')
def handle_new_skills(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle create new skills request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Create skills handler called with request: {request}")
        logger.debug("create skills:" + str(params))
        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for create skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']


        logger.info(f"create skills successful for user: {username}")
        return create_success_response(request, {
            'message': 'Create skills successful'
        })

    except Exception as e:
        logger.error(f"Error in create skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during create skills: {str(e)}"
        )




@IPCHandlerRegistry.handler('delete_skills')
def handle_delete_skills(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle delete skills request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        JSON formatted response message
    """
    try:
        logger.debug(f"Delete skills handler called with request: {request}")
        logger.debug("delete skills:" + str(params))
        # Validate parameters
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for delete skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']


        logger.info(f"delete skills successful for user: {username}")
        return create_success_response(request, {
            'message': 'Delete skills successful'
        })

    except Exception as e:
        logger.error(f"Error in delete skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during delete skills: {str(e)}"
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


# ============================================================================
# Helper Functions for Skill Management
# ============================================================================

def _get_skill_service():
    """Get skill service from mainwin (uses correct user-specific database path)

    Returns:
        skill_service: Database skill service instance, or None if not available
    """
    main_window = AppContext.get_main_window()
    if main_window and hasattr(main_window, 'ec_db_mgr'):
        return main_window.ec_db_mgr.skill_service
    else:
        logger.error("[skill_handler] mainwin.ec_db_mgr not available - cannot access database")
        return None


def _prepare_skill_data(skill_info: Dict[str, Any], username: str, skill_id: Optional[str] = None) -> Dict[str, Any]:
    """Prepare skill data for database storage

    Args:
        skill_info: Raw skill information from frontend
        username: Owner username
        skill_id: Optional skill ID (if None, will be generated by database)

    Returns:
        Dict containing prepared skill data
    """
    skill_data = {
        'name': skill_info.get('name', skill_info.get('skillName', 'Unnamed Skill')),
        'owner': username,
        'description': skill_info.get('description', ''),
        'version': skill_info.get('version', '1.0.0'),
        'path': skill_info.get('path', ''),
        'level': skill_info.get('level', 'entry'),
        'config': skill_info.get('config', {}),
        'tags': skill_info.get('tags', []),
        'examples': skill_info.get('examples', []),
        'inputModes': skill_info.get('inputModes', []),
        'outputModes': skill_info.get('outputModes', []),
        'apps': skill_info.get('apps', []),
        'limitations': skill_info.get('limitations', []),
        'price': skill_info.get('price', 0),
        'price_model': skill_info.get('price_model', ''),
        'public': skill_info.get('public', False),
        'rentable': skill_info.get('rentable', False),
    }

    # Only add ID if provided (for updates)
    if skill_id:
        skill_data['id'] = skill_id

    return skill_data


def _update_skill_in_memory(skill_id: str, skill_data: Dict[str, Any]) -> bool:
    """Update or add skill in mainwin.agent_skills memory

    Args:
        skill_id: Skill ID
        skill_data: Skill data dictionary

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        main_window = AppContext.get_main_window()
        if not main_window or not hasattr(main_window, 'agent_skills'):
            logger.warning("[skill_handler] mainwin.agent_skills not available")
            return False

        from agent.ec_skill import EC_Skill

        # Check if skill already exists in memory
        existing_index = None
        for i, skill in enumerate(main_window.agent_skills or []):
            if hasattr(skill, 'id') and skill.id == skill_id:
                existing_index = i
                break

        # Create skill object
        skill_obj = EC_Skill()
        skill_obj.id = skill_id
        skill_obj.name = skill_data['name']
        skill_obj.owner = skill_data['owner']
        skill_obj.description = skill_data['description']
        skill_obj.version = skill_data['version']
        skill_obj.config = skill_data.get('config', {})
        skill_obj.level = skill_data.get('level', 'entry')

        if existing_index is not None:
            # Update existing skill
            main_window.agent_skills[existing_index] = skill_obj
            logger.info(f"[skill_handler] Updated skill in memory: {skill_data['name']}")
        else:
            # Add new skill
            if main_window.agent_skills is None:
                main_window.agent_skills = []
            main_window.agent_skills.append(skill_obj)
            logger.info(f"[skill_handler] Added new skill to memory: {skill_data['name']}")

        return True

    except Exception as e:
        logger.warning(f"[skill_handler] Failed to update mainwin.agent_skills: {e}")
        return False


def _create_clean_skill_response(skill_id: str, skill_data: Dict[str, Any]) -> Dict[str, Any]:
    """Create clean skill data for response (avoid circular references)

    Args:
        skill_id: Skill ID
        skill_data: Skill data dictionary

    Returns:
        Dict containing clean skill data
    """
    return {
        'id': skill_id,
        'name': skill_data['name'],
        'owner': skill_data['owner'],
        'description': skill_data['description'],
        'version': skill_data['version'],
        'level': skill_data['level'],
        'public': skill_data.get('public', False),
        'rentable': skill_data.get('rentable', False),
        'price': skill_data.get('price', 0)
    }
