#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
URL Scheme Handler for eCan Application

This module handles ecan:// URL scheme calls for OAuth callbacks and other
application-specific URL scheme operations.
"""

import sys
import os
import platform
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, Callable
from utils.logger_helper import logger_helper as logger


class URLSchemeHandler:
    """Handle ecan:// URL scheme calls"""
    
    def __init__(self, app_instance=None):
        """
        Initialize URL scheme handler
        
        Args:
            app_instance: Main application instance for callbacks
        """
        self.app = app_instance
        self.auth_success_callback: Optional[Callable] = None
        self.auth_error_callback: Optional[Callable] = None
        
    def set_app_instance(self, app_instance):
        """Set the main application instance"""
        self.app = app_instance
        
    def set_auth_callbacks(self, success_callback: Callable = None, error_callback: Callable = None):
        """Set authentication callback functions"""
        self.auth_success_callback = success_callback
        self.auth_error_callback = error_callback
    
    def handle_scheme_url(self, url_string: str) -> bool:
        """
        Process incoming URL scheme calls
        
        Args:
            url_string: The complete URL scheme string (e.g., "ecan://auth/success" or "ecan://")
            
        Returns:
            bool: True if handled successfully, False otherwise
        """
        try:
            logger.info(f"Handling URL scheme: {url_string}")
            parsed_url = urlparse(url_string)
            
            if parsed_url.scheme != "ecan":
                logger.warning(f"Unsupported URL scheme: {parsed_url.scheme}")
                return False
            
            # Bring application to foreground first
            self._bring_app_to_front()
            
            # Route based on host or path
            if parsed_url.netloc == "auth":
                return self._handle_auth_callback(parsed_url)
            elif not parsed_url.netloc or parsed_url.netloc == "":
                # Handle simple ecan:// calls (OAuth success from browser)
                logger.info("OAuth success callback received via simple ecan:// scheme")
                if self.auth_success_callback:
                    self.auth_success_callback()
                elif self.app and hasattr(self.app, 'handle_oauth_success'):
                    self.app.handle_oauth_success()
                return True
            else:
                logger.warning(f"Unknown URL host: {parsed_url.netloc}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling URL scheme: {e}")
            return False
    
    def _handle_auth_callback(self, parsed_url) -> bool:
        """Handle authentication callbacks"""
        try:
            if parsed_url.path == "/success":
                logger.info("OAuth authentication success callback received")
                if self.auth_success_callback:
                    self.auth_success_callback()
                elif self.app and hasattr(self.app, 'handle_oauth_success'):
                    self.app.handle_oauth_success()
                else:
                    logger.warning("No OAuth success handler configured")
                return True
                
            elif parsed_url.path == "/error":
                query_params = parse_qs(parsed_url.query)
                error = query_params.get('error', ['Unknown error'])[0]
                logger.error(f"OAuth authentication error: {error}")
                if self.auth_error_callback:
                    self.auth_error_callback(error)
                elif self.app and hasattr(self.app, 'handle_oauth_error'):
                    self.app.handle_oauth_error(error)
                else:
                    logger.warning("No OAuth error handler configured")
                return True
                
            else:
                logger.warning(f"Unknown auth callback path: {parsed_url.path}")
                return False
                
        except Exception as e:
            logger.error(f"Error handling auth callback: {e}")
            return False
    
    def _bring_app_to_front(self):
        """Bring application window to foreground"""
        try:
            if self.app:
                # Try different methods to bring window to front
                if hasattr(self.app, 'activateWindow'):
                    self.app.activateWindow()
                if hasattr(self.app, 'raise_'):
                    self.app.raise_()
                if hasattr(self.app, 'show'):
                    self.app.show()
                
                # Platform-specific methods
                import platform
                if platform.system() == 'Windows':
                    try:
                        import ctypes
                        hwnd = None
                        if hasattr(self.app, 'winId'):
                            hwnd = int(self.app.winId())
                        if hwnd:
                            user32 = ctypes.windll.user32
                            # Bring window to foreground
                            user32.SetForegroundWindow(hwnd)
                            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002)  # SWP_NOMOVE | SWP_NOSIZE
                            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002)  # HWND_TOPMOST then HWND_NOTOPMOST
                    except Exception as e:
                        logger.debug(f"Windows-specific bring to front failed: {e}")
                elif platform.system() == 'Darwin':  # macOS
                    try:
                        from AppKit import NSApplication, NSApplicationActivateIgnoringOtherApps
                        app = NSApplication.sharedApplication()
                        app.activateIgnoringOtherApps_(True)
                    except Exception as e:
                        logger.debug(f"macOS-specific bring to front failed: {e}")
                
                logger.info("Application brought to foreground")
        except Exception as e:
            logger.warning(f"Failed to bring application to foreground: {e}")


class URLSchemeRegistrar:
    """Handle URL scheme registration for different platforms"""
    
    @staticmethod
    def register_url_scheme() -> bool:
        """Register ecan:// URL scheme for the current platform"""
        system = platform.system().lower()
        
        if system == "windows":
            return URLSchemeRegistrar._register_windows()
        elif system == "darwin":
            return URLSchemeRegistrar._register_macos()
        elif system == "linux":
            return URLSchemeRegistrar._register_linux()
        else:
            logger.warning(f"URL scheme registration not supported for platform: {system}")
            return False
    
    @staticmethod
    def _register_windows() -> bool:
        """Register URL scheme in Windows registry"""
        try:
            import winreg
            import ctypes
            
            def is_admin():
                try:
                    return ctypes.windll.shell32.IsUserAnAdmin()
                except:
                    return False
            
            app_path = os.path.abspath(sys.executable)
            app_name = "eCan"
            registered = False
            
            # First try with HKCU (Current User) - doesn't require admin
            try:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Software\Classes\ecan", 0, 
                                     winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as key:
                    winreg.SetValue(key, "", winreg.REG_SZ, f"URL:{app_name} Protocol")
                    winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
                    
                    with winreg.CreateKeyEx(key, "shell\open\command", 0, 
                                         winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as cmd_key:
                        winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{app_path}" "%1"')
                    
                    # Set default icon if available
                    icon_path = os.path.join(os.path.dirname(app_path), "eCan.ico")
                    if os.path.exists(icon_path):
                        with winreg.CreateKeyEx(key, "DefaultIcon", 0, 
                                             winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY) as icon_key:
                            winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{icon_path}",0')
                
                logger.info("URL scheme registered in HKCU successfully")
                registered = True

                # Verify registration by reading back the key
                try:
                    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\ecan\\shell\\open\\command", 0,
                                      winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as verify_key:
                        command_value, _ = winreg.QueryValueEx(verify_key, "")
                        if app_path in command_value:
                            logger.info(f"URL scheme registration verified: {command_value}")
                        else:
                            logger.warning(f"URL scheme registration verification failed: {command_value}")
                except Exception as e:
                    logger.warning(f"Could not verify URL scheme registration: {e}")
                
            except Exception as e:
                logger.warning(f"Failed to register URL scheme in HKCU: {e}")
            
            # If not registered and running as admin, try HKLM
            if not registered and is_admin():
                try:
                    # Open or create HKLM key
                    key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, "Software\\Classes\\ecan", 0, 
                                          winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)
                    try:
                        winreg.SetValue(key, "", winreg.REG_SZ, f"URL:{app_name} Protocol")
                        winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
                        
                        # Set command
                        cmd_key = winreg.CreateKeyEx(key, "shell\\open\\command", 0, 
                                                  winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)
                        winreg.SetValue(cmd_key, "", winreg.REG_SZ, f'"{app_path}" "%1"')
                        winreg.CloseKey(cmd_key)
                        
                        # Set icon if available
                        icon_path = os.path.join(os.path.dirname(app_path), "eCan.ico")
                        if os.path.exists(icon_path):
                            icon_key = winreg.CreateKeyEx(key, "DefaultIcon", 0, 
                                                       winreg.KEY_WRITE | winreg.KEY_WOW64_64KEY)
                            winreg.SetValue(icon_key, "", winreg.REG_SZ, f'"{icon_path}",0')
                            winreg.CloseKey(icon_key)
                        
                        logger.info("Windows URL scheme registered in HKLM successfully")
                        return True
                        
                    finally:
                        winreg.CloseKey(key)
                        
                except Exception as e:
                    logger.error(f"Failed to register URL scheme in HKLM: {e}")
                    return False
            elif not registered:
                logger.warning("URL scheme registration failed. Some features may be limited.")
                # Still return True if HKCU registration succeeded, as that's sufficient for most use cases
                return False
                    
        except Exception as e:
            logger.error(f"Unexpected error during URL scheme registration: {e}")
            return False
    
    @staticmethod
    def _register_macos() -> bool:
        """Register URL scheme for macOS (requires Info.plist configuration)"""
        # macOS URL scheme registration is handled via Info.plist
        # This method just logs the requirement
        logger.info("macOS URL scheme registration requires Info.plist configuration")
        logger.info("Please ensure CFBundleURLTypes is configured in your app bundle")
        return True
    
    @staticmethod
    def _register_linux() -> bool:
        """Register URL scheme for Linux"""
        try:
            # Create desktop entry for URL scheme handling
            desktop_entry = f"""[Desktop Entry]
Name=eCan
Exec={sys.executable} %u
Icon=ecan
Type=Application
MimeType=x-scheme-handler/ecan
"""
            
            # Write to user applications directory
            apps_dir = os.path.expanduser("~/.local/share/applications")
            os.makedirs(apps_dir, exist_ok=True)
            
            desktop_file = os.path.join(apps_dir, "ecan.desktop")
            with open(desktop_file, 'w') as f:
                f.write(desktop_entry)
            
            # Update desktop database and register MIME type
            os.system("update-desktop-database ~/.local/share/applications/")
            os.system("xdg-mime default ecan.desktop x-scheme-handler/ecan")
            
            logger.info("Linux URL scheme registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register Linux URL scheme: {e}")
            return False


def check_url_scheme_launch() -> Optional[str]:
    """
    Check if application was launched via URL scheme
    
    Returns:
        str: URL scheme string if launched via scheme, None otherwise
    """
    if len(sys.argv) > 1:
        url_arg = sys.argv[1]
        if url_arg.startswith("ecan://"):
            logger.info(f"Application launched via URL scheme: {url_arg}")
            return url_arg
    return None


def setup_url_scheme_handling(app_instance=None, auto_register: bool = True) -> URLSchemeHandler:
    """
    Setup URL scheme handling for the application
    
    Args:
        app_instance: Main application instance
        auto_register: Whether to automatically register URL scheme
        
    Returns:
        URLSchemeHandler: Configured handler instance
    """
    handler = URLSchemeHandler(app_instance)
    
    # Auto-register URL scheme if requested
    if auto_register:
        try:
            URLSchemeRegistrar.register_url_scheme()
        except Exception as e:
            logger.warning(f"URL scheme auto-registration failed: {e}")
    
    # Check for URL scheme launch
    scheme_url = check_url_scheme_launch()
    if scheme_url:
        handler.handle_scheme_url(scheme_url)
    
    return handler
