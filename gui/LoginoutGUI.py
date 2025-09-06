from app_context import AppContext
from utils.logger_helper import logger_helper as logger
from utils.time_util import TimeUtil

print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui start...")

from auth.auth_manager import AuthManager
from config.app_info import app_info
from bot.envi import getECBotDataHome
from bot.network import commanderIP


print(TimeUtil.formatted_now_with_ms() + " load LoginoutGui finished...")

# Configuration
ecbhomepath = app_info.app_home_path
ecb_data_homepath = getECBotDataHome()


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

        logger.info("Login controller initialized end")


    # Handler methods for UI callbacks, now simplified to delegate to AuthManager
    def _handle_login(self, username: str, password: str, role: str, schedule_mode: str):
        """Handle login request from UI and return the result."""
        result = self.auth_manager.login(username, password, role)
        if result['success']:
            self._launch_main_window(schedule_mode)
            logger.info("Login successful!")
        else:
            logger.error(f"Login failed: {result.get('error')}")
        return result

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
        """Handle Google OAuth login request from UI."""
        result = self.auth_manager.google_login(machine_role)
        if result['success']:
            self._launch_main_window(schedule_mode)
            logger.info("Google login successful!")
            return True, "Google login successful", {}
        else:
            logger.error(f"Google login failed: {result['error']}")
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
            from gui.MainGUI import MainWindow
            self.main_win = MainWindow(
                self.auth_manager, AppContext.main_loop, self.ip,
                self.auth_manager.get_current_user(), ecbhomepath,
                self.auth_manager.get_role(), schedule_mode
            )

            AppContext().set_main_window(self.main_win)

            logger.info(f"Main window launched for user: {self.auth_manager.get_current_user()}")

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
        return self.auth_manager.logout()

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
