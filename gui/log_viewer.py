#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Log Viewer Window
Displays real-time and historical log information from logger_helper
"""

import os
import sys
from datetime import datetime
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                               QPushButton, QTextEdit, QLabel, QComboBox,
                               QCheckBox, QFileDialog, QMessageBox,
                               QProgressBar, QStatusBar, QLineEdit)
from PySide6.QtCore import QThread, Signal, Qt, QEvent
from PySide6.QtGui import QFont, QTextCursor, QAction, QSyntaxHighlighter, QTextCharFormat, QColor
from utils.logger_helper import logger_helper as logger
from config.constants import APP_NAME


class LogViewerMessages:
    """Internationalization messages for Log Viewer"""
    
    DEFAULT_LANG = 'zh-CN'
    
    MESSAGES = {
        'en-US': {
            'window_title': 'Log Viewer',
            'realtime_monitoring': 'Real-time monitoring',
            'auto_scroll': 'Auto-scroll',
            'filter': 'Filter:',
            'filter_all': 'All',
            'refresh': 'Refresh',
            'search': 'Search:',
            'search_placeholder': 'Enter search term...',
            'clear': 'Clear',
            'open_log_file': 'Open Log File...',
            'save_logs': 'Save Logs...',
            'close': 'Close',
            'file_menu': 'File',
            'view_menu': 'View',
            'ready': 'Ready',
            'loaded': 'Loaded: {filename}',
            'no_log_file': 'No log file found',
            'error_loading': 'Error loading log file',
            'error_title': 'Error',
            'error_load_file': 'Failed to load log file:\n{error}',
            'realtime_enabled': 'Real-time monitoring enabled',
            'realtime_disabled': 'Real-time monitoring disabled',
            'showing_all_levels': 'Showing all log levels',
            'showing_level': 'Showing {count} lines with {level} level',
            'error_filtering': 'Error filtering logs',
            'found_lines': 'Found {count} lines matching \'{term}\'',
            'no_lines_found': 'No lines found matching \'{term}\'',
            'error_searching': 'Error searching logs',
            'logs_refreshed': 'Logs refreshed',
            'display_cleared': 'Log display cleared',
            'open_log_title': 'Open Log File',
            'log_files_filter': 'Log Files (*.log *.txt);;All Files (*)',
            'save_logs_title': 'Save Logs',
            'save_files_filter': 'Text Files (*.txt);;Log Files (*.log);;All Files (*)',
            'logs_saved': 'Logs saved to: {filename}',
            'error_save': 'Failed to save logs:\n{error}',
            'viewing_history': '📜 Viewing history - Auto-scroll paused (scroll to bottom to resume)',
        },
        'zh-CN': {
            'window_title': '日志查看器',
            'realtime_monitoring': '实时监控',
            'auto_scroll': '自动滚动',
            'filter': '筛选:',
            'filter_all': '全部',
            'refresh': '刷新',
            'search': '搜索:',
            'search_placeholder': '输入搜索词...',
            'clear': '清空',
            'open_log_file': '打开日志文件...',
            'save_logs': '保存日志...',
            'close': '关闭',
            'file_menu': '文件',
            'view_menu': '查看',
            'ready': '就绪',
            'loaded': '已加载: {filename}',
            'no_log_file': '未找到日志文件',
            'error_loading': '加载日志文件出错',
            'error_title': '错误',
            'error_load_file': '加载日志文件失败:\n{error}',
            'realtime_enabled': '实时监控已启用',
            'realtime_disabled': '实时监控已禁用',
            'showing_all_levels': '显示所有日志级别',
            'showing_level': '显示 {count} 行 {level} 级别日志',
            'error_filtering': '筛选日志出错',
            'found_lines': '找到 {count} 行匹配 \'{term}\'',
            'no_lines_found': '未找到匹配 \'{term}\' 的行',
            'error_searching': '搜索日志出错',
            'logs_refreshed': '日志已刷新',
            'display_cleared': '日志显示已清空',
            'open_log_title': '打开日志文件',
            'log_files_filter': '日志文件 (*.log *.txt);;所有文件 (*)',
            'save_logs_title': '保存日志',
            'save_files_filter': '文本文件 (*.txt);;日志文件 (*.log);;所有文件 (*)',
            'logs_saved': '日志已保存到: {filename}',
            'error_save': '保存日志失败:\n{error}',
            'viewing_history': '📜 查看历史记录 - 自动滚动已暂停（滚动到底部以恢复）',
        }
    }
    
    def __init__(self):
        from utils.i18n_helper import detect_language
        self.current_lang = detect_language(
            default_lang=self.DEFAULT_LANG,
            supported_languages=list(self.MESSAGES.keys())
        )
        logger.info(f"[LogViewer] Language: {self.current_lang}")
    
    def get(self, key, **kwargs):
        """Get message by key with optional formatting."""
        messages = self.MESSAGES.get(self.current_lang, self.MESSAGES[self.DEFAULT_LANG])
        message = messages.get(key, key)
        if kwargs:
            try:
                return message.format(**kwargs)
            except Exception:
                return message
        return message


# Global message instance - lazy initialization
_log_viewer_messages = None

def _get_log_viewer_messages():
    """Get LogViewerMessages instance with lazy initialization."""
    global _log_viewer_messages
    if _log_viewer_messages is None:
        _log_viewer_messages = LogViewerMessages()
    return _log_viewer_messages


class LogFileWatcher(QThread):
    """Thread to watch log file changes and emit new content"""
    new_content = Signal(str)
    
    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = log_file_path
        self.last_position = 0
        self.running = True
        
    def run(self):
        """Monitor log file for new content"""
        while self.running:
            try:
                if os.path.exists(self.log_file_path):
                    with open(self.log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                        f.seek(self.last_position)
                        new_content = f.read()
                        if new_content:
                            self.new_content.emit(new_content)
                            self.last_position = f.tell()
                
                self.msleep(1000)  # Check every second
            except Exception as e:
                logger.error(f"Error reading log file: {e}")
                self.msleep(5000)  # Wait longer on error
    
    def stop(self):
        """Stop the watcher thread"""
        self.running = False
        self.wait()


class FileReaderThread(QThread):
    """Background file reader to avoid blocking UI when loading large logs"""
    loaded = Signal(str)
    error = Signal(str)

    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            with open(self.file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            self.loaded.emit(content)
        except Exception as e:
            self.error.emit(str(e))


class LogHighlighter(QSyntaxHighlighter):
    """Simple syntax highlighter for log levels and timestamps"""
    def __init__(self, parent):
        super().__init__(parent)
        self.fmt_debug = QTextCharFormat()
        self.fmt_debug.setForeground(QColor('#7aa2f7'))

        self.fmt_info = QTextCharFormat()
        self.fmt_info.setForeground(QColor('#9ece6a'))

        self.fmt_warning = QTextCharFormat()
        self.fmt_warning.setForeground(QColor('#e0af68'))

        self.fmt_error = QTextCharFormat()
        self.fmt_error.setForeground(QColor('#f7768e'))

        self.fmt_critical = QTextCharFormat()
        self.fmt_critical.setForeground(QColor('#ff5370'))
        self.fmt_critical.setFontWeight(600)

        self.fmt_timestamp = QTextCharFormat()
        self.fmt_timestamp.setForeground(QColor('#6b7280'))

    def highlightBlock(self, text: str):
        # Timestamp like 2025-11-06 12:00:00,123 or [2025-11-06 12:00:00]
        # Light, non-intrusive coloring
        ts_positions = []
        # Find patterns without regex overhead in Qt loop
        if len(text) >= 19 and text[4] == '-' and text[7] == '-' and (' ' in text[:20]):
            ts_positions.append((0, min(len(text), 23)))
        for start, length in ts_positions:
            self.setFormat(start, length, self.fmt_timestamp)

        upper = text.upper()
        # Color per-level tokens but do not alter content
        for token, fmt in (
            (' - DEBUG - ', self.fmt_debug),
            (' DEBUG ', self.fmt_debug),
            (' - INFO - ', self.fmt_info),
            (' INFO ', self.fmt_info),
            (' - WARNING - ', self.fmt_warning),
            (' WARNING ', self.fmt_warning),
            (' - ERROR - ', self.fmt_error),
            (' ERROR ', self.fmt_error),
            (' - CRITICAL - ', self.fmt_critical),
            (' CRITICAL ', self.fmt_critical),
        ):
            idx = upper.find(token)
            if idx != -1:
                self.setFormat(idx, len(token), fmt)


class LogViewer(QMainWindow):
    """Log Viewer Window for displaying real-time and historical logs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - {_get_log_viewer_messages().get('window_title')}")
        self.setGeometry(100, 100, 1000, 700)
        
        # Initialize variables
        self.log_watcher = None
        self.auto_scroll = True
        self.current_log_file = None
        self.user_is_scrolling = False  # Track if user is manually scrolling
        self.last_scroll_position = 0  # Track last scroll position
        self.programmatic_scroll = False  # Flag to ignore programmatic scrolls
        
        # Set up UI
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        
        # Load current log file
        self._load_current_log_file()
        
        # Apply dark theme
        self._apply_dark_theme()
        
        logger.info("Log Viewer window initialized")

    def eventFilter(self, obj, event):
        """Event filter to catch user scroll events"""
        if obj == self.log_display:
            if event.type() == QEvent.Wheel:
                # Mouse wheel scroll - this is definitely user interaction
                # Don't set user_is_scrolling here, let the scroll change handler deal with it
                # Just mark that this is user-initiated
                self._mark_user_interaction()
            elif event.type() == QEvent.KeyPress:
                # Check for scroll-related keys
                key = event.key()
                if key in [Qt.Key_Up, Qt.Key_Down, Qt.Key_PageUp, Qt.Key_PageDown,
                          Qt.Key_Home, Qt.Key_End]:
                    self._mark_user_interaction()

        return super().eventFilter(obj, event)

    def _mark_user_interaction(self):
        """Mark that user is interacting with scroll"""
        # This will be handled by the scroll change event
        pass
    
    def _setup_ui(self):
        """Set up the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Control panel
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)
        
        # Log display area
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        self.log_display.setFont(QFont("Consolas", 10))
        # Preserve original log layout: no line wrapping
        self.log_display.setLineWrapMode(QTextEdit.NoWrap)

        # Highlighter for colored levels
        self.highlighter = LogHighlighter(self.log_display.document())

        # Install event filter to catch wheel events and key presses
        self.log_display.installEventFilter(self)

        # Connect scroll bar signals to detect user scrolling
        self.scroll_bar = self.log_display.verticalScrollBar()
        self.scroll_bar.valueChanged.connect(self._on_scroll_changed)
        self.scroll_bar.sliderPressed.connect(self._on_scroll_pressed)
        self.scroll_bar.sliderReleased.connect(self._on_scroll_released)

        main_layout.addWidget(self.log_display)
        
        # Bottom controls
        bottom_controls = self._create_bottom_controls()
        main_layout.addWidget(bottom_controls)
    
    def _create_control_panel(self):
        """Create the control panel with buttons and options"""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        # Real-time monitoring checkbox
        self.realtime_checkbox = QCheckBox(_get_log_viewer_messages().get('realtime_monitoring'))
        self.realtime_checkbox.setChecked(True)
        self.realtime_checkbox.toggled.connect(self._toggle_realtime_monitoring)
        layout.addWidget(self.realtime_checkbox)
        
        # Auto-scroll checkbox
        self.autoscroll_checkbox = QCheckBox(_get_log_viewer_messages().get('auto_scroll'))
        self.autoscroll_checkbox.setChecked(True)
        self.autoscroll_checkbox.toggled.connect(self._toggle_auto_scroll)
        layout.addWidget(self.autoscroll_checkbox)
        
        layout.addStretch()
        
        # Log level filter
        layout.addWidget(QLabel(_get_log_viewer_messages().get('filter')))
        self.level_filter = QComboBox()
        self.level_filter.addItems([_get_log_viewer_messages().get('filter_all'), "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_filter.currentTextChanged.connect(self._filter_logs)
        layout.addWidget(self.level_filter)
        
        # Refresh button
        self.refresh_btn = QPushButton(_get_log_viewer_messages().get('refresh'))
        self.refresh_btn.clicked.connect(self._refresh_logs)
        layout.addWidget(self.refresh_btn)
        
        # Search box
        layout.addWidget(QLabel(_get_log_viewer_messages().get('search')))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText(_get_log_viewer_messages().get('search_placeholder'))
        self.search_box.textChanged.connect(self._search_logs)
        layout.addWidget(self.search_box)

        # Clear button
        self.clear_btn = QPushButton(_get_log_viewer_messages().get('clear'))
        self.clear_btn.clicked.connect(self._clear_logs)
        layout.addWidget(self.clear_btn)

        return panel
    
    def _create_bottom_controls(self):
        """Create bottom control buttons"""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        # Open log file button
        self.open_file_btn = QPushButton(_get_log_viewer_messages().get('open_log_file'))
        self.open_file_btn.clicked.connect(self._open_log_file)
        layout.addWidget(self.open_file_btn)
        
        # Save logs button
        self.save_btn = QPushButton(_get_log_viewer_messages().get('save_logs'))
        self.save_btn.clicked.connect(self._save_logs)
        layout.addWidget(self.save_btn)
        
        layout.addStretch()
        
        # Close button
        self.close_btn = QPushButton(_get_log_viewer_messages().get('close'))
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)
        
        return panel
    
    def _setup_menu(self):
        """Set up the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu(_get_log_viewer_messages().get('file_menu'))
        
        open_action = QAction(_get_log_viewer_messages().get('open_log_file'), self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_log_file)
        file_menu.addAction(open_action)
        
        save_action = QAction(_get_log_viewer_messages().get('save_logs'), self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_logs)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        close_action = QAction(_get_log_viewer_messages().get('close'), self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        
        # View menu
        view_menu = menubar.addMenu(_get_log_viewer_messages().get('view_menu'))
        
        refresh_action = QAction(_get_log_viewer_messages().get('refresh'), self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_logs)
        view_menu.addAction(refresh_action)
        
        clear_action = QAction(_get_log_viewer_messages().get('clear'), self)
        clear_action.setShortcut("Ctrl+L")
        clear_action.triggered.connect(self._clear_logs)
        view_menu.addAction(clear_action)
    
    def _setup_status_bar(self):
        """Set up the status bar"""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Progress bar for loading
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_bar.addPermanentWidget(self.progress_bar)

        self._last_status_message = _get_log_viewer_messages().get('ready')
        self.status_bar.showMessage(self._last_status_message)
    
    def _apply_dark_theme(self):
        """Apply dark theme to the log viewer"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #23272e;
                color: #e5e7eb;
            }
            QTextEdit {
                background-color: #111317;
                color: #e5e7eb;
                border: 1px solid #374151;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
                selection-background-color: #374151;
                selection-color: #e5e7eb;
            }
            QPushButton {
                background-color: #334155;
                color: #e5e7eb;
                border: 1px solid #475569;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3b4a61;
                border-color: #5b6b83;
            }
            QPushButton:pressed {
                background-color: #283548;
            }
            QCheckBox {
                color: #e5e7eb;
            }
            QComboBox {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            }
            QLineEdit:focus {
                border-color: #60a5fa;
                background-color: #111827;
            }
            QLabel {
                color: #e5e7eb;
            }
            QMenuBar {
                background-color: #23272e;
                color: #e5e7eb;
                border-bottom: 1px solid #374151;
            }
            QMenuBar::item:selected {
                background-color: #334155;
            }
            QMenu {
                background-color: #23272e;
                color: #e5e7eb;
                border: 1px solid #374151;
            }
            QMenu::item:selected {
                background-color: #334155;
            }
            QStatusBar {
                background-color: #23272e;
                color: #e5e7eb;
                border-top: 1px solid #374151;
            }
        """)

    def _load_current_log_file(self):
        """Load the current log file from logger_helper"""
        try:
            # Get log file path from logger_helper
            log_info = logger.get_crash_log_info()
            log_file = log_info.get('log_file', '')

            if log_file and log_file != "Unknown" and os.path.exists(log_file):
                self.current_log_file = log_file
                self._load_log_file(log_file)
                self._set_status_message(_get_log_viewer_messages().get('loaded', filename=os.path.basename(log_file)))
                logger.info(f"Loaded log file: {log_file}")
            else:
                self._set_status_message(_get_log_viewer_messages().get('no_log_file'))
                logger.warning("No valid log file found")

        except Exception as e:
            logger.error(f"Error loading current log file: {e}")
            self._set_status_message(_get_log_viewer_messages().get('error_loading'))

    def _load_log_file(self, file_path):
        """Load and display log file content asynchronously"""
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)

            # Stop previous loader if any
            if hasattr(self, '_file_loader') and self._file_loader and self._file_loader.isRunning():
                self._file_loader.requestInterruption()
                self._file_loader.wait(100)

            self._file_loader = FileReaderThread(file_path)
            self._file_loader.loaded.connect(self._on_file_loaded)
            self._file_loader.error.connect(self._on_file_load_error)
            self._file_loader.start()

        except Exception as e:
            logger.error(f"Error loading log file {file_path}: {e}")
            QMessageBox.warning(self, _get_log_viewer_messages().get('error_title'), 
                              _get_log_viewer_messages().get('error_load_file', error=str(e)))
            self.progress_bar.setVisible(False)

    def _on_file_loaded(self, content: str):
        # Remember if user was viewing history before loading new content
        was_viewing_history = self.user_is_scrolling
        
        # Set programmatic scroll flag to ignore scroll events during text setting
        self.programmatic_scroll = True
        self.log_display.setPlainText(content)
        self.programmatic_scroll = False

        # Start real-time monitoring if enabled
        if self.realtime_checkbox.isChecked() and self.current_log_file:
            self._start_realtime_monitoring(self.current_log_file)

        # Only auto-scroll if:
        # 1. Auto-scroll checkbox is enabled
        # 2. User was NOT viewing history (was at bottom before load)
        # This prevents interrupting users who are reading historical logs
        if self.auto_scroll and not was_viewing_history:
            # Use QTimer.singleShot to scroll after the text is fully rendered
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, self._scroll_to_bottom)
        else:
            # If user was viewing history, reset the flag since content changed
            # but don't scroll - let them stay where they were (or at top)
            if was_viewing_history:
                # Keep the scroll position at top or preserve it
                cursor = self.log_display.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self.log_display.setTextCursor(cursor)
                self.user_is_scrolling = False  # Reset since content changed

        self.progress_bar.setVisible(False)

    def _on_file_load_error(self, err: str):
        QMessageBox.warning(self, _get_log_viewer_messages().get('error_title'), 
                          _get_log_viewer_messages().get('error_load_file', error=err))
        self.progress_bar.setVisible(False)

    def _start_realtime_monitoring(self, file_path):
        """Start real-time monitoring of log file"""
        if self.log_watcher:
            self.log_watcher.stop()

        self.log_watcher = LogFileWatcher(file_path)
        self.log_watcher.new_content.connect(self._append_new_content)
        self.log_watcher.start()

        logger.debug(f"Started real-time monitoring for: {file_path}")

    def _append_new_content(self, content):
        """Append new content to the log display"""
        if content.strip():
            # Check if scroll bar is at bottom BEFORE adding new content
            # Also check if user is actively viewing history
            was_at_bottom = self._is_at_bottom()
            user_viewing_history = self.user_is_scrolling or not was_at_bottom
            
            # Save current scroll position if user is viewing history
            scrollbar = self.log_display.verticalScrollBar()
            saved_scroll_position = scrollbar.value() if user_viewing_history else None

            # Set programmatic scroll flag to prevent scroll events from affecting user_is_scrolling
            self.programmatic_scroll = True
            
            # Insert content at the end
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_display.setTextCursor(cursor)
            self.log_display.insertPlainText(content)
            
            # Restore scroll position if user was viewing history
            if user_viewing_history and saved_scroll_position is not None:
                # Restore the saved scroll position
                scrollbar.setValue(saved_scroll_position)
            elif self.auto_scroll and was_at_bottom:
                # Only auto-scroll if:
                # 1. Auto-scroll checkbox is enabled
                # 2. Scroll bar was at bottom before new content was added
                # This ensures we don't interrupt users who are reading historical logs
                self._scroll_to_bottom()
            
            self.programmatic_scroll = False

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the log display"""
        scrollbar = self.log_display.verticalScrollBar()
        self.programmatic_scroll = True  # Mark as programmatic scroll
        scrollbar.setValue(scrollbar.maximum())
        self.programmatic_scroll = False

    def _is_at_bottom(self):
        """Check if scroll bar is at or near the bottom"""
        scrollbar = self.log_display.verticalScrollBar()
        return scrollbar.value() >= scrollbar.maximum() - 20  # 20 pixel tolerance

    def _on_scroll_changed(self, value):
        """Handle scroll bar value changes"""
        # Ignore programmatic scrolls (when we programmatically scroll to bottom)
        if self.programmatic_scroll:
            return

        # Track user scrolling state based on whether scroll bar is at bottom
        # This is used for status display only - the actual auto-scroll decision
        # is made in _append_new_content based on was_at_bottom check
        was_user_scrolling = self.user_is_scrolling

        if self._is_at_bottom():
            # User scrolled back to bottom
            self.user_is_scrolling = False
        else:
            # User scrolled away from bottom (viewing history)
            self.user_is_scrolling = True

        # Update status if state changed
        if was_user_scrolling != self.user_is_scrolling:
            self._update_scroll_status()

        self.last_scroll_position = value

    def _on_scroll_pressed(self):
        """Handle when user starts dragging the scroll bar"""
        # Don't immediately set user_is_scrolling here, wait for actual movement
        pass

    def _on_scroll_released(self):
        """Handle when user releases the scroll bar"""
        # Check final position after release
        if self._is_at_bottom():
            if self.user_is_scrolling:
                self.user_is_scrolling = False
                self._update_scroll_status()

    def _update_scroll_status(self):
        """Update status bar to show scroll state"""
        if self.user_is_scrolling and self.auto_scroll:
            self.status_bar.showMessage(_get_log_viewer_messages().get('viewing_history'))
        elif hasattr(self, '_last_status_message'):
            # Restore the last status message
            self.status_bar.showMessage(self._last_status_message)
        else:
            self.status_bar.showMessage(_get_log_viewer_messages().get('ready'))

    def _set_status_message(self, message):
        """Set status message and save it as the last message"""
        self._last_status_message = message
        if not (self.user_is_scrolling and self.auto_scroll):
            # Only show the message if we're not in scroll-paused state
            self.status_bar.showMessage(message)

    def _toggle_realtime_monitoring(self, enabled):
        """Toggle real-time monitoring on/off"""
        if enabled and self.current_log_file:
            self._start_realtime_monitoring(self.current_log_file)
            self._set_status_message(_get_log_viewer_messages().get('realtime_enabled'))
        else:
            if self.log_watcher:
                self.log_watcher.stop()
                self.log_watcher = None
            self._set_status_message(_get_log_viewer_messages().get('realtime_disabled'))

    def _toggle_auto_scroll(self, enabled):
        """Toggle auto-scroll on/off"""
        self.auto_scroll = enabled
        if enabled:
            # When auto-scroll is re-enabled, reset user scrolling state and scroll to bottom
            self.user_is_scrolling = False
            self._scroll_to_bottom()

    def _filter_logs(self, level):
        """Filter logs by level"""
        try:
            if not self.current_log_file:
                return

            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)

            def do_filter(content: str, level_text: str):
                all_text = _get_log_viewer_messages().get('filter_all')
                if level_text == all_text or level_text == "All":
                    return content, _get_log_viewer_messages().get('showing_all_levels')
                lines = content.split('\n')
                filtered = [line for line in lines if (f" - {level_text} - " in line) or (level_text.upper() in line)]
                return '\n'.join(filtered), _get_log_viewer_messages().get('showing_level', count=len(filtered), level=level_text)

            # Reuse file loader thread to avoid blocking
            loader = FileReaderThread(self.current_log_file)

            def on_loaded(content: str):
                # Remember if user was viewing history before filtering
                was_viewing_history = self.user_is_scrolling
                
                filtered_content, msg = do_filter(content, level)
                
                # Set programmatic scroll flag to ignore scroll events during text setting
                self.programmatic_scroll = True
                self.log_display.setPlainText(filtered_content)
                self.programmatic_scroll = False
                
                self._set_status_message(msg)
                
                # Only auto-scroll if:
                # 1. Auto-scroll checkbox is enabled
                # 2. User was NOT viewing history (was at bottom before filter)
                # This prevents interrupting users who are reading historical logs
                if self.auto_scroll and not was_viewing_history:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, self._scroll_to_bottom)
                else:
                    # If user was viewing history, reset the flag since content changed
                    # but don't scroll - let them stay at top
                    if was_viewing_history:
                        cursor = self.log_display.textCursor()
                        cursor.movePosition(QTextCursor.Start)
                        self.log_display.setTextCursor(cursor)
                        self.user_is_scrolling = False  # Reset since content changed
                
                self.progress_bar.setVisible(False)

            def on_error(err: str):
                logger.error(f"Error filtering logs: {err}")
                self._set_status_message(_get_log_viewer_messages().get('error_filtering'))
                self.progress_bar.setVisible(False)

            loader.loaded.connect(on_loaded)
            loader.error.connect(on_error)
            loader.start()

            self._filter_loader = loader

        except Exception as e:
            logger.error(f"Error filtering logs: {e}")
            self._set_status_message(_get_log_viewer_messages().get('error_filtering'))

    def _search_logs(self, search_term):
        """Search for specific text in logs"""
        if not search_term.strip():
            # If search is empty, reload original content
            if self.current_log_file:
                self._load_log_file(self.current_log_file)
            return

        try:
            # Get current content
            current_content = self.log_display.toPlainText()

            if not current_content:
                return

            # Split into lines and search
            lines = current_content.split('\n')
            matching_lines = []

            search_term_lower = search_term.lower()

            for line in lines:
                if search_term_lower in line.lower():
                    matching_lines.append(line)

            # Display matching lines
            if matching_lines:
                filtered_content = '\n'.join(matching_lines)
                self.log_display.setPlainText(filtered_content)
                self._set_status_message(_get_log_viewer_messages().get('found_lines', count=len(matching_lines), term=search_term))
            else:
                self.log_display.setPlainText("")
                self._set_status_message(_get_log_viewer_messages().get('no_lines_found', term=search_term))

            # Auto-scroll to top for search results
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.log_display.setTextCursor(cursor)

        except Exception as e:
            logger.error(f"Error searching logs: {e}")
            self._set_status_message(_get_log_viewer_messages().get('error_searching'))

    def _refresh_logs(self):
        """Refresh the log display"""
        if self.current_log_file:
            self._load_log_file(self.current_log_file)
            self._set_status_message(_get_log_viewer_messages().get('logs_refreshed'))
        else:
            self._load_current_log_file()

    def _clear_logs(self):
        """Clear the log display"""
        self.log_display.clear()
        self._set_status_message(_get_log_viewer_messages().get('display_cleared'))

    def _open_log_file(self):
        """Open a different log file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            _get_log_viewer_messages().get('open_log_title'),
            os.path.dirname(self.current_log_file) if self.current_log_file else "",
            _get_log_viewer_messages().get('log_files_filter')
        )

        if file_path:
            self.current_log_file = file_path
            self._load_log_file(file_path)

    def _save_logs(self):
        """Save current log content to a file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            _get_log_viewer_messages().get('save_logs_title'),
            f"eCan_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            _get_log_viewer_messages().get('save_files_filter')
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_display.toPlainText())
                self._set_status_message(_get_log_viewer_messages().get('logs_saved', filename=os.path.basename(file_path)))
                logger.info(f"Logs saved to: {file_path}")
            except Exception as e:
                logger.error(f"Error saving logs: {e}")
                QMessageBox.warning(self, _get_log_viewer_messages().get('error_title'), 
                                  _get_log_viewer_messages().get('error_save', error=str(e)))

    def closeEvent(self, event):
        """Handle window close event"""
        if self.log_watcher:
            self.log_watcher.stop()
        logger.info("Log Viewer window closed")
        event.accept()
