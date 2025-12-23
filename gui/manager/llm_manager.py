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
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, asdict

from gui.config.llm_config import llm_config, LLMProviderConfig
from utils.logger_helper import logger_helper as logger

if TYPE_CHECKING:
    from gui.manager.config_manager import ConfigManager


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
        
        # Load and merge Ollama models at initialization
        # This is CRITICAL for extract_provider_config to validate user-selected models
        self._load_and_merge_ollama_models()
    
    def _load_and_merge_ollama_models(self):
        """
        Load ollama_tags.json and merge models into Ollama provider's supported_models.
        
        This is essential for:
        1. extract_provider_config to validate user-selected models
        2. Preventing model_name from being reset to empty string
        
        Note: This is different from handler's merge_ollama_models_to_providers:
        - Handler merge: For frontend display (dict-based providers)
        - Manager merge: For LLM instance creation validation (config-based providers)
        """
        try:
            from gui.ollama_utils import merge_ollama_models_to_config_providers
            
            # Get all providers as dict
            all_providers = llm_config.get_all_providers()
            
            # Use the unified merge function (auto-loads ollama_tags)
            merge_ollama_models_to_config_providers(all_providers, provider_type='llm')
            
        except Exception as e:
            logger.warning(f"[LLMManager] Failed to load Ollama models during init: {e}")
    
    # API Key Management Methods - Using Environment Variables
    
    def store_api_key(self, env_var: str, api_key: str) -> Tuple[bool, Optional[str]]:
        """
        Store an API key securely with user isolation

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

            # Get current username for user isolation
            from utils.env.secure_store import secure_store, get_current_username
            username = get_current_username()
            
            # Persist to secure store with user isolation (Keychain on macOS, Credential Manager on Windows, etc.)
            ok = secure_store.set(env_var, value, username=username)
            if not ok:
                return False, "Failed to persist API key to secure store"

            logger.info(f"API key stored for {env_var} in secure store (user: {username or 'anonymous'})")
            return True, None

        except Exception as e:
            error_msg = f"Failed to store API key for {env_var}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg

    def retrieve_api_key(self, env_var: str) -> Optional[str]:
        """
        Retrieve an API key from secure store with user isolation

        Args:
            env_var: Environment variable name

        Returns:
            API key if found, None otherwise
        """
        try:
            # Get current username for user isolation
            from utils.env.secure_store import secure_store, get_current_username
            username = get_current_username()
            value = secure_store.get(env_var, username=username)
            if value and value.strip():
                return value
            return None

        except Exception as e:
            logger.error(f"Failed to retrieve API key for {env_var}: {e}")
            return None

    def has_api_key(self, env_var: str) -> bool:
        """
        Check if an API key exists in secure store with user isolation

        Args:
            env_var: Environment variable name

        Returns:
            True if API key exists, False otherwise
        """
        try:
            # Get current username for user isolation
            from utils.env.secure_store import secure_store, get_current_username
            username = get_current_username()
            value = secure_store.get(env_var, username=username)
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

            # Get current username for user isolation
            from utils.env.secure_store import secure_store, get_current_username
            username = get_current_username()
            
            # Delete from secure store
            store_deleted = False
            try:
                store_deleted = secure_store.delete(env_var, username=username)
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
        For local providers like Ollama, check if base_url is valid.
        """
        if provider_config.is_local:
            # For local providers, check if base_url is configured and valid
            base_url = provider_config.base_url
            if base_url and (base_url.strip().startswith('http://') or base_url.strip().startswith('https://')):
                return True
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
            # Only set preferred_model if this is the current default provider (case-insensitive comparison)
            is_default_provider = (provider_config.provider.value.lower() == (current_default_llm or "").lower())
            preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
            is_preferred = is_default_provider
            custom_params = {}

            # Check if API keys are configured using environment variables
            api_key_configured = self._check_provider_api_keys_configured(provider_config)
            
            # Validate configuration
            validation = llm_config.validate_provider_config(provider_name)
            
            # For Ollama, use base_url from settings.json if available (user preference)
            base_url = provider_config.base_url
            if 'ollama' in provider_config.name.lower() or 'ollama' in provider_config.provider.value.lower():
                try:
                    from gui.manager.provider_settings_helper import get_ollama_base_url
                    settings_base_url = get_ollama_base_url('llm', provider_config)
                    if settings_base_url and settings_base_url.strip():
                        base_url = settings_base_url
                except Exception:
                    pass  # Use default base_url if settings retrieval fails
            
            provider_data = {
                "name": provider_config.name,
                "display_name": provider_config.display_name,
                "class_name": provider_config.class_name,
                "provider": provider_config.provider.value,  # Convert enum to string value (canonical identifier)
                "description": provider_config.description,
                "documentation_url": provider_config.documentation_url,
                "is_local": provider_config.is_local,
                "base_url": base_url,
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
    
    def get_provider(self, provider_key: str) -> Optional[Dict[str, Any]]:
        """Get a specific provider by canonical provider identifier (providers[i]['provider']).
        
        Provider comparison is case-insensitive for better compatibility.
        Also supports lookup by:
        1. provider identifier (canonical, e.g., "openai")
        2. class_name (backward compatibility, e.g., "ChatOpenAI" -> "openai")
        3. name (backward compatibility, e.g., "Qwen (DashScope)" -> "dashscope")
        """
        key = (provider_key or "").strip().lower()
        if not key:
            return None
        
        providers = self.get_all_providers()
        
        # First try: match by provider identifier (canonical)
        for provider in providers:
            provider_id = (provider.get("provider") or "").lower()
            if provider_id == key:
                return provider
        
        # Second try: match by class_name (backward compatibility for old settings)
        for provider in providers:
            class_name = (provider.get("class_name") or "").lower()
            if class_name == key:
                provider_id = provider.get("provider")
                logger.info(f"[LLMManager] Found provider '{provider.get('name')}' by class_name '{provider_key}', provider_id='{provider_id}'")
                # Auto-migrate settings if this was found by class_name (not provider identifier)
                # This ensures settings.json is updated to use canonical identifier
                if provider_id and provider_id.lower() != key:
                    try:
                        from app_context import AppContext
                        main_window = AppContext.get_main_window()
                        if main_window and main_window.config_manager.general_settings.default_llm == provider_key:
                            logger.info(f"[LLMManager] Auto-updating settings: '{provider_key}' -> '{provider_id}'")
                            main_window.config_manager.general_settings.default_llm = provider_id
                            main_window.config_manager.general_settings.save()
                    except Exception as e:
                        logger.debug(f"[LLMManager] Could not auto-update settings (non-critical): {e}")
                return provider
        
        # Third try: match by name (backward compatibility with old settings using display names)
        for provider in providers:
            provider_name = (provider.get("name") or "").lower()
            if provider_name == key:
                provider_id = provider.get("provider")
                logger.info(f"[LLMManager] Found provider '{provider.get('name')}' by name '{provider_key}', provider_id='{provider_id}'")
                # Auto-migrate settings if this was found by name (not provider identifier)
                if provider_id and provider_id.lower() != key:
                    try:
                        from app_context import AppContext
                        main_window = AppContext.get_main_window()
                        if main_window and main_window.config_manager.general_settings.default_llm == provider_key:
                            logger.info(f"[LLMManager] Auto-updating settings: '{provider_key}' -> '{provider_id}'")
                            main_window.config_manager.general_settings.default_llm = provider_id
                            main_window.config_manager.general_settings.save()
                    except Exception as e:
                        logger.debug(f"[LLMManager] Could not auto-update settings (non-critical): {e}")
                return provider
        
        logger.warning(f"[LLMManager] Provider '{provider_key}' not found (tried identifier, class_name, and name)")
        return None
    
    def _try_migrate_class_name_to_identifier(self, class_name_or_identifier: str) -> Optional[str]:
        """Try to migrate class_name to provider identifier (e.g., "ChatOpenAI" -> "openai").
        
        Returns the provider identifier if found, None otherwise.
        """
        key = (class_name_or_identifier or "").strip().lower()
        if not key:
            return None
        
        # Try to find by class_name and return its provider identifier
        providers = self.get_all_providers()
        logger.debug(f"[LLMManager] Attempting migration for '{class_name_or_identifier}' (normalized: '{key}'), checking {len(providers)} providers...")
        
        for provider in providers:
            class_name = (provider.get("class_name") or "").lower()
            provider_id = provider.get("provider", "")
            # logger.debug(f"[LLMManager] Checking provider '{provider.get('name')}': class_name='{provider.get('class_name')}' (normalized: '{class_name}'), provider_id='{provider_id}'")
            if class_name == key:
                logger.info(f"[LLMManager] Found match: '{class_name_or_identifier}' -> '{provider_id}'")
                return provider_id  # Return the canonical identifier
        
        logger.debug(f"[LLMManager] No provider found with class_name matching '{class_name_or_identifier}'")
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

    def update_default_llm(self, provider_key: str) -> bool:
        """Update the default LLM provider
        
        Args:
            provider_key: Provider identifier (e.g., "openai", "azure_openai") - case-insensitive
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Normalize provider key (case-insensitive)
        provider_key_normalized = (provider_key or "").strip().lower()
        if not provider_key_normalized:
            logger.warning("[LLMManager] Cannot update default LLM: empty provider key")
            return False
        
        # Get provider config by identifier (case-insensitive)
        provider_config = None
        for name, pc in llm_config.get_all_providers().items():
            if pc.provider.value.lower() == provider_key_normalized:
                provider_config = pc
                break
        
        if not provider_config:
            logger.warning(f"[LLMManager] Provider '{provider_key}' not found")
            return False
        
        # Save to user's settings.json (writable even in PyInstaller)
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.warning("[LLMManager] Main window not available")
            return False
        
        general_settings = main_window.config_manager.general_settings
        
        # Update default LLM
        general_settings.default_llm = provider_config.provider.value
        
        # If provider has a default model, set it
        available_models = llm_config.get_models_for_provider(provider_config.name)
        if available_models:
            general_settings.default_llm_model = available_models[0].name
        
        # Save settings
        if not general_settings.save():
            logger.error(f"[LLMManager] Failed to save default LLM setting")
            return False
        
        logger.info(f"[LLMManager] ✅ Updated default LLM to {provider_config.provider.value}")
        return True
    
    def set_provider_default_model(self, provider_key: str, model_name: str) -> Tuple[bool, Optional[str]]:
        """Update the default model for the default LLM provider
        
        Args:
            provider_key: Provider identifier (e.g., "openai", "azure_openai") - case-insensitive
            model_name: Model name to set as default
        
        Note: Only saves if this is the current default provider.
        Saves to user's settings.json (writable in PyInstaller), 
        NOT to llm_providers.json (read-only in PyInstaller).
        """
        # Normalize provider key (case-insensitive)
        provider_key_normalized = (provider_key or "").strip().lower()
        if not provider_key_normalized:
            return False, "Provider key cannot be empty"
        
        # Get provider config by identifier (case-insensitive)
        provider_config = None
        for name, pc in llm_config.get_all_providers().items():
            if pc.provider.value.lower() == provider_key_normalized:
                provider_config = pc
                break
        
        if not provider_config:
            return False, f"Provider '{provider_key}' not found"

        available_models = llm_config.get_models_for_provider(provider_config.name)
        valid_model_names = {model.name for model in available_models}

        if available_models and model_name not in valid_model_names:
            return False, f"Model '{model_name}' is not supported by provider '{provider_config.name}'"

        # Save to user's settings.json (writable even in PyInstaller)
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return False, "Main window not available"
        
        general_settings = main_window.config_manager.general_settings
        
        # Check if this is the current default provider (compare by provider identifier, case-insensitive)
        current_default_llm = (general_settings.default_llm or "").lower()
        provider_identifier = provider_config.provider.value.lower()
        if current_default_llm == provider_identifier:
            # Update default_llm_model for the current default provider
            general_settings.default_llm_model = model_name
            
            if not general_settings.save():
                return False, "Failed to save model selection to settings"
            
            logger.info(f"Updated default_llm_model to {model_name} for current default provider '{provider_config.name}'")
        else:
            # Not the default provider, just return success without saving
            # The frontend may want to change models for non-default providers for preview
            logger.info(f"Model '{model_name}' selected for '{provider_config.name}' (not saved since it's not the default provider)")

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
            # Get default LLM from settings (provider identifier expected, e.g., "openai")
            default_llm = self.config_manager.general_settings.default_llm
            
            # Case 1: If default_llm is empty, set it to OpenAI as default
            if not default_llm or not default_llm.strip():
                logger.info("[LLMManager] No default LLM is set - setting to OpenAI (provider identifier: 'openai') with default model")
                self.config_manager.general_settings.default_llm = "openai"
                # Also set the default model if not already set
                if not self.config_manager.general_settings.default_llm_model:
                    provider_config = llm_config.get_provider("OpenAI")
                    if provider_config:
                        self.config_manager.general_settings.default_llm_model = provider_config.default_model
                        logger.info(f"[LLMManager] Set default model to {provider_config.default_model}")
                self.config_manager.general_settings.save()
                default_llm = "openai"
                # Continue to check API key configuration below
            
            # Get provider configuration (supports both provider identifier and class_name)
            provider = self.get_provider(default_llm)
            
            # Case 2: Provider not found, try auto-migration from class_name to identifier
            if not provider:
                logger.warning(f"[LLMManager] Provider '{default_llm}' not found by identifier, trying class_name lookup...")
                # Try to auto-migrate if it's a class_name (e.g., "ChatOpenAI" -> "openai")
                provider_identifier = self._try_migrate_class_name_to_identifier(default_llm)
                if provider_identifier:
                    logger.info(f"[LLMManager] Auto-migrated '{default_llm}' (class_name) to provider identifier '{provider_identifier}'")
                    self.config_manager.general_settings.default_llm = provider_identifier
                    self.config_manager.general_settings.save()
                    # Continue with migrated identifier (don't recurse to avoid infinite loop)
                    default_llm = provider_identifier
                    provider = self.get_provider(provider_identifier)
                    if not provider:
                        logger.error(f"[LLMManager] Failed to find provider after migration to '{provider_identifier}'")
                        return False, None
                    logger.info(f"[LLMManager] Successfully found provider '{provider.get('name')}' after migration")
                    # Continue to check configuration below
                else:
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
                logger.warning(f"[LLMManager] Provider '{default_llm}' doesn't require API keys")
                return True, default_llm
            
            # Check each required API key
            missing_keys = []
            for env_var in api_key_env_vars:
                if not self.has_api_key(env_var):
                    missing_keys.append(env_var)
            
            if missing_keys:
                # API keys are missing, show onboarding
                logger.warning(f"[LLMManager] Provider '{default_llm}' is missing API keys: {missing_keys} - onboarding required")
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
        Check LLM and Embedding provider configuration and show onboarding guide if needed
        This runs asynchronously and should be called after initialization is complete
        
        Checks in order:
        1. LLM provider default API key configuration
        2. Embedding provider default API key configuration (if LLM is configured)
        
        Args:
            delay_seconds: Delay before checking to ensure web GUI is ready
        """
        try:
            import asyncio
            # Wait a bit to ensure web GUI is ready
            await asyncio.sleep(delay_seconds)
            
            # Step 1: Check LLM provider configuration
            is_llm_configured, configured_llm_provider = self.check_provider_configured()
            
            if not is_llm_configured:
                logger.info("[LLMManager] 📋 LLM provider not configured, showing onboarding guide")
                await self.show_onboarding_guide()
                return
            else:
                logger.debug(f"[LLMManager] LLM provider configured: {configured_llm_provider}")
            
            # Step 2: If LLM is configured, check Embedding provider configuration
            if hasattr(self.config_manager, 'embedding_manager'):
                embedding_manager = self.config_manager.embedding_manager
                is_embedding_configured, configured_embedding_provider = embedding_manager.check_provider_configured()
                
                if not is_embedding_configured:
                    logger.info("[LLMManager] 📋 Embedding provider not configured, showing onboarding guide")
                    await self.show_embedding_onboarding_guide()
                else:
                    logger.debug(f"[LLMManager] Embedding provider configured: {configured_embedding_provider}")
            else:
                logger.warning("[LLMManager] Embedding manager not available")
                
        except Exception as e:
            logger.error(f"[LLMManager] Error in provider onboarding check: {e}")

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
    
    async def show_embedding_onboarding_guide(self):
        """
        Show onboarding guide for Embedding provider configuration
        Sends instruction to frontend to display onboarding guide and navigate to embedding tab.
        """
        try:
            from app_context import AppContext
            web_gui = AppContext.get_web_gui()
            if not web_gui:
                logger.warning("[LLMManager] Web GUI not available for embedding onboarding guide")
                return
            
            ipc_api = web_gui.get_ipc_api()
            if not ipc_api:
                logger.warning("[LLMManager] IPC API not available for embedding onboarding guide")
                return
            
            # Push onboarding instruction to frontend for embedding provider
            ipc_api.push_onboarding_message(
                onboarding_type='embedding_provider_config',
                context={
                    'suggestedAction': {
                        'type': 'navigate',
                        'path': '/settings',
                        'params': {'tab': 'embedding'}
                    }
                }
            )
            
            logger.info("[LLMManager] Embedding onboarding instruction pushed to frontend")
            
        except Exception as e:
            logger.error(f"[LLMManager] Error showing Embedding provider onboarding guide: {e}")
    
    def reset_onboarding_flag(self):
        """
        Reset the onboarding flag so onboarding can be shown again
        This is useful when a new user logs in or when we want to force show onboarding
        """
        self._onboarding_shown = False
        logger.debug("[LLMManager] Onboarding flag reset")
    
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