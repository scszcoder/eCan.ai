"""
WebEngine 核心模块，处理 Web 引擎相关的功能
"""
from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage, QWebEngineScript
from PySide6.QtCore import QUrl, Qt, Slot, Signal, QObject
from PySide6.QtWebChannel import QWebChannel
from utils.logger_helper import logger_helper as logger
from gui.core.request_interceptor import RequestInterceptor
from gui.ipc.webchannel_service import IPCWebChannelService
from gui.ipc.api import IPCAPI
from typing import Optional, Callable, Any, Dict, Union
from pathlib import Path
import os
import shutil

class CustomWebEnginePage(QWebEnginePage):
    def __init__(self, profile=None, parent=None):
        super().__init__(profile, parent)
        self.featurePermissionRequested.connect(self.onFeaturePermissionRequested)

    def onFeaturePermissionRequested(self, url, feature):
        # Uncomment to debug
        # print(f"Feature requested: {feature} at {url}")
        # Grant ALL permissions (camera, microphone, etc)
        self.setFeaturePermission(
            url, feature, QWebEnginePage.PermissionPolicy.PermissionGrantedByUser
        )


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
        QWebEngineSettings.FocusOnNavigationEnabled: True,
        QWebEngineSettings.JavascriptCanOpenWindows: True,  # 允许JS打开新窗口
        QWebEngineSettings.JavascriptCanAccessClipboard: True,  # 允许JS访问剪贴板
        QWebEngineSettings.AutoLoadImages: True,  # 自动加载图片
        QWebEngineSettings.JavascriptCanPaste: True,  # 允许JS粘贴
        QWebEngineSettings.Accelerated2dCanvasEnabled: True,  # 启用2D Canvas硬件加速
        QWebEngineSettings.WebGLEnabled: True,  # 启用WebGL
    }
    
    def __init__(self, parent: Optional[QMainWindow] = None):
        super().__init__(parent)
        # Use default profile or create a new one
        profile = QWebEngineProfile.defaultProfile()
        custom_page = CustomWebEnginePage(profile, self)
        self.setPage(custom_page)

        self._interceptor: Optional[RequestInterceptor] = None
        self._is_loading: bool = False
        self._last_error: Optional[str] = None
        self._channel: Optional[QWebChannel] = None
        self._ipc_webchannel_service: Optional[IPCWebChannelService] = None
        self._webchannel_script: Optional[QWebEngineScript] = None
        self.gui_top = parent
        # 1. 初始化引擎
        self.init_engine()
        
        # 2. 连接信号
        self.connect_signals()
        
        # 3. 设置拦截器
        self.setup_interceptor()
        
        # 4. 创建 IPC 服务（在页面初始化后）
        self._ipc_webchannel_service = IPCWebChannelService()

        # 5. 设置 WebChannel（在页面加载前）
        self.setup_webchannel()

        # # 6. 初始化 IPCAPI 单例
        self._ipc_api = IPCAPI(self._ipc_webchannel_service)

    def get_ipc_api(self):
        return self._ipc_api

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

    def setup_webchannel(self):
        """设置 WebChannel"""
        try:
            # 如果已经设置了 WebChannel，先清理
            if self._channel:
                self._cleanup_webchannel()

            # 获取 qwebchannel.js 内容
            qwc_js = self._get_qwebchannel_js()
            if not qwc_js:
                raise RuntimeError("Failed to get qwebchannel.js content")

            # 创建 WebChannel
            self._channel = QWebChannel()
            self.page().setWebChannel(self._channel)

            # 注册 IPC 服务
            self._channel.registerObject('ipc', self.ipc_webchannel_service)

            # 注入初始化脚本
            init_js = f'''
            {qwc_js}
            
            // 等待 DOM 加载完成
            if (document.readyState === 'loading') {{
                document.addEventListener('DOMContentLoaded', initWebChannel);
            }} else {{
                initWebChannel();
            }}
            
            function initWebChannel() {{
                console.log('Initializing WebChannel...');
                new QWebChannel(qt.webChannelTransport, channel => {{
                    console.log('WebChannel initialized, creating IPC object...');
                    window.ipc = channel.objects.ipc;
                    console.log('IPC object created:', window.ipc);
                    // 触发自定义事件通知前端 WebChannel 已就绪
                    window.dispatchEvent(new CustomEvent('webchannel-ready'));
                }});
            }}
            '''
            
            # 创建并注入脚本
            self._webchannel_script = QWebEngineScript()
            self._webchannel_script.setName('init-webchannel')
            self._webchannel_script.setInjectionPoint(QWebEngineScript.DocumentCreation)
            self._webchannel_script.setWorldId(QWebEngineScript.MainWorld)
            self._webchannel_script.setSourceCode(init_js)
            self.page().scripts().insert(self._webchannel_script)

            logger.info("WebChannel setup completed")
        except Exception as e:
            logger.error(f"Failed to setup WebChannel: {str(e)}")
            raise

    def _cleanup_webchannel(self):
        """清理 WebChannel 相关资源"""
        try:
            # 移除脚本
            if self._webchannel_script:
                self.page().scripts().remove(self._webchannel_script)
                self._webchannel_script = None

            # 清理 WebChannel
            if self._channel:
                self._channel.deleteLater()
                self._channel = None

            # 清理 IPC 服务
            if self._ipc_webchannel_service:
                self._ipc_webchannel_service.deleteLater()
                self._ipc_webchannel_service = None

            logger.info("WebChannel cleanup completed")
        except Exception as e:
            logger.error(f"Failed to cleanup WebChannel: {str(e)}")

    def _get_qwebchannel_js(self) -> Optional[str]:
        """获取 qwebchannel.js 内容"""
        try:
            # 从项目资源目录获取
            resource_path = os.path.join(os.path.dirname(__file__), 'resources', 'qwebchannel.js')
            if os.path.exists(resource_path):
                with open(resource_path, 'r', encoding='utf-8') as f:
                    return f.read()
            
            # 如果找不到，尝试从 PySide6 安装目录获取
            import PySide6
            pyside_path = os.path.dirname(PySide6.__file__)
            src_qwc = os.path.join(pyside_path, 'qtwebchannel', 'qwebchannel.js')
            
            if os.path.exists(src_qwc):
                # 如果找到，复制到项目资源目录
                os.makedirs(os.path.dirname(resource_path), exist_ok=True)
                shutil.copy2(src_qwc, resource_path)
                with open(src_qwc, 'r', encoding='utf-8') as f:
                    return f.read()
            
            logger.error("qwebchannel.js not found in any location")
            return None
        except Exception as e:
            logger.error(f"Error getting qwebchannel.js: {str(e)}")
            return None

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
            # 重新加载页面
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

    @property
    def ipc_webchannel_service(self) -> Optional[IPCWebChannelService]:
        """获取 IPC 服务"""
        return self._ipc_webchannel_service 