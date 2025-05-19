from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl
from pathlib import Path
import os

from config.app_settings import app_settings

class WebGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ECBot Web Interface")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建 Web 视图
        self.web_view = QWebEngineView()
        
        # 根据配置加载页面
        web_url = app_settings.get_web_url()
        if web_url:
            self.web_view.setUrl(QUrl(web_url))
            print(f"Loading web page from: {web_url}")
        else:
            print(f"Warning: Could not find web page to load")
        
        # 添加 Web 视图到布局
        layout.addWidget(self.web_view)
        
    def reload(self):
        """重新加载页面"""
        self.web_view.reload() 