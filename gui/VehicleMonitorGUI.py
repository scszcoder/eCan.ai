import json
import time
import random
from datetime import datetime
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QLabel, QScrollArea, QTextEdit,
    QProgressBar, QLineEdit
)

from bot.missions import TIME_SLOT_MINS, EBMISSION
from gui.tool.MainGUITool import StaticResource
from utils.logger_helper import logger_helper


class VehicleMonitorWin(QMainWindow):
    log_received = Signal(str)  # Signal to update the log console

    def __init__(self, main_win, vehicle=None):
        super(VehicleMonitorWin, self).__init__(main_win)
        self.static_resource = StaticResource()
        self.setWindowTitle("Vehicle Monitor")
        self.setGeometry(100, 100, 800, 500)

        self.mainwin = main_win
        self.vehicle = vehicle
        self.vehicles = self.mainwin.vehicles  # List of VEHICLE objects

        self.initUI()
        self.log_received.connect(self.appendLog)
        print("DEBUG: Signal connected!")  # ✅ Debug print

    def initUI(self):
        """Initialize UI layout and widgets."""
        main_widget = QWidget()
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # **LEFT PANE: Vehicle List (Scrollable)**
        self.vehicle_list = QListWidget()
        self.vehicle_list.addItems([v.getName() for v in self.vehicles])
        self.vehicle_list.itemClicked.connect(self.selectVehicle)
        left_pane = QScrollArea()
        left_pane.setWidgetResizable(True)
        left_pane.setWidget(self.vehicle_list)
        main_layout.addWidget(left_pane, 1)

        # **RIGHT PANE: Main Monitor Panel**
        self.right_pane = QWidget()
        right_layout = QVBoxLayout()
        self.right_pane.setLayout(right_layout)
        main_layout.addWidget(self.right_pane, 3)

        # **TOP: Progress Bar with Bot Animation**
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.bot_icon = QLabel()
        self.bot_icon.setPixmap(QIcon(self.mainwin.file_resource.bot_icon_path).pixmap(32, 32))  # Static icon
        right_layout.addWidget(QLabel("Progress:"))
        right_layout.addWidget(self.bot_icon)
        right_layout.addWidget(self.progress_bar)

        # **MIDDLE: Log Console**
        self.log_console = QTextEdit()
        self.log_console.setReadOnly(False)
        right_layout.addWidget(QLabel("Vehicle Logs:"))
        right_layout.addWidget(self.log_console)

        # **BOTTOM: Control Buttons & Command Input**
        button_layout = QHBoxLayout()
        self.btn_pause = QPushButton("Pause")
        self.btn_resume = QPushButton("Resume")
        self.btn_terminate = QPushButton("Terminate")
        self.btn_report = QPushButton("Report")
        button_layout.addWidget(self.btn_pause)
        button_layout.addWidget(self.btn_resume)
        button_layout.addWidget(self.btn_terminate)
        button_layout.addWidget(self.btn_report)
        right_layout.addLayout(button_layout)

        # **Command Input & Send Button**
        self.command_input = QLineEdit()
        self.send_button = QPushButton("Send Command")
        self.send_button.clicked.connect(self.sendCommand)
        right_layout.addWidget(QLabel("Send Command:"))
        right_layout.addWidget(self.command_input)
        right_layout.addWidget(self.send_button)

        # Timer for Progress Bar Animation
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self.updateProgress)

        self.addVehicles()

    def selectVehicle(self, item):
        """Switch view when a vehicle is selected."""
        vehicle_name = item.text()
        self.vehicle = next((v for v in self.vehicles if v.getName() == vehicle_name), None)
        self.log_console.append(f"Monitoring {vehicle_name}...")
        self.startProgress()

    def startProgress(self):
        """Start progress animation for vehicle execution."""
        if not self.vehicle:
            return
        self.progress_bar.setValue(0)
        self.progress_timer.start(100)  # Update every 100ms

    def updateProgress(self):
        """Animate the progress bar and update bot icon."""
        value = self.progress_bar.value()
        if value < 100:
            self.progress_bar.setValue(value + 5)
        else:
            self.progress_timer.stop()
            self.bot_icon.setPixmap(QIcon(self.mainwin.file_resource.bot_icon_path).pixmap(32, 32))

    def appendLog(self, msg):
        """Append log messages to the log console."""
        print(f"DEBUG: Received log in GUI: {msg}")  # ✅ Debug print
        if isinstance(msg, str):
            msgJS = json.loads(msg)
        else:
            msgJS = msg
        displayable = self.formDisplayable(msgJS)
        self.log_console.append(displayable)
        self.log_console.moveCursor(QTextCursor.MoveOperation.End)

    def sendCommand(self):
        """Send command to the selected vehicle."""
        if not self.vehicle:
            self.log_console.append("No vehicle selected!")
            return
        command = self.command_input.text().strip()
        if command:
            self.log_console.append(f">> {command}")
            self.command_input.clear()
            # TODO: Implement actual command sending logic

    def addVehicles(self):
        """Populate the left-side vehicle list with vehicles from self.mainwin.vehicles."""
        self.vehicle_list.clear()  # ✅ Clear existing items
        for vehicle in self.mainwin.vehicles:
            self.vehicle_list.addItem(vehicle.getName())  # ✅ Add each vehicle to the list


    # "chatID": so_chat_id,
    # "sender": "commander",
    # "receiver": self.user,
    # "type": "logs",
    # "contents": logmsg.replace('"', '\\"'),
    # # "contents": json.dumps({"msg": logmsg}).replace('"', '\\"'),
    #  "parameters": json.dumps(parameters)

    # contents will be in form of:
    # {"v": vehicle, "b":bid, "m":mid, "vstate": "running_idle/running_rpa/done/error",
    #   "step": step }
    def formDisplayable(self, msgJS):
        htmlMsg = ""

        logTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text_color = "color:#ff0000;"
        if "error" in msgJS["contents"]:
            text_color = "color:#ff0000;"
        elif "warn" in msgJS["contents"]:
            text_color = "color:#ff8000;"
        elif "info" in msgJS["contents"]:
            text_color = "color:#004800;"
        elif "debug" in msgJS["contents"]:
            text_color = "color:#90ffff;"
        else:
            text_color = "color:#608F80;"

        print("text color:", text_color)
        if msgJS['type'] == "logs":
            mc = msgJS['contents'].replace('\\"', '"')      # invers operation to recover the raw message
            # contents = f"<{mc['v']}>[{mc['vstate']}]B{mc['bid']}-M{mc['mid']}-{mc['progress']}%-Step#{mc['step']}::{mc['log_msg']}"

            ek = self.mainwin.generate_key_from_string(self.mainwin.main_key)
            decryptedWanMsgRaw = self.mainwin.decrypt_string(ek, mc)
        else:
            decryptedWanMsgRaw = msgJS['contents'].replace('\\"', '"')  # invers operation to recover the raw message
            # contents = f"<{mc['v']}>[{mc['vstate']}]B{mc['bid']}-M{mc['mid']}-{mc['progress']}%-Step#{mc['step']}::{mc['log_msg']}"
            contentsJson = json.loads(decryptedWanMsgRaw)
            vinfo = contentsJson["vehiclesInfo"]
            vstring = ""
            for v in vinfo:
                vstring = vstring + v["vname"]+"-"+v["vehicles_status"] + "; "
            # decryptedWanMsgRaw = json.dumps(contentsJson, indent=2).replace("\n", "<br>").replace("  ","&nbsp;&nbsp;")
            decryptedWanMsgRaw = vstring.replace("\n", "<br>")
        htmlMsg = """ 
            <div style="display: flex; padding: 5pt;">
                <span  style=" font-size:12pt; font-weight:450; margin-right: 40pt;"> 
                    %s |
                </span>
                <span style=" font-size:12pt; font-weight:450; %s;">
                    %s
                </span>
            </div>""" % (logTime, text_color, decryptedWanMsgRaw)

        return htmlMsg
