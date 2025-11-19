#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ECBot OTA Update Dialog - Standard UI Version
Follows ECBot standard UI design guidelines
"""

import os
import sys
import time
import threading
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QProgressBar, QTextEdit, QMessageBox, QGroupBox, QFrame,
    QGridLayout, QCheckBox, QSpacerItem, QSizePolicy, QApplication
)
from PySide6.QtCore import Qt, QTimer, Signal, QThread
from PySide6.QtGui import QFont

from utils.logger_helper import logger_helper as logger
from .i18n import get_translator
from ota.core.download_manager import download_manager, DownloadState


# Get translator instance
_tr = get_translator()


class InstallWorker(QThread):
    """Installation worker thread"""
    
    # Signals
    status_updated = Signal(str)  # Status message
    install_completed = Signal(bool, str)  # Success, message
    installation_progress = Signal(int, str)  # Progress percentage, phase
    
    def __init__(self, package_path: Path, install_options: Dict[str, Any]):
        super().__init__()
        self.package_path = package_path
        self.install_options = install_options
    
    def _on_progress(self, progress: int, phase: str):
        """Progress callback from installer"""
        self.installation_progress.emit(progress, phase)
    
    def run(self):
        """Execute installation in background thread"""
        try:
            from ota.core.installer import InstallationManager
            
            # Create installation manager with progress callback
            installer = InstallationManager(progress_callback=self._on_progress)
            
            # Update status
            if self.install_options.get('create_backup', False):
                self.status_updated.emit(_tr.tr("creating_backup"))
            
            self.status_updated.emit(_tr.tr("installing_update"))
            
            # Execute installation
            success = installer.install_package(self.package_path, self.install_options)
            
            if success:
                self.install_completed.emit(True, _tr.tr("installer_launched_status"))
            else:
                self.install_completed.emit(False, _tr.tr("failed_to_launch_installer"))
                
        except Exception as e:
            logger.error(f"Install worker error: {e}")
            self.install_completed.emit(False, f"{_tr.tr('installation_failed')}: {str(e)}")



class DownloadWorker(QThread):
    """Download worker thread"""
    
    # Signal definitions
    progress_updated = Signal(int, str, str)  # progress, speed, remaining time
    download_completed = Signal(bool, str)    # success/failure, message
    status_updated = Signal(str)              # status update
    
    def __init__(self, ota_updater, update_info):
        super().__init__()
        self.ota_updater = ota_updater
        self.update_info = update_info
        self.is_cancelled = False
        self.start_time = None
        self.last_update_time = None
        self.last_downloaded = 0
        
    def run(self):
        """Execute download"""
        try:
            self.status_updated.emit(_tr.tr("preparing_download"))
            self.start_time = time.time()
            self.last_update_time = self.start_time
            
            # Create update package
            from ota.core.package_manager import UpdatePackage, package_manager
            
            package = UpdatePackage(
                version=self.update_info.get('latest_version', '1.1.0'),
                download_url=self.update_info.get('download_url', ''),
                file_size=self.update_info.get('file_size', 0),
                signature=self.update_info.get('signature', ''),
                description=self.update_info.get('description', '')
            )
            
            self.status_updated.emit(_tr.tr("downloading"))
            
            # Start download with progress callback
            success = package_manager.download_package(
                package, 
                progress_callback=self._progress_callback
            )
            
            if success and not self.is_cancelled:
                self.status_updated.emit(_tr.tr("download_complete"))
                
                # Verify package
                verify_success = package_manager.verify_package(package)
                if verify_success:
                    self.download_completed.emit(True, _tr.tr("download_success"))
                else:
                    self.download_completed.emit(False, _tr.tr("verification_failed"))
            elif self.is_cancelled:
                self.download_completed.emit(False, _tr.tr("download_cancelled"))
            else:
                self.download_completed.emit(False, _tr.tr("download_failed"))
                
        except Exception as e:
            logger.error(f"Download worker error: {e}")
            self.download_completed.emit(False, f"{_tr.tr('download_error')}: {str(e)}")
    
    def _progress_callback(self, progress):
        """Download progress callback"""
        if self.is_cancelled:
            return
            
        current_time = time.time()
        
        # Calculate download speed
        if self.last_update_time and current_time > self.last_update_time:
            time_diff = current_time - self.last_update_time
            if time_diff >= 0.5:  # Update every 0.5 seconds
                # Estimate current downloaded bytes (simplified calculation)
                total_size = self.update_info.get('file_size', 0)
                current_downloaded = int((progress / 100) * total_size)
                
                if self.last_downloaded > 0:
                    bytes_diff = current_downloaded - self.last_downloaded
                    speed_bps = bytes_diff / time_diff
                    speed_text = self._format_speed(speed_bps)
                    
                    # Calculate remaining time
                    remaining_bytes = total_size - current_downloaded
                    if speed_bps > 0:
                        remaining_seconds = remaining_bytes / speed_bps
                        remaining_text = self._format_time(remaining_seconds)
                    else:
                        remaining_text = _tr.tr("calculating")
                else:
                    speed_text = _tr.tr("calculating")
                    remaining_text = _tr.tr("calculating")
                
                self.progress_updated.emit(progress, speed_text, remaining_text)
                self.last_update_time = current_time
                self.last_downloaded = current_downloaded
    
    def _format_speed(self, bytes_per_second):
        """Format speed display"""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.1f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    
    def _format_time(self, seconds):
        """Format time display"""
        if seconds < 60:
            return f"{int(seconds)} {_tr.tr('seconds')}"
        elif seconds < 3600:
            return f"{int(seconds // 60)} {_tr.tr('minutes')} {int(seconds % 60)} {_tr.tr('seconds')}"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours} {_tr.tr('hours')} {minutes} {_tr.tr('minutes')}"
    
    def cancel(self):
        """Cancel download"""
        self.is_cancelled = True


class InstallConfirmDialog(QDialog):
    """Install confirmation dialog - ECBot standard UI"""
    
    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setup_ui()
        
    def setup_ui(self):
        """Setup UI - Follow ECBot standard"""
        self.setWindowTitle(_tr.tr("confirm_install_title"))
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title_label = QLabel(_tr.tr("preparing_install"))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Update information group
        info_group = QGroupBox(_tr.tr("update_info"))
        info_layout = QGridLayout()
        info_layout.setSpacing(10)
        
        # Version information
        info_layout.addWidget(QLabel(f"{_tr.tr('new_version')}:"), 0, 0)
        version_label = QLabel(self.update_info.get('latest_version', 'Unknown'))
        version_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(version_label, 0, 1)
        
        # File size
        file_size = self.update_info.get('file_size', 0)
        size_text = self._format_file_size(file_size)
        info_layout.addWidget(QLabel(f"{_tr.tr('file_size')}:"), 1, 0)
        info_layout.addWidget(QLabel(size_text), 1, 1)
        
        # Release date
        release_date = self.update_info.get('release_date', 'Unknown')
        info_layout.addWidget(QLabel(f"{_tr.tr('release_date')}:"), 2, 0)
        info_layout.addWidget(QLabel(release_date), 2, 1)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # Release notes
        desc_group = QGroupBox(_tr.tr("update_notes"))
        desc_layout = QVBoxLayout()
        
        description = self.update_info.get('description', _tr.tr('no_update_notes'))
        desc_text = QTextEdit()
        # Use setHtml to properly render HTML content
        desc_text.setHtml(description)
        desc_text.setMaximumHeight(120)
        desc_text.setReadOnly(True)
        desc_layout.addWidget(desc_text)
        
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # Installation options
        options_group = QGroupBox(_tr.tr("install_options"))
        options_layout = QVBoxLayout()
        
        self.backup_checkbox = QCheckBox(_tr.tr("create_backup"))
        self.backup_checkbox.setChecked(True)
        options_layout.addWidget(self.backup_checkbox)
        
        self.auto_restart_checkbox = QCheckBox(_tr.tr("auto_restart"))
        self.auto_restart_checkbox.setChecked(True)
        options_layout.addWidget(self.auto_restart_checkbox)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # Warning message
        warning_label = QLabel(_tr.tr("install_warning"))
        warning_label.setStyleSheet("color: #FF6B35; font-weight: bold;")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)
        
        # Add flexible space
        layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton(_tr.tr("cancel"))
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        self.install_button = QPushButton(_tr.tr("install_now"))
        self.install_button.clicked.connect(self.accept)
        self.install_button.setDefault(True)
        button_layout.addWidget(self.install_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def _format_file_size(self, size_bytes):
        """Format file size"""
        if size_bytes == 0:
            return _tr.tr("unknown")
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def get_install_options(self):
        """Get installation options"""
        return {
            'create_backup': self.backup_checkbox.isChecked(),
            'auto_restart': self.auto_restart_checkbox.isChecked()
        }


class UpdateDialog(QDialog):
    """ECBot OTA Update Dialog - Standard UI Version"""
    
    def __init__(self, parent=None, ota_updater=None, show_current_download=False):
        super().__init__(parent)
        self.ota_updater = ota_updater
        self.update_info = None
        self.download_worker = None
        self.install_worker = None  # Add install worker
        self.show_current_download = show_current_download  # Flag to show ongoing download
        
        self.setup_ui()
        self.setup_connections()
        
        # 设置窗口属性 - 遵循ECBot标准
        self.setWindowTitle(_tr.tr("window_title"))
        self.setModal(False)  # Changed to non-modal to allow background operation
        self.setFixedSize(600, 600)
        
        # Connect to global download manager
        self._connect_download_manager()
        
        # If showing current download, restore download state
        if show_current_download and download_manager.is_downloading():
            self._restore_download_state()
        
    def setup_ui(self):
        """Setup user interface - ECBot standard UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title区域
        title_label = QLabel(_tr.tr("window_title"))
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # Current version information
        if self.ota_updater:
            version_label = QLabel(f"{_tr.tr('current_version')}: {self.ota_updater.app_version}")
            version_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(version_label)
        
        # Status area
        status_group = QGroupBox(_tr.tr("status"))
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel(_tr.tr("ready_to_check"))
        self.status_label.setStyleSheet("padding: 10px;")
        status_layout.addWidget(self.status_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # Progress area
        progress_group = QGroupBox(_tr.tr("download_progress"))
        progress_layout = QVBoxLayout()
        
        # Download progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        # Details layout
        details_layout = QHBoxLayout()
        
        self.speed_label = QLabel(f"{_tr.tr('speed')}: --")
        self.speed_label.setVisible(False)
        details_layout.addWidget(self.speed_label)
        
        details_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        self.remaining_label = QLabel(f"{_tr.tr('remaining_time')}: --")
        self.remaining_label.setVisible(False)
        details_layout.addWidget(self.remaining_label)
        
        progress_layout.addLayout(details_layout)
        
        # Installation progress bar (separate from download)
        self.install_progress_bar = QProgressBar()
        self.install_progress_bar.setVisible(False)
        self.install_progress_bar.setFormat("安装进度: %p%")
        progress_layout.addWidget(self.install_progress_bar)
        
        # Installation phase label
        self.install_phase_label = QLabel("")
        self.install_phase_label.setVisible(False)
        self.install_phase_label.setStyleSheet("color: #666; font-size: 11px; padding: 2px;")
        progress_layout.addWidget(self.install_phase_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # Update information area
        self.info_group = QGroupBox(_tr.tr("update_info"))
        self.info_group.setVisible(False)
        info_layout = QVBoxLayout()
        
        self.info_text = QTextEdit()
        self.info_text.setMinimumHeight(200)
        self.info_text.setMaximumHeight(300)
        self.info_text.setReadOnly(True)
        info_layout.addWidget(self.info_text)
        
        self.info_group.setLayout(info_layout)
        layout.addWidget(self.info_group)
        
        # Add small fixed space
        layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Fixed))
        
        # Button area - minimal layout (only control buttons)
        button_layout = QHBoxLayout()
        
        # Only show cancel button during download
        self.cancel_button = QPushButton(_tr.tr("cancel"))
        self.cancel_button.setVisible(False)
        
        # Close button - smart behavior (hide when downloading, close otherwise)
        self.close_button = QPushButton(_tr.tr("close"))
        
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def setup_connections(self):
        """Setup signal connections"""
        self.cancel_button.clicked.connect(self.cancel_download)
        self.close_button.clicked.connect(self.handle_close_button)
    
    def check_for_updates(self):
        """Check for updates"""
        logger.info("[UpdateDialog] Check for updates button clicked")
        
        if not self.ota_updater:
            error_msg = "Updater not initialized"
            self.status_label.setText(error_msg)
            logger.error(f"[UpdateDialog] {error_msg}")
            return
        
        logger.info(f"[UpdateDialog] OTA Updater: {self.ota_updater}")
        self.status_label.setText(_tr.tr("checking_updates"))
        
        try:
            logger.info("[UpdateDialog] Calling check_for_updates...")
            has_update, info = self.ota_updater.check_for_updates(silent=True, return_info=True)
            logger.info(f"[UpdateDialog] Result: has_update={has_update}, info={info}")
            
            if has_update:
                self.status_label.setText(_tr.tr("update_available"))
                self.update_info = info
                
                if isinstance(info, dict):
                    version = info.get('latest_version', 'Unknown')
                    description = info.get('description', _tr.tr('no_update_notes'))
                    # Use setHtml to properly render HTML content
                    html_content = f"<p><b>{_tr.tr('latest_version')}: {version}</b></p>{description}"
                    self.info_text.setHtml(html_content)
                else:
                    self.info_text.setText(str(info))
                
                self.info_group.setVisible(True)
            else:
                self.status_label.setText(_tr.tr("no_updates"))
                
        except Exception as e:
            self.status_label.setText(f"{_tr.tr('check_failed')}: {str(e)}")
            logger.error(f"Update check failed: {e}")
    
    def download_update(self):
        """Download update - called automatically"""
        if not self.update_info:
            return
        
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.speed_label.setVisible(True)
        self.remaining_label.setVisible(True)
        
        # 创建下载工作线程
        self.download_worker = DownloadWorker(self.ota_updater, self.update_info)
        self.download_worker.progress_updated.connect(self.update_progress)
        self.download_worker.download_completed.connect(self.download_finished)
        self.download_worker.status_updated.connect(self.update_status)
        
        # Register with global download manager
        version = self.update_info.get('latest_version', '1.1.0')
        download_manager.start_download(version, self.update_info, self.download_worker)
        
        self.download_worker.start()
    
    def update_progress(self, progress, speed, remaining):
        """Update download progress"""
        self.progress_bar.setValue(progress)
        self.speed_label.setText(f"{_tr.tr('speed')}: {speed}")
        self.remaining_label.setText(f"{_tr.tr('remaining_time')}: {remaining}")
        
        # Update global download manager (only if this is from download worker, not from global manager)
        if not hasattr(self, '_updating_from_global'):
            download_manager.update_progress(progress, speed, remaining)
    
    def update_status(self, status):
        """Update status"""
        self.status_label.setText(status)
    
    def download_finished(self, success, message):
        """Download finished"""
        self.download_worker = None
        self.cancel_button.setVisible(False)
        
        # Update global download manager
        download_manager.complete_download(success, message)
        
        if success:
            # ✅ Update progress to 100%
            self.progress_bar.setValue(100)
            self.speed_label.setText(_tr.tr("speed") + ": -")
            self.remaining_label.setText(_tr.tr("remaining_time") + ": -")
            
            self.status_label.setText(message)
            
            # Auto-start installation after download completes
            logger.info("[UpdateDialog] Download complete, auto-starting installation...")
            from PySide6.QtCore import QTimer
            QTimer.singleShot(1000, self.install_update)  # Wait 1 second then install
        else:
            self.status_label.setText(message)
            
            # Hide progress related controls
            self.progress_bar.setVisible(False)
            self.speed_label.setVisible(False)
            self.remaining_label.setVisible(False)
    
    def _show_download_complete_dialog(self):
        """Show beautiful download complete dialog with app icon"""
        try:
            from PySide6.QtGui import QPixmap, QIcon
            from PySide6.QtCore import Qt
            
            # Create custom dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(_tr.tr("download_complete"))
            dialog.setModal(True)
            dialog.setFixedSize(450, 300)
            
            # Main layout
            layout = QVBoxLayout()
            layout.setSpacing(20)
            layout.setContentsMargins(30, 30, 30, 30)
            
            # App icon
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            
            # Try to load app icon
            icon_paths = [
                "resource/images/icons/app_icon.png",
                "resource/images/logos/logo.png",
                "eCan.icns",
                "eCan.ico"
            ]
            
            icon_loaded = False
            for icon_path in icon_paths:
                if os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        # Scale to 80x80
                        scaled_pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        icon_label.setPixmap(scaled_pixmap)
                        icon_loaded = True
                        break
            
            if not icon_loaded:
                # Use default icon from QMessageBox
                icon_label.setPixmap(QMessageBox.standardIcon(QMessageBox.Icon.Information).pixmap(80, 80))
            
            layout.addWidget(icon_label)
            
            # Success title
            title_label = QLabel("✅ " + _tr.tr("download_complete"))
            title_font = QFont()
            title_font.setPointSize(18)
            title_font.setBold(True)
            title_label.setFont(title_font)
            title_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_label)
            
            # Message
            message_label = QLabel(_tr.tr('download_success') + "\n\n" + _tr.tr('install_update'))
            message_label.setAlignment(Qt.AlignCenter)
            message_label.setWordWrap(True)
            message_font = QFont()
            message_font.setPointSize(12)
            message_label.setFont(message_font)
            layout.addWidget(message_label)
            
            # Spacer
            layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
            
            # OK button - changed to "Install Now"
            ok_button = QPushButton(_tr.tr("install_now") if hasattr(_tr, 'tr') else "Install Now")
            ok_button.setFixedHeight(40)
            ok_button.setStyleSheet("""
                QPushButton {
                    background-color: #007AFF;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0051D5;
                }
                QPushButton:pressed {
                    background-color: #004DB8;
                }
            """)
            ok_button.clicked.connect(dialog.accept)
            layout.addWidget(ok_button)
            
            dialog.setLayout(layout)
            
            # Set dialog style
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #2C2C2E;
                    color: white;
                }
                QLabel {
                    color: white;
                }
            """)
            
            # Show dialog and auto-install if user clicks OK
            if dialog.exec() == QDialog.Accepted:
                # User clicked "Install Now" - start installation
                logger.info("[UpdateDialog] User confirmed installation, starting auto-install")
                # Use QTimer to start installation after dialog closes
                from PySide6.QtCore import QTimer
                QTimer.singleShot(100, self.install_update)
            
        except Exception as e:
            logger.error(f"Error showing download complete dialog: {e}")
            # Fallback to simple message box
            QMessageBox.information(
                self, 
                _tr.tr("download_complete"), 
                f"{_tr.tr('download_success')}\n{_tr.tr('install_update')}"
            )
    
    def cancel_download(self):
        """Cancel download"""
        if self.download_worker:
            self.download_worker.cancel()
            self.download_worker.wait()  # Wait for thread to finish
            self.download_worker = None
        
        # Update global download manager
        download_manager.cancel_download()
        
        self.status_label.setText(_tr.tr("download_cancelled"))
        self.cancel_button.setVisible(False)
        
        # Hide progress related controls
        self.progress_bar.setVisible(False)
        self.speed_label.setVisible(False)
        self.remaining_label.setVisible(False)
    
    def install_update(self):
        """Install update - called automatically after download"""
        if not self.update_info:
            return
        
        # Check if already installing
        if self.install_worker and self.install_worker.isRunning():
            logger.warning("Installation already in progress")
            return
        
        # Get downloaded package path
        from ota.core.package_manager import package_manager
        
        if not package_manager.current_package or not package_manager.current_package.download_path:
            self.status_label.setText(_tr.tr("package_not_found"))
            QMessageBox.warning(self, _tr.tr("installation_failed"), _tr.tr("package_not_found_message"))
            return
        
        package_path = package_manager.current_package.download_path
        
        # ✅ OTA update installation options - silent mode
        install_opts = {
            'create_backup': True,      # Always create backup for safety
            'silent': True,              # Silent installation (no installer UI)
            'auto_restart': False        # Don't auto-restart (let installer handle it)
        }
        
        logger.info(f"[UpdateDialog] Starting OTA silent installation: {package_path}")
        logger.info(f"[UpdateDialog] Installation options: {install_opts}")
        
        self.status_label.setText(_tr.tr("preparing_install"))
        
        # Create and start install worker thread
        self.install_worker = InstallWorker(package_path, install_opts)
        self.install_worker.status_updated.connect(self.install_status_updated)
        self.install_worker.install_completed.connect(self.install_finished)
        self.install_worker.installation_progress.connect(self.installation_progress_updated)
        self.install_worker.start()
        
        logger.info("[UpdateDialog] Installation started in background thread (auto-install, no confirmation)")
    
    def install_status_updated(self, status: str):
        """Installation status updated"""
        self.status_label.setText(status)
    
    def installation_progress_updated(self, progress: int, phase: str):
        """Installation progress updated - show progress bar and phase"""
        # Show installation progress bar
        if not self.install_progress_bar.isVisible():
            self.install_progress_bar.setVisible(True)
            self.install_phase_label.setVisible(True)
            logger.info("[UpdateDialog] Installation progress bar shown")
        
        # Update progress
        self.install_progress_bar.setValue(progress)
        
        # Update phase text
        if phase:
            self.install_phase_label.setText(f"📦 {phase}")
        
        logger.debug(f"[UpdateDialog] Installation progress: {progress}% - {phase}")
    
    def install_finished(self, success: bool, message: str):
        """Installation finished"""
        self.install_worker = None
        
        if success:
            # ✅ Update status but don't show dialog
            # The system installer will show its own window
            self.status_label.setText(_tr.tr("installer_launched_status"))
            
            # ✅ Hide the update dialog since installation is in progress
            logger.info("[UpdateDialog] Installation launched successfully, hiding update dialog")
            self.hide()
        else:
            self.status_label.setText(_tr.tr("installation_failed_status"))
            QMessageBox.warning(self, _tr.tr("installation_failed"), message)
    
    def _show_installation_launched_dialog(self):
        """Show beautiful installation launched dialog"""
        try:
            from PySide6.QtGui import QPixmap
            from PySide6.QtCore import Qt
            
            # Create custom dialog
            dialog = QDialog(self)
            dialog.setWindowTitle(_tr.tr("installer_launched"))
            dialog.setModal(True)
            dialog.setFixedSize(500, 350)
            
            # Main layout
            layout = QVBoxLayout()
            layout.setSpacing(20)
            layout.setContentsMargins(30, 30, 30, 30)
            
            # App icon
            icon_label = QLabel()
            icon_label.setAlignment(Qt.AlignCenter)
            
            # Try to load app icon
            icon_paths = [
                "resource/images/icons/app_icon.png",
                "resource/images/logos/logo.png",
                "eCan.icns",
                "eCan.ico"
            ]
            
            icon_loaded = False
            for icon_path in icon_paths:
                if os.path.exists(icon_path):
                    pixmap = QPixmap(icon_path)
                    if not pixmap.isNull():
                        scaled_pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        icon_label.setPixmap(scaled_pixmap)
                        icon_loaded = True
                        break
            
            if not icon_loaded:
                icon_label.setPixmap(QMessageBox.standardIcon(QMessageBox.Icon.Information).pixmap(80, 80))
            
            layout.addWidget(icon_label)
            
            # Title
            title_label = QLabel(_tr.tr("installer_launched_title"))
            title_font = QFont()
            title_font.setPointSize(18)
            title_font.setBold(True)
            title_label.setFont(title_font)
            title_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(title_label)
            
            # Message
            message_label = QLabel(_tr.tr("installer_launched_message"))
            message_label.setAlignment(Qt.AlignCenter)
            message_label.setWordWrap(True)
            message_font = QFont()
            message_font.setPointSize(12)
            message_label.setFont(message_font)
            layout.addWidget(message_label)
            
            # Spacer
            layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
            
            # OK button
            ok_button = QPushButton(_tr.tr("ok"))
            ok_button.setFixedHeight(40)
            ok_button.setStyleSheet("""
                QPushButton {
                    background-color: #007AFF;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    font-size: 14px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0051D5;
                }
                QPushButton:pressed {
                    background-color: #004DB8;
                }
            """)
            ok_button.clicked.connect(dialog.accept)
            layout.addWidget(ok_button)
            
            dialog.setLayout(layout)
            
            # Set dialog style
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #2C2C2E;
                    color: white;
                }
                QLabel {
                    color: white;
                }
            """)
            
            dialog.exec()
            
        except Exception as e:
            logger.error(f"Error showing installation launched dialog: {e}")
            # Fallback to simple message box
            QMessageBox.information(
                self,
                "Installer Launched",
                "The installer has been launched.\n\nPlease follow the on-screen instructions to complete the installation."
            )
    
    def handle_close_button(self):
        """Handle close button - hide if downloading, close otherwise"""
        if self.download_worker and self.download_worker.isRunning():
            # Downloading - hide to background
            logger.info("[UpdateDialog] Hiding to background, download continues")
            self.hide()
        else:
            # Not downloading - close dialog
            self.close()
    
    def _connect_download_manager(self):
        """Connect to global download manager signals"""
        download_manager.progress_updated.connect(self._on_global_progress_update)
        download_manager.download_completed.connect(self._on_global_download_complete)
    
    def _on_global_progress_update(self, progress, speed, remaining):
        """Handle global progress update"""
        if self.isVisible():
            # Set flag to prevent recursion
            self._updating_from_global = True
            self.progress_bar.setValue(progress)
            self.speed_label.setText(f"{_tr.tr('speed')}: {speed}")
            self.remaining_label.setText(f"{_tr.tr('remaining_time')}: {remaining}")
            self._updating_from_global = False
    
    def _on_global_download_complete(self, success, message):
        """Handle global download complete"""
        if self.isVisible() and success:
            self._show_download_complete_dialog()
    
    def _restore_download_state(self):
        """Restore download state from global manager"""
        self.update_info = download_manager.update_info
        self.progress_bar.setVisible(True)
        self.speed_label.setVisible(True)
        self.remaining_label.setVisible(True)
        self.cancel_button.setVisible(True)
        
        self.progress_bar.setValue(download_manager.progress)
        self.speed_label.setText(f"Speed: {download_manager.speed}")
        self.remaining_label.setText(f"Remaining: {download_manager.remaining_time}")
        self.status_label.setText("Downloading...")
    
    def closeEvent(self, event):
        """Close event - hide if downloading, close otherwise"""
        if self.download_worker and self.download_worker.isRunning():
            # Downloading - hide to background
            logger.info("[UpdateDialog] Hiding to background, download continues")
            self.hide()
            event.ignore()
        else:
            event.accept()


# Simple notification dialog
class UpdateNotificationDialog(QDialog):
    """Simple update notification dialog"""
    
    def __init__(self, update_info="New version available", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Notification")
        self.setModal(True)
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Information
        info_label = QLabel(update_info)
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        later_button = QPushButton("Later")
        later_button.clicked.connect(self.reject)
        button_layout.addWidget(later_button)
        
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        install_button = QPushButton("Update Now")
        install_button.clicked.connect(self.accept)
        install_button.setDefault(True)
        button_layout.addWidget(install_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
