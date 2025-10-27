"""
eCan Menu Manager
Responsible for managing all menu functionality of the application
"""

import sys
import os
from PySide6.QtWidgets import (QMessageBox, QDialog, QLabel, QCheckBox,
                               QPushButton, QHBoxLayout, QVBoxLayout,
                               QComboBox, QTextEdit, QApplication, QGroupBox,
                               QRadioButton, QLineEdit)
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

    def setup_custom_menu(self, custom_menubar):
        """Set up eCan menu bar for custom title bar (Windows/Linux)"""
        try:
            logger.info("Setting up custom title bar menu for Windows/Linux...")
            
            # Set up simplified menus for custom title bar
            app_menu = custom_menubar.addMenu('eCan')
            logger.debug("Added 'eCan' menu to custom menubar")
            self._setup_app_menu(app_menu)

            help_menu = custom_menubar.addMenu('Help')
            logger.debug("Added 'Help' menu to custom menubar")
            self._setup_help_menu(help_menu)

            logger.info("✅ Custom title bar menu setup complete (eCan + Help only)")
        except Exception as e:
            logger.error(f"❌ Failed to setup custom menu: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
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
        try:
            # User manual
            user_manual_action = QAction('eCan Help', self.main_window)
            user_manual_action.setShortcut('F1')
            user_manual_action.triggered.connect(self.show_user_manual)
            help_menu.addAction(user_manual_action)
            logger.debug("Added 'eCan Help' menu item")
            
            # Quick start guide
            quick_start_action = QAction('Quick Start Guide', self.main_window)
            quick_start_action.triggered.connect(self.show_quick_start)
            help_menu.addAction(quick_start_action)
            logger.debug("Added 'Quick Start Guide' menu item")
            
            # Keyboard shortcuts
            shortcuts_action = QAction('Keyboard Shortcuts', self.main_window)
            shortcuts_action.triggered.connect(self.show_shortcuts)
            help_menu.addAction(shortcuts_action)
            logger.debug("Added 'Keyboard Shortcuts' menu item")

            help_menu.addSeparator()

            # Log Viewer - use platform-specific shortcut
            log_viewer_action = QAction('View Logs...', self.main_window)
            # Only set shortcut on macOS to avoid conflicts on Windows
            if sys.platform == 'darwin':
                log_viewer_action.setShortcut('Cmd+Shift+L')
            # On Windows, avoid Ctrl+Shift+L as it may conflict with system shortcuts
            log_viewer_action.triggered.connect(self.show_log_viewer)
            help_menu.addAction(log_viewer_action)
            logger.debug("Added 'View Logs' menu item")
            
            logger.info("Help menu setup completed successfully")
        except Exception as e:
            logger.error(f"Error setting up help menu: {e}")

        # Hidden menu items (kept for potential future use)
        # help_menu.addSeparator()
        # 
        # # Report issue
        # feedback_action = QAction('Report Issue...', self.main_window)
        # feedback_action.triggered.connect(self.report_issue)
        # help_menu.addAction(feedback_action)
        # 
        # # Send feedback
        # send_feedback_action = QAction('Send Feedback...', self.main_window)
        # send_feedback_action.triggered.connect(self.send_feedback)
        # help_menu.addAction(send_feedback_action)
    
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
                import sys
                import os

                # Get correct resource path (supports PyInstaller packaging environment)
                if hasattr(sys, '_MEIPASS'):
                    # PyInstaller packaging environment
                    base_path = sys._MEIPASS
                else:
                    # Development environment - from gui/menu_manager.py to project root
                    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

                # Try multiple possible VERSION file locations
                if hasattr(sys, '_MEIPASS'):
                    # PyInstaller environment - VERSION is in _internal directory
                    version_paths = [
                        os.path.join(base_path, "VERSION"),  # PyInstaller _MEIPASS root
                        os.path.join(base_path, "_internal", "VERSION"),  # PyInstaller _internal directory
                        os.path.join(os.path.dirname(sys.executable), "VERSION"),  # Executable directory
                        os.path.join(os.path.dirname(sys.executable), "_internal", "VERSION"),  # Executable _internal
                    ]
                else:
                    # Development environment
                    version_paths = [
                        os.path.join(base_path, "VERSION"),  # Project root
                        os.path.join(os.path.dirname(__file__), "..", "VERSION"),  # Project root directory
                        os.path.join(os.getcwd(), "VERSION"),  # Working directory
                        "VERSION",  # Current directory
                    ]

                # Use unified version reading function
                from utils.app_setup_helper import read_version_file
                version = read_version_file(version_paths)
            except Exception:
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
            from ota.core.updater import OTAUpdater
            from ota.gui.dialog import UpdateDialog
            
            # Create OTA updater instance (only when needed)
            ota_updater = OTAUpdater()
            
            # Create and show update dialog, pass OTA updater instance
            dialog = UpdateDialog(parent=self.main_window, ota_updater=ota_updater)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to show update dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", f"Failed to open update dialog: {str(e)}")
    
    def show_settings(self):
        """Show settings dialog"""
        try:
            settings_dialog = QDialog(self.main_window)
            settings_dialog.setWindowTitle("eCan Settings")
            settings_dialog.setModal(True)
            settings_dialog.setFixedSize(600, 500)
            
            layout = QVBoxLayout()
            
            # Settings label
            title_label = QLabel("Application Settings")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # OTA Update Settings Group
            ota_group = QGroupBox("OTA Update Settings")
            ota_layout = QVBoxLayout()
            
            # Server selection
            server_layout = QHBoxLayout()
            server_label = QLabel("Update Server:")
            server_layout.addWidget(server_label)
            
            # Radio buttons for server selection
            self.remote_server_radio = QRadioButton("Remote Server (GitHub)")
            self.local_server_radio = QRadioButton("Local Test Server")
            
            # Load current configuration
            try:
                from ota.core.config import ota_config
                if ota_config.is_using_local_server():
                    self.local_server_radio.setChecked(True)
                else:
                    self.remote_server_radio.setChecked(True)
            except Exception as e:
                logger.warning(f"Failed to load OTA config: {e}")
                self.remote_server_radio.setChecked(True)
            
            ota_layout.addWidget(self.remote_server_radio)
            ota_layout.addWidget(self.local_server_radio)
            
            # Local server URL input
            local_url_layout = QHBoxLayout()
            local_url_label = QLabel("Local Server URL:")

            # Get default URL from config
            try:
                from ota.core.config import ota_config
                default_url = ota_config.config.get("local_server_url", "http://127.0.0.1:8080")
            except:
                default_url = "http://127.0.0.1:8080"
            
            self.local_url_input = QLineEdit(default_url)
            local_url_layout.addWidget(local_url_label)
            local_url_layout.addWidget(self.local_url_input)
            ota_layout.addLayout(local_url_layout)
            
            # Start local server button
            start_server_button = QPushButton("Start Local Test Server")
            start_server_button.clicked.connect(self.start_local_ota_server)
            ota_layout.addWidget(start_server_button)
            
            ota_group.setLayout(ota_layout)
            layout.addWidget(ota_group)
            
            # Other settings
            other_group = QGroupBox("General Settings")
            other_layout = QVBoxLayout()
            
            auto_save_checkbox = QCheckBox("Auto-save projects")
            auto_save_checkbox.setChecked(True)
            other_layout.addWidget(auto_save_checkbox)
            
            dark_mode_checkbox = QCheckBox("Dark mode")
            other_layout.addWidget(dark_mode_checkbox)
            
            other_group.setLayout(other_layout)
            layout.addWidget(other_group)
            
            # Buttons
            button_layout = QHBoxLayout()
            ok_button = QPushButton("OK")
            cancel_button = QPushButton("Cancel")
            apply_button = QPushButton("Apply")
            
            ok_button.clicked.connect(lambda: self.save_ota_settings(settings_dialog))
            cancel_button.clicked.connect(settings_dialog.reject)
            apply_button.clicked.connect(lambda: self.save_ota_settings())
            
            button_layout.addWidget(apply_button)
            button_layout.addWidget(ok_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            settings_dialog.setLayout(layout)
            settings_dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to show settings: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open settings")
    
    def save_ota_settings(self, dialog=None):
        """Save OTA settings"""
        try:
            from ota.core.config import ota_config

            # Save server selection
            use_local = self.local_server_radio.isChecked()
            ota_config.set_use_local_server(use_local)

            # Save local server URL
            local_url = self.local_url_input.text().strip()
            if local_url:
                ota_config.set_local_server_url(local_url)
            
            logger.info(f"OTA settings saved: use_local={use_local}, local_url={local_url}")
            QMessageBox.information(self.main_window, "Settings", "OTA settings saved successfully!")
            
            if dialog:
                dialog.accept()
                
        except Exception as e:
            logger.error(f"Failed to save OTA settings: {e}")
            QMessageBox.warning(self.main_window, "Error", f"Failed to save settings: {e}")
    
    def start_local_ota_server(self):
        """Start local OTA test server"""
        try:
            import subprocess
            import sys
            from pathlib import Path

            # Get startup script path
            project_root = Path(__file__).parent.parent
            start_script = project_root / "ota" / "start_local_server.py"

            if not start_script.exists():
                QMessageBox.warning(self.main_window, "Error", f"Local server script not found: {start_script}")
                return

            # Start server in new command line window
            from utils.subprocess_helper import popen_no_window
            if sys.platform == "win32":
                # Windows
                popen_no_window([
                    "cmd", "/c", "start", "cmd", "/k",
                    f"python \"{start_script}\""
                ], shell=True)
            else:
                # macOS/Linux
                popen_no_window([
                    "gnome-terminal", "--", "python", str(start_script)
                ])

            # Get local server URL for display
            try:
                from ota.core.config import ota_config
                server_url = ota_config.config.get("local_server_url", "http://127.0.0.1:8080")
            except:
                server_url = "http://127.0.0.1:8080"
            
            QMessageBox.information(
                self.main_window, 
                "Server Starting", 
                f"Local OTA test server is starting in a new window.\n"
                f"Server will be available at: {server_url}\n\n"
                "Check the terminal window for server status."
            )
            
        except Exception as e:
            logger.error(f"Failed to start local OTA server: {e}")
            QMessageBox.warning(self.main_window, "Error", f"Failed to start server: {e}")
    
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
            <h3>Overview</h3>
            <p>eCan is an enterprise-grade intelligent automation platform designed to streamline 
            e-commerce operations through advanced AI-powered agents and workflow automation.</p>
            
            <h3>Core Capabilities</h3>
            <ul>
                <li><b>Agent Management:</b> Deploy and orchestrate AI agents for automated task execution</li>
                <li><b>Skill Development:</b> Create and customize automation skills using visual workflow editor</li>
                <li><b>Organization Structure:</b> Manage hierarchical teams and agent assignments</li>
                <li><b>Task Scheduling:</b> Configure automated workflows with flexible scheduling options</li>
                <li><b>Real-time Monitoring:</b> Track agent performance and task execution status</li>
            </ul>
            
            <h3>Getting Help</h3>
            <ul>
                <li>Press <b>F1</b> at any time to access this help documentation</li>
                <li>View <b>Quick Start Guide</b> for step-by-step instructions</li>
                <li>Check <b>Keyboard Shortcuts</b> for productivity tips</li>
                <li>Access <b>View Logs</b> for system diagnostics and troubleshooting</li>
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
            
            <h3>Step 1: Configure Your Organization</h3>
            <p>Navigate to the <b>Agents</b> page to set up your organizational structure. 
            Create departments and assign agents to appropriate teams for optimal workflow management.</p>
            
            <h3>Step 2: Deploy AI Agents</h3>
            <p>Access the <b>Agents</b> section to deploy and configure AI agents. 
            Assign specific roles, capabilities, and permissions to each agent based on your operational requirements.</p>
            
            <h3>Step 3: Create Automation Skills</h3>
            <p>Use the <b>Skills</b> editor to design custom automation workflows. 
            Leverage the visual node-based interface to create, test, and deploy automation skills.</p>
            
            <h3>Step 4: Schedule Tasks</h3>
            <p>Configure task schedules in the <b>Schedule</b> section. 
            Set up recurring automation tasks with flexible timing and execution parameters.</p>
            
            <h3>Step 5: Monitor and Optimize</h3>
            <p>Use the <b>Chat</b> interface to interact with agents and monitor task execution. 
            Review performance metrics and optimize workflows for improved efficiency.</p>
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
            # Determine platform-specific modifier key
            if sys.platform == 'darwin':
                modifier = 'Cmd'
            else:
                modifier = 'Ctrl'
            
            shortcuts_text = f"""
            <h2>Keyboard Shortcuts</h2>
            
            <h3>Application Control</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+,</b></td><td style="padding: 4px;">Open Preferences</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+H</b></td><td style="padding: 4px;">Hide Application</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+Q</b></td><td style="padding: 4px;">Quit Application</td></tr>
                <tr><td style="padding: 4px;"><b>F1</b></td><td style="padding: 4px;">Open Help Documentation</td></tr>
            </table>
            
            <h3>System Utilities</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+Shift+L</b></td><td style="padding: 4px;">View System Logs</td></tr>
            </table>
            
            <h3>Navigation</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+1</b></td><td style="padding: 4px;">Navigate to Chat</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+2</b></td><td style="padding: 4px;">Navigate to Agents</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+3</b></td><td style="padding: 4px;">Navigate to Skills</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+4</b></td><td style="padding: 4px;">Navigate to Schedule</td></tr>
            </table>
            
            <p style="margin-top: 16px; color: #666; font-size: 12px;">
            <i>Note: Additional context-specific shortcuts are available within each module.</i>
            </p>
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
        """Apply message box style and set eCan icon"""
        try:
            # Set eCan icon for message box
            try:
                from config.app_info import app_info
                resource_path = app_info.app_resources_path

                # Platform-specific icon candidates
                if sys.platform == 'darwin':
                    # macOS prefers larger, high-quality icons, prioritize logoWhite22.png
                    icon_candidates = [
                        os.path.join(resource_path, "images", "logos", "logoWhite22.png"),
                        os.path.join(resource_path, "images", "logos", "rounded", "dock_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "rounded", "dock_128x128.png"),
                        os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                    ]
                else:
                    # Windows/Linux icon candidates
                    icon_candidates = [
                        os.path.join(resource_path, "images", "logos", "desktop_256x256.png"),
                        os.path.join(resource_path, "images", "logos", "taskbar_32x32.png"),
                        os.path.join(os.path.dirname(resource_path), "eCan.ico"),
                    ]

                icon_set = False
                for candidate in icon_candidates:
                    if os.path.exists(candidate):
                        from PySide6.QtGui import QPixmap
                        from PySide6.QtCore import Qt
                        pixmap = QPixmap(candidate)
                        if not pixmap.isNull():
                            # Use larger icon size for macOS
                            icon_size = 128 if sys.platform == 'darwin' else 64
                            scaled_pixmap = pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            msg.setIconPixmap(scaled_pixmap)
                            icon_set = True
                            logger.info(f"✅ MenuManager MessageBox custom icon set from: {candidate} (size: {icon_size}x{icon_size})")

                            # Additional logging for development debugging
                            if sys.platform == 'darwin':
                                logger.info("ℹ️  macOS: Custom icon set, but system may override in development environment")
                            break
                        else:
                            logger.warning(f"Failed to load icon from: {candidate}")

                if not icon_set:
                    from PySide6.QtWidgets import QMessageBox
                    msg.setIcon(QMessageBox.Information)
                    logger.warning("⚠️  Using default information icon - custom icon loading failed")
                    logger.info("💡 If running in development, try building and running as packaged application")
            except Exception as e:
                logger.warning(f"Failed to set message box icon: {e}")
                from PySide6.QtWidgets import QMessageBox
                msg.setIcon(QMessageBox.Information)

        except Exception as e:
            logger.error(f"Failed to apply messagebox style: {e}")

    def show_log_viewer(self):
        """Show log viewer window"""
        try:
            # Import here to avoid circular imports
            from gui.log_viewer import LogViewer

            # Check if log viewer is already open
            if hasattr(self, 'log_viewer_window') and self.log_viewer_window and not self.log_viewer_window.isHidden():
                # Bring existing window to front
                self.log_viewer_window.raise_()
                self.log_viewer_window.activateWindow()
                logger.info("Brought existing log viewer window to front")
            else:
                # Create new log viewer window
                self.log_viewer_window = LogViewer(self.main_window)
                self.log_viewer_window.show()
                logger.info("Opened new log viewer window")

        except Exception as e:
            logger.error(f"Failed to show log viewer: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self.main_window, "Error", f"Failed to open log viewer:\n{str(e)}")



