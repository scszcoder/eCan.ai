import base64
import re
import uuid
from datetime import datetime
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, QListWidget,
                               QListWidgetItem, QLineEdit, QDialog, QFrame, QMenu, QFileDialog,
                               QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QAction, QTextBlockFormat, QImage, QPixmap


class ChatDialog(QDialog):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.contact_messages = {}  # 用于存储每个联系人的消息记录
        self.init_ui()
        self.init_contact()

    def init_contact(self):
        bots = self.parent.bots
        for bot in bots:
            self.contact_messages[bot.getBid()] = []
            item = QListWidgetItem(bot.text())
            item.setData(Qt.UserRole, bot.getBid())
            self.contacts_list.addItem(item)

    def init_ui(self):
        self.setWindowTitle("聊天对话框")
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

        send_button = QPushButton("发送")
        send_button.setStyleSheet("""
            min-width: 80px;
            height: 35px;
            border-radius: 5px;
            background-color: #007bff;
            color: white;
        """)
        send_button.clicked.connect(self.send_message)
        input_layout.addWidget(send_button)

        attach_button = QPushButton("添加图片")
        attach_button.setStyleSheet("""
            min-width: 80px;
            height: 35px;
            border-radius: 5px;
            background-color: #4CAF50;
            color: white;
        """)
        attach_button.clicked.connect(self.attach_image)
        input_layout.addWidget(attach_button)

        self.contacts_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.contacts_list.customContextMenuRequested.connect(self.show_contact_menu)

        self.setStyleSheet("""
            QWidget {
                font-size: 14px;
            }
            /* 根据需要进一步美化 */
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
                QMessageBox.warning(self, "错误", f"加载图片时出错: {e}")

    def show_contact_menu(self, pos):
        index = self.contacts_list.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self)
        delete_action = QAction("删除", self)
        delete_action.triggered.connect(lambda: self.delete_contact(index.row()))
        menu.addAction(delete_action)
        menu.exec_(self.contacts_list.mapToGlobal(pos))

    def delete_contact(self, row):
        item = self.contacts_list.takeItem(row)
        if item:
            del item

    def contact_selected(self, current, previous):
        print(current)
        if current:
            contact_id = current.data(Qt.UserRole)
            self.load_chat_history(contact_id)

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
            current_item = self.contacts_list.currentItem()
            if current_item:
                self.input_field.clear()
                self.addHyperlinkMessage(message, datetime.now().strftime('%H:%M'))
                # 实际应用中，还需将消息发送到服务器等后续逻辑
            self.message_history.moveCursor(QTextCursor.MoveOperation.End)
            self.message_history.ensureCursorVisible()
            self.addLeftMessage("测试回来的消息", )

    def addHyperlinkMessage(self, message, time):
        """插入可能含有超链接的文本"""
        # 自动识别并转换URL为超链接
        hyperlink_message = re.sub(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            lambda x: f'<a href="{x.group(0)}">{x.group(0)}</a>', message
        )
        formatted_message = f'{hyperlink_message}'
        self.addRightMessage(formatted_message)

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

        self.insertion_message(block_format, message, history, type, time, unique_id, 'left')

    def addRightMessage(self, message, history=False, type='text', time='', unique_id=''):
        # 设置右侧消息格式
        block_format = QTextBlockFormat()
        block_format.setAlignment(Qt.AlignRight)
        block_format.setBottomMargin(5)
        self.insertion_message(block_format, message, history, type, time, unique_id, 'right')

    def insertion_message(self, block_format, message, history=False, type='text', time='', unique_id='', dir='left'):
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
            self.message_history.anchorClicked.connect(self.show_image_preview)
        self.message_history.setTextCursor(cursor)
        if not history:
            self.set_message_history(unique_id, message, type, time, dir)

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
                        preview.setWindowTitle("图片预览")
                        preview.setIconPixmap(scaled_pixmap)
                        preview.exec_()
