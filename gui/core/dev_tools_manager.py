"""
DevTools Manager module for handling developer tools functionality
"""

from PySide6.QtWidgets import QDockWidget, QWidget, QVBoxLayout
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtGui import QAction, QKeySequence
from utils.logger_helper import logger_helper as logger
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gui.WebGUI import WebGUI

class DevToolsManager(QWidget):
    """DevTools Manager class responsible for managing developer tools lifecycle and state"""

    # Define signals
    closed = Signal()
    
    def __init__(self, parent: 'WebGUI'):
        super().__init__(parent)
        self.parent: 'WebGUI' = parent

        # Get parent window size to calculate appropriate default height
        parent_height = parent.height() if parent else 800
        # Set default height to 30% of parent window height, minimum 280px, maximum 450px
        default_height = max(280, min(400, int(parent_height * 0.25)))

        # Set default size
        self.setMinimumSize(QSize(800, 280))  # Set appropriate minimum height
        self.resize(QSize(1000, default_height))  # Set initial size

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Create developer tools page and view
        self.dev_tools_page = QWebEnginePage(self)
        self.dev_tools_view = QWebEngineView()
        self.dev_tools_view.setPage(self.dev_tools_page)

        # Set developer tools page
        self.parent.web_engine_view.page().setDevToolsPage(self.dev_tools_page)

        # Add view to layout
        layout.addWidget(self.dev_tools_view)

        # Create Dock Widget
        self.dev_tools_dock = QDockWidget("Developer Tools", self.parent)
        self.dev_tools_dock.setWidget(self)
        # Set appropriate minimum height and default height
        self.dev_tools_dock.setMinimumHeight(280)
        self.dev_tools_dock.resize(1000, default_height)
        self.parent.addDockWidget(Qt.BottomDockWidgetArea, self.dev_tools_dock)
        self.dev_tools_dock.hide()

        # Setup shortcuts
        self._setup_shortcuts()

        # Connect title change signal using lambda function
        self.dev_tools_page.titleChanged.connect(
            lambda title: self.dev_tools_dock.setWindowTitle(f"Developer Tools - {title}")
        )

        # Set developer tools view style
        self.dev_tools_view.setStyleSheet("""
            QWebEngineView {
                border: none;
            }
        """)

        logger.info("DevTools initialized")
    
    def _setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        # F12 key to toggle developer tools
        toggle_action = QAction(self)
        toggle_action.setShortcut(QKeySequence(Qt.Key_F12))
        toggle_action.triggered.connect(self.toggle)
        self.addAction(toggle_action)

        # Esc key to close developer tools
        close_action = QAction(self)
        close_action.setShortcut(QKeySequence(Qt.Key_Escape))
        close_action.triggered.connect(self.hide)
        self.addAction(close_action)
    
    def toggle(self):
        """Toggle developer tools display state"""
        logger.info("Toggling developer tools...")
        if self.dev_tools_dock.isVisible():
            self.hide()
        else:
            self.show()

    def show(self):
        """Show developer tools"""
        # Adjust window size before showing
        self._adjust_window_size()
        self.dev_tools_dock.show()
        self.raise_()
        self.activateWindow()

    def _adjust_window_size(self):
        """Adjust developer tools window size based on current parent window size"""
        if not self.parent:
            return

        parent_height = self.parent.height()
        parent_width = self.parent.width()

        # Calculate appropriate height: 25-35% of parent window height
        optimal_height = max(280, min(400, int(parent_height * 0.25)))

        # Calculate appropriate width: at least 800px, but not exceeding parent window width
        optimal_width = max(800, min(parent_width, 1200))

        # Set dock widget size
        self.dev_tools_dock.resize(optimal_width, optimal_height)

        # If dock widget is already visible, try to adjust its proportion in parent window
        if self.dev_tools_dock.isVisible():
            # Get dock widget size policy and adjust
            self.dev_tools_dock.setMaximumHeight(int(parent_height * 0.5))  # Maximum not exceeding 50%
    
    def hide(self):
        """Hide developer tools"""
        self.dev_tools_dock.hide()
        self.closed.emit()

    def is_visible(self):
        """Check if developer tools is visible"""
        return self.dev_tools_dock.isVisible()

    def clear_all(self):
        """Clear all data (reload developer tools)"""
        self.parent.web_engine_view.page().setDevToolsPage(self.dev_tools_page)