from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QProgressBar, QTextEdit, QCheckBox)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap

from utils.logger_helper import logger_helper as logger
from ..core.errors import UpdateError, get_user_friendly_message


class UpdateCheckerThread(QThread):
    """更新检查线程"""
    update_found = Signal(bool, str)
    check_finished = Signal()
    error_occurred = Signal(str)
    update_error = Signal(object)  # 传递UpdateError对象
    
    def __init__(self, ota_updater, silent=False):
        super().__init__()
        self.ota_updater = ota_updater
        self.silent = silent
    
    def run(self):
        try:
            # 检查是否被中断
            if self.isInterruptionRequested():
                return
            
            # 设置错误回调
            def error_callback(error: UpdateError):
                if not self.isInterruptionRequested():
                    self.update_error.emit(error)
            
            self.ota_updater.set_error_callback(error_callback)
            
            # 再次检查中断
            if self.isInterruptionRequested():
                return
                
            has_update = self.ota_updater.check_for_updates(self.silent)
            
            # 检查中断后再发送信号
            if not self.isInterruptionRequested():
                if has_update:
                    self.update_found.emit(True, "New update available")
                else:
                    self.update_found.emit(False, "No updates available")
                    
        except UpdateError as e:
            if not self.isInterruptionRequested():
                self.update_error.emit(e)
        except Exception as e:
            if not self.isInterruptionRequested():
                self.error_occurred.emit(str(e))
        finally:
            if not self.isInterruptionRequested():
                self.check_finished.emit()


class UpdateInstallThread(QThread):
    """更新安装线程"""
    progress_updated = Signal(int)
    install_finished = Signal(bool, str)
    
    def __init__(self, ota_updater):
        super().__init__()
        self.ota_updater = ota_updater
    
    def run(self):
        try:
            # 检查是否被中断
            if self.isInterruptionRequested():
                return
            
            # 再次检查中断
            if self.isInterruptionRequested():
                return
            
            # 设置进度回调
            def progress_callback(progress):
                if not self.isInterruptionRequested():
                    self.progress_updated.emit(progress)
            
            success = self.ota_updater.install_update()
            
            # 检查中断后再发送信号
            if not self.isInterruptionRequested():
                if success:
                    self.install_finished.emit(True, "Update installed successfully")
                else:
                    self.install_finished.emit(False, "Update installation failed")
        except Exception as e:
            if not self.isInterruptionRequested():
                self.install_finished.emit(False, f"Installation error: {str(e)}")


class UpdateDialog(QDialog):
    """更新对话框"""
    
    def __init__(self, ota_updater, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ECBot Update")
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        self.ota_updater = ota_updater
        self.checker_thread = None
        self.install_thread = None
        
        self.setup_ui()
        self.setup_connections()
        
        # 自动检查更新
        self.check_for_updates()
    
    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("ECBot Update")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; margin: 10px;")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 状态标签
        self.status_label = QLabel("Checking for updates...")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 更新信息
        self.update_info = QTextEdit()
        self.update_info.setMaximumHeight(150)
        self.update_info.setVisible(False)
        layout.addWidget(self.update_info)
        
        # 自动更新选项
        self.auto_check_checkbox = QCheckBox("Automatically check for updates")
        self.auto_check_checkbox.setChecked(True)
        layout.addWidget(self.auto_check_checkbox)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        self.check_button = QPushButton("Check for Updates")
        self.check_button.setEnabled(False)
        button_layout.addWidget(self.check_button)
        
        self.install_button = QPushButton("Install Update")
        self.install_button.setVisible(False)
        button_layout.addWidget(self.install_button)
        
        self.close_button = QPushButton("Close")
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def setup_connections(self):
        """设置信号连接"""
        self.check_button.clicked.connect(self.check_for_updates)
        self.install_button.clicked.connect(self.install_update)
        self.close_button.clicked.connect(self.accept)
        self.auto_check_checkbox.toggled.connect(self.toggle_auto_check)
    
    def check_for_updates(self):
        """检查更新"""
        self.status_label.setText("Checking for updates...")
        self.check_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度
        
        self.checker_thread = UpdateCheckerThread(self.ota_updater, silent=False)
        self.checker_thread.update_found.connect(self.on_update_found)
        self.checker_thread.check_finished.connect(self.on_check_finished)
        self.checker_thread.error_occurred.connect(self.on_error)
        self.checker_thread.update_error.connect(self.on_update_error)
        self.checker_thread.start()
    
    def on_update_found(self, has_update, message):
        """更新检查结果"""
        if has_update:
            self.status_label.setText("Update available!")
            self.update_info.setVisible(True)
            self.update_info.setPlainText(message)
            self.install_button.setVisible(True)
        else:
            self.status_label.setText("No updates available")
            self.update_info.setVisible(False)
            self.install_button.setVisible(False)
    
    def on_check_finished(self):
        """检查完成"""
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)
    
    def on_error(self, error_message):
        """错误处理"""
        self.status_label.setText(f"Error: {error_message}")
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        logger.error(f"Update check error: {error_message}")
    
    def on_update_error(self, error: UpdateError):
        """更新错误处理"""
        user_message = get_user_friendly_message(error)
        self.status_label.setText(f"Error: {user_message}")
        
        # 显示详细错误信息
        if error.details:
            details_text = f"Error Code: {error.code.value}\n"
            details_text += f"Message: {error.message}\n"
            if error.details:
                details_text += f"Details: {error.details}"
            self.update_info.setPlainText(details_text)
            self.update_info.setVisible(True)
        
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        logger.error(f"Update error: {error}")
    
    def install_update(self):
        """安装更新"""
        self.status_label.setText("Installing update...")
        self.install_button.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 100)
        
        self.install_thread = UpdateInstallThread(self.ota_updater)
        self.install_thread.progress_updated.connect(self.progress_bar.setValue)
        self.install_thread.install_finished.connect(self.on_install_finished)
        self.install_thread.start()
    
    def on_install_finished(self, success, message):
        """安装完成"""
        if success:
            self.status_label.setText("Update installed successfully. Please restart the application.")
            self.install_button.setVisible(False)
        else:
            self.status_label.setText(f"Installation failed: {message}")
            self.install_button.setEnabled(True)
        
        self.progress_bar.setVisible(False)
    
    def toggle_auto_check(self, enabled):
        """切换自动检查"""
        if enabled:
            self.ota_updater.start_auto_check()
        else:
            self.ota_updater.stop_auto_check()
    
    def closeEvent(self, event):
        """关闭事件"""
        # 优雅地停止线程
        if self.checker_thread and self.checker_thread.isRunning():
            self.checker_thread.requestInterruption()
            if not self.checker_thread.wait(3000):  # 等待3秒
                logger.warning("Checker thread did not stop gracefully, terminating...")
                self.checker_thread.terminate()
                self.checker_thread.wait()
        
        if self.install_thread and self.install_thread.isRunning():
            self.install_thread.requestInterruption()
            if not self.install_thread.wait(3000):  # 等待3秒
                logger.warning("Install thread did not stop gracefully, terminating...")
                self.install_thread.terminate()
                self.install_thread.wait()
        
        event.accept()


class UpdateNotificationDialog(QDialog):
    """更新通知对话框"""
    
    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setFixedSize(400, 300)
        
        self.setup_ui(update_info)
    
    def setup_ui(self, update_info):
        """设置UI"""
        layout = QVBoxLayout()
        
        # 标题
        title_label = QLabel("Update Available")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title_label)
        
        # 更新信息
        info_label = QLabel(update_info)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.install_button = QPushButton("Install Now")
        self.install_button.clicked.connect(self.accept)
        button_layout.addWidget(self.install_button)
        
        self.later_button = QPushButton("Later")
        self.later_button.clicked.connect(self.reject)
        button_layout.addWidget(self.later_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout) 