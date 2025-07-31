import traceback
from typing import Any, Optional, Dict
import uuid
from app_context import AppContext
from gui.MainGUI import MainWindow
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_tools')
def handle_get_tools(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get tools handler called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get tools: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']
        token = str(uuid.uuid4()).replace('-', '')
        logger.info(f"get tools successful for user: {username}")

        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        resultJS = {
            'token': token,
            'tools': [tool.model_dump() for tool in main_window.mcp_tools_schemas],
            'message': 'Get all successful'
        }
        resultJS_str = str(resultJS)
        truncated_resultJS = resultJS_str[:800] + "..." if len(resultJS_str) > 500 else resultJS_str
        logger.debug('get tools resultJS:' + str(truncated_resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get tools handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get tools: {str(e)}"
        )