"""
Embedding management related IPC handlers - Similar to LLM handler architecture
"""
import os
from typing import Optional, Dict, Any
from ..types import IPCRequest, IPCResponse, create_success_response, create_error_response
from ..registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
from app_context import AppContext


def validate_params(params: Optional[Dict[str, Any]], required_keys: list) -> tuple[bool, Dict[str, Any], str]:
    """Validate parameters"""
    if not params:
        return False, {}, "Missing parameters"

    for key in required_keys:
        if key not in params:
            return False, {}, f"Missing required parameter: {key}"

    return True, params, ""


def get_embedding_manager():
    """Get Embedding manager instance"""
    main_window = AppContext.get_main_window()
    return main_window.config_manager.embedding_manager


@IPCHandlerRegistry.handler('get_embedding_providers')
def handle_get_embedding_providers(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get all Embedding providers with Ollama models merged"""
    try:
        from gui.ollama_utils import merge_ollama_models_to_providers
        
        embedding_manager = get_embedding_manager()
        providers = embedding_manager.get_all_providers()
        
        # Merge Ollama models using shared utility
        providers = merge_ollama_models_to_providers(providers, provider_type='embedding')
        
        logger.info(f"Retrieved {len(providers)} Embedding providers")

        # Include current settings for frontend
        main_window = AppContext.get_main_window()
        settings = {}
        if main_window:
            general_settings = main_window.config_manager.general_settings
            settings = {
                'default_embedding': general_settings.default_embedding,
                'default_embedding_model': general_settings.default_embedding_model
            }

        return create_success_response(request, {
            'providers': providers,
            'settings': settings,
            'message': 'Embedding providers retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting Embedding providers: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to get Embedding providers: {str(e)}")


@IPCHandlerRegistry.handler('update_embedding_provider')
def handle_update_embedding_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Update Embedding provider configuration"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        embedding_manager = get_embedding_manager()
        # Frontend MUST send standard provider identifier (e.g., "openai", "dashscope", "azure_openai")
        # NOT name or display_name (e.g., NOT "OpenAI", "Qwen (DashScope)")
        provider_identifier = (data.get('name') or "").strip()
        if not provider_identifier:
            return create_error_response(request, 'INVALID_PARAMS', "Provider identifier is required")
        
        api_key = data.get('api_key')
        azure_endpoint = data.get('azure_endpoint')
        base_url = data.get('base_url')  # Support updating base_url for local providers like Ollama

        # Get provider by standard identifier (case-insensitive)
        provider = embedding_manager.get_provider(provider_identifier)
        if not provider:
            # Provide helpful error message with available identifiers
            all_providers = embedding_manager.get_all_providers()
            available_ids = [p.get("provider") for p in all_providers if p.get("provider")]
            return create_error_response(
                request, 
                'EMBEDDING_ERROR', 
                f"Provider identifier '{provider_identifier}' not found. "
                f"Available identifiers: {', '.join(available_ids[:5])}{'...' if len(available_ids) > 5 else ''}"
            )

        # Get environment variable names for this provider
        env_vars = provider.get('api_key_env_vars', [])

        # Store API keys based on provider type
        api_key_stored = False
        
        # Handle special cases requiring multiple credentials
        if provider_identifier == 'azure_openai':
            if azure_endpoint:
                # Store Azure endpoint
                if 'AZURE_ENDPOINT' in env_vars:
                    success, error_msg = embedding_manager.store_api_key('AZURE_ENDPOINT', azure_endpoint)
                    if not success:
                        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to store Azure endpoint: {error_msg}")
                    api_key_stored = True

            if api_key:
                # Store Azure OpenAI API key
                if 'AZURE_OPENAI_API_KEY' in env_vars:
                    success, error_msg = embedding_manager.store_api_key('AZURE_OPENAI_API_KEY', api_key)
                    if not success:
                        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to store API key: {error_msg}")
                    api_key_stored = True

        else:
            # Handle other providers - use first environment variable to store API key
            if api_key and env_vars:
                env_var = env_vars[0]  # Use first environment variable
                success, error_msg = embedding_manager.store_api_key(env_var, api_key)
                if not success:
                    return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to store API key: {error_msg}")
                api_key_stored = True

        # Update base_url for local providers (e.g., Ollama)
        # Note: We don't save here, will save together with other settings below
        base_url_updated = False
        if base_url and provider.get('is_local', False):
            from gui.manager.provider_settings_helper import update_ollama_base_url
            success, error_msg = update_ollama_base_url(provider_identifier, base_url, 'embedding')
            if success:
                base_url_updated = True
            elif error_msg:
                logger.warning(f"Failed to update base_url: {error_msg}")

        # Auto-set as default_embedding if no default is set or if this is the only configured provider
        # Combine all general_settings updates and save once
        auto_set_as_default = False
        if api_key_stored or base_url_updated:
            try:
                main_window = AppContext.get_main_window()
                if main_window:
                    general_settings = main_window.config_manager.general_settings
                    current_default = general_settings.default_embedding
                    
                    configured_providers = []
                    for p in embedding_manager.get_all_providers():
                        if p.get('api_key_configured', False):
                            configured_providers.append(p['provider'])
                    
                    # Auto-set if:
                    # 1. No default is set, OR
                    # 2. This is the only configured provider
                    should_auto_set = (not current_default or current_default.strip() == "") or \
                                     (len(configured_providers) == 1 and configured_providers[0] == provider_identifier)
                    
                    if should_auto_set:
                        general_settings.default_embedding = provider_identifier
                        # Always update default model when auto-setting provider
                        default_model = provider.get('default_model') or provider.get('preferred_model')
                        if default_model:
                            general_settings.default_embedding_model = default_model
                            logger.info(f"Auto-set default embedding model to {default_model}")
                        else:
                            # Fallback to provider's default model
                            provider_config = embedding_manager.get_provider(provider_identifier)
                            if provider_config:
                                fallback_model = provider_config.get('default_model', 'text-embedding-3-small')
                                general_settings.default_embedding_model = fallback_model
                                logger.info(f"Auto-set default embedding model to {fallback_model} (fallback)")
                        auto_set_as_default = True
                        logger.info(f"Auto-set {provider_identifier} as default_embedding")
                    
                    # Save all general_settings changes at once (base_url + auto-set default)
                    from gui.manager.provider_settings_helper import save_general_settings_if_needed
                    save_general_settings_if_needed(base_url_updated, auto_set_as_default)
            except Exception as e:
                logger.warning(f"Failed to auto-set default_embedding: {e}")

        logger.info(f"Updated Embedding provider: {provider_identifier}")
        
        # Find shared LLM providers that use the same API keys
        from gui.ipc.w2p_handlers.llm_handler import find_shared_providers
        shared_providers = find_shared_providers(env_vars, 'embedding')
        
        # Get updated provider info for frontend
        updated_provider = embedding_manager.get_provider(provider_identifier)
        
        # Build response with auto-set information and updated provider
        main_window = AppContext.get_main_window()
        response_data = {
            'message': f'Embedding provider {provider_identifier} updated successfully',
            'provider': updated_provider
        }
        
        # Include shared providers info so frontend can refresh both LLM and Embedding UI
        # Always include shared_providers in response (even if empty) for consistency
        response_data['shared_providers'] = shared_providers
        if shared_providers:
            logger.info(f"[Embedding] Found {len(shared_providers)} shared LLM providers: {[p['name'] for p in shared_providers]}")
        else:
            logger.debug(f"[Embedding] No shared LLM providers found for {provider_identifier}")
        
        # Always include current settings for frontend UI update
        if main_window:
            response_data['settings'] = {
                'default_embedding': main_window.config_manager.general_settings.default_embedding,
                'default_embedding_model': main_window.config_manager.general_settings.default_embedding_model
            }
        
        if auto_set_as_default:
            response_data['auto_set_as_default'] = True
            response_data['default_embedding'] = provider_identifier
            default_model = provider.get('default_model') or provider.get('preferred_model')
            response_data['default_embedding_model'] = default_model
            
            # Hot-update: Update all agents' memoryManager embeddings (similar to update_all_llms)
            if main_window and default_model and hasattr(main_window, 'agents') and main_window.agents:
                try:
                    updated_agents = 0
                    for agent in main_window.agents:
                        # Update memoryManager embeddings
                        if hasattr(agent, 'mem_manager') and agent.mem_manager:
                            try:
                                agent.mem_manager.update_embeddings(provider_name=provider_identifier, model_name=default_model)
                                updated_agents += 1
                                logger.debug(f"[Embedding] Updated embeddings for agent: {agent.card.name}")
                            except Exception as e:
                                logger.warning(f"[Embedding] Failed to update embeddings for agent {agent.card.name}: {e}")
                    
                    logger.info(f"[Embedding] ✅ Updated embeddings for {updated_agents} agents (auto-set)")
                except Exception as e:
                    logger.error(f"[Embedding] ❌ Error updating agent embeddings: {e}")
        
        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"Error updating Embedding provider: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to update Embedding provider: {str(e)}")


@IPCHandlerRegistry.handler('set_embedding_provider_model')
def handle_set_embedding_provider_model(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Set the default model for an Embedding provider"""
    try:
        is_valid, data, error = validate_params(params, ['name', 'model'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        # Frontend MUST send standard provider identifier (e.g., "openai", "dashscope")
        provider_identifier = (data.get('name') or "").strip()
        if not provider_identifier:
            return create_error_response(request, 'INVALID_PARAMS', "Provider identifier is required")
        
        model_name = data['model']

        embedding_manager = get_embedding_manager()
        main_window = AppContext.get_main_window()
        
        # Get provider by standard identifier (case-insensitive)
        provider = embedding_manager.get_provider(provider_identifier)
        if not provider:
            all_providers = embedding_manager.get_all_providers()
            available_ids = [p.get("provider") for p in all_providers if p.get("provider")]
            return create_error_response(
                request, 
                'EMBEDDING_ERROR', 
                f"Provider identifier '{provider_identifier}' not found. "
                f"Available identifiers: {', '.join(available_ids[:5])}{'...' if len(available_ids) > 5 else ''}"
            )
        
        # Update provider's default model
        success, error_msg = embedding_manager.set_provider_default_model(provider_identifier, model_name)

        if not success:
            return create_error_response(request, 'EMBEDDING_ERROR', error_msg or 'Failed to update model')

        updated_provider = embedding_manager.get_provider(provider_identifier)
        
        # If this is the current default embedding, also update default_embedding_model in general_settings (case-insensitive)
        current_default = (main_window.config_manager.general_settings.default_embedding or "").lower()
        if current_default == (provider_identifier or "").lower():
            main_window.config_manager.general_settings.default_embedding_model = model_name
            main_window.config_manager.general_settings.save()
            logger.info(f"[Embedding] Updated default_embedding_model to {model_name} for current provider {provider_identifier}")
            
            # Hot-update: Update all agents' memoryManager embeddings (similar to update_all_llms)
            if hasattr(main_window, 'agents') and main_window.agents:
                try:
                    updated_agents = 0
                    for agent in main_window.agents:
                        # Update memoryManager embeddings
                        if hasattr(agent, 'mem_manager') and agent.mem_manager:
                            try:
                                agent.mem_manager.update_embeddings(provider_name=provider_identifier, model_name=model_name)
                                updated_agents += 1
                                logger.debug(f"[Embedding] Updated embeddings for agent: {agent.card.name}")
                            except Exception as e:
                                logger.warning(f"[Embedding] Failed to update embeddings for agent {agent.card.name}: {e}")
                    
                    logger.info(f"[Embedding] ✅ Updated embeddings for {updated_agents} agents (model change)")
                except Exception as e:
                    logger.error(f"[Embedding] ❌ Error updating agent embeddings: {e}")

        return create_success_response(request, {
            'message': f'Default model for {provider_identifier} updated successfully',
            'provider': updated_provider,
            'settings': {
                'default_embedding': main_window.config_manager.general_settings.default_embedding,
                'default_embedding_model': main_window.config_manager.general_settings.default_embedding_model
            }
        })

    except Exception as e:
        logger.error(f"Error setting default model for provider {params}: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to set default model: {str(e)}")


@IPCHandlerRegistry.handler('delete_embedding_provider_config')
def handle_delete_embedding_provider_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete Embedding provider configuration"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        embedding_manager = get_embedding_manager()
        main_window = AppContext.get_main_window()
        # Frontend MUST send standard provider identifier
        provider_identifier = (data.get('name') or "").strip()
        if not provider_identifier:
            return create_error_response(request, 'INVALID_PARAMS', "Provider identifier is required")
        
        username = data.get('username', '')

        # Get provider by standard identifier (case-insensitive)
        provider = embedding_manager.get_provider(provider_identifier)
        if not provider:
            all_providers = embedding_manager.get_all_providers()
            available_ids = [p.get("provider") for p in all_providers if p.get("provider")]
            return create_error_response(
                request, 
                'EMBEDDING_ERROR', 
                f"Provider identifier '{provider_identifier}' not found. "
                f"Available identifiers: {', '.join(available_ids[:5])}{'...' if len(available_ids) > 5 else ''}"
            )

        # Check if this is the current default embedding (case-insensitive)
        current_default_embedding = (main_window.config_manager.general_settings.default_embedding or "").lower()
        is_default_embedding = (current_default_embedding == (provider_identifier or "").lower())

        # Delete API key and other credentials from environment variables
        env_vars = provider.get('api_key_env_vars', [])
        deleted_vars = []
        failed_vars = []
        
        for env_var in env_vars:
            logger.debug(f"Deleting environment variable {env_var} for provider {provider_identifier}")

            if env_var in os.environ:
                del os.environ[env_var]
                logger.debug(f"Removed {env_var} from current session")

            try:
                success = embedding_manager.delete_api_key(env_var)

                if os.environ.get(env_var):
                    logger.warning(f"Environment variable {env_var} still present in process environment after deletion attempt")

                if success:
                    deleted_vars.append(env_var)
                else:
                    failed_vars.append(env_var)
                    logger.warning(f"Failed to delete environment variable {env_var} from persistent configuration")
            except Exception as e:
                failed_vars.append(env_var)
                logger.error(f"Error deleting environment variable {env_var}: {e}", exc_info=True)
        
        if deleted_vars:
            logger.info(f"Deleted Embedding provider config {provider_identifier}, removed environment variables: {deleted_vars}")
        if failed_vars:
            logger.warning(f"Failed to delete some environment variables for {provider_identifier}: {failed_vars}")

        # Check if we need to update default embedding after deletion
        new_default_embedding = None
        new_default_model = None
        
        # Get all providers and find configured ones after deletion
        all_providers = embedding_manager.get_all_providers()
        configured_providers = [p for p in all_providers if p.get('api_key_configured', False)]
        
        # Case 1: Deleted the current default embedding
        # Case 2: No providers are configured anymore (all API keys deleted)
        should_update_default = is_default_embedding or (len(configured_providers) == 0)
        
        if should_update_default:
            if is_default_embedding:
                logger.info(f"Provider {provider_identifier} was the default embedding, selecting a new default")
            else:
                logger.info("All API keys deleted, resetting to default OpenAI provider")
            
            if configured_providers:
                # Select the first available configured provider
                new_provider = configured_providers[0]
                new_default_embedding = new_provider.get('provider')  # Use provider identifier
                new_default_model = new_provider.get('preferred_model') or new_provider.get('default_model') or ''
                logger.info(f"Selected new default Embedding {new_default_embedding} with model {new_default_model}")
            else:
                # No providers are configured, default to OpenAI with its default model
                new_default_embedding = 'openai'
                try:
                    openai_provider = embedding_manager.get_provider('openai')
                    new_default_model = openai_provider.get('default_model', 'text-embedding-3-small') if openai_provider else 'text-embedding-3-small'
                except:
                    new_default_model = 'text-embedding-3-small'
                logger.info(f"No configured providers found; defaulting to {new_default_embedding} with model {new_default_model} (no API key)")
            
            # Update default_embedding setting
            main_window.config_manager.general_settings.default_embedding = new_default_embedding
            main_window.config_manager.general_settings.default_embedding_model = new_default_model
            save_result = main_window.config_manager.general_settings.save()
            
            if not save_result:
                logger.error(f"Failed to save new default Embedding setting")
                return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to save new default Embedding setting")
            
            # Hot-update: Update all agents' memoryManager embeddings after switching default
            if new_default_embedding and new_default_model and hasattr(main_window, 'agents') and main_window.agents:
                try:
                    updated_agents = 0
                    for agent in main_window.agents:
                        # Update memoryManager embeddings
                        if hasattr(agent, 'mem_manager') and agent.mem_manager:
                            try:
                                agent.mem_manager.update_embeddings(provider_name=new_default_embedding, model_name=new_default_model)
                                updated_agents += 1
                                logger.debug(f"[Embedding] Updated embeddings for agent: {agent.card.name}")
                            except Exception as e:
                                logger.warning(f"[Embedding] Failed to update embeddings for agent {agent.card.name}: {e}")
                    
                    logger.info(f"[Embedding] ✅ Updated embeddings for {updated_agents} agents (after deletion)")
                except Exception as e:
                    logger.error(f"[Embedding] ❌ Error updating agent embeddings: {e}")

        # Find shared LLM providers that use the same API keys
        from gui.ipc.w2p_handlers.llm_handler import find_shared_providers
        shared_providers = find_shared_providers(env_vars, 'embedding')
        
        # Get updated provider info for frontend
        updated_provider = embedding_manager.get_provider(provider_identifier)
        
        response_data = {
            'message': f'Embedding provider {provider_identifier} configuration deleted successfully',
            'deleted_env_vars': deleted_vars,
            'was_default_embedding': is_default_embedding,
            'provider': updated_provider
        }
        
        # Include shared providers info so frontend can refresh both LLM and Embedding UI
        # Always include shared_providers in response (even if empty) for consistency
        response_data['shared_providers'] = shared_providers
        if shared_providers:
            logger.info(f"[Embedding] Found {len(shared_providers)} shared LLM providers affected by deletion: {[p['name'] for p in shared_providers]}")
        else:
            logger.debug(f"[Embedding] No shared LLM providers affected by deletion of {provider_identifier}")
        
        # Always include current settings for frontend UI update
        response_data['settings'] = {
            'default_embedding': main_window.config_manager.general_settings.default_embedding,
            'default_embedding_model': main_window.config_manager.general_settings.default_embedding_model
        }
        
        # Include new default settings if changed
        if should_update_default and new_default_embedding:
            response_data['new_default_embedding'] = new_default_embedding
            response_data['new_default_model'] = new_default_model
            response_data['reset_to_default'] = (len(configured_providers) == 0)
        
        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"Error deleting Embedding provider config: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to delete Embedding provider config: {str(e)}")


@IPCHandlerRegistry.handler('set_default_embedding')
def handle_set_default_embedding(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Set default Embedding provider"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        name = data['name']  # May be name or provider identifier
        model = data.get('model')  # Optional model parameter from frontend

        embedding_manager = get_embedding_manager()
        main_window = AppContext.get_main_window()

        # Verify provider exists and is configured
        provider = embedding_manager.get_provider(name)
        if not provider:
            return create_error_response(request, 'EMBEDDING_ERROR', f"Provider {name} not found")
        
        # Use provider identifier for all operations
        provider_identifier = provider.get('provider')
        if not provider_identifier:
            return create_error_response(request, 'EMBEDDING_ERROR', f"Provider {name} has no provider identifier")

        if not provider['api_key_configured']:
            return create_error_response(request, 'EMBEDDING_ERROR', f"Provider {provider_identifier} is not configured")

        # Save current settings for potential rollback
        old_default_embedding = main_window.config_manager.general_settings.default_embedding
        old_default_model = main_window.config_manager.general_settings.default_embedding_model

        # Update default_embedding and default_embedding_model in general_settings
        main_window.config_manager.general_settings.default_embedding = provider_identifier
        
        # Use model from frontend if provided, otherwise fallback to provider's preferred/default model
        if model:
            provider_model = model
            logger.info(f"[Embedding] Using model from frontend: {model}")
        else:
            provider_model = provider.get('preferred_model') or provider.get('default_model') or ''
            logger.info(f"[Embedding] Using provider's model: {provider_model}")
        
        # Validate model belongs to this provider (safety check)
        supported_models = provider.get('supported_models', [])
        if supported_models:
            model_ids = [m.get('model_id', m.get('name', '')) for m in supported_models]
            if provider_model and provider_model not in model_ids:
                logger.warning(f"Model '{provider_model}' not found in provider '{name}' supported models: {model_ids}")
                logger.warning("Using provider's default model instead")
                provider_model = provider.get('default_model', '')
        
        main_window.config_manager.general_settings.default_embedding_model = provider_model
        
        save_result = main_window.config_manager.general_settings.save()

        if not save_result:
            return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to save default Embedding setting")

        logger.info(f"Default Embedding set to {provider_identifier} with model {provider_model}")
        
        # Hot-update: Update all agents' memoryManager embeddings (similar to update_all_llms)
        try:
            updated_agents = 0
            for agent in main_window.agents:
                # Update memoryManager embeddings
                if hasattr(agent, 'mem_manager') and agent.mem_manager:
                    try:
                        agent.mem_manager.update_embeddings(provider_name=provider_identifier, model_name=provider_model)
                        updated_agents += 1
                        logger.debug(f"[Embedding] Updated embeddings for agent: {agent.card.name}")
                    except Exception as e:
                        logger.warning(f"[Embedding] Failed to update embeddings for agent {agent.card.name}: {e}")
            
            logger.info(f"[Embedding] ✅ Updated embeddings for {updated_agents} agents")
        except Exception as e:
            logger.error(f"[Embedding] ❌ Error updating agent embeddings: {e}")
            # Don't fail the request if agent update fails, but log the error
        
        # Get updated provider info for frontend
        updated_provider = embedding_manager.get_provider(provider_identifier)
        
        return create_success_response(request, {
            'default_embedding': provider_identifier,
            'model_name': provider_model,
            'message': f'Default Embedding set to {provider_identifier} successfully (hot-updated {updated_agents} agents)',
            'provider': updated_provider,
            'settings': {
                'default_embedding': main_window.config_manager.general_settings.default_embedding,
                'default_embedding_model': main_window.config_manager.general_settings.default_embedding_model
            }
        })

    except Exception as e:
        logger.error(f"Error setting default Embedding: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to set default Embedding: {str(e)}")


@IPCHandlerRegistry.handler('get_default_embedding')
def handle_get_default_embedding(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get current default Embedding provider"""
    try:
        main_window = AppContext.get_main_window()
        if not main_window:
            return create_error_response(request, 'EMBEDDING_ERROR', "Main window not available")
        
        general_settings = main_window.config_manager.general_settings
        default_embedding = general_settings.default_embedding
        default_embedding_model = general_settings.default_embedding_model

        return create_success_response(request, {
            'default_embedding': default_embedding,
            'default_embedding_model': default_embedding_model,
            'message': 'Default Embedding retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting default Embedding: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to get default Embedding: {str(e)}")


@IPCHandlerRegistry.handler('get_embedding_provider_api_key')
def handle_get_embedding_provider_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get Embedding provider's API key (masked or full)"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        # Frontend MUST send standard provider identifier
        provider_identifier = (data.get('name') or "").strip()
        if not provider_identifier:
            return create_error_response(request, 'INVALID_PARAMS', "Provider identifier is required")
        
        show_full = data.get('show_full', False)  # Whether to show full API key

        embedding_manager = get_embedding_manager()

        # Get provider by standard identifier (case-insensitive)
        provider = embedding_manager.get_provider(provider_identifier)
        if not provider:
            all_providers = embedding_manager.get_all_providers()
            available_ids = [p.get("provider") for p in all_providers if p.get("provider")]
            return create_error_response(
                request, 
                'EMBEDDING_ERROR', 
                f"Provider identifier '{provider_identifier}' not found. "
                f"Available identifiers: {', '.join(available_ids[:5])}{'...' if len(available_ids) > 5 else ''}"
            )

        # Get API key environment variables
        env_vars = provider.get('api_key_env_vars', [])
        if not env_vars:
            return create_error_response(request, 'EMBEDDING_ERROR', f"Provider {provider_identifier} has no API key environment variables")

        # Handle special cases requiring multiple credentials
        if provider_identifier == 'azure_openai':
            result = {
                'provider_name': provider_identifier,
                'credentials': {},
                'is_masked': not show_full,
                'message': f'Credentials retrieved for {provider_identifier}'
            }

            # Get Azure endpoint
            if 'AZURE_ENDPOINT' in env_vars:
                if show_full:
                    endpoint = embedding_manager.retrieve_api_key('AZURE_ENDPOINT')
                else:
                    endpoint = embedding_manager._get_masked_api_key('AZURE_ENDPOINT')
                result['credentials']['azure_endpoint'] = endpoint

            # Get Azure OpenAI API key
            if 'AZURE_OPENAI_API_KEY' in env_vars:
                if show_full:
                    api_key = embedding_manager.retrieve_api_key('AZURE_OPENAI_API_KEY')
                else:
                    api_key = embedding_manager._get_masked_api_key('AZURE_OPENAI_API_KEY')
                result['credentials']['api_key'] = api_key

            return create_success_response(request, result)

        else:
            # Handle other providers - use first environment variable
            env_var = env_vars[0]  # Use first environment variable

            if show_full:
                # Return full API key (for display only, use with caution)
                api_key = embedding_manager.retrieve_api_key(env_var)
            else:
                # Return masked API key
                api_key = embedding_manager._get_masked_api_key(env_var)

            if api_key is None:
                return create_error_response(request, 'EMBEDDING_ERROR', f"No API key found for {provider_identifier}")

            return create_success_response(request, {
                'provider_name': provider_identifier,
                'env_var': env_var,
                'api_key': api_key,
                'is_masked': not show_full,
                'message': f'API key retrieved for {provider_identifier}'
            })

    except Exception as e:
        logger.error(f"Error getting Embedding provider API key: {e}")
        return create_error_response(request, 'EMBEDDING_ERROR', f"Failed to get API key: {str(e)}")



