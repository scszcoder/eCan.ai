import traceback
from collections import defaultdict
from typing import TYPE_CHECKING, Any, Optional, Dict
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from agent.ec_org_ctrl import get_ec_org_ctrl


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
        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for get agents: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名
        username = data['username']
        logger.info(f"[agent_handler] get agents request for user: {username}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username} - user may have logged out")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')

        # Get agents from database instead of memory
        # This ensures we get all agents including newly created ones
        if not main_window.ec_db_mgr or not main_window.ec_db_mgr.agent_service:
            logger.error(f"[agent_handler] Database service not available")
            return create_error_response(request, 'DB_ERROR', 'Database service not available')

        agent_service = main_window.ec_db_mgr.agent_service

        try:
            # Query all agents from database
            with agent_service.session_scope() as session:
                from agent.db.models.agent_model import DBAgent
                db_agents = session.query(DBAgent).filter(DBAgent.owner == username).all()
                agents_data = [agent.to_dict() for agent in db_agents]
                logger.info(f"[agent_handler] Successfully retrieved {len(agents_data)} agents from database for user: {username}")

                resultJS = {
                    'agents': agents_data,
                    'message': 'Get all successful'
                }
                logger.trace('[agent_handler] get agents resultJS:' + str(resultJS))
                return create_success_response(request, resultJS)
        except Exception as e:
            logger.error(f"[agent_handler] Error querying agents from database: {e}")
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
    
@IPCHandlerRegistry.handler('save_agents')
def handle_save_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Save/update agents

    Args:
        request: IPC request object
        params: Request parameters with username and agents data

    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[agent_handler] Save agents handler called with request: {request}")

        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'agents'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for save agents: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)
        username = data['username']
        agents_data = data['agents']

        logger.info(f"[agent_handler] Saving {len(agents_data)} agents for user: {username}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Process each agent
        saved_count = 0
        errors = []

        for agent_data in agents_data:
            try:
                # Handle organization migration: if organizations list exists, use first one as organization_id
                if 'organizations' in agent_data and agent_data['organizations'] and not agent_data.get('organization_id'):
                    agent_data['organization_id'] = agent_data['organizations'][0]

                # Find existing agent by ID
                agent_id = agent_data.get('id') or (agent_data.get('card', {}).get('id') if agent_data.get('card') else None)
                if agent_id:
                    existing_agent = next((ag for ag in main_window.agents if getattr(getattr(ag, 'card', None), 'id', None) == agent_id), None)
                    if existing_agent:
                        # Update existing agent
                        for key, value in agent_data.items():
                            if hasattr(existing_agent, key):
                                setattr(existing_agent, key, value)
                        saved_count += 1
                        logger.info(f"[agent_handler] Updated agent: {agent_id}")
                    else:
                        logger.warning(f"[agent_handler] Agent not found for update: {agent_id}")
                        errors.append(f"Agent not found: {agent_id}")
                else:
                    logger.warning(f"[agent_handler] No agent ID provided for save")
                    errors.append("No agent ID provided")

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
                'message': f'Successfully saved {saved_count} agents'
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error in save agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_AGENTS_ERROR',
            f"Error during save agents: {str(e)}"
        )



@IPCHandlerRegistry.handler('delete_agents')
def handle_delete_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段, 'agent_id'

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Delete agents handler called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for delete agents: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        logger.info(f"[agent_handler] delete agents successful for user: {username}")
        return create_success_response(request, {
            'message': 'Delete agents successful'
        })

    except Exception as e:
        logger.error(f"[agent_handler] Error in delete agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during delete agents: {str(e)}"
        )



@IPCHandlerRegistry.handler('new_agents')
def handle_new_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Create new agents

    Args:
        request: IPC request object
        params: Request parameters with username and agents data

    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[agent_handler] Create agents handler called with request: {request}")

        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['agents'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for new agents: {error}")
            return create_error_response(request, 'INVALID_PARAMS', error)

        # Get username from params or from first agent's owner field
        username = data.get('username')
        agents_data = data['agents']

        if not username and agents_data:
            # Try to get username from first agent's owner field
            username = agents_data[0].get('owner', 'unknown')

        logger.info(f"[agent_handler] Creating {len(agents_data)} agents for user: {username}")

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

        # Call service layer to create agents in batch
        result = agent_service.create_agents_batch(agents_data, username)

        created_count = result['created_count']
        errors = result['errors']
        created_agents = result['agents']

        # Note: We don't add created agents to main_window.agents here because:
        # 1. main_window.agents contains EC_Agent objects which require complex initialization
        # 2. EC_Agent requires mainwin, skill_llm, and other dependencies
        # 3. The agents are already in the database and will be loaded on next app restart
        # 4. For immediate access, frontend should query the database directly via get_org_agents

        logger.info(f"[agent_handler] Created {created_count} agents in database. "
                   f"Note: These agents will be available in memory after app restart, "
                   f"or can be queried from database immediately.")

        if errors:
            logger.warning(f"[agent_handler] Created {created_count} agents with {len(errors)} errors")
            return create_error_response(
                request,
                'PARTIAL_CREATE_ERROR',
                f"Created {created_count} agents with errors: {'; '.join(errors)}"
            )
        else:
            logger.info(f"[agent_handler] Successfully created {created_count} agents for user: {username}")
            return create_success_response(
                request,
                {
                    'message': f'Successfully created {created_count} agents',
                    'created_count': created_count,
                    'agents': created_agents
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
        
        # Get main window for agents data
        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.warning(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')
        
        # Get all agents from main window
        all_agents = getattr(main_window, 'agents', []) or []
        logger.info(f"[agent_handler] Retrieved {len(all_agents)} total agents from main window")
        
        # Get org manager for organization data
        ec_org_ctrl = get_ec_org_ctrl()
        
        # Get all organizations as flat list (not tree structure)
        org_result = ec_org_ctrl.org_service.get_all_orgs()
        
        if not org_result.get("success"):
            logger.error(f"[agent_handler] Failed to get organizations: {org_result.get('error')}")
            return create_error_response(request, 'GET_ORGANIZATIONS_FAILED', org_result.get('error', 'Unknown error'))
        
        organizations = org_result.get("data", [])
        logger.info(f"[agent_handler] Retrieved {len(organizations)} organizations from flat list")
        
        # logger.info(f"[agent_handler] org_result full response: {org_result}")
        
        # Debug: log organization structure
        if organizations:
            logger.info("[agent_handler] Organization details length:", len(organizations))
            # for org in organizations:
            #     logger.info(f"  - Org: {org.get('name', 'Unknown')} (id: {org.get('id')}, parent_id: {org.get('parent_id')})")
        else:
            logger.error("[agent_handler] No organizations found in database!")
            logger.error(f"[agent_handler] Database query result: success={org_result.get('success')}, data={org_result.get('data')}, error={org_result.get('error')}")
            
            # Check if the service is properly initialized
            try:
                # Check database service initialization
                if hasattr(ec_org_ctrl.org_service, 'session_scope'):
                    logger.info("[agent_handler] Database service appears to be initialized")
                    
                    # Try to check if table exists and has data
                    try:
                        with ec_org_ctrl.org_service.session_scope() as session:
                            from agent.db.models.org_model import DBAgentOrg
                            
                            # Check if table exists by trying to count records
                            count = session.query(DBAgentOrg).count()
                            logger.info(f"[agent_handler] Found {count} organizations in agent_orgs table")
                            
                            if count == 0:
                                logger.warning("[agent_handler] agent_orgs table is empty - this explains why children is empty")
                                logger.warning("[agent_handler] You may need to check if organization template was loaded during initialization")
                            else:
                                # If there are records, let's see what they look like
                                sample_orgs = session.query(DBAgentOrg).limit(3).all()
                                logger.info("[agent_handler] Sample organizations from database:")
                                for org in sample_orgs:
                                    logger.info(f"  - {org.name} (id: {org.id}, parent_id: {org.parent_id})")
                                    
                    except Exception as db_e:
                        logger.error(f"[agent_handler] Error checking database table: {db_e}")
                        
                else:
                    logger.error("[agent_handler] Database service not properly initialized - missing session_scope")
                    
            except Exception as debug_e:
                logger.error(f"[agent_handler] Error during debugging: {debug_e}")
        
        # Process all agents with org_id field to indicate assignment
        agents = []
        
        for agent in all_agents:
            try:
                # Convert agent to dict format
                agent_dict = agent.to_dict() if hasattr(agent, 'to_dict') else agent
                
                # Check if agent has organization assignment
                org_id = None
                
                # Try different ways to get org_id
                if hasattr(agent, 'organization_id') and agent.organization_id:
                    org_id = agent.organization_id
                elif hasattr(agent, 'organizations') and agent.organizations:
                    org_id = agent.organizations[0] if isinstance(agent.organizations, list) else agent.organizations
                elif isinstance(agent_dict, dict):
                    org_id = agent_dict.get('organization_id') or (
                        agent_dict.get('organizations', [None])[0] if agent_dict.get('organizations') else None
                    )
                
                # Create agent data with org_id field (null for unassigned)
                # Ensure compatibility with frontend OrgAgent interface
                agent_data = {
                    'id': agent_dict.get('id') or (agent_dict.get('card', {}).get('id') if agent_dict.get('card') else None),
                    'name': agent_dict.get('name') or (agent_dict.get('card', {}).get('name') if agent_dict.get('card') else 'Unknown'),
                    'description': agent_dict.get('description') or agent_dict.get('job_description', ''),
                    'avatar': agent_dict.get('avatar'),
                    'status': agent_dict.get('status', 'active'),
                    'org_id': org_id,  # null for unassigned, org_id for assigned
                    'created_at': agent_dict.get('created_at'),
                    'updated_at': agent_dict.get('updated_at'),
                    'capabilities': agent_dict.get('capabilities', []),
                    'isBound': org_id is not None  # 添加前端期望的 isBound 字段
                }
                
                agents.append(agent_data)
                    
            except Exception as e:
                logger.warning(f"[agent_handler] Error processing agent {getattr(agent, 'id', 'unknown')}: {e}")
                continue
        
        # Count assigned vs unassigned for logging
        assigned_count = len([a for a in agents if a['org_id']])
        unassigned_count = len([a for a in agents if not a['org_id']])
        logger.info(f"[agent_handler] Processed {len(agents)} total agents: {assigned_count} assigned, {unassigned_count} unassigned")
        
        # Build integrated tree structure with organizations and their agents
        tree_root = build_org_agent_tree(organizations, agents)
        
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
