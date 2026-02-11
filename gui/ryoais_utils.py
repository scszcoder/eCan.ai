"""
RyoAIS utilities for fetching and merging dynamic model lists into provider configurations.

This module provides shared functions to:
- Fetch models from RyoAIS OpenAI-compatible API
- Manage ryoais_models.json file (save/load/get path)
- Merge RyoAIS models into provider configurations
Similar to ollama_utils.py but for RyoAIS OpenAI-compatible API.
"""

import json
import logging
from os.path import exists
from typing import Dict, List, Any, Optional, Tuple

from utils.logger_helper import logger_helper as logger


# ==================== RyoAIS Models File Management ====================

def get_ryoais_models_path(username: str = None) -> str:
    """
    Get the path to ryoais_models.json file for the current user.
    
    Args:
        username: Optional username/email. If None, tries to get from AppContext.
    
    Returns:
        Full path to ryoais_models.json
    """
    from utils.user_path_helper import ensure_user_data_dir
    
    # Get user data directory under resource/data
    user_data_dir = ensure_user_data_dir(username, "resource/data")
    return f"{user_data_dir}/ryoais_models.json"


def save_ryoais_models(models: list, host: str, username: str = None) -> bool:
    """
    Save RyoAIS models to ryoais_models.json file.
    
    Args:
        models: List of model info dicts
        host: RyoAIS API host
        username: Optional username/email
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        models_path = get_ryoais_models_path(username)
        data = {
            'host': host,
            'models': models,
            'updated_at': __import__('datetime').datetime.now().isoformat()
        }
        with open(models_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"[RyoAIS] Saved {len(models)} models to {models_path}")
        return True
    except Exception as e:
        logger.error(f"[RyoAIS] Failed to save ryoais_models.json: {e}")
        return False


def load_ryoais_models(username: str = None, model_type: str = None) -> dict:
    """
    Load RyoAIS models from ryoais_models.json file.
    
    Args:
        username: Optional username/email
        model_type: Optional model type filter ('llm', 'embedding', 'rerank'). If None, returns all models.
    
    Returns:
        Dict with 'host' and 'models' keys, or empty dict if file doesn't exist
    """
    try:
        models_path = get_ryoais_models_path(username)
        if not exists(models_path):
            logger.debug(f"[RyoAIS] ryoais_models.json not found at {models_path}")
            return {}
        
        with open(models_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Filter by model_type if specified
        if model_type:
            all_models = data.get('models', [])
            filtered_models = [m for m in all_models if m.get('type') == model_type]
            data['models'] = filtered_models
            logger.debug(f"[RyoAIS] Loaded {len(filtered_models)} {model_type} models from {models_path}")
        else:
            logger.debug(f"[RyoAIS] Loaded {len(data.get('models', []))} models from {models_path}")
        
        return data
    except Exception as e:
        logger.error(f"[RyoAIS] Failed to load ryoais_models.json: {e}")
        return {}


def _detect_embedding_dimension(host: str, model_id: str, api_key: str = None) -> int:
    """
    Detect the actual embedding dimension by making a test API call.
    
    Args:
        host: RyoAIS API host
        model_id: Model ID to test
        api_key: Optional API key for authentication
    
    Returns:
        Embedding dimension (int), or None if detection fails
    """
    import requests
    
    try:
        embeddings_url = f"{host}/embeddings"
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        payload = {
            'model': model_id,
            'input': 'test'
        }
        
        response = requests.post(embeddings_url, json=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                embedding = data['data'][0].get('embedding', [])
                dimension = len(embedding)
                logger.info(f"[RyoAIS] Detected dimension for {model_id}: {dimension}")
                return dimension
        else:
            logger.warning(f"[RyoAIS] Failed to detect dimension for {model_id}: HTTP {response.status_code}")
    except Exception as e:
        logger.warning(f"[RyoAIS] Error detecting dimension for {model_id}: {e}")
    
    return None


def fetch_ryoais_models(host: str, api_key: str = None, username: str = None) -> Tuple[bool, list, str]:
    """
    Fetch available models from RyoAIS OpenAI-compatible API and save to local file.
    
    Args:
        host: RyoAIS API host (e.g., 'http://localhost/v1')
        api_key: Optional API key for authentication
        username: Optional username for saving to user-specific path
    
    Returns:
        Tuple of (success: bool, models: list, error_message: str)
    """
    import requests
    
    try:
        import time
        start_time = time.time()
        
        # Normalize host - remove trailing slash
        host = host.rstrip('/')
        
        # Call OpenAI-compatible API to get models
        api_url = f"{host}/models"
        
        logger.info(f"[RyoAIS] Fetching models from: {api_url}")
        
        # Prepare headers
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        
        response = requests.get(api_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            error_msg = f"RyoAIS API returned status {response.status_code}"
            logger.warning(f"[RyoAIS] {error_msg}")
            return False, [], error_msg
        
        data = response.json()
        models_data = data.get('data', [])
        
        # Extract model info
        model_list = []
        embedding_models_to_test = []
        
        for model in models_data:
            model_id = model.get('id', '')
            if model_id:
                model_info = {
                    'name': model_id,
                    'id': model_id,
                    'object': model.get('object', 'model'),
                    'created': model.get('created', 0),
                    'owned_by': model.get('owned_by', 'ryoais')
                }
                
                # Detect model type based on name
                model_name_lower = model_id.lower()
                if 'embed' in model_name_lower:
                    model_info['type'] = 'embedding'
                    # Try to detect embedding dimension from API response
                    if 'dimensions' in model:
                        model_info['dimensions'] = model.get('dimensions')
                    else:
                        # Mark for dimension detection
                        embedding_models_to_test.append(model_info)
                elif 'rerank' in model_name_lower:
                    model_info['type'] = 'rerank'
                # BGE models are primarily embedding models, but some can be used for both
                elif 'bge' in model_name_lower:
                    # bge-m3 and bge-large can be used as both embedding and LLM
                    # Default to embedding, but also mark as available for LLM
                    model_info['type'] = 'embedding'
                    model_info['supports_llm'] = True
                    # Mark for dimension detection
                    embedding_models_to_test.append(model_info)
                else:
                    model_info['type'] = 'llm'
                
                model_list.append(model_info)
        
        # Detect dimensions for embedding models (limit to first 5 to avoid too many API calls)
        if embedding_models_to_test:
            logger.info(f"[RyoAIS] Detecting dimensions for {len(embedding_models_to_test)} embedding models...")
            for model_info in embedding_models_to_test[:5]:  # Limit to 5 models
                dimension = _detect_embedding_dimension(host, model_info['id'], api_key)
                if dimension:
                    model_info['dimensions'] = dimension
        
        total_duration = time.time() - start_time
        logger.info(f"[RyoAIS] Found {len(model_list)} models (total time: {total_duration:.2f}s)")
        
        # Save to local file for later use by providers
        save_ryoais_models(model_list, host, username)
        
        return True, model_list, None
        
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Cannot connect to RyoAIS at {host}"
        logger.warning(f"[RyoAIS] Connection error: {e}")
        return False, [], error_msg
    except requests.exceptions.Timeout:
        error_msg = "RyoAIS API request timed out"
        logger.warning(f"[RyoAIS] {error_msg}")
        return False, [], error_msg
    except Exception as e:
        error_msg = f"Error fetching RyoAIS models: {e}"
        logger.error(f"[RyoAIS] {error_msg}")
        return False, [], error_msg


# ==================== RyoAIS Model Merging ====================

def merge_ryoais_models_to_dict_provider(
    provider: Dict[str, Any], 
    ryoais_models: Dict[str, Any],
    model_type: str = 'llm'
) -> Dict[str, Any]:
    """
    Merge RyoAIS models from ryoais_models.json into a dict-based provider's supported_models.
    
    Args:
        provider: Provider dict to merge models into
        ryoais_models: Dict loaded from ryoais_models.json with 'models' and 'host' keys
        model_type: Type of models to filter ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated provider dict with merged models
    """
    if not ryoais_models or not ryoais_models.get('models'):
        return provider
    
    # Create a copy to avoid modifying original
    provider = provider.copy()
    
    # Get existing supported_models or empty list
    existing_models = provider.get('supported_models', [])
    existing_model_names = {m.get('name') for m in existing_models if isinstance(m, dict)}
    
    # Filter and convert RyoAIS models to supported_models format
    new_models = []
    for model in ryoais_models.get('models', []):
        # Filter by model type
        if model.get('type') != model_type:
            continue
        
        model_name = model.get('name', '')
        if model_name and model_name not in existing_model_names:
            new_model = {
                'name': model_name,
                'display_name': model_name,
                'model_id': model_name,
                'description': f"RyoAIS {model_type} model: {model_name}"
            }
            
            # Add type-specific fields
            if model_type == 'llm':
                new_model.update({
                    'default_temperature': 0.7,
                    'max_tokens': 8192,
                    'supports_streaming': True,
                    'supports_function_calling': True,
                    'supports_vision': False,
                    'cost_per_1k_tokens': 0.0
                })
            elif model_type == 'embedding':
                new_model.update({
                    'dimensions': model.get('dimensions', 1024),
                    'max_tokens': 8192
                })
            elif model_type == 'rerank':
                new_model.update({
                    'max_chunks_per_doc': 1000
                })
            
            new_models.append(new_model)
    
    # Merge models
    provider['supported_models'] = existing_models + new_models
    
    # Update base_url if host is available and not already set
    if ryoais_models.get('host') and not provider.get('base_url'):
        provider['base_url'] = ryoais_models.get('host')
    
    # Set api_key_configured to True if API key is available
    provider['api_key_configured'] = True
    
    logger.debug(f"[RyoAIS] Merged {len(new_models)} {model_type} models into dict provider")
    return provider


def merge_ryoais_models_to_config_provider(
    provider,
    ryoais_models: Dict[str, Any],
    provider_type: str = 'llm'
):
    """
    Merge RyoAIS models from ryoais_models.json into a config-based provider's supported_models.
    
    Args:
        provider: Provider config object (LLMProviderConfig, EmbeddingProviderConfig, or RerankProviderConfig)
        ryoais_models: Dict loaded from ryoais_models.json with 'models' and 'host' keys
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated provider config object with merged models
    """
    if not ryoais_models or not ryoais_models.get('models'):
        return provider
    
    # Import the appropriate ModelConfig class based on provider type
    if provider_type == 'llm':
        from gui.config.llm_config import LLMModelConfig
        ModelConfigClass = LLMModelConfig
        extra_kwargs = {
            'provider': provider.provider,
            'supports_streaming': True,
            'supports_function_calling': True,
            'supports_vision': False
        }
    elif provider_type == 'embedding':
        from gui.config.embedding_config import EmbeddingModelConfig
        ModelConfigClass = EmbeddingModelConfig
        extra_kwargs = {
            'dimensions': 1024
        }
    elif provider_type == 'rerank':
        from gui.config.rerank_config import RerankModelConfig
        ModelConfigClass = RerankModelConfig
        extra_kwargs = {}
    else:
        logger.warning(f"[RyoAIS] Unknown provider type: {provider_type}")
        return provider
    
    # Convert RyoAIS models to ModelConfig objects
    ryoais_model_configs = []
    models_list = ryoais_models.get('models', [])
    logger.debug(f"[RyoAIS] Processing {len(models_list)} models from ryoais_models for {provider_type}")
    
    for model in models_list:
        # Filter by model type
        if model.get('type') != provider_type:
            continue
        
        model_name = model.get('name', '')
        if model_name:
            logger.debug(f"[RyoAIS] Creating config for model: {model_name}")
            try:
                model_kwargs = extra_kwargs.copy()
                
                # Add embedding dimensions if available
                if provider_type == 'embedding' and model.get('dimensions'):
                    model_kwargs['dimensions'] = model.get('dimensions')
                
                model_config = ModelConfigClass(
                    name=model_name,
                    model_id=model_name,
                    display_name=model_name,
                    **model_kwargs
                )
                
                ryoais_model_configs.append(model_config)
            except Exception as e:
                logger.warning(f"[RyoAIS] Failed to create model config for {model_name}: {e}", exc_info=True)
    
    # Replace supported_models with RyoAIS models
    provider.supported_models = ryoais_model_configs
    
    logger.debug(f"[RyoAIS] Merged {len(ryoais_model_configs)} models into {provider_type} config provider")
    return provider


def merge_ryoais_models_to_providers(
    providers: List[Dict[str, Any]], 
    ryoais_models: Optional[Dict[str, Any]] = None,
    provider_type: str = 'llm'
) -> List[Dict[str, Any]]:
    """
    Merge RyoAIS models into a list of dict-based providers.
    
    Args:
        providers: List of provider dicts
        ryoais_models: Optional pre-loaded ryoais_models dict. If None, will load from file.
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated list of providers with RyoAIS models merged
    """
    # Load RyoAIS models if not provided
    if ryoais_models is None:
        try:
            ryoais_models = load_ryoais_models(model_type=provider_type)
        except Exception as e:
            logger.warning(f"[RyoAIS] Failed to load ryoais_models: {e}")
            return providers
    
    if not ryoais_models or not ryoais_models.get('models'):
        logger.debug(f"[RyoAIS] No models found in ryoais_models for {provider_type}")
        return providers
    
    # Find and update RyoAIS provider
    updated_providers = []
    ryoais_found = False
    
    for provider in providers:
        provider_name = (provider.get('name') or '').lower()
        provider_id = (provider.get('provider') or '').lower()
        
        # Check if this is a RyoAIS provider
        if 'ryoais' in provider_name or 'ryoais' in provider_id:
            provider = merge_ryoais_models_to_dict_provider(provider, ryoais_models, provider_type)
            ryoais_found = True
            logger.info(f"[RyoAIS] Merged {len([m for m in ryoais_models.get('models', []) if m.get('type') == provider_type])} models into {provider_type.upper()} RyoAIS provider")
        
        updated_providers.append(provider)
    
    if not ryoais_found:
        logger.debug(f"[RyoAIS] No RyoAIS provider found in {provider_type} providers list")
    
    return updated_providers


def merge_ryoais_models_to_config_providers(
    providers: Dict[str, Any],
    ryoais_models: Optional[Dict[str, Any]] = None,
    provider_type: str = 'llm'
) -> Dict[str, Any]:
    """
    Merge RyoAIS models into a dict of config-based providers.
    
    Args:
        providers: Dict of provider configs (key: provider_name, value: provider_config)
        ryoais_models: Optional pre-loaded ryoais_models dict. If None, will load from file.
        provider_type: Type of provider ('llm', 'embedding', or 'rerank')
    
    Returns:
        Updated dict of providers with RyoAIS models merged
    """
    # Load RyoAIS models if not provided
    if ryoais_models is None:
        try:
            ryoais_models = load_ryoais_models(model_type=provider_type)
        except Exception as e:
            logger.warning(f"[RyoAIS] Failed to load ryoais_models: {e}")
            return providers
    
    if not ryoais_models or not ryoais_models.get('models'):
        logger.debug(f"[RyoAIS] No models found in ryoais_models for {provider_type}")
        return providers
    
    # Find and update RyoAIS provider
    ryoais_found = False
    for provider_key, provider in providers.items():
        if hasattr(provider, 'provider') and provider.provider.value.lower() == 'ryoais':
            merge_ryoais_models_to_config_provider(provider, ryoais_models, provider_type)
            ryoais_found = True
            logger.info(f"[RyoAIS] Merged {len([m for m in ryoais_models.get('models', []) if m.get('type') == provider_type])} models into {provider_type.upper()} RyoAIS config provider")
            break
    
    if not ryoais_found:
        logger.debug(f"[RyoAIS] No RyoAIS provider found in {provider_type} config providers dict")
    
    return providers
