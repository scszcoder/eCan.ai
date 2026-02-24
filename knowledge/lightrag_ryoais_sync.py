"""
LightRAG RyoAIS Model Synchronization

This module provides functionality to synchronize RyoAIS model configurations
before starting LightRAG server. It detects the current running model from RyoAIS
and updates the lightrag.env configuration if changes are detected.
"""

import logging
from typing import Dict, Optional, Tuple
from utils.logger_helper import logger_helper as logger


def _get_provider_config(manager, provider_name: str, provider_type: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Get RyoAIS provider configuration (base_url and api_key) from manager.
    
    This is the unified method to get provider configuration, avoiding code duplication
    and ensuring consistency across LLM/Embedding/Rerank providers.
    
    Args:
        manager: Provider manager instance (llm_manager/embedding_manager/rerank_manager)
        provider_name: Provider name (e.g., 'ryoais')
        provider_type: Provider type for logging (e.g., 'LLM', 'Embedding', 'Rerank')
    
    Returns:
        Tuple of (base_url, api_key) or (None, None) if not found
    """
    if not manager:
        logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  {provider_type} manager not available")
        return None, None
    
    try:
        provider = manager.get_provider(provider_name)
        if not provider:
            logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  {provider_name} provider not found in {provider_type} manager")
            return None, None
        
        base_url = provider.get('base_url', '')
        if not base_url:
            logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  {provider_name} provider has no base_url configured")
            return None, None
        
        logger.info(f"[LightRAG-RyoAIS-Sync] 📍 Got {provider_name} {provider_type} base_url from manager: {base_url}")
        
        # Try to get API key
        api_key = None
        api_key_env_vars = provider.get('api_key_env_vars', [])
        if api_key_env_vars:
            for env_var in api_key_env_vars:
                key = manager.retrieve_api_key(env_var)
                if key:
                    api_key = key
                    break
        
        return base_url, api_key
        
    except Exception as e:
        logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  Error getting {provider_name} provider from {provider_type} manager: {e}")
        return None, None


def sync_ryoais_models_for_lightrag(current_config: Dict[str, str]) -> Tuple[bool, Dict[str, str]]:
    """
    Synchronize RyoAIS model configurations before starting LightRAG.
    
    This function checks if any provider (LLM/Embedding/Rerank) is configured to use RyoAIS,
    and if so, fetches the current running model from RyoAIS API. If the current model
    differs from the configured model, it updates the configuration.
    
    IMPORTANT: For rerank provider, we need to get the actual RyoAIS base_url from
    rerank_manager, not the proxy address from RERANK_BINDING_HOST in lightrag.env.
    
    Args:
        current_config: Current LightRAG configuration dict (from lightrag.env)
    
    Returns:
        Tuple of (updated: bool, new_config: dict)
        - updated: True if any configuration was changed
        - new_config: Updated configuration dict (same as input if no changes)
    """
    from gui.ryoais_utils import get_ryoais_current_model
    
    updated = False
    new_config = current_config.copy()
    
    logger.info("[LightRAG-RyoAIS-Sync] 🔍 Starting RyoAIS model synchronization check...")
    
    # Get manager instances for accessing provider configurations
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if main_window and hasattr(main_window, 'config_manager'):
            llm_manager = main_window.config_manager.llm_manager
            embedding_manager = main_window.config_manager.embedding_manager
            rerank_manager = main_window.config_manager.rerank_manager
        else:
            logger.warning("[LightRAG-RyoAIS-Sync] ⚠️  Cannot access managers, using config file values")
            llm_manager = None
            embedding_manager = None
            rerank_manager = None
    except Exception as e:
        logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  Error accessing managers: {e}")
        llm_manager = None
        embedding_manager = None
        rerank_manager = None
    
    # Check LLM provider
    llm_binding = current_config.get('LLM_BINDING', '').lower()
    if llm_binding == 'ryoais':
        logger.info("[LightRAG-RyoAIS-Sync] 📌 LLM provider is RyoAIS, checking current model...")
        
        llm_host, llm_api_key = _get_provider_config(llm_manager, 'ryoais', 'LLM')
        
        if llm_host:
            configured_model = current_config.get('LLM_MODEL', '')
            current_model = get_ryoais_current_model(llm_host, llm_api_key, 'llm')
            
            if current_model and current_model != configured_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] 🔄 LLM model changed: '{configured_model}' → '{current_model}'")
                new_config['LLM_MODEL'] = current_model
                updated = True
            elif current_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] ✅ LLM model unchanged: '{current_model}'")
            else:
                logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  Could not detect current LLM model, keeping configured: '{configured_model}'")
        else:
            logger.warning("[LightRAG-RyoAIS-Sync] ⚠️  Cannot get RyoAIS LLM provider configuration from manager")
    
    # Check Embedding provider
    embedding_binding = current_config.get('EMBEDDING_BINDING', '').lower()
    if embedding_binding == 'ryoais':
        logger.info("[LightRAG-RyoAIS-Sync] 📌 Embedding provider is RyoAIS, checking current model...")
        
        embedding_host, embedding_api_key = _get_provider_config(embedding_manager, 'ryoais', 'Embedding')
        
        if embedding_host:
            configured_model = current_config.get('EMBEDDING_MODEL', '')
            current_model = get_ryoais_current_model(embedding_host, embedding_api_key, 'embedding')
            
            if current_model and current_model != configured_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] 🔄 Embedding model changed: '{configured_model}' → '{current_model}'")
                new_config['EMBEDDING_MODEL'] = current_model
                updated = True
            elif current_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] ✅ Embedding model unchanged: '{current_model}'")
            else:
                logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  Could not detect current Embedding model, keeping configured: '{configured_model}'")
        else:
            logger.warning("[LightRAG-RyoAIS-Sync] ⚠️  Cannot get RyoAIS Embedding provider configuration from manager")
    
    # Check Rerank provider
    rerank_binding = current_config.get('RERANK_BINDING', '').lower()
    if rerank_binding == 'ryoais':
        logger.info("[LightRAG-RyoAIS-Sync] 📌 Rerank provider is RyoAIS, checking current model...")
        
        # IMPORTANT: For rerank, RERANK_BINDING_HOST in lightrag.env is the proxy address,
        # not the actual RyoAIS provider base_url. Must get it from rerank_manager.
        rerank_host, rerank_api_key = _get_provider_config(rerank_manager, 'ryoais', 'Rerank')
        
        if rerank_host:
            configured_model = current_config.get('RERANK_MODEL', '')
            current_model = get_ryoais_current_model(rerank_host, rerank_api_key, 'rerank')
            
            if current_model and current_model != configured_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] 🔄 Rerank model changed: '{configured_model}' → '{current_model}'")
                new_config['RERANK_MODEL'] = current_model
                updated = True
            elif current_model:
                logger.info(f"[LightRAG-RyoAIS-Sync] ✅ Rerank model unchanged: '{current_model}'")
            else:
                logger.warning(f"[LightRAG-RyoAIS-Sync] ⚠️  Could not detect current Rerank model, keeping configured: '{configured_model}'")
        else:
            logger.warning("[LightRAG-RyoAIS-Sync] ⚠️  Cannot get RyoAIS Rerank provider configuration from manager")
            logger.warning("[LightRAG-RyoAIS-Sync] ⚠️  Note: RERANK_BINDING_HOST in lightrag.env is proxy address, not RyoAIS base_url")
    
    # Summary
    if updated:
        logger.info("[LightRAG-RyoAIS-Sync] ✅ RyoAIS model synchronization completed with updates")
        logger.info("[LightRAG-RyoAIS-Sync] 📝 Updated configuration will be saved to lightrag.env")
    else:
        logger.info("[LightRAG-RyoAIS-Sync] ✅ RyoAIS model synchronization completed, no changes needed")
    
    return updated, new_config
