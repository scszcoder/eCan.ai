import subprocess
import os
import sys
import signal
from pathlib import Path
import threading
import time
from utils.logger_helper import logger_helper as logger

# Prioritize reading .env file from knowledge directory
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
except ImportError:
    pass


class LightragServer:
    def __init__(self, extra_env=None):
        self.extra_env = extra_env or {}
        logger.info(f"[LightragServer] extra_env: {self.extra_env}")
        self.proc = None

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

        # In PyInstaller environment, disable parent process monitoring by default to avoid issues
        if self.is_frozen:
            logger.info("[LightragServer] Running in PyInstaller environment, disabling parent monitoring by default")
            self.disable_parent_monitoring = True
            self.parent_pid = None
        else:
            if is_windows:
                try:
                    import psutil
                    self.parent_pid = psutil.Process().ppid()
                except (ImportError, AttributeError):
                    # Fallback to os.getppid() if psutil is not available
                    self.parent_pid = os.getppid()
            else:
                self.parent_pid = os.getppid()

            # Check if parent process monitoring should be disabled
            self.disable_parent_monitoring = self.extra_env.get("DISABLE_PARENT_MONITORING", "false").lower() == "true"

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

    def build_env(self):
        env = os.environ.copy()

        # Force fix Windows encoding issues
        env['PYTHONIOENCODING'] = 'utf-8'
        env['PYTHONUTF8'] = '1'
        env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output for subprocess to avoid missing logs
        env['PYTHONLEGACYWINDOWSSTDIO'] = '0'
        env['LANG'] = 'en_US.UTF-8'
        env['LC_ALL'] = 'en_US.UTF-8'

        # Set default values
        env.setdefault('HOST', '127.0.0.1')
        env.setdefault('PORT', '9621')
        env.setdefault('MAX_RESTARTS', '3')
        env.setdefault('RESTART_COOLDOWN', '5')
        env.setdefault('NO_COLOR', '1')
        env.setdefault('ASCII_COLORS_DISABLE', '1')

        # Health check parameters (configurable via environment variables)
        env.setdefault('LIGHTRAG_HEALTH_TIMEOUT', '45')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_INITIAL', '0.5')  # seconds
        env.setdefault('LIGHTRAG_HEALTH_INTERVAL_MAX', '1.5')  # seconds

        if self.extra_env:
            env.update({str(k): str(v) for k, v in self.extra_env.items()})

        # Special handling in packaged environment
        if self.is_frozen:
            # Clear Python environment variables that might cause conflicts
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            logger.info("[LightragServer] Cleaned Python environment variables for packaged environment")
            # # Force bind to 127.0.0.1, avoid 0.0.0.0 in .env affecting health checks in packaged environment
            # host = str(env.get('HOST', '127.0.0.1')).strip()
            # if host in ('0.0.0.0', '::', ''):
            #     env['HOST'] = '127.0.0.1'

        # Set path-related environment variables
        if 'APP_DATA_PATH' in env:
            app_data_path = env['APP_DATA_PATH']
            env.setdefault('INPUT_DIR', os.path.join(app_data_path, 'inputs'))
            env.setdefault('WORKING_DIR', os.path.join(app_data_path, 'rag_storage'))
            env.setdefault('LOG_DIR', os.path.join(app_data_path, 'runlogs'))

        # Override API keys from OPENAI_API_KEY environment variable
        openai_api_key = env.get('OPENAI_API_KEY')
        if openai_api_key and openai_api_key.strip():
            # Create masked version for logging
            masked_key = openai_api_key[:8] + "..." + openai_api_key[-4:] if len(openai_api_key) > 12 else "***"
            
            # Override LLM API key
            env['LLM_BINDING_API_KEY'] = openai_api_key
            logger.info(f"[LightragServer] ✅ LLM_BINDING_API_KEY overridden from OPENAI_API_KEY environment variable ({masked_key})")
            
            # Override Embedding API key
            env['EMBEDDING_BINDING_API_KEY'] = openai_api_key
            logger.info(f"[LightragServer] ✅ EMBEDDING_BINDING_API_KEY overridden from OPENAI_API_KEY environment variable ({masked_key})")
        else:
            logger.error("[LightragServer] ❌ OPENAI_API_KEY environment variable not found or empty. LLM and Embedding API keys will use .env file values.")

        return env

    def _get_virtual_env_python(self):
        """Get Python interpreter path in virtual environment"""
        # In packaged environment, sys.executable is the exe file containing all dependencies
        # LightRAG server should use the same exe to ensure environment consistency
        if self.is_frozen:
            logger.info(f"[LightragServer] Running in PyInstaller environment, using current executable: {sys.executable}")
            return sys.executable

        # Original logic for non-packaged environment
        # Check if currently in virtual environment
        if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
            logger.info(f"[LightragServer] Already in virtual environment: {sys.executable}")
            return sys.executable

        # Try to find virtual environment in project root directory
        project_root = os.path.dirname(os.path.dirname(__file__))
        venv_paths = [
            os.path.join(project_root, "venv", "bin", "python"),
            os.path.join(project_root, "venv", "Scripts", "python.exe"),
        ]

        for venv_python in venv_paths:
            if os.path.exists(venv_python):
                logger.info(f"[LightragServer] Found virtual environment Python: {venv_python}")
                return venv_python

        # If virtual environment not found, return current interpreter
        logger.warning(f"[LightragServer] No virtual environment found, using current Python: {sys.executable}")
        return sys.executable

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

            # In non-packaged environment, test Python interpreter version
            result = subprocess.run(
                [python_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                logger.info(f"[LightragServer] Python validation successful: {result.stdout.strip()}")
                return True
            else:
                logger.error(f"[LightragServer] Python validation failed with return code {result.returncode}")
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
        """Create simple LightRAG startup script, utilizing main.py protection mechanism"""
        try:
            import tempfile

            # Safely handle environment variables
            env_settings = []
            for key, value in self.extra_env.items():
                # Safely escape paths
                safe_value = str(value).replace('\\', '/')
                env_settings.append(f'os.environ["{key}"] = r"{safe_value}"')

            env_code = '\n    '.join(env_settings)

            # Create simple startup script
            # Key: don't import main module, run LightRAG directly
            script_content = f'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LightRAG Simple Startup Script
Utilize existing protection mechanism in main.py, don't import main program module
"""

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
    """Setup LightRAG environment"""
    # Set environment variables
    {env_code}

    # Clean command line arguments
    sys.argv = ["lightrag_server"]

    print("LightRAG Environment Setup Complete")

def main():
    """Start LightRAG server"""
    try:
        print("=" * 50)
        print("LightRAG Server Starting...")
        print("=" * 50)

        # Setup environment
        setup_lightrag_environment()

        # Check LightRAG availability
        try:
            import lightrag
            print(f"LightRAG version: {{getattr(lightrag, '__version__', 'unknown')}}")
        except ImportError as e:
            print(f"LightRAG not available: {{e}}")
            print("Exiting gracefully...")
            return 0

        # Start LightRAG server
        from lightrag.api.lightrag_server import main as lightrag_main
        print("Starting LightRAG API server...")
        lightrag_main()

    except KeyboardInterrupt:
        print("LightRAG server interrupted")
        return 0
    except Exception as e:
        print(f"LightRAG server error: {{e}}")
        import traceback
        traceback.print_exc()
        return 1

# Use standard if __name__ == '__main__'
# This will be properly handled by main.py protection mechanism
if __name__ == '__main__':
    sys.exit(main())
'''

            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(script_content)
                script_path = f.name

            logger.info(f"[LightragServer] Created simple startup script: {script_path}")
            return script_path

        except Exception as e:
            logger.error(f"[LightragServer] Failed to create simple startup script: {e}")
            return None

    def _check_and_free_port(self):
        """Check if port is occupied, try to free it if occupied"""
        try:
            import socket
            import platform
            import subprocess
            import time

            port = int(self.extra_env.get("PORT", "9621"))
            is_windows = platform.system().lower().startswith('win')

            # Check if port is occupied
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('localhost', port))
            sock.close()

            if result == 0:
                # Port is occupied, try to free it
                logger.warning(f"[LightragServer] Port {port} is in use, attempting to free it...")

                pids = self._find_processes_using_port(port, is_windows)

                if pids:
                    logger.info(f"[LightragServer] Found {len(pids)} process(es) using port {port}: {pids}")

                    # Try to kill processes
                    killed_count = 0
                    for pid in pids:
                        if self._kill_process(pid, is_windows):
                            killed_count += 1
                            logger.info(f"[LightragServer] Successfully killed process {pid}")
                        else:
                            logger.warning(f"[LightragServer] Failed to kill process {pid}")

                    if killed_count > 0:
                        # Wait for port to be released
                        for i in range(15):  # Wait up to 15 seconds
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(1)
                            result = sock.connect_ex(('localhost', port))
                            sock.close()
                            if result != 0:
                                logger.info(f"[LightragServer] Port {port} is now free after killing {killed_count} process(es)")
                                return True
                            time.sleep(1)

                        logger.warning(f"[LightragServer] Port {port} is still in use after killing processes")
                    else:
                        logger.warning(f"[LightragServer] Could not kill any processes using port {port}")

                    # If unable to kill processes, try using different port
                    return self._try_alternative_port(port)
                else:
                    logger.warning(f"[LightragServer] Could not find processes using port {port}")
                    return self._try_alternative_port(port)
            else:
                # Port is available
                return True

        except Exception as e:
            logger.warning(f"[LightragServer] Error checking port: {e}")
            return True  # If check fails, assume port is available

    def _find_processes_using_port(self, port, is_windows):
        """Find processes using specified port"""
        try:
            if is_windows:
                # Windows: use netstat
                result = subprocess.run(
                    ['netstat', '-ano'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    pids = []
                    for line in result.stdout.split('\n'):
                        if f':{port}' in line and 'LISTENING' in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                pid = parts[-1]
                                if pid.isdigit():
                                    pids.append(pid)
                    return pids
            else:
                # Unix/Linux/macOS: use lsof
                result = subprocess.run(
                    ['lsof', '-ti', f':{port}'],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split('\n')

            return []
        except Exception as e:
            logger.warning(f"[LightragServer] Error finding processes using port {port}: {e}")
            return []

    def _kill_process(self, pid, is_windows):
        """Try to kill process"""
        try:
            if is_windows:
                # Windows: use taskkill
                result = subprocess.run(
                    ['taskkill', '/PID', str(pid), '/F'],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
            else:
                # Unix/Linux/macOS: use kill
                result = subprocess.run(
                    ['kill', '-9', str(pid)],
                    capture_output=True, text=True, timeout=10
                )
                return result.returncode == 0
        except Exception as e:
            logger.warning(f"[LightragServer] Error killing process {pid}: {e}")
            return False

    def _try_alternative_port(self, original_port):
        """Try to use alternative port"""
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
                    logger.info(f"[LightragServer] Found alternative port {port}")
                    self.extra_env["PORT"] = str(port)
                    return True

            logger.error(f"[LightragServer] No available ports found in range {original_port}-{original_port + 9}")
            return False

        except Exception as e:
            logger.warning(f"[LightragServer] Error trying alternative ports: {e}")
            return False

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

    def _start_server_process(self, wait_gating: bool = False):
        """Start server process
        
        Args:
            wait_gating: Whether to wait for health check to pass in foreground (blocking). Default False non-blocking.
        """
        try:
            env = self.build_env()
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files()

            # Check and determine final port (based on env, find available port if necessary), keep env and extra_env consistent
            try:
                desired_port = int(env.get("PORT", "9621"))
            except (ValueError, TypeError):
                desired_port = 9621
                logger.warning("[LightragServer] Invalid PORT in env, falling back to 9621")

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
                except ImportError:
                    logger.warning("[LightragServer] lightrag module not available in packaged environment")
                    logger.warning("[LightragServer] LightRAG server will be disabled")
                    return False

            import platform

            # Build start command
            if self.is_frozen:
                # In packaged environment, use the existing protection mechanism in main.py
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
                cmd = [python_executable]  # No -u needed; PYTHONUNBUFFERED=1 forces unbuffered output
                logger.info(f"[LightragServer] PyInstaller mode command: {cmd} with ECAN_RUN_SCRIPT={script_path}")
            else:
                # Development environment: use -u for unbuffered output to locate errors quickly
                cmd = [python_executable, "-u", "-m", "lightrag.api.lightrag_server"]
                logger.info(f"[LightragServer] Development mode command: {' '.join(cmd)}")

            if platform.system().lower().startswith('win'):
                # Hide console window in production by default; enable via env for debugging
                show_console = os.getenv("ECBOT_CHILD_SHOW_CONSOLE") == "1"
                creation_flags = 0
                if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP'):
                    creation_flags |= subprocess.CREATE_NEW_PROCESS_GROUP
                if not show_console and hasattr(subprocess, 'CREATE_NO_WINDOW'):
                    creation_flags |= subprocess.CREATE_NO_WINDOW

                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    creationflags=creation_flags
                )
                try:
                    self.proc.stdin.write("yes\n")
                    self.proc.stdin.flush()
                except Exception as e:
                    logger.error(f"[LightragServer] Failed to write to stdin: {e}")
            else:
                # Unix-like systems
                yes_proc = subprocess.Popen(["yes", "yes"], stdout=subprocess.PIPE)
                self.proc = subprocess.Popen(
                    cmd,
                    env=env,
                    stdin=yes_proc.stdout,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )

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
                return True

        except Exception as e:
            logger.error(f"[LightragServer] Failed to start server: {e}")
            return False

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

    def stop(self):
        """Stop the server"""
        logger.info("[LightragServer] Stopping server...")

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
                # Try graceful shutdown
                self.proc.terminate()

                # Wait for process to exit
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill the process
                    logger.warning("[LightragServer] Force killing server process")
                    self.proc.kill()
                    self.proc.wait()

                logger.info("[LightragServer] Server stopped")

            except Exception as e:
                logger.error(f"[LightragServer] Error stopping server: {e}")
            finally:
                self.proc = None
        else:
            logger.info("[LightragServer] Server is not running")

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