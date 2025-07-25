import subprocess
import os
import sys
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
        logger.info(f"[LightragServer] extra_env: {self.extra_env}")  # debug log
        self.proc = None
        self.parent_pid = os.getppid()
        self._monitor_running = False
        self._monitor_thread = None
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

    def build_env(self):
        env = os.environ.copy()
        if self.extra_env:
            env.update({str(k): str(v) for k, v in self.extra_env.items()})
        return env

    def _monitor_parent(self):
        while self._monitor_running:
            try:
                os.kill(self.parent_pid, 0)
            except OSError:
                logger.error("Parent process is gone, exiting lightrag server...")
                os._exit(1)
            time.sleep(2)

    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            logger.warning("lightrag server is already running.")
            return self.proc
        env = self.build_env()
        final_host = env.get("HOST", "0.0.0.0")
        final_port = env.get("PORT", "9621")
        # 日志文件路径
        log_dir = self.extra_env.get("LOG_DIR", ".")
        os.makedirs(log_dir, exist_ok=True)  # 自动创建日志目录
        stdout_log_path = os.path.join(log_dir, "lightrag_server_stdout.log")
        stderr_log_path = os.path.join(log_dir, "lightrag_server_stderr.log")
        stdout_log = open(stdout_log_path, "a", encoding="utf-8")
        stderr_log = open(stderr_log_path, "a", encoding="utf-8")
        # 启动父进程监控线程
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_parent, daemon=True)
        self._monitor_thread.start()
        import platform
        if platform.system().lower().startswith('win'):
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "lightrag.api.lightrag_server"],
                env=env,
                stdin=subprocess.PIPE,
                stdout=stdout_log,
                stderr=stderr_log,
                text=True
            )
            try:
                self.proc.stdin.write("yes\n")
                self.proc.stdin.flush()
            except Exception as e:
                logger.error(f"Failed to write yes to lightrag_server: {e}")
        else:
            yes_proc = subprocess.Popen(["yes", "yes"], stdout=subprocess.PIPE)
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "lightrag.api.lightrag_server"],
                env=env,
                stdin=yes_proc.stdout,
                stdout=stdout_log,
                stderr=stderr_log,
                text=True
            )
        logger.info(f"lightrag server started at http://{final_host}:{final_port}")
        logger.info(f"webui: http://{final_host}:{final_port}/webui")
        logger.info(f"lightrag server stdout log: {stdout_log_path}")
        logger.info(f"lightrag server stderr log: {stderr_log_path}")
        return self.proc

    def stop(self):
        self._monitor_running = False
        if self._monitor_thread is not None:
            self._monitor_thread.join(timeout=2)
            self._monitor_thread = None
        if self.proc is not None:
            self.proc.terminate()
            logger.info("lightrag server stopped.")
            self.proc = None
        else:
            logger.info("lightrag server is not running.")

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