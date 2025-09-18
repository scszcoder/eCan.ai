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
        self.settings_file = os.path.join(config_manager.user_data_path, 'llm_settings.json')
        self._user_settings = self._load_user_settings()
    
    def _load_user_settings(self) -> dict:
        """Load user LLM settings"""
        default_settings = {
            "preferred_providers": {},  # provider_name -> bool
            "model_preferences": {},    # provider_name -> model_name
            "custom_parameters": {},    # provider_name -> {param: value}
            "api_key_configured": {},   # provider_name -> bool (for UI display)
            "last_updated": None
        }
        
        return self.config_manager.load_json(self.settings_file, default_settings)
    
    def save_user_settings(self) -> bool:
        """Save user LLM settings"""
        import datetime
        self._user_settings["last_updated"] = datetime.datetime.now().isoformat()
        return self.config_manager.save_json(self.settings_file, self._user_settings)

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

            # Store as environment variable
            os.environ[env_var] = api_key.strip()

            logger.info(f"API key stored successfully for {env_var}")
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
        return self.retrieve_api_key(env_var) is not None

    def delete_api_key(self, env_var: str) -> bool:
        """
        Delete an API key from environment variable

        Args:
            env_var: Environment variable name

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            if env_var in os.environ:
                del os.environ[env_var]
                logger.info(f"API key deleted for {env_var}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete API key for {env_var}: {e}")
            return False

    def validate_api_key_format(self, env_var: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Validate API key format for specific providers

        Args:
            env_var: Environment variable name
            api_key: API key to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not api_key or not api_key.strip():
            return False, "API key cannot be empty"

        api_key = api_key.strip()

        # Basic validation based on environment variable patterns
        if env_var == "OPENAI_API_KEY":
            if not api_key.startswith("sk-"):
                return False, "OpenAI API key should start with 'sk-'"
            if len(api_key) < 20:
                return False, "OpenAI API key is too short"

        elif env_var == "ANTHROPIC_API_KEY":
            if not api_key.startswith("sk-ant-"):
                return False, "Anthropic API key should start with 'sk-ant-'"
            if len(api_key) < 20:
                return False, "Anthropic API key is too short"

        elif env_var == "GEMINI_API_KEY":
            if len(api_key) < 20:
                return False, "Gemini API key is too short"

        elif env_var == "DEEPSEEK_API_KEY":
            if not api_key.startswith("sk-"):
                return False, "DeepSeek API key should start with 'sk-'"
            if len(api_key) < 20:
                return False, "DeepSeek API key is too short"

        elif env_var == "DASHSCOPE_API_KEY":
            if len(api_key) < 20:
                return False, "DashScope API key is too short"

        elif env_var in ["AZURE_OPENAI_API_KEY"]:
            if len(api_key) < 20:
                return False, "Azure OpenAI API key is too short"

        elif env_var == "AZURE_ENDPOINT":
            if not api_key.startswith("https://"):
                return False, "Azure endpoint should start with 'https://'"
            if ".openai.azure.com" not in api_key:
                return False, "Azure endpoint should contain '.openai.azure.com'"

        elif env_var == "AWS_ACCESS_KEY_ID":
            if len(api_key) < 16:
                return False, "AWS Access Key ID is too short"
            if not api_key.startswith("AKIA"):
                return False, "AWS Access Key ID should start with 'AKIA'"

        elif env_var == "AWS_SECRET_ACCESS_KEY":
            if len(api_key) < 40:
                return False, "AWS Secret Access Key is too short"

        return True, None

    def export_api_keys_masked(self) -> Dict[str, Optional[str]]:
        """
        Export all API keys with masking for display

        Returns:
            Dictionary of env_var -> masked_value
        """
        masked_keys = {}

        # Get all required environment variables from LLM config
        all_env_vars = set()
        for provider in llm_config.get_all_providers().values():
            all_env_vars.update(provider.api_key_env_vars)

        for env_var in all_env_vars:
            api_key = self.retrieve_api_key(env_var)
            if api_key:
                # Mask the API key (show first 4 and last 4 characters)
                if len(api_key) > 8:
                    masked_keys[env_var] = f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"
                else:
                    masked_keys[env_var] = "*" * len(api_key)
            else:
                masked_keys[env_var] = None

        return masked_keys

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
        """Get all LLM providers with user preferences"""
        providers = []
        
        for provider_name, provider_config in llm_config.get_all_providers().items():
            # Get user preferences
            is_preferred = self._user_settings.get("preferred_providers", {}).get(provider_name, False)
            preferred_model = self._user_settings.get("model_preferences", {}).get(provider_name)
            custom_params = self._user_settings.get("custom_parameters", {}).get(provider_name, {})

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

                # User preferences
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
    
    def set_provider_preference(self, provider_name: str, is_preferred: bool) -> bool:
        """Set provider preference"""
        try:
            if "preferred_providers" not in self._user_settings:
                self._user_settings["preferred_providers"] = {}
            
            self._user_settings["preferred_providers"][provider_name] = is_preferred
            return self.save_user_settings()
        except Exception as e:
            logger.error(f"Error setting provider preference: {e}")
            return False
    
    def set_model_preference(self, provider_name: str, model_name: str) -> bool:
        """Set preferred model for a provider"""
        try:
            if "model_preferences" not in self._user_settings:
                self._user_settings["model_preferences"] = {}
            
            self._user_settings["model_preferences"][provider_name] = model_name
            return self.save_user_settings()
        except Exception as e:
            logger.error(f"Error setting model preference: {e}")
            return False
    
    def set_custom_parameters(self, provider_name: str, parameters: Dict[str, Any]) -> bool:
        """Set custom parameters for a provider"""
        try:
            if "custom_parameters" not in self._user_settings:
                self._user_settings["custom_parameters"] = {}
            
            self._user_settings["custom_parameters"][provider_name] = parameters
            return self.save_user_settings()
        except Exception as e:
            logger.error(f"Error setting custom parameters: {e}")
            return False
    
    def get_preferred_providers(self) -> List[str]:
        """Get list of preferred provider names"""
        preferred = []
        for provider_name, is_preferred in self._user_settings.get("preferred_providers", {}).items():
            if is_preferred:
                preferred.append(provider_name)
        return preferred
    
    def get_provider_summary(self) -> Dict[str, Any]:
        """Get summary of provider status"""
        summary = llm_config.get_provider_summary()
        
        # Add user preference information
        preferred_count = len(self.get_preferred_providers())
        configured_with_keys = sum(1 for p in self.get_all_providers() if p["api_key_configured"])
        
        summary.update({
            "preferred_providers": preferred_count,
            "providers_with_api_keys": configured_with_keys,
            "user_settings_file": self.settings_file
        })
        
        return summary
    
    # Model Management
    def get_models_for_provider(self, provider_name: str) -> List[Dict[str, Any]]:
        """Get models for a specific provider"""
        provider_config = llm_config.get_provider(provider_name)
        if not provider_config:
            return []
        
        models = []
        preferred_model = self._user_settings.get("model_preferences", {}).get(provider_name)
        
        for model in provider_config.supported_models:
            model_data = asdict(model)
            # Convert enum values to strings if they exist
            if 'provider' in model_data and hasattr(model_data['provider'], 'value'):
                model_data['provider'] = model_data['provider'].value
            model_data["is_preferred"] = (model.name == preferred_model)
            models.append(model_data)
        
        return models
    
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

    def bulk_store_api_keys(self, api_keys: Dict[str, str]) -> Dict[str, Tuple[bool, Optional[str]]]:
        """
        Store multiple API keys at once

        Args:
            api_keys: Dict mapping env_var to api_key

        Returns:
            Dict mapping env_var to (success, error_message)
        """
        results = {}
        for env_var, api_key in api_keys.items():
            results[env_var] = self.store_api_key(env_var, api_key)
        return results

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


