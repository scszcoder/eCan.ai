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
            url_string: The complete URL scheme string (e.g., "ecan://auth/success")
            
        Returns:
            bool: True if handled successfully, False otherwise
        """
        try:
            logger.info(f"Handling URL scheme: {url_string}")
            parsed_url = urlparse(url_string)
            
            if parsed_url.scheme != "ecan":
                logger.warning(f"Unsupported URL scheme: {parsed_url.scheme}")
                return False
            
            # Route based on host
            if parsed_url.netloc == "auth":
                return self._handle_auth_callback(parsed_url)
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
            
            # Get application executable path
            if getattr(sys, 'frozen', False):
                app_path = sys.executable
            else:
                app_path = os.path.abspath(sys.argv[0])
            
            # Create the protocol key
            key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, "ecan")
            winreg.SetValue(key, "", winreg.REG_SZ, "URL:eCan Protocol")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")
            
            # Set the default icon
            icon_key = winreg.CreateKey(key, "DefaultIcon")
            icon_path = os.path.join(os.path.dirname(app_path), "eCan.ico")
            if os.path.exists(icon_path):
                winreg.SetValue(icon_key, "", winreg.REG_SZ, f"{icon_path},0")
            else:
                winreg.SetValue(icon_key, "", winreg.REG_SZ, f"{app_path},0")
            
            # Set the command to execute
            command_key = winreg.CreateKey(key, "shell\\open\\command")
            winreg.SetValue(command_key, "", winreg.REG_SZ, f'"{app_path}" "%1"')
            
            winreg.CloseKey(command_key)
            winreg.CloseKey(icon_key)
            winreg.CloseKey(key)
            
            logger.info("Windows URL scheme registered successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register Windows URL scheme: {e}")
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
