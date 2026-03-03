"""
WebEngine core module for handling Web engine related functionality
"""
from PySide6.QtWidgets import (QMainWindow, QApplication)

from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings, QWebEnginePage, QWebEngineScript
from PySide6.QtCore import QUrl, Qt, Slot, Signal
from utils.logger_helper import logger_helper as logger
from gui.core.request_interceptor import RequestInterceptor
from gui.ipc.api import IPCAPI
from typing import Optional, Callable, Any, Dict, Union
from pathlib import Path
import os
import sys
import shutil
import logging
from logging.handlers import RotatingFileHandler
from config.app_info import app_info


class CustomWebEnginePage(QWebEnginePage):
    # Class-level browser console logger
    _browser_console_logger = None
    
    @classmethod
    def _setup_browser_console_logger(cls):
        """Setup a separate logger for browser console messages (development only)"""
        if cls._browser_console_logger is not None:
            return cls._browser_console_logger
        
        try:
            from config.app_settings import app_settings
            if not app_settings.is_dev_mode:
                logger.info("[WebEngine] Browser console logging disabled (not in dev mode)")
                return None
        except Exception as e:
            logger.warning(f"[WebEngine] Failed to check dev mode, disabling browser console logging: {e}")
            return None
        
        try:
            # Get log directory from app_info (same as ecan.log)
            appdata_path = app_info.appdata_path
            runlogs_dir = os.path.join(appdata_path, "runlogs")
            if not os.path.isdir(runlogs_dir):
                os.makedirs(runlogs_dir, exist_ok=True)
            
            log_file = os.path.join(runlogs_dir, "browser_console.log")
            
            # Create dedicated logger for browser console
            browser_logger = logging.getLogger("BrowserConsole")
            browser_logger.setLevel(logging.DEBUG)
            browser_logger.propagate = False  # Don't propagate to root logger
            
            # Remove existing handlers if any
            browser_logger.handlers.clear()
            
            # Add file handler with rotation (same settings as ecan.log)
            file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=1024 * 1024 * 10,  # 10MB
                backupCount=5,
                encoding='utf-8',
                errors='replace'
            )
            file_handler.setFormatter(file_formatter)
            browser_logger.addHandler(file_handler)
            
            cls._browser_console_logger = browser_logger
            logger.info(f"[WebEngine] Browser console logger initialized: {log_file}")
            return browser_logger
            
        except Exception as e:
            logger.error(f"[WebEngine] Failed to setup browser console logger: {e}")
            return None
    
    def __init__(self, profile=None, parent=None):
        super().__init__(profile, parent)
        self.featurePermissionRequested.connect(self.onFeaturePermissionRequested)
        self._enable_console_capture = False
        self._browser_logger = None

    def enable_console_capture(self, enable: bool = True):
        """Enable or disable console message capture (for development)"""
        self._enable_console_capture = enable
        if enable:
            # Setup browser console logger when enabling capture
            self._browser_logger = self._setup_browser_console_logger()
            logger.info("[WebEngine] Console message capture enabled")
        else:
            self._browser_logger = None
            logger.info("[WebEngine] Console message capture disabled")

    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
        """
        Capture JavaScript console messages from the web page.
        This method is called whenever console.log/warn/error is used in the frontend.
        
        Args:
            level: QWebEnginePage.JavaScriptConsoleMessageLevel (InfoMessageLevel, WarningMessageLevel, ErrorMessageLevel)
            message: The console message string
            lineNumber: Line number where the message originated
            sourceID: Source file/URL where the message originated
        """
        if not self._enable_console_capture:
            return
        
        # Map Qt console levels to logger levels
        level_map = {
            QWebEnginePage.JavaScriptConsoleMessageLevel.InfoMessageLevel: "INFO",
            QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel: "WARNING",
            QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel: "ERROR"
        }
        
        level_str = level_map.get(level, "INFO")
        
        # Format the console message with source information
        source_info = f"{sourceID}:{lineNumber}" if sourceID else f"line {lineNumber}"
        formatted_msg = f"[WebConsole/{level_str}] {message} ({source_info})"
        
        # Log to browser console log file (development only)
        if self._browser_logger:
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                self._browser_logger.error(formatted_msg)
            elif level == QWebEnginePage.JavaScriptConsoleMessageLevel.WarningMessageLevel:
                self._browser_logger.warning(formatted_msg)
            else:
                self._browser_logger.info(formatted_msg)
        
        # Also log ERROR level to main ecan.log
        if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
            logger.error(formatted_msg)

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

    # Track temporary pages created by createWindow to prevent premature GC
    _temp_pages = None

    def createWindow(self, _type):
        """Handle JavaScript window.open calls without creating visible popup windows.
        
        IMPORTANT: The returned page is held by Chromium's C++ layer. We must NOT
        destroy it immediately via deleteLater() because Chromium may still access
        the page pointer after urlChanged fires. Instead, we use a delayed timer
        to give Chromium enough time to release its reference.
        """
        logger.debug(f"Window creation requested, type: {_type}")

        # Lazy-init the temp page tracking list
        if self._temp_pages is None:
            self._temp_pages = []

        # Create a temporary page to capture the target URL, then open in system browser
        temp_page = CustomWebEnginePage(self.profile(), self)
        self._temp_pages.append(temp_page)

        def _open_external(url):
            try:
                # Disconnect immediately to prevent multiple firings (e.g. redirects)
                try:
                    temp_page.urlChanged.disconnect(_open_external)
                except (RuntimeError, TypeError):
                    pass

                url_str = url.toString()
                if url_str and url_str.startswith(('http://', 'https://')):
                    import webbrowser
                    webbrowser.open(url_str)
                    logger.info(f"Opened external window.open URL in system browser: {url_str}")
            except Exception as e:
                logger.warning(f"Failed to open external URL from window.open: {e}")
            finally:
                # Schedule safe cleanup after a delay so Chromium can release its reference
                self._schedule_temp_page_cleanup(temp_page)

        # When the temp page receives a URL, handle it externally and dispose the page
        temp_page.urlChanged.connect(_open_external)
        return temp_page

    def _schedule_temp_page_cleanup(self, page):
        """Safely schedule cleanup of a temporary page after Chromium releases it."""
        from PySide6.QtCore import QTimer
        def _do_cleanup():
            try:
                if self._temp_pages and page in self._temp_pages:
                    self._temp_pages.remove(page)
                page.deleteLater()
                logger.debug("[createWindow] Temp page cleaned up safely")
            except (RuntimeError, TypeError):
                pass  # Page already destroyed or parent gone
        # 10 second delay gives Chromium plenty of time to release the page reference
        QTimer.singleShot(10000, _do_cleanup)


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
            
            # Enable console capture in development mode
            try:
                from config.app_settings import app_settings
                if app_settings.is_dev_mode:
                    custom_page.enable_console_capture(True)
                    logger.info("[WebEngine] Console capture enabled for development mode")
            except Exception as e:
                logger.warning(f"[WebEngine] Failed to check dev mode for console capture: {e}")

            self._interceptor: Optional[RequestInterceptor] = None
            self._is_loading: bool = False
            self._last_error: Optional[str] = None

            # 1. Initialize engine
            self.init_engine()

            # 2. Connect signals
            self.connect_signals()

            # 3. Setup interceptor
            self.setup_interceptor()

            # 4. Initialize IPCAPI singleton
            self._ipc_api = IPCAPI()

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