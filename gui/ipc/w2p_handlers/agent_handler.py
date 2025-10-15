import traceback
import uuid
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Dict
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from agent.ec_org_ctrl import get_ec_org_ctrl
from agent.cloud_api.constants import Operation


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
            'description': '根组织',
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
    log_tree_structure(tree_root)
    
    return tree_root


@IPCHandlerRegistry.handler('get_agents')
def handle_get_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"[agent_handler] Get agents handler called with request: {request}")

        # 获取用户名和 agent IDs
        username = params.get('username')
        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Missing username parameter')
        
        # 获取 agent_id 参数（数组）
        agent_ids = params.get('agent_id', [])
        
        logger.info(f"[agent_handler] get agents request for user: {username}, agent_id: {agent_ids}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username} - user may have logged out")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')

        # This ensures we get all agents including newly created ones
        if not main_window.ec_db_mgr or not main_window.ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')

        agent_service = main_window.ec_db_mgr.agent_service

        # If specific agent IDs are requested, filter by them
        if agent_ids and len(agent_ids) > 0:
            # Get all agents first
            result = agent_service.get_agents_by_owner(username)
            if result.get('success'):
                all_agents = result.get('data', [])
                # Filter by requested IDs
                agents_data = [agent for agent in all_agents if agent.get('id') in agent_ids]
                logger.info(f"[agent_handler] Filtered {len(agents_data)} agents from {len(all_agents)} total agents")
            else:
                agents_data = []
        else:
            # Get all agents for the user
            result = agent_service.get_agents_by_owner(username)
            agents_data = result.get('data', []) if result.get('success') else []
        
        if result.get('success'):
            agents_data = agents_data  # Already filtered above
            logger.info(f"[agent_handler] Successfully retrieved {len(agents_data)} agents from database for user: {username}")
            
            resultJS = {
                'agents': agents_data,
                'message': 'Get all successful'
            }
            logger.debug(f"[agent_handler] Successfully retrieved {resultJS}")
            return create_success_response(request, resultJS)
        else:
            logger.error(f"[agent_handler] Failed to get agents: {result.get('error')}")
            # Fallback to memory agents
            agents = getattr(main_window, 'agents', []) or []
            logger.info(f"[agent_handler] Fallback to memory: retrieved {len(agents)} agents")
            resultJS = {
                'agents': [agent.to_dict() for agent in agents],
                'message': 'Get all successful (from memory)'
            }
            return create_success_response(request, resultJS)

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

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Get database service
        if not main_window.ec_db_mgr or not main_window.ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = main_window.ec_db_mgr.agent_service
        
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
                result = agent_service.update_agent(agent_id, agent_data)
                
                if result.get('success'):
                    # Get updated agent data from database
                    updated_agent_data = result.get('data', {})
                    updated_agents.append(updated_agent_data)
                    
                    # Step 2: Update agent in memory after database update succeeds
                    existing_agent = next((ag for ag in main_window.agents if ag.card.id == agent_id), None)
                    if existing_agent:
                        logger.debug(f"[agent_handler] Found agent in memory: {agent_id}, current name: {existing_agent.card.name}")
                        
                        # Update memory agent with new data
                        if 'name' in agent_data:
                            old_name = existing_agent.card.name
                            existing_agent.card.name = agent_data['name']
                            logger.info(f"[agent_handler] Updated agent name in memory: '{old_name}' -> '{agent_data['name']}'")
                        if 'description' in agent_data:
                            existing_agent.card.description = agent_data['description']
                        if 'org_id' in agent_data:
                            org_id = agent_data['org_id']
                            existing_agent.org_ids = [org_id] if org_id else []
                        
                        # Update other fields if they exist
                        if hasattr(existing_agent, 'gender') and 'gender' in agent_data:
                            existing_agent.gender = agent_data['gender']
                        if hasattr(existing_agent, 'birthday') and 'birthday' in agent_data:
                            existing_agent.birthday = agent_data['birthday']
                        
                        logger.info(f"[agent_handler] Updated agent in memory: {agent_id}")
                    else:
                        logger.warning(f"[agent_handler] Agent {agent_id} not found in memory (main_window.agents)")
                        logger.debug(f"[agent_handler] Available agents in memory: {[ag.card.id for ag in main_window.agents if hasattr(ag, 'card') and hasattr(ag.card, 'id')]}")
                    
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
            return create_success_response(request, {
                'message': f'Successfully saved {saved_count} agents',
                'agents': updated_agents  # 返回更新后的 agent 数据
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error in save agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_AGENTS_ERROR',
            f"Error during save agents: {str(e)}"
        )



@IPCHandlerRegistry.handler('delete_agent')
def handle_delete_agent(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理删除代理请求

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'agent_id' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        # 获取用户名
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
        
        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')
        
        # Get database service
        if not main_window.ec_db_mgr or not main_window.ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')
        
        agent_service = main_window.ec_db_mgr.agent_service
        
        # Delete each agent from database and memory
        deleted_count = 0
        errors = []
        
        for agent_id in agent_ids:
            try:
                # Step 1: Delete from database first
                result = agent_service.delete_agent(agent_id)
                
                if result.get('success'):
                    try:
                        original_count = len(main_window.agents)
                        # Step 2: Delete from memory after database deletion succeeds
                        main_window.agents = [ag for ag in main_window.agents if ag.card.id != agent_id]
                        new_count = len(main_window.agents)
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
                    
                    # Step 4: Sync deletion to cloud after memory update (async, fire and forget)
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
        username = params.get('username') or agent_data.get('owner', 'unknown')

        logger.info(f"[agent_handler] Creating agent '{agent_data.get('name')}' for user: {username}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Get database service
        if not main_window.ec_db_mgr:
            logger.error(f"[agent_handler] Database manager not available")
            return create_error_response(request, 'DB_ERROR', 'Database manager not available')

        agent_service = main_window.ec_db_mgr.agent_service
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

        # Step 2: Add agent to memory after database creation succeeds
        # Convert created agent to EC_Agent object and add to main_window.agents
        # Use common converter function for consistency
        try:
            from agent.agent_converter import convert_agent_dict_to_ec_agent
            
            ec_agent = convert_agent_dict_to_ec_agent(created_agent, main_window)
            
            if ec_agent:
                # Add to main_window.agents
                main_window.agents.append(ec_agent)
                logger.info(f"[agent_handler] Created and added EC_Agent '{created_agent.get('name')}' to memory")
            else:
                logger.warning(f"[agent_handler] Failed to convert agent to EC_Agent. Frontend will need to refresh.")
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

        logger.info(f"[agent_handler] Successfully created agent '{created_agent.get('name')}' for user: {username}")
        return create_success_response(
            request,
            {
                'message': f"Successfully created agent '{created_agent.get('name')}'",
                'agent': created_agent
            }
        )

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
        
        # Get main_window to access integrated agents list
        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')
        
        # Get integrated agents from MainWindow.agents (includes local DB + cloud + code-built agents)
        # If agents not ready, we still return org structure (empty agents list)
        all_agents = []
        if hasattr(main_window, 'agents') and main_window.agents:
            # All agents in MainWindow.agents are EC_Agent instances with to_flat_dict method
            all_agents = [agent.to_flat_dict(owner=username) for agent in main_window.agents]
            logger.info(f"[agent_handler] Retrieved {len(all_agents)} agents from MainWindow.agents")
        else:
            logger.warning(f"[agent_handler] MainWindow.agents not initialized - will return org structure only")
        
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
        
        # Build integrated tree structure with organizations and their agents
        tree_root = build_org_agent_tree(organizations, all_agents)
        
        # Return complete tree structure with root as orgs
        result_data = {
            'orgs': tree_root,  # Complete tree structure: root with children and agents
            'message': 'Successfully retrieved integrated organizations and agents tree'
        }
        
        logger.info(f"[agent_handler] Successfully retrieved integrated data for user: {username}")
        return create_success_response(request, result_data)
        
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
