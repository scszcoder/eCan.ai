"""
Modal overlay shown over the WebGUI while heavy startup work runs.

The user's Windows machine produced repeated `AppHangB1` WER reports because
the qasync event loop (which IS the Qt UI thread) was blocked by synchronous
agent skill build work during Phase 2 background initialization. Even with
the executor-offload fix in `build_agent_skills._create_skills_batch`, brief
UI-thread stalls can still happen during ramp-up. If the user clicks during
those stalls, Windows escalates to "Not Responding" → End Task.

This overlay sits on top of the WebGUI's central widget, swallows mouse and
keyboard events, and tells the user the app is initializing. It's purely a
UX guard rail — even if the underlying work stays on the UI thread, the
overlay prevents the user from generating click events that Windows can
escalate.

Usage:
    overlay = StartupBusyOverlay.show_on(web_gui)
    # ... heavy work ...
    overlay.dismiss()
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer, QEvent, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StartupBusyOverlay(QWidget):
    """Semi-transparent click-blocking overlay with a status message."""

    # Emitted by post_status() — Qt routes it back to the GUI thread via
    # an auto-connection, so callers from worker threads (e.g. the skill-build
    # ThreadPool) can update the status text without touching the widget
    # directly. The signal connects to set_status() in __init__.
    _statusChanged = Signal(str)

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._parent_widget = parent
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        # Intercept clicks before they can reach the WebEngine below.
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.WaitCursor)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(12)

        title = QLabel("Initializing agents…")
        title.setAlignment(Qt.AlignCenter)
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #e6edf3;")

        self._detail = QLabel(
            "Please wait — building agent skills and connecting services.\n"
            "Clicks are temporarily disabled to prevent Windows "
            "\"Not Responding\" interruptions."
        )
        self._detail.setAlignment(Qt.AlignCenter)
        self._detail.setWordWrap(True)
        self._detail.setStyleSheet("color: #8b949e; font-size: 13px;")

        self._dots_label = QLabel("●○○")
        self._dots_label.setAlignment(Qt.AlignCenter)
        self._dots_label.setStyleSheet("color: #58a6ff; font-size: 22px; letter-spacing: 6px;")

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(self._detail)
        layout.addWidget(self._dots_label)
        layout.addStretch(2)

        # Lightweight pulsing dots so the user can tell the overlay is alive
        # even when the main thread is briefly busy.
        self._dot_idx = 0
        self._dot_states = ["●○○", "○●○", "○○●"]
        self._timer = QTimer(self)
        self._timer.setInterval(450)
        self._timer.timeout.connect(self._tick_dots)
        self._timer.start()

        self._resize_to_parent()
        if parent is not None:
            parent.installEventFilter(self)

        # Route cross-thread status updates onto the GUI thread.
        self._statusChanged.connect(self.set_status)

    def _tick_dots(self) -> None:
        self._dot_idx = (self._dot_idx + 1) % len(self._dot_states)
        self._dots_label.setText(self._dot_states[self._dot_idx])

    def set_status(self, text: str) -> None:
        """Optional: update the detail line as init progresses. GUI thread only."""
        self._detail.setText(text)

    def post_status(self, text: str) -> None:
        """Thread-safe status update — safe to call from skill-build workers."""
        try:
            self._statusChanged.emit(text)
        except Exception:
            pass

    def _resize_to_parent(self) -> None:
        if self._parent_widget is None:
            return
        self.setGeometry(self._parent_widget.rect())

    def eventFilter(self, obj, event):
        if obj is self._parent_widget and event.type() == QEvent.Resize:
            self._resize_to_parent()
        return super().eventFilter(obj, event)

    def paintEvent(self, _event):
        # Semi-transparent dark backdrop so the underlying WebEngine
        # is still visible but visibly dimmed.
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(15, 20, 30, 215))

    # Swallow ALL interactive events so they can't reach the WebEngine.
    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        event.accept()

    def keyReleaseEvent(self, event):
        event.accept()

    def dismiss(self) -> None:
        try:
            self._timer.stop()
        except Exception:
            pass
        try:
            if self._parent_widget is not None:
                self._parent_widget.removeEventFilter(self)
        except Exception:
            pass
        self.hide()
        self.deleteLater()

    @classmethod
    def show_on(cls, web_gui) -> Optional["StartupBusyOverlay"]:
        """Construct and show an overlay over the given WebGUI's central widget.

        Returns the overlay instance, or None if the parent isn't ready yet.
        Safe to call from any thread that holds the Qt object — but creation
        must happen on the GUI thread (Qt invariant); callers that aren't on
        the GUI thread should use QMetaObject.invokeMethod or similar.
        """
        if web_gui is None:
            return None
        try:
            central = web_gui.centralWidget() if hasattr(web_gui, "centralWidget") else None
        except Exception:
            central = None
        if central is None:
            return None
        try:
            overlay = cls(central)
            overlay.show()
            overlay.raise_()
            return overlay
        except Exception:
            return None
