import logging
import traceback
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Dict, Set, Tuple, List
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from utils.logger_helper import logger_helper as logger
from agent.ec_org_ctrl import get_ec_org_ctrl
from agent.cloud_api.constants import Operation
convert_agent_dict_to_ec_agent = None  # Lazy import to avoid circulars


def _get_main_window():
    """Get actual MainWindow for mutations (writing agents list, etc.)."""
    try:
        mw = AppContext.get_main_window()
        return mw
    except Exception:
        return None


def _get_converter():
    """Lazy import agent converter to reduce circular import risk."""
    global convert_agent_dict_to_ec_agent
    if convert_agent_dict_to_ec_agent is None:
        try:
            from agent.agent_converter import convert_agent_dict_to_ec_agent as _conv
            convert_agent_dict_to_ec_agent = _conv
        except Exception as e:
            logger.error(f"[agent_handler] Failed to import agent converter: {e}")
            convert_agent_dict_to_ec_agent = False  # mark tried
    return convert_agent_dict_to_ec_agent or None


def _json_safe(
    value,
    depth: int = 0,
    seen: Optional[Set[int]] = None,
    depth_warning_state: Optional[Dict[str, bool]] = None,
):
    """Recursively convert values to JSON-serializable structures.

    - Pydantic models: use model_dump(mode="python")
    - Objects with __dict__: use vars()
    - Dicts/lists/sets/tuples: sanitize recursively
    - Fallback: str(value)
    """
    if seen is None:
        seen = set()
    if depth_warning_state is None:
        depth_warning_state = {'emitted': False}
    try:
        # Prevent extremely deep recursion - increased limit for complex agent objects
        if depth > 15:
            if not depth_warning_state['emitted']:
                logger.warning(
                    f"[agent_handler] _json_safe depth limit reached at depth {depth}, "
                    "converting nested values to string (warning shown once per sanitation pass)"
                )
                depth_warning_state['emitted'] = True
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        obj_id = id(value)
        if obj_id in seen:
            return '<circular_ref>'
        if isinstance(value, dict):
            seen.add(obj_id)
            safe_dict = {}
            for k, v in value.items():
                key = str(k)
                safe_dict[key] = _json_safe(v, depth + 1, seen, depth_warning_state)
            seen.discard(obj_id)
            return safe_dict
        if isinstance(value, (list, tuple, set)):
            seen.add(obj_id)
            result = [_json_safe(v, depth + 1, seen, depth_warning_state) for v in value]
            seen.discard(obj_id)
            return result
        # Pydantic BaseModel-like
        if hasattr(value, 'model_dump') and callable(getattr(value, 'model_dump')):
            try:
                return _json_safe(value.model_dump(mode="python"), depth + 1, seen, depth_warning_state)
            except Exception:
                pass
        # Generic objects
        if hasattr(value, '__dict__'):
            try:
                return _json_safe(vars(value), depth + 1, seen, depth_warning_state)
            except Exception:
                pass
        return str(value)
    except Exception:
        try:
            return str(value)
        except Exception:
            return '<unserializable>'


def _normalize_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    # Treat empty strings as missing
    if isinstance(value, str) and value.strip() == '':
        return None
    return str(value)


def build_org_agent_tree(organizations, agents):
    """
    Build tree structure with organization and agent data integrated
    
    Args:
        organizations: List of organization data from ec_org_ctrl
        agents: List of agent data with org_id field
        
    Returns:
        dict: Tree structure with integrated organization and agent data
    """
    # Create agent lookup by org_id for efficient access
    agents_by_org: Dict[str, list] = defaultdict(list)
    unassigned_agents = []

    for agent in agents:
        raw_org_id = agent.get('org_id')
        normalized_org_id = _normalize_id(raw_org_id)

        if normalized_org_id:
            # Store normalized org_id back onto the agent so downstream consumers get consistent types
            agent['org_id'] = normalized_org_id
            agents_by_org[normalized_org_id].append(agent)
        else:
            agent['org_id'] = None
            unassigned_agents.append(agent)

    # Build organization lookup and parent-child relationships
    normalized_orgs = []
    for org in organizations:
        org_copy = dict(org)
        org_copy['_normalized_id'] = _normalize_id(org.get('id'))
        org_copy['_normalized_parent_id'] = _normalize_id(org.get('parent_id'))
        normalized_orgs.append(org_copy)

    org_map: Dict[str, Dict[str, Any]] = {
        org['_normalized_id']: org
        for org in normalized_orgs
        if org.get('_normalized_id')
    }

    children_map: Dict[str, list] = defaultdict(list)
    root_candidates = []

    for org in normalized_orgs:
        org_id = org.get('_normalized_id')
        if not org_id:
            continue

        parent_id = org.get('_normalized_parent_id')
        if parent_id and parent_id in org_map:
            children_map[parent_id].append(org)
        else:
            root_candidates.append(org)

    # If no valid root found, create a default root organization placeholder
    if not root_candidates:
        default_root = {
            'id': '__virtual_root__',
            'name': 'eCan.ai',
            'description': 'Root Organization',
            'org_type': 'company',
            'level': 0,
            'sort_order': 0,
            'status': 'active',
            'parent_id': None,
            'created_at': None,
            'updated_at': None,
            '_normalized_id': '__virtual_root__',
            '_normalized_parent_id': None,
        }
        root_candidates = [default_root]
        org_map[default_root['_normalized_id']] = default_root

    def sort_key(org_data: Dict[str, Any]):
        return (org_data.get('sort_order', 0), org_data.get('name', ''))

    # Build tree structure recursively
    def build_tree_node(org_data: Dict[str, Any]):
        """Build a single tree node with its children and agents
        
        Each node contains:
        - agents: Direct agents assigned to this organization only
        - children: Child organizations (each with their own agents)
        
        The frontend will recursively collect agents from all descendants.
        """
        # Get direct agents for this organization
        org_normalized_id = org_data.get('_normalized_id')
        direct_agents = agents_by_org.get(org_normalized_id, [])
        
        node = {
            'id': org_data.get('id'),
            'name': org_data.get('name'),
            'description': org_data.get('description', ''),
            'org_type': org_data.get('org_type', 'department'),
            'level': org_data.get('level', 0),
            'sort_order': org_data.get('sort_order', 0),
            'status': org_data.get('status', 'active'),
            'parent_id': org_data.get('parent_id'),
            'created_at': org_data.get('created_at'),
            'updated_at': org_data.get('updated_at'),
            'children': [],
            'agents': direct_agents  # Only direct agents
        }

        # Build children recursively
        child_orgs_list = sorted(
            children_map.get(org_data.get('_normalized_id'), []),
            key=sort_key,
        )
        for child_org in child_orgs_list:
            node['children'].append(build_tree_node(child_org))

        return node

    # Build the complete tree starting from root candidates
    if len(root_candidates) == 1:
        tree_root = build_tree_node(root_candidates[0])
    else:
        tree_root = {
            'id': '__virtual_root__',
            'name': 'Organizations',
            'description': 'Virtual root node for multiple top-level organizations',
            'org_type': 'company',
            'level': 0,
            'sort_order': 0,
            'status': 'active',
            'parent_id': None,
            'created_at': None,
            'updated_at': None,
            'children': [
                build_tree_node(org)
                for org in sorted(root_candidates, key=sort_key)
            ],
            'agents': []
        }

    # Add unassigned agents to root level
    tree_root.setdefault('agents', [])
    tree_root['agents'].extend(unassigned_agents)
    
    # Debug: detailed tree structure logging
    def log_tree_structure(node, indent=0):
        prefix = "  " * indent
        agent_ids = [a.get('id', 'unknown') for a in node.get('agents', [])]
        logger.debug(f"{prefix}- {node['name']} (id: {node['id']}) - {len(node.get('agents', []))} agents {agent_ids}, {len(node.get('children', []))} children")
        for child in node.get('children', []):
            log_tree_structure(child, indent + 1)
    
    logger.info(f"[agent_handler] Built integrated tree: {len(organizations)} orgs, {len(agents)} agents ({len(unassigned_agents)} unassigned)")
    logger.debug(f"[agent_handler] Agents by org_id distribution:")
    for org_id, org_agents in agents_by_org.items():
        logger.debug(f"    - org_id={org_id}: {len(org_agents)} agents")
    logger.debug(f"Tree structure:")
    log_tree_structure(tree_root)
    
    return tree_root


@IPCHandlerRegistry.background_handler('get_agents')
def handle_get_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle get agents request (runs in background thread to avoid blocking UI).
    
    Database queries with relations (JOIN operations) can be slow when there are
    many agents with tasks/skills. Running in background prevents UI freezing.

    Retrieve agents for the specified user.

    Args:
        request: IPC request object
        params: Request parameters, must include 'username' field

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"[agent_handler] Get agents handler called with request: {request}")

        # Get username and agent IDs
        username = params.get('username')
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')
        
        # Get agent_id parameter (array)
        agent_ids = params.get('agent_id', [])
        
        logger.info(f"[agent_handler] get agents request for user: {username}, agent_id: {agent_ids}")

        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username} - user may have logged out")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')

        # This ensures we get all agents including newly created ones
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr or not ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')

        # Get all agents from memory (MainWindow.agents contains the most up-to-date data)
        # This includes both database agents and special agents like MyTwinAgent
        memory_agents = ctx.get_agents() or []
        
        # If specific agent IDs are requested, query from database with relations to get tasks/skills
        if agent_ids and len(agent_ids) > 0:
            logger.info(f"[agent_handler] Querying agents from database with relations for IDs: {agent_ids}")
            agent_service = ec_db_mgr.agent_service
            
            agents_data = []
            for agent_id in agent_ids:
                # Query from database with full relations
                db_result = agent_service.query_agents_with_relations(id=agent_id, include_skills=True, include_tasks=True)
                
                if db_result.get('success') and db_result.get('data'):
                    agents_data.extend(db_result['data'])
                    # Log tasks count for debugging
                    for agent in db_result['data']:
                        logger.info(f"[agent_handler] Agent {agent.get('id')} has {len(agent.get('tasks', []))} tasks, {len(agent.get('skills', []))} skills")
                else:
                    logger.warning(f"[agent_handler] Failed to query agent {agent_id}: {db_result.get('error', 'Unknown error')}")
            
            logger.info(f"[agent_handler] Retrieved {len(agents_data)} agents from database with relations")
        else:
            # For listing all agents, use memory (faster, but without detailed relations)
            agents_data = [agent.to_dict(owner=username) for agent in memory_agents]
            logger.info(f"[agent_handler] Retrieved {len(agents_data)} agents from memory")
        
        resultJS = {
            'agents': agents_data,
            'message': 'Get all successful'
        }
        
        
        # Sanitize for JSON serialization safety (handles Pydantic objects like TaskSendParams)
        safe_result = _json_safe(resultJS)
        if safe_result is not resultJS:
            logger.debug("[agent_handler] Applied JSON-safe sanitation to get_agents result")
        
        logger.debug(f"[agent_handler] Successfully retrieved {len(agents_data)} agents")
        return create_success_response(request, safe_result)

    except Exception as e:
        logger.error(f"[agent_handler] Error in get agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get agents: {str(e)} "
        )
    
@IPCHandlerRegistry.handler('save_agent')
def handle_save_agent(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Save/update agents

    Args:
        request: IPC request object
        params: Request parameters with username and agent data

    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[agent_handler] Save agents handler called with request: {request}")

        # Get username
        username = params.get('username')
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')
        
        # Get agent parameter (array)
        agents_data = params.get('agent', [])
        if not agents_data:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing agent parameter')

        logger.info(f"[agent_handler] Saving {len(agents_data)} agents for user: {username}")

        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Get database service
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr or not ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = ec_db_mgr.agent_service
        
        # Process each agent
        saved_count = 0
        errors = []
        updated_agents = []

        for agent_data in agents_data:
            try:
                # Get agent ID (must use 'id' field for consistency)
                agent_id = agent_data.get('id')
                if not agent_id:
                    logger.error(f"[agent_handler] Missing 'id' field in agent data. Available fields: {list(agent_data.keys())}")
                    errors.append("Missing required 'id' field")
                    continue
                
                # Step 1: Check if agent exists in database
                existing_agent = agent_service.query_agents(id=agent_id)
                is_new_agent = not (existing_agent.get('success') and existing_agent.get('data'))
                
                if is_new_agent:
                    # Create new agent
                    logger.info(f"[agent_handler] Creating new agent {agent_id} with fields: {list(agent_data.keys())}")
                    result = agent_service.create_agent_from_data(agent_data, username)
                else:
                    # Update existing agent
                    logger.info(f"[agent_handler] Updating existing agent {agent_id} with fields: {list(agent_data.keys())}")
                    result = agent_service.update_agent(agent_id, agent_data)
                
                if result.get('success'):
                    logger.info(f"[agent_handler] ✅ Database update successful for agent {agent_id}")
                    # Get updated agent data from database
                    updated_agent_data = result.get('data', {})
                    updated_agents.append(updated_agent_data)
                    
                    # Step 2: Reload agent from database and replace in memory
                    # This ensures all fields are correctly updated, including skills and tasks
                    try:
                        # Query the updated agent from database with full details
                        logger.info(f"[agent_handler] Querying agent {agent_id} with relations...")
                        db_agent_result = agent_service.query_agents_with_relations(id=agent_id, include_skills=True, include_tasks=True)
                        
                        if db_agent_result.get('success') and db_agent_result.get('data'):
                            db_agent_data = db_agent_result['data'][0]
                            logger.info(f"[agent_handler] ✅ Query successful, agent has {len(db_agent_data.get('skills', []))} skills, {len(db_agent_data.get('tasks', []))} tasks")
                            
                            # Convert database agent to EC_Agent instance
                            converter = _get_converter()
                            updated_ec_agent = converter(db_agent_data, ctx.main_window) if converter else None
                            
                            if updated_ec_agent:
                                # Replace the agent in ctx.get_agents()
                                agent_index = next((i for i, ag in enumerate(ctx.get_agents()) if ag.card.id == agent_id), None)
                                if agent_index is not None:
                                    ctx.get_agents()[agent_index] = updated_ec_agent
                                    logger.info(f"[agent_handler] ✅ Replaced agent in memory: {agent_id}")
                                else:
                                    # Agent not in memory, add it (might be newly created or memory was cleared)
                                    ctx.get_agents().append(updated_ec_agent)
                                    logger.info(f"[agent_handler] ✅ Added agent to memory (was missing): {agent_id}")
                            else:
                                logger.error(f"[agent_handler] ❌ Failed to convert agent to EC_Agent: {agent_id}")
                                logger.error(f"[agent_handler] ⚠️ Memory will be out of sync! Consider restarting.")
                        else:
                            logger.error(f"[agent_handler] ❌ Failed to query updated agent: {db_agent_result.get('error')}")
                    except Exception as e:
                        logger.error(f"[agent_handler] Error reloading agent from database: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())
                    
                    # Step 3: Clean up offline sync queue for this agent (remove pending add/update operations)
                    try:
                        from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
                        sync_queue = get_offline_sync_queue()
                        removed_add = sync_queue.remove_tasks_by_resource('agent', agent_id, operation='add')
                        removed_update = sync_queue.remove_tasks_by_resource('agent', agent_id, operation='update')
                        if removed_add + removed_update > 0:
                            logger.info(f"[agent_handler] Removed {removed_add + removed_update} pending sync tasks for agent: {agent_id}")
                    except Exception as e:
                        logger.warning(f"[agent_handler] Failed to clean offline sync queue: {e}")
                    
                    # Step 4: Sync to cloud after memory update succeeds (async, auto-cached if failed)
                    # Use correct operation based on whether agent is new or existing
                    sync_operation = Operation.ADD if is_new_agent else Operation.UPDATE

                    # Sync Agent entity first, then sync relations after completion to avoid FK races.
                    def _after_agent_sync(result: Dict[str, Any]):
                        if result.get('synced') or result.get('cached'):
                            _sync_agent_relations_after_entity_sync(updated_agent_data, agent_data)
                        else:
                            logger.error(
                                f"[agent_handler] Skipping relation sync due to agent sync failure: {result.get('error') or result.get('errors') or result}"
                            )

                    # For custom avatars: sync avatar first (FK dependency), then agent in callback.
                    # For system avatars (A00x): _trigger_cloud_sync strips avatar_resource_id itself.
                    avatar_rid_upd = updated_agent_data.get('avatar_resource_id') or ''
                    avatar_changed = 'avatar_id' in agent_data
                    has_custom_avatar_upd = isinstance(avatar_rid_upd, str) and avatar_rid_upd and not avatar_rid_upd.startswith('A00')
                    if avatar_changed and has_custom_avatar_upd:
                        _upd_op = Operation.UPDATE
                        _upd_agent = updated_agent_data
                        _upd_sync_op = sync_operation
                        def _after_avatar_then_agent_upd(avatar_result: Dict[str, Any]):
                            _trigger_cloud_sync(_upd_agent, _upd_sync_op, callback=_after_agent_sync)
                        _sync_agent_avatar_to_cloud(updated_agent_data, _upd_op, request, params, callback=_after_avatar_then_agent_upd)
                    else:
                        _trigger_cloud_sync(updated_agent_data, sync_operation, callback=_after_agent_sync)
                        if avatar_changed:
                            _sync_agent_avatar_to_cloud(updated_agent_data, Operation.UPDATE, request, params)
                    
                    saved_count += 1
                    logger.info(f"[agent_handler] Updated agent in database: {agent_id}")
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"[agent_handler] Failed to update agent {agent_id}: {error_msg}")
                    errors.append(f"Agent {agent_id}: {error_msg}")

            except Exception as e:
                error_msg = f"Error saving agent: {str(e)}"
                logger.error(f"[agent_handler] {error_msg}")
                errors.append(error_msg)

        if errors:
            logger.warning(f"[agent_handler] Saved {saved_count} agents with {len(errors)} errors")
            return create_error_response(request, 'PARTIAL_SAVE_ERROR', f"Saved {saved_count} agents with errors: {'; '.join(errors)}")
        else:
            logger.info(f"[agent_handler] Successfully saved {saved_count} agents for user: {username}")
            result_data = {
                'message': f'Successfully saved {saved_count} agents',
                'agents': updated_agents  # Return updated agent data
            }
            # Sanitize for JSON serialization safety
            safe_result = _json_safe(result_data)
            return create_success_response(request, safe_result)

    except Exception as e:
        logger.error(f"[agent_handler] Error in save agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_AGENTS_ERROR',
            f"Error during save agents: {str(e)}"
        )



@IPCHandlerRegistry.handler('delete_agent')
def handle_delete_agent(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle delete agent request

    Args:
        request: IPC request object
        params: Request parameters, must include 'username' and 'agent_id' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        
        # Get username
        username = params.get('username') if params else None
        logger.info(f"[agent_handler] Extracted username: {username}")
        
        if not username:
            logger.error(f"[agent_handler] Missing username parameter, params={params}")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')
        
        # Get agent_id parameter (can be a single string or array)
        agent_id_param = params.get('agent_id')
        logger.info(f"[agent_handler] Extracted agent_id_param: {agent_id_param}")
        
        if not agent_id_param:
            logger.error(f"[agent_handler] Missing agent_id parameter, params={params}")
            return create_error_response(request, 'INVALID_PARAMS', 'Missing agent_id parameter')
        
        # Normalize to array
        if isinstance(agent_id_param, str):
            agent_ids = [agent_id_param]
        elif isinstance(agent_id_param, list):
            agent_ids = agent_id_param
        else:
            return create_error_response(request, 'INVALID_PARAMS', 'Invalid agent_id parameter type')
        
        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')
        
        # Get database service
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr or not ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = ec_db_mgr.agent_service
        
        # Delete each agent from database and memory
        deleted_count = 0
        errors = []
        
        for agent_id in agent_ids:
            try:
                # Step 1: Delete from database first
                result = agent_service.delete_agent(agent_id)
                
                if result.get('success'):
                    deleted_agent = None
                    try:
                        agents = ctx.get_agents()
                        original_count = len(agents)
                        # Capture the agent BEFORE removal (Step 4 needs its
                        # avatar_id; looking it up after removal always found
                        # None, so orphan-avatar cleanup never ran).
                        deleted_agent = next(
                            (ag for ag in agents
                             if getattr(getattr(ag, 'card', None), 'id', None) == agent_id),
                            None)
                        # Step 2: Delete from memory after database deletion
                        # succeeds. getattr-guarded: one malformed agent (no
                        # .card) must not abort the whole removal — a lingering
                        # memory row wins over the DB in get_all_org_agents, so
                        # the deleted agent would reappear on every refresh.
                        agents[:] = [
                            ag for ag in agents
                            if getattr(getattr(ag, 'card', None), 'id', None) != agent_id
                        ]
                        new_count = len(agents)
                        logger.info(f"[agent_handler] Removed agent from memory: {agent_id} (count: {original_count} → {new_count})")
                    except Exception as e:
                        logger.warning(f"[agent_handler] Failed to remove agent from memory: {e}")
                    
                    # Step 3: Clean up offline sync queue for this agent
                    try:
                        from agent.cloud_api.offline_sync_queue import get_offline_sync_queue
                        sync_queue = get_offline_sync_queue()
                        removed_count_queue = sync_queue.remove_tasks_by_resource('agent', agent_id)
                        if removed_count_queue > 0:
                            logger.info(f"[agent_handler] Removed {removed_count_queue} pending sync tasks for agent: {agent_id}")
                    except Exception as e:
                        logger.warning(f"[agent_handler] Failed to clean offline sync queue: {e}")
                    
                    # Step 4: Check if agent had a custom avatar and clean it up if orphaned
                    try:
                        # deleted_agent was captured in Step 2 before the
                        # memory removal (a post-removal lookup finds nothing).
                        avatar_id = deleted_agent.card.avatar_id if deleted_agent and hasattr(deleted_agent.card, 'avatar_id') else None
                        
                        if avatar_id and not avatar_id.startswith('A00'):  # Not a system avatar
                            # Check if this avatar is used by other agents
                            is_orphaned = _check_and_cleanup_orphaned_avatar(avatar_id, agent_id, username, request, params)
                            if is_orphaned:
                                logger.info(f"[agent_handler] Orphaned avatar {avatar_id} cleaned up")
                    except Exception as e:
                        logger.warning(f"[agent_handler] Error checking avatar cleanup: {e}")
                    
                    # Step 5: Sync deletion to cloud after memory update (async, fire and forget)
                    delete_agent_data = {
                        'id': agent_id,
                        'owner': username,
                        'name': f"Agent_{agent_id}"  # Placeholder name for deletion
                    }
                    _trigger_cloud_sync(delete_agent_data, Operation.DELETE)
                    
                    # Note: Agent-Skill/Task/Tool relationships are cascade deleted in database
                    logger.info(f"[agent_handler] Agent relationships cascade deleted, cloud sync triggered")
                    
                    deleted_count += 1
                else:
                    error_msg = result.get('error', 'Unknown error')
                    logger.error(f"[agent_handler] Failed to delete agent {agent_id}: {error_msg}")
                    errors.append(f"Agent {agent_id}: {error_msg}")
                    
            except Exception as e:
                error_msg = f"Error deleting agent {agent_id}: {str(e)}"
                logger.error(f"[agent_handler] {error_msg}")
                errors.append(error_msg)
        
        if errors:
            return create_error_response(
                request,
                'PARTIAL_DELETE_ERROR',
                f"Deleted {deleted_count} agents with errors: {'; '.join(errors)}"
            )
        else:
            return create_success_response(request, {
                'message': f'Successfully deleted {deleted_count} agent(s)'
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error in delete agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'DELETE_ERROR',
            f"Error during delete agents: {str(e)}"
        )



@IPCHandlerRegistry.handler('new_agent')
def handle_new_agent(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Create new agents

    Args:
        request: IPC request object
        params: Request parameters with username and agent data

    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[agent_handler] Create agents handler called with request: {request}")

        # Get agent parameter (array, but we only process the first one)
        agents_data = params.get('agent', [])
        
        if not agents_data:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing agent parameter')
        
        # Only process the first agent (single create, not batch)
        agent_data = agents_data[0]

        # Get username from params or from agent's owner field
        username = params.get('username') or agent_data.get('owner')
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')

        logger.info(f"[agent_handler] Creating agent '{agent_data.get('name')}' for user: {username}")

        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Get database service
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            logger.error(f"[agent_handler] Database manager not available")
            return create_error_response(request, 'DB_ERROR', 'Database manager not available')

        agent_service = ec_db_mgr.agent_service
        if not agent_service:
            logger.error(f"[agent_handler] Agent service not available")
            return create_error_response(request, 'DB_ERROR', 'Agent service not available')

        # Step 1: Create agent in database first
        result = agent_service.create_agent_from_data(agent_data, username)

        if not result.get('success'):
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[agent_handler] Failed to create agent: {error_msg}")
            return create_error_response(request, 'CREATE_AGENT_ERROR', error_msg)
        
        created_agent = result.get('data')

        # Step 2: Reload agent from database and add to memory
        # This ensures all fields are correctly loaded, including skills and tasks
        try:
            agent_id = created_agent.get('id')
            
            # Query the created agent from database with full details
            db_agent_result = agent_service.query_agents_with_relations(id=agent_id, include_skills=True, include_tasks=True)
            if db_agent_result.get('success') and db_agent_result.get('data'):
                db_agent_data = db_agent_result['data'][0]
                
                # Convert database agent to EC_Agent instance
                converter = _get_converter()
                ec_agent = converter(db_agent_data, ctx.main_window) if converter else None
                
                if ec_agent:
                    # Add to ctx.get_agents()
                    ctx.get_agents().append(ec_agent)
                    
                    # Hot-start the new agent
                    try:
                        logger.info(f"[agent_handler] Hot-starting new agent '{ec_agent.card.name}'...")
                        ec_agent.start()
                        logger.info(f"[agent_handler] ✅ Agent '{ec_agent.card.name}' started successfully")
                    except Exception as e:
                        logger.error(f"[agent_handler] ❌ Failed to start new agent: {e}")
                    
                    logger.info(f"[agent_handler] Created and added EC_Agent '{ec_agent.card.name}' to memory")
                else:
                    logger.warning(f"[agent_handler] Failed to convert agent to EC_Agent. Frontend will need to refresh.")
            else:
                logger.error(f"[agent_handler] Failed to query created agent from database: {agent_id}")
        except Exception as e:
            logger.warning(f"[agent_handler] Failed to add agent to memory: {e}. Frontend will need to refresh.")
            logger.debug(f"[agent_handler] Traceback: {traceback.format_exc()}")

        # Step 3: Sync to cloud after memory update succeeds (async, auto-cached if failed)
        # Sync Agent entity first, then sync relations after completion to avoid FK races.
        def _after_agent_sync(result: Dict[str, Any]):
            if result.get('synced') or result.get('cached'):
                _sync_agent_relations_after_entity_sync(created_agent, agent_data)
            else:
                logger.error(
                    f"[agent_handler] Skipping relation sync due to agent sync failure: {result.get('error') or result.get('errors') or result}"
                )

        # For custom avatars: sync avatar first (FK dependency), then agent in callback.
        # For system avatars (A00x): _trigger_cloud_sync strips avatar_resource_id itself,
        # so we can fire agent sync directly without waiting.
        avatar_rid = created_agent.get('avatar_resource_id') or ''
        has_custom_avatar = isinstance(avatar_rid, str) and avatar_rid and not avatar_rid.startswith('A00')
        if has_custom_avatar:
            def _after_avatar_then_agent(avatar_result: Dict[str, Any]):
                # Proceed with agent sync even if avatar sync was cached (offline queue)
                if avatar_result.get('synced') or avatar_result.get('cached'):
                    _trigger_cloud_sync(created_agent, Operation.ADD, callback=_after_agent_sync)
                else:
                    logger.error("[agent_handler] Avatar sync failed; proceeding with agent sync anyway")
                    _trigger_cloud_sync(created_agent, Operation.ADD, callback=_after_agent_sync)
            _sync_agent_avatar_to_cloud(created_agent, Operation.ADD, request, params, callback=_after_avatar_then_agent)
        else:
            # System avatar or no avatar — agent sync can fire immediately
            _trigger_cloud_sync(created_agent, Operation.ADD, callback=_after_agent_sync)

        logger.info(f"[agent_handler] Successfully created agent '{created_agent.get('name')}' for user: {username}")
        result_data = {
            'message': f"Successfully created agent '{created_agent.get('name')}'",
            'agent': created_agent
        }
        # Sanitize for JSON serialization safety
        safe_result = _json_safe(result_data)
        return create_success_response(request, safe_result)

    except Exception as e:
        logger.error(f"[agent_handler] Error in create agents handler: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CREATE_AGENTS_ERROR', f"Error during create agents: {str(e)}")


@IPCHandlerRegistry.handler('get_all_org_agents')
def handle_get_all_org_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Get all organizations and their associated agents in a single request
    
    This is an optimized endpoint that returns:
    - All organizations in a hierarchical structure
    - All agents that belong to organizations (org_agents)
    - All agents that don't belong to any organization (unassigned_agents)
    
    Args:
        request: IPC request object
        params: Request parameters with username
    
    Returns:
        IPCResponse: Response with integrated organization and agent data
    """
    try:
        logger.debug(f"[agent_handler] get_all_org_agents called with request: {request}")
        
        # Resolve username from params or context (for local_server requests)
        from gui.ipc.handlers import resolve_username
        username = resolve_username(request, params)
        
        if not username:
            logger.warning(f"[agent_handler] No username provided and could not determine from context")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Missing required parameter: username'
            )
        logger.info(f"[agent_handler] Getting all organizations and agents for user: {username}")
        
        # Get ctx to access integrated agents list
        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')
        
        # In web mode we may not have DB/config wired yet; fall back to empty structures
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr or not ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            empty_tree = {
                'id': '__virtual_root__',
                'name': 'eCan.ai',
                'description': 'Root Organization',
                'org_type': 'company',
                'level': 0,
                'sort_order': 0,
                'status': 'active',
                'parent_id': None,
                'created_at': None,
                'updated_at': None,
                'children': [],
                'agents': []
            }
            return create_success_response(request, {
                'orgs': empty_tree,
                'message': 'Database service not available; returning empty org structure'
            })
        
        # ── Merge memory + DB agents, deduplicate by ID (memory wins) ──────────
        # Strategy:
        #   • memory: EC_Agent objects (authoritative runtime state)
        #   • DB     : agent dicts (authoritative persisted config)
        #   • merge  : same ID → keep memory row; DB rows backfill only missing IDs
        mem_agents_map: Dict[str, Any] = {}
        for agent in ctx.get_agents():
            aid = getattr(getattr(agent, 'card', None), 'id', None)
            if aid:
                mem_agents_map[aid] = agent.to_dict(owner=username)

        logger.info(f"[agent_handler] Memory agents: {len(mem_agents_map)}")

        db_agents_map: Dict[str, Any] = {}
        if ec_db_mgr and ec_db_mgr.agent_service:
            try:
                db_result = ec_db_mgr.agent_service.get_agents_by_owner(username)
                if db_result and isinstance(db_result, dict) and db_result.get('success'):
                    for ag_dict in db_result.get('data') or []:
                        aid = ag_dict.get('id')
                        if aid and aid not in mem_agents_map:
                            db_agents_map[aid] = ag_dict
                    logger.info(f"[agent_handler] DB backfill agents (not in memory): {len(db_agents_map)}")

                    # Try to convert DB agents to EC_Agent and add to memory if skills are ready
                    converter = _get_converter()
                    main_win = ctx.main_window
                    skills_ready = bool(getattr(main_win, 'agent_skills', None))
                    if converter and skills_ready:
                        converted = 0
                        for db_agent_dict in db_agents_map.values():
                            try:
                                ec_agent = converter(db_agent_dict, main_win)
                                if ec_agent:
                                    ctx.get_agents().append(ec_agent)
                                    converted += 1
                            except Exception as e:
                                logger.debug(f"[agent_handler] DB agent convert skip: {e}")
                        logger.info(f"[agent_handler] Converted {converted} DB agents to EC_Agent in memory")
            except Exception as e:
                logger.warning(f"[agent_handler] DB agent query failed: {e}")

        all_agents = list(mem_agents_map.values()) + list(db_agents_map.values())
        if len(all_agents) < len(mem_agents_map) + len(db_agents_map):
            logger.info(f"[agent_handler] Deduped {len(mem_agents_map) + len(db_agents_map)} -> {len(all_agents)} agents by ID")
        
        # Get org manager for organization data
        ec_org_ctrl = get_ec_org_ctrl()
        
        # Get all organizations as flat list (not tree structure)
        org_result = ec_org_ctrl.org_service.get_all_orgs()
        
        # Get organizations - if query fails or returns empty, return empty structure
        organizations = []
        if org_result.get("success"):
            organizations = org_result.get("data", [])
            logger.info(f"[agent_handler] Retrieved {len(organizations)} organizations from database")
        else:
            logger.warning(f"[agent_handler] Failed to get organizations: {org_result.get('error')} - will return empty org structure")
        
        # all_agents is already in flat dict format from to_flat_dict() method
        # Just add isBound field for frontend compatibility
        for agent in all_agents:
            agent['isBound'] = agent.get('org_id') is not None
        
        # Count assigned vs unassigned for logging
        if all_agents:
            assigned_count = len([a for a in all_agents if a.get('org_id')])
            unassigned_count = len([a for a in all_agents if not a.get('org_id')])
            logger.info(f"[agent_handler] Processed {len(all_agents)} total agents: {assigned_count} assigned, {unassigned_count} unassigned")

        # Note: Agent assignment to orgs is handled in build_org_agent_tree
        # No need to manually assign here

        # Build integrated tree structure with organizations and their agents
        tree_root = build_org_agent_tree(organizations, all_agents)
        
        # Return complete tree structure with root as orgs
        result_data = {
            'orgs': tree_root,  # Complete tree structure: root with children and agents
            'message': 'Successfully retrieved integrated organizations and agents tree'
        }
        # Sanitize for JSON serialization safety (handles Pydantic objects like TaskSendParams)
        safe_result = _json_safe(result_data)
        if safe_result is not result_data:
            logger.debug("[agent_handler] Applied JSON-safe sanitation to get_all_org_agents result")
        
        logger.info(f"[agent_handler] Successfully retrieved integrated data for user: {username}")
        return create_success_response(request, safe_result)
        
    except Exception as e:
        logger.error(f"[agent_handler] Error in get_all_org_agents: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_ALL_ORG_AGENTS_ERROR', str(e))


# ============================================================================
# Cloud Synchronization Functions
# ============================================================================

def _trigger_cloud_sync(agent_data: Dict[str, Any], operation: 'Operation', callback: Optional[callable] = None) -> None:
    """Trigger cloud synchronization (async, non-blocking)
    
    Async background execution, doesn't block UI operations, ensures eventual consistency.
    
    Args:
        agent_data: Agent data to sync
        operation: Operation type (Operation enum)
    """
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    def _log_result(result: Dict[str, Any]):
        """Log sync result"""
        error_msg = result.get('error')
        if not error_msg:
            errors = result.get('errors')
            if isinstance(errors, list) and errors:
                error_msg = '; '.join([str(e) for e in errors if e])
        if result.get('synced'):
            logger.info(f"[agent_handler] ✅ Agent synced to cloud: {operation} - {agent_data.get('name')}")
        elif result.get('cached'):
            logger.info(f"[agent_handler] 💾 Agent cached for later sync: {operation} - {agent_data.get('name')}")
        else:
            # For required sync, any non-synced result is a failure signal (even if success=True)
            logger.error(f"[agent_handler] ❌ Failed to sync agent: {error_msg or result}")
    
    # Use SyncManager's thread pool for async execution
    def _callback_chain(result: Dict[str, Any]):
        _log_result(result)
        if callback:
            callback(result)

    # Strip system avatar IDs before cloud sync — system avatars (A001-A007) are
    # hardcoded locally and never exist in cloud avatar_resources table, so sending
    # avatar_resource_id for them triggers MySQL FK constraint error 1452.
    sync_data = agent_data
    avatar_rid = (agent_data.get('avatar_resource_id') or '') if isinstance(agent_data, dict) else ''
    if isinstance(avatar_rid, str) and avatar_rid.startswith('A00'):
        sync_data = {k: v for k, v in agent_data.items() if k != 'avatar_resource_id'}
        logger.debug(f"[agent_handler] Stripped system avatar_resource_id '{avatar_rid}' from cloud payload")

    manager = get_sync_manager()
    manager.sync_to_cloud_async(DataType.AGENT, sync_data, operation, callback=_callback_chain)


def _sync_agent_status_to_cloud(agent_service, agent_id: str, status: str) -> None:
    """Sync agent status change to cloud DB (async, non-blocking).

    Sends a minimal payload (id + status only) to avoid FK constraint issues
    and validation errors from unrelated fields like avatar_resource_id.
    """
    try:
        from agent.cloud_api.constants import Operation
        # Minimal payload — only the fields we need to update
        agent_data = {
            'id': agent_id,
            'status': status,
        }
        _trigger_cloud_sync(agent_data, Operation.UPDATE)
        logger.info(f"[agent_handler] Cloud sync triggered for agent {agent_id} status='{status}'")
    except Exception as e:
        logger.warning(f"[agent_handler] Cloud sync failed for agent {agent_id}: {e}")


def _sync_agent_relations_after_entity_sync(updated_agent_data: Dict[str, Any], input_agent_data: Dict[str, Any]) -> None:
    """Sync agent relations only after agent entity sync is accepted/cached.

    This prevents cloud FK races where relation rows are written before the
    corresponding agent row exists on cloud side.
    """
    # Relationship syncs always use ADD (cloud resolver handles upsert).
    # UPDATE requires the cloud-side auto-generated relation row 'id' which
    # the local client doesn't have.
    if 'skills' in input_agent_data:
        _sync_agent_skill_relations(updated_agent_data, input_agent_data.get('skills', []), Operation.ADD)

    if 'tasks' in input_agent_data:
        _sync_agent_task_relations(updated_agent_data, input_agent_data.get('tasks', []), Operation.ADD)

    if 'tools' in input_agent_data:
        _sync_agent_tool_relations(updated_agent_data, input_agent_data.get('tools', []), Operation.ADD)

    if 'org_id' in input_agent_data or 'org_ids' in input_agent_data:
        org_ids = input_agent_data.get('org_ids', [])
        if not org_ids and input_agent_data.get('org_id'):
            org_ids = [input_agent_data['org_id']]
        _sync_agent_org_relations(updated_agent_data, org_ids, Operation.ADD)


def _sync_agent_skill_relations(agent_data: Dict[str, Any], skill_ids: list, operation: 'Operation') -> None:
    """Sync Agent-Skill relationships to cloud (async, non-blocking)
    
    Args:
        agent_data: Agent data (must contain 'agid' and 'owner')
        skill_ids: List of skill IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not skill_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    manager = get_sync_manager()
    agent_id = agent_data.get('agid') or agent_data.get('id')
    owner = agent_data.get('owner', 'unknown')
    
    logger.info(f"[agent_handler] Syncing {len(skill_ids)} skill relationships for agent: {agent_id}")
    
    for skill_id in skill_ids:
        skill_relation_data = {
            'agid': agent_id,
            'skid': skill_id
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Skill relation synced: {skill_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Skill relation cached: {skill_id}")
            else:
                logger.error(f"[agent_handler] ❌ Failed to sync skill relation: {error_msg or result}")
        
        manager.sync_to_cloud_async(DataType.AGENT_SKILL, skill_relation_data, operation, callback=_log_result)


def _sync_agent_task_relations(agent_data: Dict[str, Any], task_ids: list, operation: 'Operation') -> None:
    """Sync Agent-Task relationships to cloud (async, non-blocking)
    
    Args:
        agent_data: Agent data (must contain 'agid' and 'owner')
        task_ids: List of task IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not task_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    manager = get_sync_manager()
    agent_id = agent_data.get('agid') or agent_data.get('id')
    owner = agent_data.get('owner', 'unknown')
    
    logger.info(f"[agent_handler] Syncing {len(task_ids)} task relationships for agent: {agent_id}")
    
    for task_id in task_ids:
        task_relation_data = {
            'agid': agent_id,
            'task_id': task_id,
            'status': 'assigned'  # Default status
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Task relation synced: {task_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Task relation cached: {task_id}")
            else:
                logger.error(f"[agent_handler] ❌ Failed to sync task relation: {error_msg or result}")
        
        manager.sync_to_cloud_async(DataType.AGENT_TASK, task_relation_data, operation, callback=_log_result)


def _sync_agent_tool_relations(agent_data: Dict[str, Any], tool_ids: list, operation: 'Operation') -> None:
    """Sync Agent-Tool relationships to cloud (async, non-blocking)
    
    Args:
        agent_data: Agent data (must contain 'agid' and 'owner')
        tool_ids: List of tool IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not tool_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    manager = get_sync_manager()
    agent_id = agent_data.get('agid') or agent_data.get('id')
    owner = agent_data.get('owner', 'unknown')
    
    logger.info(f"[agent_handler] Syncing {len(tool_ids)} tool relationships for agent: {agent_id}")
    
    for tool_id in tool_ids:
        tool_relation_data = {
            'agid': agent_id,
            'tool_id': tool_id,
            'permission': 'use'  # Default permission
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Tool relation synced: {tool_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Tool relation cached: {tool_id}")
            else:
                logger.error(f"[agent_handler] ❌ Failed to sync tool relation: {error_msg or result}")
        
        manager.sync_to_cloud_async(DataType.AGENT_TOOL, tool_relation_data, operation, callback=_log_result)


def _sync_agent_org_relations(agent_data: Dict[str, Any], org_ids: list, operation: 'Operation') -> None:
    """Sync Agent-Organization relationships to cloud (async, non-blocking)
    
    Args:
        agent_data: Agent data (must contain 'agid' or 'id')
        org_ids: List of organization IDs
        operation: Operation type (ADD/UPDATE/DELETE)
    """
    if not org_ids:
        return
    
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType
    
    manager = get_sync_manager()
    agent_id = agent_data.get('agid') or agent_data.get('id')
    
    logger.info(f"[agent_handler] Syncing {len(org_ids)} org relationships for agent: {agent_id}")
    
    for org_id in org_ids:
        org_relation_data = {
            'agent_id': agent_id,
            'org_id': org_id,
        }
        
        def _log_result(result: Dict[str, Any]):
            error_msg = result.get('error')
            if not error_msg:
                errors = result.get('errors')
                if isinstance(errors, list) and errors:
                    error_msg = '; '.join([str(e) for e in errors if e])
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Org relation synced: {org_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Org relation cached: {org_id}")
            else:
                logger.error(f"[agent_handler] ❌ Failed to sync org relation: {error_msg or result}")
        
        manager.sync_to_cloud_async(DataType.AGENT_ORG, org_relation_data, operation, callback=_log_result)


def _sync_agent_avatar_to_cloud(agent_data: Dict[str, Any], operation: 'Operation', request=None, params=None, callback=None) -> None:
    """Sync agent's avatar resource to cloud (async, non-blocking)

    When creating or updating an agent, if the agent has an avatar_id,
    we need to sync the corresponding avatar resource to cloud.

    Args:
        agent_data: Agent data (must contain 'avatar_id' and 'owner')
        operation: Operation type (ADD/UPDATE/DELETE)
        request: IPC request object (optional)
        params: Request parameters (optional)
    """
    avatar_id = agent_data.get('avatar_id')
    if not avatar_id:
        logger.debug("[agent_handler] No avatar_id in agent data, skipping avatar sync")
        return
    
    # Skip system avatars (they don't need cloud sync)
    if isinstance(avatar_id, str) and avatar_id.startswith('A00'):
        logger.debug(f"[agent_handler] System avatar {avatar_id}, skipping cloud sync")
        return
    
    try:
        ctx = get_handler_context(request, params)
        if not ctx:
            logger.warning("[agent_handler] Context not available for avatar sync")
            return
        
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            logger.warning("[agent_handler] DB manager not available for avatar sync")
            return
        
        # Get avatar resource from database
        from agent.db.models.avatar_model import DBAvatarResource
        with ec_db_mgr.get_session() as db_session:
            avatar_resource = db_session.query(DBAvatarResource).filter_by(id=avatar_id).first()
        
        if not avatar_resource:
            logger.warning(f"[agent_handler] Avatar resource not found: {avatar_id}")
            return
        
        # Only sync uploaded and generated avatars (not system avatars)
        if avatar_resource.resource_type not in ['uploaded', 'generated']:
            logger.debug(f"[agent_handler] Avatar type '{avatar_resource.resource_type}' doesn't need cloud sync")
            return
        
        # Check if already synced (unless it's a DELETE operation)
        if operation != Operation.DELETE and avatar_resource.cloud_synced:
            logger.debug(f"[agent_handler] Avatar {avatar_id} already synced to cloud")
            return
        
        # Prepare avatar data for cloud sync
        from agent.cloud_api.offline_sync_manager import get_sync_manager
        from agent.cloud_api.constants import DataType
        
        manager = get_sync_manager()
        
        # Use to_dict() method to get avatar resource data
        avatar_sync_data = avatar_resource.to_dict()
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Avatar resource synced to cloud: {avatar_id}")
                # Update cloud_synced flag in database
                try:
                    with ec_db_mgr.get_session() as db_session:
                        avatar_db = db_session.query(DBAvatarResource).filter_by(id=avatar_id).first()
                        if avatar_db:
                            avatar_db.cloud_synced = True
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update cloud_synced flag: {e}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Avatar resource cached for later sync: {avatar_id}")
            elif not result.get('success'):
                logger.error(f"[agent_handler] ❌ Failed to sync avatar resource: {result.get('error')}")
            # Invoke caller's callback regardless (e.g. to trigger agent sync after avatar)
            if callback:
                callback(result)

        # Trigger async cloud sync for avatar resource
        logger.info(f"[agent_handler] Syncing avatar resource to cloud: {avatar_id} ({operation})")
        manager.sync_to_cloud_async(DataType.AVATAR_RESOURCE, avatar_sync_data, operation, callback=_log_result)
        
        # Upload files to cloud storage (S3) only for uploaded/generated avatars with local files
        if operation != Operation.DELETE:
            # Only upload files for custom avatars (uploaded or generated)
            if avatar_resource.resource_type in ['uploaded', 'generated']:
                # Check if there are local files to upload
                has_local_files = (
                    (avatar_resource.image_path and avatar_resource.image_path.strip()) or
                    (avatar_resource.video_path and avatar_resource.video_path.strip())
                )
                if has_local_files:
                    from agent.avatar.avatar_cloud_sync import upload_avatar_to_cloud_async
                    upload_avatar_to_cloud_async(avatar_resource, db_service=ec_db_mgr.avatar_service)
                else:
                    logger.debug(f"[agent_handler] No local files to upload for avatar: {avatar_id}")
            else:
                logger.debug(f"[agent_handler] Avatar type '{avatar_resource.resource_type}' doesn't need file upload")
        
    except Exception as e:
        logger.error(f"[agent_handler] Error syncing avatar to cloud: {e}")
        import traceback
        logger.debug(traceback.format_exc())


# Removed: _upload_avatar_files_to_cloud() is now in agent.avatar.avatar_cloud_sync
# Use: from agent.avatar.avatar_cloud_sync import upload_avatar_to_cloud_async


def _check_and_cleanup_orphaned_avatar(avatar_id: str, deleted_agent_id: str, username: str, request=None, params=None) -> bool:
    """Check if an avatar is orphaned and clean it up if needed
    
    An avatar is orphaned if no other agents are using it after the current agent is deleted.
    
    Args:
        avatar_id: Avatar resource ID to check
        deleted_agent_id: ID of the agent being deleted
        username: Owner username
        request: IPC request object (optional)
        params: Request parameters (optional)
        
    Returns:
        True if avatar was orphaned and cleaned up, False otherwise
    """
    try:
        ctx = get_handler_context(request, params)
        if not ctx:
            logger.warning("[agent_handler] Context not available for avatar cleanup")
            return False
        
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            logger.warning("[agent_handler] DB manager not available for avatar cleanup")
            return False
        
        agent_service = ec_db_mgr.agent_service
        
        # Query all agents with this avatar_id (excluding the one being deleted)
        result = agent_service.query_agents_with_relations(
            avatar_id=avatar_id,
            owner=username
        )
        
        if not result.get('success'):
            logger.warning(f"[agent_handler] Failed to query agents with avatar {avatar_id}")
            return False
        
        agents_with_avatar = result.get('data', [])
        
        # Filter out the agent being deleted
        other_agents = [ag for ag in agents_with_avatar if ag.get('id') != deleted_agent_id]
        
        if len(other_agents) > 0:
            logger.info(f"[agent_handler] Avatar {avatar_id} is still used by {len(other_agents)} other agent(s), not deleting")
            return False
        
        # Avatar is orphaned, delete it from database and cloud
        logger.info(f"[agent_handler] Avatar {avatar_id} is orphaned, cleaning up...")
        
        # Delete from database
        from agent.db.models.avatar_model import DBAvatarResource
        with ec_db_mgr.get_session() as db_session:
            avatar_resource = db_session.query(DBAvatarResource).filter_by(id=avatar_id).first()
        
        if avatar_resource:
            # Delete local files
            import os
            if avatar_resource.image_path and os.path.exists(avatar_resource.image_path):
                try:
                    os.remove(avatar_resource.image_path)
                    logger.info(f"[agent_handler] Deleted local avatar image: {avatar_resource.image_path}")
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to delete local image: {e}")
            
            if avatar_resource.video_path and os.path.exists(avatar_resource.video_path):
                try:
                    os.remove(avatar_resource.video_path)
                    logger.info(f"[agent_handler] Deleted local avatar video: {avatar_resource.video_path}")
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to delete local video: {e}")
            
            # Delete from database
            with ec_db_mgr.get_session() as db_session:
                avatar_to_delete = db_session.query(DBAvatarResource).filter_by(id=avatar_id).first()
                if avatar_to_delete:
                    db_session.delete(avatar_to_delete)
            logger.info(f"[agent_handler] Deleted avatar resource from database: {avatar_id}")
            
            # Sync deletion to cloud (async)
            avatar_data = {
                'id': avatar_id,
                'owner': username,
                'resource_type': avatar_resource.resource_type
            }
            _sync_agent_avatar_to_cloud(avatar_data, Operation.DELETE, request, params)
            
            return True
        else:
            logger.warning(f"[agent_handler] Avatar resource not found in database: {avatar_id}")
            return False
        
    except Exception as e:
        logger.error(f"[agent_handler] Error checking/cleaning orphaned avatar: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return False


@IPCHandlerRegistry.handler('query_agent_org_rels')
def handle_query_agent_org_rels(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Query agent-organization relationships
    
    Args:
        request: IPC request
        params: Optional parameters containing input JSON with agent_id, limit, offset
        
    Returns:
        IPCResponse with list of agent-org relationships
    """
    try:
        request_params = request.get('params', {})
        input_str = request_params.get('input', '{}')
        
        # Parse input JSON
        import json
        input_data = json.loads(input_str) if isinstance(input_str, str) else input_str
        
        agent_id = input_data.get('agent_id')
        limit = input_data.get('limit', 500)
        offset = input_data.get('offset', 0)
        
        logger.debug(f"[agent_handler] query_agent_org_rels: agent_id={agent_id}, limit={limit}, offset={offset}")
        
        # Get database manager
        ctx = get_handler_context(request, params)
        if not ctx:
            return create_error_response(request, 'CONTEXT_NOT_AVAILABLE', 'Context not available')

        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            return create_error_response(request, 'DB_NOT_AVAILABLE', 'Database manager not available')
        
        # Query relationships from database
        from agent.db.models.association_models import DBAgentOrgRel
        with ec_db_mgr.get_session() as db_session:
            query = db_session.query(DBAgentOrgRel)
            if agent_id:
                query = query.filter(DBAgentOrgRel.agent_id == agent_id)

            # Apply pagination
            total_count = query.count()
            rels = query.offset(offset).limit(limit).all()
            
            # Convert to dict INSIDE session to avoid DetachedInstanceError
            result = []
            for rel in rels:
                result.append({
                    'id': rel.id,
                    'agent_id': rel.agent_id,
                    'org_id': rel.org_id,
                    'created_at': rel.created_at.isoformat() if hasattr(rel, 'created_at') and rel.created_at else None,
                    'updated_at': rel.updated_at.isoformat() if hasattr(rel, 'updated_at') and rel.updated_at else None
                })
        
        logger.info(f"[agent_handler] Retrieved {len(result)} agent-org relationships (total: {total_count})")
        
        # Return as JSON string for GraphQL compatibility
        import json
        return create_success_response(request, json.dumps(result))
        
    except Exception as e:
        logger.error(f"[agent_handler] Error querying agent-org relationships: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'QUERY_ERROR', str(e))


@IPCHandlerRegistry.handler('query_agent_skill_rels')
def handle_query_agent_skill_rels(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Query agent-skill relationships
    
    Args:
        request: IPC request
        params: Optional parameters containing input JSON with agent_id, limit, offset
        
    Returns:
        IPCResponse with list of agent-skill relationships
    """
    try:
        request_params = request.get('params', {})
        input_str = request_params.get('input', '{}')
        
        # Parse input JSON
        import json
        input_data = json.loads(input_str) if isinstance(input_str, str) else input_str
        
        agent_id = input_data.get('agent_id')
        limit = input_data.get('limit', 500)
        offset = input_data.get('offset', 0)
        
        logger.debug(f"[agent_handler] query_agent_skill_rels: agent_id={agent_id}, limit={limit}, offset={offset}")
        
        # Get database manager
        ctx = get_handler_context(request, params)
        if not ctx:
            return create_error_response(request, 'CONTEXT_NOT_AVAILABLE', 'Context not available')

        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            return create_error_response(request, 'DB_NOT_AVAILABLE', 'Database manager not available')
        
        # Query relationships from database
        from agent.db.models.association_models import DBAgentSkillRel
        from sqlalchemy.orm import make_transient
        
        # Must convert to dict INSIDE the with block to avoid detached instance errors
        result = []
        total_count = 0
        with ec_db_mgr.get_session() as db_session:
            query = db_session.query(DBAgentSkillRel)
            if agent_id:
                query = query.filter(DBAgentSkillRel.agent_id == agent_id)

            # Apply pagination
            total_count = query.count()
            rels = query.offset(offset).limit(limit).all()
        
            # Convert to dict inside the with block to ensure session is still open
            for rel in rels:
                # Make a detached copy using make_transient to avoid session issues
                rel_copy = rel.__class__(rel.id, rel.agent_id, rel.skill_id)
                if hasattr(rel, 'created_at'):
                    rel_copy.created_at = rel.created_at
                if hasattr(rel, 'updated_at'):
                    rel_copy.updated_at = rel.updated_at
                if hasattr(rel, 'status'):
                    rel_copy.status = rel.status
                make_transient(rel_copy)
                result.append({
                    'id': rel_copy.id,
                    'agent_id': rel_copy.agent_id,
                    'skill_id': rel_copy.skill_id,
                    'created_at': rel_copy.created_at.isoformat() if hasattr(rel_copy, 'created_at') and rel_copy.created_at else None,
                    'updated_at': rel_copy.updated_at.isoformat() if hasattr(rel_copy, 'updated_at') and rel_copy.updated_at else None
                })
        
        logger.info(f"[agent_handler] Retrieved {len(result)} agent-skill relationships (total: {total_count})")
        
        # Return as JSON string for GraphQL compatibility
        import json
        return create_success_response(request, json.dumps(result))
        
    except Exception as e:
        logger.error(f"[agent_handler] Error querying agent-skill relationships: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'QUERY_ERROR', str(e))


@IPCHandlerRegistry.handler('query_agent_task_rels')
def handle_query_agent_task_rels(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Query agent-task relationships
    
    Args:
        request: IPC request
        params: Optional parameters containing input JSON with agent_id, limit, offset
        
    Returns:
        IPCResponse with list of agent-task relationships
    """
    try:
        request_params = request.get('params', {})
        input_str = request_params.get('input', '{}')
        
        # Parse input JSON
        import json
        input_data = json.loads(input_str) if isinstance(input_str, str) else input_str
        
        agent_id = input_data.get('agent_id')
        limit = input_data.get('limit', 500)
        offset = input_data.get('offset', 0)
        
        logger.debug(f"[agent_handler] query_agent_task_rels: agent_id={agent_id}, limit={limit}, offset={offset}")
        
        # Get database manager
        ctx = get_handler_context(request, params)
        if not ctx:
            return create_error_response(request, 'CONTEXT_NOT_AVAILABLE', 'Context not available')
        
        ec_db_mgr = ctx.get_ec_db_mgr()
        if not ec_db_mgr:
            return create_error_response(request, 'DB_NOT_AVAILABLE', 'Database manager not available')
        
        # Query relationships from database
        from agent.db.models.association_models import DBAgentTaskRel
        with ec_db_mgr.get_session() as db_session:
            query = db_session.query(DBAgentTaskRel)
            if agent_id:
                query = query.filter(DBAgentTaskRel.agent_id == agent_id)

            # Apply pagination
            total_count = query.count()
            rels = query.offset(offset).limit(limit).all()
            
            # Convert to dict INSIDE session to avoid DetachedInstanceError
            result = []
            for rel in rels:
                result.append({
                    'id': rel.id,
                    'agent_id': rel.agent_id,
                    'task_id': rel.task_id,
                    'created_at': rel.created_at.isoformat() if hasattr(rel, 'created_at') and rel.created_at else None,
                    'updated_at': rel.updated_at.isoformat() if hasattr(rel, 'updated_at') and rel.updated_at else None
                })
        
        logger.info(f"[agent_handler] Retrieved {len(result)} agent-task relationships (total: {total_count})")
        
        # Return as JSON string for GraphQL compatibility
        import json
        return create_success_response(request, json.dumps(result))
        
    except Exception as e:
        logger.error(f"[agent_handler] Error querying agent-task relationships: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'QUERY_ERROR', str(e))


@IPCHandlerRegistry.handler('get_agent_runtime_status')
def handle_get_agent_runtime_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get agent runtime status: disabled / stopped / standby / working.

    - disabled: agent DB status is 'disabled' (persistent — won't auto-start on app restart)
    - stopped: agent is enabled in DB but not loaded/running in memory
    - standby: agent is running and only has chat/message-trigger tasks (or no tasks)
    - working: agent is running and has at least one non-chat task

    Params:
        agent_id: str - agent ID
    Returns:
        { agent_id, runtime_status, enabled, active_task_count, detail }
    """
    try:
        agent_id = (params or {}).get('agent_id')
        if not agent_id:
            return create_error_response(request, 'MISSING_PARAM', 'agent_id is required')

        mainwin = get_handler_context()
        if not mainwin:
            return create_error_response(request, 'CONTEXT_ERROR', 'Handler context not available')

        # Step 1: Check if agent is in memory FIRST (most accurate for runtime status)
        ec_agent = None
        agents = mainwin.get_agents() if hasattr(mainwin, 'get_agents') else getattr(mainwin, 'agents', []) or []
        for ag in agents:
            cid = getattr(getattr(ag, 'card', None), 'id', None)
            if cid == agent_id:
                ec_agent = ag
                break

        # Step 2: Check DB status for enabled/disabled state
        ec_db_mgr = AppContext.get_ec_db_mgr()
        db_status = 'active'
        if ec_db_mgr:
            try:
                agent_service = ec_db_mgr.agent_service
                result = agent_service.query_agents_with_relations(id=agent_id, include_skills=False, include_tasks=False, include_org=False)
                if result.get('success') and result.get('data'):
                    db_agent_dict = result['data'][0]
                    db_status = db_agent_dict.get('status', 'active') or 'active'
            except Exception:
                pass

        is_enabled = db_status != 'disabled'

        # Log for debugging status sync issues
        agent_name = getattr(getattr(ec_agent, 'card', None), 'name', '?') if ec_agent else '?'
        # Also log all agent card IDs in memory for diagnosing lookup mismatches
        mem_ids = [getattr(getattr(ag, 'card', None), 'id', '?') for ag in agents]

        # If DB says disabled, that's the persistent off — regardless of memory state
        if not is_enabled:
            logger.info(f"[agent_handler] Status: {agent_id} → disabled (db_status={db_status}, in_memory={ec_agent is not None})")
            return create_success_response(request, {
                'agent_id': agent_id,
                'runtime_status': 'disabled',
                'enabled': False,
                'active_task_count': 0,
                'detail': 'Agent is disabled (will not auto-start)'
            })

        # Agent is enabled but not in memory → stopped
        if not ec_agent:
            logger.info(f"[agent_handler] Status: {agent_id} → stopped (db_status={db_status}, "
                        f"not found in {len(agents)} agents, mem_ids={mem_ids})")
            return create_success_response(request, {
                'agent_id': agent_id,
                'runtime_status': 'stopped',
                'enabled': True,
                'active_task_count': 0,
                'detail': 'Agent is enabled but not running'
            })

        # Count active tasks and determine if any are non-chat
        active_count = 0
        with ec_agent.task_lock:
            active_count = len(ec_agent.active_tasks)

        has_non_chat_task = False
        task_details = []
        for task in ec_agent.tasks:
            run_id = getattr(task, 'run_id', None)
            is_running = ec_agent.is_task_running(run_id) if run_id else False
            triggers = getattr(task, 'trigger', []) or []
            task_details.append(f"{getattr(task, 'name', '?')}(run_id={run_id}, running={is_running}, triggers={triggers})")
            if run_id and is_running:
                chat_triggers = {'message', 'interaction', 'human chat', 'agent message',
                                 'a2a_queue', 'chat_queue'}
                is_chat_only = all(t.lower() in chat_triggers for t in triggers) if triggers else False
                if not is_chat_only:
                    has_non_chat_task = True

        runtime_status = 'working' if has_non_chat_task else 'standby'

        logger.info(f"[agent_handler] Status: {agent_name}({agent_id}) → {runtime_status} "
                    f"(db={db_status}, active_tasks={active_count}, tasks={task_details})")

        return create_success_response(request, {
            'agent_id': agent_id,
            'runtime_status': runtime_status,
            'enabled': True,
            'active_task_count': active_count,
            'detail': f'{active_count} active task(s)'
        })

    except Exception as e:
        logger.error(f"[agent_handler] Error getting agent runtime status: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'STATUS_ERROR', str(e))


# Cache for batch status DB query to avoid hitting SQLite every poll cycle
_batch_status_db_cache = {'data': {}, 'timestamp': 0.0, 'ttl': 30.0}  # 30s TTL


@IPCHandlerRegistry.handler('get_all_agents_runtime_status')
def handle_get_all_agents_runtime_status(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get runtime status for ALL agents in one call (efficient batch endpoint for polling).

    Returns:
        { agents: [ { agent_id, agent_name, runtime_status, enabled, active_task_count } ] }
    """
    try:
        mainwin = get_handler_context()
        if not mainwin:
            return create_error_response(request, 'CONTEXT_ERROR', 'Handler context not available')

        # Get all agents from DB to know enabled/disabled state (with cache)
        import time as _time
        now = _time.time()
        db_status_map = {}  # agent_id -> db_status

        if now - _batch_status_db_cache['timestamp'] < _batch_status_db_cache['ttl']:
            # Use cached DB status
            db_status_map = _batch_status_db_cache['data']
        else:
            # Refresh from DB
            ec_db_mgr = AppContext.get_ec_db_mgr()
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    mw = _get_main_window()
                    user = getattr(mw, 'user', None) if mw else None
                    if not user:
                        user = mainwin.get_username() if hasattr(mainwin, 'get_username') else None
                    if user:
                        result = agent_service.get_agents_by_owner(user)
                        if result.get('success'):
                            for ag_dict in result.get('data', []):
                                aid = ag_dict.get('id')
                                if aid:
                                    db_status_map[aid] = ag_dict.get('status', 'active') or 'active'
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to load DB agent statuses: {e}")
            _batch_status_db_cache['data'] = db_status_map
            _batch_status_db_cache['timestamp'] = now

        # Build in-memory agent map: agent_id -> ec_agent
        agents = mainwin.get_agents() if hasattr(mainwin, 'get_agents') else getattr(mainwin, 'agents', []) or []
        mem_agent_map = {}
        for ag in agents:
            cid = getattr(getattr(ag, 'card', None), 'id', None)
            if cid:
                mem_agent_map[cid] = ag

        # Combine: iterate all known agent IDs from both DB and memory
        all_ids = set(db_status_map.keys()) | set(mem_agent_map.keys())
        results = []

        chat_triggers = {'message', 'interaction', 'human chat', 'agent message',
                         'a2a_queue', 'chat_queue'}

        for agent_id in all_ids:
            db_status = db_status_map.get(agent_id, 'active')
            is_enabled = db_status != 'disabled'
            ec_agent = mem_agent_map.get(agent_id)
            agent_name = getattr(getattr(ec_agent, 'card', None), 'name', None) if ec_agent else None

            if not is_enabled:
                results.append({
                    'agent_id': agent_id,
                    'agent_name': agent_name,
                    'runtime_status': 'disabled',
                    'enabled': False,
                    'active_task_count': 0,
                })
                continue

            if not ec_agent:
                results.append({
                    'agent_id': agent_id,
                    'agent_name': agent_name,
                    'runtime_status': 'stopped',
                    'enabled': True,
                    'active_task_count': 0,
                })
                continue

            # Agent is in memory — determine standby/working
            active_count = 0
            with ec_agent.task_lock:
                active_count = len(ec_agent.active_tasks)

            has_non_chat_task = False
            for task in ec_agent.tasks:
                run_id = getattr(task, 'run_id', None)
                if run_id and ec_agent.is_task_running(run_id):
                    triggers = getattr(task, 'trigger', []) or []
                    is_chat_only = all(t.lower() in chat_triggers for t in triggers) if triggers else False
                    if not is_chat_only:
                        has_non_chat_task = True
                        break

            runtime_status = 'working' if has_non_chat_task else 'standby'
            results.append({
                'agent_id': agent_id,
                'agent_name': agent_name or getattr(getattr(ec_agent, 'card', None), 'name', '?'),
                'runtime_status': runtime_status,
                'enabled': True,
                'active_task_count': active_count,
            })

        # Log summary at debug level to avoid I/O overhead on every poll
        summary = [(r['agent_name'] or r['agent_id'][:8], r['runtime_status'], r.get('active_task_count', 0)) for r in results]
        logger.debug(f"[agent_handler] Batch status: db_agents={len(db_status_map)}, mem_agents={len(mem_agent_map)}, "
                     f"mem_ids={list(mem_agent_map.keys())}, results={summary}")

        return create_success_response(request, {'agents': results})

    except Exception as e:
        logger.error(f"[agent_handler] Error getting all agent runtime statuses: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'STATUS_ERROR', str(e))


@IPCHandlerRegistry.handler('toggle_agent_enabled')
def handle_toggle_agent_enabled(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Start or stop an agent (runtime control, does NOT change enabled/disabled state).

    - enable=true: set DB status to 'active', load agent into memory, call ec_agent.start()
    - enable=false: cancel all active tasks, remove agent from memory, set DB status to 'inactive'

    Params:
        agent_id: str
        enable: bool
    Returns:
        { agent_id, runtime_status }
    """
    try:
        agent_id = (params or {}).get('agent_id')
        enable = (params or {}).get('enable')
        if not agent_id or enable is None:
            return create_error_response(request, 'MISSING_PARAM', 'agent_id and enable are required')

        mainwin = get_handler_context()
        if not mainwin:
            return create_error_response(request, 'CONTEXT_ERROR', 'Handler context not available')

        # Invalidate DB cache so next poll gets fresh data
        _batch_status_db_cache['timestamp'] = 0.0

        ec_db_mgr = AppContext.get_ec_db_mgr()

        if enable:
            # --- START ---
            # Update DB status to active
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    agent_service.update_agent(agent_id, {'status': 'active'})
                    # Sync to cloud
                    _sync_agent_status_to_cloud(agent_service, agent_id, 'active')
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update DB status: {e}")

            # Check if already loaded
            agents = mainwin.get_agents() if hasattr(mainwin, 'get_agents') else getattr(mainwin, 'agents', []) or []
            ec_agent = None
            for ag in agents:
                cid = getattr(getattr(ag, 'card', None), 'id', None)
                if cid == agent_id:
                    ec_agent = ag
                    break

            if ec_agent:
                # Already in memory - just start if not already running
                with ec_agent.task_lock:
                    if len(ec_agent.active_tasks) == 0:
                        ec_agent.start()
                return create_success_response(request, {
                    'agent_id': agent_id,
                    'runtime_status': 'standby'
                })

            # Not in memory - load from DB and start
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    result = agent_service.query_agents_with_relations(id=agent_id)
                    if result.get('success') and result.get('data'):
                        agent_dict = result['data'][0]
                        converter = _get_converter()
                        mw = _get_main_window()
                        if converter and mw:
                            ec_agent = converter(agent_dict, mw)
                            if ec_agent:
                                mw.agents.append(ec_agent)
                                ec_agent.start()
                                logger.info(f"[agent_handler] Agent {agent_id} loaded and started")
                            else:
                                return create_error_response(request, 'START_ERROR', 'Failed to convert agent from DB')
                        else:
                            return create_error_response(request, 'START_ERROR', 'Agent converter not available')
                    else:
                        return create_error_response(request, 'START_ERROR', f'Agent {agent_id} not found in database')
                except Exception as e:
                    logger.error(f"[agent_handler] Failed to load and start agent: {e}")
                    logger.debug(traceback.format_exc())
                    return create_error_response(request, 'START_ERROR', str(e))

            return create_success_response(request, {
                'agent_id': agent_id,
                'runtime_status': 'standby'
            })

        else:
            # --- STOP ---
            # Find agent in memory and cancel all tasks
            agents = mainwin.get_agents() if hasattr(mainwin, 'get_agents') else getattr(mainwin, 'agents', []) or []
            ec_agent = None
            for ag in agents:
                cid = getattr(getattr(ag, 'card', None), 'id', None)
                if cid == agent_id:
                    ec_agent = ag
                    break

            if ec_agent:
                # Cancel all active task futures
                with ec_agent.task_lock:
                    for run_id, future in list(ec_agent.active_tasks.items()):
                        try:
                            future.cancel()
                            logger.info(f"[agent_handler] Cancelled task run_id={run_id}")
                        except Exception as e:
                            logger.warning(f"[agent_handler] Failed to cancel task {run_id}: {e}")
                    ec_agent.active_tasks.clear()

                # Remove from agents list
                mw = _get_main_window()
                if mw:
                    mw.agents = [ag for ag in agents
                                 if getattr(getattr(ag, 'card', None), 'id', None) != agent_id]
                logger.info(f"[agent_handler] Agent {agent_id} stopped and removed from memory")

            # Update DB status to inactive (not 'disabled' — that's the persistent off)
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    agent_service.update_agent(agent_id, {'status': 'inactive'})
                    # Sync to cloud
                    _sync_agent_status_to_cloud(agent_service, agent_id, 'inactive')
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update DB status: {e}")

            return create_success_response(request, {
                'agent_id': agent_id,
                'runtime_status': 'stopped'
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error toggling agent: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'TOGGLE_ERROR', str(e))


@IPCHandlerRegistry.handler('set_agent_enabled')
def handle_set_agent_enabled(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Enable or disable an agent (persistent — survives app restart).

    - enabled=true: set DB status to 'active' (agent can be started, will auto-start on next app launch)
    - enabled=false: set DB status to 'disabled', also stop the agent if running

    Params:
        agent_id: str
        enabled: bool
    Returns:
        { agent_id, enabled, runtime_status }
    """
    try:
        agent_id = (params or {}).get('agent_id')
        enabled = (params or {}).get('enabled')
        if not agent_id or enabled is None:
            return create_error_response(request, 'MISSING_PARAM', 'agent_id and enabled are required')

        mainwin = get_handler_context()
        if not mainwin:
            return create_error_response(request, 'CONTEXT_ERROR', 'Handler context not available')

        # Invalidate DB cache so next poll gets fresh data
        _batch_status_db_cache['timestamp'] = 0.0

        ec_db_mgr = AppContext.get_ec_db_mgr()

        if enabled:
            # --- ENABLE ---
            # Set DB status to 'active' so agent will auto-start on next app launch
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    agent_service.update_agent(agent_id, {'status': 'active'})
                    logger.info(f"[agent_handler] Agent {agent_id} enabled (status='active')")
                    # Sync to cloud
                    _sync_agent_status_to_cloud(agent_service, agent_id, 'active')
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update DB status: {e}")

            return create_success_response(request, {
                'agent_id': agent_id,
                'enabled': True,
                'runtime_status': 'stopped'  # enabled but not yet started
            })

        else:
            # --- DISABLE ---
            # First stop the agent if it's running
            agents = mainwin.get_agents() if hasattr(mainwin, 'get_agents') else getattr(mainwin, 'agents', []) or []
            ec_agent = None
            for ag in agents:
                cid = getattr(getattr(ag, 'card', None), 'id', None)
                if cid == agent_id:
                    ec_agent = ag
                    break

            if ec_agent:
                with ec_agent.task_lock:
                    for run_id, future in list(ec_agent.active_tasks.items()):
                        try:
                            future.cancel()
                            logger.info(f"[agent_handler] Cancelled task run_id={run_id}")
                        except Exception:
                            pass
                    ec_agent.active_tasks.clear()
                mw = _get_main_window()
                if mw:
                    mw.agents = [ag for ag in agents
                                 if getattr(getattr(ag, 'card', None), 'id', None) != agent_id]
                logger.info(f"[agent_handler] Agent {agent_id} stopped (disabling)")

            # Set DB status to 'disabled' — agent won't auto-start on next app launch
            if ec_db_mgr:
                try:
                    agent_service = ec_db_mgr.agent_service
                    agent_service.update_agent(agent_id, {'status': 'disabled'})
                    logger.info(f"[agent_handler] Agent {agent_id} disabled (status='disabled')")
                    # Sync to cloud
                    _sync_agent_status_to_cloud(agent_service, agent_id, 'disabled')
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update DB status: {e}")

            return create_success_response(request, {
                'agent_id': agent_id,
                'enabled': False,
                'runtime_status': 'disabled'
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error setting agent enabled: {e}")
        logger.debug(traceback.format_exc())
        return create_error_response(request, 'ENABLE_ERROR', str(e))
