import traceback
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Dict
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from utils.logger_helper import logger_helper as logger
from agent.ec_org_ctrl import get_ec_org_ctrl
from agent.cloud_api.constants import Operation
convert_agent_dict_to_ec_agent = None  # Lazy import to avoid circulars


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


def _json_safe(value, depth: int = 0):
    """Recursively convert values to JSON-serializable structures.

    - Pydantic models: use model_dump(mode="python")
    - Objects with __dict__: use vars()
    - Dicts/lists/sets/tuples: sanitize recursively
    - Fallback: str(value)
    """
    try:
        # Prevent extremely deep recursion
        if depth > 8:
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, dict):
            safe_dict = {}
            for k, v in value.items():
                key = str(k)
                safe_dict[key] = _json_safe(v, depth + 1)
            return safe_dict
        if isinstance(value, (list, tuple, set)):
            return [_json_safe(v, depth + 1) for v in value]
        # Pydantic BaseModel-like
        if hasattr(value, 'model_dump') and callable(getattr(value, 'model_dump')):
            try:
                return _json_safe(value.model_dump(mode="python"), depth + 1)
            except Exception:
                pass
        # Generic objects
        if hasattr(value, '__dict__'):
            try:
                return _json_safe(vars(value), depth + 1)
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
        """Build a single tree node with its children and agents"""
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
            'agents': agents_by_org.get(org_data.get('_normalized_id'), [])
        }

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
        logger.info(f"{prefix}- {node['name']} (id: {node['id']}) - {len(node.get('agents', []))} agents, {len(node.get('children', []))} children")
        for child in node.get('children', []):
            log_tree_structure(child, indent + 1)
    
    logger.info(f"[agent_handler] Built integrated tree structure:")
    logger.info(f"  - Total organizations processed: {len(organizations)}")
    logger.info(f"  - Unassigned agents: {len(unassigned_agents)}")
    logger.info(f"Tree structure:")
    # log_tree_structure(tree_root)
    
    return tree_root


@IPCHandlerRegistry.handler('get_agents')
def handle_get_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle get agents request

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
        if not ctx.get_ec_db_mgr() or not ctx.get_ec_db_mgr().agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')

        # Get all agents from memory (MainWindow.agents contains the most up-to-date data)
        # This includes both database agents and special agents like MyTwinAgent
        memory_agents = ctx.get_agents() or []
        
        # If specific agent IDs are requested, query from database with relations to get tasks/skills
        if agent_ids and len(agent_ids) > 0:
            logger.info(f"[agent_handler] Querying agents from database with relations for IDs: {agent_ids}")
            agent_service = ctx.get_ec_db_mgr().agent_service
            
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
        
        # Debug: log the first agent's skills/tasks to verify serialization
        if agents_data and len(agents_data) > 0:
            sample_agent = agents_data[0]
            logger.info(f"[agent_handler] Sample agent data: id={sample_agent.get('id')}, skills={len(sample_agent.get('skills', []))}, tasks={len(sample_agent.get('tasks', []))}")
        
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
        if not ctx.get_ec_db_mgr() or not ctx.get_ec_db_mgr().agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = ctx.get_ec_db_mgr().agent_service
        
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
                
                # Step 1: Update agent in database first
                logger.info(f"[agent_handler] Updating agent {agent_id} with fields: {list(agent_data.keys())}")
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
                    # Sync Agent entity
                    _trigger_cloud_sync(agent_data, Operation.UPDATE)
                    
                    # Sync Agent-Skill relationships (if changed)
                    if 'skills' in agent_data:
                        _sync_agent_skill_relations(updated_agent_data, agent_data.get('skills', []), Operation.UPDATE)
                    
                    # Sync Agent-Task relationships (if changed)
                    if 'tasks' in agent_data:
                        _sync_agent_task_relations(updated_agent_data, agent_data.get('tasks', []), Operation.UPDATE)
                    
                    # Sync Agent-Tool relationships (if changed)
                    if 'tools' in agent_data:
                        _sync_agent_tool_relations(updated_agent_data, agent_data.get('tools', []), Operation.UPDATE)
                    
                    # Sync Agent's Avatar resource to cloud (if avatar changed)
                    if 'avatar_id' in agent_data:
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
        username = params.get('username')
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')
        
        # Get agent_id parameter (can be a single string or array)
        agent_id_param = params.get('agent_id')
        
        if not agent_id_param:
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
        if not ctx.get_ec_db_mgr() or not ctx.get_ec_db_mgr().agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = ctx.get_ec_db_mgr().agent_service
        
        # Delete each agent from database and memory
        deleted_count = 0
        errors = []
        
        for agent_id in agent_ids:
            try:
                # Step 1: Delete from database first
                result = agent_service.delete_agent(agent_id)
                
                if result.get('success'):
                    try:
                        agents = ctx.get_agents()
                        original_count = len(agents)
                        # Step 2: Delete from memory after database deletion succeeds
                        agents[:] = [ag for ag in agents if ag.card.id != agent_id]
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
                        # Get the deleted agent's avatar_id before it's removed from memory
                        deleted_agent = next((ag for ag in ctx.get_agents() if ag.card.id == agent_id), None)
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
        if not ctx.get_ec_db_mgr():
            logger.error(f"[agent_handler] Database manager not available")
            return create_error_response(request, 'DB_ERROR', 'Database manager not available')

        agent_service = ctx.get_ec_db_mgr().agent_service
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
        # Sync Agent entity
        _trigger_cloud_sync(created_agent, Operation.ADD)
        
        # Sync Agent-Skill relationships
        _sync_agent_skill_relations(created_agent, agent_data.get('skills', []), Operation.ADD)
        
        # Sync Agent-Task relationships
        _sync_agent_task_relations(created_agent, agent_data.get('tasks', []), Operation.ADD)
        
        # Sync Agent-Tool relationships
        _sync_agent_tool_relations(created_agent, agent_data.get('tools', []), Operation.ADD)
        
        # Sync Agent's Avatar resource to cloud (if has custom avatar)
        _sync_agent_avatar_to_cloud(created_agent, Operation.ADD, request, params)

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
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for get_all_org_agents: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        logger.info(f"[agent_handler] Getting all organizations and agents for user: {username}")
        
        # Get ctx to access integrated agents list
        ctx = get_handler_context(request, params)
        if ctx is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')
        
        # In web mode we may not have DB/config wired yet; fall back to empty structures
        if not ctx.get_ec_db_mgr() or not ctx.get_ec_db_mgr().agent_service:
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
        
        # 🔥 Optimization: Prefer memory, sync from database if memory is empty
        # This ensures both performance and data consistency
        all_agents = []
        
        if ctx.get_agents():
            # Data in memory, use directly (best performance)
            all_agents = [agent.to_dict(owner=username) for agent in ctx.get_agents()]
            logger.info(f"[agent_handler] Retrieved {len(all_agents)} agents from memory")
        else:
            # Memory empty, sync from database (ensure data availability)
            logger.warning(f"[agent_handler] Memory cache empty, syncing from database...")
            try:
                # Get database service from ctx
                if not ctx.get_ec_db_mgr() or not ctx.get_ec_db_mgr().agent_service:
                    logger.error(f"[agent_handler] Database service not available")
                    return create_error_response(request, 'DB_ERROR', 'Database service not available')
                
                db_service = ctx.get_ec_db_mgr().agent_service
                db_result = db_service.get_agents_by_owner(username)
                
                # Improved error handling - check if db_result is valid
                if not db_result:
                    logger.error(f"[agent_handler] Failed to query agents from database: db_service returned None")
                elif not isinstance(db_result, dict):
                    logger.error(f"[agent_handler] Failed to query agents from database: unexpected result type {type(db_result)}")
                elif db_result.get('success'):
                    # Note: data can be empty list [], which is valid
                    db_agents = db_result.get('data') or []
                    logger.info(f"[agent_handler] Retrieved {len(db_agents)} agents from database")
                    
                    # Convert to EC_Agent and add to memory
                    converter = _get_converter()
                    if not converter:
                        logger.error("[agent_handler] Agent converter unavailable; returning DB agent dicts")
                        all_agents.extend(db_agents)
                    else:
                        agents = ctx.get_agents()
                        agents.clear()
                        for db_agent_dict in db_agents:
                            try:
                                ec_agent = converter(db_agent_dict, ctx.main_window)
                                if ec_agent:
                                    agents.append(ec_agent)
                                    all_agents.append(ec_agent.to_dict(owner=username))
                            except Exception as e:
                                logger.warning(f"[agent_handler] Failed to convert agent: {e}")
                                logger.debug(traceback.format_exc())
                                continue
                    
                    logger.info(f"[agent_handler] Synced {len(ctx.get_agents())} agents to memory")
                else:
                    error_msg = db_result.get('error', 'Unknown error')
                    logger.error(f"[agent_handler] Failed to query agents from database: {error_msg}")
            except Exception as e:
                logger.error(f"[agent_handler] Error syncing agents from database: {e}")
                logger.debug(traceback.format_exc())
        
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

def _trigger_cloud_sync(agent_data: Dict[str, Any], operation: 'Operation') -> None:
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
        if result.get('synced'):
            logger.info(f"[agent_handler] ✅ Agent synced to cloud: {operation} - {agent_data.get('name')}")
        elif result.get('cached'):
            logger.info(f"[agent_handler] 💾 Agent cached for later sync: {operation} - {agent_data.get('name')}")
        elif not result.get('success'):
            logger.error(f"[agent_handler] ❌ Failed to sync agent: {result.get('error')}")
    
    # Use SyncManager's thread pool for async execution
    manager = get_sync_manager()
    manager.sync_to_cloud_async(DataType.AGENT, agent_data, operation, callback=_log_result)


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
            'skid': skill_id,
            'owner': owner
        }
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Skill relation synced: {skill_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Skill relation cached: {skill_id}")
            elif not result.get('success'):
                logger.error(f"[agent_handler] ❌ Failed to sync skill relation: {result.get('error')}")
        
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
            'owner': owner,
            'status': 'assigned'  # Default status
        }
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Task relation synced: {task_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Task relation cached: {task_id}")
            elif not result.get('success'):
                logger.error(f"[agent_handler] ❌ Failed to sync task relation: {result.get('error')}")
        
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
            'owner': owner,
            'permission': 'use'  # Default permission
        }
        
        def _log_result(result: Dict[str, Any]):
            if result.get('synced'):
                logger.info(f"[agent_handler] ✅ Tool relation synced: {tool_id}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Tool relation cached: {tool_id}")
            elif not result.get('success'):
                logger.error(f"[agent_handler] ❌ Failed to sync tool relation: {result.get('error')}")
        
        manager.sync_to_cloud_async(DataType.AGENT_TOOL, tool_relation_data, operation, callback=_log_result)


def _sync_agent_avatar_to_cloud(agent_data: Dict[str, Any], operation: 'Operation', request=None, params=None) -> None:
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
        if not ctx or not ctx.get_ec_db_mgr():
            logger.warning("[agent_handler] MainWindow or DB manager not available for avatar sync")
            return
        
        # Get avatar resource from database
        from agent.db.models.avatar_model import DBAvatarResource
        db_session = ctx.get_ec_db_mgr().get_session()
        
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
                    avatar_resource.cloud_synced = True
                    db_session.commit()
                except Exception as e:
                    logger.warning(f"[agent_handler] Failed to update cloud_synced flag: {e}")
            elif result.get('cached'):
                logger.info(f"[agent_handler] 💾 Avatar resource cached for later sync: {avatar_id}")
            elif not result.get('success'):
                logger.error(f"[agent_handler] ❌ Failed to sync avatar resource: {result.get('error')}")
        
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
                    upload_avatar_to_cloud_async(avatar_resource, db_service=ctx.get_ec_db_mgr().avatar_service)
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
        if not ctx or not ctx.get_ec_db_mgr():
            logger.warning("[agent_handler] MainWindow or DB manager not available for avatar cleanup")
            return False
        
        agent_service = ctx.get_ec_db_mgr().agent_service
        
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
        db_session = ctx.get_ec_db_mgr().get_session()
        
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
            db_session.delete(avatar_resource)
            db_session.commit()
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
