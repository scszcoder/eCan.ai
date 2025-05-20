"""
开发者工具插件模块，使用 Qt 官方的开发者工具
"""

from PySide6.QtWidgets import QDockWidget
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtCore import Qt

class DevToolsPlugin(QDockWidget):
    """开发者工具插件类，使用 Qt 官方的开发者工具"""
    
    def __init__(self, parent=None):
        super().__init__("开发者工具", parent)
        self.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable)
        
        # 创建开发者工具页面和视图
        self.dev_tools_page = QWebEnginePage(self)
        self.dev_tools_view = QWebEngineView(self)
        self.dev_tools_view.setPage(self.dev_tools_page)
        
        # 设置开发者工具页面
        if hasattr(parent, 'web_engine'):
            parent.web_engine.page().setDevToolsPage(self.dev_tools_page)
        
        # 设置开发者工具视图
        self.setWidget(self.dev_tools_view)
        
        # 默认隐藏
        self.hide()
    
    def toggle_dev_tools(self):
        """切换开发者工具显示状态"""
        if self.isVisible():
            self.hide()
        else:
            self.show()
    
    def clear_all(self):
        """清除所有数据（重新加载开发者工具）"""
        if hasattr(self.parent(), 'web_engine'):
            self.parent().web_engine.page().setDevToolsPage(self.dev_tools_page) 