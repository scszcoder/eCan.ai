import subprocess
import os
import sys
import signal
import json
import atexit
from pathlib import Path
import threading
import time
import locale
from utils.logger_helper import logger_helper as logger


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

        # Restart control - read configuration from environment variables
        self.restart_count = 0
        self.max_restarts = int(self.extra_env.get("MAX_RESTARTS", "3"))
        self.last_restart_time = 0
        self.restart_cooldown = int(self.extra_env.get("RESTART_COOLDOWN", "30"))  # seconds

        # Get parent process ID - handle Windows compatibility and PyInstaller
        import platform
        is_windows = platform.system().lower().startswith('win')

        # IMPORTANT: Disable parent process monitoring by default to prevent premature exit
        # The parent process check can cause false positives during application startup
        # or when the main process is busy with initialization
        # Users can explicitly enable it via ENABLE_PARENT_MONITORING=true if needed
        
        # Check if parent process monitoring should be explicitly enabled
        enable_monitoring = self.extra_env.get("ENABLE_PARENT_MONITORING", "false").lower() == "true"
        
        if enable_monitoring:
            # Only enable monitoring if explicitly requested
            if is_windows:
                try:
                    import psutil
                    self.parent_pid = psutil.Process().ppid()
                except (ImportError, AttributeError):
                    # Fallback to os.getppid() if psutil is not available
                    self.parent_pid = os.getppid()
            else:
                self.parent_pid = os.getppid()
            
            self.disable_parent_monitoring = False
            logger.info(f"[LightragServer] Parent process monitoring ENABLED (PID: {self.parent_pid})")
        else:
            # Default: disable parent monitoring to avoid false positives
            self.disable_parent_monitoring = True
            self.parent_pid = None
            logger.info("[LightragServer] Parent process monitoring DISABLED by default (use ENABLE_PARENT_MONITORING=true to enable)")

        self._monitor_running = False
        self._monitor_thread = None

        logger.info(f"[LightragServer] Parent PID: {self.parent_pid}, Monitoring disabled: {self.disable_parent_monitoring}")

        # Setup signal handlers
        self._setup_signal_handlers()

        # Automatically handle APP_DATA directory generation
        app_data_path = self.extra_env.get("APP_DATA_PATH")
        if app_data_path:
            input_dir = os.path.join(app_data_path, "inputs")
            working_dir = os.path.join(app_data_path, "rag_storage")
            log_dir = os.path.join(app_data_path, "runlogs")
            self.extra_env.setdefault("INPUT_DIR", input_dir)
            self.extra_env.setdefault("WORKING_DIR", working_dir)
            self.extra_env.setdefault("LOG_DIR", log_dir)
            logger.info(f"[LightragServer] INPUT_DIR: {input_dir}, WORKING_DIR: {working_dir}, LOG_DIR: {log_dir}")
        
        # Proxy state change callback registration (deferred to avoid blocking startup)
        self._proxy_callback_unregister = None
        self._initialized_time = time.time()  # Track initialization time
        # Register callback in background thread to avoid blocking initialization
        def _register_in_background():
            """Register proxy change callback in background to avoid blocking startup."""
            try:
                time.sleep(0.5)  # Brief delay to ensure ProxyManager is initialized and avoid race conditions
                self._register_proxy_change_callback()
            except Exception as e:
                logger.debug(f"[LightragServer] Failed to register proxy change callback in background: {e}")
        
        registration_thread = threading.Thread(
            target=_register_in_background,
            name="LightragProxyCallbackReg",
            daemon=True
        )
        registration_thread.start()

    def _setup_signal_handlers(self):
        """Setup signal handlers (only works in main thread)"""
        def signal_handler(signum, frame):
            logger.info(f"[LightragServer] Received signal {signum}, stopping server...")
            self.stop()
            if not self.is_frozen:  # Only exit in non-packaged environment
                sys.exit(0)

        try:
            # Check if we're in the main thread
            if threading.current_thread() is threading.main_thread():
                # Register signal handlers only in main thread
                signal.signal(signal.SIGTERM, signal_handler)
                signal.signal(signal.SIGINT, signal_handler)

                # macOS/Linux specific signals
                if hasattr(signal, 'SIGHUP'):
                    signal.signal(signal.SIGHUP, signal_handler)

                logger.info("[LightragServer] Signal handlers registered in main thread")
            else:
                logger.debug("[LightragServer] Skipping signal handler setup - not in main thread")
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to setup signal handlers: {e}")

    def _register_atexit_handler(self):
        if self._atexit_registered:
            return
        try:
            atexit.register(self._ensure_process_cleanup)
            self._atexit_registered = True
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to register atexit handler: {e}")

    def _ensure_process_cleanup(self):
        try:
            if self.is_running():
                logger.info("[LightragServer] Atexit cleanup triggered")
            self.stop()
        except Exception as e:
            logger.debug(f"[LightragServer] Atexit cleanup error: {e}")

    def _get_env_file_paths(self):
        """Get possible .env file paths for both development and PyInstaller environments"""
        possible_paths = []

        def add_path(path: Path):
            if path and path not in possible_paths:
                possible_paths.append(path)

        resource_env_name = "lightrag.env"
        add_path(Path.cwd() / "resource" / "data" / resource_env_name)

        if self.is_frozen:
            exe_dir = Path(sys.executable).parent
            add_path(exe_dir / "resource" / "data" / resource_env_name)
            add_path(exe_dir / ".env")
            add_path(exe_dir / "knowledge" / ".env")
            add_path(Path.cwd() / ".env")
            add_path(Path.cwd() / "knowledge" / ".env")
        else:
            script_dir = Path(__file__).parent
            project_root = script_dir.parent
            add_path(project_root / "resource" / "data" / resource_env_name)
            add_path(script_dir / ".env")
            add_path(project_root / ".env")
            add_path(project_root / "knowledge" / ".env")
            add_path(Path.cwd() / ".env")
            add_path(Path.cwd() / "knowledge" / ".env")

        return possible_paths

    def _load_env_file_content(self):
        """Load .env file content and return as dict - unified logic for all environments"""
        possible_paths = self._get_env_file_paths()
        
        # Find the first existing .env file
        env_file = None
        for env_path in possible_paths:
            if env_path.exists():
                env_file = env_path
                logger.info(f"[LightragServer] Found .env file at: {env_file}")
                break
        
        if not env_file:
            logger.warning(f"[LightragServer] .env file not found. Searched paths: {[str(p) for p in possible_paths]}")
            return {}
        
        # Load .env file content - same logic for all environments
        temp_env = {}
        try:
            logger.info(f"[LightragServer] Loading environment from {env_file}")
            with open(env_file, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        try:
                            key, value = line.split('=', 1)
                            # Remove quotes if present - unified processing
                            value = value.strip('"\'')
                            temp_env[key] = value
                            logger.debug(f"[LightragServer] Loaded {key}={value}")
                        except ValueError:
                            logger.warning(f"[LightragServer] Invalid line {line_num} in .env file: {line}")
            
            logger.info(f"[LightragServer] Loaded {len(temp_env)} variables from .env file")
            return temp_env
        except Exception as e:
            logger.error(f"[LightragServer] Error loading .env file {env_file}: {e}")
            return {}

    def build_env(self):
        # Start with current environment (includes latest proxy settings from ProxyManager)
        env = os.environ.copy()
        
        # Load .env file content
        env_file_content = self._load_env_file_content()
        if env_file_content:
            env.update(env_file_content)

        # Force fix Windows encoding issues
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output for subprocess to avoid missing logs
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'

        self._ensure_utf8_locale(env)

        env.setdefault('MAX_RESTARTS', '5')  # Increase restart attempts for network issues
        env.setdefault('RESTART_COOLDOWN', '10')  # Longer cooldown for network recovery
        env.setdefault('NO_COLOR', '1')
        env.setdefault('ASCII_COLORS_DISABLE', '1')

        # Health check parameters (configurable via environment variables)
        env.setdefault('LIGHTRAG_HEALTH_TIMEOUT', '45')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_INITIAL', '0.5')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_MAX', '1.5')  # seconds
        
        # Network timeout configurations for OpenAI API to prevent ConnectTimeout
        env.setdefault('OPENAI_TIMEOUT', '300')  # 5 minutes total timeout
        env.setdefault('OPENAI_CONNECT_TIMEOUT', '60')  # 1 minute connection timeout
        env.setdefault('OPENAI_READ_TIMEOUT', '240')  # 4 minutes read timeout
        env.setdefault('HTTPX_TIMEOUT', '300')  # HTTP client timeout

        # Apply extra_env (from parent process) - these take priority over .env file
        if self.extra_env:
            logger.info(f"[LightragServer] Applying {len(self.extra_env)} extra environment variables")
            for k, v in self.extra_env.items():
                env[str(k)] = str(v)
                logger.debug(f"[LightragServer] Extra env: {k}={self._mask_env_value(k, v)}")

        # Apply environment-specific optimizations - unified approach
        self._apply_environment_optimizations(env)

        # Log proxy settings for debugging (inherited from parent process)
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy']
        proxy_settings = {k: v for k, v in env.items() if k in proxy_vars}
        if proxy_settings:
            logger.info(f"[LightragServer] 🌐 Proxy settings inherited from parent process:")
            for k, v in proxy_settings.items():
                # Mask proxy URL for security (show only host:port)
                if v and '://' in v:
                    logger.info(f"[LightragServer]   {k}={v}")
                else:
                    logger.info(f"[LightragServer]   {k}={v}")
        else:
            logger.info("[LightragServer] 🌐 No proxy settings detected")

        # Set path-related environment variables
        if 'APP_DATA_PATH' in env:
            app_data_path = env['APP_DATA_PATH']
            env.setdefault('INPUT_DIR', os.path.join(app_data_path, 'inputs'))
            env.setdefault('WORKING_DIR', os.path.join(app_data_path, 'rag_storage'))
            env.setdefault('LOG_DIR', os.path.join(app_data_path, 'runlogs'))

        # Prefer secure_store for API keys with user isolation; fallback to env and finally .env
        openai_api_key = None
        try:
            from utils.env.secure_store import secure_store, get_current_username
            # Get current username for user isolation
            username = get_current_username()
            openai_api_key = secure_store.get('OPENAI_API_KEY', username=username)
        except Exception:
            openai_api_key = None

        if not openai_api_key:
            openai_api_key = env.get('OPENAI_API_KEY')

        if openai_api_key and str(openai_api_key).strip():
            masked_key = openai_api_key[:8] + "..." + openai_api_key[-4:] if len(openai_api_key) > 12 else "***"
            env['LLM_BINDING_API_KEY'] = str(openai_api_key)
            env['EMBEDDING_BINDING_API_KEY'] = str(openai_api_key)
            logger.info(f"[LightragServer] ✅ LLM/EMBEDDING keys set (source: {'secure_store' if 'secure_store' in globals() else 'env'}) {masked_key}")
        else:
            logger.warning("[LightragServer] ⚠️ No OPENAI_API_KEY found in secure_store or env; will rely on .env file values if present.")
        
        # Log critical timeout settings for debugging
        critical_vars = ['EMBEDDING_TIMEOUT', 'LLM_TIMEOUT', 'EMBEDDING_FUNC_MAX_ASYNC', 
                        'OPENAI_TIMEOUT', 'OPENAI_CONNECT_TIMEOUT', 'OPENAI_READ_TIMEOUT']
        logger.info("[LightragServer] 🔧 Critical timeout settings:")
        for critical_var in critical_vars:
            value = env.get(critical_var, 'NOT_SET')
            logger.info(f"[LightragServer]   {critical_var}: {value}")

        self._sync_restart_settings(env)

        return env

    def _sync_restart_settings(self, env):
        """Synchronize restart settings from environment"""

        def _read_int(key, current_value, minimum=0):
            raw_value = env.get(key)
            if raw_value is None:
                return current_value
            try:
                parsed = int(raw_value)
                if parsed < minimum:
                    logger.warning(f"[LightragServer] {key} ({parsed}) below minimum {minimum}, using minimum")
                    return minimum
                return parsed
            except (TypeError, ValueError):
                logger.warning(f"[LightragServer] {key} has invalid value {raw_value}, keeping {current_value}")
                return current_value

        new_max_restarts = _read_int('MAX_RESTARTS', self.max_restarts)
        new_cooldown = _read_int('RESTART_COOLDOWN', self.restart_cooldown)

        if new_max_restarts != self.max_restarts:
            logger.info(f"[LightragServer] MAX_RESTARTS updated to {new_max_restarts}")
        if new_cooldown != self.restart_cooldown:
            logger.info(f"[LightragServer] RESTART_COOLDOWN updated to {new_cooldown}")

        self.max_restarts = new_max_restarts
        self.restart_cooldown = new_cooldown

    def _ensure_utf8_locale(self, env):
        """Ensure UTF-8 locale if available without forcing missing locales"""
        target_locale = 'en_US.UTF-8'
        if env.get('LANG') or env.get('LC_ALL'):
            return

        if self._locale_available(target_locale):
            env.setdefault('LANG', target_locale)
            env.setdefault('LC_ALL', target_locale)
            logger.debug(f"[LightragServer] Locale set to {target_locale}")
        else:
            logger.warning(f"[LightragServer] Locale {target_locale} not available, skipping locale override")

    @staticmethod
    def _locale_available(locale_name: str) -> bool:
        """Check whether a locale can be set on this system"""
        try:
            current_locale = locale.setlocale(locale.LC_ALL)
        except locale.Error:
            current_locale = None

        try:
            locale.setlocale(locale.LC_ALL, locale_name)
            return True
        except locale.Error:
            return False
        finally:
            if current_locale:
                try:
                    locale.setlocale(locale.LC_ALL, current_locale)
                except locale.Error:
                    pass

    @staticmethod
    def _mask_env_value(key: str, value: str) -> str:
        """Mask sensitive environment values when logging"""
        if value is None:
            return "<None>"

        sensitive_markers = ["KEY", "TOKEN", "SECRET", "PASSWORD"]
        upper_key = str(key).upper()
        if any(marker in upper_key for marker in sensitive_markers):
            text = str(value)
            if len(text) <= 8:
                return "***"
            return f"{text[:4]}...{text[-4:]}"

        return str(value)

    def _apply_environment_optimizations(self, env):
        """Apply environment-specific optimizations - unified logic with different defaults"""
        # Set default values based on environment
        default_values = self._get_environment_defaults()
        
        for key, default_value in default_values.items():
            if not env.get(key):
                env[key] = default_value
                logger.info(f"[LightragServer] Set {('PyInstaller' if self.is_frozen else 'development')} default: {key}={default_value}")
        
        # Clean Python environment variables for PyInstaller (doesn't affect development)
        if self.is_frozen:
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            logger.info("[LightragServer] Cleaned Python environment variables for packaged environment")

    def _get_environment_defaults(self):
        """Get environment-specific default values - only for values not in .env file"""
        base_defaults = {}
        
        # Set common defaults for both environments
        base_defaults['EMBEDDING_TIMEOUT'] = '120'
        base_defaults['EMBEDDING_FUNC_MAX_ASYNC'] = '2'
        base_defaults['LLM_TIMEOUT'] = '300'
        
        # Only set defaults for values that are truly environment-specific
        # and not already configured in .env file
        if self.is_frozen:
            # PyInstaller-specific: prefer localhost to avoid network issues
            # Only override if HOST is not already set
            if not os.environ.get('HOST'):
                base_defaults['HOST'] = '127.0.0.1'
        
        return base_defaults

    def _validate_critical_env_vars(self, env):
        """Validate that critical environment variables are properly set"""
        critical_issues = []
        
        # Check OPENAI_API_KEY
        if not env.get('OPENAI_API_KEY'):
            critical_issues.append("OPENAI_API_KEY is missing")
        
        # Check timeout settings (optional, with defaults)
        embedding_timeout = env.get('EMBEDDING_TIMEOUT')
        if embedding_timeout:
            try:
                timeout_val = int(embedding_timeout)
                if timeout_val < 30:
                    logger.warning(f"[LightragServer] EMBEDDING_TIMEOUT ({timeout_val}s) is low, recommend >= 60s")
            except ValueError:
                critical_issues.append(f"EMBEDDING_TIMEOUT ({embedding_timeout}) is not a valid number")
        else:
            # Set default value
            env['EMBEDDING_TIMEOUT'] = '120'
            logger.info("[LightragServer] EMBEDDING_TIMEOUT not set, using default: 120s")
        
        # Check concurrency settings (optional, with defaults)
        max_async = env.get('EMBEDDING_FUNC_MAX_ASYNC')
        if max_async:
            try:
                async_val = int(max_async)
                if async_val > 5:
                    logger.warning(f"[LightragServer] EMBEDDING_FUNC_MAX_ASYNC ({async_val}) is high, recommend <= 2")
            except ValueError:
                critical_issues.append(f"EMBEDDING_FUNC_MAX_ASYNC ({max_async}) is not a valid number")
        else:
            # Set default value
            env['EMBEDDING_FUNC_MAX_ASYNC'] = '2'
            logger.info("[LightragServer] EMBEDDING_FUNC_MAX_ASYNC not set, using default: 2")
        
        if critical_issues:
            logger.warning("[LightragServer] ⚠️ Critical environment variable issues:")
            for issue in critical_issues:
                logger.warning(f"[LightragServer]   - {issue}")
        else:
            logger.info("[LightragServer] ✅ All critical environment variables are properly configured")
        
        return len(critical_issues) == 0

    def _get_virtual_env_python(self):
        """Get Python interpreter path in virtual environment"""
        # Use unified VenvHelper to find Python interpreter
        # This handles all cases: packaged environment, virtual environment, and development
        from utils.venv_helper import VenvHelper
        from pathlib import Path
        
        # Get project root
        project_root = Path(__file__).parent.parent
        
        # Use VenvHelper to intelligently find Python interpreter
        # On Windows, prefer pythonw.exe to avoid console window
        python_exe = VenvHelper.find_python_interpreter(
            project_root=project_root,
            prefer_pythonw=True
        )
        
        logger.info(f"[LightragServer] Using Python interpreter: {python_exe}")
        return str(python_exe)

    def _validate_python_executable(self, python_path):
        """Validate if Python interpreter is available"""
        try:
            # In packaged environment, validate if exe file exists and is executable
            if self.is_frozen:
                if os.path.exists(python_path) and os.access(python_path, os.X_OK):
                    logger.info(f"[LightragServer] PyInstaller executable validation successful: {python_path}")
                    return True
                else:
                    logger.error(f"[LightragServer] PyInstaller executable not found or not executable: {python_path}")
                    return False

            # In non-packaged environment, just check if Python executable exists and is executable
            # Skip subprocess call to avoid window flash - we trust sys.executable
            if os.path.isfile(python_path) and os.access(python_path, os.X_OK):
                logger.info(f"[LightragServer] Python validation successful: {python_path}")
                return True
            else:
                logger.error(f"[LightragServer] Python executable not found or not executable: {python_path}")
                return False
        except subprocess.TimeoutExpired:
            logger.error(f"[LightragServer] Python validation timed out: {python_path}")
            return False
        except FileNotFoundError:
            logger.error(f"[LightragServer] Python executable not found: {python_path}")
            return False
        except Exception as e:
            logger.error(f"[LightragServer] Python validation error: {e}")
            return False

    def _create_simple_lightrag_script(self):
        """Create simple LightRAG startup script - unified approach for environment setup"""
        try:
            import tempfile
            import textwrap

            # Create simple startup script without persisting environment secrets
            script_content = textwrap.dedent(
                """
                #!/usr/bin/env python3
                # -*- coding: utf-8 -*-
                #
                # LightRAG Simple Startup Script
                # Utilize existing protection mechanism in main.py; do not import main program module.

                import sys
                import os
                import io

                # Force UTF-8 encoding to avoid UnicodeEncodeError from Windows GBK console encoding
                os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
                os.environ.setdefault('PYTHONUTF8', '1')
                # Most coloring libraries support NO_COLOR to disable colored output, minimize non-ASCII characters
                os.environ.setdefault('NO_COLOR', '1')

                try:
                    if hasattr(sys.stdout, 'reconfigure'):
                        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
                    else:
                        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
                        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
                except Exception:
                    pass

                def setup_lightrag_environment():
                    # Configure runtime environment based on inherited variables
                    print("Setting up LightRAG environment variables...")
                    _log_environment_status()
                    sys.argv = ["lightrag_server"]
                    print("LightRAG Environment Setup Complete")

                def _log_environment_status():
                    # Log key environment settings for quick diagnosis
                    critical_vars = ['EMBEDDING_TIMEOUT', 'LLM_TIMEOUT', 'EMBEDDING_FUNC_MAX_ASYNC', 'LOG_LEVEL']
                    print("Critical timeout settings:")
                    for critical_var in critical_vars:
                        value = os.environ.get(critical_var, 'NOT_SET')
                        print(f"  {critical_var}: {value}")

                    has_openai = bool(os.environ.get('OPENAI_API_KEY'))
                    has_llm = bool(os.environ.get('LLM_BINDING_API_KEY'))
                    has_embed = bool(os.environ.get('EMBEDDING_BINDING_API_KEY'))
                    print(f"API Keys: OPENAI={'✓' if has_openai else '✗'}, LLM={'✓' if has_llm else '✗'}, EMBED={'✓' if has_embed else '✗'}")

                    log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
                    if log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
                        import logging
                        lightrag_logger = logging.getLogger('lightrag')
                        level = getattr(logging, log_level)
                        lightrag_logger.setLevel(level)
                        print(f"LightRAG log level set to: {log_level}")
                    else:
                        print(f"Invalid LOG_LEVEL: {log_level}, using default")

                def main():
                    # Entrypoint for LightRAG when launched via packaged worker
                    try:
                        print("=" * 50)
                        print("LightRAG Server Starting...")
                        print("=" * 50)

                        setup_lightrag_environment()

                        try:
                            import lightrag
                            print(f"LightRAG version: {getattr(lightrag, '__version__', 'unknown')}")
                        except ImportError as e:
                            print(f"LightRAG not available: {e}")
                            print("Exiting gracefully...")
                            return 0

                        from lightrag.api.lightrag_server import main as lightrag_main
                        print("Starting LightRAG API server...")

                        log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
                        if log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
                            sys.argv = ["lightrag_server", "--log-level", log_level.lower()]
                            print(f"LightRAG will start with log level: {log_level}")

                        lightrag_main()

                    except KeyboardInterrupt:
                        print("LightRAG server interrupted")
                        return 0
                    except Exception as e:
                        print(f"LightRAG server error: {e}")
                        import traceback
                        traceback.print_exc()
                        return 1

                if __name__ == '__main__':
                    sys.exit(main())
                """
            ).lstrip()

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                script_path = f.name

            logger.info(f"[LightragServer] Created simple startup script: {script_path}")
            return script_path

        except Exception as e:
            logger.error(f"[LightragServer] Failed to create simple startup script: {e}")
            return None

    def _try_alternative_port(self, original_port):
        """Try to use alternative port
        
        For standard port 9621, will wait briefly before trying alternatives
        to give the previous process time to release the port.
        """
        try:
            import socket

            # Try port range 9621-9630
            for port in range(original_port, original_port + 10):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', port))
                sock.close()

                if result != 0:
                    # Found available port
                    if port == original_port:
                        logger.info(f"[LightragServer] Standard port {port} is available")
                    else:
                        logger.info(f"[LightragServer] Found alternative port {port}")
                    self.extra_env["PORT"] = str(port)
                    return True
                elif port == original_port and original_port == 9621:
                    # Standard port 9621 is in use, retry multiple times with progressive delays
                    # This gives the previous process more time to release the port
                    logger.info(f"[LightragServer] Standard port {original_port} is in use, will retry with progressive delays...")
                    
                    # Progressive retry: 1s, 2s, 3s (total 6s additional wait)
                    retry_delays = [1.0, 2.0, 3.0]
                    for retry_num, delay in enumerate(retry_delays, 1):
                        logger.debug(f"[LightragServer] Retry {retry_num}/{len(retry_delays)}: waiting {delay}s...")
                        time.sleep(delay)
                        
                        sock_retry = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        sock_retry.settimeout(1)
                        result_retry = sock_retry.connect_ex(('localhost', original_port))
                        sock_retry.close()
                        
                        if result_retry != 0:
                            logger.info(f"[LightragServer] ✅ Standard port {original_port} is now available after {retry_num} retries")
                            self.extra_env["PORT"] = str(original_port)
                            return True
                    
                    logger.warning(f"[LightragServer] ⚠️  Standard port {original_port} still in use after {len(retry_delays)} retries, trying alternatives...")

            logger.error(f"[LightragServer] No available ports found in range {original_port}-{original_port + 9}")
            return False

        except Exception as e:
            logger.warning(f"[LightragServer] Error trying alternative ports: {e}")
            return False

    def _wait_for_port_release(self, port: int, timeout: float = 10.0) -> bool:
        """Wait until the specified port becomes available.

        Returns True if the port is free before timeout, False otherwise.
        """
        try:
            import socket
            deadline = time.time() + timeout
            while time.time() < deadline:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1)
                    result = sock.connect_ex(('localhost', port))
                if result != 0:
                    return True
                time.sleep(0.2)
        except Exception as e:
            logger.debug(f"[LightragServer] Port release wait error for {port}: {e}")
            return False

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
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to ensure pid directory {log_dir}: {e}")
            log_dir = str(Path.cwd())
        pid_path = os.path.join(log_dir, 'lightrag_server.pid')
        self._pid_file_path = pid_path
        return pid_path

    def _read_pid_file(self, env=None):
        try:
            pid_file = self._get_pid_file_path(env)
            if not os.path.exists(pid_file):
                return None
            with open(pid_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to read pid file: {e}")
            return None

    def _write_pid_file(self, pid, env):
        try:
            pid_file = self._get_pid_file_path(env)
            start_time = self._get_process_start_time(pid)
            with open(pid_file, 'w', encoding='utf-8') as f:
                json.dump({'pid': pid, 'start_time': start_time}, f)
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to write pid file: {e}")

    def _remove_pid_file(self):
        try:
            pid_file = self._pid_file_path
            if pid_file and os.path.exists(pid_file):
                os.remove(pid_file)
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to remove pid file: {e}")

    @staticmethod
    def _get_process_start_time(pid):
        try:
            import psutil, datetime
            p = psutil.Process(int(pid))
            ts = p.create_time()
            # Format similar to `ps -o lstart` (ctime-like)
            return time.strftime('%a %b %d %H:%M:%S %Y', time.localtime(ts))
        except Exception:
            return ''

    @staticmethod
    def _is_process_alive(pid):
        try:
            import psutil
            return psutil.pid_exists(int(pid))
        except Exception:
            # Fallback: best-effort without spawning subprocesses
            try:
                os.kill(int(pid), 0)
                return True
            except ProcessLookupError:
                return False
            except PermissionError:
                return True
            except Exception:
                return False

    def _terminate_pid(self, pid, force=False):
        signal_to_send = signal.SIGKILL if force else signal.SIGTERM
        try:
            if hasattr(os, 'killpg'):
                try:
                    os.killpg(os.getpgid(pid), signal_to_send)
                    return
                except ProcessLookupError:
                    return
                except Exception:
                    pass
            os.kill(pid, signal_to_send)
        except ProcessLookupError:
            return
        except Exception as e:
            logger.debug(f"[LightragServer] Failed to send signal {signal_to_send} to pid {pid}: {e}")

    def _wait_for_process_termination(self, pid, timeout=10.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._is_process_alive(pid):
                return True
            time.sleep(0.2)
        return not self._is_process_alive(pid)

    def _cleanup_stale_process(self, env, port):
        pid_info = self._read_pid_file(env)
        if not pid_info:
            return

        pid = pid_info.get('pid')
        if not pid:
            self._remove_pid_file()
            return

        if not isinstance(pid, int):
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                self._remove_pid_file()
                return

        if not self._is_process_alive(pid):
            self._remove_pid_file()
            return

        recorded_start = pid_info.get('start_time', '')
        current_start = self._get_process_start_time(pid)
        if recorded_start and current_start and recorded_start.strip() != current_start.strip():
            logger.info(f"[LightragServer] PID file references different process (pid={pid}), skipping termination")
            self._remove_pid_file()
            return

        logger.warning(f"[LightragServer] Detected stale LightRAG subprocess (pid={pid}), attempting to terminate")
        self._terminate_pid(pid, force=False)
        if not self._wait_for_process_termination(pid, timeout=10.0):
            logger.warning(f"[LightragServer] Stale subprocess {pid} still running, force killing")
            self._terminate_pid(pid, force=True)
            self._wait_for_process_termination(pid, timeout=5.0)

        self._wait_for_port_release(port, timeout=5.0)
        self._remove_pid_file()

    def _monitor_parent(self):
        import platform
        is_windows = platform.system().lower().startswith('win')

        # Try to import psutil for Windows process monitoring
        psutil_available = False
        if is_windows:
            try:
                import psutil
                psutil_available = True
            except ImportError:
                logger.warning("psutil not available, parent process monitoring may not work properly on Windows")
            except Exception as e:
                logger.warning(f"psutil import error: {e}, falling back to basic monitoring")

        # Add failure counter to avoid exit due to occasional check failures
        failure_count = 0
        max_failures = 3  # Exit only after 3 consecutive failures

        logger.info(f"[LightragServer] Starting parent process monitoring for PID {self.parent_pid}")

        while self._monitor_running:
            try:
                if self.parent_pid is None:
                    # If no parent process PID, skip check
                    time.sleep(5)
                    continue

                if is_windows and psutil_available:
                    # On Windows, use psutil to check if parent process exists
                    try:
                        parent_process = psutil.Process(self.parent_pid)
                        # Check if process is still running
                        if not parent_process.is_running():
                            failure_count += 1
                            logger.warning(f"Parent process check failed ({failure_count}/{max_failures})")
                            if failure_count >= max_failures:
                                logger.error("Parent process is gone, exiting lightrag server...")
                                os._exit(1)
                        else:
                            failure_count = 0  # Reset failure count
                    except psutil.NoSuchProcess:
                        failure_count += 1
                        logger.warning(f"Parent process not found ({failure_count}/{max_failures})")
                        if failure_count >= max_failures:
                            logger.error("Parent process is gone, exiting lightrag server...")
                            os._exit(1)
                else:
                    # On Unix-like systems or Windows without psutil, use os.kill
                    # Note: This may not work reliably on Windows
                    try:
                        os.kill(self.parent_pid, 0)
                        failure_count = 0  # Reset failure count
                    except (OSError, ProcessLookupError):
                        failure_count += 1
                        logger.warning(f"Parent process check failed ({failure_count}/{max_failures})")
                        if failure_count >= max_failures:
                            logger.error("Parent process is gone, exiting lightrag server...")
                            os._exit(1)

            except Exception as e:
                failure_count += 1
                logger.warning(f"Parent process monitoring error: {e} ({failure_count}/{max_failures})")
                if failure_count >= max_failures:
                    logger.error("Too many parent process monitoring errors, exiting lightrag server...")
                    os._exit(1)

            time.sleep(5)  # Increase check interval to 5 seconds

    def _monitor_server_process(self):
        """Monitor server process with automatic restart support"""
        while self._monitor_running:
            try:
                if self.proc is None:
                    time.sleep(5)
                    continue

                # Check if process is still running
                if self.proc.poll() is not None:
                    # Process has exited
                    return_code = self.proc.returncode
                    logger.warning(f"[LightragServer] Server process exited with code {return_code}")

                    # Check if restart is needed
                    current_time = time.time()
                    if (current_time - self.last_restart_time) > self.restart_cooldown:
                        self.restart_count = 0  # Reset restart count

                    if self.restart_count < self.max_restarts:
                        self.restart_count += 1
                        self.last_restart_time = current_time
                        logger.info(f"[LightragServer] Attempting restart {self.restart_count}/{self.max_restarts}")

                        # Wait before restart
                        time.sleep(5)
                        if self._start_server_process():
                            continue

                    logger.error(f"[LightragServer] Max restarts ({self.max_restarts}) reached, giving up")
                    break

                time.sleep(5)  # Check every 5 seconds

            except Exception as e:
                logger.error(f"[LightragServer] Process monitor error: {e}")
                time.sleep(5)

    def _create_log_files(self):
        """Create log files"""
        log_dir = self.extra_env.get("LOG_DIR", ".")
        os.makedirs(log_dir, exist_ok=True)

        stdout_log_path = os.path.join(log_dir, "lightrag_server_stdout.log")
        stderr_log_path = os.path.join(log_dir, "lightrag_server_stderr.log")

        stdout_log = open(stdout_log_path, "a", encoding="utf-8")
        stderr_log = open(stderr_log_path, "a", encoding="utf-8")

        return stdout_log, stderr_log, stdout_log_path, stderr_log_path

    def _close_log_files(self):
        """Close log file handles if they are open"""
        for attr in ('_stdout_log_handle', '_stderr_log_handle'):
            handle = getattr(self, attr, None)
            if handle:
                try:
                    handle.close()
                except Exception:
                    pass
                finally:
                    setattr(self, attr, None)

    def _start_server_process(self, wait_gating: bool = False):
        """Start server process
        
        Args:
            wait_gating: Whether to wait for health check to pass in foreground (blocking). Default False non-blocking.
        """
        try:
            env = self.build_env()
            
            # Validate critical environment variables
            if not self._validate_critical_env_vars(env):
                logger.error("[LightragServer] Critical environment variables validation failed")
                # Continue anyway, but with warnings
            
            self._close_log_files()
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files()
            self._stdout_log_handle = stdout_log
            self._stderr_log_handle = stderr_log
            log_handles_active = True

            # Check and determine final port (based on env, find available port if necessary), keep env and extra_env consistent
            try:
                desired_port = int(env.get("PORT", "9621"))
            except (ValueError, TypeError):
                desired_port = 9621
                logger.warning("[LightragServer] Invalid PORT in env, falling back to 9621")

            self._cleanup_stale_process(env, desired_port)

            if not self._try_alternative_port(desired_port):
                logger.error("[LightragServer] No available port found, cannot start server")
                return False

            # _try_alternative_port writes selected port back to self.extra_env['PORT'], sync to env here to ensure subprocess reads consistently
            env["PORT"] = str(self.extra_env.get("PORT", desired_port))

            # Try to find Python interpreter in virtual environment
            python_executable = self._get_virtual_env_python()

            # Validate if Python interpreter is available
            if not self._validate_python_executable(python_executable):
                logger.error(f"[LightragServer] Python executable validation failed: {python_executable}")
                if self.is_frozen:
                    logger.warning("[LightragServer] In packaged environment, LightRAG server will be disabled")
                    logger.warning("[LightragServer] This is normal if lightrag is not packaged with the application")
                    return False
                else:
                    logger.error("[LightragServer] Cannot start server without valid Python interpreter")
                    return False

            # In packaged environment, check if lightrag module is available
            if self.is_frozen:
                try:
                    import lightrag
                    logger.info("[LightragServer] lightrag module is available in packaged environment")
                    
                    # Log environment status for PyInstaller debugging
                    logger.info("[LightragServer] PyInstaller environment status:")
                    logger.info(f"[LightragServer]   sys.executable: {sys.executable}")
                    logger.info(f"[LightragServer]   sys.frozen: {getattr(sys, 'frozen', False)}")
                    logger.info(f"[LightragServer]   _MEIPASS: {getattr(sys, '_MEIPASS', 'Not found')}")
                    
                except ImportError as e:
                    logger.warning(f"[LightragServer] lightrag module not available in packaged environment: {e}")
                    logger.warning("[LightragServer] LightRAG server will be disabled")
                    return False

            import platform

            # Build start command - unified approach for both environments
            if self.is_frozen:
                # PyInstaller environment: use the existing protection mechanism in main.py
                logger.info("[LightragServer] Using main.py protection mechanism for packaged environment")

                # Create a simple startup script to import and run LightRAG
                script_path = self._create_simple_lightrag_script()
                if not script_path:
                    logger.error("[LightragServer] Failed to create startup script")
                    return False

                # Save the script path so it can be cleaned up when stopping
                self._script_path = script_path

                # Use environment variable to deliver script path to main.exe (worker mode)
                env['ECAN_RUN_SCRIPT'] = script_path
                env['ECAN_BYPASS_SINGLE_INSTANCE'] = '1'
                cmd = [python_executable]
                logger.info(f"[LightragServer] PyInstaller command: {cmd} with ECAN_RUN_SCRIPT={script_path}")
            else:
                # Development environment: direct module execution with log level
                cmd = [python_executable, "-u", "-m", "lightrag.api.lightrag_server"]
                
                # Add log level parameter if specified in .env
                log_level = env.get('LOG_LEVEL', 'INFO').upper()
                if log_level in ['DEBUG', 'INFO', 'WARNING', 'ERROR']:
                    cmd.extend(["--log-level", log_level])
                    logger.info(f"[LightragServer] Adding log level parameter: --log-level {log_level}")
                
                logger.info(f"[LightragServer] Development command: {' '.join(cmd)}")
            
            # Both environments use the same subprocess.Popen parameters

            if platform.system().lower().startswith('win'):
                # Hide console window in production by default; enable via env for debugging
                show_console = os.getenv("ECAN_CHILD_SHOW_CONSOLE") == "1"
                creation_flags = 0
                
                # Always create new process group for better process management
                if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                    creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
                
                # Hide console window in production (PyInstaller environment)
                if not show_console:
                    if hasattr(subprocess, 'CREATE_NO_WINDOW'):
                        creation_flags |= subprocess.CREATE_NO_WINDOW
                    # Additional flag to ensure window is hidden
                    if hasattr(subprocess, 'STARTF_USESHOWWINDOW'):
                        startupinfo = subprocess.STARTUPINFO()
                        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                        startupinfo.wShowWindow = 0  # SW_HIDE
                    else:
                        startupinfo = None
                else:
                    startupinfo = None

                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=creation_flags,
                    startupinfo=startupinfo
                )
                try:
                    self.proc.stdin.write("yes\n")
                    self.proc.stdin.flush()
                except Exception as e:
                    logger.error(f"[LightragServer] Failed to write to stdin: {e}")
            else:
                # Unix-like systems
                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )
                try:
                    if self.proc.stdin:
                        self.proc.stdin.write("yes\n")
                        self.proc.stdin.flush()
                except Exception as e:
                    logger.error(f"[LightragServer] Failed to write to stdin: {e}")

            final_host = env.get("HOST", "127.0.0.1")
            final_port = env.get("PORT", "9621")

            # Ensure the port is a valid number
            try:
                final_port = str(int(final_port))
            except (ValueError, TypeError):
                final_port = "9621"
                logger.warning(f"[LightragServer] Invalid port, using default: 9621")

            logger.info(f"[LightragServer] Logs: {stdout_log_path}, {stderr_log_path}")

            if wait_gating:
                # Health-check gating to confirm the server is actually listening (parameterized + exponential backoff)
                try:
                    import httpx
                    health_host = '127.0.0.1' if str(final_host) in ('0.0.0.0', '::', '') else str(final_host)
                    hc_url = f"http://{health_host}:{final_port}/healthz"
                    total_timeout = float(env.get('LIGHTRAG_HEALTH_TIMEOUT', '45'))
                    interval = float(env.get('LIGHTRAG_HEALTH_INTERVAL_INITIAL', '0.5'))
                    max_interval = float(env.get('LIGHTRAG_HEALTH_INTERVAL_MAX', '1.5'))
                    deadline = time.time() + total_timeout
                    last_err = None
                    # Quickly detect if the process exited immediately to surface logs early
                    time.sleep(0.2)
                    if self.proc and self.proc.poll() is not None:
                        logger.error(f"[LightragServer] Server process exited immediately with code {self.proc.returncode}")
                        _stderr_tail = _safe_tail(stderr_log_path)
                        _stdout_tail = _safe_tail(stdout_log_path)
                        if _stderr_tail:
                            logger.error(f"[LightragServer] stderr tail:\n{_stderr_tail}")
                        if _stdout_tail:
                            logger.error(f"[LightragServer] stdout tail:\n{_stdout_tail}")
                        return False

                    while time.time() < deadline:
                        try:
                            r = httpx.get(hc_url, timeout=2.0)
                            if r.status_code < 500:
                                logger.info(f"[LightragServer] Server started at http://{final_host}:{final_port}")
                                logger.info(f"[LightragServer] WebUI: http://{final_host}:{final_port}/webui")
                                self._write_pid_file(self.proc.pid, env)
                                log_handles_active = False
                                return True
                        except Exception as e:
                            last_err = e
                        time.sleep(interval)
                        interval = min(max_interval, interval * 1.2)
                    logger.error(f"[LightragServer] Health check failed for {hc_url}: {last_err}")
                    # Try to surface last few stderr/stdout lines to parent log for quick diagnosis
                    _stderr_tail = _safe_tail(stderr_log_path)
                    _stdout_tail = _safe_tail(stdout_log_path)
                    if _stderr_tail:
                        logger.error(f"[LightragServer] stderr tail:\n{_stderr_tail}")
                    if _stdout_tail:
                        logger.error(f"[LightragServer] stdout tail:\n{_stdout_tail}")
                except Exception as e:
                    logger.error(f"[LightragServer] Health check gating error: {e}")

                return False
            else:
                # Non-blocking mode: return immediately; health check should be handled by the monitor thread or via logs
                logger.info(f"[LightragServer] Started (non-blocking) at http://{final_host}:{final_port}, skipping health-gating")
                log_handles_active = False
                self._write_pid_file(self.proc.pid, env)
                return True

        except Exception as e:
            logger.error(f"[LightragServer] Failed to start server: {e}")
            return False
        finally:
            if locals().get('log_handles_active'):
                self._close_log_files()

    def start(self, wait_ready: bool = False):
        """Start the server
        
        Args:
            wait_ready: Whether to block until health check passes
        """
        if self.proc is not None and self.proc.poll() is None:
            logger.warning("[LightragServer] Server is already running")
            return self.proc

        logger.info("[LightragServer] Starting LightRAG server...")

        # Start server process
        if not self._start_server_process(wait_gating=wait_ready):
            return None

        # Any monitoring requires the running flag
        self._monitor_running = True

        # Start parent process monitor thread
        if not self.disable_parent_monitoring and self.parent_pid is not None:
            self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
            self._monitor_thread.start()
            logger.info(f"[LightragServer] Parent process monitoring enabled for PID {self.parent_pid}")
        else:
            logger.info(f"[LightragServer] Parent process monitoring disabled (disabled={self.disable_parent_monitoring}, pid={self.parent_pid})")

        # Start process monitor thread (for auto-restart)
        if self.max_restarts > 0:
            self._proc_monitor_thread = threading.Thread(target=self._monitor_server_process, daemon=True)
            self._proc_monitor_thread.start()
            logger.info("[LightragServer] Process monitoring enabled for auto-restart")

        return self.proc

    def _register_proxy_change_callback(self):
        """Register callback for proxy state changes."""
        try:
            from agent.ec_skills.system_proxy import get_proxy_manager
            
            proxy_manager = get_proxy_manager()
            if proxy_manager is None:
                logger.debug("[LightragServer] Proxy manager not available, skipping proxy change callback registration")
                return
            
            def on_proxy_state_change(proxies):
                """Handle proxy state change notification (called from background thread - non-blocking)."""
                try:
                    # Ignore callback if called too soon after initialization (avoid restart during startup)
                    if time.time() - self._initialized_time < 2.0:
                        logger.debug("[LightragServer] Ignoring proxy state change during initialization phase")
                        return
                    
                    if proxies is None:
                        logger.info("[LightragServer] 🌐 Proxy state changed: Proxy is now unavailable")
                    else:
                        proxy_info = f"HTTP: {proxies.get('http://', 'N/A')}, HTTPS: {proxies.get('https://', 'N/A')}"
                        logger.info(f"[LightragServer] 🌐 Proxy state changed: Proxy is now available - {proxy_info}")
                    
                    # If subprocess is running, restart it to pick up new proxy settings
                    # This is necessary because subprocess environment variables are set at startup
                    if self.is_running():
                        logger.info("[LightragServer] 🔄 Restarting subprocess to apply new proxy settings...")
                        
                        def _do_restart():
                            """Perform restart in a separate thread to avoid blocking."""
                            try:
                                logger.info("[LightragServer] 🔄 Stopping subprocess...")
                                try:
                                    current_port = int(self.extra_env.get("PORT", "9621"))
                                except (ValueError, TypeError):
                                    current_port = 9621
                                
                                # Always try to use standard port 9621 on restart
                                # If it's occupied, _try_alternative_port() will find next available port
                                standard_port = 9621
                                logger.info(f"[LightragServer] Will attempt restart on standard port {standard_port}")
                                self.extra_env["PORT"] = str(standard_port)
                                
                                self.stop()
                                # Minimal wait - let _try_alternative_port() handle port availability check
                                time.sleep(0.5)  # Brief delay to allow process cleanup to start
                                logger.info("[LightragServer] 🔄 Restarting subprocess with new proxy settings...")
                                self.start(wait_ready=False)  # Non-blocking restart
                                logger.info("[LightragServer] ✅ Subprocess restarted with new proxy settings")
                            except Exception as e:
                                logger.error(f"[LightragServer] Error during proxy-triggered restart: {e}")
                        
                        # Schedule restart in background thread (non-blocking)
                        restart_thread = threading.Thread(
                            target=_do_restart,
                            name="LightragProxyRestart",
                            daemon=True
                        )
                        restart_thread.start()
                    else:
                        logger.info(
                            "[LightragServer] ℹ️  Proxy settings updated. "
                            "Server will use new proxy settings on next start."
                        )
                            
                except Exception as e:
                    logger.error(f"[LightragServer] Error handling proxy state change: {e}")
            
            self._proxy_callback_unregister = proxy_manager.register_callback(on_proxy_state_change)
            logger.info("[LightragServer] ✅ Registered proxy state change callback (auto-restart enabled)")
            
        except ImportError:
            logger.debug("[LightragServer] Proxy manager module not available")
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to register proxy change callback: {e}")
    
    def stop(self):
        """Stop the server"""
        logger.info("[LightragServer] Stopping server...")
        
        # Unregister proxy change callback on stop
        if self._proxy_callback_unregister is not None:
            try:
                self._proxy_callback_unregister()
                self._proxy_callback_unregister = None
            except Exception as e:
                logger.debug(f"[LightragServer] Error unregistering proxy change callback: {e}")

        # Stop monitoring threads
        self._monitor_running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
        if getattr(self, "_proc_monitor_thread", None) is not None:
            try:
                self._proc_monitor_thread.join(timeout=2)
            except Exception:
                pass
            self._proc_monitor_thread = None

        # Stop server process
        if self.proc is not None:
            try:
                # Try graceful shutdown (process group aware)
                pid = self.proc.pid
                self._terminate_pid(pid, force=False)

                # Wait for process to exit
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill the process
                    logger.warning("[LightragServer] Force killing server process")
                    self._terminate_pid(pid, force=True)
                    self.proc.wait()

                logger.info("[LightragServer] Server stopped")

            except Exception as e:
                logger.error(f"[LightragServer] Error stopping server: {e}")
            finally:
                self.proc = None
        else:
            logger.info("[LightragServer] Server is not running")

        self._remove_pid_file()
        self._close_log_files()

        # Clean up temporary startup script
        try:
            if getattr(self, "_script_path", None):
                os.remove(self._script_path)
                self._script_path = None
        except Exception:
            pass

    def is_running(self):
        """Check if the server is running"""
        return self.proc is not None and self.proc.poll() is None

    def get_current_port(self):
        """Get the current port in use"""
        try:
            # Get port from environment variables
            port = self.extra_env.get("PORT", "9621")
            return int(port)
        except (ValueError, TypeError):
            # If the port is not a valid number, return the default port
            return 9621

    def get_server_url(self):
        """Get the server URL"""
        port = self.get_current_port()
        host = self.extra_env.get("HOST", "127.0.0.1")
        return f"http://{host}:{port}"

    def get_webui_url(self):
        """Get the WebUI URL"""
        port = self.get_current_port()
        host = self.extra_env.get("HOST", "127.0.0.1")
        return f"http://{host}:{port}/webui"


# -------- helpers --------
def _safe_tail(file_path: str, num_lines: int = 80) -> str:
    try:
        if not file_path or not os.path.exists(file_path):
            return ""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            return ''.join(lines[-num_lines:])
    except Exception:
        return ""

if __name__ == "__main__":
    server = LightragServer()
    proc = server.start()
    try:
        proc.wait()
    except KeyboardInterrupt:
        server.stop()
