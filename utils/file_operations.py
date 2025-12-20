#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File Operations Utility - Centralized file operations with permission handling
Provides safe file operations that automatically handle permission issues
"""

import io
import os
import json
import csv
import shutil
import tempfile
from typing import Any, Dict, List, Optional, Union
from utils.logger_helper import logger_helper as logger
from utils.path_manager import path_manager
from utils.permission_helper import safe_write, safe_append
from config.app_info import app_info


class FileOperations:
    """Centralized file operations with automatic permission handling"""
    
    @staticmethod
    def write_json(file_path: str, data: Any, indent: int = 2, ensure_ascii: bool = False) -> bool:
        """
        Safely write JSON data to file
        
        Args:
            file_path: Target file path
            data: Data to write
            indent: JSON indentation
            ensure_ascii: Whether to ensure ASCII encoding
            
        Returns:
            Whether write was successful
        """
        try:
            # Ensure directory exists
            path_manager.ensure_directory_exists(file_path)
            
            # Convert data to JSON string
            json_content = json.dumps(data, indent=indent, ensure_ascii=ensure_ascii)
            
            # Use safe write
            return safe_write(file_path, json_content)
            
        except Exception as e:
            logger.error(f"Failed to write JSON file {file_path}: {e}")
            return False
    
    @staticmethod
    def read_json(file_path: str, default: Any = None) -> Any:
        """
        Safely read JSON data from file
        
        Args:
            file_path: Source file path
            default: Default value if file doesn't exist or can't be read
            
        Returns:
            Parsed JSON data or default value
        """
        try:
            if not os.path.exists(file_path):
                return default
                
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
                
        except Exception as e:
            logger.error(f"Failed to read JSON file {file_path}: {e}")
            return default
    
    @staticmethod
    def write_text(file_path: str, content: str, encoding: str = 'utf-8', append: bool = False) -> bool:
        """
        Safely write text content to file
        
        Args:
            file_path: Target file path
            content: Text content to write
            encoding: File encoding
            append: Whether to append instead of overwrite
            
        Returns:
            Whether write was successful
        """
        try:
            # Ensure directory exists
            path_manager.ensure_directory_exists(file_path)
            
            # Use appropriate safe method
            if append:
                return safe_append(file_path, content, encoding)
            else:
                return safe_write(file_path, content, encoding)
                
        except Exception as e:
            logger.error(f"Failed to write text file {file_path}: {e}")
            return False
    
    @staticmethod
    def read_text(file_path: str, encoding: str = 'utf-8', default: str = "") -> str:
        """
        Safely read text content from file
        
        Args:
            file_path: Source file path
            encoding: File encoding
            default: Default value if file doesn't exist or can't be read
            
        Returns:
            File content or default value
        """
        try:
            if not os.path.exists(file_path):
                return default
                
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
                
        except Exception as e:
            logger.error(f"Failed to read text file {file_path}: {e}")
            return default
    
    @staticmethod
    def write_csv(file_path: str, data: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> bool:
        """
        Safely write CSV data to file
        
        Args:
            file_path: Target file path
            data: List of dictionaries to write
            fieldnames: CSV field names (auto-detected if None)
            
        Returns:
            Whether write was successful
        """
        try:
            if not data:
                return safe_write(file_path, "")
            
            # Auto-detect fieldnames if not provided
            if fieldnames is None:
                fieldnames = list(data[0].keys())
            
            # Ensure directory exists
            path_manager.ensure_directory_exists(file_path)
            
            # Write CSV content to string first
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in data:
                writer.writerow(row)
            
            # Use safe write
            return safe_write(file_path, output.getvalue())
            
        except Exception as e:
            logger.error(f"Failed to write CSV file {file_path}: {e}")
            return False
    
    @staticmethod
    def read_csv(file_path: str, default: List[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Safely read CSV data from file
        
        Args:
            file_path: Source file path
            default: Default value if file doesn't exist or can't be read
            
        Returns:
            List of dictionaries or default value
        """
        if default is None:
            default = []
            
        try:
            if not os.path.exists(file_path):
                return default
                
            with open(file_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                return list(reader)
                
        except Exception as e:
            logger.error(f"Failed to read CSV file {file_path}: {e}")
            return default
    
    @staticmethod
    def copy_file(source_path: str, target_path: str, create_dirs: bool = True) -> bool:
        """
        Safely copy file with permission handling
        
        Args:
            source_path: Source file path
            target_path: Target file path
            create_dirs: Whether to create target directories
            
        Returns:
            Whether copy was successful
        """
        try:
            if not os.path.exists(source_path):
                logger.error(f"Source file not found: {source_path}")
                return False
            
            if create_dirs:
                path_manager.ensure_directory_exists(target_path)
            
            shutil.copy2(source_path, target_path)
            logger.info(f"Successfully copied file: {source_path} -> {target_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy file {source_path} to {target_path}: {e}")
            return False
    
    @staticmethod
    def move_file(source_path: str, target_path: str, create_dirs: bool = True) -> bool:
        """
        Safely move file with permission handling
        
        Args:
            source_path: Source file path
            target_path: Target file path
            create_dirs: Whether to create target directories
            
        Returns:
            Whether move was successful
        """
        try:
            if not os.path.exists(source_path):
                logger.error(f"Source file not found: {source_path}")
                return False
            
            if create_dirs:
                path_manager.ensure_directory_exists(target_path)
            
            shutil.move(source_path, target_path)
            logger.info(f"Successfully moved file: {source_path} -> {target_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to move file {source_path} to {target_path}: {e}")
            return False
    
    @staticmethod
    def delete_file(file_path: str, ignore_errors: bool = True) -> bool:
        """
        Safely delete file
        
        Args:
            file_path: File path to delete
            ignore_errors: Whether to ignore errors if file doesn't exist
            
        Returns:
            Whether deletion was successful
        """
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.info(f"Successfully deleted file: {file_path}")
                return True
            elif not ignore_errors:
                logger.error(f"File not found: {file_path}")
                return False
            else:
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete file {file_path}: {e}")
            return False
    
    @staticmethod
    def create_temp_file(suffix: str = "", prefix: str = "ecan_", content: str = "") -> Optional[str]:
        """
        Create temporary file with content
        
        Args:
            suffix: File suffix
            prefix: File prefix
            content: Initial content
            
        Returns:
            Temporary file path or None if failed
        """
        try:
            # Use app's temp directory
            temp_dir = app_info.appdata_temp_path
            
            # Create temporary file
            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=temp_dir)
            
            # Write content if provided
            if content:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write(content)
            else:
                os.close(fd)
            
            logger.debug(f"Created temporary file: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to create temporary file: {e}")
            return None


# Global file operations instance
file_ops = FileOperations()

# Convenience functions
def write_json(file_path: str, data: Any, **kwargs) -> bool:
    """Convenience function: Write JSON file"""
    return file_ops.write_json(file_path, data, **kwargs)

def read_json(file_path: str, default: Any = None) -> Any:
    """Convenience function: Read JSON file"""
    return file_ops.read_json(file_path, default)

def write_text(file_path: str, content: str, **kwargs) -> bool:
    """Convenience function: Write text file"""
    return file_ops.write_text(file_path, content, **kwargs)

def read_text(file_path: str, **kwargs) -> str:
    """Convenience function: Read text file"""
    return file_ops.read_text(file_path, **kwargs)

def write_csv(file_path: str, data: List[Dict[str, Any]], **kwargs) -> bool:
    """Convenience function: Write CSV file"""
    return file_ops.write_csv(file_path, data, **kwargs)

def read_csv(file_path: str, **kwargs) -> List[Dict[str, Any]]:
    """Convenience function: Read CSV file"""
    return file_ops.read_csv(file_path, **kwargs)
