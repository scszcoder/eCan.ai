"""
ECBot OTA更新对话框模块
提供标准的更新对话框组件
"""

# 导入标准更新对话框
from .update_dialog import UpdateDialog, UpdateNotificationDialog
        
        # Status label
        self.status_label = QLabel("Ready to check for updates...")
        layout.addWidget(self.status_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Update information
        self.info_text = QTextEdit()
        self.info_text.setVisible(False)
        self.info_text.setMaximumHeight(100)
        layout.addWidget(self.info_text)
        
        # Version information
        if self.ota_updater:
            version_label = QLabel(f"Current version: {self.ota_updater.app_version}")
            layout.addWidget(version_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.check_button = QPushButton("Check for Updates")
        self.install_button = QPushButton("Install Update")
        self.install_button.setEnabled(False)
        self.close_button = QPushButton("Close")
        
        button_layout.addWidget(self.check_button)
        button_layout.addWidget(self.install_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def setup_connections(self):
        """Setup signal connections"""
        self.check_button.clicked.connect(self.check_for_updates)
        self.install_button.clicked.connect(self.install_update)
        self.close_button.clicked.connect(self.close)
    
    def check_for_updates(self):
        """Simplified update check"""
        if not self.ota_updater:
            self.status_label.setText("Updater not initialized")
            return
        
        self.check_button.setEnabled(False)
        self.status_label.setText("Checking for updates...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            # Direct call to check, no threading
            has_update, info = self.ota_updater.check_for_updates(silent=True, return_info=True)
            
            if has_update:
                self.status_label.setText("New version found!")
                self.update_info = info
                if isinstance(info, dict):
                    version = info.get('latest_version', 'Unknown')
                    self.info_text.setText(f"Latest version: {version}")
                else:
                    self.info_text.setText(str(info))
                self.info_text.setVisible(True)
                self.install_button.setEnabled(True)
            else:
                self.status_label.setText("Already up to date")
                
        except Exception as e:
            self.status_label.setText(f"Check failed: {str(e)}")
            logger.error(f"Update check failed: {e}")
        
        finally:
            self.progress_bar.setVisible(False)
            self.check_button.setEnabled(True)
    
    
    def install_update(self):
        """Simplified update installation"""
        if not self.ota_updater:
            return
        
        # Confirmation dialog
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 
            "Confirm Installation", 
            "Installing updates may require restarting the application. Continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.install_button.setEnabled(False)
        self.status_label.setText("Installing update...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            success = self.ota_updater.install_update()
            if success:
                self.status_label.setText("Update installed successfully! Please restart the application.")
                QMessageBox.information(self, "Installation Successful", "Update has been installed.")
            else:
                self.status_label.setText("Update installation failed.")
                QMessageBox.warning(self, "Installation Failed", "Update installation failed.")
        except Exception as e:
            error_msg = f"Installation error: {str(e)}"
            self.status_label.setText(error_msg)
            QMessageBox.critical(self, "Installation Error", error_msg)
        finally:
            self.install_button.setEnabled(True)
            self.progress_bar.setVisible(False)
    
    
    def closeEvent(self, event):
        """Close event (simplified version)"""
        # Simplified version doesn't use threading, close directly
        logger.info("Dialog closing")
        event.accept()
    
    


class UpdateNotificationDialog(QDialog):
    """Simplified update notification dialog"""
    
    def __init__(self, update_info="New version found", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Notification")
        self.setModal(True)
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # Information
        info_label = QLabel(update_info)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        install_button = QPushButton("Update Now")
        install_button.clicked.connect(self.accept)
        button_layout.addWidget(install_button)
        
        later_button = QPushButton("Later")
        later_button.clicked.connect(self.reject)
        button_layout.addWidget(later_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)


# 导入增强对话框
try:
    from .enhanced_dialog import EnhancedUpdateDialog
    # 默认使用增强对话框
    UpdateDialog = EnhancedUpdateDialog
except ImportError:
    # 如果导入失败，使用简单对话框作为后备
    UpdateDialog = SimpleUpdateDialog

# 为了向后兼容，保留原始名称
SimpleDialog = SimpleUpdateDialog