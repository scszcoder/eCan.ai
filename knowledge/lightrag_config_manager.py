"""
LightRAG Configuration Manager
Handles reading, writing, and managing LightRAG .env configuration files
"""
import os
import logging
from typing import Dict, Optional, List
from pathlib import Path

from knowledge.lightrag_config_utils import get_user_env_path, ensure_user_env_file

logger = logging.getLogger('eCan')


class LightRAGConfigManager:
    """
    Manages LightRAG configuration stored in .env files.
    Provides methods for reading, writing, and updating configuration.
    """
    
    def __init__(self):
        """Initialize the configuration manager."""
        self._config_cache: Optional[Dict[str, str]] = None
    
    def get_config_file_path(self) -> Optional[str]:
        """
        Get the path to the user's configuration file.
        
        Returns:
            Path to lightrag.env file, or None if unable to determine
        """
        env_path = ensure_user_env_file()
        return str(env_path) if env_path else None
    
    def read_config(self, use_cache: bool = False) -> Dict[str, str]:
        """
        Read configuration from .env file.
        
        Args:
            use_cache: If True, return cached config if available
            
        Returns:
            Dictionary of configuration key-value pairs
        """
        if use_cache and self._config_cache is not None:
            return self._config_cache.copy()
        
        config_file = self.get_config_file_path()
        if not config_file:
            logger.warning("[LightRAGConfig] Unable to determine config file path")
            return {}
        
        config = self._read_env_file(config_file)
        self._config_cache = config.copy()
        return config
    
    def write_config(self, config: Dict[str, str], merge: bool = True) -> bool:
        """
        Write configuration to .env file.
        
        Args:
            config: Dictionary of configuration key-value pairs to write
            merge: If True, merge with existing config; if False, replace entirely
            
        Returns:
            True if successful, False otherwise
        """
        config_file = self.get_config_file_path()
        if not config_file:
            logger.error("[LightRAGConfig] Unable to determine config file path")
            return False
        
        if merge:
            # Read existing config and merge
            existing_config = self._read_env_file(config_file)
            existing_config.update(config)
            config_to_write = existing_config
        else:
            config_to_write = config
        
        success = self._write_env_file(config_file, config_to_write)
        if success:
            self._config_cache = config_to_write.copy()
        return success
    
    def update_config(self, updates: Dict[str, str]) -> bool:
        """
        Update specific configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if successful, False otherwise
        """
        return self.write_config(updates, merge=True)
    
    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a specific configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        config = self.read_config(use_cache=True)
        return config.get(key, default)
    
    def set_value(self, key: str, value: str) -> bool:
        """
        Set a specific configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_config({key: value})
    
    def delete_value(self, key: str) -> bool:
        """
        Delete a specific configuration value.
        
        Args:
            key: Configuration key to delete
            
        Returns:
            True if successful, False otherwise
        """
        config_file = self.get_config_file_path()
        if not config_file:
            logger.error("[LightRAGConfig] Unable to determine config file path")
            return False
        
        config = self._read_env_file(config_file)
        if key in config:
            del config[key]
            success = self._write_env_file(config_file, config)
            if success:
                self._config_cache = config.copy()
            return success
        return True  # Key doesn't exist, consider it successful
    
    def clear_cache(self):
        """Clear the configuration cache."""
        self._config_cache = None
    
    def _read_env_file(self, file_path: str) -> Dict[str, str]:
        """
        Read .env file into a dictionary.
        
        Args:
            file_path: Path to .env file
            
        Returns:
            Dictionary of configuration key-value pairs
        """
        config = {}
        if not os.path.exists(file_path):
            logger.warning(f"[LightRAGConfig] Config file not found: {file_path}")
            return config
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value
                    if '=' not in line:
                        logger.warning(f"[LightRAGConfig] Invalid line {line_num} in {file_path}: {line}")
                        continue
                    
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    config[key] = value
            
            logger.debug(f"[LightRAGConfig] Read {len(config)} config entries from {file_path}")
        except Exception as e:
            logger.error(f"[LightRAGConfig] Error reading config file {file_path}: {e}")
        
        return config
    
    def _write_env_file(self, file_path: str, config: Dict[str, str]) -> bool:
        """
        Write configuration dictionary to .env file.
        
        Args:
            file_path: Path to .env file
            config: Dictionary of configuration key-value pairs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Prepare lines to write
            lines = []
            for key, value in sorted(config.items()):
                # Convert value to string
                str_val = str(value)
                
                # Add quotes if value contains spaces and isn't already quoted
                if ' ' in str_val and not (str_val.startswith('"') or str_val.startswith("'")):
                    str_val = f'"{str_val}"'
                
                lines.append(f"{key}={str_val}\n")
            
            # Write to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info(f"[LightRAGConfig] Wrote {len(config)} config entries to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[LightRAGConfig] Error writing config file {file_path}: {e}")
            return False
    
    def validate_config(self, config: Optional[Dict[str, str]] = None) -> tuple[bool, List[str]]:
        """
        Validate configuration for required fields and correct formats.
        
        Args:
            config: Configuration to validate, or None to validate current config
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        if config is None:
            config = self.read_config()
        
        errors = []
        
        # Add validation rules here as needed
        # Example: Check for required fields
        # required_fields = ['HOST', 'PORT']
        # for field in required_fields:
        #     if field not in config:
        #         errors.append(f"Missing required field: {field}")
        
        return len(errors) == 0, errors


# Global instance for convenience
_config_manager_instance: Optional[LightRAGConfigManager] = None


def get_config_manager() -> LightRAGConfigManager:
    """
    Get the global LightRAGConfigManager instance.
    
    Returns:
        LightRAGConfigManager instance
    """
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = LightRAGConfigManager()
    return _config_manager_instance
