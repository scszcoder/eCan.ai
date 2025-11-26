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
from utils.logger_helper import logger_helper as logger
from knowledge.lightrag_config_manager import get_config_manager

class LightragServer:
    def __init__(self, extra_env=None):
        self.extra_env = extra_env or {}
        if self.extra_env:
            logged_keys = sorted(str(k) for k in self.extra_env.keys())
            logger.info(f"[LightragServer] extra_env keys: {logged_keys}")
        self.proc = None
        self._stdout_log_handle = None
        self._stderr_log_handle = None
        self._pid_file_path = None
        self._atexit_registered = False
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

        # 3. Python runtime environment
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
        env['NO_COLOR'] = '1'
        env['ASCII_COLORS_DISABLE'] = '1'

        # 4. Apply extra_env overrides
        if self.extra_env:
            logger.info(f"[LightragServer] Applying {len(self.extra_env)} extra environment variables")
            for k, v in self.extra_env.items():
                env[str(k)] = str(v)
        
        self._ensure_utf8_locale(env)

        if self.is_frozen and not env.get('HOST'):
            env['HOST'] = '127.0.0.1'

        # 6. Map provider bindings to LightRAG-supported values
        # LightRAG only supports: lollms, ollama, openai, azure_openai, aws_bedrock
        # Map all other providers to OpenAI-compatible API
        
        # Provider mapping table
        LIGHTRAG_SUPPORTED = ['lollms', 'ollama', 'openai', 'azure_openai', 'aws_bedrock']
        PROVIDER_MAPPING = {
            # AWS
            'bedrock': 'aws_bedrock',
            # Chinese LLM providers (OpenAI-compatible)
            'anthropic': 'openai',
            'google': 'openai',
            'deepseek': 'openai',
            'dashscope': 'openai',
            'bytedance': 'openai',
            'baidu_qianfan': 'openai',
            # Embedding providers (OpenAI-compatible)
            'huggingface': 'openai',
            'cohere': 'openai',
            'voyageai': 'openai',
            'alibaba_qwen': 'openai',
            'doubao': 'openai',
            # Provider display names (map to their provider IDs)
            'Qwen (DashScope)': 'openai',  # alibaba_qwen
            'Baidu Qianfan': 'openai',  # baidu_qianfan
        }
        
        # Map LLM binding (case-insensitive)
        llm_binding = env.get('LLM_BINDING')
        if llm_binding and llm_binding not in LIGHTRAG_SUPPORTED:
            # Try case-insensitive matching
            mapped = None
            llm_binding_lower = llm_binding.lower()
            for key, value in PROVIDER_MAPPING.items():
                if key.lower() == llm_binding_lower:
                    mapped = value
                    break
            if mapped is None:
                mapped = 'openai'  # Default fallback
            logger.info(f"[LightragServer] Mapped LLM binding '{llm_binding}' -> '{mapped}'")
            env['LLM_BINDING'] = mapped
        
        # Map Embedding binding (case-insensitive, also supports 'jina')
        embedding_binding = env.get('EMBEDDING_BINDING')
        if embedding_binding and embedding_binding not in LIGHTRAG_SUPPORTED + ['jina']:
            # Try case-insensitive matching
            mapped = None
            embedding_binding_lower = embedding_binding.lower()
            for key, value in PROVIDER_MAPPING.items():
                if key.lower() == embedding_binding_lower:
                    mapped = value
                    break
            if mapped is None:
                mapped = 'openai'  # Default fallback
            logger.info(f"[LightragServer] Mapped Embedding binding '{embedding_binding}' -> '{mapped}'")
            env['EMBEDDING_BINDING'] = mapped
        
        # Map Rerank binding (LightRAG natively supports: cohere, jina, voyageai, siliconflow, aliyun, ollama)
        # Map all other providers to 'aliyun' (Alibaba-compatible API)
        RERANK_NATIVE_SUPPORTED = ['cohere', 'jina', 'aliyun']
        rerank_binding = env.get('RERANK_BINDING')
        if rerank_binding and rerank_binding.lower() not in ['null', 'none', '']:
            rerank_binding_lower = rerank_binding.lower()
            if rerank_binding_lower not in RERANK_NATIVE_SUPPORTED:
                # Map unsupported providers to aliyun (Alibaba-compatible)
                logger.info(f"[LightragServer] Mapped Rerank binding '{rerank_binding}' -> 'aliyun' (Alibaba-compatible API)")
                env['RERANK_BINDING'] = 'aliyun'
        
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

        self._sync_restart_settings(env)
        
        return env

    def _sync_restart_settings(self, env):
        try:
            self.max_restarts = int(env.get('MAX_RESTARTS', self.max_restarts))
            self.restart_cooldown = int(env.get('RESTART_COOLDOWN', self.restart_cooldown))
        except (ValueError, TypeError):
            pass

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

    def _create_log_files(self):
        """
        Create log file handles for LightRAG server subprocess output.
        Uses fixed filenames (lightrag_server.log) instead of timestamped files
        to avoid accumulating many log files. Implements simple log rotation
        when files exceed 10MB.
        """
        env = self.build_env()
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
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files()
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

            python_executable = self._get_virtual_env_python()
            if not self._validate_python_executable(python_executable): return False

            # Use -m module approach for both frozen and non-frozen modes
            # The environment variables are already properly configured
            
            # Use the static launcher script for SSL patching
            # This script should be distributed with the application
            launcher_path = os.path.join(os.path.dirname(__file__), "lightrag_launcher.py")
            
            if os.path.exists(launcher_path):
                cmd = [python_executable, "-u", launcher_path]
                logger.info(f"[LightragServer] Using launcher script: {launcher_path}")
            else:
                logger.warning(f"[LightragServer] Launcher not found at {launcher_path}, falling back to -m (SSL patch will NOT be applied)")
                cmd = [python_executable, "-u", "-m", "lightrag.api.lightrag_server"]

            # Log final environment variables (masked) for debugging
            try:
                debug_env = {k: self._mask_env_value(k, v) for k, v in env.items()}
                logger.info(f"[LightragServer] Process Environment:\n{json.dumps(debug_env, ensure_ascii=False, indent=2)}")
            except Exception as e:
                logger.warning(f"[LightragServer] Failed to log environment: {e}")

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
                summary.append(f"🧠 Embedding Provider: {embed_provider}")
                summary.append(f"   Embedding Model:   {embed_model}")
                if env.get('EMBEDDING_BINDING_HOST'):
                    summary.append(f"   Embedding Host:    {env.get('EMBEDDING_BINDING_HOST')}")
                if env.get('EMBEDDING_BINDING_API_KEY'):
                    summary.append(f"   Embedding Key:     {self._mask_env_value('EMBEDDING_API_KEY', env['EMBEDDING_BINDING_API_KEY'])}")

                # Rerank
                rerank_provider = env.get('RERANK_BINDING', 'null')
                rerank_model = env.get('RERANK_MODEL', '')
                rerank_enabled = env.get('RERANK_BY_DEFAULT', 'false')
                summary.append(f"🔄 Rerank Provider:    {rerank_provider}")
                summary.append(f"   Rerank Model:      {rerank_model if rerank_model else 'N/A'}")
                summary.append(f"   Enabled by Default: {rerank_enabled}")
                if env.get('RERANK_BINDING_HOST'):
                    summary.append(f"   Rerank Host:       {env.get('RERANK_BINDING_HOST')}")
                if env.get('RERANK_BINDING_API_KEY'):
                    summary.append(f"   Rerank Key:        {self._mask_env_value('RERANK_API_KEY', env['RERANK_BINDING_API_KEY'])}")

                # Storage
                summary.append("-" * 20 + " Storage " + "-" * 20)
                summary.append(f"📦 KV Storage:        {env.get('LIGHTRAG_KV_STORAGE', 'Default')}")
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
            if self.proc and self.proc.poll() is None:
                self._write_pid_file(self.proc.pid, env)
                
                if wait_gating:
                    health_timeout = float(env.get('LIGHTRAG_HEALTH_TIMEOUT', 45.0))
                    if self._wait_for_server_ready(int(env['PORT']), timeout=health_timeout):
                        return True
                    else:
                        logger.error("[LightragServer] Server failed to become ready, stopping...")
                        self._log_startup_failure()
                        self.stop()
                        return False
                
                return True
            return False
        except Exception as e:
            logger.error(f"[LightragServer] Start error: {e}")
            return False

    def _wait_for_server_ready(self, port, timeout=45.0):
        start_time = time.time()
        import requests
        
        logger.info(f"[LightragServer] Waiting for server to be ready on port {port}...")
        while time.time() - start_time < timeout:
            try:
                # Check if process is still running
                if self.proc and self.proc.poll() is not None:
                    logger.error(f"[LightragServer] Server process exited prematurely with code {self.proc.returncode}")
                    return False
                
                response = requests.get(f"http://127.0.0.1:{port}/health", timeout=1)
                if response.status_code == 200:
                    logger.info(f"[LightragServer] Server is ready on port {port}")
                    return True
            except:
                pass
            time.sleep(0.5)
        
        logger.error(f"[LightragServer] Timeout waiting for server ready on port {port}")
        return False

    def start(self, wait_ready=False):
        if self.is_running(): return True
        if time.time() - self.last_restart_time > 300: self.restart_count = 0
        if self.restart_count >= self.max_restarts:
            logger.error("[LightragServer] Max restarts reached")
            return False
        self.restart_count += 1
        self.last_restart_time = time.time()
        
        success = self._start_server_process(wait_gating=wait_ready)
        if success and not self._monitor_running and not self.disable_parent_monitoring:
            self._monitor_running = True
            self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
            self._monitor_thread.start()
        return success

    def stop(self):
        self._monitor_running = False
        if hasattr(self, '_script_path') and self._script_path and os.path.exists(self._script_path):
            try: os.remove(self._script_path)
            except Exception as e: logger.debug(f"[LightragServer] Error removing script: {e}")
        
        if self.proc:
            logger.info("[LightragServer] Stopping server...")
            try:
                if self.proc.poll() is None:
                    self.proc.terminate()
                    try: self.proc.wait(timeout=5)
                    except: 
                        logger.warning("[LightragServer] Process unresponsive, killing...")
                        self.proc.kill()
            except Exception as e:
                logger.error(f"[LightragServer] Error stopping process: {e}")
            finally: self.proc = None
            
        self._close_log_files()
        self._remove_pid_file()
        logger.info("[LightragServer] Server stopped")

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def _monitor_parent(self):
        while self._monitor_running and self.parent_pid:
             if not self._is_process_alive(self.parent_pid):
                 logger.warning(f"[LightragServer] Parent process {self.parent_pid} died, stopping server...")
                 self.stop()
                 sys.exit(0)
             time.sleep(2)
