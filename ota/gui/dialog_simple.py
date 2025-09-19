"""
简化的OTA更新对话框
移除了过度实现的多线程、复杂样式和不必要的功能
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QProgressBar, QTextEdit, QMessageBox)
from PySide6.QtCore import Qt

from utils.logger_helper import logger_helper as logger


class SimpleUpdateDialog(QDialog):
    """简化的更新对话框 - 移除了多线程复杂性"""
    
    def __init__(self, parent=None, ota_updater=None):
        super().__init__(parent)
        self.ota_updater = ota_updater
        self.update_info = None
        
        self.setup_ui()
        self.setup_connections()
        
        # 设置窗口属性
        self.setWindowTitle("软件更新")
        self.setModal(True)
        self.resize(400, 250)
    
    def setup_ui(self):
        """设置简化的用户界面"""
        layout = QVBoxLayout()
        
        # 标题
        self.title_label = QLabel("<h3>ECBot 软件更新</h3>")
        layout.addWidget(self.title_label)
        
        # 状态标签
        self.status_label = QLabel("准备检查更新...")
        layout.addWidget(self.status_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # 更新信息
        self.info_text = QTextEdit()
        self.info_text.setVisible(False)
        self.info_text.setMaximumHeight(100)
        layout.addWidget(self.info_text)
        
        # 版本信息
        if self.ota_updater:
            version_label = QLabel(f"当前版本: {self.ota_updater.app_version}")
            layout.addWidget(version_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.check_button = QPushButton("检查更新")
        self.install_button = QPushButton("安装更新")
        self.install_button.setEnabled(False)
        self.close_button = QPushButton("关闭")
        
        button_layout.addWidget(self.check_button)
        button_layout.addWidget(self.install_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def setup_connections(self):
        """设置信号连接"""
        self.check_button.clicked.connect(self.check_for_updates)
        self.install_button.clicked.connect(self.install_update)
        self.close_button.clicked.connect(self.close)
    
    def check_for_updates(self):
        """简化的检查更新 - 直接调用，不使用线程"""
        if not self.ota_updater:
            self.status_label.setText("更新器未初始化")
            return
        
        self.check_button.setEnabled(False)
        self.status_label.setText("正在检查更新...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            # 直接调用检查，不使用线程
            has_update, info = self.ota_updater.check_for_updates(silent=True, return_info=True)
            
            if has_update:
                self.status_label.setText("发现新版本！")
                self.update_info = info
                if isinstance(info, dict):
                    version = info.get('latest_version', 'Unknown')
                    self.info_text.setText(f"最新版本: {version}")
                else:
                    self.info_text.setText(str(info))
                self.info_text.setVisible(True)
                self.install_button.setEnabled(True)
            else:
                self.status_label.setText("已是最新版本")
                
        except Exception as e:
            self.status_label.setText(f"检查失败: {str(e)}")
            logger.error(f"Update check failed: {e}")
        
        finally:
            self.progress_bar.setVisible(False)
            self.check_button.setEnabled(True)
    
    def install_update(self):
        """简化的安装更新"""
        if not self.ota_updater:
            return
        
        # 确认对话框
        reply = QMessageBox.question(
            self, 
            "确认安装", 
            "安装更新可能需要重启应用程序。是否继续？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply != QMessageBox.Yes:
            return
        
        self.install_button.setEnabled(False)
        self.status_label.setText("正在安装更新...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        
        try:
            success = self.ota_updater.install_update()
            if success:
                self.status_label.setText("更新安装成功！请重启应用程序。")
                QMessageBox.information(self, "安装成功", "更新已安装完成。")
            else:
                self.status_label.setText("更新安装失败。")
                QMessageBox.warning(self, "安装失败", "更新安装失败。")
        except Exception as e:
            error_msg = f"安装错误: {str(e)}"
            self.status_label.setText(error_msg)
            QMessageBox.critical(self, "安装错误", error_msg)
        finally:
            self.install_button.setEnabled(True)
            self.progress_bar.setVisible(False)


class SimpleUpdateNotificationDialog(QDialog):
    """简化的更新通知对话框"""
    
    def __init__(self, update_info="发现新版本", parent=None):
        super().__init__(parent)
        self.setWindowTitle("更新通知")
        self.setModal(True)
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        
        # 信息
        info_label = QLabel(update_info)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        install_button = QPushButton("立即更新")
        install_button.clicked.connect(self.accept)
        button_layout.addWidget(install_button)
        
        later_button = QPushButton("稍后")
        later_button.clicked.connect(self.reject)
        button_layout.addWidget(later_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)


# 为了向后兼容，保留原名称
UpdateDialog = SimpleUpdateDialog
UpdateNotificationDialog = SimpleUpdateNotificationDialog
