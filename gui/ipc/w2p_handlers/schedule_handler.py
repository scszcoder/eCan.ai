import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from app_context import AppContext
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_schedules')
def handle_get_schedules(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get Schedule handler called with request: {request}")

        main_window = AppContext.get_main_window()
        agents = main_window.agents
        all_tasks = []
        for agent in agents:
            all_tasks.extend(agent.tasks)

        # Build schedules with task information
        schedules_with_task_info = []
        for task in all_tasks:
            if task.schedule:
                schedule_data = task.schedule.model_dump(mode='json')
                # Add task information to schedule
                schedule_data['taskId'] = task.id
                schedule_data['taskName'] = task.name
                schedules_with_task_info.append(schedule_data)
            else:
                schedules_with_task_info.append(None)

        resultJS = {
            'schedules': schedules_with_task_info,
            'message': 'Get all successful'
        }
        logger.debug(f'get schedules resultJS: {len(schedules_with_task_info)} schedules with task info')
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get schedules handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get schedules: {str(e)}"
        )