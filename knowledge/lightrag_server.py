import subprocess
import os
import sys
import signal
import json
import atexit
import threading
import time
import locale
from pathlib import Path
from typing import Optional
from utils.logger_helper import logger_helper as logger
from knowledge.lightrag_config_manager import get_config_manager

class LightragServer:
    def __init__(self, extra_env=None):
        self.extra_env = extra_env or {}
        self.port = None  # actual bound port, set on successful start
        if self.extra_env:
            logged_keys = sorted(str(k) for k in self.extra_env.keys())
            logger.info(f"[LightragServer] extra_env keys: {logged_keys}")
        self.proc = None
        self._stdout_log_handle = None
        self._stderr_log_handle = None
        self._pid_file_path = None
        self._atexit_registered = False
        self._last_log_paths = (None, None)
        self._last_start_status = {
            'ok': None,
            'message': '',
            'error_type': '',
            'timestamp': 0.0,
        }
        self._register_atexit_handler()

        # Detect if running in PyInstaller packaged environment
        self.is_frozen = getattr(sys, 'frozen', False)

        # Restart control
        self.restart_count = 0
        self.max_restarts = 3
        self.last_restart_time = 0
        self.restart_cooldown = 30  # seconds

        # Get parent process ID
        import platform
        is_windows = platform.system().lower().startswith('win')
        
        enable_monitoring = self.extra_env.get("ENABLE_PARENT_MONITORING", "false").lower() == "true"
        
        if enable_monitoring:
            if is_windows:
                try:
                    import psutil
                    self.parent_pid = psutil.Process().ppid()
                except (ImportError, AttributeError):
                    self.parent_pid = os.getppid()
            else:
                self.parent_pid = os.getppid()
            
            self.disable_parent_monitoring = False
            logger.info(f"[LightragServer] Parent process monitoring ENABLED (PID: {self.parent_pid})")
        else:
            self.disable_parent_monitoring = True
            self.parent_pid = None
            logger.info("[LightragServer] Parent process monitoring DISABLED by default")

        self._monitor_running = False
        self._monitor_thread = None
        self._self_health_check_interval = 60  # seconds
        self._self_health_check_thread = None
        self._last_health_check_time = 0
        self._unhealthy_count = 0
        self._unhealthy_count_lock = threading.Lock()  # guards _unhealthy_count
        self._max_unhealthy = 3  # Restart after 3 consecutive unhealthy checks

        # ---- vLLM max_model_len cache (persistent across restarts) ----
        # Source: vLLM 400 error responses carry the model's real cap in
        # `upstream_body.max_model_len`.  We extract it once and cache it so
        # that subsequent launches (including the very next one) apply the
        # correct MAX_TOTAL_TOKENS / OPENAI_LLM_MAX_COMPLETION_TOKENS without
        # waiting for another error.  The cache key is the LLM_MODEL name so
        # multiple models get separate entries.
        self._vllm_cache: dict = {}       # in-memory: model -> max_model_len
        self._vllm_cache_lock = threading.Lock()  # guards _vllm_cache read/write
        self._vllm_cache_file = None       # resolved lazily in build_env (needs LOG_DIR)
        self._vllm_error_monitor_thread: Optional[threading.Thread] = None
        self._vllm_monitor_event: Optional[threading.Event] = None  # replaced _vllm_error_monitor_active

        self._setup_signal_handlers()
        
        # Proxy callback registration
        self._initialized_time = time.time()
        threading.Thread(target=self._register_proxy_change_callback, name="LightragProxyCallbackReg", daemon=True).start()

    def _register_proxy_change_callback(self):
        try:
            time.sleep(2.0) # Wait for system to stabilize
            from agent.ec_skills.system_proxy import get_proxy_manager
            
            proxy_manager = get_proxy_manager()
            if not proxy_manager:
                logger.debug("[LightragServer] ProxyManager not available")
                return
            
            def on_proxy_change(proxies):
                if self.is_running():
                    logger.info("[LightragServer] Proxy settings changed, scheduling restart...")
                    # Restart in a separate thread to avoid blocking the callback
                    def restart_task():
                        try:
                            self.stop()
                            time.sleep(1)
                            self.start(wait_ready=False)
                        except Exception as e:
                            logger.error(f"[LightragServer] Restart on proxy change failed: {e}")
                    
                    threading.Thread(target=restart_task, name="LightragProxyRestart", daemon=True).start()
            
            proxy_manager.register_callback(on_proxy_change)
            logger.info("[LightragServer] Proxy change callback registered")
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to register proxy callback: {e}")

    def _setup_signal_handlers(self):
        def signal_handler(signum, frame):
            logger.info(f"[LightragServer] Received signal {signum}, stopping server...")
            self.stop()
            if not self.is_frozen:
                sys.exit(0)

        try:
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGTERM, signal_handler)
                signal.signal(signal.SIGINT, signal_handler)
                if hasattr(signal, 'SIGHUP'):
                    signal.signal(signal.SIGHUP, signal_handler)
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to setup signal handlers: {e}")

    def _register_atexit_handler(self):
        if self._atexit_registered: return
        try:
            atexit.register(self._ensure_process_cleanup)
            self._atexit_registered = True
        except Exception: pass

    def _ensure_process_cleanup(self):
        try:
            if self.is_running(): self.stop()
        except Exception: pass

    def _set_start_status(self, ok, message='', error_type=''):
        self._last_start_status = {
            'ok': ok,
            'message': message or '',
            'error_type': error_type or '',
            'timestamp': time.time(),
        }

    def get_startup_status(self):
        return dict(self._last_start_status)

    def _load_proxy_config(self):
        """
        Load proxy configuration from rerank_providers.json.
        
        Returns:
            dict: Proxy configuration with keys: proxy_host, proxy_path, proxy_format, enabled
        """
        default_config = {
            'enabled': True,
            'proxy_host': 'http://localhost:4668',
            'proxy_path': '/api/rerank',
            'proxy_format': 'aliyun'
        }
        
        try:
            import json
            config_path = os.path.join(os.path.dirname(__file__), '..', 'gui', 'config', 'rerank_providers.json')
            
            if not os.path.exists(config_path):
                logger.warning(f"[LightragServer] Proxy config file not found: {config_path}")
                logger.info(f"[LightragServer] Using default proxy config")
                return default_config
            
            with open(config_path, 'r', encoding='utf-8') as f:
                providers_config = json.load(f)
                ollama_config = providers_config.get('providers', {}).get('Ollama (Local)', {})
                proxy_info = ollama_config.get('proxy_info', {})
                
                if not proxy_info:
                    logger.warning(f"[LightragServer] No proxy_info found in config")
                    logger.info(f"[LightragServer] Using default proxy config")
                    return default_config
                
                # Merge with default config
                config = default_config.copy()
                config.update({
                    'enabled': proxy_info.get('enabled', True),
                    'proxy_host': proxy_info.get('proxy_host', default_config['proxy_host']),
                    'proxy_path': proxy_info.get('proxy_path', default_config['proxy_path']),
                    'proxy_format': proxy_info.get('proxy_format', default_config['proxy_format'])
                })
                
                logger.info(f"[LightragServer] ✅ Loaded proxy config from rerank_providers.json:")
                logger.info(f"   - Enabled:      {config['enabled']}")
                logger.info(f"   - Proxy Host:   {config['proxy_host']}")
                logger.info(f"   - Proxy Path:   {config['proxy_path']}")
                logger.info(f"   - Proxy Format: {config['proxy_format']}")
                
                return config
                
        except Exception as e:
            logger.error(f"[LightragServer] ❌ Failed to load proxy config: {e}")
            logger.info(f"[LightragServer] Using default proxy config")
            return default_config

    def _intercept_ollama_rerank(self, env):
        """
        Intercept Ollama rerank requests and redirect to eCan proxy.
        
        This method:
        1. Detects if RERANK_BINDING is set to 'ollama'
        2. Loads proxy configuration from rerank_providers.json
        3. Saves the original Ollama host to OLLAMA_HOST
        4. Redirects RERANK_BINDING_HOST to the proxy
        5. Converts RERANK_BINDING to the configured format (default: aliyun)
        
        Args:
            env (dict): Environment variables dictionary
            
        Returns:
            bool: True if interception was applied, False otherwise
        """
        rerank_binding = env.get('RERANK_BINDING', '').lower()
        
        # Only intercept if binding is 'ollama'
        if rerank_binding != 'ollama':
            return False
        
        logger.info("=" * 70)
        logger.info("[LightragServer] 🔄 Ollama Rerank Interception")
        logger.info("=" * 70)
        
        # Get original Ollama host
        original_host = env.get('RERANK_BINDING_HOST', 'http://localhost:11434')
        original_model = env.get('RERANK_MODEL', 'N/A')
        
        logger.info(f"📋 Original Configuration:")
        logger.info(f"   - Binding:      {rerank_binding}")
        logger.info(f"   - Host:         {original_host}")
        logger.info(f"   - Model:        {original_model}")
        
        # Load proxy configuration
        proxy_config = self._load_proxy_config()
        
        if not proxy_config.get('enabled'):
            logger.warning(f"⚠️  Proxy is disabled in configuration")
            logger.warning(f"   Ollama rerank will not work (Ollama doesn't support Rerank API)")
            return False
        
        # Build proxy URL
        proxy_host = proxy_config['proxy_host']
        proxy_path = proxy_config['proxy_path']
        proxy_format = proxy_config['proxy_format']
        proxy_url = f"{proxy_host}{proxy_path}"
        
        logger.info(f"")
        logger.info(f"🔧 Proxy Configuration:")
        logger.info(f"   - Proxy URL:    {proxy_url}")
        logger.info(f"   - API Format:   {proxy_format}")
        
        # Apply interception
        env['OLLAMA_HOST'] = original_host  # Save original host for proxy to use
        env['RERANK_BINDING_HOST'] = proxy_url  # Redirect to proxy
        env['RERANK_BINDING'] = proxy_format  # Convert to proxy format
        
        logger.info(f"")
        logger.info(f"✅ Interception Applied:")
        logger.info(f"   - OLLAMA_HOST:           {original_host}  (saved for proxy)")
        logger.info(f"   - RERANK_BINDING_HOST:   {proxy_url}  (redirected)")
        logger.info(f"   - RERANK_BINDING:        {proxy_format}  (converted)")
        
        logger.info(f"")
        logger.info(f"📡 Request Flow:")
        logger.info(f"   LightRAG → {proxy_url} → eCan Proxy → {original_host} → Ollama")
        logger.info("=" * 70)
        
        return True

    def build_env(self):
        """Build environment variables for LightRAG server process."""
        # 1. Start with system environment
        env = os.environ.copy()
        
        # 2. Load effective config (File + System API Keys)
        config_manager = get_config_manager()
        effective_config = config_manager.get_effective_config()
        
        if effective_config:
            logger.info(f"[LightragServer] Loaded {len(effective_config)} variables from effective config")
            env.update(effective_config)
        else:
            logger.warning("[LightragServer] No effective configuration loaded")

        # Heal legacy values such as the literal string "None" before
        # LightRAG validates the parser rule table during create_app().
        from knowledge.lightrag_parser_config import normalize_parser_routing
        env['LIGHTRAG_PARSER'] = normalize_parser_routing(env.get('LIGHTRAG_PARSER'))

        # LOG_DIR is now known, so load the real deployment limit before any
        # token budgets are calculated.  Loading this at the end of build_env
        # made the first (and actually launched) environment trust an
        # over-reported /models value; only a later, discarded build saw the
        # cached limit learned from vLLM's 400 response.
        self._load_vllm_max_model_len_cache(env)

        # 3. Python runtime environment
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
        env['NO_COLOR'] = '1'
        env['ASCII_COLORS_DISABLE'] = '1'

        # 2.5 Derive LLM token limits from the selected model's deployment
        # Override MAX_TOTAL_TOKENS / OPENAI_LLM_MAX_COMPLETION_TOKENS with the
        # model's actual deployed context window. Source priority:
        #   1. GET {LLM_BINDING_HOST}/models  -> response.data[*].max_model_len
        #      (vLLM reports the deployment cap here; this is the only value
        #       that matches what the server will actually accept.)
        #   2. ryoais_models.json             -> models[].context_length
        #      (cached API snapshot from gui/ryoais_utils.fetch_ryoais_models;
        #       may overshoot the deployed cap.)
        #   3. Static fallback (8192)
        # extra_env (applied in step 4) still wins over this, so callers can
        # force a value when needed.
        self._apply_llm_token_limits(env)

        # 2.5.5 Scale TOP_K / CHUNK_TOP_K to the deployed model's context window.
        # A 8K model can't afford the default (TOP_K=40 / CHUNK_TOP_K=20) without
        # the prompt overflowing. This mirrors _apply_llm_token_limits above:
        # resolve max_model_len, then cap oversized user values.
        self._apply_top_k_for_window(env)

        # 2.6 Ensure retrieval token limits have sane minimums (chunk protection)
        self._apply_retrieval_token_limits(env)

        # 2.7 Limit storage backends to only what we use (mt101: reduce memory)
        # LightRAG ships optional storage backends (neo4j, pymongo, redis, milvus)
        # that are NOT used by eCan. They import heavyweight libs (~1-2GB each)
        # and are loaded at startup even if unused. We hardcode the backends
        # we actually use so LightRAG's conditional imports don't eagerly load them.
        #
        # What we use: JsonKVStorage + FaissVectorDBStorage + NetworkXStorage
        # What we DON'T use: Neo4JStorage, MongoKVStorage, RedisKVStorage, MilvusVectorDBStorage
        env.setdefault('LIGHTRAG_KV_STORAGE', 'JsonKVStorage')
        env.setdefault('LIGHTRAG_DOC_STATUS_STORAGE', 'JsonDocStatusStorage')
        env.setdefault('LIGHTRAG_VECTOR_STORAGE', 'FaissVectorDBStorage')
        env.setdefault('LIGHTRAG_GRAPH_STORAGE', 'NetworkXStorage')
        logger.info(
            f"[LightragServer] Storage backends: KV={env['LIGHTRAG_KV_STORAGE']}, "
            f"Vector={env['LIGHTRAG_VECTOR_STORAGE']}, Graph={env['LIGHTRAG_GRAPH_STORAGE']} "
            f"(unneeded backends neo4j/mongo/redis/milvus are NOT loaded)"
        )


        # 3.1 CPU optimization for embedding and LLM inference
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        # Use 75% of available CPU cores for optimal performance
        optimal_threads = max(4, int(cpu_count * 0.75))
        
        # OpenMP threads (for numpy, scipy, scikit-learn)
        env['OMP_NUM_THREADS'] = str(optimal_threads)
        # Intel MKL threads (for Intel Math Kernel Library)
        env['MKL_NUM_THREADS'] = str(optimal_threads)
        # OpenBLAS threads (for linear algebra operations)
        env['OPENBLAS_NUM_THREADS'] = str(optimal_threads)
        # PyTorch threads
        env['TORCH_NUM_THREADS'] = str(optimal_threads)
        # Disable dynamic thread adjustment for consistent performance
        env['MKL_DYNAMIC'] = 'FALSE'
        env['OMP_DYNAMIC'] = 'FALSE'
        
        logger.info(f"[LightragServer] 🚀 CPU Optimization: Using {optimal_threads}/{cpu_count} threads for parallel processing")

        # 4. Apply extra_env overrides
        if self.extra_env:
            logger.info(f"[LightragServer] Applying {len(self.extra_env)} extra environment variables")
            for k, v in self.extra_env.items():
                env[str(k)] = str(v)
        
        self._ensure_utf8_locale(env)

        if self.is_frozen and not env.get('HOST'):
            env['HOST'] = '127.0.0.1'

        # 6. Map provider bindings to LightRAG-supported values
        # LightRAG server whitelist (from lightrag/api/lightrag_server.py):
        #   LLM:       lollms, ollama, openai, azure_openai, aws_bedrock, gemini
        #   Embedding: lollms, ollama, openai, azure_openai, aws_bedrock, jina, gemini
        #   Rerank:    cohere, jina, aliyun (handled by launcher)
        # All other providers must be mapped to one of these.
        
        # LightRAG natively supported providers (hardcoded in lightrag/api/lightrag_server.py)
        # Note: ryoais is NOT in these sets because LightRAG doesn't recognize it.
        #       It uses OpenAI-compatible API, so it's mapped to 'openai' via PROVIDER_MAPPING.
        LIGHTRAG_LLM_SUPPORTED = {'lollms', 'ollama', 'openai', 'azure_openai', 'aws_bedrock', 'gemini'}
        LIGHTRAG_EMBED_SUPPORTED = LIGHTRAG_LLM_SUPPORTED | {'jina'}
        LIGHTRAG_RERANK_SUPPORTED = {'cohere', 'jina', 'aliyun'}
        
        # Static mapping: provider identifier -> LightRAG-compatible binding
        # Covers all providers from llm_providers.json + common aliases
        PROVIDER_MAPPING = {
            # OpenAI-compatible providers (use openai binding)
            'ryoais':        'openai',
            'ecanai':        'openai',
            'anthropic':     'openai',
            'deepseek':      'openai',
            'dashscope':     'openai',
            'bytedance':     'openai',
            'baidu_qianfan': 'openai',
            'zhipuai':       'openai',
            'google':        'openai',  # Google via OpenAI-compatible API
            # AWS Bedrock alias
            'bedrock':       'aws_bedrock',
        }
        
        def _map_binding(binding_value, supported_set, binding_name, default='openai'):
            """Map a provider binding to a LightRAG-supported value."""
            if not binding_value:
                return
            key = binding_value.lower()
            if key in supported_set:
                return  # Already supported, no mapping needed
            mapped = PROVIDER_MAPPING.get(key, default)
            logger.info(f"[LightragServer] Mapped {binding_name} '{binding_value}' -> '{mapped}'")
            env[binding_name] = mapped
        
        _map_binding(env.get('LLM_BINDING'), LIGHTRAG_LLM_SUPPORTED, 'LLM_BINDING')
        _map_binding(env.get('EMBEDDING_BINDING'), LIGHTRAG_EMBED_SUPPORTED, 'EMBEDDING_BINDING')
        
        # Rerank binding: map non-native providers to 'jina' (launcher may further process)
        # Ollama is routed through the local compatibility proxy. Other
        # non-native rerank providers use LightRAG's Jina-compatible client.
        rerank_binding = env.get('RERANK_BINDING')
        if rerank_binding and rerank_binding.lower() not in ('null', 'none', ''):
            if rerank_binding.lower() != 'ollama':
                _map_binding(rerank_binding, LIGHTRAG_RERANK_SUPPORTED, 'RERANK_BINDING', default='jina')
        
        # 7. Add SSL/TLS configuration to fix certificate errors
        # Disable SSL verification for development/testing (can be overridden by extra_env)
        if 'SSL_VERIFY' not in env:
            env['SSL_VERIFY'] = 'false'

        # 8. Clean up empty string values that cause argument parsing errors
        # LightRAG server cannot handle empty strings for numeric/float parameters
        keys_to_clean = []
        for key, value in env.items():
            if isinstance(value, str) and value.strip() == '':
                keys_to_clean.append(key)
        
        for key in keys_to_clean:
            del env[key]
            logger.debug(f"[LightragServer] Removed empty env var: {key}")

        # 9. Log API Key Status (Masked)
        # Only read LLM_BINDING_API_KEY as requested
        llm_api_key = env.get('LLM_BINDING_API_KEY')
        if llm_api_key and str(llm_api_key).strip():
            masked_key = self._mask_env_value('API_KEY', str(llm_api_key))
            logger.info(f"[LightragServer] ✅ LLM API key set: {masked_key}")
        else:
             logger.warning("[LightragServer] ⚠️ No LLM_BINDING_API_KEY found.")

        # 10. Lambda proxy metadata for per-user accounting headers
        # The launcher's patch_openai_client_for_lambda_proxy() reads these
        try:
            from app_context import AppContext
            main_window = AppContext.get_main_window()
            if main_window:
                # User ID for token accounting
                user_id = ''
                if hasattr(main_window, 'config_manager') and main_window.config_manager:
                    gs = main_window.config_manager.general_settings
                    user_id = getattr(gs, 'user_id', '') or ''
                if not user_id and hasattr(main_window, 'user_email'):
                    user_id = main_window.user_email or ''
                if user_id:
                    env['ECAN_USER_ID'] = user_id

                # LLM provider name (so Lambda knows which backend to call)
                llm_provider = env.get('LLM_BINDING', '')
                if llm_provider:
                    env['ECAN_LLM_PROVIDER'] = llm_provider
        except Exception as e:
            logger.debug(f"[LightragServer] Could not set proxy metadata env vars: {e}")

        self._sync_restart_settings(env)

        return env

    def _sync_restart_settings(self, env):
        try:
            self.max_restarts = int(env.get('MAX_RESTARTS', self.max_restarts))
            self.restart_cooldown = int(env.get('RESTART_COOLDOWN', self.restart_cooldown))
        except (ValueError, TypeError):
            pass

    # ---- LLM token limits ---------------------------------------------------
    #
    # These two env vars control how much of the model's context window
    # lightrag is allowed to use:
    #   MAX_TOTAL_TOKENS                 - total prompt + output cap
    #   OPENAI_LLM_MAX_COMPLETION_TOKENS - output cap only
    #
    # Both must be <= the model's deployed context window (vLLM's
    # `max_model_len`). If they exceed it the request is rejected with 400:
    #   "max_completion_tokens=9000 cannot be greater than
    #    max_model_len=max_total_tokens=4096"
    #
    # We resolve the value from the deployment itself rather than relying on
    # the static value in lightrag.env, because the model registered in the
    # provider config (e.g. Qwen3.6-27B-AWQ-INT4) can be redeployed with a
    # smaller window than its native capability.

    @staticmethod
    def _llm_models_endpoint(host: str) -> Optional[str]:
        """Return the OpenAI-compatible /models URL for the given binding host,
        or None if `host` doesn't look usable."""
        if not host:
            return None
        host = host.rstrip('/')
        # Host already includes /v1 (ryoais style) -> /v1/models
        if host.endswith('/v1'):
            return f'{host}/models'
        # Bare host -> /v1/models
        return f'{host}/v1/models'

    def _resolve_llm_max_model_len(self, env: dict) -> Optional[int]:
        """Best-effort lookup of the model's deployed context window.

        Returns an integer context length, or None when neither source is
        reachable. Never raises - all failures are logged at WARNING.

        Lookup order (first hit wins):
          1. Persistent vLLM error cache  – extracted from vLLM 400 responses
          2. Live /v1/models query         – authoritative but may not expose max_model_len
          3. ryoais_models.json snapshot   – cached API response; may overshoot deployed cap
          4. Known model registry          – hard-coded map for common aihub deployments
        """
        host = (env.get('LLM_BINDING_HOST') or '').strip()
        model = (env.get('LLM_MODEL') or '').strip()
        if not host or not model:
            return None

        # Case-insensitive model name for matching against registry / API responses
        model_lower = model.lower()

        # ---- 0. Persistent vLLM error cache (populated from vLLM 400 responses) ----
        with self._vllm_cache_lock:
            if model in self._vllm_cache:
                cached_len = self._vllm_cache[model]
                logger.info(
                    f"[LightragServer] LLM max_model_len from vLLM error cache: "
                    f"model={model} len={cached_len}"
                )
                return cached_len

        # Only attempt the live query for OpenAI-compatible bindings (which is
        # what ryoais / deepseek / dashscope / bytedance etc. all are after
        # _map_binding runs upstream of us). Other bindings (ollama, lollms,
        # gemini, bedrock) have their own context knobs and shouldn't be
        # queried here.
        binding = (env.get('LLM_BINDING') or '').lower()
        if binding and binding not in ('openai', 'ryoais', 'ecanai', 'anthropic', 'deepseek',
                                       'dashscope', 'bytedance', 'baidu_qianfan',
                                       'zhipuai', 'google'):
            return None

        api_key = (env.get('LLM_BINDING_API_KEY') or '').strip()

        # ---- 1. Live /v1/models query (authoritative) ----
        endpoint = self._llm_models_endpoint(host)
        if endpoint:
            try:
                import requests
                headers = {}
                if api_key and api_key != 'your_api_key':
                    headers['Authorization'] = f'Bearer {api_key}'
                resp = requests.get(endpoint, headers=headers, timeout=5, verify=False)
                if resp.status_code == 200:
                    data = resp.json().get('data', []) or []
                    for entry in data:
                        # Match by id, model_id, or name (case-insensitive)
                        entry_id = (entry.get('id') or '').lower()
                        entry_model_id = (entry.get('model_id') or '').lower()
                        if entry_id != model_lower and entry_model_id != model_lower:
                            continue
                        # vLLM returns the deployed cap as `max_model_len`.
                        # Some proxies use `context_length` / `max_tokens`.
                        for key in ('max_model_len', 'context_length', 'max_tokens', 'n_ctx'):
                            val = entry.get(key)
                            if val:
                                length = int(val)
                                if length > 0:
                                    logger.info(
                                        f"[LightragServer] LLM max_model_len from {endpoint}: "
                                        f"model={model} len={length} (key={key})"
                                    )
                                    return length
                    logger.debug(
                        f"[LightragServer] /models OK but model '{model}' not found in response"
                    )
                else:
                    logger.info(
                        f"[LightragServer] /models returned HTTP {resp.status_code} "
                        f"(endpoint={endpoint})"
                    )
            except Exception as e:
                logger.info(f"[LightragServer] /models query failed: {e}")

        # ---- 2. Fallback: ryoais_models.json (cached snapshot from earlier fetch) ----
        try:
            from gui.ryoais_utils import load_ryoais_models
            snapshot = load_ryoais_models(model_type='llm') or {}
            for entry in snapshot.get('models', []) or []:
                entry_name = (entry.get('id') or entry.get('name') or '').lower()
                entry_model_id = (entry.get('model_id') or '').lower()
                if entry_name != model_lower and entry_model_id != model_lower:
                    continue
                val = entry.get('context_length')
                if val and int(val) > 0:
                    length = int(val)
                    logger.warning(
                        f"[LightragServer] LLM context_length from ryoais_models.json "
                        f"(may exceed deployed cap): model={model} len={length}"
                    )
                    return length
        except Exception as e:
            logger.debug(f"[LightragServer] ryoais_models.json lookup failed: {e}")

        # ---- 3. Known model registry for common aihub deployments ----
        # aihub vLLM nodes often don't expose max_model_len in /v1/models.
        # Map the model ID (case-insensitive) directly to its context window.
        _KNOWN_AIHUB_MODELS: dict[str, int] = {
            # Qwen3 8K context window models
            'qwen3.8-27b-awq-int4': 8192,
            'qwen3.8-27b-awq': 8192,
            'qwen3.6-27b-awq-int4': 8192,
            'qwen3.6-27b-awq': 8192,
            'qwen3.8-2.4t-a95b': 8192,
            'qwen3.7-max': 8192,
            'qwen3.6-max': 8192,
            # Qwen3 32K context window models
            'qwen3.8-max': 32768,
            'qwen3.7-plus': 32768,
            'qwen3.6-flash': 32768,
            # OpenAI compatible models with known context
            'gpt-4': 8192,
            'gpt-4-turbo': 128000,
            'gpt-4o': 128000,
            'claude-3-opus': 200000,
            'claude-3-sonnet': 200000,
        }
        if model_lower in _KNOWN_AIHUB_MODELS:
            length = _KNOWN_AIHUB_MODELS[model_lower]
            logger.warning(
                f"[LightragServer] LLM max_model_len from known model registry "
                f"(check this value periodically): model={model} len={length}"
            )
            return length

        # ---- 4. Static fallback (last resort) ----
        # Default to 8K context, which is the most common deployment size.
        # The ratio-based budget in _compute_llm_budget then distributes it
        # between output and retrieval share.  A wrong 8K is recoverable;
        # returning None and falling through to the old env value is not.
        logger.warning(
            f"[LightragServer] LLM max_model_len unresolved for '{model}' "
            f"(all lookups failed); using static fallback 8192. "
            f"Consider adding '{model}' to the known model registry above."
        )
        return 8192

    def _compute_llm_budget(self, max_model_len: int) -> tuple:
        """Return (output_tokens, retrieval_share) for the given deployed context window.

        The retrieval context (entity + relation + chunks + system prompt) needs
        the lion's share of every small model. This function maps a model's
        max_model_len to a tier-appropriate output budget so 8K models stop
        colliding with their own prompt.

        Output budget: one third of the window, floored at 512 so a tiny model
        still gets a usable answer, and capped so we always keep ≥500 tokens
        for system prompt + at least one chunk.

        Retrieval share: the remaining window after output and 500 tokens of
        system-prompt overhead. Used by _apply_retrieval_token_limits to cap
        entity+relation combined budget. For an 8196-token deployment this
        yields 8196-2732-500=4964.

        Replaces the old formula `max_model_len - max(2000, 0.5*max_model_len)`
        which produced output=4096 on 8K models and collided with the
        ~4000-token system+entity+chunks prompt.
        """
        # Entity/relation extraction produces verbose structured output. The
        # former 25% cap (2049 on the deployed 8196-token model) repeatedly
        # ended with finish_reason=length and an incomplete record delimiter.
        # One third leaves most of the window for the prompt while giving the
        # extractor enough room to finish a normal 2K-token source chunk. The
        # floor keeps tiny models usable, while the cap always reserves at
        # least 500 tokens for system prompt and source content.
        output = max(512, max_model_len // 3)
        if output > max_model_len - 500:
            # Window too small to fit 500 overhead AND 512 output: prefer
            # the floor (drop the overhead floor) rather than returning
            # negative tokens, which would later break token math.
            output = max(512, max_model_len - 500)
        # Retrieval share: everything that isn't output or system overhead.
        retrieval_share = max(0, max_model_len - output - 500)
        return output, retrieval_share

    def _apply_llm_token_limits(self, env: dict) -> None:
        """Sync MAX_TOTAL_TOKENS / OPENAI_LLM_MAX_COMPLETION_TOKENS with the model's
        deployed context window.

        Resolution order:
          1. If the deployment exposes max_model_len (vLLM /v1/models) or a
             ryoais_models.json snapshot has context_length — use that value
             as MAX_TOTAL_TOKENS, and derive OPENAI_LLM_MAX_COMPLETION_TOKENS
             as one third of the window (see _compute_llm_budget).  This is
             universal across 8K/16K/32K/64K deployments and replaces the old
             formula `max_model_len - max(2000, 0.5*max_model_len)` which was
             too generous on small-context models (output=4096 on an 8K model
             collided with a ~4100-token prompt, producing 400 errors).
          2. Neither source is reachable — leave the env untouched. LightRAG's
             own DEFAULT_MAX_TOTAL_TOKENS (30000 in 1.4.x) then applies.

        Never raises."""
        try:
            max_model_len = self._resolve_llm_max_model_len(env)
            if not max_model_len:
                logger.info(
                    "[LightragServer] LLM max_model_len unknown; "
                    "leaving MAX_TOTAL_TOKENS to LightRAG default "
                    "(env value: %s)",
                    env.get('MAX_TOTAL_TOKENS', '<unset>')
                )
                return

            output_tokens, retrieval_share = self._compute_llm_budget(max_model_len)

            previous_total = env.get('MAX_TOTAL_TOKENS')
            previous_output = env.get('OPENAI_LLM_MAX_COMPLETION_TOKENS')
            env['MAX_TOTAL_TOKENS'] = str(max_model_len)
            env['OPENAI_LLM_MAX_COMPLETION_TOKENS'] = str(output_tokens)
            # Extraction needs a relatively large structured response, while
            # retrieval queries spend substantially more tokens on graph and
            # chunk context. Keep the role-specific query response small enough
            # that an 8K deployment cannot overflow after context assembly.
            query_output_tokens = max(512, min(4096, max_model_len // 8))
            env['QUERY_OPENAI_LLM_MAX_COMPLETION_TOKENS'] = str(query_output_tokens)
            # LightRAG's extraction prompt itself occupies most of an 8K
            # context window. Its upstream paragraph defaults (2000 tokens +
            # one gleaning pass) can therefore overflow even for a short DOCX.
            # Apply safe defaults/caps only to small-context deployments.
            if max_model_len <= 8196:
                env.setdefault('CHUNK_P_SIZE', '800')
                gleaning = self._coerce_int(env.get('MAX_GLEANING'))
                if gleaning is None or gleaning > 0:
                    env['MAX_GLEANING'] = '0'
            logger.info(
                f"[LightragServer] LLM token limits derived from deployment: "
                f"max_model_len={max_model_len} "
                f"MAX_TOTAL_TOKENS={previous_total}->{env['MAX_TOTAL_TOKENS']} "
                f"OPENAI_LLM_MAX_COMPLETION_TOKENS={previous_output}->{env['OPENAI_LLM_MAX_COMPLETION_TOKENS']} "
                f"QUERY_OPENAI_LLM_MAX_COMPLETION_TOKENS={env['QUERY_OPENAI_LLM_MAX_COMPLETION_TOKENS']} "
                f"(proportional budget; retrieval share ~ {retrieval_share} "
                f"for downstream entity/relation cap)"
            )
        except Exception as e:
            logger.warning(f"[LightragServer] _apply_llm_token_limits failed: {e}")

    def _compute_top_k_budget(self, max_model_len: int) -> tuple:
        """Return (top_k, chunk_top_k) for the given deployed context window.

        TOP_K and CHUNK_TOP_K feed the LightRAG vector search. Each retrieved
        entity/chunk costs roughly:
          - entity:        ~200 tokens (description + name)
          - chunk:         ~500 tokens (BGE-M3 chunk size of 1200 chars ≈ 500 tokens)
          - relation:      ~150 tokens

        So retrieved-token cost ≈ top_k * 200 + chunk_top_k * 500. For an 8K
        window with output 1024 + system 1800, the retrieval share is ~5400
        tokens — at the proportional split top_k=8 + chunk_top_k=12 fits
        comfortably (~5200 tokens retrieved), while top_k=12 + chunk_top_k=18
        saturates (~7200 tokens) and forces truncation.

        Tiers are bucket-sized so the common 8K boundaries (8192 / 8196) and
        16K (16384 / 16386) both land in the same tier regardless of the
        exact deployed value:
          <=  9K (9216)   -> top_k=8,  chunk_top_k=12  (8K resume/CRM)
          <= 17K (17408)  -> top_k=12, chunk_top_k=18  (eCan default)
          <= 33K (33792)  -> top_k=20, chunk_top_k=32  (LightRAG default)
          <= 66K (67584)  -> top_k=30, chunk_top_k=40
          >  66K          -> top_k=40, chunk_top_k=50
        """
        if max_model_len <= 9216:
            return 8, 12
        if max_model_len <= 17408:
            return 12, 18
        if max_model_len <= 33792:
            return 20, 32
        if max_model_len <= 67584:
            return 30, 40
        return 40, 50

    def _apply_top_k_for_window(self, env: dict) -> None:
        """Scale TOP_K / CHUNK_TOP_K to the deployed model's context window.

        Resolution order:
          1. Resolve max_model_len the same way _apply_llm_token_limits does
             (vLLM /v1/models -> ryoais_models.json -> static 8192 fallback).
          2. If the env already has a *smaller* TOP_K than the tier value,
             respect the user's choice (they may have tuned it for cost).
          3. If the env has a *larger* TOP_K than the tier value, cap it.
             Oversized retrieval on a small model bloats the prompt past the
             context window and slows generation 2-5x.
          4. CHUNK_TOP_K follows the same pattern but with its own tier table.

        Note: this is a *ceiling* policy, not a hard override. If the user's
        value is below the tier cap we leave it alone, matching the existing
        _apply_retrieval_token_limits behaviour.

        Never raises."""
        try:
            max_model_len = self._resolve_llm_max_model_len(env)
            if not max_model_len:
                # Cannot resolve — don't touch the user's settings.
                logger.debug(
                    "[LightragServer] max_model_len unknown; leaving TOP_K/CHUNK_TOP_K as-is"
                )
                return

            tier_top_k, tier_chunk_top_k = self._compute_top_k_budget(max_model_len)
            changes = []

            def _cap_if_oversized(key: str, tier_value: int, label: str) -> None:
                raw = env.get(key)
                if raw is None or str(raw).strip() == "":
                    return
                try:
                    n = int(str(raw).strip())
                except (ValueError, TypeError):
                    return
                if n > tier_value:
                    changes.append(f"{key}: {n} -> {tier_value} ({label} cap for {max_model_len}-token window)")
                    env[key] = str(tier_value)

            _cap_if_oversized('TOP_K', tier_top_k, 'top_k')
            _cap_if_oversized('CHUNK_TOP_K', tier_chunk_top_k, 'chunk_top_k')

            if changes:
                logger.warning(
                    f"[LightragServer] TOP_K scaled for {max_model_len}-token window: "
                    + "; ".join(changes)
                )
        except Exception as e:
            logger.warning(f"[LightragServer] _apply_top_k_for_window failed: {e}")

    # ---- vLLM max_model_len cache helpers -----------------------------------

    def _get_vllm_cache_path(self, env: dict = None) -> str:
        """Return the path to the persistent vLLM max_model_len cache file.

        The file lives next to the PID / log files so it travels with the
        workspace and is automatically workspace-scoped.
        """
        # Prefer the env dict (set by build_env at startup) over extra_env,
        # because lightrag_config_utils.py sets LOG_DIR there.
        _env = env or {}
        log_dir = _env.get('LOG_DIR') or self.extra_env.get('LOG_DIR')
        if not log_dir:
            app_data = _env.get('APP_DATA_PATH') or self.extra_env.get('APP_DATA_PATH')
            if app_data:
                log_dir = os.path.join(app_data, 'runlogs')
            else:
                log_dir = os.path.join(str(Path.cwd()), 'lightrag_data', 'runlogs')
        os.makedirs(log_dir, exist_ok=True)
        return os.path.join(log_dir, 'vllm_max_model_len.json')

    def _load_vllm_max_model_len_cache(self, env: dict = None) -> None:
        """Load persisted vLLM max_model_len entries from disk."""
        self._vllm_cache_file = self._get_vllm_cache_path(env)
        with self._vllm_cache_lock:
            try:
                if os.path.exists(self._vllm_cache_file):
                    with open(self._vllm_cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict):
                        self._vllm_cache = data
                        logger.info(
                            f"[LightragServer] Loaded vLLM max_model_len cache "
                            f"({len(data)} entries) from {self._vllm_cache_file}"
                        )
            except Exception as e:
                logger.debug(f"[LightragServer] Failed to load vLLM cache: {e}")
                self._vllm_cache = {}

    def _save_vllm_max_model_len(self, model: str, max_model_len: int) -> None:
        """Persist a discovered vLLM max_model_len to disk (workspace-scoped)."""
        if not model or not max_model_len or max_model_len <= 0:
            return
        with self._vllm_cache_lock:
            self._vllm_cache[model] = max_model_len
            cache_snapshot = dict(self._vllm_cache)
        try:
            with open(self._vllm_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_snapshot, f, ensure_ascii=False, indent=2)
            logger.warning(
                f"[LightragServer] vLLM max_model_len discovered and cached: "
                f"model={model} max_model_len={max_model_len}"
            )
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to save vLLM cache: {e}")

    def _parse_vllm_error_for_max_model_len(self, line: str) -> tuple:
        """Scan one stderr line for a vLLM 400 error that carries max_model_len.

        Returns (model, max_model_len) when found, else (None, None).
        The relevant error field looks like::

            "upstream_body": "{\"error\":{...\"max_model_len\":8196,...}}"
        """
        # Match the pattern where vLLM reports the cap inside upstream_body
        # e.g.: '"max_model_len":8196' or '"max_model_len": 8196'
        import re as _re
        m = _re.search(r'"max_model_len"\s*:\s*(\d+)', line)
        if not m:
            return None, None
        val = int(m.group(1))
        if val <= 0:
            return None, None
        # Also try to extract the model name from the error context
        model_m = _re.search(r'"requested_model"\s*:\s*"([^"]+)"', line)
        model = model_m.group(1) if model_m else None
        return model, val

    def _start_vllm_error_monitor(self) -> None:
        """Spawn a background thread that watches stderr for vLLM max_model_len.

        Once a value is found for a given model it is saved to the persistent
        cache and the thread terminates.  This makes the cap available to the
        very next LightRAG restart without needing another error.
        """
        def monitor():
            while True:
                # Re-open stderr pipe on every iteration so we catch new lines
                # written by the child process (stderr_log is a rotating wrapper).
                stderr_path = None
                if self._last_log_paths and self._last_log_paths[1]:
                    stderr_path = self._last_log_paths[1]
                if not stderr_path or not os.path.exists(stderr_path):
                    import time as _t
                    _t.sleep(2)
                    if not self._vllm_monitor_event.wait(timeout=0):
                        break
                    continue

                current_pos = 0
                # Track per-model so we stop after first discovery per model
                discovered: dict = {}   # model -> max_model_len
                while True:
                    import time as _t
                    _t.sleep(2)
                    if not self._vllm_monitor_event.is_set():
                        break
                    if not os.path.exists(stderr_path):
                        break
                    try:
                        with open(stderr_path, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(current_pos)
                            for raw in f:
                                model, val = self._parse_vllm_error_for_max_model_len(raw)
                                if model and val:
                                    discovered[model] = val
                            current_pos = f.tell()
                        # Once we have discoveries, save and signal stop
                        if discovered:
                            for m, v in discovered.items():
                                self._save_vllm_max_model_len(m, v)
                            break
                    except Exception:
                        pass
                if not self._vllm_monitor_event.is_set():
                    break

        self._vllm_monitor_event = threading.Event()
        self._vllm_monitor_event.set()
        t = threading.Thread(target=monitor, name="LightragVLLMErrorMonitor", daemon=True)
        t.start()
        self._vllm_error_monitor_thread = t
        logger.info("[LightragServer] vLLM error monitor thread started")

    # Minimum token limits to ensure chunks are not completely discarded
    # These are industry-standard minimums for RAG systems
    _MIN_ENTITY_TOKENS = 1500   # Minimum for entity context (covers ~5-10 entities)
    _MIN_RELATION_TOKENS = 2000 # Minimum for relation context (covers ~10-20 relations)
    _MIN_CHUNK_BUDGET = 500     # Minimum tokens reserved for chunks

    def _compute_retrieval_budget(self, max_model_len: int) -> tuple:
        """Return (entity_cap, relation_cap) for the given deployed context window.

        Proportional allocation: entity gets 40% of the retrieval share,
        relation gets 60%. For 8K the retrieval share is ~6668, giving
        entity=2667, relation=4001; for 32K the share is ~27068, giving
        entity=10827, relation=16241 (well over LightRAG's hardcoded
        defaults of 6000/8000 — those defaults apply naturally for ≤32K).

        The split (entity 40% / relation 60%) preserves the historical
        4:6 ratio used by the legacy ceiling logic, so retrieval quality
        on larger models doesn't regress.
        """
        retrieval_share = max(0, max_model_len - int(max_model_len * 0.125) - 500)
        entity_cap = int(retrieval_share * 0.4)
        relation_cap = retrieval_share - entity_cap
        return entity_cap, relation_cap

    def _apply_retrieval_token_limits(self, env: dict) -> None:
        """Ensure retrieval token limits (entity/relation) fit within MAX_TOTAL_TOKENS.

        LightRAG's DEFAULT_MAX_ENTITY_TOKENS (6000) + DEFAULT_MAX_RELATION_TOKENS (8000)
        = 14000, which exceeds most deployments' MAX_TOTAL_TOKENS (8196). This causes
        the entity/relation context to consume the entire budget and leaves zero for
        chunks — or worse, exceeds the model's context window entirely.

        Behaviour (paired with _compute_llm_budget output budget):
          - Cap entity and relation to the proportional 40:60 split of the
            retrieval share (window minus output minus 500 system overhead).
            For 8K this caps entity≈2668, relation≈4004.
          - Floor at 500 entity / 800 relation so sub-2K windows still
            surface useful context.
          - If the resulting entity+relation+output+500 would push chunk
            budget below 500, scale entity/relation down proportionally so
            chunks are never completely discarded.
        """
        # Tier-based caps. These default to safe values when MAX_TOTAL_TOKENS is
        # not yet set (e.g. _apply_llm_token_limits failed to resolve max_model_len).
        max_total = self._coerce_int(env.get('MAX_TOTAL_TOKENS')) or 8192
        cap_entity, cap_relation = self._compute_retrieval_budget(max_total)

        try:
            entity_tokens = self._coerce_int(env.get('MAX_ENTITY_TOKENS'))
            relation_tokens = self._coerce_int(env.get('MAX_RELATION_TOKENS'))

            # ---- Ceiling: cap to the tier value ----
            changes = []
            if entity_tokens is not None and entity_tokens > cap_entity:
                changes.append(f"MAX_ENTITY_TOKENS: {entity_tokens} -> {cap_entity} (tier cap for {max_total}-token window)")
                env['MAX_ENTITY_TOKENS'] = str(cap_entity)
                entity_tokens = cap_entity

            if relation_tokens is not None and relation_tokens > cap_relation:
                changes.append(f"MAX_RELATION_TOKENS: {relation_tokens} -> {cap_relation} (tier cap for {max_total}-token window)")
                env['MAX_RELATION_TOKENS'] = str(cap_relation)
                relation_tokens = cap_relation

            # ---- Floor: raise values set too low (only when explicitly set) ----
            # Sub-2K windows still get something useful.
            floor_entity = 500
            floor_relation = 800
            if entity_tokens is not None and entity_tokens < floor_entity:
                changes.append(f"MAX_ENTITY_TOKENS: {entity_tokens} -> {floor_entity} (floor)")
                env['MAX_ENTITY_TOKENS'] = str(floor_entity)
                entity_tokens = floor_entity

            if relation_tokens is not None and relation_tokens < floor_relation:
                changes.append(f"MAX_RELATION_TOKENS: {relation_tokens} -> {floor_relation} (floor)")
                env['MAX_RELATION_TOKENS'] = str(floor_relation)
                relation_tokens = floor_relation

            # ---- Chunk budget sanity check ----
            entity_limit = entity_tokens or cap_entity
            relation_limit = relation_tokens or cap_relation
            chunk_budget = max_total - entity_limit - relation_limit
            # Reserve at least _MIN_CHUNK_BUDGET for the chunk context; otherwise
            # LightRAG truncates chunks to zero and the query returns "no results".
            if chunk_budget < self._MIN_CHUNK_BUDGET:
                # If we'd starve chunks, scale entity/relation down proportionally
                # (only the explicit-overridden values; the tier caps stay authoritative)
                headroom = max_total - self._MIN_CHUNK_BUDGET
                scaled_entity = max(floor_entity, int(headroom * 0.4))
                scaled_relation = max(floor_relation, headroom - scaled_entity)
                changes.append(
                    f"Chunk budget critically low: {chunk_budget} tokens "
                    f"(MIN={self._MIN_CHUNK_BUDGET}). Scaling ENTITY->{scaled_entity}, "
                    f"RELATION->{scaled_relation} to preserve chunk budget."
                )
                env['MAX_ENTITY_TOKENS'] = str(scaled_entity)
                env['MAX_RELATION_TOKENS'] = str(scaled_relation)
                chunk_budget = max_total - scaled_entity - scaled_relation

            if changes:
                for msg in changes:
                    if "critically" in msg.lower() or "tier cap" in msg.lower():
                        logger.warning(f"[LightragServer] {msg}")
                    else:
                        logger.info(f"[LightragServer] {msg}")
        except Exception as e:
            logger.debug(f"[LightragServer] _apply_retrieval_token_limits failed: {e}")

    @staticmethod
    def _coerce_int(value) -> Optional[int]:
        """Return int(value) if value parses as a positive integer, else None."""
        if value is None:
            return None
        try:
            n = int(str(value).strip())
            return n if n > 0 else None
        except (ValueError, TypeError):
            return None

    def _ensure_utf8_locale(self, env):
        target_locale = 'en_US.UTF-8'
        if env.get('LANG') or env.get('LC_ALL'): return
        if self._locale_available(target_locale):
            env.setdefault('LANG', target_locale)
            env.setdefault('LC_ALL', target_locale)

    @staticmethod
    def _locale_available(locale_name: str) -> bool:
        try:
            locale.setlocale(locale.LC_ALL, locale_name)
            return True
        except locale.Error:
            return False

    @staticmethod
    def _mask_env_value(key: str, value: str) -> str:
        """Mask sensitive environment values when logging"""
        if value is None:
            return "<None>"

        # Only mask if key ends with these sensitive suffixes
        # This avoids masking config parameters like MAX_TOKENS, TOKEN_LIMIT, etc.
        sensitive_suffixes = ["_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_API_KEY"]
        upper_key = str(key).upper()
        if any(upper_key.endswith(suffix) for suffix in sensitive_suffixes):
            text = str(value)
            if len(text) <= 8:
                return "***"
            return f"{text[:4]}...{text[-4:]}"

        return str(value)

    def _get_virtual_env_python(self):
        from utils.venv_helper import VenvHelper
        from pathlib import Path
        from config.app_info import app_info
        
        # Use app_home_path from app_info as project root
        project_root = Path(app_info.app_home_path)
        python_exe = VenvHelper.find_python_interpreter(project_root=project_root, prefer_pythonw=True)
        return str(python_exe)
    

    def _validate_python_executable(self, python_path):
        if not python_path or not os.path.exists(python_path):
            logger.error(f"[LightragServer] Python executable not found: {python_path}")
            return False
        return True

    def _try_alternative_port(self, original_port):
        import socket
        try:
            for port in range(original_port, original_port + 10):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result != 0:
                    if port != original_port:
                        logger.info(f"[LightragServer] Found alternative port {port}")
                    self.extra_env["PORT"] = str(port)
                    return True
                elif port == original_port and original_port == 9621:
                    logger.info(f"[LightragServer] Standard port {original_port} in use, retrying...")
                    time.sleep(1.0)
                    # Simple single retry for brevity
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(1)
                    res = sock.connect_ex(('localhost', original_port))
                    sock.close()
                    if res != 0:
                        self.extra_env["PORT"] = str(original_port)
                        return True

            logger.error(f"[LightragServer] No available ports found in range {original_port}-{original_port + 9}")
            return False
        except Exception as e:
            logger.warning(f"[LightragServer] Error trying alternative ports: {e}")
            return False

    def _wait_for_port_release(self, port: int, timeout: float = 10.0) -> bool:
        try:
            import socket
            deadline = time.time() + timeout
            while time.time() < deadline:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    result = sock.connect_ex(('localhost', port))
                if result != 0: return True
                time.sleep(0.2)
        except Exception: pass
        return False

    def _get_pid_file_path(self, env=None):
        env = env or {}
        log_dir = env.get('LOG_DIR') or self.extra_env.get('LOG_DIR')
        if not log_dir:
            app_data_path = env.get('APP_DATA_PATH') or self.extra_env.get('APP_DATA_PATH')
            if app_data_path:
                log_dir = os.path.join(app_data_path, 'runlogs')
            else:
                log_dir = os.path.join(str(Path.cwd()), 'lightrag_data', 'runlogs')
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            log_dir = str(Path.cwd())
        pid_path = os.path.join(log_dir, 'lightrag_server.pid')
        self._pid_file_path = pid_path
        return pid_path

    def _read_pid_file(self, env=None):
        try:
            pid_file = self._get_pid_file_path(env)
            if not os.path.exists(pid_file): return None
            with open(pid_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception: return None

    def _write_pid_file(self, pid, env):
        try:
            pid_file = self._get_pid_file_path(env)
            start_time = self._get_process_start_time(pid)
            with open(pid_file, 'w', encoding='utf-8') as f:
                json.dump({'pid': pid, 'start_time': start_time}, f)
        except Exception: pass

    def _remove_pid_file(self):
        try:
            pid_file = self._pid_file_path
            if pid_file and os.path.exists(pid_file): os.remove(pid_file)
        except Exception: pass

    @staticmethod
    def _get_process_start_time(pid):
        try:
            import psutil
            return time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(psutil.Process(int(pid)).create_time()))
        except Exception: return ''

    @staticmethod
    def _is_process_alive(pid):
        try:
            import psutil
            return psutil.pid_exists(int(pid))
        except Exception:
            try:
                os.kill(int(pid), 0)
                return True
            except Exception: return False

    def _terminate_pid(self, pid, force=False):
        try:
            os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
        except Exception: pass

    def _wait_for_process_termination(self, pid, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._is_process_alive(pid): return True
            time.sleep(0.2)
        return not self._is_process_alive(pid)

    def _cleanup_stale_process(self, env, port):
        pid_info = self._read_pid_file(env)
        if not pid_info: return
        pid = pid_info.get('pid')
        if not pid or not self._is_process_alive(pid):
            self._remove_pid_file()
            return
        
        recorded_start = pid_info.get('start_time', '')
        current_start = self._get_process_start_time(pid)
        if recorded_start and current_start and recorded_start.strip() != current_start.strip():
            self._remove_pid_file()
            return

        logger.warning(f"[LightragServer] Terminating stale process {pid}")
        self._terminate_pid(pid, force=False)
        if not self._wait_for_process_termination(pid):
            self._terminate_pid(pid, force=True)
        self._wait_for_port_release(port)
        self._remove_pid_file()

    def _log_startup_failure(self):
        if not hasattr(self, '_last_log_paths') or not self._last_log_paths:
            return
        
        out_path, err_path = self._last_log_paths
        
        def read_tail(path, n=20):
            if not path or not os.path.exists(path): return []
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.readlines()[-n:]
            except: return []

        stderr_lines = read_tail(err_path)
        stdout_lines = read_tail(out_path)
        
        if stderr_lines:
            logger.error(f"[LightragServer] Stderr tail:\n{''.join(stderr_lines)}")
        if stdout_lines:
            logger.error(f"[LightragServer] Stdout tail:\n{''.join(stdout_lines)}")

    def _create_log_files(self, env=None):
        """
        Create log file handles for LightRAG server subprocess output.
        Uses fixed filenames (lightrag_server.log) instead of timestamped files
        to avoid accumulating many log files. Implements simple log rotation
        when files exceed 10MB.
        """
        # Reuse the exact environment that will be passed to the subprocess.
        # Rebuilding here can perform remote model discovery a second time and
        # produce token limits different from the environment being launched.
        env = env or self.build_env()
        log_dir = env.get('LOG_DIR', '')
        if not log_dir:
            log_dir = os.path.join(str(Path.cwd()), 'lightrag_data', 'runlogs')
        os.makedirs(log_dir, exist_ok=True)
        
        # Use fixed filenames instead of timestamps to avoid log file accumulation
        out_path = os.path.join(log_dir, "lightrag_server.log")
        err_path = os.path.join(log_dir, "lightrag_server_error.log")
        
        # Simple log rotation: if file > 10MB, rename to .old and start fresh
        max_size = 10 * 1024 * 1024  # 10MB
        for path in [out_path, err_path]:
            if os.path.exists(path) and os.path.getsize(path) > max_size:
                old_path = path + '.old'
                try:
                    if os.path.exists(old_path):
                        os.remove(old_path)
                    os.rename(path, old_path)
                    logger.info(f"[LightragServer] Rotated log file: {path}")
                except Exception as e:
                    logger.warning(f"[LightragServer] Failed to rotate log {path}: {e}")
        
        # Append mode with line buffering for real-time output
        return (
            open(out_path, 'a', encoding='utf-8', buffering=1),
            open(err_path, 'a', encoding='utf-8', buffering=1),
            out_path,
            err_path
        )

    def _close_log_files(self):
        if self._stdout_log_handle:
            try: self._stdout_log_handle.close()
            except Exception: pass
            self._stdout_log_handle = None
        if self._stderr_log_handle:
            try: self._stderr_log_handle.close()
            except Exception: pass
            self._stderr_log_handle = None

    def _start_server_process(self, wait_gating: bool = False):
        try:
            env = self.build_env()
            self._close_log_files()
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files(env)
            self._stdout_log_handle = stdout_log
            self._stderr_log_handle = stderr_log
            self._last_log_paths = (stdout_log_path, stderr_log_path)

            try: desired_port = int(env.get("PORT", "9621"))
            except: desired_port = 9621

            self._cleanup_stale_process(env, desired_port)
            if not self._try_alternative_port(desired_port):
                logger.error("[LightragServer] No available port")
                return False
            env["PORT"] = str(self.extra_env.get("PORT", desired_port))

            from utils.venv_helper import VenvHelper
            from config.app_info import app_info
            python_executable = self._get_virtual_env_python()
            
            # Add project root to PYTHONPATH for knowledge module import
            project_root = app_info.app_home_path
            existing_pythonpath = env.get('PYTHONPATH', '')
            if existing_pythonpath:
                env['PYTHONPATH'] = f"{project_root}:{existing_pythonpath}"
            else:
                env['PYTHONPATH'] = project_root
            logger.info(f"[LightragServer] Set PYTHONPATH to include project root: {project_root}")
            
            # Use the static launcher script for SSL patching
            launcher_path = os.path.join(os.path.dirname(__file__), "lightrag_launcher.py")

            if VenvHelper.is_packaged_environment():
                # PyInstaller Packaged Environment
                # We cannot use sys.executable as a generic python interpreter to run scripts with arguments
                # Instead, we use the main application executable with ECAN_RUN_SCRIPT env var
                # This triggers the worker mode in main.py
                logger.info(f"[LightragServer] Running in packaged environment via ECAN_RUN_SCRIPT")
                
                if os.path.exists(launcher_path):
                    env['ECAN_RUN_SCRIPT'] = launcher_path
                    # Use the main executable itself (e.g., eCan.app/Contents/MacOS/eCan)
                    cmd = [sys.executable]
                    logger.info(f"[LightragServer] Using launcher script via worker mode: {launcher_path}")
                else:
                     logger.error(f"[LightragServer] Critical: Launcher script not found in packaged env: {launcher_path}")
                     return False
            else:
                # Development Environment
                if not self._validate_python_executable(python_executable): return False
            
                if os.path.exists(launcher_path):
                    cmd = [python_executable, "-u", launcher_path]
                    logger.info(f"[LightragServer] Using launcher script: {launcher_path}")
                else:
                    logger.warning(f"[LightragServer] Launcher not found at {launcher_path}, falling back to -m (SSL patch will NOT be applied)")
                    cmd = [python_executable, "-u", "-m", "lightrag.api.lightrag_server"]

            # Log final environment variables (masked) for debugging
            # try:
            #     debug_env = {k: self._mask_env_value(k, v) for k, v in env.items()}
            #     logger.info(f"[LightragServer] Process Environment:\n{json.dumps(debug_env, ensure_ascii=False, indent=2)}")
            # except Exception as e:
            #     logger.warning(f"[LightragServer] Failed to log environment: {e}")

            # Log useful configuration summary
            try:
                summary = []
                summary.append("="*30 + " LightRAG Config Summary " + "="*30)
                
                # LLM
                llm_provider = env.get('LLM_BINDING', 'Unknown')
                llm_model = env.get('LLM_MODEL', 'Unknown')
                summary.append(f"🤖 LLM Provider:      {llm_provider}")
                summary.append(f"   LLM Model:         {llm_model}")
                if env.get('LLM_BINDING_HOST'):
                    summary.append(f"   LLM Host:          {env.get('LLM_BINDING_HOST')}")
                if env.get('LLM_BINDING_API_KEY'):
                    summary.append(f"   LLM Key:           {self._mask_env_value('LLM_API_KEY', env['LLM_BINDING_API_KEY'])}")

                # Embedding
                embed_provider = env.get('EMBEDDING_BINDING', 'Unknown')
                embed_model = env.get('EMBEDDING_MODEL', 'Unknown')
                embed_dim = env.get('EMBEDDING_DIM', 'Unknown')
                summary.append(f"🧠 Embedding Provider: {embed_provider}")
                summary.append(f"   Embedding Model:   {embed_model}")
                summary.append(f"   Embedding Dim:     {embed_dim}")
                if env.get('EMBEDDING_BINDING_HOST'):
                    summary.append(f"   Embedding Host:    {env.get('EMBEDDING_BINDING_HOST')}")
                if env.get('EMBEDDING_BINDING_API_KEY'):
                    summary.append(f"   Embedding Key:     {self._mask_env_value('EMBEDDING_API_KEY', env['EMBEDDING_BINDING_API_KEY'])}")
                
                # Check FAISS index dimension mismatch and auto-fix
                try:
                    import shutil
                    from datetime import datetime

                    working_dir = env.get('WORKING_DIR')
                    workspace = (env.get('WORKSPACE') or '').strip()
                    if working_dir:
                        workspace_candidates = []
                        if workspace and os.path.basename(os.path.normpath(working_dir)) == workspace:
                            workspace_candidates.append(working_dir)
                        if workspace:
                            workspace_candidates.append(os.path.join(working_dir, workspace))
                        workspace_candidates.append(working_dir)

                        workspace_path = next((p for p in workspace_candidates if p and os.path.isdir(p)), None)
                        if workspace_path:
                            possible_index_files = [
                                'vdb_entities.index',
                                'faiss_index_entities.index',
                                'vdb_chunks.index',
                                'faiss_index_chunks.index',
                            ]

                            existing_dim = None
                            for file_name in possible_index_files:
                                faiss_index_path = os.path.join(workspace_path, file_name)
                                if not os.path.exists(faiss_index_path):
                                    continue
                                try:
                                    import faiss

                                    index = faiss.read_index(faiss_index_path)
                                    existing_dim = getattr(index, 'd', None)
                                    if existing_dim:
                                        logger.info(f"[LightRAG] Detected FAISS dimension {existing_dim} from {faiss_index_path}")
                                        break
                                except Exception as read_error:
                                    logger.debug(f"[LightRAG] Could not read FAISS index {faiss_index_path}: {read_error}")

                            if existing_dim is not None:
                                if str(existing_dim) != str(embed_dim):
                                    # Dimension mismatch detected - auto-fix
                                    logger.warning(f"[LightRAG] ⚠️  Dimension mismatch: config={embed_dim}, existing FAISS={existing_dim}")
                                    summary.append(f"   ⚠️  Dimension mismatch detected!")
                                    summary.append(f"       Config dimension:   {embed_dim}")
                                    summary.append(f"       Existing FAISS dim: {existing_dim}")

                                    # Auto-fix: backup old workspace and create new one
                                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    workspace_label = workspace or os.path.basename(os.path.normpath(workspace_path)) or 'workspace'
                                    backup_name = f"{workspace_label}_{existing_dim}d_backup_{timestamp}"
                                    backup_path = os.path.join(os.path.dirname(workspace_path), backup_name)

                                    try:
                                        logger.info(f"[LightRAG] 🔄 Auto-fixing: Backing up old workspace to '{backup_name}'")
                                        shutil.move(workspace_path, backup_path)
                                        os.makedirs(workspace_path, exist_ok=True)

                                        summary.append(f"   ✅ Auto-fixed: Old workspace backed up")
                                        summary.append(f"       Backup: {backup_name}")
                                        summary.append(f"       New workspace will use {embed_dim}d")
                                        logger.info("[LightRAG] ✅ Auto-fix completed: Old data backed up, new workspace created")
                                        logger.info(f"[LightRAG] 📁 Backup location: {backup_path}")
                                        logger.info(f"[LightRAG] 🔙 To restore: mv '{backup_path}' '{workspace_path}'")
                                    except Exception as fix_error:
                                        logger.error(f"[LightRAG] ❌ Auto-fix failed: {fix_error}")
                                        summary.append(f"   ❌ Auto-fix failed: {fix_error}")
                                        summary.append("       → Manual fix required: delete FAISS index files")
                                else:
                                    summary.append(f"   ✅ FAISS index dimension matches config ({existing_dim})")
                except Exception as e:
                    logger.debug(f"[LightRAG] Error checking FAISS dimension: {e}")

                # Rerank - show both original and converted provider
                original_rerank_provider = "Unknown"
                try:
                    from knowledge.lightrag_config_manager import get_config_manager
                    config_manager = get_config_manager()
                    original_config = config_manager.get_effective_config()
                    original_rerank_provider = original_config.get('RERANK_BINDING', 'null')
                except Exception:
                    pass
                
                rerank_provider = env.get('RERANK_BINDING', 'null')
                rerank_model = env.get('RERANK_MODEL', '')
                rerank_enabled = env.get('RERANK_BY_DEFAULT', 'false')
                
                # Show original provider if different from converted
                if original_rerank_provider != rerank_provider and original_rerank_provider != "Unknown":
                    summary.append(f"🔄 Rerank Provider:    {original_rerank_provider} (user config) → {rerank_provider} (passed to LightRAG)")
                else:
                    summary.append(f"🔄 Rerank Provider:    {rerank_provider}")
                
                summary.append(f"   Rerank Model:      {rerank_model if rerank_model else 'N/A'}")
                summary.append(f"   Enabled by Default: {rerank_enabled}")
                if env.get('RERANK_BINDING_HOST'):
                    summary.append(f"   Rerank Host:       {env.get('RERANK_BINDING_HOST')}")
                
                # Show target service URL (where proxy will forward requests)
                target_service_url = "Unknown"
                try:
                    from app_context import AppContext
                    app_context = AppContext.get_instance()
                    if app_context and app_context.main_window:
                        rerank_manager = app_context.main_window.config_manager.rerank_manager
                        # Use original provider to get target URL
                        provider_to_check = original_rerank_provider if original_rerank_provider != "Unknown" else rerank_provider
                        provider_config = rerank_manager.get_provider(provider_to_check)
                        if provider_config:
                            base_url = provider_config.get('base_url', '').rstrip('/')
                            if base_url:
                                provider_type = provider_config.get('provider', '').lower()
                                # Build URL correctly - check if base_url already has /v1
                                if provider_type in ('ryoais', 'ecanai'):
                                    if base_url.endswith('/v1'):
                                        target_service_url = f"{base_url}/rerank"
                                    else:
                                        target_service_url = f"{base_url}/v1/rerank"
                                elif provider_type == 'ollama':
                                    target_service_url = f"{base_url}/api/embed"
                                else:
                                    target_service_url = f"{base_url}/rerank"
                except Exception:
                    pass
                
                if target_service_url != "Unknown":
                    summary.append(f"   🎯 Target Host:    {target_service_url} (final destination)")
                
                if original_rerank_provider != rerank_provider and original_rerank_provider != "Unknown":
                    summary.append(f"   Note: Non-native provider '{original_rerank_provider}' converted to '{rerank_provider}' by launcher")
                if env.get('RERANK_BINDING_API_KEY'):
                    summary.append(f"   Rerank Key:        {self._mask_env_value('RERANK_API_KEY', env['RERANK_BINDING_API_KEY'])}")

                # Storage
                summary.append("-" * 20 + " Storage " + "-" * 20)
                summary.append(f"� Workspace:         {env.get('WORKSPACE', 'Unknown')}")
                summary.append(f"� KV Storage:        {env.get('LIGHTRAG_KV_STORAGE', 'Default')}")
                summary.append(f"📊 Vector Storage:    {env.get('LIGHTRAG_VECTOR_STORAGE', 'Default')}")
                summary.append(f"🕸️ Graph Storage:     {env.get('LIGHTRAG_GRAPH_STORAGE', 'Default')}")
                summary.append(f"📄 Doc Status:        {env.get('LIGHTRAG_DOC_STATUS_STORAGE', 'Default')}")
                
                # Common DB
                if any(v and v.startswith('PG') for k,v in env.items() if k.endswith('_STORAGE')):
                     summary.append("-" * 20 + " Database " + "-" * 20)
                     summary.append(f"🗄️ Postgres Host:     {env.get('POSTGRES_HOST', 'localhost')}:{env.get('POSTGRES_PORT', '5432')}")
                     summary.append(f"   Database:          {env.get('POSTGRES_DATABASE', '')}")

                summary.append("="*83)
                logger.info("\n".join(summary))
            except Exception: pass

            logger.info(f"[LightragServer] Starting: {' '.join(cmd)}")
            import platform
            if platform.system().lower().startswith('win'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0
                self.proc = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=stdout_log, stderr=stderr_log, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NEW_PROCESS_GROUP, startupinfo=startupinfo)
            else:
                self.proc = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=stdout_log, stderr=stderr_log, text=True, encoding='utf-8', errors='replace', preexec_fn=os.setsid)

            try: 
                if self.proc.stdin: 
                    self.proc.stdin.write("yes\n")
                    self.proc.stdin.flush()
            except: pass

            logger.info(f"[LightragServer] Started on port {env['PORT']}")
            # Record the ACTUAL bound port on the instance AND the parent
            # process env. The client (knowledge/lightrag_client.py) resolves
            # its base_url from os.environ['PORT']; when 9621 was occupied
            # (e.g. a stale orphan from a previous session) the server
            # relocated but only the SUBPROCESS env knew — every client call
            # then went to the orphan (2026-08-30: ingest hit an old
            # ollama-configured instance on 9621 while the real server sat
            # on 9622).
            self.port = env.get('PORT')
            try:
                os.environ['PORT'] = str(env['PORT'])
            except Exception:
                pass
            if self.proc and self.proc.poll() is None:
                self._write_pid_file(self.proc.pid, env)

                # Start vLLM error monitor so we catch max_model_len on the very
                # first 400 error, making it available for the next restart.
                self._start_vllm_error_monitor()

                if wait_gating:
                    health_timeout = float(env.get('LIGHTRAG_HEALTH_TIMEOUT', 120.0))
                    if self._wait_for_server_ready(int(env['PORT']), timeout=health_timeout):
                        self._set_start_status(True, 'LightRAG server is ready', '')
                        # ── Async warmup (2026-05-18) ──
                        # /auth-status returning 200 means the FastAPI app
                        # is accepting connections, BUT LightRAG's first
                        # /query still pays a one-time init cost (load
                        # vector indexes into memory, lazy-init embedding
                        # client pool, fault-in graph storage).  Observed
                        # 2026-05-18 customer trace: first rag_query of a
                        # session waited ~7.7 s "inside LightRAG init"
                        # before processing began.  Fire a synthetic
                        # short query in a background thread so the cost
                        # is paid before the first customer-driven query
                        # arrives.  Non-blocking: the app start path
                        # returns immediately; only the first real query
                        # benefits if the warmup hasn't finished yet
                        # (which is still a strict improvement).
                        try:
                            self._spawn_warmup_query(int(env['PORT']), env)
                        except Exception as _warm_err:
                            logger.debug(
                                f"[LightragServer] Warmup spawn failed "
                                f"(non-fatal): {_warm_err}"
                            )
                        return True
                    else:
                        # Check if process is still alive - if so, don't kill it
                        # The server may just be slow to initialize (e.g. first-time FAISS/NetworkX setup)
                        if self.proc and self.proc.poll() is None:
                            logger.warning(
                                "[LightragServer] Server not ready within timeout, but process is still alive. "
                                "Keeping server running in background - it may become ready later."
                            )
                            self._log_startup_failure()
                            # Start background health monitor to detect when server becomes ready
                            self._start_background_health_monitor(int(env['PORT']))
                            self._set_start_status(True, 'LightRAG server is still starting in background', '')
                            return True  # Return success so the app doesn't block
                        else:
                            logger.error("[LightragServer] Server failed to become ready and process has exited.")
                            self._log_startup_failure()
                            self._set_start_status(False, 'LightRAG startup failed: process exited before ready', 'startup_failed')
                            self.stop()
                            return False
                
                self._set_start_status(True, 'LightRAG server started', '')
                return True
            self._set_start_status(False, 'LightRAG startup failed: process not running after spawn', 'startup_failed')
            return False
        except Exception as e:
            logger.error(f"[LightragServer] Start error: {e}")
            self._set_start_status(False, str(e), 'start_exception')
            return False

    def _wait_for_server_ready(self, port, timeout=120.0):
        start_time = time.time()
        import requests
        
        logger.info(f"[LightragServer] Waiting for server to be ready on port {port} (timeout: {timeout}s)...")
        attempt = 0
        while time.time() - start_time < timeout:
            attempt += 1
            elapsed = time.time() - start_time
            try:
                # Check if process is still running
                if self.proc and self.proc.poll() is not None:
                    logger.error(f"[LightragServer] Server process exited prematurely with code {self.proc.returncode}")
                    return False
                
                # Use /auth-status instead of /health (which requires authentication)
                # /auth-status is public and returns server status
                response = requests.get(f"http://127.0.0.1:{port}/auth-status", timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"[LightragServer] Server is ready on port {port} (took {elapsed:.1f}s, {attempt} attempts)")
                    logger.info(f"[LightragServer] Auth mode: {data.get('auth_mode', 'unknown')}, API version: {data.get('api_version', 'unknown')}")
                    return True
                else:
                    logger.debug(f"[LightragServer] Health check attempt {attempt} got status {response.status_code} ({elapsed:.1f}s elapsed)")
            except requests.exceptions.ConnectionError as e:
                logger.debug(f"[LightragServer] Health check attempt {attempt} connection refused ({elapsed:.1f}s elapsed)")
            except requests.exceptions.Timeout:
                logger.debug(f"[LightragServer] Health check attempt {attempt} timeout ({elapsed:.1f}s elapsed)")
            except Exception as e:
                logger.debug(f"[LightragServer] Health check attempt {attempt} error: {type(e).__name__} ({elapsed:.1f}s elapsed)")
            # Progressive interval: 0.5s for first 30s, 1s for 30-60s, 2s after 60s
            if elapsed < 30:
                time.sleep(0.5)
            elif elapsed < 60:
                time.sleep(1.0)
            else:
                time.sleep(2.0)
        
        logger.warning(f"[LightragServer] Timeout waiting for server ready on port {port} after {timeout}s ({attempt} attempts). Server may still be initializing (first-time FAISS/NetworkX setup can be slow).")
        return False

    def _spawn_warmup_query(self, port: int, env: dict) -> None:
        """Fire a synthetic /query in a background thread to pay LightRAG's
        first-query init cost before the first real customer query lands.

        Why: ``/auth-status`` returning 200 only proves FastAPI is up;
        LightRAG itself does lazy initialisation on first query:
          * vector store handles are constructed
          * embedding client pool is opened
          * graph storage loads into memory
          * keyword-extraction LLM client warms its TCP pool
        Customer's 2026-05-18 trace showed the first rag_query of a
        session spent ~7.7 s in this lock-wait before processing began,
        compounding the 8 s+ that the second LLM call already cost.
        A throwaway "warmup" query, fired BEFORE customer load arrives,
        pre-pays this cost so the first real query is fast.

        Non-blocking: runs in a daemon thread.  If the warmup fails or
        is slow, the only downside is the first real query may still
        pay some cost — strictly no worse than today.  Disabled by env
        ``ECAN_LIGHTRAG_WARMUP=0`` if an operator needs to skip it.
        """
        # Read the disable flag from the SUBPROCESS env (the launcher
        # may have stripped it from os.environ).  Default ON.
        if str(env.get("ECAN_LIGHTRAG_WARMUP", "1")).strip().lower() in (
            "0", "false", "no", "off",
        ):
            logger.info("[LightragServer] Warmup disabled by ECAN_LIGHTRAG_WARMUP")
            return

        import threading

        def _warmup_worker():
            import time as _wt
            import requests as _wr
            _wt0 = _wt.time()
            try:
                # Short, generic query to touch every lazy code path
                # (keyword extraction LLM, embedding API, vector
                # search, context builder).  ``only_need_context=True``
                # skips the synthesis LLM — we just want the init paths
                # warm; we don't need a real answer.
                resp = _wr.post(
                    f"http://127.0.0.1:{port}/query",
                    json={
                        "query": "warmup",
                        "mode": "mix",
                        "only_need_context": True,
                    },
                    timeout=60,
                )
                _elapsed = _wt.time() - _wt0
                if resp.status_code == 200:
                    logger.info(
                        f"[LightragServer] Warmup query OK in {_elapsed:.1f}s "
                        f"— first customer query will skip the init cost"
                    )
                else:
                    logger.warning(
                        f"[LightragServer] Warmup query returned "
                        f"HTTP {resp.status_code} in {_elapsed:.1f}s — "
                        f"first real query may still pay init cost"
                    )
            except Exception as exc:
                _elapsed = _wt.time() - _wt0
                logger.warning(
                    f"[LightragServer] Warmup query failed after "
                    f"{_elapsed:.1f}s ({type(exc).__name__}: {exc}) — "
                    f"first real query may still pay init cost"
                )

        t = threading.Thread(
            target=_warmup_worker, name="LightragWarmup", daemon=True,
        )
        t.start()
        logger.info(
            f"[LightragServer] Warmup query dispatched (background "
            f"thread, port {port})"
        )

    def _start_background_health_monitor(self, port, check_interval=5.0, max_duration=300.0):
        """Start a background thread that continues health-checking the server.
        
        This is used when the initial wait_for_server_ready times out but the process
        is still alive. The server may just be slow to initialize (e.g. first-time
        FAISS index build, NetworkX graph loading).
        
        Args:
            port: Server port to check
            check_interval: Seconds between health checks
            max_duration: Maximum time to keep monitoring (seconds)
        """
        def _monitor():
            import requests
            start = time.time()
            logger.info(f"[LightragServer] Background health monitor started (port={port}, max={max_duration}s)")
            while time.time() - start < max_duration:
                try:
                    if self.proc and self.proc.poll() is not None:
                        logger.error("[LightragServer] Background monitor: server process has exited")
                        return
                    response = requests.get(f"http://127.0.0.1:{port}/auth-status", timeout=3)
                    if response.status_code == 200:
                        elapsed = time.time() - start
                        logger.info(
                            f"[LightragServer] Background monitor: server is NOW ready on port {port} "
                            f"(took {elapsed:.1f}s after initial timeout)"
                        )
                        return
                except Exception:
                    pass
                time.sleep(check_interval)
            logger.warning(f"[LightragServer] Background monitor: gave up after {max_duration}s, server may still start later")

        t = threading.Thread(target=_monitor, name="LightragBgHealthMonitor", daemon=True)
        t.start()

    def start(self, wait_ready=False):
        if self.is_running():
            self._set_start_status(True, 'LightRAG server is already running', '')
            return True
        if time.time() - self.last_restart_time > 300: self.restart_count = 0
        if self.restart_count >= self.max_restarts:
            logger.error("[LightragServer] Max restarts reached")
            self._set_start_status(False, 'LightRAG startup blocked: max restarts reached', 'max_restarts_reached')
            return False
        self.restart_count += 1
        self.last_restart_time = time.time()
        
        success = self._start_server_process(wait_gating=wait_ready)
        if success and not self._monitor_running and not self.disable_parent_monitoring:
            self._monitor_running = True
            self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
            self._monitor_thread.start()
        # Always start self-health check to detect hangs
        if success:
            self._monitor_running = True
            self._start_self_health_check()
        return success

    def stop(self, force: bool = False):
        """Stop the LightRAG server.

        Args:
            force: If True, forcefully kill the entire process group immediately.
                   This will interrupt all running LLM/embedding HTTP requests.
                   If False (default), use graceful termination.
        """
        self._monitor_running = False
        # Stop vLLM error monitor thread via Event (replaces _vllm_error_monitor_active)
        if hasattr(self, '_vllm_monitor_event') and self._vllm_monitor_event:
            self._vllm_monitor_event.clear()
        if hasattr(self, '_vllm_error_monitor_thread') and self._vllm_error_monitor_thread:
            self._vllm_error_monitor_thread.join(timeout=2)
            self._vllm_error_monitor_thread = None
        # Join self-health check thread to prevent leak on restart.
        # Without this, the old thread continues running because start()
        # immediately sets _monitor_running=True again, masking the False.
        if hasattr(self, '_self_health_check_thread') and self._self_health_check_thread:
            if self._self_health_check_thread.is_alive():
                self._self_health_check_thread.join(timeout=3)
            self._self_health_check_thread = None

        if hasattr(self, '_script_path') and self._script_path and os.path.exists(self._script_path):
            try: os.remove(self._script_path)
            except Exception as e: logger.debug(f"[LightragServer] Error removing script: {e}")
        
        if self.proc:
            try:
                # Get PID and PGID while process is still alive
                pid = self.proc.pid
                pgid = None
                if sys.platform != 'win32' and self.proc.poll() is None:
                    try:
                        pgid = os.getpgid(pid)
                        logger.info(f"[LightragServer] Process {pid} is in process group {pgid}")
                    except (ProcessLookupError, OSError) as e:
                        logger.warning(f"[LightragServer] Could not get process group: {e}")
                
                if force:
                    logger.info("[LightragServer] Force stopping server...")
                    self._kill_process_tree(pid, pgid, force=True)
                else:
                    logger.info("[LightragServer] Stopping server...")
                    # Try graceful termination first
                    if self.proc.poll() is None:
                        if sys.platform != 'win32' and pgid:
                            try:
                                os.killpg(pgid, signal.SIGTERM)
                                logger.info(f"[LightragServer] Sent SIGTERM to process group {pgid}")
                            except (ProcessLookupError, OSError) as e:
                                logger.warning(f"[LightragServer] Could not send SIGTERM to process group: {e}")
                                self.proc.terminate()
                        else:
                            self.proc.terminate()
                        
                        # Wait for graceful shutdown
                        try:
                            self.proc.wait(timeout=5)
                            logger.info("[LightragServer] Process terminated gracefully")
                        except subprocess.TimeoutExpired:
                            logger.warning("[LightragServer] Process unresponsive, force killing...")
                            self._kill_process_tree(pid, pgid, force=True)
                    
                    # Final verification: ensure all child processes are gone
                    self._verify_cleanup(pid)
                    
            except Exception as e:
                logger.error(f"[LightragServer] Error stopping process: {e}")
            finally:
                self.proc = None
            
        self._close_log_files()
        self._remove_pid_file()
        logger.info("[LightragServer] Server stopped")
    
    def _kill_process_tree(self, pid, pgid=None, force=False):
        """Kill a process and all its children recursively."""
        try:
            import psutil
            
            # Try to get the process
            try:
                parent = psutil.Process(pid)
            except psutil.NoSuchProcess:
                logger.info(f"[LightragServer] Process {pid} already terminated")
                return
            
            # Get all children recursively
            children = parent.children(recursive=True)
            logger.info(f"[LightragServer] Found {len(children)} child processes")
            
            # Terminate children first
            signal_type = signal.SIGKILL if force else signal.SIGTERM
            signal_name = "SIGKILL" if force else "SIGTERM"
            
            for child in children:
                try:
                    logger.debug(f"[LightragServer] Sending {signal_name} to child process {child.pid}")
                    child.send_signal(signal_type)
                except psutil.NoSuchProcess:
                    pass
            
            # Terminate parent
            try:
                logger.info(f"[LightragServer] Sending {signal_name} to parent process {pid}")
                parent.send_signal(signal_type)
            except psutil.NoSuchProcess:
                pass
            
            # Wait for all processes to terminate
            gone, alive = psutil.wait_procs(children + [parent], timeout=3)
            
            if alive:
                logger.warning(f"[LightragServer] {len(alive)} processes still alive after {signal_name}, force killing...")
                for p in alive:
                    try:
                        logger.debug(f"[LightragServer] Force killing process {p.pid}")
                        p.kill()
                    except psutil.NoSuchProcess:
                        pass
                
                # Final wait
                psutil.wait_procs(alive, timeout=2)
            
            logger.info(f"[LightragServer] Successfully terminated process tree (root: {pid})")
            
        except ImportError:
            # Fallback to process group kill if psutil not available
            logger.warning("[LightragServer] psutil not available, using fallback process group kill")
            if sys.platform != 'win32' and pgid:
                try:
                    os.killpg(pgid, signal.SIGKILL if force else signal.SIGTERM)
                    logger.info(f"[LightragServer] Sent {'SIGKILL' if force else 'SIGTERM'} to process group {pgid}")
                except (ProcessLookupError, OSError) as e:
                    logger.warning(f"[LightragServer] Could not kill process group: {e}")
            
            # Try to kill the main process
            try:
                if self.proc and self.proc.poll() is None:
                    if force:
                        self.proc.kill()
                    else:
                        self.proc.terminate()
                    self.proc.wait(timeout=2)
            except Exception as e:
                logger.warning(f"[LightragServer] Error in fallback kill: {e}")
    
    def _verify_cleanup(self, pid):
        """Verify that all child processes have been cleaned up."""
        try:
            import psutil
            
            # Check if any child processes are still running
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
                if children:
                    logger.warning(f"[LightragServer] {len(children)} child processes still running after cleanup:")
                    for child in children:
                        try:
                            logger.warning(f"  - PID {child.pid}: {child.name()} (status: {child.status()})")
                        except psutil.NoSuchProcess:
                            pass
            except psutil.NoSuchProcess:
                logger.info(f"[LightragServer] Process {pid} confirmed terminated")
        except ImportError:
            logger.debug("[LightragServer] psutil not available, skipping cleanup verification")
        except Exception as e:
            logger.debug(f"[LightragServer] Error verifying cleanup: {e}")

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def _monitor_parent(self):
        while self._monitor_running and self.parent_pid:
             if not self._is_process_alive(self.parent_pid):
                 logger.warning(f"[LightragServer] Parent process {self.parent_pid} died, stopping server...")
                 self.stop()
                 sys.exit(0)
             time.sleep(2)

    def _start_self_health_check(self):
        """Start background self-health check thread to detect hangs"""
        self._self_health_check_thread = threading.Thread(
            target=self._self_health_check_loop,
            name="LightragSelfHealthCheck",
            daemon=True
        )
        self._self_health_check_thread.start()
        logger.info("[LightragServer] Self-health check thread started")

    def _self_health_check_loop(self):
        """Background loop that checks if the server is responding"""
        import requests
        port = 9621
        try:
            port = int(self.extra_env.get("PORT", 9621))
        except (ValueError, TypeError):
            pass

        check_count = 0
        while getattr(self, '_monitor_running', True):
            time.sleep(self._self_health_check_interval)
            check_count += 1
            try:
                response = requests.get(
                    f"http://127.0.0.1:{port}/auth-status",
                    timeout=10
                )
                if response.status_code == 200:
                    with self._unhealthy_count_lock:
                        if self._unhealthy_count > 0:
                            prev = self._unhealthy_count
                            self._unhealthy_count = 0
                            logger.info(
                                f"[LightragServer] Self-health check recovered "
                                f"(was unhealthy {prev} times)"
                            )
                        else:
                            self._unhealthy_count = 0
                    self._last_health_check_time = time.time()
                    logger.debug(
                        f"[LightragServer] Self-health check OK "
                        f"(check #{check_count})"
                    )
                else:
                    with self._unhealthy_count_lock:
                        self._unhealthy_count += 1
                        current = self._unhealthy_count
                    logger.warning(
                        f"[LightragServer] Self-health check returned {response.status_code} "
                        f"(unhealthy count: {current}/{self._max_unhealthy})"
                    )
                    self._maybe_self_restart()
            except requests.exceptions.ConnectionError:
                with self._unhealthy_count_lock:
                    self._unhealthy_count += 1
                    current = self._unhealthy_count
                logger.warning(
                    f"[LightragServer] Self-health check connection refused "
                    f"(unhealthy count: {current}/{self._max_unhealthy})"
                )
                self._maybe_self_restart()
            except Exception as e:
                logger.debug(f"[LightragServer] Self-health check error: {e}")

    def _maybe_self_restart(self):
        """Restart server if unhealthy for too long"""
        with self._unhealthy_count_lock:
            count = self._unhealthy_count
        if count >= self._max_unhealthy:
            elapsed = time.time() - self._last_health_check_time
            logger.warning(
                f"[LightragServer] Server unhealthy for {count} checks, "
                f"last success {elapsed:.0f}s ago. Initiating self-restart..."
            )
            with self._unhealthy_count_lock:
                self._unhealthy_count = 0
            try:
                self.stop(force=True)
                # stop() now joins the old self-health check thread; give it
                # a moment for any in-flight requests.get to return.
                time.sleep(2)
                self.start(wait_ready=False)
                logger.info("[LightragServer] Self-restart completed")
            except Exception as e:
                logger.error(f"[LightragServer] Self-restart failed: {e}")
