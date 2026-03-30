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
    """DevTools Manager class responsible for managing developer tools lifecycle and state.

    DevTools WebEngine components are created lazily — only when the user first opens
    the DevTools panel.  This saves a full QtWebEngine rendering process when the
    panel is never used.
    """

    # Define signals
    closed = Signal()

    def __init__(self, parent: 'WebGUI'):
        super().__init__(parent)
        self.parent: 'WebGUI' = parent

        # Get parent window size to calculate appropriate default height
        parent_height = parent.height() if parent else 800
        # Set default height to 25% of parent window height, minimum 280px, maximum 400px
        default_height = max(280, min(400, int(parent_height * 0.25)))

        # Set default size on self (widget container)
        self.setMinimumSize(QSize(800, 280))
        self.resize(QSize(1000, default_height))

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # DevTools components are created lazily on first open (lazy pattern:
        # avoids a second QtWebEnginePage + QWebEngineView process until needed).
        self.dev_tools_page: QWebEnginePage | None = None
        self.dev_tools_view: QWebEngineView | None = None
        self.dev_tools_dock: QDockWidget | None = None

        # Create Dock Widget shell immediately (so toggle/hide can work before first open)
        self.dev_tools_dock = QDockWidget("Developer Tools", self.parent)
        self.dev_tools_dock.setWidget(self)
        self.dev_tools_dock.setMinimumHeight(280)
        self.dev_tools_dock.resize(1000, default_height)
        self.parent.addDockWidget(Qt.BottomDockWidgetArea, self.dev_tools_dock)
        self.dev_tools_dock.hide()

        # Setup keyboard shortcuts (before lazy creation so shortcuts work immediately)
        self._setup_shortcuts()

        logger.info("DevTools manager created (DevTools view will be created lazily on first open)")

    # ── Lazy initialiser ──────────────────────────────────────────────────────────

    def _ensure_devtools(self) -> None:
        """Create DevTools WebEngine components on first use (lazy init).

        This avoids keeping a second QtWebEnginePage + QWebEngineView process alive
        when the user never opens the DevTools panel.
        """
        if self.dev_tools_page is not None:
            return  # Already initialised

        from PySide6.QtWebEngineCore import QWebEnginePage
        from PySide6.QtWebEngineWidgets import QWebEngineView

        page = QWebEnginePage(self)
        view = QWebEngineView()
        view.setPage(page)
        page.setParent(self)  # Ownership to self so they are cleaned up with the widget

        # Attach DevTools to the main page (this can be called at any time)
        self.parent.web_engine_view.page().setDevToolsPage(page)

        # Connect title-changed signal
        page.titleChanged.connect(
            lambda title: self.dev_tools_dock.setWindowTitle(f"Developer Tools - {title}") if self.dev_tools_dock else None
        )

        # Apply minimal styling
        view.setStyleSheet("QWebEngineView { border: none; }")

        # Store references
        self.dev_tools_page = page
        self.dev_tools_view = view

        # Add the DevTools view to our layout
        self.layout().addWidget(view)

        logger.info("DevTools lazy-initialised (WebEngine page + view created)")

    # ── Shortcuts ─────────────────────────────────────────────────────────────────

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

    # ── Public API ───────────────────────────────────────────────────────────────

    def toggle(self):
        """Toggle developer tools display state"""
        logger.info("Toggling developer tools...")
        if self.dev_tools_dock.isVisible():
            self.hide()
        else:
            self.show()

    def show(self):
        """Show developer tools (lazy: creates WebEngine components on first call)"""
        self._ensure_devtools()
        self._adjust_window_size()
        self.dev_tools_dock.show()
        self.raise_()
        self.activateWindow()

    def _adjust_window_size(self):
        """Adjust developer tools window size based on current parent window size"""
        if not self.parent or not self.dev_tools_dock:
            return

        parent_height = self.parent.height()
        parent_width = self.parent.width()

        # Calculate appropriate height: 25-35% of parent window height
        optimal_height = max(280, min(400, int(parent_height * 0.25)))
        optimal_width = max(800, min(parent_width, 1200))

        self.dev_tools_dock.resize(optimal_width, optimal_height)

        if self.dev_tools_dock.isVisible():
            self.dev_tools_dock.setMaximumHeight(int(parent_height * 0.5))

    def hide(self):
        """Hide developer tools"""
        if self.dev_tools_dock:
            self.dev_tools_dock.hide()
        self.closed.emit()

    def is_visible(self):
        """Check if developer tools is visible"""
        return bool(self.dev_tools_dock and self.dev_tools_dock.isVisible())

    def clear_all(self):
        """Clear all data (reload developer tools)"""
        self._ensure_devtools()
        if self.dev_tools_page:
            self.parent.web_engine_view.page().setDevToolsPage(self.dev_tools_page)