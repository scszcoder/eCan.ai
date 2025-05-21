from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QDockWidget, 
                             QTextEdit, QTabWidget, QSplitter)
from PySide6.QtCore import Qt, Signal, Slot, QObject, Property
from PySide6.QtGui import QAction, QKeySequence, QTextCursor, QShortcut
import datetime
import sys
import os
import logging

# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
    logging.getLogger('PySide6').setLevel(logging.ERROR)

from config.app_settings import app_settings
from utils.logger_helper import logger_helper
from gui.ipc import IPCHandler, WebRequestHandler
from gui.core.web_engine import WebEngine
from gui.core.request_interceptor import RequestInterceptor
from gui.core.js_injector import JavaScriptInjector
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
        self.web_engine = WebEngine()
        
        # 创建开发者工具管理器
        self.dev_tools_manager = DevToolsManager(self)
        
        # 创建 IPC 处理器
        self.ipc_handler = IPCHandler(self)
        
        # 创建 Web 请求处理器
        self.web_request = WebRequestHandler(self.ipc_handler)
        
        # 设置请求拦截器
        interceptor = RequestInterceptor()
        self.web_engine.page().profile().setUrlRequestInterceptor(interceptor)
        
        # 设置 WebChannel
        self.web_engine.setup_web_channel(self.ipc_handler)
        
        # 连接信号
        self.web_engine.loadStarted.connect(self.on_load_started)
        self.web_engine.loadProgress.connect(self.on_load_progress)
        self.web_engine.loadFinished.connect(self.on_load_finished)
        self.web_engine.loadStarted.connect(lambda: logger_helper.info("Page load started"))
        self.web_engine.loadFinished.connect(lambda ok: logger_helper.info(f"Page load finished: {'success' if ok else 'failed'}"))
        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger_helper.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_engine.load_url(web_url)
                logger_helper.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger_helper.error("Failed to get web URL")
        
        # 添加 Web 引擎到布局
        layout.addWidget(self.web_engine)
        
        # 设置快捷键
        self._setup_shortcuts()
    
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
                
                # 注入 WebChannel 和调试代码
                webchannel_script = JavaScriptInjector.get_web_channel_script()
                dev_tools_script = JavaScriptInjector.get_dev_tools_script()
                
                # 在 </head> 标签前插入脚本
                html_content = html_content.replace('</head>', f'{webchannel_script}{dev_tools_script}</head>')
                
                # 修改资源路径为绝对路径
                html_content = html_content.replace('src="./', f'src="file://{base_url}/')
                html_content = html_content.replace('href="./', f'href="file://{base_url}/')
                
                # 加载 HTML 内容
                self.web_engine.page().setHtml(html_content, base_url)
                logger_helper.info(f"Production mode: Loading from {index_path}, {base_url}")
                
                # 重新初始化 WebChannel
                self.web_engine.setup_web_channel(self.ipc_handler)
                
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
    
    def on_console_message(self, message, level):
        """处理 JavaScript 控制台消息"""
        logger_helper.info(f"Console message: {message}")
    
    def on_network_request(self, request_data):
        """处理网络请求"""
        logger_helper.info(f"Network request: {request_data}")
    
    def on_element_inspection(self, element_data):
        """处理元素检查"""
        logger_helper.info(f"Element inspection: {element_data}")
    
    def on_performance_metrics(self, metrics):
        """处理性能指标"""
        logger_helper.info(f"Performance metrics: {metrics}")
    
    @Slot()
    def on_load_started(self):
        logger_helper.info("Page load started")
    
    @Slot(int)
    def on_load_progress(self, progress):
        logger_helper.info(f"Page load progress: {progress}%")
    
    @Slot(bool)
    def on_load_finished(self, success):
        if success:
            logger_helper.info("Page load completed successfully")
            # 获取当前页面标题
            title = self.web_engine.page().title()
            logger_helper.info(f"Page title: {title}")
            # 获取当前 URL
            url = self.web_engine.url().toString()
            logger_helper.info(f"Current URL: {url}")
            
            # 执行额外的检查
            def check_react_status(result):
                logger_helper.info(f"React status check result: {result}")
            
            self.web_engine.execute_script("""
                (function() {
                    console.log('Checking React application status...');
                    console.log('Root element:', document.getElementById('root'));
                    console.log('React version:', window.React?.version);
                    console.log('ReactDOM version:', window.ReactDOM?.version);
                    
                    // 确保 WebChannel 已初始化
                    if (window.bridge) {
                        console.log('WebChannel initialized successfully');
                    } else {
                        console.error('WebChannel not initialized');
                    }
                    
                    return {
                        rootElement: document.getElementById('root') ? 'Found' : 'Not found',
                        reactVersion: window.React?.version || 'Not found',
                        reactDOMVersion: window.ReactDOM?.version || 'Not found',
                        webChannelInitialized: !!window.bridge
                    };
                })();
            """, check_react_status)
        else:
            logger_helper.error("Page load failed")
    
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
            self.web_engine.reload_page()
        else:
            self.load_local_html() 