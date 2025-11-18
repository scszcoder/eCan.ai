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
from urllib.parse import quote
import traceback
from utils.logger_helper import logger_helper as logger
from utils.logger_helper import get_traceback
from app_context import AppContext


class MenuMessages:
    """Internationalization messages for menu"""
    
    MESSAGES = {
        'en-US': {
            # Menus
            'menu_help': 'Help',
            'menu_ecan': 'eCan',
            
            # App Menu
            'about_ecan': 'About eCan',
            'check_updates': 'Check for Updates...',
            'preferences': 'Preferences...',
            'services': 'Services',
            'hide_ecan': 'Hide eCan',
            'hide_others': 'Hide Others',
            'show_all': 'Show All',
            'quit_ecan': 'Quit eCan',
            
            # Help Menu
            'ecan_help': 'eCan Help',
            'quick_start': 'Quick Start Guide',
            'keyboard_shortcuts': 'Keyboard Shortcuts',
            'view_logs': 'View Logs...',
            'test': 'Test',
            
            # About Dialog
            'about_title': 'About eCan',
            'about_text': '<h2>eCan</h2><p>Version: {version}</p><p>An intelligent automation platform for e-commerce operations.</p><p>© 2024 eCan Team</p>',
            
            # Settings Dialog
            'settings_title': 'eCan Settings',
            'app_settings': 'Application Settings',
            'ota_update_settings': 'OTA Update Settings',
            'update_server': 'Update Server:',
            'remote_server': 'Remote Server (GitHub)',
            'local_server': 'Local Test Server',
            'local_server_url': 'Local Server URL:',
            'start_local_server': 'Start Local Test Server',
            'general_settings': 'General Settings',
            'auto_save_projects': 'Auto-save projects',
            'dark_mode': 'Dark mode',
            'ok': 'OK',
            'cancel': 'Cancel',
            'apply': 'Apply',
            'settings_saved': 'OTA settings saved successfully!',
            'settings_error': 'Failed to save settings: {error}',
            
            # Server Dialog
            'server_starting': 'Server Starting',
            'server_starting_message': 'Local OTA test server is starting in a new window.\nServer will be available at: {url}\n\nCheck the terminal window for server status.',
            'server_error': 'Failed to start server: {error}',
            'error_title': 'Error',
            'settings_open_error': 'Failed to open settings',
            'update_error': 'Failed to open update dialog: {error}',
            
            # User Manual
            'user_manual_title': 'eCan User Manual',
            'user_manual_text': '''
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
            ''',
            'user_manual_error': 'Failed to open user manual',
            
            # Quick Start
            'quick_start_title': 'Quick Start Guide',
            'quick_start_text': '''
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
            ''',
            'quick_start_error': 'Failed to open quick start guide',
            
            # Keyboard Shortcuts
            'shortcuts_title': 'Keyboard Shortcuts',
            'shortcuts_app_control': 'Application Control',
            'shortcuts_open_prefs': 'Open Preferences',
            'shortcuts_hide_app': 'Hide Application',
            'shortcuts_quit_app': 'Quit Application',
            'shortcuts_open_help': 'Open Help Documentation',
            'shortcuts_system': 'System Utilities',
            'shortcuts_view_logs': 'View System Logs',
            'shortcuts_navigation': 'Navigation',
            'shortcuts_nav_chat': 'Navigate to Chat',
            'shortcuts_nav_agents': 'Navigate to Agents',
            'shortcuts_nav_skills': 'Navigate to Skills',
            'shortcuts_nav_schedule': 'Navigate to Schedule',
            'shortcuts_note': '<i>Note: Additional context-specific shortcuts are available within each module.</i>',
            'shortcuts_error': 'Failed to open shortcuts',
        },
        'zh-CN': {
            # 菜单
            'menu_help': '帮助',
            'menu_ecan': 'eCan',
            
            # 应用菜单
            'about_ecan': '关于 eCan',
            'check_updates': '检查更新...',
            'preferences': '偏好设置...',
            'services': '服务',
            'hide_ecan': '隐藏 eCan',
            'hide_others': '隐藏其他',
            'show_all': '全部显示',
            'quit_ecan': '退出 eCan',
            
            # 帮助菜单
            'ecan_help': 'eCan 帮助',
            'quick_start': '快速入门指南',
            'keyboard_shortcuts': '键盘快捷键',
            'view_logs': '查看日志...',
            'test': '测试',
            
            # 关于对话框
            'about_title': '关于 eCan',
            'about_text': '<h2>eCan</h2><p>版本: {version}</p><p>智能电商运营自动化平台。</p><p>© 2024 eCan 团队</p>',
            
            # 设置对话框
            'settings_title': 'eCan 设置',
            'app_settings': '应用程序设置',
            'ota_update_settings': 'OTA 更新设置',
            'update_server': '更新服务器:',
            'remote_server': '远程服务器 (GitHub)',
            'local_server': '本地测试服务器',
            'local_server_url': '本地服务器 URL:',
            'start_local_server': '启动本地测试服务器',
            'general_settings': '通用设置',
            'auto_save_projects': '自动保存项目',
            'dark_mode': '深色模式',
            'ok': '确定',
            'cancel': '取消',
            'apply': '应用',
            'settings_saved': 'OTA 设置保存成功！',
            'settings_error': '保存设置失败: {error}',
            
            # 服务器对话框
            'server_starting': '服务器启动中',
            'server_starting_message': '本地 OTA 测试服务器正在新窗口中启动。\n服务器地址: {url}\n\n请查看终端窗口了解服务器状态。',
            'server_error': '启动服务器失败: {error}',
            'error_title': '错误',
            'settings_open_error': '打开设置失败',
            'update_error': '打开更新对话框失败: {error}',
            
            # 用户手册
            'user_manual_title': 'eCan 用户手册',
            'user_manual_text': '''
            <h2>eCan 用户手册</h2>
            <h3>概述</h3>
            <p>eCan 是企业级智能自动化平台，通过先进的 AI 代理和工作流自动化来简化电子商务运营。</p>
            
            <h3>核心功能</h3>
            <ul>
                <li><b>代理管理：</b>部署和编排 AI 代理以执行自动化任务</li>
                <li><b>技能开发：</b>使用可视化工作流编辑器创建和自定义自动化技能</li>
                <li><b>组织架构：</b>管理层级团队和代理分配</li>
                <li><b>任务调度：</b>配置具有灵活时间和执行参数的自动化工作流</li>
                <li><b>实时监控：</b>跟踪代理性能和任务执行状态</li>
            </ul>
            
            <h3>获取帮助</h3>
            <ul>
                <li>随时按 <b>F1</b> 访问此帮助文档</li>
                <li>查看<b>快速入门指南</b>以获取分步说明</li>
                <li>查看<b>键盘快捷键</b>以获取生产力提示</li>
                <li>访问<b>查看日志</b>进行系统诊断和故障排除</li>
            </ul>
            ''',
            'user_manual_error': '打开用户手册失败',
            
            # 快速入门
            'quick_start_title': '快速入门指南',
            'quick_start_text': '''
            <h2>快速入门指南</h2>
            
            <h3>步骤 1: 配置您的组织</h3>
            <p>导航到<b>代理</b>页面设置您的组织架构。
            创建部门并将代理分配到适当的团队以实现最佳工作流管理。</p>
            
            <h3>步骤 2: 部署 AI 代理</h3>
            <p>访问<b>代理</b>部分以部署和配置 AI 代理。
            根据您的运营要求为每个代理分配特定的角色、功能和权限。</p>
            
            <h3>步骤 3: 创建自动化技能</h3>
            <p>使用<b>技能</b>编辑器设计自定义自动化工作流。
            利用基于可视化节点的界面创建、测试和部署自动化技能。</p>
            
            <h3>步骤 4: 调度任务</h3>
            <p>在<b>调度</b>部分配置任务调度。
            设置具有灵活时间和执行参数的周期性自动化任务。</p>
            
            <h3>步骤 5: 监控和优化</h3>
            <p>使用<b>聊天</b>界面与代理互动并监控任务执行。
            查看性能指标并优化工作流以提高效率。</p>
            ''',
            'quick_start_error': '打开快速入门指南失败',
            
            # 键盘快捷键
            'shortcuts_title': '键盘快捷键',
            'shortcuts_app_control': '应用程序控制',
            'shortcuts_open_prefs': '打开偏好设置',
            'shortcuts_hide_app': '隐藏应用程序',
            'shortcuts_quit_app': '退出应用程序',
            'shortcuts_open_help': '打开帮助文档',
            'shortcuts_system': '系统工具',
            'shortcuts_view_logs': '查看系统日志',
            'shortcuts_navigation': '导航',
            'shortcuts_nav_chat': '导航到聊天',
            'shortcuts_nav_agents': '导航到代理',
            'shortcuts_nav_skills': '导航到技能',
            'shortcuts_nav_schedule': '导航到调度',
            'shortcuts_note': '<i>注意: 每个模块内都有额外的上下文相关快捷键。</i>',
            'shortcuts_error': '打开快捷键失败',
        }
    }
    
    DEFAULT_LANG = 'zh-CN'
    
    def __init__(self):
        from utils.i18n_helper import detect_language
        self.current_lang = detect_language(
            default_lang=self.DEFAULT_LANG,
            supported_languages=list(self.MESSAGES.keys())
        )
        logger.info(f"[MenuManager] Language: {self.current_lang}")
    
    def get(self, key, **kwargs):
        """Get message by key with optional formatting."""
        messages = self.MESSAGES.get(self.current_lang, self.MESSAGES[self.DEFAULT_LANG])
        message = messages.get(key, key)
        if kwargs:
            try:
                return message.format(**kwargs)
            except Exception:
                return message
        return message


# Global message instance - lazy initialization
_menu_messages = None

def _get_menu_messages():
    """Get MenuMessages instance with lazy initialization."""
    global _menu_messages
    if _menu_messages is None:
        _menu_messages = MenuMessages()
    return _menu_messages

class MenuManager:
    """Menu Manager Class"""
    
    def __init__(self, main_window):
        """
        Initialize menu manager
        
        Args:
            main_window: Main window instance
        """
        self.main_window = main_window
        self.check_update_action = None  # Store reference to update menu item
        self.has_update = False  # Track if update is available
        self.update_version = None  # Store available version
        self.app_menu = None  # Store reference to app menu (for macOS)
        self.help_menu = None  # Store reference to help menu (for Windows/Linux)
        self.update_notice_action = None  # Store reference to update notice item (macOS only)
    
    def set_update_available(self, has_update: bool, version: str = None):
        """Set update available status and update menu text with prominent visual indicators
        
        Args:
            has_update: Whether update is available
            version: Version string if available
        """
        self.has_update = has_update
        self.update_version = version
        
        # Update menu item text
        if self.check_update_action:
            if has_update:
                # Add prominent visual indicators for update availability
                base_text = _get_menu_messages().get('check_updates')
                
                # Use a small, elegant indicator
                # • (U+2022 BULLET) is small and elegant, used by macOS Mail and Messages
                indicator = "● "  # U+25CF Medium Black Circle - smaller than 🔴
                
                if version:
                    # Show version with indicator
                    if _get_menu_messages().current_lang == 'zh-CN':
                        text = f"{indicator}{base_text} (v{version} 可用)"
                    else:
                        text = f"{indicator}{base_text} (v{version} available)"
                else:
                    # Just indicate update available
                    if _get_menu_messages().current_lang == 'zh-CN':
                        text = f"{indicator}{base_text} (有新版本)"
                    else:
                        text = f"{indicator}{base_text} (update available)"
                
                self.check_update_action.setText(text)
                
                # Add update icon to make it more prominent
                try:
                    from PySide6.QtGui import QIcon, QFont
                    from PySide6.QtWidgets import QStyle
                    
                    # Use system icon for download/update
                    # On macOS, use a download arrow icon
                    style = self.main_window.style()
                    if style:
                        # Try to use a download or sync icon
                        icon = style.standardIcon(QStyle.StandardPixmap.SP_ArrowDown)
                        if icon and not icon.isNull():
                            self.check_update_action.setIcon(icon)
                            logger.info("[OTA] Update icon set successfully")
                except Exception as e:
                    logger.warning(f"[OTA] Failed to set update icon: {e}")
                
                # Make the menu item more prominent with font styling
                # Use bold font like macOS system apps do for important items
                try:
                    from PySide6.QtGui import QFont
                    font = self.check_update_action.font()
                    font.setBold(True)
                    self.check_update_action.setFont(font)
                except Exception as e:
                    logger.warning(f"[OTA] Failed to set bold font: {e}")
                
                logger.info(f"[OTA] Menu updated with indicator: {text}")
            else:
                # Reset to original text and font
                self.check_update_action.setText(_get_menu_messages().get('check_updates'))
                
                # Remove icon
                try:
                    from PySide6.QtGui import QIcon
                    self.check_update_action.setIcon(QIcon())  # Empty icon
                except Exception as e:
                    logger.warning(f"[OTA] Failed to remove icon: {e}")
                
                # Reset font
                try:
                    from PySide6.QtGui import QFont
                    font = self.check_update_action.font()
                    font.setBold(False)
                    self.check_update_action.setFont(font)
                except Exception as e:
                    logger.warning(f"[OTA] Failed to reset font: {e}")
        
        # Update menu title to make it more prominent
        self._update_menu_title(has_update)
        
        # For macOS: Add/remove update notice at top of menu
        self._update_menu_notice(has_update, version)
    
    def _update_menu_notice(self, has_update: bool, version: str = None):
        """Add/remove update notice at top of menu (macOS only)
        
        Args:
            has_update: Whether update is available
            version: Version string if available
        """
        try:
            # Only for macOS where menu title can't be changed
            if sys.platform != 'darwin' or not self.app_menu:
                return
            
            if has_update and version:
                # Add or update notice at top of menu
                if self.update_notice_action is None:
                    # Create new notice action
                    from PySide6.QtGui import QAction, QFont
                    
                    # Use smaller indicator for elegance
                    indicator = "● "  # U+25CF Medium Black Circle
                    
                    if _get_menu_messages().current_lang == 'zh-CN':
                        notice_text = f"{indicator}新版本 v{version} 可用"
                    else:
                        notice_text = f"{indicator}New Version v{version} Available"
                    
                    self.update_notice_action = QAction(notice_text, self.main_window)
                    self.update_notice_action.setEnabled(False)  # Make it non-clickable (just a notice)
                    
                    # Make it bold and prominent
                    font = self.update_notice_action.font()
                    font.setBold(True)
                    font.setPointSize(font.pointSize() + 1)  # Slightly larger
                    self.update_notice_action.setFont(font)
                    
                    # Insert at the top of the menu (position 0)
                    actions = self.app_menu.actions()
                    if actions:
                        self.app_menu.insertAction(actions[0], self.update_notice_action)
                        self.app_menu.insertSeparator(actions[0])  # Add separator after notice
                    else:
                        self.app_menu.addAction(self.update_notice_action)
                        self.app_menu.addSeparator()
                    
                    logger.info(f"[OTA] Added update notice to menu: {notice_text}")
                else:
                    # Update existing notice
                    indicator = "● "  # U+25CF Medium Black Circle
                    
                    if _get_menu_messages().current_lang == 'zh-CN':
                        notice_text = f"{indicator}新版本 v{version} 可用"
                    else:
                        notice_text = f"{indicator}New Version v{version} Available"
                    self.update_notice_action.setText(notice_text)
                    logger.info(f"[OTA] Updated menu notice: {notice_text}")
            else:
                # Remove notice if it exists
                if self.update_notice_action is not None:
                    self.app_menu.removeAction(self.update_notice_action)
                    self.update_notice_action = None
                    logger.info("[OTA] Removed update notice from menu")
        except Exception as e:
            logger.warning(f"[OTA] Failed to update menu notice: {e}")
            import traceback
            logger.debug(traceback.format_exc())
    
    def _update_menu_title(self, has_update: bool):
        """Update menu title to show update indicator
        
        Args:
            has_update: Whether update is available
        """
        try:
            # For macOS: Try to update app menu title
            # Note: macOS usually manages this, but we can try to set it
            if sys.platform == 'darwin' and self.app_menu:
                indicator = "● "  # U+25CF Medium Black Circle
                if has_update:
                    # Try to set app menu title with indicator
                    app_text = _get_menu_messages().get('menu_ecan')
                    self.app_menu.setTitle(f"{indicator}{app_text}")
                    logger.info(f"[OTA] macOS app menu title set to: {indicator}{app_text}")
                else:
                    self.app_menu.setTitle(_get_menu_messages().get('menu_ecan'))
                    logger.info("[OTA] macOS app menu title restored to normal")
            
            # For Windows/Linux: Update Help menu title with small indicator
            elif self.help_menu and sys.platform != 'darwin':
                # Use the same small indicator for consistency
                indicator = "● "  # U+25CF Medium Black Circle
                if has_update:
                    help_text = _get_menu_messages().get('menu_help')
                    self.help_menu.setTitle(f"{indicator}{help_text}")
                    logger.info(f"[OTA] Help menu title updated: {indicator}{help_text}")
                else:
                    self.help_menu.setTitle(_get_menu_messages().get('menu_help'))
                    logger.info("[OTA] Help menu title restored to normal")
            
            logger.debug(f"[OTA] Menu title update completed: has_update={has_update}")
        except Exception as e:
            logger.warning(f"[OTA] Failed to update menu title: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
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
            app_menu = custom_menubar.addMenu(_get_menu_messages().get('menu_ecan'))
            logger.debug("Added 'eCan' menu to custom menubar")
            self._setup_app_menu(app_menu)

            help_menu = custom_menubar.addMenu(_get_menu_messages().get('menu_help'))
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

            # CRITICAL: On macOS, we must add actions BEFORE the menu is shown
            # The application menu (first menu) is special and managed by macOS
            # We need to add our custom items to it explicitly
            
            # Create application menu (empty string makes it the app menu)
            self.app_menu = menubar.addMenu('')
            
            # Add About action at the very top
            about_action = QAction(_get_menu_messages().get('about_ecan'), self.main_window)
            about_action.triggered.connect(self.show_about_dialog)
            about_action.setMenuRole(QAction.MenuRole.AboutRole)  # Tell macOS this is About
            self.app_menu.addAction(about_action)
            
            self.app_menu.addSeparator()
            
            # Add Check for Updates action
            self.check_update_action = QAction(_get_menu_messages().get('check_updates'), self.main_window)
            self.check_update_action.triggered.connect(lambda: self.show_update_dialog(manual=True))
            self.check_update_action.setMenuRole(QAction.MenuRole.ApplicationSpecificRole)  # Custom action
            self.app_menu.addAction(self.check_update_action)
            
            # Add a separator before Check for Updates to make it more prominent
            # This will be removed later, just marking the position
            self.update_separator = None
            
            self.app_menu.addSeparator()
            
            # Add Preferences action
            preferences_action = QAction(_get_menu_messages().get('preferences'), self.main_window)
            preferences_action.setShortcut('Cmd+,')
            preferences_action.triggered.connect(self.show_settings)
            preferences_action.setMenuRole(QAction.MenuRole.PreferencesRole)  # Tell macOS this is Preferences
            self.app_menu.addAction(preferences_action)
            
            # Note: macOS will automatically add Services, Hide, Show All, Quit
            # We don't need to add them manually
            
            logger.info("macOS application menu setup complete with custom actions")

        except Exception as e:
            logger.error(f"macOS menu setup failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return

        # Add Help menu
        self.help_menu = menubar.addMenu(_get_menu_messages().get('menu_help'))
        self._setup_help_menu(self.help_menu)

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
        app_menu = menubar.addMenu(_get_menu_messages().get('menu_ecan'))
        self._setup_app_menu(app_menu)

        # Only keep Help menu
        self.help_menu = menubar.addMenu(_get_menu_messages().get('menu_help'))
        self._setup_help_menu(self.help_menu)
    
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
        app_menu = menubar.addMenu(_get_menu_messages().get('menu_ecan'))
        self._setup_app_menu(app_menu)

        self.help_menu = menubar.addMenu(_get_menu_messages().get('menu_help'))
        self._setup_help_menu(self.help_menu)

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
        about_action = QAction(_get_menu_messages().get('about_ecan'), self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        app_menu.addSeparator()
        
        # Preferences/Settings
        preferences_action = QAction(_get_menu_messages().get('preferences'), self.main_window)
        preferences_action.setShortcut('Ctrl+,')
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # Services menu (macOS standard)
        services_menu = app_menu.addMenu(_get_menu_messages().get('services'))
        # Services menu is usually managed by system, just placeholder here
        
        app_menu.addSeparator()
        
        # Hide eCan
        hide_action = QAction(_get_menu_messages().get('hide_ecan'), self.main_window)
        hide_action.setShortcut('Ctrl+H')
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # Hide others
        hide_others_action = QAction(_get_menu_messages().get('hide_others'), self.main_window)
        hide_others_action.setShortcut('Ctrl+Alt+H')
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # Show all
        show_all_action = QAction(_get_menu_messages().get('show_all'), self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # Quit eCan
        quit_action = QAction(_get_menu_messages().get('quit_ecan'), self.main_window)
        quit_action.setShortcut('Ctrl+Q')
        quit_action.triggered.connect(self.main_window.close)
        app_menu.addAction(quit_action)
    

    
    def _setup_help_menu(self, help_menu):
        """Set up Help menu"""
        try:
            # Check for updates (for Windows/Linux only)
            if sys.platform != 'darwin':
                self.check_update_action = QAction(_get_menu_messages().get('check_updates'), self.main_window)
                self.check_update_action.triggered.connect(lambda: self.show_update_dialog(manual=True))
                help_menu.addAction(self.check_update_action)

                about_action = QAction(_get_menu_messages().get('about_ecan'), self.main_window)
                about_action.triggered.connect(self.show_about_dialog)
                help_menu.addAction(about_action)

                help_menu.addSeparator()

            # User manual
            user_manual_action = QAction(_get_menu_messages().get('ecan_help'), self.main_window)
            user_manual_action.setShortcut('F1')
            user_manual_action.triggered.connect(self.show_user_manual)
            help_menu.addAction(user_manual_action)
            logger.debug("Added 'eCan Help' menu item")
            
            # Quick start guide
            quick_start_action = QAction(_get_menu_messages().get('quick_start'), self.main_window)
            quick_start_action.triggered.connect(self.show_quick_start)
            help_menu.addAction(quick_start_action)
            logger.debug("Added 'Quick Start Guide' menu item")
            
            # Keyboard shortcuts
            shortcuts_action = QAction(_get_menu_messages().get('keyboard_shortcuts'), self.main_window)
            shortcuts_action.triggered.connect(self.show_shortcuts)
            help_menu.addAction(shortcuts_action)
            logger.debug("Added 'Keyboard Shortcuts' menu item")

            help_menu.addSeparator()

            # Log Viewer - use platform-specific shortcut
            log_viewer_action = QAction(_get_menu_messages().get('view_logs'), self.main_window)
            # Only set shortcut on macOS to avoid conflicts on Windows
            if sys.platform == 'darwin':
                log_viewer_action.setShortcut('Cmd+Shift+L')
            # On Windows, avoid Ctrl+Shift+L as it may conflict with system shortcuts
            log_viewer_action.triggered.connect(self.show_log_viewer)
            help_menu.addAction(log_viewer_action)
            logger.debug("Added 'View Logs' menu item")

            # Test (for eCan.ai app) - simple harness entry below 'View Logs'
            test_action = QAction(_get_menu_messages().get('test'), self.main_window)
            test_action.triggered.connect(self.quick_test)
            help_menu.addAction(test_action)
            logger.debug("Added 'Test' menu item under Help")
            
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
        about_action = QAction(_get_menu_messages().get('about_ecan'), self.main_window)
        about_action.triggered.connect(self.show_about_dialog)
        app_menu.addAction(about_action)
        
        app_menu.addSeparator()
        
        # Check for updates (OTA functionality) - macOS only
        self.check_update_action = QAction(_get_menu_messages().get('check_updates'), self.main_window)
        self.check_update_action.triggered.connect(lambda: self.show_update_dialog(manual=True))
        app_menu.addAction(self.check_update_action)
        
        app_menu.addSeparator()
        
        # Preferences/Settings
        preferences_action = QAction(_get_menu_messages().get('preferences'), self.main_window)
        preferences_action.setShortcut('Cmd+,')  # macOS uses Cmd instead of Ctrl
        preferences_action.triggered.connect(self.show_settings)
        app_menu.addAction(preferences_action)
        
        app_menu.addSeparator()
        
        # Services menu (macOS standard)
        services_menu = app_menu.addMenu(_get_menu_messages().get('services'))
        # Services menu is usually managed by system, just placeholder here
        
        app_menu.addSeparator()
        
        # Hide eCan
        hide_action = QAction(_get_menu_messages().get('hide_ecan'), self.main_window)
        hide_action.setShortcut('Cmd+H')  # macOS uses Cmd
        hide_action.triggered.connect(self.hide_app)
        app_menu.addAction(hide_action)
        
        # Hide others
        hide_others_action = QAction(_get_menu_messages().get('hide_others'), self.main_window)
        hide_others_action.setShortcut('Cmd+Alt+H')  # macOS uses Cmd
        hide_others_action.triggered.connect(self.hide_others)
        app_menu.addAction(hide_others_action)
        
        # Show all
        show_all_action = QAction(_get_menu_messages().get('show_all'), self.main_window)
        show_all_action.triggered.connect(self.show_all)
        app_menu.addAction(show_all_action)
        
        app_menu.addSeparator()
        
        # Quit eCan
        quit_action = QAction(_get_menu_messages().get('quit_ecan'), self.main_window)
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
            
            about_text = _get_menu_messages().get('about_text', version=version)
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle(_get_menu_messages().get('about_title'))
            msg.setText(about_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
        except Exception as e:
            logger.error(f"Failed to show about dialog: {e}")
    
    def show_update_dialog(self, manual=False):
        """Show update dialog
        
        Args:
            manual: True if triggered by user manually, False if auto-check
        """
        try:
            # Import and initialize OTA components on demand
            from ota.core.updater import OTAUpdater
            
            # Prefer reusing global OTA updater instance from AppContext
            ota_updater = None
            try:
                ctx = AppContext.get_instance()
                ota_updater = getattr(ctx, "ota_updater", None)
                if ota_updater is not None:
                    logger.info("[OTA] Reusing global ota_updater for update dialog")
            except Exception:
                logger.debug("[OTA] Failed to get ota_updater from AppContext", exc_info=True)

            # Fallback: create OTA updater instance (only when needed)
            if ota_updater is None:
                logger.info("[OTA] Creating new OTAUpdater instance for update dialog")
                ota_updater = OTAUpdater()

            # Manual check: Always check for updates and show result
            if manual:
                logger.info("[OTA] Manual update check initiated")
                
                # Temporarily disable callback to avoid duplicate dialogs
                original_callback = ota_updater.update_callback
                ota_updater.update_callback = None
                
                try:
                    # Perform update check
                    has_update, update_info = ota_updater.check_for_updates(return_info=True)
                    
                    if has_update and update_info:
                        version = update_info.get('latest_version') or update_info.get('version')
                        logger.info(f"[OTA] Manual check found update: {version}")
                        
                        # For manual check, show confirmation dialog (ignore "don't remind" setting)
                        try:
                            web_gui = getattr(ctx, "web_gui", None) if 'ctx' in locals() else None
                            if web_gui and hasattr(web_gui, '_show_update_confirmation'):
                                web_gui._show_update_confirmation(version, update_info, is_manual=True)
                            else:
                                # Fallback: show update dialog directly
                                from ota.gui.dialog import UpdateDialog
                                dialog = UpdateDialog(parent=self.main_window, ota_updater=ota_updater)
                                dialog.exec()
                        except Exception as e:
                            logger.error(f"[OTA] Failed to show update confirmation: {e}")
                    else:
                        # No update available
                        QMessageBox.information(
                            self.main_window,
                            _get_menu_messages().get('check_updates'),
                            "您已经在使用最新版本。" if _get_menu_messages().current_lang == 'zh-CN' 
                            else "You are already running the latest version."
                        )
                finally:
                    # Restore original callback
                    ota_updater.update_callback = original_callback
        except Exception as e:
            logger.error(f"Failed to show update dialog: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'),
                              _get_menu_messages().get('update_error', error=str(e)))

    def show_settings(self):
        """Show settings dialog"""
        try:
            settings_dialog = QDialog(self.main_window)
            settings_dialog.setWindowTitle(_get_menu_messages().get('settings_title'))
            settings_dialog.setModal(True)
            settings_dialog.setFixedSize(600, 500)
            
            layout = QVBoxLayout()
            
            # Settings label
            title_label = QLabel(_get_menu_messages().get('app_settings'))
            title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
            layout.addWidget(title_label)
            
            # OTA Update Settings Group
            ota_group = QGroupBox(_get_menu_messages().get('ota_update_settings'))
            ota_layout = QVBoxLayout()
            
            # Server selection
            server_layout = QHBoxLayout()
            server_label = QLabel(_get_menu_messages().get('update_server'))
            server_layout.addWidget(server_label)
            
            # Radio buttons for server selection
            self.remote_server_radio = QRadioButton(_get_menu_messages().get('remote_server'))
            self.local_server_radio = QRadioButton(_get_menu_messages().get('local_server'))
            
            # Load current configuration
            try:
                from ota.config.loader import ota_config
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
            local_url_label = QLabel(_get_menu_messages().get('local_server_url'))

            # Get default URL from config
            try:
                from ota.config.loader import ota_config
                default_url = ota_config.config.get("local_server_url", "http://127.0.0.1:8080")
            except:
                default_url = "http://127.0.0.1:8080"
            
            self.local_url_input = QLineEdit(default_url)
            local_url_layout.addWidget(local_url_label)
            local_url_layout.addWidget(self.local_url_input)
            ota_layout.addLayout(local_url_layout)
            
            # Start local server button
            start_server_button = QPushButton(_get_menu_messages().get('start_local_server'))
            start_server_button.clicked.connect(self.start_local_ota_server)
            ota_layout.addWidget(start_server_button)
            
            ota_group.setLayout(ota_layout)
            layout.addWidget(ota_group)
            
            # Other settings
            other_group = QGroupBox(_get_menu_messages().get('general_settings'))
            other_layout = QVBoxLayout()
            
            auto_save_checkbox = QCheckBox(_get_menu_messages().get('auto_save_projects'))
            auto_save_checkbox.setChecked(True)
            other_layout.addWidget(auto_save_checkbox)
            
            dark_mode_checkbox = QCheckBox(_get_menu_messages().get('dark_mode'))
            other_layout.addWidget(dark_mode_checkbox)
            
            other_group.setLayout(other_layout)
            layout.addWidget(other_group)
            
            # Buttons
            button_layout = QHBoxLayout()
            ok_button = QPushButton(_get_menu_messages().get('ok'))
            cancel_button = QPushButton(_get_menu_messages().get('cancel'))
            apply_button = QPushButton(_get_menu_messages().get('apply'))
            
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
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('settings_open_error'))
    
    def save_ota_settings(self, dialog=None):
        """Save OTA settings"""
        try:
            from ota.config.loader import ota_config

            # Save server selection
            use_local = self.local_server_radio.isChecked()
            ota_config.set_use_local_server(use_local)

            # Save local server URL
            local_url = self.local_url_input.text().strip()
            if local_url:
                ota_config.set_local_server_url(local_url)
            
            logger.info(f"OTA settings saved: use_local={use_local}, local_url={local_url}")
            QMessageBox.information(self.main_window, _get_menu_messages().get('settings_title'), 
                                  _get_menu_messages().get('settings_saved'))
            
            if dialog:
                dialog.accept()
                
        except Exception as e:
            logger.error(f"Failed to save OTA settings: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('settings_error', error=str(e)))
    
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
                QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                                  f"Local server script not found: {start_script}")
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
                from ota.config.loader import ota_config
                server_url = ota_config.config.get("local_server_url", "http://127.0.0.1:8080")
            except:
                server_url = "http://127.0.0.1:8080"
            
            QMessageBox.information(
                self.main_window, 
                _get_menu_messages().get('server_starting'), 
                _get_menu_messages().get('server_starting_message', url=server_url)
            )
            
        except Exception as e:
            logger.error(f"Failed to start local OTA server: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('server_error', error=str(e)))
    
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
            manual_text = _get_menu_messages().get('user_manual_text')
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle(_get_menu_messages().get('user_manual_title'))
            msg.setText(manual_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show user manual: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('user_manual_error'))
    
    def show_quick_start(self):
        """Show quick start guide"""
        try:
            quick_start_text = _get_menu_messages().get('quick_start_text')
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle(_get_menu_messages().get('quick_start_title'))
            msg.setText(quick_start_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show quick start guide: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('quick_start_error'))

    def show_test_item(self):
        """Handler for Help > Test: simple test dialog"""
        try:
            logger.info("[Menu] Help > Test clicked")
            QMessageBox.information(
                self.main_window,
                "Test",
                "This is a test action from Help > Test."
            )
        except Exception as e:
            logger.error(f"Failed to execute Help > Test: {e}")
            QMessageBox.warning(self.main_window, "Error", f"Failed to run test action: {e}")

    def quick_test(self):
        """Handler for Help > Test: simple test dialog"""
        try:
            # Lazy imports to avoid heavy deps
            from PySide6.QtWidgets import QInputDialog
            from agent.ec_skills.story.scene_utils import update_scene

            # Ask for agent id (prefilled)
            # agent_id, ok = QInputDialog.getText(self.main_window, "Update Scene Test", "Agent ID:", text="a1")
            # if not ok or not agent_id.strip():
            #     return
            # agent_id = agent_id.strip()
            agent_id = "6d5ea546c995bbdf679ca88dbe83371c"

            # Demo scenes (use natural media length; no duration field)
            # Use public asset path served by gui_v2
            abs_path = r"C:\Users\songc\PycharmProjects\eCan.ai\resource\avatars\system\agent3_celebrate0.webm"
            clip_url = f"http://localhost:4668/api/avatar?path={quote(abs_path)}"

            demo_scenes = [
                {
                    "label": "celebrate",
                    "clip": clip_url,
                    "n_repeat": 1,
                    "priority": 5,
                    "captions": ["Local celebrate clip"]
                }
            ]

            sent = update_scene(agent_id=agent_id, scenes=demo_scenes, play_label="celebrate")
            if sent:
                print(f"update_scene sent for agent '{agent_id}'.")
            else:
                print(f"Failed to send update_scene for agent '{agent_id}'. See logs.")

        except Exception as e:
            logger.error(f"ErrorQuickTest: {e}")
            logger.error(traceback.format_exc())


    def show_shortcuts(self):
        """Show keyboard shortcuts"""
        try:
            # Determine platform-specific modifier key
            if sys.platform == 'darwin':
                modifier = 'Cmd'
            else:
                modifier = 'Ctrl'
            
            shortcuts_text = f"""
            <h2>{_get_menu_messages().get('shortcuts_title')}</h2>
            
            <h3>{_get_menu_messages().get('shortcuts_app_control')}</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+,</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_open_prefs')}</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+H</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_hide_app')}</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+Q</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_quit_app')}</td></tr>
                <tr><td style="padding: 4px;"><b>F1</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_open_help')}</td></tr>
            </table>
            
            <h3>{_get_menu_messages().get('shortcuts_system')}</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+Shift+L</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_view_logs')}</td></tr>
            </table>
            
            <h3>{_get_menu_messages().get('shortcuts_navigation')}</h3>
            <table style="width: 100%; border-collapse: collapse;">
                <tr><td style="padding: 4px;"><b>{modifier}+1</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_nav_chat')}</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+2</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_nav_agents')}</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+3</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_nav_skills')}</td></tr>
                <tr><td style="padding: 4px;"><b>{modifier}+4</b></td><td style="padding: 4px;">{_get_menu_messages().get('shortcuts_nav_schedule')}</td></tr>
            </table>
            
            <p style="margin-top: 16px; color: #666; font-size: 12px;">
            {_get_menu_messages().get('shortcuts_note')}
            </p>
            """
            
            msg = QMessageBox(self.main_window)
            msg.setWindowTitle(_get_menu_messages().get('shortcuts_title'))
            msg.setText(shortcuts_text)
            msg.setTextFormat(Qt.RichText)
            self._apply_messagebox_style(msg)
            msg.exec()
            
        except Exception as e:
            logger.error(f"Failed to show shortcuts: {e}")
            QMessageBox.warning(self.main_window, _get_menu_messages().get('error_title'), 
                              _get_menu_messages().get('shortcuts_error'))
    
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
            from PySide6.QtCore import Qt

            # Check if log viewer is already open
            if hasattr(self, 'log_viewer_window') and self.log_viewer_window and not self.log_viewer_window.isHidden():
                # Bring existing window to front
                self.log_viewer_window.raise_()
                self.log_viewer_window.activateWindow()
                logger.info("Brought existing log viewer window to front")
            else:
                # Create new log viewer window WITHOUT parent to avoid staying on top of main window
                self.log_viewer_window = LogViewer(None)
                # Ensure it's a normal top-level, non-modal window
                self.log_viewer_window.setWindowModality(Qt.NonModal)
                self.log_viewer_window.setWindowFlag(Qt.Window, True)
                self.log_viewer_window.setWindowFlag(Qt.WindowStaysOnTopHint, False)
                self.log_viewer_window.show()
                logger.info("Opened new log viewer window")

        except Exception as e:
            logger.error(f"Failed to show log viewer: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self.main_window, "Error", f"Failed to open log viewer:\n{str(e)}")



