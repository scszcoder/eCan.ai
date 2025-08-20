from PySide6.QtCore import Qt, QThread, QObject, Signal, QRectF, QTimer
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QFont, QConicalGradient
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QProgressBar,
    QHBoxLayout,
    QApplication,
    QGraphicsDropShadowEffect,
)
import os
from datetime import datetime
import sys
import json

try:
    from config.app_info import app_info
except Exception:
    app_info = None


class ThemedSplashScreen(QWidget):
    """
    A modern splash screen following the provided spec:
    640x400 frameless window, rounded container, centered column (logo, title,
    subtitle, indeterminate progress, status), bottom footer (version & copyright).
    """

    def __init__(self):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(640, 400)

        self._build_ui()
        self._center_on_screen()

    def _build_ui(self):
        app_name = 'eCan'

        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(
            """
            QWidget#container {
                background-color: #0f172a; /* --bg-primary */
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }

            /* Content */
            QLabel#title {
                color: #f8fafc;
                font-size: 26px;
                font-weight: 700;
                letter-spacing: 0.4px;
                padding: 0px;
            }
            QLabel#subtitle { color: #94a3b8; font-size: 14px; }
            QLabel#status   { color: #94a3b8; font-size: 12px; }
            QLabel#meta     { color: #94a3b8; font-size: 11px; }
            QLabel#copy     { color: #64748b; font-size: 10px; }

            QProgressBar {
                background-color: #1e293b;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                height: 16px; /* increase to fit centered text */
                color: #f8fafc;
            }
            QProgressBar::chunk {
                border-radius: 6px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #8b5cf6);
            }
            """
        )

        # subtle shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setXOffset(0)
        shadow.setYOffset(8)
        shadow.setColor(Qt.black)
        container.setGraphicsEffect(shadow)

        # Root layout
        root_v = QVBoxLayout(container)
        root_v.setContentsMargins(18, 18, 18, 18)
        root_v.setSpacing(10)

        # Center column
        center = QWidget()
        center.setFixedWidth(520)
        col = QVBoxLayout(center)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(10)

        # Logo
        self.logo_label = QLabel()
        self.logo_label.setAlignment(Qt.AlignCenter)
        self.logo_label.setFixedSize(96, 96)
        logo_pixmap = self._load_logo_pixmap()
        if logo_pixmap:
            self.logo_label.setPixmap(logo_pixmap.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        col.addWidget(self.logo_label, alignment=Qt.AlignCenter)

        # Title and subtitle
        title = QLabel(app_name)
        title.setObjectName("title")
        title.setAlignment(Qt.AlignHCenter)
        subtitle = QLabel("Your Intelligent E-Commerce Agent Network")
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        subtitle.setAlignment(Qt.AlignHCenter)
        col.addWidget(title)
        col.addWidget(subtitle)

        # Progress (indeterminate initially)
        self.progress_bar = QProgressBar()
        # Start determinate at 0 so format displays immediately
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0%")
        self.progress_bar.setAlignment(Qt.AlignCenter)
        col.addWidget(self.progress_bar)

        # Status text
        self.status_label = QLabel("loading…")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignHCenter)
        col.addWidget(self.status_label)

        # Vertical centering relative to footer
        root_v.addStretch(1)
        root_v.addWidget(center, alignment=Qt.AlignHCenter)
        root_v.addStretch(2)

        # Footer row (version left, copyright right)
        footer = QWidget()
        footer_h = QHBoxLayout(footer)
        footer_h.setContentsMargins(0, 0, 0, 0)
        footer_h.setSpacing(8)
        version_label = QLabel(f"v{self._get_version()}")
        version_label.setObjectName("meta")
        copy_label = QLabel(f"© {datetime.now().year} eCan.ai Team")
        copy_label.setObjectName("meta")
        footer_h.addWidget(version_label)
        footer_h.addStretch(1)
        footer_h.addWidget(copy_label)
        root_v.addWidget(footer)

        # Combined progress state (Python + Web)
        self._progress_value = 0
        self._web_progress = 0
        self._py_progress = 0
        self._web_done = False
        self._py_done = False
        self._target_main_window = None
        self._is_hidden = False

        # Start Python initialization in background thread to avoid blocking UI
        self._py_thread = QThread(self)
        try:
            self._py_thread.setObjectName('SplashInitThread')
        except Exception:
            pass
        self._py_worker = PythonInitWorker()
        self._py_worker.moveToThread(self._py_thread)
        self._py_thread.started.connect(self._py_worker.run)
        self._py_worker.progress.connect(self._on_py_progress)
        self._py_worker.status_update.connect(self._on_status_update)
        self._py_worker.finished.connect(self._on_py_finished)
        self._py_worker.finished.connect(self._py_thread.quit)
        self._py_worker.finished.connect(self._py_worker.deleteLater)
        self._py_thread.finished.connect(self._py_thread.deleteLater)
        self._py_thread.start()

        # Ensure cleanup on app exit
        try:
            app = QApplication.instance()
            if app is not None:
                app.aboutToQuit.connect(self._ensure_thread_stopped)
        except Exception:
            pass

        # put container into main widget
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(container)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        sg = screen.availableGeometry()
        self.move(
            sg.center().x() - self.width() // 2,
            sg.center().y() - self.height() // 2,
        )

    def showEvent(self, event):
        """Override showEvent to ensure the window is always centered when shown"""
        super().showEvent(event)
        # Re-center the window after it's shown to ensure it's always in the center
        QTimer.singleShot(0, self._center_on_screen)

    def _load_logo_pixmap(self):
        # Prefer the specified logo path
        if app_info:
            base = app_info.app_resources_path
        else:
            base = os.path.join(os.path.dirname(__file__), '..', 'resource')

        candidates = [
            os.path.join(base, 'images', 'logos', 'logoWhite22.png'),
            # fallbacks
            os.path.join(base, 'images', 'logos', 'dock_256x256.png'),
            os.path.join(base, 'images', 'logos', 'rounded', 'dock_256x256.png'),
            os.path.join(base, 'images', 'logos', 'desktop_256x256.png'),
        ]
        for p in candidates:
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    return pm
        return None

    def _get_version(self) -> str:
        # Try to read VERSION file similar to app_setup_helper
        try_paths = [
            os.path.join(os.path.dirname(__file__), '..', 'VERSION'),
            os.path.join(os.path.dirname(__file__), '..', '..', 'VERSION'),
        ]
        for p in try_paths:
            try:
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        v = f.read().strip()
                        if v:
                            return v
            except Exception:
                pass

    # Spinner no longer used; kept for reference if needed
    def _load_spinner_movie(self):
        return None

    def set_status(self, text: str):
        try:
            if hasattr(self, 'status_label') and self.status_label is not None:
                self.status_label.setText(str(text))
                # Force immediate repaint of the status label
                self.status_label.repaint()
                QApplication.processEvents()
        except Exception:
            pass

    def set_progress(self, value: int):
        try:
            # Treat as WebView load progress
            self._web_progress = max(0, min(100, int(value)))
            self._update_combined()
            # Force immediate UI update
            QApplication.processEvents()
        except Exception:
            pass

    def finish(self, main_window=None):
        try:
            # Mark web as done; only close when both web and python are done
            self._web_done = True
            if main_window is not None:
                self._target_main_window = main_window
            # Hide immediately once web is ready; keep initialization running
            self._hide_now()
            # Delete later when python init finishes
            self._maybe_delete()
        except Exception:
            pass

    # Python-side progress handlers
    def _on_py_progress(self, value: int):
        try:
            self._py_progress = max(0, min(100, int(value)))
            self._update_combined()
        except Exception:
            pass

    def _on_py_finished(self):
        try:
            self._py_done = True
            self._maybe_delete()
        except Exception:
            pass

    def _on_status_update(self, status: str):
        """Handle status updates from Python initialization worker"""
        try:
            self.set_status(status)
            # Force immediate UI update
            QApplication.processEvents()
        except Exception:
            pass

    def _update_combined(self):
        try:
            combined = int(round((self._web_progress + self._py_progress) / 2))
            if combined != self._progress_value:
                self._progress_value = combined
                # Switch to determinate once we have a numeric value
                if hasattr(self, 'progress_bar') and self.progress_bar is not None:
                    # Already determinate; ensure value and text are updated
                    self.progress_bar.setValue(self._progress_value)
                    try:
                        # Show centered percentage text
                        self.progress_bar.setFormat(f"{self._progress_value}%")
                        self.progress_bar.setAlignment(Qt.AlignCenter)
                        # Force immediate repaint of the progress bar
                        self.progress_bar.repaint()
                    except Exception:
                        pass
        except Exception:
            pass

    def _hide_now(self):
        try:
            if not self._is_hidden:
                self._is_hidden = True
                self.hide()
        except Exception:
            pass

    def _maybe_delete(self):
        if not (self._web_done and self._py_done):
            return
        # Defer delete to next event loop turn
        QTimer.singleShot(0, self._finalize_delete)

    def _finalize_delete(self):
        try:
            self._progress_value = 100
            # By now python thread should be finished via _on_py_finished
            self.deleteLater()
        except Exception:
            pass

    def _ensure_thread_stopped(self, timeout_ms: int = 3000):
        try:
            if hasattr(self, '_py_thread') and self._py_thread is not None:
                if self._py_thread.isRunning():
                    try:
                        self._py_thread.quit()
                    except Exception:
                        pass
                    try:
                        self._py_thread.wait(timeout_ms)
                    except Exception:
                        pass
        finally:
            try:
                if hasattr(self, '_py_thread') and self._py_thread is not None:
                    self._py_thread.deleteLater()
            except Exception:
                pass
            try:
                self._py_thread = None
            except Exception:
                pass

    def closeEvent(self, event):
        try:
            self._ensure_thread_stopped()
        except Exception:
            pass
        event.accept()

    def __del__(self):
        try:
            self._ensure_thread_stopped()
        except Exception:
            pass


class CircularProgress(QWidget):
    def __init__(self, diameter: int = 160, thickness: int = 10, parent=None):
        super().__init__(parent)
        self._value = 0
        self._diameter = max(80, diameter)
        self._thickness = max(6, thickness)
        self.setFixedSize(self._diameter, self._diameter)

    def set_value(self, value: int):
        new_val = max(0, min(100, int(value)))
        if new_val != self._value:
            self._value = new_val
            self.update()

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setRenderHint(QPainter.HighQualityAntialiasing, True)

            # Compute an inner rect that accounts for pen thickness to avoid clipping
            pen_width = float(self._thickness)
            margin = pen_width / 2.0 + 2.0
            rect = QRectF(margin, margin, self.width() - 2 * margin, self.height() - 2 * margin)

            # Background track
            track_pen = QPen(QColor("#1e293b"))
            track_pen.setWidthF(pen_width)
            painter.setPen(track_pen)
            painter.drawEllipse(rect)

            # Progress arc (start at top, clockwise)
            start_angle = 90 * 16  # 90 deg is top in Qt (but clockwise with negative span)
            span_angle = -int(360 * 16 * (self._value / 100.0))

            # Gradient for arc
            grad = QConicalGradient(rect.center(), -90)
            grad.setColorAt(0.0, QColor("#3b82f6"))
            grad.setColorAt(1.0, QColor("#8b5cf6"))
            arc_pen = QPen(grad, pen_width)
            arc_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(arc_pen)
            painter.drawArc(QRectF(rect), start_angle, span_angle)

            # Percent text
            painter.setPen(QColor("#f8fafc"))
            font = QFont()
            font.setPointSize(14)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignCenter, f"{self._value}%")


class PythonInitWorker(QObject):
    progress = Signal(int)
    status_update = Signal(str)
    finished = Signal()

    def run(self):
        try:
            # Phase 1: Basic initialization
            self.status_update.emit("Initializing Python environment...")
            self.progress.emit(5)

            # Phase 2: Import core modules
            self.status_update.emit("Loading core modules...")
            self.progress.emit(15)

            # Phase 3: Database migration
            self.status_update.emit("Checking database...")
            try:
                from agent.chats.db_migration import DBMigration
                migration = DBMigration()
                ok = migration.upgrade_to_version('2.0.0', 'Auto-upgrade at startup')
                self.progress.emit(35 if not ok else 45)
                if ok:
                    self.status_update.emit("Database updated successfully")
                else:
                    self.status_update.emit("Database check completed")
            except Exception as e:
                self.status_update.emit("Database initialization failed")
                self.progress.emit(35)

            # Phase 4: Load configuration
            self.status_update.emit("Loading configuration...")
            self.progress.emit(55)

            # Phase 5: Initialize services
            self.status_update.emit("Initializing services...")
            self.progress.emit(70)

            # Phase 6: Prepare GUI components
            self.status_update.emit("Preparing interface...")
            self.progress.emit(85)

            # Phase 7: Final preparations
            self.status_update.emit("Finalizing startup...")
            self.progress.emit(95)

        finally:
            self.status_update.emit("Ready to launch!")
            self.progress.emit(100)
            self.finished.emit()


class StartupProgressManager:
    """Manages startup progress updates for the splash screen"""

    def __init__(self, splash_screen):
        self.splash = splash_screen
        self.current_progress = 0

    def update_progress(self, progress: int, status: str = None):
        """Update progress and optionally status"""
        if self.splash:
            self.current_progress = max(self.current_progress, progress)
            self.splash.set_progress(self.current_progress)
            if status:
                self.splash.set_status(status)
            QApplication.processEvents()

    def update_status(self, status: str):
        """Update only status text"""
        if self.splash:
            self.splash.set_status(status)
            QApplication.processEvents()

    def finish(self, main_window=None):
        """Finish the splash screen"""
        if self.splash:
            self.splash.finish(main_window)


def init_startup_splash():
    """
    Ensure QApplication exists, create and show ThemedSplashScreen immediately,
    and process initial events. Returns the splash instance (or None on failure).
    """
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            app = QApplication(sys.argv)
        splash = ThemedSplashScreen()
        splash.show()
        app.processEvents()
        # Ensure the splash is centered after showing and processing events
        splash._center_on_screen()
        app.processEvents()
        return splash
    except Exception:
        return None


def create_startup_progress_manager(splash_screen):
    """Create a startup progress manager for the given splash screen"""
    return StartupProgressManager(splash_screen)


