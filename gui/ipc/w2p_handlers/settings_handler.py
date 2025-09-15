import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_settings')
def handle_get_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """处理登录请求

    验证用户凭据并返回访问令牌。

    Args:
        request: IPC 请求对象
        params: 请求参数，必须包含 'username' 和 'password' 字段

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"get settings handler called with request: {request}")

        # 验证参数
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get settings: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # 获取用户名和密码
        username = data['username']
        # 简单的密码验证
        logger.info(f"get settings successful for user: {username}")
        main_window = AppContext.get_main_window()
        settings = main_window.config_manager.general_settings.data
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
    """处理保存设置请求

    保存用户设置到配置文件。

    Args:
        request: IPC 请求对象
        params: 请求参数，包含设置数据

    Returns:
        str: JSON 格式的响应消息
    """
    try:
        logger.debug(f"Save settings handler called with request: {request}")

        # 验证参数
        if not params or len(params) == 0:
            logger.warning("No settings data provided")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'No settings data provided'
            )

        # 获取设置数据
        settings_data = params[0] if isinstance(params, list) else params

        if not isinstance(settings_data, dict):
            logger.warning(f"Invalid settings data format: {type(settings_data)}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Settings data must be a dictionary'
            )

        logger.info(f"Saving settings: {list(settings_data.keys())}")

        # 获取主窗口实例
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.error("Main window not available")
            return create_error_response(
                request,
                'SYSTEM_ERROR',
                'Main window not available'
            )

        # 获取配置管理器
        if not main_window.config_manager:
            logger.error("Config manager not available")
            return create_error_response(
                request,
                'SYSTEM_ERROR',
                'Config manager not available'
            )

        # 保存设置到 general_settings
        general_settings = main_window.config_manager.general_settings

        # 更新设置值
        updated_fields = []
        for key, value in settings_data.items():
            if hasattr(general_settings, key):
                try:
                    setattr(general_settings, key, value)
                    updated_fields.append(key)
                    logger.debug(f"Updated {key} = {value}")
                except Exception as e:
                    logger.warning(f"Failed to set {key} = {value}: {e}")
            else:
                logger.warning(f"Unknown setting field: {key}")

        # 保存到文件
        try:
            general_settings.save()
            logger.info(f"Settings saved successfully. Updated fields: {updated_fields}")

            return create_success_response(request, {
                'message': 'Settings saved successfully',
                'updated_fields': updated_fields
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

