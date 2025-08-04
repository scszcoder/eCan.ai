from PySide6.QtWidgets import (QMainWindow, QVBoxLayout, QWidget, QMessageBox)
from PySide6.QtGui import QAction, QKeySequence, QShortcut
import sys
import os
from gui.ipc.api import IPCAPI
from PySide6.QtGui import QPixmap  # Add this import
from PySide6.QtGui import QIcon  # Add this import
from PySide6.QtCore import Qt  # For high quality scaling

from config.app_settings import app_settings
from utils.logger_helper import logger_helper as logger
from gui.core.web_engine_view import WebEngineView
from gui.core.dev_tools_manager import DevToolsManager
from app_context import AppContext
from agent.chats.chat_service import ChatService
import time


# 配置日志以抑制 macOS IMK 警告
if sys.platform == 'darwin':
    os.environ["QT_LOGGING_RULES"] = "qt.webengine* = false"


class WebGUI(QMainWindow):
    def __init__(self, parent=None):
        super().__init__()
        self.setWindowTitle("eCan.ai")
        self.parent = parent
        # Set window icon
        icon_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
        self.setWindowIcon(QIcon(icon_path))
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        # 创建 Web 引擎
        self.web_engine_view = WebEngineView(self)
        
        # 创建开发者工具管理器
        self.dev_tools_manager = DevToolsManager(self)

        # 获取 IPC API
        self._ipc_api = None
        
        # 获取 Web URL
        web_url = app_settings.get_web_url()
        logger.info(f"Web URL from settings: {web_url}")
        
        if web_url:
            if app_settings.is_dev_mode:
                # 开发模式：使用 Vite 开发服务器
                self.web_engine_view.load_url(web_url)
                logger.info(f"Development mode: Loading from {web_url}")
            else:
                # 生产模式：加载本地文件
                self.load_local_html()
        else:
            logger.error("Failed to get web URL")
        
        # 添加 Web 引擎到布局
        layout.addWidget(self.web_engine_view)
        layout.setSpacing(0)
        
        # 设置快捷键
        self._setup_shortcuts()

    def set_parent(self, parent):
        self.parent = parent

    def load_local_html(self):
        """加载本地 HTML 文件"""
        index_path = app_settings.dist_dir / "index.html"
        logger.info(f"Looking for index.html at: {index_path}")
        
        if index_path.exists():
            try:
                # 直接加载本地文件
                self.web_engine_view.load_local_file(index_path)
                logger.info(f"Production mode: Loading from {index_path}")
                
            except Exception as e:
                logger.error(f"Error loading HTML file: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        else:
            logger.error(f"index.html not found in {app_settings.dist_dir}")
            # 列出目录内容以便调试
            if app_settings.dist_dir.exists():
                logger.info(f"Contents of {app_settings.dist_dir}:")
                for item in app_settings.dist_dir.iterdir():
                    logger.info(f"  - {item.name}")
            else:
                logger.error(f"Directory {app_settings.dist_dir} does not exist")
    
    def _setup_shortcuts(self):
        """设置快捷键"""
        # 开发者工具快捷键
        self.dev_tools_shortcut = QShortcut(QKeySequence("F12"), self)
        self.dev_tools_shortcut.activated.connect(self.dev_tools_manager.toggle)
        
        # F5 重新加载
        reload_action = QAction(self)
        reload_action.setShortcut(QKeySequence('F5'))
        reload_action.triggered.connect(self.reload)
        self.addAction(reload_action)
        
        # Ctrl+L 清除日志
        clear_logs_action = QAction(self)
        clear_logs_action.setShortcut(QKeySequence('Ctrl+L'))
        clear_logs_action.triggered.connect(self.dev_tools_manager.clear_all)
        self.addAction(clear_logs_action)

    def self_confirm(self):
        print("self confirming top web gui....")

    def reload(self):
        """重新加载页面"""
        logger.info("Reloading page...")
        if app_settings.is_dev_mode:
            self.web_engine_view.reload_page()
        else:
            self.load_local_html()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 创建自定义对话框
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('Confirm Exit')
        msg_box.setText('Are you sure you want to exit the program?')
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        # Set custom icon
        logo_path = os.path.join(os.path.dirname(__file__), '../resource/images/logos/logoWhite22.png')
        pixmap = QPixmap(logo_path)
        if not pixmap.isNull():
            # 保持比例并高质量缩放
            scaled_pixmap = pixmap.scaled(128, 128, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            msg_box.setIconPixmap(scaled_pixmap)
        else:
            msg_box.setIcon(QMessageBox.Question)
        reply = msg_box.exec()
        if reply == QMessageBox.Yes:
            # 接受关闭事件
            event.accept()
            from PySide6.QtWidgets import QApplication
            QApplication.quit()
        else:
            # 忽略关闭事件
            event.ignore()

 
    def get_ipc_api(self):
        self._ipc_api = IPCAPI.get_instance()
        return self._ipc_api

    # Message
    # {
    #     role: 'user' | 'assistant' | 'system' | 'agent';
    # id: string;
    # createAt: number;
    # content: string | Content | Content[]; // 支持字符串、单个Content对象或Content数组
    # status: MessageStatus; // 使用枚举类型
    # attachments?: Attachment[]; // 统一使用
    # attachments
    # 字段，匹配后端数据结构
    #
    #      // 以下字段为应用内部使用，不是Semi
    # Chat组件必需的
    # chatId?: string;
    # senderId?: string;
    # senderName?: string;
    # time?: number;
    # isRead?: boolean; // 新增，表示消息是否已读
    # }
    def push_message_to_chat(self, chatId, msg):
        """类型分发，自动调用 chat_service.add_xxx_message，推送到前端，并记录数据库写入结果"""
        main_window = self.parent
        logger.info(f"push_message echo_msg: {msg}")
        chat_service: ChatService = main_window.chat_service
        content = msg.get('content')
        role = msg.get('role')
        senderId = msg.get('senderId')
        createAt = msg.get('createAt')
        senderName = msg.get('senderName')
        status = msg.get('status')
        ext = msg.get('ext')
        attachments = msg.get('attachments')
        # 类型分发
        db_result = None
        if isinstance(content, dict):
            msg_type = content.get('type')
            if msg_type == 'text':
                print("pushing text message", content)
                db_result = chat_service.add_text_message(
                    chatId=chatId, role=role, text=content.get('text', ''), senderId=senderId, createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'form':
                form = content.get('form', {})
                db_result = chat_service.add_form_message(
                    chatId=chatId, role=role, form=form, senderId=senderId,
                    createAt=createAt, senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'code':
                code = content.get('code', {})
                db_result = chat_service.add_code_message(
                    chatId=chatId, role=role, code=code.get('value', ''), language=code.get('lang', 'python'),
                    senderId=senderId, createAt=createAt, senderName=senderName, status=status, ext=ext,
                    attachments=attachments)
            elif msg_type == 'system':
                system = content.get('system', {})
                db_result = chat_service.add_system_message(
                    chatId=chatId, text=system.get('text', ''), level=system.get('level', 'info'),
                    senderId=senderId, createAt=createAt, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'notification':
                print("pushing notification message", content)
                notification = content.get('notification', {})
                db_result = chat_service.add_notification_message(
                    chatId=chatId, title=notification.get('title', ''), content=notification,
                    level=notification.get('level', 'info'), senderId=senderId, createAt=createAt, status=status,
                    ext=ext, attachments=attachments)
            elif msg_type == 'card':
                card = content.get('card', {})
                db_result = chat_service.add_card_message(
                    chatId=chatId, role=role, title=card.get('title', ''), content=card.get('content', ''),
                    actions=card.get('actions', []), senderId=senderId, createAt=createAt, senderName=senderName,
                    status=status, ext=ext, attachments=attachments)
            elif msg_type == 'markdown':
                db_result = chat_service.add_markdown_message(
                    chatId=chatId, role=role, markdown=content.get('markdown', ''), senderId=senderId,
                    createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
            elif msg_type == 'table':
                table = content.get('table', {})
                db_result = chat_service.add_table_message(
                    chatId=chatId, role=role, headers=table.get('headers', []), rows=table.get('rows', []),
                    senderId=senderId, createAt=createAt, senderName=senderName, status=status, ext=ext,
                    attachments=attachments)
            else:
                db_result = chat_service.add_message(
                    chatId=chatId, role=role, content=content, senderId=senderId, createAt=createAt,
                    senderName=senderName, status=status, ext=ext, attachments=attachments)
        else:
            db_result = chat_service.add_text_message(
                chatId=chatId, role=role, text=str(content), senderId=senderId, createAt=createAt,
                senderName=senderName, status=status, ext=ext, attachments=attachments)
        logger.info(f"push_message db_result: {db_result}")
        print("push_message db_result:", db_result)
        # 推送到前端
        app_ctx = AppContext()
        web_gui = app_ctx.web_gui
        # 推送写入数据库后的真实数据
        if db_result and isinstance(db_result, dict) and 'data' in db_result and msg_type != "notification":
            print("push_message db_result['data']:", db_result['data'])
            web_gui.get_ipc_api().push_chat_message(chatId, db_result['data'])
        elif db_result and isinstance(db_result, dict) and 'data' in db_result and msg_type == "notification":
            uid = msg.get('id')
            web_gui.get_ipc_api().push_chat_notification(chatId, content.get('notification', {}), True, createAt, uid)
        else:
            logger.error(f"message insert db failed{chatId}, {msg.id}")
            # web_gui.get_ipc_api().push_chat_message(chatId, msg)

    def receive_new_chat_message(self, sender_agent, chatId, content, uid):
        isRead = True
        timestamp = int(time.time())

        # chatId: str, content: dict, isRead: bool = False, timestamp: int = None, uid: str = None,
        response = self._ipc_api.push_chat_message(chatId, content, isRead, timestamp, uid)
        print("receive_new_chat_message response::", response)

    def receive_new_chat_notification(self, sender_agent, chatId, content, uid):
        isRead = True
        timestamp = int(time.time())

        # chatId: str, content: dict, isRead: bool = False, timestamp: int = None, uid: str = None,
        response = self._ipc_api.push_chat_notification(chatId, content, isRead, timestamp, uid)
        print("receive_new_chat_message response::", response)