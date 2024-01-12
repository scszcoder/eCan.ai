import json

from PySide6.QtGui import QFont

from BotGUI import *
from MissionGUI import *
from ScheduleGUI import *
from PlatoonGUI import *
from SkillGUI import *

from ebbot import *
from inventories import *
from csv import reader
from signio import *
import platform
from os.path import exists
import webbrowser
from Cloud import *
from TrainGUI import *
from BorderLayout import *
import lzstring
from network import *
from LoggerGUI import *
from ui_settings import *
import schedule
from datetime import datetime, timedelta
import time
import pytz
import tzlocal
import TestAll
import sqlite3
from scraper import *
from pynput.mouse import Button, Controller
from genSkills import *
import importlib
import sys
import copy

from vehicles import *
from envi import *
from unittests import *
from SkillManagerGUI import *

START_TIME = 15      # 15 x 20 minute = 5 o'clock in the morning

Tzs = ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"]

rpaConfig = None
ecb_data_homepath = getECBotDataHome()

# adopted from web: https://stackoverflow.com/questions/32476006/how-to-make-an-expandable-collapsable-section-widget-in-qt
class Expander(QtWidgets.QWidget):
    def __init__(self, parent=None, title='', animationDuration=300):
        """
        References:
            # Adapted from PyQt4 version
            https://stackoverflow.com/a/37927256/386398
            # Adapted from c++ version
            https://stackoverflow.com/a/37119983/386398
        """
        super(Expander, self).__init__(parent=parent)

        self.animationDuration = animationDuration
        self.toggleAnimation = QtCore.QParallelAnimationGroup()
        self.contentArea =  QtWidgets.QScrollArea()
        self.headerLine =   QtWidgets.QFrame()
        self.toggleButton = QtWidgets.QToolButton()
        self.mainLayout =   QtWidgets.QGridLayout()

        toggleButton = self.toggleButton
        toggleButton.setStyleSheet("QToolButton { border: none; }")
        toggleButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toggleButton.setArrowType(QtCore.Qt.RightArrow)
        toggleButton.setText(str(title))
        toggleButton.setCheckable(True)
        toggleButton.setChecked(False)

        headerLine = self.headerLine
        headerLine.setFrameShape(QtWidgets.QFrame.HLine)
        headerLine.setFrameShadow(QtWidgets.QFrame.Sunken)
        headerLine.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)

        self.contentArea.setStyleSheet("QScrollArea { background-color: white; border: none; }")
        self.contentArea.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        # start out collapsed
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        # let the entire widget grow and shrink with its content
        toggleAnimation = self.toggleAnimation
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"minimumHeight"))
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self, b"maximumHeight"))
        toggleAnimation.addAnimation(QtCore.QPropertyAnimation(self.contentArea, b"maximumHeight"))
        # don't waste space
        mainLayout = self.mainLayout
        mainLayout.setVerticalSpacing(0)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        row = 0
        mainLayout.addWidget(self.toggleButton, row, 0, 1, 1, QtCore.Qt.AlignLeft)
        mainLayout.addWidget(self.headerLine, row, 2, 1, 1)
        row += 1
        mainLayout.addWidget(self.contentArea, row, 0, 1, 3)
        self.setLayout(self.mainLayout)

        def start_animation(checked):
            arrow_type = QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            direction = QtCore.QAbstractAnimation.Forward if checked else QtCore.QAbstractAnimation.Backward
            toggleButton.setArrowType(arrow_type)
            self.toggleAnimation.setDirection(direction)
            self.toggleAnimation.start()

        self.toggleButton.clicked.connect(start_animation)

    def setContentLayout(self, contentLayout):
        # Not sure if this is equivalent to self.contentArea.destroy()
        self.contentArea.destroy()
        self.contentArea.setLayout(contentLayout)
        collapsedHeight = self.sizeHint().height() - self.contentArea.maximumHeight()
        contentHeight = contentLayout.sizeHint().height()
        for i in range(self.toggleAnimation.animationCount()-1):
            expandAnimation = self.toggleAnimation.animationAt(i)
            expandAnimation.setDuration(self.animationDuration)
            expandAnimation.setStartValue(collapsedHeight)
            expandAnimation.setEndValue(collapsedHeight + contentHeight)
        contentAnimation = self.toggleAnimation.animationAt(self.toggleAnimation.animationCount() - 1)
        contentAnimation.setDuration(self.animationDuration)
        contentAnimation.setStartValue(0)
        contentAnimation.setEndValue(contentHeight)


# class MainWindow(QtWidgets.QWidget):
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, inTokens, tcpserver, ip, user, homepath, machine_role, lang):
        super(MainWindow, self).__init__()
        if homepath[len(homepath)-1] == "/":
            self.homepath = homepath[:len(homepath)-1]
        else:
            self.homepath = homepath
        print("HOME PATH is::", self.homepath)
        self.lang = lang
        self.tz = self.obtainTZ()
        self.bot_icon_path = self.homepath+'/resource/images/icons/c_robot64_0.png'
        self.mission_icon_path = self.homepath + '/resource/images/icons/c_mission96_1.png'
        self.skill_icon_path = self.homepath + '/resource/images/icons/skills_78.png'
        self.product_icon_path = self.homepath + '/resource/images/icons/product80_0.png'
        self.vehicle_icon_path = self.homepath + '/resource/images/icons/vehicle_128.png'
        self.commander_icon_path = self.homepath + '/resource/images/icons/general1_4.png'
        self.BOTS_FILE = self.homepath+"/resource/bots.json"
        self.MISSIONS_FILE = self.homepath+"/resource/missions.json"
        self.SELLER_INVENTORY_FILE = self.homepath+"/resource/inventory.json"
        self.session = set_up_cloud()
        self.tokens = inTokens
        self.machine_role = machine_role
        self.ip = ip
        if self.machine_role != "Platoon":
            self.tcpServer = tcpserver
            self.commanderXport = None
        else:
            print("This is a platoon...")
            self.commanderXport = tcpserver
            self.tcpServer = None
        self.user = user
        self.cog = None
        self.cog_client = None
        self.hostrole = machine_role
        self.workingState = "Idle"
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]
        self.platform = platform.system().lower()[0:2]
        self.std_item_font = QFont('Arial', 10)

        self.sellerInventoryJsonData = None
        self.botJsonData = None
        self.inventories = []

        # self.readBotJsonFile()
        self.readSellerInventoryJsonFile("")
        self.vehicles = []                      # computers on LAN that can carry out bots's tasks.， basically tcp transports
        self.bots = []
        self.missions = []              # mission 0 will always default to be the fetch schedule mission
        self.trMission = self.createTrialRunMission()
        self.skills = []
        self.missionsToday = []
        self.platoons = []
        self.products = []
        self.zipper = lzstring.LZString()
        self.threadPool = QtCore.QThreadPool()
        self.selected_row = -1
        self.BotNewWin = None
        self.missionWin = None
        self.trainNewSkillWin = None
        self.reminderWin = None
        self.platoonWin = None
        self.SkillManagerWin = None
        self.SettingsWin = SettingsWidget(self)
        self.netLogWin = CommanderLogWin(self)

        self.logConsoleBox = Expander(self, QtWidgets.QApplication.translate("QtWidgets.QWidget", "Log Console:"))
        self.commanderName = ""
        self.todaysReport = []
        self.todaysReports = []
        self.todaysPlatoonReports = []
        self.tester = TestAll.Tester()
        self.wifis = []
        self.dbfile = self.homepath + "/resource/data/myecb.db"
        print(self.dbfile)
        if (self.machine_role != "Platoon"):
            self.dbcon = sqlite3.connect(self.dbfile)

            # make sure designated tables exists in DB, if not create those tables.
            self.dbCursor = self.dbcon.cursor()

            # create tables.
            sql = 'CREATE TABLE IF NOT EXISTS bots (botid INTEGER PRIMARY KEY, owner TEXT, levels TEXT, gender TEXT, birthday TEXT, interests TEXT, location TEXT, roles TEXT, status TEXT, delDate TEXT, name TEXT, pseudoname TEXT, nickname TEXT, addr TEXT, shipaddr TEXT, phone TEXT, email TEXT, epw TEXT, backemail TEXT, ebpw TEXT)'
            #sql = '''ALTER TABLE bots RENAME TO junkbots0'''
            self.dbCursor.execute(sql)
            sql = 'SELECT * FROM bots'
            res = self.dbCursor.execute(sql)
            print("BOTS fetchall", res.fetchall())
            for column in res.description:
                print(column[0])
            #
            sql = 'CREATE TABLE IF NOT EXISTS  missions (mid INTEGER PRIMARY KEY, ticket INTEGER, botid INTEGER, status TEXT, createon TEXT, esd TEXT, ecd TEXT, asd TEXT, abd TEXT, aad TEXT, afd TEXT, acd TEXT, startt TEXT, esttime TEXT, runtime TEXT, cuspas TEXT, category TEXT, phrase TEXT, pseudoStore TEXT, pseudoBrand TEXT, pseudoASIN TEXT, type TEXT, config TEXT, skills TEXT, delDate TEXT, asin TEXT, store TEXT, brand TEXT, img TEXT, title TEXT, rating TEXT, customer TEXT, platoon TEXT, FOREIGN KEY(botid) REFERENCES bots(botid))'
            self.dbCursor.execute(sql)

            sql = 'CREATE TABLE IF NOT EXISTS  skills (skid INTEGER PRIMARY KEY, owner TEXT, platform TEXT, app TEXT, applink TEXT, site TEXT, sitelink TEXT, name TEXT, path TEXT, runtime TEXT, price_model TEXT, price INTEGER, privacy TEXT)'
            self.dbCursor.execute(sql)

        else:
            self.dbcon = None
            self.dbCursor = None

        # self.logConsoleBox = QtWidgets.QWidget()
        self.logConsole = QtWidgets.QTextEdit()
        self.logConsole.setLineWrapMode(QtWidgets.QTextEdit.FixedPixelWidth)
        self.logConsole.verticalScrollBar().setValue(self.logConsole.verticalScrollBar().minimum())
        self.logConsoleLayout = QtWidgets.QVBoxLayout()

        # self.logConsoleBox.setContentLayout(self.logConsoleLayout)

        # self.toggle_button = QtWidgets.QToolButton(
        #     text="log console", checkable=True, checked=False
        # )
        # self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        # self.toggle_button.setToolButtonStyle(
        #     QtCore.Qt.ToolButtonTextBesideIcon
        # )
        # self.toggle_button.setArrowType(QtCore.Qt.RightArrow)
        # self.toggle_button.pressed.connect(self.on_tg_pressed)

        # self.logConsoleLayout.addWidget(self.toggle_button)
        self.logConsoleLayout.addWidget(self.logConsole)
        # self.logConsoleBox.setLayout(self.logConsoleLayout)

        self.logConsoleBox.setContentLayout(self.logConsoleLayout)

        self.owner = "NA"
        self.botRank = "soldier"              # this should be read from a file which is written during installation phase, user will select this during installation phase

        self.save_all_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Save All"))
        self.log_out_button = QtWidgets.QPushButton(QtWidgets.QApplication.translate("QtWidgets.QPushButton", "Logout"))
        self.south_layout = QtWidgets.QVBoxLayout(self)
        self.south_layout.addWidget(self.logConsoleBox)
        self.bottomButtonsLayout = QtWidgets.QHBoxLayout(self)
        self.bottomButtonsLayout.addWidget(self.save_all_button)
        self.south_layout.addLayout(self.bottomButtonsLayout)
        self.bottomButtonsLayout.addWidget(self.log_out_button)
        self.save_all_button.clicked.connect(self.saveAll)
        self.log_out_button.clicked.connect(self.logOut)

        self.southWidget = QtWidgets.QWidget()
        self.southWidget.setLayout(self.south_layout)

        self.menuFont = QFont('Arial', 10)
        self.mainWidget = QtWidgets.QWidget()
        self.westScrollArea = QtWidgets.QWidget()
        self.westScrollLayout = QtWidgets.QVBoxLayout(self)
        self.westScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Missions:"), alignment=QtCore.Qt.AlignLeft)
        self.westScrollLabel.setFont(self.menuFont)

        self.centralScrollArea = QtWidgets.QWidget()
        self.centralScrollLayout = QtWidgets.QVBoxLayout(self)
        self.centralScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Bots:"), alignment=QtCore.Qt.AlignLeft)
        self.centralScrollLabel.setFont(self.menuFont)

        self.east0ScrollArea = QtWidgets.QWidget()
        self.east0ScrollLayout = QtWidgets.QVBoxLayout(self)
        if (self.machine_role == "Platoon"):
            self.east0ScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Running Missions:"), alignment=QtCore.Qt.AlignLeft)
        else:
            self.east0ScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Vehicles:"), alignment=QtCore.Qt.AlignLeft)
        self.east0ScrollLabel.setFont(self.menuFont)

        self.east1ScrollArea = QtWidgets.QWidget()
        self.east1ScrollLayout = QtWidgets.QVBoxLayout(self)

        self.east1ScrollLabel = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", "Completed Missions:"), alignment=QtCore.Qt.AlignLeft)
        self.east1ScrollLabel.setFont(self.menuFont)

        self.westScroll = QtWidgets.QScrollArea()
        self.centralScroll = QtWidgets.QScrollArea()
        self.east0Scroll = QtWidgets.QScrollArea()
        self.east1Scroll = QtWidgets.QScrollArea()

        self.westScrollLayout.addWidget(self.westScrollLabel)
        self.westScrollLayout.addWidget(self.westScroll)
        self.westScrollArea.setLayout(self.westScrollLayout)

        self.centralScrollLayout.addWidget(self.centralScrollLabel)
        self.centralScrollLayout.addWidget(self.centralScroll)
        self.centralScrollArea.setLayout(self.centralScrollLayout)

        self.east0ScrollLayout.addWidget(self.east0ScrollLabel)
        self.east0ScrollLayout.addWidget(self.east0Scroll)
        self.east0ScrollArea.setLayout(self.east0ScrollLayout)

        self.east1ScrollLayout.addWidget(self.east1ScrollLabel)
        self.east1ScrollLayout.addWidget(self.east1Scroll)
        self.east1ScrollArea.setLayout(self.east1ScrollLayout)

        self.westScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.westScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.westScroll.setWidgetResizable(True)

        self.centralScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.centralScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.centralScroll.setWidgetResizable(True)

        self.east0Scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east0Scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east0Scroll.setWidgetResizable(True)

        self.east1Scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east1Scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east1Scroll.setWidgetResizable(True)

        #creating QActions
        self.botNewAction = self._createBotNewAction()
        self.botGetAction = self._createGetBotsAction()
        self.saveAllAction = self._createSaveAllAction()
        self.botDelAction = self._createBotDelAction()
        self.botEditAction = self._createBotEditAction()
        self.botCloneAction = self._createBotCloneAction()
        self.botNewFromFileAction = self._createBotNewFromFileAction()

        self.missionNewAction = self._createMissionNewAction()
        self.missionDelAction = self._createMissionDelAction()
        self.missionEditAction = self._createMissionEditAction()
        self.missionImportAction = self._createMissionImportAction()
        self.missionNewFromFileAction = self._createMissionNewFromFileAction()

        self.settingsAccountAction = self._createSettingsAccountAction()
        self.settingsEditAction = self._createSettingsEditAction()

        self.runRunAllAction = self._createRunRunAllAction()
        self.runTestAllAction = self._createRunTestAllAction()

        self.scheduleCalendarViewAction = self._createScheduleCalendarViewAction()
        self.fetchScheduleAction = self._createFetchScheduleAction()
        self.scheduleFromFileAction = self._createScheduleNewFromFileAction()

        self.reportsShowAction = self._createReportsShowAction()
        self.reportsGenAction = self._createReportsGenAction()
        self.reportsLogConsoleAction = self._createReportsLogConsoleAction()

        self.skillNewAction = self._createSkillNewAction()
        self.skillManagerAction = self._createSkillManagerAction()
        self.skillDeleteAction = self._createSkillDeleteAction()
        self.skillShowAction = self._createSkillShowAction()
        self.skillUploadAction = self._createSkillUploadAction()

        self.skillNewFromFileAction = self._createSkillNewFromFileAction()


        self.helpUGAction = self._createHelpUGAction()
        self.helpCommunityAction = self._createHelpCommunityAction()
        self.helpMyAccountAction = self._createHelpMyAccountAction()
        self.helpAboutAction = self._createHelpAboutAction()

        self.popMenu = QtWidgets.QMenu(self)
        self.pop_menu_font = QtGui.QFont("Helvetica", 10)
        self.popMenu.setFont(self.pop_menu_font)

        self.popMenu.addAction(QtGui.QAction(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"), self))
        self.popMenu.addAction(QtGui.QAction(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"), self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QtGui.QAction(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"), self))

        self.botListView = BotListView()
        self.botListView.installEventFilter(self)
        self.botModel = QtGui.QStandardItemModel(self.botListView)

        self.missionListView = MissionListView()
        self.missionListView.installEventFilter(self)
        self.missionModel = QtGui.QStandardItemModel(self.missionListView)

        self.running_missionListView = MissionListView()
        self.runningMissionModel = QtGui.QStandardItemModel(self.running_missionListView)

        self.vehicleListView = PlatoonListView(self)
        self.vehicleListView.installEventFilter(self)
        self.runningVehicleModel = QtGui.QStandardItemModel(self.vehicleListView)

        self.skillListView = SkillListView(self)
        self.skillListView.installEventFilter(self)
        self.skillModel = QtGui.QStandardItemModel(self.skillListView)

        self.completed_missionListView = MissionListView()
        self.completedMissionModel = QtGui.QStandardItemModel(self.completed_missionListView)

        self.mtvViewAction = self._createMTVViewAction()
        # self.fieldMonitorAction = self._createFieldMonitorAction()
        self.commandSendAction = self._createCommandSendAction()

        # Apply the model to the list view
        self.botListView.setModel(self.botModel)
        self.botListView.setViewMode(QtWidgets.QListView.IconMode)
        self.botListView.setMovement(QtWidgets.QListView.Snap)

        self.skillListView.setModel(self.skillModel)
        self.skillListView.setViewMode(QtWidgets.QListView.IconMode)
        self.skillListView.setMovement(QtWidgets.QListView.Snap)

        self.mission0 = EBMISSION(self)
        self.missionModel.appendRow(self.mission0)
        self.missions.append(self.mission0)

        self.missionListView.setModel(self.missionModel)
        self.missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.missionListView.setMovement(QtWidgets.QListView.Snap)

        self.running_missionListView.setModel(self.runningMissionModel)
        self.running_missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.running_missionListView.setMovement(QtWidgets.QListView.Snap)

        self.vehicleListView.setModel(self.runningVehicleModel)
        self.vehicleListView.setViewMode(QtWidgets.QListView.ListMode)
        self.vehicleListView.setMovement(QtWidgets.QListView.Snap)

        self.completed_missionListView.setModel(self.completedMissionModel)
        self.completed_missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.completed_missionListView.setMovement(QtWidgets.QListView.Snap)

        centralWidget = DragPanel()

        if self.machine_role == "Platoon":
            self.botNewAction.setDisabled(True)
            self.saveAllAction.setDisabled(True)
            self.botDelAction.setDisabled(True)
            self.botEditAction.setDisabled(True)
            self.botCloneAction.setDisabled(True)
            self.botNewFromFileAction.setDisabled(True)

            self.missionNewAction.setDisabled(True)
            self.missionDelAction.setDisabled(True)
            self.missionEditAction.setDisabled(True)
            self.missionImportAction.setDisabled(True)
            self.missionNewFromFileAction.setDisabled(True)

            self.skillNewAction.setDisabled(True)
            self.skillEditAction.setDisabled(True)
            self.skillDeleteAction.setDisabled(True)
            self.skillShowAction.setDisabled(True)
            self.skillUploadAction.setDisabled(True)

            self.skillNewFromFileAction.setDisabled(True)


        # centralWidget.addBot(self.botListView)
        self.centralScroll.setWidget(self.botListView)


        #centralWidget.setPlainText("Central widget")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        self.centralSplitter = QtWidgets.QSplitter(Qt.Horizontal)
        self.bottomSplitter = QtWidgets.QSplitter(Qt.Vertical)



        # Because BorderLayout doesn't call its super-class addWidget() it
        # doesn't take ownership of the widgets until setLayout() is called.
        # Therefore we keep a local reference to each label to prevent it being
        # garbage collected too soon.
        #label_n = self.createLabel("North")
        # layout.addWidget(label_n, BorderLayout.North)
        self.menuBar = self._createMenuBar()
        self.mbWidget = QtWidgets.QWidget()
        self.mbLayout = QtWidgets.QVBoxLayout(self)
        #self.mbLayout.addWidget(menuBar)
        self.mbWidget.setLayout(self.mbLayout)

        # layout.addWidget(menuBar, BorderLayout.North)

        label_w = self.createLabel("West")

        self.westScroll.setWidget(self.missionListView)
        # layout.addWidget(self.westScroll, BorderLayout.West)
        #layout.addWidget(ic0, BorderLayout.West)

        if (self.machine_role == "Platoon"):
            self.east0Scroll.setWidget(self.running_missionListView)
            label_e1 = self.createLabel("Running Missions")
        else:
            self.east0Scroll.setWidget(self.vehicleListView)
            label_e1 = self.createLabel("Vehicles")
        # layout.addWidget(self.east0Scroll, BorderLayout.East)

        self.east1Scroll.setWidget(self.completed_missionListView)
        label_e2 = self.createLabel("Completed Missions")
        # layout.addWidget(self.east1Scroll, BorderLayout.East)

        label_s = self.createLabel("South")

        self.centralSplitter.addWidget(self.westScrollArea)
        self.centralSplitter.addWidget(self.centralScrollArea)
        self.centralSplitter.addWidget(self.east0ScrollArea)
        self.centralSplitter.addWidget(self.east1ScrollArea)

        self.bottomSplitter.addWidget(self.centralSplitter)
        self.bottomSplitter.addWidget(self.southWidget)

        #layout.addWidget(self.mbWidget)
        layout.addWidget(self.menuBar)
        layout.addWidget(self.bottomSplitter)
        #layout.addWidget(self.centralSplitter)
        #layout.addLayout(self.south_layout)


        self.mainWidget.setLayout(layout)
        self.setCentralWidget(self.mainWidget)

        self.setWindowTitle("Main Bot&Mission Scheduler")
        # ================= DONE with GUI ==============================

        self.checkVehicles()

        # get current wifi ssid and store it.
        print("OS platform: ", self.platform)
        if  self.platform=="win":
            wifi_info = subprocess.check_output(['netsh', 'WLAN', 'show', 'interfaces'])
            wifi_data = wifi_info.decode('utf-8')
            wifi_lines = wifi_data.split("\n")
            ssidline = [l for l in wifi_lines if " SSID" in l]
            if len(ssidline) == 1:
                ssid = ssidline[0].split(":")[1].strip()
                self.wifis.append(ssid)

        if (self.machine_role != "Platoon"):
            # load skills into memory.
            self.loadLocalBots()
            self.loadLocalMissions()

        # this will handle all skill bundled into software itself.
        self.loadLocalSkills()

        # Done with all UI stuff, now do the instruction set extension work.
        sk_extension_file = self.homepath + "/resource/skills/my/skill_extension.json"
        if os.path.isfile(sk_extension_file):
            with open(sk_extension_file, 'r') as sk_extension:
                addon = json.load(sk_extension)
                added_module_names = addon['modules']
                print("added module names:", added_module_names)
                added_module0 = importlib.import_module(added_module_names[0])
                vicrop_extension = getattr(added_module0, 'extended_vicrop')
                vicrop.update(vicrop_extension)

        # now hand daily tasks

        self.todays_work = {"tbd": [], "allstat": "working"}
        self.todays_completed = []
        if not self.hostrole == "Platoon":
            # For commander creates
            self.todays_work["tbd"].append({"name": "fetch schedule", "works": self.gen_default_fetch(), "status": "yet to start", "current tz": "eastern", "current grp": "other_works", "current bidx": 0, "current widx": 0, "current oidx": 0, "completed" : [], "aborted": []})
            # point to the 1st task to run for the day.
            self.updateRunStatus(self.todays_work["tbd"][0], 0)

    def getHomePath(self):
        return self.homepath


    def setCog(self, cog):
        self.cog = cog

    def setCogClient(self, client):
        self.cog_client = client

    def on_tg_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            QtCore.Qt.DownArrow if not checked else QtCore.Qt.RightArrow
        )

        if self.toggle_button.arrowType() == QtCore.Qt.DownArrow:
            self.logConsole.setVisible(True)
        else:
            self.logConsole.setVisible(False)

    def getWifis(self):
        return self.wifis

    #async def networking(self, platoonCallBack):
    def setHostRole(self, role):
        self.hostrole = role

    def getHostRole(self):
        return self.hostrole

    def appendNetLogs(self, msgs):
        # self.netLogWin.show()
        for msg in msgs:
            self.logConsole.append(msg)

    def setTokens(self, intoken):
        self.tokens = intoken

    def createLabel(self, text):
        label = QtWidgets.QLabel(QtWidgets.QApplication.translate("QtWidgets.QLabel", text))
        label.setFrameStyle(QtWidgets.QFrame.Box | QtWidgets.QFrame.Raised)
        return label

    def _createMenuBar(self):
        print("MAIN Creating Menu Bar")
        self.main_menu_bar_font = QtGui.QFont("Helvetica", 12)
        self.main_menu_font = QtGui.QFont("Helvetica", 10)

        menu_bar = QtWidgets.QMenuBar()
        menu_bar.setFont(self.main_menu_bar_font)
        # Creating menus using a QMenu object

        bot_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Bots"), self)
        bot_menu.setFont(self.main_menu_font)

        bot_menu.addAction(self.botNewAction)
        bot_menu.addAction(self.botGetAction)
        bot_menu.addAction(self.botEditAction)
        bot_menu.addAction(self.botCloneAction)
        bot_menu.addAction(self.botDelAction)
        bot_menu.addAction(self.botNewFromFileAction)
        menu_bar.addMenu(bot_menu)

        mission_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Missions"), self)
        mission_menu.setFont(self.main_menu_font)
        mission_menu.addAction(self.missionNewAction)
        mission_menu.addAction(self.missionImportAction)
        mission_menu.addAction(self.missionEditAction)
        mission_menu.addAction(self.missionDelAction)
        mission_menu.addAction(self.missionNewFromFileAction)
        menu_bar.addMenu(mission_menu)

        platoon_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Platoons"), self)
        platoon_menu.setFont(self.main_menu_font)
        platoon_menu.addAction(self.mtvViewAction)
        # platoon_menu.addAction(self.fieldMonitorAction)
        platoon_menu.addAction(self.commandSendAction)
        menu_bar.addMenu(platoon_menu)

        settings_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Settings"), self)
        settings_menu.setFont(self.main_menu_font)
        # settings_menu.addAction(self.settingsAccountAction)
        #settings_menu.addAction(self.settingsImportAction)
        settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(settings_menu)

        reports_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Reports"), self)
        reports_menu.setFont(self.main_menu_font)
        reports_menu.addAction(self.reportsShowAction)
        reports_menu.addAction(self.reportsGenAction)
        reports_menu.addAction(self.reportsLogConsoleAction)
        menu_bar.addMenu(reports_menu)

        run_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Run"), self)
        run_menu.setFont(self.main_menu_font)
        run_menu.addAction(self.runRunAllAction)
        run_menu.addAction(self.runTestAllAction)
        menu_bar.addMenu(run_menu)

        schedule_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Schedule"), self)
        schedule_menu.setFont(self.main_menu_font)
        schedule_menu.addAction(self.fetchScheduleAction)
        schedule_menu.addAction(self.scheduleCalendarViewAction)
        schedule_menu.addAction(self.scheduleFromFileAction)
        schedule_menu.setFont(self.main_menu_font)
        menu_bar.addMenu(schedule_menu)

        skill_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Skills"), self)
        skill_menu.setFont(self.main_menu_font)
        skill_menu.addAction(self.skillNewAction)
        skill_menu.addAction(self.skillManagerAction)
        # skill_menu.addAction(self.skillDeleteAction)
        # skill_menu.addAction(self.skillShowAction)
        # skill_menu.addAction(self.skillUploadAction)

        skill_menu.addAction(self.skillNewFromFileAction)
        menu_bar.addMenu(skill_menu)

        help_menu = QtWidgets.QMenu(QtWidgets.QApplication.translate("QtWidgets.QMenu", "&Help"), self)
        help_menu.setFont(self.main_menu_font)
        help_menu.addAction(self.helpUGAction)
        help_menu.addAction(self.helpCommunityAction)
        help_menu.addAction(self.helpMyAccountAction)

        help_menu.addAction(self.helpAboutAction)
        menu_bar.addMenu(help_menu)
        # Creating menus using a title
        #editMenu = menuBar.addMenu("&Edit")
        #helpMenu = menuBar.addMenu("&Help")
        return menu_bar

    def _createBotNewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&New"))
        new_action.triggered.connect(self.newBotGui)

        return new_action


    def _createBotNewFromFileAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&New From File"))
        new_action.triggered.connect(self.newBotFromFile)
        return new_action

    def _createGetBotsAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Load All Bots"))
        new_action.triggered.connect(self.getAllBotsFromCloud)
        # ew_action.connect(QtGui.QAction.)

        # new_action.connect(self.newBot)
        # self.newAction.setIcon(QtGui.QIcon(":file-new.svg"))
        # self.openAction = QtGui.QAction(QtGui.QIcon(":file-open.svg"), "&Open...", self)
        # self.saveAction = QtGui.QAction(QtGui.QIcon(":file-save.svg"), "&Save", self)
        # self.exitAction = QtGui.QAction("&Exit", self)
        return new_action

    def _createSaveAllAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Save All"))
        new_action.triggered.connect(self.saveAll)
        return new_action

    def _createBotDelAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Remove"))
        return new_action

    def _createBotEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        return new_action

    def _createBotCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createBotEnDisAbleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Disable"))
        return new_action

    def _createMissionNewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Create"))
        new_action.triggered.connect(self.newMissionView)

        return new_action

    def _createMTVViewAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Vehicles View"))
        new_action.triggered.connect(self.newVehiclesView)

        return new_action


    def _createFieldMonitorAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Field Monitor"))
        #new_action.triggered.connect(self.newMissionView)

        return new_action


    def _createCommandSendAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Send Command"))
        # new_action.triggered.connect(lambda: self.sendToPlatoons("7000", None))
        cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
        new_action.triggered.connect(lambda: self.sendToPlatoons([], cmd))

        return new_action


    def _createMissionDelAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete M"))
        return new_action


    def _createMissionImportAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Import"))
        return new_action


    def _createMissionEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        return new_action

    def _createMissionNewFromFileAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&New From File"))
        new_action.triggered.connect(self.newMissionFromFile)
        return new_action



    def _createSettingsAccountAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Account"))
        return new_action

    def _createSettingsEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
        new_action.triggered.connect(self.editSettings)
        return new_action


    def _createRunRunAllAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Run All"))
        new_action.triggered.connect(self.manualRunAll)
        return new_action

    def _createRunTestAllAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Run All Tests"))
        new_action.triggered.connect(self.runAllTests)
        return new_action


    def _createScheduleCalendarViewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Calendar View"))
        new_action.triggered.connect(self.scheduleCalendarView)
        return new_action


    def _createFetchScheduleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Fetch Schedules"))
        new_action.triggered.connect(lambda: self.fetchSchedule("", None))
        return new_action


    def _createScheduleNewFromFileAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Test Schedules From File"))
        new_action.triggered.connect(self.fetchScheduleFromFile)
        return new_action

    def _createReportsShowAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&View"))
        return new_action

    def _createReportsGenAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Generate"))
        return new_action

    def _createReportsLogConsoleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Log Console"))
        new_action.triggered.connect(self.showLogs)
        return new_action

    def _createSettingsGenAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Generate"))
        return new_action

    # after click, should pop up a windows to ask user to choose from 3 options
    # start from scratch, start from template, start by interactive show and learn tip bubble "most popular".
    def _createSkillNewAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Create New"))
            new_action.triggered.connect(self.trainNewSkill)
            return new_action

    def _createSkillManagerAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Manager"))
            new_action.triggered.connect(self.showSkillManager)
            return new_action

    def _createSkillDeleteAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
            return new_action

    def _createSkillShowAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Show All"))
            return new_action

    def _createSkillUploadAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Upload Skill"))
            new_action.triggered.connect(self.uploadSkill)
            return new_action

    def _createSkillNewFromFileAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&New From File"))
        new_action.triggered.connect(self.newSkillFromFile)
        return new_action

    def _createHelpUGAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&User Guide"))
        return new_action


    def _createHelpCommunityAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Community"))
        new_action.triggered.connect(self.gotoForum)
        return new_action

    def _createHelpMyAccountAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&My Account"))
        new_action.triggered.connect(self.gotoMyAccount)
        return new_action

    def _createHelpAboutAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&About"))
        new_action.triggered.connect(self.showAbout)
        return new_action

    def showLogs(self):
        self.netLogWin.show()

    def findIndex(self, list, element):
        try:
            index_value = list.index(element)
        except ValueError:
            index_value = -1
        return index_value


    def test_scroll(self):
        mouse = Controller()
        print("testing scrolling....")
        url = 'https://www.amazon.com/s?k=yoga+mats&crid=2Y3M8P4537BWF&sprefix=%2Caps%2C331&ref=nb_sb_ss_recent_1_0_recent'
        webbrowser.open(url, new=0, autoraise=True)
        time.sleep(8)
        mouse.scroll(0, -25)
        #pyautogui.scroll(-500)
        # time.sleep(5)
        # pyautogui.scroll(-500)
        # time.sleep(5)
        # pyautogui.scroll(500)
        # time.sleep(5)
        # pyautogui.scroll(500)
        print("done testing....")

    def runAllTests(self):
        print("running all test suits.")
        htmlfile = 'C:/temp/pot.html'
        # self.test_scroll()

        test_api(self.session, self.tokens['AuthenticationResult']['IdToken'])

        #the grand test,
        # 1) fetch today's schedule.
        # result = self.fetchSchedule("5000", None)            # test case for chrome etsy seller task automation.
        # result = self.fetchSchedule("4000", None)            # test case for ads power ebay seller task automation.
        # result = self.fetchSchedule("6000", None)            # test case for chrome amz seller task automation.

        # ===================
        # 2) run all tasks, with bot profile loading on ADS taken care of....

        #configAMZWalkSkill("", None)
        #amz_buyer_fetch_product_list(htmlfile)


        # this will generate a local skill file to run, the input the skill data structure
        # which contains the configuration part which comes from cloud scheduling API.
        # testskfile = self.homepath + "../testdata/testsk.json"
        # testmissionfile = homepath + "../testdata/testmission.json"
        # with open(testskfile, 'rb') as skfp:
        #     testsk = json.load(skfp)
        #     skillDS = WORKSKILL("browse_search")
        #     skillDS.loadJson(testsk)
        #
        #     with open(testmissionfile, 'rb') as mfp:
        #         testmission = json.load(mfp)
        #         print("TEST MISSION:", testmission)
        #         print(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        #         missionDS = EBMISSION(self)
        #         missionDS.loadJson(testmission)
        #         print("test json LOADED!!!!")
        #         steps2brun = configAMZWalkSkill(0, missionDS, testsk, self.homepath)
        #         print("steps GENERATED!!!!")
        #         #generated
        #         #step_keys = readSkillFile(testsk.getName(), testsk.get_run_steps_file())
        #         print("steps READ AND LOADED!!!!")
        #
        #         runAllSteps(steps2brun, missionDS, skillDS)
        #
        #     mfp.close()
        # skfp.close()


    # this function fetches schedule and assign work based on fetch schedule results...
    def fetchSchedule(self, ts_name, settings):
        fetch_stat = "Completed:0"
        try:
            jresp = send_schedule_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], ts_name, settings)
            if "errorType" in jresp:
                screen_error = True
                print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
            else:
                # first, need to decompress the body.
                # very important to use compress and decompress on Base64
                uncompressed = self.zipper.decompressFromBase64(jresp["body"])
                # uncompressed = jresp["body"]
                print("decomppressed response:", uncompressed, "!")
                if uncompressed != "":
                    # print("body string:", uncompressed, "!", len(uncompressed), "::")
                    bodyobj = json.loads(uncompressed)
                    # bodyobj = uncompressed

                    # body object will be a list of task groups[
                    # {
                    # "eastern": [{
                    #       bid : 0,
                    #       tz : "eastern",
                    #       bw_works : [{
                    #           mid : 0,
                    #           name: "",
                    #           cuspas : "",
                    #           todos : null,
                    #           start_time : null
                    #       }],
                    #       other_works : [],
                    # }...],
                    # "central": [],
                    # "mountain": [],
                    # "pacific": [],
                    # "alaska": [],
                    # "hawaii": []
                    #}, ....
                    #]
                    # each task is a json, { skill steps. [...]
                    # each step is a json
                    ##print("resp body: ", bodyobj)
                    #if len(bodyobj.keys()) > 0:
                        #jbody = json.loads(jresp["body"])
                        #jbody = json.loads(originalS)

                    print("bodyobj: ", json.dumps(bodyobj))
                    if len(bodyobj) > 0:
                        self.updateMissions(bodyobj)
                        self.assignWork(bodyobj["task_groups"])
                        self.logDailySchedule(uncompressed)
                    else:
                        self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO schedule generated."))
                else:
                    self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: Empty Network Response."))

            if len(self.todays_work["tbd"]) > 0:
                self.todays_work["tbd"][0]["status"] = fetch_stat
            else:
                print("WARNING!!!! no work TBD after fetching schedule...")

        # ni is already incremented by processExtract(), so simply return it.
        except:
            print("ERROR EXCEPTION:")
            fetch_stat = "ErrorFetchSchedule:" + jresp["errorType"]

        return fetch_stat

    def fetchScheduleFromFile(self):

        uncompressed = open(self.homepath + "/resource/testdata/testschedule.json")
        if uncompressed != "":
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            bodyobj = json.load(uncompressed)
            if len(bodyobj) > 0:
                self.assignWork(bodyobj)
                self.logDailySchedule(uncompressed)
            else:
                self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO schedule generated."))
        else:
            self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: Empty Network Response."))

    def warn(self, msg):
        warnText = "<span style=\" font-size:12pt; font-weight:300; color:#ff0000;\" >"
        warnText += msg
        warnText += "</span>"
        # self.netLogWin.appendLogs([warnText])
        self.appendNetLogs([warnText])
        self.appendDailyLogs([msg])


    def showMsg(self, msg):
        MsgText = "<span style=\" font-size:12pt; font-weight:300; color:#ff0000;\" >"
        MsgText += msg
        MsgText += "</span>"
        # self.netLogWin.appendLogs([MsgText])
        self.appendNetLogs([MsgText])
        self.appendDailyLogs([msg])

    def appendDailyLogs(self, msgs):
        #check if daily log file exists, if exists simply append to it, if not create and write to the file.
        now = datetime.datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        print("homepath:::", self.homepath)
        dailyLogDir = ecb_data_homepath + "/runlogs/{}".format(year)
        dailyLogFile = ecb_data_homepath + "/runlogs/{}/log{}{}{}.txt".format(year, year, month, day)
        print("daily log file:::", dailyLogFile)

        if os.path.isfile(dailyLogFile):
            file1 = open(dailyLogFile, "a")  # append mode
            for msg in msgs:
                file1.write(msg+"\n")
            file1.close()
        else:
            if not os.path.exists(dailyLogDir):
                os.makedirs(dailyLogDir)

            file1 = open(dailyLogFile, "w")  # append mode
            for msg in msgs:
                file1.write(msg + "\n")
            file1.close()


    def logDailySchedule(self, netSched):
        now = datetime.datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dailyScheduleLogFile = ecb_data_homepath + "/runlogs/{}/schedule{}{}{}.txt".format(year, month, day, year)
        print("netSched:: ", netSched)
        if os.path.isfile(dailyScheduleLogFile):
            file1 = open(dailyScheduleLogFile, "a")  # append mode
            file1.write(json.dumps(netSched) + "\n=====================================================================\n")
            file1.close()
        else:
            file1 = open(dailyScheduleLogFile, "w")  # write mode
            file1.write(json.dumps(netSched) + "\n=====================================================================\n")
            file1.close()

    def saveDailyRunReport(self, runStat):
        now = datetime.datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dailyRunReportFile = ecb_data_homepath + "/runlogs/{}/runreport{}{}{}.txt".format(year, month, day, year)

        if os.path.isfile(dailyRunReportFile):
            with open(dailyRunReportFile, 'a') as f:

                f.write(json.dumps(runStat) + "\n")

                f.close()
        else:
            with open(dailyRunReportFile, 'w') as f:

                f.write(json.dumps(runStat) + "\n")

                f.close()


    def fill_mission(self, blank_m, m, tgs):
        blank_m.loadNetRespJson(m)
        mconfig = None
        for tz_group in tgs:
            for tz in tz_group:
                if len(tz_group[tz]) > 0:
                    for bot_works in tz_group[tz]:
                        for bw in bot_works["bw_works"]:
                            if m["mid"] == bw["mid"]:
                                # now add this mission to the list.
                                print("found a bw mission matching mid....", bw["mid"])
                                mconfig = bw["config"]
                                break
                        if mconfig:
                            break

                        for ow in bot_works["other_works"]:
                            if m["mid"] == ow["mid"]:
                                # now add this mission to the list.
                                print("found a other mission matching mid....", ow["mid"])
                                mconfig = ow["config"]
                                break
                        if mconfig:
                            break
                if mconfig:
                    break
            if mconfig:
                break

        blank_m.setConfig(mconfig)

    # after fetching today's schedule, update missions data structure since some walk/buy routine will be created.
    # as well as some daily routines.... will be generated either....
    def updateMissions(self, resp_data):
        # for each received work mission, check whether they're in the self.missions already, if not, create them and
        # add to the missions list.
        task_groups = resp_data["task_groups"]
        added_missions = resp_data["added_missions"]
        # for tz_group in task_groups:
        #     for tz in tz_group:
        #         if len(tz_group[tz]) > 0:
        #             for bot_works in tz_group[tz]:
        #                 for bw in bot_works["bw_works"]:
        #                     if not any(m.getMid() == bw["mid"] for m in self.missions):
        #                         # now add this mission to the list.
        #                         print("adding a BW mission....", bw["mid"])
        #                         new_mission = EBMISSION(self)
        #                         new_mission.setMid(bw["mid"])
        #                         skid = [0]
        #                         new_mission.setSkills(skid)
        #                         self.missions.append(new_mission)
        #                 for ow in bot_works["other_works"]:
        #                     if not any(m.getMid() == ow["mid"] for m in self.missions):
        #                         # now add this mission to the list.
        #                         print("adding a Other mission....", ow["mid"])
        #                         new_mission = EBMISSION(self)
        #                         new_mission.setMid(ow["mid"])
        #                         skid = [0]
        #                         new_mission.setSkills(skid)
        #                         self.missions.append(new_mission)

        for m in added_missions:
            new_mission = EBMISSION(self)
            self.fill_mission(new_mission, m, task_groups)
            self.missions.append(new_mission)
            print("adding mission....")

    def getBotByID(self, bid):
        found_bot = None
        for bot in self.bots:
            if bot.getBid() == bid:
                found_bot = bot
                break
        return found_bot

    def getMissionByID(self, mid):
        found_mission = None
        for mission in self.missions:
            if mission.getMid() == mid:
                found_mission = mission
                break
        return found_mission

    def formBotsString(self, botids):
        result = "["
        for bid in botids:
            # result = result + json.dumps(self.getBotByID(bid).genJson()).replace('"', '\\"')
            result = result + json.dumps(self.getBotByID(bid).genJson())

            if bid != botids[-1]:
                result = result + ","
        result = result + "]"
        print("BOT STRING:", result)
        return result

    def formMissionsString(self, mids):
        result = "["
        for mid in mids:
            # result = result + json.dumps(self.getMissionByID(mid).genJson()).replace('"', '\\"')
            result = result + json.dumps(self.getMissionByID(mid).genJson())

            if mid != mids[-1]:
                result = result + ","
        result = result + "]"
        print("MISSIONS STRING:", result)
        return result

    def formBotsMissionsString(self, botids, mids):
        # result = "{\"bots\": " + self.formBotsString(botids) + ",\"missions\": " + self.formMissionsString(mids) + "}"
        result = "\"bots\": " + self.formBotsString(botids) + ",\"missions\": " + self.formMissionsString(mids) + ""

        # junk = json.loads(result)
        return result


    def getAllBotidsMidsFromTaskGroup(self, task_group):
        bids = []
        mids = []
        for key, value in task_group.items():
            if isinstance(value, list) and len(value) > 0:
                for assignment in value:
                    bids.append(assignment["bid"])
                    for work in assignment["bw_works"]:
                        mids.append(work["mid"])
                    for work in assignment["other_works"]:
                        mids.append(work["mid"])
        print("bids in the task group::", bids)
        print("mids in the task group::", mids)
        return bids, mids

    # assign work, if this commander runs, assign works for commander,
    # otherwise, send works to platoons to execute.
    def assignWork(self, task_groups):
        # tasks should already be sorted by botid,
        nsites = 0
        if len(task_groups) > 0:
            if self.hostrole == "CommanderOnly":
                nsites = len(fieldLinks)
                print("commander only machine [", nsites, "]")
            else:
                nsites = 1 + len(fieldLinks)
                print("commander can run.....[", nsites, "]")

            tg_botids, tg_mids = self.getAllBotidsMidsFromTaskGroup(task_groups[0])
            resource_string = self.formBotsMissionsString(tg_botids, tg_mids)
            print("test code here.....", resource_string)

        if len(task_groups) > nsites:
            # there will be unserved tasks due to over capacity
            print("Run Capacity Spilled, some tasks will NOT be served!!!")
            self.netLogWin.appendLogs("Run Capacity Spilled, some tasks will NOT be served!!!")

        # distribute work to all available sites, which is the limit for the total capacity.
        if nsites > 0:
            for i in range(nsites):
                if i == 0 and not self.hostrole == "CommanderOnly":
                    # if commander participate work, give work to here.
                    print("arranged for today on this machine....")
                    self.todays_work["tbd"].append({"name": "automation", "works": task_groups[0], "status": "yet to start", "current tz": "pacific", "current grp": "bw_works", "current bidx": 0, "current widx": 0, "current oidx": 0, "competed": [], "aborted": []})
                else:
                    #otherwise, send work to platoons in the field.
                    if self.hostrole == "CommanderOnly":
                        print("cmd only sending to platoon: ", i)
                        task_group_string = json.dumps(task_groups[i]).replace('"', '\\"')
                        self.todays_work["tbd"].append(
                            {"name": "automation", "works": task_groups[i], "ip": fieldLinks[i]["ip"][0], "status": "yet to start",
                             "current tz": "pacific", "current grp": "bw_works", "current bidx": 0, "current widx": 0,
                             "current oidx": 0, "competed": [], "aborted": []})

                    else:
                        print("cmd sending to platoon: ", i)
                        task_group_string = json.dumps(task_groups[i+1]).replace('"', '\\"')
                        self.todays_work["tbd"].append(
                            {"name": "automation", "works": task_groups[i+1], "ip": fieldLinks[i]["ip"][0], "status": "yet to start",
                             "current tz": "pacific", "current grp": "bw_works", "current bidx": 0, "current widx": 0,
                             "current oidx": 0, "competed": [], "aborted": []})

                    # now need to fetch this task associated bots, mission, skills
                    # get all bots IDs involved. get all mission IDs involved.
                    tg_botids, tg_mids = self.getAllBotidsMidsFromTaskGroup(task_groups[i])
                    resource_string = self.formBotsMissionsString(tg_botids, tg_mids)
                    schedule = '{\"cmd\":\"reqSetSchedule\", \"todos\":\"' + task_group_string + '\", ' + resource_string + '}'
                    print("SCHEDULE:::", schedule)

                    fieldLinks[i]["link"].transport.write(schedule.encode("utf-8"))

        # now that a new day starts, clear all reports data structure
        self.todaysReports = []

    # find to todos.,
    # 1) check whether need to fetch schedules,
    # 2) checking whether need to do RPA
    # the key data structure is self.todays_work["tbd"] which should be an array of either 1 or 2 elements.
    # either 1 or 2 elements depends on the role, if commander_only or platoon, will be 1 element,
    # if commander (which means commander can do tasks too) then there will be 2 elements.
    # in case of 1 element, it will be the actuall bot tasks to be done for platton or the fetch schedule task for Comander Only.
    # in case of 2 elements, the 0th element will be the fetch schedule, the 1st element will be the bot tasks(as a whole)
    # self.todays_work = {"tbd": [], "allstat": "working"}
    def checkToDos(self):
        print("checking todos......", self.todays_work["tbd"])
        nextrun = None
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.datetime.now()
        if len(self.todays_work["tbd"]) > 0:
            if ("Completed" not in self.todays_work["tbd"][0]["status"]) and (self.todays_work["tbd"][0]["name"] == "fetch schedule"):
                # in case the 1st todos is fetch schedule
                if self.ts2time(self.todays_work["tbd"][0]["works"]["eastern"][0]["other_works"][0]["start_time"]) < pt:
                    nextrun = self.todays_work["tbd"][0]
            elif "Completed" not in self.todays_work["tbd"][0]["status"]:
                # in case the 1st todos is an automation task.
                print("self.todays_work[\"tbd\"][0] :", self.todays_work["tbd"][0])
                tz = self.todays_work["tbd"][0]["current tz"]

                bith = self.todays_work["tbd"][0]["current bidx"]

                # determin next task group:
                current_bw_idx = self.todays_work["tbd"][0]["current widx"]
                current_other_idx = self.todays_work["tbd"][0]["current oidx"]

                if current_bw_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"]):
                    current_bw_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"][current_bw_idx]["start_time"]
                else:
                    # just give it a huge number so that, this group won't get run
                    current_bw_start_time = 1000

                if current_other_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["other_works"]):
                    current_other_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["other_works"][current_other_idx]["start_time"]
                else:
                    # in case, all just give it a huge number so that, this group won't get run
                    current_other_start_time = 1000

                # if a buy-walk task is scheduled earlier than other tasks, arrange the buy-walk task, otherwise arrange other works.
                if current_bw_start_time < current_other_start_time:
                    grp = "bw_works"
                    wjth = current_bw_idx
                elif current_bw_start_time > current_other_start_time:
                    grp = "other_works"
                    wjth = current_other_idx
                else:
                    # if both gets 1000 value, that means there is nothing to run.
                    grp = ""
                    wjth = -1

                self.todays_work["tbd"][0]["current grp"] = grp


                print("tz: ", tz, "bith: ", bith, "grp: ", grp, "wjth: ", wjth)

                if wjth >= 0:
                    if self.ts2time(self.todays_work["tbd"][0]["works"][tz][bith][grp][wjth]["start_time"]) < pt:
                        print("next run is now set up......")
                        nextrun = self.todays_work["tbd"][0]


        return nextrun

    def findMissonsToBeRetried(self, todos):
        retryies = copied_dict = copy.deepcopy(todos)
        for key1, value1 in todos.items():
            # regions
            if isinstance(value1, dict):
                for key2, value2 in value1.items():
                    # botids
                    if isinstance(value2, dict):
                        for key3, value3 in value2.items():
                            # groups
                            if isinstance(value3, dict):
                                for key4, value4 in value3.items():
                                    # missions
                                    if isinstance(value4, dict):
                                        if "Completed" in value4["status"]:
                                            junk = retryies[key1][key2][key3].pop(key4)

        #now point to the 1st item in this todo list

        print("MISSIONS needs retry:", retryies)
        return retryies

    def flatten_todos(self, todos):
        all_missions = {}
        for key1, value1 in todos.items():
            # regions
            if isinstance(value1, dict):
                for key2, value2 in value1.items():
                    # botids
                    if isinstance(value2, dict):
                        for key3, value3 in value2.items():
                            # groups
                            if isinstance(value3, dict):
                                all_missions.update(value3)
        return all_missions


    def loadSkillFile(self, skname, pub):
        #slap on a file path prefix, then read in the file.
        skillsubnames = skname.split("_")
        actionname = ''.join(skillsubnames[2:len(skillsubnames)])
        if pub:
            skill_file = self.homepath + "resource/skills/public/" + skname + "/scripts/" + skname + ".psk"
        else:
            skill_file = self.homepath + "resource/skills/my/" + skname + "/scripts/" + skname + ".psk"

        print("loadSKILLFILE: ", skill_file)
        stepKeys = readSkillFile(skname, skill_file, lvl=0)

        return stepKeys


    # run one bot one time slot at a time，for 1 bot and 1 time slot, there should be only 1 mission running
    def runRPA(self, worksTBD):
        global rpaConfig
        global skill_code

        all_done = False
        worksettings = getWorkSettings(self, worksTBD)
        print("worksettings: mid, bid", worksettings["botid"], worksettings["mid"])

        rpaScripts = []

        # generate walk skills on the fly.
        running_mission = self.missions[worksettings["midx"]]
        rpaSkillIdWords = running_mission.getSkills().split(",")
        rpaSkillIds = [int(skidword.strip()) for skidword in rpaSkillIdWords]

        print("rpaSkillIds:", rpaSkillIds, type(rpaSkillIds[0]), "running mission id:", running_mission.getMid())

        # get skills data structure by IDs
        print("all skills ids:", [sk.getSkid() for sk in self.skills])
        relevant_skills = [sk for sk in self.skills if sk.getSkid() in rpaSkillIds]
        relevant_skill_ids = [sk.getSkid() for sk in self.skills if sk.getSkid() in rpaSkillIds]
        print("relevant skills ids:", relevant_skill_ids)

        if len(relevant_skill_ids) < len(rpaSkillIds):
            s = set(relevant_skill_ids)
            missing = [x for x in rpaSkillIds if x not in s]
            print("ERROR: Required Skills not found:", missing)
        else:
            ordered_relevant_skills = sorted(relevant_skills, key=lambda x: rpaSkillIds.index(x.getSkid()))

        all_skill_codes = []
        for sk in ordered_relevant_skills:
            print("settingSKKKKKKKK: ", sk.getSkid(), sk.getName())
            setWorkSettingsSkill(worksettings, sk)
            # print("settingSKKKKKKKK: ", json.dumps(worksettings, indent=4))
            genSkillCode(worksettings, first_step, "light")

            all_skill_codes.append({"ns": worksettings["name_space"], "skfile": worksettings["skfname"]})

        print("all_skill_codes: ", all_skill_codes)


        rpa_script = prepRunSkill(all_skill_codes)
        print("generated psk:", rpa_script)

        rpaScripts.append(rpa_script)
        print("rpaScripts:[", len(rpaScripts), "] ", rpaScripts)

        #now run the steps
        for script in rpaScripts:
            # (steps, mission, skill, mode="normal"):
            # it_items = (item for i, item in enumerate(self.skills) if item.getSkid() == rpaSkillIds[0])
            # print("it_items: ", it_items)
            # for it in it_items:
            #     print("item: ", it.getSkid())
            # running_skill = next((item for i, item in enumerate(self.skills) if item.getSkid() == int(rpaSkillIds[0])), -1)
            # print("running skid:", rpaSkillIds[0], "len(self.skills): ", len(self.skills), "skill 0 skid: ", self.skills[0].getSkid())
            # print("running skill: ", running_skill)
            runResult = runAllSteps(script, self.missions[worksettings["midx"]], relevant_skills[0])
            if runResult.split(":")[0] != "Completed":
                # some thing is wrong.... simply exit and claim this mission execution failed.
                break

        # finished 1 mission, update status and update pointer to the next one on the list.... and be done.
        # the timer tick will trigger the run of the next mission on the list....
        self.update1MStat(worksettings["midx"], runResult)
        self.updateRunStatus(worksTBD, worksettings["midx"])

        return worksettings["botid"], worksettings["midx"], runResult


    def update1MStat(self, midx, result):
        print("1 mission run completed.")
        self.missions[midx].setStatus(result)
        retry_count = self.missions[midx].getRetry()
        if retry_count > 0:
            self.missions[midx].setRetry(retry_count - 1)

    def updateRunStatus(self, worksTBD, midx):

        works = worksTBD["works"]

        tz = worksTBD["current tz"]
        grp = worksTBD["current grp"]
        bidx = worksTBD["current bidx"]
        widx = worksTBD["current widx"]
        oidx = worksTBD["current oidx"]
        switch_tz = False
        switch_grp = False
        switch_bot = False
        if grp == "other_works":
            idx = oidx
        else:
            idx = widx

        this_stat = self.missions[midx].getStatus()

        print("TZ:", tz, "GRP:", grp, "BIDX:", bidx, "WIDX:", widx, "OIDX:", oidx, "THIS STATUS:", this_stat)

        if "Completed" in this_stat:
            # check whether need to switch group?
            if grp == None:
                # just the begining....
                tzi = 0
                switch_tz = True
            else:
                # update after already started
                if len(works[tz]) > 0:
                    if grp == "other_works":
                        if len(works[tz][bidx][grp])-1 > oidx:
                            oidx = oidx + 1
                        else:
                            # all other_works are done. simply go to the next bw_works if there are more
                            # simply switch group
                            grp = "bw_works"
                            # but if no more work after switching grp, switch timezone.
                            if len(works[tz][bidx][grp]) > 0:
                                if widx > len(works[tz][bidx][grp])-1:
                                    if bidx < len(works[tz]) - 1:
                                        bidx = bidx + 1
                                        switch_bot = True
                                    else:
                                        # in case this is the last bot, then switch timezone.
                                        switch_tz = True
                                else:
                                    switch_grp = True
                                    widx = widx + 1
                            else:
                                # all other_works and bw_works of this region(timezone) are done, check to see whether to switch bot.
                                if bidx < len(works[tz])-1:
                                    bidx = bidx + 1
                                    switch_bot = True
                                else:
                                    # in case this is the last bot, then switch timezone.
                                    switch_tz = True
                    else:
                        # bw works
                        if len(works[tz][bidx][grp])-1 > widx:
                            widx = widx + 1
                        else:
                            # all walk-buy works are done. simply go to the next other_works  if there are more
                            grp = "other_works"
                            if len(works[tz][bidx][grp]) > 0:
                                if oidx > len(works[tz][bidx][grp])-1:
                                    if bidx < len(works[tz]) - 1:
                                        bidx = bidx + 1
                                        switch_bot = True
                                    else:
                                        # switch tz.
                                        switch_tz = True
                                else:
                                    switch_grp = True
                                    oidx = oidx + 1
                            else:
                                if bidx < len(works[tz])-1:
                                    bidx = bidx + 1
                                    switch_bot = True
                                else:
                                    # switch tz.
                                    switch_tz = True
                    # now compare time.
                    if switch_tz == False:
                        if switch_bot == False:
                            if switch_grp == False:
                                if works[tz][bidx]["other_works"][oidx]["start_time"] < works[tz][bidx]["bw_works"][widx]["start_time"]:
                                    worksTBD["current grp"] = "other_works"
                                else:
                                    worksTBD["current grp"] = "bw_works"
                            else:
                                worksTBD["current grp"] = grp
                        else:
                            # if bot is changed, oidx and widx restart from 0.
                            oidx = 0
                            widx = 0
                            print("SWITCHED BOT:", bidx)
                            if len(works[tz][bidx]["other_works"]) > 0 and len(works[tz][bidx]["bw_works"]) > 0:
                                if works[tz][bidx]["other_works"][oidx]["start_time"] < works[tz][bidx]["bw_works"][widx][
                                    "start_time"]:
                                    worksTBD["current grp"] = "other_works"
                                else:
                                    worksTBD["current grp"] = "bw_works"
                            elif len(works[tz][bidx]["other_works"]) > 0:
                                worksTBD["current grp"] = "other_works"
                            else:
                                worksTBD["current grp"] = "bw_works"

                        worksTBD["current bidx"] = bidx
                        worksTBD["current widx"] = widx
                        worksTBD["current oidx"] = oidx
                        worksTBD["current tz"] = tz
                else:
                    switch_tz = True

            # check whether need to switch region?
            if switch_tz:
                tzi = Tzs.index(tz)
                while tzi < len(Tzs) and len(works[tz]) == 0:
                    tzi = tzi + 1

                if tzi < len(Tzs):
                    tz = Tzs[tzi]
                    print("SWITCHED TZ:", tz)
                    if len(works[tz][bidx]["other_works"]) > 0 and len(works[tz][bidx]["bw_works"]) > 0:
                        # see which one's start time is earlier
                        if works[tz][bidx]["other_works"][0]["start_time"] < works[tz][bidx]["bw_works"][0]["start_time"]:
                            worksTBD["current grp"] = "other_works"
                            worksTBD["current bidx"] = 0
                            worksTBD["current widx"] = -1
                            worksTBD["current oidx"] = 0
                        else:
                            worksTBD["current grp"] = "bw_works"
                            worksTBD["current bidx"] = 0
                            worksTBD["current widx"] = 0
                            worksTBD["current oidx"] = -1
                    elif len(works[tz][bidx]["other_works"]) > 0:
                        worksTBD["current grp"] = "other_works"
                        worksTBD["current bidx"] = 0
                        worksTBD["current widx"] = -1
                        worksTBD["current oidx"] = 0
                    elif len(works[tz][bidx]["bw_works"]) > 0:
                        worksTBD["current grp"] = "bw_works"
                        worksTBD["current bidx"] = 0
                        worksTBD["current widx"] = 0
                        worksTBD["current oidx"] = -1

                else:
                    # already reached the last region in this todo group, consider this group done.
                    # now check whether there is any failed missions, if there is, now it's time to set
                    # up to re-run it, simply by set the pointers to it.
                    print("all workdsTBD exhausted...")
                    rt_tz, rt_bid, rt_grp, rt_mid = self.findNextMissonsToBeRetried(worksTBD)
                    if rt_tz == "":
                        # if nothing is found, we're done with this todo list...
                        worksTBD["status"] == "Completed"
                    else:
                        # now set the pointer to the next mission that needs to be retried....
                        tz = rt_tz
                        worksTBD["current grp"] = rt_grp
                        worksTBD["current bidx"] = int(rt_bid)
                        if rt_grp == "bw_works":
                            worksTBD["current widx"] = int(rt_mid)
                            worksTBD["current oidx"] = 0
                        else:
                            worksTBD["current oidx"] = int(rt_mid)
                            worksTBD["current widx"] = 0

        worksTBD["current tz"] = tz


    def findNextMissonsToBeRetried(self, workgroup):
        found = False
        works = workgroup["works"]
        while not found:
            tz = workgroup["current tz"]
            grp = workgroup["current grp"]
            bidx = workgroup["current bidx"]
            widx = workgroup["current widx"]
            oidx = workgroup["current oidx"]

            switch_tz = False
            switch_grp = False
            switch_bot = False

            # check whether need to switch group?
            if grp == None:
                # just the begining....
                tzi = 0
                switch_tz = True
            else:
                # update after already started
                if len(works[tz]) > 0:
                    if grp == "other_works":
                        if len(works[tz][bidx][grp]) - 1 > oidx:
                            oidx = oidx + 1
                        else:
                            # all other_works are done. simply go to the next bw_works if there are more
                            # simply switch group
                            grp = "bw_works"
                            # but if no more work after switching grp, switch timezone.
                            if len(works[tz][bidx][grp]) > 0:
                                if widx > len(works[tz][bidx][grp]) - 1:
                                    if bidx < len(works[tz]) - 1:
                                        bidx = bidx + 1
                                        switch_bot = True
                                    else:
                                        # in case this is the last bot, then switch timezone.
                                        switch_tz = True
                                else:
                                    switch_grp = True
                                    widx = widx + 1
                            else:
                                # all other_works and bw_works of this region(timezone) are done, check to see whether to switch bot.
                                if bidx < len(works[tz]) - 1:
                                    bidx = bidx + 1
                                    switch_bot = True
                                else:
                                    # in case this is the last bot, then switch timezone.
                                    switch_tz = True
                    else:
                        # bw works
                        if len(works[tz][bidx][grp]) - 1 > widx:
                            widx = widx + 1
                        else:
                            # all walk-buy works are done. simply go to the next other_works  if there are more
                            grp = "other_works"
                            if len(works[tz][bidx][grp]) > 0:
                                if oidx > len(works[tz][bidx][grp]) - 1:
                                    if bidx < len(works[tz]) - 1:
                                        bidx = bidx + 1
                                        switch_bot = True
                                    else:
                                        # switch tz.
                                        switch_tz = True
                                else:
                                    switch_grp = True
                                    oidx = oidx + 1
                            else:
                                if bidx < len(works[tz]) - 1:
                                    bidx = bidx + 1
                                    switch_bot = True
                                else:
                                    # switch tz.
                                    switch_tz = True
                    # now compare time.
                    if switch_tz == False:
                        if switch_bot == False:
                            if switch_grp == False:
                                if works[tz][bidx]["other_works"][oidx]["start_time"] < \
                                        works[tz][bidx]["bw_works"][widx]["start_time"]:
                                    workgroup["current grp"] = "other_works"
                                else:
                                    workgroup["current grp"] = "bw_works"
                            else:
                                workgroup["current grp"] = grp
                        else:
                            # if bot is changed, oidx and widx restart from 0.
                            oidx = 0
                            widx = 0
                            if works[tz][bidx]["other_works"][oidx]["start_time"] < \
                                    works[tz][bidx]["bw_works"][widx][
                                        "start_time"]:
                                workgroup["current grp"] = "other_works"
                            else:
                                workgroup["current grp"] = "bw_works"

                        workgroup["current bidx"] = bidx
                        workgroup["current widx"] = widx
                        workgroup["current oidx"] = oidx
                        workgroup["current tz"] = tz
                else:
                    switch_tz = True

            # check whether need to switch region?
            if switch_tz:
                tzi = Tzs.index(tz)
                while tzi < len(Tzs) and len(works[tz]) == 0:
                    tzi = tzi + 1

                if tzi < len(Tzs):
                    tz = Tzs[tzi]
                    if len(works[tz][bidx]["other_works"]) > 0 and len(works[tz][bidx]["bw_works"]) > 0:
                        # see which one's start time is earlier
                        if works[tz][bidx]["other_works"][0]["start_time"] < works[tz][bidx]["bw_works"][0][
                            "start_time"]:
                            workgroup["current grp"] = "other_works"
                            workgroup["current bidx"] = 0
                            workgroup["current widx"] = -1
                            workgroup["current oidx"] = 0
                        else:
                            workgroup["current grp"] = "bw_works"
                            workgroup["current bidx"] = 0
                            workgroup["current widx"] = 0
                            workgroup["current oidx"] = -1
                    elif len(works[tz][bidx]["other_works"]) > 0:
                        workgroup["current grp"] = "other_works"
                        workgroup["current bidx"] = 0
                        workgroup["current widx"] = -1
                        workgroup["current oidx"] = 0
                    elif len(works[tz][bidx]["bw_works"]) > 0:
                        workgroup["current grp"] = "bw_works"
                        workgroup["current bidx"] = 0
                        workgroup["current widx"] = 0
                        workgroup["current oidx"] = -1
                else:
                    # this is the case we have reach the last mission of the todo list...
                    tz, bid, grp, mid  = self.findFirstMissonsToBeRetried(works)
                    if tz == "":
                        # in such a case there is nothing to retry. consider it done....
                        found = True
                        workgroup["status"] = "Completed"
                    else:
                        workgroup["current tz"] = tz
                        workgroup["current bidx"] = bid
                        workgroup["current grp"] = grp
                        if grp == "bw_works":
                            workgroup["current widx"] = mid
                        else:
                            workgroup["current oidx"] = mid

            workgroup["current tz"] = tz

            if grp == "other_works":
                idx = oidx
            else:
                idx = widx

            mission_id = works[tz][bidx][grp][idx]["mid"]
            midx = next((i for i, mission in enumerate(self.missions) if str(mission.getMid()) == mission_id), -1)
            this_stat = self.missions[midx].getStatus()
            n_retries = self.missions[midx].getRetry()
            if "Completed" not in this_stat and n_retries > 0:
                found = True


    # go thru all todos to find the first mission that's incomplete and retry count is not down to 0 yet.
    def findFirstMissonsToBeRetried(self, todos):
        found = False
        mid = grp = bid = tz = ""
        for key1, value1 in todos.items():
            # regions
            if isinstance(value1, dict):
                for key2, value2 in value1.items():
                    # botids
                    if isinstance(value2, dict):
                        for key3, value3 in value2.items():
                            # groups
                            if isinstance(value3, dict):
                                mid = 0
                                for item in value3.items():
                                    # missions
                                    mission_id = item["mid"]
                                    midx = next((i for i, mission in enumerate(self.missions) if str(mission.getMid()) == mission_id), -1)
                                    this_stat = self.missions[midx].getStatus()
                                    n_retry = self.missions[midx].getRetry()
                                    if "Completed" not in this_stat and n_retry > 0:
                                        found = True
                                        grp = key3
                                        bid = key2
                                        tz = key1
                                        break
                                    else:
                                        mid = mid + 1
                            if found:
                                break
                    if found:
                        break
            if found:
                break
        #now point to the 1st item in this todo list

        print("MISSIONS needs retry:", tz, bid, grp, mid)
        return tz, bid, grp, mid




    #convert time zone, time slot to datetime
    # the time slot is defined as following:
    # time slot is defined as a 20 minute interval, an entire day has 72 slots indexed 0~71
    # counting timezone, and starts from eastern standard time, the timezone will extend to
    # cover hawaii, which is 5 timezone away from eastern, so total time zone slots are
    # 72+15=87 or index 0~86.
    def ts2time(self, ts):
        thistime = datetime.datetime.now()
        zerotime = datetime.datetime(thistime.date().year, thistime.date().month, thistime.date().day, 0, 0, 0)
        time_change = timedelta(minutes=20*ts)
        runtime = zerotime + time_change
        return runtime


    def runBotTask(self, task):
        self.workingState = "Working"
        task_mission = self.missions[task.mid]
        # run all the todo steps
        # (steps, mission, skill, mode="normal"):
        runResult = runAllSteps(task.todos, task_mission.parent_settings)


    def showAbout(self):
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "E-Commerce Bots. \n (V1.0 2024-01-12 AIPPS LLC) \n"))
        # msgBox.setInformativeText("Do you want to save your changes?")
        # msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        # msgBox.setDefaultButton(QMessageBox.Save)
        ret = msgBox.exec()


    def gotoForum(self):
        url="https://www.maipps.com/forum.html"
        webbrowser.open(url, new=0, autoraise=True)

    def gotoMyAccount(self):
        url="https://www.maipps.com/my.html"
        webbrowser.open(url, new=0, autoraise=True)

    def newBotGui(self):
        # Logic for creating a new bot:
        # pop out a new windows for user to set parameters for a new bot.
        # at the moment, just add an icon.
        #new_bot = EBBOT(self)
        #new_icon = QtGui.QIcon((":file-open.svg"))
        #self.centralWidget.setText("<b>File > New</b> clicked")
        if self.BotNewWin == None:
            self.BotNewWin = BotNewWin(self)
        self.BotNewWin.show()


    def trainNewSkill(self):
        if self.trainNewSkillWin == None:
            self.trainNewSkillWin = TrainNewWin(self)
            self.reminderWin = ReminderWin(self)
        print("train new skill....")
        #self.trainNewSkillWin.resize(200, 200)
        self.trainNewSkillWin.show()
        #rem = ReminderWin(self)
        #rem.show()
        self.trainNewSkillWin.set_cloud(self.session, self.tokens)


    def saveAll(self):
        # Logic for creating a new bot:
        self.saveBotJsonFile()
        self.writeMissionJsonFile()
        self.wirteSkillJsonFiles()
        self.saveRunReports()


    def logOut(self):
        print("logging out........")
        # result = self.cog_client.global_sign_out(self.cog.access_token)
        #result = self.cog_client.global_sign_out(AccessToken=self.cog.access_token)
        result = self.cog.logout()

        print("logged out........", result)
        # now should close the main window and bring back up the login screen?


    def addNewBot(self, new_bot):
        # Logic for creating a new bot:
        print("adding a .... new... bot")
        self.bots.append(new_bot)
        self.botModel.appendRow(new_bot)
        api_bots = [{
            "bid": new_bot.getBid(),
            "owner": self.owner,
            "roles": new_bot.getRoles(),
            "pubbirthday": new_bot.getPubBirthday(),
            "gender": new_bot.getGender(),
            "location": new_bot.getLocation(),
            "levels": new_bot.getLevels(),
            "birthday": new_bot.getBirthdayTxt(),
            "interests": new_bot.getInterests(),
            "status": new_bot.getStatus(),
            "delDate": new_bot.getInterests(),
            "name": new_bot.getName(),
            "pseudoname": new_bot.getPseudoName(),
            "nickname": new_bot.getNickName(),
            "addr": new_bot.getInterests(),
            "shipaddr": new_bot.getInterests(),
            "phone": new_bot.getPhone(),
            "email": new_bot.getEmail(),
            "epw": new_bot.getEmPW(),
            "backemail": new_bot.getBackEm(),
            "ebpw": new_bot.getAcctPw()
        }]
        jresp = send_add_bots_request_to_cloud(self.session, api_bots, self.tokens['AuthenticationResult']['IdToken'])



        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            #now that add is successfull, update local file as well.

            sql = 'CREATE TABLE IF NOT EXISTS bots (botid INTEGER PRIMARY KEY, owner TEXT, levels TEXT, gender TEXT, birthday TEXT, interests TEXT, location TEXT, roles TEXT, status TEXT, delDate TEXT, name TEXT, pseudoname TEXT, nickname TEXT, addr TEXT, shipaddr TEXT, phone TEXT, email TEXT, epw TEXT, backemail TEXT, ebpw TEXT)'

            # now add bot to local DB.
            for newbot in jbody:
                sql = ''' INSERT INTO bots(botid, owner, levels, gender, birthday, interests, location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr, phone, email, epw, backemail, ebpw)
                              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
                data_tuple = (api_bots[0]["bid"], api_bots[0]["owner"], api_bots[0]["levels"], api_bots[0]["gender"], api_bots[0]["birthday"], \
                              api_bots[0]["interests"], api_bots[0]["location"], api_bots[0]["roles"], api_bots[0]["status"], api_bots[0]["delDate"], \
                              api_bots[0]["name"], api_bots[0]["pseudoname"], api_bots[0]["nickname"], api_bots[0]["addr"], api_bots[0]["shipaddr"], \
                              api_bots[0]["phone"], api_bots[0]["email"], api_bots[0]["epw"], api_bots[0]["backemail"], api_bots[0]["ebpw"])

                self.dbCursor.execute(sql, data_tuple)

            #update self data structure and save in json file for easy access (1 line of python code)
            self.saveBotJsonFile(jbody)


    def updateABot(self, abot):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        jresp = {"body": []}
        api_bots = [{
            "bid": abot.getBid(),
            "owner": self.owner,
            "roles": abot.getRoles(),
            "pubbirthday": abot.getPubBirthday(),
            "gender": abot.getGender(),
            "location": abot.getLocation(),
            "levels": abot.getLevels(),
            "birthday": abot.getBirthdayTxt(),
            "interests": abot.getInterests(),
            "status": abot.getStatus(),
            "delDate": abot.getInterests(),
            "name": abot.getName(),
            "pseudoname": abot.getPseudoName(),
            "nickname": abot.getNickName(),
            "addr": abot.getInterests(),
            "shipaddr": abot.getInterests(),
            "phone": abot.getPhone(),
            "email": abot.getEmail(),
            "epw": abot.getEmPW(),
            "backemail": abot.getBackEm(),
            "ebpw": abot.getAcctPw()
        }]
        jresp = send_update_bots_request_to_cloud(self.session, api_bots, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])

            #update local DB
            for updatedbot in jbody:
                sql = ''' Update bots (owner = ?, levels = ?, gender = ?, birthday = ?, interests = ?, location = ?, roles = ?,
                        status = ?, delDate = ?, name = ?, pseudoname = ?, nickname = ?, addr = ?, shipaddr = ?, phone = ?, 
                        email = ?,  epw = ?, backemail = ?, ebpw = ? where botid = ?; '''

                data_tuple = (api_bots[0]["bid"], api_bots[0]["owner"], api_bots[0]["levels"], api_bots[0]["gender"], api_bots[0]["birthday"], \
                              api_bots[0]["interests"], api_bots[0]["location"], api_bots[0]["roles"], api_bots[0]["status"], api_bots[0]["delDate"], \
                              api_bots[0]["name"], api_bots[0]["pseudoname"], api_bots[0]["nickname"], api_bots[0]["addr"], api_bots[0]["shipaddr"], \
                              api_bots[0]["phone"], api_bots[0]["email"], api_bots[0]["epw"], api_bots[0]["backemail"], api_bots[0]["ebpw"] )

                self.dbCursor.execute(sql, data_tuple)

            #now that add is successfull, update local file as well.
            self.saveBotJsonFile()

    def addNewMission(self, new_mission):
        # Logic for creating a new mission:
        print("adding a .... new... mission")
        self.missions.append(new_mission)
        self.missionModel.appendRow(new_mission)
        api_missions = [{
            "mid": new_mission.getMid(),
            "ticket": new_mission.getMid(),
            "botid": new_mission.getBid(),
            "owner": self.owner,
            "status": new_mission.getStatus(),
            "createon": new_mission.getBD(),
            "esd": new_mission.getEsd(),
            "ecd": new_mission.getEcd(),
            "asd": new_mission.getAsd(),
            "abd": new_mission.getAbd(),
            "aad": new_mission.getAad(),
            "afd": new_mission.getAfd(),
            "acd": new_mission.getAcd(),
            "startt": new_mission.getActualStartTime(),
            "esttime": new_mission.getEstimatedStartTime(),
            "runtime": new_mission.getRunTime(),
            "cuspas": new_mission.getCusPAS(),
            "search_cat": new_mission.getSearchCat(),
            "search_kw": new_mission.getSearchKW(),
            "pseudo_store": new_mission.getPseudoStore(),
            "pseudo_brand": new_mission.getPseudoBrand(),
            "pseudo_asin": new_mission.getPseudoASIN(),
            "repeat": new_mission.getRepeat(),
            "mtype": new_mission.getMtype(),
            "mconfig": new_mission.getConfig(),
            "skills": new_mission.getSkills(),
            "delDate": new_mission.getDelDate(),
            "asin": new_mission.getASIN(),
            "store": new_mission.getStore(),
            "brand": new_mission.getBrand(),
            "image": new_mission.getImagePath(),
            "title": new_mission.getTitle(),
            "rating": new_mission.getRating(),
            "customer": new_mission.getCustomerID(),
            "platoon": new_mission.getPlatoonID()
        }]
        jresp = send_add_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            # now that delete is successfull, update local file as well.
            self.writeMissionJsonFile()

            #add to local DB
            sql = ''' INSERT INTO missions(mid, ticket, owner, botid, status, createon, esd, ecd, asd, abd, aad, afd, acd, startt, esttime, runtime, 
                    cuspas, category, phrase, pseudoStore, pseudoBrand, pseudoASIN, type, config, skills, delDate, asin, store, brand, img, 
                    title, rating, customer, platoon) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
            data_tuple = (api_missions[0]["mid"], api_missions[0]["ticket"], api_missions[0]["owner"], api_missions[0]["botid"], api_missions[0]["status"], api_missions[0]["createon"], \
                          api_missions[0]["esd"], api_missions[0]["ecd"], api_missions[0]["asd"], api_missions[0]["abd"], api_missions[0]["aad"], \
                          api_missions[0]["afd"], api_missions[0]["acd"], api_missions[0]["startt"], api_missions[0]["esttime"], api_missions[0]["runtime"], \
                          api_missions[0]["cuspas"], api_missions[0]["category"], api_missions[0]["phrase"], api_missions[0]["pseudoStore"], \
                          api_missions[0]["pseudoBrand"], api_missions[0]["pseudoASIN"], api_missions[0]["type"], api_missions[0]["config"], \
                          api_missions[0]["skills"], api_missions[0]["delDate"], api_missions[0]["asin"], api_missions[0]["store"], api_missions[0]["brand"], \
                          api_missions[0]["img"], api_missions[0]["title"], api_missions[0]["rating"], api_missions[0]["customer"], api_missions[0]["platoon"])
            self.dbCursor.execute(sql, data_tuple)

    def updateAMission(self, amission):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        jresp = {"body": []}
        api_missions = [{
            "bid": amission.getBid(),
            "owner": self.owner,
            "role": amission.getRole(),
            "age": amission.getAge(),
            "gender": amission.getGender(),
            "location": amission.getLocation(),
            "interests": amission.getInterests()
        }]
        api_missions = [amission]
        jresp = send_update_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])

            #update local DB
            sql = ''' Update missions(ticket = ?, botid = ?, owner = ?, status = ?, createon = ?, esd = ?, ecd = ?, asd = ?, abd = ?, 
                    aad = ?, afd = ?, acd = ?, startt = ?, esttime = ?, runtime = ?, cuspas = ?, category = ?, phrase = ?, 
                    pseudoStore = ?, pseudoBrand = ?, pseudoASIN = ?, type = ?, config = ?, skills = ?, delDate = ?, 
                    asin = ?, store = ?, brand = ?, img = ?, title = ?, rating = ?, customer = ?, platoon = ? where mid = ?; '''
            data_tuple = (
            api_missions[0]["mid"], api_missions[0]["ticket"], api_missions[0]["botid"], api_missions[0]["status"], api_missions[0]["createon"], \
            api_missions[0]["esd"], api_missions[0]["ecd"], api_missions[0]["asd"], api_missions[0]["abd"], api_missions[0]["aad"], \
            api_missions[0]["afd"], api_missions[0]["acd"], api_missions[0]["startt"], api_missions[0]["esttime"], api_missions[0]["runtime"], \
            api_missions[0]["cuspas"], api_missions[0]["category"], api_missions[0]["phrase"], api_missions[0]["pseudoStore"], \
            api_missions[0]["pseudoBrand"], api_missions[0]["pseudoASIN"], api_missions[0]["type"], api_missions[0]["config"], \
            api_missions[0]["skills"], api_missions[0]["delDate"], api_missions[0]["asin"], api_missions[0]["store"], api_missions[0]["brand"], \
            api_missions[0]["img"], api_missions[0]["title"], api_missions[0]["rating"], api_missions[0]["customer"], api_missions[0]["platoon"])
            self.dbCursor.execute(sql, data_tuple)

            # now that add is successfull, update local file as well.
            self.writeMissionJsonFile()

    def addBotsMissionsFromCommander(self, botsJson, missionsJson):

        print("BOTS String:", type(botsJson), botsJson)
        print("Missions String:", type(missionsJson), missionsJson)
        for bjs in botsJson:
            self.newBot = EBBOT(self)
            self.newBot.loadJson(bjs)
            self.bots.append(self.newBot)

        for mjs in missionsJson:
            self.newMission = EBMISSION(self)
            self.newMission.loadJson(mjs)
            self.missions.append(self.newMission)

    def addVehicle(self, vinfo):
        ipfields = vinfo.peername[0].split(".")
        ip = ipfields[len(ipfields) - 1]
        if len(self.vehicles) > 0:
            vids = [v.getVid() for v in self.vehicles]
        else:
            vids = []
        if ip not in vids:
            print("adding a new vehicle.....", vinfo.peername)
            newVehicle = VEHICLE(self)
            newVehicle.setIP(vinfo.peername[0])
            newVehicle.setVid(ip)
            self.vehicles.append(newVehicle)
            self.runningVehicleModel.appendRow(newVehicle)
            if self.platoonWin:
                self.platoonWin.updatePlatoonWinWithMostRecentlyAddedVehicle()
        else:
            print("Reconnected:", vinfo.peername)

    def checkVehicles(self):
        print("adding already linked vehicles.....")
        for i in range(len(fieldLinks)):
            print("a fieldlink.....", fieldLinks[i])
            newVehicle = VEHICLE(self)
            newVehicle.setIP(fieldLinks[i]["ip"][0])
            ipfields = fieldLinks[i]["ip"][0].split(".")
            ip = ipfields[len(ipfields)-1]
            newVehicle.setVid(ip)
            self.vehicles.append(newVehicle)
            self.runningVehicleModel.appendRow(newVehicle)

    def fetchVehicleStatus(self, rows):
        cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
        effective_rows = list(filter(lambda r: r >= 0, rows))
        if len(effective_rows) > 0:
            self.sendToPlatoons(effective_rows, cmd)

    def sendPlatoonCommand(self, command, rows, mids):
        print("hello???")
        if command == "refresh":
            cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
        elif command == "halt":
            cmd = '{\"cmd\":\"reqHaltMissions\", \"missions\":\"all\"}'
        elif command == "resume":
            cmd = '{\"cmd\":\"reqResumeMissions\", \"missions\":\"all\"}'
        elif command == "cancel this":
            mission_list_string = ','.join(str(x) for x in mids)
            cmd = '{\"cmd\":\"reqCancelMissions\", \"missions\":\"'+mission_list_string+'\"}'
        elif command == "cancel all":
            cmd = '{\"cmd\":\"reqCancelAllMissions\", \"missions\":\"all\"}'
        else:
            cmd = '{\"cmd\":\"ping\", \"missions\":\"all\"}'

        print("cmd is:", cmd)
        if len(rows) > 0:
            effective_rows = list(filter(lambda r: r >= 0, rows))
        else:
            effective_rows = []

        print("effective_rows:", effective_rows)
        self.sendToPlatoons(effective_rows, cmd)


    def cancelVehicleMission(self, rows):
        cmd = '{\"cmd\":\"reqCancelMission\", \"missions\":\"all\"}'
        effective_rows = list(filter(lambda r: r >= 0, rows))
        if len(effective_rows) > 0:
            self.sendToPlatoons(effective_rows, cmd)

    # this function sends commands to platoon(s)
    def sendToPlatoons(self, idxs, cmd='{\"cmd\":\"ping\"}'):
        # this shall bring up a windows, but for now, simply send something to a platoon for network testing purpose...
        #if self.platoonWin == None:
        #    self.platoonWin = PlatoonWindow(self)
        #self.BotNewWin.resize(400, 200)
        #self.platoonWin.show()
        print("sending commands.....")
        print("tcp connections.....", fieldLinks)
        print("tcp server.....", self.tcpServer)
        print("commander server.....", commanderServer)

        if len(idxs) == 0:
            idxs = range(self.runningVehicleModel.rowCount())

        # if not self.tcpServer == None:
        if len(fieldLinks) > 0:
            print("Currently, there are (", len(fieldLinks), ") connection to this server.....")
            for i in range(len(fieldLinks)):
                if i in idxs:
                    fieldLinks[i]["link"].transport.write(cmd.encode('utf8'))
                    print("cmd sent on link:", i)
        else:
            print("Warning..... TCP server not up and running yet...")

    # This function translate bots data structure matching ebbot.py to Json format for file storage.
    def genBotsJson(self):
        bjs = []
        for bot in self.bots:
            print("bot gen json0...." + str(len(self.bots)))
            bjs.append(bot.genJson())
        #print(json.dumps(bjs))
        return bjs


    # This function translate bots data from Json format to the data structure matching ebbot.py
    def translateBotsJson(self):
        for bj in self.botJsonData:
            new_bot = EBBOT(self)
            new_bot.setJsonData(bj)
            self.bots.append(new_bot)


    def readBotJsonFile(self):
        if exists(self.BOTS_FILE):
            with open(self.BOTS_FILE, 'r') as file:
                self.botJsonData = json.load(file)
                self.translateBotsJson(self.botJsonData)


    def saveBotJsonFile(self):
        if self.BOTS_FILE == None:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.BOTS_FILE = filename

        if self.BOTS_FILE:
            try:
                botsdata = self.genBotsJson()
                print(self.BOTS_FILE)
                with open(self.BOTS_FILE, 'w') as jsonfile:
                    json.dump(botsdata, jsonfile)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QtGui.QMessageBox.information(
                    self,
                    "Unable to save file: %s" % filename
                )
        else:
            print("Bot file does NOT exist.")

    def translateInventoryJson(self):
        # print("Translating JSON to data.......", len(self.sellerInventoryJsonData))
        for bj in self.sellerInventoryJsonData:
            new_inventory = INVENTORY()
            new_inventory.setJsonData(bj)
            self.inventories.append(new_inventory)


    def readSellerInventoryJsonFile(self, inv_file):
        if inv_file == "":
            inv_file_name = self.SELLER_INVENTORY_FILE
        else:
            inv_file_name = inv_file

        print("INVENTORY file: ", inv_file_name)
        if exists(inv_file_name):
            print("Reading inventory file: ", inv_file_name)
            with open(inv_file_name, 'r') as file:
                self.sellerInventoryJsonData = json.load(file)
                self.translateInventoryJson()
        else:
            print("NO inventory file found!")


    def getBotsInventory(self, botid):
        print("botid type:", type(botid), len(self.inventories))
        print(self.inventories[0].products[0].genJson())
        found = next((x for x in self.inventories if botid in x.getAllowedBids()), None)
        return found

    # This function translate bots data structure matching ebbot.py to Json format for file storage.
    def genMissionsJson(self):
        mjs = []
        for mission in self.missions:
            print("mission gen json0...." + str(len(self.missions)))
            mjs.append(mission.genJson())
        #print(json.dumps(bjs))
        return mjs


    # This function translate bots data from Json format to the data structure matching ebbot.py
    def translateMissionsJson(self):
        for mj in self.missionJsonData:
            new_mission = EBMISSION()
            new_mission.setJsonData(mj)
            self.missions.append(new_mission)


    def readMissionJsonFile(self):
        if exists(self.MISSIONS_FILE):
            with open(self.MISSIONS_FILE, 'r') as file:
                self.missionJsonData = json.load(file)
                self.translateMissionsJson(self.missionJsonData)


    def writeMissionJsonFile(self):
        if self.MISSIONS_FILE == None:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.MISSIONS_FILE = filename

        if self.MISSIONS_FILE and exists(self.MISSIONS_FILE):
            try:
                missionsdata = self.genMissionsJson()
                print(self.MISSIONS_FILE)
                with open(self.MISSIONS_FILE, 'w') as jsonfile:
                    json.dump(missionsdata, jsonfile)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QtGui.QMessageBox.information(
                    self,
                    "Unable to save file: %s" % filename
                )


    def readCSVFiles(self):
        # read files from the local disk and. bot file in csv file format.
        # text, icon, ebtype, email, empw, phone, backemail, acctpw, fn, ln,
        # pfn, pln, pnn, loc, age, mf, interests, role,
        # platform, os, machine, browser, past_schedule, next_schedule
        # state(green/mature), state_start_date, last_walk_date, last_rv_date,
        names_path = 'C:/CrawlerData/names'
        nfiles = os.listdir(names_path)
        nfiles = list(filter(lambda f: f.endswith('.csv'), nfiles))
        nfiles = list(filter(lambda f: f.startswith('bot_'), nfiles))
        for bf in nfiles:
            botjson = {}
            with open((names_path + bf), 'r') as read_obj:
                # pass the file object to reader() to get the reader object
                csv_reader = reader(read_obj)
                rows = list(csv_reader)
                i=0
                # Iterate over each row in the csv using reader object
                botjson["text"] = rows[1][i]
                i = i + 1
                botjson["icon"] = rows[1][i]
                i = i + 1
                botjson["ebtype"] = rows[1][i]
                i = i + 1
                botjson["private_profile"] = {}
                botjson["private_profile"]["fn"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["ln"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["email"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["emailpw"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["acctpw"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["phone"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["backemail"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["prox0"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["prox1"] = rows[1][i]
                i = i + 1
                botjson["private_profile"]["prox2"] = rows[1][i]
                i = i + 1
                botjson["public_profile"] = {}
                botjson["public_profile"]["pfn"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["fln"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["fnn"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["loc"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["age"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["mf"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["interests"] = rows[1][i]
                i = i + 1
                botjson["public_profile"]["role"] = rows[1][i]
                i = i + 1
                botjson["settings"] = {}
                botjson["settings"]["platform"] = rows[1][i]
                i = i + 1
                botjson["settings"]["browser"] = rows[1][i]
                i = i + 1
                botjson["settings"]["machine"] = rows[1][i]
                i = i + 1
                botjson["settings"]["os"] = rows[1][i]
                i = i + 1
                botjson["status"] = {}
                botjson["status"]["state"] = rows[1][i]
                i = i + 1
                botjson["status"]["levels"] = rows[1][i]
                i = i + 1
                botjson["status"]["lvl_start_date"] = rows[1][i]
                i = i + 1
                botjson["status"]["last_walk_date"] = rows[1][i]
                i = i + 1
                botjson["status"]["last_fb_date"] = rows[1][i]
                i = i + 1
                botjson["status"]["last_mi_date"] = rows[1][i]
                i = i + 1
                botjson["status"]["walks_in1m"] = rows[1][i]
                i = i + 1
                botjson["status"]["mi_in1m"] = rows[1][i]
                i = i + 1
                botjson["status"]["fb_in1m"] = rows[1][i]
                i = i + 1


    def runAll(self):
        # Logic for removing a bot, remove the data and remove the file.
        print("runn all")

    def scheduleCalendarView(self):
        # Logic for the bot-mission-scheduler
        # pop out a new windows for user to view and schedule the missions.
        # at the moment, just add an icon.
        #new_bot = EBBOT(self)
        #new_icon = QtGui.QIcon((":file-open.svg"))
        #self.centralWidget.setText("<b>File > New</b> clicked")
        self.scheduleWin = ScheduleWin()
        #self.BotNewWin.resize(400, 200)
        self.scheduleWin.show()

    def newMissionView(self):
        if self.missionWin == None:
            self.missionWin = MissionNewWin(self)
            self.missionWin.setOwner(self.owner)
        #self.BotNewWin.resize(400, 200)
        self.missionWin.show()

    def newVehiclesView(self):
        if self.platoonWin == None:
            print("creating platoon monitor window....")
            self.platoonWin = PlatoonWindow(self, "init")
        else:
            print("Shows existing windows...")
        self.platoonWin.show()

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.ContextMenu and source is self.botListView:
            #print("bot RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.pop_menu_font = QtGui.QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)

            self.rcbotEditAction = self._createBotRCEditAction()
            self.rcbotCloneAction = self._createBotRCCloneAction()
            self.rcbotDeleteAction = self._createBotRCDeleteAction()

            self.popMenu.addAction(self.rcbotEditAction)
            self.popMenu.addAction(self.rcbotCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.rcbotDeleteAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_bot_row = source.indexAt(event.pos()).row()
                self.selected_bot_item = self.botModel.item(self.selected_bot_row)
                if selected_act == self.rcbotEditAction:
                    self.editBot()
                elif selected_act == self.rcbotCloneAction:
                    self.cloneBot()
                elif selected_act == self.rcbotDeleteAction:
                    self.deleteBot()
            return True
        elif event.type() == QtCore.QEvent.ContextMenu and source is self.missionListView:
            #print("mission RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.pop_menu_font = QtGui.QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)
            self.cusMissionEditAction = self._createCusMissionEditAction()
            self.cusMissionCloneAction = self._createCusMissionCloneAction()
            self.cusMissionDeleteAction = self._createCusMissionDeleteAction()
            self.cusMissionUpdateAction = self._createCusMissionUpdateAction()

            self.popMenu.addAction(self.cusMissionEditAction)
            self.popMenu.addAction(self.cusMissionCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionDeleteAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionUpdateAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_cus_mission_row = source.indexAt(event.pos()).row()
                self.selected_cus_mission_item = self.missionModel.item(self.selected_cus_mission_row)
                if selected_act == self.cusMissionEditAction:
                    self.editCusMission()
                elif selected_act == self.cusMissionCloneAction:
                    self.cloneCusMission()
                elif selected_act == self.cusMissionDeleteAction:
                    self.deleteCusMission()
                elif selected_act == self.cusMissionUpdateAction:
                    self.updateCusMissionStatus(self.selected_cus_mission_item)
            return True
        # else:
        #     print("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)


    def _createCusMissionEditAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
       return new_action

    def _createCusMissionCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createCusMissionDeleteAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
        return new_action

    def _createCusMissionUpdateAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Update Status"))
        return new_action

    def editCusMission(self):
        # File actions
        if self.missionWin:
            self.missionWin.setMission(self.selected_cus_mission_item)
        else:
            self.missionWin = MissionNewWin(self)
            self.missionWin.setOwner(self.owner)
        self.missionWin.show()
        print("edit bot" + str(self.selected_cus_mission_row))

    def cloneCusMission(self):
        # File actions
        print("clone bot" + str(self.selected_bot_row))

    def deleteCusMission(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "The mission will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this mission?"))
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Yes)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:
            api_removes = []
            items = [self.selected_cus_mission_item]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.missionModel.removeRow(item.row())
                    api_removes.append({"id": item.getMid(), "owner": "", "reason": ""})

                # remove on the cloud side
                jresp = send_remove_missions_request_to_cloud(self.session, api_removes, self.tokens['AuthenticationResult']['IdToken'])
                if "errorType" in jresp:
                    screen_error = True
                    print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                else:
                    jbody = json.loads(jresp["body"])
                    #now that delete is successfull, update local file as well.
                    self.writeMissionJsonFile()

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    def updateCusMissionStatus(self, amission):
        # send this mission's status to Cloud
        api_missions = [amission]
        jresp = send_update_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            # now that delete is successfull, update local file as well.
            self.writeMissionJsonFile()

    def _createBotRCEditAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Edit"))
       return new_action

    def _createBotRCCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Clone"))
        return new_action

    def _createBotRCDeleteAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText(QtWidgets.QApplication.translate("QtGui.QAction", "&Delete"))
        return new_action

    def editBot(self):
        # File actions
        if self.BotNewWin:
            self.BotNewWin.setBot(self.selected_bot_item)
        else:
            self.BotNewWin = BotNewWin(self)
        self.BotNewWin.show()
        print("edit bot" + str(self.selected_bot_row))

    def cloneBot(self):
        # File actions
        print("clone bot" + str(self.selected_bot_row))

    def deleteBot(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "The bot will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QtWidgets.QApplication.translate("QtWidgets.QMessageBox", "Are you sure about deleting this bot?"))
        msgBox.setStandardButtons(QtWidgets.QMessageBox.Cancel | QtWidgets.QMessageBox.Yes)
        msgBox.setDefaultButton(QtWidgets.QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QtWidgets.QMessageBox.Yes:
            api_removes = []
            items = [self.selected_bot_item]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.botModel.removeRow(item.row())
                    api_removes.append({"id": item.getBid(), "owner": "", "reason": ""})

                # remove on the cloud side
                jresp = send_remove_missions_request_to_cloud(self.session, api_removes, self.tokens['AuthenticationResult']['IdToken'])
                if "errorType" in jresp:
                    screen_error = True
                    print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                else:
                    jbody = json.loads(jresp["body"])
                    #now that delete is successfull, update local file as well.
                    self.saveBotJsonFile()

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    #data format conversion. nb is in EBBOT data structure format., nbdata is json
    def fillNewBotPubInfo(self, nbjson, nb):
        print("filling bot public data for bot-"+str(nbjson["pubProfile"]["bid"]))
        nb.setNetRespJsonData(nbjson)

    def fillNewBotFullInfo(self, nbjson, nb):
        print("filling bot data for bot-"+str(nbjson["pubProfile"]["bid"]))
        nb.loadJson(nbjson)


    def newBotFromFile(self):
        print("loading bots from a file...")
        api_bots = []
        uncompressed = open(self.homepath + "/resource/testdata/newbots.json")
        if uncompressed != None:
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            filebbots = json.load(uncompressed)
            if len(filebbots) > 0:
                #add bots to the relavant data structure and add these bots to the cloud and local DB.
                for fb in filebbots:
                    new_bot = EBBOT(self)
                    self.fillNewBotFullInfo(fb, new_bot)
                    self.bots.append(new_bot)
                    self.botModel.appendRow(new_bot)

                # jresp = send_add_bots_request_to_cloud(self.session, filebbots,
                #                                        self.tokens['AuthenticationResult']['IdToken'])
                #
                # if "errorType" in jresp:
                #     screen_error = True
                #     print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                # else:
                #     print("jresp type: ", type(jresp), len(jresp["body"]))
                #     jbody = jresp["body"]
                #     # now that add is successfull, update local file as well.
                #
                #     # now add bot to local DB.
                #
                #     for i in range(len(jbody)):
                #         print(i)
                #         new_bot = EBBOT(self)
                #         self.fillNewBotPubInfo(jbody[i], new_bot)
                #         self.bots.append(new_bot)
                #         self.botModel.appendRow(new_bot)
                #         api_bots.append({
                #             "bid": new_bot.getBid(),
                #             "owner": self.owner,
                #             "roles": new_bot.getRoles(),
                #             "pubbirthday": new_bot.getPubBirthday(),
                #             "gender": new_bot.getGender(),
                #             "location": new_bot.getLocation(),
                #             "levels": new_bot.getLevels(),
                #             "birthday": new_bot.getBirthdayTxt(),
                #             "interests": new_bot.getInterests(),
                #             "status": new_bot.getStatus(),
                #             "delDate": new_bot.getInterests(),
                #             "name": new_bot.getName(),
                #             "pseudoname": new_bot.getPseudoName(),
                #             "nickname": new_bot.getNickName(),
                #             "addr": new_bot.getInterests(),
                #             "shipaddr": new_bot.getInterests(),
                #             "phone": new_bot.getPhone(),
                #             "email": new_bot.getEmail(),
                #             "epw": new_bot.getEmPW(),
                #             "backemail": new_bot.getBackEm(),
                #             "ebpw": new_bot.getAcctPw()
                #         })
                #
                #         sql = ''' INSERT INTO bots(botid, owner, levels, gender, birthday, interests, location, roles, status, delDate, name, pseudoname, nickname, addr, shipaddr, phone, email, epw, backemail, ebpw)
                #                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
                #         data_tuple = (
                #         api_bots[i]["bid"], api_bots[i]["owner"], api_bots[i]["levels"], api_bots[i]["gender"],
                #         api_bots[i]["birthday"], \
                #         api_bots[i]["interests"], api_bots[i]["location"], api_bots[i]["roles"], api_bots[i]["status"],
                #         api_bots[i]["delDate"], \
                #         api_bots[i]["name"], api_bots[i]["pseudoname"], api_bots[i]["nickname"], api_bots[i]["addr"],
                #         api_bots[i]["shipaddr"], \
                #         api_bots[i]["phone"], api_bots[i]["email"], api_bots[i]["epw"], api_bots[i]["backemail"],
                #         api_bots[i]["ebpw"])
                #
                #         self.dbCursor.execute(sql, data_tuple)
                #
                #         sql = 'SELECT * FROM bots'
                #         res = self.dbCursor.execute(sql)
                #         print("fetchall", res.fetchall())
                        # important about format: returned here is a list of tuples (,,,,)
                        #for column in res.description:
                        #    print(column[0])

            else:
                self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO bots found in file."))
        else:
            self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: No file."))

        for b in self.bots:
            print("added BID:", b.getBid())

    # data format conversion. nb is in EBMISSION data structure format., nbdata is json
    def fillNewMission(self, nmjson, nm):
        print("filling mission data")
        nm.setNetRespJsonData(nmjson)

    def newMissionFromFile(self):

        print("loading missions from a file...")
        api_missions = []
        uncompressed = open(self.homepath + "/resource/testdata/newmissions.json")
        if uncompressed != None:
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            filebmissions = json.load(uncompressed)
            if len(filebmissions) > 0:
                #add bots to the relavant data structure and add these bots to the cloud and local DB.

                jresp = send_add_missions_request_to_cloud(self.session, filebmissions,
                                                       self.tokens['AuthenticationResult']['IdToken'])

                if "errorType" in jresp:
                    screen_error = True
                    print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                else:
                    print("jresp type: ", type(jresp), len(jresp["body"]))
                    jbody = jresp["body"]
                    # now that add is successfull, update local file as well.

                    # now add bot to local DB.

                    for i in range(len(jbody)):
                        print(i)
                        new_mission = EBMISSION(self)
                        self.fillNewMission(jbody[i], new_mission)
                        self.missions.append(new_mission)
                        self.missionModel.appendRow(new_mission)

                        api_missions.append({
                            "mid": new_mission.getMid(),
                            "ticket": new_mission.getMid(),
                            "botid": new_mission.getBid(),
                            "owner": self.owner,
                            "status": new_mission.getStatus(),
                            "createon": new_mission.getBD(),
                            "esd": new_mission.getEsd(),
                            "ecd": new_mission.getEcd(),
                            "asd": new_mission.getAsd(),
                            "abd": new_mission.getAbd(),
                            "aad": new_mission.getAad(),
                            "afd": new_mission.getAfd(),
                            "acd": new_mission.getAcd(),
                            "eststartt": new_mission.getEstimatedStartTime(),
                            "startt": new_mission.getActualStartTime(),
                            "esttime": new_mission.getEstimatedRunTime(),
                            "runtime": new_mission.getRunTime(),
                            "cuspas": new_mission.getCusPAS(),
                            "search_cat": new_mission.getSearchCat(),
                            "search_kw": new_mission.getSearchKW(),
                            "pseudo_store": new_mission.getPseudoStore(),
                            "pseudo_brand": new_mission.getPseudoBrand(),
                            "pseudo_asin": new_mission.getPseudoASIN(),
                            "repeat": new_mission.getRepeat(),
                            "mtype": new_mission.getMtype(),
                            "mconfig": new_mission.getConfig(),
                            "skills": new_mission.getSkills(),
                            "delDate": new_mission.getDelDate(),
                            "asin": new_mission.getASIN(),
                            "store": new_mission.getStore(),
                            "brand": new_mission.getBrand(),
                            "image": new_mission.getImagePath(),
                            "title": new_mission.getTitle(),
                            "rating": new_mission.getRating(),
                            "feedbacks": new_mission.getFeedbacks(),
                            "customer": new_mission.getCustomerID(),
                            "platoon": new_mission.getPlatoonID()
                        })

                        sql = ''' INSERT INTO missions(mid, ticket, owner, botid, status, createon, esd, ecd, asd, abd, aad, afd, acd, eststartt, startt, esttime, runtime, 
                                            cuspas, category, phrase, pseudoStore, pseudoBrand, pseudoASIN, type, config, skills, delDate, asin, store, brand, img, 
                                            title, rating, feedbacks, customer, platoon) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
                        data_tuple = (api_missions[0]["mid"], api_missions[0]["ticket"], api_missions[0]["owner"], \
                                      api_missions[0]["botid"], api_missions[0]["status"], api_missions[0]["createon"], \
                                      api_missions[0]["esd"], api_missions[0]["ecd"], api_missions[0]["asd"], \
                                      api_missions[0]["abd"], api_missions[0]["aad"], \
                                      api_missions[0]["afd"], api_missions[0]["acd"], api_missions[0]["eststartt"], api_missions[0]["startt"], \
                                      api_missions[0]["esttime"], api_missions[0]["runtime"], \
                                      api_missions[0]["cuspas"], api_missions[0]["category"], api_missions[0]["phrase"], \
                                      api_missions[0]["pseudoStore"], \
                                      api_missions[0]["pseudoBrand"], api_missions[0]["pseudoASIN"], \
                                      api_missions[0]["type"], api_missions[0]["config"], \
                                      api_missions[0]["skills"], api_missions[0]["delDate"], api_missions[0]["asin"], \
                                      api_missions[0]["store"], api_missions[0]["brand"], \
                                      api_missions[0]["img"], api_missions[0]["title"], api_missions[0]["rating"], \
                                      api_missions[0]["feedbacks"], api_missions[0]["customer"], api_missions[0]["platoon"])

                        self.dbCursor.execute(sql, data_tuple)

                        sql = 'SELECT * FROM missions'
                        res = self.dbCursor.execute(sql)
                        print("fetchall", res.fetchall())
                        # important about format: returned here is a list of tuples (,,,,)
                        #for column in res.description:
                        #    print(column[0])

            else:
                self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO missions found in file."))
        else:
            self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: No test mission file"))


    def fillNewSkill(self, nskjson, nsk):
        print("filling mission data")
        nsk.setNetRespJsonData(nskjson)

    def showSkillManager(self):
        if self.SkillManagerWin == None:
            self.SkillManagerWin = SkillManagerWindow(self)
        self.SkillManagerWin.show()

    def uploadSkill(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            QtWidgets.QApplication.translate("QtWidgets.QFileDialog", "Upload Skill File"),
            '',
            QtWidgets.QApplication.translate("QtWidgets.QFileDialog", "Skill Json Files (*.json)")
        )
        if filename != "":
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            sk_dir == os.path.abspath(filename)
            anchor_dir = sk_dir + "/" + os.path.basename(filename).split(".")[0] + "/images"
            scripts_dir = sk_dir + "/" + os.path.basename(filename).split(".")[0] + "/scripts"
            anchor_files = os.listdir(anchor_dir)
            for af in anchor_files:
                full_af_name = anchor_dir + "/" + af
                jresp = upload_file(self.session, full_af_name, self.tokens['AuthenticationResult']['IdToken'], "anchor")

            csk_file = scripts_dir + "/" + os.path.basename(filename).split(".")[0] + ".csk"
            jresp = upload_file(self.session, csk_file, self.tokens['AuthenticationResult']['IdToken'], "csk")


    def newSkillFromFile(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            QtWidgets.QApplication.translate("QtWidgets.QFileDialog", "Open Skill File"),
            '',
            QtWidgets.QApplication.translate("QtWidgets.QFileDialog", "Skill Json Files (*.json)")
        )
        print("loading skill from a file...", filename)
        if filename != "":
            api_skills = []
            new_skill_file = open(filename)
            if new_skill_file != None:
                # print("body string:", uncompressed, "!", len(uncompressed), "::")
                filebskill = json.load(new_skill_file)
                if len(filebskill) > 0:
                    #add bots to the relavant data structure and add these bots to the cloud and local DB.

                    jresp = send_add_skills_to_cloud(self.session, filebskill, self.tokens['AuthenticationResult']['IdToken'])

                    if "errorType" in jresp:
                        screen_error = True
                        print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                    else:
                        print("jresp type: ", type(jresp), len(jresp["body"]))
                        jbody = jresp["body"]
                        # now that add is successfull, update local file as well.

                        # now add bot to local DB.

                        for i in range(len(jbody)):
                            print(i)
                            new_skill = WORKSKILL()
                            self.fillNewSkill(jbody[i], new_skill)
                            self.skills.append(new_skill)
                            self.skillModel.appendRow(new_skill)
                            api_skills.append({
                                "skid": new_skill.getBid(),
                                "owner": self.owner,
                                "platform": new_skill.getRoles(),
                                "app": new_skill.getPubBirthday(),
                                "site": new_skill.getGender(),
                                "name": new_skill.getName(),
                                "path": new_skill.getLevels(),
                                "runtime": new_skill.getBirthdayTxt(),
                                "price_model": new_skill.getInterests(),
                                "price": new_skill.getStatus(),
                                "privacy": new_skill.getInterests(),
                            })

                            sql = ''' INSERT INTO skills(skid, owner, platform, app, site, name, path, runtime, price_model, price, privacy)
                                           VALUES(?,?,?,?,?,?,?,?,?,?,?); '''
                            data_tuple = (
                            api_skills[i]["skid"], api_skills[i]["owner"], api_skills[i]["platform"], \
                            api_skills[i]["app"], api_skills[i]["site"], api_skills[i]["name"], \
                            api_skills[i]["path"], api_skills[i]["runtime"], api_skills[i]["price_model"], \
                            api_skills[i]["price"], api_skills[i]["privacy"])

                            self.dbCursor.execute(sql, data_tuple)

                            sql = 'SELECT * FROM skills'
                            res = self.dbCursor.execute(sql)
                            print("fetchall", res.fetchall())
                            # important about format: returned here is a list of tuples (,,,,)
                            #for column in res.description:
                            #    print(column[0])

                else:
                    self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO skills in the file."))
            else:
                self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: no test skill file."))

    # load locally stored skills
    def loadLocalSkills(self):
        skill_def_files = []
        skdir = self.homepath + "/resource/skills/"
        # Iterate over all files in the directory
        # Walk through the directory tree recursively
        for root, dirs, files in os.walk(skdir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    skill_def_files.append(file_path)

        # print("local skill files: ", skill_def_files)

        for file_path in skill_def_files:
            with open(file_path) as json_file:
                data = json.load(json_file)
                # print("loading skill f: ", data["skid"], file_path)
                new_skill = WORKSKILL(self, data["name"])
                new_skill.loadJson(data)
                self.skills.append(new_skill)

        print("total skill files loaded: ", len(self.skills))

    def newProductsFromFile(self):

        print("loading products from a file...")
        api_products = []
        uncompressed = open(self.homepath + "/resource/testdata/newproducts.json")
        if uncompressed != None:
            # print("body string:", uncompressed, "!", len(uncompressed), "::")
            fileproducts = json.load(uncompressed)
            if len(fileproducts) > 0:
                #add bots to the relavant data structure and add these bots to the cloud and local DB.

                jresp = send_add_missions_request_to_cloud(self.session, filebmissions,
                                                       self.tokens['AuthenticationResult']['IdToken'])

                if "errorType" in jresp:
                    screen_error = True
                    print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
                else:
                    print("jresp type: ", type(jresp), len(jresp["body"]))
                    jbody = jresp["body"]
                    # now that add is successfull, update local file as well.

                    # now add bot to local DB.

                    for i in range(len(jbody)):
                        print(i)
                        new_mission = EBMISSION(self)
                        self.fillNewMission(jbody[i], new_mission)
                        self.missions.append(new_mission)
                        self.missionModel.appendRow(new_mission)

                        api_missions.append({
                            "mid": new_mission.getMid(),
                            "ticket": new_mission.getMid(),
                            "botid": new_mission.getBid(),
                            "owner": self.owner,
                            "status": new_mission.getStatus(),
                            "createon": new_mission.getBD(),
                            "esd": new_mission.getEsd(),
                            "ecd": new_mission.getEcd(),
                            "asd": new_mission.getAsd(),
                            "abd": new_mission.getAbd(),
                            "aad": new_mission.getAad(),
                            "afd": new_mission.getAfd(),
                            "acd": new_mission.getAcd(),
                            "eststartt": new_mission.getEstimatedStartTime(),
                            "startt": new_mission.getActualStartTime(),
                            "esttime": new_mission.getEstimatedRunTime(),
                            "runtime": new_mission.getRunTime(),
                            "cuspas": new_mission.getCusPAS(),
                            "search_cat": new_mission.getSearchCat(),
                            "search_kw": new_mission.getSearchKW(),
                            "pseudo_store": new_mission.getPseudoStore(),
                            "pseudo_brand": new_mission.getPseudoBrand(),
                            "pseudo_asin": new_mission.getPseudoASIN(),
                            "repeat": new_mission.getRepeat(),
                            "mtype": new_mission.getMtype(),
                            "mconfig": new_mission.getConfig(),
                            "skills": new_mission.getSkills(),
                            "delDate": new_mission.getDelDate(),
                            "asin": new_mission.getASIN(),
                            "store": new_mission.getStore(),
                            "brand": new_mission.getBrand(),
                            "image": new_mission.getImagePath(),
                            "title": new_mission.getTitle(),
                            "rating": new_mission.getRating(),
                            "feedbacks": new_mission.getFeedbacks(),
                            "customer": new_mission.getCustomerID(),
                            "platoon": new_mission.getPlatoonID()
                        })

                        sql = ''' INSERT INTO missions(mid, ticket, owner, botid, status, createon, esd, ecd, asd, abd, aad, afd, acd, eststartt, startt, esttime, runtime, 
                                            cuspas, category, phrase, pseudoStore, pseudoBrand, pseudoASIN, type, config, skills, delDate, asin, store, brand, img, 
                                            title, rating, feedbacks, customer, platoon) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
                        data_tuple = (api_missions[0]["mid"], api_missions[0]["ticket"], api_missions[0]["owner"], \
                                      api_missions[0]["botid"], api_missions[0]["status"], api_missions[0]["createon"], \
                                      api_missions[0]["esd"], api_missions[0]["ecd"], api_missions[0]["asd"], \
                                      api_missions[0]["abd"], api_missions[0]["aad"], \
                                      api_missions[0]["afd"], api_missions[0]["acd"], api_missions[0]["eststartt"], api_missions[0]["startt"], \
                                      api_missions[0]["esttime"], api_missions[0]["runtime"], \
                                      api_missions[0]["cuspas"], api_missions[0]["category"], api_missions[0]["phrase"], \
                                      api_missions[0]["pseudoStore"], \
                                      api_missions[0]["pseudoBrand"], api_missions[0]["pseudoASIN"], \
                                      api_missions[0]["type"], api_missions[0]["config"], \
                                      api_missions[0]["skills"], api_missions[0]["delDate"], api_missions[0]["asin"], \
                                      api_missions[0]["store"], api_missions[0]["brand"], \
                                      api_missions[0]["img"], api_missions[0]["title"], api_missions[0]["rating"], \
                                      api_missions[0]["feedbacks"], api_missions[0]["customer"], api_missions[0]["platoon"])

                        self.dbCursor.execute(sql, data_tuple)

                        sql = 'SELECT * FROM missions'
                        res = self.dbCursor.execute(sql)
                        print("fetchall", res.fetchall())
                        # important about format: returned here is a list of tuples (,,,,)
                        #for column in res.description:
                        #    print(column[0])

            else:
                self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: NO products found in file."))
        else:
            self.warn(QtWidgets.QApplication.translate("QtWidgets.QMainWindow", "Warning: No test products file"))

    # try load bots from local database, if nothing in th local DB, then
    # try to fetch bots from local json files (this is mostly for testing).
    def loadLocalBots(self):
        skill_def_files = []
        sql = 'SELECT * FROM bots'

        # column_name = 'your_column_name'
        # column_value = 'your_column_value'
        #
        # # Construct the SQL query with placeholders
        # query = f"SELECT * FROM your_table_name WHERE {column_name} = ?"
        #
        # # Execute the query and fetch the results
        # cursor.execute(query, (column_value,))

        res = self.dbCursor.execute(sql)

        db_data = res.fetchall()
        if len(db_data) != 0:
            print("bot fetchall", db_data)
            for row in db_data:
                print("loading a bot: ", row)
                new_bot = EBBOT(self)
                new_bot.loadDBData(row)
                self.bots.append(new_bot)
        else:
            self.newBotFromFile()



    # load locally stored skills
    def loadLocalMissions(self):
        skill_def_files = []

        sql = 'SELECT * FROM missions'
        res = self.dbCursor.execute(sql)

        db_data = res.fetchall()
        print("mission fetchall", db_data)

        for row in db_data:
            print("loading a bot: ", row)
            new_mission = EBMISSION(self)
            new_mission.loadDBData(row)
            self.missions.append(new_mission)

    # fetch all bots stored in the cloud.
    def getAllBotsFromCloud(self):
        # File actions
        #resp = send_get_bots_request_to_cloud(self.session, self.cog.access_token)
        jresp = send_get_bots_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("Gat All Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            print("resp body", jresp["body"])
            #jbody = json.loads(jresp["body"])
            # now that fetch all bots from the cloud side is successfull, need to compare with local data and merge:


    def setOwner(self, owner):
        self.owner = owner

    def runAll(self):
        threadCount = QtCore.QThreadPool.globalInstance().maxThreadCount()
        self.label.setText(f"Running {threadCount} Threads")
        pool = QtCore.QThreadPool.globalInstance()
        for i in range(threadCount):
            # 2. Instantiate the subclass of QRunnable
            #runnable = Runnable(i)
            # 3. Call start()
            #pool.start(runnable)
            print("run thread")

    def editSettings(self):
        self.SettingsWin.show()

    def manualRunAll(self):
        txt_results = "{}"
        ico_results = "{}"

        for m in self.missions:
            status = m.run()

    def runbotworks(self):
        # run all the work
        botTodos = None
        if self.workingState == "Idle":
            botTodos = self.checkToDos()
            self.showMsg("check todos....")
            if not botTodos == None:
                print("working on..... ", botTodos["name"])
                self.workingState = "Working"
                if botTodos["name"] == "fetch schedule":
                    print("fetching schedule..........")
                    last_start = int(datetime.datetime.now().timestamp()*1)
                    botTodos["status"] = self.fetchSchedule("", None)
                    last_end = int(datetime.datetime.now().timestamp()*1)
                    # there should be a step here to reconcil the mission fetched and missions already there in local data structure.
                    # if there are new cloud created walk missions, should add them to local data structure and store to the local DB.
                    # if "Completed" in botTodos["status"]:
                    current_run_report = self.genRunReport(last_start, last_end, 0, 0, botTodos["status"])
                    finished = self.todays_work["tbd"].pop(0)
                    self.todays_completed.append(finished)
                elif botTodos["name"] == "automation":
                    # run 1 bot's work
                    print("running RPA..............")
                    if "Completed" not in botTodos["status"]:
                        print("time to run RPA........", botTodos)
                        last_start = int(datetime.datetime.now().timestamp()*1)
                        current_bid, current_mid, run_result = self.runRPA(botTodos)
                        last_end = int(datetime.datetime.now().timestamp()*1)
                    # else:
                        # now need to chop off the 0th todo since that's done by now....
                        current_run_report = self.genRunReport(last_start, last_end, current_bid, current_mid, run_result)

                        finished = self.todays_work["tbd"].pop(0)
                        self.todays_completed.append(finished)

                        if len(self.todays_work["tbd"]) == 0:
                            if self.hostrole == "Platoon":
                                print("Platoon Done with today!!!!!!!!!")
                                self.doneWithToday()
                            else:
                                # check whether we have collected all reports so far, there is 1 count difference between,
                                # at this point the local report on this machine has not been added to toddaysReports yet.
                                # this will be done in doneWithToday....
                                if len(self.todaysPlatoonReports) == (len(self.todays_completed) - 2):
                                    print("Commander Done with today!!!!!!!!!")
                                    self.doneWithToday()
                else:
                    print("Unrecogizable todo name....", botTodos["name"])

            else:
                # nothing to do right now. check if all of today's work are done.
                # if my own works are done and all platoon's reports are collected.
                if self.hostrole == "Platoon":
                    if len(self.todays_work["tbd"]) == 0:
                        self.doneWithToday()

        if self.workingState != "Idle":
            self.workingState = "Idle"


    #update a vehicle's missions status
    # rx_data is a list of mission status for each mission that belongs to the vehicle.
    def updateVMStats(self, rx_data):
        foundV = None
        for v in self.vehicles:
            if v.getIP() == rx_data["ip"]:
                print("found vehicle by IP")
                foundV = v
                break

        if foundV:
            print("updating vehicle Mission status...")
            foundV.setMStats(rx_data)

    # create some test data just to test out the vehichle view GUI.
    def genGuiTestDat(self):
        newV = VEHICLE(self)
        newV.setIP("192.168.22.33")
        newV.setVid("33")
        newV.setMStats([{
            "mid": 1,
            "botid": 1,
            "sst": "2023-10-22 00:11:12",
            "sd": 600,
            "ast": "2023-10-22 00:12:12",
            "aet": "2023-10-22 00:22:12",
            "status": "completed",
            "error": "",
        },
            {
                "mid": 2,
                "botid": 2,
                "sst": "2023-10-22 12:11:12",
                "sd": 600,
                "ast": "2023-10-22 12:12:12",
                "aet": "2023-10-22 12:22:12",
                "status": "running",
                "error": "",
            }])
        self.parent.vehicles.append(newV)

        newV = VEHICLE(self)
        newV.setIP("192.168.22.34")
        newV.setVid("34")
        newV.setMStats([{
            "mid": 3,
            "botid": 3,
            "sst": "2023-10-22 00:11:12",
            "sd": 600,
            "ast": "2023-10-22 00:12:12",
            "aet": "2023-10-22 00:22:12",
            "status": "scheduled",
            "error": "",
        },
            {
                "mid": 4,
                "botid": 3,
                "sst": "2023-10-22 12:11:12",
                "sd": 600,
                "ast": "2023-10-22 12:12:12",
                "aet": "2023-10-22 12:22:12",
                "status": "warned",
                "error": "100: warning reason 1",
            }])
        self.parent.vehicles.append(newV)

        newV = VEHICLE(self)
        newV.setIP("192.168.22.29")
        newV.setVid("29")
        newV.setMStats([{
            "mid": 5,
            "botid": 5,
            "sst": "2023-10-22 00:11:12",
            "sd": 600,
            "ast": "2023-10-22 00:12:12",
            "aet": "2023-10-22 00:22:12",
            "status": "aborted",
            "error": "203: Found Captcha",
        }])
        self.parent.vehicles.append(newV)

    # msg in json format
    # { sender: "ip addr", type: "intro/status/report", content : "another json" }
    # content format varies according to type.
    def processPlatoonMsgs(self, msgString, ip):
        print("Platoon Msg Received:", msgString)
        msg = json.loads(msgString)

        found = next((x for x in fieldLinks if x["ip"] == ip), None)

        # first, check ip and make sure this from a know vehicle.
        if msg["type"] == "intro":
            if found:
                found["name"] = msg["content"]["name"]
        elif msg["type"] == "status":
            # update vehicle status display.
            self.showMsg(msg["content"])
            print("recevied a status update message")
            if self.platoonWin:
                print("updating platoon WIN")
                self.platoonWin.updatePlatoonStatAndShow(msg)
                self.platoonWin.show()
            else:
                print("ERROR: platoon win not yet exists.......")

            self.updateVMStats(msg)

        elif msg["type"] == "report":
            # collect report, the report should be already organized in json format and ready to submit to the network.
            print("msg type:", type(msg), msg)
            self.todaysPlatoonReports.append(msg)

            # now using ip to find the item added to self.self.todays_work["tbd"]
            task_idx = 0
            found = False
            for item in self.todays_work["tbd"]:
                if "ip" in item:
                    if item["ip"] == msg["ip"]:
                        found = True
                        break
                task_idx = task_idx + 1

            if found:
                print("finising a task....", task_idx)
                finished = self.todays_work["tbd"].pop(task_idx)
                self.todays_completed.append(finished)

            print("len todays's reports:", len(self.todaysPlatoonReports), "len todays's completed:", len(self.todays_completed))
            print("completd：", self.todays_completed)

            # keep statistics on all platoon runs.
            if len(self.todaysPlatoonReports) == (len(self.todays_completed)):
                # check = all(item in List1 for item in List2)
                # this means all reports are collected, ready to send to cloud.
                self.doneWithToday()

    def genMissionStatusReport(self, mids, test_mode=True):
        # assumptions: mids should have already been error checked.
        print("mids: ", mids)
        results = []
        if test_mode:
            # just to test commander GUI can handle the result
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "scheduled", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "completed", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "running", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "500", "aet": "2023-11-09 01:22:12", "status": "warned", "error": "505"}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "300", "aet": "2023-11-09 01:22:12", "status": "aborted", "error": "5"}
            results.append(result)
        else:
            for mid in mids:
                if mid > 0 and mid < len(self.missions):
                    print("working on MID:", mid)
                    m_stat_parts = self.missions[mid].getStatus().split(":")
                    m_stat = m_stat_parts[0]
                    if len(m_stat_parts) > 1:
                        m_err = m_stat_parts[1]
                    else:
                        m_err = ""
                    result = {
                        "mid": mid,
                        "botid": self.missions[mid].getBid(),
                        "sst": self.missions[mid].getEstimatedStartTime(),
                        "sd": self.missions[mid].getEstimatedRunTime(),
                        "ast": self.missions[mid].getActualStartTime(),
                        "aet": self.missions[mid].getActualEndTime(),
                        "status": m_stat,
                        "error": m_err
                    }
                    results.append(result)


        print("mission status result:", results)
        return results


    # '{"cmd":"reqStatusUpdate", "missions":"all"}'
    # content format varies according to type.
    def processCommanderMsgs(self, msgString):
        print("received from commander: ", msgString)
        msg = json.loads(msgString)
        # first, check ip and make sure this from a know vehicle.
        if msg["cmd"] == "reqStatusUpdate":
            if msg["missions"] != "":
                if msg["missions"] == "all":
                    mids = [m.getMid() for m in self.missions]
                else:
                    mid_chars = msg["missions"].aplit(",")
                    mids = [int(mc) for mc in mid_chars]

                # capture all the status of all the missions specified and send back the commander...
                statusJson = self.genMissionStatusReport(mids, False)
                msg = "{\"ip\": \"" + self.ip + "\", \"type\":\"status\", \"content\":\"" + json.dumps(statusJson).replace('"', '\\"') +"\"}"
                # send to commander
                self.commanderXport.write(msg.encode('utf8'))

        elif msg["cmd"] == "reqCancelMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
            # first check if the missions are completed or being run or not, if so nothing could be done.
            # otherwise, simply update the mission status to be "Cancelled"
        elif msg["cmd"] == "reqSetSchedule":
            # schedule work now..... append to array data structure and set up the pointer to the 1st task.
            # the actual running of the tasks will be taken care of by the schduler.
            localworks = json.loads(msg["todos"])
            self.addBotsMissionsFromCommander(msg["bots"], msg["missions"])
            print("received work request:", localworks)
            # send work into work Queue which is the self.todays_work["tbd"] data structure.
            for key, value in localworks.items():
                if isinstance(value, list) and len(value) > 0:
                    current_tz = key
                    current_tz_works = value
                    if len(current_tz_works[0]["bw_works"]) > 0:
                        current_group = "bw_works"
                    else:
                        current_group = "other_works"
                    break
            self.todays_work["tbd"].append({"name": "automation", "works": localworks, "status": "yet to start", "current tz": current_tz, "current grp": current_group, "current bidx": 0, "current widx": 0, "current oidx": 0, "competed": [], "aborted": []})
            print("after assigned work, ", len(self.todays_work["tbd"]), "todos exists in the queue.", self.todays_work["tbd"])
            # clean up the reports on this vehicle....
            self.todaysReports = []

        elif msg["cmd"] == "reqCancelAllMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
        elif msg["cmd"] == "reqHaltMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
            # simply change the mission's status to be "Halted" again, this will make task runner to run this mission
        elif msg["cmd"] == "reqResumeMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
            # simply change the mission's status to be "Scheduled" again, this will make task runner to run this mission
        elif msg["cmd"] == "reqAddMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
            # this is for manual generated missions, simply added to the todo list.


    # a run report is just an array of the following object:
    # MissionStatus {
    #     mid: ID!
    #     bid: ID!
    #     blevels: String!
    #     status: String!
    #     }
    # 1 report is for 1 TBD workgroup.
    def genRunReport(self, last_start, last_end, current_mid, current_bid, run_status):
        statReport = None
        tzi = 0
        #only generate report when all done.
        works = self.todays_work["tbd"][0]["works"]

        if current_bid < 0:
            current_bid = 0

        print("GEN REPORT FOR WORKS:", works)
        if not self.hostrole == "CommanderOnly":
            # for platoon or commander does work itself, need to gather current todo's report , each mission's run result
            # for tzi in Tzs:
            #     if len(works[tzi]) > 0:
            #         for bi in range(len(works[tzi])):
            #             if len(works[tzi][bi]["other_works"]) > 0:
            #                 for oi in range(len(works[tzi][bi]["other_works"])):
            #                     self.todaysReport.append({ "mid": works[tzi][bi]["bw_works"][wi]["mid"], "bid": works[tzi][bi]["bid"], "starttime": last_start, "endtime": last_end, "status": run_status})
            #
            #             if len(works[tzi][bi]["bw_works"]) > 0:
            #                 for wi in range(len(works[tzi][bi]["bw_works"])):
            #                     self.todaysReport.append({ "mid": works[tzi][bi]["bw_works"][wi]["mid"], "bid": works[tzi][bi]["bid"], "starttime": last_start, "endtime": last_end, "status": run_status})
            #
            # self.todaysReport.append({ "mid": current_mid, "bid": current_bid, "starttime": last_start, "endtime": last_end, "status": run_status})
            mission_report = {"mid": current_mid, "bid": current_bid, "starttime": last_start, "endtime": last_end, "status": run_status}

            if self.hostrole != "Platoon":
                # add generated report to report list....
                self.todaysPlatoonReports.append(self.todaysReport)
            else:
                # self.todaysPlatoonReports.append(str.encode(json.dumps(rpt)))
                self.todaysPlatoonReports.append(self.todaysReport)

        return self.todaysReport

    def updateMissionsStatsFromReports(self, all_reports):
        for rpt in all_reports:
            found = next((x for x in self.missions if x.getMid() == rpt["mid"]), None)
            if found:
                found.setStatus(rpt["status"])
                found.setActualStartTime(rpt["starttime"])
                found.setActualEndTime(rpt["endtime"])

            # for tz, tzw in rpt:
            #     if len(tzw) > 0:
            #         if len(tzw["bw_works"]) > 0:
            #             for m in tzw["bw_works"]:
            #                 found = next((x for x in self.missions if x.getMid() == m["mid"]), None)
            #                 if found:
            #                     found.setStatus(m["status"])
            #
            #         if len(tzw["other_works"]) > 0:
            #             for m in tzw["other_works"]:
            #                 found = next((x for x in self.missions if x.getMid() == m["mid"]), None)
            #                 if found:
            #                     found.setStatus(m["status"])


    # all work done today, now
    # 1) send report to the network,
    # 2) save report to local logs,
    # 3) clear today's work data structures.
    #
    def doneWithToday(self):
        global commanderXport
        # call reportStatus API to send today's report to API
        print("Done with today!")

        if not self.hostrole == "Platoon":
            if self.hostrole == "Commander":
                rpt = {"ip": self.ip, "type": "report", "content": self.todaysReports}
                self.todaysPlatoonReports.append(rpt)

            if len(self.todaysPlatoonReports) > 0:
                # flatten the report data structure...
                allTodoReports = [item for pr in self.todaysPlatoonReports for item in pr["content"]]
                print("ALLTODOREPORTS:", allTodoReports)
                # missionReports = [item for pr in allTodoReports for item in pr]
            else:
                missionReports = []

            self.updateMissionsStatsFromReports(allTodoReports)

            print("TO be sent to cloud side::", allTodoReports)
            # if this is a commmander, then send report to cloud
            send_completion_status_to_cloud(self.session, allTodoReports, self.tokens['AuthenticationResult']['IdToken'])
        else:
            # if this is a platoon, send report to commander today's report is just an list mission status....
            rpt = {"ip": self.ip, "type": "report", "content": self.todaysReports}
            print("Sending report to Commander::", rpt)
            self.commanderXport.write(str.encode(json.dumps(rpt)))

        # 2) log reports on local drive.
        self.saveDailyRunReport(self.todaysPlatoonReports)

        # 3) clear data structure, set up for tomorrow morning, this is the case only if this is a commander
        if not self.hostrole == "Platoon":
            self.todays_work = {"tbd": [{"name": "fetch schedule", "works": self.gen_default_fetch(), "status": "yet to start", "current tz": "eastern", "current grp": "other_works", "current bidx": 0, "current widx": 0, "current oidx": 0, "completed" : [], "aborted": []}]}

        self.todays_completed = []
        self.todaysReports = []
        self.todaysPlatoonReports = []

    def obtainTZ(self):
        local_time = time.localtime()  # returns a `time.struct_time`
        tzname_local = local_time.tm_zone
        if "East" in tzname_local or "EST" in tzname_local:
            tz = "eastern"
        elif "Pacific" in tzname_local or "PST" in tzname_local:
            tz = "pacific"
        elif "Central" in tzname_local or "CST" in tzname_local:
            tz = "central"
        elif "Mountain" in tzname_local or "MST" in tzname_local:
            tz = "mountain"
        elif "Alaska" in tzname_local or "AST" in tzname_local:
            tz = "alaska"
        elif "Hawaii" in tzname_local or "HST" in tzname_local:
            tz = "hawaii"
        else:
            tz = "eastern"

        return tz

    def getTZ(self):
        return self.tz

    def gen_default_fetch(self):
        FETCH_ROUTINE = {
            "eastern": [{
                "bid": 0,
                "tz": self.tz,
                "bw_works": [],
                "other_works": [{
                    "mid": 0,
                    "name": "fetch schedules",
                    "cuspas": "",
                    "todos": None,
                    "start_time": START_TIME,
                    "end_time": "",
                    "stat": "nys"
                }],
            }],
            "central": [],
            "moutain": [],
            "pacific": [],
            "alaska": [],
            "hawaii": []
        }

        return FETCH_ROUTINE


    def closeEvent(self):
        #Your desired functionality here
        print('Program quitting....')

        if self.dbcon:
            self.dbconn.close()

        sys.exit(0)

    def createTrialRunMission(self):
        self.trMission = EBMISSION(self)
        self.trMission.pubAttributes.setType(20231225, "user", "Sell")
        self.trMission.pubAttributes.setBot(0)
        self.trMission.setCusPAS("win,chrome,amz")
        self.missions.append(self.trMission)

    def addSkillToTrialRunMission(self, skid):
        found = False
        for m in self.missions:
            if m.getMid == 20231225:
                found = True
                break
        if found:
            m.setSkills([skid])

    def getTrialRunMission(self):
        found = False
        for m in self.missions:
            if m.getMid == 20231225:
                found = True
                break
        if found:
            return m
        else:
            return None