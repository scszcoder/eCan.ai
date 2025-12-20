"""
Label Configuration IPC handlers.
Provides loading and saving of shipping label configurations.
"""

import os
import json
from pathlib import Path
from typing import Any, Optional, Dict, List
from ..types import IPCRequest, IPCResponse, create_success_response, create_error_response
from ..registry import IPCHandlerRegistry
from utils.logger_helper import logger_helper as logger

# Project paths (same pattern as prompt_handler.py)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SYSTEM_LABEL_CONFIGS_DIR = PROJECT_ROOT / "resource" / "systems" / "sample_label_configs"
USER_LABEL_CONFIGS_DIR = PROJECT_ROOT / "resource" / "my_label_configs"

# Log when this module is imported (handler registration happens at import time)
logger.info("[LabelConfig] label_config_handler module loaded - handlers being registered")
logger.info(f"[LabelConfig] System configs dir: {SYSTEM_LABEL_CONFIGS_DIR}")
logger.info(f"[LabelConfig] User configs dir: {USER_LABEL_CONFIGS_DIR}")


def _get_system_label_configs_dir() -> str:
    """Get the system (pre-configured) label configs directory."""
    return str(SYSTEM_LABEL_CONFIGS_DIR)


def _get_user_label_configs_dir() -> str:
    """Get the user-defined label configs directory."""
    return str(USER_LABEL_CONFIGS_DIR)


def _load_configs_from_dir(directory: str) -> List[Dict[str, Any]]:
    """Load all JSON config files from a directory."""
    configs = []
    if not os.path.exists(directory):
        return configs
    
    for filename in os.listdir(directory):
        if filename.endswith('.json'):
            filepath = os.path.join(directory, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    config['_filepath'] = filepath
                    config['_filename'] = filename
                    configs.append(config)
            except Exception as e:
                logger.error(f"[LabelConfig] Failed to load {filepath}: {e}")
    
    return configs


@IPCHandlerRegistry.handler('label_config.get_all')
def handle_get_all_label_configs(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Get all label configurations (both system and user-defined).
    
    Returns:
        IPCResponse with:
        - system_configs: List of pre-configured label configs
        - user_configs: List of user-defined label configs
    """
    try:
        system_dir = _get_system_label_configs_dir()
        user_dir = _get_user_label_configs_dir()
        
        logger.info(f"[LabelConfig] Loading configs from system: {system_dir}, exists: {os.path.exists(system_dir)}")
        logger.info(f"[LabelConfig] Loading configs from user: {user_dir}, exists: {os.path.exists(user_dir)}")
        
        if os.path.exists(system_dir):
            logger.info(f"[LabelConfig] System dir contents: {os.listdir(system_dir)}")
        
        system_configs = _load_configs_from_dir(system_dir)
        user_configs = _load_configs_from_dir(user_dir)
        
        logger.info(f"[LabelConfig] Loaded {len(system_configs)} system configs, {len(user_configs)} user configs")
        if system_configs:
            logger.info(f"[LabelConfig] System config names: {[c.get('name') for c in system_configs]}")
        
        return create_success_response(request, {
            'system_configs': system_configs,
            'user_configs': user_configs
        })
    except Exception as e:
        logger.error(f"[LabelConfig] Error loading configs: {e}", exc_info=True)
        return create_error_response(request, 'LOAD_ERROR', str(e))


@IPCHandlerRegistry.handler('label_config.save')
def handle_save_label_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Save a user-defined label configuration.
    
    Args:
        params: Dict containing the label config to save
            - config: The label configuration object
            - overwrite: Whether to overwrite existing file (default False)
    
    Returns:
        IPCResponse with saved file info or error
    """
    try:
        if not params:
            return create_error_response(request, 'MISSING_PARAMS', 'No parameters provided')
        
        config = params.get('config')
        overwrite = params.get('overwrite', False)
        
        if not config:
            return create_error_response(request, 'MISSING_CONFIG', 'No config provided')
        
        if not config.get('name') or not config.get('id'):
            return create_error_response(request, 'INVALID_CONFIG', 'Config must have name and id')
        
        user_dir = _get_user_label_configs_dir()
        
        # Create directory if it doesn't exist
        os.makedirs(user_dir, exist_ok=True)
        
        # Generate filename from id
        filename = f"{config['id']}.json"
        filepath = os.path.join(user_dir, filename)
        
        # Check for duplicate name (not id) in existing configs
        existing_configs = _load_configs_from_dir(user_dir)
        for existing in existing_configs:
            if existing.get('name') == config['name'] and existing.get('id') != config['id']:
                return create_error_response(
                    request, 
                    'DUPLICATE_NAME', 
                    f"A configuration with name '{config['name']}' already exists"
                )
        
        # Check if file exists and overwrite is not allowed
        if os.path.exists(filepath) and not overwrite:
            return create_error_response(
                request, 
                'FILE_EXISTS', 
                f"Configuration '{config['id']}' already exists. Set overwrite=true to replace."
            )
        
        # Remove internal fields before saving
        save_config = {k: v for k, v in config.items() if not k.startswith('_')}
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(save_config, f, indent=2)
        
        logger.info(f"[LabelConfig] Saved config to {filepath}")
        
        return create_success_response(request, {
            'filepath': filepath,
            'filename': filename,
            'config': save_config
        })
    except Exception as e:
        logger.error(f"[LabelConfig] Error saving config: {e}", exc_info=True)
        return create_error_response(request, 'SAVE_ERROR', str(e))


@IPCHandlerRegistry.handler('label_config.delete')
def handle_delete_label_config(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Delete a user-defined label configuration.
    
    Args:
        params: Dict containing:
            - id: The config id to delete
    
    Returns:
        IPCResponse with success or error
    """
    try:
        if not params:
            return create_error_response(request, 'MISSING_PARAMS', 'No parameters provided')
        
        config_id = params.get('id')
        if not config_id:
            return create_error_response(request, 'MISSING_ID', 'No config id provided')
        
        user_dir = _get_user_label_configs_dir()
        filename = f"{config_id}.json"
        filepath = os.path.join(user_dir, filename)
        
        if not os.path.exists(filepath):
            return create_error_response(request, 'NOT_FOUND', f"Configuration '{config_id}' not found")
        
        os.remove(filepath)
        logger.info(f"[LabelConfig] Deleted config {filepath}")
        
        return create_success_response(request, {
            'deleted': True,
            'id': config_id
        })
    except Exception as e:
        logger.error(f"[LabelConfig] Error deleting config: {e}", exc_info=True)
        return create_error_response(request, 'DELETE_ERROR', str(e))


@IPCHandlerRegistry.handler('label_config.check_name')
def handle_check_label_config_name(request: IPCRequest, params: Optional[Dict[str, Any]]) -> IPCResponse:
    """Check if a label config name already exists.
    
    Args:
        params: Dict containing:
            - name: The name to check
            - exclude_id: Optional id to exclude from check (for editing existing config)
    
    Returns:
        IPCResponse with exists: bool
    """
    try:
        if not params:
            return create_error_response(request, 'MISSING_PARAMS', 'No parameters provided')
        
        name = params.get('name')
        exclude_id = params.get('exclude_id')
        
        if not name:
            return create_error_response(request, 'MISSING_NAME', 'No name provided')
        
        user_dir = _get_user_label_configs_dir()
        existing_configs = _load_configs_from_dir(user_dir)
        
        for config in existing_configs:
            if config.get('name') == name:
                if exclude_id and config.get('id') == exclude_id:
                    continue
                return create_success_response(request, {'exists': True, 'name': name})
        
        return create_success_response(request, {'exists': False, 'name': name})
    except Exception as e:
        logger.error(f"[LabelConfig] Error checking name: {e}", exc_info=True)
        return create_error_response(request, 'CHECK_ERROR', str(e))
