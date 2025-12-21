"""
Rerank Manager

This module provides unified Rerank configuration management interface.
It integrates with the configuration system and provides methods for:
- Managing Rerank provider configurations
- Handling API key storage and retrieval
- Validating Rerank configurations
- Providing UI-friendly data structures
"""

import os
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, asdict

from gui.config.rerank_config import rerank_config, RerankProviderConfig
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


class RerankManager:
    """Rerank configuration manager with environment variable API key management"""

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize Rerank manager

        Args:
            config_manager: Configuration manager instance
        """
        self.config_manager = config_manager
        self._checking_provider = False  # Flag to prevent recursion
        
        # Load and merge Ollama models at initialization
        # This ensures consistency with LLMManager and prepares for future validation
        self._load_and_merge_ollama_models()
    
    def _load_and_merge_ollama_models(self):
        """
        Load ollama_tags.json and merge models into Ollama provider's supported_models.
        
        Note: Rerank uses proxy mechanism, but we load models for consistency.
        """
        try:
            from gui.ollama_utils import merge_ollama_models_to_config_providers
            from gui.config.rerank_config import rerank_config
            
            # Get all providers as dict
            all_providers = rerank_config.get_all_providers()
            
            # Use the unified merge function (auto-loads ollama_tags)
            merge_ollama_models_to_config_providers(all_providers, provider_type='rerank')
            
        except Exception as e:
            logger.warning(f"[RerankManager] Failed to load Ollama models during init: {e}")
    
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
    
    def _check_provider_api_keys_configured(self, provider_config: RerankProviderConfig) -> bool:
        """Check if all required API keys for a provider are configured"""
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
            serialized_models.append(model_dict)
        return serialized_models

    # Provider Management
    def get_all_providers(self) -> List[Dict[str, Any]]:
        """Get all Rerank providers with user preferences
        
        Merges data from:
        - rerank_providers.json (provider definitions, supported models)
        - settings.json (default_rerank, default_rerank_model)
        
        Automatically checks and sets default provider if not configured.
        """
        # Check and auto-configure default provider if needed (only once)
        if not self._checking_provider:
            self.check_provider_configured()
        
        providers = []
        
        # Get current default provider and its model from settings.json
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        current_default_rerank = ""
        current_default_model = ""
        if main_window:
            general_settings = main_window.config_manager.general_settings
            current_default_rerank = general_settings.default_rerank
            current_default_model = general_settings.default_rerank_model
        
        for provider_name, provider_config in rerank_config.get_all_providers().items():
            # Only set preferred_model if this is the current default provider (compare by provider identifier, case-insensitive)
            is_default_provider = (provider_config.provider.value.lower() == (current_default_rerank or "").lower())
            preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
            is_preferred = is_default_provider

            # Check if API keys are configured using environment variables
            api_key_configured = self._check_provider_api_keys_configured(provider_config)
            
            # Validate configuration
            validation = rerank_config.validate_provider_config(provider_name)
            
            # For Ollama, use base_url from settings.json if available (user preference)
            base_url = provider_config.base_url
            if 'ollama' in provider_config.name.lower() or 'ollama' in provider_config.provider.value.lower():
                try:
                    from gui.manager.provider_settings_helper import get_ollama_base_url
                    settings_base_url = get_ollama_base_url('rerank', provider_config)
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
        Also supports lookup by class_name for backward compatibility.
        """
        key = (provider_key or "").strip().lower()
        if not key:
            return None
        
        # First try: match by provider identifier (canonical)
        for provider in self.get_all_providers():
            provider_id = (provider.get("provider") or "").lower()
            if provider_id == key:
                return provider
        
        # Second try: match by class_name (backward compatibility for old settings)
        for provider in self.get_all_providers():
            class_name = (provider.get("class_name") or "").lower()
            if class_name == key:
                return provider
        
        return None
    
    def set_provider_default_model(self, provider_key: str, model_name: str) -> Tuple[bool, Optional[str]]:
        """Update the default model for the default Rerank provider
        
        Args:
            provider_key: Provider identifier (e.g., "cohere", "jina") - case-insensitive
            model_name: Model name to set as default
        
        Note: Only saves if this is the current default provider.
        Saves to user's settings.json (writable in PyInstaller), 
        NOT to rerank_providers.json (read-only in PyInstaller).
        """
        # Normalize provider key (case-insensitive)
        provider_key_normalized = (provider_key or "").strip().lower()
        if not provider_key_normalized:
            return False, "Provider key cannot be empty"
        
        # Resolve provider config by provider identifier (case-insensitive)
        provider_config = None
        for _, pc in rerank_config.get_all_providers().items():
            if pc.provider.value.lower() == provider_key_normalized:
                provider_config = pc
                break
        if not provider_config:
            return False, f"Provider '{provider_key}' not found"

        # Validate model belongs to provider
        if provider_config.supported_models:
            valid_model_names = {m.name for m in provider_config.supported_models}
            if model_name not in valid_model_names:
                return False, f"Model '{model_name}' is not supported by provider '{provider_config.name}'"

        # Save to user's settings.json (writable even in PyInstaller)
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return False, "Main window not available"
        
        general_settings = main_window.config_manager.general_settings
        
        # Check if this is the current default provider (case-insensitive comparison)
        current_default_rerank = (general_settings.default_rerank or "").lower()
        provider_identifier = provider_config.provider.value.lower()
        if current_default_rerank == provider_identifier:
            # Update default_rerank_model for the current default provider
            general_settings.default_rerank_model = model_name
            
            if not general_settings.save():
                return False, "Failed to save model selection to settings"
            
            logger.info(f"Updated default_rerank_model to '{model_name}' for current default provider '{provider_config.name}'")
        else:
            # Not the default provider, just return success without saving
            logger.info(f"Model '{model_name}' selected for '{provider_config.name}' (not saved since it's not the default provider)")

        return True, None

    def check_provider_configured(self) -> Tuple[bool, Optional[str]]:
        """
        Check if default Rerank provider is configured with API key
        
        This method ensures onboarding is shown when:
        1. No default_rerank is set (empty or None) - will NOT auto-set (rerank is optional)
        2. default_rerank is set but provider not found - will keep the setting
        3. default_rerank is set but API key is missing (for non-local providers)
        4. default_rerank is set but base_url is missing/invalid (for local providers)
        
        Note: Unlike LLM/Embedding, Rerank is optional, so we don't auto-set a default.
        
        Returns:
            tuple: (is_configured: bool, configured_provider_name: Optional[str])
            - is_configured: True if default Rerank provider is configured, False otherwise
            - configured_provider_name: Name of configured default provider, or None
        """
        # Prevent recursion
        if self._checking_provider:
            return False, None
        
        self._checking_provider = True
        try:
            # Get default Rerank from settings (provider identifier expected, e.g., "cohere")
            default_rerank = self.config_manager.general_settings.default_rerank
            
            # Case 1: If default_rerank is empty, it's OK (rerank is optional)
            if not default_rerank or not default_rerank.strip():
                logger.debug("[RerankManager] No default Rerank is set (rerank is optional)")
                return True, None  # Return True because rerank is optional
            
            # Get provider configuration
            provider = self.get_provider(default_rerank)
            
            # Case 2: Provider not found, show onboarding but keep the default_rerank setting
            if not provider:
                logger.warning(f"[RerankManager] Default Rerank '{default_rerank}' provider not found - onboarding required")
                # Keep default_rerank setting, don't clear it
                return False, None
            
            # For local providers (e.g., vLLM), check base_url configuration
            if provider.get('is_local', False):
                base_url = provider.get('base_url', '')
                if not base_url or not base_url.strip():
                    logger.info(f"[RerankManager] Local provider '{default_rerank}' has no base_url - onboarding required")
                    return False, None
                
                # Validate base_url format
                base_url = base_url.strip()
                if not (base_url.startswith('http://') or base_url.startswith('https://')):
                    logger.warning(f"[RerankManager] Local provider '{default_rerank}' has invalid base_url: {base_url} - onboarding required")
                    return False, None
                
                # Local provider properly configured
                logger.debug(f"[RerankManager] Local provider '{default_rerank}' is properly configured with base_url: {base_url}")
                return True, default_rerank
            
            # For non-local providers, check API key configuration
            # Case 3: Check if required API keys are configured for the default provider
            api_key_env_vars = provider.get('api_key_env_vars', [])
            
            if not api_key_env_vars:
                # Provider doesn't require API keys (unusual but possible)
                logger.debug(f"[RerankManager] Provider '{default_rerank}' doesn't require API keys")
                return True, default_rerank
            
            # Check each required API key for the default provider
            missing_keys = []
            for env_var in api_key_env_vars:
                if not self.has_api_key(env_var):
                    missing_keys.append(env_var)
            
            if missing_keys:
                # API keys are missing, show onboarding
                logger.info(f"[RerankManager] Provider '{default_rerank}' is missing API keys: {missing_keys} - onboarding required")
                return False, None
            
            # All API keys are configured for the default provider
            logger.debug(f"[RerankManager] Provider '{default_rerank}' is fully configured with all required API keys")
            return True, default_rerank
            
        except Exception as e:
            logger.error(f"[RerankManager] Error checking Rerank provider configuration: {e}")
            # On error, return True because rerank is optional
            return True, None
        finally:
            self._checking_provider = False



