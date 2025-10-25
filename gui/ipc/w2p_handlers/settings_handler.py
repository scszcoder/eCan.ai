import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_settings')
def handle_get_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"get settings handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get settings: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']
        # Simple password validation
        logger.info(f"get settings successful for user: {username}")
        main_window = AppContext.get_main_window()
        general_settings = main_window.config_manager.general_settings
        settings = general_settings.data.copy()
        
        # Add cached hardware detection info (no real-time probing here)
        try:
            # Use cached value updated by background scan
            cached_wifi = general_settings.default_wifi or None
            settings['current_wifi'] = cached_wifi
            logger.debug(f"Current WiFi (cached): {cached_wifi}")

            # Cached or last-scan results
            available_wifi_networks = general_settings.get_wifi_networks()
            settings['available_wifi_networks'] = available_wifi_networks
            logger.debug(f"Available WiFi networks (cached): {len(available_wifi_networks)}")

            available_printers = general_settings.get_printer_names()
            settings['available_printers'] = available_printers
            logger.debug(f"Available printers (cached): {len(available_printers)}")

        except Exception as hw_error:
            logger.warning(f"Failed to get cached hardware info: {hw_error}")
            # Don't fail the entire request if cache is unavailable
            settings['current_wifi'] = None
            settings['available_wifi_networks'] = []
            settings['available_printers'] = []
        
        resultJS = {
            'settings': settings,
            'message': 'Get settings successful'
        }
        logger.debug('get settings resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get settings handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get settings: {str(e)}"
        )

@IPCHandlerRegistry.handler('save_settings')
def handle_save_settings(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle save settings request

    Save user settings to configuration file.

    Args:
        request: IPC request object
        params: Request parameters, containing settings data

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Save settings handler called with request: {request}")

        # Validate parameters
        if not params or len(params) == 0:
            logger.warning("No settings data provided")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'No settings data provided'
            )

        # Get settings data
        settings_data = params[0] if isinstance(params, list) else params

        if not isinstance(settings_data, dict):
            logger.warning(f"Invalid settings data format: {type(settings_data)}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Settings data must be a dictionary'
            )

        logger.info(f"Saving settings: {list(settings_data.keys())}")

        # Get main window instance
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.error("Main window not available - user may have logged out")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')

        # Get config manager
        if not main_window.config_manager:
            logger.error("Config manager not available")
            return create_error_response(
                request,
                'SYSTEM_ERROR',
                'Config manager not available'
            )

        # Save settings to general_settings
        general_settings = main_window.config_manager.general_settings

        # Use update_data method to handle all settings data uniformly
        try:
            general_settings.update_data(settings_data)
            logger.info(f"Settings updated successfully. Fields: {list(settings_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to update settings data: {e}")
            return create_error_response(
                request,
                'UPDATE_ERROR',
                f"Failed to update settings: {str(e)}"
            )

        # Save to file
        try:
            general_settings.save()
            logger.info(f"Settings saved successfully")

            return create_success_response(request, {
                'message': 'Settings saved successfully',
                'updated_fields': list(settings_data.keys())
            })

        except Exception as e:
            logger.error(f"Failed to save settings to file: {e}")
            return create_error_response(
                request,
                'SAVE_ERROR',
                f"Failed to save settings to file: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Error in save settings handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_ERROR',
            f"Error during save settings: {str(e)}"
        )

