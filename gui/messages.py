import os
import sys
from datetime import datetime
from utils.logger_helper import logger_helper as logger
from utils.i18n_helper import detect_language

class MenuMessages:
    """Internationalization messages for menu and dialogs"""
    
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
            'view_lightrag_logs': 'View LightRAG Logs...',
            'request_log_analysis': 'Request Log Analysis...',
            'sqlite_merge': 'SQLite Merge...',
            'test': 'Test',
            
            # About Dialog
            'about_title': 'About eCan',
            'about_text': '<h2>eCan</h2><p>Version: {version}</p><p>An intelligent automation platform for e-commerce operations.</p><p>© {year} eCan.ai. All Rights Reserved.</p>',
            'version_label': 'Version {version}',
            'about_desc': 'Enterprise Intelligent E-commerce Automation Platform',
            'about_designed_by': 'Designed by eCan.ai Team',
            'about_copyright': '© {year} eCan.ai. All Rights Reserved.',
            
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
            'user_manual_page_title': 'eCan.ai User Manual',
            'user_manual_page_subtitle': 'Click the button below to open the complete online user manual in your browser<br>Get the latest usage guides and help documentation',
            'user_manual_open_button': '🚀 Open Online User Manual',
            'user_manual_feature_1': 'Real-time updated documentation',
            'user_manual_feature_2': 'Detailed feature descriptions and tutorials',
            'user_manual_feature_3': 'FAQ and troubleshooting',
            'user_manual_feature_4': 'Video tutorials and sample code',
            'close': 'Close',
            
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
            'shortcuts_view_lightrag_logs': 'View LightRAG Logs',
            'shortcuts_navigation': 'Navigation',
            'shortcuts_nav_chat': 'Navigate to Chat',
            'shortcuts_nav_agents': 'Navigate to Agents',
            'shortcuts_nav_skills': 'Navigate to Skills',
            'shortcuts_nav_schedule': 'Navigate to Schedule',
            'shortcuts_note': '<i>Note: Additional context-specific shortcuts are available within each module.</i>',
            'shortcuts_error': 'Failed to open shortcuts',
            
            # Version Check Dialog
            'check_updates_title': 'Check for Updates',
            'check_failed': 'Check Failed',
            'update_latest_title': 'You are up to date!',
            'update_available_title': 'Update Available',
            'update_latest_desc': 'eCan {version} is the latest version available.',
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
            'view_lightrag_logs': '查看 LightRAG 日志...',
            'request_log_analysis': '请求日志分析...',
            'sqlite_merge': 'SQLite 合并...',
            'test': '测试',
            
            # About Dialog
            'about_title': '关于 eCan',
            'about_text': '<h2>eCan</h2><p>版本: {version}</p><p>智能电商运营自动化平台。</p><p>© {year} eCan.ai. 保留所有权利。</p>',
            'version_label': '版本 {version}',
            'about_desc': '企业级智能电商运营自动化平台',
            'about_designed_by': 'eCan.ai 团队设计',
            'about_copyright': '© {year} eCan.ai. 保留所有权利。',
            
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
            'user_manual_page_title': 'eCan.ai 用户手册',
            'user_manual_page_subtitle': '点击下方按钮在浏览器中打开完整的在线用户手册<br>获取最新的使用指南和帮助文档',
            'user_manual_open_button': '🚀 打开在线用户手册',
            'user_manual_feature_1': '实时更新的文档内容',
            'user_manual_feature_2': '详细的功能说明和使用教程',
            'user_manual_feature_3': '常见问题解答和故障排除',
            'user_manual_feature_4': '视频教程和示例代码',
            'close': '关闭',
            
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
            'shortcuts_view_lightrag_logs': '查看 LightRAG 日志',
            'shortcuts_navigation': '导航',
            'shortcuts_nav_chat': '导航到聊天',
            'shortcuts_nav_agents': '导航到代理',
            'shortcuts_nav_skills': '导航到技能',
            'shortcuts_nav_schedule': '导航到调度',
            'shortcuts_note': '<i>注意: 每个模块内都有额外的上下文相关快捷键。</i>',
            'shortcuts_error': '打开快捷键失败',
            
            # 版本检查对话框
            'check_updates_title': '检查更新',
            'check_failed': '检查失败',
            'update_latest_title': '您已是最新版本！',
            'update_available_title': '有新版本可用',
            'update_latest_desc': 'eCan {version} 是当前最新版本。',
        }
    }
    
    DEFAULT_LANG = 'zh-CN'
    
    def __init__(self):
        self.current_lang = detect_language(
            default_lang=self.DEFAULT_LANG,
            supported_languages=list(self.MESSAGES.keys())
        )
        logger.info(f"[MenuMessages] Language: {self.current_lang}")
    
    def get(self, key, **kwargs):
        """Get message by key with optional formatting."""
        messages = self.MESSAGES.get(self.current_lang, self.MESSAGES[self.DEFAULT_LANG])
        message = messages.get(key, key)
        
        # Auto-inject year if not provided
        if '{year}' in message and 'year' not in kwargs:
            kwargs['year'] = datetime.now().year
            
        if kwargs:
            try:
                return message.format(**kwargs)
            except Exception:
                return message
        return message

# Global message instance - lazy initialization
_menu_messages = None

def get_message(key, **kwargs):
    """Global helper to get messages"""
    global _menu_messages
    if _menu_messages is None:
        _menu_messages = MenuMessages()
    return _menu_messages.get(key, **kwargs)

def get_current_language():
    """Get current language code"""
    global _menu_messages
    if _menu_messages is None:
        _menu_messages = MenuMessages()
    return _menu_messages.current_lang
