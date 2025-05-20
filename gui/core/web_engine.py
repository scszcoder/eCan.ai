"""
WebEngine 核心模块，处理 Web 引擎相关的功能
"""

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtCore import QUrl, Qt
from PySide6.QtWebChannel import QWebChannel
import logging

logger = logging.getLogger(__name__)

class WebEngine(QWebEngineView):
    """WebEngine 类，封装了 Web 引擎的核心功能"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_engine()
    
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
    
    def setup_web_channel(self, handler):
        """设置 WebChannel"""
        channel = QWebChannel(self.page())
        channel.registerObject("bridge", handler)
        self.page().setWebChannel(channel)
        logger.info("WebChannel setup completed")
    
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