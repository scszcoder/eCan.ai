from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtCore import QTimer
import sys
import os
import random

from gui.ipc.api import IPCAPI

# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"

from config.app_settings import app_settings
from utils.logger_helper import logger_helper
from gui.core.web_engine_view import WebEngineView
from gui.core.dev_tools_manager import DevToolsManager

class WebGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ECBot Web Interface")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 创建 Web 引擎
        self.web_engine_view = WebEngineView()
        
        # 创建开发者工具管理器
        self.dev_tools_manager = DevToolsManager(self)
        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger_helper.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_engine_view.load_url(web_url)
                logger_helper.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger_helper.error("Failed to get web URL")
        
        # 添加 Web 引擎到布局
        layout.addWidget(self.web_engine_view)
        
        # 设置快捷键
        self._setup_shortcuts()
        
        # # 创建定时器 Demo 测试使用的
        self.dashboard_timer = QTimer(self)
        self.dashboard_timer.timeout.connect(self.update_dashboard_data)
        self.dashboard_timer.start(5000)  # 每5秒触发一次
    
    def load_local_html(self):
        """加载本地 HTML 文件"""
        index_path = app_settings.dist_dir / "index.html"
        logger_helper.info(f"Looking for index.html at: {index_path}")
        
        if index_path.exists():
            try:
                # 读取 HTML 内容
                with open(index_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                
                # 设置基础 URL
                base_url = str(app_settings.dist_dir.absolute())
                logger_helper.info(f"Base URL: {base_url}")
                
                # 修改资源路径为绝对路径
                html_content = html_content.replace('src="./', f'src="file://{base_url}/')
                html_content = html_content.replace('href="./', f'href="file://{base_url}/')
                
                # 加载 HTML 内容
                self.web_engine_view.page().setHtml(html_content, base_url)
                logger_helper.info(f"Production mode: Loading from {index_path}, {base_url}")
                
            except Exception as e:
                logger_helper.error(f"Error loading HTML file: {str(e)}")
                import traceback
                logger_helper.error(traceback.format_exc())
        else:
            logger_helper.error(f"index.html not found in {app_settings.dist_dir}")
            # 列出目录内容以便调试
            if app_settings.dist_dir.exists():
                logger_helper.info(f"Contents of {app_settings.dist_dir}:")
                for item in app_settings.dist_dir.iterdir():
                    logger_helper.info(f"  - {item.name}")
            else:
                logger_helper.error(f"Directory {app_settings.dist_dir} does not exist")
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        # 开发者工具快捷键
        self.dev_tools_shortcut = QShortcut(QKeySequence("F12"), self)
        self.dev_tools_shortcut.activated.connect(self.dev_tools_manager.toggle)
        
        # F5 重新加载
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L 清除日志
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools_manager.clear_all)
        self.addAction(clear_logs_action)
    
    def reload(self):
        """重新加载页面"""
        logger_helper.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_engine_view.reload_page()
        else:
            self.load_local_html()
    
    def update_dashboard_data(self):
        """更新仪表盘数据"""
        try:
            # 生成随机数据
            data = {
                'overview': random.randint(10, 100),
                'statistics': random.randint(5, 50),
                'recentActivities': random.randint(20, 200),
                'quickActions': random.randint(1, 30)
            }
            
            # 调用 refresh_dashboard API
            def handle_response(response):
                if response.success:
                    logger_helper.info(f"Dashboard data updated successfully: {response.data}")
                else:
                    logger_helper.error(f"Failed to update dashboard data: {response.error}")
            
            IPCAPI.get_instance().refresh_dashboard(data, handle_response)
            
        except Exception as e:
            logger_helper.error(f"Error updating dashboard data: {e}")
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 创建确认对话框
        reply = QMessageBox.question(
            self,
            'Confirm Exit',
            'Are you sure you want to exit the program?',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 接受关闭事件
            event.accept()
            # 结束整个应用程序
            sys.exit(0)
        else:
            # 忽略关闭事件
            event.ignore() 