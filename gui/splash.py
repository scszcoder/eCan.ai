from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QColor
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

try:
    from config.app_info import app_info
except Exception:
    app_info = None


# Internationalization for splash screen
class SplashMessages:
    """Simple i18n support for splash screen."""
    
    DEFAULT_LANG = 'zh-CN'
    
    MESSAGES = {
        'en-US': {
            'app_subtitle': 'Your Intelligent E-Commerce Agent Network',
            'loading': 'Loading...',
            'initializing': 'Initializing...',
            'init_python_env': 'Initializing APP environment...',
            'loading_core_modules': 'Loading core modules...',
            'loading_config': 'Loading configuration...',
            'init_services': 'Initializing services...',
            'preparing_gui': 'Preparing interface...',
            'finalizing': 'Finalizing startup...',
            'ready': 'Ready to launch!',
        },
        'zh-CN': {
            'app_subtitle': '您的智能电商智能体网络平台',
            'loading': '加载中...',
            'initializing': '初始化中...',
            'init_python_env': '初始化应用环境...',
            'loading_core_modules': '加载核心模块...',
            'loading_config': '加载配置...',
            'init_services': '初始化服务...',
            'preparing_gui': '准备界面...',
            'finalizing': '完成启动...',
            'ready': '准备启动!',
        }
    }
    
    def __init__(self):
        from utils.i18n_helper import detect_language
        self.language = detect_language(
            default_lang=self.DEFAULT_LANG,
            supported_languages=list(self.MESSAGES.keys())
        )
        print(f"[Splash] Language: {self.language}")
    
    def get(self, key: str) -> str:
        """Get localized message."""
        lang = self.language if self.language in self.MESSAGES else self.DEFAULT_LANG
        return self.MESSAGES[lang].get(key, key)


# Global instance - lazy initialization
_splash_messages = None

def _get_splash_messages():
    """Get SplashMessages instance with lazy initialization."""
    global _splash_messages
    if _splash_messages is None:
        _splash_messages = SplashMessages()
    return _splash_messages


class ThemedSplashScreen(QWidget):
    """
    A modern splash screen following the provided spec:
    640x400 frameless window, rounded container, centered column (logo, title,
    subtitle, indeterminate progress, status), bottom footer (version & copyright).
    """

    def __init__(self):
        # Initialize ALL state variables FIRST, before any other operations
        self._is_deleted = False
        self._is_hidden = False
        self._centered_on_show = False
        self._center_timers = []
        self._last_center_pos = None

        # Use additional window flags for better Windows compatibility
        window_flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if sys.platform == 'win32':
            # Additional Windows-specific flags to reduce flicker
            window_flags |= Qt.Tool  # Prevents taskbar entry and reduces flicker

        super().__init__(None, window_flags)

        # Set attributes to reduce flicker and improve appearance
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(640, 400)

        # Set window properties for better positioning
        self.setWindowFlags(window_flags)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Install event filter for Windows-specific handling
        if sys.platform == 'win32':
            self.installEventFilter(self)

        # Build UI first, then position
        self._build_ui()
        # Defer centering until after show

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

        # Optimized shadow effect - reduce blur radius for better performance
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)  # Reduced from 28 for better performance
        shadow.setXOffset(0)
        shadow.setYOffset(6)  # Reduced from 8
        shadow.setColor(QColor(0, 0, 0, 180))  # Slightly transparent
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
        subtitle = QLabel(_get_splash_messages().get('app_subtitle'))
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
        self.status_label = QLabel(_get_splash_messages().get('loading'))
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
        from PySide6.QtCore import QThread
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
        """Center the splash screen on the primary screen with Windows-specific handling"""
        # Check if object is still valid
        if self._is_deleted or not hasattr(self, '_is_deleted'):
            return

        try:
            # Prefer the screen where this window is (after show), fallback to cursor screen, then primary
            from PySide6.QtGui import QGuiApplication, QCursor
            screen = self.screen()
            if screen is None:
                screen = QGuiApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
            if not screen:
                return

            # Get screen geometry
            sg = screen.availableGeometry()

            # Calculate center position
            x = sg.center().x() - self.width() // 2
            y = sg.center().y() - self.height() // 2

            # Ensure position is within screen bounds
            x = max(sg.left(), min(x, sg.right() - self.width()))
            y = max(sg.top(), min(y, sg.bottom() - self.height()))

            # Prefer Windows API for frameless windows to avoid (0,0) jumps
            if sys.platform == 'win32' and self.windowFlags() & Qt.FramelessWindowHint:
                try:
                    import ctypes
                    hwnd = int(self.winId())
                    if hwnd:
                        user32 = ctypes.windll.user32
                        SWP_NOSIZE = 0x0001
                        SWP_NOZORDER = 0x0004
                        SWP_SHOWWINDOW = 0x0040
                        user32.SetWindowPos(hwnd, 0, x, y, 0, 0, SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW)
                    else:
                        self.move(x, y)
                except Exception:
                    self.move(x, y)
            else:
                # Fallback to Qt positioning
                self.move(x, y)

            # Force update and ensure window is properly positioned
            self.update()
            QApplication.processEvents()
            try:
                # Minimal logging to help diagnose positioning issues
                from utils.logger_helper import logger_helper as logger
                final_pos = self.pos()
                # Record last stable position
                try:
                    from PySide6.QtCore import QPoint
                    self._last_center_pos = QPoint(final_pos.x(), final_pos.y())
                except Exception:
                    self._last_center_pos = final_pos
                logger.info(f"[Splash] Final position: ({final_pos.x()}, {final_pos.y()})")
            except Exception:
                pass
        except RuntimeError as e:
            if "already deleted" in str(e):
                self._is_deleted = True
                return
            raise

    def showEvent(self, event):
        """Override showEvent to ensure the window is centered once when shown"""
        # Center BEFORE calling super to ensure correct position from the start
        if not self._is_deleted and not hasattr(self, '_centered_on_show'):
            self._centered_on_show = True
            self._center_on_screen()
            # Process events to ensure position is applied
            QApplication.processEvents()
        super().showEvent(event)

    def move(self, *args):
        """Override move to prevent moving to (0,0) at source"""
        try:
            # Parse position from args
            if len(args) == 1:
                # QPoint argument
                pos = args[0]
                x, y = pos.x(), pos.y()
            elif len(args) == 2:
                # x, y arguments
                x, y = args[0], args[1]
            else:
                return super().move(*args)
            
            # Block moves to (0,0) unless we're being hidden
            if x < 5 and y < 5 and not self._is_hidden:
                # Debug log
                try:
                    from utils.logger_helper import logger_helper as logger
                    logger.warning(f"[Splash] 🛡️ BLOCKED move to ({x},{y}), staying at current position")
                except Exception:
                    print(f"[Splash] 🛡️ BLOCKED move to ({x},{y})")
                
                # Ignore this move request - stay at current position
                if self._last_center_pos is not None:
                    return super().move(self._last_center_pos)
                return  # Don't move at all
            
            # Allow valid moves
            return super().move(*args)
        except Exception as e:
            print(f"[Splash] move() exception: {e}")
            return super().move(*args)
    
    def moveEvent(self, event):
        """Guard against unintended jumps to (0,0) by immediately restoring position."""
        try:
            # Only guard if visible and not being hidden
            if (not self._is_deleted and 
                not self._is_hidden and 
                self.isVisible()):
                pos = event.pos()
                # If moved to (0,0), immediately restore to saved position
                if pos.x() < 5 and pos.y() < 5:
                    try:
                        from utils.logger_helper import logger_helper as logger
                        logger.warning(f"[Splash] 🛡️ Detected move to ({pos.x()}, {pos.y()}), restoring position")
                    except Exception:
                        pass
                    # Must call super first to process the event
                    super().moveEvent(event)
                    # Then immediately restore position
                    if self._last_center_pos is not None:
                        from PySide6.QtCore import QTimer
                        QTimer.singleShot(0, lambda: super(ThemedSplashScreen, self).move(self._last_center_pos))
                    return
        except Exception:
            pass
        return super().moveEvent(event)


    def eventFilter(self, obj, event):
        """Event filter to handle Windows-specific window positioning issues"""
        try:
            # Check if we have the required attributes and object is valid
            if (sys.platform == 'win32' and
                obj == self and
                hasattr(self, '_is_deleted') and
                not self._is_deleted):
                # No-op: avoid aggressive recentering on move/state changes to prevent visible jumps
                pass
        except Exception:
            # If any error occurs, just pass through to parent
            pass
        return super().eventFilter(obj, event)

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
        from PySide6.QtGui import QPixmap
        for p in candidates:
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    return pm
        return None

    def _get_version(self) -> str:
        # Try to read VERSION file similar to app_setup_helper
        import sys

        # Get correct resource path (supports PyInstaller packaging environment)
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller packaging environment
            base_path = sys._MEIPASS
        else:
            # Development environment - from gui/splash.py to project root
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Try multiple possible VERSION file locations
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller environment - VERSION is in _internal directory
            try_paths = [
                os.path.join(base_path, "VERSION"),  # PyInstaller _MEIPASS root
                os.path.join(base_path, "_internal", "VERSION"),  # PyInstaller _internal directory
                os.path.join(os.path.dirname(sys.executable), "VERSION"),  # Executable directory
                os.path.join(os.path.dirname(sys.executable), "_internal", "VERSION"),  # Executable _internal
            ]
        else:
            # Development environment
            try_paths = [
                os.path.join(base_path, "VERSION"),  # Project root
                os.path.join(os.path.dirname(__file__), '..', 'VERSION'),  # Project root directory
                os.path.join(os.getcwd(), "VERSION"),  # Working directory
                "VERSION",  # Current directory
            ]

        # Use unified version reading function
        try:
            from utils.app_setup_helper import read_version_file
            return read_version_file(try_paths)
        except ImportError:
            # If import fails, use original logic as fallback
            for p in try_paths:
                try:
                    # Check if it's a file
                    if os.path.exists(p) and os.path.isfile(p):
                        with open(p, 'r', encoding='utf-8') as f:
                            v = f.read().strip()
                            if v:
                                return v
                    # Check if it's a directory containing VERSION file (PyInstaller packaging case)
                    elif os.path.exists(p) and os.path.isdir(p):
                        nested_version_path = os.path.join(p, "VERSION")
                        if os.path.exists(nested_version_path) and os.path.isfile(nested_version_path):
                            with open(nested_version_path, 'r', encoding='utf-8') as f:
                                v = f.read().strip()
                                if v:
                                    return v
                except Exception:
                    pass

        # Return default version if not found
        return "1.0.0"

    # Spinner no longer used; kept for reference if needed
    def _load_spinner_movie(self):
        return None

    def set_status(self, text: str):
        """Update status text with optimized repaint."""
        try:
            if hasattr(self, 'status_label') and self.status_label is not None:
                self.status_label.setText(str(text))
                # Use update() instead of repaint() for better performance
                # update() schedules a paint event, while repaint() forces immediate painting
                self.status_label.update()
                # Reduce processEvents calls to improve performance
        except Exception:
            pass

    def set_progress(self, value: int):
        """Update progress with optimized rendering."""
        try:
            # Treat as WebView load progress
            self._web_progress = max(0, min(100, int(value)))
            self._update_combined()
            # Remove excessive processEvents() calls to reduce CPU usage
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
            # Show and bring main window to front reliably
            if main_window is not None:
                try:
                    main_window.show()
                    main_window.raise_()
                    main_window.activateWindow()
                    if sys.platform == 'win32':
                        try:
                            import ctypes
                            hwnd = int(main_window.winId())
                            if hwnd:
                                user32 = ctypes.windll.user32
                                user32.SetForegroundWindow(hwnd)
                        except Exception:
                            pass
                except Exception:
                    pass
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
        """Handle status updates from Python initialization worker with optimized rendering."""
        try:
            self.set_status(status)
            # Removed excessive processEvents() call for better performance
        except Exception:
            pass

    def _update_combined(self):
        """Update combined progress with optimized rendering."""
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
                        # Use update() instead of repaint() for better performance
                        self.progress_bar.update()
                    except Exception:
                        pass
        except Exception:
            pass

    def _hide_now(self):
        try:
            if not self._is_hidden:
                self._is_hidden = True
                # Immediately set opacity to 0 for smooth fade
                try:
                    self.setWindowOpacity(0.0)
                except Exception:
                    pass
                # On Windows, hide without moving using SetWindowPos
                if sys.platform == 'win32':
                    try:
                        import ctypes
                        hwnd = int(self.winId())
                        if hwnd:
                            user32 = ctypes.windll.user32
                            SWP_NOSIZE = 0x0001
                            SWP_NOMOVE = 0x0002
                            SWP_NOZORDER = 0x0004
                            SWP_HIDEWINDOW = 0x0080
                            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_HIDEWINDOW)
                            return
                    except Exception:
                        pass
                # Fallback: hide immediately
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
            self._is_deleted = True
            # Clear all centering timers
            self._clear_center_timers()
            # By now python thread should be finished via _on_py_finished
            self.deleteLater()
        except Exception:
            pass

    def _clear_center_timers(self):
        """Clear all centering timers to prevent memory leaks"""
        try:
            # Note: QTimer.singleShot returns None, so we can't actually stop them
            # But we can clear our tracking list
            self._center_timers.clear()
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
            self._is_deleted = True
            self._clear_center_timers()
            self._ensure_thread_stopped()
        except Exception:
            pass
        event.accept()

    def __del__(self):
        try:
            self._is_deleted = True
            self._clear_center_timers()
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
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QConicalGradient, QFont
        
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


from PySide6.QtCore import QObject

class PythonInitWorker(QObject):
    progress = Signal(int)
    status_update = Signal(str)
    finished = Signal()

    def run(self):
        try:
            # Phase 1: Basic initialization
            self.status_update.emit(_get_splash_messages().get('init_python_env'))
            self.progress.emit(5)

            # Phase 2: Import core modules
            self.status_update.emit(_get_splash_messages().get('loading_core_modules'))
            self.progress.emit(15)
            
            # Phase 3: Load configuration
            self.status_update.emit(_get_splash_messages().get('loading_config'))
            self.progress.emit(30)

            # Phase 4: Initialize services
            self.status_update.emit(_get_splash_messages().get('init_services'))
            self.progress.emit(35)

            # Phase 5 Prepare GUI components
            self.status_update.emit(_get_splash_messages().get('preparing_gui'))
            self.progress.emit(40)

            # Phase 6: Final preparations
            self.status_update.emit(_get_splash_messages().get('finalizing'))
            self.progress.emit(50)

        finally:
            self.status_update.emit(_get_splash_messages().get('ready'))
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
    Create and show ThemedSplashScreen immediately, and process initial events.
    Returns the splash instance (or None on failure).

    Note: This function assumes QApplication already exists and should NOT create it.
    """
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if not app:
            print("ERROR: QApplication instance not found in init_startup_splash!")
            return None

        # Set application icon as early as possible (before splash)
        try:
            from utils.app_setup_helper import set_app_icon_early
            success = set_app_icon_early(app)
            print(f"Early icon setting: {'success' if success else 'failed'}")
        except Exception as e:
            # Don't let icon setting failure prevent splash from showing
            print(f"Early icon setting failed: {e}")

        splash = ThemedSplashScreen()
        splash.show()
        app.processEvents()
        # Set window icon using IconManager for proper platform-specific handling
        try:
            from utils.icon_manager import get_icon_manager
            icon_manager = get_icon_manager()
            if icon_manager.icon_path:
                try:
                    from PySide6.QtGui import QIcon as _QIcon
                    splash.setWindowIcon(_QIcon(icon_manager.icon_path))
                except Exception:
                    pass
        except Exception:
            pass


        # Ensure the splash is centered immediately after showing
        app.processEvents()
        splash._center_on_screen()
        app.processEvents()

        return splash
    except Exception as e:
        print(f"Failed to initialize splash screen: {e}")
        return None


def create_startup_progress_manager(splash_screen):
    """Create a startup progress manager for the given splash screen"""
    return StartupProgressManager(splash_screen)


def init_minimal_splash():
    """
    Create and show a minimal splash screen IMMEDIATELY after QApplication creation.
    This is a lightweight version that shows instantly, before loading the full splash.
    The structure and styling match ThemedSplashScreen exactly for smooth transition.
    Returns the splash instance (or None on failure).
    
    This function uses minimal imports to ensure fast display, but matches the
    exact visual appearance of ThemedSplashScreen for seamless transition.
    """
    try:
        from PySide6.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QGraphicsDropShadowEffect
        import sys
        
        app = QApplication.instance()
        if not app:
            return None
        
        # Create minimal splash window - match ThemedSplashScreen exactly
        window_flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if sys.platform == 'win32':
            window_flags |= Qt.Tool  # Prevents taskbar entry and reduces flicker
        
        splash = QWidget(None, window_flags)
        splash.setAttribute(Qt.WA_TranslucentBackground, True)
        splash.setFixedSize(640, 400)  # Match ThemedSplashScreen size
        splash.setAttribute(Qt.WA_ShowWithoutActivating, True)
        
        # Create container widget with same styling as ThemedSplashScreen
        container = QWidget(splash)
        container.setObjectName("container")
        container.setStyleSheet("""
            QWidget#container {
                background-color: #0f172a; /* --bg-primary */
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
            }
        """)
        
        # Optimized shadow effect for minimal splash
        shadow = QGraphicsDropShadowEffect(splash)
        shadow.setBlurRadius(16)  # Reduced for better performance
        shadow.setXOffset(0)
        shadow.setYOffset(6)
        shadow.setColor(QColor(0, 0, 0, 180))
        container.setGraphicsEffect(shadow)
        
        # Root layout with same margins as ThemedSplashScreen
        root_layout = QVBoxLayout(container)
        root_layout.setContentsMargins(18, 18, 18, 18)  # Match ThemedSplashScreen
        root_layout.setSpacing(10)
        
        # Center column with same width as ThemedSplashScreen
        center = QWidget()
        center.setFixedWidth(520)  # Match ThemedSplashScreen center width
        col_layout = QVBoxLayout(center)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(10)
        
        # App name with same styling as ThemedSplashScreen title
        title_label = QLabel("eCan")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel#title {
                color: #f8fafc;
                font-size: 26px;
                font-weight: 700;
                letter-spacing: 0.4px;
                padding: 0px;
            }
        """)
        col_layout.addWidget(title_label)
        
        # Loading text with same styling as ThemedSplashScreen subtitle
        loading_label = QLabel(_get_splash_messages().get('initializing'))
        loading_label.setObjectName("subtitle")
        loading_label.setAlignment(Qt.AlignCenter)
        loading_label.setStyleSheet("""
            QLabel#subtitle {
                color: #94a3b8;
                font-size: 14px;
            }
        """)
        col_layout.addWidget(loading_label)
        
        # Vertical centering relative to footer (match ThemedSplashScreen structure)
        root_layout.addStretch(1)
        root_layout.addWidget(center, alignment=Qt.AlignHCenter)
        root_layout.addStretch(2)
        
        # Put container into main widget
        main_layout = QVBoxLayout(splash)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)
        
        # Center on screen using same logic as ThemedSplashScreen
        screen = app.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            x = screen_geometry.center().x() - splash.width() // 2
            y = screen_geometry.center().y() - splash.height() // 2
            splash.move(x, y)
        
        # Show immediately
        splash.show()
        app.processEvents()
        
        return splash
    except Exception as e:
        print(f"Failed to initialize minimal splash screen: {e}")
        return None


