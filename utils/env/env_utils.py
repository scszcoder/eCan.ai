"""
Environment Variables Utilities

This module provides utilities for loading and managing environment variables
from shell configuration files across different platforms.
"""

import os
import platform
import subprocess
import sys
from typing import Optional
from utils.logger_helper import logger_helper as logger
from .constants import (
    EnvLoadingConstants
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
                                if not value.strip():
                                    continue
                                
                                existing_value = os.environ.get(key)
                                if existing_value:
                                    # Override with shell value
                                    os.environ[key] = value.strip()
                                    loaded_count += 1
                                    masked_value = self._mask_sensitive_value(key, value.strip())
                                    logger.trace(f"Reloaded from {config_file} (overriding inherited): {key}={masked_value}")
                                else:
                                    # Load if not exists
                                    os.environ[key] = value.strip()
                                    loaded_count += 1
                                    masked_value = self._mask_sensitive_value(key, value.strip())
                                    logger.info(f"Loaded from {config_file}: {key}={masked_value}")
                            except ValueError:
                                continue
            except Exception as e:
                logger.debug(f"Failed to load from {config_file}: {e}")
                continue
        
        return loaded_count
    
    def _load_windows_env_vars(self) -> int:
        """Load environment variables on Windows without spawning console windows."""
        loaded_count = 0

        try:
            import winreg  # type: ignore
        except ImportError as exc:
            logger.warning(f"winreg unavailable, skipping registry environment load: {exc}")
            return 0

        def _read_registry_values(root, subkey):
            nonlocal loaded_count
            try:
                with winreg.OpenKey(root, subkey) as key:
                    index = 0
                    while True:
                        try:
                            name, value, value_type = winreg.EnumValue(key, index)
                        except OSError:
                            break
                        index += 1

                        if not name:
                            continue

                        expanded_value = self._expand_windows_registry_value(value, value_type, winreg)
                        if not expanded_value:
                            continue

                        # For API key variables, always reload from registry (override inherited values)
                        # This ensures registry is the single source of truth
                        is_api_key = any(pattern in name for pattern in ['_API_KEY', '_KEY', '_TOKEN', '_SECRET'])
                        existing_value = os.environ.get(name)
                        
                        if is_api_key and existing_value:
                            # Override inherited API key with registry value
                            os.environ[name] = expanded_value
                            loaded_count += 1
                            masked_value = self._mask_sensitive_value(name, expanded_value)
                            logger.info(f"Reloaded from Windows registry (overriding inherited) ({subkey}): {name}={masked_value}")
                        elif not existing_value:
                            # Load if not exists
                            os.environ[name] = expanded_value
                            loaded_count += 1
                            masked_value = self._mask_sensitive_value(name, expanded_value)
                            logger.info(f"Loaded from Windows registry ({subkey}): {name}={masked_value}")
            except FileNotFoundError:
                logger.debug(f"Registry path not found: {subkey}")
            except OSError as e:
                logger.debug(f"Failed to read registry path {subkey}: {e}")

        # User-specific environment variables
        _read_registry_values(winreg.HKEY_CURRENT_USER, r"Environment")
        # Machine-wide environment variables
        _read_registry_values(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")

        return loaded_count

    @staticmethod
    def _expand_windows_registry_value(value: object, value_type: int, winreg_module) -> Optional[str]:
        """Convert registry value into a usable string."""
        if value is None:
            return None

        if value_type in (winreg_module.REG_SZ, winreg_module.REG_EXPAND_SZ):
            string_value = str(value)
            if value_type == winreg_module.REG_EXPAND_SZ:
                try:
                    string_value = winreg_module.ExpandEnvironmentStrings(string_value)
                except Exception:
                    string_value = os.path.expandvars(string_value)
            return string_value.strip() or None

        if value_type == winreg_module.REG_MULTI_SZ:
            try:
                string_value = os.pathsep.join(part for part in value if part)
            except TypeError:
                string_value = str(value)
            return string_value.strip() or None

        return None
    
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
