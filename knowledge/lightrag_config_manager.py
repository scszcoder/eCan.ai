"""
LightRAG Configuration Manager
Handles reading, writing, and managing LightRAG .env configuration files
"""
import os
from typing import Dict, Optional, List

from knowledge.lightrag_config_utils import ensure_user_env_file

from utils.logger_helper import logger_helper as logger


class LightRAGConfigManager:
    """
    Manages LightRAG configuration stored in .env files.
    Provides methods for reading, writing, and updating configuration.
    """
    
    def __init__(self):
        """Initialize the configuration manager."""
        self._config_cache: Optional[Dict[str, str]] = None
    
    def get_config_file_path(self) -> Optional[str]:
        """
        Get the path to the user's configuration file.
        
        Returns:
            Path to lightrag.env file, or None if unable to determine
        """
        env_path = ensure_user_env_file()
        return str(env_path) if env_path else None
    
    def read_config(self, use_cache: bool = False) -> Dict[str, str]:
        """
        Read configuration from .env file.
        
        Args:
            use_cache: If True, return cached config if available
            
        Returns:
            Dictionary of configuration key-value pairs
        """
        if use_cache and self._config_cache is not None:
            return self._config_cache.copy()
        
        config_file = self.get_config_file_path()
        if not config_file:
            logger.warning("[LightRAGConfig] Unable to determine config file path")
            return {}
        
        config = self._read_env_file(config_file)
        self._config_cache = config.copy()
        return config
    
    def write_config(self, config: Dict[str, str], merge: bool = True) -> bool:
        """
        Write configuration to .env file.
        
        Args:
            config: Dictionary of configuration key-value pairs to write
            merge: If True, merge with existing config; if False, replace entirely
            
        Returns:
            True if successful, False otherwise
        """
        config_file = self.get_config_file_path()
        if not config_file:
            logger.error("[LightRAGConfig] Unable to determine config file path")
            return False
        
        if merge:
            # Read existing config and merge
            existing_config = self._read_env_file(config_file)
            existing_config.update(config)
            config_to_write = existing_config
        else:
            config_to_write = config
        
        success = self._write_env_file(config_file, config_to_write)
        if success:
            self._config_cache = config_to_write.copy()
        return success
    
    def update_config(self, updates: Dict[str, str]) -> bool:
        """
        Update specific configuration values.
        
        Args:
            updates: Dictionary of key-value pairs to update
            
        Returns:
            True if successful, False otherwise
        """
        return self.write_config(updates, merge=True)
    
    def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get a specific configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        config = self.read_config(use_cache=True)
        return config.get(key, default)
    
    def set_value(self, key: str, value: str) -> bool:
        """
        Set a specific configuration value.
        
        Args:
            key: Configuration key
            value: Configuration value
            
        Returns:
            True if successful, False otherwise
        """
        return self.update_config({key: value})
    
    def delete_value(self, key: str) -> bool:
        """
        Delete a specific configuration value.
        
        Args:
            key: Configuration key to delete
            
        Returns:
            True if successful, False otherwise
        """
        config_file = self.get_config_file_path()
        if not config_file:
            logger.error("[LightRAGConfig] Unable to determine config file path")
            return False
        
        config = self._read_env_file(config_file)
        if key in config:
            del config[key]
            success = self._write_env_file(config_file, config)
            if success:
                self._config_cache = config.copy()
            return success
        return True  # Key doesn't exist, consider it successful
    
    def clear_cache(self):
        """Clear the configuration cache."""
        self._config_cache = None
    
    def _read_env_file(self, file_path: str) -> Dict[str, str]:
        """
        Read .env file into a dictionary.
        
        Args:
            file_path: Path to .env file
            
        Returns:
            Dictionary of configuration key-value pairs
        """
        config = {}
        if not os.path.exists(file_path):
            logger.warning(f"[LightRAGConfig] Config file not found: {file_path}")
            return config
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse key=value
                    if '=' not in line:
                        logger.warning(f"[LightRAGConfig] Invalid line {line_num} in {file_path}: {line}")
                        continue
                    
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    
                    config[key] = value
            
            logger.debug(f"[LightRAGConfig] Read {len(config)} config entries from {file_path}")
        except Exception as e:
            logger.error(f"[LightRAGConfig] Error reading config file {file_path}: {e}")
        
        return config
    
    def _write_env_file(self, file_path: str, config: Dict[str, str]) -> bool:
        """
        Write configuration dictionary to .env file.
        
        Args:
            file_path: Path to .env file
            config: Dictionary of configuration key-value pairs
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Prepare lines to write
            lines = []
            for key, value in sorted(config.items()):
                # Convert value to string
                str_val = str(value)
                
                # Add quotes if value contains spaces and isn't already quoted
                if ' ' in str_val and not (str_val.startswith('"') or str_val.startswith("'")):
                    str_val = f'"{str_val}"'
                
                lines.append(f"{key}={str_val}\n")
            
            # Write to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            
            logger.info(f"[LightRAGConfig] Wrote {len(config)} config entries to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[LightRAGConfig] Error writing config file {file_path}: {e}")
            return False
    
    def validate_config(self, config: Optional[Dict[str, str]] = None) -> tuple[bool, List[str]]:
        """
        Validate configuration for required fields and correct formats.
        
        Args:
            config: Configuration to validate, or None to validate current config
            
        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        if config is None:
            config = self.read_config()
        
        errors = []
        
        # Add validation rules here as needed
        # Example: Check for required fields
        # required_fields = ['HOST', 'PORT']
        # for field in required_fields:
        #     if field not in config:
        #         errors.append(f"Missing required field: {field}")
        
        return len(errors) == 0, errors

    def get_system_api_keys(self) -> Dict[str, str]:
        """
        Get active LLM/Embedding API keys from system configuration.
        This allows LightRAG to use the global system API keys.
        """
        keys = {}
        try:
            # Import here to avoid circular dependency
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if not main_window:
                return keys

            # 1. LLM API Key
            # Use LLM_BINDING from .env file instead of system default_llm
            try:
                llm_mgr = main_window.config_manager.llm_manager
                
                # Read current .env file to get LLM_BINDING
                current_config = self.read_config()
                llm_binding = current_config.get('LLM_BINDING')
                logger.info(f"[LightRAG Config] LLM_BINDING from .env = {llm_binding}")
                
                if llm_binding:
                    # Try to get provider by the binding value
                    llm_provider = llm_mgr.get_provider(llm_binding)
                    logger.info(f"[LightRAG Config] llm_provider = {llm_provider.get('name') if llm_provider else None}")
                    
                    if llm_provider:
                        # Use provider's base_url if available
                        base_url = llm_provider.get('base_url')
                        if base_url:
                            keys['LLM_BINDING_HOST'] = base_url
                            logger.info(f"[LightRAG Config] Using LLM base URL: {base_url}")
                        
                        # Extract model parameters (max_tokens) from current model
                        llm_model = current_config.get('LLM_MODEL')
                        if llm_model and llm_provider.get('supported_models'):
                            for model in llm_provider.get('supported_models', []):
                                if model.get('model_id') == llm_model or model.get('name') == llm_model:
                                    # Extract max_tokens
                                    if model.get('max_tokens'):
                                        keys['LLM_MAX_TOKENS'] = str(model.get('max_tokens'))
                                        logger.info(f"[LightRAG Config] Using LLM model max_tokens: {model.get('max_tokens')}")
                                    break
                        
                        api_key_env_vars = llm_provider.get('api_key_env_vars', [])
                        logger.info(f"[LightRAG Config] LLM api_key_env_vars = {api_key_env_vars}")
                        for env_var in api_key_env_vars:
                            key_val = llm_mgr.retrieve_api_key(env_var)
                            logger.info(f"[LightRAG Config] Checking LLM {env_var}: {'Found' if key_val else 'Not found'}")
                            if key_val:
                                keys['LLM_BINDING_API_KEY'] = key_val
                                keys['_SYSTEM_LLM_KEY_SOURCE'] = env_var
                                logger.info(f"[LightRAG Config] Using LLM API key from {env_var}")
                                # For backward compatibility/fallback, if it's OpenAI, set OPENAI_API_KEY too
                                if 'OPENAI_API_KEY' in env_var:
                                    keys['OPENAI_API_KEY'] = key_val
                                break
                    else:
                        logger.warning(f"[LightRAG Config] LLM Provider '{llm_binding}' not found in llm_manager")
            except Exception as e:
                logger.warning(f"Failed to get system LLM key: {e}")
                import traceback
                logger.warning(traceback.format_exc())

            # 2. Embedding API Key
            # Use EMBEDDING_BINDING from .env file instead of system default_embedding
            try:
                embed_mgr = main_window.config_manager.embedding_manager
                
                # Read current .env file to get EMBEDDING_BINDING
                current_config = self.read_config()
                embedding_binding = current_config.get('EMBEDDING_BINDING')
                logger.info(f"[LightRAG Config] EMBEDDING_BINDING from .env = {embedding_binding}")
                
                if embedding_binding:
                    # Try to get provider by the binding value
                    embed_provider = embed_mgr.get_provider(embedding_binding)
                    logger.info(f"[LightRAG Config] embed_provider = {embed_provider.get('name') if embed_provider else None}")
                    
                    if embed_provider:
                        # Use provider's base_url if available
                        base_url = embed_provider.get('base_url')
                        if base_url:
                            keys['EMBEDDING_BINDING_HOST'] = base_url
                            logger.info(f"[LightRAG Config] Using Embedding base URL: {base_url}")
                        
                        # Extract model parameters (dimensions, max_tokens) from current model
                        embedding_model = current_config.get('EMBEDDING_MODEL')
                        if embedding_model and embed_provider.get('supported_models'):
                            for model in embed_provider.get('supported_models', []):
                                if model.get('model_id') == embedding_model or model.get('name') == embedding_model:
                                    # Extract dimensions
                                    if model.get('dimensions'):
                                        keys['EMBEDDING_DIM'] = str(model.get('dimensions'))
                                        logger.info(f"[LightRAG Config] Using model dimensions: {model.get('dimensions')}")
                                    # Extract max_tokens
                                    if model.get('max_tokens'):
                                        keys['EMBEDDING_TOKEN_LIMIT'] = str(model.get('max_tokens'))
                                        logger.info(f"[LightRAG Config] Using model max_tokens: {model.get('max_tokens')}")
                                    break
                        
                        api_key_env_vars = embed_provider.get('api_key_env_vars', [])
                        logger.info(f"[LightRAG Config] api_key_env_vars = {api_key_env_vars}")
                        for env_var in api_key_env_vars:
                            key_val = embed_mgr.retrieve_api_key(env_var)
                            logger.info(f"[LightRAG Config] Checking {env_var}: {'Found' if key_val else 'Not found'}")
                            if key_val:
                                keys['EMBEDDING_BINDING_API_KEY'] = key_val
                                keys['_SYSTEM_EMBED_KEY_SOURCE'] = env_var
                                logger.info(f"[LightRAG Config] Using Embedding API key from {env_var}")
                                break
                    else:
                        logger.warning(f"[LightRAG Config] Provider '{embedding_binding}' not found in embedding_manager")
            except Exception as e:
                logger.warning(f"Failed to get system Embedding key: {e}")
                import traceback
                logger.warning(traceback.format_exc())

            # 3. Rerank API Key
            # Use RERANK_BINDING from .env file instead of system default_rerank
            try:
                rerank_mgr = main_window.config_manager.rerank_manager
                
                # Read current .env file to get RERANK_BINDING
                current_config = self.read_config()
                rerank_binding = current_config.get('RERANK_BINDING')
                logger.info(f"[LightRAG Config] RERANK_BINDING from .env = {rerank_binding}")
                
                if rerank_binding:
                    # Try to get provider by the binding value
                    rerank_provider = rerank_mgr.get_provider(rerank_binding)
                    logger.info(f"[LightRAG Config] rerank_provider = {rerank_provider.get('name') if rerank_provider else None}")
                    
                    if rerank_provider:
                        # Use provider's base_url if available
                        base_url = rerank_provider.get('base_url')
                        if base_url:
                            keys['RERANK_BINDING_HOST'] = base_url
                            logger.info(f"[LightRAG Config] Using Rerank base URL: {base_url}")
                        
                        api_key_env_vars = rerank_provider.get('api_key_env_vars', [])
                        logger.info(f"[LightRAG Config] api_key_env_vars = {api_key_env_vars}")
                        for env_var in api_key_env_vars:
                            key_val = rerank_mgr.retrieve_api_key(env_var)
                            logger.info(f"[LightRAG Config] Checking {env_var}: {'Found' if key_val else 'Not found'}")
                            if key_val:
                                keys['RERANK_BINDING_API_KEY'] = key_val
                                keys['_SYSTEM_RERANK_KEY_SOURCE'] = env_var
                                logger.info(f"[LightRAG Config] Using Rerank API key from {env_var}")
                                break
                    else:
                        logger.warning(f"[LightRAG Config] Provider '{rerank_binding}' not found in rerank_manager")
            except Exception as e:
                logger.warning(f"Failed to get system Rerank key: {e}")
                import traceback
                logger.warning(traceback.format_exc())
                
        except Exception as e:
            logger.warning(f"Error in get_system_api_keys: {e}")
        
        return keys

    def get_effective_config(self) -> Dict[str, str]:
        """
        Get the effective configuration for LightRAG.
        This merges the .env file configuration with the system API keys.
        This is the source of truth for both the Server process and the UI display.
        """
        # 1. Read from file
        config = self.read_config()
        
        # 2. Overlay system API keys
        # This ensures we always use the latest keys from the system settings
        system_keys = self.get_system_api_keys()
        config.update(system_keys)
        
        return config


# Global instance for convenience
_config_manager_instance: Optional[LightRAGConfigManager] = None


def get_config_manager() -> LightRAGConfigManager:
    """
    Get the global LightRAGConfigManager instance.
    
    Returns:
        LightRAGConfigManager instance
    """
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = LightRAGConfigManager()
    return _config_manager_instance
