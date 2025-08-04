from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
import sys
import os
from gui.ipc.api import IPCAPI
from PySide6.QtGui import QPixmap  # Add this import
from PySide6.QtGui import QIcon  # Add this import
from PySide6.QtCore import Qt  # For high quality scaling

from PySide6.QtWidgets import QApplication

from config.app_settings import app_settings
from utils.logger_helper import logger_helper as logger
from gui.core.web_engine_view import WebEngineView
from gui.core.dev_tools_manager import DevToolsManager

# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"


class WebGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("eCan.ai")
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(100, 100, 1200, 800)

        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        # 创建 Web 引擎
        self.web_engine_view = WebEngineView(self)

        # 创建开发者工具管理器
        self.dev_tools_manager = DevToolsManager(self)

        # 设置 Windows 平台的窗口样式，与内容主题一致
        self._setup_window_style()

        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_engine_view.load_url(web_url)
                logger.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger.error("Failed to get web URL")
        
        # 添加 Web 引擎到布局
        layout.addWidget(self.web_engine_view)
        layout.setSpacing(0)

        # 设置快捷键（在所有组件初始化完成后）
        self._setup_shortcuts()

    def _setup_window_style(self):
        """设置窗口样式，与内容主题一致"""
        # Windows 平台特定的样式和原生设置
        if sys.platform == 'win32':
            # 设置 Windows 平台的灰色主题样式
            self.setStyleSheet("""
                QMainWindow {
                    background-color: #1a1a1a;  /* 深灰色背景 */
                    border: 1px solid #404040;  /* 中灰色边框 */
                    color: #e0e0e0;  /* 浅灰色文字 */
                }
                QMainWindow::title {
                    background-color: #2d2d2d;  /* 中深灰色标题栏 */
                    color: #e0e0e0;  /* 浅灰色文字 */
                    padding: 8px;
                    font-weight: 600;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
            """)

            # Windows 原生 API 设置
            try:
                # 导入 Windows API
                import ctypes

                # 获取窗口句柄
                hwnd = int(self.winId())

                # DWM API 常量
                DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                DWMWA_WINDOW_CORNER_PREFERENCE = 33
                DWMWCP_ROUND = 2

                # 设置深色标题栏（Windows 10/11）
                try:
                    dwmapi = ctypes.windll.dwmapi
                    value = ctypes.c_int(1)  # 启用深色模式
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_USE_IMMERSIVE_DARK_MODE,
                        ctypes.byref(value),
                        ctypes.sizeof(value)
                    )

                    # 设置圆角窗口（Windows 11）
                    corner_value = ctypes.c_int(DWMWCP_ROUND)
                    dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_WINDOW_CORNER_PREFERENCE,
                        ctypes.byref(corner_value),
                        ctypes.sizeof(corner_value)
                    )

                    logger.info("Windows 深色标题栏和样式已应用")

                except Exception as e:
                    logger.warning(f"设置深色标题栏失败: {e}")

            except Exception as e:
                logger.warning(f"设置 Windows 窗口样式失败: {e}")
        else:
            # 非 Windows 平台，不应用任何样式
            logger.info(f"当前平台 {sys.platform} 不支持自定义窗口样式，保持系统默认样式")

    def _apply_messagebox_style(self, msg_box):
        """为 QMessageBox 应用灰色主题样式（仅 Windows 平台）"""
        if sys.platform == 'win32':
            msg_box.setStyleSheet("""
                QMessageBox {
                    background-color: #2d2d2d;  /* 中深灰色背景 */
                    color: #e0e0e0;  /* 浅灰色文字 */
                    border: 1px solid #404040;  /* 中灰色边框 */
                    border-radius: 8px;  /* 圆角 */
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                QMessageBox::title {
                    background-color: #1a1a1a;  /* 深灰色标题栏背景 */
                    color: #e0e0e0;  /* 浅灰色标题文字 */
                    padding: 8px 12px;
                    font-weight: 600;
                    font-size: 14px;
                    border-bottom: 1px solid #404040;  /* 标题栏底部分割线 */
                }
                QMessageBox QLabel {
                    background-color: transparent;
                    color: #e0e0e0;  /* 浅灰色文字 */
                    font-size: 14px;
                    padding: 10px;
                }
                QMessageBox QPushButton {
                    background-color: #404040;  /* 中灰色按钮背景 */
                    color: #e0e0e0;  /* 浅灰色按钮文字 */
                    border: 1px solid #606060;  /* 稍亮的边框 */
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 500;
                    min-width: 80px;
                }
                QMessageBox QPushButton:hover {
                    background-color: #505050;  /* 悬停时稍亮 */
                    border-color: #707070;
                }
                QMessageBox QPushButton:pressed {
                    background-color: #353535;  /* 按下时稍暗 */
                }
                QMessageBox QPushButton:default {
                    background-color: #5a5a5a;  /* 默认按钮稍亮 */
                    border-color: #707070;
                }
                QMessageBox QPushButton:default:hover {
                    background-color: #656565;
                }
            """)
            logger.info("MessageBox Windows 样式已应用")
        else:
            # 非 Windows 平台，保持系统默认样式
            logger.info(f"当前平台 {sys.platform} 不支持自定义 MessageBox 样式，保持系统默认样式")

    def _apply_dark_titlebar_to_messagebox(self, msg_box):
        """为 MessageBox 应用 Windows 深色标题栏"""
        try:
            import ctypes

            # 显示对话框以获取窗口句柄
            msg_box.show()

            # 获取 MessageBox 的窗口句柄
            hwnd = int(msg_box.winId())

            # DWM API 常量
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20

            # 设置深色标题栏
            dwmapi = ctypes.windll.dwmapi
            value = ctypes.c_int(1)  # 启用深色模式
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value),
                ctypes.sizeof(value)
            )

            # 隐藏对话框，等待正式显示
            msg_box.hide()

            logger.info("MessageBox 深色标题栏已应用")

        except Exception as e:
            logger.warning(f"设置 MessageBox 深色标题栏失败: {e}")

    def load_local_html(self):
        """加载本地 HTML 文件"""
        index_path = app_settings.dist_dir / "index.html"
        logger.info(f"Looking for index.html at: {index_path}")
        
        if index_path.exists():
            try:
                # 直接加载本地文件
                self.web_engine_view.load_local_file(index_path)
                logger.info(f"Production mode: Loading from {index_path}")
                
            except Exception as e:
                logger.error(f"Error loading HTML file: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.error(f"index.html not found in {app_settings.dist_dir}")
            # 列出目录内容以便调试
            if app_settings.dist_dir.exists():
                logger.info(f"Contents of {app_settings.dist_dir}:")
                for item in app_settings.dist_dir.iterdir():
                    logger.info(f"  - {item.name}")
            else:
                logger.error(f"Directory {app_settings.dist_dir} does not exist")
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        # 开发者工具快捷键
        self.dev_tools_shortcut = QShortcut(QKeySequence("F12"), self)
        self.dev_tools_shortcut.activated.connect(self.dev_tools_manager.toggle)
        
        # F5 重新加载
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L 清除日志
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools_manager.clear_all)
        self.addAction(clear_logs_action)

    def self_confirm(self):
        print("self confirming top web gui....")

    def reload(self):
        """重新加载页面"""
        logger.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_engine_view.reload_page()
        else:
            self.load_local_html()
    
    def closeEvent(self, event):
        """窗口关闭事件 - 调试版本"""
        print("🔔 [DEBUG] closeEvent 被调用")
        logger.info("closeEvent triggered")

        try:
            print("🔔 [DEBUG] 创建确认对话框")
            # 创建自定义对话框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle('Confirm Exit')
            msg_box.setText('Are you sure you want to exit the program?')
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            msg_box.setDefaultButton(QMessageBox.No)

            # 设置对话框的灰色主题样式
            self._apply_messagebox_style(msg_box)

            # 为 Windows 平台设置深色标题栏
            if sys.platform == 'win32':
                self._apply_dark_titlebar_to_messagebox(msg_box)

            # 尝试设置图标，如果失败就使用默认图标
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

            print("🔔 [DEBUG] 显示对话框")
            reply = msg_box.exec()
            print(f"🔔 [DEBUG] 用户选择: {reply}")

            if reply == QMessageBox.Yes:
                print("🔔 [DEBUG] 用户确认退出")
                logger.info("User confirmed exit")
                event.accept()

                print("🔔 [DEBUG] 开始退出流程")

                # 停止 LightragServer
                try:
                    print("🔔 [DEBUG] 停止 LightragServer")
                    from app_context import AppContext
                    ctx = AppContext()
                    if ctx.main_window and hasattr(ctx.main_window, 'lightrag_server'):
                        print("🔔 [DEBUG] 找到 LightragServer，正在停止...")
                        ctx.main_window.lightrag_server.stop()
                        print("🔔 [DEBUG] LightragServer 已停止")
                    else:
                        print("🔔 [DEBUG] 未找到 LightragServer 或 MainWindow")
                except Exception as e:
                    print(f"🔔 [DEBUG] 停止 LightragServer 时出错: {e}")
                    logger.warning(f"Error stopping LightragServer: {e}")

                # 强制退出
                import os
                print("🔔 [DEBUG] 调用 os._exit(0)")
                logger.info("Force exiting with os._exit(0)")
                os._exit(0)

            else:
                print("🔔 [DEBUG] 用户取消退出")
                logger.info("User cancelled exit")
                event.ignore()

        except Exception as e:
            print(f"🔔 [DEBUG] closeEvent 异常: {e}")
            logger.error(f"closeEvent exception: {e}")
            import traceback
            traceback.print_exc()
            event.ignore()


 
    def get_ipc_api(self):
        return IPCAPI.get_instance()