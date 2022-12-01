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

class MainWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.setGeometry(100, 100, 200, 150)
        self.setWindowTitle('USHOOA!')
        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]

        self.run_button = QtWidgets.QPushButton("Run Bot")
        self.set_button = QtWidgets.QPushButton("Settings")
        self.help_button = QtWidgets.QPushButton("Help")
        self.exit_button = QtWidgets.QPushButton("Exit")
        self.text = QtWidgets.QLabel("Hello World",
                                     alignment=QtCore.Qt.AlignCenter)

        self.icon = DragIcon("<html><img src='C:/Users/Teco/PycharmProjects/ecbot/resource/c_robot64_0.png'><br><p style='text-align:center;max-width:64px;'>bot0</p></html>")
        #icpix = QtGui.QPixmap("<html><img src='C:/Users/Teco/PycharmProjects/ecbot/resource/c_robot64_0.png'></html>")
        #icpix.scaled(64, 64, QtCore.Qt.KeepAspectRatio)
        #self.icon.setPixmap(icpix)
        #self.icon.setText("bot1")

        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.run_button)
        self.layout.addWidget(self.set_button)
        self.layout.addWidget(self.help_button)
        self.layout.addWidget(self.icon)
        self.layout.addWidget(self.exit_button)

        self.run_button.clicked.connect(self.magic)
        self.set_button.clicked.connect(self.showSettings)
        self.exit_button.clicked.connect(self.close)

        # self.combo = QtWidgets.QComboBox(self)
        # self.combo.currentIndexChanged.connect(self.change_func)
        #
        # self.translator = QtCore.QTranslator(self)
        # # self.v_layout.addWidget(self.combo)
        #
        # options = ([('English', ''), ('中文', 'eng-chs'), ])
        # for i, (text, lang) in enumerate(options):
        #     self.combo.addItem(text)
        #     self.combo.setItemData(i, lang)
        #
        # self.retranslateUi()

    @QtCore.Slot()
    def magic(self):
        self.text.setText(random.choice(self.hello))

    def showSettings(self):
        self.settingsWidget = SettingsWidget()
        self.settingsWidget.resize(400, 200)
        self.settingsWidget.show()

    def runBot(self):
        self.bot = EBBOT(self.bot_settings)
        self.bot.run()

    # @QtCore.Slot(int)
    # def change_func(self, index):
    #     data = self.combo.itemData(index)
    #     if data:
    #         self.trans.load(data)
    #         QtWidgets.QApplication.instance().installTranslator(self.trans)
    #     else:
    #         QtWidgets.QApplication.instance().removeTranslator(self.trans)
    #
    # def changeEvent(self, event):
    #     if event.type() == QtCore.QEvent.LanguageChange:
    #         self.retranslateUi()
    #     super(MainWidget, self).changeEvent(event)
    #
    # def retranslateUi(self):
    #     self.button.setText(QtWidgets.QApplication.translate('Demo', 'Start'))
    #     self.label.setText(QtWidgets.QApplication.translate('Demo', 'Hello, World'))


class SettingsWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        # self.

        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.task_settings_button = QtWidgets.QPushButton("Task Settings")
        self.text = QtWidgets.QLabel("Hello World", alignment=QtCore.Qt.AlignCenter)
        self.layout = QtWidgets.QFormLayout(self)

        self.browser_path_label = QtWidgets.QLabel("Browser Executable:", alignment=QtCore.Qt.AlignLeft)
        self.browser_path_line_edit = QtWidgets.QLineEdit("input full path here")


        self.date_time_label = QtWidgets.QLabel("Start Date Time:")
        self.date_time_start = QtWidgets.QDateTimeEdit()


        self.layout.addWidget(self.text)
        self.layout.addRow(self.browser_path_label, self.browser_path_line_edit);
        self.layout.addRow(self.date_time_label, self.date_time_start)
        self.layout.addRow(self.task_settings_button)
        self.layout.addRow(self.cancel_button, self.save_button)

        self.task_settings_button.clicked.connect(self.showTaskSettings)
        self.cancel_button.clicked.connect(self.close)

    def showTaskSettings(self):
        self.taskSettingsWidget = TaskSettingsWidget()
        self.taskSettingsWidget.resize(800, 800)
        self.taskSettingsWidget.show()


class TaskSettingsWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.save_button = QtWidgets.QPushButton("Save")
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.mainTabWidget = QtWidgets.QTabWidget(self)

        # create overall tab
        self.general_widget = QtWidgets.QWidget()
        self.mainTabWidget.addTab(self.general_widget, "General")
        self.label_check_box = QtWidgets.QCheckBox("Shipping Labels")
        self.offer_respond_check_box = QtWidgets.QCheckBox("Respond To Offers")
        self.cancel_order_check_box = QtWidgets.QCheckBox("Cancel Order")
        self.sell_similar_check_box = QtWidgets.QCheckBox("Sell Similar")
        self.general_widget.layout = QtWidgets.QFormLayout(self.general_widget)
        self.general_widget.layout.addRow(self.label_check_box, self.offer_respond_check_box)
        self.general_widget.layout.addRow(self.cancel_order_check_box, self.sell_similar_check_box)

        # create label tab
        self.labels_widget = QtWidgets.QWidget()
        self.mainTabWidget.addTab(self.labels_widget, "Labels")
        self.labels_widget.layout = QtWidgets.QFormLayout(self.labels_widget)
        self.product_exclusion = QtWidgets.QTableWidget(8, 4)
        self.labels_widget.layout.addRow(self.product_exclusion)



        # create offers tab
        self.offers_widget = QtWidgets.QWidget()
        self.mainTabWidget.addTab(self.offers_widget, "Offers")

        self.layout = QtWidgets.QFormLayout(self)
        self.layout.addWidget(self.mainTabWidget)
        self.layout.addRow(self.cancel_button, self.save_button)
        self.cancel_button.clicked.connect(self.close)
