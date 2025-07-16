import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.MainGUI import MainWindow
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_vehicles')
def handle_get_vehicles(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get vehicles handler called with request: {request}")
        app_ctx = AppContext()
        main_window: MainWindow = app_ctx.main_window
        vehicles = main_window.vehicles

        logger.info(f"get vehicles successful。")
        resultJS = {
            'vehicles': [v.to_dict() for v in vehicles],
            'message': 'Get all successful'
        }
        logger.debug('get vehicles resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get vehicles handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get vehicles: {str(e)}"
        )