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
from gui.login_ui import LoginUI
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
        
        # Initialize UI
        self.ui = LoginUI(parent)
        
        # Setup UI callbacks
        self._setup_ui_callbacks()
        
        # Application state
        self.xport = None
        self.ip = commanderIP
        self.main_win = None
        self.gui_net_msg_queue = asyncio.Queue()
        self.mainLoop = None
        
        # Load initial role from auth service
        self._sync_role_with_ui()
        
        logger.info("Login controller initialized")
    
    def _setup_ui_callbacks(self):
        """Setup callbacks between UI and business logic."""
        self.ui.set_login_callback(self._handle_login)
        self.ui.set_signup_callback(self._handle_signup)
        self.ui.set_forgot_password_callback(self._handle_forgot_password)
        self.ui.set_confirm_forgot_password_callback(self._handle_confirm_forgot_password)
    
    def _sync_role_with_ui(self):
        """Sync role selection in UI with auth service."""
        role = self.auth_service.get_role()
        role_list = ["Staff Officer", "Commander", "Commander Only", "Platoon"]
        try:
            role_index = role_list.index(role)
            self.ui.role_select.setCurrentIndex(role_index)
        except ValueError:
            self.ui.role_select.setCurrentIndex(1)  # Default to Commander

    # Handler methods for UI callbacks
    def _handle_login(self, username: str, password: str, role: str, schedule_mode: str):
        """Handle login request from UI."""
        try:
            # Update auth service with selected role
            self.auth_service.set_role(role)
            
            # Attempt login
            success, message = self.auth_service.login(username, password, role)
            
            if success:
                # Save user settings
                self.ui.save_user_settings(username)
                
                # Hide UI and launch main window
                self.ui.hide()
                self._launch_main_window(schedule_mode)
                
                logger.info("Login successful!")
            else:
                self.ui.show_error_message(message)
                logger.error(f"Login failed: {message}")
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            self.ui.show_error_message(f"Login failed: {str(e)}")
            logger.error(traceback.format_exc())
    
    def _handle_signup(self, username: str, password: str):
        """Handle signup request from UI."""
        try:
            success, message = self.auth_service.sign_up(username, password)
            
            if success:
                self.ui.show_success_message(message)
                self.ui.reset_to_login_mode()
            else:
                self.ui.show_error_message(message)
                
        except Exception as e:
            logger.error(f"Signup error: {e}")
            self.ui.show_error_message(f"Signup failed: {str(e)}")
    
    def _handle_forgot_password(self, username: str):
        """Handle forgot password request from UI."""
        try:
            success, message = self.auth_service.forgot_password(username)
            
            if success:
                self.ui.show_info_message(message)
            else:
                self.ui.show_error_message(message)
                
        except Exception as e:
            logger.error(f"Forgot password error: {e}")
            self.ui.show_error_message(f"Password reset failed: {str(e)}")
    
    def _handle_confirm_forgot_password(self, username: str, confirm_code: str, new_password: str):
        """Handle confirm forgot password request from UI."""
        try:
            success, message = self.auth_service.confirm_forgot_password(username, confirm_code, new_password)
            
            if success:
                self.ui.show_success_message(message)
                self.ui.reset_to_login_mode()
            else:
                self.ui.show_error_message(message)
                
        except Exception as e:
            logger.error(f"Confirm forgot password error: {e}")
            self.ui.show_error_message(f"Password confirmation failed: {str(e)}")
    
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
        self._sync_role_with_ui()

    def is_commander(self):
        """Check if current role is commander."""
        return self.auth_service.is_commander()

    def _launch_main_window(self, schedule_mode: str):
        """Launch the main application window after successful login."""
        try:
            # Set environment variable for password
            if platform.system() == 'Darwin':
                self._set_env_variable_macos("SCECBOTPW", self.auth_service.scramble(self.auth_service.current_user_pw))
            else:
                os.environ["SCECBOTPW"] = self.auth_service.scramble(self.auth_service.current_user_pw)
            
            # Get authentication tokens
            tokens = self.auth_service.get_tokens()
            main_key = self.auth_service.scramble(self.auth_service.current_user_pw)
            
            # Create main window
            app_ctx = AppContext()
            
            self.main_win = MainWindow(
                self, main_key, tokens, self.mainLoop, self.ip,
                self.auth_service.current_user, ecbhomepath,
                self.gui_net_msg_queue, self.auth_service.machine_role, 
                schedule_mode, self.ui.get_language()
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
    
    def _set_env_variable_macos(self, var_name: str, var_value: str, shell=None):
        """Set environment variable on macOS."""
        if not shell:
            shell = os.path.basename(os.environ.get('SHELL', ''))
        
        if shell == 'bash':
            config_file = os.path.join(os.path.expanduser('~'), '.bash_profile')
            if not os.path.exists(config_file):
                config_file = os.path.join(os.path.expanduser('~'), '.bashrc')
        elif shell == 'zsh':
            config_file = os.path.join(os.path.expanduser('~'), '.zshrc')
        else:
            logger.warning("Unsupported shell for environment variable setting")
            return
        
        env_var_command = f'export {var_name}="{var_value}"'
        variable_updated = False
        
        try:
            with open(config_file, 'r') as file:
                lines = file.readlines()
            
            with open(config_file, 'w') as file:
                for line in lines:
                    if line.strip().startswith(f'export {var_name}='):
                        file.write(f'{env_var_command}\n')
                        variable_updated = True
                    else:
                        file.write(line)
                
                if not variable_updated:
                    file.write(f'\n{env_var_command}\n')
            
            logger.info(f"Environment variable {var_name} {'updated' if variable_updated else 'set'} in {config_file}")
        except IOError as e:
            logger.error(f"Unable to write to {config_file}: {e}")

    def set_or_replace_env_variable_macos(self, var_name, var_value, shell=None):
        """
        Sets or replaces a permanent environment variable for the user on macOS.
        The variable will be set or updated for the default shell of the user (Bash or Zsh).

        :param var_name: Name of the environment variable
        :param var_value: Value of the environment variable
        :param shell: Optional, specify the shell (bash or zsh), otherwise auto-detect
        :return: Status message
        """
        # Auto-detect the shell if not specified
        if not shell:
            shell = os.path.basename(os.environ.get('SHELL', ''))

        # Determine the appropriate config file based on the shell
        if shell == 'bash':
            config_file = os.path.join(os.path.expanduser('~'), '.bash_profile')
            if not os.path.exists(config_file):
                # Fallback to .bashrc if .bash_profile does not exist
                config_file = os.path.join(os.path.expanduser('~'), '.bashrc')
        elif shell == 'zsh':
            config_file = os.path.join(os.path.expanduser('~'), '.zshrc')
        else:
            return "Unsupported shell. Please use Bash or Zsh."

        # Construct the command to add or update the environment variable
        env_var_command = f'export {var_name}="{var_value}"'
        variable_updated = False

        # Check if the variable is already in the file
        try:
            with open(config_file, 'r') as file:
                lines = file.readlines()

            with open(config_file, 'w') as file:
                for line in lines:
                    # If the variable exists, replace its value
                    if line.strip().startswith(f'export {var_name}='):
                        file.write(f'{env_var_command}\n')
                        variable_updated = True
                    else:
                        file.write(line)

                # If the variable was not found, add it to the file
                if not variable_updated:
                    file.write(f'\n{env_var_command}\n')

            print(
                f"Environment variable {var_name} {'updated' if variable_updated else 'set'} successfully in {config_file}.")
        except IOError as e:
            print(f"Error: Unable to open or write to {config_file} - {e}")

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
    
    # UI delegation methods
    def show(self):
        """Show the login UI."""
        self.ui.show()
    
    def hide(self):
        """Hide the login UI."""
        self.ui.hide()
    
    def exec(self):
        """Execute the login dialog."""
        return self.ui.exec()

    # Legacy methods for backward compatibility with IPC handlers
    def handleLogin(self, uname="", pw="", mrole=""):
        """Legacy login method for backward compatibility with IPC handlers."""
        username = uname or self.ui.get_username()
        password = pw or self.ui.get_password()
        role = mrole or self.ui.get_role()
        schedule_mode = self.ui.get_schedule_mode()
        
        self._handle_login(username, password, role, schedule_mode)
        return "Successful" if self.auth_service.is_signed_in() else "Failed"
    
    def handleSignUp(self, uname="", pw=""):
        """Legacy signup method for backward compatibility with IPC handlers."""
        username = uname or self.ui.get_username()
        password = pw or self.ui.get_password()
        
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

    # Fake login method for testing
    def fakeLogin(self):
        """Fake login for testing purposes."""
        logger.info("Performing fake login for testing")
        
        username = self.ui.get_username() or "test@example.com"
        success, message = self.auth_service.fake_login(username)
        
        if success:
            self.ui.save_user_settings(username)
            self.ui.hide()
            self._launch_main_window(self.ui.get_schedule_mode())
            logger.info("Fake login completed successfully")
        else:
            self.ui.show_error_message(message)
