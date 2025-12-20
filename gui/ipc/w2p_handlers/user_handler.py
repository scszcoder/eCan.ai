import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from auth.auth_messages import auth_messages

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

def _build_user_info_response(request, token, user_profile, username, machine_role, login_type, message_key):
    """Helper to build consistent user info response for both login methods."""
    user_email = user_profile.get('email') or username
    
    return create_success_response(request, {
        'token': token,
        'message': auth_messages.get_message(message_key),
        'user_info': {
            'username': username,
            'email': user_email,
            'role': machine_role,
            'name': user_profile.get('name', ''),
            'given_name': user_profile.get('given_name', ''),
            'family_name': user_profile.get('family_name', ''),
            'picture': user_profile.get('picture', ''),
            'email_verified': user_profile.get('email_verified', True),
            'login_type': login_type
        }
    })

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
        # Support both 'role' (from frontend) and 'machine_role' (legacy) for consistency
        machine_role = data.get('role', data.get('machine_role', 'Commander'))
        lang = data.get('lang', auth_messages.DEFAULT_LANG)
        auth_messages.set_language(lang)

        login = AppContext.get_login()
        if login is None:
            logger.warning("Login object is None - system may not be properly initialized")
            return create_error_response(request, 
                'SYSTEM_NOT_READY',
                'System not ready - please try again')
        
        result = login.handleLogin(username, password, machine_role)

        if result.get('success'):
            from gui.ipc.token_manager import token_manager
            token = token_manager.generate_token(username, machine_role)
            
            # Trigger onboarding check after successful login
            try:
                config_manager = AppContext.get_config_manager()
                if config_manager and hasattr(config_manager, 'llm_manager'):
                    # Reset onboarding flag so it can be shown again for this user
                    config_manager.llm_manager.reset_onboarding_flag()
                    # Schedule onboarding check (will run after a delay)
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(config_manager.llm_manager.check_and_show_onboarding(
                            delay_seconds=3.0,
                            force_check=False
                        ))
                        logger.debug("[user_handler] Scheduled onboarding check after login")
                    except RuntimeError:
                        logger.debug("[user_handler] No event loop available for onboarding check")
            except Exception as e:
                logger.debug(f"[user_handler] Could not schedule onboarding check: {e}")
            
            # Get user profile from AuthManager (populated during login)
            user_profile = login.auth_manager.get_user_profile()
            
            return _build_user_info_response(
                request, token, user_profile, username, machine_role, 'password', 'login_success'
            )
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

        login = AppContext.get_login()
        if login is None:
            logger.warning("Login object is None - user may have logged out")
            return create_error_response(request, 
                'LOGIN_REQUIRED',
                'Login required - please login again')
        
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

        login = AppContext.get_login()
        if login is None:
            logger.warning("Login object is None - user may already be logged out")
            return create_success_response(request, {
                'message': auth_messages.get_message('logout_success')
            })
        
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

        login = AppContext.get_login()
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

        login = AppContext.get_login()
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

        login = AppContext.get_login()
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

@IPCHandlerRegistry.background_handler('google_login')
def handle_google_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle Google OAuth login in background thread to avoid blocking UI."""
    lang = auth_messages.DEFAULT_LANG
    try:
        lang = params.get('lang', auth_messages.DEFAULT_LANG) if params else auth_messages.DEFAULT_LANG
        machine_role = params.get('role', params.get('machine_role', 'Commander')) if params else 'Commander'
        auth_messages.set_language(lang)

        login = AppContext.get_login()
        if login is None:
            return create_error_response(request, 'SYSTEM_NOT_READY', 'System not ready')
        
        logger.info(f"[GoogleLogin] Starting Google OAuth login...")
        
        from gui.LoginoutGUI import LoginRequest, LoginType
        import asyncio
        
        login_request = LoginRequest(LoginType.GOOGLE_OAUTH, role=machine_role, schedule_mode='manual')
        
        try:
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            new_loop.run_until_complete(login._async_login(login_request))
            new_loop.close()
            
            if login.auth_manager.is_signed_in() and login.auth_manager.get_current_user():
                result = {'success': True}
            else:
                result = {'success': False, 'error': 'Authentication failed'}
        except Exception as e:
            logger.error(f"[GoogleLogin] Exception: {e}")
            result = {'success': False, 'error': str(e)}

        if result.get('success'):
            from gui.ipc.token_manager import token_manager
            user_email = login.auth_manager.get_current_user()
            user_profile = login.auth_manager.get_user_profile()
            session_token = token_manager.generate_token(user_email, machine_role)
            
            logger.info(f"[GoogleLogin] Completed for {user_email}, profile: {user_profile}")
            
            # Trigger onboarding check after successful Google login
            try:
                config_manager = AppContext.get_config_manager()
                if config_manager and hasattr(config_manager, 'llm_manager'):
                    # Reset onboarding flag so it can be shown again for this user
                    config_manager.llm_manager.reset_onboarding_flag()
                    # Schedule onboarding check (will run after a delay)
                    import asyncio
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(config_manager.llm_manager.check_and_show_onboarding(
                            delay_seconds=3.0,
                            force_check=False
                        ))
                        logger.debug("[user_handler] Scheduled onboarding check after Google login")
                    except RuntimeError:
                        logger.debug("[user_handler] No event loop available for onboarding check")
            except Exception as e:
                logger.debug(f"[user_handler] Could not schedule onboarding check: {e}")
            
            return _build_user_info_response(
                request, session_token, user_profile, user_email, machine_role, 'google', 'google_login_success'
            )
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[GoogleLogin] Failed: {error_msg}")
            return create_error_response(request, 'GOOGLE_LOGIN_ERROR', error_msg)

    except Exception as e:
        logger.error(f"Error in Google login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'GOOGLE_LOGIN_ERROR', auth_messages.get_message('login_failed'))