from PySide6.QtWidgets import QMainWindow, QVBoxLayout, QWidget, QMessageBox, QApplication, QHBoxLayout, QLabel, QPushButton, QMenuBar
from PySide6.QtGui import QKeySequence, QShortcut, QAction, QIcon, QPixmap
from PySide6.QtCore import Qt
from typing import Optional
import sys
import os
from gui.ipc.api import IPCAPI
from gui.menu_manager import MenuManager
from PySide6.QtGui import QPixmap  # Add this import
from PySide6.QtGui import QIcon  # Add this import
from PySide6.QtCore import Qt  # For high quality scaling

from PySide6.QtWidgets import QApplication

from config.app_settings import app_settings
from utils.logger_helper import logger_helper as logger
from gui.core.web_engine_view import WebEngineView
from gui.core.dev_tools_manager import DevToolsManager
from app_context import AppContext
from agent.chats.chat_service import ChatService
import time


# Configure logging to suppress macOS IMK warnings
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"


class WebGUI(QMainWindow):
    def __init__(self, parent=None, splash: Optional[object] = None):
        super().__init__()
        self.setWindowTitle("eCan.ai")
        self.parent = parent
        self._splash = splash
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(100, 100, 1200, 800)

        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        # Create web engine
        self.web_engine_view = WebEngineView(self)

        # Create developer tools manager
        self.dev_tools_manager = DevToolsManager(self)

        # Set Windows window style to match content theme
        self._setup_window_style()

        # Initialize IPC API
        self._ipc_api = None
        
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
        except Exception:
            try:
                self.show()
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
    def set_parent(self, parent):
        self.parent = parent

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
        self.dev_tools_shortcut.activated.connect(self.dev_tools_manager.toggle)
        
        # F5 reload
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L clear logs
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools_manager.clear_all)
        self.addAction(clear_logs_action)

    def self_confirm(self):
        print("self confirming top web gui....")

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

            # Try to set icon; fall back to default icon on failure
            try:
                logo_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
                pixmap = QPixmap(logo_path)
                if not pixmap.isNull():
                    scaled_pixmap = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    msg_box.setIconPixmap(scaled_pixmap)
                else:
                    msg_box.setIcon(QMessageBox.Question)
            except:
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
                    from app_context import AppContext
                    ctx = AppContext()
                    if ctx.main_window and hasattr(ctx.main_window, 'lightrag_server'):
                        logger.info("🔔 [DEBUG] Found LightragServer, stopping...")
                        ctx.main_window.lightrag_server.stop()
                        logger.info("🔔 [DEBUG] LightragServer stopped")
                    else:
                        logger.info("🔔 [DEBUG] LightragServer or MainWindow not found")
                except Exception as e:
                    logger.warning(f"Error stopping LightragServer: {e}")

                # Force exit
                import os
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

    # Message
    # {
    #     role: 'user' | 'assistant' | 'system' | 'agent';
    # id: string;
    # createAt: number;
    # content: string | Content | Content[]; // Supports string, single Content object, or Content array
    # status: MessageStatus; // Enum type
    # attachments?: Attachment[]; // Unified usage
    # attachments
    # Fields matching backend data structure
    #
    #      // The following fields are for internal app use, not Semi
    # Required by Chat component
    # chatId?: string;
    # senderId?: string;
    # senderName?: string;
    # time?: number;
    # isRead?: boolean; // New: whether the message has been read
    # }
    def push_message_to_chat(self, chatId, msg):
        """Dispatch by type, call chat_service.add_xxx_message, push to frontend, and record DB write result"""
        main_window = self.parent
        logger.info(f"push_message echo_msg: {msg}")
        chat_service: ChatService = main_window.chat_service
        content = msg.get('content')
        role = msg.get('role')
        senderId = msg.get('senderId')[0]
        createAt = msg.get('createAt')[0]
        senderName = msg.get('senderName')[0]
        status = msg.get('status')[0]
        ext = msg.get('ext')
        attachments = msg.get('attachments')
        # Type dispatch
        db_result = None
        if isinstance(content, dict):
            msg_type = content.get('type')
            if msg_type == 'text' or "text" in content:
                print("pushing text message", content)
                db_result = chat_service.add_text_message(
                    chatId=chatId, role=role, text=content.get('text', ''), senderId=senderId, createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'form':
                form = content.get('form', {})
                db_result = chat_service.add_form_message(
                    chatId=chatId, role=role, form=form, senderId=senderId,
                    createAt=createAt, senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'code':
                code = content.get('code', {})
                db_result = chat_service.add_code_message(
                    chatId=chatId, role=role, code=code.get('value', ''), language=code.get('lang', 'python'),
                    senderId=senderId, createAt=createAt, senderName=senderName, status=status, ext=ext,
                    attachments=attachments)
            elif msg_type == 'system':
                system = content.get('system', {})
                db_result = chat_service.add_system_message(
                    chatId=chatId, text=system.get('text', ''), level=system.get('level', 'info'),
                    senderId=senderId, createAt=createAt, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'notification':
                print("pushing notification message", content)
                notification = content.get('notification', {})
                db_result = chat_service.add_notification_message(
                    chatId=chatId, title=notification.get('title', ''), content=notification,
                    level=notification.get('level', 'info'), senderId=senderId, createAt=createAt, status=status,
                    ext=ext, attachments=attachments)
            elif msg_type == 'card':
                card = content.get('card', {})
                db_result = chat_service.add_card_message(
                    chatId=chatId, role=role, title=card.get('title', ''), content=card.get('content', ''),
                    actions=card.get('actions', []), senderId=senderId, createAt=createAt, senderName=senderName,
                    status=status, ext=ext, attachments=attachments)
            elif msg_type == 'markdown':
                db_result = chat_service.add_markdown_message(
                    chatId=chatId, role=role, markdown=content.get('markdown', ''), senderId=senderId,
                    createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'table':
                table = content.get('table', {})
                db_result = chat_service.add_table_message(
                    chatId=chatId, role=role, headers=table.get('headers', []), rows=table.get('rows', []),
                    senderId=senderId, createAt=createAt, senderName=senderName, status=status, ext=ext,
                    attachments=attachments)
            else:
                db_result = chat_service.add_message(
                    chatId=chatId, role=role, content=content, senderId=senderId, createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
        else:
            db_result = chat_service.add_text_message(
                chatId=chatId, role=role, text=str(content), senderId=senderId, createAt=createAt,
                senderName=senderName, status=status, ext=ext, attachments=attachments)
        logger.info(f"push_message db_result: {db_result}")
        print("push_message db_result:", db_result)
        # Push to frontend
        app_ctx = AppContext()
        web_gui = app_ctx.web_gui
        # Push actual data after database write
        if db_result and isinstance(db_result, dict) and 'data' in db_result and msg_type != "notification":
            print("push_message db_result['data']:", db_result['data'])
            web_gui.get_ipc_api().push_chat_message(chatId, db_result['data'])
        elif db_result and isinstance(db_result, dict) and 'data' in db_result and msg_type == "notification":
            uid = msg.get('id')
            web_gui.get_ipc_api().push_chat_notification(chatId, content.get('notification', {}), True, createAt, uid)
        else:
            logger.error(f"message insert db failed{chatId}, {msg.id}")
            # web_gui.get_ipc_api().push_chat_message(chatId, msg)

    def receive_new_chat_message(self, sender_agent, chatId, content, uid):
        isRead = True
        timestamp = int(time.time())

        # chatId: str, content: dict, isRead: bool = False, timestamp: int = None, uid: str = None,
        response = self._ipc_api.push_chat_message(chatId, content, isRead, timestamp, uid)
        print("receive_new_chat_message response::", response)

    def receive_new_chat_notification(self, sender_agent, chatId, content, uid):
        isRead = True
        timestamp = int(time.time())

        # chatId: str, content: dict, isRead: bool = False, timestamp: int = None, uid: str = None,
        response = self._ipc_api.push_chat_notification(chatId, content, isRead, timestamp, uid)
        print("receive_new_chat_message response::", response)

    def _adjust_layout_for_titlebar_menu(self):
        """Adjust window layout on Windows/Linux to fit the title bar menu"""
        try:
            # Get menu bar
            menubar = self.menuBar()

            # Ensure the menu bar is positioned correctly
            # In Qt, the menu bar is below the title bar by default; styling makes it appear in the title bar
            menubar.setCornerWidget(None)  # Clear any corner widgets

            # Adjust main window margins to leave space for the menu bar
            central_widget = self.centralWidget()
            if central_widget:
                layout = central_widget.layout()
                if layout:
                    # Reduce top margin as the menu bar is more compact now
                    layout.setContentsMargins(0, 0, 0, 0)

            logger.info("Windows layout adjusted to title bar menu mode")

        except Exception as e:
            logger.error(f"Failed to adjust window layout: {e}")

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
            titlebar_layout.setContentsMargins(8, 0, 0, 0)  # Right margin 0 to align control buttons to the edge
            titlebar_layout.setSpacing(0)

            # Add application icon
            self.app_icon = QLabel()
            self.app_icon.setFixedSize(24, 24)
            icon_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
            if os.path.exists(icon_path):
                pixmap = QPixmap(icon_path)
                if not pixmap.isNull():
                    # Scale image to fit 24x24 while preserving aspect ratio
                    scaled_pixmap = pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.app_icon.setPixmap(scaled_pixmap)
                    self.app_icon.setAlignment(Qt.AlignCenter)
            self.app_icon.setStyleSheet("""
                QLabel {
                    padding: 2px 8px;
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

            # Manually set menu items
            self._setup_custom_menus()

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

            # Initialize menu manager (if other features are needed)
            self.menu_manager = MenuManager(self)
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

    def _setup_custom_menus(self):
        """Set up custom menu bar items"""
        try:
            # Add primary menu items
            app_menu = self.custom_menubar.addMenu('eCan')
            self._add_app_menu_items(app_menu)

            file_menu = self.custom_menubar.addMenu('File')
            self._add_file_menu_items(file_menu)

            edit_menu = self.custom_menubar.addMenu('Edit')
            self._add_edit_menu_items(edit_menu)

            view_menu = self.custom_menubar.addMenu('View')
            self._add_view_menu_items(view_menu)

            tools_menu = self.custom_menubar.addMenu('Tools')
            self._add_tools_menu_items(tools_menu)

            help_menu = self.custom_menubar.addMenu('Help')
            self._add_help_menu_items(help_menu)

        except Exception as e:
            logger.error(f"Failed to set custom menu: {e}")

    def _add_app_menu_items(self, menu):
        """Add application menu items"""
        # About
        about_action = QAction('About eCan.ai', self)
        about_action.setStatusTip('Show information about eCan.ai')
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

        menu.addSeparator()

        # Preferences
        preferences_action = QAction('Preferences...', self)
        preferences_action.setShortcut('Ctrl+,')
        preferences_action.setStatusTip('Open application preferences')
        menu.addAction(preferences_action)

        # Check for updates
        update_action = QAction('Check for Updates...', self)
        update_action.setStatusTip('Check for application updates')
        menu.addAction(update_action)

        menu.addSeparator()

        # Quit
        quit_action = QAction('Quit eCan.ai', self)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.setStatusTip('Quit the application')
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _add_file_menu_items(self, menu):
        """Add File menu items"""
        # New
        new_action = QAction('New Chat', self)
        new_action.setShortcut('Ctrl+N')
        new_action.setStatusTip('Create a new chat conversation')
        menu.addAction(new_action)

        new_project_action = QAction('New Project...', self)
        new_project_action.setShortcut('Ctrl+Shift+N')
        new_project_action.setStatusTip('Create a new project')
        menu.addAction(new_project_action)

        menu.addSeparator()

        # Open
        open_action = QAction('Open...', self)
        open_action.setShortcut('Ctrl+O')
        open_action.setStatusTip('Open an existing file or project')
        menu.addAction(open_action)

        # Recent files submenu
        recent_menu = menu.addMenu('Open Recent')
        recent_menu.setStatusTip('Open recently used files')

        # Add some sample recent files
        for i in range(3):
            recent_action = QAction(f'Recent File {i+1}', self)
            recent_menu.addAction(recent_action)

        recent_menu.addSeparator()
        clear_recent_action = QAction('Clear Recent Files', self)
        recent_menu.addAction(clear_recent_action)

        menu.addSeparator()

        # Save
        save_action = QAction('Save', self)
        save_action.setShortcut('Ctrl+S')
        save_action.setStatusTip('Save the current file')
        menu.addAction(save_action)

        save_as_action = QAction('Save As...', self)
        save_as_action.setShortcut('Ctrl+Shift+S')
        save_as_action.setStatusTip('Save the current file with a new name')
        menu.addAction(save_as_action)

        menu.addSeparator()

        # Import/Export
        import_action = QAction('Import...', self)
        import_action.setStatusTip('Import data from external sources')
        menu.addAction(import_action)

        export_action = QAction('Export...', self)
        export_action.setStatusTip('Export data to external formats')
        menu.addAction(export_action)

    def _add_edit_menu_items(self, menu):
        """Add Edit menu items"""
        # Undo/Redo
        undo_action = QAction('Undo', self)
        undo_action.setShortcut('Ctrl+Z')
        undo_action.setStatusTip('Undo the last action')
        menu.addAction(undo_action)

        redo_action = QAction('Redo', self)
        redo_action.setShortcut('Ctrl+Y')
        redo_action.setStatusTip('Redo the last undone action')
        menu.addAction(redo_action)

        menu.addSeparator()

        # Clipboard operations
        cut_action = QAction('Cut', self)
        cut_action.setShortcut('Ctrl+X')
        cut_action.setStatusTip('Cut the selection to clipboard')
        menu.addAction(cut_action)

        copy_action = QAction('Copy', self)
        copy_action.setShortcut('Ctrl+C')
        copy_action.setStatusTip('Copy the selection to clipboard')
        menu.addAction(copy_action)

        paste_action = QAction('Paste', self)
        paste_action.setShortcut('Ctrl+V')
        paste_action.setStatusTip('Paste from clipboard')
        menu.addAction(paste_action)

        paste_special_action = QAction('Paste Special...', self)
        paste_special_action.setShortcut('Ctrl+Shift+V')
        paste_special_action.setStatusTip('Paste with special formatting options')
        menu.addAction(paste_special_action)

        menu.addSeparator()

        # Selection operations
        select_all_action = QAction('Select All', self)
        select_all_action.setShortcut('Ctrl+A')
        select_all_action.setStatusTip('Select all content')
        menu.addAction(select_all_action)

        menu.addSeparator()

        # Find/Replace
        find_action = QAction('Find...', self)
        find_action.setShortcut('Ctrl+F')
        find_action.setStatusTip('Find text in the current document')
        menu.addAction(find_action)

        find_replace_action = QAction('Find and Replace...', self)
        find_replace_action.setShortcut('Ctrl+H')
        find_replace_action.setStatusTip('Find and replace text')
        menu.addAction(find_replace_action)

    def _add_view_menu_items(self, menu):
        """Add View menu items"""
        # Window mode
        fullscreen_action = QAction('Enter Full Screen', self)
        fullscreen_action.setShortcut('F11')
        fullscreen_action.setStatusTip('Enter or exit full screen mode')
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        menu.addAction(fullscreen_action)

        menu.addSeparator()

        # Zoom controls
        zoom_menu = menu.addMenu('Zoom')
        zoom_menu.setStatusTip('Control page zoom level')

        zoom_in_action = QAction('Zoom In', self)
        zoom_in_action.setShortcut('Ctrl+=')
        zoom_in_action.setStatusTip('Increase zoom level')
        zoom_menu.addAction(zoom_in_action)

        zoom_out_action = QAction('Zoom Out', self)
        zoom_out_action.setShortcut('Ctrl+-')
        zoom_out_action.setStatusTip('Decrease zoom level')
        zoom_menu.addAction(zoom_out_action)

        zoom_reset_action = QAction('Reset Zoom', self)
        zoom_reset_action.setShortcut('Ctrl+0')
        zoom_reset_action.setStatusTip('Reset zoom to 100%')
        zoom_menu.addAction(zoom_reset_action)

        menu.addSeparator()

        # UI elements
        sidebar_action = QAction('Toggle Sidebar', self)
        sidebar_action.setShortcut('Ctrl+B')
        sidebar_action.setStatusTip('Show or hide the sidebar')
        sidebar_action.setCheckable(True)
        sidebar_action.setChecked(True)
        menu.addAction(sidebar_action)

        toolbar_action = QAction('Show Toolbar', self)
        toolbar_action.setStatusTip('Show or hide the toolbar')
        toolbar_action.setCheckable(True)
        toolbar_action.setChecked(True)
        menu.addAction(toolbar_action)

        statusbar_action = QAction('Show Status Bar', self)
        statusbar_action.setStatusTip('Show or hide the status bar')
        statusbar_action.setCheckable(True)
        statusbar_action.setChecked(True)
        menu.addAction(statusbar_action)

        menu.addSeparator()

        # Page controls
        reload_action = QAction('Reload Page', self)
        reload_action.setShortcut('Ctrl+R')
        reload_action.setStatusTip('Reload the current page')
        menu.addAction(reload_action)

        hard_reload_action = QAction('Hard Reload', self)
        hard_reload_action.setShortcut('Ctrl+Shift+R')
        hard_reload_action.setStatusTip('Reload page ignoring cache')
        menu.addAction(hard_reload_action)

        menu.addSeparator()

        # Developer tools
        dev_tools_action = QAction('Developer Tools', self)
        dev_tools_action.setShortcut('F12')
        dev_tools_action.setStatusTip('Open developer tools')
        dev_tools_action.triggered.connect(self._toggle_dev_tools)
        menu.addAction(dev_tools_action)

    def _add_tools_menu_items(self, menu):
        """Add Tools menu items"""
        # AI tools
        ai_menu = menu.addMenu('AI Tools')
        ai_menu.setStatusTip('Access AI-powered tools')

        chat_action = QAction('AI Chat Assistant', self)
        chat_action.setShortcut('Ctrl+Shift+A')
        chat_action.setStatusTip('Open AI chat assistant')
        ai_menu.addAction(chat_action)

        code_gen_action = QAction('Code Generator', self)
        code_gen_action.setStatusTip('Generate code with AI')
        ai_menu.addAction(code_gen_action)

        text_analysis_action = QAction('Text Analysis', self)
        text_analysis_action.setStatusTip('Analyze text with AI')
        ai_menu.addAction(text_analysis_action)

        menu.addSeparator()

        # System tools
        settings_action = QAction('Settings...', self)
        settings_action.setShortcut('Ctrl+,')
        settings_action.setStatusTip('Open application settings')
        menu.addAction(settings_action)

        plugins_action = QAction('Manage Plugins...', self)
        plugins_action.setStatusTip('Install and manage plugins')
        menu.addAction(plugins_action)

        menu.addSeparator()

        # Utilities
        calculator_action = QAction('Calculator', self)
        calculator_action.setStatusTip('Open calculator')
        menu.addAction(calculator_action)

        color_picker_action = QAction('Color Picker', self)
        color_picker_action.setStatusTip('Pick colors from screen')
        menu.addAction(color_picker_action)

        menu.addSeparator()

        # System information
        system_info_action = QAction('System Information', self)
        system_info_action.setStatusTip('View system information')
        menu.addAction(system_info_action)

    def _add_help_menu_items(self, menu):
        """Add Help menu items"""
        # Help documentation
        help_action = QAction('User Guide', self)
        help_action.setShortcut('F1')
        help_action.setStatusTip('Open user guide')
        menu.addAction(help_action)

        tutorials_action = QAction('Tutorials', self)
        tutorials_action.setStatusTip('View video tutorials')
        menu.addAction(tutorials_action)

        shortcuts_action = QAction('Keyboard Shortcuts', self)
        shortcuts_action.setShortcut('Ctrl+/')
        shortcuts_action.setStatusTip('View keyboard shortcuts')
        menu.addAction(shortcuts_action)

        menu.addSeparator()

        # Online resources
        website_action = QAction('Visit Website', self)
        website_action.setStatusTip('Visit the official website')
        menu.addAction(website_action)

        community_action = QAction('Community Forum', self)
        community_action.setStatusTip('Join the community forum')
        menu.addAction(community_action)

        feedback_action = QAction('Send Feedback', self)
        feedback_action.setStatusTip('Send feedback to developers')
        menu.addAction(feedback_action)

        menu.addSeparator()

        # About
        about_action = QAction('About eCan.ai', self)
        about_action.setStatusTip('Show information about eCan.ai')
        about_action.triggered.connect(self._show_about)
        menu.addAction(about_action)

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

    def _toggle_dev_tools(self):
        """Toggle developer tools"""
        if hasattr(self, 'dev_tools_manager'):
            self.dev_tools_manager.toggle_dev_tools()

    def _show_about(self):
        """Show About dialog"""
        QMessageBox.about(self, "About eCan.AI",
                         "eCan.AI\nVersion 1.0.0\n\nAn AI-powered e-commerce automation platform.")




