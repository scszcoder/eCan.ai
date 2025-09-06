import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
import uuid
from app_context import AppContext
if TYPE_CHECKING:
    from gui.MainGUI import MainWindow
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_skills')
def handle_get_skills(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get skills handler called with request: {request}")
        main_window: MainWindow = AppContext.main_window
        skills = main_window.agent_skills
        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )
        username = data['username']
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get skills successful for user: {username}")
        resultJS = {
            'token': token,
            'skills': [sk.to_dict() for sk in skills],
            'message': 'Get all successful'
        }
        resultJS_str = str(resultJS)
        truncated_resultJS = resultJS_str[:800] + "..." if len(resultJS_str) > 500 else resultJS_str
        logger.debug('get skills resultJS:' + str(truncated_resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get skills: {str(e)}"
        )
    
@IPCHandlerRegistry.handler('save_skills')
def handle_save_skills(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save skills handler called with request: {request}")
        logger.debug("save skills:" + str(params))
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"save skills successful for user: {username}")
        return create_success_response(request, {
            'token': token,
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
    """处理保存skill流程图

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'skill_info' 字段 skill_info就是json数据，其中diagram为其流程图的json表达

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save skill handler called with request: {request}")
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'skill_info'])
        if not is_valid:
            logger.warning(f"Invalid parameters for save skill: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']
        logger.info(f"save skill successful for user: {username}")
        logger.info(f"skill_info: {data['skill_info']}")

        return create_success_response(request, {
            'message': 'Save skill successful'
        })

    except Exception as e:
        logger.error(f"Error in save skills handler: {e}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save skills: {str(e)}"
        )
    

@IPCHandlerRegistry.handler('run_skill')
def handle_run_skill(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理保存skill流程图

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'skill' 字段 skill就是json数据，其中diagram为其流程图的json表达

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Run skill handler called with request: {request}")
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'skill'])
        if not is_valid:
            logger.warning(f"Invalid parameters for run skill: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']

        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"run skill successful for user: {username}")



        return create_success_response(request, {
            'token': token,
            'message': 'Save skills successful'
        })

    except Exception as e:
        logger.error(f"Error in save skills handler: {e}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during save skills: {str(e)}"
        )



@IPCHandlerRegistry.handler('new_skills')
def handle_new_skills(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Create skills handler called with request: {request}")
        logger.debug("create skills:" + str(params))
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for create skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"create skills successful for user: {username}")
        return create_success_response(request, {
            'token': token,
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
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Delete skills handler called with request: {request}")
        logger.debug("delete skills:" + str(params))
        # 验证参数
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            logger.warning(f"Invalid parameters for delete skills: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']


        # 生成随机令牌
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"delete skills successful for user: {username}")
        return create_success_response(request, {
            'token': token,
            'message': 'Delete skills successful'
        })

    except Exception as e:
        logger.error(f"Error in delete skills handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during delete skills: {str(e)}"
        )
