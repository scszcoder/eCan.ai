"""
开发者工具插件模块，使用 Qt 官方的开发者工具
"""

from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence

class DevToolsPlugin(QWidget):
    """开发者工具插件类，使用 Qt 官方的开发者工具"""
    
    # 定义信号
    closed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 创建开发者工具页面和视图
        self.dev_tools_page = QWebEnginePage(self)
        self.dev_tools_view = QWebEngineView()
        self.dev_tools_view.setPage(self.dev_tools_page)
        
        # 设置开发者工具页面
        if hasattr(parent, 'web_engine'):
            parent.web_engine.page().setDevToolsPage(self.dev_tools_page)
        
        # 将视图添加到布局中
        layout.addWidget(self.dev_tools_view)
        
        # 设置快捷键
        self.setup_shortcuts()
        
        # 默认隐藏
        self.hide()
        
        # 连接标题变化信号
        self.dev_tools_page.titleChanged.connect(self.on_title_changed)
        
        # 设置开发者工具视图的样式
        self.dev_tools_view.setStyleSheet("""
            QWebEngineView {
                border: none;
            }
        """)
    
    def on_title_changed(self, title):
        """处理标题变化"""
        # 更新父窗口的标题
        if self.parent():
            self.parent().setWindowTitle("开发者工具")
    
    def setup_shortcuts(self):
        """设置快捷键"""
        # F12 键切换开发者工具
        toggle_action = QAction(self)
        toggle_action.setShortcut(QKeySequence(Qt.Key_F12))
        toggle_action.triggered.connect(self.toggle_dev_tools)
        self.addAction(toggle_action)
        
        # Esc 键关闭开发者工具
        close_action = QAction(self)
        close_action.setShortcut(QKeySequence(Qt.Key_Escape))
        close_action.triggered.connect(self.close_dev_tools)
        self.addAction(close_action)
    
    def toggle_dev_tools(self):
        """切换开发者工具显示状态"""
        if self.isVisible():
            self.close_dev_tools()
        else:
            self.show()
            # 确保窗口在最前面
            self.raise_()
            self.activateWindow()
    
    def close_dev_tools(self):
        """关闭开发者工具"""
        self.hide()
        self.closed.emit()
    
    def closeEvent(self, event):
        """处理关闭事件"""
        self.close_dev_tools()
        event.accept()
    
    def clear_all(self):
        """清除所有数据（重新加载开发者工具）"""
        if hasattr(self.parent(), 'web_engine'):
            self.parent().web_engine.page().setDevToolsPage(self.dev_tools_page) 