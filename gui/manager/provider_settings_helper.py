"""
Provider configuration utilities
Common functions for handling provider updates (LLM, Embedding, Rerank)
"""
from typing import Optional, Tuple
from utils.logger_helper import logger_helper as logger


def sync_account_api_key_to_ecanai(api_key: str, main_window=None) -> Tuple[bool, Optional[str]]:
    """Store an account API key for all eCanAI provider roles and apply it."""
    value = str(api_key or '').strip()
    if not value:
        return False, 'Account API key is empty'

    try:
        if main_window is None:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
        if not main_window or not getattr(main_window, 'config_manager', None):
            return False, 'Main window is not initialized'

        config_manager = main_window.config_manager
        role_config = (
            ('llm', config_manager.llm_manager, 'ECANAI_LLM_API_KEY'),
            ('embedding', config_manager.embedding_manager, 'ECANAI_EMBEDDING_API_KEY'),
            ('rerank', config_manager.rerank_manager, 'ECANAI_RERANK_API_KEY'),
        )
        for role, manager, env_var in role_config:
            success, error = manager.store_api_key(env_var, value)
            if not success:
                return False, f'Failed to store eCanAI {role} key: {error or "unknown error"}'

        general_settings = config_manager.general_settings
        active_roles = [
            role for role, _, _ in role_config
            if str(getattr(general_settings, f'default_{role}', '') or '').lower() == 'ecanai'
        ]

        # Apply the new credentials to active in-process clients.
        if 'llm' in active_roles and hasattr(main_window, 'update_all_llms'):
            try:
                main_window.update_all_llms(reason='eCanAI account API key synchronized')
            except Exception as exc:
                logger.warning(f'[ProviderUtils] Failed to hot-update eCanAI LLM: {exc}')

        agents = getattr(main_window, 'agents', None) or []
        for role, update_method in (('embedding', 'update_embeddings'), ('rerank', 'update_reranks')):
            if role not in active_roles:
                continue
            model_name = getattr(general_settings, f'default_{role}_model', '')
            for agent in agents:
                mem_manager = getattr(agent, 'mem_manager', None)
                if mem_manager and hasattr(mem_manager, update_method):
                    try:
                        getattr(mem_manager, update_method)(provider_name='ecanai', model_name=model_name)
                    except Exception as exc:
                        logger.warning(f'[ProviderUtils] Failed to update agent eCanAI {role}: {exc}')

        # This invalidates LightRAG's secure-key overlay. When eCanAI is active,
        # it also restarts the existing child process so the new env takes effect.
        if active_roles:
            invalidate_lightrag_provider_cache(active_roles[0], 'ecanai')
        else:
            invalidate_lightrag_provider_cache()

        try:
            # Do not import gui.LocalServer here: that module pulls in the full
            # browser stack and can initialize AppKit as a side effect. Broadcast
            # only when the application has already loaded LocalServer.
            import sys
            local_server_module = sys.modules.get('gui.LocalServer')
            app_ws_manager = getattr(local_server_module, 'app_ws_manager', None)
            if app_ws_manager:
                for role, _, _ in role_config:
                    app_ws_manager.broadcast_sync('lightrag.providersUpdated', {
                        'provider_type': role,
                        'provider': 'ecanai',
                    })
        except Exception as exc:
            logger.debug(f'[ProviderUtils] Could not broadcast eCanAI key sync: {exc}')

        logger.info('[ProviderUtils] Account API key synchronized to all eCanAI provider roles')
        return True, None
    except Exception as exc:
        logger.error(f'[ProviderUtils] Failed to synchronize account API key: {exc}')
        return False, str(exc)


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
        
        # Sync to lightrag.env if this provider is the currently active binding.
        # Without this, Settings saves to settings.json but LightRAG server reads
        # lightrag.env on next start, so the new address would be ignored until
        # the user also opens LightRAG Settings and saves there.
        _sync_base_url_to_lightrag_env(provider_lower, provider_type, base_url)

        logger.info(f"[ProviderUtils] Updated {provider_identifier} {provider_type} base_url: {base_url}")
        return True, None

    except Exception as e:
        error_msg = f"Failed to update base_url: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def _sync_base_url_to_lightrag_env(provider_identifier: str, provider_type: str, base_url: str):
    """
    If the given provider is the currently active LLM/Embedding/Rerank binding,
    write the new base_url into the workspace's lightrag.env so the next
    LightRAG server start picks it up without requiring a second save from the
    LightRAG Settings UI.

    Falls back gracefully if lightrag.env is unavailable.
    """
    try:
        binding_key_map = {
            'llm': 'LLM_BINDING',
            'embedding': 'EMBEDDING_BINDING',
            'rerank': 'RERANK_BINDING',
        }
        host_key_map = {
            'llm': 'LLM_BINDING_HOST',
            'embedding': 'EMBEDDING_BINDING_HOST',
            'rerank': 'RERANK_BINDING_HOST',
        }
        binding_key = binding_key_map.get(provider_type)
        host_key = host_key_map.get(provider_type)
        if not binding_key or not host_key:
            return

        from knowledge.lightrag_config_manager import get_config_manager as get_lr_config
        lr_config = get_lr_config()

        # Check if this provider is the active binding
        current_binding = lr_config.get_value(binding_key, '')
        if current_binding.lower() != provider_identifier.lower():
            logger.debug(
                f"[ProviderUtils] {provider_identifier} is not the active {binding_key} "
                f"(active={current_binding}), skipping lightrag.env sync"
            )
            return

        # Write directly into lightrag.env
        lr_config.update_config({host_key: base_url})
        logger.info(
            f"[ProviderUtils] Synced {provider_identifier} → lightrag.env "
            f"{host_key}={base_url}"
        )
    except Exception as e:
        logger.debug(f"[ProviderUtils] Could not sync base_url to lightrag.env: {e}")


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

    # Safety: only allow ollama/ryoais to prevent misuse with cloud providers
    if provider_lower not in ['ollama', 'ryoais']:
        if provider_config:
            return provider_config.get('base_url', '') if isinstance(provider_config, dict) else getattr(provider_config, 'base_url', '')
        return ''
    
    # Get base_url from provider_config (fallback)
    default_url = 'http://localhost/v1' if provider_lower == 'ryoais' else 'http://localhost:11434'
    if provider_config:
        base_url = provider_config.get('base_url', default_url) if isinstance(provider_config, dict) else getattr(provider_config, 'base_url', default_url)
    else:
        base_url = default_url
    
    # Override with settings.json if available
    try:
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return base_url
        
        general_settings = main_window.config_manager.general_settings
        settings_map = {
            'llm': (general_settings.ryoais_llm_base_url, general_settings.ollama_llm_base_url),
            'embedding': (general_settings.ryoais_embedding_base_url, general_settings.ollama_embedding_base_url),
            'rerank': (general_settings.ryoais_rerank_base_url, general_settings.ollama_rerank_base_url),
        }
        
        if provider_type not in settings_map:
            logger.warning(f"[ProviderUtils] Unknown provider_type: {provider_type}")
            return base_url
        
        settings_url = settings_map[provider_type][0 if provider_lower == 'ryoais' else 1]
        if settings_url:
            logger.debug(f"[ProviderUtils] Using {provider_identifier} {provider_type} base_url from settings.json: {settings_url}")
            return settings_url
            
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


def update_ollama_model(
    provider_identifier: str,
    model_name: str,
    provider_type: str  # 'llm', 'embedding', or 'rerank'
) -> Tuple[bool, Optional[str]]:
    """
    Update Ollama/RyoAIS model selection in settings.json.
    
    Args:
        provider_identifier: Provider identifier (e.g., 'ollama', 'ryoais')
        model_name: Model name to save
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        if provider_identifier.lower() not in ['ollama', 'ryoais']:
            return False, f"update_ollama_model only supports 'ollama' or 'ryoais', got '{provider_identifier}'"
        
        from app_context import AppContext
        main_window = AppContext.get_main_window()
        
        if not main_window:
            error_msg = "Cannot update model: main_window not available"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        # Update model in memory (don't save yet, will be saved by caller)
        general_settings = main_window.config_manager.general_settings
        provider_lower = provider_identifier.lower()
        
        if provider_type == 'llm':
            if provider_lower == 'ollama':
                general_settings.ollama_llm_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_llm_model = model_name
        elif provider_type == 'embedding':
            if provider_lower == 'ollama':
                general_settings.ollama_embedding_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_embedding_model = model_name
        elif provider_type == 'rerank':
            if provider_lower == 'ollama':
                general_settings.ollama_rerank_model = model_name
            elif provider_lower == 'ryoais':
                general_settings.ryoais_rerank_model = model_name
        else:
            error_msg = f"Unknown provider_type: {provider_type}"
            logger.error(f"[ProviderUtils] {error_msg}")
            return False, error_msg
        
        logger.info(f"[ProviderUtils] Updated {provider_identifier} {provider_type} model: {model_name}")
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to update model: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        return False, error_msg


def handle_provider_model_update(
    ctx,
    provider_identifier: str,
    model_name: str,
    provider_type: str,  # 'llm', 'embedding', or 'rerank'
    manager,
    updated_provider: dict
) -> Tuple[bool, Optional[str]]:
    """
    Unified handler for provider model updates across LLM, Embedding, and Rerank.
    
    Handles:
    1. Local provider (Ollama/RyoAIS) model persistence to settings.json
    2. Default provider model update
    3. Hot-update of active instances (LLMs, embeddings, reranks)
    
    Args:
        ctx: Handler context with config_manager and main_window
        provider_identifier: Provider name (e.g., 'ollama', 'openai')
        model_name: Model name to set
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
        manager: Provider manager instance (llm_manager, embedding_manager, or rerank_manager)
        updated_provider: Updated provider info dict
    
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Step 1: For local providers (Ollama, RyoAIS), save model selection to settings.json
        model_updated = False
        if provider_identifier.lower() in ['ollama', 'ryoais']:
            success_model, error_msg_model = update_ollama_model(provider_identifier, model_name, provider_type)
            if success_model:
                model_updated = True
                # Save immediately for local providers
                save_general_settings_if_needed(False, False, model_updated)
            elif error_msg_model:
                logger.warning(f"[{provider_type.upper()}] Failed to update model in settings: {error_msg_model}")
        
        # Step 2: If this is the current default provider, also update default_xxx_model
        general_settings = ctx.get_config_manager().general_settings
        
        # Get current default provider based on type
        if provider_type == 'llm':
            current_default = (general_settings.default_llm or "").lower()
            default_model_attr = 'default_llm_model'
        elif provider_type == 'embedding':
            current_default = (general_settings.default_embedding or "").lower()
            default_model_attr = 'default_embedding_model'
        elif provider_type == 'rerank':
            current_default = (general_settings.default_rerank or "").lower()
            default_model_attr = 'default_rerank_model'
        else:
            return False, f"Unknown provider_type: {provider_type}"
        
        # Update default model if this is the default provider
        default_updated = False
        if current_default == (provider_identifier or "").lower():
            setattr(general_settings, default_model_attr, model_name)
            general_settings.save()
            default_updated = True
            logger.info(f"[{provider_type.upper()}] Updated {default_model_attr} to {model_name} for current provider {provider_identifier}")
            
            # Step 3: Hot-update active instances
            _perform_hot_update(ctx, provider_type, provider_identifier, model_name, updated_provider)
        
        return True, None
        
    except Exception as e:
        error_msg = f"Failed to handle provider model update: {e}"
        logger.error(f"[ProviderUtils] {error_msg}")
        import traceback
        logger.error(traceback.format_exc())
        return False, error_msg


def _perform_hot_update(ctx, provider_type: str, provider_identifier: str, model_name: str, updated_provider: dict):
    """
    Perform hot-update of active instances based on provider type.
    
    Args:
        ctx: Handler context
        provider_type: 'llm', 'embedding', or 'rerank'
        provider_identifier: Provider name
        model_name: New model name
        updated_provider: Updated provider info
    """
    try:
        if provider_type == 'llm':
            # Hot-update: Use unified method to update all LLMs (including browser_use)
            provider_info = f"{updated_provider.get('display_name', provider_identifier)}, Model: {model_name}"
            update_success = ctx.main_window.update_all_llms(reason=f"Model changed to {provider_info}")
            
            if not update_success:
                logger.warning(f"[LLM] Failed to update LLM instances after model change, but settings were saved")
        
        elif provider_type in ['embedding', 'rerank']:
            # Hot-update: Update all agents' memoryManager embeddings/reranks
            if ctx.get_agents():
                updated_agents = 0
                update_method = 'update_embeddings' if provider_type == 'embedding' else 'update_reranks'
                
                for agent in ctx.get_agents():
                    if hasattr(agent, 'mem_manager') and agent.mem_manager:
                        try:
                            getattr(agent.mem_manager, update_method)(provider_name=provider_identifier, model_name=model_name)
                            updated_agents += 1
                            logger.debug(f"[{provider_type.upper()}] Updated {provider_type} for agent: {agent.card.name}")
                        except Exception as e:
                            logger.warning(f"[{provider_type.upper()}] Failed to update {provider_type} for agent {agent.card.name}: {e}")
                
                logger.info(f"[{provider_type.upper()}] ✅ Updated {provider_type} for {updated_agents} agents (model change)")
    
    except Exception as e:
        logger.error(f"[{provider_type.upper()}] ❌ Error during hot-update: {e}")
        logger.warning(f"Model settings updated but hot-update failed. Restart may be required for full effect.")


def save_general_settings_if_needed(base_url_updated: bool, auto_set_as_default: bool, model_updated: bool = False) -> bool:
    """
    Save general_settings if any updates were made.
    
    Args:
        base_url_updated: Whether base_url was updated
        auto_set_as_default: Whether default provider was auto-set
        model_updated: Whether model selection was updated
    
    Returns:
        True if saved successfully or no save needed, False otherwise
    """
    logger.debug(f"[ProviderUtils] save_general_settings_if_needed called: base_url_updated={base_url_updated}, auto_set_as_default={auto_set_as_default}, model_updated={model_updated}")
    
    if not (base_url_updated or auto_set_as_default or model_updated):
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
            logger.info("[ProviderUtils] ✅ Saved general_settings to disk (base_url and/or default provider and/or model)")
        else:
            logger.error("[ProviderUtils] ❌ Failed to save general_settings")
        
        return success
        
    except Exception as e:
        logger.error(f"[ProviderUtils] ❌ Exception while saving general_settings: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


def invalidate_lightrag_provider_cache(provider_type: str = '', provider_identifier: str = '') -> None:
    """Expose provider changes to LightRAG and restart it when eCanAI is active."""
    try:
        from knowledge.lightrag_config_manager import get_config_manager
        get_config_manager().invalidate_caches()

        if (provider_identifier or '').lower() != 'ecanai':
            return

        from app_context import AppContext
        main_window = AppContext.get_main_window()
        if not main_window:
            return
        general_settings = main_window.config_manager.general_settings
        active_provider = getattr(general_settings, f'default_{provider_type}', '')
        server = getattr(main_window, 'lightrag_server', None)
        if (active_provider or '').lower() != 'ecanai' or not server or not server.is_running():
            return

        # A running child process cannot receive new environment variables.
        # Match the server's existing proxy-change behaviour and restart away
        # from the IPC thread so saving provider settings remains responsive.
        import threading

        def restart_with_updated_env() -> None:
            try:
                logger.info('[ProviderUtils] Restarting LightRAG to apply eCanAI settings')
                server.stop()
                server.start(wait_ready=False)
            except Exception as exc:
                logger.error(f'[ProviderUtils] Failed to restart LightRAG: {exc}')

        threading.Thread(
            target=restart_with_updated_env,
            name='LightragECanAIProviderRestart',
            daemon=True,
        ).start()
    except Exception as exc:
        logger.warning(f"[ProviderUtils] Failed to invalidate LightRAG provider cache: {exc}")
