"""
WebEngine core module for handling Web engine related functionality
"""
from PySide6.QtWidgets import (QMainWindow)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage, QWebEngineScript
from PySide6.QtCore import QUrl, Qt, Slot, Signal
from PySide6.QtWebChannel import QWebChannel
from utils.logger_helper import logger_helper as logger
from gui.core.request_interceptor import RequestInterceptor
from gui.ipc.wc_service import IPCWCService
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

    def acceptNavigationRequest(self, url, _type, isMainFrame):
        url_str = url.toString()
        logger.info(f"Navigation request: {url_str}, type: {_type}, isMainFrame: {isMainFrame}")

        # Only intercept external links clicked by user, not main page
        MAIN_URLS = {"http://localhost:3000", "http://localhost:3000/"}
        if (
            _type == QWebEnginePage.NavigationTypeLinkClicked
            and url_str.startswith(('http://', 'https://'))
            and url_str not in MAIN_URLS
        ):
            logger.info(f"External link detected: {url_str}")
            try:
                import webbrowser
                webbrowser.open(url_str)
                logger.info(f"Successfully opened external link in system browser: {url_str}")
                return False  # Block opening in WebEngine
            except Exception as e:
                logger.error(f"Failed to open external link '{url_str}' in system browser: {e}")
                logger.info(f"Falling back to WebEngine for external link: {url_str}")
                return True

        # Allow WebEngine normal navigation in other cases
        logger.debug(f"Allowing navigation: {url_str}")
        return True

    def createWindow(self, _type):
        """Handle JavaScript window.open calls"""
        logger.debug(f"Window creation requested, type: {_type}")

        # Create a new page instance so acceptNavigationRequest can be triggered
        # Note: Need to ensure new page also has correct acceptNavigationRequest handling
        new_page = CustomWebEnginePage(self.profile(), self)

        # Connect new page signals
        new_page.loadFinished.connect(lambda success: logger.debug(f"New page load finished: {success}"))

        return new_page


class WebEngineView(QWebEngineView):
    """WebEngineView class that encapsulates core Web view functionality"""

    # Define signals
    load_error = Signal(str)  # Load error signal
    js_error = Signal(str)    # JavaScript error signal
    title_changed = Signal(str)  # Title change signal
    url_changed = Signal(str)    # URL change signal

    # Default WebEngine settings
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
        QWebEngineSettings.JavascriptCanOpenWindows: True,  # Allow JS to open new windows
        QWebEngineSettings.JavascriptCanAccessClipboard: True,  # Allow JS to access clipboard
        QWebEngineSettings.AutoLoadImages: True,  # Auto load images
        QWebEngineSettings.JavascriptCanPaste: True,  # Allow JS to paste
        QWebEngineSettings.Accelerated2dCanvasEnabled: True,  # Enable 2D Canvas hardware acceleration
        QWebEngineSettings.WebGLEnabled: True,  # Enable WebGL
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
        self._ipc_wc_service: Optional[IPCWCService] = None
        self._webchannel_script: Optional[QWebEngineScript] = None

        # 1. Initialize engine
        self.init_engine()

        # 2. Connect signals
        self.connect_signals()

        # 3. Setup interceptor
        self.setup_interceptor()

        # 4. Create IPC service (after page initialization)
        self._ipc_wc_service = IPCWCService()

        # 5. Setup WebChannel (before page loading)
        self.setup_webchannel()

        # # 6. Initialize IPCAPI singleton
        self._ipc_api = IPCAPI(self._ipc_wc_service)

    def get_ipc_api(self):
        return self._ipc_api

    def init_engine(self):
        """Initialize Web engine"""
        try:
            # Configure page
            page = self.page()
            page.setBackgroundColor(Qt.white)

            # Configure WebEngine settings
            profile = QWebEngineProfile.defaultProfile()
            profile.setPersistentCookiesPolicy(QWebEngineProfile.NoPersistentCookies)
            profile.setHttpCacheType(QWebEngineProfile.NoCache)

            # Apply default settings
            settings = page.settings()
            for attribute, value in self.DEFAULT_SETTINGS.items():
                settings.setAttribute(attribute, value)

            logger.info("Web engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize web engine: {str(e)}")
            raise

    def setup_webchannel(self):
        """Setup WebChannel"""
        try:
            # If WebChannel is already setup, clean it up first
            if self._channel:
                self._cleanup_webchannel()

            # Get qwebchannel.js content
            qwc_js = self._get_qwebchannel_js()
            if not qwc_js:
                raise RuntimeError("Failed to get qwebchannel.js content")

            # Create WebChannel
            self._channel = QWebChannel()
            self.page().setWebChannel(self._channel)

            # Register IPC service
            self._channel.registerObject('ipc', self._ipc_wc_service)

            # Inject initialization script
            init_js = f'''
            {qwc_js}

            // Wait for DOM to load
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
                    // Trigger custom event to notify frontend that WebChannel is ready
                    window.dispatchEvent(new CustomEvent('webchannel-ready'));
                }});
            }}
            '''

            # Create and inject script
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
        """Cleanup WebChannel related resources"""
        try:
            # Remove script
            if self._webchannel_script:
                self.page().scripts().remove(self._webchannel_script)
                self._webchannel_script = None

            # Cleanup WebChannel
            if self._channel:
                self._channel.deleteLater()
                self._channel = None

            # Cleanup IPC service
            if self._ipc_wc_service:
                self._ipc_wc_service.deleteLater()
                self._ipc_wc_service = None

            logger.info("WebChannel cleanup completed")
        except Exception as e:
            logger.error(f"Failed to cleanup WebChannel: {str(e)}")

    def _get_qwebchannel_js(self) -> Optional[str]:
        """Get qwebchannel.js content"""
        try:
            # Get from project resource directory
            resource_path = os.path.join(os.path.dirname(__file__), 'resources', 'qwebchannel.js')
            if os.path.exists(resource_path):
                with open(resource_path, 'r', encoding='utf-8') as f:
                    return f.read()

            # If not found, try to get from PySide6 installation directory
            import PySide6
            pyside_path = os.path.dirname(PySide6.__file__)
            src_qwc = os.path.join(pyside_path, 'qtwebchannel', 'qwebchannel.js')

            if os.path.exists(src_qwc):
                # If found, copy to project resource directory
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
        """Setup request interceptor"""
        try:
            self._interceptor = RequestInterceptor()
            self.page().profile().setUrlRequestInterceptor(self._interceptor)
            logger.info("Request interceptor setup completed")
        except Exception as e:
            logger.error(f"Failed to setup request interceptor: {str(e)}")
            raise

    def connect_signals(self):
        """Connect signals"""
        self.loadStarted.connect(self.on_load_started)
        self.loadProgress.connect(self.on_load_progress)
        self.loadFinished.connect(self.on_load_finished)
        self.titleChanged.connect(self.on_title_changed)
        self.urlChanged.connect(self.on_url_changed)
    
    @Slot()
    def on_load_started(self):
        """Handle page load start"""
        self._is_loading = True
        self._last_error = None
        logger.info("Page load started")

    @Slot(int)
    def on_load_progress(self, progress: int):
        """Handle page load progress"""
        logger.info(f"Page load progress: {progress}%")

    @Slot(bool)
    def on_load_finished(self, success: bool):
        """Handle page load completion"""
        self._is_loading = False
        if success:
            logger.info("Page load completed successfully")
            # Get current page title
            title = self.page().title()
            logger.info(f"Page title: {title}")
            # Get current URL
            url = self.url().toString()
            logger.info(f"Current URL: {url}")
        else:
            error_msg = f"Page load failed: {self._last_error or 'Unknown error'}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)

    @Slot(str)
    def on_title_changed(self, title: str):
        """Handle page title change"""
        logger.info(f"Page title changed: {title}")
        self.title_changed.emit(title)

    @Slot(QUrl)
    def on_url_changed(self, url: QUrl):
        """Handle page URL change"""
        url_str = url.toString()
        logger.info(f"Page URL changed: {url_str}")
        self.url_changed.emit(url_str)
    
    def inject_script(self, script: str) -> None:
        """Inject JavaScript code"""
        try:
            self.page().runJavaScript(script)
            logger.debug(f"Injected script: {script[:100]}...")
        except Exception as e:
            error_msg = f"Failed to inject script: {str(e)}"
            logger.error(error_msg)
            self.js_error.emit(error_msg)

    def execute_script(self, script: str, callback: Optional[Callable[[Any], None]] = None) -> None:
        """Execute JavaScript code"""
        try:
            self.page().runJavaScript(script, callback)
            logger.debug(f"Executed script: {script[:100]}...")
        except Exception as e:
            error_msg = f"Failed to execute script: {str(e)}"
            logger.error(error_msg)
            self.js_error.emit(error_msg)

    def load_local_file(self, file_path: Union[str, Path]) -> None:
        """Load local file"""
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
        """Load URL"""
        try:
            self.load(QUrl(url))
            logger.info(f"Loading URL: {url}")
        except Exception as e:
            error_msg = f"Failed to load URL: {str(e)}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)

    def reload_page(self) -> None:
        """Reload page"""
        try:
            # Reload page
            self.reload()
            logger.info("Page reloaded")
        except Exception as e:
            error_msg = f"Failed to reload page: {str(e)}"
            logger.error(error_msg)
            self.load_error.emit(error_msg)
    
    @property
    def is_loading(self) -> bool:
        """Get whether page is loading"""
        return self._is_loading

    @property
    def last_error(self) -> Optional[str]:
        """Get last error information"""
        return self._last_error

    @property
    def interceptor(self) -> Optional[RequestInterceptor]:
        """Get request interceptor"""
        return self._interceptor

    @property
    def ipc_wc_service(self) -> Optional[IPCWCService]:
        """Get IPC service"""
        return self._ipc_wc_service