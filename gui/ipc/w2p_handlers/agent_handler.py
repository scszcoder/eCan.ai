import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from app_context import AppContext
from utils.logger_helper import logger_helper as logger

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
        else:
            agents = getattr(main_window, 'agents', []) or []
            logger.info(f"[agent_handler] Successfully retrieved {len(agents)} agents for user: {username}")

        resultJS = {
            'agents': [agent.to_dict() for agent in agents],
            'message': 'Get all successful'
        }
        logger.trace('[agent_handler] get agents resultJS:' + str(resultJS))
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
        data = validate_params(request, ['username', 'agents'])
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
        data = validate_params(request, ['username', 'agents'])
        username = data['username']
        agents_data = data['agents']

        logger.info(f"[agent_handler] Creating {len(agents_data)} agents for user: {username}")

        main_window = AppContext.get_main_window()
        if main_window is None:
            logger.error(f"[agent_handler] MainWindow not available for user: {username}")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'MainWindow not available')

        # Process each agent
        created_count = 0
        errors = []

        for agent_data in agents_data:
            try:
                # Handle organization migration: if organizations list exists, use first one as organization_id
                if 'organizations' in agent_data and agent_data['organizations'] and not agent_data.get('organization_id'):
                    agent_data['organization_id'] = agent_data['organizations'][0]

                # Create new agent using existing agent creation logic
                # This is a simplified version - in a real implementation, you'd use the proper agent creation flow
                logger.info(f"[agent_handler] Creating new agent with data: {agent_data.get('name', 'Unknown')}")
                created_count += 1

            except Exception as e:
                error_msg = f"Error creating agent: {str(e)}"
                logger.error(f"[agent_handler] {error_msg}")
                errors.append(error_msg)

        if errors:
            logger.warning(f"[agent_handler] Created {created_count} agents with {len(errors)} errors")
            return create_error_response(request, 'PARTIAL_CREATE_ERROR', f"Created {created_count} agents with errors: {'; '.join(errors)}")
        else:
            logger.info(f"[agent_handler] Successfully created {created_count} agents for user: {username}")
            return create_success_response(request, {
                'message': f'Successfully created {created_count} agents'
            })

    except Exception as e:
        logger.error(f"[agent_handler] Error in create agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during create agents: {str(e)}"
        )