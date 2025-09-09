import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
import uuid
if TYPE_CHECKING:
    from gui.MainGUI import MainWindow
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

        # 简单的密码验证
        # 生成随机令牌
        username = data['username']
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"[agent_handler] get agents successful for user: {username}")
        main_window: MainWindow = AppContext.main_window
        agents = main_window.agents

        resultJS = {
            'token': token,
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
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"[agent_handler] Save agents handler called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for save agents: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"[agent_handler] save agents successful for user: {username}")
        return create_success_response(request, {
            'token': token,
            'message': 'Save agents successful'
        })

    except Exception as e:
        logger.error(f"[agent_handler] Error in save agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
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


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"[agent_handler] delete agents successful for user: {username}")
        return create_success_response(request, {
            'token': token,
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
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"[agent_handler] Create agents handler called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"[agent_handler] Invalid parameters for create agents: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"[agent_handler] create agents successful for user: {username}")
        return create_success_response(request, {
            'token': token,
            'message': 'Create agents successful'
        })

    except Exception as e:
        logger.error(f"[agent_handler] Error in create agents handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during create agents: {str(e)}"
        )