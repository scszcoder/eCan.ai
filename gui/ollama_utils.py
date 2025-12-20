"""
Ollama utilities for merging dynamic model lists into provider configurations.

This module provides shared functions to:
- Manage ollama_tags.json file (save/load/get path)
- Merge Ollama models from ollama_tags.json into provider configurations
Used by multiple handlers to ensure consistency.
"""

import json
import logging
from os.path import exists
from typing import Dict, List, Any, Optional

logger = logging.getLogger('eCan')


# ==================== Ollama Tags File Management ====================

def get_ollama_tags_path(username: str = None) -> str:
    """
    Get the path to ollama_tags.json file for the current user.
    
    Args:
        username: Optional username/email. If None, tries to get from AppContext.
    
    Returns:
        Full path to ollama_tags.json
    """
    from utils.user_path_helper import ensure_user_data_dir
    
    # Get user data directory under resource/data
    user_data_dir = ensure_user_data_dir(username, "resource/data")
    return f"{user_data_dir}/ollama_tags.json"


def save_ollama_tags(models: list, host: str, username: str = None) -> bool:
    """
    Save Ollama models to ollama_tags.json file.
    
    Args:
        models: List of model info dicts
        host: Ollama API host
        username: Optional username/email
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        tags_path = get_ollama_tags_path(username)
        data = {
            'host': host,
            'models': models,
            'updated_at': __import__('datetime').datetime.now().isoformat()
        }
        with open(tags_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[Ollama] Saved {len(models)} models to {tags_path}")
        return True
    except Exception as e:
        logger.error(f"[Ollama] Failed to save ollama_tags.json: {e}")
        return False


def load_ollama_tags(username: str = None) -> dict:
    """
    Load Ollama models from ollama_tags.json file.
    
    Args:
        username: Optional username/email
    
    Returns:
        Dict with 'host' and 'models' keys, or empty dict if file doesn't exist
    """
    try:
        tags_path = get_ollama_tags_path(username)
        if not exists(tags_path):
            logger.debug(f"[Ollama] ollama_tags.json not found at {tags_path}")
            return {}
        
        with open(tags_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        logger.debug(f"[Ollama] Loaded {len(data.get('models', []))} models from {tags_path}")
        return data
    except Exception as e:
        logger.error(f"[Ollama] Failed to load ollama_tags.json: {e}")
        return {}


def fetch_ollama_models(host: str, username: str = None) -> tuple:
    """
    Fetch available models from Ollama API and save to local file.
    
    Args:
        host: Ollama API host (e.g., 'http://127.0.0.1:11434')
        username: Optional username for saving to user-specific path
    
    Returns:
        Tuple of (success: bool, models: list, error_message: str)
    """
    import requests
    
    try:
        # Normalize host - remove trailing slash
        host = host.rstrip('/')
        
        # Call Ollama API to get tags (models)
        api_url = f"{host}/api/tags"
        
        logger.info(f"[Ollama] Fetching models from: {api_url}")
        
        response = requests.get(api_url, timeout=10)
        
        if response.status_code != 200:
            error_msg = f"Ollama API returned status {response.status_code}"
            logger.warning(f"[Ollama] {error_msg}")
            return False, [], error_msg
        
        data = response.json()
        models = data.get('models', [])
        
        # Extract model names and fetch detailed info for each
        model_list = []
        for model in models:
            model_name = model.get('name', '')
            if model_name:
                # Get basic model details from /api/tags
                model_info = {
                    'name': model_name,
                    'size': model.get('size', 0),
                    'modified_at': model.get('modified_at', ''),
                    'digest': model.get('digest', ''),
                    'details': model.get('details', {})
                }
                
                # Fetch detailed model info from /api/show
                try:
                    show_url = f"{host}/api/show"
                    show_response = requests.post(
                        show_url,
                        json={"name": model_name},
                        timeout=5
                    )
                    
                    if show_response.status_code == 200:
                        show_data = show_response.json()
                        model_info_data = show_data.get('model_info', {})
                        
                        # Extract useful information from model_info
                        # Try to find embedding dimension
                        embedding_dim = None
                        context_length = None
                        
                        for key, value in model_info_data.items():
                            # Find embedding dimension
                            if 'embedding' in key.lower() and ('length' in key.lower() or 'dim' in key.lower()):
                                embedding_dim = value
                            # Find context length
                            elif 'context' in key.lower() and 'length' in key.lower():
                                context_length = value
                        
                        # Add to model_info
                        if embedding_dim:
                            model_info['embedding_dim'] = embedding_dim
                        if context_length:
                            model_info['context_length'] = context_length
                            model_info['max_tokens'] = context_length  # Use context_length as max_tokens
                        
                        # Store full model_info for advanced use
                        model_info['model_info'] = model_info_data
                        
                        logger.debug(f"[Ollama] Model {model_name}: embedding_dim={embedding_dim}, context_length={context_length}")
                    
                except Exception as e:
                    logger.debug(f"[Ollama] Failed to get detailed info for {model_name}: {e}")
                
                model_list.append(model_info)
        
        logger.info(f"[Ollama] Found {len(model_list)} models with detailed info")
        
        # Save to local file for later use by providers
        save_ollama_tags(model_list, host, username)
        
        return True, model_list, None
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Cannot connect to Ollama at {host}"
        logger.warning(f"[Ollama] Connection error: {e}")
        return False, [], error_msg
    except requests.exceptions.Timeout:
        error_msg = "Ollama API request timed out"
        logger.warning(f"[Ollama] {error_msg}")
        return False, [], error_msg
    except Exception as e:
        error_msg = f"Error fetching Ollama models: {e}"
        logger.error(f"[Ollama] {error_msg}")
        return False, [], error_msg


# ==================== Ollama Model Merging ====================


def merge_ollama_models_to_dict_provider(provider: Dict[str, Any], ollama_tags: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge Ollama models from ollama_tags.json into a dict-based provider's supported_models.
    
    This is used for handlers that work with dict-based providers (e.g., from manager.get_all_providers()).
    
    Args:
        provider: Provider dict to merge models into
        ollama_tags: Dict loaded from ollama_tags.json with 'models' and 'host' keys
    
    Returns:
        Updated provider dict with merged models
    """
    if not ollama_tags or not ollama_tags.get('models'):
        return provider
    
    # Create a copy to avoid modifying original
    provider = provider.copy()
    
    # Get existing supported_models or empty list
    existing_models = provider.get('supported_models', [])
    existing_model_names = {m.get('name') for m in existing_models if isinstance(m, dict)}
    
    # Convert Ollama tags to supported_models format
    new_models = []
    for model in ollama_tags.get('models', []):
        model_name = model.get('name', '')
        if model_name and model_name not in existing_model_names:
            new_model = {
                'name': model_name,
                'display_name': model_name,
                'model_id': model_name,
                'default_temperature': 0.7,
                'max_tokens': model.get('max_tokens', model.get('context_length', 8192)),  # Use actual context_length if available
                'supports_streaming': True,
                'supports_function_calling': False,
                'supports_vision': False,
                'cost_per_1k_tokens': 0.0,
                'description': f"Ollama model: {model_name}"
            }
            
            # Add detailed model info if available
            if model.get('size'):
                new_model['size'] = model.get('size')
            if model.get('embedding_dim'):
                new_model['embedding_dim'] = model.get('embedding_dim')
            if model.get('context_length'):
                new_model['context_length'] = model.get('context_length')
            if model.get('modified_at'):
                new_model['modified_at'] = model.get('modified_at')
            
            new_models.append(new_model)
    
    # Merge models
    provider['supported_models'] = existing_models + new_models
    
    # Update base_url if host is available and not already set
    if ollama_tags.get('host') and not provider.get('base_url'):
        provider['base_url'] = ollama_tags.get('host')
    
    # Set api_key_configured to True for local Ollama
    provider['api_key_configured'] = True
    
    logger.debug(f"[Ollama] Merged {len(new_models)} models into dict provider")
    return provider


def merge_ollama_models_to_config_provider(provider, ollama_tags: Dict[str, Any], provider_type: str = 'llm'):
    """
    Merge Ollama models from ollama_tags.json into a config-based provider's supported_models.
    
    This is used for handlers that work with config objects (e.g., LLMProviderConfig).
    
    Args:
        provider: Provider config object (LLMProviderConfig, EmbeddingProviderConfig, or RerankProviderConfig)
        ollama_tags: Dict loaded from ollama_tags.json with 'models' and 'host' keys
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated provider config object with merged models
    """
    if not ollama_tags or not ollama_tags.get('models'):
        return provider
    
    # Import the appropriate ModelConfig class based on provider type
    if provider_type == 'llm':
        from gui.config.llm_config import LLMModelConfig
        ModelConfigClass = LLMModelConfig
        extra_kwargs = {
            'provider': provider.provider,  # Add required provider parameter
            'supports_streaming': True,
            'supports_function_calling': False,
            'supports_vision': False
        }
    elif provider_type == 'embedding':
        from gui.config.embedding_config import EmbeddingModelConfig
        ModelConfigClass = EmbeddingModelConfig
        extra_kwargs = {
            'dimensions': 1024  # Default, will be auto-detected
        }
    elif provider_type == 'rerank':
        from gui.config.rerank_config import RerankModelConfig
        ModelConfigClass = RerankModelConfig
        extra_kwargs = {}
    else:
        logger.warning(f"[Ollama] Unknown provider type: {provider_type}")
        return provider
    
    # Convert Ollama tags to ModelConfig objects
    ollama_models = []
    models_list = ollama_tags.get('models', [])
    logger.debug(f"[Ollama] Processing {len(models_list)} models from ollama_tags for {provider_type}")
    
    for model in models_list:
        model_name = model.get('name', '')
        if model_name:
            logger.debug(f"[Ollama] Creating config for model: {model_name}")
            try:
                # Prepare kwargs with detailed model info
                model_kwargs = extra_kwargs.copy()
                
                # Add context_length/max_tokens for LLM models
                if provider_type == 'llm':
                    if model.get('context_length'):
                        model_kwargs['max_tokens'] = model.get('context_length')
                    elif model.get('max_tokens'):
                        model_kwargs['max_tokens'] = model.get('max_tokens')
                
                # Add embedding_dim for embedding models
                if provider_type == 'embedding' and model.get('embedding_dim'):
                    model_kwargs['dimensions'] = model.get('embedding_dim')
                
                model_config = ModelConfigClass(
                    name=model_name,
                    model_id=model_name,
                    display_name=model_name,
                    **model_kwargs
                )
                
                # Store additional metadata
                if hasattr(model_config, '__dict__'):
                    if model.get('size'):
                        model_config.size = model.get('size')
                    if model.get('embedding_dim'):
                        model_config.embedding_dim = model.get('embedding_dim')
                    if model.get('context_length'):
                        model_config.context_length = model.get('context_length')
                
                ollama_models.append(model_config)
            except Exception as e:
                logger.warning(f"[Ollama] Failed to create model config for {model_name}: {e}", exc_info=True)
    
    # Replace supported_models with Ollama models
    provider.supported_models = ollama_models
    
    logger.debug(f"[Ollama] Merged {len(ollama_models)} models into {provider_type} config provider")
    return provider


def merge_ollama_models_to_providers(
    providers: List[Dict[str, Any]], 
    ollama_tags: Optional[Dict[str, Any]] = None,
    provider_type: str = 'llm'
) -> List[Dict[str, Any]]:
    """
    Merge Ollama models into a list of dict-based providers.
    
    This is the main entry point for merging Ollama models into provider lists.
    It automatically loads ollama_tags if not provided.
    
    Args:
        providers: List of provider dicts
        ollama_tags: Optional pre-loaded ollama_tags dict. If None, will load from file.
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated list of providers with Ollama models merged
    """
    # Load Ollama tags if not provided
    if ollama_tags is None:
        try:
            ollama_tags = load_ollama_tags()
        except Exception as e:
            logger.warning(f"[Ollama] Failed to load ollama_tags: {e}")
            return providers
    
    if not ollama_tags or not ollama_tags.get('models'):
        logger.debug(f"[Ollama] No models found in ollama_tags for {provider_type}")
        return providers
    
    # Find and update Ollama provider
    updated_providers = []
    ollama_found = False
    
    for provider in providers:
        provider_name = (provider.get('name') or '').lower()
        provider_id = (provider.get('provider') or '').lower()
        class_name = (provider.get('class_name') or '').lower()
        
        # Check if this is an Ollama provider
        if 'ollama' in provider_name or 'ollama' in provider_id or 'ollama' in class_name:
            provider = merge_ollama_models_to_dict_provider(provider, ollama_tags)
            ollama_found = True
            logger.info(f"[Ollama] Merged {len(ollama_tags.get('models', []))} models into {provider_type.upper()} Ollama provider")
        
        updated_providers.append(provider)
    
    if not ollama_found:
        logger.debug(f"[Ollama] No Ollama provider found in {provider_type} providers list")
    
    return updated_providers


def merge_ollama_models_to_config_providers(
    providers: Dict[str, Any],
    ollama_tags: Optional[Dict[str, Any]] = None,
    provider_type: str = 'llm'
) -> Dict[str, Any]:
    """
    Merge Ollama models into a dict of config-based providers.
    
    This is used for LightRAG Settings which works with config objects.
    
    Args:
        providers: Dict of provider configs (key: provider_name, value: provider_config)
        ollama_tags: Optional pre-loaded ollama_tags dict. If None, will load from file.
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated dict of providers with Ollama models merged
    """
    # Load Ollama tags if not provided
    if ollama_tags is None:
        try:
            ollama_tags = load_ollama_tags()
        except Exception as e:
            logger.warning(f"[Ollama] Failed to load ollama_tags: {e}")
            return providers
    
    if not ollama_tags or not ollama_tags.get('models'):
        logger.debug(f"[Ollama] No models found in ollama_tags for {provider_type}")
        return providers
    
    # Find and update Ollama provider
    ollama_found = False
    for provider_key, provider in providers.items():
        if hasattr(provider, 'provider') and provider.provider.value.lower() == 'ollama':
            merge_ollama_models_to_config_provider(provider, ollama_tags, provider_type)
            ollama_found = True
            logger.info(f"[Ollama] Merged {len(ollama_tags.get('models', []))} models into {provider_type.upper()} Ollama config provider")
            break
    
    if not ollama_found:
        logger.debug(f"[Ollama] No Ollama provider found in {provider_type} config providers dict")
    
    return providers
