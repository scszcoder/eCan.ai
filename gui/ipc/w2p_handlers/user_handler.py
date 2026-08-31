import traceback
import threading
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
    'TooManyRequestsException': 'forgot_password_failed',
    'LimitExceededException': 'forgot_password_failed',
    'FORGOT_PASSWORD_TIMEOUT': 'forgot_password_failed',
    'CodeMismatchException': 'confirm_forgot_invalid_code',
    'ExpiredCodeException': 'confirm_forgot_expired_code',
    'InvalidPasswordException': 'confirm_forgot_invalid_password',
    'UserNotFoundException': 'confirm_forgot_user_not_found',
    'CONFIRM_FORGOT_PASSWORD_TIMEOUT': 'confirm_forgot_failed',
}

def get_message_from_cognito_error(error_code, default_key):
    """Maps a Cognito error code to a localized message key."""
    key = COGNITO_ERROR_MAP.get(error_code, default_key)
    return auth_messages.get_message(key)

def _get_endpoint_config_for_settings() -> Optional[Dict[str, str]]:
    """Get AppSync endpoint config for general_settings, or None if CN (CN uses TCB)."""
    try:
        from agent.cloud_api.endpoints import get_endpoint_config
        cfg = get_endpoint_config()
        if cfg.is_cn:
            return None  # CN uses TCB, handled by cloudbase_handler
        return {
            "wan_api_endpoint": cfg.graphql_endpoint,
            "ws_api_endpoint": cfg.ws_endpoint,
            "ws_api_host": cfg.host,
        }
    except Exception as e:
        logger.debug(f"[_get_endpoint_config_for_settings] Failed: {e}")
        return None


def _apply_endpoints_to_general_settings(cfg_ep: Dict[str, str]) -> bool:
    """Apply AppSync endpoints to general_settings. Returns True if any value changed."""
    try:
        from gui.context.config_manager import ConfigManager
        config_manager = ConfigManager.get_instance()
        gs = config_manager.general_settings
        
        changed = False
        if gs.wan_api_endpoint != cfg_ep.get("wan_api_endpoint"):
            gs.wan_api_endpoint = cfg_ep.get("wan_api_endpoint", "")
            changed = True
        if gs.ws_api_endpoint != cfg_ep.get("ws_api_endpoint"):
            gs.ws_api_endpoint = cfg_ep.get("ws_api_endpoint", "")
            changed = True
        if gs.ws_api_host != cfg_ep.get("ws_api_host"):
            gs.ws_api_host = cfg_ep.get("ws_api_host", "")
            changed = True
        
        if changed:
            config_manager.save_settings()
            logger.info(
                f"[_apply_endpoints_to_general_settings] Updated endpoints: "
                f"wan={gs.wan_api_endpoint}, ws={gs.ws_api_endpoint}, host={gs.ws_api_host}"
            )
        return changed
    except Exception as e:
        logger.debug(f"[_apply_endpoints_to_general_settings] Failed: {e}")
        return False


def _apply_intl_endpoints() -> None:
    """Apply AppSync endpoints from auth_config.yml for Intl version (called on login)."""
    try:
        cfg_ep = _get_endpoint_config_for_settings()
        if cfg_ep:
            _apply_endpoints_to_general_settings(cfg_ep)
    except Exception:
        pass


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
        
        # Check if this is a session replacement (user already logged in from another device)
        # NOTE: This optimization only applies to desktop/local environment, not web cloud
        from gui.ipc.token_manager import token_manager
        import os
        
        existing_token = token_manager._user_tokens.get(username)
        # Check if running in web cloud mode (ECAN_MODE=cloud)
        ecan_mode = os.getenv('ECAN_MODE', 'desktop').lower()
        is_session_replacement = existing_token is not None and ecan_mode != 'cloud'
        
        if is_session_replacement:
            # Session replacement: Skip full login flow, but ALWAYS generate new token
            # This ensures old sessions are properly invalidated (kicked offline)
            logger.info(f"[user_handler] 🔄 Session replacement detected for user: {username}")
            
            # Validate credentials directly via auth_manager (skip handleLogin to avoid re-initialization)
            auth_result = login.auth_manager.login(username, password, machine_role)
            
            if not auth_result.get('success'):
                error_code = auth_result.get('error', 'login_failed')
                message = get_message_from_cognito_error(error_code, 'login_failed')
                logger.warning(f"Login failed for user {username}: {error_code}")
                return create_error_response(request, 'INVALID_CREDENTIALS', message)
            
            # IMPORTANT: Generate new token to invalidate old session
            # The old token will be automatically deleted by token_manager.generate_token()
            # This ensures the user is kicked offline from the previous location
            token = token_manager.generate_token(username, machine_role)
            logger.info(f"[user_handler] ✅ New token generated for user: {username} (old session invalidated)")
        else:
            # First login: Execute full login flow with initialization
            logger.info(f"[user_handler] 🆕 First login for user: {username}")
            result = login.handleLogin(username, password, machine_role)

            if not result.get('success'):
                error_code = result.get('error', 'login_failed')
                message = get_message_from_cognito_error(error_code, 'login_failed')
                logger.warning(f"Login failed for user {username}: {error_code}")
                return create_error_response(request, 'INVALID_CREDENTIALS', message)
            
            # Generate token for first login
            token = token_manager.generate_token(username, machine_role)
        
        # Common logic for both scenarios
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
        
        # Apply AppSync endpoints from auth_config.yml (Intl only, CN uses TCB)
        _apply_intl_endpoints()
        
        return _build_user_info_response(
            request, token, user_profile, username, machine_role, 'password', 'login_success', session_id
        )

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

        # Flood-test harness: tell the frontend to auto-submit the prefilled
        # credentials so the GUI logs in (and visually transitions) with no
        # human click. Env-gated; no effect on normal runs.
        if isinstance(result, dict):
            import os as _os
            result['autologin'] = _os.getenv('ECAN_AUTOLOGIN', '0') == '1'

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

@IPCHandlerRegistry.handler('save_login_info')
def handle_save_login_info(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handles save_login_info requests - saves login credentials to keyring.

    This is used when the user checks 'Remember password' during login.

    The keyring.set_password() call (macOS Keychain) can take 1-12 seconds on
    cold start (Aug-20 trace measured 11.3s). That blocks the Starlette worker
    long enough to stall every other concurrent frontend request — including
    get_initialization_progress polling that the LoginCN page watches before
    navigating. We offload the actual write to a daemon thread and return
    immediately so the user's UI flow is never blocked by Keychain latency.
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        if params and 'lang' in params:
            lang = params['lang']
            auth_messages.set_language(lang)

        username = params.get('username') if params else None
        password = params.get('password') if params else None
        role = params.get('role') if params else None
        language = params.get('language') if params else None
        login_type = params.get('login_type') if params else None

        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Username is required')

        # Resolve the auth_manager once, on the request thread, so we don't
        # touch AppContext from the background thread.
        login = AppContext.get_login()
        if login is None:
            auth_manager = None
        else:
            auth_manager = login.auth_manager

        if auth_manager is None:
            # Fallback: build AuthManager directly so we still complete the save
            try:
                from auth.auth_manager import AuthManager
                auth_manager = AuthManager()
            except Exception as fallback_init_error:
                logger.error(f"Failed to construct AuthManager for save_login_info: {fallback_init_error}")
                return create_error_response(request, 'SAVE_ERROR', str(fallback_init_error))

        def _do_save():
            try:
                success = auth_manager._update_saved_login_info(
                    username=username,
                    password=password or "",
                    role=role or "Commander",
                    login_type=login_type
                )
                if success:
                    logger.info(f"[save_login_info] Background keyring save completed for {username}")
                else:
                    logger.warning(f"[save_login_info] Background keyring save returned failure for {username}")
            except Exception as bg_err:
                logger.error(f"[save_login_info] Background save failed for {username}: {bg_err} {traceback.format_exc()}")

        threading.Thread(target=_do_save, name="save-login-info", daemon=True).start()

        return create_success_response(request, {
            'message': 'Login info save scheduled',
            'async': True,
        })

    except Exception as e:
        logger.error(f"Error in save_login_info handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'SAVE_ERROR', f"Error during save_login_info: {str(e)}")

@IPCHandlerRegistry.handler('clear_login_info')
def handle_clear_login_info(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handles clear_login_info requests - clears saved credentials from keyring.
    
    This is used when the user unchecks 'Remember password'.
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        if params and 'lang' in params:
            lang = params['lang']
            auth_messages.set_language(lang)

        username = params.get('username') if params else None

        if not username:
            return create_error_response(request, 'INVALID_PARAMS', 'Username is required')

        login = AppContext.get_login()
        if login is None:
            # Fallback: try to get AuthManager directly
            try:
                from auth.auth_manager import AuthManager
                auth_manager = AuthManager()
                # Save with empty password to clear credentials, keep login_type
                success = auth_manager._update_saved_login_info(
                    username=username,
                    password="",
                    role="Commander",
                    login_type=None  # Clear login_type so user can choose again
                )
                if success:
                    return create_success_response(request, {
                        'message': 'Login info cleared successfully'
                    })
                else:
                    return create_error_response(request, 'CLEAR_FAILED', 'Failed to clear login info')
            except Exception as fallback_error:
                logger.error(f"Fallback clear failed: {fallback_error}")
                return create_error_response(request, 'CLEAR_ERROR', str(fallback_error))
        else:
            # Save with empty password to clear credentials, keep login_type
            success = login.auth_manager._update_saved_login_info(
                username=username,
                password="",
                role="Commander",
                login_type=None  # Clear login_type so user can choose again
            )
            if success:
                return create_success_response(request, {
                    'message': 'Login info cleared successfully'
                })
            else:
                return create_error_response(request, 'CLEAR_FAILED', 'Failed to clear login info')

    except Exception as e:
        logger.error(f"Error in clear_login_info handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'CLEAR_ERROR', f"Error during clear_login_info: {str(e)}")

@IPCHandlerRegistry.background_handler('logout')
def handle_logout(request: IPCRequest, params: Optional[Any]) -> IPCResponse:
    """Handles logout requests with internationalized responses.

    Note: This is a background handler because logout triggers async cleanup.
    The frontend kicks off cleanup, navigates back to /login, and re-arms
    WebSocket reconnection when LoginCN mounts (see
    gui_v2/src/pages/Login/LoginCN.tsx).  We return ``success`` immediately
    after firing the cleanup coroutine — there is no value in blocking the
    IPC response on cleanup completion:

      - Cleanup runs in the qasync event loop; a long block here would also
        block the GraphQL worker that processes ``get_initialization_progress``
        / ``get_last_login`` queries LoginCN fires on mount.  That's the
        exact race that was producing the perceived "logout hang" (terminals/
        7.txt post-logout 30-60s IPC failures during uvicorn graceful
        shutdown — see gui/LocalServer.py:1688 ``timeout_graceful_shutdown=1``).
      - Logout is best-effort: if any single cleanup step times out, the
        user should still be back at the login screen, not staring at a
        dead UI.  Cleanup exceptions are caught and logged inside
        ``MainWindow._async_cleanup_and_logout`` already.
    """
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

        # Fire-and-forget: ``handleLogout`` schedules ``MainWindow.logout``
        # via ``asyncio.run_coroutine_threadsafe`` with an internal 5s
        # timeout.  Cleanup runs on its own and we don't gate the IPC
        # response on it (see docstring above for the rationale).
        logger.info("[user_handler] Starting logout process (fire-and-forget)...")
        try:
            login.handleLogout()
        except Exception as cleanup_exc:
            # Cleanup exceptions must not surface to the IPC caller — the
            # frontend will redirect to /login regardless.  Log and move on.
            logger.warning(
                f"[user_handler] handleLogout raised {cleanup_exc!r}; "
                f"frontend will still proceed to /login"
            )

        # Destroy web session if in web mode (no-op in desktop mode)
        session_id = params.get('session_id') if params else None
        _destroy_web_session(session_id=session_id)

        return create_success_response(request, {
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
        if login is None:
            logger.warning("Login object is None during signup - system may not be properly initialized")
            return create_error_response(request,
                'SYSTEM_NOT_READY',
                auth_messages.get_message('signup_failed'))
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
        if login is None:
            logger.warning("Login object is None during forgot_password - system may not be properly initialized")
            return create_error_response(request,
                'SYSTEM_NOT_READY',
                auth_messages.get_message('forgot_password_failed'))
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
        if login is None:
            logger.warning("Login object is None during confirm_forgot_password - system may not be properly initialized")
            return create_error_response(request,
                'SYSTEM_NOT_READY',
                auth_messages.get_message('confirm_forgot_failed'))
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
            # Background handlers run in a separate thread, so we always need to create a new event loop
            # (cannot use get_running_loop() as that would get the Starlette server's loop from a different thread)
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(login._async_login(login_request))
            finally:
                new_loop.close()
            
            if login.auth_manager.is_signed_in() and login.auth_manager.get_current_user():
                result = {'success': True}
            else:
                error_detail = getattr(login.auth_manager, 'last_login_error', None) or 'Authentication failed'
                result = {'success': False, 'error': error_detail}
                # Propagate the structured port-occupied details (set by
                # auth_manager.google_login when the OAuth port is held by
                # another eCan.exe) so the frontend can offer a "force-close
                # other instance and retry" button.
                err_details = getattr(login.auth_manager, 'last_login_error_details', None)
                if isinstance(err_details, dict) and err_details.get('kind') == 'port_occupied':
                    result['error_kind'] = 'port_occupied'
                    result['error_details'] = err_details
        except Exception as e:
            logger.error(f"[GoogleLogin] Exception: {e}")
            result = {'success': False, 'error': str(e)}
            try:
                from auth.oauth.local_oauth_server import PortOccupiedError as _POE
                if isinstance(e, _POE):
                    result['error_kind'] = 'port_occupied'
                    result['error_details'] = {**e.to_dict(), 'kind': 'port_occupied'}
            except Exception:
                pass

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
            
            # Apply AppSync endpoints from auth_config.yml (Intl only, CN uses TCB)
            _apply_intl_endpoints()
            
            return _build_user_info_response(
                request, session_token, user_profile, user_email, machine_role, 'google', 'google_login_success', session_id
            )
        else:
            error_msg = result.get('error', 'Unknown error')
            logger.error(f"[GoogleLogin] Failed: {error_msg}")
            # When the error is the OAuth port being held by another
            # eCan.exe, route the structured details through the response
            # so the frontend can render a "force-close and retry" button.
            if result.get('error_kind') == 'port_occupied':
                return create_error_response(
                    request,
                    'OAUTH_PORT_OCCUPIED',
                    error_msg,
                    details=result.get('error_details'),
                )
            return create_error_response(request, 'GOOGLE_LOGIN_ERROR', error_msg)

    except Exception as e:
        logger.error(f"Error in Google login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'GOOGLE_LOGIN_ERROR', auth_messages.get_message('login_failed'))


@IPCHandlerRegistry.background_handler('wechat_login')
def handle_wechat_login(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle WeChat OAuth login in background thread to avoid blocking UI.

    This handler implements the desktop-app WeChat login flow:
    1. Start local OAuth server
    2. Open system browser to WeChat authorization
    3. Wait for callback from WeChat
    4. Exchange code for CloudBase token
    5. Complete login
    """
    lang = auth_messages.DEFAULT_LANG
    try:
        lang = params.get('lang', auth_messages.DEFAULT_LANG) if params else auth_messages.DEFAULT_LANG
        machine_role = params.get('role', params.get('machine_role', 'Commander')) if params else 'Commander'
        auth_messages.set_language(lang)

        login = AppContext.get_login()
        if login is None:
            return create_error_response(request, 'SYSTEM_NOT_READY', 'System not ready')

        logger.info("[WeChatLogin] Starting WeChat OAuth login...")

        # Directly call auth_manager.wechat_login() which handles the full flow
        result = login.auth_manager.wechat_login(role=machine_role)

        if result.get('success'):
            logger.info(f"[WeChatLogin] Success for user: {login.auth_manager.get_current_user()}")

            # Generate session token and return user info
            from gui.ipc.token_manager import token_manager
            user_email = login.auth_manager.get_current_user()
            user_profile = login.auth_manager.get_user_profile()
            session_token = token_manager.generate_token(user_email, machine_role)

            from gui.LoginoutGUI import _generate_session_id
            session_id = _generate_session_id()

            return _build_user_info_response(
                request,
                session_token,
                user_profile,
                user_email,
                machine_role,
                'wechat',
                'wechat_login_success',
                session_id
            )
        else:
            error_msg = result.get('error', 'WeChat login failed')
            logger.error(f"[WeChatLogin] Failed: {error_msg}")
            return create_error_response(request, 'WECHAT_LOGIN_ERROR', error_msg)

    except Exception as e:
        logger.error(f"Error in WeChat login handler: {e} {traceback.format_exc()}")
        auth_messages.set_language(lang)
        return create_error_response(request, 'WECHAT_LOGIN_ERROR', str(e))


@IPCHandlerRegistry.handler('force_close_oauth_port_blocker')
def handle_force_close_oauth_port_blocker(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Force-terminate the process holding the OAuth callback port.

    Only kills processes whose executable name matches our own (eCan.exe);
    refuses otherwise so a malicious caller can't use this as an
    arbitrary-process-kill primitive.  Used by the Login UI's
    "force-close other instance and retry" recovery flow when
    handle_google_login returns ``error_kind=port_occupied``.
    """
    try:
        from auth.auth_config import AuthConfig
        from auth.oauth.local_oauth_server import LocalOAuthServer
        from urllib.parse import urlparse

        callback_url = AuthConfig.GOOGLE.CALLBACK_URL
        port = urlparse(callback_url).port or 9382
        # Allow operator override (lets us also recover from non-default
        # ports if AuthConfig ever changes), but default to the configured
        # OAuth port.
        if params and isinstance(params.get('port'), int):
            port = int(params['port'])

        outcome = LocalOAuthServer.force_terminate_blocker(port, require_self=True)
        logger.warning(f"[force_close_oauth_port_blocker] port={port} outcome={outcome}")
        if outcome.get('ok'):
            return create_success_response(request, outcome)
        return create_error_response(
            request,
            'FORCE_CLOSE_FAILED',
            f"Could not close port {port} blocker: {outcome.get('reason') or 'unknown'}",
            details=outcome,
        )
    except Exception as e:
        logger.error(f"[force_close_oauth_port_blocker] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'FORCE_CLOSE_ERROR', str(e))


@IPCHandlerRegistry.handler('clear_auth_cache')
def handle_clear_auth_cache(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Clear all cached authentication data to fix stale login issues."""
    try:
        login = AppContext.get_login()
        if login is None:
            return create_error_response(request, 'SYSTEM_NOT_READY', 'System not ready')
        
        result = login.auth_manager.clear_auth_cache()
        logger.info(f"[ClearAuthCache] Result: {result}")
        return create_success_response(request, result)
    except Exception as e:
        logger.error(f"[ClearAuthCache] Error: {e} {traceback.format_exc()}")
        return create_error_response(request, 'CLEAR_CACHE_ERROR', str(e))

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


def _cn_session_token(mainwin) -> str:
    """The CN HTTP bearer (30-day session token preferred) for api-key calls."""
    from agent.cloud_api.cloud_api import _http_auth_header
    value = _http_auth_header(mainwin.get_auth_token() or "")
    return value[7:] if value.lower().startswith("bearer ") else value


@IPCHandlerRegistry.handler('sync_ecanai_account_api_key')
def handle_sync_ecanai_account_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Synchronize the signed-in account key to all local eCanAI providers."""
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')
        api_key = str((params or {}).get('api_key') or '').strip()
        if not api_key:
            return create_error_response(request, 'INVALID_PARAMS', 'api_key is required')

        from gui.manager.provider_settings_helper import sync_account_api_key_to_ecanai
        success, error = sync_account_api_key_to_ecanai(api_key, main_window=mainwin)
        if not success:
            return create_error_response(request, 'ECANAI_KEY_SYNC_ERROR', error or 'Key sync failed')
        return create_success_response(request, {'synchronized': True})
    except Exception as exc:
        logger.error(f'[SyncECanAIKey] Error: {exc}')
        return create_error_response(request, 'ECANAI_KEY_SYNC_ERROR', str(exc))


@IPCHandlerRegistry.handler('req_api_key')
def handle_req_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Request a new API key from cloud."""
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')

        customer = (params or {}).get('customer', 'guest')
        from utils.app_env import is_cn
        if is_cn():
            # CN: same myAPIKeygen backend the web Account page uses, so the
            # web and desktop manage ONE key. (The AWS-shaped reqApiKey
            # mutation below doesn't validate against the CN SDL.)
            from agent.cloud_api.api_keys import create_api_key
            response = create_api_key(_cn_session_token(mainwin), customer=customer)
            if response.get('apiKey'):
                return create_success_response(request, response)
            return create_error_response(request, 'API_KEY_ERROR',
                                         response.get('message', str(response)))

        from agent.cloud_api.cloud_api import req_api_key
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

        masked_keys = (params or {}).get('masked_keys', [])
        if not masked_keys:
            return create_error_response(request, 'INVALID_PARAMS', 'masked_keys is required')

        from utils.app_env import is_cn
        if is_cn():
            from agent.cloud_api.api_keys import remove_api_keys
            response = remove_api_keys(_cn_session_token(mainwin), masked_keys)
            if response.get('success') and not response.get('error'):
                return create_success_response(request, response)
            return create_error_response(request, 'API_KEY_ERROR',
                                         response.get('message', str(response)))

        from agent.cloud_api.cloud_api import remove_api_key
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


@IPCHandlerRegistry.handler('get_api_key')
def handle_get_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Fetch the account's existing API key (CN: myAPIKeygen getApiKey).

    An absent key is a SUCCESS with apiKey=None — the Account page uses it
    to decide whether to show the generate button.
    """
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')
        from utils.app_env import is_cn
        if not is_cn():
            return create_success_response(request, {'apiKey': None, 'status': 'not_supported'})
        from agent.cloud_api.api_keys import get_api_key
        response = get_api_key(_cn_session_token(mainwin))
        if response.get('success', True) and not response.get('error'):
            return create_success_response(request, response)
        return create_error_response(request, 'API_KEY_ERROR',
                                     response.get('message', str(response)))
    except Exception as e:
        logger.error(f"[GetApiKey] Error: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'GET_API_KEY_ERROR', str(e))


@IPCHandlerRegistry.handler('test_api_key')
@IPCHandlerRegistry.handler('query_api_keys')
def handle_test_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Validate an API key against the CN store (myAPIKeygen queryApiKey).

    Registered under both names: 'test_api_key' (CLI/tests naming) and
    'query_api_keys' (the Account page's validate button).
    """
    try:
        mainwin = AppContext.get_main_window()
        if not mainwin:
            return create_error_response(request, 'NOT_INITIALIZED', 'Main window not initialized')
        api_key = (params or {}).get('api_key', '') or (params or {}).get('apiKey', '')
        if not api_key:
            return create_error_response(request, 'INVALID_PARAMS', 'api_key is required')
        from utils.app_env import is_cn
        if not is_cn():
            return create_error_response(request, 'NOT_SUPPORTED', 'test_api_key is CN-only')
        # REAL end-to-end test: the key in an actual llm-proxy v1 request
        # (GET /v1/models) — the same surface the web app consumes it on.
        from agent.cloud_api.api_keys import test_api_key_live
        response = test_api_key_live(api_key)
        return create_success_response(request, response)
    except Exception as e:
        logger.error(f"[TestApiKey] Error: {e}")
        logger.error(traceback.format_exc())
        return create_error_response(request, 'TEST_API_KEY_ERROR', str(e))


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
