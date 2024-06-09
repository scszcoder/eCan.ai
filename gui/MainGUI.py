import asyncio
import base64
import copy
import math
import random
import sys
import traceback
import webbrowser
from _csv import reader
from os.path import exists

from PySide6.QtCore import QThreadPool, QParallelAnimationGroup, Qt, QPropertyAnimation, QAbstractAnimation, QEvent
from PySide6.QtGui import QFont, QIcon, QAction, QStandardItemModel, QTextCursor
from PySide6.QtWidgets import QMenuBar, QWidget, QScrollArea, QFrame, QToolButton, QGridLayout, QSizePolicy, QTextEdit, \
    QApplication, QVBoxLayout, QPushButton, QLabel, QLineEdit, QHBoxLayout, QListView, QSplitter, QMainWindow, QMenu, \
    QMessageBox, QFileDialog, QPlainTextEdit

import importlib
import importlib.util

from globals.bot_service import BotService
from globals.mission_service import MissionService
from globals.model import BotModel, MissionModel
from globals.product_service import ProductService
from globals.skill_service import SkillService
from tests.TestAll import Tester

from gui.BotGUI import BotNewWin
from gui.ChatGui import ChatWin
from bot.Cloud import set_up_cloud, send_feedback_request_to_cloud, upload_file, send_add_missions_request_to_cloud, \
    send_remove_missions_request_to_cloud, send_update_missions_request_to_cloud, send_add_bots_request_to_cloud, \
    send_update_bots_request_to_cloud, send_remove_bots_request_to_cloud, send_add_skills_request_to_cloud, \
    send_get_bots_request_to_cloud
from gui.FlowLayout import BotListView, MissionListView, DragPanel
from bot.Logger import log3
from gui.LoggerGUI import CommanderLogWin
from gui.MissionGUI import MissionNewWin
from gui.PlatoonGUI import PlatoonListView, PlatoonWindow
from gui.ScheduleGUI import ScheduleWin
from gui.SkillManagerGUI import SkillManagerWindow
from gui.TrainGUI import TrainNewWin, ReminderWin
from bot.WorkSkill import WORKSKILL
from bot.adsPowerSkill import formADSProfileBatchesFor1Vehicle
from bot.basicSkill import STEP_GAP
from bot.envi import getECBotDataHome
from bot.genSkills import genSkillCode, getWorkRunSettings, setWorkSettingsSkill, SkillGeneratorTable
from bot.inventories import INVENTORY
from bot.lzstring import LZString
import os
import openpyxl
from datetime import timedelta
import platform
from pynput.mouse import Controller

from bot.network import myname, fieldLinks
from bot.readSkill import RAIS, first_step, get_printable_datetime, readPSkillFile, addNameSpaceToAddress
from gui.ui_settings import SettingsWidget
from bot.vehicles import VEHICLE
from tool.MainGUITool import FileResource, StaticResource, init_sql_file
from tool.MainGUITool import SqlProcessor
from utils.logger_helper import logger_helper
from tests.unittests import *
import pandas as pd
from encrypt import *

START_TIME = 15      # 15 x 20 minute = 5 o'clock in the morning

Tzs = ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"]

rpaConfig = None

ecb_data_homepath = getECBotDataHome()


# adopted from web: https://stackoverflow.com/questions/32476006/how-to-make-an-expandable-collapsable-section-widget-in-qt
class Expander(QWidget):
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
        self.toggleAnimation = QParallelAnimationGroup()
        self.contentArea = QScrollArea()
        self.headerLine = QFrame()
        self.toggleButton = QToolButton()
        self.mainLayout = QGridLayout()

        toggleButton = self.toggleButton
        toggleButton.setStyleSheet("QToolButton { border: none; }")
        toggleButton.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        toggleButton.setArrowType(Qt.RightArrow)
        toggleButton.setText(str(title))
        toggleButton.setCheckable(True)
        toggleButton.setChecked(False)

        headerLine = self.headerLine
        headerLine.setFrameShape(QFrame.HLine)
        headerLine.setFrameShadow(QFrame.Sunken)
        headerLine.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

        self.contentArea.setStyleSheet("QScrollArea { background-color: white; border: none; }")
        self.contentArea.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # start out collapsed
        self.contentArea.setMaximumHeight(0)
        self.contentArea.setMinimumHeight(0)
        # let the entire widget grow and shrink with its content
        toggleAnimation = self.toggleAnimation
        toggleAnimation.addAnimation(QPropertyAnimation(self, b"minimumHeight"))
        toggleAnimation.addAnimation(QPropertyAnimation(self, b"maximumHeight"))
        toggleAnimation.addAnimation(QPropertyAnimation(self.contentArea, b"maximumHeight"))
        # don't waste space
        mainLayout = self.mainLayout
        mainLayout.setVerticalSpacing(0)
        mainLayout.setContentsMargins(0, 0, 0, 0)
        row = 0
        mainLayout.addWidget(self.toggleButton, row, 0, 1, 1, Qt.AlignLeft)
        mainLayout.addWidget(self.headerLine, row, 2, 1, 1)
        row += 1
        mainLayout.addWidget(self.contentArea, row, 0, 1, 3)
        self.setLayout(self.mainLayout)
        self.toggleButton.clicked.connect(self.start_animation)

    def start_animation(self, checked):
        arrow_type = Qt.DownArrow if checked else Qt.RightArrow
        direction = QAbstractAnimation.Forward if checked else QAbstractAnimation.Backward
        self.toggleButton.setArrowType(arrow_type)
        self.toggleAnimation.setDirection(direction)
        self.toggleAnimation.start()



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


class AsyncInterface:
    """ Class to handle async tasks within the Qt Event Loop. """
    def __init__(self,queue):
        self.active_queue = queue
        asyncio.create_task(self.worker_task())  # Start the worker task

    def set_active_queue(self, bot):
        self.active_queue = bot.getMsgQ()

    async def worker_task(self):
        """ Asynchronous worker task processing items from the queue. """
        while True:
            message = await self.queue.get()
            self.showMsg(f"Processed message from GUI: {message}")
            self.queue.task_done()

# class MainWindow(QWidget):
class MainWindow(QMainWindow):
    def __init__(self, parent, main_key, inTokens, tcpserver, ip, user, homepath, gui_msg_queue, machine_role, lang):
        super(MainWindow, self).__init__()
        self.loginout_gui = parent
        if homepath[len(homepath)-1] == "/":
            self.homepath = homepath[:len(homepath)-1]
        else:
            self.homepath = homepath
        self.gui_net_msg_queue = gui_msg_queue
        self.gui_rpa_msg_queue = asyncio.Queue()
        self.gui_monitor_msg_queue = asyncio.Queue()
        self.lang = lang
        self.tz = self.obtainTZ()
        self.file_resouce = FileResource(self.homepath)
        self.SELLER_INVENTORY_FILE = ecb_data_homepath + "/resource/inventory.json"
        self.DONE_WITH_TODAY = True
        self.gui_chat_msg_queue = asyncio.Queue()
        self.static_resource = StaticResource()
        self.all_ads_profiles_xls = "C:/AmazonSeller/SelfSwipe/test_all.xls"
        self.session = set_up_cloud()
        self.tokens = inTokens
        self.machine_role = machine_role
        self.ip = ip
        self.main_key = main_key

        self.user = user
        self.cog = None
        self.cog_client = None
        self.hostrole = machine_role
        self.workingState = "Idle"
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]
        self.platform = platform.system().lower()[0:3]

        self.std_item_font = QFont('Arial', 10)

        self.sellerInventoryJsonData = None
        self.botJsonData = None
        self.inventories = []

        self.bot_cookie_site_lists = {}
        self.ads_profile_dir = ecb_data_homepath + "/ads_profiles"

        self.ads_settings_file = self.ads_profile_dir + "/ads_settings.json"
        self.ads_settings = {"user name": "", "user pwd": "", "batch_size": 2}

        # self.readBotJsonFile()
        self.vehicles = []                      # computers on LAN that can carry out bots's tasks.， basically tcp transports
        self.bots = []
        self.missions = []              # mission 0 will always default to be the fetch schedule mission
        self.trMission = self.createTrialRunMission()
        self.skills = []
        self.missionsToday = []
        self.platoons = []
        self.products = []
        self.zipper = LZString()
        self.threadPool = QThreadPool()
        self.selected_bot_row = -1
        self.selected_mission_row = -1
        self.selected_bot_item = None
        self.selected_mission_item = None
        self.BotNewWin = None
        self.missionWin = None
        self.chatWin = None
        self.trainNewSkillWin = None
        self.reminderWin = None
        self.platoonWin = None

        self.logConsoleBox = Expander(self, QApplication.translate("QWidget", "Log Console:"))
        self.logConsole = QPlainTextEdit()
        self.logConsole.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self.logConsole.setReadOnly(True)
        # self.logConsole.verticalScrollBar().setValue(self.logConsole.verticalScrollBar().minimum())
        self.logConsoleLayout = QVBoxLayout()
        self.logConsole.verticalScrollBar().valueChanged.connect(self.onScrollBarValueChanged)
        self.isAutoScroll = False  # 初始化时默认不自动滚动
        # self.toggle_button = QToolButton(
        #     text="log console", checkable=True, checked=False
        # )
        # self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        # self.toggle_button.setToolButtonStyle(
        #     Qt.ToolButtonTextBesideIcon
        # )
        # self.toggle_button.setArrowType(Qt.RightArrow)
        # self.toggle_button.pressed.connect(self.on_tg_pressed)

        self.logConsoleLayout.addWidget(self.logConsole)
        self.logConsoleBox.setContentLayout(self.logConsoleLayout)

        self.SkillManagerWin = SkillManagerWindow(self)
        self.SettingsWin = SettingsWidget(self)
        self.netLogWin = CommanderLogWin(self)
        self.machine_name = myname

        self.todaysReport = []              # per task group. (inside this report, there are list of individual task/mission result report.
        self.todaysReports = []             # per vehicle/host
        self.todaysPlatoonReports = []
        self.tester = Tester()
        self.wifis = []
        self.dbfile = self.homepath + "/resource/data/myecb.db"

        self.readSellerInventoryJsonFile("")

        self.showMsg("main window ip:" + self.ip)
        if self.machine_role != "Platoon":
            self.tcpServer = tcpserver
            self.commanderXport = None
        else:
            self.showMsg("This is a platoon...")
            self.commanderXport = tcpserver
            self.tcpServer = None

        self.showMsg("self.platform==================================================>" + self.platform)
        if os.path.exists(self.ads_settings_file):
            with open(self.ads_settings_file, 'r') as ads_settings_f:
                ads_settings = json.load(ads_settings_f)

            ads_settings_f.close()

        self.showMsg("HOME PATH is::" + self.homepath, "info")
        self.showMsg(self.dbfile)
        if self.machine_role != "Platoon":
            init_sql_file(self.dbfile)
            self.bot_service = BotService(self)
            self.mission_service = MissionService(self)
            self.product_service = ProductService(self)
            self.skill_service = SkillService(self)

        self.owner = "NA"
        self.botRank = "soldier"  # this should be read from a file which is written during installation phase, user will select this during installation phase
        self.rpa_work_assigned_for_today = False

        self.save_all_button = QPushButton(QApplication.translate("QPushButton", "Save All"))
        self.log_out_button = QPushButton(QApplication.translate("QPushButton", "Logout"))
        self.south_layout = QVBoxLayout(self)
        self.south_layout.addWidget(self.logConsoleBox)
        self.bottomButtonsLayout = QHBoxLayout(self)
        self.bottomButtonsLayout.addWidget(self.save_all_button)
        self.south_layout.addLayout(self.bottomButtonsLayout)
        self.bottomButtonsLayout.addWidget(self.log_out_button)
        self.save_all_button.clicked.connect(self.saveAll)
        self.log_out_button.clicked.connect(self.logOut)

        self.southWidget = QWidget()
        self.southWidget.setLayout(self.south_layout)

        self.menuFont = QFont('Arial', 10)
        self.mainWidget = QWidget()
        self.westScrollArea = QWidget()
        self.westScrollLayout = QVBoxLayout(self)
        self.westScrollLabel = QLabel(QApplication.translate("QLabel", "Missions:"), alignment=Qt.AlignLeft)
        self.westScrollLabel.setFont(self.menuFont)

        self.centralScrollArea = QWidget()
        self.centralScrollLayout = QVBoxLayout(self)
        self.centralScrollLabel = QLabel(QApplication.translate("QLabel", "Bots:"), alignment=Qt.AlignLeft)
        self.centralScrollLabel.setFont(self.menuFont)

        self.east0ScrollArea = QWidget()
        self.east0ScrollLayout = QVBoxLayout(self)
        if (self.machine_role == "Platoon"):
            self.east0ScrollLabel = QLabel(QApplication.translate("QLabel", "Running Missions:"), alignment=Qt.AlignLeft)
        else:
            self.east0ScrollLabel = QLabel(QApplication.translate("QLabel", "Vehicles:"), alignment=Qt.AlignLeft)
        self.east0ScrollLabel.setFont(self.menuFont)

        self.east1ScrollArea = QWidget()
        self.east1ScrollLayout = QVBoxLayout(self)

        self.east1ScrollLabel = QLabel(QApplication.translate("QLabel", "Completed Missions:"), alignment=Qt.AlignLeft)
        self.east1ScrollLabel.setFont(self.menuFont)

        self.westScroll = QScrollArea()
        self.centralScroll = QScrollArea()
        self.east0Scroll = QScrollArea()
        self.east1Scroll = QScrollArea()

        self.search_mission_button = QPushButton(QApplication.translate("QPushButton", "Search"))
        self.search_mission_button.clicked.connect(self.searchLocalMissions)

        self.mission_from_date_label = QLabel(QApplication.translate("QLabel", "From:"), alignment=Qt.AlignLeft)
        self.mission_from_date_edit = QLineEdit()
        self.mission_from_date_edit.setPlaceholderText(QApplication.translate("QLineEdit", "YYYY-MM-DD"))
        self.mission_to_date_label = QLabel(QApplication.translate("QLabel", "To:"), alignment=Qt.AlignLeft)
        self.mission_to_date_edit = QLineEdit()
        self.mission_to_date_edit.setPlaceholderText(QApplication.translate("QLineEdit", "YYYY-MM-DD"))

        self.mission_search_layout = QHBoxLayout(self)
        self.mission_search_edit = QLineEdit()
        self.mission_search_edit.setClearButtonEnabled(True)
        self.mission_search_edit.addAction(QIcon(self.homepath + '/resource/images/icons/search1_80.png'), QLineEdit.LeadingPosition)
        self.mission_search_edit.setPlaceholderText(QApplication.translate("QLineEdit", "col:phrase"))
        self.mission_search_edit.returnPressed.connect(self.search_mission_button.click)
        self.mission_search_layout.addWidget(self.mission_from_date_label)
        self.mission_search_layout.addWidget(self.mission_from_date_edit)
        self.mission_search_layout.addWidget(self.mission_to_date_label)
        self.mission_search_layout.addWidget(self.mission_to_date_edit)
        self.mission_search_layout.addWidget(self.mission_search_edit)
        self.mission_search_layout.addWidget(self.search_mission_button)

        self.westScrollLayout.addLayout(self.mission_search_layout)
        self.westScrollLayout.addWidget(self.westScrollLabel)
        self.westScrollLayout.addWidget(self.westScroll)
        self.westScrollArea.setLayout(self.westScrollLayout)

        self.search_bot_button = QPushButton(QApplication.translate("QPushButton", "Search"))
        self.search_bot_button.clicked.connect(self.searchLocalBots)

        self.bot_from_date_label = QLabel(QApplication.translate("QLabel", "From:"), alignment=Qt.AlignLeft)
        self.bot_from_date_edit = QLineEdit()
        self.bot_from_date_edit.setPlaceholderText(QApplication.translate("QLineEdit", "YYYY-MM-DD"))
        self.bot_to_date_label = QLabel(QApplication.translate("QLabel", "To:"), alignment=Qt.AlignLeft)
        self.bot_to_date_edit = QLineEdit()
        self.bot_to_date_edit.setPlaceholderText(QApplication.translate("QLineEdit", "YYYY-MM-DD"))

        self.bot_search_layout = QHBoxLayout(self)
        self.bot_search_edit = QLineEdit()
        self.bot_search_edit.setClearButtonEnabled(True)
        self.bot_search_edit.addAction(QIcon(self.homepath + '/resource/images/icons/search1_80.png'), QLineEdit.LeadingPosition)
        self.bot_search_edit.setPlaceholderText(QApplication.translate("QLineEdit", "col:phrase"))
        self.bot_search_edit.returnPressed.connect(self.search_bot_button.click)
        self.bot_search_layout.addWidget(self.bot_from_date_label)
        self.bot_search_layout.addWidget(self.bot_from_date_edit)
        self.bot_search_layout.addWidget(self.bot_to_date_label)
        self.bot_search_layout.addWidget(self.bot_to_date_edit)
        self.bot_search_layout.addWidget(self.bot_search_edit)
        self.bot_search_layout.addWidget(self.search_bot_button)

        self.centralScrollLayout.addLayout(self.bot_search_layout)
        self.centralScrollLayout.addWidget(self.centralScrollLabel)
        self.centralScrollLayout.addWidget(self.centralScroll)
        self.centralScrollArea.setLayout(self.centralScrollLayout)


        self.east0ScrollLayout.addWidget(self.east0ScrollLabel)
        self.east0ScrollLayout.addWidget(self.east0Scroll)
        self.east0ScrollArea.setLayout(self.east0ScrollLayout)

        self.east1ScrollLayout.addWidget(self.east1ScrollLabel)
        self.east1ScrollLayout.addWidget(self.east1Scroll)
        self.east1ScrollArea.setLayout(self.east1ScrollLayout)

        self.westScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.westScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.westScroll.setWidgetResizable(True)

        self.centralScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setWidgetResizable(True)

        self.east0Scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.east0Scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.east0Scroll.setWidgetResizable(True)

        self.east1Scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.east1Scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.east1Scroll.setWidgetResizable(True)

        #creating QActions
        self.botNewAction = self._createBotNewAction()
        self.botGetAction = self._createGetBotsAction()
        self.botGetLocalAction = self._createGetLocalBotsAction()
        self.saveAllAction = self._createSaveAllAction()
        self.botDelAction = self._createBotDelAction()
        self.botEditAction = self._createBotEditAction()
        self.botCloneAction = self._createBotCloneAction()
        self.botNewFromFileAction = self._createBotNewFromFileAction()

        self.missionNewAction = self._createMissionNewAction()
        self.missionDelAction = self._createMissionDelAction()
        self.missionEditAction = self._createMissionEditAction()
        self.missionImportAction = self._createMissionImportAction()

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

        self.popMenu = QMenu(self)
        self.pop_menu_font = QFont("Helvetica", 10)
        self.popMenu.setFont(self.pop_menu_font)

        self.popMenu.addAction(QAction(QApplication.translate("QAction", "&Edit"), self))
        self.popMenu.addAction(QAction(QApplication.translate("QAction", "&Clone"), self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QAction(QApplication.translate("QAction", "&Delete"), self))

        self.botListView = BotListView(self)
        self.botListView.installEventFilter(self)
        self.botModel = QStandardItemModel(self.botListView)

        self.missionListView = MissionListView(self)
        self.missionListView.installEventFilter(self)
        self.missionModel = QStandardItemModel(self.missionListView)

        self.running_missionListView = MissionListView()
        self.runningMissionModel = QStandardItemModel(self.running_missionListView)

        self.vehicleListView = PlatoonListView(self)
        self.vehicleListView.installEventFilter(self)
        self.runningVehicleModel = QStandardItemModel(self.vehicleListView)

        # self.skillListView = SkillListView(self)
        # self.skillListView.installEventFilter(self)
        # self.skillModel = QStandardItemModel(self.skillListView)

        self.completed_missionListView = MissionListView()
        self.completed_missionListView.installEventFilter(self)
        self.completedMissionModel = QStandardItemModel(self.completed_missionListView)

        self.mtvViewAction = self._createMTVViewAction()
        # self.fieldMonitorAction = self._createFieldMonitorAction()
        self.commandSendAction = self._createCommandSendAction()

        # Apply the model to the list view
        self.botListView.setModel(self.botModel)
        self.botListView.setViewMode(QListView.IconMode)
        self.botListView.setMovement(QListView.Snap)

        # self.skillListView.setModel(self.skillModel)
        # self.skillListView.setViewMode(QListView.IconMode)
        # self.skillListView.setMovement(QListView.Snap)

        # self.mission0 = EBMISSION(self)
        # self.missionModel.appendRow(self.mission0)
        # self.missions.append(self.mission0)

        self.missionListView.setModel(self.missionModel)
        self.missionListView.setViewMode(QListView.ListMode)
        self.missionListView.setMovement(QListView.Snap)

        self.running_missionListView.setModel(self.runningMissionModel)
        self.running_missionListView.setViewMode(QListView.ListMode)
        self.running_missionListView.setMovement(QListView.Snap)

        self.vehicleListView.setModel(self.runningVehicleModel)
        self.vehicleListView.setViewMode(QListView.ListMode)
        self.vehicleListView.setMovement(QListView.Snap)

        self.completed_missionListView.setModel(self.completedMissionModel)
        self.completed_missionListView.setViewMode(QListView.ListMode)
        self.completed_missionListView.setMovement(QListView.Snap)

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

            self.skillNewAction.setDisabled(True)
            self.skillDeleteAction.setDisabled(True)
            self.skillShowAction.setDisabled(True)
            self.skillUploadAction.setDisabled(True)

            self.skillNewFromFileAction.setDisabled(True)


        # centralWidget.addBot(self.botListView)
        self.centralScroll.setWidget(self.botListView)


        #centralWidget.setPlainText("Central widget")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)
        self.centralSplitter = QSplitter(Qt.Horizontal)
        self.bottomSplitter = QSplitter(Qt.Vertical)



        # Because BorderLayout doesn't call its super-class addWidget() it
        # doesn't take ownership of the widgets until setLayout() is called.
        # Therefore we keep a local reference to each label to prevent it being
        # garbage collected too soon.
        #label_n = self.createLabel("North")
        # layout.addWidget(label_n, BorderLayout.North)
        self.menuBar = self._createMenuBar()
        self.mbWidget = QWidget()
        self.mbLayout = QVBoxLayout(self)
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
        self.todays_scheduled_task_groups = {"win": [], "mac": [], "linux": []}
        self.unassigned_task_groups = {"win": [], "mac": [], "linux": []}
        self.checkVehicles()

        # get current wifi ssid and store it.
        self.showMsg("OS platform: "+self.platform)
        wifi_info = None
        if self.platform == "win":
            wifi_info = subprocess.check_output(['netsh', 'WLAN', 'show', 'interfaces'])
        elif self.platform == 'dar':
            wifi_info = subprocess.check_output(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'])

        if wifi_info:
            wifi_data = wifi_info.decode('utf-8')
            wifi_lines = wifi_data.split("\n")
            ssidline = [l for l in wifi_lines if " SSID" in l]
            if len(ssidline) == 1:
                ssid = ssidline[0].split(":")[1].strip()
                self.wifis.append(ssid)
        else:
            print("***wifi info is None!")


        self.showMsg("load local bots, mission, skills ")
        if (self.machine_role != "Platoon"):
            # load skills into memory.
            self.bot_service.sync_cloud_bot_data(self.session, self.tokens)
            bots_data = self.bot_service.find_all_bots()
            self.loadLocalBots(bots_data)
            self.mission_service.sync_cloud_mission_data(self.session, self.tokens)
            missions_data = self.mission_service.find_missions_by_createon()
            self.loadLocalMissions(missions_data)
            self.dailySkillsetUpdate()

        # Done with all UI stuff, now do the instruction set extension work.
        self.showMsg("set up rais extensions ")
        rais_extensions_file = ecb_data_homepath + "/my_rais_extensions/my_rais_extensions.json"
        rais_extensions_dir = ecb_data_homepath + "/my_rais_extensions/"
        added_handlers=[]
        if os.path.isfile(rais_extensions_file):
            with open(rais_extensions_file, 'r') as rais_extensions:
                user_rais_modules = json.load(rais_extensions)
                for i, user_module in enumerate(user_rais_modules):
                    module_file = rais_extensions_dir + user_module["file"]
                    added_ins = user_module['instructions']
                    module_name = os.path.splitext(user_module["file"])[0]
                    spec = importlib.util.spec_from_file_location(module_name, module_file)
                    # Create a module object from the spec
                    module = importlib.util.module_from_spec(spec)
                    # Load the module
                    spec.loader.exec_module(module)

                    for ins in added_ins:
                        if hasattr(module, ins["handler"]):
                            RAIS[ins["instruction name"]] = getattr(module, ins["handler"])

        run_experience_file = ecb_data_homepath + "/run_experience.txt"
        if os.path.exists(run_experience_file):
            try:
                with open(run_experience_file, 'rb') as fileTBRead:
                    icon_match_dict = json.load(fileTBRead)
                    fileTBRead.close()
            except json.JSONDecodeError:
                self.showMsg("ERROR: json loads an wrongly formated json file")
                icon_match_dict = {}
            except Exception as e:
                self.showMsg("ERROR: unexpected json load error")
                icon_match_dict = {}

        self.showMsg("set up fetching schedule ")
        # now hand daily tasks
        self.todays_work = {"tbd": [], "allstat": "working"}
        self.todays_completed = []
        self.num_todays_task_groups = 0
        if not self.hostrole == "Platoon":
            # For commander creates
            self.todays_work["tbd"].append({"name": "fetch schedule", "works": self.gen_default_fetch(), "status": "yet to start", "current widx": 0, "completed" : [], "aborted": []})
            self.num_todays_task_groups = self.num_todays_task_groups + 1
            # point to the 1st task to run for the day.
            self.update1WorkRunStatus(self.todays_work["tbd"][0], 0)

        # self.async_interface = AsyncInterface()
        self.showMsg("ready to spawn mesg server task")
        if not self.hostrole == "Platoon":
            self.peer_task = asyncio.create_task(self.servePlatoons(self.gui_net_msg_queue))
        else:
            self.peer_task = asyncio.create_task(self.serveCommander(self.gui_net_msg_queue))

        # the message queue are
        self.monitor_task = asyncio.create_task(self.runRPAMonitor(self.gui_monitor_msg_queue))
        self.showMsg("spawned runbot task")

        # the message queue are
        # asyncio.create_task(self.runbotworks(self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
        # self.showMsg("spawned runbot task")

        self.chat_task = asyncio.create_task(self.connectChat(self.gui_chat_msg_queue))
        self.showMsg("spawned chat task")

        # with ThreadPoolExecutor(max_workers=3) as self.executor:
        #     self.rpa_task_future = asyncio.wrap_future(self.executor.submit(self.runbotworks, self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
        #     self.showMsg("spawned RPA task")

        # await asyncio.gather(peer_task, monitor_task, chat_task, rpa_task_future)
        loop = asyncio.get_event_loop()
        # executor = ThreadPoolExecutor()
        # asyncio.run_coroutine_threadsafe(self.run_async_tasks(loop, executor), loop)

        asyncio.run_coroutine_threadsafe(self.run_async_tasks(), loop)

    async def run_async_tasks(self):
        self.rpa_task = asyncio.create_task(self.runbotworks(self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
        await asyncio.gather(self.peer_task, self.monitor_task, self.chat_task, self.rpa_task)

    def dailySkillsetUpdate(self):
        # this will handle all skill bundled into software itself.
        self.showMsg("load local private skills")
        self.loadLocalPrivateSkills()
        cloud_skills_results = self.SkillManagerWin.fetchMySkills()

        existing_skids = [sk.getSkid() for sk in self.skills]

        if 'body' in cloud_skills_results:
            # self.showMsg("db_skills_results:::::"+json.dumps(db_skills_results))
            cloud_skills = json.loads(cloud_skills_results["body"])
            self.showMsg("Cloud side skills fetched:" + str(len(cloud_skills)))

            # convert json to WORKSKILL object.
            for cloud_skill in cloud_skills:
                if cloud_skill["skid"] not in existing_skids:
                    self.showMsg("db skill:" + json.dumps(cloud_skill))
                    cloud_work_skill = WORKSKILL(self, cloud_skill["name"])
                    cloud_work_skill.loadJson(cloud_skill)
                    self.skills.append(cloud_work_skill)

                    # update skill manager display...
                    self.SkillManagerWin.addSkillRows([cloud_work_skill])

            # for sanity immediately re-generate psk files... and gather dependencies info so that when user creates a new mission
            # when a skill is selected, its dependencies will added to mission's skills list.
            self.regenSkillPSKs()

    def onScrollBarValueChanged(self, value):
        """监听滚动条变化，判断是否自动滚动"""
        scrollbar = self.logConsole.verticalScrollBar()
        max_value = scrollbar.maximum()
        # 如果滚动条接近底部（比如距离底部小于一个单位），则设置为自动滚动
        if (max_value - value) <= 1:
            self.isAutoScroll = True
        else:
            self.isAutoScroll = False

    def addSkillRowsToSkillManager(self):
        self.skillManagerWin.addSkillRows(self.skills)

    def regenSkillPSKs(self):
        for ski, sk in enumerate(self.skills):
            # next_step is not used,
            sk_full_name = sk.getPlatform()+"_"+sk.getApp()+"_"+sk.getSiteName()+"_"+sk.getPage()+"_"+sk.getName()
            self.showMsg("PSK FILE NAME::::::::::"+str(ski)+"::::::"+sk.getPrivacy()+":::::"+sk_full_name)
            next_step, psk_file = genSkillCode(sk_full_name, sk.getPrivacy(), self.homepath, first_step, "light")
            self.showMsg("PSK FILE:::::::::::::::::::::::::"+psk_file)
            sk.setPskFileName(psk_file)
            # fill out each skill's depencies attribute
            sk.setDependencies(self.analyzeMainSkillDependencies(psk_file))


    def getHomePath(self):
        return self.homepath

    def getPLATFORMS(self):
        return self.static_resource.PLATFORMS

    def getAPPS(self):
        return self.static_resource.APPS

    def getSITES(self):
        return self.static_resource.SITES

    def getSMPLATFORMS(self):
        return self.SM_PLATFORMS

    def getBUYTYPES(self):
        return self.BUY_TYPES

    def getSUBBUYTYPES(self):
        return self.static_resource.SUB_BUY_TYPES

    def getSELLTYPES(self):
        return self.static_resource.SELL_TYPES

    def getSUBSELLTYPES(self):
        return self.static_resource.SUB_SELL_TYPES

    def getOPTYPES(self):
        return self.static_resource.OP_TYPES

    def getSUBOPTYPES(self):
        return self.static_resource.SUB_OP_TYPES

    def getSTATUSTYPES(self):
        return self.static_resource.STATUS_TYPES

    def getBUYSTATUSTYPES(self):
        return self.static_resource.BUY_STATUS_TYPES

    def translateSiteName(self, site_text):
        if site_text in self.static_resource.SITES_SH_DICT.keys():
            return self.static_resource.SITES_SH_DICT[site_text]
        else:
            return site_text

    def translatePlatform(self, site_text):
        if site_text in self.static_resource.PLATFORMS_SH_DICT.keys():
            return self.static_resource.PLATFORMS_SH_DICT[site_text]
        else:
            return site_text

    def translateShortSiteName(self, site_text):
        if site_text in self.static_resource.SH_SITES_DICT.keys():
            return self.static_resource.SH_SITES_DICT[site_text]
        else:
            return site_text

    def translateShortPlatform(self, site_text):
        if site_text in self.static_resource.SH_PLATFORMS_DICT.keys():
            return self.static_resource.SH_PLATFORMS_DICT[site_text]
        else:
            return site_text

    def setCog(self, cog):
        self.cog = cog

    def setCogClient(self, client):
        self.cog_client = client

    def on_tg_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            Qt.DownArrow if not checked else Qt.RightArrow
        )

        if self.toggle_button.arrowType() == Qt.DownArrow:
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
        for msg in msgs:
            self.logConsole.appendHtml(msg)
            if self.isAutoScroll:
                cursor = self.logConsole.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.logConsole.setTextCursor(cursor)

    def setTokens(self, intoken):
        self.tokens = intoken

    def createLabel(self, text):
        label = QLabel(QApplication.translate("QLabel", text))
        label.setFrameStyle(QFrame.Box | QFrame.Raised)
        return label

    def _createMenuBar(self):
        self.showMsg("MAIN Creating Menu Bar")
        self.main_menu_bar_font = QFont("Helvetica", 12)
        self.main_menu_font = QFont("Helvetica", 10)

        menu_bar = QMenuBar()
        menu_bar.setFont(self.main_menu_bar_font)
        # Creating menus using a QMenu object

        bot_menu = QMenu(QApplication.translate("QMenu", "&Bots"), self)
        bot_menu.setFont(self.main_menu_font)

        bot_menu.addAction(self.botNewAction)
        bot_menu.addAction(self.botGetAction)
        bot_menu.addAction(self.botGetLocalAction)
        bot_menu.addAction(self.botEditAction)
        bot_menu.addAction(self.botCloneAction)
        bot_menu.addAction(self.botDelAction)
        bot_menu.addAction(self.botNewFromFileAction)
        menu_bar.addMenu(bot_menu)

        mission_menu = QMenu(QApplication.translate("QMenu", "&Missions"), self)
        mission_menu.setFont(self.main_menu_font)
        mission_menu.addAction(self.missionNewAction)
        mission_menu.addAction(self.missionImportAction)
        mission_menu.addAction(self.missionEditAction)
        mission_menu.addAction(self.missionDelAction)
        menu_bar.addMenu(mission_menu)

        platoon_menu = QMenu(QApplication.translate("QMenu", "&Platoons"), self)
        platoon_menu.setFont(self.main_menu_font)
        platoon_menu.addAction(self.mtvViewAction)
        # platoon_menu.addAction(self.fieldMonitorAction)
        platoon_menu.addAction(self.commandSendAction)
        menu_bar.addMenu(platoon_menu)

        settings_menu = QMenu(QApplication.translate("QMenu", "&Settings"), self)
        settings_menu.setFont(self.main_menu_font)
        # settings_menu.addAction(self.settingsAccountAction)
        #settings_menu.addAction(self.settingsImportAction)
        settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(settings_menu)

        reports_menu = QMenu(QApplication.translate("QMenu", "&Reports"), self)
        reports_menu.setFont(self.main_menu_font)
        reports_menu.addAction(self.reportsShowAction)
        reports_menu.addAction(self.reportsGenAction)
        reports_menu.addAction(self.reportsLogConsoleAction)
        menu_bar.addMenu(reports_menu)

        run_menu = QMenu(QApplication.translate("QMenu", "&Run"), self)
        run_menu.setFont(self.main_menu_font)
        run_menu.addAction(self.runRunAllAction)
        run_menu.addAction(self.runTestAllAction)
        menu_bar.addMenu(run_menu)

        schedule_menu = QMenu(QApplication.translate("QMenu", "&Schedule"), self)
        schedule_menu.setFont(self.main_menu_font)
        schedule_menu.addAction(self.fetchScheduleAction)
        schedule_menu.addAction(self.scheduleCalendarViewAction)
        schedule_menu.addAction(self.scheduleFromFileAction)
        schedule_menu.setFont(self.main_menu_font)
        menu_bar.addMenu(schedule_menu)

        skill_menu = QMenu(QApplication.translate("QMenu", "&Skills"), self)
        skill_menu.setFont(self.main_menu_font)
        skill_menu.addAction(self.skillNewAction)
        skill_menu.addAction(self.skillManagerAction)
        # skill_menu.addAction(self.skillDeleteAction)
        # skill_menu.addAction(self.skillShowAction)
        # skill_menu.addAction(self.skillUploadAction)

        skill_menu.addAction(self.skillNewFromFileAction)
        menu_bar.addMenu(skill_menu)

        help_menu = QMenu(QApplication.translate("QMenu", "&Help"), self)
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
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&New"))
        new_action.triggered.connect(self.newBotView)

        return new_action


    def _createBotNewFromFileAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Import"))
        new_action.triggered.connect(self.newBotFromFile)
        return new_action

    def _createGetBotsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Load All Bots"))
        new_action.triggered.connect(self.getAllBotsFromCloud)
        # ew_action.connect(QAction.)

        # new_action.connect(self.newBot)
        # self.newAction.setIcon(QIcon(":file-new.svg"))
        # self.openAction = QAction(QIcon(":file-open.svg"), "&Open...", self)
        # self.saveAction = QAction(QIcon(":file-save.svg"), "&Save", self)
        # self.exitAction = QAction("&Exit", self)
        return new_action

    def _createGetLocalBotsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Load All Local Bots"))
        new_action.triggered.connect(self.findAllBot)
        return new_action

    def _createSaveAllAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Save All"))
        new_action.triggered.connect(self.saveAll)
        return new_action

    def _createBotDelAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Remove"))
        new_action.triggered.connect(self.deleteBot)
        return new_action

    def _createBotEditAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Edit"))
        return new_action

    def _createBotCloneAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Clone"))
        new_action.triggered.connect(self.cloneBot)
        return new_action

    def _createBotEnDisAbleAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Disable"))
        return new_action

    def _createMissionNewAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Create"))
        new_action.triggered.connect(self.newMissionView)

        return new_action

    def _createMTVViewAction(self):
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Vehicles View"))
        new_action.triggered.connect(self.newVehiclesView)

        return new_action


    def _createFieldMonitorAction(self):
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Field Monitor"))
        #new_action.triggered.connect(self.newMissionView)

        return new_action


    def _createCommandSendAction(self):
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Send Command"))
        # new_action.triggered.connect(lambda: self.sendToPlatoons("7000", None))
        cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
        new_action.triggered.connect(lambda: self.sendToPlatoons([], cmd))

        return new_action


    def _createMissionDelAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete M"))
        return new_action


    def _createMissionImportAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Import"))
        new_action.triggered.connect(self.newMissionFromFile)
        return new_action


    def _createMissionEditAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Edit"))
        return new_action


    def _createSettingsAccountAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Account"))
        return new_action

    def _createSettingsEditAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Edit"))
        new_action.triggered.connect(self.editSettings)
        return new_action


    def _createRunRunAllAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Run All"))
        new_action.triggered.connect(self.manualRunAll)
        return new_action

    def _createRunTestAllAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Run All Tests"))
        new_action.triggered.connect(self.runAllTests)
        return new_action


    def _createScheduleCalendarViewAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Calendar View"))
        new_action.triggered.connect(self.scheduleCalendarView)
        return new_action


    def _createFetchScheduleAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Fetch Schedules"))
        new_action.triggered.connect(lambda: self.fetchSchedule("", self.get_vehicle_settings()))
        return new_action


    def _createScheduleNewFromFileAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Test Schedules From File"))
        new_action.triggered.connect(self.fetchScheduleFromFile)
        return new_action

    def _createReportsShowAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&View"))
        return new_action

    def _createReportsGenAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Generate"))
        return new_action

    def _createReportsLogConsoleAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Log Console"))
        new_action.triggered.connect(self.showLogs)
        return new_action

    def _createSettingsGenAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Generate"))
        return new_action

    # after click, should pop up a windows to ask user to choose from 3 options
    # start from scratch, start from template, start by interactive show and learn tip bubble "most popular".
    def _createSkillNewAction(self):
            # File actions
            new_action = QAction(self)
            new_action.setText(QApplication.translate("QAction", "&Create New"))
            new_action.triggered.connect(self.trainNewSkill)
            return new_action

    def _createSkillManagerAction(self):
            # File actions
            new_action = QAction(self)
            new_action.setText(QApplication.translate("QAction", "&Manager"))
            new_action.triggered.connect(self.showSkillManager)
            return new_action

    def _createSkillDeleteAction(self):
            # File actions
            new_action = QAction(self)
            new_action.setText(QApplication.translate("QAction", "&Delete"))
            return new_action

    def _createSkillShowAction(self):
            # File actions
            new_action = QAction(self)
            new_action.setText(QApplication.translate("QAction", "&Show All"))
            return new_action

    def _createSkillUploadAction(self):
            # File actions
            new_action = QAction(self)
            new_action.setText(QApplication.translate("QAction", "&Upload Skill"))
            new_action.triggered.connect(self.uploadSkill)
            return new_action

    def _createSkillNewFromFileAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Import"))
        new_action.triggered.connect(self.newSkillFromFile)
        return new_action

    def _createHelpUGAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&User Guide"))
        return new_action


    def _createHelpCommunityAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Community"))
        new_action.triggered.connect(self.gotoForum)
        return new_action

    def _createHelpMyAccountAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&My Account"))
        new_action.triggered.connect(self.gotoMyAccount)
        return new_action

    def _createHelpAboutAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&About"))
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
        self.showMsg("testing scrolling....")
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
        self.showMsg("done testing....")

    def runAllTests(self):
        self.showMsg("running all tests suits.")
        htmlfile = 'C:/temp/pot.html'
        # self.test_scroll()
        # test_get_all_wins()

        # test_ads_batch(self)
        # test_sqlite3(self)
        # test_misc()
        # test_scrape_amz_prod_list()
        test_api(self, self.session, self.tokens['AuthenticationResult']['IdToken'])
        # run_genSchedules_test_case(self, self.session, self.tokens['AuthenticationResult']['IdToken'], 1)
        # test_run_mission(self)

        # asyncio.create_task(test_send_file(fieldLinks[0]["transport"]))

        # test_processSearchWordLine()
        # test_UpdateBotADSProfileFromSavedBatchTxt()
        # test_run_group_of_tasks(self)

        #the grand tests,
        # 1) fetch today's schedule.
        # result = self.fetchSchedule("5000", None)            # tests case for chrome etsy seller task automation.
        # result = self.fetchSchedule("4000", None)            # tests case for ads power ebay seller task automation.
        # result = self.fetchSchedule("6000", None)            # tests case for chrome amz seller task automation.

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
        #         self.showMsg("TEST MISSION:"+json.dumps(testmission))
        #         self.showMsg(">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>")
        #         missionDS = EBMISSION(self)
        #         missionDS.loadJson(testmission)
        #         self.showMsg("tests json LOADED!!!!")
        #         steps2brun = configAMZWalkSkill(0, missionDS, testsk, self.homepath)
        #         self.showMsg("steps GENERATED!!!!")
        #         #generated
        #         #step_keys = readSkillFile(testsk.getName(), testsk.get_run_steps_file())
        #         self.showMsg("steps READ AND LOADED!!!!")
        #
        #         runAllSteps(steps2brun, missionDS, skillDS)
        #
        #     mfp.close()
        # skfp.close()


    # this function fetches schedule and assign work based on fetch schedule results...
    def fetchSchedule(self, ts_name, settings):
        fetch_stat = "Completed:0"
        try:
            # before even actual fetch schedule, automatically all new customer buy orders from the designated directory.
            # self.newBuyMissionFromFiles()

            # next line commented out for testing purpose....
            # jresp = send_schedule_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], ts_name, settings)
            jresp = {}
            if "errorType" in jresp:
                screen_error = True
                self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
            else:
                # first, need to decompress the body.
                # very important to use compress and decompress on Base64

                # uncompressed = self.zipper.decompressFromBase64(jresp["body"])            # commented out for testing
                uncompressed = "{}"

                # for testing purpose, short circuit the cloud fetch schedule and load a tests schedule from a tests
                # json file instead.

                # uncompressed = jresp["body"]
                self.showMsg("decomppressed response:"+uncompressed+"!")
                if uncompressed != "":
                    # self.showMsg("body string:", uncompressed, "!", len(uncompressed), "::")
                    # bodyobj = json.loads(uncompressed)                  # for test purpose, comment out, put it back when test is done....
                    file = 'C:/software/scheduleResultTest7.json'
                    if exists(file):
                        with open(file) as test_schedule_file:
                            bodyobj = json.load(test_schedule_file)
                        self.showMsg("bodyobj: " + json.dumps(bodyobj))
                        if len(bodyobj) > 0:
                            self.addNewlyAddedMissions(bodyobj)
                            # now that todays' newly added missions are in place, generate the cookie site list for the run.
                            self.build_cookie_site_lists()
                            self.num_todays_task_groups = self.num_todays_task_groups + len(bodyobj["task_groups"])
                            self.todays_scheduled_task_groups = self.groupTaskGroupsByOS(bodyobj["task_groups"])
                            self.unassigned_task_groups = self.todays_scheduled_task_groups
                            self.assignWork()
                            self.logDailySchedule(uncompressed)
                        else:
                            self.warn(QApplication.translate("QMainWindow", "Warning: NO schedule generated."))
                else:
                    self.warn(QApplication.translate("QMainWindow", "Warning: Empty Network Response."))

            if len(self.todays_work["tbd"]) > 0:
                self.todays_work["tbd"][0]["status"] = fetch_stat
                # now that a new day starts, clear all reports data structure
                self.todaysReports = []
            else:
                self.showMsg("WARNING!!!! no work TBD after fetching schedule...")

        # ni is already incremented by processExtract(), so simply return it.
        except:
            self.showMsg("ERROR EXCEPTION:")
            fetch_stat = "ErrorFetchSchedule:" + jresp["errorType"]

        self.showMsg("done with fetch schedule:"+ fetch_stat)
        return fetch_stat

    def fetchScheduleFromFile(self):

        uncompressed = open(self.homepath + "/resource/testdata/testschedule.json")
        if uncompressed != "":
            # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
            bodyobj = json.load(uncompressed)
            if len(bodyobj) > 0:
                self.assignWork()
                self.logDailySchedule(uncompressed)
            else:
                self.warn(QApplication.translate("QMainWindow", "Warning: NO schedule generated."))
        else:
            self.warn(QApplication.translate("QMainWindow", "Warning: Empty Network Response."))

    def warn(self, msg, level="info"):
        warnText = self.log_text_format(msg, level)
        self.netLogWin.appendLogs([warnText])
        self.appendNetLogs([warnText])
        self.appendDailyLogs([msg], level)

    def showMsg(self, msg, level="info"):
        msg_text = self.log_text_format(msg, level)
        self.appendNetLogs([msg_text])
        self.appendDailyLogs([msg], level)

    def log_text_format(self, msg, level):
        logTime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text_color = ""
        if level == "error":
            text_color = "color:#ff0000;"
            logger_helper.error(msg)
        elif level == "warn":
            text_color = "color:#ff8000;"
            logger_helper.warning(msg)
        elif level == "info":
            text_color = "color:#00ff00;"
            logger_helper.info(msg)
        elif level == "debug":
            text_color = "color:#00ffff;"
            logger_helper.debug(msg)

        msg_text = """
            <div style="display: flex; padding: 5pt;">
                <span  style=" font-size:12pt; font-weight:300; margin-right: 40pt;"> 
                    %s |
                </span>
                <span style=" font-size:12pt; font-weight:300; %s">
                    %s
                </span>
                |
                <span style=" font-size:12pt; font-weight:300; %s;">
                    found %s
                </span>
            </div>""" % (logTime, text_color, level, text_color, msg)
        return msg_text

    def appendDailyLogs(self, msgs, level):
        # check if daily log file exists, if exists simply append to it, if not create and write to the file.
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        dailyLogDir = ecb_data_homepath + "/runlogs/{}".format(year)
        dailyLogFile = ecb_data_homepath + "/runlogs/{}/log{}{}{}.txt".format(year, year, month, day)
        time = now.strftime("%H:%M:%S - ")
        if os.path.isfile(dailyLogFile):
            file1 = open(dailyLogFile, "a")  # append mode
            for msg in msgs:
                file1.write(time+msg+"\n")
            file1.close()
        else:
            if not os.path.exists(dailyLogDir):
                os.makedirs(dailyLogDir)

            file1 = open(dailyLogFile, "w")  # append mode
            for msg in msgs:
                file1.write(time+msg + "\n")
            file1.close()


    def logDailySchedule(self, netSched):
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time = now.strftime("%H:%M:%S - ")
        dailyScheduleLogFile = ecb_data_homepath + "/runlogs/{}/schedule{}{}{}.txt".format(year, month, day, year)
        print("netSched:: "+netSched)
        if os.path.isfile(dailyScheduleLogFile):
            file1 = open(dailyScheduleLogFile, "a")  # append mode
            file1.write(json.dumps(time+netSched) + "\n=====================================================================\n")
            file1.close()
        else:
            file1 = open(dailyScheduleLogFile, "w")  # write mode
            file1.write(json.dumps(time+netSched) + "\n=====================================================================\n")
            file1.close()

    def saveDailyRunReport(self, runStat):
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time = now.strftime("%H:%M:%S - ")
        dailyRunReportFile = ecb_data_homepath + "/runlogs/{}/runreport{}{}{}.txt".format(year, month, day, year)

        if os.path.isfile(dailyRunReportFile):
            with open(dailyRunReportFile, 'a') as f:

                f.write(time+json.dumps(runStat) + "\n")

                f.close()
        else:
            with open(dailyRunReportFile, 'w') as f:

                f.write(time+json.dumps(runStat) + "\n")

                f.close()


    def fill_mission(self, blank_m, m, tgs):
        blank_m.loadNetRespJson(m)
        # self.showMsg("after fill mission paramter:"+str(blank_m.getRetry()))
        mconfig = None
        for tz_group in tgs:
            for tz in tz_group:
                if len(tz_group[tz]) > 0:
                    for bot_works in tz_group[tz]:
                        for bw in bot_works["bw_works"]:
                            if m["mid"] == bw["mid"]:
                                # now add this mission to the list.
                                self.showMsg("found a bw mission matching mid.... "+str(bw["mid"]))
                                mconfig = bw["config"]
                                break
                        if mconfig:
                            break

                        for ow in bot_works["other_works"]:
                            if m["mid"] == ow["mid"]:
                                # now add this mission to the list.
                                self.showMsg("found a other mission matching mid.... "+str(ow["mid"]))
                                mconfig = ow["config"]
                                break
                        if mconfig:
                            break
                if mconfig:
                    break
            if mconfig:
                break
        print("SETTING CONFIG:", mconfig)
        blank_m.setConfig(mconfig)

    # after fetching today's schedule, update missions data structure since some walk/buy routine will be created.
    # as well as some daily routines.... will be generated either....
    def addNewlyAddedMissions(self, resp_data):
        # for each received work mission, check whether they're in the self.missions already, if not, create them and
        # add to the missions list.
        mb_words = ""
        task_groups = resp_data["task_groups"]
        for tg in task_groups:
            for tz in tg:
                for wg in tg[tz]:
                    for w in wg["bw_works"]:
                        mb_words = mb_words + "M"+str(w["mid"])+"B"+str(wg["bid"]) + ", "

                    for w in wg["other_works"]:
                        mb_words = mb_words + "M"+str(w["mid"])+"B"+str(wg["bid"]) + ", "

        print(mb_words)


        newly_added_missions = resp_data["added_missions"]
        print("Added MS:"+json.dumps(["M"+str(m["mid"])+"B"+str(m["botid"]) for m in newly_added_missions]))
        for m in newly_added_missions:
            new_mission = EBMISSION(self)
            self.fill_mission(new_mission, m, task_groups)
            new_mission.updateDisplay()
            self.missions.append(new_mission)
            self.missionModel.appendRow(new_mission)
            self.showMsg("adding mission.... "+str(new_mission.getRetry()))


    def formBotsJsons(self, botids):
        result = []
        for bid in botids:
            # result = result + json.dumps(self.getBotByID(bid).genJson()).replace('"', '\\"')
            found_bot = next((bot for i, bot in enumerate(self.bots) if bot.getBid() == bid), None)
            if found_bot:
                result.append(found_bot.genJson())

        return result


    def formMissionsJsons(self, mids):
        result = []
        for mid in mids:
            # result = result + json.dumps(self.getMissionByID(mid).genJson()).replace('"', '\\"')
            found_mission = next((mission for i, mission in enumerate(self.missions) if mission.getMid() == mid), None)
            if found_mission:
                result.append(found_mission.genJson())

        return result

    def formSkillsJsons(self, skids):
        result = []
        all_skids = [sk.getSkid() for sk in self.skills]
        self.showMsg("all known skids:"+json.dumps(all_skids))
        for skid in skids:
            # result = result + json.dumps(self.getMissionByID(mid).genJson()).replace('"', '\\"')
            found_skill = next((sk for i, sk in enumerate(self.skills) if sk.getSkid() == skid), None)
            if found_skill:
                print("found skill")
                result.append(found_skill.genJson())
            else:
                self.showMsg("ERROR: skill id not found [" + str(skid)+"]")
        return result

    def formBotsMissionsSkillsString(self, botids, mids, skids):
        # result = "{\"bots\": " + self.formBotsString(botids) + ",\"missions\": " + self.formMissionsString(mids) + "}"
        BMS_Json = {"bots": self.formBotsJsons(botids), "missions": self.formMissionsJsons(mids), "skills": self.formSkillsJsons(skids)}

        return json.dumps(BMS_Json)

    def formBotsMissionsSkillsJsonData(self, botids, mids, skids):
        return self.formBotsJsons(botids),self.formMissionsJsons(mids),self.formSkillsJsons(skids)

    def getAllBotidsMidsSkidsFromTaskGroup(self, task_group):
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

        # Convert the set back to a list
        bids_set = set(bids)
        bids = list(bids_set)

        mids_set = set(mids)
        mids = list(mids_set)

        # at this points all skills should have been fetched, dependencies analyzed and skills regenerated, so just gather them....
        needed_skills = []
        print("check m skills: " + json.dumps(mids))
        print("all mids: " + json.dumps([m.getMid() for m in self.missions]))
        for mid in mids:
            m = next((mission for i, mission in enumerate(self.missions) if mission.getMid() == mid), None)

            if m:
                print("m skillls: "+m.getSkills())
                if m.getSkills() != "":
                    if "," in m.getSkills():
                        m_skids = [int(skstring.strip()) for skstring in m.getSkills().strip().split(",")]
                    else:
                        m_skids = [int(m.getSkills().strip())]

                    needed_skills = needed_skills + m_skids
                    m_main_skid = m_skids[0]

                    m_main_skill = next((sk for i, sk in enumerate(self.skills) if sk.getSkid() == m_main_skid), None)
                    if m_main_skill:
                        print("found skill")
                        needed_skills = needed_skills + m_main_skill.getDependencies()
                        print("needed skills add dependencies", m_main_skill.getDependencies())
                    else:
                        self.showMsg("ERROR: skill id not found - " + str(m_main_skid))
                else:
                    self.showMsg("ERROR: mission has no skill "+str(mid))
            else:
                self.showMsg("ERROR: mission ID not found " + str(mid))

        if len(needed_skills) > 0:
            skill_set = set(needed_skills)
            skids = list(skill_set)
        else:
            skids = []
        self.showMsg("bids in the task group:: "+json.dumps(bids))
        self.showMsg("mids in the task group:: "+json.dumps(mids))
        self.showMsg("skids in the task group:: " + json.dumps(skids))
        return bids, mids, skids

    # assumption, tg will not be empty.
    def getTaskGroupOS(self, tg):
        # get the 1st mission, and get its cuspas and extract platform part of the cuspas.
        for tz in tg.keys():
            if len(tg[tz]) > 0:
                # if len(tg[tz][0]["bw_works"]) > 0:
                #     mission_id = tg[tz][0]["bw_works"][0]["mid"]
                # else:
                #     mission_id = tg[tz][0]["other_works"][0]["mid"]
                #
                # midx = next((i for i, mission in enumerate(self.missions) if str(mission.getMid()) == mission_id), -1)
                # platform = self.missions[midx].getPlatform()
                platform = tg[tz][0]["cuspas"]
                break
        self.showMsg("Platform of the group:: "+platform)
        return platform


    def groupTaskGroupsByOS(self, tgs):
        result = {
            "win": [tg for tg in tgs if "win" in self.getTaskGroupOS(tg)],
            "mac": [tg for tg in tgs if "mac" in self.getTaskGroupOS(tg)],
            "linux": [tg for tg in tgs if "linux" in self.getTaskGroupOS(tg)]
        }
        return result

    def getUnassignedVehiclesByOS(self):
        self.showMsg("N vehicles " + str(len(self.vehicles)))
        result = {
            "win": [v for v in self.vehicles if v.getOS().lower() in "Windows".lower() and len(v.getBotIds()) == 0],
            "mac": [v for v in self.vehicles if v.getOS().lower() in "Mac".lower() and len(v.getBotIds()) == 0],
            "linux": [v for v in self.vehicles if v.getOS().lower() in "Linux".lower() and len(v.getBotIds()) == 0]
        }
        self.showMsg("N vehicles win " + str(len(result["win"]))+" " + str(len(result["mac"]))+" " + str(len(result["linux"])))
        if self.hostrole == "Commander" and not self.rpa_work_assigned_for_today:
            if len([wk for wk in self.todays_work["tbd"] if wk["name"] == "automation"]) == 0:
                self.showMsg("myself unassigned "+self.getIP())
                # put in a dummy V
                self_v = VEHICLE(self)
                self_v.setIP(self.getIP())
                ipfields = self.getIP().split(".")
                ip = ipfields[len(ipfields) - 1]
                self_v.setVid(ip)
                if self.platform == "win":
                    self.showMsg("add myself to win based v list")
                    result["win"].insert(0, self_v)
                elif self.platform == "mac":
                    self.showMsg("add myself to mac based v list")
                    result["mac"].insert(0, self_v)
                else:
                    self.showMsg("add myself to linux based v list")
                    result["linux"].insert(0, self_v)

        return result


    def groupVehiclesByOS(self):
        self.showMsg("groupVehiclesByOS>>>>>>>>>>>> "+self.hostrole)
        result = {
            "win": [v for v in self.vehicles if v.getOS() == "Windows"],
            "mac": [v for v in self.vehicles if v.getOS() == "Mac"],
            "linux": [v for v in self.vehicles if v.getOS() == "Linux"]
        }
        self.showMsg("all vehicles>>>>>>>>>>>> " + json.dumps(result))
        self.showMsg("now take care of commander machine itself in case of being a dual role commander")
        if self.hostrole == "Commander":
            self.showMsg("checking commander>>>>>>>>>>>>>>>>>>>>>>>>> "+self.getIP())
            # put in a dummy V
            self_v = VEHICLE(self)
            self_v.setIP(self.getIP())
            ipfields = self.getIP().split(".")
            ip = ipfields[len(ipfields) - 1]
            self_v.setVid(ip)
            if self.platform == "win":
                result["win"].insert(0, self_v)
            elif self.platform == "mac":
                result["mac"].insert(0, self_v)
            else:
                result["linux"].insert(0, self_v)

        return result


    # generate a buy associated browse-search configuration
    def gen_new_buy_search(self, work, mission):
        # simply modify mission's search configuration to fit our need.
        # we'll randomely pick one of the searches and modify its parameter.
        nth_search = random.randrange(0, len(work["config"]["searches"]))
        n_pages = len(work["config"]["searches"][nth_search]["prodlist_pages"])

        work["config"]["searches"][nth_search]["entry_paths"]["type"] = "Search"
        work["config"]["searches"][nth_search]["entry_paths"]["words"] = [mission.getSearchKW()]

        # simply duplate the last prodlist_pages enough times to satisfy up to 5 pages requreiment
        if work["name"].split("_")[1] in ["addCart", "addCartPay"]:
            last_page = work["config"]["searches"][nth_search]["prodlist_pages"][n_pages-1]
            if n_pages < 5:  # we will browse up to 5 pages for a product purchase.
                for i in range(5-n_pages):
                    work["config"]["searches"][nth_search]["prodlist_pages"].append(copy.deepcopy(last_page))

            # on each pages, add the target buy product onto the list.
            for page in work["config"]["searches"][nth_search]["prodlist_pages"]:
                if work["name"].split("_")[1] in ["addCart", "pay"]:
                    target_buy = {
                        "selType": "cus",   # this is key,
                        "detailLvl": 3,
                        "purchase": [{
                                    "action": work["name"].split("_")[1],
                                    "asin": mission.getASIN(),
                                    "seller": mission.getStore(),
                                    "brand": mission.getBrand(),
                                    "img": mission.getImagePath(),
                                    "title": mission.getTitle(),
                                    "variations": mission.getVariations(),
                                    "rating": mission.getRating(),
                                    "feedbacks": mission.getFeedbacks(),
                                    "price": mission.getPrice(),
                                }]
                    }

                elif work["name"].split("_")[1] in ["addCartPay"]:
                    target_buy = {
                        "selType": "cus",  # this is key,
                        "detailLvl": 3,
                        "purchase": [
                            {
                                "action": "addCart",
                                "asin": mission.getASIN(),
                                "seller": mission.getStore(),
                                "brand": mission.getBrand(),
                                "img": mission.getImagePath(),
                                "title": mission.getTitle(),
                                "variations": mission.getVariations(),
                                "rating": mission.getRating(),
                                "feedbacks": mission.getFeedbacks(),
                                "price": mission.getPrice()
                            }
                        ]
                    }
                page["products"].append(target_buy)
        elif work["name"].split("_")[1] in ["pay", "checkShipping", "rate", "feedback", "checkFB"]:
            # in all other case, simply replace last st product of the 1st page.
            first_page = work["config"]["searches"][nth_search]["prodlist_pages"][0]
            first_page["products"][0] = {
                        "selType": "cus",  # this is key,
                        "detailLvl": 0,
                        "purchase": [
                            {
                                "action": work["name"].split("_")[1],
                                "asin": mission.getASIN(),
                                "seller": mission.getStore(),
                                "brand": mission.getBrand(),
                                "img": mission.getImagePath(),
                                "title": mission.getTitle(),
                                "variations": mission.getVariations(),
                                "rating": mission.getRating(),
                                "feedbacks": mission.getFeedbacks(),
                                "price": mission.getPrice(),
                                "order_id": mission.getOrderID(),
                                "feedback_rating": mission.getFeedbackRating(),
                                "feedback_title": mission.getFeedbackTitle(),
                                "feedback_text": mission.getFeedbackText(),
                                "feedback_image": mission.getFeedbackImgLink(),
                                "feedback_video": mission.getFeedbackVideoLink(),
                                "feedback_instructions": mission.getFeedbackInstructions()
                            }
                        ]
                    }

        log3("Modified Buy Work:"+json.dumps(work))


    def gen_prod_sel(self):
        idx = math.floor(random.random() * (len(self.static_resource.PRODUCT_SEL_TYPES.length) - 1));
        return self.static_resource.PRODUCT_SEL_TYPES[idx];



    # given a derived buy mission, find out the original buy mission that was put in order by the users.
    # this is done thru searching ticket number. since this is likely to be a mission created 2 wks ago,
    # might not be loaded from memory, so directly search DB.
    def find_original_buy(self, buy_mission):
        # Construct the SQL query with a parameterized IN clause
        db_data = self.mission_service.delete_missions_by_ticket(buy_mission.getTicket())
        self.showMsg("same ticket missions: " + json.dumps(db_data))
        if len(db_data) != 0:
            original_buy_mission = EBMISSION(self)
            original_buy_mission.loadDBData(db_data[0])
            self.missions.append(original_buy_mission)
            self.missionModel.appendRow(original_buy_mission)
        else:
            original_buy_mission = None

        return original_buy_mission


    # if function will add buy task related search if there is any 1st stage buy type of missions. (Note a buy mission will always have a same CUSPUS browse action go along with it.
    # will go into the configuration of the browse mission, if there is a keyword search run, go the last one, and swap out the auto assigned
    # search phrase and replace with the buy search phrase. If there is no keyword search run, then simply create one and replace whatever the last
    # search with the buy related prodcut search flow, when we complete the mission and report the status, we'll do it just as the original browse
    # mission is done. This way, the cloud side will have no idea what's being processed.
    # in case  there is no same CUSPAS browse mission go along with a buy type, create one anyways, but this could affect capacity.
    # so really, we need cloud side to coordinate the buy-bowse coupling which I think it's there...
    # task name will be mainType_subType for example buy_addCart or goodFB_pay
    # main types will be: "buy", "goodFB", "badFB", "goodRating", "badRating"
    # sub types will be: 'addCart', 'pay', "checkShipping", 'rate', 'feedback', "checkFB"
    # 06-07-2024 actually not add, but again replace the configuration, otherwise, time will be wasted...
    def add_buy_searchs(self, p_task_groups):
        print("add buy to taskgroup:", p_task_groups)

        #1st find all 1st stage buy missions.
        self.showMsg("task name:" + json.dumps([tsk["name"]  for tsk in p_task_groups]))
        buys = [tsk for tsk in p_task_groups if (tsk["name"].split("_")[0] in self.BUY_TYPES)]
        initial_buys = [tsk for tsk in buys if ((tsk["name"].split("_")[0] in self.BUY_TYPES) and (tsk["name"].split("_")[1] in ['addCart', 'pay', 'addCartPay']))]
        later_buys = [tsk for tsk in buys if ((tsk["name"].split("_")[0] in self.BUY_TYPES) and (tsk["name"].split("_")[1] not in ['addCart', 'pay', 'addCartPay']))]
        print(len(buys), len(initial_buys), len(later_buys))
        for buytask in buys:
            # make sure we do search before buy
            midx = next( (i for i, mission in enumerate(self.missions) if str(mission.getMid()) == str(buytask["mid"])), -1)
            if midx >= 0:
                task_mission = self.missions[midx]
                original_buy = self.find_original_buy(task_mission)
                # first, fill the mission with original buy's private attributes for convenience.
                task_mission.setASIN(original_buy.getASIN())
                task_mission.setTitle(original_buy.getTitle())
                task_mission.setVariations(original_buy.getVariations())
                task_mission.setStore(original_buy.getStore())
                task_mission.setBrand(original_buy.getBrand())
                task_mission.setImagePath(original_buy.getImagePath())
                task_mission.setRating(original_buy.getRating())
                task_mission.setFeedbacks(original_buy.getFeedbacks())
                task_mission.setPrice(original_buy.getPrice())
                task_mission.setResult(original_buy.getResult())

                self.gen_new_buy_search(buytask, task_mission)



    # assign per vehicle task group work, if this commander runs, assign works for commander,
    # otherwise, send works to platoons to execute.
    def assignWork(self):
        # tasks should already be sorted by botid,
        nsites = 0
        v_groups = self.getUnassignedVehiclesByOS()                      #result will {"win": win_vs, "mac": mac_vs, "linux": linux_vs}

        for key in v_groups:
            print("num vehicles in "+key+" :"+str(len(v_groups[key])))
            if len(v_groups[key]) > 0:
                for k, v in enumerate(v_groups[key]):
                    self.showMsg("Vehicle OS:"+key+"["+str(k)+"]"+json.dumps(v.genJson())+"\n")

        for platform in v_groups.keys():
            p_task_groups = self.unassigned_task_groups[platform]
            p_nsites = len(v_groups[platform])

            self.showMsg("p_nsites for "+platform+":"+str(p_nsites))

            if p_nsites > 0:
                if len(p_task_groups) > p_nsites:
                    # there will be unserved tasks due to over capacity
                    self.showMsg("Run Capacity Spilled, some tasks will NOT be served!!!"+str(len(p_task_groups))+"::"+str(p_nsites))
                    # save capacity spill into unassigned_task_groups
                    self.unassigned_task_groups[platform] = self.unassigned_task_groups[platform][p_nsites:]
                else:
                    self.showMsg("No under-capacity")
                    self.unassigned_task_groups[platform] = []

                # distribute work to all available sites, which is the limit for the total capacity.
                if p_nsites > 0:
                    for i in range(p_nsites):
                        if i == 0 and not self.rpa_work_assigned_for_today and not self.hostrole == "CommanderOnly" and platform in self.platform.lower():
                            # if commander participate work, give the first(0th) work to self.
                            batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(p_task_groups[0], self)
                            # batched_tasks now contains the flattened tasks in a vehicle, sorted by start_time, so no longer need complicated structure.
                            self.showMsg("arranged for today on this machine....")
                            self.add_buy_searchs(batched_tasks)
                            # current_tz, current_group = self.setTaskGroupInitialState(p_task_groups[0])
                            self.todays_work["tbd"].append({"name": "automation", "works": batched_tasks, "status": "yet to start", "current widx": 0, "completed": [], "aborted": []})
                            vidx = 0
                            self.rpa_work_assigned_for_today = True
                        else:
                            # #otherwise, send work to platoons in the field
                            # if self.hostrole == "CommanderOnly":
                            #     # in case of commanderonly. grouptask index is the same as the platoon vehicle index.
                            #     vidx = i
                            # else:
                            #     # in case of n > 0 and not commander only. grouptask index is one more than the platoon vehicle index.
                            #     # because the first group is assigned to self. starting the 2nd task group, the 2nd task group will
                            #     # be send to the 1st vehicle , the 3rd will be send the 2nd vehicle and so .....
                            #     vidx = i - 1

                            vidx = i

                            self.showMsg("working on task group index: "+str(i)+" vehicle index: " + str(vidx))
                            # flatten tasks and regroup them based on sites, and divide them into batches
                            batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(p_task_groups[i], self)
                            self.add_buy_searchs(batched_tasks)
                            # current_tz, current_group = self.setTaskGroupInitialState(batched_tasks)
                            self.todays_work["tbd"].append(
                                {"name": "automation", "works": batched_tasks, "ip": v_groups[platform][i].getIP(), "status": "yet to start",
                                 "current widx": 0, "completed": [], "aborted": []})

                            for profile in ads_profiles:
                                self.send_file_to_platoon(v_groups[platform][i].getFieldLink(), "ads profile", profile)

                            task_group_string = json.dumps(batched_tasks).replace('"', '\\"')

                            # now need to fetch this task associated bots, mission, skills
                            # get all bots IDs involved. get all mission IDs involved.
                            tg_botids, tg_mids, tg_skids = self.getAllBotidsMidsSkidsFromTaskGroup(p_task_groups[i])
                            v_groups[platform][i].setBotIds(tg_botids)
                            v_groups[platform][i].setMids(tg_botids)

                            self.showMsg("tg_skids:"+json.dumps(tg_skids))
                            # put togehter all bots, missions, needed skills infommation in one batch and put onto the vehicle to
                            # execute
                            # resource_string = self.formBotsMissionsSkillsString(tg_botids, tg_mids, tg_skids)
                            resource_bots, resource_missions, resource_skills = self.formBotsMissionsSkillsJsonData(tg_botids, tg_mids, tg_skids)
                            schedule = {"cmd": "reqSetSchedule", "todos": batched_tasks, "bots": resource_bots, "missions": resource_missions, "skills": resource_skills}
                            self.showMsg(get_printable_datetime() + "SENDING ["+platform+"]PLATOON["+v_groups[platform][i].getFieldLink()["ip"][0]+"] SCHEDULE::: "+json.dumps(schedule))

                            # send over scheduled tasks to platton.
                            self.send_json_to_platoon(v_groups[platform][i].getFieldLink(), schedule)

                            # send over skills to platoon
                            self.empower_platoon_with_skills(v_groups[platform][i].getFieldLink(), tg_skids)

                else:
                    self.showMsg(get_printable_datetime() + f" - There is no [{platform}] based vehicles at this moment for "+ str(len(p_task_groups)) + f" task groups on {platform}")

    def empower_platoon_with_skills(self, platoon_link, skill_ids):
        # at this point skilll PSK files should be ready to use, send these files to the platton so that can use them.
        for skid in skill_ids:
            found_skill = next((sk for i, sk in enumerate(self.skills) if sk.getSkid() == skid), None)
            if found_skill:
                psk_file = self.homepath + found_skill.getPskFileName()
                self.showMsg("Empowering platoon with skill PSK"+psk_file)
                self.send_file_to_platoon(platoon_link, "skill psk", psk_file)
            else:
                self.showMsg("ERROR: skid NOT FOUND [" + str(skid) + "]")

    def setTaskGroupInitialState(self, tg):
        initial_tz = ""
        initial_group = ""
        for tz_key in tg:
            if len(tg[tz_key]) > 0:
                initial_tz = tz_key
                if len(tg[tz_key][0]['bw_works']) > 0:
                    initial_group = 'bw_works'
                else:
                    initial_group = 'other_works'
            break
        return initial_tz, initial_group


    # find to todos.,
    # 1) check whether need to fetch schedules,
    # 2) checking whether need to do RPA
    # the key data structure is self.todays_work["tbd"] which should be an array of either 1 or 2 elements.
    # either 1 or 2 elements depends on the role, if commander_only or platoon, will be 1 element,
    # if commander (which means commander can do tasks too) then there will be 2 elements.
    # in case of 1 element, it will be the actuall bot tasks to be done for platton or the fetch schedule task for Comander Only.
    # in case of 2 elements, the 0th element will be the fetch schedule, the 1st element will be the bot tasks(as a whole)
    # self.todays_work = {"tbd": [], "allstat": "working"}
    def checkNextToRun(self):
        self.showMsg("checking todos...... "+json.dumps(self.todays_work["tbd"]))
        nextrun = None
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.now()
        if len(self.todays_work["tbd"]) > 0:
            if ("Completed" not in self.todays_work["tbd"][0]["status"]) and (self.todays_work["tbd"][0]["name"] == "fetch schedule"):
                # in case the 1st todos is fetch schedule
                if self.ts2time(int(self.todays_work["tbd"][0]["works"][0]["start_time"]/1)) < pt:
                    nextrun = self.todays_work["tbd"][0]
            elif "Completed" not in self.todays_work["tbd"][0]["status"]:
                # in case the 1st todos is an automation task.
                self.showMsg("self.todays_work[\"tbd\"][0] : "+json.dumps(self.todays_work["tbd"][0]))
                self.showMsg("time right now is: "+str(self.time2ts(pt)))

                # determin next task group:
                current_work_idx = self.todays_work["tbd"][0]["current widx"]

                if self.ts2time(int(self.todays_work["tbd"][0]["works"][current_work_idx]["start_time"]/3)) < pt:
                    self.showMsg("next run is now set up......")
                    nextrun = self.todays_work["tbd"][0]
                self.showMsg("nextRUN>>>>>: "+json.dumps(nextrun))
        return nextrun

    def getNumUnassignedWork(self):
        num = 0
        for key in self.unassigned_task_groups:
            num = num + len(self.unassigned_task_groups[key])
        return num


    def checkToDos(self):
        self.showMsg("checking todos...... "+json.dumps(self.todays_work["tbd"]))
        nextrun = None
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.now()
        if len(self.todays_work["tbd"]) > 0:
            if ("Completed" not in self.todays_work["tbd"][0]["status"]) and (self.todays_work["tbd"][0]["name"] == "fetch schedule"):
                # in case the 1st todos is fetch schedule
                if self.ts2time(int(self.todays_work["tbd"][0]["works"]["eastern"][0]["other_works"][0]["start_time"]/1)) < pt:
                    nextrun = self.todays_work["tbd"][0]
            elif "Completed" not in self.todays_work["tbd"][0]["status"]:
                # in case the 1st todos is an automation task.
                print("eastern:", self.todays_work["tbd"][0]["works"]["eastern"])
                self.showMsg("self.todays_work[\"tbd\"][0] : "+json.dumps(self.todays_work["tbd"][0]))
                tz = self.todays_work["tbd"][0]["current tz"]

                bith = self.todays_work["tbd"][0]["current bidx"]

                # determin next task group:
                current_bw_idx = self.todays_work["tbd"][0]["current widx"]
                current_other_idx = self.todays_work["tbd"][0]["current oidx"]
                self.showMsg("time right now is: "+self.time2ts(pt)+"("+str(pt)+")"+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+" tz:"+tz+" bith:"+str(bith)+" bw idx:"+str(current_bw_idx)+"other idx:"+str(current_other_idx))

                if current_bw_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"]):
                    current_bw_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"][current_bw_idx]["start_time"]
                    self.showMsg("current bw start time: " + str(current_bw_start_time))
                else:
                    # just give it a huge number so that, this group won't get run
                    current_bw_start_time = 1000
                self.showMsg("current_bw_start_time: "+str(current_bw_start_time))

                if current_other_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["other_works"]):
                    current_other_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["other_works"][current_other_idx]["start_time"]
                    self.showMsg("current bw start time: " + str(current_other_start_time))
                else:
                    # in case, all just give it a huge number so that, this group won't get run
                    current_other_start_time = 1000
                self.showMsg("current_other_start_time: "+current_other_start_time)

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
                self.showMsg("tz: "+tz+" bith: "+str(bith)+" grp: "+grp+" wjth: "+str(wjth))

                if wjth >= 0:
                    if self.ts2time(int(self.todays_work["tbd"][0]["works"][tz][bith][grp][wjth]["start_time"]/3)) < pt:
                        self.showMsg("next run is now set up......")
                        nextrun = self.todays_work["tbd"][0]
                self.showMsg("nextRUN>>>>>: "+json.dumps(nextrun))
        return nextrun


    def findWorksToBeRetried(self, todos):
        retries = copy.deepcopy(todos)
        self.showMsg("MISSIONS needs retry: "+str(retries))
        return retries

    def findMissonsToBeRetried(self, todos):
        retries = copy.deepcopy(todos)
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
                                            junk = retries[key1][key2][key3].pop(key4)

        #now point to the 1st item in this todo list

        self.showMsg("MISSIONS needs retry: "+str(retries))
        return retries

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

        self.showMsg("loadSKILLFILE: "+skill_file)
        stepKeys = readPSkillFile(skname, skill_file, lvl=0)

        return stepKeys

    def reAddrAndUpdateSteps(self, pskJson, init_step_idx, work_settings):
        # self.showMsg("PSK JSON::::: "+json.dumps(pskJson))
        newPskJson = {}
        self.showMsg("New Index:"+str(init_step_idx))
        new_idx = init_step_idx
        old_keys = list(pskJson.keys())
        for key in old_keys:
            if "step" in key:
                new_key = "step "+str(new_idx)
                newPskJson[new_key] = pskJson[key]
                new_idx = new_idx + STEP_GAP
                # print("old/new key:", key, new_key, pskJson[key])
                if "Create Data" in newPskJson[new_key]['type']:
                    if newPskJson[new_key]['data_name'] == "sk_work_settings":
                        newPskJson[new_key]["key_value"] = work_settings
                        # newPskJson[new_key]["key_value"] = copy.deepcopy(work_settings)
                        # newPskJson[new_key]["key_value"]["commander_link"] = ""
                        self.showMsg("REPLACED WORKSETTINGS HERE: "+new_key+" :::: "+json.dumps(newPskJson[new_key]))

                pskJson.pop(key)

        # self.showMsg("PSK JSON after address and update step::::: "+json.dumps(newPskJson))
        return new_idx, newPskJson



    # run one bot one time slot at a time，for 1 bot and 1 time slot, there should be only 1 mission running
    async def runRPA(self, worksTBD, rpa_msg_queue, monitor_msg_queue):
        global rpaConfig
        global skill_code

        all_done = False
        try:
            worksettings = getWorkRunSettings(self, worksTBD)
            self.showMsg("worksettings: bid, mid "+str(worksettings["botid"])+" "+str(worksettings["mid"]))

            bot_idx = next((i for i, b in enumerate(self.bots) if str(b.getBid()) == str(worksettings["botid"])), -1)
            if bot_idx >= 0:
                self.showMsg("found BOT to be run......"+self.bots[bot_idx].getEmail())
                running_bot = self.bots[bot_idx]

            rpaScripts = []

            # generate walk skills on the fly.
            running_mission = self.missions[worksettings["midx"]]

            if 'ads' in running_mission.getCusPAS() and running_mission.getADSXlsxProfile() == "":
                self.showMsg("ERROR ADS mission has no profile: " + str(running_mission.getMid()) + " " + running_mission.getCusPAS() + " " + running_mission.getADSXlsxProfile())
                runResult = "ErrorRPA ADS mission has no profile " + str(running_mission.getMid())
                self.update1MStat(worksettings["midx"], runResult)
                self.update1WorkRunStatus(worksTBD, worksettings["midx"])
            else:
                self.showMsg("current RUNNING MISSION: "+json.dumps(running_mission.genJson()))
                if running_mission.getSkills() != "":
                    rpaSkillIdWords = running_mission.getSkills().split(",")
                    self.showMsg("current RUNNING MISSION SKILL: "+json.dumps(running_mission.getSkills()))
                    rpaSkillIds = [int(skidword.strip()) for skidword in rpaSkillIdWords]

                    self.showMsg("rpaSkillIds: "+json.dumps(rpaSkillIds)+" "+str(type(rpaSkillIds[0]))+" "+" running mission id: "+str(running_mission.getMid()))

                    # get skills data structure by IDs
                    self.showMsg("all skills ids:"+json.dumps([sk.getSkid() for sk in self.skills]))
                    relevant_skills = [sk for sk in self.skills if sk.getSkid() in rpaSkillIds]
                    relevant_skill_ids = [sk.getSkid() for sk in self.skills if sk.getSkid() in rpaSkillIds]
                    self.showMsg("relevant skills ids: "+json.dumps(relevant_skill_ids))
                    dependent_skids=[]
                    for sk in relevant_skills:
                        dependent_skids = dependent_skids + sk.getDependencies()
                    self.showMsg("all dependencies: "+json.dumps(dependent_skids))

                    dependent_skills = [sk for sk in self.skills if sk.getSkid() in dependent_skids]
                    relevant_skills = relevant_skills + dependent_skills
                    relevant_skill_ids = relevant_skill_ids + dependent_skids

                    if len(relevant_skill_ids) < len(rpaSkillIds):
                        s = set(relevant_skill_ids)
                        missing = [x for x in rpaSkillIds if x not in s]
                        self.showMsg("ERROR: Required Skills not found:"+json.dumps(missing))


                    all_skill_codes = []
                    step_idx = 0
                    for sk in relevant_skills:
                        self.showMsg("settingSKKKKKKKK: "+str(sk.getSkid())+" "+sk.getName()+" "+worksettings["b_email"])
                        setWorkSettingsSkill(worksettings, sk)
                        # self.showMsg("settingSKKKKKKKK: "+json.dumps(worksettings, indent=4))

                        # readPSkillFile will remove comments. from the file
                        pskJson = readPSkillFile(worksettings["name_space"], self.homepath+sk.getPskFileName(), lvl=0)
                        # self.showMsg("RAW PSK JSON::::"+json.dumps(pskJson))

                        # now regen address and update settings, after running, pskJson will be updated.
                        step_idx, pskJson = self.reAddrAndUpdateSteps(pskJson, step_idx, worksettings)
                        # self.showMsg("AFTER READDRESS AND UPDATE PSK JSON::::" + json.dumps(pskJson))

                        addNameSpaceToAddress(pskJson, worksettings["name_space"], lvl=0)

                        # self.showMsg("RUNNABLE PSK JSON::::"+json.dumps(pskJson))

                        # save the file to a .rsk file (runnable skill) which contains json only with comments stripped off from .psk file by the readSkillFile function.
                        rskFileName = self.homepath + sk.getPskFileName().split(".")[0] + ".rsk"
                        self.showMsg("rskFileName: "+rskFileName+" step_idx: "+str(step_idx))
                        with open(rskFileName, "w") as outfile:
                            json.dump(pskJson, outfile)
                        outfile.close()

                        all_skill_codes.append({"ns": worksettings["name_space"], "skfile": rskFileName})

                    self.showMsg("all_skill_codes: "+json.dumps(all_skill_codes))

                    rpa_script = prepRunSkill(all_skill_codes)
                    self.showMsg("generated ready2run: "+json.dumps(rpa_script))
                    # self.showMsg("generated psk: " + str(len(rpa_script.keys())))

                    # doing this just so that the code below can run multiple codes if needed. but in reality
                    # prepRunSkill put code in a global var "skill_code", even if there are multiple scripts,
                    # this has to be corrected because, the following append would just have multiple same
                    # skill_code...... SC, but for now this is OK, there is no multiple script scenario in
                    # forseaable future.
                    rpaScripts.append(rpa_script)
                    # self.showMsg("rpaScripts:["+str(len(rpaScripts))+"] "+json.dumps(rpaScripts))
                    self.showMsg("rpaScripts:["+str(len(rpaScripts))+"] "+str(len(relevant_skills))+" "+str(worksettings["midx"])+" "+str(len(self.missions)))


                    # (steps, mission, skill, mode="normal"):
                    # it_items = (item for i, item in enumerate(self.skills) if item.getSkid() == rpaSkillIds[0])
                    # self.showMsg("it_items: "+json.dumps(it_items))
                    # for it in it_items:
                    #     self.showMsg("item: "+str(it.getSkid()))
                    # running_skill = next((item for i, item in enumerate(self.skills) if item.getSkid() == int(rpaSkillIds[0])), -1)
                    # self.showMsg("running skid:"+str(rpaSkillIds[0])+"len(self.skills): "+str(len(self.skills))+"skill 0 skid: "+str(self.skills[0].getSkid()))
                    # self.showMsg("running skill: "+json.dumps(running_skill))
                    # runStepsTask = asyncio.create_task(runAllSteps(rpa_script, self.missions[worksettings["midx"]], relevant_skills[0], rpa_msg_queue, monitor_msg_queue))
                    # runResult = await runStepsTask

                    self.showMsg("BEFORE RUN: " + worksettings["b_email"])
                    runResult = await runAllSteps(rpa_script, self.missions[worksettings["midx"]], relevant_skills[0], rpa_msg_queue, monitor_msg_queue)

                    # finished 1 mission, update status and update pointer to the next one on the list.... and be done.
                    # the timer tick will trigger the run of the next mission on the list....
                    self.showMsg("UPDATEing completed mmission status:: "+str(worksettings["midx"])+"RUN result:"+runResult)
                    self.update1MStat(worksettings["midx"], runResult)

                    self.update1WorkRunStatus(worksTBD, worksettings["midx"])
                else:
                    self.showMsg("UPDATEing ERROR mmission status:: " + str(worksettings["midx"]) + "RUN result: " + "Incomplete: ERRORRunRPA:-1")
                    self.update1MStat(worksettings["midx"], "Incomplete: ERRORRunRPA:-1")
                    self.update1WorkRunStatus(worksTBD, worksettings["midx"])
                    raise Exception('ERROR: NO SKILL TO RUN!')


        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorRanRPA:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorRanRPA: traceback information not available:" + str(e)
            self.showMsg(ex_stat)
            runResult = "Incomplete: ERRORRunRPA:-1"

        self.showMsg("botid, mid:"+str(worksettings["botid"]) + " "+str(worksettings["mid"]))
        return worksettings["botid"], worksettings["mid"], runResult


    def update1MStat(self, midx, result):
        self.showMsg("1 mission run completed."+str(midx)+" "+str(self.missions[midx].getMid())+" "+str(self.missions[midx].getRetry())+" "+str(self.missions[midx].getNRetries())+"status:"+result)
        self.missions[midx].setStatus(result)
        retry_count = self.missions[midx].getNRetries()
        self.missions[midx].setNRetries(retry_count + 1)
        self.showMsg("update1MStat:"+str(midx)+":"+str(self.missions[midx].getMid())+":"+str(self.missions[midx].getNRetries()))

    #update next mission pointer, return -1 if exceed the end of it.
    def update1WorkRunStatus(self, worksTBD, midx):

        this_stat = self.missions[midx].getStatus()
        worksTBD["current widx"] = worksTBD["current widx"] + 1

        self.showMsg("updatin 1 work run status:"+this_stat+" "+str(worksTBD["current widx"])+" "+str(len(worksTBD["works"])))

        if worksTBD["current widx"] >= len(worksTBD["works"]):
            worksTBD["current widx"] = self.checkTaskGroupCompleteness(worksTBD)
            self.showMsg("current widx pointer after checking retries:"+str(worksTBD["current widx"])+" "+str(len(worksTBD["works"])))
            if worksTBD["current widx"] >= len(worksTBD["works"]):
                worksTBD["status"] = "Completed"
        self.showMsg("current widx pointer now at:"+str(worksTBD["current widx"])+"worksTBD status: "+worksTBD["status"])


    def checkTaskGroupCompleteness(self, worksTBD):
        mids = [w["mid"] for w in worksTBD["works"]]
        next_run_index = len(mids)
        for j, mid in enumerate(mids):
            midx = next((i for i, m in enumerate(self.missions) if m.getMid() == mid), -1)
            if midx != -1:
                this_stat = self.missions[midx].getStatus()
                n_2b_retried = self.missions[midx].getRetry()
                retry_count = self.missions[midx].getNRetries()
                self.showMsg("check retries: "+str(mid)+str(self.missions[midx].getMid())+" n2b retries: "+str(n_2b_retried)+" n retried: "+str(retry_count))
                if "Complete" not in this_stat and retry_count < n_2b_retried:
                    self.showMsg("scheduing retry#:"+str(j)+" MID: "+str(mid))
                    next_run_index = j
                    break
        return next_run_index

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

        self.showMsg("TZ:"+tz+" GRP:"+grp+" BIDX:"+str(bidx)+" WIDX:"+str(widx)+" OIDX:"+str(oidx)+" THIS STATUS:"+this_stat)

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
                            self.showMsg("SWITCHED BOT:"+str(bidx))
                            if len(works[tz][bidx]["other_works"]) > 0 and len(works[tz][bidx]["bw_works"]) > 0:
                                if works[tz][bidx]["other_works"][oidx]["start_time"] < works[tz][bidx]["bw_works"][widx]["start_time"]:
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
                    self.showMsg("SWITCHED TZ: "+tz)
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
                    self.showMsg("all workdsTBD exhausted...")
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

        self.showMsg("MISSIONS needs retry: "+tz+" "+str(bid)+" "+grp+" "+str(mid))
        return tz, bid, grp, mid




    #convert time zone, time slot to datetime
    # the time slot is defined as following:
    # time slot is defined as a 20 minute interval, an entire day has 72 slots indexed 0~71
    # counting timezone, and starts from eastern standard time, the timezone will extend to
    # cover hawaii, which is 5 timezone away from eastern, so total time zone slots are
    # 72+15=87 or index 0~86.
    def ts2time(self, ts):
        thistime = datetime.now()
        zerotime = datetime(thistime.date().year, thistime.date().month, thistime.date().day, 0, 0, 0)
        time_change = timedelta(minutes=20*ts)
        runtime = zerotime + time_change
        return runtime

    def time2ts(self, pdt):
        thistime = datetime.now()
        zerotime = datetime(thistime.date().year, thistime.date().month, thistime.date().day, 0, 0, 0)
        # Get the time difference in seconds
        ts = int((pdt - zerotime).total_seconds()/1200)         # computer time slot in 20minuts chunk

        return ts


    def runBotTask(self, task):
        self.workingState = "Working"
        task_mission = self.missions[task.mid]
        # run all the todo steps
        # (steps, mission, skill, mode="normal"):
        runResult = runAllSteps(task.todos, task_mission.parent_settings)


    def showAbout(self):
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox", "E-Commerce Bots. \n (V1.0 2024-01-12 AIPPS LLC) \n"))
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

    def newBotView(self):
        # Logic for creating a new bot:
        # pop out a new windows for user to set parameters for a new bot.
        # at the moment, just add an icon.
        #new_bot = EBBOT(self)
        #new_icon = QIcon((":file-open.svg"))
        #self.centralWidget.setText("<b>File > New</b> clicked")
        if self.BotNewWin == None:
            self.BotNewWin = BotNewWin(self)
        self.BotNewWin.setMode("new")
        self.BotNewWin.setBot(EBBOT(self))
        self.BotNewWin.show()


    def trainNewSkill(self):
        if self.trainNewSkillWin == None:
            self.trainNewSkillWin = TrainNewWin(self)
            self.reminderWin = ReminderWin(self)
        self.showMsg("train new skill....")
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

    def findAllBot(self):
        self.bot_service.find_all_bots()

    def logOut(self):
        self.showMsg("logging out........")
        # result = self.cog_client.global_sign_out(self.cog.access_token)
        #result = self.cog_client.global_sign_out(AccessToken=self.cog.access_token)
        result = self.cog.logout()

        self.showMsg("logged out........")
        self.close()
        # now should close the main window and bring back up the login screen?


    def addNewBots(self, new_bots):
        # Logic for creating a new bot:
        api_bots = []
        self.showMsg("adding new bots....")
        for new_bot in new_bots:
            api_bots.append({
                # "bid": new_bot.getBid(),
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
                "ebpw": new_bot.getAcctPw(),
                "backemail_site": new_bot.getBackEmSite()
            })
        jresp = send_add_bots_request_to_cloud(self.session, new_bots, self.tokens['AuthenticationResult']['IdToken'])

        if "errorType" in jresp:
            screen_error = True
            self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            self.showMsg("jresp:"+json.dumps(jresp))
            jbody = jresp["body"]
            #now that add is successfull, update local file as well.
            # first, update bot ID both in data structure and in GUI display.
            for i, resp_rec in enumerate(jresp["body"]):
                new_bots[i].setBid(resp_rec["bid"])
                new_bots[i].setInterests(resp_rec["interests"])
                self.bots.append(new_bots[i])
                self.botModel.appendRow(new_bots[i])
            self.selected_bot_row = self.botModel.rowCount() - 1
            self.selected_bot_item = self.botModel.item(self.selected_bot_row)
            # now add bots to local DB.
            self.bot_service.inset_bots_batch(jbody, api_bots)

    def updateBots(self, bots):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        api_bots = []
        for abot in bots:
            api_bots.append({
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
                "ebpw": abot.getAcctPw(),
                "backemail_site": abot.getAcctPw()
            })

        jresp = send_update_bots_request_to_cloud(self.session, bots, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"]), "ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            jbody = jresp["body"]

            if jbody['numberOfRecordsUpdated'] == len(bots):
                self.bot_service.update_bots_batch(api_bots)
            else:
                self.showMsg("WARNING: bot NOT updated in Cloud!")

    def addNewMissions(self, new_missions):
        # Logic for creating a new mission:
        self.showMsg("adding a .... new... mission")
        api_missions = []
        for new_mission in new_missions:
            api_missions.append({
                # "mid": new_mission.getMid(),
                "ticket": new_mission.getMid(),
                "botid": new_mission.getBid(),
                "status": new_mission.getStatus(),
                "createon": new_mission.getBD(),
                "esd": new_mission.getEsd(),
                "ecd": new_mission.getEcd(),
                "asd": new_mission.getAsd(),
                "abd": new_mission.getAbd(),
                "aad": new_mission.getAad(),
                "afd": new_mission.getAfd(),
                "acd": new_mission.getAcd(),
                "actual_start_time": new_mission.getActualStartTime(),
                "est_start_time": new_mission.getEstimatedStartTime(),
                "actual_run_time": new_mission.getActualRunTime(),
                "est_run_time": new_mission.getEstimatedRunTime(),
                "n_retries": new_mission.getNRetries(),
                "cuspas": new_mission.getCusPAS(),
                "search_cat": new_mission.getSearchCat(),
                "search_kw": new_mission.getSearchKW(),
                "pseudo_store": new_mission.getPseudoStore(),
                "pseudo_brand": new_mission.getPseudoBrand(),
                "pseudo_asin": new_mission.getPseudoASIN(),
                "repeat": new_mission.getRetry(),
                "mtype": new_mission.getMtype(),
                "mconfig": new_mission.getConfig(),
                "skills": new_mission.getSkills(),
                "delDate": new_mission.getDelDate(),
                "asin": new_mission.getASIN(),
                "store": new_mission.getStore(),
                "brand": new_mission.getBrand(),
                "image": new_mission.getImagePath(),
                "title": new_mission.getTitle(),
                "variations": new_mission.getVariations(),
                "rating": new_mission.getRating(),
                "feedbacks": new_mission.getFeedbacks(),
                "price": new_mission.getPrice(),
                "customer": new_mission.getCustomerID(),
                "platoon": new_mission.getPlatoonID(),
                "result": ""
            })
        jresp = send_add_missions_request_to_cloud(self.session, new_missions,
                                                   self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            self.showMsg("Delete Bots ERROR Type: "+json.dumps(jresp["errorType"]), "ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            jbody = jresp["body"]
            # now that delete is successfull, update local file as well.
            # self.writeMissionJsonFile()
            self.showMsg("JUST ADDED mission:"+json.dumps(jbody))
            for i, new_mission in enumerate(new_missions):
                new_mission.setMid(jbody[i]["mid"])
                new_mission.setTicket(jbody[i]["ticket"])
                new_mission.setEstimatedStartTime(jbody[i]["esttime"])
                new_mission.setEstimatedRunTime(jbody[i]["runtime"])
                new_mission.setEsd(jbody[i]["esd"])
                self.missions.append(new_mission)
                self.missionModel.appendRow(new_mission)
            self.mission_service.insert_missions_batch(jbody, api_missions)

            mid_list = [mission.getMid() for mission in new_missions]
            self.mission_service.find_missions_by_mids(mid_list)

    def updateMissions(self, missions):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        api_missions = []
        for amission in missions:
            api_missions.append({
                "mid": amission.getMid(),
                "ticket": amission.getMid(),
                "botid": amission.getBid(),
                "status": amission.getStatus(),
                "createon": amission.getBD(),
                "esd": amission.getEsd(),
                "ecd": amission.getEcd(),
                "asd": amission.getAsd(),
                "abd": amission.getAbd(),
                "aad": amission.getAad(),
                "afd": amission.getAfd(),
                "acd": amission.getAcd(),
                "actual_start_time": amission.getActualStartTime(),
                "est_start_time": amission.getEstimatedStartTime(),
                "actual_run_time": amission.getActualRunTime(),
                "est_run_time": amission.getEstimatedRunTime(),
                "n_retries": amission.getNRetries(),
                "cuspas": amission.getCusPAS(),
                "search_cat": amission.getSearchCat(),
                "search_kw": amission.getSearchKW(),
                "pseudo_store": amission.getPseudoStore(),
                "pseudo_brand": amission.getPseudoBrand(),
                "pseudo_asin": amission.getPseudoASIN(),
                "repeat": amission.getRetry(),
                "type": amission.getMtype(),
                "config": amission.getConfig(),
                "skills": amission.getSkills(),
                "delDate": amission.getDelDate(),
                "asin": amission.getASIN(),
                "store": amission.getStore(),
                "brand": amission.getBrand(),
                "image": amission.getImagePath(),
                "title": amission.getTitle(),
                "variations": amission.getVariations(),
                "rating": amission.getRating(),
                "feedbacks": amission.getFeedbacks(),
                "price": amission.getPrice(),
                "customer": amission.getCustomerID(),
                "platoon": amission.getPlatoonID(),
                "result": amission.getResult()
            })

        jresp = send_update_missions_request_to_cloud(self.session, missions, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            jbody = jresp["body"]
            self.showMsg("Update Cloud side result:"+json.dumps(jbody))
            if jbody['numberOfRecordsUpdated'] == len(missions):
                self.mission_service.update_missions_by_ticket(api_missions)
                mid_list = [mission.getMid() for mission in missions]
                self.mission_service.find_missions_by_mids(mid_list)
            else:
                self.showMsg("WARNIN: cloud NOT updated.", "warn")

    def addBotsMissionsSkillsFromCommander(self, botsJson, missionsJson, skillsJson):

        self.showMsg("BOTS String:"+str(type(botsJson))+json.dumps(botsJson))
        self.showMsg("Missions String:"+str(type(missionsJson))+json.dumps(missionsJson))
        self.showMsg("Skills String:" + str(type(skillsJson)) + json.dumps(skillsJson))
        for bjs in botsJson:
            self.newBot = EBBOT(self)
            self.newBot.loadJson(bjs)
            self.bots.append(self.newBot)
            self.botModel.appendRow(self.newBot)
            self.selected_bot_row = self.botModel.rowCount() - 1
            self.selected_bot_item = self.botModel.item(self.selected_bot_row)

        for mjs in missionsJson:
            self.newMission = EBMISSION(self)
            self.newMission.loadJson(mjs)
            self.missions.append(self.newMission)
            self.missionModel.appendRow(self.newMission)
            self.selected_mission_row = self.missionModel.rowCount() - 1
            self.selected_mission_item = self.missionModel.item(self.selected_mission_row)

        for skjs in skillsJson:
            self.newSkill = WORKSKILL(self, skjs["name"])
            self.newSkill.loadJson(skjs)
            self.skills.append(self.newSkill)
            # self.skillModel.appendRow(self.newSkill)


    def addVehicle(self, vip):
        try:
            # ipfields = vinfo.peername[0].split(".")
            ipfields = vip.split(".")
            ip = ipfields[len(ipfields) - 1]
            if len(self.vehicles) > 0:
                vids = [v.getVid() for v in self.vehicles]
                print("existing Vids "+ip+":"+json.dumps(vids))
            else:
                vids = []
            if ip not in vids:
                self.showMsg("adding a new vehicle..... "+vip)
                newVehicle = VEHICLE(self)
                newVehicle.setIP(vip)
                newVehicle.setVid(ip)
                found_fl = next((fl for i, fl in enumerate(fieldLinks) if fl["ip"][0] == vip), None)
                print("FL0 IP:", fieldLinks[0]["ip"])
                newVehicle.setFieldLink(found_fl)
                self.vehicles.append(newVehicle)
                self.runningVehicleModel.appendRow(newVehicle)
                if self.platoonWin:
                    self.platoonWin.updatePlatoonWinWithMostRecentlyAddedVehicle()
            else:
                self.showMsg("Reconnected: "+vip)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddVehicle:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddVehicle: traceback information not available:" + str(e)

            self.showMsg(ex_stat)



    def removeVehicle(self, peername):
        self.showMsg("removing vehicle: "+peername)
        found_v_idx = next((i for i, v in enumerate(self.vehicles) if v.getVid == peername), -1)

        if found_v_idx > 0:
            found_v = self.vehicles[found_v_idx]
            self.runningVehicleModel.removeRow(found_v.row())
            self.vehicles.pop(found_v_idx)

            if self.platoonWin:
                self.platoonWin.updatePlatoonWinWithMostRecentlyRemovedVehicle()


    def checkVehicles(self):
        self.showMsg("adding already linked vehicles.....")
        for i in range(len(fieldLinks)):
            self.showMsg("a fieldlink....."+json.dumps(fieldLinks[i]["ip"]))
            newVehicle = VEHICLE(self)
            newVehicle.setIP(fieldLinks[i]["ip"][0])
            newVehicle.setFieldLink(fieldLinks[i])
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
        self.showMsg("hello???")
        if command == "refresh":
            # cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqStatusUpdate", "missions":"all"}
        elif command == "halt":
            # cmd = '{\"cmd\":\"reqHaltMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqHaltMissions", "missions":"all"}
        elif command == "resume":
            # cmd = '{\"cmd\":\"reqResumeMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqResumeMissions", "missions":"all"}
        elif command == "cancel this":
            mission_list_string = ','.join(str(x) for x in mids)
            # cmd = '{\"cmd\":\"reqCancelMissions\", \"missions\":\"'+mission_list_string+'\"}'
            cmd = {"cmd":"reqCancelMissions", "missions": mission_list_string}
        elif command == "cancel all":
            # cmd = '{\"cmd\":\"reqCancelAllMissions\", \"missions\":\"all\"}'
            cmd = {"cmd":"reqCancelAllMissions", "missions":"all"}
        else:
            # cmd = '{\"cmd\":\"ping\", \"missions\":\"all\"}'
            cmd = {"cmd":"ping", "missions":"all"}

        self.showMsg("cmd is: "+cmd)
        if len(rows) > 0:
            effective_rows = list(filter(lambda r: r >= 0, rows))
        else:
            effective_rows = []

        self.showMsg("effective_rows:"+json.dumps(effective_rows))
        self.sendToPlatoons(effective_rows, cmd)


    def cancelVehicleMission(self, rows):
        # cmd = '{\"cmd\":\"reqCancelMission\", \"missions\":\"all\"}'
        cmd = {"cmd": "reqCancelMission", "missions": "all"}
        effective_rows = list(filter(lambda r: r >= 0, rows))
        if len(effective_rows) > 0:
            self.sendToPlatoons(effective_rows, cmd)

    # this function sends commands to platoon(s)
    def sendToPlatoons(self, idxs, cmd={"cmd": "ping"}):
        # this shall bring up a windows, but for now, simply send something to a platoon for network testing purpose...
        #if self.platoonWin == None:
        #    self.platoonWin = PlatoonWindow(self)
        #self.BotNewWin.resize(400, 200)
        #self.platoonWin.show()
        self.showMsg("sending commands.....")
        self.showMsg("tcp connections....."+json.dumps([flk["ip"] for flk in fieldLinks]))

        if len(idxs) == 0:
            idxs = range(self.runningVehicleModel.rowCount())

        # if not self.tcpServer == None:
        if len(fieldLinks) > 0:
            self.showMsg("Currently, there are ("+str(len(fieldLinks))+") connection to this server.....")
            for i in range(len(fieldLinks)):
                if i in idxs:
                    self.send_json_to_platoon(fieldLinks[i], cmd)
                    self.showMsg("cmd sent on link:"+str(i)+":"+json.dumps(cmd))
        else:
            self.showMsg("Warning..... TCP server not up and running yet...")

    # This function translate bots data structure matching ebbot.py to Json format for file storage.
    def genBotsJson(self):
        bjs = []
        for bot in self.bots:
            self.showMsg("bot gen json0...." + str(len(self.bots)))
            bjs.append(bot.genJson())
        #self.showMsg(json.dumps(bjs))
        return bjs


    # This function translate bots data from Json format to the data structure matching ebbot.py
    def translateBotsJson(self):
        for bj in self.botJsonData:
            new_bot = EBBOT(self)
            new_bot.setJsonData(bj)
            self.bots.append(new_bot)


    def readBotJsonFile(self):
        if exists(self.file_resouce.BOTS_FILE):
            with open(self.file_resouce.BOTS_FILE, 'r') as file:
                self.botJsonData = json.load(file)
                self.translateBotsJson(self.botJsonData)

            file.close()


    def saveBotJsonFile(self):
        if self.file_resouce.BOTS_FILE == None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.file_resouce.BOTS_FILE = filename

        if self.file_resouce.BOTS_FILE:
            try:
                botsdata = self.genBotsJson()
                self.showMsg("BOTS_FILE: " + self.file_resouce.BOTS_FILE)
                with open(self.file_resouce.BOTS_FILE, 'w') as jsonfile:
                    json.dump(botsdata, jsonfile)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QMessageBox.information(
                    self,
                    "Unable to save file: %s" % filename
                )
        else:
            self.showMsg("Bot file does NOT exist.")

    def translateInventoryJson(self):
        #self.showMsg("Translating JSON to data......."+str(len(self.sellerInventoryJsonData)))
        for bj in self.sellerInventoryJsonData:
            new_inventory = INVENTORY()
            new_inventory.setJsonData(bj)
            self.inventories.append(new_inventory)


    def readSellerInventoryJsonFile(self, inv_file):
        if inv_file == "":
            inv_file_name = self.SELLER_INVENTORY_FILE
        else:
            inv_file_name = inv_file

        self.showMsg("INVENTORY file: "+inv_file_name)
        if exists(inv_file_name):
            self.showMsg("Reading inventory file: "+inv_file_name)
            with open(inv_file_name, 'r') as file:
                self.sellerInventoryJsonData = json.load(file)
                self.translateInventoryJson()
        else:
            self.showMsg("NO inventory file found!")


    def getBotsInventory(self, botid):
        self.showMsg("botid type:"+str(botid)+" "+str(len(self.inventories)))
        self.showMsg(json.dumps(self.inventories[0].products[0].genJson()))
        found = next((x for x in self.inventories if botid in x.getAllowedBids()), None)
        return found

    # This function translate bots data structure matching ebbot.py to Json format for file storage.
    def genMissionsJson(self):
        mjs = []
        for mission in self.missions:
            self.showMsg("mission gen json0...." + str(len(self.missions)))
            mjs.append(mission.genJson())
        #self.showMsg(json.dumps(bjs))
        return mjs


    # This function translate bots data from Json format to the data structure matching ebbot.py
    def translateMissionsJson(self):
        for mj in self.missionJsonData:
            new_mission = EBMISSION()
            new_mission.setJsonData(mj)
            self.missions.append(new_mission)


    def readMissionJsonFile(self):
        if exists(self.file_resouce.MISSIONS_FILE):
            with open(self.file_resouce.MISSIONS_FILE, 'r') as file:
                self.missionJsonData = json.load(file)
                self.translateMissionsJson(self.missionJsonData)


    def writeMissionJsonFile(self):
        if self.file_resouce.MISSIONS_FILE == None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.file_resouce.MISSIONS_FILE = filename

        if self.file_resouce.MISSIONS_FILE and exists(self.file_resouce.MISSIONS_FILE):
            try:
                missionsdata = self.genMissionsJson()
                self.showMsg("MISSIONS_FILE:" + self.file_resouce.MISSIONS_FILE)
                with open(self.file_resouce.MISSIONS_FILE, 'w') as jsonfile:
                    json.dump(missionsdata, jsonfile)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QMessageBox.information(
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
        self.showMsg("runn all")

    def scheduleCalendarView(self):
        # Logic for the bot-mission-scheduler
        # pop out a new windows for user to view and schedule the missions.
        # at the moment, just add an icon.
        #new_bot = EBBOT(self)
        #new_icon = QIcon((":file-open.svg"))
        #self.centralWidget.setText("<b>File > New</b> clicked")
        self.scheduleWin = ScheduleWin()
        #self.BotNewWin.resize(400, 200)
        self.scheduleWin.show()

    def newMissionView(self):
        if self.missionWin == None:
            self.missionWin = MissionNewWin(self)
            self.missionWin.setOwner(self.owner)
            #self.BotNewWin.resize(400, 200)
        else:
            self.missionWin.setMode("new")

        self.missionWin.show()

    def newVehiclesView(self):
        if self.platoonWin == None:
            self.showMsg("creating platoon monitor window....")
            self.platoonWin = PlatoonWindow(self, "init")
        else:
            self.showMsg("Shows existing windows...")
        self.platoonWin.show()

    def eventFilter(self, source, event):
        if event.type() == QEvent.ContextMenu and source is self.botListView:
            #self.showMsg("bot RC menu....")
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)

            self.rcbotEditAction = self._createBotRCEditAction()
            self.rcbotCloneAction = self._createBotRCCloneAction()
            self.rcbotDeleteAction = self._createBotRCDeleteAction()
            self.rcbotChatAction = self._createBotRCChatAction()

            self.popMenu.addAction(self.rcbotEditAction)
            self.popMenu.addAction(self.rcbotCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.rcbotDeleteAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.rcbotChatAction)

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
                elif selected_act == self.rcbotChatAction:
                    self.chatBot()

            return True
        elif event.type() == QEvent.ContextMenu and source is self.missionListView:
            self.showMsg("mission RC menu....")
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)
            self.cusMissionEditAction = self._createCusMissionEditAction()
            self.cusMissionCloneAction = self._createCusMissionCloneAction()
            self.cusMissionDeleteAction = self._createCusMissionDeleteAction()
            self.cusMissionUpdateAction = self._createCusMissionUpdateAction()
            self.cusMissionRunAction = self._createRunMissionNowAction()

            self.popMenu.addAction(self.cusMissionEditAction)
            self.popMenu.addAction(self.cusMissionCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionDeleteAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionUpdateAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionRunAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_mission_row = source.indexAt(event.pos()).row()
                self.selected_cus_mission_item = self.missionModel.item(self.selected_mission_row)
                if selected_act == self.cusMissionEditAction:
                    print("edit mission clicked....")
                    self.editCusMission()
                elif selected_act == self.cusMissionCloneAction:
                    self.cloneCusMission()
                elif selected_act == self.cusMissionDeleteAction:
                    self.deleteCusMission()
                elif selected_act == self.cusMissionUpdateAction:
                    self.updateCusMissionStatus(self.selected_cus_mission_item)
                elif selected_act == self.cusMissionRunAction:
                    asyncio.create_task(self.runCusMissionNow(self.selected_cus_mission_item, self.gui_rpa_msg_queue))

            return True
        elif (event.type() == QEvent.MouseButtonPress ) and source is self.botListView:
            self.showMsg("CLICKED on bot:"+str(source.indexAt(event.pos()).row()))
        #     self.showMsg("unknwn.... RC menu...."+source+" EVENT: "+json.dumps(event))
        elif event.type() == QEvent.ContextMenu and source is self.completed_missionListView:
            self.showMsg("completed mission RC menu....")
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)
            self.cusMissionViewAction = self._createCusMissionViewAction()
            self.popMenu.addAction(self.cusMissionViewAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                self.selected_mission_row = source.indexAt(event.pos()).row()
                self.selected_cus_mission_item = self.completedMissionModel.item(self.selected_mission_row)
                if selected_act == self.cusMissionViewAction:
                    self.editCusMission()

        return super().eventFilter(source, event)

    def chatBot(self):
        # bring up the chat windows with this bot.
        # File actions
        if self.chatWin and self.chatWin.isVisible():
            self.showMsg("populating Chat GUI............")
            self.chatWin.select_contact(self.selected_bot_item.getBid())
            self.chatWin.load_chat_history(self.selected_bot_item.getBid())
        else:
            self.showMsg("populating a newly created Chat GUI............")
            from ChatGUIV2 import ChatDialog
            self.chatWin = ChatDialog(self, self.selected_bot_item.getBid())
            self.showMsg("done create win............"+str(self.selected_bot_item.getBid()))
        self.chatWin.show()

    def _createCusMissionViewAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&View"))
       return new_action

    def _createCusMissionEditAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Edit"))
       return new_action

    def _createCusMissionCloneAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Clone"))
        return new_action

    def _createCusMissionDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def _createCusMissionUpdateAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Update Status"))
        return new_action

    def _createRunMissionNowAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Run Now"))
        return new_action

    def editCusMission(self):
        # File actions
        if self.missionWin:
            self.showMsg("populating mission GUI............")
            self.missionWin.setMission(self.selected_cus_mission_item)
        else:
            self.showMsg("populating a newly created mission GUI............")
            self.missionWin = MissionNewWin(self)
            self.showMsg("done create mission win............"+str(self.selected_mission_item.getMid()))
            self.missionWin.setMission(self.selected_mission_item)

        self.missionWin.setMode("update")
        self.missionWin.show()
        self.showMsg("edit mission" + str(self.selected_mission_row))


    def cloneCusMission(self):
        # File actions
        new_mission = self.selected_cus_mission_item
        # new_bot.setText()
        self.addNewMissions([new_mission])
        self.searchLocalMissions()

    def deleteCusMission(self):
        # File actions
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox", "The mission will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QApplication.translate("QMessageBox", "Are you sure about deleting this mission?"))
        msgBox.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        msgBox.setDefaultButton(QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QMessageBox.Yes:
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
                self.showMsg("DONE WITH CLOUD SIDE REMOVE MISSION REQUEST.....")
                if "errorType" in jresp:
                    screen_error = True
                    self.showMsg("Delete Missions ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
                else:
                    self.showMsg("JRESP:"+json.dumps(jresp)+"<>"+json.dumps(jresp['body'])+"<>"+json.dumps(jresp['body']['$metadata'])+"<>"+json.dumps(jresp['body']['numberOfRecordsUpdated']))
                    meta_data = jresp['body']['$metadata']
                    if jresp['body']['numberOfRecordsUpdated'] == 0:
                        self.showMsg("WARNING: CLOUD SIDE MISSION DELETE NOT EXECUTED.")

                    for m in api_removes:
                        # missionTBDId = next((x for x in self.missions if x.getMid() == m["id"]), None)
                        self.mission_service.delete_missions_by_mid(m["id"])

                    for m in api_removes:
                        midx = next((i for i, x in enumerate(self.missions) if x.getMid() == m["id"]), -1)
                        self.showMsg("removeing MID:"+str(midx))
                        # If the element was found, remove it using pop()
                        if midx != -1:
                            self.missions.pop(midx)

                    # self.writeMissionJsonFile()

        #self.botModel.removeRow(self.selected_bot_row)
        #self.showMsg("delete bot" + str(self.selected_bot_row))

    def updateCusMissionStatus(self, amission):
        # send this mission's status to Cloud
        api_missions = [amission]
        # jresp = send_update_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'])
        # if "errorType" in jresp:
        #     screen_error = True
        #     self.showMsg("Delete Bots ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        # else:
        #     jbody = json.loads(jresp["body"])
        #     # now that delete is successfull, update local file as well.
        #     self.writeMissionJsonFile()

    async def runCusMissionNow(self, amission, gui_rpa_queue):
        # check if psk is already there, if not generate psk, then run it.
        self.showMsg("run mission now....")
        worksTBD = {"works": [{
            "mid": amission.getMid(),
            "name": "automation",
            "bid": amission.getBid(),
            "config": {},
            "ads_xlsx_profile": ""
        }], "current widx":0}

        current_bid, current_mid, run_result = await self.runRPA(worksTBD, gui_rpa_queue)


    def _createBotRCEditAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Edit"))
       return new_action

    def _createBotRCCloneAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Clone"))
        return new_action

    def _createBotRCDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Delete"))
        return new_action

    def _createBotRCChatAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Chat"))
        return new_action

    def editBot(self):
        if self.BotNewWin == None:
            self.BotNewWin = BotNewWin(self)
        self.BotNewWin.setBot(self.selected_bot_item)

        self.BotNewWin.setMode("update")
        self.BotNewWin.show()
        self.showMsg("edit bot" + str(self.selected_bot_row))

    def cloneBot(self):
        # File actions
        new_bot = self.selected_bot_item
        # new_bot.setText()
        self.addNewBots([new_bot])
        self.searchLocalBots()

    def deleteBot(self):
        # File actions
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox", "The bot will be removed and won't be able recover from it.."))
        msgBox.setInformativeText(QApplication.translate("QMessageBox", "Are you sure about deleting this bot?"))
        msgBox.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        msgBox.setDefaultButton(QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QMessageBox.Yes:
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
                jresp = send_remove_bots_request_to_cloud(self.session, api_removes, self.tokens['AuthenticationResult']['IdToken'])
                self.showMsg("DONE WITH CLOUD SIDE REMOVE BOT REQUEST.....")
                if "errorType" in jresp:
                    screen_error = True
                    self.showMsg("Delete Bots ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
                else:
                    self.showMsg("JRESP:"+json.dumps(jresp)+"<>"+json.dumps(jresp['body'])+"<>"+json.dumps(jresp['body']['$metadata'])+"<>"+json.dumps(jresp['body']['numberOfRecordsUpdated']))
                    meta_data = jresp['body']['$metadata']
                    if jresp['body']['numberOfRecordsUpdated'] == 0:
                        self.showMsg("WARNING: CLOUD SIDE DELETE NOT EXECUTED.")

                    for b in api_removes:
                        botTBDId = next((x for x in self.bots if x.getBid() == b["id"]), None)
                        self.bot_service.delete_bots_by_botid(b["id"])

                    for b in api_removes:
                        bidx = next((i for i, x in enumerate(self.bots) if x.getBid() == b["id"]), -1)

                        # If the element was found, remove it using pop()
                        if bidx != -1:
                            self.bots.pop(bidx)

                    # self.saveBotJsonFile()
    # data format conversion. nb is in EBBOT data structure format., nbdata is json
    def fillNewBotPubInfo(self, nbjson, nb):
        self.showMsg("filling bot public data for bot-" + str(nbjson["pubProfile"]["bid"]))
        nb.setNetRespJsonData(nbjson)

    def fillNewBotFullInfo(self, nbjson, nb):
        self.showMsg("filling bot data for bot-" + str(nbjson["pubProfile"]["bid"]))
        nb.loadJson(nbjson)


    def newBotFromFile(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open Bot Definition File"),
            '',
            QApplication.translate("QFileDialog", "Bot Files (*.json *.xlsx *.csv)")
        )
        self.showMsg("loading bots from a file..."+filename)
        bots_from_file=[]
        if filename != "":
            if "json" in filename:
                api_bots = []
                uncompressed = open(filename)
                if uncompressed != None:
                    # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
                    filebbots = json.load(uncompressed)
                    if len(filebbots) > 0:
                        bots_from_file = []
                        #add bots to the relavant data structure and add these bots to the cloud and local DB.
                        for fb in filebbots:
                            new_bot = EBBOT(self)
                            self.fillNewBotFullInfo(fb, new_bot)
                            bots_from_file.append(new_bot)
                    else:
                        self.warn(QApplication.translate("QMainWindow", "Warning: NO bots found in file."))
                else:
                    self.warn(QApplication.translate("QMainWindow", "Warning: No file."))

            elif "xlsx" in filename:
                self.showMsg("working on file:"+filename)
                xls = openpyxl.load_workbook(filename, data_only=True)

                # Initialize an empty list to store JSON data
                botsJson = []
                # Iterate over each sheet in the Excel file
                title_cells = []
                for idx, sheet in enumerate(xls.sheetnames):
                    # Read the sheet into a DataFrame
                    ws = xls[sheet]

                    # Iterate over each row in the sheet
                    for ri, row in enumerate(ws.iter_rows(values_only=True)):
                        if idx == 0 and ri == 0:
                            title_cells = [cell for cell in row]
                        elif ri > 0:
                            if len(row) == 25:
                                botJson = {}
                                for ci, cell in enumerate(title_cells):
                                    if cell == "DoB":
                                        botJson[cell] = row[ci].strftime('%Y-%m-%d')
                                    else:
                                        botJson[cell] = row[ci]

                                botsJson.append(botJson)

                    # Convert DataFrame to JSON and append to the list
                self.showMsg("total # of rows read:"+str(len(botsJson)))
                self.showMsg("all jsons from bot xlsx file:"+json.dumps(botsJson))
                bots_from_file = []
                for bjson in botsJson:
                    new_bot = EBBOT(self)
                    new_bot.loadXlsxData(bjson)
                    bots_from_file.append(new_bot)
                    new_bot.genJson()
            else:
                self.showMsg("ERROR: bot files must either be in .json format or .xlsx format!")

        if len(bots_from_file) > 0:
            self.addNewBots(bots_from_file)

    # data format conversion. nb is in EBMISSION data structure format., nbdata is json
    def fillNewMissionFromCloud(self, nmjson, nm):
        self.showMsg("filling mission data")
        nm.setNetRespJsonData(nmjson)


    def addMissionsToLocalDB(self, missions):
        api_missions = []
        for new_mission in missions:
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
                "actual_start_time": new_mission.getActualStartTime(),
                "est_start_time": new_mission.getEstimatedStartTime(),
                "actual_run_time": new_mission.getActualRunTime(),
                "est_run_time": new_mission.getEstimatedRunTime(),
                "cuspas": new_mission.getCusPAS(),
                "search_cat": new_mission.getSearchCat(),
                "search_kw": new_mission.getSearchKW(),
                "pseudo_store": new_mission.getPseudoStore(),
                "pseudo_brand": new_mission.getPseudoBrand(),
                "pseudo_asin": new_mission.getPseudoASIN(),
                "repeat": new_mission.getRetry(),
                "mtype": new_mission.getMtype(),
                "mconfig": new_mission.getConfig(),
                "skills": new_mission.getSkills(),
                "delDate": new_mission.getDelDate(),
                "asin": new_mission.getASIN(),
                "store": new_mission.getStore(),
                "brand": new_mission.getBrand(),
                "image": new_mission.getImagePath(),
                "title": new_mission.getTitle(),
                "variations": new_mission.getVariations(),
                "rating": new_mission.getRating(),
                "feedbacks": new_mission.getFeedbacks(),
                "price": new_mission.getPrice(),
                "customer": new_mission.getCustomerID(),
                "platoon": new_mission.getPlatoonID(),
                "result": new_mission.getResult()
            })
        self.mission_service.insert_missions_batch_(api_missions)

    def newMissionFromFile(self):
        self.showMsg("loading missions from a file...")
        api_missions = []
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open Mission Definition File"),
            '',
            QApplication.translate("QFileDialog", "Mission Files (*.json *.xlsx *.csv)")
        )
        if filename != "":
            if "json" in filename:
                api_missions = []
                # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
                filebmissions = json.load(filename)
                if len(filebmissions) > 0:
                    #add bots to the relavant data structure and add these bots to the cloud and local DB.

                    jresp = send_add_missions_request_to_cloud(self.session, filebmissions,
                                                           self.tokens['AuthenticationResult']['IdToken'])

                    if "errorType" in jresp:
                        screen_error = True
                        self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
                    else:
                        self.showMsg("jresp type: "+str(type(jresp))+" "+str(len(jresp["body"])))
                        jbody = jresp["body"]
                        # now that add is successfull, update local file as well.

                        # now add missions to local DB.
                        new_missions =[]
                        for i in range(len(jbody)):
                            self.showMsg(str(i))
                            new_mission = EBMISSION(self)
                            # move json file based mission into MISSION data structure.
                            new_mission.loadJson(filebmissions)
                            self.fillNewMissionFromCloud(jbody[i], new_mission)
                            self.missions.append(new_mission)
                            self.missionModel.appendRow(new_mission)
                            new_missions.append(new_mission)

                        self.addMissionsToLocalDB(new_missions)

                else:
                    self.warn(QApplication.translate("QMainWindow", "Warning: NO missions found in file."))

            elif "xlsx" in filename:
                self.showMsg("working on file:"+filename)
                xls = openpyxl.load_workbook(filename, data_only=True)

                # Initialize an empty list to store JSON data
                # Iterate over each sheet in the Excel file
                title_cells = []
                for idx, sheet in enumerate(xls.sheetnames):
                    # Read the sheet into a DataFrame
                    ws = xls[sheet]

                    # Iterate over each row in the sheet
                    for ri, row in enumerate(ws.iter_rows(values_only=True)):
                        if idx == 0 and ri == 0:
                            title_cells = [cell for cell in row]
                        elif ri > 0:
                            if len(row) == 25:
                                botJson = {}
                                for ci, cell in enumerate(title_cells):
                                    if cell == "DoB":
                                        botJson[cell] = row[ci].strftime('%Y-%m-%d')
                                    else:
                                        botJson[cell] = row[ci]

                                botsJson.append(botJson)

        self.showMsg("total # of rows read: "+str(len(botsJson)))
        self.showMsg("all jsons from bot xlsx file: "+json.dumps(botsJson))
        missions_from_file = []
        for bjson in botsJson:
            new_mission = EBMISSION(self)
            new_mission.loadXlsxData(bjson)
            missions_from_file.append(new_mission)
            # new_mission.genJson()

        self.addNewMissions(missions_from_file)

    def process_original_xlsx_file(self, file_path):
        # Read the Excel file, skipping the first two rows
        df = pd.read_excel(file_path, skiprows=2)

        # Drop rows where all elements are NaN
        df.dropna(how='all', inplace=True)

        # Convert each row to a JSON object and append to a list
        json_list = df.to_dict(orient='records')

        #add a reverse link back to
        for jl in json_list:
            jl["file_link"] = file_path

        return json_list

    def update_original_xlsx_file(self, file_path, mission_data):
        # Read the Excel file, skipping the first two rows
        dir_path = os.path.dirname(file_path)
        df = pd.read_excel(file_path, skiprows=2)

        # Drop rows where all elements are NaN
        df.dropna(how='all', inplace=True)

        # Convert each row to a JSON object and append to a list
        json_list = df.to_dict(orient='records')

        mission_ids = [mission["mission ID"] for mission in mission_data]
        completion_dates = [mission["completion date"] for mission in mission_data]

        # Add new columns with default or empty values
        df['mission ID'] = mission_ids[:len(df)]
        df['completion date'] = completion_dates[:len(df)]

        # Get the new file name using the first row of the "mission ID" column
        new_mission_id = df.loc[0, 'mission ID']
        base_name = os.path.basename(file_path)
        new_file_name = f"{os.path.splitext(base_name)[0]}_{new_mission_id}.xlsx"
        new_file_path = os.path.join(dir_path, new_file_name)

        # Save the updated DataFrame to a new file
        df.to_excel(new_file_path, index=False)

        print(f"File saved as {new_file_name}")


    def newMissionFromNewReq(self, reqJson):
        new_mission = EBMISSION(self)
        new_mission.loadAMZReqData(reqJson)
        return new_mission

    def newBuyMissionFromFiles(self):
        dtnow = datetime.now()
        date_word = dtnow.strftime("%Y%m%d")

        new_orders_dir = ecb_data_homepath + "/new_orders/ORDER" + date_word + "/"
        self.showMsg("working on new orders:" + new_orders_dir)

        new_buy_missions = []
        if os.path.isdir(new_orders_dir):
            files = os.listdir(new_orders_dir)
            xlsx_files = [os.path.join(new_orders_dir, file) for file in files if os.path.isfile(os.path.join(new_orders_dir, file)) and file.endswith('.xlsx')]

            #each row of each xlsx file becomes a new mission
            for xlsx_file in xlsx_files:
                # store, brand, execution time, quantity, asin, search term, title, page number, price, variation, product image, fb type, fb title, fb contents, notes
                buy_mission_reqs = self.process_original_xlsx_file(xlsx_file)

                for buy_req in buy_mission_reqs:
                    n_buys = int(buy_req["quantity"])
                    for n in range(n_buys):
                        new_buy_missions.append(self.newMissionFromNewReq(buy_req))

        # now that we have created all the new missions,
        # create the in the cloud and local DB.
        # cloud side first

        if len(new_buy_missions) > 0:
            jresp = send_add_missions_request_to_cloud(self.session, new_buy_missions, self.tokens['AuthenticationResult']['IdToken'])

            if "errorType" in jresp:
                screen_error = True
                self.showMsg( "ERROR Type: " + json.dumps(jresp["errorType"]) + "ERROR Info: " + json.dumps(jresp["errorInfo"]))
            else:
                self.showMsg("jresp type: " + str(type(jresp)) + " " + str(len(jresp["body"])))
                jbody = jresp["body"]
                # now that add is successfull, update local file as well.

                # now update mission ID
                for i in range(len(jbody)):
                    new_buy_missions.setMid(jbody[i]["mid"])

                #now add to local DB.
                self.addMissionsToLocalDB(new_buy_missions)

                #add to local data structure
                self.missions = self.missions + new_buy_missions
                for new_buy in new_buy_missions:
                    self.missionModel.appendRow(new_buy)

    def fillNewSkill(self, nskjson, nsk):
        self.showMsg("filling skill data")
        nsk.setNetRespJsonData(nskjson)

    def showSkillManager(self):
        if self.SkillManagerWin == None:
            self.SkillManagerWin = SkillManagerWindow(self)
        self.SkillManagerWin.show()

    def uploadSkill(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Upload Skill File"),
            '',
            QApplication.translate("QFileDialog", "Skill Json Files (*.json)")
        )
        if filename != "":
            # ("body string:", uncompressed, "!", len(uncompressed), "::")
            sk_dir = os.path.abspath(filename)
            anchor_dir = sk_dir + "/" + os.path.basename(filename).split(".")[0] + "/images"
            scripts_dir = sk_dir + "/" + os.path.basename(filename).split(".")[0] + "/scripts"
            anchor_files = os.listdir(anchor_dir)
            for af in anchor_files:
                full_af_name = anchor_dir + "/" + af
                jresp = upload_file(self.session, full_af_name, self.tokens['AuthenticationResult']['IdToken'], "anchor")

            csk_file = scripts_dir + "/" + os.path.basename(filename).split(".")[0] + ".csk"
            jresp = upload_file(self.session, csk_file, self.tokens['AuthenticationResult']['IdToken'], "csk")


    def newSkillFromFile(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open Skill File"),
            '',
            QApplication.translate("QFileDialog", "Skill Json Files (*.json)")
        )
        self.showMsg("loading skill from a file..."+filename)
        if filename != "":
            api_skills = []
            try:
                with open(filename, 'r') as new_skill_file:
                    # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
                    skill_json = json.load(new_skill_file)
                    if skill_json:
                        #add skills to the relavant data structure and add these bots to the cloud and local DB.
                        # send_add_skills_to_cloud
                        jresp = send_add_skills_request_to_cloud(self.session, [skill_json], self.tokens['AuthenticationResult']['IdToken'])

                        if "errorType" in jresp:
                            screen_error = True
                            self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
                        else:
                            self.showMsg("jresp type: "+str(type(jresp))+" "+str(len(jresp["body"])))
                            jbody = jresp["body"]
                            # now that add is successfull, update local file as well.

                            # now add bot to local DB.

                            for i in range(len(jbody)):
                                self.showMsg(str(i))
                                new_skill = WORKSKILL(self, jbody[i]["name"])
                                self.fillNewSkill(jbody[i], new_skill)
                                self.skills.append(new_skill)
                                # self.skillModel.appendRow(new_skill)
                                api_skills.append({
                                    "skid": new_skill.getSkid(),
                                    "owner": new_skill.getOwner(),
                                    "platform": new_skill.getPlatform(),
                                    "app": new_skill.getApp(),
                                    "applink": new_skill.getAppLink(),
                                    "appargs": new_skill.getAppArgs(),
                                    "site": new_skill.getSiteName(),
                                    "sitelink": new_skill.getSite(),
                                    "name": new_skill.getName(),
                                    "path": new_skill.getPath(),
                                    "main": new_skill.getMain(),
                                    "createdon": new_skill.getCreatedOn(),
                                    "extensions": "",
                                    "runtime": new_skill.getRunTime(),
                                    "price_model": new_skill.getPriceModel(),
                                    "price": new_skill.getPrice(),
                                    "privacy": new_skill.getPrivacy(),
                                })
                                self.skill_service.insert_skill(api_skills[i])
                    else:
                        self.warn(QApplication.translate("QMainWindow", "Warning: NO skills in the file."))
            except Exception as e:
                traceback_info = traceback.extract_tb(e.__traceback__)
                # Extract the file name and line number from the last entry in the traceback
                if traceback_info:
                    ex_stat = "ErrorLoadSkillFile:" + traceback.format_exc() + " " + str(e)
                else:
                    ex_stat = "ErrorLoadSkillFile: traceback information not available:" + str(e)
                log3(ex_stat)
                log3(QApplication.translate("QMainWindow", "Warning: load skill file error."))

    def find_dependencies(self, main_file, visited, dependencies):
        if main_file in visited:
            return

        visited.add(main_file)

        # "type": "Use Skill",
        # "skill_name": "update_tracking",
        # "skill_path": "public/win_chrome_etsy_orders",
        # "skill_args": "gs_input",
        # "output": "total_label_cost"
        self.showMsg("TRYING...."+main_file)
        if os.path.exists(main_file):
            self.showMsg("OPENING...."+main_file)
            with open(main_file, 'r') as psk_file:
                code_jsons = json.load(psk_file)

                # go thru all steps.
                for key in code_jsons.keys():
                    if "type" in code_jsons[key]:
                        if code_jsons[key]["type"] == "Use Skill":

                            dependency_file = self.homepath + "/resource/skills/" + code_jsons[key]["skill_path"] + "/" + code_jsons[key]["skill_name"] + ".psk"
                            if dependency_file not in dependencies:
                                dependencies.add(dependency_file)
                                self.find_dependencies(dependency_file, visited, dependencies)



        # self.platform+"_"+self.App()+"_"+self.site_name+"_"+self.page+"_"+self.name is the output string format

    def analyzeMainSkillDependencies(self, main_psk):
        dependencies = set()
        visited = set()
        if os.path.exists(main_psk):
            self.find_dependencies(main_psk, visited, dependencies)
            if len(dependencies) > 0:
                dep_list = list(dependencies)
            else:
                dep_list = []
            self.showMsg("found dependency:"+json.dumps(dep_list))

            dep_ids = []
            for dep in dep_list:
                skid = self.findSkillIDWithSkillFileName(dep)
                dep_ids.append((skid, dep))

            existing_skill_ids = []
            for dp in dep_ids:
                if dp[0] == -1:
                    self.showMsg("ERROR: missing skill dependent skills file:"+str(dp[1]))
                else:
                    existing_skill_ids.append(dp[0])
            # existing_skill_ids = filter(lambda x: x == -1, dep_ids)
            self.showMsg("existing_skill_ids:"+json.dumps(existing_skill_ids))
        else:
            existing_skill_ids = []

        return existing_skill_ids


    def findSkillIDWithSkillFileName(self, skill_file_name):
        skidx = next((i for i, x in enumerate(self.skills) if x.matchPskFileName(skill_file_name)), -1)
        if skidx >= 0:
            return self.skills[skidx].getSkid()
        else:
            return -1



    # load locally stored skills
    def loadLocalPrivateSkills(self):
        skill_def_files = []
        skid_files = []
        psk_files = []
        csk_files = []
        json_files = []

        skdir = ecb_data_homepath + "/my_skills/"
        # Iterate over all files in the directory
        # Walk through the directory tree recursively
        for root, dirs, files in os.walk(skdir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    skill_def_files.append(file_path)

        # self.showMsg("local skill files: "+json.dumps(skill_def_files))

        # if json exists, use json to guide what to do
        for file_path in skill_def_files:
            with open(file_path) as json_file:
                sk_data = json.load(json_file)
                self.showMsg("loading skill f: "+str(sk_data["skid"])+" "+file_path)
                new_skill = WORKSKILL(self, sk_data["name"])
                new_skill.loadJson(sk_data)
                self.skills.append(new_skill)

                this_skill_dir = skdir+sk_data["platform"]+"_"+sk_data["app"]+"_"+sk_data["site_name"]+"_"+sk_data["page"]+"/"
                gen_string = sk_data["platform"]+"_"+sk_data["app"]+"_"+sk_data["site_name"]+"_"+sk_data["page"]+"_"+sk_data["name"]
                self.showMsg("total skill files loaded: "+str(len(self.skills)))
                self.load_external_functions(this_skill_dir, sk_data["name"], gen_string, sk_data["generator"])
                # no need to run genSkillCode, since once in table, will be generated later....
                # genSkillCode(sk_full_name, privacy, root_path, start_step, theme)
        self.showMsg("Added Local Private Skills:"+str(len(self.skills)))

    def load_external_functions(self, sk_dir, sk_name, gen_string, generator):
        generator_script = sk_dir+sk_name+".py"
        generator_diagram = sk_dir + sk_name + ".skd"
        added_handlers = []
        self.showMsg("Generator:"+" "+sk_dir+" "+sk_name+" "+gen_string+" "+generator+" "+generator_script+" "+generator_diagram)
        if os.path.isfile(generator_script):
            spec = importlib.util.spec_from_file_location(sk_name, generator_script)
            # Create a module object from the spec
            module = importlib.util.module_from_spec(spec)
            # Load the module
            spec.loader.exec_module(module)

            if hasattr(module, generator):
                self.showMsg("add key-val pair: "+gen_string+" "+generator)
                SkillGeneratorTable[gen_string] = getattr(module, generator)
        elif os.path.isfile(generator_diagram):
            self.showMsg("gen psk from diagram.")




    def matchSkill(self, sk_long_name, sk):
        sk_words = sk_long_name.split("_")
        sk_name = "_".join(sk_words[4:])
        if sk.getPlatform() == sk_words[0] and sk.getApp() == sk_words[1] and sk.getSiteName() == sk_words[2] and sk.getName() == sk_name:
            return True
        else:
            return False


    def checkIsMain(self, sk_long_name):
        is_main = False
        # first find out the skill based on sk_long_name.
        sk = next((x for x in self.skills if self.matchSkill(sk_long_name, x)), None)
        # then check whether this is a main skill
        if sk:
            if sk.getIsMain():
                is_main = True

        return is_main

    def newProductsFromFile(self):

        self.showMsg("loading products from a local file or DB...")
        api_products = []
        uncompressed = open(self.homepath + "/resource/testdata/newproducts.json")
        if uncompressed != None:
            # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
            fileproducts = json.load(uncompressed)
            if len(fileproducts) > 0:
                #add bots to the relavant data structure and add these bots to the cloud and local DB.

                # sql = 'CREATE TABLE IF NOT EXISTS  products (pid INTEGER PRIMARY KEY, name TEXT, title TEXT, asin TEXT, variations TEXT, site TEXT, sku TEXT, size_in TEXT, weight_lbs REAL, condition TEXT, fullfiller TEXT, price INTEGER, cost INTEGER, inventory_loc TEXT, inventory_qty TEXT)'
                #
                # sql = ''' INSERT INTO products (pid, name, title, asin, variations, site, sku, size_in, weight_lbs,
                #         condition, fullfiller, price, cost, inventory_loc, inventory_qty) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?); '''
                # data_tuple = (pd[0]["pid"], pd[0]["name"], pd[0]["title"], pd[0]["asin"], pd[0]["variations"], pd[0]["site"], \
                #               pd[0]["sku"], pd[0]["size_in"], pd[0]["weight_lbs"], pd[0]["condition"], pd[0]["fullfiller"], \
                #               pd[0]["price"], pd[0]["cost"], pd[0]["inventory_loc"], pd[0]["inventory_qty"])
                #
                # self.dbCursor.execute(sql, data_tuple)
                # self.dbcon.commit()
                self.product_service.find_all_products()

            else:
                self.warn(QApplication.translate("QMainWindow", "Warning: NO products found in file."))
        else:
            self.warn(QApplication.translate("QMainWindow", "Warning: No test products file"))

    # try load bots from local database, if nothing in th local DB, then
    # try to fetch bots from local json files (this is mostly for testing).
    def loadLocalBots(self, db_data: [BotModel]):
        dict_results = [result.to_dict() for result in db_data]
        self.showMsg("get local bots from DB::" + json.dumps(dict_results))
        if len(db_data) != 0:
            self.bots = []
            self.botModel.clear()
            for row in db_data:
                self.showMsg("loading a bot: "+json.dumps(row.to_dict()))
                new_bot = EBBOT(self)
                new_bot.loadDBData(row)
                new_bot.updateDisplay()
                self.bots.append(new_bot)
                self.botModel.appendRow(new_bot)
                self.selected_bot_row = self.botModel.rowCount() - 1
                self.selected_bot_item = self.botModel.item(self.selected_bot_row)
        else:
            self.showMsg("WARNING: local bots DB empty!")
            # self.newBotFromFile()



    # load locally stored mission, but only for the past 3 days, otherwise, there would be too much......
    def loadLocalMissions(self, db_data: [MissionModel]):
        dict_results = [result.to_dict() for result in db_data]
        self.showMsg("get local missions from db::" + json.dumps(dict_results))
        if len(db_data) != 0:
            self.missions = []
            self.missionModel.clear()
            for row in db_data:
                self.showMsg("loading a mission: "+json.dumps(row.to_dict()))
                new_mission = EBMISSION(self)
                new_mission.loadDBData(row)
                new_mission.setData(row)
                self.cuspas_to_diaplayable(new_mission)
                new_mission.updateDisplay()
                self.missions.append(new_mission)
                self.missionModel.appendRow(new_mission)
                self.selected_mission_row = self.missionModel.rowCount() - 1
                self.selected_mission_item = self.missionModel.item(self.selected_mission_row)
        else:
            self.showMsg("WARNING: local mission DB empty!")
            # self.newMissionFromFile()

    def cuspas_to_diaplayable(self, a_mission):
        cuspas_parts = a_mission.getCusPAS().split(",")
        a_mission.setPlatform(self.translateShortPlatform(cuspas_parts[0]))
        a_mission.setApp(cuspas_parts[1])
        a_mission.setSite(self.translateShortSiteName(cuspas_parts[2]))


    # fetch all bots stored in the cloud.
    def getAllBotsFromCloud(self):
        # File actions
        #resp = send_get_bots_request_to_cloud(self.session, self.cog.access_token)
        jresp = send_get_bots_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            self.showMsg("Gat All Bots ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            self.showMsg("resp body"+json.dumps(jresp["body"]))
            #jbody = json.loads(jresp["body"])
            # now that fetch all bots from the cloud side is successfull, need to compare with local data and merge:

    def setOwner(self, owner):
        self.owner = owner

    def runAll(self):
        threadCount = QThreadPool.globalInstance().maxThreadCount()
        self.label.setText(f"Running {threadCount} Threads")
        pool = QThreadPool.globalInstance()
        for i in range(threadCount):
            # 2. Instantiate the subclass of QRunnable
            #runnable = Runnable(i)
            # 3. Call start()
            #pool.start(runnable)
            self.showMsg("run thread")

    def editSettings(self):
        self.SettingsWin.show()

    def manualRunAll(self):
        txt_results = "{}"
        ico_results = "{}"

        for m in self.missions:
            status = m.run()

    def get_vehicle_settings(self):
        vsettings = {
            "vwins": len([v for v in self.vehicles if v.getOS() == "win"]),
            "vmacs": len([v for v in self.vehicles if v.getOS() == "mac"]),
            "vlnxs": len([v for v in self.vehicles if v.getOS() == "linux"])
        }
        # add self to the compute resource pool
        if self.hostrole == "Commander":
            if self.platform == "win":
                vsettings["vwins"] = vsettings["vwins"] + 1
            elif self.platform == "mac":
                vsettings["vmacs"] = vsettings["vmacs"] + 1
            else:
                vsettings["vlnxs"] = vsettings["vlnxs"] + 1
        return vsettings


    # the message queue is for messsage from tcpip task to the GUI task.
    async def servePlatoons(self, msgQueue):
        self.showMsg("starting servePlatoons")
        while True:
            print("listening to platoons")
            if not msgQueue.empty():
                while not msgQueue.empty():
                    net_message = await msgQueue.get()
                    self.showMsg("received queued msg from platoon..... [" + str(msgQueue.qsize()) + "]" + net_message)
                    msg_parts = net_message.split("!")
                    if msg_parts[1] == "net data":
                        self.processPlatoonMsgs(msg_parts[2], msg_parts[0])
                    elif msg_parts[1] == "connection":
                        # this is the initial connection msg from a client
                        print("recevied connection message: "+msg_parts[0])
                        if self.platoonWin == None:
                            self.platoonWin = PlatoonWindow(self, "conn")

                        # vinfo = json.loads(msg_parts[2])

                        self.addVehicle(msg_parts[0])

                        # after adding a vehicle, try to get this vehicle's info
                        if len(self.vehicles) > 0:
                            print("pinging platoon: "+str(len(self.vehicles)-1))
                            last_idx = len(self.vehicles)-1
                            self.sendToPlatoons([last_idx])         # sends a default ping command to get userful info.

                    elif msg_parts[1] == "net loss":
                        print("received net loss")
                        # remove this link from the link list
                        self.removeVehicle()

                msgQueue.task_done()

            await asyncio.sleep(1)

    # this is be run as an async task.
    async def runbotworks(self, gui_rpa_queue, gui_monitor_queue):
        # run all the work
        running = True

        while running:
            print("looping runbotworks.....")
            botTodos = None
            if self.workingState == "Idle":
                if self.getNumUnassignedWork() > 0:
                    self.showMsg(get_printable_datetime() + " - Found unassigned work: "+str(self.getNumUnassignedWork())+"<>"+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    self.assignWork()

                botTodos = self.checkNextToRun()
                if not botTodos == None:
                    self.showMsg("working on..... "+botTodos["name"])
                    self.workingState = "Working"
                    if botTodos["name"] == "fetch schedule":
                        self.showMsg("fetching schedule.........."+"<>"+datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                        last_start = int(datetime.now().timestamp()*1)

                        # this should be a daily routine, do it along with fetch schedule which is also daily routine.
                        self.dailySkillsetUpdate()

                        botTodos["status"] = self.fetchSchedule("", self.get_vehicle_settings())
                        last_end = int(datetime.now().timestamp()*1)
                        # there should be a step here to reconcil the mission fetched and missions already there in local data structure.
                        # if there are new cloud created walk missions, should add them to local data structure and store to the local DB.
                        # if "Completed" in botTodos["status"]:
                        current_run_report = self.genRunReport(last_start, last_end, 0, 0, botTodos["status"])
                        self.showMsg("POP the daily initial fetch schedule task from queue")
                        finished = self.todays_work["tbd"].pop(0)
                        self.todays_completed.append(finished)
                        time.sleep(5)
                        self.showMsg("done fetching schedule."+"<>" + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

                    elif botTodos["name"] == "automation":
                        # run 1 bot's work
                        self.showMsg("running RPA..............")
                        if "Completed" not in botTodos["status"]:
                            self.showMsg("time to run RPA........"+json.dumps(botTodos))
                            last_start = int(datetime.now().timestamp()*1)
                            current_bid, current_mid, run_result = await self.runRPA(botTodos, gui_rpa_queue, gui_monitor_queue)
                            last_end = int(datetime.now().timestamp()*1)

                        # else:
                            # now need to chop off the 0th todo since that's done by now....
                            #
                            print("total # of works:"+str(botTodos["current widx"])+":"+str(len(botTodos["works"])))
                            if current_mid >= 0:
                                current_run_report = self.genRunReport(last_start, last_end, current_mid, current_bid, run_result)

                            # if all tasks in the task group are done, we're done with this group.
                            if botTodos["current widx"] >= len(botTodos["works"]):
                                self.showMsg("POP a finished task from queue after runRPA")
                                finished = self.todays_work["tbd"].pop(0)
                                self.showMsg("JUST FINISHED A WORK GROUP:"+json.dumps(finished))
                                self.todays_completed.append(finished)

                                # update GUI display to move missions in this task group to the completed missions list.
                                self.updateCompletedMissions(finished)


                            if len(self.todays_work["tbd"]) == 0:
                                if self.hostrole == "Platoon":
                                    self.showMsg("Platoon Done with today!!!!!!!!!")
                                    self.doneWithToday()
                                else:
                                    # check whether we have collected all reports so far, there is 1 count difference between,
                                    # at this point the local report on this machine has not been added to toddaysReports yet.
                                    # this will be done in doneWithToday....
                                    self.showMsg("n todaysPlatoonReports: "+str(len(self.todaysPlatoonReports))+" n todays_completed: "+str(len(self.todays_completed)))
                                    self.showMsg("todaysPlatoonReports"+json.dumps(self.todaysPlatoonReports))
                                    self.showMsg("todays_completed"+json.dumps(self.todays_completed))
                                    if len(self.todaysPlatoonReports) == self.num_todays_task_groups:
                                        self.showMsg("Commander Done with today!!!!!!!!!")
                                        self.doneWithToday()
                    else:
                        self.showMsg("Unrecogizable todo...."+botTodos["name"])
                        self.showMsg("POP a unrecognized task from queue")
                        self.todays_work["tbd"].pop(0)

                else:
                    # nothing to do right now. check if all of today's work are done.
                    # if my own works are done and all platoon's reports are collected.
                    if self.hostrole == "Platoon":
                        if len(self.todays_work["tbd"]) == 0:
                            self.doneWithToday()

            if self.workingState != "Idle":
                # clear to make next round ready to work
                self.workingState = "Idle"

            print("running bot works whenever there is some to run....")
            await asyncio.sleep(1)


    #update a vehicle's missions status
    # rx_data is a list of mission status for each mission that belongs to the vehicle.
    def updateVMStats(self, rx_data):
        foundV = None
        for v in self.vehicles:
            if v.getIP() == rx_data["ip"]:
                self.showMsg("found vehicle by IP")
                foundV = v
                break

        if foundV:
            self.showMsg("updating vehicle Mission status...")
            foundV.setMStats(rx_data)

    # create some tests data just to tests out the vehichle view GUI.
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
            "status": "Completed",
            "error": "",
        },
        {
            "mid": 2,
            "botid": 2,
            "sst": "2023-10-22 12:11:12",
            "sd": 600,
            "ast": "2023-10-22 12:12:12",
            "aet": "2023-10-22 12:22:12",
            "status": "Running",
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
        try:
            fl_ips = [x["ip"] for x in fieldLinks]
            self.showMsg("Platoon Msg Received:"+msgString+" from::"+ip+"  "+str(len(fieldLinks)) + json.dumps(fl_ips))
            msg = json.loads(msgString)

            found = next((x for x in fieldLinks if x["ip"][0] == ip), None)

            # first, check ip and make sure this from a know vehicle.
            if msg["type"] == "intro" or msg["type"] == "pong":
                if found:
                    self.showMsg("recevied a vehicle introduction/pong:" + msg["content"]["name"] + ":" + msg["content"]["os"] + ":"+ msg["content"]["machine"])
                    found_vehicle = next((x for x in self.vehicles if x.getIP() == msg["ip"]), None)
                    if found_vehicle:
                        print("found a vehicle to set.... "+found_vehicle.getOS())
                        found_vehicle.setName(msg["content"]["name"])
                        if "Windows" in msg["content"]["os"]:
                            found_vehicle.setOS("Windows")
                        elif "Mac" in msg["content"]["os"]:
                            found_vehicle.setOS("Mac")
                        elif "Lin" in msg["content"]["os"]:
                            found_vehicle.setOS("Linux")

                        print("now found vehicle" + found_vehicle.getName() + " " + found_vehicle.getOS())

                #now
            elif msg["type"] == "status":
                # update vehicle status display.
                self.showMsg(msg["content"])
                self.showMsg("recevied a status update message")
                if self.platoonWin:
                    self.showMsg("updating platoon WIN")
                    self.platoonWin.updatePlatoonStatAndShow(msg)
                    self.platoonWin.show()
                else:
                    self.showMsg("ERROR: platoon win not yet exists.......")

                self.updateVMStats(msg)

            elif msg["type"] == "report":
                # collect report, the report should be already organized in json format and ready to submit to the network.
                self.showMsg("msg type:"+str(type(msg)))
                #msg should be in the following json format {"ip": self.ip, "type": "report", "content": []]}
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
                    self.showMsg("pop a finising a remotely executed task...."+str(task_idx))
                    finished = self.todays_work["tbd"].pop(task_idx)
                    self.todays_completed.append(finished)

                    # Here need to update completed mission display subwindows.
                    self.updateCompletedMissions(finished)

                self.showMsg("len todays's reports: "+str(len(self.todaysPlatoonReports))+" len todays's completed:"+str(len(self.todays_completed)))
                self.showMsg("completd: "+json.dumps(self.todays_completed))

                # keep statistics on all platoon runs.
                if len(self.todaysPlatoonReports) == self.num_todays_task_groups:
                    # check = all(item in List1 for item in List2)
                    # this means all reports are collected, ready to send to cloud.
                    self.doneWithToday()

            elif msg["type"] == "chat":
                self.showMsg("received chat message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotChatMessage(msg["content"])

            elif msg["type"] == "exlog":
                self.showMsg("received exlog message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotLogMessage(msg["content"])
            elif msg["type"] == "heartbeat":
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.showMsg("Heartbeat From Vehicle: "+msg["ip"])
            else:
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.showMsg("unknown type:"+msg["contents"])

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorprocessPlatoonMsgs:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorprocessPlatoonMsgs: traceback information not available:" + str(e)

            self.showMsg(ex_stat)



    def updateCompletedMissions(self, finished):
        finished_works = finished["works"]
        finished_mids = []
        finished_midxs = []
        finished_missions = []

        self.showMsg("all mission ids:"+json.dumps([m.getMid() for m in self.missions]))

        if len(finished_works) > 0:
            for bi in range(len(finished_works)):
                finished_mids.append(finished_works[bi]["mid"])
        self.showMsg("finished MIDS:"+json.dumps(finished_mids))

        for mid in finished_mids:
            found_i = next((i for i, mission in enumerate(self.missions) if mission.getMid() == mid), -1)
            self.showMsg("found midx:"+str(found_i))
            if found_i >= 0:
                finished_midxs.append(found_i)

        sorted_finished_midxs = sorted(finished_midxs, key=lambda midx: midx, reverse=True)
        self.showMsg("finished MID INDEXS:"+json.dumps(sorted_finished_midxs))

        for midx in sorted_finished_midxs:
            found_mission = self.missions[midx]
            self.showMsg("just finished mission ["+str(found_mission.getMid())+"] status:"+found_mission.getStatus())
            if "Completed" in found_mission.getStatus():
                found_mission.setMissionIcon(QIcon(self.file_resouce.mission_success_icon_path))
            else:
                found_mission.setMissionIcon(QIcon(self.file_resouce.mission_failed_icon_path))

            for item in self.missionModel.findItems('mission' + str(found_mission.getMid()) + ":Bot" + str(
                found_mission.getBid()) + ":" + found_mission.pubAttributes.ms_type + ":" + found_mission.pubAttributes.site):
                cloned_item = item.clone()
                self.missionModel.removeRow(item.row())
                self.completedMissionModel.appendRow(cloned_item)

    def genMissionStatusReport(self, mids, test_mode=True):
        # assumptions: mids should have already been error checked.
        self.showMsg("mids: "+json.dumps(mids))
        results = []
        if test_mode:
            # just to tests commander GUI can handle the result
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "Scheduled", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "Completed", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "600", "aet": "2023-11-09 01:22:12", "status": "Running", "error": ""}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "500", "aet": "2023-11-09 01:22:12", "status": "Warned", "error": "505"}
            results.append(result)
            result = {"mid": 1, "botid": 0, "sst": "2023-11-09 01:12:02", "ast": "2023-11-09 01:12:02", "sd": "300", "aet": "2023-11-09 01:22:12", "status": "Aborted", "error": "5"}
            results.append(result)
        else:
            for mid in mids:
                if mid > 0 and mid < len(self.missions):
                    self.showMsg("working on MID:"+str(mid))
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


        self.showMsg("mission status result:"+json.dumps(results))
        return results

    async def serveCommander(self, msgQueue):
        self.showMsg("starting servePlatoons")
        heartbeat = 0
        while True:
            heartbeat = heartbeat + 1
            if heartbeat > 255:
                heartbeat = 0

            if heartbeat%8 == 0:
                # sends a heart beat to commander
                msg = "{\"ip\": \"" + self.ip + "\", \"type\":\"heartbeat\", \"content\":\"Stayin Alive\"}"
                # send to commander
                self.commanderXport.write(msg.encode('utf8'))

            if not msgQueue.empty():
                net_message = await msgQueue.get()
                print("From Commander, recevied queued net message:", net_message)
                self.processCommanderMsgs(net_message)
                msgQueue.task_done()

            await asyncio.sleep(1)

    # '{"cmd":"reqStatusUpdate", "missions":"all"}'
    # content format varies according to type.
    def processCommanderMsgs(self, msgString):
        self.showMsg("received from commander: "+msgString)
        if "!connection!" in msgString:
            msg = {"cmd": "connection"}
        elif "!net loss" in msgString:
            msg = {"cmd": "net loss"}
        else:
            msg_parts = msgString.split("!")
            msg_data = "".join(msg_parts[2:])
            msg = json.loads(msg_data)
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
        elif msg["cmd"] == "reqSendFile":
            # update vehicle status display.
            self.showMsg("received a file: "+msg["file_name"])
            file_name = msg["file_name"]
            file_type = msg["file_type"]
            file_contents = msg["file_contents"].encode('latin1')  # Encode string to binary data
            with open(file_name, 'wb') as file:
                file.write(file_contents)

            # first check if the missions are completed or being run or not, if so nothing could be done.
            # otherwise, simply update the mission status to be "Cancelled"
        elif msg["cmd"] == "reqCancelMissions":
            # update vehicle status display.
            self.showMsg(msg["content"])
            # first check if the missions are completed or being run or not, if so nothing could be done.
            # otherwise, simply update the mission status to be "Cancelled"
        elif msg["cmd"] == "reqSetSchedule":
            # schedule work now..... append to array data structure and set up the pointer to the 1st task.
            # the actual running of the tasks will be taken care of by the schduler.
            localworks = msg["todos"]
            self.addBotsMissionsSkillsFromCommander(msg["bots"], msg["missions"], msg["skills"])
            self.showMsg("received work request:"+json.dumps(localworks))
            # send work into work Queue which is the self.todays_work["tbd"] data structure.

            self.todays_work["tbd"].append({"name": "automation", "works": localworks, "status": "yet to start", "current widx": 0, "completed": [], "aborted": []})
            self.showMsg("after assigned work, "+str(len(self.todays_work["tbd"]))+" todos exists in the queue. "+json.dumps(self.todays_work["tbd"]))

            platform_os = self.platform            # win, mac or linux
            self.todays_scheduled_task_groups[platform_os] = localworks
            self.unassigned_task_groups[platform_os] = localworks

            # clean up the reports on this vehicle....
            self.todaysReports = []
            self.DONE_WITH_TODAY = False

        elif msg["cmd"] == "reqCancelAllMissions":
            # update vehicle status display.
            self.showMsg(json.dumps(msg["content"]))
            self.sendRPAMessage(msg_data)
        elif msg["cmd"] == "reqHaltMissions":
            # update vehicle status display.
            self.showMsg(json.dumps(msg["content"]))
            self.sendRPAMessage(msg_data)
            # simply change the mission's status to be "Halted" again, this will make task runner to run this mission
        elif msg["cmd"] == "reqResumeMissions":
            # update vehicle status display.
            self.showMsg(json.dumps(msg["content"]))
            self.sendRPAMessage(msg_data)
            # simply change the mission's status to be "Scheduled" again, this will make task runner to run this mission
        elif msg["cmd"] == "reqAddMissions":
            # update vehicle status display.
            self.showMsg(json.dumps(msg["content"]))
            # this is for manual generated missions, simply added to the todo list.
        elif msg["cmd"] == "ping":
            # respond to ping with pong
            self_info = {"name": platform.node(), "os": platform.system(), "machine": platform.machine()}
            resp = {"ip": self.ip, "type":"pong", "content": self_info}
            # send to commander
            self.commanderXport.write(json.dumps(resp).encode('utf8'))
        elif msg["cmd"] == "chat":
            # update vehicle status display.
            self.showMsg(json.dumps(msg))
            # this message is a chat to a bot/bot group, so forward it to the bot(s)
            # first, find out the bot's queue(which is kind of a temp mailbox for the bot and drop it there)
            self.receiveBotChatMessage(msg["message"])



    def sendRPAMessage(self, msg_data):
        asyncio.create_task(self.gui_rpa_msg_queue.put(msg_data))


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

        # self.showMsg("GEN REPORT FOR WORKS:"+json.dumps(works))
        if not self.hostrole == "CommanderOnly":
            mission_report = {"mid": current_mid, "bid": current_bid, "starttime": last_start, "endtime": last_end, "status": run_status}
            self.showMsg("mission_report:"+json.dumps(mission_report))

            if self.hostrole != "Platoon":
                # add generated report to report list....
                self.showMsg("commander gen run report....."+str(len(self.todaysReport)) + str(len(works)))
                self.todaysReport.append(mission_report)
                # once all of today's task created a report, put the collection of reports into todaysPlatoonReports.
                # on commander machine, todaysPlatoonReports contains a collection of reports from each host machine
                if len(self.todaysReport) == len(works):
                    self.showMsg("time to pack today's non-platoon report")
                    rpt = {"ip": self.ip, "type": "report", "content": self.todaysReport}
                    self.todaysPlatoonReports.append(rpt)
                    self.todaysReport = []
            else:
                # self.todaysPlatoonReports.append(str.encode(json.dumps(rpt)))
                # self.showMsg("platoon?? gen run report....."+json.dumps(self.todaysReport))
                self.todaysReport.append(mission_report)
                # once all of today's task created a report, put the collection of reports into todaysPlatoonReports.
                # on platoon machine, todaysPlatoonReports contains a collection of individual task reports on this machine.
                if len(self.todaysReport) == len(works):
                    self.showMsg("time to pack today's platoon report")
                    rpt = {"ip": self.ip, "type": "report", "content": self.todaysReport}
                    self.todaysPlatoonReports.append(rpt)
                    self.todaysReport = []

        self.showMsg("GEN REPORT FOR WORKS..."+json.dumps(self.todaysReport))
        return self.todaysReport

    def updateMissionsStatsFromReports(self, all_reports):
        for rpt in all_reports:
            found = next((x for x in self.missions if x.getMid() == rpt["mid"]), None)
            if found:
                found.setStatus(rpt["status"])
                found.setActualStartTime(rpt["starttime"])
                found.setActualEndTime(rpt["endtime"])

    # all work done today, now
    # 1) send report to the network,
    # 2) save report to local logs,
    # 3) clear today's work data structures.
    #
    def doneWithToday(self):
        global commanderXport
        # call reportStatus API to send today's report to API
        self.showMsg("Done with today!")

        if not self.DONE_WITH_TODAY:
            self.DONE_WITH_TODAY = True
            self.rpa_work_assigned_for_today = False

            if not self.hostrole == "Platoon":
                # if self.hostrole == "Commander":
                #     self.showMsg("commander generate today's report")
                #     rpt = {"ip": self.ip, "type": "report", "content": self.todaysReports}
                #     self.todaysPlatoonReports.append(rpt)

                if len(self.todaysPlatoonReports) > 0:
                    # flatten the report data structure...
                    allTodoReports = [item for pr in self.todaysPlatoonReports for item in pr["content"]]
                    self.showMsg("ALLTODOREPORTS:"+json.dumps(allTodoReports))
                    # missionReports = [item for pr in allTodoReports for item in pr]
                else:
                    missionReports = []

                self.updateMissionsStatsFromReports(allTodoReports)

                self.showMsg("TO be sent to cloud side::"+json.dumps(allTodoReports))
                # if this is a commmander, then send report to cloud
                # send_completion_status_to_cloud(self.session, allTodoReports, self.tokens['AuthenticationResult']['IdToken'])
            else:
                # if this is a platoon, send report to commander today's report is just an list mission status....
                if len(self.todaysReports) > 0:
                    rpt = {"ip": self.ip, "type": "report", "content": self.todaysReports}
                    self.showMsg("Sending report to Commander::"+json.dumps(rpt))
                    self.commanderXport.write(str.encode(json.dumps(rpt)))

            # 2) log reports on local drive.
            self.saveDailyRunReport(self.todaysPlatoonReports)

            # 3) clear data structure, set up for tomorrow morning, this is the case only if this is a commander
            if not self.hostrole == "Platoon":
                self.todays_work = {"tbd": [
                    {"name": "fetch schedule", "works": self.gen_default_fetch(), "status": "yet to start",
                     "current widx": 0, "completed": [], "aborted": []}]}
                self.bot_service.update_bots_batch(self.missions)

            self.todays_completed = []
            self.todaysReports = []                     # per vehicle/host
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
        FETCH_ROUTINE = [{
                    "mid": 0,
                    "bid": 0,
                    "name": "fetch schedules",
                    "cuspas": "",
                    "todos": None,
                    "start_time": START_TIME,
                    "end_time": "",
                    "stat": "nys"
                }]

        return FETCH_ROUTINE


    def closeEvent(self, event):
        self.showMsg('Main window close....')
        for task in (self.peer_task, self.monitor_task, self.chat_task, self.rpa_task):
            if not task.done():
                task.cancel()
        if self.loginout_gui:
            self.loginout_gui.show()
        event.accept()

    def createTrialRunMission(self):
        trMission = EBMISSION(self)
        trMission.setMid(20231225)
        trMission.pubAttributes.setType("user", "Sell")
        trMission.pubAttributes.setBot(0)
        trMission.setCusPAS("win,chrome,amz")
        self.missions.append(trMission)

        return trMission

    def addSkillToTrialRunMission(self, skid):
        found = False
        for m in self.missions:
            if m.getMid() == 20231225:
                found = True
                break
        if found:
            m.setSkills([skid])

    def getTrialRunMission(self):
        found = False
        for m in self.missions:
            if m.getMid() == 20231225:
                found = True
                break
        if found:
            return m
        else:
            return None

    def searchLocalMissions(self):
        self.showMsg("Searching local missions based on createdon date range and field parameters....")
        data = self.mission_service.find_missions_by_search(self.mission_from_date_edit.text(), self.mission_to_date_edit.text(),self.mission_search_edit.text())
        self.loadLocalMissions(data)

    def searchLocalBots(self):
        self.showMsg("Searching local bots based on createdon date range and field parameters....")
        data = self.bot_service.find_bots_by_search(self.bot_from_date_edit.text(),
                                                          self.bot_to_date_edit.text(),
                                                          self.bot_search_edit.text())
        self.loadLocalBots(data)


    # build up a dictionary of bot - to be visited site list required by today's mission.
    # this list will be used to filter out cookies of unrelated site, otherwise the
    # naturally saved cookie file by ADS will be too large to fit into an xlsx cell.
    # and the ADS profile import only access xlsx file format.
    def build_cookie_site_lists(self):
        today = datetime.today()
        formatted_today = today.strftime('%Y-%m-%d')
        # first, filter out today's missions by createon parameter.
        for m in self.missions:
            self.showMsg("mission" + str(m.getMid()) + " created ON:" + m.getBD().split(" ")[0] + " today:" + formatted_today)
        missions_today = list(filter(lambda m: formatted_today == m.getBD().split(" ")[0], self.missions))
        # first ,clear today's bot cookie site list dictionary
        self.bot_cookie_site_lists = {}
        for mission in missions_today:
            bots = [b for b in self.bots if b.getBid() == mission.getBid()]
            if len(bots) > 0:
                bot = bots[0]
                if bot.getEmail() == "":
                    self.showMsg("Error: Bot("+str(bot.getBid())+") running ADS without an Account!!!!!")
                else:
                    user_prefix = bot.getEmail().split("@")[0]
                    mail_site_words = bot.getEmail().split("@")[1].split(".")
                    mail_site = mail_site_words[len(mail_site_words) - 2]
                    bot_mission_ads_profile = user_prefix+"_m"+str(mission.getMid()) + ".txt"

                    self.bot_cookie_site_lists[bot_mission_ads_profile] = [mail_site]
                    if mail_site == "gmail":
                        self.bot_cookie_site_lists[bot_mission_ads_profile].append("google")

                    if mission.getSite() == "amz":
                        self.bot_cookie_site_lists[bot_mission_ads_profile].append("amazon")
                    elif mission.getSite() == "ali":
                        self.bot_cookie_site_lists[bot_mission_ads_profile].append("aliexpress")
                    else:
                        self.bot_cookie_site_lists[bot_mission_ads_profile].append(mission.getSite().lower())

        self.showMsg("just build cookie site list:"+json.dumps(self.bot_cookie_site_lists))


    def setADSBatchSize(self, batch_size):
        self.ads_settings["batch_size"] = batch_size

    def getADSBatchSize(self):
        return self.ads_settings["batch_size"]

    def getIP(self):
        return self.ip

    def getCookieSiteLists(self):
        return self.bot_cookie_site_lists

    def getADSProfileDir(self):
        return self.ads_profile_dir

    def send_chat_to_local_bot(self, chat_msg):
        # """ Directly enqueue a message to the asyncio task when the button is clicked. """
        asyncio.create_task(self.gui_chat_msg_queue.put(chat_msg))

    # the message will be in the format of botid:send time stamp in yyyy:mm:dd hh:mm:ss format:msg in html format
    # from network the message will have chatmsg: prepend to the message.
    def update_chat_gui(self, rcvd_msg):
        self.chatWin.updateDisplay(rcvd_msg)

    # this is the interface to the chatting bots, taking message from the running bots and display them on GUI
    async def connectChat(self, chat_msg_queue):
        running = True
        while running:
            if not chat_msg_queue.empty():
                message = await chat_msg_queue.get()
                self.showMsg(f"Rx Chat message from bot: {message}")
                self.update_chat_gui(message)
                chat_msg_queue.task_done()

            # print("polling chat msg queue....")
            await asyncio.sleep(1)


    # this is the interface to the chatting bots, taking message from the running bots and display them on GUI
    async def runRPAMonitor(self, monitor_msg_queue):
        running = True
        ticks = 0
        while running:
            ticks = ticks + 1
            if ticks > 255:
                ticks = 0

            #ping cloud every 8 second to see whether there is any monitor/control internet. use amazon's sqs
            if ticks % 8 == 0:
                self.showMsg(f"Access Internet Here with Websocket...")


            if not monitor_msg_queue.empty():
                message = await monitor_msg_queue.get()
                self.showMsg(f"RPA Monitor message: {message}")
                self.update_moitor_gui(message)
                monitor_msg_queue.task_done()

            # print("polling chat msg queue....")
            await asyncio.sleep(1)


    def update_moitor_gui(self, in_message):
        self.showMsg(f"RPA Monitor:"+in_message)

    # note recipient could be a group ID.
    def sendBotChatMessage(self, sender, recipient, text):
        # first find out where the recipient is at (which vehicle) and then, send the message to it.
        if isinstance(recipient, list):
            recipients = recipient
        else:
            recipients = [recipient]
        dtnow = datetime.now()
        date_word = dtnow.isoformat()
        allbids = [b.getBid() for b in self.bots]
        found = None
        for vidx, v in enumerate(self.vehicles):
            if len(recipients) > 0:
                receivers = set(recipients)
                vbots = set(v.getBotIds())

                # Find the intersection
                intersection = receivers.intersection(vbots)

                # Convert intersection back to a list (optional)
                bids_on_this_vehicle = list(intersection)
                if len(bids_on_this_vehicle) > 0:
                    bids_on_this_vehicle_string = ",".join(bids_on_this_vehicle)

                    #now send the message to bots on this vehicle.
                    full_txt = date_word + ">" + str(sender) + ">" + bids_on_this_vehicle_string + ">" + text
                    cmd = {"cmd": "chat", "message": full_txt.decode('latin1')}
                    cmd_str = json.dumps(cmd)
                    v.getFieldLink()["transport"].write(cmd_str.encode('utf8'))

                    # Remove the intersection from the recipients.
                    receivers.difference_update(intersection)

                    # get updated recipients
                    recipients = list(receivers)

        # if there are still recipients not sent, that means these are local bots,
        #self.send_chat_to_local_bot(text)

        if len(recipient) > 0:
            # recipient here could be comma seperated recipient ids.
            receivers = set(recipients)
            vbots = set(allbids)

            # Find the intersection
            intersection = receivers.intersection(vbots)

            # Convert intersection back to a list (optional)
            bids_on_this_vehicle = list(intersection)

            self.chatWin.addActiveChatHis(self, False, bids_on_this_vehicle, full_txt)

            if len(bids_on_this_vehicle) > 0:
                # now send the message to local bots on this vehicle.
                unfound_bid_string = ",".join(bids_on_this_vehicle)
                self.showMsg(f"Error: Bot[{unfound_bid_string}] not found")


    # note recipient could be a group ID.
    def receiveBotChatMessage(self, msg_text):
        msg_parts = msg_text.split(">")
        sender = msg_parts[1]
        receiver = msg_parts[2]
        if "," in receiver:
            receivers = [int(rs.strip()) for rs in receiver.split(",")]
        else:
            receivers = [int(receiver.strip())]

        # if 0 in receivers:
        #     # deliver the message for the commander chief - i.e. the user. which has id 0
        #     zidx = receivers.index(0)  # Get the index of the first 0
        #     receivers.pop(zidx)

        # deliver the message for the other bots. - allowed for inter-bot communication.
        if len(receivers) > 0:
            # now route message to everybody.
            self.chatWin.addNetChatHis(sender, receivers, msg_text)

    # note recipient could be a group ID.
    def receiveBotLogMessage(self, msg_text):
        msg_json = json.loads(msg_text)

        sender = msg_json["sender"]

        #logger will only be sent to the boss.
        receivers = [0]

        # deliver the message for the other bots. - allowed for inter-bot communication.
        self.chatWin.addNetChatHis(sender, receivers, msg_json["log_msg"])


    def send_file_to_platoon(self, platoon_link, file_type, file_name_full_path):
        if os.path.exists(file_name_full_path) and platoon_link:
            self.showMsg(f"Sending File [{file_name_full_path}] to platoon: "+platoon_link["ip"][0])
            with open(file_name_full_path, 'rb') as fileTBSent:
                binary_data = fileTBSent.read()
                encoded_data = base64.b64encode(binary_data).decode('utf-8')

                # Embed in JSON
                json_data = json.dumps({"cmd": "reqSendFile", "file_name": file_name_full_path, "file_type": file_type, "file_contents": encoded_data})
                length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                # Send data
                platoon_link["transport"].write(length_prefix+json_data.encode('utf-8'))
                # await xport.drain()

                fileTBSent.close()
        else:
            if not os.path.exists(file_name_full_path):
                self.showMsg(f"Error: File [{file_name_full_path}] not found")
            else:
                self.showMsg(f"Error: TCP link doesn't exist")

    def send_json_to_platoon(self, platoon_link, json_data):
        if json_data and platoon_link:
            self.showMsg(f"Sending JSON Data to platoon "+platoon_link["ip"][0] + "::" + json.dumps(json_data))
            json_string = json.dumps(json_data)
            encoded_json_string = json_string.encode('utf-8')
            length_prefix = len(encoded_json_string).to_bytes(4, byteorder='big')
            # Send data
            platoon_link["transport"].write(length_prefix+encoded_json_string)
        else:
            if json_data == None:
                self.showMsg(f"Error: JSON empty")
            else:
                self.showMsg(f"Error: TCP link doesn't exist")


    def getEncryptKey(self):
        key, salt = derive_key(self.main_key)
        return key