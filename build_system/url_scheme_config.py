#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
URL Scheme Build Configuration

This module handles URL scheme configuration for different platforms during build.
"""

import os
import sys
import platform
from pathlib import Path
from utils.logger_helper import logger_helper as logger


class URLSchemeBuildConfig:
    """Handle URL scheme configuration during build process"""
    
    @staticmethod
    def setup_url_scheme_for_build():
        """Setup URL scheme configuration for current platform"""
        system = platform.system().lower()
        
        if system == "darwin":
            return URLSchemeBuildConfig._setup_macos_build()
        elif system == "windows":
            return URLSchemeBuildConfig._setup_windows_build()
        elif system == "linux":
            return URLSchemeBuildConfig._setup_linux_build()
        else:
            logger.warning(f"URL scheme build setup not supported for platform: {system}")
            return False
    
    @staticmethod
    def _setup_macos_build():
        """Setup macOS build configuration"""
        try:
            # Ensure Info.plist exists in resource directory
            info_plist_path = Path("resource/Info.plist")
            if not info_plist_path.exists():
                logger.error("Info.plist not found in resource directory")
                return False
            
            logger.info("macOS URL scheme build configuration ready")
            logger.info("Info.plist with ecan:// scheme configuration found")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup macOS build configuration: {e}")
            return False
    
    @staticmethod
    def _setup_windows_build():
        """Setup Windows build configuration"""
        try:
            # Create Windows-specific build configuration
            build_config = {
                "url_scheme": "ecan",
                "protocol_name": "eCan Protocol",
                "executable_name": "eCan.exe",
                "icon_file": "eCan.ico"
            }
            
            # Save build configuration for PyInstaller
            import json
            config_path = Path("build_system/windows_url_scheme.json")
            with open(config_path, 'w') as f:
                json.dump(build_config, f, indent=2)
            
            logger.info("Windows URL scheme build configuration created")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Windows build configuration: {e}")
            return False
    
    @staticmethod
    def _setup_linux_build():
        """Setup Linux build configuration"""
        try:
            # Create desktop entry template
            desktop_entry = """[Desktop Entry]
Name=eCan
Exec={executable_path} %u
Icon=ecan
Type=Application
MimeType=x-scheme-handler/ecan
Categories=Utility;Development;
Comment=eCan Automation Platform
"""
            
            # Save desktop entry template
            template_path = Path("build_system/ecan.desktop.template")
            with open(template_path, 'w') as f:
                f.write(desktop_entry)
            
            logger.info("Linux URL scheme build configuration created")
            return True
            
        except Exception as e:
            logger.error(f"Failed to setup Linux build configuration: {e}")
            return False
    
    @staticmethod
    def get_pyinstaller_options():
        """Get PyInstaller options for URL scheme support"""
        system = platform.system().lower()
        options = []
        
        if system == "darwin":
            # macOS specific options
            info_plist_path = Path("resource/Info.plist")
            if info_plist_path.exists():
                options.extend([
                    f"--osx-bundle-identifier=com.ecan.app",
                    f"--info-plist={info_plist_path.absolute()}"
                ])
        
        elif system == "windows":
            # Windows specific options
            options.extend([
                "--uac-admin",  # Request admin privileges for registry access
                "--version-file=build_system/version_info.txt"
            ])
        
        return options




if __name__ == "__main__":
    # Setup URL scheme configuration for build
    URLSchemeBuildConfig.setup_url_scheme_for_build()
    
    # Print PyInstaller options
    options = URLSchemeBuildConfig.get_pyinstaller_options()
    if options:
        print("PyInstaller URL Scheme Options:")
        for option in options:
            print(f"  {option}")
