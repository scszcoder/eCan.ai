"""
Provider configuration utilities
Common functions for handling provider updates (LLM, Embedding, Rerank)
"""
from typing import Optional, Tuple
from utils.logger_helper import logger_helper as logger


def update_ollama_base_url(
    provider_identifier: str,
    base_url: str,
    provider_type: str  # 'llm', 'embedding', or 'rerank'
) -> Tuple[bool, Optional[str]]:
    """
    Update Ollama base_url in settings.json.
    
    Args:
        provider_identifier: Provider identifier (e.g., 'ollama')
        base_url: New base URL (e.g., 'http://localhost:11434')
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        if provider_identifier.lower() not in ['ollama', 'ryoais']:
            return False, f"update_ollama_base_url only supports 'ollama' or 'ryoais', got '{provider_identifier}'"
        
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            error_msg = "Cannot update base_url: main_window not available"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Update base_url in memory (don't save yet, will be saved by caller)
        general_settings = main_window.config_manager.general_settings
        provider_lower = provider_identifier.lower()
        
        if provider_type == 'llm':
            if provider_lower == 'ollama':
                general_settings.ollama_llm_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_llm_base_url = base_url
        elif provider_type == 'embedding':
            if provider_lower == 'ollama':
                general_settings.ollama_embedding_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_embedding_base_url = base_url
        elif provider_type == 'rerank':
            if provider_lower == 'ollama':
                general_settings.ollama_rerank_base_url = base_url
            elif provider_lower == 'ryoais':
                general_settings.ryoais_rerank_base_url = base_url
        else:
            error_msg = f"Unknown provider_type: {provider_type}"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        logger.info(f"[ProviderUtils] Updated {provider_identifier} {provider_type} base_url: {base_url}")
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to update base_url: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def get_ollama_base_url(provider_type: str, provider_config = None, provider_identifier: str = 'ollama') -> str:
    """
    Get Ollama/RyoAIS base_url from settings.json or provider config.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        provider_config: Optional provider config (dict or object) with default base_url
        provider_identifier: Provider identifier ('ollama' or 'ryoais')
    
    Returns:
        Base URL string
    """
    provider_lower = provider_identifier.lower()
    
    # Start with provider default or fallback
    if provider_config:
        # Handle both dict and object types
        if isinstance(provider_config, dict):
            default_url = 'http://localhost/v1' if provider_lower == 'ryoais' else 'http://localhost:11434'
            base_url = provider_config.get('base_url', default_url)
        else:
            # It's an object (e.g., LLMProviderConfig)
            default_url = 'http://localhost/v1' if provider_lower == 'ryoais' else 'http://localhost:11434'
            base_url = getattr(provider_config, 'base_url', default_url)
    else:
        base_url = 'http://localhost/v1' if provider_lower == 'ryoais' else 'http://localhost:11434'
    
    # Try to get from settings.json
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if main_window:
            general_settings = main_window.config_manager.general_settings
            
            if provider_type == 'llm':
                settings_url = general_settings.ryoais_llm_base_url if provider_lower == 'ryoais' else general_settings.ollama_llm_base_url
            elif provider_type == 'embedding':
                settings_url = general_settings.ryoais_embedding_base_url if provider_lower == 'ryoais' else general_settings.ollama_embedding_base_url
            elif provider_type == 'rerank':
                settings_url = general_settings.ryoais_rerank_base_url if provider_lower == 'ryoais' else general_settings.ollama_rerank_base_url
            else:
                logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
                return base_url
            
            if settings_url:
                base_url = settings_url
                logger.debug(f"[ProviderUtils] Using {provider_identifier} {provider_type} base_url from settings.json: {base_url}")
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not get {provider_identifier}_{provider_type}_base_url from settings: {e}")
    
    return base_url


def get_ollama_api_key(provider_type: str, provider_identifier: str = 'ollama') -> str:
    """
    Get Ollama/RyoAIS API key from Secure Store.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        provider_identifier: Provider identifier ('ollama' or 'ryoais')
    
    Returns:
        API key string (or provider name as dummy if not configured)
    """
    try:
        from utils.env.secure_store import get_current_username, secure_store
        
        provider_lower = provider_identifier.lower()
        provider_upper = provider_identifier.upper()
        
        # Determine the environment variable name based on provider type
        if provider_type == 'llm':
            env_var = f'{provider_upper}_LLM_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_LLM_API_KEY'
        elif provider_type == 'embedding':
            env_var = f'{provider_upper}_EMBEDDING_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_EMBEDDING_API_KEY'
        elif provider_type == 'rerank':
            env_var = f'{provider_upper}_RERANK_API_KEY' if provider_lower == 'ryoais' else 'OLLAMA_RERANK_API_KEY'
        else:
            logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
            return provider_lower
        
        username = get_current_username()
        api_key = secure_store.get(env_var, username=username)
        if not api_key or not api_key.strip():
            # For local providers without authentication, use dummy key
            logger.debug(f"[ProviderUtils] {env_var} not configured, using dummy key for local access")
            return provider_lower
        
        return api_key
    except Exception as e:
        logger.debug(f"[ProviderUtils] Failed to get {provider_identifier} API key: {e}")
        return provider_identifier.lower()


def save_general_settings_if_needed(base_url_updated: bool, auto_set_as_default: bool) -> bool:
    """
    Save general_settings if any updates were made.
    
    Args:
        base_url_updated: Whether base_url was updated
        auto_set_as_default: Whether default provider was auto-set
    
    Returns:
        True if saved successfully or no save needed, False otherwise
    """
    logger.debug(f"[ProviderUtils] save_general_settings_if_needed called: base_url_updated={base_url_updated}, auto_set_as_default={auto_set_as_default}")
    
    if not (base_url_updated or auto_set_as_default):
        logger.debug("[ProviderUtils] No save needed (no updates)")
        return True  # No save needed
    
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            logger.error("[ProviderUtils] Cannot save: main_window not available")
            return False
        
        logger.debug("[ProviderUtils] Attempting to save general_settings...")
        general_settings = main_window.config_manager.general_settings
        success = general_settings.save()
        
        if success:
            logger.info("[ProviderUtils] ✅ Saved general_settings to disk (base_url and/or default provider)")
        else:
            logger.error("[ProviderUtils] ❌ Failed to save general_settings")
        
        return success
        
    except Exception as e:
        logger.error(f"[ProviderUtils] ❌ Exception while saving general_settings: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
