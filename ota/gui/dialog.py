from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                               QPushButton, QProgressBar, QTextEdit)
from PySide6.QtCore import Qt

from utils.logger_helper import logger_helper as logger


class SimpleUpdateDialog(QDialog):
    """简化的更新对话框"""
    
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
        """简化的检查更新"""
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
        from PySide6.QtWidgets import QMessageBox
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
    
    def cancel_operation(self):
        """取消当前操作"""
        if self.checker_thread and self.checker_thread.isRunning():
            self.checker_thread.requestInterruption()
            self.checker_thread.wait(3000)  # 等待3秒
        
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.cancel()
            self.download_thread.wait(3000)  # 等待3秒
        
        self.reset_ui_state()
    
    def on_check_finished(self):
        """检查完成"""
        self.progress_bar.setVisible(False)
        self.check_button.setEnabled(True)
    
    def reset_ui_state(self):
        """重置UI状态"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.check_button.setEnabled(True)
        self.download_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.status_label.setText("准备检查更新...")
    
    def _format_file_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes == 0:
            return "未知大小"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"
    
    def closeEvent(self, event):
        """关闭事件"""
        # 优雅地停止线程
        if self.checker_thread and self.checker_thread.isRunning():
            self.checker_thread.requestInterruption()
            if not self.checker_thread.wait(3000):  # 等待3秒
                logger.warning("Checker thread did not stop gracefully, terminating...")
                self.checker_thread.terminate()
                self.checker_thread.wait()
        
        if hasattr(self, 'install_thread') and self.install_thread and self.install_thread.isRunning():
            self.install_thread.requestInterruption()
            if not self.install_thread.wait(3000):  # 等待3秒
                logger.warning("Install thread did not stop gracefully, terminating...")
                self.install_thread.terminate()
                self.install_thread.wait()
        
        event.accept()
    
    def on_update_found(self, has_update: bool, info: str):
        """更新检查结果"""
        if has_update:
            self.status_label.setText("发现新版本！")
            
            # 解析更新信息
            if isinstance(info, dict):
                self.update_info = info
                latest_version = info.get('latest_version', 'Unknown')
                description = info.get('description', '无更新说明')
                file_size = info.get('file_size', 0)
                
                self.latest_version_label.setText(f"最新版本: {latest_version}")
                
                # 格式化文件大小
                size_str = self._format_file_size(file_size)
                
                update_text = f"""<h3>版本 {latest_version}</h3>
                <p><b>文件大小:</b> {size_str}</p>
                <p><b>更新内容:</b></p>
                <p>{description}</p>"""
                
                self.info_text.setHtml(update_text)
            else:
                self.info_text.setText(str(info))
            
            self.info_text.setVisible(True)
            self.download_button.setEnabled(True)
        else:
            self.status_label.setText("已是最新版本")
            if self.ota_updater:
                self.latest_version_label.setText(f"最新版本: {self.ota_updater.app_version}")
    
    def on_download_progress(self, progress: int):
        """下载进度更新"""
        self.progress_bar.setValue(progress)
        self.status_label.setText(f"正在下载更新... {progress}%")
    
    def on_download_finished(self, success: bool):
        """下载完成"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        
        if success:
            self.status_label.setText("下载完成，可以安装更新")
            self.install_button.setEnabled(True)
        else:
            self.status_label.setText("下载失败")
            self.download_button.setEnabled(True)
    
    def on_download_error(self, error_msg: str):
        """下载错误"""
        self.progress_bar.setVisible(False)
        self.cancel_button.setVisible(False)
        self.status_label.setText(f"下载失败: {error_msg}")
        self.download_button.setEnabled(True)
        
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, "下载失败", f"更新下载失败:\n{error_msg}")
    
    def on_error_occurred(self, error_message: str):
        """处理一般错误"""
        self.status_label.setText(f"错误: {error_message}")
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        logger.error(f"Update check error: {error_message}")
    
    def on_update_error(self, error):
        """处理更新错误"""
        from ..core.errors import get_user_friendly_message, get_recovery_suggestions
        
        user_message = get_user_friendly_message(error, self.current_language)
        self.status_label.setText(f"错误: {user_message}")
        
        # 显示错误详情和恢复建议
        suggestions = get_recovery_suggestions(error)
        error_details = f"""<h3>更新检查失败</h3>
        <p><b>错误信息:</b> {user_message}</p>
        <p><b>建议解决方案:</b></p>
        <ul>"""
        
        for suggestion in suggestions:
            error_details += f"<li>{suggestion}</li>"
        
        error_details += "</ul>"
        
        self.info_text.setHtml(error_details)
        self.info_text.setVisible(True)
        
        self.check_button.setEnabled(True)
        self.progress_bar.setVisible(False)
        logger.error(f"Update error: {error}")

    def tr(self, text: str) -> str:
        """简单的翻译函数"""
        translations = {
            '软件更新': 'Software Update' if self.current_language == 'en' else '软件更新',
            '检查更新': 'Check Update' if self.current_language == 'en' else '检查更新',
            '下载更新': 'Download Update' if self.current_language == 'en' else '下载更新',
            '安装更新': 'Install Update' if self.current_language == 'en' else '安装更新',
            '取消': 'Cancel' if self.current_language == 'en' else '取消',
            '关闭': 'Close' if self.current_language == 'en' else '关闭'
        }
        return translations.get(text, text)


class UpdateNotificationDialog(QDialog):
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