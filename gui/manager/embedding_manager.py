"""
Embedding Manager

This module provides unified Embedding configuration management interface.
It integrates with the configuration system and provides methods for:
- Managing Embedding provider configurations
- Handling API key storage and retrieval
- Validating Embedding configurations
- Providing UI-friendly data structures
"""

import os
from typing import Dict, List, Optional, Any, Tuple, TYPE_CHECKING
from dataclasses import dataclass, asdict

from gui.config.embedding_config import embedding_config, EmbeddingProviderConfig
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


class EmbeddingManager:
    """Embedding configuration manager with environment variable API key management"""

    def __init__(self, config_manager: 'ConfigManager'):
        """
        Initialize Embedding manager

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
        
        Note: Currently EmbeddingFactory doesn't validate models against supported_models,
        but we load them for consistency and future-proofing.
        """
        try:
            from gui.ollama_utils import merge_ollama_models_to_config_providers
            from gui.config.embedding_config import embedding_config
            
            # Get all providers as dict
            all_providers = embedding_config.get_all_providers()
            
            # Use the unified merge function (auto-loads ollama_tags)
            merge_ollama_models_to_config_providers(all_providers, provider_type='embedding')
            
        except Exception as e:
            logger.warning(f"[EmbeddingManager] Failed to load Ollama models during init: {e}")
    
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
    
    def _check_provider_api_keys_configured(self, provider_config: EmbeddingProviderConfig) -> bool:
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
        """Get all Embedding providers with user preferences
        
        Merges data from:
        - embedding_providers.json (provider definitions, supported models)
        - settings.json (default_embedding, default_embedding_model)
        
        Automatically checks and sets default provider if not configured.
        """
        # Check and auto-configure default provider if needed (only once)
        if not self._checking_provider:
            self.check_provider_configured()
        
        providers = []
        
        # Get current default provider and its model from settings.json
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        current_default_embedding = ""
        current_default_model = ""
        if main_window:
            general_settings = main_window.config_manager.general_settings
            current_default_embedding = general_settings.default_embedding
            current_default_model = general_settings.default_embedding_model
        
        for provider_name, provider_config in embedding_config.get_all_providers().items():
            # Only set preferred_model if this is the current default provider (compare by provider identifier, case-insensitive)
            is_default_provider = (provider_config.provider.value.lower() == (current_default_embedding or "").lower())
            preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
            is_preferred = is_default_provider

            # Check if API keys are configured using environment variables
            api_key_configured = self._check_provider_api_keys_configured(provider_config)
            
            # Validate configuration
            validation = embedding_config.validate_provider_config(provider_name)
            
            # For Ollama, use base_url from settings.json if available (user preference)
            base_url = provider_config.base_url
            if 'ollama' in provider_config.name.lower() or 'ollama' in provider_config.provider.value.lower():
                try:
                    from gui.manager.provider_settings_helper import get_ollama_base_url
                    settings_base_url = get_ollama_base_url('embedding', provider_config)
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
    
    def _get_provider_config_only(self, provider_key: str) -> Optional[Dict[str, Any]]:
        """Get provider configuration without triggering auto-configuration
        Used internally to avoid recursion in check_provider_configured
        
        Supports matching by:
        1. provider identifier (canonical, e.g., "alibaba_qwen")
        2. name (e.g., "阿里云通义千问")
        3. display_name (for backward compatibility)
        """
        providers = []
        
        # Get current default provider and its model from settings.json
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        current_default_embedding = ""
        current_default_model = ""
        if main_window:
            general_settings = main_window.config_manager.general_settings
            current_default_embedding = general_settings.default_embedding
            current_default_model = general_settings.default_embedding_model
        
        provider_key_normalized = (provider_key or "").lower()
        for provider_name_key, provider_config in embedding_config.get_all_providers().items():
            # Match by provider identifier (canonical) - preferred
            if provider_config.provider.value.lower() == provider_key_normalized:
                is_default_provider = (provider_config.provider.value.lower() == (current_default_embedding or "").lower())
                preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
                
                api_key_configured = self._check_provider_api_keys_configured(provider_config)
                validation = embedding_config.validate_provider_config(provider_name_key)
                
                return {
                    "name": provider_config.name,
                    "display_name": provider_config.display_name,
                    "class_name": provider_config.class_name,
                    "provider": provider_config.provider.value,
                    "description": provider_config.description,
                    "documentation_url": provider_config.documentation_url,
                    "is_local": provider_config.is_local,
                    "base_url": provider_config.base_url,
                    "default_model": provider_config.default_model,
                    "api_key_env_vars": provider_config.api_key_env_vars,
                    "supported_models": self._serialize_models(provider_config.supported_models),
                    "is_preferred": is_default_provider,
                    "preferred_model": preferred_model,
                    "api_key_configured": api_key_configured,
                    "is_valid": validation["valid"],
                    "validation_error": validation.get("error"),
                    "missing_env_vars": validation.get("missing_env_vars", [])
                }
            # Match by name (for backward compatibility with old settings)
            elif provider_config.name.lower() == provider_key_normalized:
                is_default_provider = (provider_config.provider.value.lower() == (current_default_embedding or "").lower())
                preferred_model = current_default_model if (is_default_provider and current_default_model) else provider_config.default_model
                
                api_key_configured = self._check_provider_api_keys_configured(provider_config)
                validation = embedding_config.validate_provider_config(provider_name_key)
                
                # Auto-migrate: update settings.json to use provider identifier
                if main_window and current_default_embedding.lower() == provider_key_normalized:
                    logger.info(f"[EmbeddingManager] Auto-migrating default_embedding from '{current_default_embedding}' to '{provider_config.provider.value}'")
                    main_window.config_manager.general_settings.default_embedding = provider_config.provider.value
                    main_window.config_manager.general_settings.save()
                
                return {
                    "name": provider_config.name,
                    "display_name": provider_config.display_name,
                    "class_name": provider_config.class_name,
                    "provider": provider_config.provider.value,
                    "description": provider_config.description,
                    "documentation_url": provider_config.documentation_url,
                    "is_local": provider_config.is_local,
                    "base_url": provider_config.base_url,
                    "default_model": provider_config.default_model,
                    "api_key_env_vars": provider_config.api_key_env_vars,
                    "supported_models": self._serialize_models(provider_config.supported_models),
                    "is_preferred": is_default_provider,
                    "preferred_model": preferred_model,
                    "api_key_configured": api_key_configured,
                    "is_valid": validation["valid"],
                    "validation_error": validation.get("error"),
                    "missing_env_vars": validation.get("missing_env_vars", [])
                }
        return None
    
    def set_provider_default_model(self, provider_key: str, model_name: str) -> Tuple[bool, Optional[str]]:
        """Update the default model for the default Embedding provider
        
        Args:
            provider_key: Provider identifier (e.g., "openai", "azure_openai") - case-insensitive
            model_name: Model name to set as default
        
        Note: Only saves if this is the current default provider.
        Saves to user's settings.json (writable in PyInstaller), 
        NOT to embedding_providers.json (read-only in PyInstaller).
        """
        # Normalize provider key (case-insensitive)
        provider_key_normalized = (provider_key or "").strip().lower()
        if not provider_key_normalized:
            return False, "Provider key cannot be empty"
        
        # Resolve provider config by provider identifier (case-insensitive)
        provider_config = None
        for _, pc in embedding_config.get_all_providers().items():
            if pc.provider.value.lower() == provider_key_normalized:
                provider_config = pc
                break
        if not provider_config:
            return False, f"Provider '{provider_key}' not found"

        # Skip model validation - models are dynamically fetched via API

        # Save to user's settings.json (writable even in PyInstaller)
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return False, "Main window not available"
        
        general_settings = main_window.config_manager.general_settings
        
        # Check if this is the current default provider (case-insensitive comparison)
        current_default_embedding = (general_settings.default_embedding or "").lower()
        provider_identifier = provider_config.provider.value.lower()
        if current_default_embedding == provider_identifier:
            # Update default_embedding_model for the current default provider
            general_settings.default_embedding_model = model_name
            
            if not general_settings.save():
                return False, "Failed to save model selection to settings"
            
            logger.info(f"Updated default_embedding_model to '{model_name}' for current default provider '{provider_config.name}'")
        else:
            # Not the default provider, just return success without saving
            logger.info(f"Model '{model_name}' selected for '{provider_config.name}' (not saved since it's not the default provider)")

        return True, None

    def check_provider_configured(self) -> Tuple[bool, Optional[str]]:
        """
        Check if default Embedding provider is configured with API key
        
        This method ensures onboarding is shown when:
        1. No default_embedding is set (empty or None) - will auto-set to OpenAI
        2. default_embedding is set but provider not found - will keep the setting
        3. default_embedding is set but API key is missing (for non-local providers)
        4. default_embedding is set but base_url is missing/invalid (for local providers)
        
        Note: Only checks the default provider's API key, not all providers.
        default_embedding is NEVER cleared, ensuring there's always a default provider.
        
        Returns:
            tuple: (is_configured: bool, configured_provider_name: Optional[str])
            - is_configured: True if default Embedding provider is configured, False otherwise
            - configured_provider_name: Name of configured default provider, or None
        """
        # Prevent recursion
        if self._checking_provider:
            return False, None
        
        self._checking_provider = True
        try:
            # Get default Embedding from settings (provider identifier expected, e.g., "openai")
            default_embedding = self.config_manager.general_settings.default_embedding
            
            # Case 1: If default_embedding is empty, set it to OpenAI (provider identifier: "openai") as default
            if not default_embedding or not default_embedding.strip():
                logger.info("[EmbeddingManager] No default Embedding is set - setting to OpenAI (provider identifier: 'openai') with default model")
                self.config_manager.general_settings.default_embedding = "openai"
                # Also set the default model if not already set
                if not self.config_manager.general_settings.default_embedding_model:
                    provider_config = embedding_config.get_provider("OpenAI")
                    if provider_config:
                        self.config_manager.general_settings.default_embedding_model = provider_config.default_model
                        logger.info(f"[EmbeddingManager] Set default model to {provider_config.default_model}")
                self.config_manager.general_settings.save()
                default_embedding = "openai"
                # Continue to check API key configuration below
            
            # Get provider configuration (without triggering auto-configuration to avoid recursion)
            provider = self._get_provider_config_only(default_embedding)
            
            # Case 2: Provider not found, show onboarding but keep the default_embedding setting
            if not provider:
                logger.warning(f"[EmbeddingManager] Default Embedding '{default_embedding}' provider not found - onboarding required")
                # Keep default_embedding setting, don't clear it
                return False, None
            
            # For local providers (e.g., Ollama), check base_url configuration
            if provider.get('is_local', False):
                base_url = provider.get('base_url', '')
                if not base_url or not base_url.strip():
                    logger.info(f"[EmbeddingManager] Local provider '{default_embedding}' has no base_url - onboarding required")
                    return False, None
                
                # Validate base_url format
                base_url = base_url.strip()
                if not (base_url.startswith('http://') or base_url.startswith('https://')):
                    logger.warning(f"[EmbeddingManager] Local provider '{default_embedding}' has invalid base_url: {base_url} - onboarding required")
                    return False, None
                
                # Local provider properly configured
                logger.debug(f"[EmbeddingManager] Local provider '{default_embedding}' is properly configured with base_url: {base_url}")
                return True, default_embedding
            
            # For non-local providers, check API key configuration
            # Case 3: Check if required API keys are configured for the default provider
            api_key_env_vars = provider.get('api_key_env_vars', [])
            
            if not api_key_env_vars:
                # Provider doesn't require API keys (unusual but possible)
                logger.debug(f"[EmbeddingManager] Provider '{default_embedding}' doesn't require API keys")
                return True, default_embedding
            
            # Check each required API key for the default provider
            missing_keys = []
            for env_var in api_key_env_vars:
                if not self.has_api_key(env_var):
                    missing_keys.append(env_var)
            
            if missing_keys:
                # API keys are missing, show onboarding
                logger.info(f"[EmbeddingManager] Provider '{default_embedding}' is missing API keys: {missing_keys} - onboarding required")
                return False, None
            
            # All API keys are configured for the default provider
            logger.debug(f"[EmbeddingManager] Provider '{default_embedding}' is fully configured with all required API keys")
            return True, default_embedding
            
        except Exception as e:
            logger.error(f"[EmbeddingManager] Error checking Embedding provider configuration: {e}")
            # On error, show onboarding to be safe
            return False, None
        finally:
            self._checking_provider = False



