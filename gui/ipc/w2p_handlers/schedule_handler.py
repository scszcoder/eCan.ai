import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.MainGUI import MainWindow
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_schedules')
def handle_get_schedules(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Get Schedule handler called with request: {request}")

        main_window: MainWindow = AppContext.main_window
        agents = main_window.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        resultJS = {
            'schedules': [task.schedule.model_dump(mode='json') if task.schedule else None for task in all_tasks],
            'message': 'Get all successful'
        }
        logger.debug('get schedules resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get schedules handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get schedules: {str(e)}"
        )