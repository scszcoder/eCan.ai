import sys
import random

from PySide6.QtCore import QDate
from PySide6.QtGui import QPainter, qRed
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QCalendarWidget, QVBoxLayout
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *
from ebbot import *

class ScheduleWin(QWidget):
    def __init__(self):
        super().__init__()
        self.text = QApplication.translate("QWidget", "Scheduler")
        self.calendar = QCalendarWidget()
        self.Layout = QVBoxLayout(self)
        self.Layout.addWidget(self.calendar)

class Scheduler(QCalendarWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.painter = QPainter()
        self.events = {
            QDate(2019, 5, 24): ["Bob's birthday"],
            QDate(2019, 5, 19): ["Alice's birthday"]
        }

    def paintCell(self, painter, rect, date):
        super().paintCell(painter, rect, date)
        if date in self.events:
            painter.setBrush(qRed)
            painter.drawEllipse(rect.topLeft() + QPoint(12, 7), 3, 3)

