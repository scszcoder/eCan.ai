"""
Environment Variables Utilities

This module provides utilities for loading and managing environment variables
from shell configuration files across different platforms.
"""

import os
import platform
import subprocess
import sys
from typing import Dict, List, Optional
from utils.logger_helper import logger_helper as logger
from .constants import (
    EnvLoadingConstants,
    ShellConfigConstants, 
    EnvDetectionConstants,
    APIKeyConstants,
    PlatformConstants,
    LoggingConstants,
    FileConstants,
    DefaultValues
)

# Import logger using the correct method
try:
    logger = logger.logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class EnvironmentLoader:
    """Environment variables loader for cross-platform shell configurations"""
    
    def __init__(self):
        self._loaded_marker = EnvLoadingConstants.SHELL_ENV_LOADED_MARKER
    
    def should_load_shell_environment(self) -> bool:
        """
        Determine if shell environment variables should be loaded.
        
        Returns:
            bool: True if shell environment should be loaded, False otherwise
        """
        # Check if already loaded
        if os.environ.get(self._loaded_marker):
            logger.debug("Shell environment already loaded, skipping")
            return False
        
        # Always load shell environment variables regardless of the running environment
        logger.debug("Shell environment loading enabled for all environments")
        return True
    
    def _is_terminal_environment(self) -> bool:
        """Check if running in a proper terminal environment"""
        # First check for IDE indicators - if present, not a pure terminal
        ide_indicators = [
            'PYCHARM_HOSTED',     # PyCharm
            'VSCODE_PID',         # VS Code
            'TERM_PROGRAM',       # Various IDEs (but also terminals)
        ]
        
        # If IDE indicators are present, not a pure terminal
        if any(os.environ.get(indicator) for indicator in ide_indicators[:2]):  # Exclude TERM_PROGRAM for now
            return False
        
        # Check for common terminal environment indicators
        terminal_indicators = [
            'TERM',           # Terminal type
            'SHELL',          # Shell path
            'PS1',            # Primary prompt string
        ]
        
        # If most terminal indicators are present, likely in terminal
        present_count = sum(1 for indicator in terminal_indicators if os.environ.get(indicator))
        return present_count >= 2
    
    def _needs_shell_environment(self) -> bool:
        """Check if the current environment needs shell configuration loading"""
        # Running as PyInstaller bundle
        if getattr(sys, 'frozen', False):
            return True
        
        # Running in IDE (common IDE environment variables)
        ide_indicators = [
            'PYCHARM_HOSTED',     # PyCharm
            'VSCODE_PID',         # VS Code
            'TERM_PROGRAM',       # Various IDEs
        ]
        
        if any(os.environ.get(indicator) for indicator in ide_indicators):
            return True
        
        # Always assume shell environment might be needed
        # This allows loading all available environment variables from shell configuration
        return True
    
    def load_shell_environment(self) -> int:
        """
        Load environment variables from shell configuration files.
        
        Returns:
            int: Number of environment variables loaded
        """
        try:
            if not self.should_load_shell_environment():
                return 0
            
            system = platform.system()
            loaded_count = 0
            
            if system == "Darwin":  # macOS
                loaded_count = self._load_macos_env_vars()
                
            elif system == "Windows":  # Windows
                loaded_count = self._load_windows_env_vars()
                
            elif system == "Linux":  # Linux
                loaded_count = self._load_linux_env_vars()
            
            else:
                logger.debug(f"Unsupported system for environment loading: {system}")
                return 0
            
            # Set marker to indicate shell environment has been loaded
            os.environ[self._loaded_marker] = '1'
            
            if loaded_count > 0:
                logger.info(f"Loaded {loaded_count} environment variables from system config")
                # Log the launch context for debugging (simplified)
                context = "PyInstaller bundle" if getattr(sys, 'frozen', False) else "development"
                logger.info(f"Running in {context} on {system} - shell environment loaded")
            else:
                logger.debug("No additional environment variables found in system config")
            
            # Print environment variables summary (non-blocking)
            self._print_env_summary()
            
            return loaded_count
                    
        except Exception as e:
            logger.debug(f"Failed to load shell environment variables: {e}")
            return 0
    
    def _load_macos_env_vars(self) -> int:
        """Load environment variables on macOS"""
        # Try multiple shell configurations
        config_files = []
        shell = os.environ.get('SHELL', '/bin/zsh')
        
        if 'zsh' in shell:
            config_files = ['~/.zshrc', '~/.zprofile']
            shell_cmd = 'zsh'
        else:
            config_files = ['~/.bash_profile', '~/.bashrc']
            shell_cmd = 'bash'
        
        loaded_count = 0
        for config_file in config_files:
            try:
                cmd = f'source {config_file} 2>/dev/null && env'
                result = subprocess.run([shell_cmd, '-c', cmd], 
                                      capture_output=True, text=True, timeout=EnvLoadingConstants.SHELL_COMMAND_TIMEOUT)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if '=' in line and not line.startswith('_'):
                            try:
                                key, value = line.split('=', 1)
                                # Load all environment variables that don't exist yet
                                if value.strip() and not os.environ.get(key):
                                    os.environ[key] = value.strip()
                                    loaded_count += 1
                                    # Log with masked value for security
                                    masked_value = self._mask_sensitive_value(key, value.strip())
                                    logger.info(f"Loaded from {config_file}: {key}={masked_value}")
                            except ValueError:
                                continue
            except Exception as e:
                logger.debug(f"Failed to load from {config_file}: {e}")
                continue
        
        return loaded_count
    
    def _load_windows_env_vars(self) -> int:
        """Load environment variables on Windows"""
        loaded_count = 0
        try:
            # Method 1: Try to get user environment variables from registry
            cmd = 'reg query "HKEY_CURRENT_USER\\Environment" /s'
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=EnvLoadingConstants.SHELL_COMMAND_TIMEOUT)
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'REG_SZ' in line or 'REG_EXPAND_SZ' in line:
                        parts = line.strip().split()
                        if len(parts) >= 3:
                            key = parts[0]
                            value = ' '.join(parts[2:])  # Handle values with spaces
                            # Load all environment variables that don't exist yet
                            if value.strip() and not os.environ.get(key):
                                os.environ[key] = value.strip()
                                loaded_count += 1
                                masked_value = self._mask_sensitive_value(key, value.strip())
                                logger.info(f"Loaded from Windows registry: {key}={masked_value}")
            
            # Method 2: Try PowerShell environment variables (if registry method didn't work)
            if loaded_count == 0:
                cmd = 'powershell -Command "Get-ChildItem Env: | ForEach-Object {Write-Output ($_.Name + \'=\' + $_.Value)}"'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=EnvLoadingConstants.SHELL_COMMAND_TIMEOUT)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if '=' in line and line.strip():
                            try:
                                key, value = line.strip().split('=', 1)
                                # Load all environment variables that don't exist yet
                                if value.strip() and not os.environ.get(key):
                                    os.environ[key] = value.strip()
                                    loaded_count += 1
                                    masked_value = self._mask_sensitive_value(key, value.strip())
                                    logger.info(f"Loaded from PowerShell: {key}={masked_value}")
                            except ValueError:
                                continue
                                
        except Exception as e:
            logger.debug(f"Failed to load Windows environment variables: {e}")
        
        return loaded_count
    
    def _load_linux_env_vars(self) -> int:
        """Load environment variables on Linux"""
        # Try multiple shell configurations
        config_files = ['~/.bashrc', '~/.profile', '~/.bash_profile', '~/.zshrc']
        
        loaded_count = 0
        for config_file in config_files:
            try:
                # Try bash first, then zsh
                for shell_cmd in ['bash', 'zsh']:
                    try:
                        cmd = f'source {config_file} 2>/dev/null && env'
                        result = subprocess.run([shell_cmd, '-c', cmd], 
                                              capture_output=True, text=True, timeout=EnvLoadingConstants.SHELL_COMMAND_TIMEOUT)
                        
                        if result.returncode == 0:
                            for line in result.stdout.split('\n'):
                                if '=' in line and not line.startswith('_'):
                                    try:
                                        key, value = line.split('=', 1)
                                        # Load all environment variables that don't exist yet
                                        if value.strip() and not os.environ.get(key):
                                            os.environ[key] = value.strip()
                                            loaded_count += 1
                                            masked_value = self._mask_sensitive_value(key, value.strip())
                                            logger.info(f"Loaded from {config_file} ({shell_cmd}): {key}={masked_value}")
                                    except ValueError:
                                        continue
                            break  # If successful with this shell, don't try others
                    except FileNotFoundError:
                        continue  # Shell not found, try next one
                        
            except Exception as e:
                logger.debug(f"Failed to load from {config_file}: {e}")
                continue
        
        return loaded_count
    
    def _print_env_summary(self):
        """Print environment variables summary (fast, non-blocking)"""
        try:
            all_env_vars = dict(os.environ)
            sensitive_count = sum(1 for key in all_env_vars.keys() if self._is_sensitive_variable(key))
            non_sensitive_count = len(all_env_vars) - sensitive_count
            
            logger.info(f"📊 Environment Summary: {len(all_env_vars)} total (sensitive: {sensitive_count}, non-sensitive: {non_sensitive_count})")
            
            # Log a few key API keys if present (masked)
            api_keys = [key for key in all_env_vars.keys() if '_API_KEY' in key.upper()]
            if api_keys:
                logger.info(f"🔑 API Keys found: {', '.join(api_keys[:3])}{'...' if len(api_keys) > 3 else ''}")
            ecan_keys = [key for key in all_env_vars.keys() if 'ECAN_' in key.upper()]
            if ecan_keys:
                logger.info(f"🔑 eCan Keys found: {', '.join(ecan_keys[:3])}{'...' if len(ecan_keys) > 3 else ''}")
 

        except Exception as e:
            logger.debug(f"Failed to print environment summary: {e}")
    
    def _print_all_environment_variables(self):
        """Print all environment variables for debugging (detailed, use sparingly)"""
        try:
            logger.info("=== System Environment Variables List ===")
            
            # Get all environment variables
            all_env_vars = dict(os.environ)
            
            # Separate sensitive and non-sensitive variables
            sensitive_vars = {}
            non_sensitive_vars = {}
            
            for key, value in all_env_vars.items():
                if self._is_sensitive_variable(key):
                    sensitive_vars[key] = value
                else:
                    non_sensitive_vars[key] = value
            
            # Print non-sensitive variables first
            if non_sensitive_vars:
                logger.info(f"📋 Non-sensitive environment variables ({len(non_sensitive_vars)} items):")
                for key in sorted(non_sensitive_vars.keys()):
                    value = non_sensitive_vars[key]
                    # Limit length for very long values
                    display_value = value[:100] + '...' if len(value) > 100 else value
                    logger.info(f"   {key}={display_value}")
            
            # Print sensitive variables with masking
            if sensitive_vars:
                logger.info(f"🔐 Sensitive environment variables ({len(sensitive_vars)} items):")
                for key in sorted(sensitive_vars.keys()):
                    value = sensitive_vars[key]
                    masked_value = self._mask_sensitive_value(key, value)
                    logger.info(f"   {key}={masked_value}")
            
            logger.info(f"📊 Total: {len(all_env_vars)} environment variables (sensitive: {len(sensitive_vars)}, non-sensitive: {len(non_sensitive_vars)})")
            logger.info("=== End of Environment Variables List ===")
            
        except Exception as e:
            logger.error(f"Failed to print environment variables: {e}")
    
    def _is_sensitive_variable(self, key: str) -> bool:
        """Check if a variable is sensitive"""
        sensitive_patterns = [
            '_API_KEY', '_KEY', '_TOKEN', '_SECRET', '_PASSWORD', 
            'ENDPOINT', 'ACCESS_KEY_ID', 'SECRET_ACCESS_KEY',
            '_PASS', '_PWD', '_AUTH', '_CREDENTIAL'
        ]
        
        key_upper = key.upper()
        return any(pattern in key_upper for pattern in sensitive_patterns)
    
    def get_all_env_vars_status(self) -> dict:
        """Get the status of all environment variables"""
        env_vars = {}
        
        # Return all environment variables and their status
        for key, value in os.environ.items():
            env_vars[key] = bool(value and value.strip())
        
        return env_vars
    
    def is_shell_environment_loaded(self) -> bool:
        """Check if shell environment has been loaded"""
        return bool(os.environ.get(self._loaded_marker))
    
    def _mask_sensitive_value(self, key: str, value: str) -> str:
        """Mask sensitive values for logging"""
        # Check if this looks like a sensitive value
        sensitive_patterns = [
            '_API_KEY', '_KEY', '_TOKEN', '_SECRET', '_PASSWORD', 
            'ENDPOINT', 'ACCESS_KEY_ID', 'SECRET_ACCESS_KEY'
        ]
        
        is_sensitive = any(pattern in key.upper() for pattern in sensitive_patterns)
        
        if is_sensitive and len(value) > 8:
            # Show first 4 and last 4 characters for sensitive values
            return value[:4] + '...' + value[-4:]
        elif is_sensitive:
            # For short sensitive values, just show ***
            return '***'
        else:
            # For non-sensitive values, show full value but limit length
            return value[:50] + '...' if len(value) > 50 else value
    
    def cleanup_deleted_api_keys(self, specific_key: str = None) -> int:
        """
        Clean up API key environment variables that have been deleted from configuration files.
        This method should be called after deleting API keys to ensure complete cleanup.
        
        Returns:
            int: Number of environment variables cleaned up
        """
        try:
            system = platform.system()
            logger.info(f"Cleaning up deleted API keys on {system}")
            
            if system == "Darwin":  # macOS
                return self._cleanup_macos_deleted_api_keys(specific_key)
            elif system == "Windows":  # Windows
                return self._cleanup_windows_deleted_api_keys(specific_key)
            elif system == "Linux":  # Linux
                return self._cleanup_linux_deleted_api_keys(specific_key)
            else:
                logger.debug(f"Unsupported system for API key cleanup: {system}")
                return 0
                
        except Exception as e:
            logger.error(f"Failed to cleanup deleted API keys: {e}")
            return 0
    
    def _cleanup_macos_deleted_api_keys(self, specific_key: str = None) -> int:
        """Clean up deleted API keys on macOS using simplified logic"""
        from gui.utils.api_key_validator import get_api_key_validator
        validator = get_api_key_validator()
        
        # Get shell configuration and current environment
        shell_vars = self._get_shell_environment_vars()
        current_env_keys = list(os.environ.keys())
        removed_vars = []
        
        if specific_key:
            # Targeted cleanup for specific key
            removed_count = self._cleanup_specific_key(specific_key, shell_vars, validator)
            if removed_count > 0:
                removed_vars.append(specific_key)
        else:
            # General cleanup for all orphaned API keys
            removed_vars = self._cleanup_orphaned_api_keys(current_env_keys, shell_vars, validator)
        
        # Clean up known orphaned variables
        orphaned_count = self._cleanup_known_orphaned_vars(current_env_keys, shell_vars, validator)
        
        total_removed = len(removed_vars) + orphaned_count
        if total_removed > 0:
            logger.info(f"Cleaned up {total_removed} deleted API key variables: {removed_vars}")
        else:
            logger.info("No deleted API key variables needed cleanup")
        
        return total_removed
    
    def _get_shell_environment_vars(self) -> Dict[str, str]:
        """Get environment variables from shell configuration files"""
        shell = os.environ.get('SHELL', DefaultValues.DEFAULT_SHELL)
        config_files = ShellConfigConstants.ZSH_CONFIG_FILES if 'zsh' in shell else ShellConfigConstants.BASH_CONFIG_FILES
        shell_cmd = ShellConfigConstants.ZSH_COMMAND if 'zsh' in shell else ShellConfigConstants.BASH_COMMAND
        
        logger.info(f"Checking environment variables in {config_files}")
        
        shell_vars = {}
        for config_file in config_files:
            expanded_path = os.path.expanduser(config_file)
            if not os.path.exists(expanded_path):
                continue
                
            try:
                cmd = f'source {config_file} 2>/dev/null && env'
                result = subprocess.run([shell_cmd, '-c', cmd], 
                                      capture_output=True, text=True, timeout=EnvLoadingConstants.SHELL_COMMAND_TIMEOUT)
                
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if '=' in line and not line.startswith('_'):
                            try:
                                key, value = line.split('=', 1)
                                if value.strip():
                                    shell_vars[key] = value.strip()
                            except ValueError:
                                continue
            except Exception as e:
                logger.debug(f"Failed to read from {config_file}: {e}")
                continue
        
        return shell_vars
    
    def _cleanup_specific_key(self, specific_key: str, shell_vars: Dict[str, str], validator) -> int:
        """Clean up a specific API key if it should not exist"""
        logger.info(f"Targeted cleanup for specific key: {specific_key}")
        
        if not validator.is_api_key_variable(specific_key):
            logger.debug(f"{specific_key} is not an API key variable, skipping")
            return 0
        
        if specific_key not in os.environ:
            logger.info(f"{specific_key} not found in current environment")
            return 0
        
        # Check if it should exist in configuration files
        if self._should_key_exist_in_config(specific_key):
            logger.info(f"Keeping {specific_key} as it exists in configuration files")
            return 0
        
        # Remove the key
        del os.environ[specific_key]
        logger.info(f"Force removed {specific_key} from current session (not in any config file)")
        return 1
    
    def _cleanup_orphaned_api_keys(self, current_env_keys: List[str], shell_vars: Dict[str, str], validator) -> List[str]:
        """Clean up all orphaned API keys"""
        logger.info("General cleanup for all orphaned API keys")
        removed_vars = []
        
        for key in current_env_keys:
            if not validator.is_api_key_variable(key):
                continue
            
            # If not in shell config or should not exist in config files
            if key not in shell_vars or not self._should_key_exist_in_config(key):
                if key in os.environ:
                    del os.environ[key]
                    removed_vars.append(key)
                    logger.info(f"Removed {key} from current session (orphaned)")
        
        return removed_vars
    
    def _cleanup_known_orphaned_vars(self, current_env_keys: List[str], shell_vars: Dict[str, str], validator) -> int:
        """Clean up known orphaned variables like VSCODE debug variables"""
        orphaned_patterns = validator.get_orphaned_patterns()
        removed_count = 0
        
        for key in current_env_keys:
            if key in orphaned_patterns and key not in shell_vars:
                if key in os.environ:
                    del os.environ[key]
                    removed_count += 1
                    logger.info(f"Removed orphaned variable {key} from current session")
        
        return removed_count
    
    def _should_key_exist_in_config(self, key: str) -> bool:
        """Check if a key should exist based on configuration files"""
        config_files = ShellConfigConstants.ALL_CONFIG_FILES[:6]  # Use first 6 most common files
        
        for config_file in config_files:
            expanded_path = os.path.expanduser(config_file)
            if os.path.exists(expanded_path):
                try:
                    with open(expanded_path, 'r', encoding=FileConstants.DEFAULT_ENCODING) as f:
                        content = f.read()
                        if f'export {key}=' in content:
                            return True
                except:
                    continue
        
        return False
    
    def _cleanup_windows_deleted_api_keys(self, specific_key: str = None) -> int:
        """Clean up deleted API keys on Windows"""
        # Windows environment variables are handled by registry
        logger.info("Cleaning up Windows session API key variables")
        
        api_key_patterns = ['_API_KEY', '_KEY', '_TOKEN', '_SECRET', '_PASSWORD', 'ENDPOINT']
        removed_vars = []
        
        current_env_keys = list(os.environ.keys())
        for key in current_env_keys:
            if any(pattern in key.upper() for pattern in api_key_patterns):
                # Check if variable exists in registry
                try:
                    result = subprocess.run(['reg', 'query', 'HKEY_CURRENT_USER\\Environment', '/v', key], 
                                          capture_output=True, text=True)
                    if result.returncode != 0:
                        # Variable doesn't exist in registry, remove from session
                        if key in os.environ:
                            del os.environ[key]
                            removed_vars.append(key)
                            logger.info(f"Removed {key} from Windows session (not in registry)")
                except:
                    continue
        
        return len(removed_vars)
    
    def _cleanup_linux_deleted_api_keys(self, specific_key: str = None) -> int:
        """Clean up deleted API keys on Linux"""
        # Similar to macOS implementation
        return self._cleanup_macos_deleted_api_keys(specific_key)
    
    def _cleanup_orphaned_config_entries(self):
        """Clean up orphaned API key entries from all possible configuration files"""
        # List of all possible configuration files
        all_config_files = [
            '~/.zshrc', '~/.zprofile', '~/.zshenv', '~/.zlogin',
            '~/.bash_profile', '~/.bashrc', '~/.profile', '~/.bash_login',
            '~/.env', '~/.environment'
        ]
        
        api_key_patterns = ['_API_KEY', '_KEY', '_TOKEN', '_SECRET', '_PASSWORD', 'ENDPOINT']
        
        for config_file in all_config_files:
            expanded_path = os.path.expanduser(config_file)
            if not os.path.exists(expanded_path):
                continue
            
            try:
                # Find lines with API key patterns
                result = subprocess.run(['grep', '-n'] + [f'{pattern}' for pattern in api_key_patterns] + [expanded_path], 
                                      capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.debug(f"Found potential API keys in {config_file}, checking for cleanup")
                    
                    # Read and filter the file
                    with open(expanded_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    filtered_lines = []
                    removed_count = 0
                    
                    for line in lines:
                        # Check if line contains any API key pattern and looks like an export
                        if (line.strip().startswith('export ') and 
                            any(pattern in line.upper() for pattern in api_key_patterns)):
                            # Extract the variable name
                            try:
                                export_part = line.strip()[7:]  # Remove 'export '
                                var_name = export_part.split('=')[0].strip()
                                
                                # Check if this variable is currently in the environment
                                if var_name not in os.environ:
                                    removed_count += 1
                                    logger.info(f"Removing orphaned API key from {config_file}: {var_name}")
                                    continue
                            except:
                                pass
                        
                        filtered_lines.append(line)
                    
                    if removed_count > 0:
                        # Write back the cleaned file
                        with open(expanded_path, 'w', encoding='utf-8') as f:
                            f.writelines(filtered_lines)
                        logger.info(f"Cleaned {removed_count} orphaned API keys from {config_file}")
                        
            except Exception as e:
                logger.debug(f"Failed to cleanup {config_file}: {e}")
                continue


# Global instance for easy access
env_loader = EnvironmentLoader()


def load_shell_environment() -> int:
    """
    Convenience function to load shell environment variables.
    
    Returns:
        int: Number of environment variables loaded
    """
    return env_loader.load_shell_environment()


def get_all_env_vars_status() -> dict:
    """
    Convenience function to get all environment variables status.
    
    Returns:
        dict: Status of all environment variables (key -> bool)
    """
    return env_loader.get_all_env_vars_status()


def get_api_keys_status() -> dict:
    """
    Convenience function to get all environment variables status.
    (Deprecated: Use get_all_env_vars_status() instead)
    
    Returns:
        dict: Status of all environment variables (key -> bool)
    """
    return env_loader.get_all_env_vars_status()


def is_shell_environment_loaded() -> bool:
    """
    Convenience function to check if shell environment has been loaded.
    
    Returns:
        bool: True if shell environment has been loaded
    """
    return env_loader.is_shell_environment_loaded()


def cleanup_deleted_api_keys(specific_key: str = None) -> int:
    """
    Convenience function to clean up deleted API key environment variables.
    
    Args:
        specific_key: If provided, only clean up this specific key and known orphaned variables
    
    Returns:
        int: Number of environment variables cleaned up
    """
    return env_loader.cleanup_deleted_api_keys(specific_key)
