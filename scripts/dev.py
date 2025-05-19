import subprocess
import sys
import os
import time
import signal
from typing import List, Optional
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, QSize

# 添加项目根目录到 Python 路径
ROOT_DIR = Path(__file__).parent.parent
sys.path.append(str(ROOT_DIR))

class MainWindow(QMainWindow):
    def __init__(self, url: str):
        super().__init__()
        self.setWindowTitle("ECBot - 开发模式")
        self.setMinimumSize(QSize(1200, 800))
        
        # 创建 WebView
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl(url))
        self.setCentralWidget(self.web_view)

class DevServer:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.frontend_url = "http://localhost:5173"
        self.root_dir = ROOT_DIR

    def start(self) -> bool:
        """启动开发服务器"""
        try:
            frontend_dir = self.root_dir / 'gui_v2'
            os.chdir(frontend_dir)
            if sys.platform == 'win32':
                self.process = subprocess.Popen('npm run dev', shell=True)
            else:
                self.process = subprocess.Popen(['npm', 'run', 'dev'])
            os.chdir(self.root_dir)
            return True
        except Exception as e:
            print(f"启动开发服务器失败: {e}")
            return False

    def wait_for_server(self, timeout: int = 30) -> bool:
        """等待服务器启动"""
        import requests
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(self.frontend_url)
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(1)
        return False

    def cleanup(self):
        """清理进程"""
        if self.process:
            try:
                if sys.platform == 'win32':
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)])
                else:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            except:
                pass

def main():
    try:
        # 启动开发服务器
        server = DevServer()
        if not server.start():
            print("启动开发服务器失败")
            return 1

        print("等待开发服务器启动...")
        if not server.wait_for_server():
            print("开发服务器启动超时")
            server.cleanup()
            return 1

        print("开发服务器已就绪")

        # 启动桌面应用
        app = QApplication(sys.argv)
        window = MainWindow(server.frontend_url)
        window.show()

        try:
            return app.exec()
        finally:
            server.cleanup()

    except Exception as e:
        print(f"启动应用失败: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main()) 