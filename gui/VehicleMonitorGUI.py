import json

from PySide6.QtCore import QEvent, QStringListModel, Qt
from PySide6.QtGui import QStandardItemModel, QColor, QPalette, QIcon, QAction, QStandardItem, QScreen
from PySide6.QtWidgets import QApplication, QWidget, QPushButton, QMainWindow, QTabWidget, QVBoxLayout, QLineEdit, \
    QCompleter, QComboBox, QScrollArea, QHBoxLayout, QRadioButton, QFileDialog, QButtonGroup, QStyledItemDelegate, \
    QListView, QLabel, QFrame, QMenu
import traceback
import time

from bot.missions import TIME_SLOT_MINS, EBMISSION
from gui.tool.MainGUITool import StaticResource
from utils.logger_helper import logger_helper


class VehicleMonitorWin(QMainWindow):
    def __init__(self, main_win, vehicle=None):
        super(VehicleMonitorWin, self).__init__(main_win)
        self.static_resource = StaticResource()
        self.text = QApplication.translate("QMainWindow", "Vehicle Monitor")
        self.parent = main_win
        self.vehicle = vehicle

    def setVehicle(self, v):
        self.vehicle = v