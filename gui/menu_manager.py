"""
eCan Menu Manager
Responsible for managing all menu functionality of the application
"""

import sys
from PySide6.QtWidgets import (QMessageBox, QDialog, QLabel, QCheckBox,
                               QPushButton, QHBoxLayout, QVBoxLayout,
                               QComboBox, QTextEdit, QApplication)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from utils.logger_helper import logger_helper as logger


class MenuManager:
    """Menu Manager Class"""
    
    def __init__(self, main_window):
        """
        Initialize menu manager
        
        Args:
            main_window: Main window instance
        """
        self.main_window = main_window
        
    def setup_menu(self):
        """Set up eCan menu bar - cross-platform support"""
        menubar = self.main_window.menuBar()
        
        # Note: Application basic info is already set in main.py, no need to repeat here
        
        # Set up menus based on platform
        if sys.platform == 'darwin':  # macOS
            self._setup_macos_menus(menubar)
        elif sys.platform == 'win32':  # Windows
            self._setup_windows_menus(menubar)
        else:  # Linux and other platforms
            self._setup_linux_menus(menubar)
    
    def _setup_macos_menus(self, menubar):
        """Set up simplified macOS menu (eCan + Help only)"""
        try:
            # Enable native macOS menu bar
            menubar.setNativeMenuBar(True)
            logger.info("Enabled native macOS menu bar")

            # Check if menus already exist to avoid duplicate setup
            existing_menus = menubar.actions()
            if existing_menus:
                logger.info(f"Found {len(existing_menus)} existing menus, skipping duplicate setup")
                return

            # On macOS, the first menu automatically becomes the application menu
            # Use empty string to let system auto-set application menu name
            app_menu = menubar.addMenu('')  # Empty string lets system auto-set application menu
            self._setup_macos_app_menu(app_menu)  # Use specialized macOS app menu setup

            logger.info("macOS application menu setup complete")

        except Exception as e:
            logger.warning(f"macOS menu setup failed, using default method: {e}")
            # If failed, try to add basic menu
            try:
                app_menu = menubar.addMenu('')  # Use empty string even if failed
                self._setup_app_menu(app_menu)
            except Exception as e2:
                logger.error(f"Fallback menu setup also failed: {e2}")
                return

        # Only keep Help menu in addition to application menu
        help_menu = menubar.addMenu('Help')
        self._setup_help_menu(help_menu)

        logger.info("macOS menu bar setup complete (eCan + Help only)")
    
    def _setup_windows_menus(self, menubar):
        """Set up simplified Windows menu (eCan + Help only)"""
        try:
            # Windows uses non-native menu bar for better control
            menubar.setNativeMenuBar(False)

            # Set menu bar style to integrate with title bar
            self._setup_titlebar_menu_style(menubar)

            logger.info("Using Qt menu bar (Windows optimized, integrated with title bar)")

        except Exception as e:
            logger.warning(f"Windows menu setup failed: {e}")

        # Application menu
        app_menu = menubar.addMenu('eCan')
        self._setup_app_menu(app_menu)

        # Only keep Help menu
        help_menu = menubar.addMenu('Help')
        self._setup_help_menu(help_menu)
    
    def _setup_linux_menus(self, menubar):
        """Set up simplified Linux menu (eCan + Help only)"""
        try:
            # Linux typically uses Qt menu bar
            menubar.setNativeMenuBar(False)

            # Set menu bar style to integrate with title bar
            self._setup_titlebar_menu_style(menubar)

            logger.info("Using Qt menu bar (Linux, integrated with title bar)")

        except Exception as e:
            logger.warning(f"Linux menu setup failed: {e}")

        # Standard menu layout on Linux - keep only eCan and Help
        app_menu = menubar.addMenu('eCan')
        self._setup_app_menu(app_menu)

        help_menu = menubar.addMenu('Help')
        self._setup_help_menu(help_menu)

    def _setup_titlebar_menu_style(self, menubar):
        """Set menu bar style to integrate with title bar"""
        try:
            # Set menu bar style to make it look like part of the title bar
            menubar.setStyleSheet("""
                QMenuBar {
                    background-color: #2d2d2d;  /* Match title bar color */
                    color: #e0e0e0;
                    border: none;
                    border-bottom: 1px solid #404040;  /* Add bottom border separator */
                    padding: 0px 8px;  /* Add some left-right padding */
                    margin: 0px;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 13px;
                    font-weight: 500;
                    height: 30px;  /* Slightly reduce height for compactness */
                    spacing: 8px;  /* Spacing between menu items */
                }

                QMenuBar::item {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 4px 10px;  /* Reduce padding for compactness */
                    margin: 2px 1px;  /* Add small margins */
                    border-radius: 3px;  /* Slightly reduce corner radius */
                    min-width: 40px;  /* Minimum width */
                }

                QMenuBar::item:selected {
                    background-color: #404040;
                    color: #ffffff;
                }

                QMenuBar::item:pressed {
                    background-color: #505050;
                    color: #ffffff;
                }

                QMenu {
                    background-color: #2d2d2d;
                    color: #e0e0e0;
                    border: 1px solid #404040;
                    border-radius: 6px;
                    padding: 4px 0px;
                    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    font-size: 13px;
                    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);  /* Add shadow effect */
                }

                QMenu::item {
                    background-color: transparent;
                    color: #e0e0e0;
                    padding: 8px 24px;  /* Increase padding for comfort */
                    margin: 1px 4px;
                    border-radius: 4px;
                    min-height: 20px;  /* Minimum height */
                }

                QMenu::item:selected {
                    background-color: #404040;
                    color: #ffffff;
                }

                QMenu::item:disabled {
                    color: #808080;  /* Color for disabled items */
                }

                QMenu::separator {
                    height: 1px;
                    background-color: #404040;
                    margin: 6px 12px;  /* Increase separator margins */
                }

                QMenu::indicator {
                    width: 16px;
                    height: 16px;
                    margin-left: 4px;
                }

                QMenu::indicator:checked {
                    background-color: #0078d4;  /* Use blue for selected state */
                    border-radius: 2px;
                }

                QMenu::right-arrow {
                    width: 12px;
                    height: 12px;
                    margin-right: 8px;
                }
            """)

            # Set fixed height for menu bar to make it more compact
            menubar.setFixedHeight(30)

            logger.info("Menu bar style set to title bar integration mode")

        except Exception as e:
            logger.error(f"Failed to set menu bar style: {e}")
    

    
    def _setup_app_menu(self, app_menu):
        """Set up application menu"""
        # About eCan
        about_action = QAction('About eCan', self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        # Check for updates
        check_update_action = QAction('Check for Updates...', self.main_window)
        check_update_action.triggered.connect(self.show_update_dialog)
        app_menu.addAction(check_update_action)
        
        app_menu.addSeparator()
        
        # Preferences/Settings
        preferences_action = QAction('Preferences...', self.main_window)
        preferences_action.setShortcut('Ctrl+,')
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # Services menu (macOS standard)
        services_menu = app_menu.addMenu('Services')
        # Services menu is usually managed by system, just placeholder here
        
        app_menu.addSeparator()
        
        # Hide eCan
        hide_action = QAction('Hide eCan', self.main_window)
        hide_action.setShortcut('Ctrl+H')
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # Hide others
        hide_others_action = QAction('Hide Others', self.main_window)
        hide_others_action.setShortcut('Ctrl+Alt+H')
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # Show all
        show_all_action = QAction('Show All', self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # Quit eCan
        quit_action = QAction('Quit eCan', self.main_window)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.main_window.close)
        app_menu.addAction(quit_action)
    

    

    

    
    def _setup_help_menu(self, help_menu):
        """Set up Help menu"""
        # User manual
        user_manual_action = QAction('eCan Help', self.main_window)
        user_manual_action.setShortcut('F1')
        user_manual_action.triggered.connect(self.show_user_manual)
        help_menu.addAction(user_manual_action)
        
        # Quick start guide
        quick_start_action = QAction('Quick Start Guide', self.main_window)
        quick_start_action.triggered.connect(self.show_quick_start)
        help_menu.addAction(quick_start_action)
        
        # Keyboard shortcuts
        shortcuts_action = QAction('Keyboard Shortcuts', self.main_window)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        help_menu.addSeparator()
        
        # Report issue
        feedback_action = QAction('Report Issue...', self.main_window)
        feedback_action.triggered.connect(self.report_issue)
        help_menu.addAction(feedback_action)
        
        # Send feedback
        send_feedback_action = QAction('Send Feedback...', self.main_window)
        send_feedback_action.triggered.connect(self.send_feedback)
        help_menu.addAction(send_feedback_action)
    
    def _setup_macos_app_menu(self, app_menu):
        """Set up macOS-specific application menu (ensure all functionality included)"""
        # About eCan
        about_action = QAction('About eCan', self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        app_menu.addSeparator()
        
        # Check for updates (OTA functionality)
        check_update_action = QAction('Check for Updates...', self.main_window)
        check_update_action.triggered.connect(self.show_update_dialog)
        app_menu.addAction(check_update_action)
        
        app_menu.addSeparator()
        
        # Preferences/Settings
        preferences_action = QAction('Preferences...', self.main_window)
        preferences_action.setShortcut('Cmd+,')  # macOS uses Cmd instead of Ctrl
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # Services menu (macOS standard)
        services_menu = app_menu.addMenu('Services')
        # Services menu is usually managed by system, just placeholder here
        
        app_menu.addSeparator()
        
        # Hide eCan
        hide_action = QAction('Hide eCan', self.main_window)
        hide_action.setShortcut('Cmd+H')  # macOS uses Cmd
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # Hide others
        hide_others_action = QAction('Hide Others', self.main_window)
        hide_others_action.setShortcut('Cmd+Alt+H')  # macOS uses Cmd
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # Show all
        show_all_action = QAction('Show All', self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # Quit eCan
        quit_action = QAction('Quit eCan', self.main_window)
        quit_action.setShortcut('Cmd+Q')  # macOS uses Cmd
        quit_action.triggered.connect(self.main_window.close)
        app_menu.addAction(quit_action)
        
        logger.info("macOS application menu setup complete, includes OTA check functionality")
    

    

    
    # ==================== Application Menu Function Implementation ====================
    
    def show_about_dialog(self):
        """Show About dialog"""
        try:
            # Read version information
            version = "1.0.0"
            try:
                with open("VERSION", "r") as f:
                    version = f.read().strip()
            except:
                pass
            
            about_text = f"""
            <h2>eCan</h2>
            <p>Version: {version}</p>
            <p>An intelligent automation platform for e-commerce operations.</p>
            <p>© 2024 eCan Team</p>
            """
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle("About eCan")
            msg.setText(about_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
        except Exception as e:
            logger.error(f"Failed to show about dialog: {e}")
    
    def show_update_dialog(self):
        """Show update dialog"""
        try:
            # Import and initialize OTA components on demand
            from ota import OTAUpdater, UpdateDialog
            
            # Create OTA updater instance (only when needed)
            ota_updater = OTAUpdater()
            
            # Create and show update dialog, pass OTA updater instance
            dialog = UpdateDialog(ota_updater, self.main_window)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to show update dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open update dialog")
    
    def show_settings(self):
        """Show settings dialog"""
        try:
            settings_dialog = QDialog(self.main_window)
            settings_dialog.setWindowTitle("eCan Settings")
            settings_dialog.setModal(True)
            settings_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # Settings label
            title_label = QLabel("Application Settings")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # Settings items (examples)
            auto_save_checkbox = QCheckBox("Auto-save projects")
            auto_save_checkbox.setChecked(True)
            layout.addWidget(auto_save_checkbox)
            
            dark_mode_checkbox = QCheckBox("Dark mode")
            layout.addWidget(dark_mode_checkbox)
            
            # Buttons
            button_layout = QHBoxLayout()
            ok_button = QPushButton("OK")
            cancel_button = QPushButton("Cancel")
            
            ok_button.clicked.connect(settings_dialog.accept)
            cancel_button.clicked.connect(settings_dialog.reject)
            
            button_layout.addWidget(ok_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            settings_dialog.setLayout(layout)
            settings_dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to show settings: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open settings")
    
    def hide_app(self):
        """Hide application"""
        try:
            self.main_window.hide()
            logger.info("Application hidden")
        except Exception as e:
            logger.error(f"Failed to hide app: {e}")
    
    def hide_others(self):
        """Hide other applications"""
        try:
            # In Qt, this functionality mainly works on macOS
            QApplication.instance().setQuitOnLastWindowClosed(False)
            logger.info("Hide others action triggered")
        except Exception as e:
            logger.error(f"Failed to hide others: {e}")
    
    def show_all(self):
        """Show all applications"""
        try:
            # Show all windows of the application
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            logger.info("Show all action triggered")
        except Exception as e:
            logger.error(f"Failed to show all: {e}")
    

    

    

    
    # ==================== Help Menu Function Implementation ====================
    
    def show_user_manual(self):
        """Show user manual"""
        try:
            manual_text = """
            <h2>eCan User Manual</h2>
            <h3>Getting Started</h3>
            <p>Welcome to eCan! This is your comprehensive automation platform.</p>
            
            <h3>Main Features</h3>
            <ul>
                <li><b>Project Management:</b> Create and manage automation projects</li>
                <li><b>Data Import/Export:</b> Handle various data formats</li>
                <li><b>Task Automation:</b> Set up automated workflows</li>
                <li><b>Real-time Monitoring:</b> Track your automation progress</li>
            </ul>
            
            <h3>Quick Tips</h3>
            <ul>
                <li>Use Ctrl+N to create a new project</li>
                <li>Use Ctrl+S to save your current work</li>
                <li>Press F1 anytime to access this help</li>
            </ul>
            """
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle("eCan User Manual")
            msg.setText(manual_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show user manual: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open user manual")
    
    def show_quick_start(self):
        """Show quick start guide"""
        try:
            quick_start_text = """
            <h2>Quick Start Guide</h2>
            
            <h3>Step 1: Create Your First Project</h3>
            <p>Go to <b>File → New Project</b> or press <b>Ctrl+N</b></p>
            
            <h3>Step 2: Import Your Data</h3>
            <p>Use <b>File → Import Data</b> to load your source data</p>
            
            <h3>Step 3: Configure Automation</h3>
            <p>Set up your automation rules and workflows</p>
            
            <h3>Step 4: Run and Monitor</h3>
            <p>Start your automation and monitor progress in real-time</p>
            
            <h3>Step 5: Export Results</h3>
            <p>Use <b>File → Export Data</b> to save your results</p>
            """
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle("Quick Start Guide")
            msg.setText(quick_start_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show quick start guide: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open quick start guide")
    
    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        try:
            shortcuts_text = """
            <h2>Keyboard Shortcuts</h2>
            
            <h3>File Operations</h3>
            <table>
                <tr><td><b>Ctrl+N</b></td><td>New Project</td></tr>
                <tr><td><b>Ctrl+O</b></td><td>Open Project</td></tr>
                <tr><td><b>Ctrl+S</b></td><td>Save Project</td></tr>
                <tr><td><b>Ctrl+Shift+S</b></td><td>Save Project As</td></tr>
                <tr><td><b>Ctrl+I</b></td><td>Import Data</td></tr>
                <tr><td><b>Ctrl+E</b></td><td>Export Data</td></tr>
            </table>
            
            <h3>Edit Operations</h3>
            <table>
                <tr><td><b>Ctrl+Z</b></td><td>Undo</td></tr>
                <tr><td><b>Ctrl+Shift+Z</b></td><td>Redo</td></tr>
                <tr><td><b>Ctrl+X</b></td><td>Cut</td></tr>
                <tr><td><b>Ctrl+C</b></td><td>Copy</td></tr>
                <tr><td><b>Ctrl+V</b></td><td>Paste</td></tr>
                <tr><td><b>Ctrl+A</b></td><td>Select All</td></tr>
                <tr><td><b>Ctrl+F</b></td><td>Find</td></tr>
            </table>
            
            <h3>Application</h3>
            <table>
                <tr><td><b>Ctrl+,</b></td><td>Preferences</td></tr>
                <tr><td><b>Ctrl+H</b></td><td>Hide eCan</td></tr>
                <tr><td><b>Ctrl+Q</b></td><td>Quit eCan</td></tr>
                <tr><td><b>F1</b></td><td>Help</td></tr>
            </table>
            """
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle("Keyboard Shortcuts")
            msg.setText(shortcuts_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show shortcuts: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open shortcuts")
    
    def report_issue(self):
        """Report issue"""
        try:
            issue_dialog = QDialog(self.main_window)
            issue_dialog.setWindowTitle("Report Issue")
            issue_dialog.setModal(True)
            issue_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # Title
            title_label = QLabel("Report an Issue")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # Issue type
            type_label = QLabel("Issue Type:")
            layout.addWidget(type_label)
            
            type_combo = QComboBox()
            type_combo.addItems(["Bug Report", "Feature Request", "Performance Issue", "Other"])
            layout.addWidget(type_combo)
            
            # Issue description
            desc_label = QLabel("Description:")
            layout.addWidget(desc_label)
            
            desc_text = QTextEdit()
            desc_text.setPlaceholderText("Please describe the issue in detail...")
            layout.addWidget(desc_text)
            
            # Buttons
            button_layout = QHBoxLayout()
            submit_button = QPushButton("Submit")
            cancel_button = QPushButton("Cancel")
            
            def submit_issue():
                issue_type = type_combo.currentText()
                description = desc_text.toPlainText()
                if description.strip():
                    QMessageBox.information(self.main_window, "Success", "Issue reported successfully! Thank you for your feedback.")
                    logger.info(f"Issue reported: {issue_type} - {description[:50]}...")
                    issue_dialog.accept()
                else:
                    QMessageBox.warning(self.main_window, "Warning", "Please provide a description of the issue.")
            
            submit_button.clicked.connect(submit_issue)
            cancel_button.clicked.connect(issue_dialog.reject)
            
            button_layout.addWidget(submit_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            issue_dialog.setLayout(layout)
            issue_dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to show issue report dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open issue report dialog")
    
    def send_feedback(self):
        """Send feedback"""
        try:
            feedback_dialog = QDialog(self.main_window)
            feedback_dialog.setWindowTitle("Send Feedback")
            feedback_dialog.setModal(True)
            feedback_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # Title
            title_label = QLabel("Send Feedback to eCan Team")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # Feedback type
            type_label = QLabel("Feedback Type:")
            layout.addWidget(type_label)
            
            type_combo = QComboBox()
            type_combo.addItems(["General Feedback", "Feature Suggestion", "Compliment", "Question"])
            layout.addWidget(type_combo)
            
            # Feedback content
            content_label = QLabel("Your Feedback:")
            layout.addWidget(content_label)
            
            content_text = QTextEdit()
            content_text.setPlaceholderText("Please share your thoughts, suggestions, or questions...")
            layout.addWidget(content_text)
            
            # Buttons
            button_layout = QHBoxLayout()
            send_button = QPushButton("Send")
            cancel_button = QPushButton("Cancel")
            
            def send_feedback():
                feedback_type = type_combo.currentText()
                content = content_text.toPlainText()
                if content.strip():
                    QMessageBox.information(self.main_window, "Success", "Thank you for your feedback! We appreciate your input.")
                    logger.info(f"Feedback sent: {feedback_type} - {content[:50]}...")
                    feedback_dialog.accept()
                else:
                    QMessageBox.warning(self.main_window, "Warning", "Please provide your feedback content.")
            
            send_button.clicked.connect(send_feedback)
            cancel_button.clicked.connect(feedback_dialog.reject)
            
            button_layout.addWidget(send_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            feedback_dialog.setLayout(layout)
            feedback_dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to show feedback dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open feedback dialog")
    
    # ==================== Helper Methods ====================
    
    def _apply_messagebox_style(self, msg):
        """Apply message box style"""
        try:
            # Here you can apply custom styles
            pass
        except Exception as e:
            logger.error(f"Failed to apply messagebox style: {e}")
    

    

