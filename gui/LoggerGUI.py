import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *

class CommanderLogWin(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(CommanderLogWin, self).__init__(parent)

    # def __init__(self):
    #     super().__init__()
        self.parent = parent
        self.setWindowTitle('Network Logs')
        self.logconsolelabel = QtWidgets.QLabel("Log Console", alignment=QtCore.Qt.AlignLeft)
        self.logconsole = QtWidgets.QTextEdit()
        self.logconsole.setReadOnly(True)
        self.clearButton = QtWidgets.QPushButton("Clear")
        self.closeButton = QtWidgets.QPushButton("Close")

        self.clearButton.clicked.connect(self.clear)
        self.closeButton.clicked.connect(self.close)

        self.mainWidget = QtWidgets.QWidget()
        self.logconsoleLayout = QtWidgets.QVBoxLayout(self)
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




