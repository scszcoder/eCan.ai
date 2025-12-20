import traceback
from typing import Any, Optional, Dict
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from gui.ipc.callable.manager import callable_manager

from utils.logger_helper import logger_helper as logger


@IPCHandlerRegistry.handler('get_callables')
def handle_get_callables(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get callables request

    Args:
        request: IPC request object
        params: Request parameters, optional including:
            - text: Text filter for function name, description and parameters
            - type: Type filter ('system' or 'custom')
        py_login: Python login object

    Returns:
        str: JSON formatted response message
    """
    try:
        # Get callable functions
        functions = callable_manager.get_callables(params)
        logger.debug("Filtered callables count: %d", len(functions))

        response = create_success_response(request, {
            'data': functions,
            'message': 'Get callables successful'
        })
        return response

    except Exception as e:
        logger.error(f"Error in get callables handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'GET_CALLABLES_ERROR',
            f"Handlers Error getting callables: {str(e)}"
        )

@IPCHandlerRegistry.handler('manage_callable')
def handle_manage_callable(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle manage_callable IPC request.

    Args:
        request: Dict containing:
            - id: Request ID
            - type: Request type
            - method: Method name
        params: Dict containing:
            - action: Action to perform ('add', 'update', 'delete')
            - data: Function data including:
                - id: Function ID (required for update/delete)
                - name: Function name
                - desc: Function description
                - params: Function parameters
                - returns: Function return values
                - type: Function type
                - code: Function code
        py_login: Login context

    Returns:
        JSON string containing:
            - success: bool, whether the operation was successful
            - data: Optional[Dict], result data if successful
            - error: Optional[Dict], error information if failed
    """
    try:
        # Use params parameter directly
        result, message = callable_manager.manage_callable(params)
        return create_success_response(request, {
            'data': result,
            'message': message
        })

    except Exception as e:
        logger.error(f"Error in handle_manage_callable: {e} {traceback.format_exc()}")
        return create_error_response(
            request=request,
            code='MANAGE_CALLABLE_ERROR',
            message=str(e)
        )
