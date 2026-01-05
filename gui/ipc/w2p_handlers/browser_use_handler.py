"""
Browser Use Settings Handler

Handles IPC requests for browser-use settings management including:
- Agent settings
- Browser session settings
- Browser profiles
"""
import traceback
import json
import os
from typing import Any, Optional, Dict

from gui.ipc.context_bridge import get_handler_context
from gui.ipc.registry import IPCHandlerRegistry
from gui.ipc.types import IPCRequest, IPCResponse, create_error_response, create_success_response
from config.envi import getECBotDataHome

from utils.logger_helper import logger_helper as logger


def get_browser_use_settings_path() -> str:
    """Get the path to the browser-use settings file."""
    return os.path.join(getECBotDataHome(), 'browser_use_settings.json')


def load_browser_use_settings() -> Dict[str, Any]:
    """Load browser-use settings from file."""
    settings_path = get_browser_use_settings_path()
    
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load browser-use settings: {e}")
    
    # Return default settings if file doesn't exist or failed to load
    return get_default_browser_use_settings()


def save_browser_use_settings_to_file(settings: Dict[str, Any]) -> bool:
    """Save browser-use settings to file."""
    settings_path = get_browser_use_settings_path()
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Browser-use settings saved to {settings_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save browser-use settings: {e}")
        return False


def get_default_browser_use_settings() -> Dict[str, Any]:
    """Get default browser-use settings."""
    return {
        'agentSettings': {
            'use_vision': True,
            'vision_detail_level': 'auto',
            'max_failures': 3,
            'max_steps': 100,
            'max_actions_per_step': 3,
            'use_thinking': True,
            'flash_mode': False,
            'use_judge': True,
            'max_history_items': None,
            'calculate_cost': False,
            'include_tool_call_examples': False,
            'llm_timeout': 60,
            'step_timeout': 180,
            'final_response_after_failure': True,
        },
        'browserSessionSettings': {
            'headless': False,
            'minimum_wait_page_load_time': 0.5,
            'wait_for_network_idle_page_load_time': 1.0,
            'wait_between_actions': 0.5,
            'auto_download_pdfs': True,
            'highlight_elements': True,
            'dom_highlight_elements': True,
            'max_iframes': 3,
            'max_iframe_depth': 3,
            'keep_alive': False,
        },
        'profiles': [
            {
                'id': 'default',
                'name': 'Default Profile',
                'isDefault': True,
                # Connection settings
                'cdp_url': '',
                'is_local': False,
                'use_cloud': False,
                # Browser settings
                'headless': False,
                'user_data_dir': '',
                'profile_directory': 'Default',
                'downloads_path': '',
                'disable_security': False,
                'deterministic_rendering': False,
                'args': [],
                'user_agent': '',
                # Domain restrictions
                'allowed_domains': [],
                'prohibited_domains': [],
                'block_ip_addresses': False,
                # Session settings
                'keep_alive': False,
                'enable_default_extensions': True,
                'demo_mode': False,
                'cookie_whitelist_domains': ['nature.com', 'qatarairways.com'],
                # Window settings
                'window_width': 1280,
                'window_height': 720,
                'window_position_x': 0,
                'window_position_y': 0,
                'viewport_width': 1280,
                'viewport_height': 720,
                # iFrame settings
                'cross_origin_iframes': True,
                'max_iframes': 100,
                'max_iframe_depth': 5,
                # Timing settings
                'minimum_wait_page_load_time': 0.25,
                'wait_for_network_idle_page_load_time': 0.5,
                'wait_between_actions': 0.1,
                # UI/DOM settings
                'highlight_elements': True,
                'dom_highlight_elements': False,
                'filter_highlight_ids': True,
                'paint_order_filtering': True,
                'interaction_highlight_color': 'rgb(255, 127, 39)',
                'interaction_highlight_duration': 1.0,
                # Downloads
                'auto_download_pdfs': True,
                # Recording
                'record_video_dir': '',
                'record_video_framerate': 30,
            }
        ]
    }


@IPCHandlerRegistry.handler('get_browser_use_settings')
def handle_get_browser_use_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle get browser-use settings request.
    
    Returns the current browser-use settings including agent settings,
    browser session settings, and browser profiles.
    
    Args:
        request: IPC request object
        params: Request parameters (not required)
        
    Returns:
        IPCResponse with browser-use settings data
    """
    try:
        logger.debug("Get browser-use settings handler called")
        
        settings = load_browser_use_settings()
        
        return create_success_response(request, settings)
        
    except Exception as e:
        logger.error(f"Error in get browser-use settings handler: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'BROWSER_USE_SETTINGS_ERROR',
            f"Error getting browser-use settings: {str(e)}"
        )


@IPCHandlerRegistry.handler('save_browser_use_settings')
def handle_save_browser_use_settings(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Handle save browser-use settings request.
    
    Saves browser-use settings including agent settings,
    browser session settings, and browser profiles.
    
    Args:
        request: IPC request object
        params: Request parameters containing 'settings' dict
        
    Returns:
        IPCResponse indicating success or failure
    """
    try:
        logger.debug(f"Save browser-use settings handler called with params: {params}")
        
        if not params or 'settings' not in params:
            logger.warning("No settings data provided")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'No settings data provided'
            )
        
        settings_data = params['settings']
        
        if not isinstance(settings_data, dict):
            logger.warning(f"Invalid settings data format: {type(settings_data)}")
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Settings data must be a dictionary'
            )
        
        # Validate required keys
        required_keys = ['agentSettings', 'browserSessionSettings', 'profiles']
        for key in required_keys:
            if key not in settings_data:
                logger.warning(f"Missing required key: {key}")
                return create_error_response(
                    request,
                    'INVALID_PARAMS',
                    f'Missing required key: {key}'
                )
        
        # Validate profiles
        profiles = settings_data.get('profiles', [])
        if not isinstance(profiles, list):
            return create_error_response(
                request,
                'INVALID_PARAMS',
                'Profiles must be a list'
            )
        
        # Ensure at least one profile exists
        if len(profiles) == 0:
            settings_data['profiles'] = get_default_browser_use_settings()['profiles']
        
        # Ensure exactly one default profile
        default_count = sum(1 for p in profiles if p.get('isDefault', False))
        if default_count == 0 and len(profiles) > 0:
            profiles[0]['isDefault'] = True
        elif default_count > 1:
            # Keep only the first default
            found_default = False
            for p in profiles:
                if p.get('isDefault', False):
                    if found_default:
                        p['isDefault'] = False
                    else:
                        found_default = True
        
        # Save settings
        if save_browser_use_settings_to_file(settings_data):
            return create_success_response(request, {
                'message': 'Browser-use settings saved successfully'
            })
        else:
            return create_error_response(
                request,
                'SAVE_ERROR',
                'Failed to save browser-use settings to file'
            )
        
    except Exception as e:
        logger.error(f"Error in save browser-use settings handler: {e}\n{traceback.format_exc()}")
        return create_error_response(
            request,
            'BROWSER_USE_SETTINGS_ERROR',
            f"Error saving browser-use settings: {str(e)}"
        )


def get_default_profile() -> Optional[Dict[str, Any]]:
    """Get the default browser profile from settings."""
    settings = load_browser_use_settings()
    profiles = settings.get('profiles', [])
    
    for profile in profiles:
        if profile.get('isDefault', False):
            return profile
    
    # Return first profile if no default found
    if profiles:
        return profiles[0]
    
    return None


def get_profile_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get a browser profile by name."""
    settings = load_browser_use_settings()
    profiles = settings.get('profiles', [])
    
    for profile in profiles:
        if profile.get('name', '') == name or profile.get('id', '') == name:
            return profile
    
    return None


def get_agent_settings() -> Dict[str, Any]:
    """Get the current agent settings."""
    settings = load_browser_use_settings()
    return settings.get('agentSettings', get_default_browser_use_settings()['agentSettings'])


def get_browser_session_settings() -> Dict[str, Any]:
    """Get the current browser session settings."""
    settings = load_browser_use_settings()
    return settings.get('browserSessionSettings', get_default_browser_use_settings()['browserSessionSettings'])
