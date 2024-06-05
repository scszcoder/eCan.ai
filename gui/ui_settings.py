from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QPushButton, QMainWindow, QFormLayout, QLineEdit, QCheckBox, QLabel


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
# translator = QTranslator(app)
# translator.load('/usr/share/my_app/tr/qt_%s.qm' % locale[0])
# app.installTranslator(translator)


class SettingsWidget(QMainWindow):
    def __init__(self, parent):
        super(SettingsWidget, self).__init__(parent)

        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        # self.
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True

        self.mainWidget = QWidget()
        self.save_button = QPushButton("Save")
        self.cancel_button = QPushButton("Cancel")
        self.text = QLabel("Hello World", alignment=Qt.AlignCenter)

        self.layout = QFormLayout(self)

        self.browser_path_label = QLabel("Browser Executable:", alignment=Qt.AlignLeft)
        self.browser_path_line_edit = QLineEdit()
        self.browser_path_line_edit.setPlaceholderText("input full path here")

        self.commander_run_cb = QCheckBox("Commander Self Run Tasks")
        self.overcapcity_warning_cb = QCheckBox("Warning If Over-capacity")
        self.overcapcity_force_cb = QCheckBox("Force Commander To Run If Over-capacity")

        self.num_vehicle_label = QLabel("Number Of Vehicles:")
        self.num_vehicle_text = QLineEdit()

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
        self.commander_run = (self.commander_run_cb.checkState() == Qt.Checked)
        self.overcapcity_warning = (self.overcapcity_warning_cb.checkState() == Qt.Checked)
        self.overcapcity_force = (self.overcapcity_force_cb.checkState() == Qt.Checked)
