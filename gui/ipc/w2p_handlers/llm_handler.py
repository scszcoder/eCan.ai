"""
LLM management related IPC handlers - Using original LLM manager architecture
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


def get_llm_manager():
    """Get LLM manager instance"""
    main_window = AppContext.get_main_window()
    return main_window.config_manager.llm_manager


def get_embedding_manager():
    """Get Embedding manager instance"""
    main_window = AppContext.get_main_window()
    return main_window.config_manager.embedding_manager


def get_rerank_manager():
    """Get Rerank manager instance"""
    main_window = AppContext.get_main_window()
    return main_window.config_manager.rerank_manager


def find_shared_providers(env_vars: list, provider_type: str) -> list:
    """
    Find providers in the other systems (LLM/Embedding/Rerank) that share the same API key env vars.
    
    Args:
        env_vars: List of environment variable names used by the current provider
        provider_type: 'llm', 'embedding', or 'rerank' to indicate which system we're updating
    
    Returns:
        List of provider dicts that share the same env_vars
    """
    shared_providers = []
    try:
        main_window = AppContext.get_main_window()
        if not main_window:
            logger.debug("find_shared_providers: main_window is None")
            return shared_providers
        
        if not hasattr(main_window, 'config_manager') or not main_window.config_manager:
            logger.debug("find_shared_providers: config_manager is not available")
            return shared_providers
        
        # Helper to check providers in a specific manager
        def check_manager(manager, type_name):
            if not manager:
                return
            try:
                all_providers = manager.get_all_providers()
                for provider in all_providers:
                    provider_env_vars = provider.get('api_key_env_vars', [])
                    if any(env_var in provider_env_vars for env_var in env_vars):
                        shared_providers.append({
                            'name': provider.get('provider'),  # Use standard identifier
                            'type': type_name,
                            'shared_env_vars': [ev for ev in env_vars if ev in provider_env_vars]
                        })
            except Exception as e:
                logger.debug(f"Error checking {type_name} providers: {e}")

        # Check other systems based on current provider type
        if provider_type != 'embedding':
            check_manager(get_embedding_manager(), 'embedding')
            
        if provider_type != 'llm':
            check_manager(get_llm_manager(), 'llm')
            
        if provider_type != 'rerank':
            check_manager(get_rerank_manager(), 'rerank')

    except Exception as e:
        logger.warning(f"Error finding shared providers: {e}", exc_info=True)
    
    return shared_providers


@IPCHandlerRegistry.handler('get_llm_providers')
def handle_get_llm_providers(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get all LLM providers"""
    try:
        llm_manager = get_llm_manager()
        providers = llm_manager.get_all_providers()
        logger.info(f"Retrieved {len(providers)} LLM providers")

        return create_success_response(request, {
            'providers': providers,
            'message': 'LLM providers retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting LLM providers: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get LLM providers: {str(e)}")


@IPCHandlerRegistry.handler('get_llm_provider')
def handle_get_llm_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get specified LLM provider"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        llm_manager = get_llm_manager()
        provider = llm_manager.get_provider(data['name'])
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {data['name']} not found")

        return create_success_response(request, {
            'provider': provider,
            'message': 'LLM provider retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting LLM provider: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get LLM provider: {str(e)}")


@IPCHandlerRegistry.handler('update_llm_provider')
def handle_update_llm_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Update LLM provider configuration"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        llm_manager = get_llm_manager()
        # Frontend MUST send standard provider identifier (e.g., "openai", "dashscope", "azure_openai")
        # NOT name or display_name (e.g., NOT "OpenAI", "Qwen (DashScope)")
        provider_identifier = (data.get('name') or "").strip()
        if not provider_identifier:
            return create_error_response(request, 'INVALID_PARAMS', "Provider identifier is required")
        
        api_key = data.get('api_key')
        azure_endpoint = data.get('azure_endpoint')

        # Get provider by standard identifier (case-insensitive)
        provider = llm_manager.get_provider(provider_identifier)
        if not provider:
            # Provide helpful error message with available identifiers
            all_providers = llm_manager.get_all_providers()
            available_ids = [p.get("provider") for p in all_providers if p.get("provider")]
            return create_error_response(
                request, 
                'LLM_ERROR', 
                f"Provider identifier '{provider_identifier}' not found. "
                f"Available identifiers: {', '.join(available_ids[:5])}{'...' if len(available_ids) > 5 else ''}"
            )

        # Get environment variable names for this provider
        env_vars = provider.get('api_key_env_vars', [])

        # Store API keys based on provider type
        api_key_stored = False
        
        # Handle special cases requiring multiple credentials
        if provider_identifier == 'baidu_qianfan':
            # Baidu Qianfan V2 API only requires BAIDU_API_KEY (OpenAI-compatible with Bearer token)
            if api_key and env_vars:
                # Use BAIDU_API_KEY if available, otherwise use first env_var
                env_var = 'BAIDU_API_KEY' if 'BAIDU_API_KEY' in env_vars else env_vars[0]
                success, error_msg = llm_manager.store_api_key(env_var, api_key)
                if not success:
                    return create_error_response(request, 'LLM_ERROR', f"Failed to store Baidu API key: {error_msg}")
                api_key_stored = True
        
        elif provider_identifier == 'azure_openai':
            if azure_endpoint:
                # Store Azure endpoint
                if 'AZURE_ENDPOINT' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_ENDPOINT', azure_endpoint)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store Azure endpoint: {error_msg}")
                    api_key_stored = True

            if api_key:
                # Store Azure OpenAI API key
                if 'AZURE_OPENAI_API_KEY' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_OPENAI_API_KEY', api_key)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store API key: {error_msg}")
                    api_key_stored = True

        elif provider_identifier == 'bedrock':
            # AWS Bedrock requires two credentials: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
            aws_access_key_id = data.get('aws_access_key_id')
            aws_secret_access_key = data.get('aws_secret_access_key')

            if aws_access_key_id:
                if 'AWS_ACCESS_KEY_ID' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AWS_ACCESS_KEY_ID', aws_access_key_id)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store AWS Access Key ID: {error_msg}")
                    api_key_stored = True

            if aws_secret_access_key:
                if 'AWS_SECRET_ACCESS_KEY' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AWS_SECRET_ACCESS_KEY', aws_secret_access_key)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store AWS Secret Access Key: {error_msg}")
                    api_key_stored = True

        else:
            # Handle other providers - use first environment variable to store API key
            if api_key and env_vars:
                env_var = env_vars[0]  # Use first environment variable
                success, error_msg = llm_manager.store_api_key(env_var, api_key)
                if not success:
                    return create_error_response(request, 'LLM_ERROR', f"Failed to store API key: {error_msg}")
                api_key_stored = True

        # Auto-set as default_llm if this is the only configured provider
        auto_set_as_default = False
        if api_key_stored:
            try:
                configured_providers = []
                for p in llm_manager.get_all_providers():
                    if p.get('api_key_configured', False):
                        configured_providers.append(p['provider'])
                
                # If only one provider is configured, set it as default
                if len(configured_providers) == 1 and configured_providers[0] == provider_identifier:
                    from app_context import AppContext
                    main_window = AppContext.get_main_window()
                    if main_window:
                        general_settings = main_window.config_manager.general_settings
                        general_settings.default_llm = provider_identifier
                        # Always update default model when auto-setting provider
                        default_model = provider.get('default_model')
                        if default_model:
                            general_settings.default_llm_model = default_model
                            logger.info(f"Auto-set default model to {default_model}")
                        general_settings.save()
                        auto_set_as_default = True
                        logger.info(f"Auto-set {provider_identifier} as default_llm (only configured provider)")
                        
                        # Hot-update LLM instances to use the new provider
                        try:
                            provider_info = f"{provider.get('display_name', provider_identifier)}, Model: {default_model}"
                            update_success = main_window.update_all_llms(reason=f"Default LLM changed to {provider_info}")
                            if update_success:
                                logger.info(f"Successfully hot-updated LLM instances to {provider_identifier}")
                            else:
                                logger.warning(f"Failed to hot-update LLM instances after setting default to {provider_identifier}")
                        except Exception as update_error:
                            logger.error(f"Error during hot-update of LLM instances: {update_error}")
            except Exception as e:
                logger.warning(f"Failed to auto-set default_llm: {e}")

        logger.info(f"Updated LLM provider: {provider_identifier}")
        
        # Find shared Embedding providers that use the same API keys
        shared_providers = find_shared_providers(env_vars, 'llm')
        
        # Get updated provider info for frontend
        updated_provider = llm_manager.get_provider(provider_identifier)
        
        # Build response with auto-set information and updated provider
        response_data = {
            'message': f'LLM provider {provider_identifier} updated successfully',
            'provider': updated_provider  # Include updated provider info for UI refresh
        }
        
        # Include shared providers info so frontend can refresh both LLM and Embedding UI
        # Always include shared_providers in response (even if empty) for consistency
        response_data['shared_providers'] = shared_providers
        if shared_providers:
            logger.info(f"[LLM] Found {len(shared_providers)} shared Embedding providers: {[p['name'] for p in shared_providers]}")
        else:
            logger.debug(f"[LLM] No shared Embedding providers found for {provider_identifier}")
        
        if auto_set_as_default:
            response_data['auto_set_as_default'] = True
            response_data['default_llm'] = provider_identifier
            response_data['default_llm_model'] = provider.get('default_model')
            # Also include current settings for frontend
            main_window = AppContext.get_main_window()
            if main_window:
                response_data['settings'] = {
                    'default_llm': main_window.config_manager.general_settings.default_llm,
                    'default_llm_model': main_window.config_manager.general_settings.default_llm_model
                }
        
        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"Error updating LLM provider: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to update LLM provider: {str(e)}")


@IPCHandlerRegistry.handler('set_llm_provider_model')
def handle_set_llm_provider_model(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Set the default model for an LLM provider and hot-update all LLM instances"""
    try:
        is_valid, data, error = validate_params(params, ['name', 'model'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        provider_name = data['name']
        model_name = data['model']

        llm_manager = get_llm_manager()
        main_window = AppContext.get_main_window()
        
        # Update provider's default model
        success, error_msg = llm_manager.set_provider_default_model(provider_name, model_name)

        if not success:
            return create_error_response(request, 'LLM_ERROR', error_msg or 'Failed to update model')

        updated_provider = llm_manager.get_provider(provider_name)
        
        # If this is the current default LLM, also update default_llm_model in general_settings (case-insensitive)
        current_default = (main_window.config_manager.general_settings.default_llm or "").lower()
        if current_default == (provider_name or "").lower():
            main_window.config_manager.general_settings.default_llm_model = model_name
            main_window.config_manager.general_settings.save()
            logger.info(f"[LLM] Updated default_llm_model to {model_name} for current provider {provider_name}")
            
            # Hot-update: Use unified method to update all LLMs (including browser_use)
            try:
                provider_info = f"{updated_provider.get('display_name', provider_name)}, Model: {model_name}"
                update_success = main_window.update_all_llms(reason=f"Model changed to {provider_info}")
                
                if not update_success:
                    logger.warning(f"Failed to update LLM instances after model change, but settings were saved")
                    # Still return success since the model setting was saved
                    
            except Exception as update_error:
                logger.error(f"Error during hot-update of LLM instances: {update_error}")
                logger.warning(f"Model settings updated but hot-update failed. Restart may be required for full effect.")

        return create_success_response(request, {
            'message': f'Default model for {provider_name} updated successfully',
            'provider': updated_provider
        })

    except Exception as e:
        logger.error(f"Error setting default model for provider {params}: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to set default model: {str(e)}")


@IPCHandlerRegistry.handler('delete_llm_provider_config')
def handle_delete_llm_provider_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete LLM provider configuration"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        llm_manager = get_llm_manager()
        main_window = AppContext.get_main_window()
        provider_name = data['name']
        username = data.get('username', '')

        # Get provider information
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # Check if this is the current default LLM (case-insensitive)
        current_default_llm = (main_window.config_manager.general_settings.default_llm or "").lower()
        is_default_llm = (current_default_llm == (provider_name or "").lower())

        # Delete API key and other credentials from environment variables
        env_vars = provider.get('api_key_env_vars', [])
        deleted_vars = []
        failed_vars = []
        
        for env_var in env_vars:
            logger.debug(f"Deleting environment variable {env_var} for provider {provider_name}")

            if env_var in os.environ:
                del os.environ[env_var]
                logger.debug(f"Removed {env_var} from current session")

            try:
                success = llm_manager.delete_api_key(env_var)

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
            logger.info(f"Deleted LLM provider config {provider_name}, removed environment variables: {deleted_vars}")
        if failed_vars:
            logger.warning(f"Failed to delete some environment variables for {provider_name}: {failed_vars}")

        # Check if we need to update default LLM after deletion
        new_default_llm = None
        new_default_model = None
        new_provider = None
        
        # Get all providers and find configured ones after deletion
        all_providers = llm_manager.get_all_providers()
        configured_providers = [p for p in all_providers if p.get('api_key_configured', False)]
        
        # Case 1: Deleted the current default LLM
        # Case 2: No providers are configured anymore (all API keys deleted)
        should_update_default = is_default_llm or (len(configured_providers) == 0)
        
        if should_update_default:
            if is_default_llm:
                logger.info(f"Provider {provider_name} was the default LLM, selecting a new default")
            else:
                logger.info("All API keys deleted, resetting to default OpenAI provider")
            
            if configured_providers:
                # Select the first available configured provider
                new_provider = configured_providers[0]
                new_default_llm = new_provider.get('provider')  # Use provider identifier
                new_default_model = new_provider.get('preferred_model') or new_provider.get('default_model') or ''
                logger.info(f"Selected new default LLM {new_default_llm} with model {new_default_model}")
            else:
                # No providers are configured, default to OpenAI with its default model
                new_default_llm = 'openai'
                # Get OpenAI's default model from llm_manager
                try:
                    openai_provider = llm_manager.get_provider('openai')
                    new_default_model = openai_provider.get('default_model', 'gpt-5') if openai_provider else 'gpt-5'
                except:
                    new_default_model = 'gpt-5'
                logger.info(f"No configured providers found; defaulting to {new_default_llm} with model {new_default_model} (no API key)")
            
            # Update default_llm setting
            main_window.config_manager.general_settings.default_llm = new_default_llm
            main_window.config_manager.general_settings.default_llm_model = new_default_model
            save_result = main_window.config_manager.general_settings.save()
            
            if not save_result:
                logger.error(f"Failed to save new default LLM setting")
                return create_error_response(request, 'LLM_ERROR', f"Failed to save new default LLM setting")
            
            # If we have a configured provider, try to hot-update LLMs
            if configured_providers and new_provider:
                try:
                    provider_info = f"{new_provider.get('display_name', new_default_llm)}, Model: {new_default_model}"
                    update_success = main_window.update_all_llms(reason=f"Default LLM changed to {provider_info}")
                    if not update_success:
                        logger.warning("Failed to hot-update LLMs after default change")
                except Exception as update_error:
                    logger.error(f"Error during hot-update of LLM instances: {update_error}")
            else:
                # Clear LLM instance if no provider is configured
                try:
                    main_window.llm = None
                    logger.info("Cleared LLM instance because no providers are configured")
                except Exception as clear_error:
                    logger.error(f"Error clearing LLM instance: {clear_error}")

        # Find shared Embedding providers that use the same API keys
        shared_providers = find_shared_providers(env_vars, 'llm')
        
        # Get updated provider info for frontend
        updated_provider = llm_manager.get_provider(provider_name)
        
        response_data = {
            'message': f'LLM provider {provider_name} configuration deleted successfully',
            'deleted_env_vars': deleted_vars,
            'was_default_llm': is_default_llm,
            'provider': updated_provider  # Include updated provider info for UI refresh
        }
        
        # Include shared providers info so frontend can refresh both LLM and Embedding UI
        # Always include shared_providers in response (even if empty) for consistency
        response_data['shared_providers'] = shared_providers
        if shared_providers:
            logger.info(f"[LLM] Found {len(shared_providers)} shared Embedding providers affected by deletion: {[p['name'] for p in shared_providers]}")
        else:
            logger.debug(f"[LLM] No shared Embedding providers affected by deletion of {provider_name}")
        
        # Include new default settings if changed
        if should_update_default and new_default_llm:
            response_data['new_default_llm'] = new_default_llm
            response_data['new_default_model'] = new_default_model
            response_data['reset_to_default'] = (len(configured_providers) == 0)
            # Also include current settings for frontend
            response_data['settings'] = {
                'default_llm': main_window.config_manager.general_settings.default_llm,
                'default_llm_model': main_window.config_manager.general_settings.default_llm_model
            }
        
        return create_success_response(request, response_data)

    except Exception as e:
        logger.error(f"Error deleting LLM provider config: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to delete LLM provider config: {str(e)}")


@IPCHandlerRegistry.handler('add_custom_llm_provider')
def handle_add_custom_llm_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Add custom LLM provider - Not supported in current version"""
    return create_error_response(request, 'NOT_SUPPORTED', "Adding custom LLM providers is not supported in current version")


@IPCHandlerRegistry.handler('remove_custom_llm_provider')
def handle_remove_custom_llm_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Remove custom LLM provider - Not supported in current version"""
    return create_error_response(request, 'NOT_SUPPORTED', "Removing custom LLM providers is not supported in current version")


@IPCHandlerRegistry.handler('set_default_llm')
def handle_set_default_llm(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Set default LLM provider and hot-update all LLM instances"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        name = data['name']
        model = data.get('model')  # Optional model parameter from frontend

        llm_manager = get_llm_manager()
        main_window = AppContext.get_main_window()

        # Verify provider exists and is configured
        provider = llm_manager.get_provider(name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} not found")

        if not provider['api_key_configured']:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} is not configured")

        # Save current settings for potential rollback
        old_default_llm = main_window.config_manager.general_settings.default_llm
        old_default_model = main_window.config_manager.general_settings.default_llm_model

        # Update default_llm first
        main_window.config_manager.general_settings.default_llm = name
        
        # Determine which model to use
        if model:
            # Frontend explicitly provided a model
            provider_model = model
            logger.info(f"[LLM] Using model from frontend: {model}")
        else:
            # No model from frontend, need to determine from current settings
            current_default_model = main_window.config_manager.general_settings.default_llm_model
            
            # Check if we're switching providers
            is_switching_provider = (old_default_llm != name)
            
            if is_switching_provider and current_default_model:
                # When switching providers, validate that current_default_model belongs to the new provider
                # Use llm_manager to validate and fix
                provider_model, was_fixed = llm_manager.validate_and_fix_default_llm_model(
                    name, current_default_model
                )
                if was_fixed:
                    logger.info(f"[LLM] Switching provider: existing model '{current_default_model}' doesn't belong to '{name}', using provider default '{provider_model}'")
                else:
                    logger.info(f"[LLM] Using existing model '{provider_model}' (valid for new provider)")
            else:
                # Not switching provider, or no current_default_model
                # Use preferred_model (which may come from current_default_model) or default_model
                provider_model = provider.get('preferred_model') or provider.get('default_model') or ''
                logger.info(f"[LLM] Using provider's model: {provider_model}")
        
        # Final validation: ensure model belongs to this provider (safety check)
        supported_models = provider.get('supported_models', [])
        if supported_models:
            model_ids = [m.get('model_id', m.get('name', '')) for m in supported_models]
            model_names = [m.get('name', '') for m in supported_models]
            model_display_names = [m.get('display_name', '') for m in supported_models]
            
            if provider_model and (provider_model not in model_ids and 
                                   provider_model not in model_names and 
                                   provider_model not in model_display_names):
                logger.warning(f"Model '{provider_model}' not found in provider '{name}' supported models")
                logger.warning("Using provider's default model instead")
                provider_model = provider.get('default_model', '')
        
        # Update default_llm_model
        main_window.config_manager.general_settings.default_llm_model = provider_model
        
        save_result = main_window.config_manager.general_settings.save()

        if not save_result:
            return create_error_response(request, 'LLM_ERROR', f"Failed to save default LLM setting")

        # Hot-update: Use unified method to update all LLMs (including browser_use)
        try:
            provider_info = f"{provider.get('display_name', name)}, Model: {provider_model}"
            success = main_window.update_all_llms(reason=f"Provider switched to {provider_info}")
            
            if not success:
                # Revert the setting change if LLM creation failed
                logger.warning(f"Failed to create LLM instance for {name}, reverting settings")
                logger.info(f"Reverting: default_llm from '{name}' to '{old_default_llm}'")
                logger.info(f"Reverting: default_llm_model from '{provider_model}' to '{old_default_model}'")
                
                main_window.config_manager.general_settings.default_llm = old_default_llm
                main_window.config_manager.general_settings.default_llm_model = old_default_model
                rollback_saved = main_window.config_manager.general_settings.save()
                
                # Verify rollback
                current_llm = main_window.config_manager.general_settings.default_llm
                current_model = main_window.config_manager.general_settings.default_llm_model
                logger.info(f"After rollback: default_llm='{current_llm}', default_llm_model='{current_model}'")
                
                if current_llm != old_default_llm or current_model != old_default_model:
                    logger.error(f"Rollback verification failed. Expected ({old_default_llm}, {old_default_model}), got ({current_llm}, {current_model})")
                else:
                    logger.info("Rollback verified successfully")
                
                return create_error_response(
                    request, 
                    'LLM_ERROR', 
                    f"Failed to create LLM instance for {name}. Please check API key configuration and try again. Settings reverted to {old_default_llm} with model {old_default_model}."
                )
            
        except Exception as update_error:
            logger.error(f"Error during hot-update of LLM instances: {update_error}")
            # Revert settings on exception
            logger.warning(f"Reverting settings due to exception")
            logger.info(f"Reverting: default_llm from '{name}' to '{old_default_llm}'")
            logger.info(f"Reverting: default_llm_model from '{provider_model}' to '{old_default_model}'")
            
            main_window.config_manager.general_settings.default_llm = old_default_llm
            main_window.config_manager.general_settings.default_llm_model = old_default_model
            rollback_saved = main_window.config_manager.general_settings.save()
            
            # Verify rollback
            current_llm = main_window.config_manager.general_settings.default_llm
            current_model = main_window.config_manager.general_settings.default_llm_model
            logger.info(f"After rollback: default_llm='{current_llm}', default_llm_model='{current_model}'")
            
            if current_llm != old_default_llm or current_model != old_default_model:
                logger.error(f"Rollback verification failed. Expected ({old_default_llm}, {old_default_model}), got ({current_llm}, {current_model})")
            else:
                logger.info("Rollback verified successfully")
            
            return create_error_response(
                request,
                'LLM_ERROR',
                f"Error updating LLM instances: {str(update_error)}. Settings reverted to {old_default_llm} with model {old_default_model}."
            )

        # Verify the final state
        final_default_llm = main_window.config_manager.general_settings.default_llm
        final_llm_type = type(main_window.llm).__name__ if main_window.llm else "None"
        
        verification_status = "VERIFIED" if (final_default_llm or "").lower() == (name or "").lower() else "MISMATCH"
        logger.info("Provider switch verification:")
        logger.info(f"   Setting: default_llm={name}, model={provider_model}")
        logger.info(f"   Actual: default_llm={final_default_llm}, LLM Type={final_llm_type}")
        logger.info(f"   Status: {verification_status}")
        
        return create_success_response(request, {
            'default_llm': name,
            'model_name': provider_model,
            'actual_default_llm': final_default_llm,
            'llm_type': final_llm_type,
            'verified': (final_default_llm or "").lower() == (name or "").lower(),
            'message': f'Default LLM set to {name} successfully (hot-updated)' + (f' - {verification_status}' if verification_status else '')
        })

    except Exception as e:
        logger.error(f"Error setting default LLM: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to set default LLM: {str(e)}")


@IPCHandlerRegistry.handler('get_default_llm')
def handle_get_default_llm(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get current default LLM provider"""
    try:
        main_window = AppContext.get_main_window()
        default_llm = main_window.config_manager.general_settings.default_llm

        return create_success_response(request, {
            'default_llm': default_llm,
            'message': 'Default LLM retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting default LLM: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get default LLM: {str(e)}")


@IPCHandlerRegistry.handler('get_configured_llm_providers')
def handle_get_configured_llm_providers(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """Get configured LLM providers"""
    try:
        llm_manager = get_llm_manager()
        all_providers = llm_manager.get_all_providers()

        # Filter out configured providers
        configured_providers = [p for p in all_providers if p.get('api_key_configured', False)]
        logger.info(f"Retrieved {len(configured_providers)} configured LLM providers")

        return create_success_response(request, {
            'providers': configured_providers,
            'message': 'Configured LLM providers retrieved successfully'
        })

    except Exception as e:
        logger.error(f"Error getting configured LLM providers: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get configured LLM providers: {str(e)}")


@IPCHandlerRegistry.handler('get_llm_providers_with_credentials')
def handle_get_llm_providers_with_credentials(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """
    Get all LLM providers with their complete configuration including API keys for configured providers.
    This endpoint is designed for Skill Editor LLM Node to get all necessary information in one call.
    
    Returns:
        - All providers with their models, base_url, and other configurations
        - API keys for configured providers (full keys, not masked)
        - Status indicating which providers are configured
    """
    try:
        llm_manager = get_llm_manager()
        all_providers = llm_manager.get_all_providers()
        
        # Enhance providers with API key information
        enhanced_providers = []
        for provider in all_providers:
            provider_data = dict(provider)  # Copy provider data
            
            # If provider is configured, include API key
            if provider.get('api_key_configured', False):
                provider_name = provider.get('name')
                env_vars = provider.get('api_key_env_vars', [])
                
                # Handle different provider types
                if provider_name == 'Azure OpenAI':
                    # Azure has multiple credentials
                    credentials = {}
                    if 'AZURE_ENDPOINT' in env_vars:
                        credentials['azure_endpoint'] = llm_manager.retrieve_api_key('AZURE_ENDPOINT')
                    if 'AZURE_OPENAI_API_KEY' in env_vars:
                        credentials['api_key'] = llm_manager.retrieve_api_key('AZURE_OPENAI_API_KEY')
                    provider_data['credentials'] = credentials
                    
                elif provider_name == 'AWS Bedrock':
                    # AWS Bedrock has multiple credentials
                    credentials = {}
                    if 'AWS_ACCESS_KEY_ID' in env_vars:
                        credentials['aws_access_key_id'] = llm_manager.retrieve_api_key('AWS_ACCESS_KEY_ID')
                    if 'AWS_SECRET_ACCESS_KEY' in env_vars:
                        credentials['aws_secret_access_key'] = llm_manager.retrieve_api_key('AWS_SECRET_ACCESS_KEY')
                    provider_data['credentials'] = credentials
                    
                else:
                    # Standard single API key
                    if env_vars:
                        api_key = llm_manager.retrieve_api_key(env_vars[0])
                        provider_data['api_key'] = api_key
            
            enhanced_providers.append(provider_data)
        
        logger.info(f"Retrieved {len(enhanced_providers)} LLM providers with credentials for Skill Editor")
        
        return create_success_response(request, {
            'providers': enhanced_providers,
            'message': 'LLM providers with credentials retrieved successfully'
        })
        
    except Exception as e:
        logger.error(f"Error getting LLM providers with credentials: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get LLM providers with credentials: {str(e)}")


@IPCHandlerRegistry.handler('get_llm_provider_api_key')
def handle_get_llm_provider_api_key(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get LLM provider's API key (masked or full)"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        provider_name = data['name']
        show_full = data.get('show_full', False)  # Whether to show full API key

        llm_manager = get_llm_manager()

        # Get provider information
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # Get API key environment variables
        env_vars = provider.get('api_key_env_vars', [])
        if not env_vars:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} has no API key environment variables")

        # Handle special cases requiring multiple credentials
        if provider_name == 'AzureOpenAI':
            result = {
                'provider_name': provider_name,
                'credentials': {},
                'is_masked': not show_full,
                'message': f'Credentials retrieved for {provider_name}'
            }

            # Get Azure endpoint
            if 'AZURE_ENDPOINT' in env_vars:
                if show_full:
                    endpoint = llm_manager.retrieve_api_key('AZURE_ENDPOINT')
                else:
                    endpoint = llm_manager._get_masked_api_key('AZURE_ENDPOINT')
                result['credentials']['azure_endpoint'] = endpoint

            # Get Azure OpenAI API key
            if 'AZURE_OPENAI_API_KEY' in env_vars:
                if show_full:
                    api_key = llm_manager.retrieve_api_key('AZURE_OPENAI_API_KEY')
                else:
                    api_key = llm_manager._get_masked_api_key('AZURE_OPENAI_API_KEY')
                result['credentials']['api_key'] = api_key

            return create_success_response(request, result)

        elif provider_name == 'ChatBedrockConverse':
            result = {
                'provider_name': provider_name,
                'credentials': {},
                'is_masked': not show_full,
                'message': f'Credentials retrieved for {provider_name}'
            }

            # Get AWS Access Key ID
            if 'AWS_ACCESS_KEY_ID' in env_vars:
                if show_full:
                    access_key_id = llm_manager.retrieve_api_key('AWS_ACCESS_KEY_ID')
                else:
                    access_key_id = llm_manager._get_masked_api_key('AWS_ACCESS_KEY_ID')
                result['credentials']['aws_access_key_id'] = access_key_id

            # Get AWS Secret Access Key
            if 'AWS_SECRET_ACCESS_KEY' in env_vars:
                if show_full:
                    secret_access_key = llm_manager.retrieve_api_key('AWS_SECRET_ACCESS_KEY')
                else:
                    secret_access_key = llm_manager._get_masked_api_key('AWS_SECRET_ACCESS_KEY')
                result['credentials']['aws_secret_access_key'] = secret_access_key

            return create_success_response(request, result)

        else:
            # Handle other providers - use first environment variable
            env_var = env_vars[0]  # Use first environment variable

            if show_full:
                # Return full API key (for display only, use with caution)
                api_key = llm_manager.retrieve_api_key(env_var)
            else:
                # Return masked API key
                api_key = llm_manager._get_masked_api_key(env_var)

            if api_key is None:
                return create_error_response(request, 'LLM_ERROR', f"No API key found for {provider_name}")

            return create_success_response(request, {
                'provider_name': provider_name,
                'env_var': env_var,
                'api_key': api_key,
                'is_masked': not show_full,
                'message': f'API key retrieved for {provider_name}'
            })

    except Exception as e:
        logger.error(f"Error getting LLM provider API key: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to get API key: {str(e)}")
