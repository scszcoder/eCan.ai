import traceback
from typing import Any, Optional, Dict
import uuid
from gui.LoginoutGUI import Login
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_tasks')
def handle_get_tasks(request: IPCRequest, params: Optional[Dict[str, Any]], py_login: Login) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get tasks handler called with request: {request}, params: {params}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get tasks: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        agents = py_login.main_win.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)
        # 获取用户名和密码
        username = data['username']

        # 简单的密码验证
        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"Get tasks successful for user: {username}")
        resultJS = {
            'token': token,
            'tasks': [task.to_dict() for task in all_tasks],
            'message': 'Get all successful'
        }
        logger.debug('get tasks resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get tasks handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get tasks: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('save_tasks')
def handle_save_tasks(request: IPCRequest, params: Optional[list[Any]], py_login:Any) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save tasks handler called with request: {request}, params: {params}")
        logger.debug("save tasks:" + str(params))
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save tasks: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save tasks successful for user: {username}")
        return create_success_response(request, {
            'token': token,
            'message': 'Save tasks successful'
        })

    except Exception as e:
        logger.error(f"Error in save tasks handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save tasks: {str(e)}"
        )