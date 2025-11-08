#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ECBot OTA更新对话框 - 标准UI版本
遵循ECBot的标准UI设计规范
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


class DownloadWorker(QThread):
    """下载工作线程"""
    
    # 信号定义
    progress_updated = Signal(int, str, str)  # 进度, 速度, 剩余时间
    download_completed = Signal(bool, str)    # 成功/失败, 消息
    status_updated = Signal(str)              # 状态更新
    
    def __init__(self, ota_updater, update_info):
        super().__init__()
        self.ota_updater = ota_updater
        self.update_info = update_info
        self.is_cancelled = False
        self.start_time = None
        self.last_update_time = None
        self.last_downloaded = 0
        
    def run(self):
        """执行下载"""
        try:
            self.status_updated.emit("准备下载...")
            self.start_time = time.time()
            self.last_update_time = self.start_time
            
            # 创建更新包
            from ota.core.package_manager import UpdatePackage, package_manager
            
            package = UpdatePackage(
                version=self.update_info.get('latest_version', '1.1.0'),
                download_url=self.update_info.get('download_url', ''),
                file_size=self.update_info.get('file_size', 0),
                signature=self.update_info.get('signature', ''),
                description=self.update_info.get('description', '')
            )
            
            self.status_updated.emit("正在下载更新...")
            
            # 开始下载，传入进度回调
            success = package_manager.download_package(
                package, 
                progress_callback=self._progress_callback
            )
            
            if success and not self.is_cancelled:
                self.status_updated.emit("下载完成，正在验证...")
                
                # 验证包
                verify_success = package_manager.verify_package(package)
                if verify_success:
                    self.download_completed.emit(True, "下载并验证成功！")
                else:
                    self.download_completed.emit(False, "文件验证失败！")
            elif self.is_cancelled:
                self.download_completed.emit(False, "下载已取消")
            else:
                self.download_completed.emit(False, "下载失败")
                
        except Exception as e:
            logger.error(f"Download worker error: {e}")
            self.download_completed.emit(False, f"下载错误: {str(e)}")
    
    def _progress_callback(self, progress):
        """下载进度回调"""
        if self.is_cancelled:
            return
            
        current_time = time.time()
        
        # 计算下载速度
        if self.last_update_time and current_time > self.last_update_time:
            time_diff = current_time - self.last_update_time
            if time_diff >= 0.5:  # 每0.5秒更新一次
                # 估算当前下载的字节数（简化计算）
                total_size = self.update_info.get('file_size', 0)
                current_downloaded = int((progress / 100) * total_size)
                
                if self.last_downloaded > 0:
                    bytes_diff = current_downloaded - self.last_downloaded
                    speed_bps = bytes_diff / time_diff
                    speed_text = self._format_speed(speed_bps)
                    
                    # 计算剩余时间
                    remaining_bytes = total_size - current_downloaded
                    if speed_bps > 0:
                        remaining_seconds = remaining_bytes / speed_bps
                        remaining_text = self._format_time(remaining_seconds)
                    else:
                        remaining_text = "计算中..."
                else:
                    speed_text = "计算中..."
                    remaining_text = "计算中..."
                
                self.progress_updated.emit(progress, speed_text, remaining_text)
                self.last_update_time = current_time
                self.last_downloaded = current_downloaded
    
    def _format_speed(self, bytes_per_second):
        """格式化速度显示"""
        if bytes_per_second < 1024:
            return f"{bytes_per_second:.1f} B/s"
        elif bytes_per_second < 1024 * 1024:
            return f"{bytes_per_second / 1024:.1f} KB/s"
        else:
            return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    
    def _format_time(self, seconds):
        """格式化时间显示"""
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            return f"{int(seconds // 60)}分{int(seconds % 60)}秒"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}时{minutes}分"
    
    def cancel(self):
        """取消下载"""
        self.is_cancelled = True


class InstallConfirmDialog(QDialog):
    """安装确认对话框 - ECBot标准UI"""
    
    def __init__(self, update_info, parent=None):
        super().__init__(parent)
        self.update_info = update_info
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI - 遵循ECBot标准"""
        self.setWindowTitle("确认安装更新")
        self.setModal(True)
        self.setFixedSize(500, 400)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("准备安装更新")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 更新信息组
        info_group = QGroupBox("更新信息")
        info_layout = QGridLayout()
        info_layout.setSpacing(10)
        
        # 版本信息
        info_layout.addWidget(QLabel("新版本:"), 0, 0)
        version_label = QLabel(self.update_info.get('latest_version', 'Unknown'))
        version_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(version_label, 0, 1)
        
        # 文件大小
        file_size = self.update_info.get('file_size', 0)
        size_text = self._format_file_size(file_size)
        info_layout.addWidget(QLabel("文件大小:"), 1, 0)
        info_layout.addWidget(QLabel(size_text), 1, 1)
        
        # 发布日期
        release_date = self.update_info.get('release_date', 'Unknown')
        info_layout.addWidget(QLabel("发布日期:"), 2, 0)
        info_layout.addWidget(QLabel(release_date), 2, 1)
        
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)
        
        # 更新说明
        desc_group = QGroupBox("更新说明")
        desc_layout = QVBoxLayout()
        
        description = self.update_info.get('description', '无更新说明')
        desc_text = QTextEdit()
        desc_text.setPlainText(description)
        desc_text.setMaximumHeight(120)
        desc_text.setReadOnly(True)
        desc_layout.addWidget(desc_text)
        
        desc_group.setLayout(desc_layout)
        layout.addWidget(desc_group)
        
        # 安装选项
        options_group = QGroupBox("安装选项")
        options_layout = QVBoxLayout()
        
        self.backup_checkbox = QCheckBox("安装前创建备份")
        self.backup_checkbox.setChecked(True)
        options_layout.addWidget(self.backup_checkbox)
        
        self.auto_restart_checkbox = QCheckBox("安装完成后自动重启应用")
        self.auto_restart_checkbox.setChecked(True)
        options_layout.addWidget(self.auto_restart_checkbox)
        
        options_group.setLayout(options_layout)
        layout.addWidget(options_group)
        
        # 警告信息
        warning_label = QLabel("⚠️ 安装过程中请不要关闭应用程序")
        warning_label.setStyleSheet("color: #FF6B35; font-weight: bold;")
        warning_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(warning_label)
        
        # 添加弹性空间
        layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        self.install_button = QPushButton("立即安装")
        self.install_button.clicked.connect(self.accept)
        self.install_button.setDefault(True)
        button_layout.addWidget(self.install_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def _format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes == 0:
            return "未知"
        elif size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
    
    def get_install_options(self):
        """获取安装选项"""
        return {
            'create_backup': self.backup_checkbox.isChecked(),
            'auto_restart': self.auto_restart_checkbox.isChecked()
        }


class UpdateDialog(QDialog):
    """ECBot OTA更新对话框 - 标准UI版本"""
    
    def __init__(self, parent=None, ota_updater=None):
        super().__init__(parent)
        self.ota_updater = ota_updater
        self.update_info = None
        self.download_worker = None
        
        self.setup_ui()
        self.setup_connections()
        
        # 设置窗口属性 - 遵循ECBot标准
        self.setWindowTitle("ECBot 软件更新")
        self.setModal(True)
        self.setFixedSize(600, 450)
        
    def setup_ui(self):
        """设置用户界面 - ECBot标准UI"""
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题区域
        title_label = QLabel("ECBot 软件更新")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)
        
        # 当前版本信息
        if self.ota_updater:
            version_label = QLabel(f"当前版本: {self.ota_updater.app_version}")
            version_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(version_label)
        
        # 状态区域
        status_group = QGroupBox("状态")
        status_layout = QVBoxLayout()
        
        self.status_label = QLabel("准备检查更新...")
        self.status_label.setStyleSheet("padding: 10px;")
        status_layout.addWidget(self.status_label)
        
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)
        
        # 进度区域
        progress_group = QGroupBox("下载进度")
        progress_layout = QVBoxLayout()
        
        # 主进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)
        
        # 详细信息布局
        details_layout = QHBoxLayout()
        
        self.speed_label = QLabel("速度: --")
        self.speed_label.setVisible(False)
        details_layout.addWidget(self.speed_label)
        
        details_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        self.remaining_label = QLabel("剩余时间: --")
        self.remaining_label.setVisible(False)
        details_layout.addWidget(self.remaining_label)
        
        progress_layout.addLayout(details_layout)
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        # 更新信息区域
        self.info_group = QGroupBox("更新信息")
        self.info_group.setVisible(False)
        info_layout = QVBoxLayout()
        
        self.info_text = QTextEdit()
        self.info_text.setMaximumHeight(100)
        self.info_text.setReadOnly(True)
        info_layout.addWidget(self.info_text)
        
        self.info_group.setLayout(info_layout)
        layout.addWidget(self.info_group)
        
        # 添加弹性空间
        layout.addItem(QSpacerItem(20, 10, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.check_button = QPushButton("检查更新")
        
        self.download_button = QPushButton("下载更新")
        self.download_button.setEnabled(False)
        
        self.install_button = QPushButton("安装更新")
        self.install_button.setEnabled(False)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setVisible(False)
        
        self.close_button = QPushButton("关闭")
        
        button_layout.addWidget(self.check_button)
        button_layout.addWidget(self.download_button)
        button_layout.addWidget(self.install_button)
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    def setup_connections(self):
        """设置信号连接"""
        self.check_button.clicked.connect(self.check_for_updates)
        self.download_button.clicked.connect(self.download_update)
        self.install_button.clicked.connect(self.install_update)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.close_button.clicked.connect(self.close)
    
    def check_for_updates(self):
        """检查更新"""
        if not self.ota_updater:
            self.status_label.setText("更新器未初始化")
            return
        
        self.check_button.setEnabled(False)
        self.status_label.setText("正在检查更新...")
        
        try:
            has_update, info = self.ota_updater.check_for_updates(silent=True, return_info=True)
            
            if has_update:
                self.status_label.setText("发现新版本！")
                self.update_info = info
                
                if isinstance(info, dict):
                    version = info.get('latest_version', 'Unknown')
                    description = info.get('description', '无更新说明')
                    self.info_text.setText(f"最新版本: {version}\n\n{description}")
                else:
                    self.info_text.setText(str(info))
                
                self.info_group.setVisible(True)
                self.download_button.setEnabled(True)
            else:
                self.status_label.setText("已是最新版本")
                
        except Exception as e:
            self.status_label.setText(f"检查失败: {str(e)}")
            logger.error(f"Update check failed: {e}")
        
        finally:
            self.check_button.setEnabled(True)
    
    def download_update(self):
        """下载更新"""
        if not self.update_info:
            return
        
        self.download_button.setEnabled(False)
        self.cancel_button.setVisible(True)
        self.progress_bar.setVisible(True)
        self.speed_label.setVisible(True)
        self.remaining_label.setVisible(True)
        
        # 创建下载工作线程
        self.download_worker = DownloadWorker(self.ota_updater, self.update_info)
        self.download_worker.progress_updated.connect(self.update_progress)
        self.download_worker.download_completed.connect(self.download_finished)
        self.download_worker.status_updated.connect(self.update_status)
        
        self.download_worker.start()
    
    def update_progress(self, progress, speed, remaining):
        """更新下载进度"""
        self.progress_bar.setValue(progress)
        self.speed_label.setText(f"速度: {speed}")
        self.remaining_label.setText(f"剩余时间: {remaining}")
    
    def update_status(self, status):
        """更新状态"""
        self.status_label.setText(status)
    
    def download_finished(self, success, message):
        """下载完成"""
        self.download_worker = None
        self.cancel_button.setVisible(False)
        
        if success:
            self.status_label.setText(message)
            self.install_button.setEnabled(True)
            
            # 显示下载完成通知
            QMessageBox.information(
                self, 
                "下载完成", 
                "更新文件下载完成！\n点击'安装更新'按钮开始安装。"
            )
        else:
            self.status_label.setText(message)
            self.download_button.setEnabled(True)
            
            # 隐藏进度相关控件
            self.progress_bar.setVisible(False)
            self.speed_label.setVisible(False)
            self.remaining_label.setVisible(False)
    
    def cancel_download(self):
        """取消下载"""
        if self.download_worker:
            self.download_worker.cancel()
            self.download_worker.wait()  # 等待线程结束
            self.download_worker = None
        
        self.status_label.setText("下载已取消")
        self.download_button.setEnabled(True)
        self.cancel_button.setVisible(False)
        
        # 隐藏进度相关控件
        self.progress_bar.setVisible(False)
        self.speed_label.setVisible(False)
        self.remaining_label.setVisible(False)
    
    def install_update(self):
        """安装更新"""
        if not self.update_info:
            return
        
        # 显示安装确认对话框
        confirm_dialog = InstallConfirmDialog(self.update_info, self)
        if confirm_dialog.exec() != QDialog.Accepted:
            return
        
        install_options = confirm_dialog.get_install_options()
        
        # 开始安装
        self.install_button.setEnabled(False)
        self.status_label.setText("正在准备安装...")
        
        try:
            # 导入安装管理器
            from ota.core.installer import installation_manager
            from ota.core.package_manager import package_manager
            
            # 获取下载的包路径
            if not package_manager.current_package or not package_manager.current_package.download_path:
                self.status_label.setText("未找到下载的安装包")
                QMessageBox.warning(self, "安装失败", "未找到下载的安装包，请重新下载。")
                return
            
            package_path = package_manager.current_package.download_path
            
            # 准备安装选项
            install_opts = {
                'create_backup': install_options['create_backup'],
                'silent': True
            }
            
            if install_options['create_backup']:
                self.status_label.setText("正在创建备份...")
                QApplication.processEvents()  # 更新UI
            
            self.status_label.setText("正在安装更新...")
            QApplication.processEvents()
            
            # 执行安装
            success = installation_manager.install_package(package_path, install_opts)
            
            if success:
                self.status_label.setText("安装成功！")
                
                if install_options['auto_restart']:
                    reply = QMessageBox.question(
                        self, 
                        "安装完成", 
                        "更新安装成功！\n是否立即重启应用程序？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes
                    )
                    
                    if reply == QMessageBox.Yes:
                        self.status_label.setText("正在重启应用程序...")
                        QApplication.processEvents()
                        
                        # 延迟重启，给用户时间看到消息
                        QTimer.singleShot(2000, lambda: installation_manager.restart_application(3))
                    else:
                        QMessageBox.information(
                            self, 
                            "安装完成", 
                            "更新安装成功！\n请手动重启应用程序以使用新版本。"
                        )
                else:
                    QMessageBox.information(
                        self, 
                        "安装完成", 
                        "更新安装成功！\n请手动重启应用程序以使用新版本。"
                    )
            else:
                self.status_label.setText("安装失败")
                QMessageBox.warning(self, "安装失败", "更新安装失败，请稍后重试。")
                
        except Exception as e:
            error_msg = f"安装错误: {str(e)}"
            self.status_label.setText(error_msg)
            QMessageBox.critical(self, "安装错误", error_msg)
        finally:
            self.install_button.setEnabled(True)
    
    def closeEvent(self, event):
        """关闭事件"""
        if self.download_worker and self.download_worker.isRunning():
            reply = QMessageBox.question(
                self, 
                "确认关闭", 
                "下载正在进行中，确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            
            if reply == QMessageBox.Yes:
                self.download_worker.cancel()
                self.download_worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


# 简单的通知对话框
class UpdateNotificationDialog(QDialog):
    """简单的更新通知对话框"""
    
    def __init__(self, update_info="发现新版本", parent=None):
        super().__init__(parent)
        self.setWindowTitle("更新通知")
        self.setModal(True)
        self.setFixedSize(300, 150)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 信息
        info_label = QLabel(update_info)
        info_label.setWordWrap(True)
        info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(info_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        later_button = QPushButton("稍后")
        later_button.clicked.connect(self.reject)
        button_layout.addWidget(later_button)
        
        button_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        
        install_button = QPushButton("立即更新")
        install_button.clicked.connect(self.accept)
        install_button.setDefault(True)
        button_layout.addWidget(install_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
