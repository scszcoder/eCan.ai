import sys
import random
from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtWidgets import QApplication, QWidget, QPushButton
from ebbot import *
from locale import getdefaultlocale
from FlowLayout import *

# select webbrowser - exe path
# select auto run time.
# select repeat pattern.
# select tasks to run. (gen & print label, respond to offer, cancel order, sell similiar)
# select proxy (radio)
# specify products.(product number) to exclude.
# specify label type (default - cheapest)
# specify offer turn-down criteria


# app = QtGui.QApplication(sys.argv)
#
# locale = getdefaultlocale()
#
# translator = QtCore.QTranslator(app)
# translator.load('/usr/share/my_app/tr/qt_%s.qm' % locale[0])
# app.installTranslator(translator)


class SettingsWidget(QtWidgets.QMainWindow):
    def __init__(self, parent):
        super(SettingsWidget, self).__init__(parent)

        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        # self.
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True

        self.mainWidget = QtWidgets.QWidget()
        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.text = QtWidgets.QLabel("Hello World", alignment=QtCore.Qt.AlignCenter)

        self.layout = QtWidgets.QFormLayout(self)

        self.browser_path_label = QtWidgets.QLabel("Browser Executable:", alignment=QtCore.Qt.AlignLeft)
        self.browser_path_line_edit = QtWidgets.QLineEdit()
        self.browser_path_line_edit.setPlaceholderText("input full path here")

        self.commander_run_cb = QtWidgets.QCheckBox("Commander Self Run Tasks")
        self.overcapcity_warning_cb = QtWidgets.QCheckBox("Warning If Over-capacity")
        self.overcapcity_force_cb = QtWidgets.QCheckBox("Force Commander To Run If Over-capacity")

        self.num_vehicle_label = QtWidgets.QLabel("Number Of Vehicles:")
        self.num_vehicle_text = QtWidgets.QLineEdit()

        # self.layout.addWidget(self.text)
        self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        self.layout.addRow(self.num_vehicle_label, self.num_vehicle_text)
        self.layout.addRow(self.commander_run_cb)
        self.layout.addRow(self.overcapcity_warning_cb)
        self.layout.addRow(self.overcapcity_force_cb)
        self.layout.addRow(self.cancel_button, self.save_button)

        self.cancel_button.clicked.connect(self.close)
        self.save_button.clicked.connect(self.save_settings)

        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

    def save_settings(self):
        self.commander_run = (self.commander_run_cb.checState() == QtGui.Checked)
        self.overcapcity_warning = (self.overcapcity_warning_cb.checState() == QtGui.Checked)
        self.overcapcity_force = (self.overcapcity_force_cb.checState() == QtGui.Checked)
