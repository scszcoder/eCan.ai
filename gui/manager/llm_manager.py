"""
LLM Manager

This module provides unified LLM configuration management interface.
It integrates with the configuration system and provides methods for:
- Managing LLM provider configurations
- Handling API key storage and retrieval
- Validating LLM configurations
- Providing UI-friendly data structures
"""

import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict

from gui.config.llm_config import llm_config, LLMProviderConfig
from utils.logger_helper import logger_helper as logger


@dataclass
class APIKeyInfo:
    """Information about an API key"""
    env_var: str
    provider_names: List[str]
    is_configured: bool
    is_valid: bool = False
    error_message: Optional[str] = None


class LLMManager:
    """LLM configuration manager with environment variable API key management"""

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize LLM manager

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
    

    # API Key Management Methods - Using Environment Variables

    def store_api_key(self, env_var: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Store an API key securely

        Args:
            env_var: Environment variable name
            api_key: API key to store

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Validate format first
            is_valid, error_msg = self.validate_api_key_format(env_var, api_key)
            if not is_valid:
                return False, error_msg

            if not api_key or not api_key.strip():
                return False, "API key cannot be empty"

            # Store as environment variable (for current session)
            os.environ[env_var] = api_key.strip()

            # Persist to system environment variables for future sessions
            self._persist_to_system_env(env_var, api_key.strip())

            logger.info(f"API key stored successfully for {env_var} (current session and system env)")
            return True, None

        except Exception as e:
            error_msg = f"Failed to store API key for {env_var}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def retrieve_api_key(self, env_var: str) -> Optional[str]:
        """
        Retrieve an API key from environment variable

        Args:
            env_var: Environment variable name

        Returns:
            API key if found, None otherwise
        """
        try:
            return os.environ.get(env_var)

        except Exception as e:
            logger.error(f"Failed to retrieve API key for {env_var}: {e}")
            return None

    def has_api_key(self, env_var: str) -> bool:
        """
        Check if an API key exists

        Args:
            env_var: Environment variable name

        Returns:
            True if API key exists, False otherwise
        """
        value = os.environ.get(env_var)
        return bool(value and value.strip())

    def delete_api_key(self, env_var: str) -> bool:
        """
        Delete an API key from environment variable and system configuration

        Args:
            env_var: Environment variable name

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            logger.info(f"🗑️  Starting deletion process for {env_var}")
            
            # Check if variable exists before deletion
            current_value = os.environ.get(env_var)
            if current_value:
                masked_value = self._get_masked_api_key_value(env_var, current_value)
                logger.info(f"🔍 Found {env_var} in current session: {masked_value}")
            else:
                logger.info(f"❌ {env_var} not found in current session")
            
            # Delete from current session
            session_deleted = self._delete_from_current_session(env_var)
            
            # Delete from system environment configuration
            system_deleted = self._delete_from_system_env(env_var)
            
            # Verify deletion and cleanup
            self._verify_and_cleanup_deletion(env_var, session_deleted, system_deleted)
            
            return True  # Always return True to avoid blocking UI

        except Exception as e:
            logger.error(f"❌ Failed to delete API key for {env_var}: {e}")
            logger.debug(f"Deletion error details", exc_info=True)
            return False
    
    def _delete_from_current_session(self, env_var: str) -> bool:
        """Delete API key from current session"""
        if env_var in os.environ:
            del os.environ[env_var]
            logger.info(f"🗑️  API key deleted from current session: {env_var}")
            return True
        return False
    
    def _verify_and_cleanup_deletion(self, env_var: str, session_deleted: bool, system_deleted: bool) -> None:
        """Verify deletion and perform cleanup"""
        # Verify deletion
        after_value = os.environ.get(env_var)
        if after_value:
            masked_value = self._get_masked_api_key_value(env_var, after_value)
            logger.warning(f"⚠️  {env_var} still exists in environment after deletion: {masked_value}")
        else:
            logger.info(f"✅ {env_var} successfully removed from environment")
        
        # Log completion status
        if session_deleted or system_deleted:
            logger.info(f"🎯 API key deletion completed for {env_var} (session: {session_deleted}, system: {system_deleted})")
        else:
            logger.warning(f"⚠️  No deletion performed for {env_var} (not found in session or system)")
    
    def _get_masked_api_key_value(self, env_var: str, value: str) -> str:
        """Get masked value for logging using centralized validator"""
        from gui.utils.api_key_validator import get_api_key_validator
        validator = get_api_key_validator()
        return validator.mask_api_key(value)

    def validate_api_key_format(self, env_var: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Validate API key format using centralized validator

        Args:
            env_var: Environment variable name
            api_key: API key to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        from gui.utils.api_key_validator import get_api_key_validator
        validator = get_api_key_validator()
        return validator.validate_api_key(env_var, api_key)


    def get_api_key_info(self) -> List[APIKeyInfo]:
        """
        Get information about all API keys

        Returns:
            List of APIKeyInfo objects
        """
        api_key_info = []

        # Get all required environment variables from LLM config
        env_var_to_providers = {}
        for provider_name, provider in llm_config.get_all_providers().items():
            for env_var in provider.api_key_env_vars:
                if env_var not in env_var_to_providers:
                    env_var_to_providers[env_var] = []
                env_var_to_providers[env_var].append(provider.display_name)

        for env_var, provider_names in env_var_to_providers.items():
            is_configured = self.has_api_key(env_var)

            api_key_info.append(APIKeyInfo(
                env_var=env_var,
                provider_names=provider_names,
                is_configured=is_configured,
                is_valid=True if is_configured else False  # Could add actual validation here
            ))

        return api_key_info

    def get_api_key_info_for_ui(self) -> List[Dict[str, Any]]:
        """Get information about all API keys formatted for UI display"""
        api_key_info = self.get_api_key_info()

        result = []
        for info in api_key_info:
            result.append({
                "env_var": info.env_var,
                "provider_names": info.provider_names,
                "is_configured": info.is_configured,
                "display_name": self._get_env_var_display_name(info.env_var),
                "masked_value": self._get_masked_api_key(info.env_var) if info.is_configured else None
            })

        return result

    def _check_provider_api_keys_configured(self, provider_config: LLMProviderConfig) -> bool:
        """Check if all required API keys for a provider are configured"""
        if provider_config.is_local:
            return True  # Local providers don't need API keys

        for env_var in provider_config.api_key_env_vars:
            if not self.has_api_key(env_var):
                return False
        return True

    def _serialize_models(self, models: List) -> List[Dict[str, Any]]:
        """Serialize model configurations for JSON response"""
        serialized_models = []
        for model in models:
            model_dict = asdict(model)
            # Convert enum values to strings if they exist
            if 'provider' in model_dict and hasattr(model_dict['provider'], 'value'):
                model_dict['provider'] = model_dict['provider'].value
            serialized_models.append(model_dict)
        return serialized_models

    # Provider Management
    def get_all_providers(self) -> List[Dict[str, Any]]:
        """Get all LLM providers with user preferences
        
        Merges data from:
        - llm_providers.json (provider definitions, supported models) - read-only
        - settings.json (default_llm, default_llm_model) - writable even in PyInstaller
        
        Only the current default_llm provider gets preferred_model from settings.json.
        """
        providers = []
        
        # Get current default provider and its model from settings.json
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        current_default_llm = ""
        current_default_model = ""
        if main_window:
            general_settings = main_window.config_manager.general_settings
            current_default_llm = general_settings.default_llm
            current_default_model = general_settings.default_llm_model
        
        for provider_name, provider_config in llm_config.get_all_providers().items():
            # Only set preferred_model if this is the current default provider
            is_default_provider = (provider_name == current_default_llm)
            preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
            is_preferred = is_default_provider
            custom_params = {}

            # Check if API keys are configured using environment variables
            api_key_configured = self._check_provider_api_keys_configured(provider_config)
            
            # Validate configuration
            validation = llm_config.validate_provider_config(provider_name)
            
            provider_data = {
                "name": provider_config.name,
                "display_name": provider_config.display_name,
                "class_name": provider_config.class_name,
                "provider": provider_config.provider.value,  # Convert enum to string value
                "description": provider_config.description,
                "documentation_url": provider_config.documentation_url,
                "is_local": provider_config.is_local,
                "base_url": provider_config.base_url,
                "default_model": provider_config.default_model,
                "api_key_env_vars": provider_config.api_key_env_vars,
                "supported_models": self._serialize_models(provider_config.supported_models),

                # User preferences (only for current default provider)
                "is_preferred": is_preferred,
                "preferred_model": preferred_model,
                "custom_parameters": custom_params,
                "api_key_configured": api_key_configured,

                # Validation status
                "is_valid": validation["valid"],
                "validation_error": validation.get("error"),
                "missing_env_vars": validation.get("missing_env_vars", [])
            }
            
            providers.append(provider_data)
        
        return providers
    
    def get_provider(self, provider_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific provider with user preferences"""
        providers = self.get_all_providers()
        for provider in providers:
            if provider["name"] == provider_name:
                return provider
        return None
    
    
    def get_preferred_providers(self) -> List[str]:
        """Get list of preferred provider names"""
        return []  # No preferences stored
    
    def get_provider_summary(self) -> Dict[str, Any]:
        """Get summary of provider status"""
        summary = llm_config.get_provider_summary()
        
        # Add user preference information
        preferred_count = len(self.get_preferred_providers())
        configured_with_keys = sum(1 for p in self.get_all_providers() if p["api_key_configured"])
        
        summary.update({
            "preferred_providers": preferred_count,
            "providers_with_api_keys": configured_with_keys
        })
        
        return summary
    
    # Model Management
    def get_models_for_provider(self, provider_name: str) -> List[Dict[str, Any]]:
        """Get models for a specific provider"""
        provider_config = llm_config.get_provider(provider_name)
        if not provider_config:
            return []
        
        models = []
        preferred_model = provider_config.default_model
        
        for model in provider_config.supported_models:
            model_data = asdict(model)
            # Convert enum values to strings if they exist
            if 'provider' in model_data and hasattr(model_data['provider'], 'value'):
                model_data['provider'] = model_data['provider'].value
            model_data["is_preferred"] = (model.name == preferred_model)
            models.append(model_data)
        
        return models

    def set_provider_default_model(self, provider_name: str, model_name: str) -> Tuple[bool, Optional[str]]:
        """Update the default model for the default LLM provider
        
        Note: Only saves if this is the current default provider.
        Saves to user's settings.json (writable in PyInstaller), 
        NOT to llm_providers.json (read-only in PyInstaller).
        """
        provider_config = llm_config.get_provider(provider_name)
        if not provider_config:
            return False, f"Provider {provider_name} not found"

        available_models = llm_config.get_models_for_provider(provider_name)
        valid_model_names = {model.name for model in available_models}

        if available_models and model_name not in valid_model_names:
            return False, f"Model {model_name} is not supported by provider {provider_name}"

        # Save to user's settings.json (writable even in PyInstaller)
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return False, "Main window not available"
        
        general_settings = main_window.config_manager.general_settings
        
        # Check if this is the current default provider
        current_default_llm = general_settings.default_llm
        if current_default_llm == provider_name:
            # Update default_llm_model for the current default provider
            general_settings.default_llm_model = model_name
            
            if not general_settings.save():
                return False, "Failed to save model selection to settings"
            
            logger.info(f"Updated default_llm_model to {model_name} for current default provider {provider_name}")
        else:
            # Not the default provider, just return success without saving
            # The frontend may want to change models for non-default providers for preview
            logger.info(f"Model {model_name} selected for {provider_name} (not saved since it's not the default provider)")

        return True, None
    
    def get_model(self, provider_name: str, model_name: str) -> Optional[Dict[str, Any]]:
        """Get a specific model configuration"""
        models = self.get_models_for_provider(provider_name)
        for model in models:
            if model["name"] == model_name:
                return model
        return None
    
    # Configuration Validation
    def validate_all_configurations(self) -> Dict[str, Any]:
        """Validate all LLM configurations"""
        results = {
            "valid_providers": [],
            "invalid_providers": [],
            "missing_api_keys": [],
            "total_providers": 0,
            "valid_count": 0
        }
        
        for provider_name in llm_config.get_all_providers().keys():
            validation = llm_config.validate_provider_config(provider_name)
            results["total_providers"] += 1
            
            if validation["valid"]:
                results["valid_providers"].append(provider_name)
                results["valid_count"] += 1
            else:
                results["invalid_providers"].append({
                    "name": provider_name,
                    "error": validation.get("error"),
                    "missing_env_vars": validation.get("missing_env_vars", [])
                })
                
                if validation.get("missing_env_vars"):
                    results["missing_api_keys"].extend(validation["missing_env_vars"])
        
        # Remove duplicates from missing API keys
        results["missing_api_keys"] = list(set(results["missing_api_keys"]))
        
        return results
    
    # Utility Methods
    def get_env_var_providers_map(self) -> Dict[str, List[str]]:
        """Get mapping of environment variables to providers that use them"""
        env_var_map = {}
        
        for provider_name, provider_config in llm_config.get_all_providers().items():
            for env_var in provider_config.api_key_env_vars:
                if env_var not in env_var_map:
                    env_var_map[env_var] = []
                env_var_map[env_var].append(provider_name)
        
        return env_var_map
    
    def get_ui_friendly_data(self) -> Dict[str, Any]:
        """Get data structure optimized for UI display"""
        return {
            "providers": self.get_all_providers(),
            "summary": self.get_provider_summary(),
            "validation": self.validate_all_configurations(),
            "env_var_map": self.get_env_var_providers_map(),
            "api_keys": self.get_api_key_info_for_ui()
        }


    def _persist_to_system_env(self, env_var: str, api_key: str):
        """Persist API key to system environment variables"""
        try:
            import platform
            import subprocess
            
            system = platform.system()
            masked_key = api_key[:8] + "..." + api_key[-8:] if len(api_key) > 16 else api_key[:4] + "..."
            
            if system == "Darwin":  # macOS
                self._persist_macos_env(env_var, api_key)
                logger.info(f"API key persisted to macOS environment: {env_var}={masked_key}")
                
            elif system == "Windows":
                self._persist_windows_env(env_var, api_key)
                logger.info(f"API key persisted to Windows environment: {env_var}={masked_key}")
                
            else:  # Linux
                self._persist_linux_env(env_var, api_key)
                logger.info(f"API key persisted to Linux environment: {env_var}={masked_key}")
                
        except Exception as e:
            logger.error(f"Failed to persist to system environment: {e}")
            # Fallback: provide manual instructions
            self._provide_manual_instructions(env_var, api_key)
    
    def _persist_macos_env(self, env_var: str, api_key: str):
        """Persist environment variable on macOS"""
        import os
        import subprocess
        
        # Try to determine the user's shell
        shell = os.environ.get('SHELL', '/bin/zsh')
        
        if 'zsh' in shell:
            config_file = os.path.expanduser('~/.zshrc')
        else:
            config_file = os.path.expanduser('~/.bash_profile')
        
        # Read existing content
        existing_content = ""
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_content = f.read()
        
        # Check if the environment variable already exists
        export_line = f'export {env_var}='
        lines = existing_content.split('\n')
        updated = False
        
        # Update existing line or add new one
        for i, line in enumerate(lines):
            if line.strip().startswith(export_line):
                lines[i] = f'export {env_var}="{api_key}"'
                updated = True
                break
        
        if not updated:
            lines.append(f'export {env_var}="{api_key}"')
        
        # Write back to file
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Environment variable added to {config_file}")

    def _persist_windows_env(self, env_var: str, api_key: str):
        """Persist environment variable on Windows"""
        from utils.subprocess_helper import run_no_window
        
        try:
            # Use setx command to set user environment variable
            run_no_window(['setx', env_var, api_key], check=True, capture_output=True)
            logger.info(f"Environment variable set using setx command")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to set environment variable using setx: {e}")
            raise

    def _persist_linux_env(self, env_var: str, api_key: str):
        """Persist environment variable on Linux"""
        import os
        
        # Try ~/.bashrc first, then ~/.profile
        config_files = [
            os.path.expanduser('~/.bashrc'),
            os.path.expanduser('~/.profile')
        ]
        
        for config_file in config_files:
            try:
                # Read existing content
                existing_content = ""
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        existing_content = f.read()
                
                # Check if the environment variable already exists
                export_line = f'export {env_var}='
                lines = existing_content.split('\n')
                updated = False
                
                # Update existing line or add new one
                for i, line in enumerate(lines):
                    if line.strip().startswith(export_line):
                        lines[i] = f'export {env_var}="{api_key}"'
                        updated = True
                        break
                
                if not updated:
                    lines.append(f'export {env_var}="{api_key}"')
                
                # Write back to file
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
                
                logger.info(f"Environment variable added to {config_file}")
                break  # Success, no need to try other files
                
            except Exception as e:
                logger.debug(f"Failed to update {config_file}: {e}")
                continue

    def _provide_manual_instructions(self, env_var: str, api_key: str):
        """Provide manual instructions as fallback"""
        import platform
        system = platform.system()
        masked_key = api_key[:8] + "..." + api_key[-8:] if len(api_key) > 16 else api_key[:4] + "..."
        
        logger.warning(f"""
=== Manual Setup Required ===
Automatic persistence failed. Please set manually:
{env_var}={masked_key}

For {system}, please refer to system documentation for setting environment variables.
===============================
""")
    
    
    def update_default_llm(self, provider_name: str) -> bool:
        """Update default LLM setting in configuration"""
        try:
            # Update the general settings
            self.config_manager.general_settings.default_llm = provider_name
            self.config_manager.general_settings.save()
            
            logger.info(f"Updated default_llm setting to: {provider_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating default_llm setting: {e}")
            return False
    

    def _get_env_var_display_name(self, env_var: str) -> str:
        """Get user-friendly display name for environment variable"""
        display_names = {
            "OPENAI_API_KEY": "OpenAI API Key",
            "ANTHROPIC_API_KEY": "Anthropic API Key",
            "DEEPSEEK_API_KEY": "DeepSeek API Key",
            "DASHSCOPE_API_KEY": "DashScope API Key",
            "GEMINI_API_KEY": "Gemini API Key",
            "AZURE_ENDPOINT": "Azure Endpoint",
            "AZURE_OPENAI_API_KEY": "Azure OpenAI API Key",
            "AWS_ACCESS_KEY_ID": "AWS Access Key ID",
            "AWS_SECRET_ACCESS_KEY": "AWS Secret Access Key"
        }
        return display_names.get(env_var, env_var.replace("_", " ").title())

    def _get_masked_api_key(self, env_var: str) -> Optional[str]:
        """Get masked API key for display"""
        api_key = self.retrieve_api_key(env_var)
        if not api_key:
            return None

        # Show first 8 and last 4 characters, mask the middle
        if len(api_key) > 12:
            return api_key[:8] + "*" * (len(api_key) - 12) + api_key[-4:]
        else:
            return api_key[:2] + "*" * (len(api_key) - 2)

    def _delete_from_system_env(self, env_var: str) -> bool:
        """Delete environment variable from system configuration files
        
        Returns:
            bool: True if deletion was attempted, False if failed
        """
        try:
            import platform
            import subprocess
            import os
            
            system = platform.system()
            deleted = False
            
            if system == "Darwin":  # macOS
                deleted = self._delete_macos_env(env_var)
                if deleted:
                    logger.info(f"Environment variable deleted from macOS config: {env_var}")
                else:
                    logger.info(f"Environment variable not found in macOS config: {env_var}")
                
            elif system == "Windows":
                deleted = self._delete_windows_env(env_var)
                if deleted:
                    logger.info(f"Environment variable deleted from Windows config: {env_var}")
                else:
                    logger.info(f"Environment variable not found in Windows config: {env_var}")
                
            else:  # Linux
                deleted = self._delete_linux_env(env_var)
                if deleted:
                    logger.info(f"Environment variable deleted from Linux config: {env_var}")
                else:
                    logger.info(f"Environment variable not found in Linux config: {env_var}")
            
            # Force cleanup deleted API keys using unified env_utils method
            # This ensures we clean up any inherited or cached environment variables
            from utils.env import cleanup_deleted_api_keys
            cleaned_count = cleanup_deleted_api_keys(env_var)  # Pass the specific key being deleted
            logger.info(f"Environment cleanup completed, removed {cleaned_count} variables")
            
            return deleted
                
        except Exception as e:
            logger.error(f"Failed to delete from system environment: {e}")
            return False


    def _delete_macos_env(self, env_var: str) -> bool:
        """Delete environment variable from macOS shell configuration
        
        Returns:
            bool: True if variable was found and removed, False otherwise
        """
        import os
        
        # Try to determine the user's shell
        shell = os.environ.get('SHELL', '/bin/zsh')
        
        if 'zsh' in shell:
            config_file = os.path.expanduser('~/.zshrc')
        else:
            config_file = os.path.expanduser('~/.bash_profile')
        
        if not os.path.exists(config_file):
            logger.debug(f"Config file {config_file} does not exist")
            return False
        
        # Read existing content
        with open(config_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Filter out lines containing the environment variable
        export_pattern = f'export {env_var}='
        filtered_lines = []
        removed_count = 0
        
        for line in lines:
            if line.strip().startswith(export_pattern):
                removed_count += 1
                logger.debug(f"Removing line from {config_file}: {line.strip()}")
            else:
                filtered_lines.append(line)
        
        if removed_count > 0:
            # Write back to file
            with open(config_file, 'w', encoding='utf-8') as f:
                f.writelines(filtered_lines)
            logger.info(f"Removed {removed_count} lines for {env_var} from {config_file}")
            return True
        else:
            logger.debug(f"No lines found for {env_var} in {config_file}")
            return False

    def _delete_windows_env(self, env_var: str) -> bool:
        """Delete environment variable from Windows registry
        
        Returns:
            bool: True if variable was found and removed, False otherwise
        """
        from utils.subprocess_helper import run_no_window
        
        try:
            # Use reg command to delete user environment variable
            result = run_no_window(['reg', 'delete', 'HKEY_CURRENT_USER\\Environment', '/v', env_var, '/f'], 
                         check=True, capture_output=True, text=True)
            logger.info(f"Environment variable deleted from Windows registry: {env_var}")
            return True
        except subprocess.CalledProcessError as e:
            logger.debug(f"Failed to delete from Windows registry (may not exist): {env_var}")
            return False

    def _delete_linux_env(self, env_var: str) -> bool:
        """Delete environment variable from Linux shell configuration
        
        Returns:
            bool: True if variable was found and removed from any file, False otherwise
        """
        import os
        
        # Try multiple shell configurations
        config_files = [
            os.path.expanduser('~/.bashrc'),
            os.path.expanduser('~/.profile'),
            os.path.expanduser('~/.bash_profile'),
            os.path.expanduser('~/.zshrc')
        ]
        
        export_pattern = f'export {env_var}='
        total_removed = 0
        
        for config_file in config_files:
            if not os.path.exists(config_file):
                continue
                
            try:
                # Read existing content
                with open(config_file, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                # Filter out lines containing the environment variable
                filtered_lines = []
                removed_count = 0
                
                for line in lines:
                    if line.strip().startswith(export_pattern):
                        removed_count += 1
                        logger.debug(f"Removing line from {config_file}: {line.strip()}")
                    else:
                        filtered_lines.append(line)
                
                if removed_count > 0:
                    # Write back to file
                    with open(config_file, 'w', encoding='utf-8') as f:
                        f.writelines(filtered_lines)
                    logger.info(f"Removed {removed_count} lines for {env_var} from {config_file}")
                    total_removed += removed_count
                    
            except Exception as e:
                logger.debug(f"Failed to process {config_file}: {e}")
                continue
        
        return total_removed > 0

    # Onboarding and Configuration Check
    
    def check_provider_configured(self) -> Tuple[bool, Optional[str]]:
        """
        Check if LLM provider is configured and a default is selected
        
        Returns:
            tuple: (is_configured: bool, configured_provider_name: Optional[str])
            - is_configured: True if default LLM provider is configured, False otherwise
            - configured_provider_name: Name of configured default provider, or None
        """
        try:
            # Get default LLM from settings
            default_llm = self.config_manager.general_settings.default_llm
            
            if default_llm:
                # Check if default LLM provider is configured
                provider = self.get_provider(default_llm)
                if provider and provider.get('api_key_configured', False):
                    # Default LLM is configured
                    return True, default_llm
                else:
                    # Default LLM is set but not configured (missing API key)
                    logger.debug(f"[LLMManager] Default LLM '{default_llm}' is set but not configured")
                    return False, None
            
            # If no default is set, check if any provider is configured
            # This helps us determine if we should prompt user to set a default
            all_providers = self.get_all_providers()
            has_configured_provider = False
            for provider in all_providers:
                if provider.get('api_key_configured', False):
                    has_configured_provider = True
                    break
            
            if has_configured_provider:
                # Found configured provider but no default is set
                logger.debug("[LLMManager] Found configured provider but no default is set")
                return False, None
            
            # No provider is configured at all
            logger.debug("[LLMManager] No LLM provider is configured")
            return False, None
            
        except Exception as e:
            logger.error(f"[LLMManager] Error checking LLM provider configuration: {e}")
            return False, None

    async def check_and_show_onboarding(self, delay_seconds: float = 2.0):
        """
        Check LLM provider configuration and show onboarding guide if needed
        This runs asynchronously and should be called after initialization is complete
        
        Args:
            delay_seconds: Delay before checking to ensure web GUI is ready
        """
        try:
            import asyncio
            # Wait a bit to ensure web GUI is ready
            await asyncio.sleep(delay_seconds)
            
            is_configured, configured_provider = self.check_provider_configured()
            
            if not is_configured:
                logger.info("[LLMManager] 📋 LLM provider not configured, showing onboarding guide")
                await self.show_onboarding_guide()
            else:
                logger.debug(f"[LLMManager] ✅ LLM provider configured: {configured_provider}")
                
        except Exception as e:
            logger.error(f"[LLMManager] Error in LLM provider onboarding check: {e}")

    async def show_onboarding_guide(self):
        """
        Show onboarding guide for LLM provider configuration
        Sends instruction to frontend to display onboarding guide.
        Frontend determines UI, text, and behavior based on instruction type.
        """
        try:
            from app_context import AppContext
            web_gui = AppContext.get_web_gui()
            if not web_gui:
                logger.warning("[LLMManager] Web GUI not available for onboarding guide")
                return
            
            ipc_api = web_gui.get_ipc_api()
            if not ipc_api:
                logger.warning("[LLMManager] IPC API not available for onboarding guide")
                return
            
            # Push onboarding instruction to frontend (one-way push, no response expected)
            # Frontend will determine how to display based on onboarding_type
            ipc_api.push_onboarding_message(
                onboarding_type='llm_provider_config',
                context={
                    'suggestedAction': {
                        'type': 'navigate',
                        'path': '/settings',
                        'params': {'tab': 'llm'}
                    }
                }
            )
            
            logger.info("[LLMManager] Onboarding instruction pushed to frontend")
            
        except Exception as e:
            logger.error(f"[LLMManager] Error showing LLM provider onboarding guide: {e}")


