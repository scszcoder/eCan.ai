from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QDockWidget, 
                             QTextEdit, QTabWidget, QSplitter)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import QUrl, Qt, Signal, Slot, QObject, Property
from PySide6.QtGui import QAction, QKeySequence, QTextCursor
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings, QWebEngineUrlRequestInterceptor, QWebChannel
from pathlib import Path
import os
import datetime
import sys
import logging
import json

# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ['OBJC_DISABLE_INITIALIZE_FORK_SAFETY'] = 'YES'
    logging.getLogger('PySide6').setLevel(logging.ERROR)

from config.app_settings import app_settings
from utils.logger_helper import logger_helper
from gui.ipc import IPCHandler, WebRequestHandler

class DevToolsWindow(QDockWidget):
    def __init__(self, parent=None):
        super().__init__("开发者工具", parent)
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        
        # 创建中心部件
        central_widget = QWidget()
        self.setWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        
        # 控制台标签页
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setLineWrapMode(QTextEdit.NoWrap)
        self.console.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.tab_widget.addTab(self.console, "控制台")
        
        # 网络标签页
        self.network = QTextEdit()
        self.network.setReadOnly(True)
        self.network.setLineWrapMode(QTextEdit.NoWrap)
        self.network.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.tab_widget.addTab(self.network, "网络")
        
        # 元素标签页
        self.elements = QTextEdit()
        self.elements.setReadOnly(True)
        self.elements.setLineWrapMode(QTextEdit.NoWrap)
        self.elements.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: monospace;
                font-size: 12px;
            }
        """)
        self.tab_widget.addTab(self.elements, "元素")
        
        layout.addWidget(self.tab_widget)
        
        # 设置初始大小
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
    
    def append_log(self, message, level="INFO"):
        """添加日志到控制台"""
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        color = {
            "INFO": "#6A9955",    # 绿色
            "WARNING": "#DCDCAA", # 黄色
            "ERROR": "#F44747",   # 红色
            "DEBUG": "#569CD6"    # 蓝色
        }.get(level, "#D4D4D4")  # 默认白色
        
        formatted_message = f'<span style="color: {color}">[{timestamp}] {level}: {message}</span><br>'
        
        self.console.append(formatted_message)
        # 滚动到底部
        self.console.moveCursor(QTextCursor.End)
    
    def clear_logs(self):
        """清除所有日志"""
        self.console.clear()
        self.network.clear()
        self.elements.clear()

class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        # 添加 CORS 头
        info.setHttpHeader(b"Access-Control-Allow-Origin", b"*")
        info.setHttpHeader(b"Access-Control-Allow-Methods", b"GET, POST, PUT, DELETE, OPTIONS")
        info.setHttpHeader(b"Access-Control-Allow-Headers", b"Content-Type, Authorization")
        info.setHttpHeader(b"Access-Control-Allow-Credentials", b"true")

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
        
        # 创建开发者工具窗口
        self.dev_tools = DevToolsWindow(self)
        self.addDockWidget(Qt.BottomDockWidgetArea, self.dev_tools)
        self.dev_tools.hide()  # 默认隐藏
        
        # 创建 IPC 处理器
        self.ipc_handler = IPCHandler(self)
        
        # 创建 Web 请求处理器
        self.web_request = WebRequestHandler(self.ipc_handler)
        
        # 设置页面
        page = self.web_view.page()
        channel = QWebChannel(page)
        channel.registerObject("bridge", self.ipc_handler)
        page.setWebChannel(channel)
        page.setBackgroundColor(Qt.white)  # 设置背景色
        
        # 配置 WebEngine 设置
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.NoCache)
        
        # 设置请求拦截器
        interceptor = RequestInterceptor()
        profile.setUrlRequestInterceptor(interceptor)
        
        # 允许本地文件访问
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.AllowGeolocationOnInsecureOrigins, True)
        
        # 连接信号
        self.web_view.loadStarted.connect(self.on_load_started)
        self.web_view.loadProgress.connect(self.on_load_progress)
        self.web_view.loadFinished.connect(self.on_load_finished)
        self.web_view.loadStarted.connect(lambda: logger_helper.info("Page load started"))
        self.web_view.loadFinished.connect(lambda ok: logger_helper.info(f"Page load finished: {'success' if ok else 'failed'}"))
        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger_helper.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_view.setUrl(QUrl(web_url))
                logger_helper.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger_helper.error("Failed to get web URL")
        
        # 添加 Web 视图到布局
        layout.addWidget(self.web_view)
        
        # 设置快捷键
        self.setup_shortcuts()
    
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
                base_url = QUrl.fromLocalFile(str(app_settings.dist_dir.absolute()))
                logger_helper.info(f"Base URL: {base_url.toString()}")
                
                # 注入 WebChannel 和调试代码
                webchannel_script = """
                <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
                <script>
                    // 初始化 WebChannel
                    new QWebChannel(qt.webChannelTransport, function(channel) {
                        window.bridge = channel.objects.bridge;
                        
                        // 监听来自 Python 的消息
                        bridge.dataReceived.connect(function(message) {
                            try {
                                const data = JSON.parse(message);
                                console.log('Received from Python:', data);
                                // 处理来自 Python 的消息
                                if (data.type === 'response') {
                                    handlePythonResponse(data);
                                }
                            } catch (e) {
                                console.error('Error parsing message from Python:', e);
                            }
                        });
                        
                        // 发送消息到 Python 的函数
                        window.sendToPython = function(message) {
                            if (typeof message === 'object') {
                                message = JSON.stringify(message);
                            }
                            bridge.sendToPython(message);
                        };
                        
                        // 处理来自 Python 的响应
                        function handlePythonResponse(data) {
                            // 根据响应类型处理数据
                            switch(data.responseType) {
                                case 'command_result':
                                    console.log('Command result:', data.result);
                                    break;
                                case 'request_result':
                                    console.log('Request result:', data.result);
                                    break;
                                default:
                                    console.log('Unknown response type:', data);
                            }
                        }
                    });
                </script>
                """
                
                # 在 </head> 标签前插入 WebChannel 代码
                html_content = html_content.replace('</head>', f'{webchannel_script}</head>')
                
                # 修改资源路径为绝对路径
                html_content = html_content.replace('src="./', f'src="file://{app_settings.dist_dir}/')
                html_content = html_content.replace('href="./', f'href="file://{app_settings.dist_dir}/')
                
                # 加载 HTML 内容
                self.web_view.page().setHtml(html_content, base_url)
                logger_helper.info(f"Production mode: Loading from {index_path}, {base_url}")
                
                # 检查资源文件是否存在
                assets_dir = app_settings.dist_dir / "assets"
                if assets_dir.exists():
                    logger_helper.info(f"Assets directory exists at: {assets_dir}")
                    for item in assets_dir.iterdir():
                        logger_helper.info(f"Found asset: {item.name}")
                else:
                    logger_helper.error(f"Assets directory not found at: {assets_dir}")
                
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
    
    def on_console_message(self, level, message, line, source):
        """处理 JavaScript 控制台消息"""
        level_str = {
            QWebEnginePage.InfoMessageLevel: "INFO",
            QWebEnginePage.WarningMessageLevel: "WARNING",
            QWebEnginePage.ErrorMessageLevel: "ERROR"
        }.get(level, "UNKNOWN")
        
        log_message = f"{message} (at {source}:{line})"
        logger_helper.info(log_message)
        
        # 在开发者工具中显示消息
        if self.dev_tools.isVisible():
            self.dev_tools.append_log(log_message, level_str)
    
    @Slot()
    def on_load_started(self):
        logger_helper.info("Page load started")
        if self.dev_tools.isVisible():
            self.dev_tools.append_log("Page load started", "INFO")
    
    @Slot(int)
    def on_load_progress(self, progress):
        logger_helper.info(f"Page load progress: {progress}%")
        if self.dev_tools.isVisible():
            self.dev_tools.append_log(f"Page load progress: {progress}%", "INFO")
    
    @Slot(bool)
    def on_load_finished(self, success):
        if success:
            logger_helper.info("Page load completed successfully")
            # 获取当前页面标题
            title = self.web_view.page().title()
            logger_helper.info(f"Page title: {title}")
            # 获取当前 URL
            url = self.web_view.url().toString()
            logger_helper.info(f"Current URL: {url}")
            
            if self.dev_tools.isVisible():
                self.dev_tools.append_log("Page load completed successfully", "INFO")
                self.dev_tools.append_log(f"Page title: {title}", "INFO")
                self.dev_tools.append_log(f"Current URL: {url}", "INFO")
            
            # 执行额外的检查
            self.web_view.page().runJavaScript("""
                (function() {
                    console.log('Checking React application status...');
                    console.log('Root element:', document.getElementById('root'));
                    console.log('React version:', window.React?.version);
                    console.log('ReactDOM version:', window.ReactDOM?.version);
                })();
            """)
        else:
            logger_helper.error("Page load failed")
            if self.dev_tools.isVisible():
                self.dev_tools.append_log("Page load failed", "ERROR")
    
    def setup_shortcuts(self):
        """设置快捷键"""
        # F12 打开开发者工具
        dev_tools_action = QAction(self)
        dev_tools_action.setShortcut(QKeySequence('F12'))
        dev_tools_action.triggered.connect(self.toggle_dev_tools)
        self.addAction(dev_tools_action)
        
        # F5 重新加载
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L 清除日志
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools.clear_logs)
        self.addAction(clear_logs_action)
        
    def toggle_dev_tools(self):
        """切换开发者工具"""
        logger_helper.info("Toggling developer tools...")
        if self.dev_tools.isVisible():
            self.dev_tools.hide()
        else:
            self.dev_tools.show()
        
    def reload(self):
        """重新加载页面"""
        logger_helper.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_view.reload()
        else:
            self.load_local_html() 