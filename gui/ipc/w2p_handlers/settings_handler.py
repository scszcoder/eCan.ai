import traceback
import json
from os.path import exists
from typing import Any, Optional, Dict
import requests
from app_context import AppContext
from gui.ipc.context_bridge import get_handler_context
from config.envi import getECBotDataHome
from gui.ipc.handlers import validate_params
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response

from utils.logger_helper import logger_helper as logger

@IPCHandlerRegistry.handler('get_hostname')
def handle_get_hostname(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get the current machine's hostname.
    
    Returns:
        IPCResponse with hostname
    """
    try:
        import socket
        import platform
        
        # Try multiple methods to get hostname
        hostname = None
        try:
            hostname = socket.gethostname()
        except Exception:
            pass
        
        if not hostname:
            try:
                hostname = platform.node()
            except Exception:
                pass
        
        if not hostname:
            hostname = "Unknown-Computer"
        
        # Clean up hostname (remove domain suffix if present)
        if "." in hostname:
            hostname = hostname.split(".", 1)[0]
        
        logger.debug(f"[get_hostname] Returning hostname: {hostname}")
        return create_success_response(request, {'hostname': hostname})
        
    except Exception as e:
        logger.error(f"Error getting hostname: {e}")
        return create_error_response(request, 'HOSTNAME_ERROR', f"Error getting hostname: {str(e)}")


@IPCHandlerRegistry.handler('get_settings')
def handle_get_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle login request

    Validate user credentials and return access token.

    Args:
        request: IPC request object
        params: Request parameters, must contain 'username' and 'password' fields

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"get settings handler called with request: {request}")

        # Validate parameters
        is_valid, data, error = validate_params(params, ['username'])
        if not is_valid:
            logger.warning(f"Invalid parameters for get settings: {error}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                error
            )

        # Get username and password
        username = data['username']
        # Simple password validation
        logger.info(f"get settings successful for user: {username}")
        ctx = get_handler_context(request, params)
        general_settings = ctx.get_config_manager().general_settings
        settings = general_settings.data.copy()
        
        # Add cached hardware detection info (no real-time probing here)
        try:
            # Use cached value updated by background scan
            cached_wifi = general_settings.default_wifi or None
            settings['current_wifi'] = cached_wifi
            logger.debug(f"Current WiFi (cached): {cached_wifi}")

            # Cached or last-scan results
            available_wifi_networks = general_settings.get_wifi_networks()
            settings['available_wifi_networks'] = available_wifi_networks
            logger.debug(f"Available WiFi networks (cached): {len(available_wifi_networks)}")

            available_printers = general_settings.get_printer_names()
            settings['available_printers'] = available_printers
            logger.debug(f"Available printers (cached): {len(available_printers)}")

        except Exception as hw_error:
            logger.warning(f"Failed to get cached hardware info: {hw_error}")
            # Don't fail the entire request if cache is unavailable
            settings['current_wifi'] = None
            settings['available_wifi_networks'] = []
            settings['available_printers'] = []
        
        resultJS = {
            'settings': settings,
            'message': 'Get settings successful'
        }
        logger.debug('get settings resultJS:' + str(resultJS))
        return create_success_response(request, resultJS)

    except Exception as e:
        logger.error(f"Error in get settings handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'LOGIN_ERROR',
            f"Error during get settings: {str(e)}"
        )

@IPCHandlerRegistry.handler('save_settings')
def handle_save_settings(request: IPCRequest, params: Optional[list[Any]]) -> IPCResponse:
    """Handle save settings request

    Save user settings to configuration file.

    Args:
        request: IPC request object
        params: Request parameters, containing settings data

    Returns:
        str: JSON formatted response message
    """
    try:
        logger.debug(f"Save settings handler called with request: {request}")

        # Validate parameters
        if not params or len(params) == 0:
            logger.warning("No settings data provided")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'No settings data provided'
            )

        # Get settings data
        settings_data = params[0] if isinstance(params, list) else params

        if not isinstance(settings_data, dict):
            logger.warning(f"Invalid settings data format: {type(settings_data)}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Settings data must be a dictionary'
            )

        logger.info(f"Saving settings: {list(settings_data.keys())}")

        # Get main window instance
        ctx = get_handler_context(request, params)
        if not ctx:
            logger.error("Main window not available - user may have logged out")
            return create_error_response(request, 'MAIN_WINDOW_ERROR', 'User session not available - please login again')

        # Get config manager
        if not ctx.get_config_manager():
            logger.error("Config manager not available")
            return create_error_response(
                request,
                'SYSTEM_ERROR',
                'Config manager not available'
            )

        # Save settings to general_settings
        general_settings = ctx.get_config_manager().general_settings

        # Use update_data method to handle all settings data uniformly
        try:
            general_settings.update_data(settings_data)
            logger.info(f"Settings updated successfully. Fields: {list(settings_data.keys())}")
        except Exception as e:
            logger.error(f"Failed to update settings data: {e}")
            return create_error_response(
                request,
                'UPDATE_ERROR',
                f"Failed to update settings: {str(e)}"
            )

        # Save to file
        try:
            general_settings.save()
            logger.info(f"Settings saved successfully")

            return create_success_response(request, {
                'message': 'Settings saved successfully',
                'updated_fields': list(settings_data.keys())
            })

        except Exception as e:
            logger.error(f"Failed to save settings to file: {e}")
            return create_error_response(
                request,
                'SAVE_ERROR',
                f"Failed to save settings to file: {str(e)}"
            )

    except Exception as e:
        logger.error(f"Error in save settings handler: {e} {traceback.format_exc()}")
        return create_error_response(
            request,
            'SAVE_ERROR',
            f"Error during save settings: {str(e)}"
        )


@IPCHandlerRegistry.handler('update_user_preferences')
def handle_update_user_preferences(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Update user preferences (language, theme) in uli.json
    
    This handler is whitelisted and can be called before login.
    
    Args:
        request: IPC request object
        params: Request parameters containing 'language' and/or 'theme' fields
        
    Returns:
        IPCResponse indicating success or failure
    """
    try:
        logger.debug(f"Update user preferences handler called with params: {params}")
        
        # Validate parameters
        if not params or not isinstance(params, dict):
            logger.warning("Invalid parameters for update user preferences")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Parameters must be a dictionary'
            )
        
        language = params.get('language')
        theme = params.get('theme')
        
        if not language and not theme:
            logger.warning("No language or theme provided")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'At least one of language or theme must be provided'
            )
        
        # Validate language if provided
        if language:
            valid_languages = ['zh-CN', 'en-US']
            if language not in valid_languages:
                logger.warning(f"Invalid language code: {language}")
                return create_error_response(
                    request,
                    'INVALID_PARAMS',
                    f'Language must be one of: {", ".join(valid_languages)}'
                )
        
        # Validate theme if provided
        if theme:
            valid_themes = ['light', 'dark', 'system']
            if theme not in valid_themes:
                logger.warning(f"Invalid theme: {theme}")
                return create_error_response(
                    request,
                    'INVALID_PARAMS',
                    f'Theme must be one of: {", ".join(valid_themes)}'
                )
        
        # Update uli.json
        uli_file = f"{getECBotDataHome()}/uli.json"
        data = {}
        
        if exists(uli_file):
            try:
                with open(uli_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"Error reading {uli_file}: {e}")
        
        # Update preferences
        if language:
            data['language'] = language
            logger.info(f"Updated language preference to: {language}")
        
        if theme:
            data['theme'] = theme
            logger.info(f"Updated theme preference to: {theme}")
        
        # Save back to file
        try:
            with open(uli_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            result = {'message': 'User preferences updated successfully'}
            if language:
                result['language'] = language
            if theme:
                result['theme'] = theme
            
            logger.info(f"User preferences saved to {uli_file}")
            return create_success_response(request, result)
            
        except Exception as e:
            logger.error(f"Failed to save user preferences: {e}")
            return create_error_response(
                request,
                'SAVE_ERROR',
                f'Failed to save user preferences: {str(e)}'
            )
        
    except Exception as e:
        logger.error(f"Error in update user preferences handler: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'PREFERENCES_ERROR',
            f"Error updating user preferences: {str(e)}"
        )


# Ollama tags management functions moved to gui/ollama_utils.py
# Import them here for backward compatibility
from gui.ollama_utils import get_ollama_tags_path, save_ollama_tags, load_ollama_tags, fetch_ollama_models

# RyoAIS models management functions
from gui.ryoais_utils import get_ryoais_models_path, save_ryoais_models, load_ryoais_models, fetch_ryoais_models


@IPCHandlerRegistry.background_handler('settings.getProviderModels')
def handle_get_provider_models(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Fetch an OpenAI-compatible provider's model list from ``<host>/models``."""
    params = params or {}
    host = str(params.get('host') or '').strip().rstrip('/')
    if not host:
        return create_error_response(request, 'PROVIDER_MODELS_INVALID_HOST', 'Provider host is required')

    api_key = str(params.get('api_key') or '').strip()
    provider_id = str(params.get('provider') or '').strip()
    requested_type = str(params.get('model_type') or '').lower()

    # System-managed LightRAG key fields are intentionally not exposed to the
    # web UI. Resolve the provider credential in the backend when needed.
    if not api_key and provider_id and requested_type in ('llm', 'embedding', 'rerank'):
        try:
            ctx = get_handler_context(request, params)
            manager = getattr(ctx.get_config_manager(), f'{requested_type}_manager') if ctx else None
            provider = manager.get_provider(provider_id) if manager else None
            for env_var in (provider or {}).get('api_key_env_vars', []):
                api_key = manager.retrieve_api_key(env_var) or ''
                if api_key:
                    break
        except Exception as key_exc:
            logger.warning(f'[SettingsHandler] Could not resolve {provider_id} API key: {key_exc}')

    headers = {'Authorization': f'Bearer {api_key}'} if api_key else {}

    try:
        response = requests.get(f'{host}/models', headers=headers, timeout=15)
        response.raise_for_status()
        payload = response.json()
        models = payload.get('data', payload.get('models', [])) if isinstance(payload, dict) else []
        normalized = []
        for model in models if isinstance(models, list) else []:
            item = model if isinstance(model, dict) else {'id': str(model)}
            item_type = str(item.get('type') or item.get('model_type') or '').lower()
            if requested_type and item_type and item_type not in (requested_type, f'{requested_type}s'):
                continue
            model_id = item.get('id') or item.get('model_id') or item.get('name')
            if model_id:
                normalized.append({**item, 'name': str(model_id)})
        return create_success_response(request, {'models': normalized, 'host': host})
    except Exception as exc:
        logger.warning(f'[SettingsHandler] Failed to fetch provider models from {host}: {exc}')
        return create_error_response(request, 'PROVIDER_MODELS_ERROR', str(exc))


@IPCHandlerRegistry.background_handler('settings.getOllamaModels')
def handle_get_ollama_models(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Fetch available models from Ollama API and save to local file.
    
    Expected params:
    - host: str - Ollama API host (e.g., 'http://127.0.0.1:11434')
    - username: str - Optional username for saving to user-specific path
    """
    host = params.get('host', 'http://127.0.0.1:11434') if params else 'http://127.0.0.1:11434'
    username = params.get('username') if params else None
    
    # Use the common fetch_ollama_models function
    success, model_list, error_msg = fetch_ollama_models(host, username)
    
    if success:
        # CRITICAL: Reload dynamic models into memory after file is updated.
        # Without this, LLMConfig._models still holds stale data and model validation
        # (e.g. in set_llm_provider_model) will fail with "Model not supported".
        try:
            from gui.config.llm_config import llm_config
            llm_config.reload_dynamic_models()
            logger.debug(f"[SettingsHandler] ✅ Reloaded dynamic Ollama models after fetch")
        except Exception as reload_err:
            logger.warning(f"[SettingsHandler] ⚠️ Failed to reload Ollama models: {reload_err}")

        return create_success_response(request, {
            'models': model_list,
            'host': host
        })
    else:
        # Determine error type based on error message
        if 'Cannot connect' in error_msg:
            error_type = 'OLLAMA_CONNECTION_ERROR'
        elif 'timed out' in error_msg:
            error_type = 'OLLAMA_TIMEOUT'
        elif 'status' in error_msg:
            error_type = 'OLLAMA_API_ERROR'
        else:
            error_type = 'OLLAMA_ERROR'
        
        return create_error_response(request, error_type, error_msg)


@IPCHandlerRegistry.background_handler('settings.getRyoAISModels')
def handle_get_ryoais_models(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """
    Fetch available models from RyoAIS OpenAI-compatible API and save to local file.

    Expected params:
    - host: str - RyoAIS API host (e.g., 'http://localhost/v1')
    - api_key: str - Optional API key for authentication
    - username: str - Optional username for saving to user-specific path
    - verify_ssl: bool - Optional, default False (self-signed certs are common)
    """
    host = params.get('host', 'http://localhost/v1') if params else 'http://localhost/v1'
    api_key = params.get('api_key') if params else None
    username = params.get('username') if params else None
    verify_ssl = params.get('verify_ssl', False) if params else False

    # Use the common fetch_ryoais_models function
    success, model_list, error_msg = fetch_ryoais_models(host, api_key, username, verify_ssl=verify_ssl)
    
    if success:
        # CRITICAL: Reload dynamic models into memory after file is updated.
        # Without this, LLMConfig._models still holds stale data and model validation
        # (e.g. in set_llm_provider_model) will fail with "Model not supported".
        try:
            from gui.config.llm_config import llm_config
            llm_config.reload_dynamic_models()
            logger.debug(f"[SettingsHandler] ✅ Reloaded dynamic RyoAIS models after fetch")
        except Exception as reload_err:
            logger.warning(f"[SettingsHandler] ⚠️ Failed to reload RyoAIS models: {reload_err}")

        return create_success_response(request, {
            'models': model_list,
            'host': host
        })
    else:
        # Determine error type based on error message
        if 'Cannot connect' in error_msg:
            error_type = 'RYOAIS_CONNECTION_ERROR'
        elif 'timed out' in error_msg:
            error_type = 'RYOAIS_TIMEOUT'
        elif 'status' in error_msg:
            error_type = 'RYOAIS_API_ERROR'
        else:
            error_type = 'RYOAIS_ERROR'
        
        return create_error_response(request, error_type, error_msg)
