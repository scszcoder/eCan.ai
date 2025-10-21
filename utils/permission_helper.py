#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Permission Helper - Handle file permissions and secure write operations
"""

import os
import sys
import platform
from utils.logger_helper import logger_helper as logger
from config.constants import APP_NAME


class PermissionHelper:
    """Permission helper class for handling file permission related operations"""
    
    @staticmethod
    def is_admin() -> bool:
        """Check if current process has administrator privileges"""
        try:
            if platform.system() == 'Windows':
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0
            else:
                # Unix-like systems
                return os.geteuid() == 0
        except Exception:
            return False
    
    @staticmethod
    def can_write_to_directory(directory: str) -> bool:
        """Check if can write to specified directory"""
        try:
            # Ensure directory exists
            if not os.path.exists(directory):
                return False

            # Try to create temporary file
            test_file = os.path.join(directory, '.write_test_temp')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except (OSError, IOError, PermissionError):
            return False
    

    


    @staticmethod
    def safe_write_file(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
        """
        Safely write file with permission error handling

        Args:
            file_path: File path
            content: File content
            encoding: File encoding

        Returns:
            Whether write was successful
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # Try to write file
            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
            logger.info(f"Successfully wrote file: {file_path}")
            return True

        except PermissionError as e:
            # Check if this is a permission issue with root-owned directories
            if PermissionHelper._is_permission_issue(directory):
                logger.error(f"Permission denied: Cannot write to {file_path}")
                logger.error("This directory appears to be owned by root. Please fix permissions by running:")
                logger.error(f"sudo chown -R $(whoami):staff '{directory}'")
                logger.error("Or delete the directory and let the application recreate it.")
            else:
                logger.error(f"Permission denied writing to {file_path}: {e}")
            return False

        except Exception as e:
            logger.error(f"Failed to write file {file_path}: {e}")
            return False

    @staticmethod
    def _is_permission_issue(directory: str) -> bool:
        """
        Check if directory has permission issues (e.g., owned by root)

        Args:
            directory: Directory path to check

        Returns:
            Whether this appears to be a permission issue with root ownership
        """
        try:
            import pwd

            if not os.path.exists(directory):
                return False

            # Get directory owner
            dir_stat = os.stat(directory)
            dir_owner = pwd.getpwuid(dir_stat.st_uid).pw_name
            current_user = pwd.getpwuid(os.getuid()).pw_name

            # Check if directory is owned by root but we're not root
            return dir_owner == 'root' and current_user != 'root'

        except Exception:
            return False
    
    @staticmethod
    def safe_append_file(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
        """
        Safely append file content

        Args:
            file_path: File path
            content: Content to append
            encoding: File encoding

        Returns:
            Whether append was successful
        """
        try:
            # Ensure directory exists
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)

            # Try to append file
            with open(file_path, 'a', encoding=encoding) as f:
                f.write(content)

            return True

        except PermissionError:
            logger.warning(f"Permission denied appending to {file_path}")
            return False

        except Exception as e:
            logger.error(f"Failed to append to file {file_path}: {e}")
            return False
    
    @staticmethod
    def check_install_location() -> dict:
        """
        Check application install location and permission status

        Returns:
            Dictionary containing installation information
        """
        if getattr(sys, 'frozen', False):
            # Packaged application
            if hasattr(sys, '_MEIPASS'):
                app_path = sys._MEIPASS
            else:
                app_path = os.path.dirname(sys.executable)
        else:
            # Development environment
            app_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        is_system_install = False
        is_writable = PermissionHelper.can_write_to_directory(app_path)
        
        # Check if it's system-level installation
        if platform.system() == 'Windows':
            program_files = os.environ.get('PROGRAMFILES', 'C:\\Program Files')
            program_files_x86 = os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')
            is_system_install = (
                app_path.startswith(program_files) or
                app_path.startswith(program_files_x86)
            )
        elif platform.system() == 'Darwin':
            is_system_install = app_path.startswith('/Applications/')
        else:
            # Linux
            is_system_install = (
                app_path.startswith('/usr/') or
                app_path.startswith('/opt/') or
                app_path.startswith('/Applications/')
            )
        
        return {
            'app_path': app_path,
            'is_system_install': is_system_install,
            'is_writable': is_writable,
            'is_admin': PermissionHelper.is_admin(),
            'platform': platform.system()
        }
    
    @staticmethod
    def suggest_user_data_location() -> str:
        """
        Suggest user data directory location

        Returns:
            Suggested user data directory path
        """
        app_name = APP_NAME # Can be obtained from configuration

        if platform.system() == 'Windows':
            # Windows: Use LOCALAPPDATA
            base_path = os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
            return os.path.join(base_path, app_name)
        elif platform.system() == 'Darwin':
            # macOS: Use Application Support
            return os.path.expanduser(f'~/Library/Application Support/{app_name}')
        else:
            # Linux: Use XDG standard
            xdg_data_home = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
            return os.path.join(xdg_data_home, app_name)


# Global permission helper instance
permission_helper = PermissionHelper()


def check_write_permission(path: str) -> bool:
    """Convenience function: Check write permission"""
    return permission_helper.can_write_to_directory(os.path.dirname(path))


def safe_write(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """Convenience function: Safely write file"""
    return permission_helper.safe_write_file(file_path, content, encoding)


def safe_append(file_path: str, content: str, encoding: str = 'utf-8') -> bool:
    """Convenience function: Safely append file"""
    return permission_helper.safe_append_file(file_path, content, encoding)


def get_install_info() -> dict:
    """Convenience function: Get installation information"""
    return permission_helper.check_install_location()
