#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Path Manager - Solve permission issues during system-level installation
Handle path management for application install directory and user data directory
"""

import os
import sys
import shutil
from config.app_info import app_info
from config.envi import getECBotDataHome
from utils.logger_helper import logger_helper as logger


class PathManager:
    """
    Path Manager class for handling application file path issues
    Ensures no permission problems during system-level installation
    """
    
    def __init__(self):
        self.app_install_path = app_info.app_home_path
        self.user_data_path = getECBotDataHome()
        self.is_frozen = getattr(sys, 'frozen', False)
        
    def get_writable_path(self, relative_path: str, file_type: str = "data") -> str:
        """
        Get writable file path

        Args:
            relative_path: Relative path
            file_type: File type ("data", "config", "log", "skill", "temp")

        Returns:
            Complete writable path
        """
        if file_type in ["data", "config", "log", "skill", "temp"]:
            # These types of files should be written to user data directory
            return os.path.join(self.user_data_path, relative_path)
        else:
            # Other types might be read-only resources, read from install directory
            return os.path.join(self.app_install_path, relative_path)
    
    def get_readable_path(self, relative_path: str, prefer_user_data: bool = False) -> str:
        """
        Get readable file path with fallback mechanism

        Args:
            relative_path: Relative path
            prefer_user_data: Whether to prioritize reading from user data directory

        Returns:
            Complete readable path
        """
        if prefer_user_data:
            # Prioritize reading from user data directory
            user_path = os.path.join(self.user_data_path, relative_path)
            if os.path.exists(user_path):
                return user_path

            # If user data directory doesn't exist, fallback to install directory
            install_path = os.path.join(self.app_install_path, relative_path)
            if os.path.exists(install_path):
                return install_path

            # Neither exists, return user data path (for creation)
            return user_path
        else:
            # Prioritize reading from install directory
            install_path = os.path.join(self.app_install_path, relative_path)
            if os.path.exists(install_path):
                return install_path

            # Fallback to user data directory
            return os.path.join(self.user_data_path, relative_path)
    
    def get_skill_path(self, skill_path: str, skill_name: str, is_public: bool = True) -> str:
        """
        Get skill file path

        Args:
            skill_path: Skill path
            skill_name: Skill name
            is_public: Whether it's a public skill

        Returns:
            Complete path of skill file
        """
        if is_public:
            # Public skills: prioritize reading from user data directory, fallback to install directory if not exists
            relative_path = f"skills/{skill_path}/{skill_name}.psk"
            return self.get_readable_path(relative_path, prefer_user_data=True)
        else:
            # Private skills: only read from user data directory
            return os.path.join(self.user_data_path, f"my_skills/{skill_path}/{skill_name}.psk")
    
    def get_log_path(self, log_user: str, date_word: str, additional_path: str = "") -> str:
        """
        Get log file path

        Args:
            log_user: Username
            date_word: Date string
            additional_path: Additional path

        Returns:
            Complete path of log file
        """
        log_dir = os.path.join(self.user_data_path, log_user, "runlogs", log_user, date_word)
        if additional_path:
            log_dir = os.path.join(log_dir, additional_path)
        return log_dir
    
    def ensure_directory_exists(self, file_path: str) -> bool:
        """
        Ensure directory exists, create if it doesn't exist

        Args:
            file_path: File path

        Returns:
            Whether successfully created or directory already exists
        """
        try:
            directory = os.path.dirname(file_path)
            if directory and not os.path.exists(directory):
                os.makedirs(directory, exist_ok=True)
                logger.info(f"Created directory: {directory}")
            return True
        except Exception as e:
            logger.error(f"Failed to create directory for {file_path}: {e}")
            return False
    
    def copy_file_to_user_data(self, relative_path: str, force: bool = False) -> bool:
        """
        Copy file from install directory to user data directory

        Args:
            relative_path: Relative path
            force: Whether to force overwrite

        Returns:
            Whether copy was successful
        """
        try:
            source_path = os.path.join(self.app_install_path, relative_path)
            target_path = os.path.join(self.user_data_path, relative_path)

            if not os.path.exists(source_path):
                logger.warning(f"Source file not found: {source_path}")
                return False

            if os.path.exists(target_path) and not force:
                logger.info(f"Target file already exists: {target_path}")
                return True

            # Ensure target directory exists
            self.ensure_directory_exists(target_path)

            # Copy file
            shutil.copy2(source_path, target_path)
            logger.info(f"Copied file: {source_path} -> {target_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy file {relative_path}: {e}")
            return False
    
    def is_path_writable(self, path: str) -> bool:
        """
        Check if path is writable

        Args:
            path: Path to check

        Returns:
            Whether path is writable
        """
        try:
            # If it's a file, check parent directory
            if os.path.isfile(path):
                test_path = os.path.dirname(path)
            else:
                test_path = path

            # Try to create temporary file in directory
            test_file = os.path.join(test_path, '.write_test')
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            return True
        except (OSError, IOError, PermissionError):
            return False


# Global path manager instance
path_manager = PathManager()


def get_writable_path(relative_path: str, file_type: str = "data") -> str:
    """Convenience function: Get writable path"""
    return path_manager.get_writable_path(relative_path, file_type)


def get_readable_path(relative_path: str, prefer_user_data: bool = False) -> str:
    """Convenience function: Get readable path"""
    return path_manager.get_readable_path(relative_path, prefer_user_data)


def get_skill_path(skill_path: str, skill_name: str, is_public: bool = True) -> str:
    """Convenience function: Get skill file path"""
    return path_manager.get_skill_path(skill_path, skill_name, is_public)


def ensure_directory_exists(file_path: str) -> bool:
    """Convenience function: Ensure directory exists"""
    return path_manager.ensure_directory_exists(file_path)


def get_user_data_path(user: str = None) -> str:
    """
    Get user data path, optionally for a specific user

    Args:
        user (str, optional): User identifier for user-specific data path

    Returns:
        str: User data path
    """
    if user:
        return os.path.join(path_manager.user_data_path, user)
    return path_manager.user_data_path
