from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox, QApplication, QHBoxLayout, QLabel, QPushButton, QMenuBar
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QIcon, QPixmap
from PySide6.QtCore import Qt
from typing import Optional
from utils.time_util import TimeUtil
import sys
import os
from gui.ipc.api import IPCAPI
from gui.menu_manager import MenuManager

from config.app_settings import app_settings
from utils.logger_helper import logger_helper as logger
from gui.core.web_engine_view import WebEngineView

from app_context import AppContext


# Configure logging to suppress macOS IMK warnings
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"


class WebGUI(QMainWindow):
    def __init__(self, parent=None, splash: Optional[object] = None, progress_callback=None):
        super().__init__()
        self.setWindowTitle("eCan.ai")
        self.parent = parent
        self._splash = splash
        self._progress_callback = progress_callback

        # Update progress if callback is available
        if self._progress_callback:
            self._progress_callback(72, "Setting up main window...")

        # Set window icon for taskbar display (required for taskbar icon)
        self._set_window_icon()
        # Set window size first, then center it
        self.resize(1200, 800)
        self._center_on_screen()

        if self._progress_callback:
            self._progress_callback(74, "Creating interface layout...")

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)

        if self._progress_callback:
            self._progress_callback(76, "Initializing web engine...")

        # Create web engine
        self.web_engine_view = WebEngineView(self)

        if self._progress_callback:
            self._progress_callback(78, "Setting up developer tools...")

        # Developer tools manager will be created on-demand
        self.dev_tools_manager = None

        if self._progress_callback:
            self._progress_callback(80, "Configuring window style...")

        # Set Windows window style to match content theme
        self._setup_window_style()

        # Initialize IPC API
        self._ipc_api = None

        if self._progress_callback:
            self._progress_callback(82, "Connecting web engine...")

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
                self._show_error_page("Web URL not available")

        except Exception as e:
            logger.error(f"Error during WebGUI initialization: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            self._show_error_page(f"Initialization error: {str(e)}")
        
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

        # Show behavior: if no splash, show immediately; else splash will call show on finished
        if self._splash is None:
            try:
                self.show()
            except Exception:
                pass

    # --- Splash handlers ---
    def _on_load_progress(self, progress: int):
        try:
            if self._splash is not None:
                self._splash.set_status(f"Loading {progress}%…")
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
                        font-family: Arial, sans-serif;
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
                    <h1>⚠️ Application Error</h1>
                    <p>eCan.ai encountered an error during startup:</p>
                    <div class="error-message">{error_message}</div>
                    <p>This usually happens when:</p>
                    <ul style="text-align: left; display: inline-block;">
                        <li>Frontend files are missing or corrupted</li>
                        <li>PyInstaller packaging issue</li>
                        <li>File permissions problem</li>
                    </ul>
                    <button class="retry-button" onclick="location.reload()">Retry</button>
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
        """Apply dark gray theme to QMessageBox (Windows only)"""
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
            # Non-Windows platform, keep system default style
            logger.info(f"Current platform {sys.platform} does not support custom MessageBox style; using system default")

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
            # Create custom dialog
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('Confirm Exit')
            msg_box.setText('Are you sure you want to exit the program?')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

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
                    if AppContext.main_window and hasattr(AppContext.main_window, 'lightrag_server'):
                        logger.info("🔔 [DEBUG] Found LightragServer, stopping...")
                        AppContext.main_window.lightrag_server.stop()
                        logger.info("🔔 [DEBUG] LightragServer stopped")
                    else:
                        logger.info("🔔 [DEBUG] LightragServer or MainWindow not found")
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

    def get_ipc_api(self):
        self._ipc_api = IPCAPI.get_instance()
        return self._ipc_api

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
                    padding: 2px 4px;  # Reduced padding to give more space for icon
                    background-color: transparent;
                }
            """)
            titlebar_layout.addWidget(self.app_icon)

            # Create menu bar and add to title bar
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
                    transition: all 0.2s ease;
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
                    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
                    margin-top: 2px;
                }

                QMenu::item {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 6px 16px 6px 28px;
                    margin: 1px 4px;
                    border-radius: 4px;
                    min-height: 16px;
                    transition: all 0.15s ease;
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
        """Set window icon using the same logic as application icon"""
        try:
            from config.app_info import app_info
            resource_path = app_info.app_resources_path

            # Use the same icon candidates as the application
            icon_candidates = [
                os.path.join(os.path.dirname(resource_path), "eCan.ico"),
                os.path.join(resource_path, "images", "logos", "icon_multi.ico"),
                os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                os.path.join(resource_path, "images", "logos", "taskbar_16x16.png"),
            ]

            # Find first existing icon
            icon_path = None
            for candidate in icon_candidates:
                if os.path.exists(candidate):
                    icon_path = candidate
                    break

            if icon_path:
                window_icon = QIcon(icon_path)
                self.setWindowIcon(window_icon)
                logger.debug(f"WebGUI window icon set: {icon_path}")
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
        """Make title bar draggable"""
        self.custom_titlebar.mousePressEvent = self._titlebar_mouse_press
        self.custom_titlebar.mouseMoveEvent = self._titlebar_mouse_move
        self.custom_titlebar.mouseDoubleClickEvent = self._titlebar_double_click
        self._drag_position = None

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

    def _toggle_maximize(self):
        """Toggle maximize/restore window"""
        if self.isMaximized():
            self.showNormal()
            self.maximize_btn.setText('□')
        else:
            self.showMaximized()
            self.maximize_btn.setText('❐')

    def _toggle_fullscreen(self):
        """Toggle fullscreen mode"""
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()





    def _center_on_screen(self):
        """Center the window on the screen"""
        screen = QApplication.primaryScreen()
        if not screen:
            return
        sg = screen.availableGeometry()
        self.move(
            sg.center().x() - self.width() // 2,
            sg.center().y() - self.height() // 2,
        )
    
    def handle_oauth_success(self):
        """Handle successful OAuth authentication"""
        try:
            logger.info("OAuth authentication successful - bringing window to foreground")
            
            # Bring window to foreground
            self.activateWindow()
            self.raise_()
            self.show()
            
            # Set window on top temporarily
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
            self.show()
            # Remove stay on top after a short delay
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, lambda: self._remove_stay_on_top())
            
            # Show success notification
            self._show_notification("Authentication successful!", "success")
            
            # Refresh authentication status in the web interface
            if hasattr(self, 'web_engine_view') and self.web_engine_view:
                self.web_engine_view.page().runJavaScript("""
                    if (window.authManager) {
                        window.authManager.refreshAuthStatus();
                    }
                """)
            
        except Exception as e:
            logger.error(f"Error handling OAuth success: {e}")
    
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
