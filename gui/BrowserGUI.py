# from PySide6.QtWidgets import (QVBoxLayout, QWidget, QMainWindow)

# from PySide6.QtWebEngineWidgets import QWebEngineView

# class BrowserWindow(QMainWindow):
#     def __init__(self, parent=None):
#         super().__init__(parent)

#         # Create the QWebEngineView (browser)
#         self.browser = QWebEngineView()

#         # Set the initial URL (you can change this to any URL or a local file)
#         self.browser.setUrl("http://127.0.0.1:7860")

#         # Create a layout for the browser window and add the browser widget to it
#         layout = QVBoxLayout()
#         central_widget = QWidget()  # Create a central widget to hold the layout
#         central_widget.setLayout(layout)
#         layout.addWidget(self.browser)

#         # Set the central widget of the browser window
#         self.setCentralWidget(central_widget)

#         # 默认隐藏窗口，避免闪现
#         self.setVisible(False)

#     def loadURL(self, url):
#         self.browser.setUrl(url)