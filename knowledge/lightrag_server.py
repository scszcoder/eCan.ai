import subprocess
import os
import sys
import signal
from pathlib import Path
import threading
import time
from utils.logger_helper import logger_helper as logger

# 优先读取 knowledge 目录下的 .env 文件
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

        # 检测是否在 PyInstaller 打包环境中
        self.is_frozen = getattr(sys, 'frozen', False)

        # 重启控制 - 从环境变量读取配置
        self.restart_count = 0
        self.max_restarts = int(self.extra_env.get("MAX_RESTARTS", "3"))
        self.last_restart_time = 0
        self.restart_cooldown = int(self.extra_env.get("RESTART_COOLDOWN", "30"))  # 秒

        # Get parent process ID - handle Windows compatibility and PyInstaller
        import platform
        is_windows = platform.system().lower().startswith('win')

        # 在 PyInstaller 环境中，默认禁用父进程监控以避免问题
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

        # 设置信号处理器
        self._setup_signal_handlers()

        # 自动处理 APP_DATA 生成相关目录
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
        """设置信号处理器"""
        def signal_handler(signum, frame):
            logger.info(f"[LightragServer] Received signal {signum}, stopping server...")
            self.stop()
            if not self.is_frozen:  # 只在非打包环境中退出
                sys.exit(0)

        try:
            # 注册信号处理器
            signal.signal(signal.SIGTERM, signal_handler)
            signal.signal(signal.SIGINT, signal_handler)

            # macOS/Linux 特有信号
            if hasattr(signal, 'SIGHUP'):
                signal.signal(signal.SIGHUP, signal_handler)

            logger.info("[LightragServer] Signal handlers registered")
        except Exception as e:
            logger.warning(f"[LightragServer] Failed to setup signal handlers: {e}")

    def build_env(self):
        env = os.environ.copy()
        if self.extra_env:
            env.update({str(k): str(v) for k, v in self.extra_env.items()})
        return env

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

        # 添加失败计数器，避免偶发性检查失败导致退出
        failure_count = 0
        max_failures = 3  # 连续失败3次才退出

        logger.info(f"[LightragServer] Starting parent process monitoring for PID {self.parent_pid}")

        while self._monitor_running:
            try:
                if self.parent_pid is None:
                    # 如果没有父进程 PID，跳过检查
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
                            failure_count = 0  # 重置失败计数
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
                        failure_count = 0  # 重置失败计数
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

            time.sleep(5)  # 增加检查间隔到5秒

    def _monitor_server_process(self):
        """监控服务器进程，支持自动重启"""
        while self._monitor_running:
            try:
                if self.proc is None:
                    time.sleep(5)
                    continue

                # 检查进程是否还在运行
                if self.proc.poll() is not None:
                    # 进程已退出
                    return_code = self.proc.returncode
                    logger.warning(f"[LightragServer] Server process exited with code {return_code}")

                    # 检查是否需要重启
                    current_time = time.time()
                    if (current_time - self.last_restart_time) > self.restart_cooldown:
                        self.restart_count = 0  # 重置重启计数

                    if self.restart_count < self.max_restarts:
                        self.restart_count += 1
                        self.last_restart_time = current_time
                        logger.info(f"[LightragServer] Attempting restart {self.restart_count}/{self.max_restarts}")

                        # 等待一段时间后重启
                        time.sleep(5)
                        if self._start_server_process():
                            continue

                    logger.error(f"[LightragServer] Max restarts ({self.max_restarts}) reached, giving up")
                    break

                time.sleep(5)  # 每5秒检查一次

            except Exception as e:
                logger.error(f"[LightragServer] Process monitor error: {e}")
                time.sleep(5)

    def _create_log_files(self):
        """创建日志文件"""
        log_dir = self.extra_env.get("LOG_DIR", ".")
        os.makedirs(log_dir, exist_ok=True)

        stdout_log_path = os.path.join(log_dir, "lightrag_server_stdout.log")
        stderr_log_path = os.path.join(log_dir, "lightrag_server_stderr.log")

        stdout_log = open(stdout_log_path, "a", encoding="utf-8")
        stderr_log = open(stderr_log_path, "a", encoding="utf-8")

        return stdout_log, stderr_log, stdout_log_path, stderr_log_path

    def _start_server_process(self):
        """启动服务器进程"""
        try:
            env = self.build_env()
            stdout_log, stderr_log, stdout_log_path, stderr_log_path = self._create_log_files()

            import platform
            if platform.system().lower().startswith('win'):
                self.proc = subprocess.Popen(
                    [sys.executable, "-m", "lightrag.api.lightrag_server"],
                    env=env,
                    stdin=subprocess.PIPE,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if hasattr(subprocess, 'CREATE_NEW_PROCESS_GROUP') else 0
                )
                try:
                    self.proc.stdin.write("yes\n")
                    self.proc.stdin.flush()
                except Exception as e:
                    logger.error(f"[LightragServer] Failed to write to stdin: {e}")
            else:
                # Unix-like 系统
                yes_proc = subprocess.Popen(["yes", "yes"], stdout=subprocess.PIPE)
                self.proc = subprocess.Popen(
                    [sys.executable, "-m", "lightrag.api.lightrag_server"],
                    env=env,
                    stdin=yes_proc.stdout,
                    stdout=stdout_log,
                    stderr=stderr_log,
                    text=True,
                    preexec_fn=os.setsid if hasattr(os, 'setsid') else None
                )

            final_host = env.get("HOST", "0.0.0.0")
            final_port = env.get("PORT", "9621")

            logger.info(f"[LightragServer] Server started at http://{final_host}:{final_port}")
            logger.info(f"[LightragServer] WebUI: http://{final_host}:{final_port}/webui")
            logger.info(f"[LightragServer] Logs: {stdout_log_path}, {stderr_log_path}")

            return True

        except Exception as e:
            logger.error(f"[LightragServer] Failed to start server: {e}")
            return False

    def start(self):
        """启动服务器"""
        if self.proc is not None and self.proc.poll() is None:
            logger.warning("[LightragServer] Server is already running")
            return self.proc

        logger.info("[LightragServer] Starting LightRAG server...")

        # 启动服务器进程
        if not self._start_server_process():
            return None

        # 启动父进程监控线程
        if not self.disable_parent_monitoring and self.parent_pid is not None:
            self._monitor_running = True
            self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
            self._monitor_thread.start()
            logger.info(f"[LightragServer] Parent process monitoring enabled for PID {self.parent_pid}")
        else:
            logger.info(f"[LightragServer] Parent process monitoring disabled (disabled={self.disable_parent_monitoring}, pid={self.parent_pid})")

        # 启动进程监控线程（用于自动重启）
        if self.max_restarts > 0:
            process_monitor_thread = threading.Thread(target=self._monitor_server_process, daemon=True)
            process_monitor_thread.start()
            logger.info("[LightragServer] Process monitoring enabled for auto-restart")

        return self.proc

    def stop(self):
        """停止服务器"""
        logger.info("[LightragServer] Stopping server...")

        # 停止监控线程
        self._monitor_running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None

        # 停止服务器进程
        if self.proc is not None:
            try:
                # 尝试优雅关闭
                self.proc.terminate()

                # 等待进程结束
                try:
                    self.proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # 强制杀死进程
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

    def is_running(self):
        """检查服务器是否在运行"""
        return self.proc is not None and self.proc.poll() is None

if __name__ == "__main__":
    server = LightragServer()
    proc = server.start()
    try:
        proc.wait()
    except KeyboardInterrupt:
        server.stop()

    # import openai
    # client = openai.OpenAI(api_key="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")
    # resp = client.embeddings.create(
    #     input="test",
    #     model="text-embedding-3-large"
    # )
    # print(len(resp.data[0].embedding))