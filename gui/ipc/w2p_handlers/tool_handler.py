import traceback
from typing import TYPE_CHECKING, Any, Optional, Dict
from app_context import AppContext
if TYPE_CHECKING:
    from gui.MainGUI import MainWindow
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger
from agent.mcp.server import tool_schemas as mcp_tool_schemas

@IPCHandlerRegistry.handler('get_tools')
def handle_get_tools(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Get tools handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get tools: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']
        logger.info(f"get tools successful for user: {username}")

        main_window: MainWindow = AppContext.get_main_window()
        resultJS = {
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


@IPCHandlerRegistry.handler('new_tools')
def handle_new_tools(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Create tools handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for create tools: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']
        logger.info(f"create tools successful for user: {username}")

        main_window: MainWindow = AppContext.get_main_window()
        resultJS = {
            'tools': [tool.model_dump() for tool in main_window.mcp_tools_schemas],
            'message': 'Create all successful'
        }
        resultJS_str = str(resultJS)
        truncated_resultJS = resultJS_str[:800] + "..." if len(resultJS_str) > 500 else resultJS_str
        logger.debug('create tools resultJS:' + str(truncated_resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in create tools handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during create tools: {str(e)}"
        )




@IPCHandlerRegistry.handler('delete_tools')
def handle_delete_tools(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Delete tools handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for delete tools: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']
        logger.info(f"delete tools successful for user: {username}")

        main_window: MainWindow = AppContext.get_main_window()
        resultJS = {
            'tools': [tool.model_dump() for tool in main_window.mcp_tools_schemas],
            'message': 'Delete all successful'
        }
        resultJS_str = str(resultJS)
        truncated_resultJS = resultJS_str[:800] + "..." if len(resultJS_str) > 500 else resultJS_str
        logger.debug('delete tools resultJS:' + str(truncated_resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in delete tools handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during delete tools: {str(e)}"
        )


# ============================================================================
# Cloud Synchronization Functions
# ============================================================================


def _trigger_cloud_sync(tool_data: Dict[str, Any], operation: 'Operation') -> None:
    """Trigger cloud synchronization (async, non-blocking)
    
    Async background execution, doesn't block UI operations, ensures eventual consistency.
    
    Args:
        tool_data: Tool data to sync
        operation: Operation type (Operation enum)
    """
    from agent.cloud_api.offline_sync_manager import get_sync_manager
    from agent.cloud_api.constants import DataType, Operation
    
    def _log_result(result: Dict[str, Any]):
        """Log sync result"""
        if result.get('synced'):
            logger.info(f"[tool_handler] ✅ Tool synced to cloud: {operation} - {tool_data.get('name')}")
        elif result.get('cached'):
            logger.info(f"[tool_handler] 💾 Tool cached for later sync: {operation} - {tool_data.get('name')}")
        elif not result.get('success'):
            logger.error(f"[tool_handler] ❌ Failed to sync tool: {result.get('error')}")
    
    # Use SyncManager's thread pool for async execution
    # Note: Use TOOL for Tool entity data (name, description, etc.)
    #       Use AGENT_TOOL for Agent-Tool relationship data (agid, tool_id, owner)
    manager = get_sync_manager()
    manager.sync_to_cloud_async(DataType.TOOL, tool_data, operation, callback=_log_result)