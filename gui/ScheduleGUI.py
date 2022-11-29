import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *

class ScheduleWin(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.text = "Scheduler"
        self.calendar = QtWidgets.QCalendarWidget()
        self.Layout = QtWidgets.QVBoxLayout(self)
        self.Layout.addWidget(self.calendar)

class Scheduler(QtWidgets.QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.painter = QtGui.QPainter()
        self.events = {
            QtCore.QDate(2019, 5, 24): ["Bob's birthday"],
            QtCore.QDate(2019, 5, 19): ["Alice's birthday"]
        }

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        if date in self.events:
            painter.setBrush(QtGui.qRed)
            painter.drawEllipse(rect.topLeft() + QtCore.QPoint(12, 7), 3, 3)

