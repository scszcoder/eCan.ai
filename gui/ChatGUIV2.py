import base64
import json
import re
import uuid
from datetime import datetime
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, QListWidget,
                               QListWidgetItem, QLineEdit, QDialog, QFrame, QMenu, QFileDialog,
                               QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QAction, QTextBlockFormat, QImage, QPixmap, QIcon

from Cloud import send_query_chat_request_to_cloud


class ChatDialog(QDialog):
    def __init__(self, parent, select_bot_id):
        super().__init__()
        self.parent = parent
        self.contact_messages = {}  # 用于存储每个联系人的消息记录
        self.init_ui()
        self.init_contact(select_bot_id)
        self.goals_json = {
            "pass_method": "all mandatory",
            "total_score": 0,
            "passed": False,
            "goals": [
                {
                    "name": "test",
                    "type": "echo",
                    "mandatory": True,
                    "score": 0,
                    "standards": [],
                    "weight": 1,
                    "passed": False
                }
            ]
        }

    def init_contact(self, select_bot_id):
        bots = self.parent.bots
        select_index = 0
        for index, bot in enumerate(bots):
            if bot.getBid() == select_bot_id:
                select_index = index
            self.contact_messages[bot.getBid()] = []
            item = QListWidgetItem(bot.text())
            item.setData(Qt.UserRole, bot.getBid())
            item.setIcon(QIcon(bot.icon))
            self.contacts_list.addItem(item)
        self.contacts_list.setCurrentRow(select_index)

    def init_ui(self):
        self.setWindowTitle("Agent Chat")
        self.setGeometry(100, 100, 800, 600)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 左侧联系人列表布局
        contacts_layout = QVBoxLayout()
        contacts_layout.setContentsMargins(0, 0, 0, 0)
        contacts_layout.setSpacing(0)
        left_frame = QFrame()
        left_frame.setLayout(contacts_layout)
        left_frame.setFixedWidth(200)
        main_layout.addWidget(left_frame)

        self.contacts_list = QListWidget()
        self.contacts_list.setStyleSheet("""
            QListWidget::item:selected {
                background-color: blue;
                color: white;
            }
        """)
        self.contacts_list.currentItemChanged.connect(self.contact_selected)
        contacts_layout.addWidget(self.contacts_list)

        # 右侧消息区域布局
        messages_layout = QVBoxLayout()
        messages_layout.setContentsMargins(0, 0, 0, 0)
        messages_layout.setSpacing(0)
        right_frame = QFrame()
        right_frame.setLayout(messages_layout)
        main_layout.addWidget(right_frame)

        # 更改为QTextBrowser以支持超链接
        self.message_history = QTextBrowser()
        self.message_history.setOpenExternalLinks(True)  # 允许打开外部链接
        self.message_history.setStyleSheet("""
            background-color: #F0F0F0;
            border-radius: 10px;
            padding: 10px;
        """)
        self.message_history.anchorClicked.connect(self.show_image_preview)
        messages_layout.addWidget(self.message_history)

        # 输入与发送区域布局
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(0)
        messages_layout.addLayout(input_layout)

        self.input_field = QLineEdit()
        self.input_field.setStyleSheet("""
            min-height: 30px;
            border-radius: 5px;
            padding: 5px;
        """)
        input_layout.addWidget(self.input_field)

        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("""
            min-width: 80px;
            height: 35px;
            border-radius: 5px;
            background-color: #007bff;
            color: white;
        """)
        self.send_button.clicked.connect(self.send_message)
        input_layout.addWidget(self.send_button)

        self.attach_button = QPushButton(QApplication.translate("QPushButton", "Add Image"))
        self.attach_button.setStyleSheet("""
            min-width: 80px;
            height: 35px;
            border-radius: 5px;
            background-color: #4CAF50;
            color: white;
        """)
        self.attach_button.clicked.connect(self.attach_image)
        input_layout.addWidget(self.attach_button)

        self.contacts_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.contacts_list.customContextMenuRequested.connect(self.show_contact_menu)

        self.setStyleSheet("""
            QWidget {
                font-size: 14px;
            }
        """)

    # 添加图片发送功能
    def attach_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "选择图片", "", "Images (*.png *.xpm *.jpg *.bmp)")
        if file_path:
            try:
                with open(file_path, 'rb') as img_file:
                    image_data = img_file.read()
                    image_base64 = base64.b64encode(image_data).decode('utf-8')
                    self.addRightMessage(image_base64, type="image")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Error loading images: {e}")

    def show_contact_menu(self, pos):
        index = self.contacts_list.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        delete_action = QAction(QApplication.translate("QAction", "Delete"), self)
        all_activities_action = QAction("Show All Activities", self)
        delete_action.triggered.connect(lambda: self.delete_contact(index.row()))
        all_activities_action.triggered.connect(lambda: self.show_all_activities(index.row()))
        menu.addAction(delete_action)
        menu.exec_(self.contacts_list.mapToGlobal(pos))

    def delete_contact(self, row):
        item = self.contacts_list.takeItem(row)
        if item:
            del item

    def show_all_activities(self, row):
        print("open a new window or tab or frame (or swap the current bot list) to show a list of conversations this bot has with other bot/bot groups")
        print("before open, should check permission and authorization first. only open when permission allows.")
        print("if openable, a supervisor could chime into the communication, or whisper into an agent?")

    def contact_selected(self, current):
        print(current)
        if current:
            contact_id = current.data(Qt.UserRole)
            self.load_chat_history(contact_id)

    def select_contact(self, select_bot_id):
        if select_bot_id:
            for i in range(self.contacts_list.count()):
                current = self.contacts_list.item(i)
                if current.data(Qt.UserRole) == select_bot_id:
                    self.contacts_list.setCurrentRow(i)
                    break
        self.load_chat_history(select_bot_id)

    def load_chat_history(self, contact_id):
        self.message_history.clear()  # 清空当前聊天记录
        # 假设这里是从数据库或网络获取的消息历史，简化为直接从contact_messages字典获取
        if contact_id in self.contact_messages:
            messages = self.contact_messages[contact_id]
            for unique_id, message, type, dir, time in messages:
                if isinstance(message, str):  # 文本消息
                    if dir == 'right':
                        self.addRightMessage(message, history=True, type=type, time=time, unique_id=unique_id)
                    else:
                        self.addLeftMessage(message, history=True, type=type, time=time, unique_id=unique_id)
            self.message_history.moveCursor(QTextCursor.MoveOperation.End)
            self.message_history.ensureCursorVisible()

    def send_message(self):
        message = self.input_field.text()
        if message:
            if self.parent.host_role == "Staff Officer":
                self.parent.sa_send_chat(message)
                self.input_field.clear()
                self.addRightMessage(message)
            else:
                current_item = self.contacts_list.currentItem()
                if current_item:
                    self.input_field.clear()
                    self.addRightMessage(message)
                    # 实际应用中，还需将消息发送到服务器等后续逻辑

    def addHyperlinkMessage(self, message):
        """插入可能含有超链接的文本"""
        # 自动识别并转换URL为超链接
        return re.sub(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            lambda x: f'<a href="{x.group(0)}">{x.group(0)}</a>', message
        )

    def set_message_history(self, uuid, message, type, time, dir):
        current_item = self.contacts_list.currentItem()
        if current_item:
            contact_id = current_item.data(Qt.UserRole)
            if contact_id not in self.contact_messages:
                self.contact_messages[contact_id] = []
            self.contact_messages[contact_id].append((uuid, message, type, dir, time))

    def scrollToBottomIfNeeded(self):
        scrollbar = self.message_history.verticalScrollBar()
        if scrollbar.value() == scrollbar.maximum():
            self.scrollToBottom()

    def scrollToBottom(self):
        cursor = self.message_history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.message_history.setTextCursor(cursor)

    def addLeftMessage(self, message, history=False, type='text', time='', unique_id=''):
        # 设置左侧消息格式
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignLeft)
        block_format.setBottomMargin(5)
        send_message = self.addHyperlinkMessage(message)
        self.insertion_message(block_format, send_message, history, type, time, unique_id, 'left')

    def addRightMessage(self, message, history=False, type='text', time='', unique_id=''):
        # 设置右侧消息格式
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignRight)
        block_format.setBottomMargin(5)
        send_message = self.addHyperlinkMessage(message)
        message_id = self.insertion_message(block_format, send_message, history, type, time, unique_id, 'right')
        if unique_id == '':
            self.send_message_cloud(message_id, message)

    def send_message_cloud(self, message_id, message):
        current_item = self.contacts_list.currentItem()
        goals_string = json.dumps(self.goals_json).replace('"', '\\"')
        timeStamp = datetime.now().isoformat(timespec='milliseconds') + 'Z'
        qs = [{"msgID": message_id, "user": current_item.text(),
               "timeStamp": timeStamp, "products": "",
               "goals": goals_string, "background": "", "msg": message}]
        result = send_query_chat_request_to_cloud(self.parent.session,
                                                  self.parent.tokens['AuthenticationResult']['IdToken'], qs)
        self.addLeftMessage(result['body'])
        self.message_history.moveCursor(QTextCursor.MoveOperation.End)
        self.message_history.ensureCursorVisible()

    def insertion_message(self, block_format, message, history=False, type='text', time='', unique_id='',
                          dir='left') -> str:
        # 插入消息
        cursor = self.message_history.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertBlock(block_format)
        if unique_id == '':
            unique_id = str(uuid.uuid4())
        if time == '':
            time = datetime.now().strftime('%H:%M')
        if type == 'text':
            cursor.insertHtml(f"{message}    {time}")
        elif type == 'image':
            image_html = f'<a href="#image_{unique_id}"><img src="data:image/jpeg;base64,{message}" width="300"/></a>'
            cursor.insertHtml(f"{image_html}    {time}")
        self.message_history.setTextCursor(cursor)
        if not history:
            self.set_message_history(unique_id, message, type, time, dir)
        return unique_id

    def show_image_preview(self, qurl):
        fragment_id = qurl.fragment()
        if fragment_id.startswith("image_"):
            current_item = self.contacts_list.currentItem()
            if current_item:
                contact_id = current_item.data(Qt.UserRole)
                messages = self.contact_messages[contact_id]
                uuid = fragment_id[len("image_"):]
                for unique_id, message, type, dir, time in messages:
                    if unique_id == uuid:
                        img_data = base64.b64decode(message)
                        img = QImage.fromData(img_data)
                        pixmap = QPixmap.fromImage(img)
                        scaled_pixmap = pixmap.scaledToWidth(500, Qt.TransformationMode.SmoothTransformation)
                        # 使用QMessageBox展示图片预览
                        preview = QMessageBox()
                        preview.setWindowTitle("Picture Preview")
                        preview.setIconPixmap(scaled_pixmap)
                        preview.exec_()

    def closeEvent(self, event):
        """
        重写关闭事件处理方法，以便在窗口关闭前执行一些清理工作。
        """
        self.disconnectSignals()

        if QMessageBox.question(self, "Confirm Exit", "Are you sure you want to exit?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
            event.ignore()  # 如果用户点击"No"，忽略关闭事件
            return
        # 如果一切清理工作完成，或者用户确认关闭，继续关闭窗口
        event.accept()

    def disconnectSignals(self):
        self.contacts_list.currentItemChanged.disconnect(self.contact_selected)
        self.send_button.clicked.disconnect(self.send_message)
        self.attach_button.clicked.disconnect(self.attach_image)
        self.message_history.anchorClicked.disconnect(self.show_image_preview)
