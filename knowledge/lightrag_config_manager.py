"""
LightRAG Configuration Manager
Handles reading, writing, and managing LightRAG .env configuration files
"""
import os
import time
from typing import Dict, Optional, List

from knowledge.lightrag_config_utils import ensure_user_env_file

from utils.logger_helper import logger_helper as logger

# Per-query reload of system API keys (Windows credential store + provider
# manager scans) was costing ~7 s on second and later queries minutes apart.
# A 60 s TTL only helped back-to-back queries; real Feige chat traffic spaces
# customer messages 1–10 min apart, so almost every query paid the cold cost.
# Extended to 30 min — API keys rarely rotate, and write_config() invalidates
# the cache explicitly when the user edits config through the UI.
_SYSTEM_KEYS_TTL_SEC = 1800.0
_EFFECTIVE_CONFIG_TTL_SEC = 1800.0


class LightRAGConfigManager:
    """
    Manages LightRAG configuration stored in .env files.
    Provides methods for reading, writing, and updating configuration.
    """

    def __init__(self):
        """Initialize the configuration manager."""
        self._config_cache: Optional[Dict[str, str]] = None
        self._cache_mtime: Optional[float] = None
        self._system_keys_cache: Optional[Dict[str, str]] = None
        self._system_keys_cache_time: Optional[float] = None
        self._effective_config_cache: Optional[Dict[str, str]] = None
        self._effective_config_cache_time: Optional[float] = None
        self._effective_config_cache_mtime: Optional[float] = None

    def _detect_embedding_on_demand(self, host: str, model_id: str, api_key: str = None) -> Optional[int]:
        """
        Detect embedding dimension on-demand by making a test API call.
        
        This is called when LightRAG needs the dimension but it's not available
        from the provider's model metadata.
        
        Args:
            host: Embedding API host (e.g., 'http://39.108.220.98:9003/v1')
            model_id: Model ID to test
            api_key: Optional API key
            
        Returns:
            Embedding dimension (int), or None if detection fails
        """
        import requests
        
        # Normalize host URL
        if host.endswith('/v1'):
            embeddings_url = f"{host}/embeddings"
        else:
            embeddings_url = f"{host}/v1/embeddings"
        
        try:
            headers = {'Content-Type': 'application/json'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            
            payload = {
                'model': model_id,
                'input': 'test'
            }
            
            logger.info(f"[LightRAG Config] Detecting embedding dimension for '{model_id}'...")
            response = requests.post(embeddings_url, json=payload, headers=headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and len(data['data']) > 0:
                    embedding = data['data'][0].get('embedding', [])
                    dimension = len(embedding)
                    logger.info(f"[LightRAG Config] Detected dimension for '{model_id}': {dimension}")
                    return dimension
            else:
                logger.warning(f"[LightRAG Config] Failed to detect dimension for '{model_id}': HTTP {response.status_code}")
        except requests.exceptions.Timeout:
            logger.warning(f"[LightRAG Config] Timeout detecting dimension for '{model_id}'")
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"[LightRAG Config] Connection error detecting dimension for '{model_id}': {e}")
        except Exception as e:
            logger.warning(f"[LightRAG Config] Error detecting dimension for '{model_id}': {e}")
        
        return None

    def get_config_file_path(self) -> Optional[str]:
        """
        Get the path to the user's configuration file.
        
        Returns:
            Path to lightrag.env file, or None if unable to determine
        """
        env_path = ensure_user_env_file()
        return str(env_path) if env_path else None
    
    def read_config(self, use_cache: bool = True) -> Dict[str, str]:
        """
        Read configuration from .env file.
        
        Args:
            use_cache: If True (default), return cached config if file hasn't changed
            
        Returns:
            Dictionary of configuration key-value pairs
        """
        config_file = self.get_config_file_path()
        if not config_file:
            logger.warning("[LightRAGConfig] Unable to determine config file path")
            return {}
        
        # Check if cache is valid (file hasn't been modified)
        if use_cache and self._config_cache is not None:
            try:
                current_mtime = os.path.getmtime(config_file)
                if self._cache_mtime is not None and current_mtime == self._cache_mtime:
                    # Cache is still valid, return it without re-reading file
                    logger.debug(f"[LightRAGConfig] Using cached config ({len(self._config_cache)} entries)")
                    return self._config_cache.copy()
            except OSError:
                pass  # File might not exist, will be handled below
        
        # Read config from file
        config = self._read_env_file(config_file)
        
        # Update cache
        self._config_cache = config.copy()
        try:
            self._cache_mtime = os.path.getmtime(config_file)
        except OSError:
            self._cache_mtime = None
        
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
            self._invalidate_derived_caches()
        return success

    def _invalidate_derived_caches(self) -> None:
        """Drop cached system-key / effective-config results after a write."""
        self._system_keys_cache = None
        self._system_keys_cache_time = None
        self._effective_config_cache = None
        self._effective_config_cache_time = None
        self._effective_config_cache_mtime = None

    def invalidate_caches(self) -> None:
        """Make provider/key changes visible to the next LightRAG env build."""
        self._invalidate_derived_caches()
    
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

    def get_system_api_keys(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Get active LLM/Embedding API keys from system configuration.

        Result is memoized for _SYSTEM_KEYS_TTL_SEC to avoid repeatedly hitting
        the Windows credential store (which can take ~4 s per provider when its
        in-memory cache has been evicted under memory pressure). Pass
        ``force_refresh=True`` to bypass the cache.
        """
        now = time.time()
        if (
            not force_refresh
            and self._system_keys_cache is not None
            and self._system_keys_cache_time is not None
            and (now - self._system_keys_cache_time) < _SYSTEM_KEYS_TTL_SEC
        ):
            age_s = now - self._system_keys_cache_time
            logger.info(
                f"[LightRAG Config][Cache] system_api_keys HIT (age={age_s:.1f}s, "
                f"ttl={_SYSTEM_KEYS_TTL_SEC:.0f}s)"
            )
            return self._system_keys_cache.copy()

        logger.info("[LightRAG Config][Cache] system_api_keys MISS — recomputing")
        keys = self._compute_system_api_keys()
        self._system_keys_cache = keys.copy()
        self._system_keys_cache_time = now
        return keys

    def _compute_system_api_keys(self) -> Dict[str, str]:
        """Actual provider lookup. Kept separate so the public method can cache."""
        keys: Dict[str, str] = {}
        try:
            # Import here to avoid circular dependency
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if not main_window:
                return keys

            general_settings = main_window.config_manager.general_settings

            # 1. LLM API Key
            # Use LLM_BINDING from .env file instead of system default_llm
            try:
                llm_mgr = main_window.config_manager.llm_manager
                
                # Read current .env file to get LLM_BINDING
                current_config = self.read_config()
                system_llm = str(getattr(general_settings, 'default_llm', '') or '').strip().lower()
                llm_binding = 'ecanai' if system_llm == 'ecanai' else current_config.get('LLM_BINDING')
                if system_llm == 'ecanai':
                    keys['LLM_BINDING'] = 'ecanai'
                    system_model = str(getattr(general_settings, 'default_llm_model', '') or '').strip()
                    if system_model:
                        keys['LLM_MODEL'] = system_model
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
                                # eCanAI exposes an OpenAI-compatible API. Some
                                # LightRAG/OpenAI client paths still consult the
                                # conventional alias directly.
                                if llm_binding == 'ecanai':
                                    keys['OPENAI_API_KEY'] = key_val
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
                system_embedding = str(getattr(general_settings, 'default_embedding', '') or '').strip().lower()
                embedding_binding = 'ecanai' if system_embedding == 'ecanai' else current_config.get('EMBEDDING_BINDING')
                if system_embedding == 'ecanai':
                    keys['EMBEDDING_BINDING'] = 'ecanai'
                    system_model = str(getattr(general_settings, 'default_embedding_model', '') or '').strip()
                    if system_model:
                        keys['EMBEDDING_MODEL'] = system_model
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
                        
                        # Extract model parameters (dimensions, max_tokens) from current model.
                        # PRIORITY: a model already resolved above (the ecanai
                        # overlay carries the user's Settings choice) must WIN
                        # over the stale .env value — otherwise an old
                        # text-embedding-3-small in lightrag.env silently
                        # overwrites the selected text-embedding-v3 forever
                        # (2026-08-30 CN ingest 404 model_not_found incident).
                        embedding_model = (keys.get('EMBEDDING_MODEL')
                                           or current_config.get('EMBEDDING_MODEL') or '').strip()
                        if not embedding_model:
                            # An empty value in an older lightrag.env must not
                            # erase the model selected in the global provider
                            # settings.  Provider managers expose that choice
                            # as preferred_model (including provider-specific
                            # choices such as ryoais_embedding_model).
                            embedding_model = (
                                embed_provider.get('preferred_model')
                                or getattr(main_window.config_manager.general_settings, 'default_embedding_model', '')
                                or embed_provider.get('default_model')
                                or ''
                            ).strip()
                            if embedding_model:
                                logger.warning(
                                    f"[LightRAG Config] EMBEDDING_MODEL is empty; "
                                    f"using selected provider model: {embedding_model}"
                                )
                        if embedding_model:
                            keys['EMBEDDING_MODEL'] = embedding_model
                        if embedding_model and embed_provider.get('supported_models'):
                            for model in embed_provider.get('supported_models', []):
                                if model.get('model_id') == embedding_model or model.get('name') == embedding_model:
                                    # Extract dimensions
                                    if model.get('dimensions'):
                                        keys['EMBEDDING_DIM'] = str(model.get('dimensions'))
                                        logger.info(f"[LightRAG Config] Using model dimensions: {model.get('dimensions')}")
                                    else:
                                        # Dimensions not available - detect it on-demand
                                        logger.warning(f"[LightRAG Config] Model '{embedding_model}' has no dimensions, detecting on-demand...")
                                        detected_dim = self._detect_embedding_on_demand(
                                            host=base_url,
                                            model_id=embedding_model,
                                            api_key=keys.get('EMBEDDING_BINDING_API_KEY')
                                        )
                                        if detected_dim:
                                            keys['EMBEDDING_DIM'] = str(detected_dim)
                                            logger.info(f"[LightRAG Config] Detected dimensions: {detected_dim}")
                                        else:
                                            logger.error(f"[LightRAG Config] Failed to detect dimensions for '{embedding_model}'")
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

                        # Dimension safety net (2026-08-30 DashScope 400
                        # incident): on-demand detection above only runs when
                        # the model is found in supported_models — providers
                        # with dynamic models (eCanAI) never enter that loop,
                        # so a stale EMBEDDING_DIM in lightrag.env (1536 from
                        # text-embedding-3-small) survived a model change and
                        # DashScope rejected it (valid: 64..1024). Whenever the
                        # resolved model differs from the .env model and no dim
                        # was resolved, detect it live so dim always matches
                        # the model actually used.
                        _env_model = (current_config.get('EMBEDDING_MODEL') or '').strip()
                        if (embedding_model and 'EMBEDDING_DIM' not in keys
                                and _env_model != embedding_model):
                            detected_dim = self._detect_embedding_on_demand(
                                host=keys.get('EMBEDDING_BINDING_HOST') or base_url,
                                model_id=embedding_model,
                                api_key=keys.get('EMBEDDING_BINDING_API_KEY')
                            )
                            if detected_dim:
                                keys['EMBEDDING_DIM'] = str(detected_dim)
                                logger.info(
                                    f"[LightRAG Config] Model changed "
                                    f"({_env_model!r} -> {embedding_model!r}); "
                                    f"detected dimensions: {detected_dim}"
                                )
                            else:
                                logger.warning(
                                    f"[LightRAG Config] Model changed but dimension "
                                    f"detection failed for '{embedding_model}' — the "
                                    f"stale EMBEDDING_DIM may be wrong"
                                )
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
                system_rerank = str(getattr(general_settings, 'default_rerank', '') or '').strip().lower()
                rerank_binding = 'ecanai' if system_rerank == 'ecanai' else current_config.get('RERANK_BINDING')
                if system_rerank == 'ecanai':
                    keys['RERANK_BINDING'] = 'ecanai'
                    system_model = str(getattr(general_settings, 'default_rerank_model', '') or '').strip()
                    if system_model:
                        keys['RERANK_MODEL'] = system_model
                logger.info(f"[LightRAG Config] RERANK_BINDING from .env = {rerank_binding}")
                
                if rerank_binding:
                    # Try to get provider by the binding value
                    rerank_provider = rerank_mgr.get_provider(rerank_binding)
                    logger.info(f"[LightRAG Config] rerank_provider = {rerank_provider.get('name') if rerank_provider else None}")
                    
                    if rerank_provider:
                        base_url = rerank_provider.get('base_url')
                        if base_url:
                            keys['RERANK_BINDING_HOST'] = base_url
                        # Retrieve API keys if needed
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
                
            # 4. Missing-key → cloud LLM proxy fallback (2026-08-27).
            # Same semantics as the chat-path fallback in build_node: when a
            # binding needs a key, none was resolved (provider store or .env),
            # and a proxy endpoint is configured, route that binding through
            # the OpenAI-compatible proxy (endpoint + /v1) with the eCan auth
            # token as the bearer key. Key-less bindings (ollama) are left
            # alone. This overlays get_effective_config, so it overrides the
            # .env binding/host for the server process.
            try:
                gs = main_window.config_manager.general_settings
                proxy_endpoint = (gs.lambda_proxy_endpoint or '').strip()
                if proxy_endpoint:
                    proxy_base = proxy_endpoint.rstrip('/') + '/v1'
                    auth_token = ''
                    if hasattr(main_window, 'get_auth_token'):
                        auth_token = main_window.get_auth_token() or ''
                    env_config = self.read_config()
                    for kind in ('LLM', 'EMBEDDING'):
                        binding = str(env_config.get(f'{kind}_BINDING') or '').strip().lower()
                        if not binding or binding == 'ollama':
                            continue
                        has_key = bool(keys.get(f'{kind}_BINDING_API_KEY')
                                       or env_config.get(f'{kind}_BINDING_API_KEY'))
                        if has_key:
                            continue
                        keys[f'{kind}_BINDING'] = 'openai'
                        keys[f'{kind}_BINDING_HOST'] = proxy_base
                        keys[f'{kind}_BINDING_API_KEY'] = auth_token or 'proxy'
                        logger.info(
                            f"[LightRAG Config] No local {kind} API key for binding "
                            f"'{binding}' — falling back to LLM proxy at {proxy_base}"
                        )
            except Exception as proxy_err:
                logger.warning(f"[LightRAG Config] proxy fallback check failed: {proxy_err}")

        except Exception as e:
            logger.warning(f"Error in get_system_api_keys: {e}")

        return keys

    def get_effective_config(self, force_refresh: bool = False) -> Dict[str, str]:
        """
        Get the effective configuration for LightRAG.
        This merges the .env file configuration with the system API keys.
        This is the source of truth for both the Server process and the UI display.

        Result is memoized for _EFFECTIVE_CONFIG_TTL_SEC. The cache is also
        invalidated automatically when lightrag.env mtime changes.

        IMPORTANT: This method also performs RyoAIS model synchronization.
        If any provider (LLM/Embedding/Rerank) is configured to use RyoAIS,
        it will fetch the current running model from RyoAIS API and update
        the configuration if changes are detected.
        """
        now = time.time()
        config_file = self.get_config_file_path()
        current_mtime: Optional[float]
        try:
            current_mtime = os.path.getmtime(config_file) if config_file else None
        except OSError:
            current_mtime = None

        if (
            not force_refresh
            and self._effective_config_cache is not None
            and self._effective_config_cache_time is not None
            and (now - self._effective_config_cache_time) < _EFFECTIVE_CONFIG_TTL_SEC
            and self._effective_config_cache_mtime == current_mtime
        ):
            age_s = now - self._effective_config_cache_time
            logger.info(
                f"[LightRAG Config][Cache] effective_config HIT (age={age_s:.1f}s, "
                f"ttl={_EFFECTIVE_CONFIG_TTL_SEC:.0f}s)"
            )
            return self._effective_config_cache.copy()

        # 1. Read from file
        config = self.read_config()

        # 2. Overlay system API keys
        # This ensures we always use the latest keys from the system settings
        system_keys = self.get_system_api_keys(force_refresh=force_refresh)
        config.update(system_keys)

        # NOTE: RyoAIS/Ollama model synchronization is now handled globally by MainGUI
        # at startup (_auto_refresh_ryoais_models), so we don't need to do it here.
        # This avoids duplicate API calls and ensures models are refreshed once per startup.

        self._effective_config_cache = config.copy()
        self._effective_config_cache_time = now
        self._effective_config_cache_mtime = current_mtime
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
