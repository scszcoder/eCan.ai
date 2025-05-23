"""
DevTools 管理器模块，处理开发者工具相关的功能
"""

from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QAction, QKeySequence
from utils.logger_helper import logger_helper
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.WebGUI import WebGUI

class DevToolsManager(QWidget):
    """DevTools 管理器类，负责管理开发者工具的生命周期和状态"""
    
    # 定义信号
    closed = Signal()
    
    def __init__(self, parent: 'WebGUI'):
        super().__init__(parent)
        self.parent: 'WebGUI' = parent
        
        # 设置默认大小
        self.setMinimumSize(QSize(800, 300))
        
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建开发者工具页面和视图
        self.dev_tools_page = QWebEnginePage(self)
        self.dev_tools_view = QWebEngineView()
        self.dev_tools_view.setPage(self.dev_tools_page)
        
        # 设置开发者工具页面
        self.parent.web_engine_view.page().setDevToolsPage(self.dev_tools_page)
        
        # 将视图添加到布局中
        layout.addWidget(self.dev_tools_view)
        
        # 创建 Dock Widget
        self.dev_tools_dock = QDockWidget("开发者工具", self.parent)
        self.dev_tools_dock.setWidget(self)
        self.dev_tools_dock.setMinimumHeight(300)
        self.parent.addDockWidget(Qt.BottomDockWidgetArea, self.dev_tools_dock)
        self.dev_tools_dock.hide()
        
        # 设置快捷键
        self._setup_shortcuts()
        
        # 连接标题变化信号，使用 lambda 函数来处理
        self.dev_tools_page.titleChanged.connect(
            lambda title: self.dev_tools_dock.setWindowTitle(f"开发者工具 - {title}")
        )
        
        # 设置开发者工具视图的样式
        self.dev_tools_view.setStyleSheet("""
            QWebEngineView {
                border: none;
            }
        """)
        
        logger_helper.info("DevTools initialized")
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        # F12 键切换开发者工具
        toggle_action = QAction(self)
        toggle_action.setShortcut(QKeySequence(Qt.Key_F12))
        toggle_action.triggered.connect(self.toggle)
        self.addAction(toggle_action)
        
        # Esc 键关闭开发者工具
        close_action = QAction(self)
        close_action.setShortcut(QKeySequence(Qt.Key_Escape))
        close_action.triggered.connect(self.hide)
        self.addAction(close_action)
    
    def toggle(self):
        """切换开发者工具显示状态"""
        logger_helper.info("Toggling developer tools...")
        if self.dev_tools_dock.isVisible():
            self.hide()
        else:
            self.show()
    
    def show(self):
        """显示开发者工具"""
        self.dev_tools_dock.show()
        self.raise_()
        self.activateWindow()
    
    def hide(self):
        """隐藏开发者工具"""
        self.dev_tools_dock.hide()
        self.closed.emit()
    
    def is_visible(self):
        """检查开发者工具是否可见"""
        return self.dev_tools_dock.isVisible()
    
    def clear_all(self):
        """清除所有数据（重新加载开发者工具）"""
        self.parent.web_engine_view.page().setDevToolsPage(self.dev_tools_page) 