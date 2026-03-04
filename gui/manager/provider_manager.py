"""
Provider Manager - Centralized management for LLM provider models and configurations.

This module handles:
- Auto-refreshing provider models from APIs (RyoAIS, Ollama, etc.)
- Updating llm_providers.json configuration file with latest model info
- Managing model metadata including context_length for message compaction

This replaces scattered model management logic and provides a clean interface
for provider model operations.
"""

import json
import os
from typing import List, Dict, Any, Tuple, Optional
from utils.logger_helper import logger_helper as logger


class ProviderManager:
    """Centralized manager for LLM provider models and configurations."""
    
    def __init__(self):
        """Initialize the provider manager."""
        self.config_file = self._get_config_file_path()
    
    def _get_config_file_path(self) -> str:
        """Get the path to llm_providers.json configuration file."""
        config_dir = os.path.join(os.path.dirname(__file__), '..', 'config')
        return os.path.join(config_dir, 'llm_providers.json')
    
    def refresh_provider_models(self, provider_name: str, host: str, api_key: str = None, username: str = None) -> Tuple[bool, List[Dict], str]:
        """
        Refresh models from a provider's API and update both cache and config files.
        
        Args:
            provider_name: Provider name ('ryoais', 'ollama', etc.)
            host: API host URL
            api_key: Optional API key for authentication
            username: Optional username for user-specific cache
        
        Returns:
            Tuple of (success: bool, models: list, error_message: str)
        """
        logger.info(f"[ProviderManager] 📡 Refreshing {provider_name} models from {host}...")
        
        # Fetch models from API based on provider type
        if provider_name.lower() == 'ryoais':
            from gui.ryoais_utils import fetch_ryoais_models
            success, model_list, error_msg = fetch_ryoais_models(host, api_key, username)
        elif provider_name.lower() == 'ollama':
            from gui.ollama_utils import fetch_ollama_models
            success, model_list, error_msg = fetch_ollama_models(host, username)
        else:
            return False, [], f"Unsupported provider: {provider_name}"
        
        if not success:
            logger.warning(f"[ProviderManager] ⚠️ Failed to fetch {provider_name} models: {error_msg}")
            return False, [], error_msg
        
        logger.info(f"[ProviderManager] ✅ Successfully fetched {len(model_list)} {provider_name} models")
        
        # Log context_length for LLM models
        for model in model_list:
            if model.get('type') == 'llm' and 'context_length' in model:
                logger.info(f"[ProviderManager] 📊 {provider_name.upper()} Model {model['name']}: context_length={model['context_length']}")
            elif 'context_length' in model:
                logger.info(f"[ProviderManager] 📊 {provider_name.upper()} Model {model['name']}: context_length={model['context_length']}")
        
        # Note: Model information is already saved to user data directory by fetch_*_models()
        # No need to update code directory's llm_providers.json
        
        return True, model_list, None
    
    def update_provider_config(self, provider_name: str, model_list: List[Dict[str, Any]]):
        """
        Update llm_providers.json configuration file with latest model information.
        
        This ensures that the configuration file always contains the latest model info including
        context_length, which is critical for message compaction.
        
        Args:
            provider_name: Provider name ('ryoais', 'ollama', etc.)
            model_list: List of model dicts from API (with context_length, etc.)
        """
        # Load current configuration
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Find the provider in config (case-insensitive search)
        provider_key = None
        for key in config.get('providers', {}).keys():
            provider_config = config['providers'][key]
            if (key.lower() == provider_name.lower() or 
                provider_config.get('provider', '').lower() == provider_name.lower()):
                provider_key = key
                break
        
        if not provider_key:
            logger.warning(f"[ProviderManager] Provider '{provider_name}' not found in llm_providers.json")
            return
        
        # Convert API model list to provider config format
        supported_models = []
        for model in model_list:
            model_config = {
                'name': model.get('name', model.get('id', '')),
                'display_name': model.get('name', model.get('id', '')),
                'model_id': model.get('id', model.get('name', '')),
                'default_temperature': 0.7,
                'supports_streaming': True,
                'supports_function_calling': True,
                'supports_vision': False,
                'cost_per_1k_tokens': 0.0
            }
            
            # Add context_length as max_tokens for LLM models
            if model.get('type') == 'llm' and 'context_length' in model:
                model_config['max_tokens'] = model['context_length']
                logger.debug(f"[ProviderManager] Added max_tokens={model['context_length']} for {model['name']}")
            
            # Add embedding dimensions
            if model.get('type') == 'embedding' and 'dimensions' in model:
                model_config['dimensions'] = model['dimensions']
            
            # Add description based on type
            model_type = model.get('type', 'llm')
            model_config['description'] = f"{provider_name.upper()} {model_type} model: {model['name']}"
            
            supported_models.append(model_config)
        
        # Update provider's supported_models
        config['providers'][provider_key]['supported_models'] = supported_models
        
        # Save updated configuration
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"[ProviderManager] 📝 Updated {provider_key} in llm_providers.json with {len(supported_models)} models")
    
    def auto_refresh_all_providers(self, username: str = None, main_window=None):
        """
        Auto-refresh all configured providers on startup.
        
        This method checks which providers are actively configured and refreshes their models.
        Only runs if providers have valid configuration (non-empty host, etc.).
        
        Args:
            username: Optional username for user-specific operations
            main_window: MainWindow instance to access general_settings
        """
        from gui.config.llm_config import llm_config  # Use global instance
        import os
        
        try:
            logger.info("[ProviderManager] 🔄 Starting auto-refresh for all configured providers...")
            
            # ========== Check and refresh RyoAIS ==========
            # Find RyoAIS provider by matching provider enum value
            ryoais_provider = None
            for p_name, p_conf in llm_config.get_all_providers().items():
                if p_conf.provider.value == 'ryoais':
                    ryoais_provider = p_conf
                    break
            
            if ryoais_provider:
                # Get actual base_url from settings.json (not the default from llm_providers.json)
                ryoais_host = ''
                if main_window and hasattr(main_window, 'config_manager'):
                    ryoais_host = main_window.config_manager.general_settings.ryoais_llm_base_url
                
                if ryoais_host:
                    logger.debug(f"[ProviderManager] Using RyoAIS base_url from settings: {ryoais_host}")
                    
                    # Get API key from environment variables
                    ryoais_api_key = None
                    if ryoais_provider.api_key_env_vars:
                        for env_var in ryoais_provider.api_key_env_vars:
                            ryoais_api_key = os.getenv(env_var)
                            if ryoais_api_key:
                                break
                    
                    self.refresh_provider_models('ryoais', ryoais_host, ryoais_api_key, username)
                else:
                    logger.debug("[ProviderManager] RyoAIS base_url not configured in settings, skipping refresh")
            
            # ========== Check and refresh Ollama ==========
            # Find Ollama provider by matching provider enum value
            ollama_provider = None
            for p_name, p_conf in llm_config.get_all_providers().items():
                if p_conf.provider.value == 'ollama':
                    ollama_provider = p_conf
                    break
            
            if ollama_provider:
                # Get actual base_url from settings.json (not the default from llm_providers.json)
                ollama_host = ''
                if main_window and hasattr(main_window, 'config_manager'):
                    ollama_host = main_window.config_manager.general_settings.ollama_llm_base_url
                
                if ollama_host:
                    logger.debug(f"[ProviderManager] Using Ollama base_url from settings: {ollama_host}")
                    self.refresh_provider_models('ollama', ollama_host, None, username)
                else:
                    logger.debug("[ProviderManager] Ollama base_url not configured in settings, skipping refresh")
            
            logger.info("[ProviderManager] ✅ Auto-refresh completed for all providers")
            
            # IMPORTANT: Reload dynamic models from user data directory
            # This ensures that the updated ryoais_models.json and ollama_models.json are loaded into memory
            try:
                llm_config.reload_dynamic_models()
                logger.info("[ProviderManager] 🔄 Reloaded dynamic models from user data directory")
            except Exception as reload_error:
                logger.warning(f"[ProviderManager] ⚠️ Failed to reload dynamic models: {reload_error}")
            
        except Exception as e:
            logger.warning(f"[ProviderManager] ⚠️ Error during auto-refresh: {e}")
            import traceback
            logger.debug(f"[ProviderManager] Auto-refresh error traceback:\n{traceback.format_exc()}")


# Singleton instance
_provider_manager = None

def get_provider_manager() -> ProviderManager:
    """Get the singleton ProviderManager instance."""
    global _provider_manager
    if _provider_manager is None:
        _provider_manager = ProviderManager()
    return _provider_manager
