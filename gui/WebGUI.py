from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox, QApplication, QHBoxLayout, QLabel, QPushButton, QMenuBar
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QIcon, QPixmap
from PySide6.QtCore import Qt
from typing import Optional
from utils.time_util import TimeUtil
import sys
import os
from gui.menu_manager import MenuManager

# Windows-specific imports for resize handling
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

from config.app_settings import app_settings
from utils.logger_helper import logger_helper as logger
from gui.core.web_engine_view import WebEngineView

from app_context import AppContext


# Configure logging to suppress macOS IMK warnings
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"


# Internationalization for WebGUI
class WebGUIMessages:
    """Simple i18n support for WebGUI status and error messages."""

    DEFAULT_LANG = 'zh-CN'

    MESSAGES = {
        'en-US': {
            'initializing_webgui': 'Initializing WebGUI...',
            'creating_layout': 'Creating interface layout...',
            'init_web_engine': 'Initializing web engine...',
            'setup_dev_tools': 'Setting up developer tools...',
            'config_window_style': 'Configuring window style...',
            'connecting_web_engine': 'Connecting web engine...',
            'loading_progress': 'Loading {progress}%...',
            'error_page_title': 'Failed to Load',
            'error_page_subtitle': 'We encountered an error while loading the application',
            'possible_reasons': 'Possible reasons:',
            'reason_network': 'Network connection issue',
            'reason_config': 'Configuration error',
            'reason_resources': 'Missing required resources',
            'retry_button': 'Retry',
            'web_url_unavailable': 'Web URL not available',
            'init_error': 'Initialization error: {error}',
            'confirm_exit_title': 'Confirm Exit',
            'confirm_exit_message': 'Are you sure you want to exit the program?',
            'button_yes': 'Yes',
            'button_no': 'No',
        },
        'zh-CN': {
            'initializing_webgui': '初始化 WebGUI...',
            'creating_layout': '创建界面布局...',
            'init_web_engine': '初始化 Web 引擎...',
            'setup_dev_tools': '设置开发者工具...',
            'config_window_style': '配置窗口样式...',
            'connecting_web_engine': '连接 Web 引擎...',
            'loading_progress': '加载中 {progress}%...',
            'error_page_title': '加载失败',
            'error_page_subtitle': '在加载应用程序时遇到错误',
            'possible_reasons': '可能的原因：',
            'reason_network': '网络连接问题',
            'reason_config': '配置错误',
            'reason_resources': '缺少必需的资源',
            'retry_button': '重试',
            'web_url_unavailable': 'Web URL 不可用',
            'init_error': '初始化错误：{error}',
            'confirm_exit_title': '确认退出',
            'confirm_exit_message': '确定要退出程序吗？',
            'button_yes': '是',
            'button_no': '否',
        }
    }

    def __init__(self):
        from utils.i18n_helper import detect_language
        self.language = detect_language(
            default_lang=self.DEFAULT_LANG,
            supported_languages=list(self.MESSAGES.keys())
        )
        logger.info(f"[WebGUI] Language: {self.language}")

    def get(self, key: str, **kwargs) -> str:
        """Get localized message with optional formatting."""
        lang = self.language if self.language in self.MESSAGES else self.DEFAULT_LANG
        message = self.MESSAGES[lang].get(key, key)
        if kwargs:
            return message.format(**kwargs)
        return message


# Global instance - lazy initialization
_webgui_messages = None

def _get_webgui_messages():
    """Get WebGUIMessages instance with lazy initialization."""
    global _webgui_messages
    if _webgui_messages is None:
        _webgui_messages = WebGUIMessages()
    return _webgui_messages


class WebGUI(QMainWindow):
    def __init__(self, parent=None, splash=None, progress_callback=None):
        super().__init__()
        self.setWindowTitle("eCan.ai")
        self.parent = parent
        self._splash = splash
        self._progress_callback = progress_callback
        self._centered_once = False
        self._restoring_position = False  # prevent recursion during position restore
        self._last_center_pos = None    # guard against unintended (0,0) jumps
        self._taskbar_icon_set = False  # prevent repeated taskbar icon setup

        # Update progress if callback is available
        if self._progress_callback:
            self._progress_callback(30, _get_webgui_messages().get('initializing_webgui'))

        # Windows-specific optimizations to reduce flicker
        if sys.platform == 'win32':
            # Hide window during setup to prevent flicker
            self.setAttribute(Qt.WA_DontShowOnScreen, True)
            # Disable updates during initialization
            self.setUpdatesEnabled(False)

        # Set window size first, then center it
        self.resize(1200, 800)
        # Defer centering until the window is actually shown to avoid (0,0) jumps

        if self._progress_callback:
            self._progress_callback(74, _get_webgui_messages().get('creating_layout'))

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        if self._progress_callback:
            self._progress_callback(76, _get_webgui_messages().get('init_web_engine'))

        # Create web engine
        self.web_engine_view = WebEngineView(self)

        if self._progress_callback:
            self._progress_callback(78, _get_webgui_messages().get('setup_dev_tools'))

        # Developer tools manager will be created on-demand
        self.dev_tools_manager = None

        if self._progress_callback:
            self._progress_callback(80, _get_webgui_messages().get('config_window_style'))

        # Set Windows window style to match content theme
        self._setup_window_style()

        if self._progress_callback:
            self._progress_callback(82, _get_webgui_messages().get('connecting_web_engine'))

        # Wire splash updates to web load if provided
        if self._splash is not None:
            try:
                self.web_engine_view.loadProgress.connect(self._on_load_progress)
                self.web_engine_view.loadFinished.connect(self._on_load_finished)
            except Exception as e:
                logger.warning(f"Failed to bind splash to web view: {e}")

        # Get web URL
        try:
            web_url = app_settings.get_web_url()
            logger.info(f"Web URL from settings: {web_url}")

            if web_url:
                if app_settings.is_dev_mode:
                    # Development mode: use Vite dev server
                    logger.info(f"Development mode: Loading from {web_url}")
                    self.web_engine_view.load_url(web_url)
                else:
                    # Production mode: load local file
                    logger.info("Production mode: Loading local HTML file")
                    self.load_local_html()
            else:
                logger.error("Failed to get web URL - will show error page")
                self._show_error_page(_get_webgui_messages().get('web_url_unavailable'))

        except Exception as e:
            logger.error(f"Error during WebGUI initialization: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error_page(_get_webgui_messages().get('init_error', error=str(e)))

        # Add web engine to layout
        layout.addWidget(self.web_engine_view)
        layout.setSpacing(0)

        # Set up shortcuts (after all components initialized)
        self._setup_shortcuts()

        # Create custom title bar menu on Windows and Linux
        if sys.platform in ['win32', 'linux']:
            self._setup_custom_titlebar_with_menu()
        else:
            # Use standard menu bar on macOS
            self.menu_manager = MenuManager(self)
            self.menu_manager.setup_menu()

        # Windows-specific: Re-enable showing after setup is complete
        if sys.platform == 'win32':
            self.setAttribute(Qt.WA_DontShowOnScreen, False)
            self.setUpdatesEnabled(True)

        # Show behavior: if no splash, show immediately; else splash will call show on finished
        if self._splash is None:
            try:
                self.show()
                # Set Windows taskbar icon using IconManager (centralized, no duplicates)
                self._setup_taskbar_icon_via_manager()
            except Exception:
                pass

        # Start async preload in background after event loop is ready
        # 100ms delay ensures Qt event loop is running before creating async task
        # Preload will run during user login, making MainWindow startup instant
        from PySide6.QtCore import QTimer
        QTimer.singleShot(100, self._start_background_preload)

    def showEvent(self, event):
        """On first show: center+front immediately; always: reset cursors."""
        # Center BEFORE calling super to ensure correct position from the start
        try:
            if not self._centered_once:
                self._centered_once = True
                if sys.platform == 'win32':
                    try:
                        self.setAttribute(Qt.WA_DontShowOnScreen, False)
                    except Exception:
                        pass
                # Center immediately on first show
                if not self.isMaximized():
                    self._center_on_screen()
                # Process events to ensure position is applied
                QApplication.processEvents()
                self._bring_to_front()
        except Exception:
            pass

        super().showEvent(event)

        # Always ensure cursors are sane
        try:
            self.setCursor(Qt.ArrowCursor)
            if hasattr(self, 'centralWidget') and self.centralWidget():
                self.centralWidget().setCursor(Qt.ArrowCursor)
            if hasattr(self, 'web_engine_view'):
                self.web_engine_view.setCursor(Qt.ArrowCursor)
        except Exception:
            pass

    def _start_background_preload(self):
        """
        Start async preload in background after event loop is ready.
        This preloads heavy modules (MainWindow dependencies, crypto, database, etc.)
        while user is logging in, resulting in ~340x faster MainWindow startup.
        """
        try:
            import asyncio
            import threading
            from gui.async_preloader import start_async_preload

            logger.info(" [WebGUI] Starting async preload in background...")

            # Run async preload in a separate thread with its own event loop
            # This is necessary because Qt has its own event loop and doesn't run asyncio
            def _run_async_preload():
                loop = None
                try:
                    # Create new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)

                    # Run the preload coroutine (wait for completion)
                    loop.run_until_complete(start_async_preload(wait_for_completion=True))

                    # Get preload summary
                    from gui.async_preloader import get_preload_summary
                    summary = get_preload_summary()
                    success_count = summary.get('success_count', 0)
                    total_tasks = summary.get('total_tasks', 0)
                    total_time = summary.get('total_time', 0)

                    logger.info(f"✅ [WebGUI] Async preload completed: {success_count}/{total_tasks} tasks in {total_time:.2f}s")
                except Exception as e:
                    logger.warning(f"⚠️ [WebGUI] Async preload thread error: {e}")
                    import traceback
                    logger.warning(f"⚠️ [WebGUI] Traceback: {traceback.format_exc()}")
                finally:
                    # Ensure loop is properly closed
                    if loop is not None and not loop.is_closed():
                        try:
                            # Cancel any remaining tasks
                            pending = asyncio.all_tasks(loop)
                            for task in pending:
                                task.cancel()
                            # Wait for cancellations
                            if pending:
                                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        except Exception:
                            pass
                        finally:
                            loop.close()

            # Start preload in daemon thread (won't block app exit)
            preload_thread = threading.Thread(target=_run_async_preload, daemon=True, name="AsyncPreloadThread")
            preload_thread.start()
            logger.info("✅ [WebGUI] Async preload thread started")

        except Exception as e:
            logger.warning(f"⚠️ [WebGUI] Failed to start preload: {e}")
            import traceback
            logger.warning(f"⚠️ [WebGUI] Traceback: {traceback.format_exc()}")

    def move(self, *args):
        """Override move to prevent moving to (0,0) at source"""
        try:
            # Parse position from args
            if len(args) == 1:
                # QPoint argument
                pos = args[0]
                x, y = pos.x(), pos.y()
            elif len(args) == 2:
                # x, y arguments
                x, y = args[0], args[1]
            else:
                return super().move(*args)

            # Skip guard while maximized or fullscreen
            if self.isMaximized() or self.isFullScreen():
                return super().move(*args)

            # Block moves to (0,0) unless window is being initialized
            if x < 5 and y < 5 and hasattr(self, '_centered_once') and self._centered_once:
                # Debug log
                logger.warning(f"[WebGUI] 🛡️ BLOCKED move to ({x},{y}), staying at current position")

                # Ignore this move request - stay at current position
                if self._last_center_pos is not None:
                    return super().move(self._last_center_pos)
                return  # Don't move at all

            # Allow valid moves
            return super().move(*args)
        except Exception as e:
            logger.debug(f"[WebGUI] move() exception: {e}")
            return super().move(*args)

    def moveEvent(self, event):
        """Guard against unintended jumps to (0,0) by immediately restoring position."""
        try:
            # Skip guard while maximized or fullscreen so window can align to (0,0)
            if self.isMaximized() or self.isFullScreen():
                return super().moveEvent(event)

            # Skip if we're currently restoring position (prevent recursion)
            if self._restoring_position:
                return super().moveEvent(event)

            # Only guard if window is visible and initialized
            if self.isVisible() and hasattr(self, '_centered_once') and self._centered_once:
                pos = event.pos()

                # If moved to (0,0), immediately restore to saved position
                if pos.x() < 5 and pos.y() < 5 and self._last_center_pos is not None:
                    logger.warning(f"[WebGUI] Detected move to ({pos.x()}, {pos.y()}), restoring immediately")
                    # Set flag to prevent recursion
                    self._restoring_position = True
                    try:
                        # Call super first to process the event
                        super().moveEvent(event)
                        # Immediately restore position synchronously
                        super(WebGUI, self).move(self._last_center_pos)
                    finally:
                        # Clear flag
                        self._restoring_position = False
                    return
        except Exception as e:
            logger.debug(f"[WebGUI] moveEvent exception: {e}")
            self._restoring_position = False
        return super().moveEvent(event)

    def _center_on_screen(self):
        """Center the window on the PRIMARY screen with proper handling for frameless windows"""
        try:
            screen = QApplication.primaryScreen()
            if not screen:
                logger.debug("No primary screen found for centering")
                return

            sg = screen.availableGeometry()
            window_width = self.width()
            window_height = self.height()

            x = sg.center().x() - window_width // 2
            y = sg.center().y() - window_height // 2

            # Keep within available area
            x = max(sg.left(), min(x, sg.right() - window_width))
            y = max(sg.top(), min(y, sg.bottom() - window_height))

            logger.debug(f"Centering (primary) window: size=({window_width}, {window_height}), target=({x}, {y})")

            if sys.platform == 'win32' and self.windowFlags() & Qt.FramelessWindowHint:
                try:
                    import ctypes
                    hwnd = int(self.winId())
                    if hwnd:
                        user32 = ctypes.windll.user32
                        SWP_NOSIZE = 0x0001
                        SWP_NOZORDER = 0x0004
                        SWP_SHOWWINDOW = 0x0040
                        user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
                    else:
                        self.move(x, y)
                except Exception as api_e:
                    logger.debug(f"Windows API positioning failed, fallback to Qt move: {api_e}")
                    self.move(x, y)
            else:
                self.move(x, y)

            # Record final position
            QApplication.processEvents()
            final_pos = self.pos()
            try:
                from PySide6.QtCore import QPoint
                self._last_center_pos = QPoint(final_pos.x(), final_pos.y())
            except Exception:
                self._last_center_pos = final_pos
            logger.info(f"[WebGUI] ✅ Centered at ({final_pos.x()}, {final_pos.y()}), saved as guard position")
        except Exception as e:
            logger.debug(f"Failed to center window: {e}")

    # --- Splash handlers ---
    def _on_load_progress(self, progress: int):
        try:
            if self._splash is not None:
                self._splash.set_status(_get_webgui_messages().get('loading_progress', progress=progress))
                self._splash.set_progress(progress)
        except Exception:
            pass

    def _on_load_finished(self, success: bool):
        try:
            if self._splash is not None:
                self._splash.finish(self)
                self._splash = None
            # Show main window when ready
            self.show()
            # Ensure window icon is set after showing for taskbar display
            self._set_window_icon()
            # Set Windows taskbar icon using IconManager (centralized, no duplicates)
            self._setup_taskbar_icon_via_manager()
            # Bring to front once more after splash is gone
            self._bring_to_front()
        except Exception:
            try:
                self.show()
                # Try to set icon even if show failed
                self._set_window_icon()
            except Exception:
                pass

    def _show_error_page(self, error_message):
        """Show error page"""
        try:
            error_html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>eCan.ai - Error</title>
                <style>
                    body {{
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
                        background: #1a1a1a;
                        color: #ffffff;
                        display: flex;
                        justify-content: center;
                        align-items: center;
                        height: 100vh;
                        margin: 0;
                    }}
                    .error-container {{
                        text-align: center;
                        padding: 40px;
                        background: #2a2a2a;
                        border-radius: 10px;
                        box-shadow: 0 4px 20px rgba(0,0,0,0.3);
                    }}
                    h1 {{ color: #ff6b6b; }}
                    .error-message {{
                        margin: 20px 0;
                        padding: 15px;
                        background: #3a3a3a;
                        border-radius: 5px;
                        font-family: monospace;
                    }}
                    .retry-button {{
                        background: #4CAF50;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 5px;
                        cursor: pointer;
                        font-size: 16px;
                        margin-top: 20px;
                    }}
                    .retry-button:hover {{ background: #45a049; }}
                </style>
            </head>
            <body>
                <div class="error-container">
                    <h1>⚠️ {_get_webgui_messages().get('error_page_title')}</h1>
                    <p>{_get_webgui_messages().get('error_page_subtitle')}</p>
                    <div class="error-message">{error_message}</div>
                    <p>{_get_webgui_messages().get('possible_reasons')}</p>
                    <ul style="text-align: left; display: inline-block;">
                        <li>{_get_webgui_messages().get('reason_network')}</li>
                        <li>{_get_webgui_messages().get('reason_config')}</li>
                        <li>{_get_webgui_messages().get('reason_resources')}</li>
                    </ul>
                    <button class="retry-button" onclick="location.reload()">{_get_webgui_messages().get('retry_button')}</button>
                </div>
            </body>
            </html>
            """
            self.web_engine_view.setHtml(error_html)
            logger.info("Error page displayed")
        except Exception as e:
            logger.error(f"Failed to show error page: {e}")

    def _setup_window_style(self):
        """Set window style to match content theme"""
        # Windows-specific styles and native settings
        if sys.platform == 'win32':
            # Apply Windows dark gray theme style
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #1a1a1a;  /* Dark gray background */
                    border: 1px solid #404040;  /* Medium gray border */
                    color: #e0e0e0;  /* Light gray text */
                }
                QMainWindow::title {
                    background-color: #2d2d2d;  /* Darker gray title bar */
                    color: #e0e0e0;  /* Light gray text */
                    padding: 8px;
                    font-weight: 600;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
            """)

            # Windows native API settings
            try:
                # Import Windows API
                import ctypes

                # Get window handle
                hwnd = int(self.winId())

                # DWM API constants
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                DWMWA_WINDOW_CORNER_PREFERENCE = 33
                DWMWCP_ROUND = 2

                # Set dark title bar (Windows 10/11)
                try:
                    dwmapi = ctypes.windll.dwmapi
                    value = ctypes.c_int(1)  # Enable dark mode
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_USE_IMMERSIVE_DARK_MODE,
                        ctypes.byref(value),
                        ctypes.sizeof(value)
                    )

                    # Set rounded window (Windows 11)
                    corner_value = ctypes.c_int(DWMWCP_ROUND)
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_WINDOW_CORNER_PREFERENCE,
                        ctypes.byref(corner_value),
                        ctypes.sizeof(corner_value)
                    )

                    logger.info("Windows dark title bar and styles applied")

                except Exception as e:
                    logger.warning(f"Failed to set dark title bar: {e}")

            except Exception as e:
                logger.warning(f"Failed to set Windows window style: {e}")
        else:
            # Non-Windows platform, keep default style
            logger.info(f"Current platform {sys.platform} does not support custom window styles; using system default")

    def _apply_messagebox_style(self, msg_box):
        """Apply dark gray theme to QMessageBox with logo background support"""
        # Apply style to all platforms for better logo visibility
        if sys.platform == 'win32':
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2d2d2d;  /* Dark gray background */
                    color: #e0e0e0;  /* Light gray text */
                    border: 1px solid #404040;  /* Medium gray border */
                    border-radius: 8px;  /* Rounded corners */
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                QMessageBox::title {
                    background-color: #1a1a1a;  /* Dark title bar background */
                    color: #e0e0e0;  /* Light title text */
                    padding: 8px 12px;
                    font-weight: 600;
                    font-size: 14px;
                    border-bottom: 1px solid #404040;  /* Bottom border of title bar */
                }
                /* Icon area background for better logo visibility */
                QMessageBox QLabel[objectName="qt_msgbox_icon_label"] {
                    background-color: #1a1a1a;  /* Dark background for icon area */
                    border-radius: 4px;
                    padding: 8px;
                }
                QMessageBox QLabel {
                    background-color: transparent;
                    color: #e0e0e0;  /* Light gray text */
                    font-size: 14px;
                    padding: 10px;
                }
                QMessageBox QPushButton {
                    background-color: #404040;  /* Medium gray button background */
                    color: #e0e0e0;  /* Light gray button text */
                    border: 1px solid #606060;  /* Slightly brighter border */
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 500;
                    min-width: 80px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #505050;  /* Slightly brighter on hover */
                    border-color: #707070;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #353535;  /* Slightly darker when pressed */
                }
                QMessageBox QPushButton:default {
                    background-color: #5a5a5a;  /* Default button slightly brighter */
                    border-color: #707070;
                }
                QMessageBox QPushButton:default:hover {
                    background-color: #656565;
                }
            """)
            logger.info("MessageBox Windows style applied")
        else:
            # macOS and Linux: Apply style with icon area background and header support
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2d2d2d;  /* Dark gray background */
                    color: #e0e0e0;  /* Light gray text */
                    border: 1px solid #404040;  /* Medium gray border */
                    border-radius: 8px;  /* Rounded corners */
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                /* Top header area background for logo visibility (macOS system title area) */
                QMessageBox::title {
                    background-color: #1a1a1a;  /* Very dark background for title/logo area */
                    color: #ffffff;  /* White text for better contrast */
                    padding: 12px 16px;
                    font-weight: 600;
                    font-size: 16px;
                    border-bottom: 1px solid #404040;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                }
                /* Icon area background for better logo visibility */
                QMessageBox QLabel[objectName="qt_msgbox_icon_label"] {
                    background-color: #1a1a1a;  /* Dark background for icon area */
                    border-radius: 4px;
                    padding: 8px;
                }
                QMessageBox QLabel {
                    background-color: transparent;
                    color: #e0e0e0;  /* Light gray text */
                    font-size: 14px;
                    padding: 10px;
                }
                QMessageBox QPushButton {
                    background-color: #404040;  /* Medium gray button background */
                    color: #e0e0e0;  /* Light gray button text */
                    border: 1px solid #606060;  /* Slightly brighter border */
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 500;
                    min-width: 80px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #505050;  /* Slightly brighter on hover */
                    border-color: #707070;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #353535;  /* Slightly darker when pressed */
                }
                QMessageBox QPushButton:default {
                    background-color: #5a5a5a;  /* Default button slightly brighter */
                    border-color: #707070;
                }
                QMessageBox QPushButton:default:hover {
                    background-color: #656565;
                }
            """)
            logger.info(f"MessageBox style applied for {sys.platform}")

    def _apply_dark_titlebar_to_messagebox(self, msg_box):
        """Apply Windows dark title bar to MessageBox"""
        try:
            import ctypes

            # Show dialog to get window handle
            msg_box.show()

            # Get MessageBox window handle
            hwnd = int(msg_box.winId())

            # DWM API constants
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20

            # Set dark title bar
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(1)  # Enable dark mode
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

            # Hide dialog until ready to show
            msg_box.hide()

            logger.info("MessageBox dark title bar applied")

        except Exception as e:
            logger.warning(f"Failed to set MessageBox dark title bar: {e}")

    def load_local_html(self):
        """Load local HTML file"""
        index_path = app_settings.dist_dir / "index.html"
        logger.info(f"Looking for index.html at: {index_path}")

        if index_path.exists():
            try:
                # Load local file directly
                self.web_engine_view.load_local_file(index_path)
                logger.info(f"Production mode: Loading from {index_path}")

            except Exception as e:
                logger.error(f"Error loading HTML file: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.error(f"index.html not found in {app_settings.dist_dir}")
            # List directory contents for debugging
            if app_settings.dist_dir.exists():
                logger.info(f"Contents of {app_settings.dist_dir}:")
                for item in app_settings.dist_dir.iterdir():
                    logger.info(f"  - {item.name}")
            else:
                logger.error(f"Directory {app_settings.dist_dir} does not exist")

    def get_ipc_api(self):
        return self.web_engine_view.get_ipc_api()

    def _setup_shortcuts(self):
        """Set up shortcuts"""
        # Developer tools shortcut
        self.dev_tools_shortcut = QShortcut(QKeySequence("F12"), self)
        self.dev_tools_shortcut.activated.connect(self._toggle_dev_tools)

        # F5 reload
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)

        # Ctrl+L clear logs
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self._clear_dev_tools_logs)
        self.addAction(clear_logs_action)

    def _ensure_dev_tools_manager(self):
        """Create DevToolsManager instance if it doesn't exist."""
        if self.dev_tools_manager is None:
            logger.info(f"[{TimeUtil.formatted_now_with_ms()}] Creating DevToolsManager on demand...")
            from gui.core.dev_tools_manager import DevToolsManager
            self.dev_tools_manager = DevToolsManager(self)
            logger.info(f"[{TimeUtil.formatted_now_with_ms()}] DevToolsManager created.")

    def _toggle_dev_tools(self):
        """Toggle the developer tools panel."""
        self._ensure_dev_tools_manager()
        self.dev_tools_manager.toggle()

    def _clear_dev_tools_logs(self):
        """Clear logs in the developer tools panel."""
        self._ensure_dev_tools_manager()
        self.dev_tools_manager.clear_all()

    def self_confirm(self):
        logger.info("self confirming top web gui....")

    def reload(self):
        """Reload page"""
        logger.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_engine_view.reload_page()
        else:
            self.load_local_html()

    def closeEvent(self, event):
        """Window close event - debug version"""
        logger.info("closeEvent triggered")

        try:
            # Create custom dialog with i18n support
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(_get_webgui_messages().get('confirm_exit_title'))
            msg_box.setText(_get_webgui_messages().get('confirm_exit_message'))
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

            # Set button text with i18n
            yes_button = msg_box.button(QMessageBox.Yes)
            no_button = msg_box.button(QMessageBox.No)
            if yes_button:
                yes_button.setText(_get_webgui_messages().get('button_yes'))
            if no_button:
                no_button.setText(_get_webgui_messages().get('button_no'))

            # Set window flags to ensure proper rendering on macOS
            if sys.platform == 'darwin':
                # On macOS, ensure the dialog is opaque and has proper background
                msg_box.setAttribute(Qt.WA_TranslucentBackground, False)
                msg_box.setWindowFlags(msg_box.windowFlags() | Qt.FramelessWindowHint)
                # Re-enable window frame for proper system integration
                msg_box.setWindowFlags(msg_box.windowFlags() & ~Qt.FramelessWindowHint)

            # Apply dark gray theme to dialog
            self._apply_messagebox_style(msg_box)

            # Apply dark title bar for Windows
            if sys.platform == 'win32':
                self._apply_dark_titlebar_to_messagebox(msg_box)

            # Try to set eCan icon; fall back to default icon on failure
            try:
                from config.app_info import app_info
                resource_path = app_info.app_resources_path

                # Platform-specific icon candidates
                if sys.platform == 'darwin':
                    # macOS prefers larger, high-quality icons, prioritize logoWhite22.png
                    icon_candidates = [
                        os.path.join(resource_path, "images", "logos", "logoWhite22.png"),
                        os.path.join(resource_path, "images", "logos", "rounded", "dock_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "rounded", "dock_128x128.png"),
                        os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                    ]
                else:
                    # Windows/Linux icon candidates
                    icon_candidates = [
                        os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                        os.path.join(os.path.dirname(resource_path), "eCan.ico"),
                    ]

                icon_set = False
                for candidate in icon_candidates:
                    if os.path.exists(candidate):
                        pixmap = QPixmap(candidate)
                        if not pixmap.isNull():
                            # Use larger icon size for macOS
                            icon_size = 128 if sys.platform == 'darwin' else 64
                            scaled_pixmap = pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            msg_box.setIconPixmap(scaled_pixmap)
                            icon_set = True
                            logger.info(f"✅ MessageBox custom icon set from: {candidate} (size: {icon_size}x{icon_size})")

                            # Additional logging for development debugging
                            if sys.platform == 'darwin':
                                logger.info("ℹ️  macOS: Custom icon set, but system may override in development environment")
                                logger.info("ℹ️  macOS: Icon should display correctly in packaged application")
                            break
                        else:
                            logger.warning(f"Failed to load icon from: {candidate}")

                if not icon_set:
                    msg_box.setIcon(QMessageBox.Question)
                    logger.warning("⚠️  Using default question icon - custom icon loading failed")
                    logger.info("💡 If running in development, try building and running as packaged application")
            except Exception as e:
                logger.warning(f"Failed to set message box icon: {e}")
                msg_box.setIcon(QMessageBox.Question)

            logger.info("🔔 [DEBUG] Show dialog")
            reply = msg_box.exec()
            logger.info(f"🔔 [DEBUG] User selection: {reply}")

            if reply == QMessageBox.Yes:
                logger.info("User confirmed exit")
                event.accept()

                logger.info("🔔 [DEBUG] Start exit process")

                # Stop LightragServer
                try:
                    logger.info("🔔 [DEBUG] Stopping LightragServer")
                    mainwin = AppContext.get_main_window()
                    if mainwin and hasattr(mainwin, 'lightrag_server') and mainwin.lightrag_server:
                        logger.info("🔔 [DEBUG] Found LightragServer, stopping...")
                        mainwin.lightrag_server.stop()
                        logger.info("🔔 [DEBUG] LightragServer stopped")
                    else:
                        logger.info("🔔 [DEBUG] LightragServer or MainWindow not found or not initialized")
                except Exception as e:
                    logger.warning(f"Error stopping LightragServer: {e}")

                # Force exit
                logger.info("Force exiting with os._exit(0)")
                os._exit(0)

            else:
                logger.info("User cancelled exit")
                event.ignore()

        except Exception as e:
            logger.error(f"closeEvent exception: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()

    def _setup_custom_titlebar_with_menu(self):
        """Set a custom title bar and integrate the menu bar into it"""
        try:
            # Hide default title bar
            self.setWindowFlags(Qt.FramelessWindowHint)

            # Create custom title bar container
            self.custom_titlebar = QWidget()
            self.custom_titlebar.setFixedHeight(32)  # Standard Windows title bar height
            self.custom_titlebar.setStyleSheet("""
                QWidget {
                    background-color: #2d2d2d;
                    border-bottom: 1px solid #404040;
                }
            """)

            # Create title bar layout
            titlebar_layout = QHBoxLayout(self.custom_titlebar)
            titlebar_layout.setContentsMargins(32, 0, 0, 0)  # Left margin to avoid system icon overlap
            titlebar_layout.setSpacing(0)

            # Add application icon
            self.app_icon = QLabel()
            self.app_icon.setFixedSize(32, 24)  # Wider container for better icon display
            self._set_titlebar_icon()
            self.app_icon.setStyleSheet("""
                QLabel {
                    padding: 2px 4px;
                    background-color: transparent;
                }
            """)
            titlebar_layout.addWidget(self.app_icon)

            # Create menu bar and add to title bar (clean, single stylesheet)
            self.custom_menubar = QMenuBar()
            self.custom_menubar.setStyleSheet("""
                QMenuBar {
                    background-color: transparent;
                    color: #e0e0e0;
                    border: none;
                    padding: 0px;
                    margin: 0px;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    spacing: 2px;
                }

                QMenuBar::item {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 6px 12px;
                    margin: 0px 1px;
                    border-radius: 4px;
                }

                QMenuBar::item:selected {
                    background-color: rgba(64, 64, 64, 0.8);
                    color: #ffffff;
                    border: 1px solid rgba(96, 96, 96, 0.3);
                }

                QMenuBar::item:pressed {
                    background-color: rgba(80, 80, 80, 0.9);
                    color: #ffffff;
                    border: 1px solid rgba(112, 112, 112, 0.4);
                }

                QMenu {
                    background-color: #2a2a2a;
                    color: #e0e0e0;
                    border: 1px solid #404040;
                    border-radius: 6px;
                    padding: 4px 0px;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 13px;
                    font-weight: 400;
                    margin-top: 2px;
                }

                QMenu::item {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 6px 16px 6px 28px;
                    margin: 1px 4px;
                    border-radius: 4px;
                    min-height: 16px;
                }

                QMenu::item:selected {
                    background-color: #0078d4;
                    color: #ffffff;
                    border: none;
                }

                QMenu::item:disabled {
                    color: #808080;
                    background-color: transparent;
                }

                QMenu::separator {
                    height: 1px;
                    background-color: #404040;
                    margin: 4px 12px;
                    border: none;
                }

                QMenu::indicator {
                    width: 14px;
                    height: 14px;
                    left: 6px;
                    margin-right: 4px;
                }

                QMenu::indicator:checked {
                    background-color: #0078d4;
                    border: 2px solid #ffffff;
                    border-radius: 3px;
                }

                QMenu::indicator:unchecked {
                    background-color: transparent;
                    border: 2px solid #808080;
                    border-radius: 3px;
                }

                QMenu::right-arrow {
                    width: 12px;
                    height: 12px;
                    margin-right: 8px;
                    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iMTIiIHZpZXdCb3g9IjAgMCAxMiAxMiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTQuNSAyTDguNSA2TDQuNSAxMCIgc3Ryb2tlPSIjZTBlMGUwIiBzdHJva2Utd2lkdGg9IjEuNSIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
                }

                /* Shortcut key style */
                QMenu::item:selected QKeySequence {
                    color: rgba(255, 255, 255, 0.8);
                }

                /* Submenu style */
                QMenu QMenu {
                    margin-left: 2px;
                    border: 1px solid #505050;
                }

                /* Menu item icon style */
                QMenu::icon {
                    padding-left: 8px;
                    width: 16px;
                    height: 16px;
                }
            """)

            # Use MenuManager to set up menu items
            self.menu_manager = MenuManager(self)
            self.menu_manager.setup_custom_menu(self.custom_menubar)

            titlebar_layout.addWidget(self.custom_menubar)

            # Add stretch to center the title
            titlebar_layout.addStretch()

            # Add title (centered)
            self.title_label = QLabel("eCan.ai")
            self.title_label.setAlignment(Qt.AlignCenter)
            self.title_label.setStyleSheet("""
                QLabel {
                    color: #e0e0e0;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 13px;
                    font-weight: 600;
                    padding: 0px;
                }
            """)
            titlebar_layout.addWidget(self.title_label)

            # Add stretch to keep title centered
            titlebar_layout.addStretch()

            # Override menuBar to return our custom menu bar
            self.menuBar = lambda: self.custom_menubar

            # Add window control buttons
            self._add_window_controls(titlebar_layout)

            # Add custom title bar to main layout
            main_layout = self.centralWidget().layout()
            main_layout.insertWidget(0, self.custom_titlebar)

            # Make title bar draggable
            self._make_titlebar_draggable()

            logger.info("Custom title bar menu set up successfully")

        except Exception as e:
            logger.error(f"Failed to set custom title bar: {e}")
            # Fallback to standard menu bar on failure
            self.setWindowFlags(Qt.Window)
            self.menu_manager = MenuManager(self)
            self.menu_manager.setup_menu()



    def _set_window_icon(self):
        """Set window icon using IconManager for proper platform-specific handling"""
        try:
            from utils.icon_manager import get_icon_manager
            icon_manager = get_icon_manager()
            icon_manager.set_logger(logger)

            if icon_manager.icon_path:
                window_icon = QIcon(icon_manager.icon_path)
                self.setWindowIcon(window_icon)
                logger.debug(f"WebGUI window icon set: {icon_manager.icon_path}")
            else:
                logger.warning("No icon found for WebGUI window")

        except Exception as e:
            logger.error(f"Failed to set WebGUI window icon: {e}")

    def _set_titlebar_icon(self):
        """Set titlebar icon using eCan icon"""
        try:
            from config.app_info import app_info
            resource_path = app_info.app_resources_path

            # Use inverted PNG icons for titlebar (better visibility on dark background)
            icon_candidates = [
                os.path.join(resource_path, "images", "logos", "taskbar_32x32_inverted.png"),
                os.path.join(resource_path, "images", "logos", "taskbar_16x16_inverted.png"),
                os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                os.path.join(resource_path, "images", "logos", "taskbar_16x16.png"),
                os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                os.path.join(os.path.dirname(resource_path), "eCan.ico"),
            ]

            # Find first existing icon
            icon_path = None
            for candidate in icon_candidates:
                if os.path.exists(candidate):
                    icon_path = candidate
                    break

            if icon_path and hasattr(self, 'app_icon'):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # Container is 32x24, with padding 2px top/bottom, 4px left/right
                    # Use a conservative size to ensure the icon displays properly without distortion
                    # Choose 18x18 to leave some margin and ensure square aspect ratio
                    target_size = 18

                    # Scale image while preserving aspect ratio
                    scaled_pixmap = pixmap.scaled(target_size, target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                    self.app_icon.setPixmap(scaled_pixmap)
                    self.app_icon.setAlignment(Qt.AlignCenter)
                    logger.debug(f"Titlebar icon set: {icon_path} (scaled to {scaled_pixmap.size().width()}x{scaled_pixmap.size().height()}, target: {target_size}x{target_size})")
                else:
                    logger.warning(f"Failed to load titlebar icon: {icon_path}")
            else:
                logger.warning("No icon found for titlebar or app_icon not available")

        except Exception as e:
            logger.error(f"Failed to set titlebar icon: {e}")


    def _setup_taskbar_icon_via_manager(self):
        """
        Set Windows taskbar icon using IconManager (Windows-only, delayed setup).

        Why delayed?
        - Windows taskbar icon requires valid window handle (HWND)
        - In frozen/packaged builds, icon extraction from EXE resources needs time
        - Immediate setup may fail, causing default Python icon to show

        Timing: 1-second delay ensures window is fully visible and stable.
        """
        if sys.platform != 'win32':
            return

        from PySide6.QtCore import QTimer

        def setup_via_manager():
            try:
                from utils.icon_manager import get_icon_manager
                icon_mgr = get_icon_manager()

                # Check if already set (prevent duplicate operations)
                if icon_mgr.is_taskbar_icon_set():
                    logger.debug("[IconManager] Taskbar icon already set, skipping")
                    return

                # Ensure window is ready (has valid handle)
                if not self.isVisible() or not self.winId():
                    logger.warning("[IconManager] Window not ready for taskbar icon setup")
                    return

                # Set taskbar icon (will extract from EXE in frozen builds)
                from PySide6.QtWidgets import QApplication
                app = QApplication.instance()
                success = icon_mgr.set_window_taskbar_icon(self, app)

                if not success:
                    logger.warning("[IconManager] ⚠️ Taskbar icon setup failed")

            except Exception as e:
                logger.error(f"[IconManager] ❌ Failed to set taskbar icon: {e}")

        # Delay 1 second to ensure window is fully visible and stable
        QTimer.singleShot(1000, setup_via_manager)

    def _add_window_controls(self, layout):
        """Add window control buttons (minimize, maximize, close)"""
        try:
            # Minimize button
            minimize_btn = QPushButton('−')
            minimize_btn.setFixedSize(46, 32)  # Standard Windows control button size
            minimize_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #e0e0e0;
                    border: none;
                    font-size: 16px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #404040;
                }
                QPushButton:pressed {
                    background-color: #505050;
                }
            """)
            minimize_btn.clicked.connect(self.showMinimized)
            layout.addWidget(minimize_btn)

            # Maximize/restore button
            self.maximize_btn = QPushButton('□')
            self.maximize_btn.setFixedSize(46, 32)  # Standard Windows control button size
            self.maximize_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #e0e0e0;
                    border: none;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #404040;
                }
                QPushButton:pressed {
                    background-color: #505050;
                }
            """)
            self.maximize_btn.clicked.connect(self._toggle_maximize)
            layout.addWidget(self.maximize_btn)

            # Close button
            close_btn = QPushButton('×')
            close_btn.setFixedSize(46, 32)  # Standard Windows control button size
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #e0e0e0;
                    border: none;
                    font-size: 18px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #e74c3c;
                    color: #ffffff;
                }
                QPushButton:pressed {
                    background-color: #c0392b;
                }
            """)
            close_btn.clicked.connect(self.close)
            layout.addWidget(close_btn)

        except Exception as e:
            logger.error(f"Failed to add window control buttons: {e}")

    def _make_titlebar_draggable(self):
        """Make title bar draggable and enable window resizing"""
        self.custom_titlebar.mousePressEvent = self._titlebar_mouse_press
        self.custom_titlebar.mouseMoveEvent = self._titlebar_mouse_move
        self.custom_titlebar.mouseDoubleClickEvent = self._titlebar_double_click
        self._drag_position = None

        # Disable custom resize cursor handling - rely on nativeEvent for Windows resize
        # This prevents cursor getting stuck in resize mode
        self._resize_margin = 8  # Larger margin for easier resizing
        self._resizing = False
        self._resize_direction = None

        # DO NOT install event filter or enable mouse tracking
        # The nativeEvent handler will take care of resize detection

        # Force cursor to arrow on window
        self.setCursor(Qt.ArrowCursor)
        self.centralWidget().setCursor(Qt.ArrowCursor)
        if hasattr(self, 'web_engine_view'):
            self.web_engine_view.setCursor(Qt.ArrowCursor)

    def _titlebar_mouse_press(self, event):
        """Title bar mouse press event"""
        if event.button() == Qt.LeftButton:
            self._drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def _titlebar_mouse_move(self, event):
        """Title bar mouse move event"""
        if event.buttons() == Qt.LeftButton and self._drag_position:
            self.move(event.globalPosition().toPoint() - self._drag_position)
            event.accept()

    def _titlebar_double_click(self, event):
        """Title bar double-click event"""
        if event.button() == Qt.LeftButton:
            self._toggle_maximize()
            event.accept()

    # (Removed disabled custom mouse handlers for clarity)

    def _get_resize_direction(self, pos):
        """Determine resize direction based on mouse position"""
        rect = self.rect()
        margin = self._resize_margin

        left = pos.x() <= margin
        right = pos.x() >= rect.width() - margin
        top = pos.y() <= margin
        bottom = pos.y() >= rect.height() - margin

        direction = None
        if top and left:
            direction = 'top-left'
        elif top and right:
            direction = 'top-right'
        elif bottom and left:
            direction = 'bottom-left'
        elif bottom and right:
            direction = 'bottom-right'
        elif left:
            direction = 'left'
        elif right:
            direction = 'right'
        elif top:
            direction = 'top'
        elif bottom:
            direction = 'bottom'

        return direction

    def _update_cursor(self, direction):
        """Update cursor based on resize direction"""
        if direction == 'top' or direction == 'bottom':
            self.setCursor(Qt.SizeVerCursor)
        elif direction == 'left' or direction == 'right':
            self.setCursor(Qt.SizeHorCursor)
        elif direction == 'top-left' or direction == 'bottom-right':
            self.setCursor(Qt.SizeFDiagCursor)
        elif direction == 'top-right' or direction == 'bottom-left':
            self.setCursor(Qt.SizeBDiagCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def _perform_resize(self, global_pos):
        """Perform window resize based on mouse movement"""
        delta = global_pos - self._resize_start_pos
        geo = self._resize_start_geometry

        new_geo = geo

        if 'left' in self._resize_direction:
            new_geo.setLeft(geo.left() + delta.x())
        if 'right' in self._resize_direction:
            new_geo.setRight(geo.right() + delta.x())
        if 'top' in self._resize_direction:
            new_geo.setTop(geo.top() + delta.y())
        if 'bottom' in self._resize_direction:
            new_geo.setBottom(geo.bottom() + delta.y())

        # Enforce minimum size
        min_width = 400
        min_height = 300
        if new_geo.width() >= min_width and new_geo.height() >= min_height:
            self.setGeometry(new_geo)

    def _toggle_maximize(self):
        """Toggle maximize/restore window"""
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setText('□')
        else:
            self.showMaximized()
            self.maximize_btn.setText('❐')

    def nativeEvent(self, eventType, message):
        """Handle Windows native events for resize support"""
        if sys.platform == 'win32' and eventType == b'windows_generic_MSG':
            try:
                from PySide6.QtGui import QCursor
                msg = ctypes.wintypes.MSG.from_address(int(message))

                # WM_NCLBUTTONDBLCLK = 0x00A3 - Handle double-click on non-client area (title bar)
                if msg.message == 0x00A3:
                    # wParam contains hit test code
                    hit_test = msg.wParam
                    # HTCAPTION = 2 (title bar area)
                    if hit_test == 2:
                        # Toggle maximize/restore on title bar double-click
                        self._toggle_maximize()
                        return True, 0  # Message handled

                # WM_NCHITTEST = 0x0084
                if msg.message == 0x0084:
                    rect = self.rect()
                    border_width = 8

                    # Prefer Qt's global cursor position mapping; fallback to lParam if needed
                    try:
                        global_pos = QCursor.pos()
                        local_pos = self.mapFromGlobal(global_pos)
                        client_x = local_pos.x()
                        client_y = local_pos.y()
                    except Exception:
                        win_x = msg.lParam & 0xFFFF
                        win_y = (msg.lParam >> 16) & 0xFFFF
                        if win_x >= 0x8000:
                            win_x -= 0x10000
                        if win_y >= 0x8000:
                            win_y -= 0x10000
                        client_x = win_x - self.x()
                        client_y = win_y - self.y()

                    # If pointer is outside our client rect, do not claim any hit
                    if client_x < 0 or client_y < 0 or client_x > rect.width() or client_y > rect.height():
                        return False, 0

                    # Determine if the pointer is over interactive titlebar widgets that must receive clicks
                    # Always treat these as client area so Qt widgets get events (menus, buttons, labels)
                    from PySide6.QtCore import QPoint
                    point_in_self = QPoint(client_x, client_y)

                    def _contains(widget) -> bool:
                        try:
                            if widget is None:
                                return False
                            p = widget.mapFrom(self, point_in_self)
                            return widget.rect().contains(p)
                        except Exception:
                            return False

                    over_menubar = _contains(getattr(self, 'custom_menubar', None))
                    over_icon = _contains(getattr(self, 'app_icon', None))
                    over_title = _contains(getattr(self, 'title_label', None))

                    # Window control buttons (min/max/close)
                    over_max = _contains(getattr(self, 'maximize_btn', None))
                    # minimize and close are created as local vars in _add_window_controls, not stored
                    # so conservatively exclude rightmost zone (~150px) to cover them
                    over_right_controls_zone = client_x >= rect.width() - 150 and 0 <= client_y < 32

                    if over_menubar or over_icon or over_title or over_max or over_right_controls_zone:
                        return True, 1  # HTCLIENT

                    # Title bar drag zone: only the empty area within top band that is not occupied by widgets
                    if border_width <= client_y < 32:
                        return True, 2  # HTCAPTION

                    if not self.isMaximized():
                        # Corners
                        if client_x < border_width and client_y < border_width:
                            return True, 13  # HTTOPLEFT
                        if client_x > rect.width() - border_width and client_y < border_width:
                            return True, 14  # HTTOPRIGHT
                        if client_x < border_width and client_y > rect.height() - border_width:
                            return True, 16  # HTBOTTOMLEFT
                        if client_x > rect.width() - border_width and client_y > rect.height() - border_width:
                            return True, 17  # HTBOTTOMRIGHT
                        # Edges
                        if client_x < border_width:
                            return True, 10  # HTLEFT
                        if client_x > rect.width() - border_width:
                            return True, 11  # HTRIGHT
                        if client_y < border_width:
                            return True, 12  # HTTOP
                        if client_y > rect.height() - border_width:
                            return True, 15  # HTBOTTOM
            except Exception as e:
                logger.error(f"Error in nativeEvent: {e}")

        return super().nativeEvent(eventType, message)

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def handle_oauth_error(self, error: str):
        """Handle OAuth authentication error"""
        try:
            logger.error(f"OAuth authentication error: {error}")

            # Bring window to foreground
            self.activateWindow()
            self.raise_()
            self.show()

            # Show error notification
            self._show_notification(f"Authentication failed: {error}", "error")

        except Exception as e:
            logger.error(f"Error handling OAuth error: {e}")

    def _remove_stay_on_top(self):
        """Remove stay on top flag"""
        try:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
            self.show()
        except Exception as e:
            logger.error(f"Error removing stay on top: {e}")

    def _show_notification(self, message: str, notification_type: str = "info"):
        """Show notification to user"""
        try:
            # Show system notification if available
            if hasattr(self, 'web_engine_view') and self.web_engine_view:
                # Send notification to web interface
                js_code = f"""
                    if (window.showNotification) {{
                        window.showNotification('{message}', '{notification_type}');
                    }} else if (window.console) {{
                        console.log('Notification: {message}');
                    }}
                """
                self.web_engine_view.page().runJavaScript(js_code)

            # Fallback: log the notification
            if notification_type == "error":
                logger.error(f"Notification: {message}")
            else:
                logger.info(f"Notification: {message}")

        except Exception as e:
            logger.error(f"Error showing notification: {e}")

    def _set_update_badge(self, has_update: bool, version: str = ""):
        """Update menu to show update availability indicator.
        
        This updates the menu item text to show an indicator when update is available.
        No longer uses frontend badge - all OTA UI is in native menu.
        
        Args:
            has_update: Whether an update is available
            version: Version string of the available update
        """
        try:
            # Update menu manager to show indicator
            if hasattr(self, 'menu_manager') and self.menu_manager:
                self.menu_manager.set_update_available(has_update, version)
                logger.info(f"[OTA] Menu indicator updated: has_update={has_update}, version={version}")
            else:
                logger.warning("[OTA] menu_manager not available, cannot update menu indicator")
                
        except Exception as e:
            logger.error(f"[OTA] Error updating menu indicator: {e}")
    
    def _show_update_confirmation(self, version: str, update_info: dict, is_manual: bool = False):
        """Show update confirmation dialog with "Don't remind again" option.
        
        Args:
            version: Available version string
            update_info: Update information dictionary
            is_manual: True if triggered by manual check, False if auto-check
        """
        try:
            from PySide6.QtWidgets import QMessageBox, QCheckBox
            from PySide6.QtCore import Qt
            from ota.core.version_ignore import get_version_ignore_manager
            from ota.gui.i18n import get_translator
            
            # Get translator
            _tr = get_translator()
            
            # ✅ Prevent duplicate dialogs - check if dialog is already showing
            if hasattr(self, '_update_dialog_showing') and self._update_dialog_showing:
                logger.info(f"[OTA] Update confirmation dialog already showing, skipping duplicate")
                return
            
            # Mark dialog as showing
            self._update_dialog_showing = True
            
            try:
                # Create message box
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle(_tr.tr("software_update"))
                
                # Set icon
                msg_box.setIcon(QMessageBox.Icon.Information)
                
                # Set text
                text = f"<h3>{_tr.tr('new_version_available').format(version=version)}</h3>"
                text += f"<p>{_tr.tr('current_version_label').format(version=self._get_current_version())}</p>"
                if update_info.get('description'):
                    text += f"<p>{update_info['description']}</p>"
                text += f"<p>{_tr.tr('would_you_like_to_update')}</p>"
                msg_box.setText(text)
                
                # Add buttons
                update_btn = msg_box.addButton(
                    _tr.tr("update_now"),
                    QMessageBox.ButtonRole.AcceptRole
                )
                later_btn = msg_box.addButton(
                    _tr.tr("remind_later"),
                    QMessageBox.ButtonRole.RejectRole
                )
                
                # Add "Don't remind again" checkbox (only for auto-check)
                dont_remind_checkbox = None
                if not is_manual:
                    dont_remind_checkbox = QCheckBox(
                        _tr.tr("dont_remind_this_version"),
                        msg_box
                    )
                    msg_box.setCheckBox(dont_remind_checkbox)
                
                # Show dialog
                msg_box.exec()
                clicked_button = msg_box.clickedButton()
                
                # Handle user choice
                if clicked_button == update_btn:
                    # User chose to update
                    logger.info(f"[OTA] User confirmed update to version {version}")
                    self._start_ota_update(version, update_info)
                else:
                    # User chose "Remind Later"
                    logger.info(f"[OTA] User postponed update to version {version}")
                    
                    # Check if "Don't remind again" was selected
                    if dont_remind_checkbox and dont_remind_checkbox.isChecked():
                        ignore_mgr = get_version_ignore_manager()
                        ignore_mgr.ignore_version(version)
                        logger.info(f"[OTA] Version {version} added to ignore list")
            finally:
                # ✅ Reset flag when dialog closes
                self._update_dialog_showing = False
                    
        except Exception as e:
            logger.error(f"[OTA] Error showing update confirmation: {e}")
            import traceback
            logger.error(traceback.format_exc())
            # ✅ Reset flag on error
            self._update_dialog_showing = False
    
    def _start_ota_update(self, version: str, update_info: dict):
        """Start OTA update process and show progress dialog.
        
        Args:
            version: Version to update to
            update_info: Update information dictionary
        """
        try:
            from ota.gui.dialog import UpdateDialog
            from ota.core.updater import OTAUpdater
            from app_context import AppContext
            from PySide6.QtCore import QTimer
            
            # Get or create OTA updater
            ctx = AppContext.get_instance()
            ota_updater = getattr(ctx, "ota_updater", None)
            if ota_updater is None:
                ota_updater = OTAUpdater()
                setattr(ctx, "ota_updater", ota_updater)
            
            # Show update dialog
            dialog = UpdateDialog(parent=self, ota_updater=ota_updater)
            dialog.show()  # Use show() instead of exec() to allow background operation
            
            # Auto-start download after dialog is shown
            # Set update_info first so download can start
            dialog.update_info = update_info
            
            # Use QTimer to start download after dialog is fully shown
            QTimer.singleShot(500, lambda: self._auto_start_download(dialog, update_info))
            
            logger.info(f"[OTA] Update dialog shown for version {version}, auto-starting download")
            
        except Exception as e:
            logger.error(f"[OTA] Error starting OTA update: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    def _auto_start_download(self, dialog, update_info: dict):
        """Auto-start download in the update dialog"""
        try:
            if dialog and hasattr(dialog, 'download_update'):
                # Update UI to show update is available
                dialog.status_label.setText("发现新版本，准备下载..." if self._is_chinese() else "New version found, preparing download...")
                dialog.info_group.setVisible(True)
                
                # Set update info and start download
                if isinstance(update_info, dict):
                    version = update_info.get('latest_version', 'Unknown')
                    description = update_info.get('description', '')
                    html_content = f"<p><b>{'最新版本' if self._is_chinese() else 'Latest Version'}: {version}</b></p>{description}"
                    dialog.info_text.setHtml(html_content)
                
                # Start download
                dialog.download_update()
                logger.info("[OTA] Auto-started download")
        except Exception as e:
            logger.error(f"[OTA] Error auto-starting download: {e}")
    
    def _is_chinese(self) -> bool:
        """Check if current language is Chinese."""
        try:
            from utils.i18n_helper import detect_language
            lang = detect_language(default_lang='zh-CN', supported_languages=['zh-CN', 'en-US'])
            return lang == 'zh-CN'
        except:
            return True  # Default to Chinese
    
    def _get_current_version(self) -> str:
        """Get current application version."""
        try:
            from config.app_info import app_info
            return app_info.version
        except:
            return "Unknown"
