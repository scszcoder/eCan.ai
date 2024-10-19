from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QPushButton, QMainWindow, QFormLayout, QLineEdit, QCheckBox, QLabel, QComboBox, QApplication
import win32print
import subprocess
import re
import time
import traceback

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
        self.parent = parent
        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        # self.
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True
        try:
            self.list_wifi_networks()
            self.list_printers()

            self.mainWidget = QWidget()
            self.save_button = QPushButton("Save")
            self.cancel_button = QPushButton("Cancel")
            self.text = QLabel("Hello World", alignment=Qt.AlignCenter)

            self.layout = QFormLayout(self)

            self.browser_path_label = QLabel("Browser Executable:", alignment=Qt.AlignLeft)
            self.browser_path_line_edit = QLineEdit()
            self.browser_path_line_edit.setPlaceholderText("input full path here")

            default_printer = self.parent.get_default_printer()
            self.printer_label = QLabel("Printer:", alignment=Qt.AlignLeft)
            self.printer_line_edit = QLineEdit()
            self.printer_select = QComboBox()
            for role in [p[2] for p in self.printers]:
                self.printer_select.addItem(QApplication.translate("QComboBox", role))

            found_idx = next((i for i, p in enumerate([p[2] for p in self.printers]) if p == default_printer), -1)
            print("finding default printer", found_idx, default_printer, "among:", [p[2] for p in self.printers])
            if found_idx >= 0:
                self.printer_select.setCurrentIndex(found_idx)
            else:
                self.printer_select.setCurrentIndex(0)         #commander will be set if file based machine role is unknown
                self.default_printer = self.printer_select.currentText()

            self.printer_select.currentIndexChanged.connect(self.on_printer_selected)

            default_wifi = self.parent.get_default_wifi()
            self.wifi_label = QLabel("WiFi:", alignment=Qt.AlignLeft)
            self.wifi_select = QComboBox()
            self.wifi_line_edit = QLineEdit()
            self.wifi_pw_label = QLabel("WiFi:", alignment=Qt.AlignLeft)
            self.wifi_pw_line_edit = QLineEdit()
            for wifi in self.parent.wifis:
                self.wifi_select.addItem(QApplication.translate("QComboBox", wifi))

            found_idx = next((i for i, w in enumerate(self.parent.wifis) if w == default_wifi), -1)
            print("finding default wifi", found_idx, default_wifi, "among:", self.parent.wifis)
            if found_idx >= 0:
                self.wifi_select.setCurrentIndex(found_idx)
            else:
                self.wifi_select.setCurrentIndex(0)  # commander will be set if file based machine role is unknown
                self.default_wifi = self.wifi_select.currentText()

            self.wifi_select.currentIndexChanged.connect(self.on_wifi_selected)

            self.auto_schedule_cb = QCheckBox("Auto Schedule Mode")

            self.commander_run_cb = QCheckBox("Commander Self Run Tasks")
            self.overcapcity_warning_cb = QCheckBox("Warning If Over-capacity")
            self.overcapcity_force_cb = QCheckBox("Force Commander To Run If Over-capacity")

            self.num_vehicle_label = QLabel("Number Of Vehicles:")
            self.num_vehicle_text = QLineEdit()

            # self.layout.addWidget(self.text)
            self.layout.addRow(self.printer_label, self.printer_select)
            self.layout.addRow(self.wifi_label, self.wifi_select)
            self.layout.addRow(self.browser_path_label, self.browser_path_line_edit)
            self.layout.addRow(self.num_vehicle_label, self.num_vehicle_text)
            self.layout.addRow(self.auto_schedule_cb)
            self.layout.addRow(self.commander_run_cb)
            self.layout.addRow(self.overcapcity_warning_cb)
            self.layout.addRow(self.overcapcity_force_cb)
            self.layout.addRow(self.cancel_button, self.save_button)

            self.cancel_button.clicked.connect(self.close)
            self.save_button.clicked.connect(self.save_settings)


            self.mainWidget.setLayout(self.layout)
            self.setCentralWidget(self.mainWidget)
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorCheckCloudWorkQueue:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCheckCloudWorkQueue: traceback information not available:" + str(e)
            print(ex_stat)
    def save_settings(self):
        self.commander_run = (self.commander_run_cb.checkState() == Qt.Checked)
        self.overcapcity_warning = (self.overcapcity_warning_cb.checkState() == Qt.Checked)
        self.overcapcity_force = (self.overcapcity_force_cb.checkState() == Qt.Checked)
        self.parent.set_schedule_mode("auto" if self.auto_schedule_cb.checkState() == Qt.Checked else "manual")
        self.parent.set_default_wifi(self.wifi_select.currentText())
        self.parent.set_default_printer(self.printer_select.currentText())
        self.parent.saveSettings()
        self.close()

    def list_printers(self):
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        self.printers = printers
        print([p[2] for p in self.printers])

    def list_wifi_networks(self):
        for i in range(3):  # Try scanning multiple times
            # Run the command to list available Wi-Fi networks
            result = subprocess.run(["netsh", "wlan", "show", "networks"], capture_output=True, text=True)

            # Output the result
            networks_output = result.stdout

            # Use regular expression to find all SSID lines and extract SSID names
            ssid_list = re.findall(r"SSID \d+ : (.+)", networks_output)
            if ssid_list:
                print("Available Wi-Fi Networks (Scan {}):".format(i + 1))
                for ssid in ssid_list:
                    print(f"- {ssid}")
            else:
                print("No Wi-Fi networks found.")

        self.wifi_list = ssid_list

    def on_printer_selected(self):
        print("Index changed", self.printer_select.currentIndex())
        self.default_printer = self.printer_select.currentText()
        print("new printer selected: "+self.default_printer)


    def on_wifi_selected(self):
        print("Index changed", self.wifi_select.currentIndex())
        self.default_wifi = self.wifi_select.currentText()
        print("new wifi selected: "+self.default_wifi)
