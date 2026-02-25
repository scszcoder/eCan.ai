import traceback
from typing import Any, Optional, Dict
from app_context import AppContext
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from auth.auth_messages import auth_messages

from utils.logger_helper import logger_helper as logger


def _is_web_mode() -> bool:
    """Check if running in web deployment mode."""
    import os
    return os.getenv('ECAN_MODE', 'desktop') == 'web'


def _create_web_session(user_id: str, user_data: dict, auth_token: str = "") -> Optional[str]:
    """Create a web session for the user. Only called in web mode."""
    if not _is_web_mode():
        return None
    try:
        from gui.context.session_manager import SessionManager
        session_id = SessionManager.get_instance().create_session(
            user_id=user_id,
            username=user_data.get('email', user_id),  # Use email as username
            auth_token=auth_token,
        )
        logger.info(f"[user_handler] Created web session {session_id} for user {user_id}")
        return session_id
    except Exception as e:
        logger.error(f"[user_handler] Failed to create web session: {e}")
        return None


def _destroy_web_session(session_id: Optional[str] = None, user_id: Optional[str] = None) -> bool:
    """Destroy a web session. Only called in web mode."""
    if not _is_web_mode():
        return True
    try:
        from gui.context.session_manager import SessionManager
        manager = SessionManager.get_instance()
        if session_id:
            manager.destroy_session(session_id)
            logger.info(f"[user_handler] Destroyed web session {session_id}")
        elif user_id:
            context = manager.get_context_by_user(user_id)
            if context:
                for sid in list(manager._sessions.keys()):
                    if manager._sessions.get(sid) == context:
                        manager.destroy_session(sid)
                        logger.info(f"[user_handler] Destroyed web session {sid} for user {user_id}")
                        break
        return True
    except Exception as e:
        logger.error(f"[user_handler] Failed to destroy web session: {e}")
        return False


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

def _build_user_info_response(request, token, user_profile, username, machine_role, login_type, message_key, session_id=None):
    """Helper to build consistent user info response for both login methods.
    
    Args:
        session_id: Optional session ID for web mode. If provided, included in response.
    """
    user_email = user_profile.get('email') or username
    
    response_data = {
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
    }
    
    # Include session_id for web mode (frontend needs this for subsequent requests)
    if session_id:
        response_data['session_id'] = session_id
    
    return create_success_response(request, response_data)

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
            
            # Create web session if in web mode (no-op in desktop mode)
            user_email = user_profile.get('email') or username
            session_id = _create_web_session(username, {
                'email': user_email,
                'role': machine_role,
                'login_type': 'password'
            }, auth_token=token)
            
            return _build_user_info_response(
                request, token, user_profile, username, machine_role, 'password', 'login_success', session_id
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
            # Fallback: try to get saved login info directly from AuthManager
            logger.warning("Login object is None - attempting direct AuthManager access")
            try:
                from auth.auth_manager import AuthManager
                auth_manager = AuthManager()
                result = auth_manager.get_saved_login_info()
                logger.info(f"[get_last_login] Retrieved via fallback AuthManager: username={result.get('username')}")
            except Exception as fallback_error:
                logger.error(f"Fallback AuthManager access failed: {fallback_error}")
                return create_error_response(request, 
                    'LOGIN_REQUIRED',
                    'Login required - please login again')
        else:
            result = login.handleGetLastLogin()

        # Mask sensitive fields before logging
        safe_result = {k: ('***' if k == 'password' and v else v) for k, v in result.items()} if isinstance(result, dict) else result
        logger.info(f"last saved user info: {safe_result}")
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
        
        # Destroy web session if in web mode (no-op in desktop mode)
        session_id = params.get('session_id') if params else None
        _destroy_web_session(session_id=session_id)

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
            # Check if we're already in an async context (e.g., called from GraphQL handler)
            try:
                loop = asyncio.get_running_loop()
                # We're in an async context - use nest_asyncio to allow nested event loops
                import nest_asyncio
                nest_asyncio.apply()
                loop.run_until_complete(login._async_login(login_request))
            except RuntimeError:
                # No running loop - create a new one (traditional IPC path)
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    new_loop.run_until_complete(login._async_login(login_request))
                finally:
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
            
            # Create web session if in web mode (no-op in desktop mode)
            session_id = _create_web_session(user_email, {
                'email': user_email,
                'role': machine_role,
                'login_type': 'google'
            })
            
            return _build_user_info_response(
                request, session_token, user_profile, user_email, machine_role, 'google', 'google_login_success', session_id
            )
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[GoogleLogin] Failed: {error_msg}")
            return create_error_response(request, 'GOOGLE_LOGIN_ERROR', error_msg)

    except Exception as e:
        logger.error(f"Error in Google login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'GOOGLE_LOGIN_ERROR', auth_messages.get_message('login_failed'))

@IPCHandlerRegistry.handler('get_account_info')
def handle_get_account_info(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Fetch account info from cloud on demand.
    Called when user clicks refresh on Account page.
    """
    try:
        logger.info("[GetAccountInfo] Fetching account info from cloud...")
        
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')
        
        from agent.cloud_api.cloud_api import send_account_info_request_to_cloud
        
        # Build the account info request
        acct_ops = [{
            'actid': 0,
            'op': 'query',
            'options': '{}'
        }]
        
        response = send_account_info_request_to_cloud(
            mainwin.session,
            acct_ops,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint()
        )
        
        if response and 'errorType' not in response:
            logger.info("[GetAccountInfo] Account info fetched successfully")
            # Store in mainwin for later use
            mainwin._account_info = response
            return create_success_response(request, {'accountInfo': response})
        else:
            logger.warning(f"[GetAccountInfo] Failed to fetch account info: {response}")
            return create_error_response(request, 'FETCH_ERROR', str(response))
            
    except Exception as e:
        logger.error(f"[GetAccountInfo] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_ACCOUNT_INFO_ERROR', str(e))


@IPCHandlerRegistry.handler('req_api_key')
def handle_req_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Request a new API key from cloud."""
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')

        from agent.cloud_api.cloud_api import req_api_key

        customer = (params or {}).get('customer', 'guest')
        response = req_api_key(
            mainwin.session,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint(),
            customer=customer,
        )
        if response and 'errorType' not in response:
            logger.info(f"[ReqApiKey] API key generated successfully")
            return create_success_response(request, response)
        else:
            logger.warning(f"[ReqApiKey] Failed: {response}")
            return create_error_response(request, 'API_KEY_ERROR', response.get('message', str(response)))

    except Exception as e:
        logger.error(f"[ReqApiKey] Error: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'REQ_API_KEY_ERROR', str(e))


@IPCHandlerRegistry.handler('remove_api_key')
def handle_remove_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Remove an API key via cloud."""
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')

        from agent.cloud_api.cloud_api import remove_api_key

        masked_keys = (params or {}).get('masked_keys', [])
        if not masked_keys:
            return create_error_response(request, 'INVALID_PARAMS', 'masked_keys is required')

        response = remove_api_key(
            mainwin.session,
            mainwin.get_auth_token(),
            mainwin.getWanApiEndpoint(),
            masked_keys=masked_keys,
        )
        if response and 'errorType' not in response:
            logger.info(f"[RemoveApiKey] API key removed successfully")
            return create_success_response(request, response)
        else:
            logger.warning(f"[RemoveApiKey] Failed: {response}")
            return create_error_response(request, 'API_KEY_ERROR', response.get('message', str(response)))

    except Exception as e:
        logger.error(f"[RemoveApiKey] Error: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'REMOVE_API_KEY_ERROR', str(e))


@IPCHandlerRegistry.handler('get_auth_token')
def handle_get_auth_token(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get the Cognito JWT auth token from MainWindow."""
    try:
        logger.info("[GetAuthToken] Getting main window...")
        mainwin = AppContext.get_main_window()
        logger.info(f"[GetAuthToken] mainwin type: {type(mainwin)}, is None: {mainwin is None}")
        if not mainwin:
            return create_error_response(request, 'NO_MAINWIN', 'MainWindow not available')
        
        logger.info(f"[GetAuthToken] Checking get_auth_token method exists: {hasattr(mainwin, 'get_auth_token')}")
        logger.info(f"[GetAuthToken] get_auth_token type: {type(getattr(mainwin, 'get_auth_token', None))}")
        
        token = mainwin.get_auth_token()
        logger.info(f"[GetAuthToken] Token retrieved, length: {len(token) if token else 0}")
        if not token:
            return create_error_response(request, 'NO_TOKEN', 'No auth token available')
        
        return create_success_response(request, token)
    except Exception as e:
        logger.error(f"[GetAuthToken] Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_AUTH_TOKEN_ERROR', str(e))