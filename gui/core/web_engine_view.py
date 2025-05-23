"""
WebEngine 核心模块，处理 Web 引擎相关的功能
"""

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage
from PySide6.QtCore import QUrl, Qt, Slot, Signal, QObject
from utils.logger_helper import logger_helper
from gui.core.request_interceptor import RequestInterceptor
from typing import Optional, Callable, Any, Dict, Union
from pathlib import Path

logger = logger_helper.logger

class WebEngineView(QWebEngineView):
    """WebEngineView 类，封装了 Web 视图的核心功能"""
    
    # 定义信号
    load_error = Signal(str)  # 加载错误信号
    js_error = Signal(str)    # JavaScript 错误信号
    title_changed = Signal(str)  # 标题变化信号
    url_changed = Signal(str)    # URL 变化信号
    
    # 默认的 WebEngine 设置
    DEFAULT_SETTINGS: Dict[QWebEngineSettings.WebAttribute, bool] = {
        QWebEngineSettings.LocalContentCanAccessFileUrls: True,
        QWebEngineSettings.LocalContentCanAccessRemoteUrls: True,
        QWebEngineSettings.JavascriptEnabled: True,
        QWebEngineSettings.LocalStorageEnabled: True,
        QWebEngineSettings.AllowRunningInsecureContent: True,
        QWebEngineSettings.AllowGeolocationOnInsecureOrigins: True,
        QWebEngineSettings.PluginsEnabled: True,
        QWebEngineSettings.FullScreenSupportEnabled: True,
        QWebEngineSettings.ScreenCaptureEnabled: True,
        QWebEngineSettings.WebGLEnabled: True,
        QWebEngineSettings.ScrollAnimatorEnabled: True,
        QWebEngineSettings.ErrorPageEnabled: True,
        QWebEngineSettings.FocusOnNavigationEnabled: True
    }
    
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._interceptor: Optional[RequestInterceptor] = None
        self._is_loading: bool = False
        self._last_error: Optional[str] = None
        
        self.init_engine()
        self.connect_signals()
        self.setup_interceptor()
    
    def init_engine(self):
        """初始化 Web 引擎"""
        try:
            # 配置页面
            page = self.page()
            page.setBackgroundColor(Qt.white)
            
            # 配置 WebEngine 设置
            profile = QWebEngineProfile.defaultProfile()
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
            profile.setHttpCacheType(QWebEngineProfile.NoCache)
            
            # 应用默认设置
            settings = page.settings()
            for attribute, value in self.DEFAULT_SETTINGS.items():
                settings.setAttribute(attribute, value)
            
            logger.info("Web engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize web engine: {str(e)}")
            raise
    
    def setup_interceptor(self):
        """设置请求拦截器"""
        try:
            self._interceptor = RequestInterceptor()
            self.page().profile().setUrlRequestInterceptor(self._interceptor)
            logger.info("Request interceptor setup completed")
        except Exception as e:
            logger.error(f"Failed to setup request interceptor: {str(e)}")
            raise
    
    def connect_signals(self):
        """连接信号"""
        self.loadStarted.connect(self.on_load_started)
        self.loadProgress.connect(self.on_load_progress)
        self.loadFinished.connect(self.on_load_finished)
        self.titleChanged.connect(self.on_title_changed)
        self.urlChanged.connect(self.on_url_changed)
    
    @Slot()
    def on_load_started(self):
        """页面开始加载时的处理"""
        self._is_loading = True
        self._last_error = None
        logger.info("Page load started")
    
    @Slot(int)
    def on_load_progress(self, progress: int):
        """页面加载进度处理"""
        logger.info(f"Page load progress: {progress}%")
    
    @Slot(bool)
    def on_load_finished(self, success: bool):
        """页面加载完成时的处理"""
        self._is_loading = False
        if success:
            logger.info("Page load completed successfully")
            # 获取当前页面标题
            title = self.page().title()
            logger.info(f"Page title: {title}")
            # 获取当前 URL
            url = self.url().toString()
            logger.info(f"Current URL: {url}")
        else:
            error_msg = f"Page load failed: {self._last_error or 'Unknown error'}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)
    
    @Slot(str)
    def on_title_changed(self, title: str):
        """页面标题变化时的处理"""
        logger.info(f"Page title changed: {title}")
        self.title_changed.emit(title)
    
    @Slot(QUrl)
    def on_url_changed(self, url: QUrl):
        """页面 URL 变化时的处理"""
        url_str = url.toString()
        logger.info(f"Page URL changed: {url_str}")
        self.url_changed.emit(url_str)
    
    def inject_script(self, script: str) -> None:
        """注入 JavaScript 代码"""
        try:
            self.page().runJavaScript(script)
            logger.debug(f"Injected script: {script[:100]}...")
        except Exception as e:
            error_msg = f"Failed to inject script: {str(e)}"
            logger.error(error_msg)
            self.js_error.emit(error_msg)
    
    def execute_script(self, script: str, callback: Optional[Callable[[Any], None]] = None) -> None:
        """执行 JavaScript 代码"""
        try:
            self.page().runJavaScript(script, callback)
            logger.debug(f"Executed script: {script[:100]}...")
        except Exception as e:
            error_msg = f"Failed to execute script: {str(e)}"
            logger.error(error_msg)
            self.js_error.emit(error_msg)
    
    def load_local_file(self, file_path: Union[str, Path]) -> None:
        """加载本地文件"""
        try:
            if isinstance(file_path, str):
                file_path = Path(file_path)
            
            if not file_path.exists():
                raise FileNotFoundError(f"File not found: {file_path}")
            
            url = QUrl.fromLocalFile(str(file_path.absolute()))
            self.load(url)
            logger.info(f"Loading local file: {file_path}")
        except Exception as e:
            error_msg = f"Failed to load local file: {str(e)}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)
    
    def load_url(self, url: str) -> None:
        """加载 URL"""
        try:
            self.load(QUrl(url))
            logger.info(f"Loading URL: {url}")
        except Exception as e:
            error_msg = f"Failed to load URL: {str(e)}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)
    
    def reload_page(self) -> None:
        """重新加载页面"""
        try:
            self.reload()
            logger.info("Page reloaded")
        except Exception as e:
            error_msg = f"Failed to reload page: {str(e)}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)
    
    @property
    def is_loading(self) -> bool:
        """获取页面是否正在加载"""
        return self._is_loading
    
    @property
    def last_error(self) -> Optional[str]:
        """获取最后一次错误信息"""
        return self._last_error
    
    @property
    def interceptor(self) -> Optional[RequestInterceptor]:
        """获取请求拦截器"""
        return self._interceptor 