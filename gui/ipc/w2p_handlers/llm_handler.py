"""
LLM management related IPC handlers - Using original LLM manager architecture
"""
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
        provider_name = data['name']
        api_key = data.get('api_key')
        azure_endpoint = data.get('azure_endpoint')

        # Get provider information
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # Get environment variable names for this provider
        env_vars = provider.get('api_key_env_vars', [])

        # Handle special cases requiring multiple credentials
        if provider_name == 'AzureOpenAI':
            if azure_endpoint:
                # Store Azure endpoint
                if 'AZURE_ENDPOINT' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_ENDPOINT', azure_endpoint)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store Azure endpoint: {error_msg}")

            if api_key:
                # Store Azure OpenAI API key
                if 'AZURE_OPENAI_API_KEY' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_OPENAI_API_KEY', api_key)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store API key: {error_msg}")

        elif provider_name == 'ChatBedrockConverse':
            # AWS Bedrock requires two credentials: AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
            aws_access_key_id = data.get('aws_access_key_id')
            aws_secret_access_key = data.get('aws_secret_access_key')

            if aws_access_key_id:
                if 'AWS_ACCESS_KEY_ID' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AWS_ACCESS_KEY_ID', aws_access_key_id)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store AWS Access Key ID: {error_msg}")

            if aws_secret_access_key:
                if 'AWS_SECRET_ACCESS_KEY' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AWS_SECRET_ACCESS_KEY', aws_secret_access_key)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store AWS Secret Access Key: {error_msg}")

        else:
            # Handle other providers - use first environment variable to store API key
            if api_key and env_vars:
                env_var = env_vars[0]  # Use first environment variable
                success, error_msg = llm_manager.store_api_key(env_var, api_key)
                if not success:
                    return create_error_response(request, 'LLM_ERROR', f"Failed to store API key: {error_msg}")

        logger.info(f"Updated LLM provider: {provider_name}")
        return create_success_response(request, {
            'message': f'LLM provider {provider_name} updated successfully'
        })

    except Exception as e:
        logger.error(f"Error updating LLM provider: {e}")
        return create_error_response(request, 'LLM_ERROR', f"Failed to update LLM provider: {str(e)}")


@IPCHandlerRegistry.handler('delete_llm_provider_config')
def handle_delete_llm_provider_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete LLM provider configuration"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        llm_manager = get_llm_manager()
        provider_name = data['name']

        # Get provider information
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # Delete API key and other credentials from environment variables
        env_vars = provider.get('api_key_env_vars', [])
        deleted_vars = []
        for env_var in env_vars:
            if llm_manager.delete_api_key(env_var):
                deleted_vars.append(env_var)

        logger.info(f"Deleted LLM provider config: {provider_name}, removed env vars: {deleted_vars}")
        return create_success_response(request, {
            'message': f'LLM provider {provider_name} configuration deleted successfully',
            'deleted_env_vars': deleted_vars
        })

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
    """Set default LLM provider"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        name = data['name']

        llm_manager = get_llm_manager()

        # Verify provider exists and is configured
        provider = llm_manager.get_provider(name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} not found")

        if not provider['api_key_configured']:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} is not configured")

        # Update default_llm field in general_settings
        main_window = AppContext.get_main_window()
        main_window.config_manager.general_settings.default_llm = name
        save_result = main_window.config_manager.general_settings.save()

        if not save_result:
            return create_error_response(request, 'LLM_ERROR', f"Failed to save default LLM setting")

        logger.info(f"Default LLM set to {name}")

        return create_success_response(request, {
            'default_llm': name,
            'message': f'Default LLM set to {name} successfully'
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
