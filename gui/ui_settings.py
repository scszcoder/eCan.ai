import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QPushButton, QMainWindow, QFormLayout, QLineEdit, QCheckBox, QLabel, QComboBox, QApplication
if sys.platform == "win32":
    import win32print
    import pywintypes
    import win32serviceutil
else:
    win32print = None
    pywintypes = None
    win32serviceutil = None
import subprocess
import re
import time
import traceback
import platform
import os
from utils.logger_helper import logger_helper as logger

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

def ensure_spooler_running():
    """Ensure printing backend is running on the current platform.

    - Windows: ensure Spooler service is running
    - Others: no-op
    """
    if sys.platform == "win32" and win32serviceutil is not None:
        try:
            status = win32serviceutil.QueryServiceStatus("Spooler")[1]
            if status != 4:
                win32serviceutil.StartService("Spooler")
                for _ in range(10):
                    time.sleep(0.5)
                    if win32serviceutil.QueryServiceStatus("Spooler")[1] == 4:
                        break
        except Exception:
            logger.error("Error ensuring spooler running: " + traceback.format_exc())
            pass
    else:
        return

def ensure_cups_running():
    """Ensure printing backend is running on the current platform.

    - macOS: ensure CUPS scheduler is running
    - Others: no-op
    """
    if sys.platform == "darwin":
        try:
            res = subprocess.run(["lpstat", "-r"], capture_output=True, text=True)
            if "not running" in (res.stdout or "").lower():
                # Best-effort start without sudo; may fail silently on restricted envs
                subprocess.run(["launchctl", "start", "org.cups.cupsd"], capture_output=True)
        except Exception:
            logger.error("Error ensuring cups running: " + traceback.format_exc())
            pass
    else:
        return

def win_list_printers(server: str | None = None, level: int = 2):
    """
    Enumerate printers. If `server` is None -> local; else enumerate on \\server.
    Retries once if the spooler isn't running (common cause of RPC 1722).
    """
    if server:
        server = r"\\" + server.lstrip("\\")   # ensure UNC
        flags = win32print.PRINTER_ENUM_NAME
        name  = server
    else:
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        name  = None

    def _enum():
        return win32print.EnumPrinters(flags, name, level)

    try:
        return _enum()
    except Exception as e:
        if sys.platform == 'win32' and pywintypes is not None and isinstance(e, pywintypes.error) and getattr(e, 'winerror', None) == 1722:
            try:
                win32serviceutil.StartService("Spooler")
            except Exception:
                pass
            time.sleep(1.0)
            return _enum()
        raise


def mac_list_printers():
    result = subprocess.run(['lpstat', '-p'], capture_output=True, text=True)
    printer_lines = result.stdout.strip().split('\n')
    printers = []
    for line in printer_lines:
        if line.startswith('printer'):
            printer_name = line.split(' ')[1]
            printers.append(printer_name)
    return printers

class SettingsWidget(QMainWindow):
    def __init__(self, parent):
        super(SettingsWidget, self).__init__(parent)
        self.parent = parent
        self.hello = ["Hallo Welt", "Hei maailma", "Hola Mundo", "Привет мир"]
        # self.
        self.commander_run = False
        self.overcapcity_warning = True
        self.overcapcity_force = True
        # Ensure printers attribute always exists to avoid AttributeError if enumeration fails
        self.printers = []
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
            if self.printers:
                for role in [p[2] for p in self.printers]:
                    self.printer_select.addItem(QApplication.translate("QComboBox", role))

                found_idx = next((i for i, p in enumerate([p[2] for p in self.printers]) if p == default_printer), -1)
                logger.info("finding default printer", found_idx, default_printer, "among:", [p[2] for p in self.printers])
                if found_idx >= 0:
                    self.printer_select.setCurrentIndex(found_idx)
                else:
                    # If default not found, select first available
                    self.printer_select.setCurrentIndex(0)
                    self.default_printer = self.printer_select.currentText()
            else:
                # No printers available; show a disabled placeholder
                placeholder = QApplication.translate("QComboBox", "No printers available")
                self.printer_select.addItem(placeholder)
                self.printer_select.setEnabled(False)
                self.default_printer = ""

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
            logger.info("finding default wifi", found_idx, default_wifi, "among:", self.parent.wifis)
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
                ex_stat = "ErrorSettingsWidgetInit:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSettingsWidgetInit: traceback information not available:" + str(e)
            logger.error(ex_stat)
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
        try:
            if platform.system() == 'Windows':
                # flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
                # printers = win32print.EnumPrinters(flags, None, 2)
                ensure_spooler_running()
                self.printers = win_list_printers()
            else:  # macOS
                ensure_cups_running
                self.printers = mac_list_printers()
                
            logger.info("Printers: " + str([p[2] for p in self.printers]))
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorListPrinters:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorListPrinters: traceback information not available:" + str(e)
            logger.error(ex_stat)
            # Ensure printers is defined even on failure
            self.printers = []

    def list_wifi_networks(self):
        for i in range(3):  # Try scanning multiple times
            # Run the command to list available Wi-Fi networks
            if platform.system() == 'Windows':
                result = subprocess.run(["netsh", "wlan", "show", "networks"], capture_output=True, text=True)
            else:  # macOS
                # First try to find the airport command
                airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport'
                if not os.path.exists(airport_path):
                    airport_path = '/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport'
                
                if os.path.exists(airport_path):
                    # Run airport command to scan for networks
                    result = subprocess.run([airport_path, '-s'], capture_output=True, text=True)
                    # Format output to match Windows netsh format
                    lines = result.stdout.strip().split('\n')[1:]  # Skip header
                    formatted_output = ""
                    for i, line in enumerate(lines, 1):
                        parts = line.split()
                        if parts:
                            formatted_output += f"SSID {i} : {parts[0]}\n"
                    result.stdout = formatted_output
                else:
                    # Fallback to networksetup command
                    result = subprocess.run(['networksetup', '-listpreferredwirelessnetworks', 'en0'], capture_output=True, text=True)
                    # Format output to match Windows netsh format
                    networks = [line.strip() for line in result.stdout.split('\n') if line.strip()]
                    formatted_output = ""
                    for i, network in enumerate(networks, 1):
                        formatted_output += f"SSID {i} : {network}\n"
                    result.stdout = formatted_output

            # Output the result
            networks_output = result.stdout

            # Use regular expression to find all SSID lines and extract SSID names
            ssid_list = re.findall(r"SSID \d+ : (.+)", networks_output)
            if ssid_list:
                logger.info("Available Wi-Fi Networks (Scan {}):".format(i + 1))
                for ssid in ssid_list:
                    logger.info(f"- {ssid}")
            else:
                logger.warning("No Wi-Fi networks found.")

        self.wifi_list = ssid_list

    def on_printer_selected(self):
        logger.info("Index changed", self.printer_select.currentIndex())
        self.default_printer = self.printer_select.currentText()
        logger.info("new printer selected: "+self.default_printer)


    def on_wifi_selected(self):
        logger.info("Index changed", self.wifi_select.currentIndex())
        self.default_wifi = self.wifi_select.currentText()
        logger.info("new wifi selected: "+self.default_wifi)
