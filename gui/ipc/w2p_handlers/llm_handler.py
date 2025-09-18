"""
LLM管理相关的IPC处理器 - 使用原有的LLM管理器架构
"""
from typing import Optional, Dict, Any
from ..types import IPCRequest, IPCResponse, create_success_response, create_error_response
from ..registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger
from app_context import AppContext


def validate_params(params: Optional[Dict[str, Any]], required_keys: list) -> tuple[bool, Dict[str, Any], str]:
    """验证参数"""
    if not params:
        return False, {}, "Missing parameters"

    for key in required_keys:
        if key not in params:
            return False, {}, f"Missing required parameter: {key}"

    return True, params, ""


def get_llm_manager():
    """获取LLM管理器实例"""
    main_window = AppContext.get_main_window()
    return main_window.config_manager.llm_manager


@IPCHandlerRegistry.handler('get_llm_providers')
def handle_get_llm_providers(request: IPCRequest, params: Optional[Dict[str, Any]] = None) -> IPCResponse:
    """获取所有LLM提供商"""
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
    """获取指定的LLM提供商"""
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
    """更新LLM提供商配置"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        llm_manager = get_llm_manager()
        provider_name = data['name']
        api_key = data.get('api_key')
        azure_endpoint = data.get('azure_endpoint')

        # 获取提供商信息
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # 获取该提供商的环境变量名
        env_vars = provider.get('api_key_env_vars', [])
        
        # 处理需要多个凭据的特殊情况
        if provider_name == 'AzureOpenAI':
            if azure_endpoint:
                # 存储Azure endpoint
                if 'AZURE_ENDPOINT' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_ENDPOINT', azure_endpoint)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store Azure endpoint: {error_msg}")
            
            if api_key:
                # 存储Azure OpenAI API key
                if 'AZURE_OPENAI_API_KEY' in env_vars:
                    success, error_msg = llm_manager.store_api_key('AZURE_OPENAI_API_KEY', api_key)
                    if not success:
                        return create_error_response(request, 'LLM_ERROR', f"Failed to store API key: {error_msg}")
        
        elif provider_name == 'ChatBedrockConverse':
            # AWS Bedrock需要两个凭据：AWS_ACCESS_KEY_ID 和 AWS_SECRET_ACCESS_KEY
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
            # 处理其他提供商 - 使用第一个环境变量存储API key
            if api_key and env_vars:
                env_var = env_vars[0]  # 使用第一个环境变量
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
    """删除LLM提供商配置"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        llm_manager = get_llm_manager()
        provider_name = data['name']

        # 获取提供商信息
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # 删除环境变量中的API key和其他凭据
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
    """添加自定义LLM提供商 - 当前版本不支持"""
    return create_error_response(request, 'NOT_SUPPORTED', "Adding custom LLM providers is not supported in current version")


@IPCHandlerRegistry.handler('remove_custom_llm_provider')
def handle_remove_custom_llm_provider(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """删除自定义LLM提供商 - 当前版本不支持"""
    return create_error_response(request, 'NOT_SUPPORTED', "Removing custom LLM providers is not supported in current version")


@IPCHandlerRegistry.handler('set_default_llm')
def handle_set_default_llm(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """设置默认LLM提供商"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)
        
        name = data['name']
        
        llm_manager = get_llm_manager()

        # 验证provider是否存在且已配置
        provider = llm_manager.get_provider(name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} not found")
        
        if not provider['api_key_configured']:
            return create_error_response(request, 'LLM_ERROR', f"Provider {name} is not configured")
        
        # 更新general_settings中的default_llm字段
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
    """获取当前默认的LLM提供商"""
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
    """获取已配置的LLM提供商"""
    try:
        llm_manager = get_llm_manager()
        all_providers = llm_manager.get_all_providers()

        # 过滤出已配置的提供商
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
    """获取LLM提供商的API key（masked或完整）"""
    try:
        is_valid, data, error = validate_params(params, ['name'])
        if not is_valid:
            return create_error_response(request, 'INVALID_PARAMS', error)

        provider_name = data['name']
        show_full = data.get('show_full', False)  # 是否显示完整的API key

        llm_manager = get_llm_manager()

        # 获取提供商信息
        provider = llm_manager.get_provider(provider_name)
        if not provider:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} not found")

        # 获取API key环境变量
        env_vars = provider.get('api_key_env_vars', [])
        if not env_vars:
            return create_error_response(request, 'LLM_ERROR', f"Provider {provider_name} has no API key environment variables")

        # 处理需要多个凭据的特殊情况
        if provider_name == 'AzureOpenAI':
            result = {
                'provider_name': provider_name,
                'credentials': {},
                'is_masked': not show_full,
                'message': f'Credentials retrieved for {provider_name}'
            }
            
            # 获取Azure endpoint
            if 'AZURE_ENDPOINT' in env_vars:
                if show_full:
                    endpoint = llm_manager.retrieve_api_key('AZURE_ENDPOINT')
                else:
                    endpoint = llm_manager._get_masked_api_key('AZURE_ENDPOINT')
                result['credentials']['azure_endpoint'] = endpoint
            
            # 获取Azure OpenAI API key
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
            
            # 获取AWS Access Key ID
            if 'AWS_ACCESS_KEY_ID' in env_vars:
                if show_full:
                    access_key_id = llm_manager.retrieve_api_key('AWS_ACCESS_KEY_ID')
                else:
                    access_key_id = llm_manager._get_masked_api_key('AWS_ACCESS_KEY_ID')
                result['credentials']['aws_access_key_id'] = access_key_id
            
            # 获取AWS Secret Access Key
            if 'AWS_SECRET_ACCESS_KEY' in env_vars:
                if show_full:
                    secret_access_key = llm_manager.retrieve_api_key('AWS_SECRET_ACCESS_KEY')
                else:
                    secret_access_key = llm_manager._get_masked_api_key('AWS_SECRET_ACCESS_KEY')
                result['credentials']['aws_secret_access_key'] = secret_access_key
            
            return create_success_response(request, result)
        
        else:
            # 处理其他提供商 - 使用第一个环境变量
            env_var = env_vars[0]  # 使用第一个环境变量

            if show_full:
                # 返回完整的API key（仅用于显示，需要谨慎使用）
                api_key = llm_manager.retrieve_api_key(env_var)
            else:
                # 返回masked的API key
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
