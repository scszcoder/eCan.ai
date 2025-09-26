"""
Organization IPC handlers for eCan.ai

This module provides IPC handlers for organization management operations
including CRUD operations, tree management, and agent binding.
"""

import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from agent.ec_org_ctrl import get_organization_manager


@IPCHandlerRegistry.handler('get_orgs')
def handle_get_orgs(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Get all organizations or organization tree
    
    Args:
        request: IPC request object
        params: Request parameters, may contain 'username' and optional 'root_id'
    
    Returns:
        IPCResponse: Response with organizations data
    """
    try:
        logger.debug(f"[organizations_handler] get_organizations called with request: {request}")

        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for get_organizations: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        root_id = data.get('root_id')  # Optional parameter
        
        logger.info(f"[organizations_handler] Getting organizations for user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Initialize organizations if needed
        init_result = org_manager.initialize_organizations()
        if not init_result.get("success"):
            logger.warning(f"[organizations_handler] Organization initialization warning: {init_result.get('message')}")
        
        # Get organization tree
        result = org_manager.get_organization_tree(root_id)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully retrieved organizations for user: {username}")
            return create_success_response(request, {
                'organizations': result.get("data", []),
                'message': 'Get organizations successful'
            })
        else:
            logger.error(f"[organizations_handler] Failed to get organizations: {result.get('error')}")
            return create_error_response(request, 'GET_ORGANIZATIONS_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in get_organizations: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_ORGANIZATIONS_ERROR', str(e))


@IPCHandlerRegistry.handler('create_org')
def handle_create_org(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Create a new organization
    
    Args:
        request: IPC request object
        params: Request parameters with organization data
    
    Returns:
        IPCResponse: Response with created organization data
    """
    try:
        logger.debug(f"[organizations_handler] create_organization called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'name'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for create_organization: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        name = data['name']
        description = data.get('description', '')
        parent_id = data.get('parent_id')
        organization_type = data.get('organization_type', 'department')
        
        logger.info(f"[organizations_handler] Creating organization '{name}' for user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Create organization
        result = org_manager.create_organization(
            name=name,
            description=description,
            parent_id=parent_id,
            organization_type=organization_type,
            **{k: v for k, v in data.items() if k not in ['username', 'name', 'description', 'parent_id', 'organization_type']}
        )
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully created organization '{name}'")
            return create_success_response(request, {
                'organization': result.get("data"),
                'message': 'Organization created successfully'
            })
        else:
            logger.error(f"[organizations_handler] Failed to create organization: {result.get('error')}")
            return create_error_response(request, 'CREATE_ORGANIZATION_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in create_organization: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'CREATE_ORGANIZATION_ERROR', str(e))


@IPCHandlerRegistry.handler('update_org')
def handle_update_org(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Update an organization
    
    Args:
        request: IPC request object
        params: Request parameters with organization ID and update data
    
    Returns:
        IPCResponse: Response with updated organization data
    """
    try:
        logger.debug(f"[organizations_handler] update_organization called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'organization_id'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for update_organization: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        organization_id = data['organization_id']
        
        logger.info(f"[organizations_handler] Updating organization {organization_id} for user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Prepare update fields (exclude username and organization_id)
        update_fields = {k: v for k, v in data.items() if k not in ['username', 'organization_id']}
        
        # Update organization
        result = org_manager.update_organization(organization_id, **update_fields)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully updated organization {organization_id}")
            return create_success_response(request, {
                'organization': result.get("data"),
                'message': 'Organization updated successfully'
            })
        else:
            logger.error(f"[organizations_handler] Failed to update organization: {result.get('error')}")
            return create_error_response(request, 'UPDATE_ORGANIZATION_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in update_organization: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'UPDATE_ORGANIZATION_ERROR', str(e))


@IPCHandlerRegistry.handler('delete_org')
def handle_delete_org(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Delete an organization
    
    Args:
        request: IPC request object
        params: Request parameters with organization ID
    
    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[organizations_handler] delete_organization called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'organization_id'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for delete_organization: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        organization_id = data['organization_id']
        
        logger.info(f"[organizations_handler] Deleting organization {organization_id} for user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Delete organization
        result = org_manager.delete_organization(organization_id)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully deleted organization {organization_id}")
            return create_success_response(request, {
                'message': 'Organization deleted successfully'
            })
        else:
            logger.error(f"[organizations_handler] Failed to delete organization: {result.get('error')}")
            return create_error_response(request, 'DELETE_ORGANIZATION_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in delete_organization: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'DELETE_ORGANIZATION_ERROR', str(e))


@IPCHandlerRegistry.handler('get_org_agents')
def handle_get_org_agents(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Get agents in an organization
    
    Args:
        request: IPC request object
        params: Request parameters with organization ID
    
    Returns:
        IPCResponse: Response with agents data
    """
    try:
        logger.debug(f"[organizations_handler] get_organization_agents called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'organization_id'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for get_organization_agents: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        organization_id = data['organization_id']
        include_descendants = data.get('include_descendants', False)
        
        logger.info(f"[organizations_handler] Getting agents for organization {organization_id}, user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Get organization agents
        result = org_manager.get_organization_agents(organization_id, include_descendants)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully retrieved agents for organization {organization_id}")
            return create_success_response(request, {
                'agents': result.get("data", []),
                'message': 'Get organization agents successful'
            })
        else:
            logger.error(f"[organizations_handler] Failed to get organization agents: {result.get('error')}")
            return create_error_response(request, 'GET_ORGANIZATION_AGENTS_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in get_organization_agents: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_ORGANIZATION_AGENTS_ERROR', str(e))


@IPCHandlerRegistry.handler('bind_agent_to_org')
def handle_bind_agent_to_org(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Bind an agent to an organization
    
    Args:
        request: IPC request object
        params: Request parameters with agent ID and organization ID
    
    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[organizations_handler] bind_agent_to_organization called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'agent_id', 'organization_id'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for bind_agent_to_organization: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        agent_id = data['agent_id']
        organization_id = data['organization_id']
        
        logger.info(f"[organizations_handler] Binding agent {agent_id} to organization {organization_id}, user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Bind agent to organization
        result = org_manager.bind_agent_to_organization(agent_id, organization_id)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully bound agent {agent_id} to organization {organization_id}")
            return create_success_response(request, {
                'message': 'Agent bound to organization successfully'
            })
        else:
            logger.error(f"[organizations_handler] Failed to bind agent to organization: {result.get('error')}")
            return create_error_response(request, 'BIND_AGENT_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in bind_agent_to_organization: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'BIND_AGENT_ERROR', str(e))


@IPCHandlerRegistry.handler('unbind_agent_from_org')
def handle_unbind_agent_from_org(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Unbind an agent from its organization
    
    Args:
        request: IPC request object
        params: Request parameters with agent ID
    
    Returns:
        IPCResponse: Response with success status
    """
    try:
        logger.debug(f"[organizations_handler] unbind_agent_from_organization called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username', 'agent_id'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for unbind_agent_from_organization: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        agent_id = data['agent_id']
        
        logger.info(f"[organizations_handler] Unbinding agent {agent_id} from organization, user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Unbind agent from organization
        result = org_manager.unbind_agent_from_organization(agent_id)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully unbound agent {agent_id} from organization")
            return create_success_response(request, {
                'message': 'Agent unbound from organization successfully'
            })
        else:
            logger.error(f"[organizations_handler] Failed to unbind agent from organization: {result.get('error')}")
            return create_error_response(request, 'UNBIND_AGENT_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in unbind_agent_from_organization: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'UNBIND_AGENT_ERROR', str(e))


@IPCHandlerRegistry.handler('get_available_agents_for_binding')
def handle_get_available_agents_for_binding(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """
    Get agents available for binding to an organization
    
    Args:
        request: IPC request object
        params: Request parameters with optional organization ID
    
    Returns:
        IPCResponse: Response with available agents data
    """
    try:
        logger.debug(f"[organizations_handler] get_available_agents_for_binding called with request: {request}")
        
        # Validate required parameters
        is_valid, data, error = validate_params(request.get('params'), ['username'])
        if not is_valid:
            logger.warning(f"[organizations_handler] Invalid parameters for get_available_agents_for_binding: {error}")
            return create_error_response(
                request_id=request['id'],
                method=request['method'],
                error_code='INVALID_PARAMS',
                error_message=error
            )

        username = data['username']
        organization_id = data.get('organization_id')  # Optional
        
        logger.info(f"[organizations_handler] Getting available agents for binding, user: {username}")
        
        # Get organization manager
        org_manager = get_organization_manager(username)
        
        # Get available agents
        result = org_manager.get_available_agents_for_binding(organization_id)
        
        if result.get("success"):
            logger.info(f"[organizations_handler] Successfully retrieved available agents for binding")
            return create_success_response(request, {
                'agents': result.get("data", []),
                'message': 'Get available agents successful'
            })
        else:
            logger.error(f"[organizations_handler] Failed to get available agents: {result.get('error')}")
            return create_error_response(request, 'GET_AVAILABLE_AGENTS_FAILED', result.get('error', 'Unknown error'))
            
    except Exception as e:
        logger.error(f"[organizations_handler] Error in get_available_agents_for_binding: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_AVAILABLE_AGENTS_ERROR', str(e))
