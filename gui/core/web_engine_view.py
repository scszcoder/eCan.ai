"""
WebEngine core module for handling Web engine related functionality
"""
from PySide6.QtWidgets import (QMainWindow, QApplication)

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
import sys
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
        """Handle JavaScript window.open calls without creating visible popup windows"""
        logger.debug(f"Window creation requested, type: {_type}")

        # Create a temporary page to capture the target URL, then open in system browser
        temp_page = CustomWebEnginePage(self.profile(), self)

        def _open_external(url):
            try:
                url_str = url.toString()
                if url_str.startswith(('http://', 'https://')):
                    import webbrowser
                    webbrowser.open(url_str)
                    logger.info(f"Opened external window.open URL in system browser: {url_str}")
            except Exception as e:
                logger.warning(f"Failed to open external URL from window.open: {e}")
            finally:
                try:
                    temp_page.deleteLater()
                except Exception:
                    pass

        # When the temp page receives a URL, handle it externally and dispose the page
        temp_page.urlChanged.connect(_open_external)
        return temp_page


class WebEngineView(QWebEngineView):
    """WebEngineView class that encapsulates core Web view functionality"""

    # Define signals
    load_error = Signal(str)  # Load error signal
    js_error = Signal(str)    # JavaScript error signal
    title_changed = Signal(str)  # Title change signal
    url_changed = Signal(str)    # URL change signal

    # Default WebEngine settings (Qt API level)
    # Note: Qt WebEngine has built-in support for most features
    # Command line args are only needed for VM-specific GPU issues
    DEFAULT_SETTINGS: Dict[QWebEngineSettings.WebAttribute, bool] = {
        # File and network access
        QWebEngineSettings.LocalContentCanAccessFileUrls: True,
        QWebEngineSettings.LocalContentCanAccessRemoteUrls: True,
        QWebEngineSettings.AllowRunningInsecureContent: True,
        QWebEngineSettings.AllowGeolocationOnInsecureOrigins: True,

        # JavaScript capabilities
        QWebEngineSettings.JavascriptEnabled: True,
        QWebEngineSettings.JavascriptCanOpenWindows: True,
        QWebEngineSettings.JavascriptCanAccessClipboard: True,
        QWebEngineSettings.JavascriptCanPaste: True,

        # Storage and caching
        QWebEngineSettings.LocalStorageEnabled: True,

        # Media and plugins
        QWebEngineSettings.PluginsEnabled: True,
        QWebEngineSettings.AutoLoadImages: True,

        # Display and interaction
        QWebEngineSettings.FullScreenSupportEnabled: True,
        QWebEngineSettings.ScreenCaptureEnabled: True,
        QWebEngineSettings.ScrollAnimatorEnabled: True,
        QWebEngineSettings.FocusOnNavigationEnabled: True,

        # Graphics acceleration (Qt built-in support)
        QWebEngineSettings.Accelerated2dCanvasEnabled: True,  # Qt WebEngine built-in
        QWebEngineSettings.WebGLEnabled: True,                # Qt WebEngine built-in

        # Error handling
        QWebEngineSettings.ErrorPageEnabled: True,
    }

    # Class-level flag to track if WebEngine args have been configured
    _webengine_args_configured = False

    @classmethod
    def configure_webengine_args(cls):
        """
        Configure Qt WebEngine (Chromium) command line arguments.

        IMPORTANT: Only use command line arguments for settings that CANNOT be controlled
        via QWebEngineSettings API. Most features should be configured through DEFAULT_SETTINGS.

        Command line arguments are only needed for:
        1. GPU/Hardware acceleration control (especially for VM environments)
        2. Chromium-specific features not exposed in Qt API
        3. Engine-level debugging and logging

        This should be called before creating the first WebEngineView instance.
        """
        if cls._webengine_args_configured:
            logger.debug("WebEngine arguments already configured, skipping")
            return

        logger.info("Configuring WebEngine (Chromium) command line arguments...")

        # ONLY include arguments that CANNOT be set via QWebEngineSettings
        webengine_args = [
            # === GPU Control (NOT available in QWebEngineSettings) ===
            # These are critical for VM environments where GPU may be blacklisted
            '--ignore-gpu-blocklist',            # Ignore GPU driver blacklist (REQUIRED for VMs)
            '--disable-gpu-sandbox',             # Disable GPU process sandbox (helps in VMs)

            # === Debugging (NOT available in QWebEngineSettings) ===
            # Uncomment for debugging GPU/WebGL issues
            # '--enable-logging',
            # '--log-level=0',
        ]

        # CRITICAL: Use environment variable to pass arguments to Chromium
        # This is the ONLY reliable way to pass arguments in PySide6/Qt WebEngine
        flags_str = ' '.join(webengine_args)
        os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = flags_str

        # Also add to sys.argv as fallback (though environment variable is more reliable)
        sys.argv.extend(webengine_args)

        logger.info(f"✅ Added {len(webengine_args)} Chromium command line arguments (VM-specific)")
        logger.info(f"   QTWEBENGINE_CHROMIUM_FLAGS={flags_str}")
        logger.debug(f"WebEngine args: {webengine_args}")

        cls._webengine_args_configured = True

    def __init__(self, parent: Optional[QMainWindow] = None):
        try:
            logger.info("Starting WebEngineView initialization...")

            # Configure WebEngine arguments before first instantiation
            WebEngineView.configure_webengine_args()

            # Ensure QApplication is properly initialized before WebEngine
            app = QApplication.instance()
            if not app:
                logger.error("QApplication not found during WebEngine initialization")
                raise RuntimeError("QApplication must be created before WebEngine initialization")

            # Process any pending events to ensure Qt is fully initialized
            app.processEvents()

            super().__init__(parent)

            # Use a persistent named profile
            logger.info("Creating WebEngine profile...")
            try:
                # Create a named profile for persistence
                # Using a string name makes it persistent (saves cookies, localStorage, cache to disk)
                profile = QWebEngineProfile("eCanProfile", parent)
                
                # Ensure persistence settings are enabled
                profile.setPersistentCookiesPolicy(QWebEngineProfile.AllowPersistentCookies)
                profile.setHttpCacheType(QWebEngineProfile.DiskHttpCache)
                
                logger.info("WebEngine persistent profile 'eCanProfile' created successfully")
            except Exception as e:
                logger.error(f"Failed to create WebEngine profile: {e}")
                # Fallback to default profile if creation fails
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

            logger.info("WebEngineView initialization completed successfully")
        except Exception as e:
            logger.error(f"Failed to initialize WebEngineView: {e}")
            logger.error(f"Exception type: {type(e).__name__}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise

    def get_ipc_api(self):
        return self._ipc_api

    def init_engine(self):
        """Initialize Web engine"""
        try:
            # Configure page
            page = self.page()
            page.setBackgroundColor(Qt.white)

            # Configure WebEngine settings - use the profile from page
            profile = page.profile()
            if not profile:
                logger.warning("Could not get profile from page, skipping profile configuration")

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
            # Use Deferred instead of DocumentCreation to prevent multiple executions
            # Deferred runs after DOM is loaded, once per page load
            # This prevents duplicate IPC connections when page refreshes or HMR occurs
            self._webchannel_script.setInjectionPoint(QWebEngineScript.Deferred)
            self._webchannel_script.setWorldId(QWebEngineScript.MainWorld)
            self._webchannel_script.setSourceCode(init_js)
            self.page().scripts().insert(self._webchannel_script)

            logger.info("WebChannel setup completed with Deferred injection point")
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