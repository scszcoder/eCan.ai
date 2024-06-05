from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QPushButton, QMainWindow, QTextEdit, QVBoxLayout, QLabel


class CommanderLogWin(QMainWindow):
    def __init__(self, parent):
        super(CommanderLogWin, self).__init__(parent)

    # def __init__(self):
    #     super().__init__()
        self.parent = parent
        self.setWindowTitle(QMainWindow.tr('Network Logs'))
        self.logconsolelabel = QLabel(QLabel.tr("Log Console"), alignment=Qt.AlignLeft)
        self.logconsole = QTextEdit()
        self.logconsole.setReadOnly(True)
        self.clearButton = QPushButton(QPushButton.tr("Clear"))
        self.closeButton = QPushButton(QPushButton.tr("Close"))

        self.clearButton.clicked.connect(self.clear)
        self.closeButton.clicked.connect(self.close)

        self.mainWidget = QWidget()
        self.logconsoleLayout = QVBoxLayout(self)
        self.logconsoleLayout.addWidget(self.clearButton)
        self.logconsoleLayout.addWidget(self.logconsolelabel)
        self.logconsoleLayout.addWidget(self.logconsole)
        self.logconsoleLayout.addWidget(self.closeButton)
        self.mainWidget.setLayout(self.logconsoleLayout)
        self.setCentralWidget(self.mainWidget)


    def appendLogs(self, logs):
        # File actions
        for log in logs:
            self.logconsole.append(log)

    def clear(self, mode):
        self.logconsole.clear()




