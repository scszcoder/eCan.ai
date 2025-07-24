import subprocess
import os
import sys
from pathlib import Path
import threading
import time

# 优先读取 knowledge 目录下的 .env 文件
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

class LightragServer:
    def __init__(self, extra_env=None):
        self.extra_env = extra_env or {}
        print(f"[LightragServer] extra_env: {self.extra_env}")  # debug log
        self.proc = None
        self.parent_pid = os.getppid()

        # 自动处理 APP_DATA 生成相关目录
        app_data_path = self.extra_env.get("APP_DATA_PATH")
        if app_data_path:
            input_dir = os.path.join(app_data_path, "inputs")
            working_dir = os.path.join(app_data_path, "rag_storage")
            log_dir = os.path.join(app_data_path, "runlogs")
            self.extra_env.setdefault("INPUT_DIR", input_dir)
            self.extra_env.setdefault("WORKING_DIR", working_dir)
            self.extra_env.setdefault("LOG_DIR", log_dir)
            print(f"[LightragServer] INPUT_DIR: {input_dir}, WORKING_DIR: {working_dir}, LOG_DIR: {log_dir}")

    def build_env(self):
        env = os.environ.copy()
        if self.extra_env:
            env.update({str(k): str(v) for k, v in self.extra_env.items()})
        return env

    def _monitor_parent(self):
        while True:
            try:
                os.kill(self.parent_pid, 0)
            except OSError:
                print("Parent process is gone, exiting lightrag server...")
                os._exit(1)
            time.sleep(2)

    def start(self):
        if self.proc is not None and self.proc.poll() is None:
            print("lightrag server is already running.")
            return self.proc
        env = self.build_env()
        final_host = env.get("HOST", "0.0.0.0")
        final_port = env.get("PORT", "9621")
        # 启动父进程监控线程
        threading.Thread(target=self._monitor_parent, daemon=True).start()
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "lightrag.api.lightrag_server"],
            env=env
        )
        print(f"lightrag server started at http://{final_host}:{final_port}")
        print(f"webui: http://{final_host}:{final_port}/webui")
        return self.proc

    def stop(self):
        if self.proc is not None:
            self.proc.terminate()
            print("lightrag server stopped.")
            self.proc = None
        else:
            print("lightrag server is not running.")

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