from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from utils.time_util import TimeUtil
from typing import Dict, Any, Optional, Callable
from enum import Enum
from PySide6.QtCore import QTimer

print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui start...")

from auth.auth_manager import AuthManager
from config.app_info import app_info
from config.envi import getECBotDataHome
from agent.network.network import commanderIP
import asyncio
import os


print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui finished...")

# Configuration
ecbhomepath = app_info.app_home_path
ecb_data_homepath = getECBotDataHome()


class LoginType(Enum):
    """Login type enumeration"""
    USERNAME_PASSWORD = "username_password"
    GOOGLE_OAUTH = "google_oauth"
    MICROSOFT_OAUTH = "microsoft_oauth"
    GITHUB_OAUTH = "github_oauth"
    SSO = "sso"
    

class LoginRequest:
    """Login request data class"""
    def __init__(self, login_type: LoginType, **kwargs):
        self.login_type = login_type
        self.username = kwargs.get('username', '')
        self.password = kwargs.get('password', '')
        self.role = kwargs.get('role', 'Commander')
        self.schedule_mode = kwargs.get('schedule_mode', 'manual')
        self.extra_params = {k: v for k, v in kwargs.items() 
                           if k not in ['username', 'password', 'role', 'schedule_mode']}


class Login:
    """Main controller class that coordinates between UI and business logic for user authentication."""

    def __init__(self):
        # Initialize the authentication manager which handles all logic and state
        logger.info("Login controller initialized start")
        self.auth_manager = AuthManager()

        # Application state (unrelated to auth)
        self.xport = None
        self.ip = commanderIP
        self.main_win = None
        
        # Login progress tracking
        self._login_in_progress = False
        self._login_progress_callback = None
        
        # UI references (will be set by WebGUI)
        self.login_window = None
        self.login_progress_dialog = None
        
        # Login handler mapping
        self._login_handlers = {
            LoginType.USERNAME_PASSWORD: self._handle_username_password_auth,
            LoginType.GOOGLE_OAUTH: self._handle_google_oauth_auth,
            # Reserved for future expansion
            # LoginType.MICROSOFT_OAUTH: self._handle_microsoft_oauth_auth,
            # LoginType.GITHUB_OAUTH: self._handle_github_oauth_auth,
            # LoginType.SSO: self._handle_sso_auth,
        }

        logger.info("Login controller initialized end")
    
    def set_ui_references(self, login_window=None, login_progress_dialog=None):
        """Set references to UI components (called by WebGUI)"""
        self.login_window = login_window
        self.login_progress_dialog = login_progress_dialog
        logger.debug(f"[Login] UI references set: login_window={login_window is not None}, login_progress_dialog={login_progress_dialog is not None}")

    # Unified login entry method
    def login(self, request: LoginRequest) -> Dict[str, Any]:
        """Unified login processing entry point"""
        # Check if user is already logged in
        if self.auth_manager.is_signed_in():
            logger.info(f"User is already authenticated, launching main window directly")
            try:
                self._launch_main_window(request.schedule_mode)
                return {'success': True, 'message': 'Already authenticated, main window launched'}
            except Exception as e:
                logger.error(f"Failed to launch main window for authenticated user: {e}")
                return {'success': False, 'error': f'Failed to launch main window: {str(e)}'}
        
        # Check if login is already in progress
        if self._login_in_progress:
            logger.warning(f"Login already in progress, ignoring new {request.login_type.value} request")
            return {'success': False, 'error': 'Login already in progress'}
        
        # Check if the login type is supported
        if request.login_type not in self._login_handlers:
            return {'success': False, 'error': f'Unsupported login type: {request.login_type.value}'}
        
        # Set login status immediately to prevent concurrency
        self._login_in_progress = True
        
        try:
            # Start async login
            asyncio.create_task(self._async_login(request))
            return {'success': True, 'message': f'{request.login_type.value} login started asynchronously'}
        except Exception as e:
            # Reset status if startup fails
            self._login_in_progress = False
            logger.error(f"Failed to start async {request.login_type.value} login: {e}")
            return {'success': False, 'error': f'Failed to start login: {str(e)}'}
    
    def _handle_login(self, username: str, password: str, role: str, schedule_mode: str):
        """Handle synchronous login request from UI (for username/password login).
        
        This method executes authentication synchronously and returns the result immediately.
        If authentication succeeds, it starts an async task to create MainWindow.
        """
        try:
            logger.info(f"[Login] Synchronous login for user: {username}")
            
            # Execute authentication synchronously
            result = self.auth_manager.login(username, password, role)
            
            if result['success']:
                # Authentication successful, start async MainWindow creation
                logger.info(f"[Login] Authentication successful, launching main window...")
                request = LoginRequest(
                    LoginType.USERNAME_PASSWORD,
                    username=username,
                    password=password,
                    role=role,
                    schedule_mode=schedule_mode
                )
                
                # In web mode we don't have a Qt event loop/MainWindow; mark ready and return
                if os.getenv('ECAN_MODE', 'desktop') == 'web':
                    logger.info("[Login] Web mode detected - skipping MainWindow launch")
                    self._update_progress(100, "Web session ready")
                else:
                    # Start async task to create MainWindow
                    try:
                        asyncio.create_task(self._async_launch_main_window(request))
                    except Exception as e:
                        logger.error(f"[Login] Failed to start async main window launch: {e}")
                
                return {'success': True, 'message': 'Authentication successful'}
            else:
                # Authentication failed, return error immediately
                logger.warning(f"[Login] Authentication failed for user: {username}")
                return result
                
        except Exception as e:
            logger.error(f"[Login] Synchronous login error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'success': False, 'error': str(e)}
    
    async def _async_launch_main_window(self, request: LoginRequest):
        """Launch MainWindow asynchronously (authentication already succeeded).
        
        This method waits for preload completion and then launches MainWindow.
        Used by both synchronous login (_handle_login) and async login (_async_login).
        """
        try:
            logger.info(f"[Login] Starting async main window launch...")
            
            # Check and wait for background preload completion
            try:
                from gui.async_preloader import get_async_preloader
                
                preloader = get_async_preloader()
                
                if preloader.is_in_progress():
                    logger.info("[Login] 📦 Waiting for background preload to complete...")
                    self._update_progress(70, "Finalizing preload...")
                    
                    preload_result = await preloader.wait_for_completion(timeout=30.0)
                    success_count = preload_result.get('success_count', 0)
                    total_tasks = preload_result.get('total_tasks', 0)
                    
                    logger.info(f"[Login] 📦 Preload completed: {success_count}/{total_tasks} successful")
                    self._update_progress(75, f"Preload ready ({success_count}/{total_tasks})")
                elif preloader.is_complete():
                    result = preloader.get_summary()
                    logger.info(f"[Login] ✅ Preload ready: {result['success_count']}/{result['total_tasks']} modules")
                    self._update_progress(75, "Preload ready")
                else:
                    logger.warning("[Login] ⚠️ Preload not available, continuing...")
                    self._update_progress(75, "Loading without preload...")
                    
            except Exception as e:
                logger.warning(f"[Login] ⚠️ Preload check failed: {e}")
                self._update_progress(75, "Continuing...")
            
            # Launch main window
            self._update_progress(80, "Launching main window...")
            try:
                self._launch_main_window(request.schedule_mode)
                logger.info(f"[Login] ✅ Main window launched successfully")
            except Exception as e:
                logger.error(f"[Login] ❌ Main window launch failed: {e}")
                raise  # Re-raise exception for caller to handle
                
        except Exception as e:
            logger.error(f"[Login] ❌ Async main window launch error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise  # Re-raise exception
    
    async def _async_login(self, request: LoginRequest):
        """Unified async login processing method"""
        try:
            logger.info(f"[AsyncLogin] Starting async {request.login_type.value} login")
            
            # Update progress: start authentication
            self._update_progress(10, f"Starting {self._get_login_type_display_name(request.login_type)} authentication...")
            
            # Get corresponding authentication handler
            auth_handler = self._login_handlers[request.login_type]
            
            # Execute authentication
            result = await auth_handler(request)
            
            if result['success']:
                # Update progress: authentication successful
                self._update_progress(65, "Authentication successful, launching main window...")
                
                # Use unified MainWindow launch method
                try:
                    await self._async_launch_main_window(request)
                    self._update_progress(100, "Login completed!")
                    logger.info(f"[AsyncLogin] ✅ Async {request.login_type.value} login completed successfully")
                except Exception as e:
                    logger.error(f"[AsyncLogin] ❌ Main window launch failed: {e}")
                    self._update_progress(100, f"Launch failed: {str(e)}")
            else:
                # Authentication failed
                error_msg = result.get('error', 'Unknown error')
                logger.error(f"[AsyncLogin] ❌ Async {request.login_type.value} login failed: {error_msg}")
                self._update_progress(100, f"Authentication failed: {error_msg}")
                
                # Close progress dialog and return to login screen
                logger.info("[AsyncLogin] Scheduling return to login screen...")
                QTimer.singleShot(1000, self._close_progress_and_show_login)
                
        except Exception as e:
            logger.error(f"[AsyncLogin] ❌ Async {request.login_type.value} login exception: {e}")
            import traceback
            logger.error(f"[AsyncLogin] Exception traceback: {traceback.format_exc()}")
            self._update_progress(100, f"Login exception: {str(e)}")
            
            # Close progress dialog and return to login screen
            logger.info("[AsyncLogin] Scheduling return to login screen after exception...")
            QTimer.singleShot(1000, self._close_progress_and_show_login)
        finally:
            self._login_in_progress = False
    
    def _update_progress(self, progress: int, message: str):
        """Update login progress"""
        if self._login_progress_callback:
            self._login_progress_callback(progress, message)
    
    def _close_progress_and_show_login(self):
        """Close progress dialog and return to login screen (for async login failures)"""
        logger.info("[AsyncLogin] Returning to login screen")
        
        # Close progress dialog if it exists
        if hasattr(self, 'login_progress_dialog') and self.login_progress_dialog:
            try:
                self.login_progress_dialog.close()
                self.login_progress_dialog = None
            except Exception as e:
                logger.error(f"[AsyncLogin] Error closing progress dialog: {e}")
        
        # Show login window again (for async login failures like Google OAuth)
        if hasattr(self, 'login_window') and self.login_window:
            try:
                self.login_window.show()
                self.login_window.raise_()
                self.login_window.activateWindow()
                logger.info("[AsyncLogin] Login window shown")
            except Exception as e:
                logger.error(f"[AsyncLogin] Error showing login window: {e}")
    
    def _get_login_type_display_name(self, login_type: LoginType) -> str:
        """Get display name for login type"""
        display_names = {
            LoginType.USERNAME_PASSWORD: "Username/Password",
            LoginType.GOOGLE_OAUTH: "Google",
            LoginType.MICROSOFT_OAUTH: "Microsoft",
            LoginType.GITHUB_OAUTH: "GitHub",
            LoginType.SSO: "SSO"
        }
        return display_names.get(login_type, login_type.value)
    
    async def _handle_username_password_auth(self, request: LoginRequest) -> Dict[str, Any]:
        """Handle username/password authentication with timeout and progress"""
        import time
        from auth.performance_config import perf_config

        start_time = time.time()
        auth_config = perf_config.get_auth_flow_config()
        timeout = auth_config['total_timeout']

        try:
            # Update progress: start authentication
            self._update_progress(15, "Connecting to authentication server...")

            loop = asyncio.get_event_loop()
            auth_future = loop.run_in_executor(
                None,
                self.auth_manager.login,
                request.username, request.password, request.role
            )

            # Use configured timeout
            result = await asyncio.wait_for(auth_future, timeout=timeout)

            elapsed_time = time.time() - start_time
            if perf_config.should_log_timing():
                logger.info(f"Username/password authentication completed, elapsed: {elapsed_time:.2f}s")
            return result

        except asyncio.TimeoutError:
            elapsed_time = time.time() - start_time
            logger.error(f"Authentication timeout: {request.username}, timeout threshold: {timeout}s, actual elapsed: {elapsed_time:.2f}s")
            return {'success': False, 'error': f'Authentication timeout ({timeout}s), please check network connection'}
        except Exception as e:
            elapsed_time = time.time() - start_time
            logger.error(f"Authentication exception: {request.username}, exception: {str(e)}, elapsed: {elapsed_time:.2f}s")
            return {'success': False, 'error': f'Authentication failed: {str(e)}'}
    
    async def _handle_google_oauth_auth(self, request: LoginRequest) -> Dict[str, Any]:
        """Handle Google OAuth authentication"""
        loop = asyncio.get_event_loop()
        auth_future = loop.run_in_executor(
            None,
            self.auth_manager.google_login,
            request.role
        )
        return await auth_future

    def _handle_signup(self, username: str, password: str):
        """Handle signup request from UI."""
        self.auth_manager.sign_up(username, password)

    def _handle_forgot_password(self, username: str):
        """Handle forgot password request from UI."""
        self.auth_manager.forgot_password(username)

    def _handle_confirm_forgot_password(self, username: str, confirm_code: str, new_password: str):
        """Handle confirm forgot password request from UI."""
        self.auth_manager.confirm_forgot_password(username, confirm_code, new_password)

    def _handle_google_login(self, machine_role: str = "Commander", schedule_mode: str = "manual"):
        """Handle Google OAuth login request from UI (legacy compatibility)."""
        request = LoginRequest(
            LoginType.GOOGLE_OAUTH,
            role=machine_role,
            schedule_mode=schedule_mode
        )
        result = self.login(request)
        if result['success']:
            return True, result['message'], {}
        else:
            return False, result['error'], {}

    def set_xport(self, xport):
        """Set commander export port."""
        self.xport = xport
        if self.main_win:
            self.main_win.setCommanderXPort(xport)

    def set_ip(self, ip):
        """Set IP address."""
        self.ip = ip

    def set_wan_connected(self, wan_status):
        """Set WAN connection status."""
        if self.main_win:
            self.main_win.set_wan_connected(wan_status)

    def get_role(self):
        """Get current machine role."""
        return self.auth_manager.get_role()

    def set_role(self, role):
        """Set machine role."""
        self.auth_manager.set_role(role)

    def is_commander(self):
        """Check if current role is commander."""
        return self.auth_manager.is_commander()

    def _launch_main_window(self, schedule_mode: str):
        """Launch the main application window after successful login."""
        try:
            # Ensure execution in main thread
            from PySide6.QtWidgets import QApplication
            
            # Get main application instance
            app = QApplication.instance()
            if not app:
                raise RuntimeError("QApplication instance not found")
            
            # Use QMetaObject.invokeMethod to ensure execution in main thread
            def create_main_window():
                try:
                    from gui.MainGUI import MainWindow
                    self.main_win = MainWindow(
                        self.auth_manager, AppContext.main_loop, self.ip,
                        self.auth_manager.get_current_user(), ecbhomepath,
                        self.auth_manager.get_role(), schedule_mode
                    )
                    AppContext().set_main_window(self.main_win)
                    logger.info(f"[AsyncLogin] Main window launched for user: {self.auth_manager.get_current_user()}")
                    return True
                except Exception as e:
                    logger.error(f"[AsyncLogin] Error creating main window: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    return False
            
            from PySide6.QtCore import QThread
            current_thread = QThread.currentThread()
            main_thread = app.thread()
            
            if current_thread == main_thread:
                return create_main_window()
            else:
                from PySide6.QtCore import QTimer
                
                def schedule_in_main_thread():
                    try:
                        create_main_window()
                    except Exception as e:
                        logger.error(f"[AsyncLogin] Error in main window creation: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                
                QTimer.singleShot(0, app, schedule_in_main_thread)
                logger.info("[AsyncLogin] MainWindow scheduled in main thread")
                return True

        except Exception as e:
            logger.error(f"Error launching main window: {e}")
            raise

    def getCurrentUser(self):
        """Get current logged in user."""
        return self.auth_manager.get_current_user()

    def getLogUser(self):
        """Get formatted user name for logging."""
        return self.auth_manager.get_log_user()

    def getSignedIn(self):
        """Check if user is signed in."""
        return self.auth_manager.is_signed_in()

    def handleGetLastLogin(self):
        """Get last login information from saved data."""
        return self.auth_manager.get_saved_login_info()

    def get_mainwin(self):
        """Get main window instance."""
        return self.main_win

    def handleLogout(self):
        """Handle user logout (graceful)."""
        try:
            if self.main_win:
                # Delegate to MainWindow's graceful logout which cleans tasks/servers and closes window
                self.main_win.logout()
                return True
        except Exception as e:
            logger.warning(f"handleLogout fallback due to error: {e}")

        # Fallback to direct auth logout if main window missing
        # Clear IPC registry system ready cache in fallback case
        try:
            from gui.ipc.registry import IPCHandlerRegistry
            IPCHandlerRegistry.clear_system_ready_cache()
            logger.debug("LoginoutGUI: Cleared IPC registry system ready cache on logout fallback")
        except Exception as e:
            logger.debug(f"LoginoutGUI: Error clearing IPC registry cache: {e}")

        return self.auth_manager.logout()

    def get_main_window_status(self):
        """Get MainWindow initialization status"""
        # If async login is in progress, return login progress
        if self._login_in_progress:
            return {"ready": False, "progress": 50, "status": "logging_in"}
            
        if not self.main_win:
            return {"ready": False, "progress": 0, "status": "initializing"}
        
        # Use MainWindow's own state management
        if hasattr(self.main_win, 'is_fully_initialized'):
            is_fully_ready = self.main_win.is_fully_initialized()
            
            return {
                "ready": is_fully_ready,
                "progress": 100 if is_fully_ready else 80,
                "status": "ready" if is_fully_ready else "initializing"
            }
        
        # Fallback: check if there are basic initialization completion flags
        return {"ready": True, "progress": 100, "status": "ready"}
    
    def set_login_progress_callback(self, callback):
        """Set login progress callback function"""
        self._login_progress_callback = callback
    
    
    def is_login_in_progress(self):
        """Check if login is in progress"""
        return self._login_in_progress
    
    # Extension methods: reserved for future other login types
    # async def _handle_microsoft_oauth_auth(self, request: LoginRequest) -> Dict[str, Any]:
    #     """Handle Microsoft OAuth authentication"""
    #     # TODO: Implement Microsoft OAuth authentication logic
    #     pass
    # 
    # async def _handle_github_oauth_auth(self, request: LoginRequest) -> Dict[str, Any]:
    #     """Handle GitHub OAuth authentication"""
    #     # TODO: Implement GitHub OAuth authentication logic
    #     pass
    # 
    # async def _handle_sso_auth(self, request: LoginRequest) -> Dict[str, Any]:
    #     """Handle SSO authentication"""
    #     # TODO: Implement SSO authentication logic
    #     pass
    
    # Legacy methods for backward compatibility with IPC handlers
    def handleLogin(self, uname="", pw="", mrole=""):
        """Legacy login method for backward compatibility with IPC handlers."""
        return self._handle_login(uname, pw, mrole or "Commander", "manual")

    def handleSignUp(self, uname="", pw=""):
        """Legacy signup method for backward compatibility with IPC handlers."""
        result = self.auth_manager.sign_up(uname, pw)
        return result['success'], result.get('error', 'Signup successful.')

    def handleForgotPassword(self, username):
        """Legacy forgot password method for backward compatibility with IPC handlers."""
        result = self.auth_manager.forgot_password(username)
        return result['success']

    def handleConfirmForgotPassword(self, username, confirm_code, new_password):
        """Legacy confirm forgot password method for backward compatibility with IPC handlers."""
        result = self.auth_manager.confirm_forgot_password(username, confirm_code, new_password)
        return result['success'], result.get('error', 'Password reset successful.')
    
    def handleGetMainWindowStatus(self):
        """IPC handler to get main window initialization status"""
        status = self.get_main_window_status()
        return status['ready'], status['progress'], status['status']
    
    # Convenience methods: provide shortcuts for common login types
    def login_with_username_password(self, username: str, password: str, 
                                   role: str = "Commander", schedule_mode: str = "manual") -> Dict[str, Any]:
        """Convenience method for username/password login"""
        request = LoginRequest(
            LoginType.USERNAME_PASSWORD,
            username=username,
            password=password,
            role=role,
            schedule_mode=schedule_mode
        )
        return self.login(request)
    
    def login_with_google(self, role: str = "Commander", schedule_mode: str = "manual") -> Dict[str, Any]:
        """Convenience method for Google OAuth login"""
        request = LoginRequest(
            LoginType.GOOGLE_OAUTH,
            role=role,
            schedule_mode=schedule_mode
        )
        return self.login(request)
    
    # Convenience methods reserved for future expansion
    # def login_with_microsoft(self, role: str = "Commander", schedule_mode: str = "manual") -> Dict[str, Any]:
    #     """Convenience method for Microsoft OAuth login"""
    #     request = LoginRequest(LoginType.MICROSOFT_OAUTH, role=role, schedule_mode=schedule_mode)
    #     return self.login(request)
    # 
    # def login_with_github(self, role: str = "Commander", schedule_mode: str = "manual") -> Dict[str, Any]:
    #     """Convenience method for GitHub OAuth login"""
    #     request = LoginRequest(LoginType.GITHUB_OAUTH, role=role, schedule_mode=schedule_mode)
    #     return self.login(request)
    # 
    # def login_with_sso(self, sso_provider: str, role: str = "Commander", schedule_mode: str = "manual") -> Dict[str, Any]:
    #     """Convenience method for SSO login"""
    #     request = LoginRequest(LoginType.SSO, role=role, schedule_mode=schedule_mode, sso_provider=sso_provider)
    #     return self.login(request)
