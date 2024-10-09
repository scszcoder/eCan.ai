import base64
import json
import re
import uuid
from datetime import datetime
from PySide6.QtWidgets import (QVBoxLayout, QHBoxLayout, QPushButton, QTextBrowser, QListWidget, QWidget,
                               QListWidgetItem, QLineEdit, QDialog, QFrame, QMenu, QFileDialog, QMainWindow,
                               QMessageBox, QApplication)
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QAction, QTextBlockFormat, QImage, QPixmap, QIcon

from Cloud import send_query_chat_request_to_cloud
from PySide6.QtWebEngineWidgets import QWebEngineView


class BrowserWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Create the QWebEngineView (browser)
        self.browser = QWebEngineView()

        # Set the initial URL (you can change this to any URL or a local file)
        self.browser.setUrl("http://127.0.0.1:7860")

        # Create a layout for the browser window and add the browser widget to it
        layout = QVBoxLayout()
        central_widget = QWidget()  # Create a central widget to hold the layout
        central_widget.setLayout(layout)
        layout.addWidget(self.browser)

        # Set the central widget of the browser window
        self.setCentralWidget(central_widget)

    def loadURL(self, url):
        self.browser.setUrl(url)