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
                               QCheckBox, QSplitter, QFileDialog, QMessageBox,
                               QProgressBar, QStatusBar, QLineEdit)
from PySide6.QtCore import QTimer, QThread, Signal, Qt, QFileSystemWatcher, QEvent
from PySide6.QtGui import QFont, QTextCursor, QAction, QIcon
from utils.logger_helper import logger_helper as logger
from config.app_info import app_info
from config.constants import APP_NAME


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


class LogViewer(QMainWindow):
    """Log Viewer Window for displaying real-time and historical logs"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Log Viewer")
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
        self.realtime_checkbox = QCheckBox("Real-time monitoring")
        self.realtime_checkbox.setChecked(True)
        self.realtime_checkbox.toggled.connect(self._toggle_realtime_monitoring)
        layout.addWidget(self.realtime_checkbox)
        
        # Auto-scroll checkbox
        self.autoscroll_checkbox = QCheckBox("Auto-scroll")
        self.autoscroll_checkbox.setChecked(True)
        self.autoscroll_checkbox.toggled.connect(self._toggle_auto_scroll)
        layout.addWidget(self.autoscroll_checkbox)
        
        layout.addStretch()
        
        # Log level filter
        layout.addWidget(QLabel("Filter:"))
        self.level_filter = QComboBox()
        self.level_filter.addItems(["All", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"])
        self.level_filter.currentTextChanged.connect(self._filter_logs)
        layout.addWidget(self.level_filter)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_logs)
        layout.addWidget(self.refresh_btn)
        
        # Search box
        layout.addWidget(QLabel("Search:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Enter search term...")
        self.search_box.textChanged.connect(self._search_logs)
        layout.addWidget(self.search_box)

        # Clear button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self._clear_logs)
        layout.addWidget(self.clear_btn)

        return panel
    
    def _create_bottom_controls(self):
        """Create bottom control buttons"""
        panel = QWidget()
        layout = QHBoxLayout(panel)
        
        # Open log file button
        self.open_file_btn = QPushButton("Open Log File...")
        self.open_file_btn.clicked.connect(self._open_log_file)
        layout.addWidget(self.open_file_btn)
        
        # Save logs button
        self.save_btn = QPushButton("Save Logs...")
        self.save_btn.clicked.connect(self._save_logs)
        layout.addWidget(self.save_btn)
        
        layout.addStretch()
        
        # Close button
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.close)
        layout.addWidget(self.close_btn)
        
        return panel
    
    def _setup_menu(self):
        """Set up the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        open_action = QAction("Open Log File...", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self._open_log_file)
        file_menu.addAction(open_action)
        
        save_action = QAction("Save Logs...", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._save_logs)
        file_menu.addAction(save_action)
        
        file_menu.addSeparator()
        
        close_action = QAction("Close", self)
        close_action.setShortcut("Ctrl+W")
        close_action.triggered.connect(self.close)
        file_menu.addAction(close_action)
        
        # View menu
        view_menu = menubar.addMenu("View")
        
        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self._refresh_logs)
        view_menu.addAction(refresh_action)
        
        clear_action = QAction("Clear", self)
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

        self._last_status_message = "Ready"
        self.status_bar.showMessage(self._last_status_message)
    
    def _apply_dark_theme(self):
        """Apply dark theme to the log viewer"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2d2d2d;
                color: #e0e0e0;
            }
            QTextEdit {
                background-color: #1a1a1a;
                color: #e0e0e0;
                border: 1px solid #404040;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            }
            QPushButton {
                background-color: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #505050;
                border-color: #707070;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
            QCheckBox {
                color: #e0e0e0;
            }
            QComboBox {
                background-color: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QLineEdit {
                background-color: #404040;
                color: #e0e0e0;
                border: 1px solid #606060;
                border-radius: 4px;
                padding: 4px 8px;
                font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
            }
            QLineEdit:focus {
                border-color: #808080;
                background-color: #4a4a4a;
            }
            QLabel {
                color: #e0e0e0;
            }
            QMenuBar {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border-bottom: 1px solid #404040;
            }
            QMenuBar::item:selected {
                background-color: #404040;
            }
            QMenu {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #404040;
            }
            QMenu::item:selected {
                background-color: #404040;
            }
            QStatusBar {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border-top: 1px solid #404040;
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
                self._set_status_message(f"Loaded: {os.path.basename(log_file)}")
                logger.info(f"Loaded log file: {log_file}")
            else:
                self._set_status_message("No log file found")
                logger.warning("No valid log file found")

        except Exception as e:
            logger.error(f"Error loading current log file: {e}")
            self._set_status_message("Error loading log file")

    def _load_log_file(self, file_path):
        """Load and display log file content"""
        try:
            self.progress_bar.setVisible(True)
            self.progress_bar.setRange(0, 0)  # Indeterminate progress

            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
                self.log_display.setPlainText(content)

            # Start real-time monitoring if enabled
            if self.realtime_checkbox.isChecked():
                self._start_realtime_monitoring(file_path)

            # Auto-scroll to bottom
            if self.auto_scroll:
                self._scroll_to_bottom()

            self.progress_bar.setVisible(False)

        except Exception as e:
            logger.error(f"Error loading log file {file_path}: {e}")
            QMessageBox.warning(self, "Error", f"Failed to load log file:\n{str(e)}")
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
            # Check current state before adding content
            was_at_bottom = self._is_at_bottom()

            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.log_display.setTextCursor(cursor)
            self.log_display.insertPlainText(content)

            # Only auto-scroll if:
            # 1. Auto-scroll is enabled
            # 2. User is not manually scrolling (viewing history)
            # 3. User was at the bottom before new content was added
            if self.auto_scroll and not self.user_is_scrolling and was_at_bottom:
                self._scroll_to_bottom()

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
        # Ignore programmatic scrolls
        if self.programmatic_scroll:
            return

        scrollbar = self.log_display.verticalScrollBar()

        # Always update the user scrolling state based on current position
        was_user_scrolling = self.user_is_scrolling

        if self._is_at_bottom():
            # User is at bottom, enable auto-scroll
            self.user_is_scrolling = False
        else:
            # User is not at bottom, disable auto-scroll
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
            self.status_bar.showMessage("📜 Viewing history - Auto-scroll paused (scroll to bottom to resume)")
        elif hasattr(self, '_last_status_message'):
            # Restore the last status message
            self.status_bar.showMessage(self._last_status_message)
        else:
            self.status_bar.showMessage("Ready")

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
            self._set_status_message("Real-time monitoring enabled")
        else:
            if self.log_watcher:
                self.log_watcher.stop()
                self.log_watcher = None
            self._set_status_message("Real-time monitoring disabled")

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

            # Read the original log file
            with open(self.current_log_file, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()

            if level == "All":
                # Show all content
                self.log_display.setPlainText(content)
                self._set_status_message("Showing all log levels")
            else:
                # Filter by log level
                lines = content.split('\n')
                filtered_lines = []

                for line in lines:
                    if f" - {level} - " in line or level.upper() in line:
                        filtered_lines.append(line)

                filtered_content = '\n'.join(filtered_lines)
                self.log_display.setPlainText(filtered_content)
                self._set_status_message(f"Showing {len(filtered_lines)} lines with {level} level")

            # Auto-scroll to bottom after filtering
            if self.auto_scroll:
                self._scroll_to_bottom()

        except Exception as e:
            logger.error(f"Error filtering logs: {e}")
            self._set_status_message("Error filtering logs")

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
                self._set_status_message(f"Found {len(matching_lines)} lines matching '{search_term}'")
            else:
                self.log_display.setPlainText("")
                self._set_status_message(f"No lines found matching '{search_term}'")

            # Auto-scroll to top for search results
            cursor = self.log_display.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.log_display.setTextCursor(cursor)

        except Exception as e:
            logger.error(f"Error searching logs: {e}")
            self._set_status_message("Error searching logs")

    def _refresh_logs(self):
        """Refresh the log display"""
        if self.current_log_file:
            self._load_log_file(self.current_log_file)
            self._set_status_message("Logs refreshed")
        else:
            self._load_current_log_file()

    def _clear_logs(self):
        """Clear the log display"""
        self.log_display.clear()
        self._set_status_message("Log display cleared")

    def _open_log_file(self):
        """Open a different log file"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Log File",
            os.path.dirname(self.current_log_file) if self.current_log_file else "",
            "Log Files (*.log *.txt);;All Files (*)"
        )

        if file_path:
            self.current_log_file = file_path
            self._load_log_file(file_path)

    def _save_logs(self):
        """Save current log content to a file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Logs",
            f"eCan_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            "Text Files (*.txt);;Log Files (*.log);;All Files (*)"
        )

        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_display.toPlainText())
                self._set_status_message(f"Logs saved to: {os.path.basename(file_path)}")
                logger.info(f"Logs saved to: {file_path}")
            except Exception as e:
                logger.error(f"Error saving logs: {e}")
                QMessageBox.warning(self, "Error", f"Failed to save logs:\n{str(e)}")

    def closeEvent(self, event):
        """Handle window close event"""
        if self.log_watcher:
            self.log_watcher.stop()
        logger.info("Log Viewer window closed")
        event.accept()
