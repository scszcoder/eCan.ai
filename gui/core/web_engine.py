"""
WebEngine 核心模块，处理 Web 引擎相关的功能
"""

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtCore import QUrl, Qt, Slot
from utils.logger_helper import logger_helper
from gui.core.request_interceptor import RequestInterceptor

logger = logger_helper.logger

class WebEngine(QWebEngineView):
    """WebEngine 类，封装了 Web 引擎的核心功能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_engine()
        self.connect_signals()
        self.setup_interceptor()
    
    def init_engine(self):
        """初始化 Web 引擎"""
        # 配置页面
        page = self.page()
        page.setBackgroundColor(Qt.white)
        
        # 配置 WebEngine 设置
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
        profile.setHttpCacheType(QWebEngineProfile.NoCache)
        
        # 允许本地文件访问
        settings = page.settings()
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        settings.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.AllowRunningInsecureContent, True)
        settings.setAttribute(QWebEngineSettings.AllowGeolocationOnInsecureOrigins, True)
    
    def setup_interceptor(self):
        """设置请求拦截器"""
        interceptor = RequestInterceptor()
        self.page().profile().setUrlRequestInterceptor(interceptor)
        logger.info("Request interceptor setup completed")
    
    def connect_signals(self):
        """连接信号"""
        self.loadStarted.connect(self.on_load_started)
        self.loadProgress.connect(self.on_load_progress)
        self.loadFinished.connect(self.on_load_finished)
    
    @Slot()
    def on_load_started(self):
        """页面开始加载时的处理"""
        logger.info("Page load started")
    
    @Slot(int)
    def on_load_progress(self, progress):
        """页面加载进度处理"""
        logger.info(f"Page load progress: {progress}%")
    
    @Slot(bool)
    def on_load_finished(self, success):
        """页面加载完成时的处理"""
        if success:
            logger.info("Page load completed successfully")
            # 获取当前页面标题
            title = self.page().title()
            logger.info(f"Page title: {title}")
            # 获取当前 URL
            url = self.url().toString()
            logger.info(f"Current URL: {url}")
        else:
            logger.error("Page load failed")
    
    def inject_script(self, script):
        """注入 JavaScript 代码"""
        self.page().runJavaScript(script)
    
    def execute_script(self, script, callback=None):
        """执行 JavaScript 代码"""
        self.page().runJavaScript(script, callback)
    
    def load_local_file(self, file_path):
        """加载本地文件"""
        url = QUrl.fromLocalFile(file_path)
        self.load(url)
        logger.info(f"Loading local file: {file_path}")
    
    def load_url(self, url):
        """加载 URL"""
        self.load(QUrl(url))
        logger.info(f"Loading URL: {url}")
    
    def reload_page(self):
        """重新加载页面"""
        self.reload()
        logger.info("Page reloaded") 