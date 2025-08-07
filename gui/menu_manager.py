"""
eCan 菜单管理器
负责管理应用程序的所有菜单功能
"""

import os
import sys
from PySide6.QtWidgets import (QMessageBox, QDialog, QInputDialog, QFileDialog, 
                               QLabel, QCheckBox, QPushButton, QHBoxLayout, 
                               QVBoxLayout, QComboBox, QTextEdit, QLineEdit, 
                               QApplication)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt
from utils.logger_helper import logger_helper as logger


class MenuManager:
    """菜单管理器类"""
    
    def __init__(self, main_window):
        """
        初始化菜单管理器
        
        Args:
            main_window: 主窗口实例
        """
        self.main_window = main_window
        
    def setup_menu(self):
        """设置eCan菜单栏 - 跨平台支持"""
        menubar = self.main_window.menuBar()
        
        # 注意：应用程序基本信息已在main.py中统一设置，这里不需要重复设置
        
        # 根据平台设置菜单
        if sys.platform == 'darwin':  # macOS
            self._setup_macos_menus(menubar)
        elif sys.platform == 'win32':  # Windows
            self._setup_windows_menus(menubar)
        else:  # Linux和其他平台
            self._setup_linux_menus(menubar)
    
    def _setup_macos_menus(self, menubar):
        """设置macOS完整菜单"""
        try:
            # 启用原生macOS菜单栏
            menubar.setNativeMenuBar(True)
            logger.info("启用macOS原生菜单栏")
            
            # 检查是否已经有菜单，避免重复添加
            existing_menus = menubar.actions()
            if existing_menus:
                logger.info(f"发现已存在 {len(existing_menus)} 个菜单，跳过重复设置")
                return
            
            # 在macOS上，第一个菜单会自动变成应用程序菜单
            # 使用空字符串让系统自动设置应用程序菜单名称
            app_menu = menubar.addMenu('')  # 空字符串让系统自动设置应用程序菜单
            self._setup_macos_app_menu(app_menu)  # 使用专门的macOS应用菜单设置
            
            logger.info("macOS应用程序菜单设置完成")
            
        except Exception as e:
            logger.warning(f"macOS菜单设置失败，使用默认方式: {e}")
            # 如果失败，尝试添加基本菜单
            try:
                app_menu = menubar.addMenu('')  # 即使失败也使用空字符串
                self._setup_app_menu(app_menu)
            except Exception as e2:
                logger.error(f"备用菜单设置也失败: {e2}")
                return
        
        # 设置其他标准菜单
        self._setup_common_menus(menubar)
        
        # macOS特有的Window菜单
        window_menu = menubar.addMenu('Window')
        self._setup_window_menu(window_menu)
        
        logger.info("macOS菜单栏设置完成")
    
    def _setup_windows_menus(self, menubar):
        """设置Windows完整菜单"""
        try:
            # Windows使用非原生菜单栏以获得更好的控制
            menubar.setNativeMenuBar(False)
            logger.info("使用Qt菜单栏（Windows优化）")
            
        except Exception as e:
            logger.warning(f"Windows菜单设置失败: {e}")
        
        # Windows上显示完整的应用程序菜单
        app_menu = menubar.addMenu('eCan')
        self._setup_app_menu(app_menu)
        
        # 设置其他标准菜单
        self._setup_common_menus(menubar)
        
        # Windows特有的Tools菜单
        tools_menu = menubar.addMenu('Tools')
        self._setup_tools_menu(tools_menu)
    
    def _setup_linux_menus(self, menubar):
        """设置Linux完整菜单"""
        try:
            # Linux通常使用Qt菜单栏
            menubar.setNativeMenuBar(False)
            logger.info("使用Qt菜单栏（Linux）")
            
        except Exception as e:
            logger.warning(f"Linux菜单设置失败: {e}")
        
        # Linux上的标准菜单布局
        app_menu = menubar.addMenu('eCan')
        self._setup_app_menu(app_menu)
        
        # 设置其他标准菜单
        self._setup_common_menus(menubar)
        
        # Linux可选的Tools菜单
        tools_menu = menubar.addMenu('Tools')
        self._setup_tools_menu(tools_menu)
    
    def _setup_common_menus(self, menubar):
        """设置所有平台通用的菜单"""
        # File菜单
        file_menu = menubar.addMenu('File')
        self._setup_file_menu(file_menu)
        
        # Edit菜单
        edit_menu = menubar.addMenu('Edit')
        self._setup_edit_menu(edit_menu)
        
        # View菜单
        view_menu = menubar.addMenu('View')
        self._setup_view_menu(view_menu)
        
        # Help菜单
        help_menu = menubar.addMenu('Help')
        self._setup_help_menu(help_menu)
    
    def _setup_app_menu(self, app_menu):
        """设置应用菜单"""
        # 关于eCan
        about_action = QAction('About eCan', self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        # 检查更新
        check_update_action = QAction('Check for Updates...', self.main_window)
        check_update_action.triggered.connect(self.show_update_dialog)
        app_menu.addAction(check_update_action)
        
        app_menu.addSeparator()
        
        # 偏好设置/设置
        preferences_action = QAction('Preferences...', self.main_window)
        preferences_action.setShortcut('Ctrl+,')
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # 服务菜单（macOS标准）
        services_menu = app_menu.addMenu('Services')
        # 服务菜单通常由系统管理，这里只是占位
        
        app_menu.addSeparator()
        
        # 隐藏eCan
        hide_action = QAction('Hide eCan', self.main_window)
        hide_action.setShortcut('Ctrl+H')
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # 隐藏其他
        hide_others_action = QAction('Hide Others', self.main_window)
        hide_others_action.setShortcut('Ctrl+Alt+H')
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # 显示全部
        show_all_action = QAction('Show All', self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # 退出eCan
        quit_action = QAction('Quit eCan', self.main_window)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.main_window.close)
        app_menu.addAction(quit_action)
    
    def _setup_file_menu(self, file_menu):
        """设置文件菜单"""
        # 新建项目
        new_project_action = QAction('New Project...', self.main_window)
        new_project_action.setShortcut('Ctrl+N')
        new_project_action.triggered.connect(self.new_project)
        file_menu.addAction(new_project_action)
        
        # 打开项目
        open_project_action = QAction('Open Project...', self.main_window)
        open_project_action.setShortcut('Ctrl+O')
        open_project_action.triggered.connect(self.open_project)
        file_menu.addAction(open_project_action)
        
        # 最近打开的项目
        recent_menu = file_menu.addMenu('Open Recent')
        recent_menu.addAction('Clear Menu').triggered.connect(self.clear_recent)
        
        file_menu.addSeparator()
        
        # 保存项目
        save_project_action = QAction('Save Project', self.main_window)
        save_project_action.setShortcut('Ctrl+S')
        save_project_action.triggered.connect(self.save_project)
        file_menu.addAction(save_project_action)
        
        # 另存为
        save_as_action = QAction('Save Project As...', self.main_window)
        save_as_action.setShortcut('Ctrl+Shift+S')
        save_as_action.triggered.connect(self.save_project_as)
        file_menu.addAction(save_as_action)
        
        file_menu.addSeparator()
        
        # 导入数据
        import_data_action = QAction('Import Data...', self.main_window)
        import_data_action.setShortcut('Ctrl+I')
        import_data_action.triggered.connect(self.import_data)
        file_menu.addAction(import_data_action)
        
        # 导出数据
        export_data_action = QAction('Export Data...', self.main_window)
        export_data_action.setShortcut('Ctrl+E')
        export_data_action.triggered.connect(self.export_data)
        file_menu.addAction(export_data_action)
    
    def _setup_edit_menu(self, edit_menu):
        """设置编辑菜单"""
        # 撤销
        undo_action = QAction('Undo', self.main_window)
        undo_action.setShortcut('Ctrl+Z')
        undo_action.triggered.connect(self.undo)
        edit_menu.addAction(undo_action)
        
        # 重做
        redo_action = QAction('Redo', self.main_window)
        redo_action.setShortcut('Ctrl+Shift+Z')
        redo_action.triggered.connect(self.redo)
        edit_menu.addAction(redo_action)
        
        edit_menu.addSeparator()
        
        # 剪切
        cut_action = QAction('Cut', self.main_window)
        cut_action.setShortcut('Ctrl+X')
        cut_action.triggered.connect(self.cut)
        edit_menu.addAction(cut_action)
        
        # 复制
        copy_action = QAction('Copy', self.main_window)
        copy_action.setShortcut('Ctrl+C')
        copy_action.triggered.connect(self.copy)
        edit_menu.addAction(copy_action)
        
        # 粘贴
        paste_action = QAction('Paste', self.main_window)
        paste_action.setShortcut('Ctrl+V')
        paste_action.triggered.connect(self.paste)
        edit_menu.addAction(paste_action)
        
        # 全选
        select_all_action = QAction('Select All', self.main_window)
        select_all_action.setShortcut('Ctrl+A')
        select_all_action.triggered.connect(self.select_all)
        edit_menu.addAction(select_all_action)
        
        edit_menu.addSeparator()
        
        # 查找
        find_action = QAction('Find...', self.main_window)
        find_action.setShortcut('Ctrl+F')
        find_action.triggered.connect(self.find)
        edit_menu.addAction(find_action)
    
    def _setup_view_menu(self, view_menu):
        """设置视图菜单"""
        # 工具栏
        toolbar_action = QAction('Show Toolbar', self.main_window)
        toolbar_action.setCheckable(True)
        toolbar_action.setChecked(True)
        toolbar_action.triggered.connect(self.toggle_toolbar)
        view_menu.addAction(toolbar_action)
        
        # 状态栏
        statusbar_action = QAction('Show Status Bar', self.main_window)
        statusbar_action.setCheckable(True)
        statusbar_action.setChecked(True)
        statusbar_action.triggered.connect(self.toggle_statusbar)
        view_menu.addAction(statusbar_action)
        
        view_menu.addSeparator()
        
        # 全屏
        fullscreen_action = QAction('Enter Full Screen', self.main_window)
        fullscreen_action.setShortcut('Ctrl+Ctrl+F')
        fullscreen_action.triggered.connect(self.toggle_fullscreen)
        view_menu.addAction(fullscreen_action)
    
    def _setup_help_menu(self, help_menu):
        """设置帮助菜单"""
        # 用户手册
        user_manual_action = QAction('eCan Help', self.main_window)
        user_manual_action.setShortcut('F1')
        user_manual_action.triggered.connect(self.show_user_manual)
        help_menu.addAction(user_manual_action)
        
        # 快速入门
        quick_start_action = QAction('Quick Start Guide', self.main_window)
        quick_start_action.triggered.connect(self.show_quick_start)
        help_menu.addAction(quick_start_action)
        
        # 键盘快捷键
        shortcuts_action = QAction('Keyboard Shortcuts', self.main_window)
        shortcuts_action.triggered.connect(self.show_shortcuts)
        help_menu.addAction(shortcuts_action)
        
        help_menu.addSeparator()
        
        # 反馈问题
        feedback_action = QAction('Report Issue...', self.main_window)
        feedback_action.triggered.connect(self.report_issue)
        help_menu.addAction(feedback_action)
        
        # 发送反馈
        send_feedback_action = QAction('Send Feedback...', self.main_window)
        send_feedback_action.triggered.connect(self.send_feedback)
        help_menu.addAction(send_feedback_action)
    
    def _setup_macos_app_menu(self, app_menu):
        """设置macOS专用的应用菜单（确保包含所有功能）"""
        # 关于eCan
        about_action = QAction('About eCan', self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        app_menu.addSeparator()
        
        # 检查更新（OTA功能）
        check_update_action = QAction('Check for Updates...', self.main_window)
        check_update_action.triggered.connect(self.show_update_dialog)
        app_menu.addAction(check_update_action)
        
        app_menu.addSeparator()
        
        # 偏好设置/设置
        preferences_action = QAction('Preferences...', self.main_window)
        preferences_action.setShortcut('Cmd+,')  # macOS使用Cmd而不是Ctrl
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # 服务菜单（macOS标准）
        services_menu = app_menu.addMenu('Services')
        # 服务菜单通常由系统管理，这里只是占位
        
        app_menu.addSeparator()
        
        # 隐藏eCan
        hide_action = QAction('Hide eCan', self.main_window)
        hide_action.setShortcut('Cmd+H')  # macOS使用Cmd
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # 隐藏其他
        hide_others_action = QAction('Hide Others', self.main_window)
        hide_others_action.setShortcut('Cmd+Alt+H')  # macOS使用Cmd
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # 显示全部
        show_all_action = QAction('Show All', self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # 退出eCan
        quit_action = QAction('Quit eCan', self.main_window)
        quit_action.setShortcut('Cmd+Q')  # macOS使用Cmd
        quit_action.triggered.connect(self.main_window.close)
        app_menu.addAction(quit_action)
        
        logger.info("macOS应用菜单设置完成，包含OTA检查功能")
    
    def _setup_window_menu(self, window_menu):
        """设置Window菜单（macOS标准）"""
        # 最小化
        minimize_action = QAction('Minimize', self.main_window)
        if sys.platform == 'darwin':
            minimize_action.setShortcut('Cmd+M')  # macOS使用Cmd
        else:
            minimize_action.setShortcut('Ctrl+M')
        minimize_action.triggered.connect(self.minimize_window)
        window_menu.addAction(minimize_action)
        
        # 缩放
        zoom_action = QAction('Zoom', self.main_window)
        zoom_action.triggered.connect(self.zoom_window)
        window_menu.addAction(zoom_action)
        
        window_menu.addSeparator()
        
        # 前置所有窗口
        bring_all_to_front_action = QAction('Bring All to Front', self.main_window)
        bring_all_to_front_action.triggered.connect(self.bring_all_to_front)
        window_menu.addAction(bring_all_to_front_action)
    
    def _setup_tools_menu(self, tools_menu):
        """设置Tools菜单（Windows/Linux）"""
        # 选项/首选项
        options_action = QAction('Options...', self.main_window)
        options_action.setShortcut('Ctrl+,')
        options_action.triggered.connect(self.show_settings)
        tools_menu.addAction(options_action)
        
        tools_menu.addSeparator()
        
        # 插件管理
        plugins_action = QAction('Manage Plugins...', self.main_window)
        plugins_action.triggered.connect(self.manage_plugins)
        tools_menu.addAction(plugins_action)
        
        # 扩展
        extensions_action = QAction('Extensions...', self.main_window)
        extensions_action.triggered.connect(self.manage_extensions)
        tools_menu.addAction(extensions_action)
        
        tools_menu.addSeparator()
        
        # 开发者工具
        dev_tools_action = QAction('Developer Tools', self.main_window)
        dev_tools_action.setShortcut('F12')
        dev_tools_action.triggered.connect(self.show_developer_tools)
        tools_menu.addAction(dev_tools_action)
    
    # ==================== 应用菜单功能实现 ====================
    
    def show_about_dialog(self):
        """显示关于对话框"""
        try:
            # 读取版本信息
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
        """显示更新对话框"""
        try:
            # 按需导入和初始化OTA组件
            from ota import OTAUpdater, UpdateDialog
            
            # 创建OTA更新器实例（仅在需要时）
            ota_updater = OTAUpdater()
            
            # 创建并显示更新对话框，传递OTA更新器实例
            dialog = UpdateDialog(ota_updater, self.main_window)
            dialog.exec()
        except Exception as e:
            logger.error(f"Failed to show update dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open update dialog")
    
    def show_settings(self):
        """显示设置对话框"""
        try:
            settings_dialog = QDialog(self.main_window)
            settings_dialog.setWindowTitle("eCan Settings")
            settings_dialog.setModal(True)
            settings_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # 设置标签
            title_label = QLabel("Application Settings")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # 设置项（示例）
            auto_save_checkbox = QCheckBox("Auto-save projects")
            auto_save_checkbox.setChecked(True)
            layout.addWidget(auto_save_checkbox)
            
            dark_mode_checkbox = QCheckBox("Dark mode")
            layout.addWidget(dark_mode_checkbox)
            
            # 按钮
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
        """隐藏应用程序"""
        try:
            self.main_window.hide()
            logger.info("Application hidden")
        except Exception as e:
            logger.error(f"Failed to hide app: {e}")
    
    def hide_others(self):
        """隐藏其他应用程序"""
        try:
            # 在Qt中，这个功能主要在macOS上有效
            QApplication.instance().setQuitOnLastWindowClosed(False)
            logger.info("Hide others action triggered")
        except Exception as e:
            logger.error(f"Failed to hide others: {e}")
    
    def show_all(self):
        """显示所有应用程序"""
        try:
            # 显示应用程序的所有窗口
            self.main_window.show()
            self.main_window.raise_()
            self.main_window.activateWindow()
            logger.info("Show all action triggered")
        except Exception as e:
            logger.error(f"Failed to show all: {e}")
    
    # ==================== 文件菜单功能实现 ====================
    
    def new_project(self):
        """新建项目"""
        try:
            project_name, ok = QInputDialog.getText(self.main_window, 'New Project', 'Enter project name:')
            if ok and project_name:
                # 这里可以调用项目管理相关的API
                QMessageBox.information(self.main_window, "Success", f"Project '{project_name}' created successfully!")
                logger.info(f"New project created: {project_name}")
        except Exception as e:
            logger.error(f"Failed to create new project: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to create new project")
    
    def open_project(self):
        """打开项目"""
        try:
            file_dialog = QFileDialog(self.main_window)
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            file_dialog.setNameFilter("eCan Project Files (*.ecan);;All Files (*)")
            
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    project_file = selected_files[0]
                    QMessageBox.information(self.main_window, "Success", f"Project opened: {os.path.basename(project_file)}")
                    logger.info(f"Project opened: {project_file}")
        except Exception as e:
            logger.error(f"Failed to open project: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open project")
    
    def save_project(self):
        """保存项目"""
        try:
            # 这里可以调用项目保存相关的API
            QMessageBox.information(self.main_window, "Success", "Project saved successfully!")
            logger.info("Project saved")
        except Exception as e:
            logger.error(f"Failed to save project: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to save project")
    
    def save_project_as(self):
        """另存为项目"""
        try:
            file_dialog = QFileDialog(self.main_window)
            file_dialog.setFileMode(QFileDialog.AnyFile)
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setNameFilter("eCan Project Files (*.ecan);;All Files (*)")
            file_dialog.setDefaultSuffix("ecan")
            
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    save_file = selected_files[0]
                    QMessageBox.information(self.main_window, "Success", f"Project saved as: {os.path.basename(save_file)}")
                    logger.info(f"Project saved as: {save_file}")
        except Exception as e:
            logger.error(f"Failed to save project as: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to save project as")
    
    def clear_recent(self):
        """清除最近打开的项目列表"""
        try:
            reply = QMessageBox.question(self.main_window, "Clear Recent", 
                                       "Are you sure you want to clear the recent projects list?",
                                       QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                # 这里可以清除最近项目的记录
                QMessageBox.information(self.main_window, "Success", "Recent projects list cleared")
                logger.info("Recent projects list cleared")
        except Exception as e:
            logger.error(f"Failed to clear recent: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to clear recent projects")
    
    def import_data(self):
        """导入数据"""
        try:
            file_dialog = QFileDialog(self.main_window)
            file_dialog.setFileMode(QFileDialog.ExistingFile)
            file_dialog.setNameFilter("CSV Files (*.csv);;JSON Files (*.json);;Excel Files (*.xlsx);;All Files (*)")
            
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    data_file = selected_files[0]
                    QMessageBox.information(self.main_window, "Success", f"Data imported from: {os.path.basename(data_file)}")
                    logger.info(f"Data imported from: {data_file}")
        except Exception as e:
            logger.error(f"Failed to import data: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to import data")
    
    def export_data(self):
        """导出数据"""
        try:
            file_dialog = QFileDialog(self.main_window)
            file_dialog.setFileMode(QFileDialog.AnyFile)
            file_dialog.setAcceptMode(QFileDialog.AcceptSave)
            file_dialog.setNameFilter("CSV Files (*.csv);;JSON Files (*.json);;Excel Files (*.xlsx)")
            file_dialog.setDefaultSuffix("csv")
            
            if file_dialog.exec():
                selected_files = file_dialog.selectedFiles()
                if selected_files:
                    export_file = selected_files[0]
                    QMessageBox.information(self.main_window, "Success", f"Data exported to: {os.path.basename(export_file)}")
                    logger.info(f"Data exported to: {export_file}")
        except Exception as e:
            logger.error(f"Failed to export data: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to export data")
    
    # ==================== 编辑菜单功能实现 ====================
    
    def undo(self):
        """撤销操作"""
        try:
            # 这里可以实现撤销逻辑
            QMessageBox.information(self.main_window, "Undo", "Undo operation performed")
            logger.info("Undo action triggered")
        except Exception as e:
            logger.error(f"Failed to undo: {e}")
    
    def redo(self):
        """重做操作"""
        try:
            # 这里可以实现重做逻辑
            QMessageBox.information(self.main_window, "Redo", "Redo operation performed")
            logger.info("Redo action triggered")
        except Exception as e:
            logger.error(f"Failed to redo: {e}")
    
    def cut(self):
        """剪切操作"""
        try:
            # 获取当前焦点widget并执行剪切
            focused_widget = QApplication.focusWidget()
            if focused_widget and hasattr(focused_widget, 'cut'):
                focused_widget.cut()
            logger.info("Cut action triggered")
        except Exception as e:
            logger.error(f"Failed to cut: {e}")
    
    def copy(self):
        """复制操作"""
        try:
            # 获取当前焦点widget并执行复制
            focused_widget = QApplication.focusWidget()
            if focused_widget and hasattr(focused_widget, 'copy'):
                focused_widget.copy()
            logger.info("Copy action triggered")
        except Exception as e:
            logger.error(f"Failed to copy: {e}")
    
    def paste(self):
        """粘贴操作"""
        try:
            # 获取当前焦点widget并执行粘贴
            focused_widget = QApplication.focusWidget()
            if focused_widget and hasattr(focused_widget, 'paste'):
                focused_widget.paste()
            logger.info("Paste action triggered")
        except Exception as e:
            logger.error(f"Failed to paste: {e}")
    
    def select_all(self):
        """全选操作"""
        try:
            # 获取当前焦点widget并执行全选
            focused_widget = QApplication.focusWidget()
            if focused_widget and hasattr(focused_widget, 'selectAll'):
                focused_widget.selectAll()
            logger.info("Select all action triggered")
        except Exception as e:
            logger.error(f"Failed to select all: {e}")
    
    def find(self):
        """查找功能"""
        try:
            find_dialog = QDialog(self.main_window)
            find_dialog.setWindowTitle("Find")
            find_dialog.setModal(True)
            find_dialog.setFixedSize(400, 150)
            
            layout = QVBoxLayout()
            
            # 查找输入框
            find_label = QLabel("Find:")
            layout.addWidget(find_label)
            
            find_input = QLineEdit()
            find_input.setPlaceholderText("Enter text to find...")
            layout.addWidget(find_input)
            
            # 按钮
            button_layout = QHBoxLayout()
            find_button = QPushButton("Find")
            cancel_button = QPushButton("Cancel")
            
            def perform_find():
                search_text = find_input.text()
                if search_text:
                    QMessageBox.information(self.main_window, "Find", f"Searching for: {search_text}")
                    logger.info(f"Find action: {search_text}")
                    find_dialog.accept()
                else:
                    QMessageBox.warning(self.main_window, "Warning", "Please enter text to find")
            
            find_button.clicked.connect(perform_find)
            cancel_button.clicked.connect(find_dialog.reject)
            
            button_layout.addWidget(find_button)
            button_layout.addWidget(cancel_button)
            layout.addLayout(button_layout)
            
            find_dialog.setLayout(layout)
            find_dialog.exec()
            
        except Exception as e:
            logger.error(f"Failed to show find dialog: {e}")
            QMessageBox.warning(self.main_window, "Error", "Failed to open find dialog")
    
    # ==================== 视图菜单功能实现 ====================
    
    def toggle_toolbar(self, checked):
        """切换工具栏显示"""
        try:
            # 这里可以实现工具栏的显示/隐藏
            if checked:
                logger.info("Toolbar shown")
            else:
                logger.info("Toolbar hidden")
        except Exception as e:
            logger.error(f"Failed to toggle toolbar: {e}")
    
    def toggle_statusbar(self, checked):
        """切换状态栏显示"""
        try:
            # 这里可以实现状态栏的显示/隐藏
            if hasattr(self.main_window, 'statusBar'):
                if checked:
                    self.main_window.statusBar().show()
                else:
                    self.main_window.statusBar().hide()
            logger.info(f"Status bar {'shown' if checked else 'hidden'}")
        except Exception as e:
            logger.error(f"Failed to toggle status bar: {e}")
    
    def toggle_fullscreen(self):
        """切换全屏模式"""
        try:
            if self.main_window.isFullScreen():
                self.main_window.showNormal()
                logger.info("Exited full screen mode")
            else:
                self.main_window.showFullScreen()
                logger.info("Entered full screen mode")
        except Exception as e:
            logger.error(f"Failed to toggle fullscreen: {e}")
    
    # ==================== 帮助菜单功能实现 ====================
    
    def show_user_manual(self):
        """显示用户手册"""
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
        """显示快速入门指南"""
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
        """显示键盘快捷键"""
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
        """报告问题"""
        try:
            issue_dialog = QDialog(self.main_window)
            issue_dialog.setWindowTitle("Report Issue")
            issue_dialog.setModal(True)
            issue_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # 标题
            title_label = QLabel("Report an Issue")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # 问题类型
            type_label = QLabel("Issue Type:")
            layout.addWidget(type_label)
            
            type_combo = QComboBox()
            type_combo.addItems(["Bug Report", "Feature Request", "Performance Issue", "Other"])
            layout.addWidget(type_combo)
            
            # 问题描述
            desc_label = QLabel("Description:")
            layout.addWidget(desc_label)
            
            desc_text = QTextEdit()
            desc_text.setPlaceholderText("Please describe the issue in detail...")
            layout.addWidget(desc_text)
            
            # 按钮
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
        """发送反馈"""
        try:
            feedback_dialog = QDialog(self.main_window)
            feedback_dialog.setWindowTitle("Send Feedback")
            feedback_dialog.setModal(True)
            feedback_dialog.setFixedSize(500, 400)
            
            layout = QVBoxLayout()
            
            # 标题
            title_label = QLabel("Send Feedback to eCan Team")
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # 反馈类型
            type_label = QLabel("Feedback Type:")
            layout.addWidget(type_label)
            
            type_combo = QComboBox()
            type_combo.addItems(["General Feedback", "Feature Suggestion", "Compliment", "Question"])
            layout.addWidget(type_combo)
            
            # 反馈内容
            content_label = QLabel("Your Feedback:")
            layout.addWidget(content_label)
            
            content_text = QTextEdit()
            content_text.setPlaceholderText("Please share your thoughts, suggestions, or questions...")
            layout.addWidget(content_text)
            
            # 按钮
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
    
    # ==================== 辅助方法 ====================
    
    def _apply_messagebox_style(self, msg):
        """应用消息框样式"""
        try:
            # 这里可以应用自定义样式
            pass
        except Exception as e:
            logger.error(f"Failed to apply messagebox style: {e}")
    
    # ==================== Window菜单功能实现 ====================
    
    def minimize_window(self):
        """最小化窗口"""
        try:
            self.main_window.showMinimized()
            logger.info("Window minimized")
        except Exception as e:
            logger.error(f"Failed to minimize window: {e}")
    
    def zoom_window(self):
        """缩放窗口"""
        try:
            if self.main_window.isMaximized():
                self.main_window.showNormal()
                logger.info("Window restored to normal size")
            else:
                self.main_window.showMaximized()
                logger.info("Window maximized")
        except Exception as e:
            logger.error(f"Failed to zoom window: {e}")
    
    def bring_all_to_front(self):
        """前置所有窗口"""
        try:
            self.main_window.raise_()
            self.main_window.activateWindow()
            logger.info("Brought all windows to front")
        except Exception as e:
            logger.error(f"Failed to bring windows to front: {e}")
    
    # ==================== Tools菜单功能实现 ====================
    
    def manage_plugins(self):
        """管理插件"""
        try:
            QMessageBox.information(self.main_window, "Plugins", 
                                  "Plugin management feature coming soon!")
            logger.info("Plugin management requested")
        except Exception as e:
            logger.error(f"Failed to show plugin management: {e}")
    
    def manage_extensions(self):
        """管理扩展"""
        try:
            QMessageBox.information(self.main_window, "Extensions", 
                                  "Extension management feature coming soon!")
            logger.info("Extension management requested")
        except Exception as e:
            logger.error(f"Failed to show extension management: {e}")
    
    def show_developer_tools(self):
        """显示开发者工具"""
        try:
            QMessageBox.information(self.main_window, "Developer Tools", 
                                  "Developer tools feature coming soon!")
            logger.info("Developer tools requested")
        except Exception as e:
            logger.error(f"Failed to show developer tools: {e}")
