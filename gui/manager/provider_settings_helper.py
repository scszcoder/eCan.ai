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
        if provider_identifier.lower() != 'ollama':
            return False, f"update_ollama_base_url only supports 'ollama', got '{provider_identifier}'"
        
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            error_msg = "Cannot update base_url: main_window not available"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Update base_url in memory (don't save yet, will be saved by caller)
        general_settings = main_window.config_manager.general_settings
        
        if provider_type == 'llm':
            general_settings.ollama_llm_base_url = base_url
        elif provider_type == 'embedding':
            general_settings.ollama_embedding_base_url = base_url
        elif provider_type == 'rerank':
            general_settings.ollama_rerank_base_url = base_url
        else:
            error_msg = f"Unknown provider_type: {provider_type}"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        logger.info(f"[ProviderUtils] Updated Ollama {provider_type} base_url: {base_url}")
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to update base_url: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def get_ollama_base_url(provider_type: str, provider_config: dict = None) -> str:
    """
    Get Ollama base_url from settings.json or provider config.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        provider_config: Optional provider config dict with default base_url
    
    Returns:
        Base URL string
    """
    # Start with provider default or fallback
    base_url = provider_config.get('base_url', 'http://localhost:11434') if provider_config else 'http://localhost:11434'
    
    # Try to get from settings.json
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if main_window:
            general_settings = main_window.config_manager.general_settings
            
            if provider_type == 'llm':
                settings_url = general_settings.ollama_llm_base_url
            elif provider_type == 'embedding':
                settings_url = general_settings.ollama_embedding_base_url
            elif provider_type == 'rerank':
                settings_url = general_settings.ollama_rerank_base_url
            else:
                logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
                return base_url
            
            if settings_url:
                base_url = settings_url
                logger.debug(f"[ProviderUtils] Using Ollama {provider_type} base_url from settings.json: {base_url}")
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not get ollama_{provider_type}_base_url from settings: {e}")
    
    return base_url


def get_ollama_api_key(provider_type: str) -> str:
    """
    Get Ollama API key from Secure Store.
    
    Args:
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        API key string (or 'ollama' as dummy if not configured)
    """
    try:
        from utils.env.env_utils import get_api_key
        
        # Determine the environment variable name based on provider type
        if provider_type == 'llm':
            env_var = 'OLLAMA_LLM_API_KEY'
        elif provider_type == 'embedding':
            env_var = 'OLLAMA_EMBEDDING_API_KEY'
        elif provider_type == 'rerank':
            env_var = 'OLLAMA_RERANK_API_KEY'
        else:
            logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
            return "ollama"
        
        api_key = get_api_key(env_var)
        if not api_key:
            # For local Ollama without authentication, use dummy key
            logger.debug(f"[ProviderUtils] {env_var} not configured, using dummy key for local access")
            return "ollama"
        
        return api_key
    except Exception as e:
        logger.debug(f"[ProviderUtils] Failed to get Ollama API key: {e}")
        return "ollama"


def save_general_settings_if_needed(base_url_updated: bool, auto_set_as_default: bool) -> bool:
    """
    Save general_settings if any updates were made.
    
    Args:
        base_url_updated: Whether base_url was updated
        auto_set_as_default: Whether default provider was auto-set
    
    Returns:
        True if saved successfully or no save needed, False otherwise
    """
    if not (base_url_updated or auto_set_as_default):
        return True  # No save needed
    
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            logger.error("[ProviderUtils] Cannot save: main_window not available")
            return False
        
        general_settings = main_window.config_manager.general_settings
        success = general_settings.save()
        
        if success:
            logger.info("[ProviderUtils] Saved general_settings (base_url and/or default provider)")
        else:
            logger.error("[ProviderUtils] Failed to save general_settings")
        
        return success
        
    except Exception as e:
        logger.error(f"[ProviderUtils] Failed to save general_settings: {e}")
        return False
