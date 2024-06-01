import sys
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QFrame, QLineEdit, QPushButton, QLabel, QHBoxLayout
from PySide6.QtGui import QPainter, QBrush, QColor, QPainterPath, QPolygonF, QPen, QStandardItemModel
from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QTimer
from PySide6.QtWidgets import QApplication, QSplitter, QListWidget, QListWidgetItem, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLineEdit, QPushButton, QLabel, QScrollArea, QMainWindow
from PySide6.QtWidgets import QTextBrowser, QListView
from PySide6.QtGui import QIcon
from PySide6.QtGui import QDesktopServices
import re
from math import cos, radians, sin
from FlowLayout import *
from ebbot import *

class MultiLineLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.AltModifier:
            self.insert("\n")  # Insert a newline
        else:
            super().keyPressEvent(event)

class BubbleLabel(QFrame):
    def __init__(self, text, is_self, parent=None):
        super().__init__(parent)
        self.text_browser = QTextBrowser(self)
        self.text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.text_browser.setOpenExternalLinks(True)  # Handle link clicks within the application
        self.text_browser.setAcceptRichText(True)
        self.text_browser.setHtml(text)
        self.text_browser.setStyleSheet("background: transparent; border: none;")
        # self.text_browser.anchorClicked.connect(self.on_anchor_clicked)  # Connect the link clicked signal
        self.is_self = is_self

        self.initUI()
        html_text = self.convert_urls_to_links(text)
        self.text_browser.setHtml(html_text)

    # def on_anchor_clicked(self, url):
    #     if url.isValid():
    #         QDesktopServices.openUrl(url)

    def convert_urls_to_links(self, text):
        # Regular expression pattern for URLs
        url_pattern = r'(https?://\S+)'
        # Replace URLs with HTML anchor tags
        return re.sub(url_pattern, r'<a href="\1">\1</a>', text)

    def initUI(self):
        bubble_max_width = self.parent().width() * 0.75 - 40  # 75% of parent width minus padding
        self.text_browser.setMaximumWidth(bubble_max_width)
        self.text_browser.document().setTextWidth(bubble_max_width)
        self.adjustSizeToContent()

    def adjustSizeToContent(self):
        horizontal_padding = 20
        vertical_padding = 10
        tail_space = 15
        text_margin_adjustment = 5

        # Set maximum width for the text
        self.text_browser.setMaximumWidth(
            self.parent().width() * 0.75 - horizontal_padding * 2 - tail_space + text_margin_adjustment)
        self.text_browser.document().adjustSize()
        text_browser_size = self.text_browser.document().size().toSize()

        # Adjust the bubble size
        bubble_width = min(text_browser_size.width() + horizontal_padding * 2 + tail_space,
                           self.parent().width() * 0.75)
        bubble_height = text_browser_size.height() + vertical_padding * 2 + 5  # Increased height to accommodate text
        self.setFixedSize(bubble_width, bubble_height)

        # Adjust text position
        if self.is_self:
            text_x_position = horizontal_padding
        else:
            text_x_position = horizontal_padding + tail_space // 2 - text_margin_adjustment

        text_y_position = vertical_padding
        self.text_browser.setGeometry(text_x_position, text_y_position, text_browser_size.width(),
                                      text_browser_size.height() - 5)

    def adjustSizeToContentNearPerfect(self):
        padding = 20
        tail_space = 15
        text_margin_adjustment = 5  # Further margin adjustment for left bubble

        # Set maximum width for text
        self.text_browser.setMaximumWidth(
            self.parent().width() * 0.75 - padding * 2 - tail_space + text_margin_adjustment)
        self.text_browser.document().adjustSize()
        text_browser_size = self.text_browser.document().size().toSize()

        # Adjust bubble size
        bubble_width = min(text_browser_size.width() + padding * 2 + tail_space, self.parent().width() * 0.75)
        bubble_height = text_browser_size.height() + padding * 2
        self.setFixedSize(bubble_width, bubble_height)

        # Adjust text position
        if self.is_self:
            text_x_position = padding
        else:
            # Reduce left margin and increase right margin for the left bubble
            text_x_position = padding + tail_space // 2 - text_margin_adjustment

        # Set geometry for the text browser
        self.text_browser.setGeometry(text_x_position, padding, text_browser_size.width(),
                                      text_browser_size.height())

    def paintEvent1111(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#E1FFC7") if self.is_self else QColor("#D5E8D4")))
        painter.setPen(Qt.NoPen)

        rect = QRectF(10, 10, self.width() - 40, self.height() - 30)
        path = QPainterPath()
        radius = 15
        tailWidth = 15
        tailHeight = 20
        tailOffset = 0  # The amount to move the tail up

        # Draw the rounded rectangle part of the bubble
        path.addRoundedRect(rect, radius, radius)

        # Tail position and drawing
        if self.is_self:
            # Bubble tail on the right
            tailPos = QPointF(rect.right() - tailWidth / 2, rect.bottom() - tailOffset)
            path.moveTo(tailPos)
            path.lineTo(tailPos + QPointF(0, tailHeight))
            path.lineTo(tailPos - QPointF(tailWidth, 0))
            path.lineTo(tailPos)
        else:
            # Bubble tail on the left
            tailPos = QPointF(rect.left() + tailWidth / 2, rect.bottom() - tailOffset)
            path.moveTo(tailPos)
            path.lineTo(tailPos + QPointF(0, tailHeight))
            path.lineTo(tailPos + QPointF(tailWidth, 0))
            path.lineTo(tailPos)

        path.closeSubpath()
        painter.drawPath(path)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(QColor("#0078D7") if self.is_self else QColor("#00B294")))
        painter.setPen(Qt.NoPen)

        rect = QRectF(10, 10, self.width() - 40, self.height() - 30)
        path = QPainterPath()
        radius = 10  # Smaller curvature for the round corners
        tailWidth = 15
        tailHeight = 20

        # Draw the rounded rectangle part of the bubble
        path.addRoundedRect(rect, radius, radius)

        # Tail
        tailBase = QPointF(rect.right() - tailWidth, rect.bottom()) if self.is_self else QPointF(
            rect.left() + tailWidth, rect.bottom())
        path.moveTo(tailBase)
        tailTip = QPointF(tailBase.x() + (tailWidth / 2 if self.is_self else -tailWidth / 2), tailBase.y() + tailHeight)
        path.lineTo(tailTip)
        tailOtherCorner = QPointF(tailBase.x() - (tailWidth / 2 if self.is_self else -tailWidth / 2), tailBase.y())
        path.lineTo(tailOtherCorner)
        path.lineTo(tailBase)

        path.closeSubpath()
        painter.drawPath(path)



class ChatWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.partent = parent
        self.initUI()

    def initUI(self):
        self.main_layout = QVBoxLayout(self)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area_widget_contents = QWidget()
        self.scroll_area.setWidget(self.scroll_area_widget_contents)

        self.layout = QVBoxLayout(self.scroll_area_widget_contents)
        # self.layout.setSpacing(1)  # Constant spacing between bubbles

        self.message_edit = MultiLineLineEdit(self)

        buttons_layout = QHBoxLayout()
        self.self_send_button = QPushButton("Me")
        self.self_send_button.clicked.connect(lambda: self.addMessage(True, self.message_edit.text()))
        buttons_layout.addWidget(self.self_send_button)

        self.main_layout.addWidget(self.scroll_area)
        self.main_layout.addWidget(self.message_edit)
        self.main_layout.addLayout(buttons_layout)

        self.setGeometry(300, 300, 400, 500)
        self.setWindowTitle('Chat Bubbles Example')

    def addMessage(self, is_self, msg):
        text = msg
        if text:
            bubble = BubbleLabel(text, is_self, self.scroll_area_widget_contents)
            bubble.adjustSizeToContent()
            self.layout.addWidget(bubble, alignment=Qt.AlignRight if is_self else Qt.AlignLeft)
            self.parent.addActiveChatHis(text)
            self.message_edit.clear()
            self.scroll_area.ensureWidgetVisible(bubble)
            QTimer.singleShot(100, self.scrollToBottom)
            # self.scrollToBottom()

            #now actually send the to bot agent. if the bot is on local machine, simply send it to its queue.
            # if the bot agent is on a remote computer, send the message out via TCPIP.
            self.parent.parent.sendBotChatMessage(0, self.parent.selected_agent.getBid(), text)

    def scrollToBottom(self):
        # Assuming 'self.chatDisplay' is your QScrollArea or similar widget
        # that shows the chat content.
        vertical_scroll_bar = self.scroll_area.verticalScrollBar()
        vertical_scroll_bar.setValue(vertical_scroll_bar.maximum())


class ChatWin(QMainWindow):
    def __init__(self, parent):
        super(ChatWin, self).__init__(parent)
        self.parent = parent
        self.botAgents = []
        self.teamList = BotListView(self)
        self.teamList.installEventFilter(self)
        self.botModel = QStandardItemModel(self.teamList)
        self.teamList.setModel(self.botModel)
        self.teamList.setViewMode(QListView.IconMode)
        self.teamList.setMovement(QListView.Snap)
        self.setupTeamList()  # Populate the friends list
        self.chatWidget = ChatWidget(self)  # Assuming ChatWidget is your existing chat UI class
        self.selected_index = -1
        self.selected_agent = None


        # Use QSplitter for adjustable panels
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.teamList)
        self.parent.showMsg("hello????")
        self.splitter.addWidget(self.chatWidget)

        # Set initial sizes (optional)
        self.splitter.setSizes([200, 300])

        self.setCentralWidget(self.splitter)

    def setupTeamList(self):
        # Example: Add friends to the list
        for bot in self.parent.bots:
            self.parent.showMsg("bot agent:"+bot.text())
            bot_agent = EBBOT_AGENT(self)
            bot_agent.setText(bot.text())
            bot_agent.setIcon(bot.icon())
            bot_agent.setBid(bot.getBid())
            self.botModel.appendRow(bot_agent)
            self.botAgents.append(bot_agent)

        self.teamList.clicked.connect(self.switchConversation)

    def switchConversation(self, index):
        self.selected_agent = self.botModel.itemFromIndex(index)
        self.selected_index = index
        selected_bid = int(self.selected_agent.text().split(":")[0][3:])
        self.parent.showMsg("switched talks to :"+str(selected_bid))

        # Clear current messages
        for i in reversed(range(self.chatWidget.main_layout.count())):
            self.chatWidget.main_layout.itemAt(i).widget().setParent(None)

        # Add new messages
        for message in self.selected_agent.chat_history.get_messages():
            if "<" in message[:30]:
                is_self = True
                start_idx = [li for li, letter in enumerate(message) if letter == "<"][1] + 1
            else:
                is_self = False
                start_idx = [li for li, letter in enumerate(message) if letter == ">"][1] + 1

            chat_message = "["+message[5:19]+"]"+message[start_idx:]
            self.chatWidget.addMessage(is_self, chat_message)
        self.chatWidget.scroll_area.verticalScrollBar().setValue(self.chatWidget.scroll_area.verticalScrollBar().maximum())

    def addActiveChatHis(self, to_me, others, text):
        recipients = ""
        dtnow = datetime.now()
        date_word = dtnow.isoformat()
        if to_me:
            # this is some one sending the message to a bot agent (to agent, this is incoming)
            self.selected_agent.addChat(date_word+">"+str(others[0])+">0>"+text)
        else:
            # this a bot agent send message to some other entity (to agent, this is outgoing).
            for i, aid in enumerate(others):
                if i == len(others)-1:
                    recipients = str(aid)
                else:
                    recipients = str(aid) + ","
            self.selected_agent.addChat(date_word + ">0>"+recipients+">" + text)

    # a message will be add to chat history of both the sender and the receiver.
    def addNetChatHis(self, sender, recipients, msg):
        recipients = ""
        dtnow = datetime.now()
        date_word = dtnow.isoformat()
        found = next((agent for i, agent in enumerate(self.botAgents) if str(agent.getBid()) == sender), None)
        if found:
            found.addChat(msg)

        for i, aid in enumerate(recipients):
            found = next((agent for i, agent in enumerate(self.botAgents) if str(agent.getBid()) == aid), None)
            if found:
                found.addChat(msg)
                if found.getBid() == self.selected_agent.getBid():
                    self.chatWidget.addMessage(True, msg)


    def setBot(self, item):
        self.parent.showMsg(f"Switched to conversation with {item.text()}")

    def updateDisplay(self, msg):
        self.chatWidget.addMessage(False, msg)

    def loadChat(self, msg):
        self.show()

