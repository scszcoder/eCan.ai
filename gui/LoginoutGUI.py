from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui start...")
import asyncio
import os
import platform
import traceback
from datetime import datetime

from gui.MainGUI import MainWindow
from auth.auth_service import AuthService
from config.app_info import app_info
from bot.envi import getECBotDataHome
from bot.network import commanderIP, commanderServer, commanderXport


print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui finished...")

# Configuration
ecbhomepath = app_info.app_home_path
ecb_data_homepath = getECBotDataHome()


class Login:
    """Main controller class that coordinates between UI and business logic for user authentication."""
    
    def __init__(self, parent=None):
        # Initialize business logic service
        self.auth_service = AuthService()
        
        # Application state
        self.xport = None
        self.ip = commanderIP
        self.main_win = None
        self.gui_net_msg_queue = asyncio.Queue()
        self.mainLoop = None
        
        logger.info("Login controller initialized")
    

    # Handler methods for UI callbacks
    def _handle_login(self, username: str, password: str, role: str, schedule_mode: str):
        """Handle login request from UI."""
        try:
            # Update auth service with selected role
            self.auth_service.set_role(role)
            
            # Attempt login
            success, message = self.auth_service.login(username, password, role)
            
            if success:
                self._launch_main_window(schedule_mode)
                logger.info("Login successful!")
            else:
                logger.error(f"Login failed: {message}")
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            logger.error(traceback.format_exc())
    
    def _handle_signup(self, username: str, password: str):
        """Handle signup request from UI."""
        try:
            success, message = self.auth_service.sign_up(username, password)
            
            if success:
                logger.info(f"Signup successful: {message}")
            else:
                logger.error(f"Signup failed: {message}")
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
    
    def _handle_forgot_password(self, username: str):
        """Handle forgot password request from UI."""
        try:
            success, message = self.auth_service.forgot_password(username)
            
            if success:
                logger.info(f"Forgot password: {message}")
            else:
                logger.error(f"Forgot password failed: {message}")
                
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
    
    def _handle_confirm_forgot_password(self, username: str, confirm_code: str, new_password: str):
        """Handle confirm forgot password request from UI."""
        try:
            success, message = self.auth_service.confirm_forgot_password(username, confirm_code, new_password)
            
            if success:
                logger.info(f"Password reset confirmed: {message}")
            else:
                logger.error(f"Password reset failed: {message}")
                
        except Exception as e:
            logger.error(f"Confirm forgot password error: {e}")
    
    def _handle_google_login(self, machine_role: str = "Commander", schedule_mode: str = "manual", lang: str = "en-US"):
        """Handle Google OAuth login request from UI.
        
        Delegates authentication to auth_service and handles UI-specific operations.
        
        Args:
            machine_role: Machine role for the user
            schedule_mode: Schedule mode for the application
            lang: Language for internationalization
            
        Returns:
            Tuple of (success: bool, message: str, data: dict)
        """
        try:
            from auth.auth_messages import auth_messages
            
            logger.info(f"Starting Google OAuth authentication flow for role: {machine_role}")
            
            # Set language for messages
            auth_messages.set_language(lang)
            
            # Delegate authentication to auth_service
            success, message, auth_data = self.auth_service.google_login(machine_role)
            
            if not success:
                logger.error(f"Google authentication failed: {message}")
                return False, message, {}
            
            # Launch main window after successful authentication
            try:
                self._launch_main_window(schedule_mode)
                logger.info("Main window launched successfully after Google login")
            except Exception as e:
                logger.error(f"Failed to launch main window: {e}")
                return False, f'Failed to launch main window: {str(e)}', {}
            
            # Add UI-specific data to response
            response_data = auth_data.copy()
            
            # Add redirect URL for web client
            response_data['redirect'] = '/dashboard'  # Default redirect to dashboard after successful login
            
            logger.info(f"Google login completed successfully for user: {auth_data['user_info']['email']}")
            
            return True, message, response_data
            
        except Exception as e:
            logger.error(f"Error in Google login handler: {e}")
            logger.error(traceback.format_exc())
            return False, f'Google login failed: {str(e)}', {}
    
    # Public interface methods
    def get_gui_msg_queue(self):
        """Get GUI message queue."""
        return self.gui_net_msg_queue

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
        return self.auth_service.get_role()

    def set_role(self, role):
        """Set machine role."""
        self.auth_service.set_role(role)

    def is_commander(self):
        """Check if current role is commander."""
        return self.auth_service.is_commander()

    def _launch_main_window(self, schedule_mode: str):
        """Launch the main application window after successful login."""
        try:
            # Get authentication tokens
            tokens = self.auth_service.get_tokens()
            # main_key = self.auth_service.scramble(self.auth_service.current_user_pw)
            
            # Create main window
            app_ctx = AppContext()
            
            self.main_win = MainWindow(
                self, tokens, self.mainLoop, self.ip,
                self.auth_service.current_user, ecbhomepath,
                self.gui_net_msg_queue, self.auth_service.machine_role, 
                schedule_mode, "en-US"  # Default language
            )
            
            # Configure main window
            self.main_win.setOwner(self.auth_service.current_user)
            if hasattr(self.auth_service, 'cog') and self.auth_service.cog:
                self.main_win.setCog(self.auth_service.cog)
            
            self.main_win.set_top_gui(app_ctx.web_gui)
            self.main_win.hide()
                        
            # Set main window in app context
            app_ctx.set_main_window(self.main_win)
            
            # Start token refresh task
            if tokens and isinstance(tokens, dict) and 'AuthenticationResult' in tokens:
                refresh_token = tokens['AuthenticationResult'].get('RefreshToken')
                if refresh_token:
                    asyncio.create_task(self.auth_service.refresh_tokens_periodically(refresh_token))
            
            logger.info(f"Main window launched for user: {self.auth_service.current_user}")
            
        except Exception as e:
            logger.error(f"Error launching main window: {e}")
            raise

    def setLoop(self, loop):
        """Set the main event loop."""
        self.mainLoop = loop

    def getCurrentUser(self):
        """Get current logged in user."""
        return self.auth_service.get_current_user()

    def getLogUser(self):
        """Get formatted user name for logging."""
        return self.auth_service.get_log_user()
    
    def getSignedIn(self):
        """Check if user is signed in."""
        return self.auth_service.is_signed_in()
    
    def handleGetLastLogin(self):
        """Get last login information from saved data."""
        return self.auth_service.get_saved_login_info()
    
    def get_mainwin(self):
        """Get main window instance."""
        return self.main_win
    
    def handleLogout(self):
        """Handle user logout."""
        try:
            success = self.auth_service.logout()
            if self.main_win:
                self.main_win.stop_lightrag_server()
            return success
        except Exception as e:
            logger.error(f"Logout error: {e}")
            return False
    

    # Legacy methods for backward compatibility with IPC handlers
    def handleLogin(self, uname="", pw="", mrole=""):
        """Legacy login method for backward compatibility with IPC handlers."""
        username = uname
        password = pw
        role = mrole or "Commander"  # Default role
        schedule_mode = "manual"  # Default schedule mode
        
        self._handle_login(username, password, role, schedule_mode)
        return "Successful" if self.auth_service.is_signed_in() else "Failed"
    
    def handleSignUp(self, uname="", pw=""):
        """Legacy signup method for backward compatibility with IPC handlers."""
        username = uname
        password = pw
        
        success, message = self.auth_service.sign_up(username, password)
        return success, message
    
    def handleForgotPassword(self, username):
        """Legacy forgot password method for backward compatibility with IPC handlers."""
        success, message = self.auth_service.forgot_password(username)
        return success
    
    def handleConfirmForgotPassword(self, username, confirm_code, new_password):
        """Legacy confirm forgot password method for backward compatibility with IPC handlers."""
        success, message = self.auth_service.confirm_forgot_password(username, confirm_code, new_password)
        return success, message
