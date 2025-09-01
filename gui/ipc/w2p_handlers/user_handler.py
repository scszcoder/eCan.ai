import traceback
from typing import Any, Optional, Dict
import uuid
from app_context import AppContext
from gui.LoginoutGUI import Login
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from auth.auth_messages import auth_messages

from auth.auth_config import AuthConfig

from utils.logger_helper import logger_helper as logger

COGNITO_ERROR_MAP = {
    # Login errors
    'UserNotConfirmedException': 'login_user_not_confirmed',
    'NotAuthorizedException': 'login_invalid_credentials',
    'UserNotFoundException': 'login_invalid_credentials',

    # Signup errors
    'UsernameExistsException': 'signup_user_exists',
    'InvalidPasswordException': 'signup_invalid_password',
    'InvalidParameterException': 'signup_invalid_email',

    # Forgot password errors
    'CodeMismatchException': 'confirm_forgot_invalid_code',
    'ExpiredCodeException': 'confirm_forgot_expired_code',
}

def get_message_from_cognito_error(error_code, default_key):
    """Maps a Cognito error code to a localized message key."""
    key = COGNITO_ERROR_MAP.get(error_code, default_key)
    return auth_messages.get_message(key)

@IPCHandlerRegistry.handler('login')
def handle_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handles login requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        password = data['password']
        machine_role = data.get('machine_role', 'Commander')
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleLogin(username, password, machine_role)

        if result.get('success'):
            token = str(uuid.uuid4()).replace('-', '')
            return create_success_response(request, {
                'token': token,
                'message': auth_messages.get_message('login_success')
            })
        else:
            error_code = result.get('error', 'login_failed')
            message = get_message_from_cognito_error(error_code, 'login_failed')
            logger.warning(f"Login failed for user {username}: {error_code}")
            return create_error_response(request, 'INVALID_CREDENTIALS', message)

    except Exception as e:
        logger.error(f"Error in login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'LOGIN_ERROR', auth_messages.get_message('login_failed'))

@IPCHandlerRegistry.handler('get_last_login')
def handle_get_last_login(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handles get_last_login requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        if params and 'lang' in params:
            lang = params['lang']
            auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleGetLastLogin()

        logger.info("last saved user info:", result)
        return create_success_response(request, {
            'last_login': result,
            'message': auth_messages.get_message('get_last_login_success')
        })

    except Exception as e:
        logger.error(f"Error in get_last_login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'LOGIN_ERROR', f"Error during get_last_login: {str(e)}")

@IPCHandlerRegistry.handler('logout')
def handle_logout(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handles logout requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        if params and 'lang' in params:
            lang = params['lang']
            auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        result = login.handleLogout()

        return create_success_response(request, {
            "result": result,
            'message': auth_messages.get_message('logout_success')
        })

    except Exception as e:
        logger.error(f"Error in logout handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'LOGOUT_ERROR', auth_messages.get_message('logout_failed'))

@IPCHandlerRegistry.handler('signup')
def handle_signup(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handles signup requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['username', 'password'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        password = data['password']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        success, message = login.handleSignUp(username, password)

        if success:
            return create_success_response(request, {
                'message': auth_messages.get_message('signup_success')
            })
        else:
            error_message = get_message_from_cognito_error(message, 'signup_failed')
            logger.warning(f"SignUp failed for user {username}: {message}")
            return create_error_response(request, 'SIGNUP_FAILED', error_message)

    except Exception as e:
        logger.error(f"Error in signup handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'SIGNUP_ERROR', auth_messages.get_message('signup_failed'))

@IPCHandlerRegistry.handler('forgot_password')
def handle_forgot_password(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handles forgot_password requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        success = login.handleForgotPassword(username)

        if success:
            return create_success_response(request, {
                'message': auth_messages.get_message('forgot_password_sent')
            })
        else:
            return create_error_response(request, 'FORGOT_PASSWORD_ERROR', auth_messages.get_message('forgot_password_failed'))

    except Exception as e:
        logger.error(f"Error in forgot_password handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'FORGOT_PASSWORD_ERROR', auth_messages.get_message('forgot_password_failed'))

@IPCHandlerRegistry.handler('confirm_forgot_password')
def handle_confirm_forgot_password(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handles confirm_forgot_password requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        is_valid, data, error = validate_params(params, ['username', 'confirmCode', 'newPassword'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        username = data['username']
        confirm_code = data['confirmCode']
        new_password = data['newPassword']
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        success, message = login.handleConfirmForgotPassword(username, confirm_code, new_password)

        if success:
            return create_success_response(request, {
                'message': auth_messages.get_message('confirm_forgot_success')
            })
        else:
            error_message = get_message_from_cognito_error(message, 'confirm_forgot_failed')
            logger.warning(f"ConfirmForgotPassword failed for user {username}: {message}")
            return create_error_response(request, 'CONFIRM_FORGOT_PASSWORD_FAILED', error_message)

    except Exception as e:
        logger.error(f"Error in confirm_forgot_password handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CONFIRM_FORGOT_PASSWORD_ERROR', auth_messages.get_message('confirm_forgot_failed'))

@IPCHandlerRegistry.handler('google_login')
def handle_google_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handles google_login requests with internationalized responses."""
    lang = auth_messages.DEFAULT_LANG
    try:
        lang = params.get('lang', auth_messages.DEFAULT_LANG) if params else auth_messages.DEFAULT_LANG
        machine_role = params.get('machine_role', 'Commander') if params else 'Commander'
        schedule_mode = params.get('schedule_mode', 'manual') if params else 'manual'
        auth_messages.set_language(lang)

        ctx = AppContext()
        login: Login = ctx.login
        success, message, _ = login._handle_google_login(machine_role, schedule_mode)

        if success:
            session_token = str(uuid.uuid4()).replace('-', '')
            response_data = {
                'token': session_token,
                'message': auth_messages.get_message('google_login_success'),
                'user_info': {
                    'email': login.auth_manager.get_current_user()
                }
            }
            return create_success_response(request, response_data)
        else:
            # The message from the auth_manager is already a user-facing error string.
            return create_error_response(request, 'GOOGLE_LOGIN_ERROR', message)

    except Exception as e:
        logger.error(f"Error in Google login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'GOOGLE_LOGIN_ERROR', auth_messages.get_message('login_failed'))