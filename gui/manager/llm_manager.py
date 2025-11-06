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
        self._onboarding_shown = False  # Track if onboarding has been shown this session
    
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

            value = api_key.strip()

            # Persist to secure store (Keychain on macOS, Credential Manager on Windows, etc.)
            from utils.env.secure_store import secure_store
            ok = secure_store.set(env_var, value)
            if not ok:
                return False, "Failed to persist API key to secure store"

            logger.info(f"API key stored for {env_var} in secure store")
            return True, None

        except Exception as e:
            error_msg = f"Failed to store API key for {env_var}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def retrieve_api_key(self, env_var: str) -> Optional[str]:
        """
        Retrieve an API key from secure store

        Args:
            env_var: Environment variable name

        Returns:
            API key if found, None otherwise
        """
        try:
            from utils.env.secure_store import secure_store
            value = secure_store.get(env_var)
            if value and value.strip():
                return value
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve API key for {env_var}: {e}")
            return None

    def has_api_key(self, env_var: str) -> bool:
        """
        Check if an API key exists in secure store

        Args:
            env_var: Environment variable name

        Returns:
            True if API key exists, False otherwise
        """
        try:
            from utils.env.secure_store import secure_store
            value = secure_store.get(env_var)
            return bool(value and value.strip())
        except Exception:
            return False

    def delete_api_key(self, env_var: str) -> bool:
        """
        Delete an API key from environment variable and system configuration

        Args:
            env_var: Environment variable name

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            logger.debug(f"Starting deletion process for {env_var}")

            current_value = os.environ.get(env_var)
            if current_value:
                masked_value = self._get_masked_api_key_value(env_var, current_value)
                logger.debug(f"Current session value for {env_var}: {masked_value}")
            else:
                logger.debug(f"Environment variable {env_var} not present in current session")

            # Delete from secure store
            from utils.env.secure_store import secure_store
            store_deleted = False
            try:
                store_deleted = secure_store.delete(env_var)
            except Exception as e:
                logger.warning(f"Failed to delete from secure store: {e}")
                store_deleted = False

            # Delete from current session
            session_deleted = self._delete_from_current_session(env_var)
            
            # Verify deletion
            if session_deleted or store_deleted:
                logger.info(f"Deletion completed for {env_var}: session={session_deleted}, store={store_deleted}")
                return True
            else:
                # If variable doesn't exist in session or config files, consider it already deleted
                logger.debug(f"Environment variable {env_var} not found in session or persistent configuration")
                return True  # Still return True as it's effectively "deleted"

        except Exception as e:
            logger.error(f"Failed to delete API key for {env_var}: {e}")
            logger.debug("Deletion error details", exc_info=True)
            return False
    
    def _delete_from_current_session(self, env_var: str) -> bool:
        """Delete API key from current session"""
        if env_var in os.environ:
            del os.environ[env_var]
            logger.debug(f"Removed {env_var} from current session")
            return True
        return False
    
    def _get_masked_api_key_value(self, env_var: str, value: str) -> str:
        """Get masked value for logging using centralized validator"""
        from gui.utils.api_key_validator import get_api_key_validator
        validator = get_api_key_validator()
        return validator.mask_api_key(value)

    def _get_masked_api_key(self, env_var: str) -> Optional[str]:
        """Get masked API key for UI display"""
        api_key = self.retrieve_api_key(env_var)
        if api_key:
            return self._get_masked_api_key_value(env_var, api_key)
        return None

    def _get_env_var_display_name(self, env_var: str) -> str:
        """Get display-friendly name for environment variable"""
        # Convert env var name to display name (e.g., OPENAI_API_KEY -> OpenAI API Key)
        # Remove common prefixes
        name = env_var
        for prefix in ['ANTHROPIC_', 'OPENAI_', 'GOOGLE_', 'DEEPSEEK_', 'GEMINI_']:
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        
        # Convert to title case and replace underscores with spaces
        display_name = name.replace('_', ' ').title()
        return display_name

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
        """
        Check if all required API keys for a provider are configured.
        For local providers like Ollama, do NOT automatically consider them configured
        just because they have a default base_url in llm_providers.json.
        Local providers should only be considered configured if explicitly set as default_llm
        and have a valid base_url.
        """
        if provider_config.is_local:
            # For local providers, do not automatically consider them configured
            # They should only be considered configured when explicitly selected as default_llm
            # and validated in check_provider_configured()
            # This prevents auto-selection of unconfigured local providers
            return False

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
    
    def get_provider_summary(self) -> Dict[str, Any]:
        """Get summary of provider status"""
        summary = llm_config.get_provider_summary()
        
        # Add configured providers count
        configured_with_keys = sum(1 for p in self.get_all_providers() if p["api_key_configured"])
        
        summary.update({
            "providers_with_api_keys": configured_with_keys
        })
        
        return summary
    
    # Model Management
    def get_models_for_provider(self, provider_name: str) -> List[Dict[str, Any]]:
        """Get models for a specific provider"""
        provider_config = llm_config.get_provider(provider_name)
        if not provider_config:
            return []
        
        preferred_model = provider_config.default_model
        models = self._serialize_models(provider_config.supported_models)
        
        # Mark the preferred model
        for model in models:
            model["is_preferred"] = (model["name"] == preferred_model)
        
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
    
    # Onboarding and Configuration Check
    
    def check_provider_configured(self) -> Tuple[bool, Optional[str]]:
        """
        Check if LLM provider is configured and a default is selected
        
        This method ensures onboarding is shown when:
        1. No default_llm is set (empty or None) - will auto-set to OpenAI
        2. default_llm is set but provider not found - will keep the setting
        3. default_llm is set but API key is missing (for non-local providers)
        4. default_llm is set but base_url is missing/invalid (for local providers)
        
        Note: default_llm is NEVER cleared, ensuring there's always a default provider.
        
        Returns:
            tuple: (is_configured: bool, configured_provider_name: Optional[str])
            - is_configured: True if default LLM provider is configured, False otherwise
            - configured_provider_name: Name of configured default provider, or None
        """
        try:
            # Get default LLM from settings
            default_llm = self.config_manager.general_settings.default_llm
            
            # Case 1: If default_llm is empty, set it to OpenAI as default
            if not default_llm or not default_llm.strip():
                logger.info("[LLMManager] No default LLM is set - setting to OpenAI with default model")
                self.config_manager.general_settings.default_llm = "OpenAI"
                # Also set the default model if not already set
                if not self.config_manager.general_settings.default_llm_model:
                    provider = llm_config.get_provider("OpenAI")
                    if provider:
                        self.config_manager.general_settings.default_llm_model = provider.default_model
                        logger.info(f"[LLMManager] Set default model to {provider.default_model}")
                self.config_manager.general_settings.save()
                default_llm = "OpenAI"
                # Still show onboarding since API key is likely not configured
                return False, None
            
            # Get provider configuration
            provider = self.get_provider(default_llm)
            
            # Case 2: Provider not found, show onboarding but keep the default_llm setting
            if not provider:
                logger.warning(f"[LLMManager] Default LLM '{default_llm}' provider not found - onboarding required")
                # Keep default_llm setting, don't clear it
                return False, None
            
            # For local providers (e.g., Ollama), check base_url configuration
            if provider.get('is_local', False):
                base_url = provider.get('base_url', '')
                if not base_url or not base_url.strip():
                    logger.info(f"[LLMManager] Local provider '{default_llm}' has no base_url - onboarding required")
                    return False, None
                
                # Validate base_url format
                base_url = base_url.strip()
                if not (base_url.startswith('http://') or base_url.startswith('https://')):
                    logger.warning(f"[LLMManager] Local provider '{default_llm}' has invalid base_url: {base_url} - onboarding required")
                    return False, None
                
                # Local provider properly configured
                logger.debug(f"[LLMManager] Local provider '{default_llm}' is properly configured with base_url: {base_url}")
                return True, default_llm
            
            # For non-local providers (e.g., OpenAI, Anthropic), check API key configuration
            # Case 3: Check if required API keys are configured
            api_key_env_vars = provider.get('api_key_env_vars', [])
            
            if not api_key_env_vars:
                # Provider doesn't require API keys (unusual but possible)
                logger.debug(f"[LLMManager] Provider '{default_llm}' doesn't require API keys")
                return True, default_llm
            
            # Check each required API key
            missing_keys = []
            for env_var in api_key_env_vars:
                if not self.has_api_key(env_var):
                    missing_keys.append(env_var)
            
            if missing_keys:
                # API keys are missing, show onboarding
                logger.info(f"[LLMManager] Provider '{default_llm}' is missing API keys: {missing_keys} - onboarding required")
                return False, None
            
            # All API keys are configured
            logger.debug(f"[LLMManager] Provider '{default_llm}' is fully configured with all required API keys")
            return True, default_llm
            
        except Exception as e:
            logger.error(f"[LLMManager] Error checking LLM provider configuration: {e}")
            # On error, show onboarding to be safe
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
                logger.debug(f"[LLMManager] LLM provider configured: {configured_provider}")
                
        except Exception as e:
            logger.error(f"[LLMManager] Error in LLM provider onboarding check: {e}")

    async def show_onboarding_guide(self):
        """
        Show onboarding guide for LLM provider configuration
        Sends instruction to frontend to display onboarding guide.
        Frontend determines UI, text, and behavior based on instruction type.
        """
        try:
            # Check if already shown this session
            if self._onboarding_shown:
                logger.debug("[LLMManager] Onboarding guide already shown this session, skipping")
                return
            
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
            
            # Mark as shown
            self._onboarding_shown = True
            logger.info("[LLMManager] Onboarding instruction pushed to frontend")
            
        except Exception as e:
            logger.error(f"[LLMManager] Error showing LLM provider onboarding guide: {e}")
    
    def validate_and_fix_default_llm_model(self, default_llm: str, default_llm_model: str) -> Tuple[str, bool]:
        """
        Validate that default_llm_model belongs to the default_llm provider.
        If not, return the provider's default model.
        
        Args:
            default_llm: The provider name
            default_llm_model: The model name to validate
            
        Returns:
            Tuple of (corrected_model_name, was_fixed)
            - corrected_model_name: The model name to use (either original or provider default)
            - was_fixed: True if the model was corrected, False if it was already valid
        """
        try:
            if not default_llm or not default_llm_model:
                # If no provider or model, return empty and indicate no fix needed
                return (default_llm_model or '', False)
            
            # Get the provider configuration
            provider = self.get_provider(default_llm)
            if not provider:
                # Provider not found, return original model
                return (default_llm_model, False)
            
            # Check if default_llm_model belongs to this provider
            supported_models = provider.get('supported_models', [])
            if supported_models:
                model_ids = [m.get('model_id', m.get('name', '')) for m in supported_models]
                model_names = [m.get('name', '') for m in supported_models]
                model_display_names = [m.get('display_name', '') for m in supported_models]
                
                # Check if model belongs to provider
                if (default_llm_model in model_ids or 
                    default_llm_model in model_names or 
                    default_llm_model in model_display_names):
                    # Model is valid, return as-is
                    return (default_llm_model, False)
                else:
                    # Model doesn't belong to provider, return provider's default
                    provider_default_model = provider.get('default_model', '')
                    logger.info(
                        f"[LLMManager] 🔧 Model '{default_llm_model}' does not belong to provider '{default_llm}'. "
                        f"Using provider default '{provider_default_model}' instead."
                    )
                    return (provider_default_model, True)
            else:
                # No supported models list, return provider's default
                provider_default_model = provider.get('default_model', '')
                if provider_default_model != default_llm_model:
                    logger.info(
                        f"[LLMManager] 🔧 No supported models list for '{default_llm}'. "
                        f"Using provider default '{provider_default_model}' instead of '{default_llm_model}'."
                    )
                    return (provider_default_model, True)
                return (default_llm_model, False)
                
        except Exception as e:
            logger.warning(f"[LLMManager] Error validating default_llm_model: {e}")
            return (default_llm_model, False)