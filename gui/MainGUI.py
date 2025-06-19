import ast
import json

from common.models import VehicleModel
from utils.server import HttpServer
from utils.time_util import TimeUtil
from gui.LocalServer import start_local_server_in_thread, create_mcp_client

print(TimeUtil.formatted_now_with_ms() + " load MainGui start...")
import asyncio

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.fernet import Fernet
import hashlib
import base64

import copy
import math
import os.path
import random
import traceback
import webbrowser
from _csv import reader
from os.path import exists
import glob
import threading

from PySide6.QtCore import QThreadPool, QParallelAnimationGroup, Qt, QPropertyAnimation, QAbstractAnimation, QEvent, QSize
from PySide6.QtGui import QFont, QIcon, QAction, QStandardItemModel, QTextCursor
from PySide6.QtWidgets import QMenuBar, QWidget, QScrollArea, QFrame, QToolButton, QGridLayout, QSizePolicy, \
    QApplication, QVBoxLayout, QPushButton, QLabel, QLineEdit, QHBoxLayout, QListView, QSplitter, QMainWindow, QMenu, \
    QMessageBox, QFileDialog, QPlainTextEdit, QDialog

import importlib
import importlib.util
from common.models import BotModel, MissionModel
from common.db_init import init_db, get_session
from common.services import MissionService, ProductService, SkillService, BotService, VehicleService
from tests.TestAll import Tester

from gui.BotGUI import BotNewWin
from bot.Cloud import set_up_cloud, upload_file, send_add_missions_request_to_cloud, \
    send_remove_missions_request_to_cloud, send_update_missions_request_to_cloud, send_add_bots_request_to_cloud, \
    send_update_bots_request_to_cloud, send_remove_bots_request_to_cloud, send_add_skills_request_to_cloud, \
    send_get_bots_request_to_cloud, send_query_chat_request_to_cloud, download_file, send_report_vehicles_to_cloud,\
    send_update_vehicles_request_to_cloud

from gui.FlowLayout import BotListView, MissionListView, DragPanel
from gui.LoggerGUI import CommanderLogWin
from bot.Logger import LOG_SWITCH_BOARD, log3
from gui.MissionGUI import MissionNewWin
from gui.PlatoonGUI import PlatoonListView, PlatoonWindow
from gui.ScheduleGUI import ScheduleWin
from gui.SkillManagerGUI import SkillManagerWindow
from gui.TrainGUI import TrainNewWin, ReminderWin
from gui.VehicleMonitorGUI import VehicleMonitorWin
from bot.WorkSkill import WORKSKILL
from bot.adsPowerSkill import formADSProfileBatchesFor1Vehicle, convertTxtProfiles2DefaultXlsxProfiles, updateIndividualProfileFromBatchSavedTxt, genAdsProfileBatchs
from bot.basicSkill import symTab, STEP_GAP, setMissionInput, unzip_file, list_zip_file, getScreenSize
from bot.envi import getECBotDataHome
from bot.genSkills import genSkillCode, getWorkRunSettings, setWorkSettingsSkill, SkillGeneratorTable, ManagerTriggerTable
from bot.inventories import INVENTORY
from bot.wanChat import subscribeToWanChat, wanHandleRxMessage, wanSendMessage, wanSendMessage8, parseCommandString
from lzstring import LZString
import openpyxl
import tzlocal
from datetime import timedelta
import platform
from pynput.mouse import Controller
from PySide6.QtWebEngineWidgets import QWebEngineView

from bot.network import myname, fieldLinks, commanderIP, commanderXport, runCommanderLAN, runPlatoonLAN
from bot.readSkill import RAIS, ARAIS, first_step, get_printable_datetime, readPSkillFile, addNameSpaceToAddress, running, running_step_index
from gui.ui_settings import SettingsWidget
from bot.vehicles import VEHICLE
from gui.tool.MainGUITool import FileResource, StaticResource
from utils.logger_helper import logger_helper
from tests.unittests import *
from tests.agent_tests import *
import pandas as pd
from gui.encrypt import *
import keyboard
from bot.labelSkill import handleExtLabelGenResults, setLabelsReady
import cpuinfo
import psutil
from gui.BrowserGUI import BrowserWindow
from config.constants import API_DEV_MODE
from langchain_openai import ChatOpenAI
from agent.ec_agent import EC_Agent
from agent.runner.service import Runner
from agent.ec_skills.build_skills import build_agent_skills
from agent.ec_skill import *
from agent.mcp.server.tool_schemas import build_agent_mcp_tools_schemas
from agent.mcp.server.server import set_server_main_win
from agent.ec_agents.build_agents import *




print(TimeUtil.formatted_now_with_ms() + " load MainGui finished...")

START_TIME = 15      # 15 x 20 minute = 5 o'clock in the morning

Tzs = ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"]

rpaConfig = None

ecb_data_homepath = getECBotDataHome()

in_data_string = ""

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
    def __init__(self, loginout_gui, main_key, inTokens, mainloop, ip, user, homepath, gui_msg_queue, machine_role, schedule_mode, lang):
        super(MainWindow, self).__init__()
        self.loginout_gui = loginout_gui
        if homepath[len(homepath)-1] == "/":
            self.homepath = homepath[:len(homepath)-1]
        else:
            self.homepath = homepath
        self.gui_net_msg_queue = gui_msg_queue
        self.gui_rpa_msg_queue = asyncio.Queue()
        self.gui_manager_msg_queue = asyncio.Queue()
        self.virtual_cloud_task_queue = asyncio.Queue()
        self.gui_monitor_msg_queue = asyncio.Queue()
        self.lang = lang
        self.tz = self.obtainTZ()
        self.file_resource = FileResource(self.homepath)
        self.top_gui = None
        self.DONE_WITH_TODAY = True
        self.gui_chat_msg_queue = asyncio.Queue()
        self.wan_chat_msg_queue = asyncio.Queue()
        self.static_resource = StaticResource()
        self.all_ads_profiles_xls = "C:/AmazonSeller/SelfSwipe/test_all.xls"
        self.session = set_up_cloud()
        self.mainLoop = mainloop
        self.tokens = inTokens
        self.machine_role = machine_role
        if "Platoon" in self.machine_role:
            self.functions = "buyer,seller"
        elif "Commander" in self.machine_role:
            self.functions = "manager,hr,it"
        else:
            self.functions = ""

        self.todaysSchedule = {}
        self.schedule_mode = schedule_mode
        self.ip = ip
        self.main_key = main_key
        self.user = user
        self.chat_id = user.split("@")[0] + "_" + user.split("@")[1].replace(".", "_")
        self.log_user = self.chat_id
        self.my_ecb_data_homepath = f"{ecb_data_homepath}/{self.log_user}"
        if not os.path.exists(f"{self.my_ecb_data_homepath}/resource/data/"):
            os.makedirs(f"{self.my_ecb_data_homepath}/resource/data/")
        self.cog = None
        self.cog_client = None
        self.VEHICLES_FILE = self.my_ecb_data_homepath + "/vehicles.json"
        self.host_role = machine_role
        self.screen_size = getScreenSize()
        self.display_resolution = "D"+str(self.screen_size[0])+"X"+str(self.screen_size[1])
        if "Only" in self.host_role:
            self.chat_id = self.chat_id + "_Commander"
        else:
            self.chat_id = self.chat_id+"_"+"".join(self.host_role.split())
        print("my chatId:", self.chat_id)
        self.staff_officer_on_line = False
        self.working_state = "running_idle"
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]
        system = platform.system()
        release = platform.release()
        version = platform.version()
        architecture = platform.architecture()[0]
        self.os_info = f"{system} {release} ({architecture}), Version: {version}"

        self.platform = platform.system().lower()[0:3]
        self.cpuinfo = cpuinfo.get_cpu_info()
        self.processor = self.cpuinfo.get('brand_raw', 'Unknown Processor')
        self.cpu_cores = psutil.cpu_count(logical=False)  # Physical cores
        self.cpu_threads = psutil.cpu_count(logical=True)  # Logical cores (including hyper-threading)
        self.cpu_speed = self.cpuinfo.get('hz_advertised_friendly', 'Unknown Speed')

        # Memory Information
        self.virtual_memory = psutil.virtual_memory()
        self.total_memory = self.virtual_memory.total / (1024 ** 3)  # Convert bytes to GB

        self.std_item_font = QFont('Arial', 10)

        self.sellerInventoryJsonData = None
        self.botJsonData = None
        self.inventories = []

        self.bot_cookie_site_lists = {}
        self.ads_profile_dir = self.my_ecb_data_homepath + "/ads_profiles/"
        if not os.path.exists(self.ads_profile_dir):
            os.makedirs(self.ads_profile_dir)

        self.ads_settings_file = self.ads_profile_dir + "ads_settings.json"
        self.ads_settings = {"user name": "", "user pwd": "", "batch_size": 2, "batch_method": "min batches", "ads_port": 0, "ads_api_key": ""}
        self.bot_states = ["active", "disabled", "banned", "deleted"]
        self.todays_bot_profiles = []
        # self.readBotJsonFile()
        self.vehicles = []                              # computers on LAN that can carry out bots's tasks.， basically tcp transports

        self.bots = []
        self.missions = []                              # mission 0 will always default to be the fetch schedule mission
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
        self.newGui = BrowserWindow(self)

        self.trainNewSkillWin = None
        self.reminderWin = None
        self.platoonWin = None
        self.botsFingerPrintsReady = False
        self.default_webdriver_path = f"{self.homepath}/chromedriver-win64/chromedriver.exe"
        self.default_webdriver = None
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

        self.netLogWin = CommanderLogWin(self)
        self.machine_name = myname
        self.commander_name = ""
        self.system = platform.system()
        if self.system == "Windows":
            self.os_short = "win"
        elif self.system == "Linux":
            self.os_short = "linux"
        elif self.system == "Darwin":
            self.os_short = "mac"

        self.todaysReport = []              # per task group. (inside this report, there are list of individual task/mission result report.
        self.todaysReports = []             # per vehicle/host
        self.todaysPlatoonReports = []
        self.tester = Tester()
        self.wifis = []

        if not os.path.exists(f"{self.my_ecb_data_homepath}/resource/data/"):
            os.makedirs(f"{self.my_ecb_data_homepath}/resource/data/")

        self.dbfile = f"{self.my_ecb_data_homepath}/resource/data/myecb.db"
        self.product_catelog_file = f"{self.my_ecb_data_homepath}/resource/data/product_catelog.json"
        self.general_settings_file = f"{self.my_ecb_data_homepath}/resource/data/settings.json"
        self.log_settings_file = f"{self.my_ecb_data_homepath}/resource/data/log_settings.json"
        self.buy_search_settings_file =  f"{self.my_ecb_data_homepath}/resource/data/search_settings.json"
        self.general_settings = {}
        self.debug_mode = True
        self.fetch_schedule_counter = 1
        self.readSellerInventoryJsonFile("")

        self.showMsg("main window ip:" + self.ip)
        if "Commander" in self.machine_role:
            self.tcpServer = None
            self.commanderXport = None
            self.commander_name = self.machine_name
        elif self.machine_role == "Platoon":
            self.showMsg("This is a platoon...")
            self.commanderXport = None
            self.commanderIP = commanderIP
            self.tcpServer = None

        if os.path.exists(self.log_settings_file):
            with open(self.log_settings_file, 'r', encoding='utf-8') as log_settings_f:
                self.log_settings = json.load(log_settings_f)
        else:
            self.log_settings = {}

        if os.path.exists(self.buy_search_settings_file):
            print("buy_serach_settings_file:", self.buy_search_settings_file)
            with open(self.buy_search_settings_file, 'r', encoding='utf-8') as buy_search_settings_f:
                self.buy_search_settings = json.load(buy_search_settings_f)
        else:
            self.buy_search_settings = {}


        if os.path.exists(self.general_settings_file):
            with open(self.general_settings_file, 'r', encoding='utf-8') as gen_settings_f:
                self.general_settings = json.load(gen_settings_f)

                self.debug_mode = self.general_settings.get("debug_mode", False)
                self.schedule_mode = self.general_settings.get("schedule_mode", "auto")
                self.default_wifi = self.general_settings.get("default_wifi", "")
                self.default_printer = self.general_settings.get("default_printer", "")
                self.display_resolution = self.general_settings.get("display_resolution", "")
                self.default_webdriver_path = self.general_settings.get("default_webdriver_path", "")
                self.build_dom_tree_script_path = self.general_settings.get("build_dom_tree_script_path", "")

                self.new_orders_dir = self.general_settings.get("new_orders_dir", "c:/ding_dan/")
                self.local_user_db_server = self.general_settings.get("localUserDB_host", "127.0.0.1")
                self.local_user_db_port = self.general_settings.get("localUserDB_port", "5080")
                self.local_agent_db_server = self.general_settings.get("localAgentDB_host", "192.168.0.16")
                self.local_agent_db_port = self.general_settings.get("localAgentDB_port", "6668")
                self.lan_api_endpoint = self.general_settings.get("lan_api_endpoint", "")
                self.wan_api_endpoint = self.general_settings.get("wan_api_endpoint", "")
                self.ws_api_endpoint = self.general_settings.get("ws_api_endpoint", "")
                self.img_engine = self.general_settings.get("img_engine", "lan")
                self.schedule_engine = self.general_settings.get("schedule_engine", "wan")
                self.local_agents_port_range = self.general_settings.get("localAgent_ports", [3600, 3800])



        self.showMsg("loaded general settings:" + json.dumps(self.general_settings))
        self.showMsg("Debug Mode:" + str(self.debug_mode) + " Schedule Mode:" + str(self.schedule_mode))
        self.showMsg("self.platform==================================================>" + self.platform)
        if os.path.exists(self.ads_settings_file):
            with open(self.ads_settings_file, 'r') as ads_settings_f:
                self.ads_settings = json.load(ads_settings_f)
                if "ads_profile_dir" in self.ads_settings:
                    if self.ads_settings["ads_profile_dir"]:
                        self.ads_profile_dir = self.ads_settings["ads_profile_dir"]

            ads_settings_f.close()
        self.showMsg("ADS SETTINGS:"+json.dumps(self.ads_settings))
        self.showMsg("=========Done With Network Setup, Start Local DB Setup =========")
        self.showMsg("HOME PATH is::" + self.homepath, "info")
        self.showMsg(self.dbfile)
        if "Commander" in self.machine_role:
            engine = init_db(self.dbfile)
            session = get_session(engine)
            self.bot_service = BotService(self, session)
            self.mission_service = MissionService(self, session)
            self.product_service = ProductService(self, session)
            self.skill_service = SkillService(self, session)
            self.vehicle_service = VehicleService(self, session)
        else:
            self.bot_service = None
            self.mission_service = None
            self.product_service = None
            self.skill_service = None
            self.vehicle_service = None


        self.owner = "NA"
        self.botRank = "soldier"  # this should be read from a file which is written during installation phase, user will select this during installation phase
        self.rpa_work_assigned_for_today = False
        self.showMsg("=========Done With Local DB Setup, Start GUI Setup =========")
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
        self.syncBotAccountsAction = self._syncBotAccountsAction()

        self.missionNewAction = self._createMissionNewAction()
        self.missionDelAction = self._createMissionDelAction()
        self.missionEditAction = self._createMissionEditAction()
        self.missionImportAction = self._createMissionImportAction()

        self.settingsAccountAction = self._createSettingsAccountAction()
        self.settingsEditAction = self._createSettingsEditAction()

        self.runRunLocalWorksAction = self._createRunLocalWorkAction()
        self.runRunAllAction = self._createRunRunAllAction()
        self.runTestAllAction = self._createRunTestAllAction()

        self.scheduleCalendarViewAction = self._createScheduleCalendarViewAction()
        self.fetchScheduleAction = self._createFetchScheduleAction()

        self.rescheduleAction = self._createRescheduleAction()
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

        self.toolsADSProfileConverterAction = self._createToolsADSProfileConverterAction()
        self.toolsADSProfileBatchToSinglesAction = self._createToolsADSProfileBatchToSinglesAction()
        self.toolsWanChatTestAction = self._createToolsWanChatTestAction()
        self.toolsStopWaitUntilTestAction = self._createToolsStopWaitUntilTestAction()
        self.toolsSimWanRequestAction = self._createToolsSimWanRequestAction()
        self.toolsSyncFingerPrintRequestAction = self._createToolsSyncFingerPrintRequestAction()
        self.toolsDailyHousekeepingAction = self._createToolsDailyHousekeepingAction()
        self.toolsDailyTeamPrepAction = self._createToolsDailyTeamPrepAction()
        self.toolsGatherFingerPrintsRequestAction = self._createToolsGatherFingerPrintsRequestAction()

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
        self.running_mission = None

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
        self.botListView.setSelectionMode(QListView.ExtendedSelection)
        self.botListView.setSelectionBehavior(QListView.SelectRows)

        # self.skillListView.setModel(self.skillModel)
        # self.skillListView.setViewMode(QListView.IconMode)
        # self.skillListView.setMovement(QListView.Snap)

        # self.mission0 = EBMISSION(self)
        # self.missionModel.appendRow(self.mission0)
        # self.missions.append(self.mission0)

        self.missionListView.setModel(self.missionModel)
        self.missionListView.setViewMode(QListView.ListMode)
        self.missionListView.setMovement(QListView.Snap)
        # self.missionListView.setSelectionMode(QListView.MultiSelection)
        self.missionListView.setSelectionMode(QListView.ExtendedSelection)
        self.missionListView.setSelectionBehavior(QListView.SelectRows)

        self.running_missionListView.setModel(self.runningMissionModel)
        self.running_missionListView.setViewMode(QListView.ListMode)
        self.running_missionListView.setMovement(QListView.Snap)
        self.running_missionListView.setSelectionMode(QListView.ExtendedSelection)
        self.running_missionListView.setSelectionBehavior(QListView.SelectRows)

        self.vehicleListView.setModel(self.runningVehicleModel)
        self.vehicleListView.setViewMode(QListView.ListMode)
        self.vehicleListView.setIconSize(QSize(48, 48))
        self.vehicleListView.setMovement(QListView.Snap)
        self.vehicleListView.setSelectionMode(QListView.ExtendedSelection)
        self.vehicleListView.setSelectionBehavior(QListView.SelectRows)


        self.completed_missionListView.setModel(self.completedMissionModel)
        self.completed_missionListView.setViewMode(QListView.ListMode)
        self.completed_missionListView.setMovement(QListView.Snap)
        self.completed_missionListView.setSelectionMode(QListView.ExtendedSelection)
        self.completed_missionListView.setSelectionBehavior(QListView.SelectRows)

        centralWidget = DragPanel()

        if "Commander" not in self.machine_role:
            self.botNewAction.setDisabled(True)
            self.saveAllAction.setDisabled(True)
            self.botDelAction.setDisabled(True)
            self.botEditAction.setDisabled(True)
            self.botCloneAction.setDisabled(True)
            self.botNewFromFileAction.setDisabled(True)
            self.syncBotAccountsAction.setDisabled(True)

            self.missionNewAction.setDisabled(True)
            self.missionDelAction.setDisabled(True)
            self.missionEditAction.setDisabled(True)
            self.missionImportAction.setDisabled(True)

            self.skillNewAction.setDisabled(True)
            self.skillDeleteAction.setDisabled(True)
            self.skillShowAction.setDisabled(True)
            self.skillUploadAction.setDisabled(True)

            self.skillNewFromFileAction.setDisabled(True)

        # server = HttpServer(self, self.session, self.tokens['AuthenticationResult']['IdToken'])
        # self.server_port = server.port

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

        self.rpa_quit_dialog = QDialog(self)
        self.rpa_quit_dialog.setWindowTitle(QApplication.translate("QDialog", "Quit RPA Confirmation"))
        self.rpa_quit_dialog_layout = QHBoxLayout()

        self.rpa_quit_label = QLabel(QApplication.translate("QLabel", "Are you sure you want to quit?"))
        self.rpa_quit_dialog_layout.addWidget(self.rpa_quit_label)

        self.rpa_quit_ok_button = QPushButton("OK")
        self.rpa_quit_cancel_button = QPushButton("Cancel")

        self.rpa_quit_dialog_layout.addWidget(self.rpa_quit_ok_button)
        self.rpa_quit_dialog_layout.addWidget(self.rpa_quit_cancel_button)

        self.rpa_quit_dialog.setLayout(self.rpa_quit_dialog_layout)
        self.rpa_quit_confirmation_future = asyncio.get_event_loop().create_future()

        # finally start the network service
        # because if we don't know who the real boss is, there no point doing any networking.....
        if "Platoon" not in self.machine_role:
            print("run commander side networking......")
            self.mainLoop.create_task(runCommanderLAN(self))

        else:
            print("run platoon side networking...")
            self.mainLoop.create_task(runPlatoonLAN(self, self.mainLoop))

        def on_ok():
            self.rpa_quit_confirmation_future = loop.create_future()
            if not self.rpa_quit_confirmation_future.done():
                self.rpa_quit_confirmation_future.set_result(True)
            self.rpa_quit_dialog.close()

        def on_cancel():
            self.rpa_quit_confirmation_future = loop.create_future()
            if not self.rpa_quit_confirmation_future.done():
                self.rpa_quit_confirmation_future.set_result(False)
            self.rpa_quit_dialog.close()

        self.rpa_quit_ok_button.clicked.connect(on_ok)
        self.rpa_quit_cancel_button.clicked.connect(on_cancel)


        self.mainWidget.setLayout(layout)
        self.setCentralWidget(self.mainWidget)
        self.wan_connected = False
        self.wan_msg_subscribed = False
        self.websocket = None
        self.setWindowTitle("My E-Commerce Agents ("+self.user+") - "+self.machine_role)
        self.vehicleMonitor = VehicleMonitorWin(self)
        self.showMsg("================= DONE with GUI Setup ==============================")


        self.todays_scheduled_task_groups = {}
        self.unassigned_scheduled_task_groups = {}                # per vehicle, flatten task list
        self.unassigned_reactive_task_groups = {}  # per vehicle, flatten task list
        self.checkVehicles()

        print("Check Vehicles:", len(self.vehicles))
        for v in self.vehicles:
            print("vname:", v.getName(), "status:", v.getStatus(), )

        # get current wifi ssid and store it.
        self.showMsg("Checking Wifi on OS platform: "+self.platform)
        wifi_info = None
        if self.platform == "win":
            wifi_info = subprocess.check_output(['netsh', 'WLAN', 'show', 'interfaces'])
        elif self.platform == 'dar':
            wifi_info = subprocess.check_output(['/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport', '-I'])

        if wifi_info:
            try:
                wifi_data = wifi_info.decode('utf-8')
            except UnicodeDecodeError:
                for enc in ['utf-8', 'gbk', 'latin1']:
                    try:
                        wifi_data = wifi_info.decode(enc)
                    except UnicodeDecodeError:
                        pass
            wifi_lines = wifi_data.split("\n")
            ssidline = [l for l in wifi_lines if " SSID" in l]
            if len(ssidline) == 1:
                ssid = ssidline[0].split(":")[1].strip()
                self.wifis.append(ssid)
                self.default_wifi = self.wifis[0]
        else:
            print("***wifi info is None!")
            self.default_wifi = ""

        self.SettingsWin = SettingsWidget(self)
        self.showMsg("load local bots, mission, skills ")
        if ("Commander" in self.machine_role):
            self.readVehicleJsonFile()
            self.showMsg("Vehicle files loaded"+json.dumps(self.vehiclesJsonData))
            # load skills into memory.
            if not self.debug_mode or self.schedule_mode == "auto":
                print("getting bots from cloud....")
                self.bot_service.sync_cloud_bot_data(self.session, self.tokens, self)
                print("bot cloud done....")
            print("bot service sync cloud data")
            bots_data = self.bot_service.find_all_bots()
            print("find all bots")
            self.loadLocalBots(bots_data)
            self.showMsg("bots loaded")

            self.createNewBotsFromBotsXlsx()

            if not self.debug_mode or self.schedule_mode == "auto":
                self.mission_service.sync_cloud_mission_data(self.session, self.tokens, self)
            print("mission cloud synced")
            missions_data = self.mission_service.find_missions_by_createon()
            print("local mission data:", missions_data)
            # missions_data = []      # test hack
            self.loadLocalMissions(missions_data)
            log3("missions loaded")
            self.dailySkillsetUpdate()
            log3("skills loaded")

            # self.createNewMissionsFromOrdersXlsx()

        # Done with all UI stuff, now do the instruction set extension work.
        self.showMsg("set up rais extensions ")
        rais_extensions_file = self.my_ecb_data_homepath + "/my_rais_extensions/my_rais_extensions.json"
        rais_extensions_dir = self.my_ecb_data_homepath + "/my_rais_extensions/"
        added_handlers=[]
        print("rais extension file:"+rais_extensions_file)
        if os.path.isfile(rais_extensions_file):
            with open(rais_extensions_file, 'r') as rais_extensions:
                user_rais_modules = json.load(rais_extensions)
                print("user_rais_modules:", user_rais_modules)
                for i, user_module in enumerate(user_rais_modules):
                    module_file = self.my_ecb_data_homepath + "/" + user_module["dir"] + "/"+user_module["file"]
                    added_ins = user_module['instructions']
                    module_name = os.path.splitext(user_module["file"])[0]
                    spec = importlib.util.spec_from_file_location(module_name, module_file)
                    print("ext rais:", module_file, added_ins, module_name, spec)
                    # Create a module object from the spec
                    module = importlib.util.module_from_spec(spec)
                    # Load the module
                    spec.loader.exec_module(module)

                    for ins in added_ins:
                        if hasattr(module, ins["handler"]):
                            RAIS[ins["instruction name"]] = getattr(module, ins["handler"])
                            ARAIS[ins["instruction name"]] = getattr(module, ins["handler"])
                            print("EXTENDING ARAIS", ins["instruction name"])

        # now load experience file which will speed up icon matching
        run_experience_file = self.my_ecb_data_homepath + "/run_experience.txt"
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
        self.reactive_work = {"tbd": [], "allstat": "working"}
        self.todays_completed = []
        self.reactive_completed = []
        self.num_todays_task_groups = 0
        self.num_reactive_task_groups = 0
        if "Commander" in self.host_role:
            # For commander creates
            fetchCloudScheduledWork = {
                "name": "fetch schedule",
               "works": self.gen_default_fetch(),
               "status": "yet to start",
               "current widx": 0,
               "completed" : [],
               "aborted": []
            }
            print("debug mode:", self.debug_mode, self.schedule_mode)
            if not self.debug_mode and self.schedule_mode == "auto":
                print("add fetch schedule to todo list....")
                self.todays_work["tbd"].append(fetchCloudScheduledWork)

        # setup local web server including MCP server.
        os.environ["NO_PROXY"] = "localhost,127.0.0.1"
        set_server_main_win(self)
        start_local_server_in_thread(self)

        # async def setupAsyncTasks(self):
        self.showMsg("ready to spawn mesg server task")
        if not self.host_role == "Platoon":
            if not self.host_role == "Staff Officer":
                self.peer_task = asyncio.create_task(self.servePlatoons(self.gui_net_msg_queue))
            else:
                self.peer_task = asyncio.create_task(self.wait_forever())
                # self.peer_task = asyncio.create_task(self.monitorTroop(self.gui_net_msg_queue))
            self.wan_sub_task = asyncio.create_task(subscribeToWanChat(self, self.tokens, self.chat_id))
            # self.wan_msg_task = asyncio.create_task(wanHandleRxMessage(self))
            self.showMsg("spawned wan chat task")

        if self.host_role == "Platoon":
            self.peer_task = asyncio.create_task(self.serveCommander(self.gui_net_msg_queue))
            self.wan_sub_task = asyncio.create_task(subscribeToWanChat(self, self.tokens, self.chat_id))
            # self.wan_sub_task = asyncio.create_task(self.wait_forever())
            # self.wan_msg_task = asyncio.create_task(self.wait_forever())

        # the message queue are
        self.monitor_task = asyncio.create_task(self.runRPAMonitor(self.gui_monitor_msg_queue))
        self.showMsg("spawned RPA Monitor task")



        # self.gchat_task = asyncio.create_task(start_gradio_chat_in_background(self))
        # self.gradio_thread = threading.Thread(target=launchChat, args=(self,), daemon=True)
        # self.gradio_thread.start()

        self.showMsg("spawned runbot task")

        # the message queue are
        # asyncio.create_task(self.runbotworks(self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
        # self.showMsg("spawned runbot task")

        self.chat_task = asyncio.create_task(self.connectChat(self.gui_chat_msg_queue))
        self.showMsg("spawned chat task")

        # with ThreadPoolExecutor(max_workers=3) as self.executor:
        #     self.rpa_task_future = asyncio.wrap_future(self.executor.submit(self.runbotworks, self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
        #     self.showMsg("spawned RPA task")

        self.keyboard_task = asyncio.create_task(self.listen_for_hotkey())

        # await asyncio.gather(peer_task, monitor_task, chat_task, rpa_task_future)
        loop = asyncio.get_event_loop()
        # executor = ThreadPoolExecutor()
        # asyncio.run_coroutine_threadsafe(self.run_async_tasks(loop, executor), loop)

        asyncio.run_coroutine_threadsafe(self.run_async_tasks(), loop)

        self.saveSettings()
        print("vehicles after init:", [v.getName() for v in self.vehicles])

        # finally setup agents, note: local servers needs to be setup and running
        # before this.
        self.llm = ChatOpenAI(model='gpt-4o')
        self.agents = []
        build_agent_mcp_tools_schemas()
        print("Building agent skills.....")
        asyncio.create_task(self.async_agents_init())


    async def async_agents_init(self):
        self.mcp_client = await create_mcp_client()
        print("MCP client created....", len(self.mcp_client.get_tools()))

        self.agent_skills = await build_agent_skills(self)
        print("DONE build agent skills.....", len(self.agent_skills))
        build_agents(self)
        print("DONE build agents.....")
        # await self.launch_agents()
        print("DONE launch agents.....")
        self.top_gui.update_all(self)
        # await self.test_a2a()

    def wait_for_server(self, agent, timeout: float = 10.0):
        url = agent.get_card().url+'/ping'
        print("agent card url:", url)
        start = time.time()
        while time.time() - start < timeout:
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    print("✅ Server is up!")
                    return True
            except requests.ConnectionError:
                pass
            time.sleep(1)
        raise RuntimeError(f"❌ Server did not start within {timeout} seconds")


    async def launch_agents(self):
        print(f"launching agents:{len(self.agents)}")
        for agent in self.agents:
            if agent:
                print("KICKING OFF AGENT.....")
                await agent.start()
                print("checking a2a server status....")
                self.wait_for_server(agent)
                print("AGENT STARTED.....")
            else:
                print("WARNING EMPTY AGENT .....")

    async def test_a2a(self):
        # let supervisor agent sends a message to agent
        supervisor = next((ag for ag in self.agents if "Helper" not in ag.card.name), None)
        if supervisor:
            print("found supervisor:", supervisor.card.name)
            await supervisor.request_local_help()
        else:
            print("Warning, supervisor not found...")

    def get_free_agent_ports(self, n):
        used_ports = [ag.get_a2a_server_port() for ag in self.agents if ag is not None]
        print("#agents:", len(self.agents), "used ports:", used_ports, "port range:", self.local_agents_port_range)
        all_ports = range(self.local_agents_port_range[0], self.local_agents_port_range[1]+1)
        free_ports = [port for port in all_ports if port not in used_ports]

        if len(free_ports) < n:
            raise RuntimeError(f"Only {len(free_ports)} free ports available, but {n} requested.")

        print("free ports", free_ports)
        return free_ports[:n]

    def get_local_server_port(self):
        return self.general_settings["local_server_port"]


    def set_top_gui(self, top_gui):
        self.top_gui = top_gui


    def get_vehicle_ecbot_op_agent(self, v):
        # obtain agents on a vehicle.
        print(f"{len(self.agents)}")
        ecb_op_agent = next((ag for ag in self.agents if "ECBot RPA Operator Agent" in ag.card.name), None)
        print("FOUND Operator......", ecb_op_agent.card.name)
        return ecb_op_agent

    # SC note - really need to have
    async def run_async_tasks(self):
        if self.host_role != "Staff Officer":
            self.rpa_task = asyncio.create_task(self.runbotworks(self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
            self.manager_task = asyncio.create_task(self.runmanagerworks(self.gui_manager_msg_queue, self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))

        else:
            self.rpa_task = asyncio.create_task(self.wait_forever())

        # await asyncio.gather(self.peer_task, self.monitor_task, self.chat_task, self.rpa_task, self.wan_sub_task, self.wan_msg_task)
        await asyncio.gather(self.peer_task, self.monitor_task, self.chat_task, self.rpa_task, self.wan_sub_task)

    # 1) gather all skills (cloud + local public)
    # 2) analyze dependence and update data structure
    # 3) regenerate psk files for each skill
    # 4) build up skill_table (a look up table)
    def dailySkillsetUpdate(self):
        if self.general_settings["schedule_mode"] != "test":
            cloud_skills_results = self.SkillManagerWin.fetchMySkills()
            print("DAILY SKILL FETCH:", cloud_skills_results)
        else:
            cloud_skills_results = {"body": "{}"}
        existing_skids = [sk.getSkid() for sk in self.skills]
        print("EXISTING SKIDS:", existing_skids)

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

                    # now read the cloud skill's local definition file to get
                    self.skills.append(cloud_work_skill)

            # this will handle all skill bundled into software itself.
            self.showMsg("load local private skills")
            self.loadLocalPrivateSkills()

            # read public skills from local json files and merge with what's just read from the cloud.
            # if there is any conlict will use the cloud data as the true data.
            self.loadPublicSkills()

            # now add to skill manager display
            for skill in self.skills:
                    # update skill manager display...
                    self.SkillManagerWin.addSkillRows([skill])


            # for sanity immediately re-generate psk files... and gather dependencies info so that when user creates a new mission
            # when a skill is selected, its dependencies will added to mission's skills list.
            print("SKIDS to be regenerated:", [sk.getSkid() for sk in self.skills])
            self.regenSkillPSKs()

        print("after daily sync SKIDS:", [sk.getSkid() for sk in self.skills])

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
            log3("PSK FILE NAME::::::::::"+str(ski)+"::["+str(sk.getSkid())+"::"+sk.getPrivacy()+":::::"+sk_full_name, "fetchSchedule", self)
            if sk.getPrivacy() == "public":
                next_step, psk_file = genSkillCode(sk_full_name, sk.getPrivacy(), self.homepath, first_step, "light")
            else:
                self.showMsg("GEN PRIVATE SKILL PSK::::::" + sk_full_name)
                next_step, psk_file = genSkillCode(sk_full_name, sk.getPrivacy(), self.my_ecb_data_homepath, first_step, "light")
            log3("PSK FILE:::::::::::::::::::::::::"+psk_file, "fetchSchedule", self)
            sk.setPskFileName(psk_file)
            # fill out each skill's depencies attribute
            sk.setDependencies(self.analyzeMainSkillDependencies(psk_file))
            print("RESULTING DEPENDENCIES:["+str(sk.getSkid())+"] ", sk.getDependencies())

    def get_helper_agent(self):
        return self.helper_agent

    def updateTokens(self, tokens):
        self.tokens = tokens

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
        return self.static_resource.BUY_TYPES

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

    def setCommanderName(self, cn):
        self.commander_name = cn

    def getCommanderName(self):
        return self.commander_name

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

    def getWebDriverPath(self):
        return self.default_webdriver_path

    def setWebDriverPath(self, driver_path):
        self.default_webdriver_path = driver_path

    def getWebDriver(self):
        return self.default_webdriver

    def setWebDriver(self, driver):
        self.default_webdriver = driver

    def load_build_dom_tree_script(self):
        script = ""
        try:
            with open(self.build_dom_tree_script_path, 'r', encoding='utf-8') as file:
                script = file.read()
            return script
        except FileNotFoundError:
            print(f"Error: The file {self.build_dom_tree_script_path} was not found.")
            return ""
        except IOError as e:
            print(f"Error reading {self.build_dom_tree_script_path}: {e}")
            return ""

    #async def networking(self, platoonCallBack):
    def set_host_role(self, role):
        self.host_role = role

    def set_schedule_mode(self, sm):
        self.general_settings["schedule_mode"] = sm

    def get_schedule_mode(self):
        return self.general_settings["schedule_mode"]

    def set_default_wifi(self, default_wifi):
        self.general_settings["default_wifi"] = default_wifi

    def get_default_wifi(self):
        if "default_wifi" in self.general_settings:
            return self.general_settings["default_wifi"]
        else:
            return "unknown"

    def set_default_printer(self, default_printer):
        self.general_settings["default_printer"] = default_printer

    def get_default_printer(self):
        if "default_printer" in self.general_settings:
            return self.general_settings["default_printer"]
        else:
            return "unknown"


    def saveSettings(self):
        try:
            self.showMsg("saving general settings:" + json.dumps(self.general_settings))
            with open(self.general_settings_file, 'w') as f:
                json.dump(self.general_settings, f, indent=4)
                # self.rebuildHTML()
                f.close()
        except IOError:
            QMessageBox.information(self, f"Unable to open settings file {self.general_settings_file}")

    def get_schedule_mode(self):
        return self.schedule_mode


    def get_host_role(self):
        return self.host_role

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
        bot_menu.addAction(self.syncBotAccountsAction)
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
        run_menu.addAction(self.runRunLocalWorksAction)
        run_menu.addAction(self.runRunAllAction)
        run_menu.addAction(self.runTestAllAction)
        menu_bar.addMenu(run_menu)

        schedule_menu = QMenu(QApplication.translate("QMenu", "&Schedule"), self)
        schedule_menu.setFont(self.main_menu_font)
        schedule_menu.addAction(self.fetchScheduleAction)
        schedule_menu.addAction(self.scheduleCalendarViewAction)
        schedule_menu.addAction(self.scheduleFromFileAction)
        schedule_menu.addAction(self.rescheduleAction)
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


        tools_menu = QMenu(QApplication.translate("QMenu", "&Tools"), self)
        tools_menu.setFont(self.main_menu_font)
        tools_menu.addAction(self.toolsADSProfileConverterAction)
        tools_menu.addAction(self.toolsADSProfileBatchToSinglesAction)
        tools_menu.addAction(self.toolsWanChatTestAction)
        tools_menu.addAction(self.toolsStopWaitUntilTestAction)
        tools_menu.addAction(self.toolsSimWanRequestAction)
        tools_menu.addAction(self.toolsSyncFingerPrintRequestAction)
        tools_menu.addAction(self.toolsDailyHousekeepingAction)
        tools_menu.addAction(self.toolsDailyTeamPrepAction)
        tools_menu.addAction(self.toolsGatherFingerPrintsRequestAction)

        menu_bar.addMenu(tools_menu)


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


    def setCommanderXPort(self, xport):
        self.commanderXport = xport

    def getGuiMsgQueue(self):
        return self.gui_net_msg_queue

    def setIP(self, ip):
        self.ip = ip

    def getUser(self):
        return self.user

    def getImageEngine(self):
        return self.general_settings["img_engine"]

    def getLanImageEndpoint(self):
        return self.general_settings["lan_api_endpoint"]

    def getWanImageEndpoint(self):
        return self.general_settings["wan_api_endpoint"]

    def getWanApiEndpoint(self):
        return self.general_settings["wan_api_endpoint"]

    def getWanApiKey(self):
        return self.general_settings["wan_api_key"]

    def getWSApiEndpoint(self):
        return self.general_settings["ws_api_endpoint"]

    def getLanApiEndpoint(self):
        return self.general_settings["lan_api_endpoint"]

    def setMILANServer(self, ip, port="8848"):
        self.general_settings["lan_api_host"] = ip
        self.general_settings["lan_api_port"] = port
        self.general_settings["lan_api_endpoint"] = f"http://{ip}:{port}/graphql"
        print("lan_api_endpoint:", self.general_settings["lan_api_endpoint"])

    def setLanDBServer(self, ip, port="5080"):
        self.general_settings["localUserDB_host"] = ip
        self.general_settings["localUserDB_port"] = port

    def _syncBotAccountsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Sync Bot Accounts"))
        new_action.triggered.connect(self.syncBotAccounts)
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
        new_action.triggered.connect(lambda: self.sendToPlatoonsByRowIdxs([], cmd))

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

    def _createRunLocalWorkAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Run Local Work"))
        new_action.triggered.connect(lambda: asyncio.create_task(self.runTodaysLocalWork()))
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


    def _createRescheduleAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Reschedule"))
        new_action.triggered.connect(lambda: self.fetchSchedule("", self.get_vehicle_settings("true"), True))
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


    def _createToolsADSProfileConverterAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&ADS Profile Converter"))
        new_action.triggered.connect(self.runADSProfileConverter)
        return new_action

    def _createToolsADSProfileBatchToSinglesAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&ADS Profile Batch To Singles"))
        new_action.triggered.connect(self.runADSProfileBatchToSingles)
        return new_action


    def _createToolsWanChatTestAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Wan Chat Test"))
        new_action.triggered.connect(self.wan_chat_test)
        return new_action

    def _createToolsStopWaitUntilTestAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Stop Wait Until Test"))
        new_action.triggered.connect(self.stopWaitUntilTest)
        return new_action

    def _createToolsSimWanRequestAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Simulate Wan Request"))
        new_action.triggered.connect(self.simWanRequest)
        return new_action

    def _createToolsSyncFingerPrintRequestAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Sync Finger Print Request(Manager Only)"))
        new_action.triggered.connect(self.syncFingerPrintRequest)
        return new_action

    def _createToolsDailyHousekeepingAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Daily Housekeeping(Manager Only)"))
        new_action.triggered.connect(self.dailyHousekeeping)
        return new_action

    def _createToolsDailyTeamPrepAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Daily Team Prep(Manager Only)"))
        new_action.triggered.connect(self.dailyTeamPrep)
        return new_action

    def _createToolsGatherFingerPrintsRequestAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Gather Finger Prints Request(Platoon Only)"))
        new_action.triggered.connect(self.gatherFingerPrints)
        return new_action

    def _createHelpUGAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&User Guide"))
        new_action.triggered.connect(self.gotoUserGuide)
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

    def getDisplayResolution(self):
        return self.display_resolution

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
        # test_read_buy_req_files(self)
        # test_misc()
        # test_scrape_amz_prod_list()
        # test_api(self, self.session, self.tokens['AuthenticationResult']['IdToken'])
        # run_genSchedules_test_case(self, self.session, self.tokens['AuthenticationResult']['IdToken'], 1)
        # test_run_mission(self)
        # test_save_csk(self.session, self.tokens['AuthenticationResult']['IdToken'])

        # new_mission = EBMISSION(self)
        # test_request_skill_run(new_mission)

        # asyncio.ensure_future(testLocalImageAPI2(self))
        # asyncio.create_task(testLocalImageAPI2(self))
        # asyncio.create_task(testLocalImageAPI3(self))
        # testSyncLocalImageAPI(self)
        # asyncio.ensure_future(stressTestImageAPI(self, 5))

        # loop = asyncio.get_event_loop()
        # loop.create_task(stressTestImageAPI(self, iterations=6))
        # testGetManagerMissions(self)
        # test_report_skill_run_result(new_mission)
        # msg = "vVABC|M123|B21|S-running_idle|Error: Exception hello world"
        # ek = self.getEncryptKey()
        # ek = self.generate_key_from_string(self.main_key)
        # em = self.encrypt_string(ek, msg)
        # print("key:", self.main_key, ek, em)
        # print("recovered:", self.decrypt_string(ek, em))
        #
        # test_presigned_updownload(new_mission)
        # asyncio.create_task(test_send_file(fieldLinks[0]["transport"]))
        # test_handle_extern_skill_run_report(self.session, self.tokens['AuthenticationResult']['IdToken'])
        # asyncio.ensure_future(test_wait_until8())

        # testCloudAccessWithAPIKey(self.session, self.tokens['AuthenticationResult']['IdToken'])
        # testSyncPrivateCloudImageAPI(self)
        asyncio.ensure_future(test_helper(self))
        # testReportVehicles(self)
        # testDequeue(self)
        # Start Gradio in a separate thread
        # self.gradioWin.show()
        # test_processSearchWordLine()
        # test_UpdateBotADSProfileFromSavedBatchTxt()
        # test_run_group_of_tasks(self)

        # filename, _ = QFileDialog.getOpenFileName(
        #     self,
        #     QApplication.translate("QFileDialog", "Open Browser Test Setup File"),
        #     '',
        #     QApplication.translate("QFileDialog", "Setup Files (*.json)")
        # )

        # testWebdriverADSAndChromeConnection(self, filename)

    async def runTodaysLocalWork(self):
        # send a request to commander for today's scheduled work.
        workReq = {"type": "reqResendWorkReq", "ip": self.ip, "content": "now"}
        await self.send_json_to_commander(self.commanderXport, workReq)

    # 1) prepre ads profile cookies
    # 2) group them by vehicle
    # 3) assign them. (move the troop to the vehicle(host computer where they belong， Bots, Missions, Skills, ADS related data and files.)
    def handleCloudScheduledWorks(self, bodyobj):
        if bodyobj:
            log3("handleCloudScheduledWorks...."+str(len(bodyobj))+" "+str(type(bodyobj)), "fetchSchedule", self)
            # print("bodyobj:", bodyobj)
            for nm in bodyobj["added_missions"]:
                today = datetime.today()
                formatted_today = today.strftime('%Y-%m-%d')
                bd_parts = nm["createon"].split()
                nm["createon"] = formatted_today + " " + bd_parts[1]

            # log3("cloud schedule works:" + json.dumps(bodyobj), "fetchSchedule", self)
            log3("BEGIN ASSIGN INCOMING MISSION....", "fetchSchedule", self)
            self.build_cookie_site_lists()
            # convert new added mission json to MISSIONs object
            newlyAdded = self.addNewlyAddedMissions(bodyobj)
            # now that todays' newly added missions are in place, generate the cookie site list for the run.
            self.num_todays_task_groups = self.num_todays_task_groups + len(bodyobj["task_groups"])
            print("num_todays_task_groups:", self.num_todays_task_groups)
            # self.todays_scheduled_task_groups = self.groupTaskGroupsByOS(bodyobj["task_groups"])
            #  turn this into a per-vehicle flattend list of tasks (vehicle name based dictionary).
            self.todays_scheduled_task_groups = self.reGroupByBotVehicles(bodyobj["task_groups"])
            self.unassigned_scheduled_task_groups = self.todays_scheduled_task_groups
            print("current unassigned task groups:", list(self.unassigned_scheduled_task_groups.keys()))
            for vn in self.unassigned_scheduled_task_groups:
                print(f"unassigned task groups:{vn} {len(self.unassigned_scheduled_task_groups[vn])}")
            # print("current work to do:", self.todays_work)
            # for works on this host, add to the list of todos, otherwise send to the designated vehicle.
            # self.assignWork()

            # log3("current unassigned scheduled task groups after assignwork:"+json.dumps(self.unassigned_scheduled_task_groups), "fetchSchedule", self)
            # log3("current work to do after assignwork:"+json.dumps(self.todays_work), "fetchSchedule", self)

            self.logDailySchedule(json.dumps(bodyobj))
        else:
            log3("WARN: empty obj", "fetchSchedule", self)
            self.warn(QApplication.translate("QMainWindow", "Warning: NO schedule generated."))

    # this is more for the convinence of isolated testing ....
    def reGenWorksForVehicle(self, vehicle):

        if len(self.todaysSchedule) > 0:
            log3("reGenWorksForVehicle...." + str(len(self.todaysSchedule)) + " " + str(type(self.todaysSchedule)),
                 "fetchSchedule", self)
            # print("todaysSchedule:", self.todaysSchedule)

            vname = vehicle.getName()
            if vname in self.todaysSchedule["task_groups"]:
                vbids = []
                tzs = self.todaysSchedule["task_groups"][vname].keys()
                for tz in tzs:
                    vbids = vbids + [vw["bid"] for vw in self.todaysSchedule["task_groups"][vname][tz]]
                vadded_ms = [m for m in self.todaysSchedule["added_missions"] if m["botid"] in vbids]
                print("vbids:", vbids)
                print("vadded mids:", [m["mid"] for m in vadded_ms])
                vtg = {"task_groups": {vname: self.todaysSchedule["task_groups"][vname]},
                       "added_missions": vadded_ms}

                print("vtg:", vtg)

            # now that todays' newly added missions are in place, generate the cookie site list for the run.
            self.num_todays_task_groups = self.num_todays_task_groups + len(vtg["task_groups"])
            print("regen num_todays_task_groups:", self.num_todays_task_groups)

            self.todays_scheduled_task_groups = self.reGroupByBotVehicles(vtg["task_groups"])
            self.unassigned_scheduled_task_groups = self.todays_scheduled_task_groups
            # print("current unassigned task groups:", self.unassigned_scheduled_task_groups)
            # assignWork() will take care of the rest, it will check any unassigned work and assign them.

            log3("current unassigned scheduled task groups after assignwork:"+json.dumps(self.unassigned_scheduled_task_groups), "fetchSchedule", self)
            log3("current work to do after assignwork:"+json.dumps(self.todays_work), "fetchSchedule", self)

        else:
            log3("WARN: empty obj", "fetchSchedule", self)
            self.warn(QApplication.translate("QMainWindow", "Warning: NO schedule generated."))


    def addTestMissions(self, bodyobj):
        for m in bodyobj["added_missions"]:
            new_mission = EBMISSION(self)
            self.fill_mission(new_mission, m, bodyobj["task_groups"])
            self.setPrivateAttributesBasedOnPast(new_mission)
            new_mission.updateDisplay()
            self.missions.append(new_mission)
            self.missionModel.appendRow(new_mission)

    # this function fetches schedule and assign work based on fetch schedule results...
    def fetchSchedule(self, ts_name, settings, forceful=False):
        log3("time stamp " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + " start fetching schedule...", "fetchSchedule", self)
        ex_stat = "Completed:0"
        try:
            # before even actual fetch schedule, automatically all new customer buy orders from the designated directory.
            # self.newBuyMissionFromFiles()
            # self.createNewBotsFromBotsXlsx()
            # self.createNewMissionsFromOrdersXlsx()
            today = datetime.now()
            # Format the date as yyyymmdd
            yyyymmdd = today.strftime("%Y%m%d")
            sf_name = "schedule" + yyyymmdd+".json"
            schedule_file = os.path.join(self.my_ecb_data_homepath + "/runlogs", sf_name)
            todaysScheduleExists = os.path.exists(schedule_file)
            log3("Done handling today's new Buy orders...", "fetchSchedule", self)
            bodyobj = {}
            # next line commented out for testing purpose....
            if not self.debug_mode and self.schedule_mode == "auto":
                log3("schedule setting:"+json.dumps(settings), "fetchSchedule", self)

                log3(f"schedule file {schedule_file} exists: {todaysScheduleExists}", "fetchSchedule", self)
                if not todaysScheduleExists or forceful:
                    jresp = send_schedule_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], ts_name, settings, self.getWanApiEndpoint())
                    log3(f"schedule JRESP: {len(jresp['body'])} bytes", "fetchSchedule", self)
                else:
                    with open(schedule_file, "r") as sf:
                        jresp = json.load(sf)
            else:
                log3("debug mode, skipping cloud fetch schedule", "fetchSchedule", self)
                jresp = {}

            if "errorType" in jresp:
                screen_error = True
                log3("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]), "fetchSchedule", self)
            else:
                # first, need to decompress the body.
                # very important to use compress and decompress on Base64
                if not self.debug_mode and self.schedule_mode == "auto":
                    if not todaysScheduleExists or forceful:
                        uncompressed = self.zipper.decompressFromBase64(jresp["body"])   # commented out for testing
                    else:
                        uncompressed = "{}"
                else:
                    uncompressed = "{}"
                print("unzip schedule done....")
                # for testing purpose, short circuit the cloud fetch schedule and load a tests schedule from a tests
                # json file instead.

                # uncompressed = jresp["body"]
                if uncompressed != "":
                    self.showMsg("body string:!"+str(len(uncompressed))+"::")

                    bodyobj = {"task_groups": {}, "added_missions": []}

                    if not self.debug_mode and self.schedule_mode == "auto":
                        if not todaysScheduleExists or forceful:
                            bodyobj = json.loads(uncompressed)                      # for test purpose, comment out, put it back when test is done....
                        else:
                            bodyobj = jresp
                    else:
                        log3("debug mode, using test vector....", "fetchSchedule", self)
                        # file = 'C:/software/scheduleResultTest7.json'
                        file = 'C:/temp/scheduleResultTest1.json'
                        # file = 'C:/temp/scheduleResultTest5.json'             # ads ebay sell test
                        # file = 'C:/temp/scheduleResultTest7.json'             # ads amz browse test
                        # file = 'C:/temp/scheduleResultTest10_9_3.json'             # ads ebay amz etsy sell test.
                        # file = 'C:/temp/scheduleResultTest999.json'
                        # file = 'C:/temp/scheduleResult Test6.json'               # ads amz buy test.
                        if exists(file):
                            with open(file) as test_schedule_file:
                                bodyobj = json.load(test_schedule_file)
                                self.addTestMissions(bodyobj)

                    # self.handleCloudScheduledWorks(bodyobj)
                else:
                    self.warn(QApplication.translate("QMainWindow", "Warning: Empty Network Response."))

            if ((not todaysScheduleExists) or forceful) and (not self.debug_mode) and (self.schedule_mode == "auto"):
                log3(f"saving schedule file {schedule_file}", "fetchSchedule", self)

                with open(schedule_file, 'w') as sf:
                    json.dump(bodyobj, sf, indent=4)
                sf.close()

            print("fetch schedule time stamp " + datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3] + " done with fetch schedule....", list(bodyobj.keys()), len(bodyobj["added_missions"]))
            self.todaysSchedule = bodyobj
            return bodyobj
        # ni is already incremented by processExtract(), so simply return it.
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorFetchSchedule:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorFetchSchedule: traceback information not available:" + str(e)
            self.showMsg(ex_stat)
            return {}


    def fetchScheduleFromFile(self):
        try:
            ex_stat = "Completed:0"
            file = 'C:/temp/scheduleResultTest9D.json'  # ads ebay amz etsy sell test.
            filename, _ = QFileDialog.getOpenFileName(
                self,
                QApplication.translate("QFileDialog", "Open Browser Test Setup File"),
                '',
                QApplication.translate("QFileDialog", "Setup Files (*.json)")
            )
            if os.path.exists(filename):
                with open(filename, 'rb') as test_schedule_file:
                    testSchedule = json.load(test_schedule_file)
                    # self.rebuildHTML()
                    test_schedule_file.close()

                if "Commander" in self.machine_role:
                    self.handleCloudScheduledWorks(testSchedule)
                elif "Platoon" in self.machine_role:
                    # put this into Platoon's commander message queue, the rest will be take care of by itself.
                    asyncio.create_task(
                        self.gui_net_msg_queue.put("192.168.0.8!net data!" + json.dumps(testSchedule)))

            else:
                self.warn(QApplication.translate("QMainWindow", "Warning: Test Vector File Not Found."))
            # ni is already incremented by processExtract(), so simply return it.
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorFetchScheduleFromFile:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorFetchScheduleFromFile: traceback information not available:" + str(e)
            self.showMsg(ex_stat)

        log3("done with fetch schedule from file:" + ex_stat, "fetchSchedule", self)
        return ex_stat

    def warn(self, msg, level="info"):
        warnText = self.log_text_format(msg, level)
        self.netLogWin.appendLogs([warnText])
        self.appendNetLogs([warnText])

    def showMsg(self, msg, level="info"):
        msg_text = self.log_text_format(msg, level)
        self.appendNetLogs([msg_text])

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
            text_color = "color:#004800;"
            logger_helper.info(msg)
        elif level == "debug":
            text_color = "color:#00ffff;"
            logger_helper.debug(msg)

        msg_text = """ 
            <div style="display: flex; padding: 5pt;">
                <span  style=" font-size:12pt; font-weight:450; margin-right: 40pt;"> 
                    %s |
                </span>
                <span style=" font-size:12pt; font-weight:450; %s">
                    %s
                </span>
                |
                <span style=" font-size:12pt; font-weight:450; %s;">
                    found %s
                </span>
            </div>""" % (logTime, text_color, level, text_color, msg)
        return msg_text

    def logDailySchedule(self, netSched):
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time = now.strftime("%H:%M:%S - ")
        dailyScheduleLogFile = self.my_ecb_data_homepath + "/runlogs/{}/{}/schedule{}{}{}.txt".format(self.log_user, year, month, day, year)
        if os.path.isfile(dailyScheduleLogFile):
            log3("append to daily schedule file:" + dailyScheduleLogFile, "fetchSchedule", self)
            file1 = open(dailyScheduleLogFile, "a")  # append mode
            file1.write(json.dumps(time+netSched) + "\n=====================================================================\n")
            file1.close()
        else:
            log3("daily schedule file not exist:"+dailyScheduleLogFile, "fetchSchedule", self)
            file1 = open(dailyScheduleLogFile, "w")  # write mode
            file1.write(json.dumps(time+netSched) + "\n=====================================================================\n")
            file1.close()

    def saveDailyRunReport(self, runStat):
        now = datetime.now()  # current date and time
        year = now.strftime("%Y")
        month = now.strftime("%m")
        day = now.strftime("%d")
        time = now.strftime("%H:%M:%S - ")
        dailyRunReportFile = self.my_ecb_data_homepath + "/runlogs/{}/{}/runreport{}{}{}.txt".format(self.log_user, year, month, day, year)

        if os.path.isfile(dailyRunReportFile):
            with open(dailyRunReportFile, 'a') as f:

                f.write(time+json.dumps(runStat) + "\n")

                f.close()
        else:
            with open(dailyRunReportFile, 'w') as f:

                f.write(time+json.dumps(runStat) + "\n")

                f.close()


    def fill_mission(self, blank_m, m, tgs):
        # print("BLANK:", m)
        blank_m.loadNetRespJson(m)
        # self.showMsg("after fill mission paramter:"+str(blank_m.getRetry()))
        mconfig = None
        for v in tgs:
            tz_group = tgs[v]
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
    # as well as some daily routines.... will be generated as well....
    # one of the key thing to do here is the fill out the private attribute from the most recent past similar missions.
    def addNewlyAddedMissions(self, resp_data):
        # for each received work mission, check whether they're in the self.missions already, if not, create them and
        # add to the missions list.
        mb_words = ""
        task_groups = resp_data["task_groups"]
        for v in task_groups:
            tg = task_groups[v]
            for tz in tg:
                for wg in tg[tz]:
                    for w in wg["bw_works"]:
                        mb_words = mb_words + "M"+str(w["mid"])+"B"+str(wg["bid"]) + ", "

                    for w in wg["other_works"]:
                        mb_words = mb_words + "M"+str(w["mid"])+"B"+str(wg["bid"]) + ", "

        log3(mb_words, "fetchSchedule", self)

        newAdded = []
        newly_added_missions = resp_data["added_missions"]
        true_newly_added = []       # newly_added_missions includes some previous incompleted missions, they're not really NEW.
        log3("Added MS:"+json.dumps(["M"+str(m["mid"])+"B"+str(m["botid"]) for m in newly_added_missions]), "fetchSchedule", self)
        loadedMids = [m.getMid() for m in self.missions]
        for m in newly_added_missions:
            if m["mid"] not in loadedMids:
                new_mission = EBMISSION(self)
                self.fill_mission(new_mission, m, task_groups)
                self.setPrivateAttributesBasedOnPast(new_mission)
                new_mission.updateDisplay()
                self.missions.append(new_mission)
                self.missionModel.appendRow(new_mission)
                log3("adding mission.... "+str(new_mission.getRetry()), "fetchSchedule", self)
                true_newly_added.append(new_mission)
                newAdded.append(new_mission)
            else:
                log3("this mission already exists:"+str(m["mid"]), "fetchSchedule", self)
                # in such a case, simply sync up the data
                existingMission = self.getMissionByID(m["mid"])
                # now, update data from cloud...
                existingMission.loadNetRespJson(m)
                newAdded.append(existingMission)

        if not self.debug_mode:
            self.addMissionsToLocalDB(true_newly_added)

        return(newAdded)

    # this is really about setting up fingerprint profile automatically for a new Mission
    # if it's not already set up, basically using bot's email + site in cuspas to create
    # the relevant profile xlsx from the superset .txt version of the bot's profile (based on email only)
    def setPrivateAttributesBasedOnPast(self, newMission):
        print("new mission type and cuspas:", newMission.getType(), newMission.getCusPAS())

        foundBot = self.getBotByID(newMission.getBid())
        if foundBot:
            botEmail = foundBot.getEmail()

        similar = [m for m in self.missions if m.getType() == newMission.getType() and m.getCusPAS() == newMission.getCusPAS()]
        similarWithFingerPrintProfile = [m for m in similar if m.getFingerPrintProfile()]

        print("similar w fpp: ", [m.getFingerPrintProfile() for m in similarWithFingerPrintProfile])
        if similarWithFingerPrintProfile:
            mostRecent = similarWithFingerPrintProfile[-1]

            newMission.setFingerPrintProfile(mostRecent.getFingerPrintProfile())
            print("newy set fpp:", newMission.getFingerPrintProfile())

    def getBotByID(self, bid):
        found_bot = next((bot for i, bot in enumerate(self.bots) if bot.getBid() == bid), None)
        return found_bot

    def getMissionByID(self, mid):
        found_mission = next((mission for i, mission in enumerate(self.missions) if mission.getMid() == mid), None)
        return found_mission

    def getSkillByID(self, skid):
        found_skill = next((skill for i, skill in enumerate(self.skills) if skill.getSkid() == skid), None)
        return found_skill

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
                mj = found_mission.genJson()
                result.append(mj)

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
        # bids = []
        # mids = []
        # for key, value in task_group.items():
        #     if isinstance(value, list) and len(value) > 0:
        #         for assignment in value:
        #             bids.append(assignment["bid"])
        #             for work in assignment["bw_works"]:
        #                 mids.append(work["mid"])
        #             for work in assignment["other_works"]:
        #                 mids.append(work["mid"])

        bids = [task["bid"] for task in task_group]
        mids = [task["mid"] for task in task_group]

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
                print("m skillls: ", mid, m.getMid(), m.getSkills(), type(m.getSkills()))
                if isinstance(m.getSkills(), list):
                    m_skids = m.getSkills()
                else:
                    m_skids = [int(skstring.strip()) for skstring in m.getSkills().strip().split(",")]
                print("m_skids: ", m_skids)
                if m_skids:
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

    # flatten all tasks associated with a vehicle.
    def flattenTaskGroup(self, vTasks):
        try:
            tgbs = []

            # flatten across time zone
            for tz in vTasks.keys():
                tgbs = tgbs + vTasks[tz]

            all_works = []

            for tgb in tgbs:
                bid = tgb["bid"]

                for bw in tgb["bw_works"]:
                    bw["bid"] = bid
                    all_works.append(bw)

                for other in tgb["other_works"]:
                    other["bid"] = bid
                    all_works.append(other)

            self.showMsg("after flatten and aggregation, total of "+str(len(all_works))+"tasks in this group!")
            time_ordered_works = sorted(all_works, key=lambda x: x["start_time"], reverse=False)
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorFlattenTasks:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorFlattenTasks: traceback information not available:" + str(e)

        return time_ordered_works


    def groupTaskGroupsByOS(self, tgs):
        result = {
            "win": [tg for tg in tgs if "win" in self.getTaskGroupOS(tg)],
            "mac": [tg for tg in tgs if "mac" in self.getTaskGroupOS(tg)],
            "linux": [tg for tg in tgs if "linux" in self.getTaskGroupOS(tg)]
        }
        return result

    # note there could be schedule conflict here, because on cloud side, the schedule are assigned sequentially without knowing
    # which bot on which vehicle, if 2 bots are on the same vehicle, cloud doesn't know it and could assign them to two
    # vehicle group and cause them to be assigned with the same time slot. Q: should cloud side change assignment algorithm?
    # or should time assignment be done locally anyways? should bot cloud DB includes vehicle info? if cloud side includes
    # vehicle info, what algorithm should it be?
    def reGroupByBotVehicles(self, tgs):
        vtgs = {}
        for vehicle in tgs.keys():
            vtasks = self.flattenTaskGroup(tgs[vehicle])
            # for vtask in vtasks:
            #     found_bot = next((b for i, b in enumerate(self.bots) if b.getBid() == vtask["bid"]), None)
            #     bot_v = found_bot.getVehicle()
            #     print("bot_v:", bot_v, "task v:", vehicle)
            vtgs[vehicle] = vtasks
        return vtgs


    def getUnassignedVehiclesByOS(self):
        self.showMsg("N vehicles " + str(len(self.vehicles)))
        result = {
            "win": [v for v in self.vehicles if v.getOS().lower() in "Windows".lower() and len(v.getBotIds()) == 0],
            "mac": [v for v in self.vehicles if v.getOS().lower() in "Mac".lower() and len(v.getBotIds()) == 0],
            "linux": [v for v in self.vehicles if v.getOS().lower() in "Linux".lower() and len(v.getBotIds()) == 0]
        }
        self.showMsg("N vehicles win " + str(len(result["win"]))+" " + str(len(result["mac"]))+" " + str(len(result["linux"])))
        if self.host_role == "Commander" and not self.rpa_work_assigned_for_today:
            print("checking commander", self.todays_work["tbd"])
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
        self.showMsg("groupVehiclesByOS>>>>>>>>>>>> "+self.host_role)
        result = {
            "win": [v for v in self.vehicles if v.getOS() == "Windows"],
            "mac": [v for v in self.vehicles if v.getOS() == "Mac"],
            "linux": [v for v in self.vehicles if v.getOS() == "Linux"]
        }
        self.showMsg("all vehicles>>>>>>>>>>>> " + json.dumps(result))
        self.showMsg("now take care of commander machine itself in case of being a dual role commander")
        if self.host_role == "Commander":
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
    # on the cloud side, a search config should have been attached to the buy_*** mission,
    # in case we just started execute a buy mission (i.e. the first steps are addcart or
    # addcart and pay, then:
    # 0) randomly select a search to swap the actual buy-related search.
    # 1) expand search result pages to 5 pages (we'll search up to 5 pages for the designated product.
    # 2) on each result pages of this selected search, make a to-be-opened product,(sel_type "cus" and add purchase)
    #    to the to-be-opened products list.
    # in case we are onto the later stage of buy (such as check shipping status, feedback etc.)
    # we would simply
    #  0) add "purchase" to first product on the first porduct list page of the selected search.
    # this would trigger the skill to go directly to the account's orders list and perform the buy
    # step.
    def gen_new_buy_search(self, work, mission):
        # simply modify mission's search configuration to fit our need.
        # we'll randomely pick one of the searches and modify its parameter.
        log3(f"gen buy related search...", "buyConfig", self)
        nth_search = random.randrange(0, len(work["config"]["searches"]))
        # nth_search = 0                  # quick hack for speeding up unit test. should be removed in release code.
        n_pages = len(work["config"]["searches"][nth_search]["prodlist_pages"])
        log3(f"nth_search-{nth_search}", "buyConfig", self)

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
                if work["name"].split("_")[1] in ["addCart", "addCartPay"]:
                    target_buy = {
                        "selType": "cus",   # this is key, the skill itself will do the swapping of search terms once it see "cus" here.
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
                                    "follow_seller": mission.getFollowSeller(),
                                    "follow_price": mission.getFollowPrice()
                                }]
                    }
                log3(f"added target buy cart pay: {target_buy}", "buyConfig", self)
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
                                "feedback_instructions": mission.getFeedbackInstructions(),
                                "follow_seller": mission.getFollowSeller(),
                                "follow_price": mission.getFollowPrice()
                            }
                        ]
                    }
            log3(f"set up run time swap with buy related search to replace cloud search {first_page['products'][0]}", "buyConfig", self)
        log3("Modified Buy Search Work:"+json.dumps(work), "buyConfig", self)


    def findWorkFromMission(self, mission):
        found = False
        foundWork = None
        if self.todaysSchedule():
            for vname in self.todaysSchedule["task_groups"]:
                tzs = self.todaysSchedule["task_groups"][vname].keys()
                for tz in tzs:
                    for w in self.todaysSchedule["task_groups"][vname][tz]["bw_works"]:
                        if w["mid"] == mission.getMid():
                            found = True
                            foundWork = w
                            break

                    if not found:
                        for w in self.todaysSchedule["task_groups"][vname][tz]["other_works"]:
                            if w["mid"] == mission.getMid():
                                found = True
                                foundWork = w
                                break

                    else:
                        break
                if found:
                    break

        return foundWork

    def gen_random_search_term(self, mission):
        main_cats = list(self.buy_search_settings["search_terms"]["amz"].keys())
        main_cat_idx = random.randint(0, len(main_cats))
        main_cat = main_cats[main_cat_idx]
        sub1_cats = list(self.buy_search_settings["search_terms"]["amz"][main_cat].keys())
        sub1_cat_idx = random.randint(0, len(sub1_cats))
        sub1_cat = sub1_cats[sub1_cat_idx]
        terms = self.buy_search_settings["search_terms"]["amz"][main_cat][sub1_cat]
        terms_idx = random.randint(0, len(terms))
        search_term = terms[terms_idx]
        return search_term

    def gen_random_product_params(self, mission):
        random_st_idx = random.randint(0, len(self.buy_search_settings["selType_selections"]))
        random_dl_idx = random.randint(0, len(self.buy_search_settings["detailLvl_selections"]))
        product_params = {
            "selType": self.buy_search_settings["selType_selections"][random_st_idx],
            "detailLvl": self.buy_search_settings["selType_selections"][random_dl_idx],
            "purchase": []
        }

        return product_params

    def gen_random_page_params(self, mission):
        random_flow_idx = random.randint(0, len(self.buy_search_settings["flow_selections"]))
        pg_params = {
            "flow_type": self.buy_search_settings["flow_selections"][random_flow_idx],
            "products": []
        }
        nProducts = random.randint(1, self.buy_search_settings["max_browse_products_per_page"]+1)
        for n in range(nProducts):
            productConfig = self.gen_random_product_params(mission)
            pg_params["products"].append(productConfig)

        return pg_params

    def gen_random_search_params(self, mission):
        search = {
            "type": "browse_routine",
            "site": "amz",
            "os": "win",
            "app": "ads",
            "entry_paths": {
                "type": "Search",
                "words": [self.gen_random_search_term(mission)]
            },
            "top_menu_item": "",
            "prodlist_pages": [],
            "buy_cfg": None
        }
        nPages = random.randint(1, self.buy_search_settings["max_browse_pages"]+1)
        for n in range(nPages):
            pageConfig = self.gen_random_page_params(mission)
            search["prodlist_pages"].append(pageConfig)

        return search

    def gen_random_search_config(self, mission):
        config = {"estRunTime": 1, "searches": []}
        nSearches = random.randint(1, self.buy_search_settings["max_searches"]+1)
        log3(f"gen nsearches:{nSearches}", "buyConfig", self)
        for n in range(nSearches):
            search = self.gen_random_search_params(mission)
            config["searches"].append(search)
        return config

    def gen_buy_search_config(self, mission):
        log3(f"cofigure buy search {mission.getMid()}", "buyConfig", self)
        work = self.findWorkFromMission(mission)
        work["config"] = self.gen_random_search_config(mission)

        # simply modify mission's search configuration to fit our need.
        # we'll randomely pick one of the searches and modify its parameter.
        nth_search = random.randrange(0, len(work["config"]["searches"]))
        # nth_search = 0                  # quick hack for speeding up unit test. should be removed in release code.
        n_pages = len(work["config"]["searches"][nth_search]["prodlist_pages"])

        work["config"]["searches"][nth_search]["entry_paths"]["type"] = "Search"
        work["config"]["searches"][nth_search]["entry_paths"]["words"] = [mission.getSearchKW()]

        # simply duplate the last prodlist_pages enough times to satisfy up to 5 pages requirement
        if work["name"].split("_")[1] in ["addCart", "addCartPay"]:
            last_page = work["config"]["searches"][nth_search]["prodlist_pages"][n_pages-1]
            if n_pages < 5:  # we will browse up to 5 pages for a product purchase.
                for i in range(5-n_pages):
                    work["config"]["searches"][nth_search]["prodlist_pages"].append(copy.deepcopy(last_page))

            # on each pages, add the target buy product onto the list.
            for page in work["config"]["searches"][nth_search]["prodlist_pages"]:
                if work["name"].split("_")[1] in ["addCart", "addCartPay"]:
                    target_buy = {
                        "selType": "cus",   # this is key, the skill itself will do the swapping of search terms once it see "cus" here.
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
                                    "follow_seller": mission.getFollowSeller(),
                                    "follow_price": mission.getFollowPrice()
                                }]
                    }
                log3(f"added target buy: {target_buy}", "buyConfig", self)
                page["products"].append(target_buy)

        mission.setConfig(work["config"])
        log3("Modified Buy Work:"+json.dumps(work), "buyConfig", self)


    def gen_prod_sel(self):
        idx = math.floor(random.random() * (len(self.static_resource.PRODUCT_SEL_TYPES.length) - 1))
        return self.static_resource.PRODUCT_SEL_TYPES[idx]


    # given a derived buy mission, find out the original buy mission that was put in order by the users.
    # this is done thru searching ticket number. since this is likely to be a mission created 2 wks ago,
    # might not be loaded from memory, so directly search DB.
    def find_original_buy(self, buy_mission):
        # Construct the SQL query with a parameterized IN clause
        if buy_mission.getTicket() == 0:
            print("original buy mission ticket")
            # this is test mode special ticket, so provide some test vector.
            original_buy_mission = EBMISSION(self)
            original_buy_mission.setMid(0)
            original_buy_mission.setASIN("B0D1BY5VTM")
            original_buy_mission.setStore("Tikom")
            original_buy_mission.setFollowSeller("")
            original_buy_mission.setBrand("Tikom")
            original_buy_mission.setImagePath("")
            original_buy_mission.setSearchKW("dumb bells")
            original_buy_mission.setTitle("Tikom Robot Vacuum and Mop Combo with LiDAR Navigation, L9000 Robotic Vacuum Cleaner with 4000Pa Suction,150Min Max, 14 No-Go Zones, Smart Mapping, Good for Pet Hair, Carpet, Hard Floor")
            original_buy_mission.setVariations("")
            original_buy_mission.setRating("5.0")
            original_buy_mission.setFeedbacks("23")
            original_buy_mission.setPrice(229.99)
            original_buy_mission.setFollowPrice(0.0)
            original_buy_mission.setCustomerID("")
        else:
            db_data = self.mission_service.find_missions_by_ticket(buy_mission.getTicket())
            print("buy mission ticket:", buy_mission.getTicket())
            self.showMsg("same ticket missions: " + json.dumps(db_data.to_dict()))
            if len(db_data) != 0:
                original_buy_mission = EBMISSION(self)
                original_buy_mission.loadDBData(db_data)
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
        buys = [tsk for tsk in p_task_groups if (tsk["name"].split("_")[0] in self.static_resource.BUY_TYPES)]
        initial_buys = []
        later_buys = []
        for buy in buys:
            buy_parts = buy["name"].split("_")
            if len(buy_parts) > 1:
                if buy_parts[1] in ['addCart', 'pay', 'addCartPay']:
                    initial_buys.append(buy)
                else:
                    later_buys.append(buy)

        print(f"# buys:{len(buys)}, {len(initial_buys)}, {len(later_buys)}")
        for buytask in buys:
            # make sure we do search before buy
            midx = next( (i for i, mission in enumerate(self.missions) if str(mission.getMid()) == str(buytask["mid"])), -1)
            if midx >= 0:
                task_mission = self.missions[midx]
                original_buy = self.find_original_buy(task_mission)
                # first, fill the mission with original buy's private attributes for convenience.
                if original_buy:
                    task_mission.setASIN(original_buy.getASIN())
                    task_mission.setTitle(original_buy.getTitle())
                    task_mission.setVariations(original_buy.getVariations())
                    task_mission.setFollowSeller(original_buy.getFollowSeller())
                    task_mission.setStore(original_buy.getStore())
                    task_mission.setBrand(original_buy.getBrand())
                    task_mission.setImagePath(original_buy.getImagePath())
                    task_mission.setRating(original_buy.getRating())
                    task_mission.setFeedbacks(original_buy.getFeedbacks())
                    task_mission.setPrice(original_buy.getPrice())
                    task_mission.setFollowPrice(original_buy.getFollowPrice())
                    task_mission.setResult(original_buy.getResult())
                    task_mission.setSearchKW(original_buy.getSearchKW())

                    self.gen_new_buy_search(buytask, task_mission)
                else:
                    log3("ERROR: could NOT find original buy mission!")
            else:
                log3(f"buy mission not found {midx} {buytask['mid']}")
    # 1) group vehicle based on OS
    # 2) matche unassigned task group to vehicle based on OS.
    # 3) generate ADS profile xls for bots on that vehicle.
    # 4) modify task in case of buy related task....
    # 5) empower that vehicle with bots(including profiles), missions, tasks, skills
    # SC-06/27/2024 this algorithm asssumes, any bots can run on any vehicle as long as role, skill platform matches.
    # but this could be aggressive, bots and vehicles relationship could be fixed. in that case, we'll need a different
    # algorithm. which leas to assignWork2() where a vehicle-bot relationship will be read out at the beginning and
    # maintained in constant. when work group is scheduled. we will regroups bots' vehicle, and then generated associated
    # ads profiles, bots, missions, tasks, skills file.....
    # otherwise, send works to platoons to execute.
    async def assignWork(self):
        # tasks should already be sorted by botid,
        try:
            nsites = 0
            
            v_groups = self.getUnassignedVehiclesByOS()                      #result will {"win": win_vs, "mac": mac_vs, "linux": linux_vs}
            # print some debug info.
            for key in v_groups:
                log3("num vehicles in "+key+" :"+str(len(v_groups[key])), "assignWork", self)
                if len(v_groups[key]) > 0:
                    for k, v in enumerate(v_groups[key]):
                        log3("Vehicle OS:"+key+"["+str(k)+"]"+json.dumps(v.genJson())+"\n", "assignWork", self)
            print("assigning work....")

            # log3("unassigned_scheduled_task_groups: "+json.dumps(self.unassigned_scheduled_task_groups), "assignWork", self)
            tbd_unassigned = []
            for vname in self.unassigned_scheduled_task_groups:
                log3("assignwork scheduled checking vehicle: "+vname, "assignWork", self)
                p_task_groups = self.unassigned_scheduled_task_groups[vname]      # flattend per vehicle tasks.
                # log3("p_task_groups: "+json.dumps(p_task_groups), "assignWork", self)
                # print("p_task_groups:", p_task_groups)
                if len(p_task_groups) > 0:
                    print("some work to assign...", self.machine_name)
                    if self.machine_name in vname:
                        vehicle = self.getVehicleByName(vname)

                        if vehicle:
                            # if commander participate work, give the first(0th) work to self.

                            # in case this is an e-commerce work that requires finger print browser, then prepare here.
                            # all_works = [work for tg in p_task_groups for work in tg.get("works", [])]
                            # SC - at this point, p_task_groups should already be a flattened list of tasks
                            batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(p_task_groups, vehicle, self)
                            # batched_tasks now contains the flattened tasks in a vehicle, sorted by start_time, so no longer need complicated structure.
                            log3("arranged for today on this machine...."+vname, "assignWork", self)

                            # handle any buy-side tasks. - no long needs this, will let skill itself take care of it.
                            # self.add_buy_searchs(batched_tasks)

                            # current_tz, current_group = self.setTaskGroupInitialState(p_task_groups[0])
                            self.todays_work["tbd"].append({"name": "automation", "works": batched_tasks, "status": "yet to start", "current widx": 0, "vname": vname, "completed": [], "aborted": []})
                            vidx = 0
                            self.rpa_work_assigned_for_today = True
                            self.updateUnassigned("scheduled", vname, p_task_groups, tbd_unassigned)
                    else:
                        # vidx = i
                        vehicle = self.getVehicleByName(vname)
                        print("VVV:",vehicle)
                        log3("assign work for vehicle:"+vname, "assignWork", self)
                        if vehicle:
                            print("assign for other machine...", vname, vehicle.getVid(), vehicle.getStatus())

                            if not vehicle.getTestDisabled():
                                print("set up schedule for vehicle", vname)
                                await self.vehicleSetupWorkSchedule(vehicle, p_task_groups)
                                if "running" in vehicle.getStatus():
                                    self.updateUnassigned("scheduled", vname, p_task_groups, tbd_unassigned)
            if tbd_unassigned:
                log3("deleting alread assigned schedule task groups", "assignWork", self)
                for vname in tbd_unassigned:
                    del self.unassigned_scheduled_task_groups[vname]

                tbd_unassigned = []
                
            for vname in self.unassigned_reactive_task_groups:
                log3("assignwork reactive checking vehicle: "+vname, "assignWork", self)
                p_task_groups = self.unassigned_reactive_task_groups[vname]      # flattend per vehicle tasks.
                log3("p_task_groups: "+json.dumps(p_task_groups), "assignWork", self)
                if len(p_task_groups) > 0:

                    if self.machine_name in vname:
                        vehicle = self.getVehicleByName(vname)

                        if vehicle:
                            # if commander participate work, give the first(0th) work to self.

                            # in case this is an e-commerce work that requires finger print browser, then prepare here.
                            # all_works = [work for tg in p_task_groups for work in tg.get("works", [])]
                            # SC - at this point, p_task_groups should already be a flattened list of tasks
                            batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(p_task_groups, vehicle, self)
                            # batched_tasks now contains the flattened tasks in a vehicle, sorted by start_time, so no longer need complicated structure.
                            log3("arranged for today on this machine...."+vname, "assignWork", self)

                            #need to do some prep work here if the work needs to download certain files......
                            for tsk in batched_tasks:
                                if tsk["name"] == "sellFullfill_genECBLabels":
                                    tskMission = next((m for i, m in enumerate(self.missions) if m.getMid() == tsk["mid"]), None)
                                    self.downloadForFullfillGenECBLabels(tskMission.getConfig()[1], tsk['config'][1][0])

                            # current_tz, current_group = self.setTaskGroupInitialState(p_task_groups[0])
                            self.reactive_work["tbd"].append({"name": "automation", "works": batched_tasks, "status": "yet to start", "current widx": 0, "vname": vname, "completed": [], "aborted": []})
                            vidx = 0
                            self.rpa_work_assigned_for_today = True
                            self.updateUnassigned("reactive", vname, p_task_groups, tbd_unassigned)
                    else:

                        # vidx = i
                        vehicle = self.getVehicleByName(vname)
                        log3("assign reactive work for vehicle:"+vname, "assignWork", self)
                        if not vehicle.getTestDisabled():
                            await self.vehicleSetupWorkSchedule(vehicle, p_task_groups, False)
                            if "running" in vehicle.getStatus():
                                self.updateUnassigned("reactive", vname, p_task_groups, tbd_unassigned)

            if tbd_unassigned:
                log3("deleting alread assigned reactive task groups", "assignWork", self)
                for vname in tbd_unassigned:
                    del self.unassigned_reactive_task_groups[vname]
                    
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAssignWork:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAssignWork: traceback information not available:" + str(e)
            log3(ex_stat, "assignWork", self)


    def getVehicleByName(self, vname):
        found_vehicle = next((v for i, v in enumerate(self.vehicles) if v.getName() == vname), None)
        return found_vehicle


    async def empower_platoon_with_skills(self, platoon_link, skill_ids):
        # at this point skilll PSK files should be ready to use, send these files to the platton so that can use them.
        for skid in skill_ids:
            found_skill = next((sk for i, sk in enumerate(self.skills) if sk.getSkid() == skid), None)
            if found_skill:
                if found_skill.getPrivacy() == "public":
                    psk_file = self.homepath + found_skill.getPskFileName()
                else:
                    psk_file = self.my_ecb_data_homepath + found_skill.getPskFileName()
                log3("Empowering platoon with skill PSK"+psk_file, "empower_platoon_with_skills", self)
                await self.send_file_to_platoon(platoon_link, "skill psk", psk_file)
            else:
                log3("ERROR: skid NOT FOUND [" + str(skid) + "]", "empower_platoon_with_skills", self)


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
    # 1) check whether need to fetch schedules, this is highest priority, it occurs at 2am, there should be no requested work anyways...
    # 2) checking whether need to do RPA
    #    2a) there are two queues: reactive and scheduled, reactive take higher priority since they are almost always
    #        customer request driven work.
    # the key data structure is self.todays_work["tbd"] which should be an array of either 1 or 2 elements.
    # either 1 or 2 elements depends on the role, if commander_only or platoon, will be 1 element,
    # if commander (which means commander can do tasks too) then there will be 2 elements.
    # in case of 1 element, it will be the actuall bot tasks to be done for platton or the fetch schedule task for Comander Only.
    # in case of 2 elements, the 0th element will be the fetch schedule, the 1st element will be the bot tasks(as a whole)
    # self.todays_work = {"tbd": [], "allstat": "working"}
    def checkNextToRun(self):
        log3("checkNextToRun: todays tbd... "+json.dumps(self.todays_work["tbd"]), "checkNextToRun", self)
        log3("checkNextToRun: reactive tbd... " + json.dumps(self.reactive_work["tbd"]), "checkNextToRun", self)
        nextrun = None
        runType = "scheduled"
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.now()
        ten_hours = timedelta(hours=10)

        # Add 10 hours to the present date and time, some temp hack here to prevent something to run....
        pt = pt + ten_hours

        if len(self.todays_work["tbd"]) > 0:
            if ("Completed" not in self.todays_work["tbd"][0]["status"]) and (self.todays_work["tbd"][0]["name"] == "fetch schedule"):
                # in case the 1st todos is fetch schedule
                log3("set up first todo", "checkNextToRun", self)
                if self.ts2time(int(self.todays_work["tbd"][0]["works"][0]["start_time"]/1)) < pt:
                    log3("set up next run"+json.dumps(self.todays_work["tbd"][0]), "checkNextToRun", self)
                    nextrun = self.todays_work["tbd"][0]
            elif "Completed" not in self.todays_work["tbd"][0]["status"]:
                # in case the 1st todos is an automation task.
                log3("self.todays_work[\"tbd\"][0] : "+json.dumps(self.todays_work["tbd"][0]), "checkNextToRun", self)
                log3("time right now is: "+str(self.time2ts(pt)), "checkNextToRun", self)

                # determin next task group:

                if self.reactive_work["tbd"]:
                    nextrun = self.reactive_work["tbd"][0]
                else:
                    # check schedule work queue only when there is nothing in the reactive work queue
                    current_work_idx = self.todays_work["tbd"][0]["current widx"]

                    # if time is up to run the next work group,
                    if self.todays_work["tbd"][0]["works"]:
                        if self.ts2time(int(self.todays_work["tbd"][0]["works"][current_work_idx]["start_time"])) < pt:
                            log3("next run is now set up......", "checkNextToRun", self)
                            nextrun = self.todays_work["tbd"][0]
                        else:
                            nextrun = {}
                    else:
                        nextrun = {}
                log3("nextRUN>>>>>: "+json.dumps(nextrun), "checkNextToRun", self)
            else:
                log3("now today's schedule work are all finished, only serve the reactive work...", "checkNextToRun", self)
                if self.reactive_work["tbd"]:
                    nextrun = self.reactive_work["tbd"][0]
                log3("nextRUN reactive>>>>>: " + json.dumps(nextrun), "checkNextToRun", self)
        else:
            # if there is no schedule task to run, check whether there is reactive tasks to do, if so, do it asap.
            if self.reactive_work["tbd"]:
                log3("run contracted work netxt", "checkNextToRun", self)
                nextrun = self.reactive_work["tbd"][0]
                runType = "reactive"
            else:
                log3("no contract work to run", "checkNextToRun", self)
        return nextrun, runType

    def getNumUnassignedWork(self):
        num = 0
        for key in self.unassigned_scheduled_task_groups:
            num = num + len(self.unassigned_scheduled_task_groups[key])
        for key in self.unassigned_reactive_task_groups:
            num = num + len(self.unassigned_reactive_task_groups[key])
        return num


    def checkToDos(self):
        log3("checking todos...... "+json.dumps(self.todays_work["tbd"]), "checkToDos", self)
        nextrun = None
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.now()
        ten_hours = timedelta(hours=10)

        # Add 10 hours to the current date and time
        pt = pt + ten_hours
        if len(self.todays_work["tbd"]) > 0:
            if ("Completed" not in self.todays_work["tbd"][0]["status"]) and (self.todays_work["tbd"][0]["name"] == "fetch schedule"):
                # in case the 1st todos is fetch schedule
                log3("checking fetch time", "checkToDos", self)
                if self.ts2time(int(self.todays_work["tbd"][0]["works"]["eastern"][0]["other_works"][0]["start_time"]/1)) < pt:
                    nextrun = self.todays_work["tbd"][0]
            elif "Completed" not in self.todays_work["tbd"][0]["status"]:
                # in case the 1st todos is an automation task.
                log3("eastern:"+json.dumps(self.todays_work["tbd"][0]["works"]["eastern"]), "checkToDos", self)
                log3("self.todays_work[\"tbd\"][0] : "+json.dumps(self.todays_work["tbd"][0]), "checkToDos", self)
                tz = self.todays_work["tbd"][0]["current tz"]

                bith = self.todays_work["tbd"][0]["current bidx"]

                # determin next task group:
                current_bw_idx = self.todays_work["tbd"][0]["current widx"]
                current_other_idx = self.todays_work["tbd"][0]["current oidx"]
                log3("time right now is: "+self.time2ts(pt)+"("+str(pt)+")"+datetime.now().strftime('%Y-%m-%d %H:%M:%S')+" tz:"+tz+" bith:"+str(bith)+" bw idx:"+str(current_bw_idx)+"other idx:"+str(current_other_idx), "checkToDos", self)

                if current_bw_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"]):
                    current_bw_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["bw_works"][current_bw_idx]["start_time"]
                    log3("current bw start time: " + str(current_bw_start_time), "checkToDos", self)
                else:
                    # just give it a huge number so that, this group won't get run
                    current_bw_start_time = 1000
                log3("current_bw_start_time: "+str(current_bw_start_time), "checkToDos", self)

                if current_other_idx < len(self.todays_work["tbd"][0]["works"][tz][bith]["other_works"]):
                    current_other_start_time = self.todays_work["tbd"][0]["works"][tz][bith]["other_works"][current_other_idx]["start_time"]
                    log3("current bw start time: " + str(current_other_start_time), "checkToDos", self)
                else:
                    # in case, all just give it a huge number so that, this group won't get run
                    current_other_start_time = 1000
                log3("current_other_start_time: "+current_other_start_time, "checkToDos", self)

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
                log3("tz: "+tz+" bith: "+str(bith)+" grp: "+grp+" wjth: "+str(wjth), "checkToDos", self)

                if wjth >= 0:
                    if self.ts2time(int(self.todays_work["tbd"][0]["works"][tz][bith][grp][wjth]["start_time"]/3)) < pt:
                        self.showMsg("next run is now set up......")
                        nextrun = self.todays_work["tbd"][0]
                log3("nextRUN>>>>>: "+json.dumps(nextrun), "checkToDos", self)
        return nextrun


    def findWorksToBeRetried(self, todos):
        retries = copy.deepcopy(todos)
        log3("MISSIONS needs retry: "+str(retries), "findWorksToBeRetried", self)
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

        log3("MISSIONS needs retry: "+str(retries), "findMissonsToBeRetried", self)
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
            skill_file = self.my_ecb_data_homepath + "/my_skills/" + skname + "/scripts/" + skname + ".psk"

        log3("loadSKILLFILE: "+skill_file, "loadSkillFile", self)
        stepKeys = readPSkillFile(skname, skill_file, lvl=0)

        return stepKeys


    # fill in real address to some placeholders
    def reAddrAndUpdateSteps(self, pskJson, init_step_idx, work_settings):
        # self.showMsg("PSK JSON::::: "+json.dumps(pskJson))
        newPskJson = {}
        log3("New Index:"+str(init_step_idx), "reAddrAndUpdateSteps", self)
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
                        log3("REPLACED WORKSETTINGS HERE: "+new_key+" :::: "+json.dumps(newPskJson[new_key]), "reAddrAndUpdateSteps", self)

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
            mid2br = worksettings["mid"]

            if (not self.checkMissionAlreadyRun(worksettings)) or mid2br in self.general_settings.get("mids_forced_to_run", []):
                log3("worksettings: bid, mid "+str(worksettings["botid"])+" "+str(worksettings["mid"])+" "+str(worksettings["midx"])+" "+json.dumps([m.getFingerPrintProfile() for m in self.missions]), "runRPA", self)

                bot_idx = next((i for i, b in enumerate(self.bots) if str(b.getBid()) == str(worksettings["botid"])), -1)
                if bot_idx >= 0:
                    log3("found BOT to be run......"+str(self.bots[bot_idx].getEmail()), "runRPA", self)
                    running_bot = self.bots[bot_idx]

                rpaScripts = []

                # generate walk skills on the fly.
                self.running_mission = self.missions[worksettings["midx"]]

                # no finger print profile, no run for ads.
                if 'ads' in self.running_mission.getCusPAS() and self.running_mission.getFingerPrintProfile() == "":
                    log3("ERROR ADS mission has no profile: " + str(self.running_mission.getMid()) + " " + self.running_mission.getCusPAS() + " " + self.running_mission.getFingerPrintProfile(), "runRPA", self)
                    runResult = "ErrorRPA ADS mission has no profile " + str(self.running_mission.getMid())
                    self.update1MStat(worksettings, runResult)
                    self.update1WorkRunStatus(worksTBD, worksettings["midx"])
                else:
                    log3("current RUNNING MISSION: "+json.dumps(self.running_mission.genJson()), "runRPA", self)
                    log3("RPA all skill ids:"+json.dumps([sk.getSkid() for sk in self.skills]), "runRPA", self)
                    if self.running_mission.getSkills() != "":
                        rpaSkillIdWords = self.running_mission.getSkills().split(",")
                        log3("current RUNNING MISSION SKILL: "+json.dumps(self.running_mission.getSkills()), "runRPA", self)
                        rpaSkillIds = [int(skidword.strip()) for skidword in rpaSkillIdWords]

                        log3("rpaSkillIds: "+json.dumps(rpaSkillIds)+" "+str(type(rpaSkillIds[0]))+" "+" running mission id: "+str(self.running_mission.getMid()), "runRPA", self)

                        # get skills data structure by IDs
                        all_skids = [sk.getSkid() for sk in self.skills]
                        log3("all skills ids:"+json.dumps([sk.getSkid() for sk in self.skills]), "runRPA", self)
                        rpaSkillIds = list(dict.fromkeys(rpaSkillIds))
                        log3("rpaSkillIds:"+json.dumps(rpaSkillIds), "runRPA", self)

                        relevant_skills = [self.skills[all_skids.index(skid)] for skid in rpaSkillIds]

                        log3("N relevant skills:"+str(len(relevant_skills))+json.dumps([sk.getSkid() for sk in relevant_skills]), "runRPA", self)
                        relevant_skill_ids = [sk.getSkid() for sk in self.skills if sk.getSkid() in rpaSkillIds]
                        relevant_skill_ids = list(set(relevant_skill_ids))
                        log3("relevant skills ids: "+json.dumps(relevant_skill_ids), "runRPA", self)
                        dependent_skids=[]
                        for sk in relevant_skills:
                            log3("add dependency: " + json.dumps(sk.getDependencies()) + "for skill#" + str(sk.getSkid()), "runRPA", self)
                            dependent_skids = dependent_skids + sk.getDependencies()

                        dependent_skids = list(set(dependent_skids))
                        dependent_skids = [skid for skid in dependent_skids if skid not in relevant_skill_ids]
                        log3("all dependencies: "+json.dumps(dependent_skids), "runRPA", self)

                        dependent_skills = [sk for sk in self.skills if sk.getSkid() in dependent_skids]
                        relevant_skills = relevant_skills + dependent_skills
                        relevant_skill_ids = relevant_skill_ids + dependent_skids

                        if len(relevant_skill_ids) < len(rpaSkillIds):
                            s = set(relevant_skill_ids)
                            missing = [x for x in rpaSkillIds if x not in s]
                            log3("ERROR: Required Skills not found:"+json.dumps(missing), "runRPA", self)


                        log3("all skids involved in this skill: "+json.dumps([sk.getSkid() for sk in relevant_skills]), "runRPA", self)
                        all_skill_codes = []
                        step_idx = 0
                        for sk in relevant_skills:
                            log3("settingSKKKKKKKK: "+str(sk.getSkid())+" "+sk.getName()+" "+str(worksettings["b_email"]), "runRPA", self)
                            setWorkSettingsSkill(worksettings, sk)
                            # self.showMsg("settingSKKKKKKKK: "+json.dumps(worksettings, indent=4))

                            # readPSkillFile will remove comments. from the file
                            if sk.getPrivacy() == "public":
                                sk_dir = self.homepath
                            else:
                                sk_dir = self.my_ecb_data_homepath
                            pskJson = readPSkillFile(worksettings["name_space"], sk_dir+sk.getPskFileName(), lvl=0)
                            # self.showMsg("RAW PSK JSON::::"+json.dumps(pskJson))

                            # now regen address and update settings, after running, pskJson will be updated.
                            step_idx, pskJson = self.reAddrAndUpdateSteps(pskJson, step_idx, worksettings)
                            # self.showMsg("AFTER READDRESS AND UPDATE PSK JSON::::" + json.dumps(pskJson))

                            addNameSpaceToAddress(pskJson, worksettings["name_space"], lvl=0)

                            # self.showMsg("RUNNABLE PSK JSON::::"+json.dumps(pskJson))

                            # save the file to a .rsk file (runnable skill) which contains json only with comments stripped off from .psk file by the readSkillFile function.
                            rskFileName = sk_dir + sk.getPskFileName().split(".")[0] + ".rsk"
                            rskFileDir = os.path.dirname(rskFileName)
                            if not os.path.exists(rskFileDir):
                                os.makedirs(rskFileDir)
                            log3("rskFileName: "+rskFileName+" step_idx: "+str(step_idx), "runRPA", self)
                            with open(rskFileName, "w") as outfile:
                                json.dump(pskJson, outfile, indent=4)
                            outfile.close()

                            all_skill_codes.append({"ns": worksettings["name_space"], "skfile": rskFileName})

                        log3("all_skill_codes: "+json.dumps(all_skill_codes), "runRPA", self)

                        rpa_script = prepRunSkill(all_skill_codes)
                        # log3("generated ready2run: "+json.dumps(rpa_script), "runRPA", self)
                        # self.showMsg("generated psk: " + str(len(rpa_script.keys())))

                        # doing this just so that the code below can run multiple codes if needed. but in reality
                        # prepRunSkill put code in a global var "skill_code", even if there are multiple scripts,
                        # this has to be corrected because, the following append would just have multiple same
                        # skill_code...... SC, but for now this is OK, there is no multiple script scenario in
                        # forseaable future.
                        rpaScripts.append(rpa_script)
                        # self.showMsg("rpaScripts:["+str(len(rpaScripts))+"] "+json.dumps(rpaScripts))
                        log3("rpaScripts:["+str(len(rpaScripts))+"] "+str(len(relevant_skills))+" "+str(worksettings["midx"])+" "+str(len(self.missions)), "runRPA", self)

                        # Before running do the needed prep to get "fin" input parameters ready.
                        # this is the case when this mission is run as an independent server, the input
                        # of the mission will come from the another computer, and there might even be
                        # files to be downloaded first as the input to the mission.
                        if worksettings["as_server"]:
                            log3("SETTING MISSSION INPUT:"+json.dumps(self.running_mission.getConfig()), "runRPA", self)
                            setMissionInput(self.running_mission.getConfig())


                        # (steps, mission, skill, mode="normal"):
                        # it_items = (item for i, item in enumerate(self.skills) if item.getSkid() == rpaSkillIds[0])
                        # self.showMsg("it_items: "+json.dumps(it_items))
                        # for it in it_items:
                        #     self.showMsg("item: "+str(it.getSkid()))
                        # running_skill = next((item for i, item in enumerate(self.skills) if item.getSkid() == int(rpaSkillIds[0])), -1)
                        # self.showMsg("running skid:"+str(rpaSkillIds[0])+"len(self.skills): "+str(len(self.skills))+"skill 0 skid: "+str(self.skills[0].getSkid()))
                        # self.showMsg("running skill: "+json.dumps(running_skill))
                        # runStepsTask = asyncio.create_task(rpaRunAllSteps(rpa_script, self.missions[worksettings["midx"]], relevant_skills[0], rpa_msg_queue, monitor_msg_queue))
                        # runResult = await runStepsTask

                        log3("BEFORE RUN: " + worksettings["b_email"], "runRPA", self)
                        runResult = await rpaRunAllSteps(rpa_script, self.missions[worksettings["midx"]], relevant_skills[0], rpa_msg_queue, monitor_msg_queue)

                        # for retry test purpose:
                        # runResult = "Incomplete Error"

                        # finished 1 mission, update status and update pointer to the next one on the list.... and be done.
                        # the timer tick will trigger the run of the next mission on the list....
                        log3("UPDATEing completed mission status:: "+str(worksettings["midx"])+"RUN result:"+runResult, "runRPA", self)
                        self.update1MStat(worksettings, runResult)
                        self.update1WorkRunStatus(worksTBD, worksettings["midx"])
                    else:
                        log3("UPDATEing ERROR mmission status:: " + str(worksettings["midx"]) + "RUN result: " + "Incomplete: ERRORRunRPA:-1", "runRPA", self)
                        self.update1MStat(worksettings, "Incomplete: ERRORRunRPA:No Skill To Run")
                        self.update1WorkRunStatus(worksTBD, worksettings["midx"])
                        raise Exception('ERROR: NO SKILL TO RUN!')
            else:
                log3("mission already ran " + str(worksettings["mid"]), "runRPA", self)
                log3("mission ALREADY Completed today: " + str(worksettings["mid"]), "runRPA", self)
                runResult = "Completed:0 Skip Rerun"
                self.update1WorkRunStatus(worksTBD, worksettings["midx"])

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorRanRPA:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorRanRPA: traceback information not available:" + str(e)
            log3(ex_stat, "runRPA", self)
            runResult = "Incomplete: ERRORRunRPA:-1"

        log3("botid, mid:"+str(worksettings["botid"]) + " "+str(worksettings["mid"]), "runRPA", self)
        return worksettings["botid"], worksettings["mid"], runResult


    # run one bot one time slot at a time，for 1 bot and 1 time slot, there should be only 1 mission running
    async def run1ManagerMission(self, mission, self_in_queue, rpa_msg_queue, monitor_msg_queue):
        global rpaConfig
        global skill_code

        all_done = False
        try:
            worksettings = getWorkRunSettings(self, mission)
            log3("manager worksettings: bid, mid "+str(worksettings["botid"])+" "+str(worksettings["mid"])+" "+str(worksettings["midx"])+" "+json.dumps([m.getFingerPrintProfile() for m in self.missions]), "runRPA", self)

            print("manager work settings:", worksettings)
            rpaScripts = []

            # generate walk skills on the fly.
            self.running_manager_mission = mission

            # no finger print profile, no run for ads.
            if 'ads' in self.running_manager_mission.getCusPAS() and self.running_manager_mission.getFingerPrintProfile() == "":
                log3("ERROR ADS mission has no profile: " + str(self.running_manager_mission.getMid()) + " " + self.running_mission.getCusPAS() + " " + self.running_mission.getFingerPrintProfile(), "runRPA", self)
                runResult = "ErrorRPA ADS mission has no profile " + str(self.running_manager_mission.getMid())
            else:
                log3("current RUNNING MISSION: "+json.dumps(self.running_manager_mission.genJson()), "runRPA", self)
                log3("RPA all skill ids:"+json.dumps([sk.getSkid() for sk in self.skills]), "runRPA", self)
                if self.running_manager_mission.getSkills() != "":
                    rpaSkillIdWords = self.running_manager_mission.getSkills().split(",")
                    log3("current RUNNING MISSION SKILL: "+json.dumps(self.running_manager_mission.getSkills()), "runRPA", self)
                    rpaSkillIds = [int(skidword.strip()) for skidword in rpaSkillIdWords]

                    log3("rpaSkillIds: "+json.dumps(rpaSkillIds)+" "+str(type(rpaSkillIds[0]))+" "+" running mission id: "+str(self.running_manager_mission.getMid()), "runRPA", self)

                    # get skills data structure by IDs
                    all_skids = [sk.getSkid() for sk in self.skills]
                    log3("all skills ids:"+json.dumps([sk.getSkid() for sk in self.skills]), "runRPA", self)
                    rpaSkillIds = list(dict.fromkeys(rpaSkillIds))
                    log3("rpaSkillIds:"+json.dumps(rpaSkillIds), "runRPA", self)

                    relevant_skills = [self.skills[all_skids.index(skid)] for skid in rpaSkillIds]

                    log3("N relevant skills:"+str(len(relevant_skills))+json.dumps([sk.getSkid() for sk in relevant_skills]), "runRPA", self)
                    relevant_skill_ids = [sk.getSkid() for sk in self.skills if sk.getSkid() in rpaSkillIds]
                    relevant_skill_ids = list(set(relevant_skill_ids))
                    log3("relevant skills ids: "+json.dumps(relevant_skill_ids), "runRPA", self)
                    dependent_skids=[]
                    for sk in relevant_skills:
                        log3("add dependency: " + json.dumps(sk.getDependencies()) + "for skill#" + str(sk.getSkid()), "runRPA", self)
                        dependent_skids = dependent_skids + sk.getDependencies()

                    dependent_skids = list(set(dependent_skids))
                    dependent_skids = [skid for skid in dependent_skids if skid not in relevant_skill_ids]
                    log3("all dependencies: "+json.dumps(dependent_skids), "runRPA", self)

                    dependent_skills = [sk for sk in self.skills if sk.getSkid() in dependent_skids]
                    relevant_skills = relevant_skills + dependent_skills
                    relevant_skill_ids = relevant_skill_ids + dependent_skids

                    if len(relevant_skill_ids) < len(rpaSkillIds):
                        s = set(relevant_skill_ids)
                        missing = [x for x in rpaSkillIds if x not in s]
                        log3("ERROR: Required Skills not found:"+json.dumps(missing), "runRPA", self)


                    log3("all skids involved in this skill: "+json.dumps([sk.getSkid() for sk in relevant_skills]), "runRPA", self)
                    all_skill_codes = []
                    step_idx = 0
                    for sk in relevant_skills:
                        log3("settingSKKKKKKKK: "+str(sk.getSkid())+" "+sk.getName()+" "+str(worksettings["b_email"]), "runRPA", self)
                        setWorkSettingsSkill(worksettings, sk)
                        # self.showMsg("settingSKKKKKKKK: "+json.dumps(worksettings, indent=4))

                        # readPSkillFile will remove comments. from the file
                        if sk.getPrivacy() == "public":
                            sk_dir = self.homepath
                        else:
                            sk_dir = self.my_ecb_data_homepath
                        pskJson = readPSkillFile(worksettings["name_space"], sk_dir+sk.getPskFileName(), lvl=0)
                        # self.showMsg("RAW PSK JSON::::"+json.dumps(pskJson))

                        # now regen address and update settings, after running, pskJson will be updated.
                        step_idx, pskJson = self.reAddrAndUpdateSteps(pskJson, step_idx, worksettings)
                        # self.showMsg("AFTER READDRESS AND UPDATE PSK JSON::::" + json.dumps(pskJson))

                        addNameSpaceToAddress(pskJson, worksettings["name_space"], lvl=0)

                        # self.showMsg("RUNNABLE PSK JSON::::"+json.dumps(pskJson))

                        # save the file to a .rsk file (runnable skill) which contains json only with comments stripped off from .psk file by the readSkillFile function.
                        rskFileName = sk_dir + sk.getPskFileName().split(".")[0] + ".rsk"
                        rskFileDir = os.path.dirname(rskFileName)
                        if not os.path.exists(rskFileDir):
                            os.makedirs(rskFileDir)
                        log3("rskFileName: "+rskFileName+" step_idx: "+str(step_idx), "runRPA", self)
                        with open(rskFileName, "w") as outfile:
                            json.dump(pskJson, outfile, indent=4)
                        outfile.close()

                        all_skill_codes.append({"ns": worksettings["name_space"], "skfile": rskFileName})

                    log3("all_skill_codes: "+json.dumps(all_skill_codes), "runRPA", self)

                    rpa_script = prepRunSkill(all_skill_codes)
                    # log3("generated ready2run: "+json.dumps(rpa_script), "runRPA", self)
                    # self.showMsg("generated psk: " + str(len(rpa_script.keys())))

                    # doing this just so that the code below can run multiple codes if needed. but in reality
                    # prepRunSkill put code in a global var "skill_code", even if there are multiple scripts,
                    # this has to be corrected because, the following append would just have multiple same
                    # skill_code...... SC, but for now this is OK, there is no multiple script scenario in
                    # forseaable future.
                    rpaScripts.append(rpa_script)
                    # self.showMsg("rpaScripts:["+str(len(rpaScripts))+"] "+json.dumps(rpaScripts))
                    log3("rpaScripts:["+str(len(rpaScripts))+"] "+str(len(relevant_skills))+" "+str(worksettings["midx"])+" "+str(len(self.missions)), "runRPA", self)

                    # Before running do the needed prep to get "fin" input parameters ready.
                    # this is the case when this mission is run as an independent server, the input
                    # of the mission will come from the another computer, and there might even be
                    # files to be downloaded first as the input to the mission.
                    if worksettings["as_server"]:
                        log3("SETTING MISSSION INPUT:"+json.dumps(self.running_manager_mission.getConfig()), "runRPA", self)
                        setMissionInput(self.running_manager_mission.getConfig())


                    log3("MANAGER BEFORE RUN: " + worksettings["b_email"], "runRPA", self)
                    runResult = await rpaRunAllSteps(rpa_script, self.running_manager_mission, relevant_skills[0], rpa_msg_queue, monitor_msg_queue)


                    # finished 1 mission, update status and update pointer to the next one on the list.... and be done.
                    # the timer tick will trigger the run of the next mission on the list....
                    log3("UPDATEing 1 completed mmission status:: "+str(worksettings["midx"])+"RUN result:"+runResult, "runRPA", self)
                    mission.setResult(runResult)
                else:
                    log3("UPDATEing ERROR mmission status:: " + str(worksettings["midx"]) + "RUN result: " + "Incomplete: ERRORRunRPA:-1", "runRPA", self)
                    mission.setResult("Incomplete: ERRORRunRPA:-1")
                    raise Exception('ERROR: NO SKILL TO RUN!')


        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorRun1ManagerMission:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorRun1ManagerMission: traceback information not available:" + str(e)

            print(ex_stat)
            log3(ex_stat, "run1managerMission", self)
            runResult = "Incomplete: ERRORRunRPA:-1"

        log3("manager mission run result:"+json.dumps(runResult), "runRPA", self)
        return runResult

    def checkMissionAlreadyRun(self, worksettings):
        alreadyRun = False
        mid = str(worksettings["mid"])
        missionReportFile = worksettings["log_path_prefix"] + "run_result.json"
        print("check mission already run missionReportFile:", missionReportFile)
        if os.path.exists(missionReportFile):
            with open(missionReportFile, "r", encoding="utf-8") as mrf:
                m_report_json = json.load(mrf)
                if "Completed" in m_report_json[mid]:
                    alreadyRun = True
        return alreadyRun

    def save1MStatToFile(self, worksettings, result):
        # save mission run status to a local file. so that if re-run and we realized the mission
        # has already being completed, we don't run it again. of course we'd have a force run
        # setting in general settings, such that if set, that would overide it.
        mid = worksettings["mid"]
        mission = self.missions[worksettings["midx"]]
        missionReportFile = worksettings["log_path_prefix"]+"run_result.json"
        print("saving missionReportFile:", missionReportFile)
        # read-modify-write
        if os.path.exists(missionReportFile):
            with open(missionReportFile, "r", encoding="utf-8") as mrf:
                m_report_json = json.load(mrf)
            m_report_json[mid] = result
            with open(missionReportFile, "w", encoding="utf-8") as mrf:
                json.dump(m_report_json, mrf, indent=4)
        else:
            # no file yet, just write it.
            os.makedirs(worksettings["log_path_prefix"], exist_ok=True)
            with open(missionReportFile, "w", encoding="utf-8") as mrf:
                m_report_json = {mid: result}
                json.dump(m_report_json, mrf, indent=4)


    def update1MStat(self, worksettings, result):
        midx = worksettings["midx"]
        log3("1 mission run completed."+str(midx)+" "+str(self.missions[midx].getMid())+" "+str(self.missions[midx].getRetry())+" "+str(self.missions[midx].getNRetries())+"status:"+result, "update1MStat", self)
        self.missions[midx].setStatus(result)
        self.save1MStatToFile(worksettings, result)
        retry_count = self.missions[midx].getNRetries()
        self.missions[midx].setNRetries(retry_count + 1)
        log3("update1MStat:"+str(midx)+":"+str(self.missions[midx].getMid())+":"+str(self.missions[midx].getNRetries()), "update1MStat", self)
        bid = self.missions[midx].getBid()

        # if platoon send this updated info to commander boss
        if "Platoon" in self.host_role:
            self.sendCommanderMissionsStatMsg([self.missions[midx].getMid()])
            missionResultFiles = self.getMissionResultFileNames(self.missions[midx])
            if missionResultFiles:
                self.send_mission_result_files_to_commander(self.commanderXport, self.missions[midx].getMid(), "zip", missionResultFiles)
        elif "Commander" in self.host_role:
            self.updateMissionsStatToCloud([self.missions[midx]])

    # update mission status to the cloud db, and to local data structure, local DB, and to chat？
    # "mid": mid,
    # "botid": self.missions[mid].getBid(),
    # "sst": self.missions[mid].getEstimatedStartTime(),
    # "sd": self.missions[mid].getEstimatedRunTime(),
    # "ast": self.missions[mid].getActualStartTime(),
    # "aet": self.missions[mid].getActualEndTime(),
    # "status": m_stat,
    # "error": m_err
    def updateMStats(self, mStats):
        inMids = [m["mid"] for m in mStats]
        foundMissions = []
        for mstat in mStats:
            foundMission = next((m for i, m in enumerate(self.missions) if m.getMid() == mstat["mid"]), None)
            if foundMission:
                foundMission.setStatus= mstat.get("status", foundMission.getStatus())
                if "ast" in mstat:
                    mStartTime = mstat.get("ast", foundMission.getActualStartTime())
                    mStartDate = mstat.get("ast", foundMission.getAsd())
                    foundMission.setActualStartTime = mStartTime
                    foundMission.setAsd = mStartDate

                if "aet" in mstat:
                    mEndTime = mstat.get("aet", foundMission.getActualEndTime())
                    mEndDate = mstat.get("act", foundMission.getAcd())

                    foundMission.setActualEndTime = mEndTime
                    foundMission.setAcd = mEndDate

                foundMission.setError = mstat.get("error", foundMission.getError())
                foundMissions.append(foundMission)

        # update missions to cloud DB and local DB
        if foundMissions:
            self.updateMissions(foundMissions)

    # check where a mission is supposed to return any resulting files, if so, return the list of full path file names.
    def getMissionResultFileNames(self, mission):
        # this is really a case by case thing, the scheme is really in the mission.config
        # if there are any expected outfiles, they ought to be in mission.config.
        # and mission.config json format depends on the mission itself.
        mConfig = mission.getConfig()
        if "out_files" in mConfig:
            return mConfig["out_files"]
        else:
            return []


    def updateMissionsStatToCloud(self, missions):
        mstats = [{"mid": m.getMid(), "status": m.getStatus()} for m in missions]
        send_update_missions_ex_status_to_cloud(self.session, mstats, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndPoint())


    def updateUnassigned(self, tg_type, vname, task_group, tbd):
        tg_mids = [tsk["mid"] for tsk in task_group]
        if tg_type == "scheduled":
            if vname in self.unassigned_scheduled_task_groups:
                # maybe an expensive way of remove a task from the group.
                self.unassigned_scheduled_task_groups[vname] = [tsk for tsk in self.unassigned_scheduled_task_groups[vname] if tsk['mid'] not in tg_mids]

                # if this vehcle no longer has unassigned work, then remove this vehicle from unassigned_task_group
                if not self.unassigned_scheduled_task_groups[vname]:
                    tbd.append(vname)
                    log3("Remove alredy assigned mission from unassigned scheduled list", "updateUnassigned", self)
            else:
                log3(vname+" NOT FOUND in unassigned scheduled work group", "updateUnassigned", self)
        elif tg_type == "reactive":
            if vname in self.unassigned_reactive_task_groups:
                # maybe an expensive way of remove a task from the group.
                self.unassigned_reactive_task_groups[vname] = [tsk for tsk in self.unassigned_reactive_task_groups[vname] if tsk['mid'] not in tg_mids]

                # if this vehcle no longer has unassigned work, then remove this vehicle from unassigned_task_group
                if not self.unassigned_reactive_task_groups[vname]:
                    tbd.append(vname)
                    log3("Remove already assigned mission from unassigned reactive list", "updateUnassigned", self)
            else:
                log3(vname+" NOT FOUND in unassigned reactive work group", "updateUnassigned", self)

        # find and delete mission from the work group.

    #update next mission pointer, return -1 if exceed the end of it.
    def update1WorkRunStatus(self, worksTBD, midx):

        this_stat = self.missions[midx].getStatus()
        worksTBD["current widx"] = worksTBD["current widx"] + 1

        log3("updatin 1 work run status:"+this_stat+" "+str(worksTBD["current widx"])+" "+str(len(worksTBD["works"])), "update1WorkRunStatus", self)

        if worksTBD["current widx"] >= len(worksTBD["works"]):
            worksTBD["current widx"] = self.checkTaskGroupCompleteness(worksTBD)
            log3("current widx pointer after checking retries:"+str(worksTBD["current widx"])+" "+str(len(worksTBD["works"])), "update1WorkRunStatus", self)
            if worksTBD["current widx"] >= len(worksTBD["works"]):
                log3("current work group is COMPLETED.", "update1WorkRunStatus", self)
                worksTBD["status"] = "Completed"


        log3("current widx pointer now at:"+str(worksTBD["current widx"])+" worksTBD status: "+worksTBD["status"], "update1WorkRunStatus", self)


    def checkTaskGroupCompleteness(self, worksTBD):
        mids = [w["mid"] for w in worksTBD["works"]]
        next_run_index = len(mids)
        for j, mid in enumerate(mids):
            midx = next((i for i, m in enumerate(self.missions) if m.getMid() == mid), -1)
            if midx != -1:
                this_stat = self.missions[midx].getStatus()
                n_2b_retried = self.missions[midx].getRetry()
                retry_count = self.missions[midx].getNRetries()
                log3("check retries: "+str(mid)+" "+str(self.missions[midx].getMid())+" n2b retries: "+str(n_2b_retried)+" n retried: "+str(retry_count), "checkTaskGroupCompleteness", self)
                if "Complete" not in this_stat and retry_count < n_2b_retried:
                    log3("scheduing retry#:"+str(j)+" MID: "+str(mid), "checkTaskGroupCompleteness", self)
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

        log3("TZ:"+tz+" GRP:"+grp+" BIDX:"+str(bidx)+" WIDX:"+str(widx)+" OIDX:"+str(oidx)+" THIS STATUS:"+this_stat, "updateRunStatus", self)

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
                            log3("SWITCHED BOT:"+str(bidx), "updateRunStatus", self)
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
                    log3("SWITCHED TZ: "+tz, "updateRunStatus", self)
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
                    log3("all workdsTBD exhausted...", "updateRunStatus", self)
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
            n_retries = self.missions[midx].getNRetries()
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

        log3("MISSIONS needs retry: "+tz+" "+str(bid)+" "+grp+" "+str(mid), "findFirstMissonsToBeRetried", self)
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
        if ts < 0:      # in case of timeslot is -1 it means run it asap, so make it 0 zero time of today.
            ts = 0
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
        self.working_state = "running_working"
        task_mission = self.missions[task.mid]
        # run all the todo steps
        # (steps, mission, skill, mode="normal"):
        runResult = rpaRunAllSteps(task.todos, task_mission.parent_settings)


    def runADSProfileConverter(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open ADS Profile File"),
            '',
            QApplication.translate("QFileDialog", "Text Files (*.txt)")
        )

        try:
            if exists(filename):
                print("file name:", filename)
                convertTxtProfiles2DefaultXlsxProfiles([filename], self)


        except IOError:
            QMessageBox.information(self, "Unable to open/save file: %s" % filename)


    def runADSProfileBatchToSingles(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open ADS Profile File"),
            '',
            QApplication.translate("QFileDialog", "Text Files (*.txt)")
        )

        try:
            if exists(filename):
                print("file name:", filename)
                updateIndividualProfileFromBatchSavedTxt(self, filename)

        except IOError:
            QMessageBox.information(self, "Error", "Unable to open/save file: %s" % filename)




    def showAbout(self):
        msgBox = QMessageBox()
        msgBox.setWindowTitle(QApplication.translate("QMessageBox", "ECBot About"))
        msgBox.setText(QApplication.translate("QMessageBox", "MAIPPS LLC E-Commerce Bots. \n (V1.01 2024-10-11 AIPPS LLC) \n"))
        # msgBox.setInformativeText("Do you want to save your changes?")
        # msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        # msgBox.setDefaultButton(QMessageBox.Save)
        ret = msgBox.exec()

    def gotoUserGuide(self):
        url="https://www.maipps.com"
        webbrowser.open(url, new=0, autoraise=True)


    def gotoForum(self):
        url="https://www.maipps.com"
        webbrowser.open(url, new=0, autoraise=True)

    def gotoMyAccount(self):
        url="https://www.maipps.com"
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
                "org": new_bot.getOrg(),
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
                "backemailpw": new_bot.getBackEmPW(),
                "ebpw": new_bot.getAcctPw(),
                "backemail_site": new_bot.getBackEmSite(),
                "createon": new_bot.getCreateOn(),
                "vehicle": new_bot.getVehicle()
            })
        jresp = send_add_bots_request_to_cloud(self.session, new_bots, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())

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
                self.updateBotRelatedVehicles(new_bots[i])
            self.selected_bot_row = self.botModel.rowCount() - 1
            self.selected_bot_item = self.botModel.item(self.selected_bot_row)
            # now add bots to local DB.
            if not self.debug_mode:
                self.bot_service.insert_bots_batch(jbody, api_bots)

    def updateBots(self, bots, localOnly=False):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        api_bots = []
        for abot in bots:
            api_bots.append({
                "bid": abot.getBid(),
                "owner": self.owner,
                "roles": abot.getRoles(),
                "org": abot.getOrg(),
                "pubbirthday": abot.getPubBirthday(),
                "gender": abot.getGender(),
                "location": abot.getLocation(),
                "levels": abot.getLevels(),
                "birthday": abot.getBirthdayTxt(),
                "interests": abot.getInterests(),
                "status": abot.getStatus(),
                "delDate": abot.getInterests(),
                "createon": abot.getCreateOn(),
                "vehicle": abot.getVehicle(),
                "name": abot.getName(),
                "pseudoname": abot.getPseudoName(),
                "nickname": abot.getNickName(),
                "addr": abot.getAddr(),
                "shipaddr": abot.getShippingAddr(),
                "phone": abot.getPhone(),
                "email": abot.getEmail(),
                "epw": abot.getEmPW(),
                "backemail": abot.getBackEm(),
                "backemailpw": abot.getBackEmPW(),
                "ebpw": abot.getAcctPw(),
                "backemail_site": abot.getAcctPw()
            })
            # self.updateBotRelatedVehicles(abot)
        if not localOnly:
            jresp = send_update_bots_request_to_cloud(self.session, bots, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
            if "errorType" in jresp:
                screen_error = True
                self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"]), "ERROR Info: "+json.dumps(jresp["errorInfo"]))
            else:
                print("update bot jresp:", jresp)
                # jbody = jresp["body"]
                jbody = jresp
                if jbody['numberOfRecordsUpdated'] == len(bots):
                    for i, abot in enumerate(bots):
                        api_bots[i]["vehicle"] = abot.getVehicle()
                    self.bot_service.update_bots_batch(api_bots)
                else:
                    self.showMsg("WARNING: bot NOT updated in Cloud!")
        else:
            print("updating local only....")
            self.bot_service.update_bots_batch(api_bots)

    # update in cloud, local DB, and local Memory
    def updateBotsWithJsData(self, bjs, localOnly=False):
        try:
            api_bots = []
            for abot in bjs:
                api_bots.append({
                    "bid": abot["pubAttributes"]["bid"],
                    "owner": self.owner,
                    "roles": abot["pubAttributes"]["roles"],
                    "org": abot["pubAttributes"]["org"],
                    "pubbirthday": abot["pubAttributes"]["pubbirthday"],
                    "gender": abot["pubAttributes"]["gender"],
                    "location": abot["pubAttributes"]["location"],
                    "levels": abot["pubAttributes"]["levels"],
                    "birthday": abot["privateProfile"]["birthday"],
                    "interests": abot["pubAttributes"]["interests"],
                    "status": abot["pubAttributes"]["status"],
                    "delDate": abot["pubAttributes"]["delDate"],
                    "createon": abot["privateProfile"]["createon"],
                    "vehicle": abot["pubAttributes"]["vehicle"],
                    "name": abot["privateProfile"]["bid"],
                    "pseudoname": abot["pubAttributes"]["pseudo_name"],
                    "nickname": abot["pubAttributes"]["pseudo_nick_name"],
                    "addr": abot["privateProfile"]["addr"],
                    "shipaddr": abot["privateProfile"]["shipping_addr"],
                    "phone": abot["privateProfile"]["phone"],
                    "email": abot["privateProfile"]["email"],
                    "epw": abot["privateProfile"]["email_pw"],
                    "backemail": abot["privateProfile"]["backup_email"],
                    "backemailpw": abot["privateProfile"]["backup_email_pw"],
                    "ebpw": abot["privateProfile"]["acct_pw"],
                    "backemail_site": abot["privateProfile"]["backup_email_site"],
                })
                self.updateBotRelatedVehicles(abot)

            if not localOnly:
                jresp = send_update_bots_request_to_cloud(self.session, bjs, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
                if "errorType" in jresp:
                    screen_error = True
                    self.showMsg("ERROR Type: " + json.dumps(jresp["errorType"]),
                                 "ERROR Info: " + json.dumps(jresp["errorInfo"]))
                else:
                    jbody = jresp["body"]
                    if jbody['numberOfRecordsUpdated'] == len(bjs):
                        self.bot_service.update_bots_batch(api_bots)

                        # finally update into in-memory data structure.

                    else:
                        self.showMsg("WARNING: bot NOT updated in Cloud!")

            else:
                self.bot_service.update_bots_batch(api_bots)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorUpdateBotsWithJsData:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorUpdateBotsWithJsData: traceback information not available:" + str(e)

            self.showMsg(ex_stat)



    def updateBotRelatedVehicles(self, bot):
        if bot.getVehicle() is not None and bot.getVehicle() != "" and bot.getVehicle() != "NA":
            # if last assigned vehicle is changed. remove botid from last assigned vehicle and botid to the new vehicle.
            vname = bot.getVehicle().split(":")[0]

            # update local DB
            currentVehicleInLocalDB = self.vehicle_service.find_vehicle_by_name(vname)
            previousVehicleInLocalDB = self.vehicle_service.find_vehicle_by_botid(str(bot.getBid()))

            if currentVehicleInLocalDB is not None:
                if previousVehicleInLocalDB is not None:
                    if currentVehicleInLocalDB.name != previousVehicleInLocalDB.name:
                        # update the current vehicle in local DB
                        bot_ids = ast.literal_eval(currentVehicleInLocalDB.bot_ids)
                        if bot.getBid() not in bot_ids:
                            bot_ids.append(bot.getBid())
                            currentVehicleInLocalDB.bot_ids = str(bot_ids)
                            self.vehicle_service.update_vehicle(currentVehicleInLocalDB)

                        # update the previous vehicle in local DB
                        self.vehicle_service.remove_bot_from_current_vehicle(str(bot.getBid()), previousVehicleInLocalDB)
                else:
                    bot_ids = ast.literal_eval(currentVehicleInLocalDB.bot_ids)
                    if bot.getBid() not in bot_ids:
                        bot_ids.append(bot.getBid())
                        currentVehicleInLocalDB.bot_ids = str(bot_ids)
                        self.vehicle_service.update_vehicle(currentVehicleInLocalDB)
            else:
                log3("ERROR: bot's vehicle non-exists in local DB...")

            # update local data structure.
            currentVehicle = next((v for i, v in enumerate(self.vehicles) if vname in v.getName()), None)
            previousVehicle = next((v for i, v in enumerate(self.vehicles) if bot.getBid() in v.getBotIds()), None)

            # update vehicle data structure
            if previousVehicle:
                if currentVehicle:
                    if previousVehicle.getName() != currentVehicle.getName():
                        previousVehicle.removeBot(bot.getBid())
                        currentVehicle.addBot(bot.getBid())
                else:
                    log3("ERROR: bot's vehicle non-exists...")
            else:
                if currentVehicle:
                    currentVehicle.addBot(bot.getBid())

    def addNewMissions(self, new_missions):
        # Logic for creating a new mission:
        try:
            self.showMsg("adding a .... new... mission")
            addedNewMissions = []
            jresp = send_add_missions_request_to_cloud(self.session, new_missions,
                                                       self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
            if "errorType" in jresp:
                print("jresp:", jresp)
                self.showMsg("Error Add New Mission From File: "+json.dumps(jresp))
            else:
                jbody = jresp["body"]
                # now that delete is successfull, update local file as well.
                # self.writeMissionJsonFile()
                self.showMsg("JUST ADDED mission: "+str(len(jbody))+json.dumps(jbody))

                # Note not all mission will be added, if the cloud scheduling algorithm could NOT
                # find a bot for the mission, it will not be added.....

                for i, added in enumerate(jbody):
                    new_mission = next((m for i, m in enumerate(self.new_mission) if m.getTicket() == added["ticket"]), None)
                    if new_mission:
                        new_mission.setMid(jbody[i]["mid"])
                        new_mission.setTicket(jbody[i]["ticket"])
                        new_mission.setEstimatedStartTime(jbody[i]["esttime"])
                        new_mission.setEstimatedRunTime(jbody[i]["runtime"])
                        new_mission.setEsd(jbody[i]["esd"])
                        self.missions.append(new_mission)
                        self.missionModel.appendRow(new_mission)
                        addedNewMissions.append(new_mission)
                if not self.debug_mode:
                    api_missions = []
                    for new_mission in addedNewMissions:
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
                            "follow_seller": new_mission.getFollowSeller(),
                            "brand": new_mission.getBrand(),
                            "image": new_mission.getImagePath(),
                            "title": new_mission.getTitle(),
                            "variations": new_mission.getVariations(),
                            "rating": new_mission.getRating(),
                            "feedbacks": new_mission.getFeedbacks(),
                            "price": new_mission.getPrice(),
                            "follow_price": new_mission.getFollowPrice(),
                            "customer": new_mission.getCustomerID(),
                            "platoon": new_mission.getPlatoonID(),
                            "fingerprint_profile": new_mission.getFingerPrintProfile(),
                            "original_req_file": new_mission.getReqFile(),
                            "as_server": new_mission.getAsServer(),
                            "result": ""
                        })
                    self.mission_service.insert_missions_batch(jbody, api_missions)

                mid_list = [mission.getMid() for mission in addedNewMissions]
                local_mission_rows = self.mission_service.find_missions_by_mids(mid_list)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddNewMissions:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddNewMissions: traceback information not available:" + str(e)

            print(ex_stat)



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
                "follow_seller": amission.getFollowSeller(),
                "brand": amission.getBrand(),
                "image": amission.getImagePath(),
                "title": amission.getTitle(),
                "variations": amission.getVariations(),
                "rating": amission.getRating(),
                "feedbacks": amission.getFeedbacks(),
                "price": amission.getPrice(),
                "follow_price": amission.getFollowPrice(),
                "customer": amission.getCustomerID(),
                "platoon": amission.getPlatoonID(),
                "result": amission.getResult(),
                "as_server": amission.getAsServer(),
                "fingerprint_profile": amission.getFingerPrintProfile(),
                "original_req_file": amission.getReqFile()
            })

        jresp = send_update_missions_request_to_cloud(self.session, missions, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
        if "errorType" in jresp:
            screen_error = True
            self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        else:
            jbody = jresp["body"]
            self.showMsg("Update Cloud side result:"+json.dumps(jbody))
            if jbody['numberOfRecordsUpdated'] == len(missions):
                self.mission_service.update_missions_by_id(api_missions)
                mid_list = [mission.getMid() for mission in missions]
                self.mission_service.find_missions_by_mids(mid_list)
            else:
                self.showMsg("WARNIN: cloud NOT updated.", "warn")

    def addBotsMissionsSkillsFromCommander(self, botsJson, missionsJson, skillsJson):
        existinBids = [b.getBid() for b in self.bots]
        existinMids = [m.getMid() for m in self.missions]
        existinSkids = [sk.getSkid() for sk in self.skills]
        print("existinBids:", existinBids)
        # print("botsJson:", botsJson)

        usefulBotsJson = [bj for bj in botsJson if bj['privateProfile']["email"]]
        # self.showMsg("BOTS String:"+str(type(botsJson))+json.dumps(botsJson))
        # self.showMsg("Missions String:"+str(type(missionsJson))+json.dumps(missionsJson))
        # self.showMsg("Skills String:" + str(type(skillsJson)) + json.dumps(skillsJson))
        for bjs in usefulBotsJson:
            if int(bjs["pubProfile"]["bid"]) not in existinBids:
                self.newBot = EBBOT(self)
                self.newBot.loadJson(bjs)
                self.newBot.updateIcon()
                self.bots.append(self.newBot)
                self.botModel.appendRow(self.newBot)
                self.selected_bot_row = self.botModel.rowCount() - 1
                self.selected_bot_item = self.botModel.item(self.selected_bot_row)
                bot_profile_name = self.my_ecb_data_homepath + "/ads_profiles/"+bjs["privateProfile"]["email"].split("@")[0]+".txt"
                if bot_profile_name not in self.todays_bot_profiles:
                    self.todays_bot_profiles.append(bot_profile_name)

        for mjs in missionsJson:
            if int(mjs["pubAttributes"]["missionId"]) not in existinMids:
                self.newMission = EBMISSION(self)
                self.newMission.loadJson(mjs)
                self.newMission.updateIcon()
                self.missions.append(self.newMission)
                self.missionModel.appendRow(self.newMission)
                self.selected_mission_row = self.missionModel.rowCount() - 1
                self.selected_mission_item = self.missionModel.item(self.selected_mission_row)

        for skjs in skillsJson:
            if int(skjs["skid"]) not in existinSkids:
                self.newSkill = WORKSKILL(self, skjs["name"])
                self.newSkill.loadJson(skjs)
                self.newSkill.updateIcon()
                self.skills.append(self.newSkill)
                # self.skillModel.appendRow(self.newSkill)

        print("done setting bots, missions, skills from commander")

    def addConnectingVehicle(self, vname, vip):
        try:
            # ipfields = vinfo.peername[0].split(".")

            if len(self.vehicles) > 0:
                v_host_names = [v.getName().split(":")[0] for v in self.vehicles]
                print("existing vehicle "+json.dumps(v_host_names))
            else:
                vids = []

            found_fl = next((fl for i, fl in enumerate(fieldLinks) if vname in fl["name"]), None)

            if vname not in v_host_names:
                self.showMsg("adding a new vehicle..... "+vname+" "+vip)
                newVehicle = VEHICLE(self)
                newVehicle.setIP(vip)
                newVehicle.setVid(vip.split(".")[3])
                newVehicle.setName(vname+":")
                if found_fl:
                    print("found_fl IP:", found_fl["ip"])
                    newVehicle.setFieldLink(found_fl)
                    newVehicle.setStatus("connecting")
                self.saveVehicle(newVehicle)
                self.vehicles.append(newVehicle)
                self.runningVehicleModel.appendRow(newVehicle)
                if self.platoonWin:
                    self.platoonWin.updatePlatoonWinWithMostRecentlyAddedVehicle()

                resultV = newVehicle
            else:
                self.showMsg("Reconnected: "+vip)
                foundV = next((v for i, v in enumerate(self.vehicles) if vname in v.getName()), None)
                foundV.setIP(vip)
                foundV.setStatus("connecting")
                if found_fl:
                    print("found_fl IP:", found_fl["ip"])
                    foundV.setFieldLink(found_fl)

                resultV = foundV

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorAddConnectingVehicle:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorAddConnectingVehicle: traceback information not available:" + str(e)

            self.showMsg(ex_stat)
        print("added connecting vehicle:", resultV.getName(), resultV.getStatus())
        return resultV



    def markVehicleOffline(self, vip, vname):
        global fieldLinks
        lostName = vname.split(":")[0]
        self.showMsg("marking vehicle offline: "+vip+" "+json.dumps([v.getIP()+":"+v.getName() for v in self.vehicles]))

        found_v_idx = next((i for i, v in enumerate(self.vehicles) if lostName in v.getName()), -1)
        print("found_v_idx", found_v_idx)
        if found_v_idx > 0:
            print("markingoff......")
            found_v = self.vehicles[found_v_idx]
            found_v.setStatus("offline")

        return found_v

    # add vehicles based on fieldlinks.
    def checkVehicles(self):
        self.showMsg("adding self as a vehicle if is Commander.....")
        existing_names = [v.getName().split(":")[0] for v in self.vehicles]
        print("existing v names:", existing_names)
        if self.machine_role == "Commander":
            # should add this machine to vehicle list.
            newVehicle = VEHICLE(self, self.machine_name+":"+self.os_short, self.ip)
            newVehicle.setStatus("running_idle")
            self.saveVehicle(newVehicle)
            self.vehicles.append(newVehicle)
            self.runningVehicleModel.appendRow(newVehicle)

        self.showMsg("adding already linked vehicles.....")
        for i in range(len(fieldLinks)):
            if fieldLinks[i]["name"].split(":")[0] not in existing_names:
                self.showMsg("a fieldlink....."+json.dumps(fieldLinks[i]["ip"]))
                newVehicle = VEHICLE(self, fieldLinks[i]["name"], fieldLinks[i]["ip"])
                newVehicle.setFieldLink(fieldLinks[i])
                newVehicle.setStatus("running_idle")        # if already has a fieldlink, that means it's tcp connected.
                ipfields = fieldLinks[i]["ip"].split(".")
                ip = ipfields[len(ipfields)-1]
                newVehicle.setVid(ip)
                self.saveVehicle(newVehicle)
                self.vehicles.append(newVehicle)
                self.runningVehicleModel.appendRow(newVehicle)

    def saveVehicle(self, vehicle: VEHICLE):
        v = self.vehicle_service.find_vehicle_by_ip(vehicle.ip)
        if v is None:
            vehicle_model = VehicleModel()
            vehicle_model.arch = vehicle.arch
            vehicle_model.bot_ids = str(vehicle.bot_ids)
            vehicle_model.daily_mids = str(vehicle.daily_mids)
            vehicle_model.ip = vehicle.ip
            vehicle_model.mstats = str(vehicle.mstats)
            vehicle_model.name = vehicle.name
            vehicle_model.os = vehicle.os
            vehicle_model.cap = vehicle.CAP
            vehicle_model.status = vehicle.status
            self.vehicle_service.insert_vehicle(vehicle_model)
            vehicle.id = vehicle_model.id
        else:
            vehicle.setVid(v.id)
            vehicle.setBotIds(ast.literal_eval(v.bot_ids))
            vehicle.setMStats(ast.literal_eval(v.mstats))
            vehicle.setMids(ast.literal_eval(v.daily_mids))
            v.cap = vehicle.CAP
            self.vehicle_service.update_vehicle(v)

    def fetchVehicleStatus(self, rows):
        cmd = '{\"cmd\":\"reqStatusUpdate\", \"missions\":\"all\"}'
        effective_rows = list(filter(lambda r: r >= 0, rows))
        if len(effective_rows) > 0:
            self.sendToPlatoonsByRowIdxs(effective_rows, cmd)

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
        self.sendToPlatoonsByRowIdxs(effective_rows, cmd)


    def cancelVehicleMission(self, rows):
        # cmd = '{\"cmd\":\"reqCancelMission\", \"missions\":\"all\"}'
        cmd = {"cmd": "reqCancelMission", "missions": "all"}
        effective_rows = list(filter(lambda r: r >= 0, rows))
        if len(effective_rows) > 0:
            self.sendToPlatoonsByRowIdxs(effective_rows, cmd)

    # this function sends commands to platoon(s)
    def sendToPlatoonsByRowIdxs(self, idxs, cmd={"cmd": "ping"}):
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

    # this function sends commands to platoon(s)
    def sendToVehicleByVip(self, vip, cmd={"cmd": "ping"}):
        self.showMsg("sending commands to vehicle by vip.....")
        self.showMsg("tcp connections....." + vip + " " + json.dumps([flk["ip"] for flk in fieldLinks]))

        link = next((x for i, x in enumerate(fieldLinks) if x["ip"] == vip), None)

        # if not self.tcpServer == None:
        if link:
            self.send_json_to_platoon(link, cmd)
            self.showMsg("cmd sent on link:" + str(vip) + ":" + json.dumps(cmd))
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
        if exists(self.file_resource.BOTS_FILE):
            with open(self.file_resource.BOTS_FILE, 'r') as file:
                self.botJsonData = json.load(file)
                self.translateBotsJson(self.botJsonData)

            file.close()


    def saveBotJsonFile(self):
        if self.file_resource.BOTS_FILE == None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.file_resource.BOTS_FILE = filename

        if self.file_resource.BOTS_FILE:
            try:
                botsdata = self.genBotsJson()
                self.showMsg("BOTS_FILE: " + self.file_resource.BOTS_FILE)
                with open(self.file_resource.BOTS_FILE, 'w') as jsonfile:
                    json.dump(botsdata, jsonfile, indent=4)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QMessageBox.information(
                    self,
                    "Unable to save file: %s" % filename
                )
        else:
            self.showMsg("Bot file does NOT exist.")


    def readVehicleJsonFile(self):
        self.showMsg("Reading Vehicle Json File: "+self.VEHICLES_FILE)
        if exists(self.VEHICLES_FILE):
            with open(self.VEHICLES_FILE, 'r') as file:
                self.vehiclesJsonData = json.load(file)
                self.translateVehiclesJson(self.vehiclesJsonData)

            file.close()
        else:
            self.vehiclesJsonData = {}
            self.showMsg("WARNING: Vehicle Json File NOT FOUND: " + self.VEHICLES_FILE)

    def translateVehiclesJson(self, vjds):
        all_vnames = [v.getName() for v in self.vehicles]
        print("vehicles names in the vehicle json file:", all_vnames)
        for vjd in vjds:
            if vjd["name"] not in all_vnames:
                print("add new vehicle to local vehicle data structure but no yet added to GUI", vjd["name"])
                new_v = VEHICLE(self)
                new_v.loadJson(vjd)
                new_v.setStatus("offline")      # always set to offline when load from file. will self correct as we update it later....
                self.saveVehicle(new_v)
                self.vehicles.append(new_v)
                self.runningVehicleModel.appendRow(new_v)             # initially set to be offline state and will be updated later when network status is updated
            else:
                if "test_disabled" in vjd:
                    foundV = self.getVehicleByName(vjd["name"])
                    foundV.setTestDisabled(vjd["test_disabled"])

    def saveVehiclesJsonFile(self):
        if self.VEHICLES_FILE == None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.VEHICLES_FILE = filename

        if self.VEHICLES_FILE:
            try:
                vehiclesdata = []
                for v in self.vehicles:
                    vehiclesdata.append(v.genJson())

                self.showMsg("WRITE TO VEHICLES_FILE: " + self.VEHICLES_FILE)
                with open(self.VEHICLES_FILE, 'w') as jsonfile:
                    json.dump(vehiclesdata, jsonfile, indent=4)

                jsonfile.close()
                # self.rebuildHTML()
            except IOError:
                QMessageBox.information(
                    self,
                    "Unable to save file: %s" % filename
                )
        else:
            self.showMsg("Vehicles json file does NOT exist.")


    def translateInventoryJson(self):
        #self.showMsg("Translating JSON to data......."+str(len(self.sellerInventoryJsonData)))
        for bj in self.sellerInventoryJsonData:
            new_inventory = INVENTORY()
            new_inventory.setJsonData(bj)
            self.inventories.append(new_inventory)


    def readSellerInventoryJsonFile(self, inv_file):
        if inv_file == "":
            inv_file_name = self.product_catelog_file
        else:
            inv_file_name = inv_file

        self.showMsg("product catelog file: "+inv_file_name)
        if exists(inv_file_name):
            self.showMsg("Reading inventory file: "+inv_file_name)
            with open(inv_file_name, 'r', encoding='utf-8') as file:
                self.sellerInventoryJsonData = json.load(file)
        else:
            self.showMsg("NO inventory file found!")

    def getSellerProductCatelog(self):
        return self.sellerInventoryJsonData

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
        if exists(self.file_resource.MISSIONS_FILE):
            with open(self.file_resource.MISSIONS_FILE, 'r') as file:
                self.missionJsonData = json.load(file)
                self.translateMissionsJson(self.missionJsonData)


    def writeMissionJsonFile(self):
        if self.file_resource.MISSIONS_FILE == None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                'Save Json File',
                '',
                "Json Files (*.json)"
            )
            self.file_resource.MISSIONS_FILE = filename

        if self.file_resource.MISSIONS_FILE and exists(self.file_resource.MISSIONS_FILE):
            try:
                missionsdata = self.genMissionsJson()
                self.showMsg("MISSIONS_FILE:" + self.file_resource.MISSIONS_FILE)
                with open(self.file_resource.MISSIONS_FILE, 'w') as jsonfile:
                    json.dump(missionsdata, jsonfile, indent=4)

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
                botjson["public_profile"]["org"] = rows[1][i]
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
                selected_indexes = self.botListView.selectedIndexes()
                print("selected indexes:", selected_indexes)

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
            self.cusMissionMarkCompletedAction = self._createMarkMissionCompletedAction()

            self.popMenu.addAction(self.cusMissionEditAction)
            self.popMenu.addAction(self.cusMissionCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionDeleteAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionUpdateAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionRunAction)
            self.popMenu.addAction(self.cusMissionMarkCompletedAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                selected_indexes = self.missionListView.selectedIndexes()
                print("selected indexes:", selected_indexes)

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
                    # print("selected_mission_row: ", self.selected_mission_row)
                    # print("selected_cus_mission_item: ", self.selected_cus_mission_item)
                    asyncio.create_task(self.runCusMissionNow(self.selected_cus_mission_item, self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))
                elif selected_act == self.cusMissionMarkCompletedAction:
                    # print("selected_mission_row: ", self.selected_mission_row)
                    # print("selected_cus_mission_item: ", self.selected_cus_mission_item)
                    asyncio.create_task(self.markCusMissionCompleted(self.selected_cus_mission_item))

            return True
        elif (event.type() == QEvent.MouseButtonPress ) and source is self.botListView:
            self.showMsg("CLICKED on bot:"+str(source.indexAt(event.pos()).row()))
        #     self.showMsg("unknwn.... RC menu...."+source+" EVENT: "+json.dumps(event))
        elif (event.type() == QEvent.MouseButtonPress ) and source is self.missionListView:
            self.showMsg("CLICKED on mission:"+str(source.indexAt(event.pos()).row())+"selected row:"+str(self.missions))
        #     self.showMsg("unknwn.... RC menu...."+source+" EVENT: "+json.dumps(event))
        elif event.type() == QEvent.ContextMenu and source is self.vehicleListView:
            self.showMsg("vehicles RC menu....")
            self.popMenu = QMenu(self)
            self.pop_menu_font = QFont("Helvetica", 10)
            self.popMenu.setFont(self.pop_menu_font)
            self.vehicleViewAction = self._createVehicleViewAction()
            self.popMenu.addAction(self.vehicleViewAction)
            self.vehicleSetUpTeamAction = self._createVehicleSetUpTeamAction()
            self.vehicleSetUpWorkScheduleAction = self._createVehicleSetUpWorkScheduleAction()
            self.vehiclePingAction = self._createVehiclePingAction()
            self.vehicleMonitorAction = self._createVehicleMonitorAction()

            self.popMenu.addAction(self.vehicleSetUpTeamAction)
            self.popMenu.addAction(self.vehicleSetUpWorkScheduleAction)
            self.popMenu.addAction(self.vehiclePingAction)
            self.popMenu.addAction(self.vehicleMonitorAction)

            selected_act = self.popMenu.exec_(event.globalPos())
            if selected_act:
                selected_indexes = self.vehicleListView.selectedIndexes()
                print("selected indexes:", selected_indexes)

                self.selected_vehicle_row = source.indexAt(event.pos()).row()
                self.selected_vehicle_item = self.runningVehicleModel.item(self.selected_vehicle_row)

                if selected_act == self.vehicleSetUpTeamAction:
                    print("vehicle setup team clicked....", self.selected_vehicle_item.getName())
                    asyncio.run(self.vehicleSetupTeam(self.selected_vehicle_item))

                elif selected_act == self.vehicleSetUpWorkScheduleAction:
                    print("vehicle setup work schedule clicked....", self.selected_vehicle_item.getName())
                    vname = self.selected_vehicle_item.getName()
                    p_task_groups = self.unassigned_scheduled_task_groups[vname]
                    asyncio.run(self.vehicleSetupWorkSchedule(self.selected_vehicle_item, p_task_groups))
                elif selected_act == self.vehiclePingAction:
                    print("vehicle ping clicked....", self.selected_vehicle_item.getName())
                    self.vehiclePing(self.selected_vehicle_item)
                elif selected_act == self.vehicleMonitorAction:
                    if self.selected_vehicle_item:
                        print("vehicle ping clicked....", self.selected_vehicle_item.getName())
                    self.vehicleShowMonitor(self.selected_vehicle_item)

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
            if self.selected_bot_item:
                self.chatWin = ChatDialog(self, self.selected_bot_item.getBid())
                self.showMsg("done create win............"+str(self.selected_bot_item.getBid()))
            else:
                self.chatWin = ChatDialog(self, 0)
                self.showMsg("done create win............commander")
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
        # new_action.triggered.connect(self.runCusMissionNowSync)

        return new_action

    def _createMarkMissionCompletedAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText(QApplication.translate("QAction", "&Mark Completed"))
        # new_action.triggered.connect(self.markCusMissionCompletedSync)

        return new_action

    def editCusMission(self):
        # File actions
        if self.missionWin:
            self.showMsg("populating mission GUI............")
            self.missionWin.setMission(self.selected_cus_mission_item)
        else:
            self.showMsg("populating a newly created mission GUI............")
            self.missionWin = MissionNewWin(self)
            self.showMsg("done create mission win............"+str(self.selected_cus_mission_item.getMid())+" skills:"+self.selected_cus_mission_item.getSkills())
            self.missionWin.setMission(self.selected_cus_mission_item)

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

            items = [self.missionModel.itemFromIndex(idx) for idx in self.missionListView.selectedIndexes()]
            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.missionModel.removeRow(item.row())
                    api_removes.append({"id": item.getMid(), "owner": "", "reason": ""})

                # remove on the cloud side, local DB side, and MainGUI side
                self.deleteMissionsWithJsons(False, api_removes)

                    # self.writeMissionJsonFile()

        #self.botModel.removeRow(self.selected_bot_row)
        #self.showMsg("delete bot" + str(self.selected_bot_row))

    # delete from cloud side
    # delete from local DB
    # delete from in-memory data structure
    # delete bots from GUI depends on the "del_gui" flag.
    # note: the mjs is in this format [{"id": mid, "owner": "", "reason": ""} .... ]
    def deleteMissionsWithJsons(self, del_gui, mjs):
        try:
            # remove on the cloud side
            if del_gui:
                print("delete GUI missions")

            # remove on the cloud side
            jresp = send_remove_missions_request_to_cloud(self.session, mjs,
                                                          self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
            self.showMsg("DONE WITH CLOUD SIDE REMOVE MISSION REQUEST.....")
            if "errorType" in jresp:
                screen_error = True
                self.showMsg(
                    "Delete Missions ERROR Type: " + json.dumps(jresp["errorType"]) + "ERROR Info: " + json.dumps(
                        jresp["errorInfo"]))
            else:
                self.showMsg("JRESP:" + json.dumps(jresp) + "<>" + json.dumps(jresp['body']) + "<>" + json.dumps(
                    jresp['body']['$metadata']) + "<>" + json.dumps(jresp['body']['numberOfRecordsUpdated']))
                meta_data = jresp['body']['$metadata']
                if jresp['body']['numberOfRecordsUpdated'] == 0:
                    self.showMsg("WARNING: CLOUD SIDE MISSION DELETE NOT EXECUTED.")

                for m in mjs:
                    # missionTBDId = next((x for x in self.missions if x.getMid() == m["id"]), None)
                    self.mission_service.delete_missions_by_mid(m["id"])

                for m in mjs:
                    midx = next((i for i, x in enumerate(self.missions) if x.getMid() == m["id"]), -1)
                    self.showMsg("removeing MID:" + str(midx))
                    # If the element was found, remove it using pop()
                    if midx != -1:
                        self.missions.pop(midx)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDeleteMissionsWithJsons:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCreateMissionsWithJsons: traceback information not available:" + str(e)
            log3(ex_stat)


    def updateCusMissionStatus(self, amission):
        # send this mission's status to Cloud
        api_missions = [amission]
        # jresp = send_update_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
        # if "errorType" in jresp:
        #     screen_error = True
        #     self.showMsg("Delete Bots ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
        # else:
        #     jbody = json.loads(jresp["body"])
        #     # now that delete is successfull, update local file as well.
        #     self.writeMissionJsonFile()


    def updateMissionsWithJsData(self, mjs):
        try:
            api_missions = []
            for amission in mjs:
                api_missions.append({
                    'mid': amission["pubAttributes"]["missionId"],
                    'ticket': amission["pubAttributes"]["ticket"],
                    'botid': amission["pubAttributes"]["bot_id"],
                    'status': amission["pubAttributes"]["status"],
                    'createon': amission["pubAttributes"]["createon"],
                    'esd': amission["pubAttributes"]["esd"],
                    'ecd': amission["pubAttributes"]["ecd"],
                    'asd': amission["pubAttributes"]["asd"],
                    'abd': amission["pubAttributes"]["abd"],
                    'aad': amission["pubAttributes"]["aad"],
                    'afd': amission["pubAttributes"]["afd"],
                    'acd': amission["pubAttributes"]["acd"],
                    'actual_start_time': amission["pubAttributes"]["actual_start_time"],
                    'est_start_time': amission["pubAttributes"]["est_start_time"],
                    'actual_runtime': amission["pubAttributes"]["actual_run_time"],
                    'est_runtime': amission["pubAttributes"]["est_run_time"],
                    'n_retries': amission["pubAttributes"]["repeat"],
                    'cuspas': amission["pubAttributes"]["cuspas"],
                    'category': amission["pubAttributes"]["category"],
                    'phrase': amission["pubAttributes"]["phrase"],
                    'pseudoStore': amission["pubAttributes"]["pseudo_store"],
                    'pseudoBrand': amission["pubAttributes"]["pseudo_brand"],
                    'pseudoASIN': amission["pubAttributes"]["pseudo_asin"],
                    'type': amission["pubAttributes"]["ms_type"],
                    'config': amission["pubAttributes"]["config"],
                    'skills': amission["pubAttributes"]["skills"],
                    'delDate': amission["pubAttributes"]["del_date"],
                    'asin': amission["privateProfile"]["item_number"],
                    'store': amission["privateProfile"]["seller"],
                    'follow_seller': amission["privateProfile"]["follow_seller"],
                    'brand': amission["privateProfile"]["brand"],
                    'img': amission["privateProfile"]["imglink"],
                    'title': amission["privateProfile"]["title"],
                    'variations': amission["privateProfile"]["variations"],
                    'rating': amission["privateProfile"]["rating"],
                    'feedbacks': amission["privateProfile"]["feedbacks"],
                    'price': amission["privateProfile"]["price"],
                    'follow_price': amission["privateProfile"]["follow_price"],
                    'fingerprint_profile': amission["privateProfile"]["fingerprint_profile"],
                    'customer': amission["privateProfile"]["customer_id"],
                    'platoon': amission["pubAttributes"]["platoon_id"],
                    'result': amission["privateProfile"]["result"],
                    'as_server': amission["pubAttributes"]["as_server"],
                    'original_req_file': amission["privateProfile"]["original_req_file"]
                })

            jresp = send_update_bots_request_to_cloud(self.session, mjs, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
            if "errorType" in jresp:
                screen_error = True
                self.showMsg("ERROR Type: " + json.dumps(jresp["errorType"]),
                             "ERROR Info: " + json.dumps(jresp["errorInfo"]))
            else:
                jbody = jresp["body"]
                if jbody['numberOfRecordsUpdated'] == len(mjs):
                    self.bot_service.update_bots_batch(api_missions)

                    # finally update into in-memory data structure.

                else:
                    self.showMsg("WARNING: bot NOT updated in Cloud!")

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorUpdateMissionsWithJsData:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorUpdateMissionsWithJsData: traceback information not available:" + str(e)

            self.showMsg(ex_stat)


    def runCusMissionNowSync(self):
        print("force mission to run now")
        asyncio.create_task(self.runCusMissionNow(self.selected_cus_mission_item, self.gui_rpa_msg_queue, self.gui_monitor_msg_queue))

    async def runCusMissionNow(self, amission, gui_rpa_queue, gui_monitor_queue):
        # check if psk is already there, if not generate psk, then run it.
        self.showMsg("run mission now...."+str(amission.getBid()))
        executor = self.getBotByID(amission.getBid())

        tempMissionTasks = [{
            "name": amission.getType(),
            "mid": amission.getMid(),
            "ticket": amission.getTicket(),
            "cuspas": amission.getCusPAS(),
            "bid": amission.getBid(),
            "skills": amission.getSkills(),
            "config": amission.getConfig(),
            "trepeat": 1,
            "fingerprint_profile": amission.getFingerPrintProfile(),
            "start_time": 1            # make this task due 00:20 am, which should have been passed by now, so to catch up, the schedule will run this at the first possible chance.
        }]

        # ads_profile_batches_fnames = genAdsProfileBatchs(self, self.ip, tempMissionTasks)
        print("updated tempMissionTasks:", tempMissionTasks)
        widx = len(self.todays_work["tbd"])
        self.todays_work["tbd"].append({"name": "automation", "works": tempMissionTasks, "status": "Assigned", "current widx": widx, "completed": [], "aborted": []})


    async def markCusMissionCompleted(self, amission, gui_rpa_queue, gui_monitor_queue):
        # check if psk is already there, if not generate psk, then run it.
        self.showMsg("run mission now...."+str(amission.getBid()))
        amission.setStatus("Completed:0")
        if "Commander" in self.host_role:
            self.updateMissionsStatToCloud([amission])

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

    def _createVehicleViewAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&View"))
       return new_action

    def _createVehicleSetUpTeamAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Set Up Team"))
       return new_action

    def _createVehicleSetUpWorkScheduleAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Set Up Work Schedule"))
       return new_action

    def _createVehiclePingAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Ping"))
       return new_action

    def _createVehicleMonitorAction(self):
       new_action = QAction(self)
       new_action.setText(QApplication.translate("QAction", "&Monitor"))
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
            # items = [self.selected_bot_item]
            items = [self.botModel.itemFromIndex(idx) for idx in self.botListView.selectedIndexes()]

            if len(items):
                for item in items:
                    # remove file first, then the item in the model.
                    # shutil.rmtree(temp_page_dir)
                    # os.remove(full_temp_page)

                    # remove the local data and GUI.
                    self.botModel.removeRow(item.row())
                    api_removes.append({"id": item.getBid(), "owner": "", "reason": ""})

                # remove on the cloud side, local side, MainGUI side.
                self.deleteBotsWithJsons(False, api_removes)

                # self.saveBotJsonFile()


    # delete from cloud side
    # delete from local DB
    # delete from in-memory data structure
    # delete bots from GUI depends on the "del_gui" flag.
    # note: the bjs is in this format [{"id": bid, "owner": "", "reason": ""} .... ]
    def deleteBotsWithJsons(self, del_gui, bjs):
        try:
            # remove on the cloud side
            if del_gui:
                print("delete GUI bots")

            # now the common part.
            jresp = send_remove_bots_request_to_cloud(self.session, bjs,
                                                      self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
            self.showMsg("DONE WITH CLOUD SIDE REMOVE BOT REQUEST.....")
            if "errorType" in jresp:
                screen_error = True
                self.showMsg("Delete Bots ERROR Type: " + json.dumps(jresp["errorType"]) + "ERROR Info: " + json.dumps(
                    jresp["errorInfo"]))
            else:
                self.showMsg("JRESP:" + json.dumps(jresp) + "<>" + json.dumps(jresp['body']))
                if jresp['body']['numberOfRecordsUpdated'] == 0:
                    self.showMsg("WARNING: CLOUD SIDE DELETE NOT EXECUTED.")

                for b in bjs:
                    botTBDId = next((x for x in self.bots if x.getBid() == b["id"]), None)
                    self.bot_service.delete_bots_by_botid(b["id"])

                for b in bjs:
                    bidx = next((i for i, x in enumerate(self.bots) if x.getBid() == b["id"]), -1)

                    # If the element was found, remove it using pop()
                    if bidx != -1:
                        self.bots.pop(bidx)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDeleteBotsWithJsons:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCreateBotsWithJsons: traceback information not available:" + str(e)
            log3(ex_stat)


    # data format conversion. nb is in EBBOT data structure format., nbdata is json
    def fillNewBotPubInfo(self, nbjson, nb):
        self.showMsg("filling bot public data for bot-" + str(nbjson["pubProfile"]["bid"]))
        nb.setNetRespJsonData(nbjson)

    def fillNewBotFullInfo(self, nbjson, nb):
        self.showMsg("filling bot data for bot-" + str(nbjson["pubProfile"]["bid"]))
        nb.loadJson(nbjson)

    # this function can only be called by a manager or HR head.
    def syncBotAccounts(self):
        try:
            # run a hook function to bring in external accounts.
            acctRows = self.runGetBotAccountsHook()
            print("ACCT ROWS:", acctRows)
            # then from there, figure out newly added accounts
            # from newly added accounts, screen the ones ready to be converted to a Bot/Agent
            # rows are updated....
            qualified, rowsNeedUpdate, botsNeedUpdate, vehiclesNeedUpdate = self.screenBuyerBotCandidates(acctRows, self.bots)
            print("qualified:", len(qualified), qualified)
            print("rowsNeedUpdate:", len(rowsNeedUpdate), rowsNeedUpdate)
            print("botsNeedUpdate:", len(botsNeedUpdate), [b.getAddr() for b in botsNeedUpdate])
            # turn qualified acct into bots/agents
            self.hireBuyerBotCandidates(qualified)
            # create new ads power profile for the newly added accounts.

            # genInitialADSProfiles(qualified)

            # call another hook function update the rowsNeedUpdate
            rowsNeedUpdate = rowsNeedUpdate + qualified
            results = self.runUpdateBotAccountsHook(rowsNeedUpdate)

            self.updateBots(botsNeedUpdate)

            if vehiclesNeedUpdate:
                self.updateVehicles(vehiclesNeedUpdate)

        except Exception as e:
            # Log and skip errors gracefully
            ex_stat = f"Error in SyncBotAccounts: {traceback.format_exc()} {str(e)}"
            print(f"{ex_stat}")


    def runGetBotAccountsHook(self):
        try:
            params = {"all": True}      # this will get all rows in accounts table.
            runStat = self.runExternalHook("hr_recruit_get_candidates_hook", params)
            # runStat = self.runExternalHook("get_accounts_hook", params)
            print("runStat:", runStat)
            if "Complete" in runStat:
                acctRows = symTab["hook_result"]["candidates"]

        except Exception as e:
            # Log and skip errors gracefully
            ex_stat = f"Error in runGetBotAccountsHook: {traceback.format_exc()} {str(e)}"
            print(f"{ex_stat}")

        return acctRows

    def runTeamPrepHook(self):
        try:
            params = {"all": True}      # this will get all rows in accounts table.
            runStat = self.runExternalHook("team_prep_hook", params)
            # runStat = self.runExternalHook("get_accounts_hook", params)
            print("runStat:", runStat)
            if "Complete" in runStat:
                runnable_work = symTab["hook_result"]["candidates"]

        except Exception as e:
            # Log and skip errors gracefully
            ex_stat = f"Error in runTeamPrepHook: {traceback.format_exc()} {str(e)}"
            print(f"{ex_stat}")

        return runnable_work

    def runUpdateBotAccountsHook(self, rows):
        try:
            params = {"rows": rows}
            runStat = self.runExternalHook("update_accounts_hook", params)

        except Exception as e:
            # Log and skip errors gracefully
            ex_stat = f"Error in runUpdateBotAccountsHook: {traceback.format_exc()} {str(e)}"
            print(f"{ex_stat}")

        return runStat

    def newBotFromFile(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open Bot Definition File"),
            '',
            QApplication.translate("QFileDialog", "Bot Files (*.json *.xlsx *.csv)")
        )
        log3("loading bots from a file..."+filename)
        b1, addedBots = self.createBotsFromFilesOrJsData([filename])

    def createBotsFromFilesOrJsData(self, bfiles):
        try:
            bots_from_file = []
            botsJson = []
            for filename in bfiles:
                if filename:
                    if isinstance(filename, str):
                        if "json" in filename:
                            try:
                                api_bots = []
                                with open(filename, 'r', encoding='utf-8') as uncompressed:
                                    filebbots = json.load(uncompressed)
                                    if filebbots:
                                        # Add bots to the relevant data structure and add these bots to the cloud and local DB.
                                        for fb in filebbots:
                                            new_bot = EBBOT(self)
                                            self.fillNewBotFullInfo(fb, new_bot)
                                            bots_from_file.append(new_bot)
                                    else:
                                        self.warn(QApplication.translate("QMainWindow", "Warning: NO bots found in file."))
                            except (FileNotFoundError, json.JSONDecodeError) as e:
                                self.warn(QApplication.translate("QMainWindow",
                                                                 f"Error opening or decoding JSON file: {filename} - {e}"))

                        elif "xlsx" in filename:
                            try:
                                log3("working on file:" + str(filename))
                                xls = openpyxl.load_workbook(filename, data_only=True)
                                botsJson = []
                                title_cells = []

                                # Process each sheet in the Excel file
                                for idx, sheet in enumerate(xls.sheetnames):
                                    ws = xls[sheet]

                                    for ri, row in enumerate(ws.iter_rows(values_only=True)):
                                        # Capture header titles from the first row of the first sheet
                                        if idx == 0 and ri == 0:
                                            title_cells = [cell for cell in row]
                                        elif ri > 0 and len(row) == len(title_cells):  # Ensure row length matches headers
                                            botJson = {}
                                            for ci, cell in enumerate(title_cells):
                                                # Format dates if necessary
                                                if cell == "DoB" and row[ci]:
                                                    botJson[cell] = row[ci].strftime('%Y-%m-%d')
                                                else:
                                                    botJson[cell] = row[ci]
                                            botsJson.append(botJson)

                                log3("total # of bot rows read:" + str(len(botsJson)))
                                log3("all jsons from bot xlsx file:" + json.dumps(botsJson, ensure_ascii=False))
                                for bjson in botsJson:
                                    new_bot = EBBOT(self)
                                    new_bot.loadXlsxData(bjson)
                                    bots_from_file.append(new_bot)
                                    print(new_bot.genJson())

                            except FileNotFoundError as e:
                                self.warn(QApplication.translate("QMainWindow", f"Excel file not found: {filename} - {e}"))
                            except Exception as e:
                                self.warn(
                                    QApplication.translate("QMainWindow", f"Error processing Excel file: {filename} - {e}"))

                        else:
                            self.showMsg("ERROR: bot files must either be in .json format or .xlsx format!")
                    else:
                        # this is the case where input is already in json format, so just directly use them.
                        jsData = filename

                        new_bot = EBBOT(self)
                        self.fillNewBotFullInfo(jsData, new_bot)
                        self.assignBotVehicle(new_bot)
                        bots_from_file.append(new_bot)

                else:
                    self.warn(QApplication.translate("QMainWindow", "Warning: No file provided."))

            if len(bots_from_file) > 0:
                print("adding new bots to both cloud and local DB... update BID and Interests along the way since they're cloud generated.")
                self.addNewBots(bots_from_file)
                firstAddedBotId = bots_from_file[0].getBid()
                return firstAddedBotId, bots_from_file

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorCreateBotsFromFilesOrJsData:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCreateBotsFromFilesOrJsData: traceback information not available:" + str(e)
            log3(ex_stat)
            return 0, []

    # data format conversion. nb is in EBMISSION data structure format., nbdata is json
    def fillNewMissionFromCloud(self, nmjson, nm):
        self.showMsg("filling mission data")
        nm.setNetRespJsonData(nmjson)

    def addMissionsToLocalDB(self, missions: [EBMISSION]):
        local_missions: [MissionModel] = []

        # Extract all mids from the new missions
        new_mids = [mission.getMid() for mission in missions]

        # Query existing mids in the local database
        existing_missions = self.mission_service.find_missions_by_mids(new_mids)
        existing_mids = {mission.mid for mission in existing_missions}

        for new_mission in missions:
            if new_mission.getMid() in existing_mids:
                log3(f"Mission with mid {new_mission.getMid()} already exists. Skipping.", "debug", self)
                continue

            local_mission = MissionModel()
            local_mission.mid = new_mission.getMid()
            local_mission.ticket = new_mission.getTicket()
            local_mission.botid = new_mission.getBid()
            local_mission.status = new_mission.getStatus()
            local_mission.createon = new_mission.getBD()
            local_mission.owner = self.owner
            local_mission.esd = new_mission.getEsd()
            local_mission.ecd = new_mission.getEcd()
            local_mission.asd = new_mission.getAsd()
            local_mission.abd = new_mission.getAbd()
            local_mission.aad = new_mission.getAad()
            local_mission.afd = new_mission.getAfd()
            local_mission.acd = new_mission.getAcd()
            local_mission.actual_start_time = new_mission.getActualStartTime()
            local_mission.est_start_time = new_mission.getEstimatedStartTime()
            local_mission.actual_runtime = new_mission.getActualRunTime()
            local_mission.est_runtime = new_mission.getEstimatedRunTime()
            local_mission.n_retries = new_mission.getNRetries()
            local_mission.cuspas = new_mission.getCusPAS()
            local_mission.category = new_mission.getSearchCat()
            local_mission.phrase = new_mission.getSearchKW()
            local_mission.pseudoStore = new_mission.getPseudoStore()
            local_mission.pseudoBrand = new_mission.getPseudoBrand()
            local_mission.pseudoASIN = new_mission.getPseudoASIN()
            local_mission.type = new_mission.getType()
            local_mission.config = json.dumps(new_mission.getConfig())
            local_mission.skills = new_mission.getSkills()
            local_mission.delDate = new_mission.getDelDate()
            local_mission.asin = new_mission.getASIN()
            local_mission.store = new_mission.getStore()
            local_mission.follow_seller = new_mission.getFollowSeller()
            local_mission.brand = new_mission.getBrand()
            local_mission.img = new_mission.getImagePath()
            local_mission.title = new_mission.getTitle()
            local_mission.rating = new_mission.getRating()
            local_mission.feedbacks = new_mission.getFeedbacks()
            local_mission.price = new_mission.getPrice()
            local_mission.follow_price = new_mission.getFollowPrice()
            local_mission.fingerprint_profile = new_mission.getFingerPrintProfile()
            local_mission.original_req_file = new_mission.getReqFile()
            local_mission.customer = new_mission.getCustomerID()
            local_mission.platoon = new_mission.getPlatoonID()
            local_mission.result = new_mission.getResult()
            local_mission.variations = new_mission.getVariations()
            local_mission.as_server = new_mission.getAsServer()
            local_missions.append(local_mission)

        if local_missions:
            self.mission_service.insert_missions_batch_(local_missions)


    def newMissionFromFile(self):
        self.showMsg("loading missions from a file...")
        api_missions = []
        filename, _ = QFileDialog.getOpenFileName(
            self,
            QApplication.translate("QFileDialog", "Open Mission Definition File"),
            '',
            QApplication.translate("QFileDialog", "Mission Files (*.json *.xlsx *.csv)")
        )
        self.createMissionsFromFile([filename])

    def createMissionsFromFilesOrJsData(self, mfiles):
        missionsJson = []
        mTypeTable = {
            "溜号": "browse",
            "免评": "buy",
            "直评": "directbuy",
            "产品点星": "goodRating",
            "产品好评": "goodFB",
            "店铺点星": "storeRating",
            "店铺好评": "storeFB",
            "加购物车": "addCart",
        }
        for filename in mfiles:
            if filename != "":
                if isinstance(filename, str):
                    dataType = "file"
                    if "json" in filename:
                        api_missions = []
                        # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
                        dataType = "missionJSFile"
                        filebmissions = json.load(filename)
                        if len(filebmissions) > 0:
                            #add bots to the relavant data structure and add these bots to the cloud and local DB.

                            jresp = send_add_missions_request_to_cloud(self.session, filebmissions,
                                                                   self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())

                            if "errorType" in jresp:
                                screen_error = True
                                self.showMsg("ERROR Type: "+json.dumps(jresp["errorType"])+"ERROR Info: "+json.dumps(jresp["errorInfo"]))
                            else:
                                self.showMsg("jresp type: "+str(type(jresp))+" "+str(len(jresp["body"])))
                                jbody = jresp["body"]
                                # now that add is successfull, update local file as well.

                                # now add missions to local DB.
                                new_missions: [EBMISSION] = []
                                for i in range(len(jbody)):
                                    self.showMsg(str(i))
                                    new_mission = EBMISSION(self)
                                    # move json file based mission into MISSION data structure.
                                    new_mission.loadJson(filebmissions)
                                    self.fillNewMissionFromCloud(jbody[i], new_mission)
                                    self.missions.append(new_mission)
                                    self.missionModel.appendRow(new_mission)
                                    new_missions.append(new_mission)

                                if not self.debug_mode:
                                    self.addMissionsToLocalDB(new_missions)

                        else:
                            self.warn(QApplication.translate("QMainWindow", "Warning: NO missions found in file."))

                    elif "xlsx" in filename:
                        dataType = "businessXlsxFile"
                        # if getting missions from xlsx file it's automatically assumed that the
                        # the mission will be for amz buy.
                        log3("working on order file:"+filename)
                        mJsons = self.convert_orders_xlsx_to_json(filename)
                        log3("mJsons from xlsx:" + json.dumps(mJsons))

                        # now if quantity is N, there will be N missions created.
                        # and add other required missions parameters....
                        for mJson in mJsons:
                            if "email" not in mJson:
                                pkString = "songc@yahoo.com"
                            elif not mJson["email"]:
                                pkString = "songc@yahoo.com"
                            else:
                                pkString = mJson["email"]
                            mJson["pseudoStore"] = self.generateShortHash(pkString+":"+mJson.get("store", "NoneStore"))
                            mJson["pseudoBrand"] = self.generateShortHash(pkString+":"+mJson.get("brand", "NoneBrand"))
                            mJson["pseudoASIN"] = self.generateShortHash(pkString+":"+mJson["asin"])

                            if not mJson["feedback_type"]:
                                mJson["type"] = mTypeTable[mJson["feedback_type"]]
                            else:
                                mJson["type"] = "buy"

                            # each buy should be a separate mission.
                            n_orders = int(mJson["quantity"])
                            missionsJson = missionsJson + [copy.deepcopy(mJson) for _ in range(n_orders)]

                        log3("total # of orders rows read: "+str(len(mJsons)))
                        log3("mJsons after conversion:"+json.dumps(mJsons))
                        m = sum(int(item["quantity"]) for item in mJsons)
                        log3("total # of missions to be generated: " + str(m))
                else:
                    log3("add missions from direct list of jsons, no data manipulation here.")
                    dataType = "businessJSData"
                    missionsJson = mfiles

        missions_from_file = []
        for mjson in missionsJson:
            new_mission = EBMISSION(self)
            if dataType == "businessJSData":
                new_mission.loadBusinessesDBData(mjson)
            else:
                new_mission.loadXlsxData(mjson)
            missions_from_file.append(new_mission)
            # new_mission.genJson()

        print("about to really add these missions to cloud and local DB...")
        if missions_from_file:
            # during the process of this the cloud generated mid should be updated to JSON.
            self.addNewMissions(missions_from_file)


        return missionsJson


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

        print("READ XLSX::", json_list)
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


    def newMissionFromNewReq(self, reqJson, reqFile):
        new_mission = EBMISSION(self)
        new_mission.loadAMZReqData(reqJson, reqFile)
        return new_mission



    # sc - 10/11/2024 - add new missions are they in todays_work?
    def newBuyMissionFromFiles(self):
        dtnow = datetime.now()

        recent = dtnow - timedelta(days=3)
        date_word = dtnow.strftime("%Y%m%d")
        year = dtnow.strftime("%Y")
        month = f"m{dtnow.month}"
        day = f"m{dtnow.day}"

        new_orders_dir = self.my_ecb_data_homepath + "/new_orders/ORDER" + date_word + "/"
        new_orders_dir = os.path.join(self.new_orders_dir, year, month, day)
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
                    if len(n_buys) > 0:
                        for n in range(n_buys):
                            print("creating new buy mission:", n)
                            new_buy_missions.append(self.newMissionFromNewReq(buy_req, xlsx_file))

        # now that we have created all the new missions,
        # create the mission in the cloud and local DB.
        # cloud side first

        if len(new_buy_missions) > 0:
            jresp = send_add_missions_request_to_cloud(self.session, new_buy_missions, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())

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
                if not self.debug_mode:
                    self.addMissionsToLocalDB(new_buy_missions)

                #add to local data structure
                self.missions = self.missions + new_buy_missions
                for new_buy in new_buy_missions:
                    self.missionModel.appendRow(new_buy)

        return new_buy_missions

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
                jresp = upload_file(self.session, full_af_name, self.tokens['AuthenticationResult']['IdToken'],  self.getWanApiEndpoint(), "anchor")

            csk_file = scripts_dir + "/" + os.path.basename(filename).split(".")[0] + ".csk"
            jresp = upload_file(self.session, csk_file, self.tokens['AuthenticationResult']['IdToken'],  self.getWanApiEndpoint(), "csk")


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
                        jresp = send_add_skills_request_to_cloud(self.session, [skill_json], self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())

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
                logger_helper.debug(ex_stat)
                logger_helper.debug(QApplication.translate("QMainWindow", "Warning: load skill file error."))

    def find_dependencies(self, main_file, visited, dependencies):
        if main_file in visited:
            return

        visited.add(main_file)

        # "type": "Use Skill",
        # "skill_name": "update_tracking",
        # "skill_path": "public/win_chrome_etsy_orders",
        # "skill_args": "gs_input",
        # "output": "total_label_cost"
        log3("TRYING...."+main_file, "fetchSchedule", self)
        if os.path.exists(main_file):
            log3("OPENING...."+main_file, "fetchSchedule", self)
            with open(main_file, 'r') as psk_file:
                code_jsons = json.load(psk_file)

                # go thru all steps.
                for key in code_jsons.keys():
                    if "type" in code_jsons[key]:
                        if code_jsons[key]["type"] == "Use Skill":
                            if "public" in code_jsons[key]["skill_path"]:
                                dependency_file = self.homepath + "/resource/skills/" + code_jsons[key]["skill_path"] + "/" + code_jsons[key]["skill_name"] + ".psk"
                            else:
                                dependency_file = self.my_ecb_data_homepath + code_jsons[key]["skill_path"] + "/" + code_jsons[key]["skill_name"] + ".psk"


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

    def loadPublicSkills(self):
        skill_def_files = []
        skid_files = []
        psk_files = []
        csk_files = []
        json_files = []

        skdir = self.homepath + "/resource/skills/public/"
        print("LISTING pub skills:", skdir, os.walk(skdir))
        # Iterate over all files in the directory
        # Walk through the directory tree recursively
        for root, dirs, files in os.walk(skdir):
            for file in files:
                if file.endswith(".json"):
                    file_path = os.path.join(root, file)
                    skill_def_files.append(file_path)
                    print("load all public skill definition json file:" + file + "::" + file_path)

        # self.showMsg("local skill files: "+json.dumps(skill_def_files))

        # if json exists, use json to guide what to do
        existing_skids = [sk.getSkid() for sk in self.skills]
        print("existing public skids:", existing_skids)
        for file_path in skill_def_files:
            print("working on:", file_path)
            with open(file_path) as json_file:
                sk_data = json.load(json_file)
                json_file.close()
                self.showMsg("loading public skill f: " + str(sk_data["skid"]) + " " + file_path)
                if sk_data["skid"] not in existing_skids:
                    new_skill = WORKSKILL(self, sk_data["name"], sk_data["path"])
                    new_skill.loadJson(sk_data)
                    self.skills.append(new_skill)
                    print("added public new skill:", sk_data["skid"], new_skill.getSkid(), new_skill.getPskFileName(),
                          new_skill.getPath())
                else:
                    existingSkill = next((x for i, x in enumerate(self.skills) if x.getSkid() == sk_data["skid"]), None)
                    if existingSkill:
                        # these are the only attributes that could be local only.
                        existingSkill.setAppLink(sk_data['app_link'])
                        existingSkill.setAppArgs(sk_data['app_args'])
                        existingSkill.add_procedural_skill(sk_data['procedural_skill'])
                        existingSkill.add_cloud_skill(sk_data['cloud_skill'])


        self.showMsg("Added Local public Skills:" + str(len(self.skills)))


    # load locally stored skills
    def loadLocalPrivateSkills(self):
        try:
            skill_def_files = []
            skid_files = []
            psk_files = []
            csk_files = []
            json_files = []

            skdir = self.my_ecb_data_homepath + "/my_skills/"
            print("LISTING myskills:", skdir, os.walk(skdir))
            # Iterate over all files in the directory
            # Walk through the directory tree recursively
            for root, dirs, files in os.walk(skdir):
                for file in files:
                    if file.endswith(".json"):
                        file_path = os.path.join(root, file)
                        skill_def_files.append(file_path)
                        print("load private skill definition json file:" + file+"::"+file_path)

            # self.showMsg("local skill files: "+json.dumps(skill_def_files))

            # if json exists, use json to guide what to do
            existing_skids = [sk.getSkid() for sk in self.skills]
            for file_path in skill_def_files:
                print("working on:", file_path)
                with open(file_path) as json_file:
                    sk_data = json.load(json_file)
                    json_file.close()
                    print("sk_data::", sk_data)
                    self.showMsg("loading private skill f: "+str(sk_data["skid"])+" "+file_path)
                    if sk_data["skid"] in existing_skids:
                        new_skill = WORKSKILL(self, sk_data["name"], sk_data["path"])
                        new_skill.loadJson(sk_data)
                        self.skills.append(new_skill)
                        print("added private new skill:", new_skill.getSkid(), new_skill.getPskFileName(), new_skill.getPath())
                    else:
                        #update the existing skill or no even needed?
                        found_skill = next((x for x in self.skills if x.getSkid()==sk_data["skid"]), None)
                        # if found_skill:


                    this_skill_dir = skdir+sk_data["platform"]+"_"+sk_data["app"]+"_"+sk_data["site_name"]+"_"+sk_data["page"]+"/"
                    gen_string = sk_data["platform"]+"_"+sk_data["app"]+"_"+sk_data["site_name"]+"_"+sk_data["page"]+"_"+sk_data["name"]
                    self.showMsg("total skill files loaded: "+str(len(self.skills)))
                    self.load_external_functions(this_skill_dir, sk_data["name"], gen_string, sk_data["generator"])
                    # no need to run genSkillCode, since once in table, will be generated later....
                    # genSkillCode(sk_full_name, privacy, root_path, start_step, theme)

            self.showMsg("Added Local Private Skills:"+str(len(self.skills)))

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorLoadLocalPrivateSkills:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorLoadLocalPrivateSkills: traceback information not available:" + str(e)
            self.showMsg(ex_stat)


    #  in case private skill use certain external functions, load them
    def load_external_functions(self, sk_dir, sk_name, gen_string, generator):
        try:
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
                    SkillGeneratorTable[gen_string+"_my"] = lambda w, x, y, z: getattr(module, generator)(w, x, y, z)

            elif os.path.isfile(generator_diagram):
                self.showMsg("gen psk from diagram.")

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorLoadExternalFunction:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorLoadExternalFunction: traceback information not available:" + str(e)
            self.showMsg(ex_stat)


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
        uncompressed = open(self.my_ecb_data_homepath + "/resource/testdata/newproducts.json")
        if uncompressed != None:
            # self.showMsg("body string:"+uncompressed+"!"+str(len(uncompressed))+"::")
            fileproducts = json.load(uncompressed)
            if len(fileproducts) > 0:
                self.product_service.find_all_products()

            else:
                self.warn(QApplication.translate("QMainWindow", "Warning: NO products found in file."))
        else:
            self.warn(QApplication.translate("QMainWindow", "Warning: No tests products file"))

    # try load bots from local database, if nothing in th local DB, then
    # try to fetch bots from local json files (this is mostly for testing).
    def loadLocalBots(self, db_data: [BotModel]):
        try:
            dict_results = [result.to_dict() for result in db_data]
            self.showMsg("get local bots from DB::" + json.dumps(dict_results))
            if len(db_data) != 0:
                self.bots = []
                self.botModel.clear()
                for row in db_data:
                    self.showMsg("loading a bot: "+json.dumps(row.to_dict()))
                    new_bot = EBBOT(self)
                    new_bot.loadDBData(row)
                    print("hello????")
                    new_bot.updateDisplay()
                    self.bots.append(new_bot)
                    self.botModel.appendRow(new_bot)
                    self.selected_bot_row = self.botModel.rowCount() - 1
                    self.selected_bot_item = self.botModel.item(self.selected_bot_row)

                    self.addBotToVehicle(new_bot)
            else:
                self.showMsg("WARNING: local bots DB empty!")
                # self.newBotFromFile()
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorloadLocalBots:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorloadLocalBots: traceback information not available:" + str(e)
            log3(ex_stat)

    def addBotToVehicle(self, new_bot):

        if new_bot.getVehicle() != "" and new_bot.getVehicle() != "NA":
            found_v = next((x for x in self.vehicles if x.getName() == new_bot.getVehicle()), None)

            if found_v:
                nadded = found_v.addBot(new_bot.getBid())
                if nadded == 0:
                    self.showMsg("WARNING: vehicle reached full capacity!")
            else:
                self.showMsg("WARNING: bot vehicle NOT FOUND!")
        else:
            self.showMsg("WARNING: bot vehicle NOT ASSIGNED!")

    # load locally stored mission, but only for the past 7 days, otherwise, there would be too much......
    def loadLocalMissions(self, db_data: [MissionModel]):
        dict_results = [result.to_dict() for result in db_data]
        # self.showMsg("get local missions from db::" + json.dumps(dict_results))
        if len(db_data) != 0:
            self.missions = []
            self.missionModel.clear()
            for row in db_data:
                # self.showMsg("loading a mission: "+json.dumps(row.to_dict()))
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
        #resp = send_get_bots_request_to_cloud(self.session, self.cog.access_token, self.getWanApiEndpoint())
        jresp = send_get_bots_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
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

    def get_vehicle_settings(self, forceful="false"):
        vsettings = {
            "vwins": len([v for v in self.vehicles if v.getOS() == "win"]),
            "vmacs": len([v for v in self.vehicles if v.getOS() == "mac"]),
            "vlnxs": len([v for v in self.vehicles if v.getOS() == "linux"]),
            "forceful": forceful,
            "tz": str(tzlocal.get_localzone())
        }

        print("v timezone:", tzlocal.get_localzone())
        # add self to the compute resource pool
        if self.host_role == "Commander":
            if self.platform == "win":
                vsettings["vwins"] = vsettings["vwins"] + 1
            elif self.platform == "mac":
                vsettings["vmacs"] = vsettings["vmacs"] + 1
            else:
                vsettings["vlnxs"] = vsettings["vlnxs"] + 1
        return vsettings

    # the message queue is for messsage from tcpip task to the GUI task. OPENAI's fix
    async def servePlatoons(self, msgQueue):
        self.showMsg("starting servePlatoons")

        while True:
            print("listening to platoons", datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])

            if not msgQueue.empty():
                try:
                    # Process all available messages in the queue
                    while not msgQueue.empty():
                        net_message = await msgQueue.get()
                        print("received net message:", type(net_message), net_message)
                        if isinstance(net_message, str):
                            if len(net_message) > 256:
                                mlen = 256
                            else:
                                mlen = len(net_message)
                            self.showMsg(
                                "received queued msg from platoon..... [" + str(msgQueue.qsize()) + "]" + net_message[:mlen])

                            print("platoon server received message from queu...")
                            # Parse the message into parts
                            msg_parts = net_message.split("!")
                            if len(msg_parts) >= 3:  # Check for valid message structure
                                if msg_parts[1] == "net data":
                                    await self.processPlatoonMsgs(msg_parts[2], msg_parts[0])
                                elif msg_parts[1] == "connection":
                                    print("received connection message: " + msg_parts[0] + " " + msg_parts[2])
                                    if self.platoonWin is None:
                                        self.platoonWin = PlatoonWindow(self, "conn")
                                    addedV = self.addConnectingVehicle(msg_parts[2], msg_parts[0])
                                    # await asyncio.sleep(8)
                                    # if len(self.vehicles) > 0:
                                    #     print("pinging platoon: " + str(len(self.vehicles) - 1) + msg_parts[0])
                                    #     self.sendToVehicleByVip(msg_parts[0])
                                elif msg_parts[1] == "net loss":
                                    print("received net loss")
                                    found_vehicle = self.markVehicleOffline(msg_parts[0], msg_parts[2])
                                    vehicle_report = self.prepVehicleReportData(found_vehicle)
                                    resp = send_report_vehicles_to_cloud(
                                        self.session,
                                        self.tokens['AuthenticationResult']['IdToken'],
                                        vehicle_report,
                                        self.getWanApiEndpoint()
                                    )
                                    self.saveVehiclesJsonFile()
                        elif isinstance(net_message, dict):
                            print("process json from queue:")

                        msgQueue.task_done()

                except asyncio.QueueEmpty:
                    print("Queue unexpectedly empty when trying to get message.")
                except Exception as e:
                    print(f"Error processing Commander message: {e}")

            else:
                # if nothing on queue, do a quick check if any vehicle needs a ping-pong check
                for v in self.vehicles:
                    if "connecting" in v.getStatus():
                        print("pinging platoon: " + v.getIP())
                        self.sendToVehicleByVip(v.getIP())
            await asyncio.sleep(1)  # Short sleep to avoid busy-waiting



    # this is be run as an async task.
    async def runbotworks(self, gui_rpa_queue, gui_monitor_queue):
        # run all the work
        try:
            running = True
            wan_pre_time = datetime.now()
            lan_pre_time = datetime.now()
            while running:
                log3("runbotwork Task.....", "runbotworks", self)
                print("runbotworks................")
                current_time = datetime.now()

                # check whether there is vehicle for hire, if so, check any contract work in the queue
                # if so grab it.
                contractWorks = await self.checkCloudWorkQueue()

                # if there is actual work, 1) deque from virutal cloud queue, 2) put it into local unassigned work list.
                # and the rest will be taken care of by the work dispatcher...
                self.arrangeContractWorks(contractWorks)

                #print only first 3 and last 3 items.
                log3("real work starts here...."+json.dumps([m.getFingerPrintProfile() for i, m in enumerate(self.missions) if i<3 or i > len(self.missions)-4]), "runbotworks", self)
                botTodos = None
                if self.working_state == "running_idle":
                    log3("idle checking.....", "runbotworks", self)
                    if self.getNumUnassignedWork() > 0:
                        log3(get_printable_datetime() + " - Found unassigned work: "+str(self.getNumUnassignedWork())+"<>"+datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "runbotworks", self)
                        await self.assignWork()

                    log3("check next to run"+str(len(self.todays_work["tbd"]))+" "+str(len(self.reactive_work["tbd"]))+" "+str(self.getNumUnassignedWork()), "runbotworks", self)
                    botTodos, runType = self.checkNextToRun()
                    log3("fp profiles of mission: "+json.dumps([m.getFingerPrintProfile() for i, m in enumerate(self.missions) if i < 3 or i > len(self.missions)-4]), "runbotworks", self)
                    if botTodos:
                        log3("working on..... "+botTodos["name"], "runbotworks", self)
                        self.working_state = "running_working"

                        if botTodos["name"] == "automation":
                            # run 1 bot's work
                            log3("running RPA.............."+json.dumps([m.getFingerPrintProfile() for m in self.missions]), "runbotworks", self)
                            if "Completed" not in botTodos["status"]:
                                log3("time to run RPA........"+json.dumps(botTodos), "runbotworks", self)
                                last_start = int(datetime.now().timestamp()*1)

                                current_bid, current_mid, run_result = await self.runRPA(botTodos, gui_rpa_queue, gui_monitor_queue)
                                last_end = int(datetime.now().timestamp()*1)

                            # else:
                                # now need to chop off the 0th todo since that's done by now....
                                #
                                log3("total # of works:"+str(botTodos["current widx"])+":"+str(len(botTodos["works"])), "runbotworks", self)
                                if current_mid >= 0:
                                    current_run_report = self.genRunReport(runType, last_start, last_end, current_mid, current_bid, run_result)

                                # if all tasks in the task group are done, we're done with this group.
                                if botTodos["current widx"] >= len(botTodos["works"]):
                                    log3("POP a finished task from queue after runRPA", "runbotworks", self)
                                    # update GUI display to move missions in this task group to the completed missions list.
                                    if self.todays_work["tbd"][0]:
                                        log3("None empt first WORK GROUP", "runbotworks", self)
                                        just_finished = copy.deepcopy(self.todays_work["tbd"][0])
                                        self.updateCompletedMissions(just_finished)
                                        self.todays_completed.append(just_finished)

                                        finished = self.todays_work["tbd"].pop(0)
                                        log3("JUST FINISHED A WORK GROUP:"+json.dumps(finished), "runbotworks", self)
                                    else:
                                        log3("empty first WORK GROUP", "runbotworks", self)


                                if len(self.todays_work["tbd"]) == 0:
                                    if self.host_role == "Platoon":
                                        log3("Platoon Done with today!!!!!!!!!", "runbotworks", self)
                                        await self.doneWithToday()
                                    else:
                                        # check whether we have collected all reports so far, there is 1 count difference between,
                                        # at this point the local report on this machine has not been added to toddaysReports yet.
                                        # this will be done in doneWithToday....
                                        log3("n todaysPlatoonReports: "+str(len(self.todaysPlatoonReports))+" n todays_completed: "+str(len(self.todays_completed)), "runbotworks", self)
                                        log3("todaysPlatoonReports"+json.dumps(self.todaysPlatoonReports), "runbotworks", self)
                                        log3("todays_completed"+json.dumps(self.todays_completed), "runbotworks", self)
                                        if len(self.todaysPlatoonReports) == self.num_todays_task_groups:
                                            log3("Commander Done with today!!!!!!!!!", "runbotworks", self)
                                            await self.doneWithToday()
                        else:
                            log3("Unrecogizable todo...."+botTodos["name"], "runbotworks", self)
                            log3("POP a unrecognized task from queue", "runbotworks", self)
                            self.todays_work["tbd"].pop(0)

                    else:
                        # nothing to do right now. check if all of today's work are done.
                        # if my own works are done and all platoon's reports are collected.
                        print("empty to do...")
                        if self.host_role == "Platoon":
                            if len(self.todays_work["tbd"]) == 0:
                                await self.doneWithToday()
                            else:
                                self.todays_work["tbd"].pop(0)

                if self.working_state != "running_idle":
                    # clear to make next round ready to work
                    self.working_state = "running_idle"

                log3("running bot works whenever there is some to run....", "runbotworks", self)
                await asyncio.sleep(3)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "Errorwanrunbotworks:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "Errorwanrunbotworks traceback information not available:" + str(e)
            log3(ex_stat, "runbotworks", self)

    def checkManagerToRuns(self, managerMissions):
        """
        Determine which missions are ready to run based on their schedule.

        Args:
            managerMissions (list): A list of mission data structures.

        Returns:
            list: Missions ready to run.
        """
        try:
            missions_to_run = []
            current_time = datetime.now()

            for mission in managerMissions:
                print("checking next to run mission:", mission.getMid())
                # Parse repeat_last and repeat_until as datetime
                repeat_last = datetime.strptime(mission.getRepeatLast(), "%Y-%m-%d %H:%M:%S")
                repeat_until = datetime.strptime(mission.getRepeatUntil(), "%Y-%m-%d")
                print("repeat_last, repeat_until:", mission.getRepeatLast(), mission.getRepeatUntil())
                # Get the time slot as hours and minutes
                esttime_index = int(mission.getEstimatedStartTime())  # Index of the 15-min time slot (0–95)
                print("esttime_index", esttime_index)
                hours, minutes = divmod(esttime_index * 15, 60)
                print("hours, minutes:", hours, minutes)

                # Determine the baseline date for repetition
                if mission.getRepeatOn() == "now":
                    if mission.getRepeatType() == "by day":
                        repeat_on_date = datetime.strptime(mission.getEsd(), "%Y-%m-%d")
                    else:
                        repeat_on_date = current_time.date()
                elif mission.getRepeatOn() in self.static_resource.WEEK_DAY_TYPES:
                    repeat_on_date = self._get_next_weekday_date(mission.getRepeatOn())
                else:
                    repeat_on_date = datetime.strptime(mission.getRepeatOn(), "%Y-%m-%d").date()

                print("repeat on date::", repeat_on_date)
                # Combine the baseline date with the time slot
                repeat_on_time = datetime.combine(repeat_on_date, datetime.min.time()).replace(hour=hours, minute=minutes)
                print("repeat on time::", repeat_on_date)

                # Check for non-repeating missions
                if mission.getRepeatType() == "none":
                    if current_time >= repeat_on_time:
                        missions_to_run.append(mission)
                        continue

                # Check for repeating missions
                elif mission.getRepeatType() in self.static_resource.REPEAT_TYPES:
                    # Calculate the repeat interval
                    repeat_interval = self._compute_repeat_interval(mission.getRepeatUnit(), mission.getRepeatNumber(),
                                                                    repeat_on_time)

                    # Determine the supposed last scheduled repetition time
                    elapsed_time = (current_time - repeat_on_time).total_seconds()
                    elapsed_intervals = max(0, int(elapsed_time // repeat_interval.total_seconds())) if isinstance(
                        repeat_interval, timedelta) else self._calculate_elapsed_intervals_manual(repeat_on_time,
                                                                                                  current_time,
                                                                                                  repeat_interval)
                    supposed_last_run = repeat_on_time + elapsed_intervals * repeat_interval
                    print("supposed last run:", supposed_last_run)
                    # Calculate the next scheduled run
                    next_scheduled_run = supposed_last_run + repeat_interval
                    print("next scheduled run:", next_scheduled_run, "repeat_last::", repeat_last)

                    # If the current time is past the supposed last run, schedule the mission
                    if current_time <= repeat_until:
                        if repeat_last < (supposed_last_run - repeat_interval*0.5) or current_time >= next_scheduled_run:
                            print("time to run now....")
                            missions_to_run.append(mission)
                        elif self.debug_mode:
                            if self.fetch_schedule_counter:
                                missions_to_run.append(mission)
                                self.fetch_schedule_counter = self.fetch_schedule_counter -1


        except Exception as e:
            # Log and skip errors gracefully
            ex_stat = f"Error in check manager to runs: {traceback.format_exc()} {str(e)}"
            missions_to_run = []
            print(ex_stat)

        return missions_to_run

    def _compute_repeat_interval(self, repeat_unit, repeat_number, start_time):
        """
        Calculate the interval for repetition using timedelta.

        Args:
            repeat_unit (str): Unit of repetition ("second", "minute", "hour", etc.).
            repeat_number (int): Number of units for the interval.

        Returns:
            timedelta: The repeat interval.
        """
        if repeat_unit == "second":
            interval = timedelta(seconds=repeat_number)
        elif repeat_unit == "minute":
            interval = timedelta(minutes=repeat_number)
        elif repeat_unit == "hour":
            interval = timedelta(hours=repeat_number)
        elif repeat_unit == "day":
            interval = timedelta(days=repeat_number)
        elif repeat_unit == "week":
            interval = timedelta(weeks=repeat_number)
        elif repeat_unit == "month":
            interval = self._add_months(start_time, repeat_number)  # Custom month logic
        elif repeat_unit == "year":
            interval = self._add_years(start_time, repeat_number)  # Custom year logic
        else:
            print("invalid repeat unit")
            raise ValueError(f"Invalid repeat_unit: {repeat_unit}")

        print("interval:", interval)
        return interval

    def _add_months(self, start_time, months):
        """
        Manually add months to a datetime, adjusting for month overflow.

        Args:
            start_time (datetime): The starting date.
            months (int): Number of months to add.

        Returns:
            datetime: The resulting datetime.
        """
        new_month = (start_time.month - 1 + months) % 12 + 1
        year_increment = (start_time.month - 1 + months) // 12
        new_year = start_time.year + year_increment

        # Handle day overflow (e.g., adding 1 month to Jan 31 should result in Feb 28/29)
        try:
            updated_start_time = start_time.replace(year=new_year, month=new_month)
            print("month updated start time:", updated_start_time)
            return updated_start_time
        except ValueError:
            # For invalid days (e.g., Feb 30), use the last day of the month
            updated_start_time = start_time.replace(year=new_year, month=new_month, day=28) + timedelta(days=1) - timedelta(days=1)
            print("error month updated start time:", updated_start_time)
            return updated_start_time

    def _add_years(self, start_time, years):
        """
        Manually add years to a datetime, adjusting for leap years.

        Args:
            start_time (datetime): The starting date.
            years (int): Number of years to add.

        Returns:
            datetime: The resulting datetime.
        """
        try:
            updated_start_time = start_time.replace(year=start_time.year + years)
            print("year updated start time:", updated_start_time)
            return updated_start_time
        except ValueError:
            # For Feb 29 on non-leap years, fallback to Feb 28
            updated_start_time = start_time.replace(year=start_time.year + years, day=28)
            print("error year updated start time:", updated_start_time)
            return updated_start_time

    def _calculate_elapsed_intervals_manual(self, start_time, current_time, interval):
        """
        Calculate the number of elapsed intervals for manual month/year intervals.

        Args:
            start_time (datetime): The baseline start time.
            current_time (datetime): The current time.
            interval: Function to calculate the next interval (e.g., _add_months).

        Returns:
            int: Number of elapsed intervals.
        """
        intervals = 0
        next_time = start_time

        while next_time <= current_time:
            next_time = interval(next_time)
            intervals += 1

        print("intervals:", intervals)
        return intervals - 1  # Subtract 1 because the last addition exceeds current_time


    def _get_next_weekday_date(self, target_weekday):
        """
        Calculate the date of the next occurrence of the target weekday.

        Args:
            target_weekday (str): Target weekday ("M", "Tu", "W", etc.).

        Returns:
            date: The date of the next occurrence of the target weekday.
        """
        weekday_map = {"M": 0, "Tu": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5, "Su": 6}
        current_date = datetime.now()
        current_weekday = current_date.weekday()
        target_weekday_num = weekday_map[target_weekday]
        print("target_weekday_num", target_weekday_num)
        days_ahead = (target_weekday_num - current_weekday) % 7
        if days_ahead == 0:  # If today is the target weekday, schedule for the next week
            days_ahead = 7

        print("days_ahead", days_ahead)
        next_week_day = (current_date + timedelta(days=days_ahead)).date()
        print("next week day:", next_week_day)
        return next_week_day



    async def runManagerMissions(self, missions, in_queue, out_team_queue, out_gui_queue):
        for mission in missions:
            #update the mission's last repeat time.
            mission.updateRepeatLast()
            await self.run1ManagerMission(mission, in_queue, out_team_queue, out_gui_queue)


    def genOneTimeMissionWithSkill(self, skid, mtype, botid):
        # simply search the past mission and check whether there are
        # already mission running this skill, if there is simply copy it and run.
        # if nothing found, then create a brand new mission on the fly.
        foundMission = next((x for i, x in enumerate(self.missions) if x.getSkills().startswith(str(skid)+',')), None)
        if foundMission:
            log3(f"duplicate the found mission {foundMission.getMid()}", "runmanagerworks", self)
            # newMisssion = copy.deepcopy(foundMission)
            newMisssion = foundMission
        else:
            log3(f"create a new mission based on skill {skid}...", "runmanagerworks", self)
            today = datetime.now()
            formatted_date = today.strftime("%Y-%m-%d")
            future_date = today + timedelta(days=1)
            formatted_future = future_date.strftime("%Y-%m-%d")
            far_future_date = today + timedelta(days=1000)
            formatted_far_future = far_future_date.strftime("%Y-%m-%d")
            mdbd = MissionModel()
            mdbd.mid = 0
            mdbd.ticket = 0
            mdbd.botid = botid
            mdbd.status = "Assiggned"
            mdbd.createon = formatted_date
            mdbd.owner = self.owner
            mdbd.esd = formatted_date
            mdbd.ecd = formatted_date
            mdbd.asd = formatted_future
            mdbd.abd = formatted_future
            mdbd.aad = formatted_future
            mdbd.afd = formatted_future
            mdbd.acd = formatted_future
            mdbd.actual_start_time = 0
            mdbd.est_start_time = 0
            mdbd.actual_runtime = 0
            mdbd.est_runtime = 30
            mdbd.n_retries = 3
            mdbd.cuspas = "win,chrome,amz"
            mdbd.category = ""
            mdbd.phrase = ""
            mdbd.pseudoStore = ""
            mdbd.pseudoBrand = ""
            mdbd.pseudoASIN = ""
            mdbd.type = mtype
            mdbd.config = "{}"
            mdbd.skills = str(skid)
            mdbd.delDate = formatted_far_future
            mdbd.asin = ""
            mdbd.store = ""
            mdbd.follow_seller = ""
            mdbd.brand = ""
            mdbd.img = ""
            mdbd.title = ""
            mdbd.rating = ""
            mdbd.feedbacks = ""
            mdbd.price = 0
            mdbd.follow_price = 0
            mdbd.fingerprint_profile = ""
            mdbd.original_req_file = ""
            mdbd.customer = ""
            mdbd.platoon = ""
            mdbd.result = ""
            mdbd.variations = ""
            mdbd.as_server = False
            newMisssion = EBMISSION(self)
            newMisssion.loadDBData(mdbd)

        return newMisssion


    # for now this is mainly used for after team run, a result to trigger some housekeeping work.
    # like process new orders, turn them into new missions, and so on....
    # the message will likely,
    async def processManagerNetMessage(self, msg, managers, in_queue, out_team_queue, out_gui_queue):
        print(f"recevied manager msg type: {msg['type']}")
        if msg["type"] in ManagerTriggerTable:
            otm = self.genOneTimeMissionWithSkill(ManagerTriggerTable[msg["type"]][0], ManagerTriggerTable[msg["type"]][1], managers[0].getBid())
            print("ready to run manager 1 mission....")
            result = await self.run1ManagerMission(otm, in_queue, out_team_queue, out_gui_queue)


    async def runmanagerworks(self, gui_manager_queue, manager_rpa_queue, gui_monitor_queue):
        # run all the work
        try:
            running = True
            while running:
                log3("runmanagerwork Task.....", "runmanagerworks", self)
                current_time = datetime.now()

                # check mission queue, how to make this flexible? (just run the mission)
                # check msg queue, (msg source: flask server, there needs to be a
                #                      api msg <-> handler skill table, there needs to be a
                #                       generic function to create a mission given the skill and run
                #                       it. and the skill can be overwritten with custom skill).
                # check time. @certain time, time based, read out all manager missions, user can
                #                  create missions and let them use certain skill and run at certain time.
                managerBots, managerMissions = self.findManagerMissionsOfThisVehicle()
                print("# manager missions:", len(managerMissions))
                managerToRun = self.checkManagerToRuns(managerMissions)

                if managerToRun:
                    print("there is some repeat type mission to run....")
                    await self.runManagerMissions(managerToRun, gui_manager_queue, manager_rpa_queue, gui_monitor_queue)

                if not gui_manager_queue.empty():
                    # Process all available messages in the queue
                    print("recevied manager queued msg...")
                    while not gui_manager_queue.empty():
                        net_message = await gui_manager_queue.get()
                        await self.processManagerNetMessage(net_message, managerBots, gui_manager_queue, manager_rpa_queue, gui_monitor_queue)
                else:
                    # always run some clean up after night
                    print("manager msg queue empty...")
                    if current_time.hour == 0 and current_time.minute < 10:
                        # do some data structure and state cleaning and get rid   the
                        # next day
                        log3("clear work related data structure", "runmanagerworks", self)
                        self.todays_scheduled_task_groups = {}
                        self.unassigned_scheduled_task_groups = {}  # per vehicle, flatten task list
                        self.unassigned_reactive_task_groups = {}
                        self.rpa_work_assigned_for_today = False

                    # start work after 5:30am
                    target_time = current_time.replace(hour=5, minute=30, second=0, microsecond=0)
                    # if manually start platoon after 5:30am, and if todays_scheduled_task_groups
                    # still empty, then check todo file.....
                    if current_time > target_time and "Platoon" in self.machine_role:
                        if not self.todays_scheduled_task_groups:
                            # check the local schedule file. if there, load it.
                            yyyymmdd = current_time.strftime("%Y%m%d")
                            sf_name = "todos" + yyyymmdd + ".json"
                            todays_todo_file = os.path.join(self.my_ecb_data_homepath + "/runlogs", sf_name)
                            # with todays_todo_file name this won't run on commander.
                            if os.path.exists(todays_todo_file):
                                if os.path.getsize(todays_todo_file) > 128:
                                    with open(todays_todo_file, "r") as tdf:
                                        msg = json.load(tdf)
                                        tdf.close()

                                        self.setupScheduledTodos(msg)
                                else:
                                    print("WARNING: invalid todo file")



                await asyncio.sleep(3)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "Errorwanrunmanagerworks:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "Errorwanrunmanagerworks traceback information not available:" + str(e)
            log3(ex_stat, "runmanagerworks", self)


    def setupScheduledTodos(self, msg):
        if msg:
            localworks = msg["todos"]
            self.addBotsMissionsSkillsFromCommander(msg["bots"], msg["missions"], msg["skills"])

            # this is the time to rebuild skills to make them up to date....
            self.dailySkillsetUpdate()

            log3("received work request:"+json.dumps(localworks), "serveCommander", self)
            # send work into work Queue which is the self.todays_work["tbd"] data structure.

            self.todays_work["tbd"].append({"name": "automation", "works": localworks, "status": "yet to start", "current widx": 0, "vname": self.machine_name+":"+self.os_short, "completed": [], "aborted": []})
            log3("after assigned work, "+str(len(self.todays_work["tbd"]))+" todos exists in the queue. "+json.dumps(self.todays_work["tbd"]), "serveCommander", self)

            platform_os = self.platform            # win, mac or linux
            vname = self.machine_name + ":" + self.os_short
            self.todays_scheduled_task_groups[vname] = localworks
            self.unassigned_scheduled_task_groups[vname] = localworks

            # generate ADS loadable batch profiles ((vTasks, vehicle, commander):)
            batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(localworks, self, self)
            # clean up the reports on this vehicle....
            self.todaysReports = []
            self.DONE_WITH_TODAY = False
        else:
            print("nothing to arrange to do....")

    #update a vehicle's missions status
    # rx_data is a list of mission status for each mission that belongs to the vehicle.
    def updateVMStats(self, rx_data):
        foundV = None
        for v in self.vehicles:
            if v.getIP() == rx_data["ip"]:
                log3("found vehicle by IP", "runbotworks", self)
                foundV = v
                break

        if foundV:
            log3("updating vehicle Mission status...", "runbotworks", self)
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
        # self.parent.vehicles.append(newV)
        self.vehicles.append(newV)

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
        # self.parent.vehicles.append(newV)
        self.vehicles.append(newV)

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
        # self.parent.vehicles.append(newV)
        self.vehicles.append(newV)

    # msg in json format
    # { sender: "ip addr", type: "intro/status/report", content : "another json" }
    # content format varies according to type.
    async def processPlatoonMsgs(self, msgString, ip):
        try:
            global running_step_index, fieldLinks
            fl_ips = [x["ip"] for x in fieldLinks]
            if len(msgString) < 128:
                log3("Platoon Msg Received:"+msgString+" from::"+ip+"  "+str(len(fieldLinks)) + json.dumps(fl_ips))
            else:
                log3("Platoon Msg Received: ..." + msgString[-127:0] + " from::" + ip + "  " + str(len(fieldLinks)) + json.dumps(
                    fl_ips))
            msg = json.loads(msgString)

            found = next((x for x in fieldLinks if x["ip"] == ip), None)
            found_vehicle = next((x for x in self.vehicles if x.getIP() == msg["ip"]), None)

            # first, check ip and make sure this from a know vehicle.
            if msg["type"] == "intro" or msg["type"] == "pong":
                if found:
                    self.showMsg("recevied a vehicle introduction/pong:" + msg["content"]["name"] + ":" + msg["content"]["os"] + ":"+ msg["content"]["machine"])

                    if found_vehicle:
                        print("found a vehicle to set.... "+found_vehicle.getOS())
                        if "connecting" in found_vehicle.getStatus():
                            found_vehicle.setStatus("running_idle")

                        if "Windows" in msg["content"]["os"]:
                            found_vehicle.setOS("Windows")
                            found_vehicle.setName(msg["content"]["name"]+":win")
                        elif "Mac" in msg["content"]["os"]:
                            found_vehicle.setOS("Mac")
                            found_vehicle.setName(msg["content"]["name"] + ":mac")
                        elif "Lin" in msg["content"]["os"]:
                            found_vehicle.setOS("Linux")
                            found_vehicle.setName(msg["content"]["name"] + ":linux")

                        print("now found vehicle" + found_vehicle.getName() + " " + found_vehicle.getOS())
                        # this is a good juncture to update vehicle status on cloud and local DB and JSON file.
                        #  now
                        vehicle_report = self.prepVehicleReportData(found_vehicle)
                        resp = send_report_vehicles_to_cloud(self.session,
                                                             self.tokens['AuthenticationResult']['IdToken'],
                                                             vehicle_report,
                                                             self.getWanApiEndpoint())
                        self.saveVehiclesJsonFile()

                        # sync finger print profiles from that vehicle.
                        if  msg["type"] == "pong":
                            self.syncFingerPrintOnConnectedVehicle(found_vehicle)

            elif msg["type"] == "status":
                # update vehicle status display.
                self.showMsg(msg["content"])
                log3("msg type:" + "status", "servePlatoons", self)
                self.showMsg("recevied a status update message:"+msg["content"])
                if self.platoonWin:
                    self.showMsg("updating platoon WIN")
                    self.platoonWin.updatePlatoonStatAndShow(msg, fieldLinks)
                    self.platoonWin.show()
                else:
                    self.showMsg("ERROR: platoon win not yet exists.......")

                self.updateVMStats(msg)

                # update mission status to the cloud and to local data structure and to chat？
                # "mid": mid,
                # "botid": self.missions[mid].getBid(),
                # "sst": self.missions[mid].getEstimatedStartTime(),
                # "sd": self.missions[mid].getEstimatedRunTime(),
                # "ast": self.missions[mid].getActualStartTime(),
                # "aet": self.missions[mid].getActualEndTime(),
                # "status": m_stat,
                # "error": m_err
                if msg["content"]:
                    mStats = json.loads(msg["content"])

                    self.updateMStats(mStats)
                else:
                    print("WARN: status contents empty.")

            elif msg["type"] == "report":
                # collect report, the report should be already organized in json format and ready to submit to the network.
                log3("msg type:"+"report", "servePlatoons", self)
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

                # update vehicle status, now becomes idle again.
                self.updateVehicleStatusToRunningIdle(msg["ip"])

                # keep statistics on all platoon runs.
                if len(self.todaysPlatoonReports) == self.num_todays_task_groups:
                    # check = all(item in List1 for item in List2)
                    # this means all reports are collected, this is the last missing piece, ready to send to cloud.
                    await self.doneWithToday()
                    self.num_todays_task_groups = 0
            elif msg["type"] == "botsADSProfilesUpdate":
                log3("received botsADSProfilesUpdate message", "servePlatoons", self)
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receivePlatoonBotsADSProfileUpdateMessage(msg)
            elif msg["type"] == "botsADSProfilesBatchUpdate":
                log3("received botsADSProfilesBatchUpdate message", "servePlatoons", self)
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                remote_outdated = self.receiveBotsADSProfilesBatchUpdateMessage(msg)
                self.expected_vehicle_responses[found_vehicle.getName()] = "Yes"

                if self.allResponded():
                    log3("all ads profiles updated...", "servePlatoons", self)
                    self.botsFingerPrintsReady = True

                if remote_outdated:
                    log3("remote outdated...", "servePlatoons", self)
                    self.batchSendFingerPrintProfilesToCommander(remote_outdated)

                # now the profiles are updated. send this vehicle's schedule to it.
                vname = found_vehicle.getName()
                log3("setup vehicle to do some work..."+vname, "servePlatoons", self)

                if self.unassigned_scheduled_task_groups:
                    if vname in self.unassigned_scheduled_task_groups:
                        p_task_groups = self.unassigned_scheduled_task_groups[vname]
                    else:
                        print(f"{vname} not found in unassigned_scheduled_task_groups empty")
                        print("keys:", list(self.unassigned_scheduled_task_groups.keys()))
                        p_task_groups = []
                else:
                    if self.todays_scheduled_task_groups:
                        if vname in self.todays_scheduled_task_groups:
                            p_task_groups = self.todays_scheduled_task_groups[vname]
                        else:
                            print(f"{vname} not found in todays_scheduled_task_groups empty")
                            print("keys:", list(self.todays_scheduled_task_groups.keys()))
                            p_task_groups = []
                    else:
                        print("time stamp "+datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]+" todays_scheduled_task_groups empty")
                        p_task_groups = []
                await self.vehicleSetupWorkSchedule(found_vehicle, p_task_groups)

            elif msg["type"] == "missionResultFile":
                self.showMsg("received missionResultFile message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receivePlatoonMissionResultFilesMessage(msg)

            elif msg["type"] == "reqResendWorkReq":
                log3("received reqResendWorkReq message")
                # get work for this vehicle and send setWork
                self.reGenWorksForVehicle(found_vehicle)
                # self.vehicleSetupWorkSchedule(found_vehicle, self.todays_scheduled_task_groups)

            elif msg["type"] == "chat":
                log3("received chat message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotChatMessage(msg["content"])

            elif msg["type"] == "exlog":
                self.showMsg("received exlog message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                self.receiveBotLogMessage(msg["content"])
            elif msg["type"] == "heartbeat":
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text

                if found_vehicle:
                    # this will set status as well as the last_update_time parameter
                    if found_vehicle.getStatus() != msg["content"]["vstatus"]:
                        found_vehicle.setStatus(msg["content"]["vstatus"])

                log3("Heartbeat From Vehicle: "+msg["ip"], "servePlatoons", self)
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
            log3(ex_stat, "servePlatoons", self)

            self.showMsg(ex_stat)

    def allResponded(self):
        alldone = False

        alldone = all([self.expected_vehicle_responses[v] for v in self.expected_vehicle_responses])

        return alldone


    # what's received here is a ADS profile for one individual bot, for safety, save the existing
    # file to file.old so that we at least always have two copies and in case something is wrong
    # we can at least go back to the previous copy.
    def receivePlatoonBotsADSProfileUpdateMessage(self, pMsg):
        file_name = self.my_ecb_data_homepath + pMsg["file_name"]           # msg["file_name"] should start with "/"
        file_name_wo_extension = os.path.basename(file_name).split(".")[0]
        file_name_dir = os.path.dirname(file_name)
        new_filename = file_name_dir + "/" + file_name_wo_extension + "_old.txt"
        os.rename(file_name, new_filename)

        file_type = pMsg["file_type"]
        file_contents = pMsg["file_contents"].encode('latin1')  # Encode string to binary data
        with open(file_name, 'wb') as file:
            file.write(file_contents)
            file.close()

    def receiveBotsADSProfilesBatchUpdateMessage(self, pMsg):
        """
            Receive multiple fingerprint profiles sent from the sender side.
            Args:
                pMsg: A dictionary containing:
                      - "profiles": A list of dictionaries, each containing:
                          - "file_name": The name of the file to be saved
                          - "file_type": The type of the file (e.g., txt)
                          - "timestamp": The timestamp of the incoming file
                          - "file_contents": The base64-encoded content of the file
            """
        try:
            remote_outdated = []
            profiles = pMsg.get("profiles", [])
            if not profiles:
                log3("ErrorReceiveBatchProfiles: No profiles received.")
                return

            for profile in profiles:
                # Resolve full file path
                file_name = os.path.basename(profile["file_name"])
                incoming_file_name = os.path.join(self.ads_profile_dir, file_name)
                incoming_file_timestamp = profile.get("timestamp")
                file_contents = base64.b64decode(profile["file_contents"])  # Decode base64-encoded binary data

                # Check if the file already exists
                if os.path.exists(incoming_file_name):
                    # Compare timestamps
                    existing_file_timestamp = os.path.getmtime(incoming_file_name)

                    if incoming_file_timestamp > existing_file_timestamp:
                        # Incoming file is newer, replace the existing file
                        with open(incoming_file_name, "wb") as file:
                            file.write(file_contents)

                        os.utime(incoming_file_name, (incoming_file_timestamp, incoming_file_timestamp))
                        log3(f"Updated profile: {incoming_file_name} (newer timestamp)")
                    else:
                        # Incoming file is older, skip saving
                        if incoming_file_timestamp < existing_file_timestamp:
                            remote_outdated.append(incoming_file_name)
                        log3(f"Skipped profile: {incoming_file_name} (existing file is newer or the same)")
                else:
                    # File doesn't exist, save it
                    with open(incoming_file_name, "wb") as file:
                        file.write(file_contents)
                    # Optionally, set the timestamp to the incoming file's timestamp (if desired)
                    os.utime(incoming_file_name, (incoming_file_timestamp, incoming_file_timestamp))
                    log3(f"Saved new profile: {incoming_file_name}")

                log3(f"Successfully updated profile: {incoming_file_name}")
            return remote_outdated

        except Exception as e:
            # Handle and log errors
            traceback_info = traceback.extract_tb(e.__traceback__)
            if traceback_info:
                ex_stat = "ErrorReceiveBatchFPProfiles:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorReceiveBatchFPProfiles: traceback information not available:" + str(e)
            self.showMsg(ex_stat)


    def receivePlatoonMissionResultFilesMessage(self, pMsg):
        file_name = pMsg["file_name"]           # msg["file_name"] should start with "/"

        file_contents = pMsg["file_contents"].encode('latin1')  # Encode string to binary data
        with open(file_name, 'wb') as file:
            file.write(file_contents)
            file.close()


    def updateCompletedMissions(self, finished):
        finished_works = finished["works"]
        finished_mids = []
        finished_midxs = []
        finished_missions = []

        # Log all current mission IDs
        self.showMsg("All mission ids: " + json.dumps([m.getMid() for m in self.missions]))

        # Collect all finished mission IDs
        if len(finished_works) > 0:
            for bi in range(len(finished_works)):
                finished_mids.append(finished_works[bi]["mid"])
        self.showMsg("Finished MIDS: " + json.dumps(finished_mids))

        # Find the indexes of the finished missions in the missions list
        for mid in finished_mids:
            found_i = next((i for i, mission in enumerate(self.missions) if mission.getMid() == mid), -1)
            self.showMsg("Found midx: " + str(found_i))
            if found_i >= 0:
                finished_midxs.append(found_i)

        # Sort the finished mission indexes
        sorted_finished_midxs = sorted(finished_midxs, key=lambda midx: midx, reverse=True)
        self.showMsg("Finished MID INDEXES: " + json.dumps(sorted_finished_midxs))

        # Iterate through the sorted mission indexes
        for midx in sorted_finished_midxs:
            found_mission = self.missions[midx]

            # Log the mission status
            self.showMsg(f"Just finished mission [{found_mission.getMid()}] status: {found_mission.getStatus()}")

            # Ensure the mission is still valid and not deleted
            if found_mission is None or not found_mission:
                self.showMsg("Mission object is invalid or already deleted.")
                continue  # Skip to the next mission if this one is invalid

            # Try to update the mission icon safely
            try:
                if "Completed" in found_mission.getStatus():
                    found_mission.setMissionIcon(QIcon(self.file_resource.mission_success_icon_path))
                else:
                    found_mission.setMissionIcon(QIcon(self.file_resource.mission_failed_icon_path))
            except RuntimeError as e:
                self.showMsg(f"Error setting mission icon: {str(e)}")
                continue  # Skip to the next mission if there's an error

            # Safely handle the removal from missionModel and addition to completedMissionModel
            try:
                for item in self.missionModel.findItems(
                        'mission' + str(found_mission.getMid()) + ":Bot" + str(found_mission.getBid()) + ":" +
                        found_mission.pubAttributes.ms_type + ":" + found_mission.pubAttributes.site):
                    # Clone the item before removing it from missionModel
                    cloned_item = item.clone()
                    self.completedMissionModel.appendRow(cloned_item)

                    # Remove the original item from missionModel safely
                    self.missionModel.removeRow(item.row())

            except Exception as e:
                self.showMsg(f"Error moving mission from missionModel to completedMissionModel: {str(e)}")


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

    def platoonHasNoneTodo(self):
        none2do = True
        if self.machine_role == "Platoon":
            platform_os = self.platform
            vname = self.machine_name + ":" + self.os_short
            # check either some RPA is being run right now, or today's rpa has being all done.
            if self.working_state == "running_working" or \
                self.todays_scheduled_task_groups[vname] or \
                self.unassigned_scheduled_task_groups[vname] or \
                self.DONE_WITH_TODAY:
                none2do = False

        return none2do


    async def todo_wait_in_line(self, request):
        try:
            print("task waiting in line.....", request)
            await self.gui_net_msg_queue.put(request)
            print("todo now in line....", datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
            return("rpa tasks queued")
        except Exception as e:
            ex_stat = "ErrorPlatoonWaitInLine:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")
            return (f"Error: {ex_stat}")


    async def rpa_wait_in_line(self, request):
        try:
            print("task waiting in line.....")
            await self.gui_rpa_msg_queue.put(request)
            print("rpa tasks now in line....", datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        except Exception as e:
            ex_stat = "ErrorRPAWaitInLine:" + traceback.format_exc() + " " + str(e)
            print(f"{ex_stat}")


    async def serveCommander(self, msgQueue):
        log3("starting serve Commanders", "serveCommander", self)
        heartbeat = 0
        while True:
            try:
                heartbeat = heartbeat + 1
                if heartbeat > 255:
                    heartbeat = 0

                if heartbeat%16 == 0:
                    # sends a heart beat to commander

                    hbJson = {
                        "ip": self.ip,
                        "type": "heartbeat",
                        "content" : {
                            "vstatus": self.working_state,
                            "running_mid": self.running_mission.getMid() if self.running_mission else 0,
                            "running_instruction": running_step_index
                        }
                    }
                    msg = json.dumps(hbJson)
                    # send to commander
                    msg_with_delimiter = msg + "!ENDMSG!"
                    log6("platoon heartbeat", "wan_log", self, self.running_mission, running_step_index, "~^v^v~")
                    if self.commanderXport:
                        log3("sending heartbeat", "serveCommander", self)
                        if self.commanderXport and not self.commanderXport.is_closing():
                            self.commanderXport.write(msg_with_delimiter.encode('utf8'))
                        # self.commanderXport.get_loop().call_soon(lambda: print("HB MSG SENT2COMMANDER..."))
                elif heartbeat%19 == 0:
                    # no need to do this, just make sure commander always send set schedule command
                    # after a ping-pong sequence...... and after syncing fingerprint profiles....
                    if False and self.platoonHasNoneTodo():
                        workReq = {"type": "reqResendWorkReq", "ip": self.ip, "content": "now"}
                        await self.send_json_to_commander(self.commanderXport, workReq)
            except (json.JSONDecodeError, AttributeError) as e:
                # Handle JSON encoding or missing attributes issues
                log3(f"Error encoding heartbeat JSON or missing attribute: {e}", "serveCommander", self)
            except OSError as e:
                # Handle network-related errors
                log3(f"Error sending heartbeat to Commander: {e}", "serveCommander", self)

            print("serving commander, checking queue...")
            if not msgQueue.empty():
                try:
                    net_message = await msgQueue.get()
                    # log3("From Commander, recevied queued net message: "+net_message, "serveCommander", self)
                    self.processCommanderMsgs(net_message)
                    msgQueue.task_done()
                except asyncio.QueueEmpty:
                    # If for some reason the queue is unexpectedly empty, handle it
                    log3("Queue unexpectedly empty when trying to get message.", "serveCommander", self)
                except Exception as e:
                    # Catch any other issues while processing the message
                    traceback_info = traceback.extract_tb(e.__traceback__)
                    # Extract the file name and line number from the last entry in the traceback
                    log3("Error processing commander msg:" + traceback.format_exc() + " " + str(e), "serveCommander", self)


            await asyncio.sleep(2)
            # log3("watching Commanders...", "serveCommander", self)

    def todoAlreadyExists(self, msg):
        exists = False
        today = datetime.now()
        # Format the date as yyyymmdd
        yyyymmdd = today.strftime("%Y%m%d")
        sf_name = "todos" + yyyymmdd + ".json"
        todays_todo_file = os.path.join(self.my_ecb_data_homepath + "/runlogs", sf_name)

        if os.path.exists(todays_todo_file):
            exists = True

        return exists

    def saveTodaysTodos(self, msg):
        today = datetime.now()
        # Format the date as yyyymmdd
        yyyymmdd = today.strftime("%Y%m%d")
        sf_name = "todos" + yyyymmdd + ".json"
        todays_todo_file = os.path.join(self.my_ecb_data_homepath + "/runlogs", sf_name)
        # print("msg:", msg)
        if msg['todos']:
            with open(todays_todo_file, "w") as tdf:
                json.dump(msg, tdf, indent=4)
                tdf.close()



    # '{"cmd":"reqStatusUpdate", "missions":"all"}'
    # content format varies according to type.
    def processCommanderMsgs(self, msgString):
        try:
            if len(msgString) > 256:
                log3("received from commander: " + msgString[:255] + "...", "serveCommander", self)
            else:
                log3("received from commander: "+msgString, "serveCommander", self)
            if "!connection!" in msgString:
                msg = {"cmd": "connection"}
                msg_parts = msgString.split("!")
                self.commanderIP = msg_parts[0]
                self.commanderName = msg_parts[2]

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
                    self.sendCommanderMissionsStatMsg(mids)

            elif msg["cmd"] == "reqSendFile":
                # update vehicle status display.
                log3("received a file: "+msg["file_name"], "serveCommander", self)
                file_name = self.ads_profile_dir + msg["file_name"]
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

                if not self.todoAlreadyExists(msg):
                    if msg:
                        self.saveTodaysTodos(msg)
                        self.setupScheduledTodos(msg)
                else:
                    log3("commander sent todos exists in the queue. "+json.dumps(self.todays_work["tbd"]), "serveCommander", self)

            elif msg["cmd"] == "reqSetReactiveWorks":
                # schedule work now..... append to array data structure and set up the pointer to the 1st task.
                # the actual running of the tasks will be taken care of by the schduler.
                localworks = msg["todos"]
                self.addBotsMissionsSkillsFromCommander(msg["bots"], msg["missions"], msg["skills"])

                log3("received reactive work request:"+json.dumps(localworks), "serveCommander", self)
                # send work into work Queue which is the self.todays_work["tbd"] data structure.

                self.reactive_work["tbd"].append({"name": "automation", "works": localworks, "status": "yet to start", "current widx": 0, "vname": self.machine_name+":"+self.os_short, "completed": [], "aborted": []})
                log3("after assigned work, "+str(len(self.todays_work["tbd"]))+" todos exists in the queue. "+json.dumps(self.todays_work["tbd"]), "serveCommander", self)

                platform_os = self.platform            # win, mac or linux
                vname = self.machine_name + ":" + self.os_short
                self.todays_scheduled_task_groups[vname] = localworks
                self.unassigned_scheduled_task_groups[vname] = localworks

                # generate ADS loadable batch profiles ((vTasks, vehicle, commander):)
                batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(localworks, self, self)

                # clean up the reports on this vehicle....
                self.todaysReports = []
                self.DONE_WITH_TODAY = False

            elif msg["cmd"] == "reqCancelAllMissions":
                # update vehicle status display.
                log3(json.dumps(msg["content"]), "serveCommander", self)
                self.sendRPAMessage(msg_data)
            elif msg["cmd"] == "reqHaltMissions":
                # update vehicle status display.
                log3(json.dumps(msg["content"]), "serveCommander", self)
                self.sendRPAMessage(msg_data)
                # simply change the mission's status to be "Halted" again, this will make task runner to run this mission
            elif msg["cmd"] == "reqResumeMissions":
                # update vehicle status display.
                log3(json.dumps(msg["content"]), "serveCommander", self)
                self.sendRPAMessage(msg_data)
                # simply change the mission's status to be "Scheduled" again, this will make task runner to run this mission
            elif msg["cmd"] == "reqAddMissions":
                # update vehicle status display.
                log3(json.dumps(msg["content"]), "serveCommander", self)
                # this is for manual generated missions, simply added to the todo list.
            elif msg["cmd"] == "reqSyncFingerPrintProfiles":
                # update vehicle status display.
                # print("profile syncing request received.....")
                # log3(json.dumps(msg["content"]), "serveCommander", self)
                # first gather all finger prints and update them to the latest
                localFingerPrintProfiles = self.gatherFingerPrints()
                self.batchSendFingerPrintProfilesToCommander(localFingerPrintProfiles)

            elif msg["cmd"] == "botsADSProfilesBatchUpdate":
                log3("received commander botsADSProfilesBatchUpdate message")
                # message format {type: chat, msg: msg} msg will be in format of timestamp>from>to>text
                outdated = self.receiveBotsADSProfilesBatchUpdateMessage(msg)
                print("any outdated remote:", outdated)

            elif msg["cmd"] == "ping":
                # respond to ping with pong
                self_info = {"name": platform.node(), "os": platform.system(), "machine": platform.machine()}
                resp = {"ip": self.ip, "type":"pong", "content": self_info}
                # send to commander
                log3("sending "+json.dumps(resp)+ " to commanderIP - " + self.commanderIP, "serveCommander", self)
                print(self.commanderXport)
                msg = json.dumps(resp)
                msg_with_delimiter = msg + "!ENDMSG!"
                if self.commanderXport and not self.commanderXport.is_closing():
                    self.commanderXport.write(msg_with_delimiter.encode('utf8'))
                # asyncio.get_running_loop().call_soon(lambda: print("PONG MSG SENT2COMMANDER..."))

                log3("pong sent!", "serveCommander", self)

            elif msg["cmd"] == "chat":
                # update vehicle status display.
                log3(json.dumps(msg), "serveCommander", self)
                # this message is a chat to a bot/bot group, so forward it to the bot(s)
                # first, find out the bot's queue(which is kind of a temp mailbox for the bot and drop it there)
                self.receiveBotChatMessage(msg["message"])

        except Exception as e:
            # Catch any other issues while processing the message
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorwanProcessCommanderMsgs:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorwanProcessCommanderMsgs traceback information not available:" + str(e)
            log3(f"{ex_stat}", "serveCommander", self)

    def sendCommanderMissionsStatMsg(self, mids):
        statusJson = self.genMissionStatusReport(mids, False)
        msg = "{\"ip\": \"" + self.ip + "\", \"type\":\"status\", \"content\":\"" + json.dumps(statusJson).replace('"', '\\"') + "\"}"

        # Append the delimiter
        msg_with_delimiter = msg + "!ENDMSG!"
        # send to commander
        if self.commanderXport and not self.commanderXport.is_closing():
            self.commanderXport.write(msg_with_delimiter.encode('utf8'))
        # asyncio.get_running_loop().call_soon(lambda: print("MSTAT MSG SENT2COMMANDER..."))

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
    def genRunReport(self, run_type, last_start, last_end, current_mid, current_bid, run_status):
        statReport = None
        tzi = 0
        #only generate report when all done.
        if run_type == "scheduled":
            works = self.todays_work["tbd"][0]["works"]
        else:
            works = self.reactive_work["tbd"][0]["works"]

        if current_bid < 0:
            current_bid = 0

        # self.showMsg("GEN REPORT FOR WORKS:"+json.dumps(works))
        if not self.host_role == "Commander Only":
            current_mission = next((m for m in self.missions if m.getMid() == current_mid), None)
            if current_mission:
                mission_report = current_mission.genSummeryJson()
            else:
                mission_report = {}

            log3("mission_report:"+json.dumps(mission_report), "genRunReport", self)

            if self.host_role != "Platoon":
                # add generated report to report list....
                log3("commander gen run report....."+str(len(self.todaysReport)) + str(len(works)), "genRunReport", self)
                self.todaysReport.append(mission_report)
                # once all of today's task created a report, put the collection of reports into todaysPlatoonReports.
                # on commander machine, todaysPlatoonReports contains a collection of reports from each host machine
                if len(self.todaysReport) == len(works):
                    log3("time to pack today's non-platoon report", "genRunReport", self)
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
                    log3("time to pack today's platoon report", "genRunReport", self)
                    # rpt = {"ip": self.ip, "type": "report", "content": self.todaysReport}
                    # self.todaysPlatoonReports.append(rpt)
                    # self.todaysReport.append(rpt)

        log3(f"GEN REPORT FOR WORKS...[{len(self.todaysReport)}] {json.dumps(self.todaysReport[-1])}", "genRunReport", self)
        return self.todaysReport

    def updateMissionsStatsFromReports(self, all_reports):
        for rpt in all_reports:
            found = next((x for x in self.missions if x.getMid() == rpt["mid"]), None)
            if found:
                found.setStatus(rpt["status"])
                found.setActualStartTime(rpt["starttime"])
                found.setActualEndTime(rpt["endtime"])

    # this function if for all SCHEDULED work done today, now
    # 1) send report to the network,
    # 2) save report to local logs,
    # 3) clear today's work data structures.
    #
    async def doneWithToday(self):
        global commanderXport
        # call reportStatus API to send today's report to API
        log3("Done with today!", "doneWithToday", self)

        if not self.DONE_WITH_TODAY:
            self.DONE_WITH_TODAY = True
            self.rpa_work_assigned_for_today = False

            if not self.host_role == "Platoon":
                # if self.host_role == "Commander":
                #     self.showMsg("commander generate today's report")
                #     rpt = {"ip": self.ip, "type": "report", "content": self.todaysReports}
                #     self.todaysPlatoonReports.append(rpt)

                if len(self.todaysPlatoonReports) > 0:
                    # flatten the report data structure...
                    allTodoReports = [item for pr in self.todaysPlatoonReports for item in pr["content"]]
                    log3("ALLTODOREPORTS:"+json.dumps(allTodoReports), "doneWithToday", self)
                    # missionReports = [item for pr in allTodoReports for item in pr]
                else:
                    allTodoReports = []

                self.updateMissionsStatsFromReports(allTodoReports)

                log3("TO be sent to cloud side::"+json.dumps(allTodoReports), "doneWithToday", self)
                # if this is a commmander, then send report to cloud
                # send_completion_status_to_cloud(self.session, allTodoReports, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
                eodReportMsg = {
                    "type": "TEAM_REPORT",
                    "bid": "",
                    "report": allTodoReports
                }
                self.gui_manager_msg_queue.put(eodReportMsg)
            else:
                # if this is a platoon, send report to commander today's report is just an list mission status....
                if len(self.todaysReport) > 0:
                    rpt = {"ip": self.ip, "type": "report", "content": self.todaysReport}
                    # Append the delimiter
                    rpt_with_delimiter = json.dumps(rpt) + "!ENDMSG!"
                    log3("Sending report to Commander::"+json.dumps(rpt), "doneWithToday", self)
                    # self.commanderXport.write(str.encode(rpt_with_delimiter))
                    if self.commanderXport and not self.commanderXport.is_closing():
                        self.commanderXport.write(rpt_with_delimiter.encode('utf-8'))
                    # asyncio.get_running_loop().call_soon(lambda: print("DONE MSG SENT2..."))


                # also send updated bot ADS profiles to the commander for backup purose.
                # for bot_profile in self.todays_bot_profiles:
                #     self.send_ads_profile_to_commander(self.commanderXport, "txt", bot_profile)
                localFingerPrintProfiles = self.gatherFingerPrints()
                self.batchSendFingerPrintProfilesToCommander(localFingerPrintProfiles)

            # 2) log reports on local drive.
            self.saveDailyRunReport(self.todaysPlatoonReports)

            # 3) clear data structure, set up for tomorrow morning, this is the case only if this is a commander
            if not self.host_role == "Platoon":
                self.todays_work = {"tbd": [
                    {"name": "fetch schedule", "works": self.gen_default_fetch(), "status": "yet to start",
                     "current widx": 0, "completed": [], "aborted": []}]}
                self.mission_service.update_missions_by_id(self.missions)

            self.todays_completed = []
            self.todaysReports = []                     # per vehicle/host
            self.todaysPlatoonReports = []

    async def sendFingerPrintProfilesToCommander(self, profiles):
        for bot_profile in profiles:
            await self.send_ads_profile_to_commander(self.commanderXport, "txt", bot_profile)

    def batchSendFingerPrintProfilesToCommander(self, profiles):
        self.batch_send_ads_profiles_to_commander(self.commanderXport, "txt", profiles)


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
        # for task in (self.peer_task, self.monitor_task, self.chat_task, self.rpa_task, self.wan_sub_task, self.wan_msg_task):
        for task in (self.peer_task, self.monitor_task, self.chat_task, self.rpa_task, self.wan_sub_task):

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
    def build_cookie_site_lists(self, added=[]):
        today = datetime.today()
        formatted_today = today.strftime('%Y-%m-%d')
        # first, filter out today's missions by createon parameter.

        if added:
            log3("for ADDED only", "build_cookie_site_lists", self)
            targetMissions = added
        else:
            targetMissions = self.missions
            self.bot_cookie_site_lists = {}

        for m in targetMissions:
            log3("mission" + str(m.getMid()) + " created ON:" + m.getBD().split(" ")[0] + " today:" + formatted_today, "build_cookie_site_lists", self)

        missions_today = list(filter(lambda m: formatted_today == m.getBD().split(" ")[0], targetMissions))
        # first ,clear today's bot cookie site list dictionary

        for mission in missions_today:
            bots = [b for b in self.bots if b.getBid() == mission.getBid()]
            if len(bots) > 0:
                bot = bots[0]
                if bot.getEmail() == "":
                    log3("Error: Mission("+str(mission.getMid())+") Bot("+str(bot.getBid())+") running ADS without an Account!!!!!", "build_cookie_site_lists", self)
                else:
                    if bot.getEmail():
                        user_prefix = bot.getEmail().split("@")[0]
                        mail_site_words = bot.getEmail().split("@")[1].split(".")
                        mail_site = mail_site_words[len(mail_site_words) - 2]
                        bot_mission_ads_profile = user_prefix+"_m"+str(mission.getMid()) + ".txt"

                        self.bot_cookie_site_lists[bot_mission_ads_profile] = [mail_site]
                        if mail_site == "gmail":
                            self.bot_cookie_site_lists[bot_mission_ads_profile].append("google")

                        if mission.getSite() == "amz":
                            self.bot_cookie_site_lists[bot_mission_ads_profile].append("amazon")
                        if mission.getSite() == "ebay":
                            self.bot_cookie_site_lists[bot_mission_ads_profile].append("ebay")
                        elif mission.getSite() == "ali":
                            self.bot_cookie_site_lists[bot_mission_ads_profile].append("aliexpress")
                        else:
                            self.bot_cookie_site_lists[bot_mission_ads_profile].append(mission.getSite().lower())

        log3("just build cookie site list:"+json.dumps(self.bot_cookie_site_lists), "build_cookie_site_lists", self)

    def setADSBatchSize(self, batch_size):
        self.ads_settings["batch_size"] = batch_size

    def getADSBatchSize(self):
        return self.ads_settings.get("batch_size", 10)

    def getADSBatchMethod(self):
        return self.ads_settings.get("batch_method", "min batches")

    def getADSSettings(self):
        return self.ads_settings

    def saveADSSettings(self, settings):
        with open(self.ads_settings_file, 'w') as ads_settings_f:
            json.dump(settings["fp_browser_settings"], ads_settings_f)
            ads_settings_f.close()

    def getIP(self):
        return self.ip

    def getHostName(self):
        return self.machine_name

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
                if self.host_role != "Staff Officer":
                    response = self.think_about_a_reponse(message)
                    self.c_send_chat(response)
                chat_msg_queue.task_done()

            print("chat Task ticking....")
            await asyncio.sleep(1)

    def getBV(self, bot):
        if bot.getVehicle():
            return bot.getVehicle()
        else:
            return ""

    def getBotsOnThisVehicle(self):
        thisBots = [b for b in self.bots if self.machine_name in self.getBV(b) ]
        return thisBots

    def getBidsOnThisVehicle(self):
        thisBots = self.getBotsOnThisVehicle()
        thisBids = [b.getBid() for b in thisBots]
        thisBidsString = json.dumps(thisBids)
        self.showMsg("bids on this vehicle:"+thisBidsString)
        return thisBidsString

    def prepFullVehicleReportData(self):
        print("prepFullVehicleReportData...")
        report = []
        try:
            for v in self.vehicles:
                if v.getStatus() == "":
                    vstat = "offline"
                else:
                    vstat = v.getStatus()

                if self.machine_name not in v.getName():
                    vinfo = {
                        "vid": v.getVid(),
                        "vname": v.getName(),
                        "owner": self.user,
                        "status": vstat,
                        "lastseen": v.getLastUpdateTime().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": v.getFunctions(),
                        "bids": ",".join(str(v.getBotIds())),
                        "hardware": v.getArch(),
                        "software": v.getOS(),
                        "ip": v.getIP(),
                        "created_at": ""
                    }
                else:
                    vinfo = {
                        "vid": 0,
                        "vname": self.machine_name+":"+self.os_short,
                        "owner": self.user,
                        "status": self.working_state,
                        "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": self.functions,
                        "bids": self.getBidsOnThisVehicle(),
                        "hardware": self.processor,
                        "software": self.platform,
                        "ip": self.ip,
                        "created_at": ""
                    }
                report.append(vinfo)
            print("vnames:", [v["vname"] for v in report])
            if (self.machine_name+":"+self.os_short) not in [v["vname"] for v in report]:
                if "Only" not in self.host_role and "Staff" not in self.host_role:
                    # add myself as a vehicle resource too.
                    vinfo = {
                        "vid": 0,
                        "vname": self.machine_name+":"+self.os_short,
                        "owner": self.user,
                        "status": self.working_state,
                        "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                        "functions": self.functions,
                        "bids": self.getBidsOnThisVehicle(),
                        "hardware": self.processor,
                        "software": self.platform,
                        "ip": self.ip,
                        "created_at": ""
                    }

                    report.append(vinfo)
                    print("report:", report)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorPrepFullVReport:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorPrepFullVReport traceback information not available:" + str(e)
            print(ex_stat)

        return report


    def prepVehicleReportData(self, v):
        report = []

        if v:
            vinfo = {
                "vid": v.getVid(),
                "vname": v.getName(),
                "owner": self.user,
                "status": v.getStatus(),
                "lastseen": v.getLastUpdateTime().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                "functions": v.getFunctions(),
                "bids": json.dumps(v.getBotIds()),
                "hardware": v.getArch(),
                "software": v.getOS(),
                "ip": v.getIP(),
                "created_at": ""
            }
        else:
            vinfo = {
                "vid": 0,
                "vname": self.machine_name+":"+self.os_short,
                "owner": self.user,
                "status": self.working_state,
                "lastseen": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:19],
                "functions": self.functions,
                "bids": self.getBidsOnThisVehicle(),
                "hardware": self.processor,
                "software": self.platform,
                "ip": self.ip,
                "created_at": ""
            }
        report.append(vinfo)

        return report


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

            if ticks % 15 == 0:
                self.showMsg(f"report vehicle status")

                # update vehicles status to local disk, this is done either on platoon or commander
                self.saveVehiclesJsonFile()

                if "Commander" in self.host_role:
                    self.showMsg(f"sending vehicle heartbeat to cloud....")
                    hbInfo = self.stateCapture()
                    # update vehicle info to the chat channel (don't we need to update this to cloud lambda too?)
                    await self.wan_send_heartbeat(hbInfo)

                    # send vehicle status to cloud DB
                    vehicle_report = self.prepFullVehicleReportData()
                    resp = send_report_vehicles_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'],
                                                         vehicle_report, self.getWanApiEndpoint())

            if not monitor_msg_queue.empty():
                message = await monitor_msg_queue.get()
                self.showMsg(f"RPA Monitor message: {message}")
                if type(message) != str:
                    print("wanlog message....", message)
                    if self.vehicleMonitor:
                        self.vehicleMonitor.log_received.emit(json.dumps(message))
                else:
                    self.update_monitor_gui(message)

                monitor_msg_queue.task_done()

            print("running monitoring Task....", ticks)
            await asyncio.sleep(1)
        print("RPA monitor ended!!!")


    def update_monitor_gui(self, in_message):
        try:
            print("raw rpa monitor incoming msg:", in_message)
            # self.showMsg(f"RPA Monitor:"+in_message)
            if in_message["type"] == "request mission" and self.getIP() not in in_message["sender"]:
                print("request mission:", in_message)
                new_works = json.loads(in_message["contents"])
                print("CONFIG:", new_works['added_missions'][0]['config'])

                # downloaded files if any so that we don't have to do this later on....
                # and set up mission input parameters.
                self.prepareMissionRunAsServer(new_works)
                self.handleCloudScheduledWorks(new_works)

            elif in_message["type"] == "request queued":
                print("processing enqueue notification")
                # a request received on the cloud queue side. here what we will do:
                # enqueue an item on local mirror (we call it virtual cloud queue)
                requester_info = json.loads(in_message["contents"])

                print("requester info:", requester_info)

                asyncio.create_task(self.virtual_cloud_task_queue.put(requester_info))

                print("done local enqueue....")

                #then whenever a task group is finished either local or from remote. in that handler.
                # we will probe virtual cloud queue whethere there is something to work on.
                # if not empty, we will dequeue something from the cloud, once received work, we will deque local
                # and dispatch the work into scheduler.
            elif in_message["type"] == "report results":
                ext_run_results = json.loads(in_message["contents"].replace("\\", "\\\\"))
                handleExtLabelGenResults(self.session, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint(), ext_run_results)
            else:
                print("Unknown message type!!!")

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "Errorupdate_monitor_gui:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "Errorupdate_monitor_gui traceback information not available:" + str(e)
            print(ex_stat)


    def downloadForFullfillGenECBLabels(self, orders, worklink):
        try:
            for bi, batch in enumerate(orders):
                if batch['file']:
                    print("batch....", batch)
                    print("about to download....", batch['file'])

                    local_file = download_file(self.session, self.my_ecb_data_homepath, batch['dir'] + "/" + batch['file'],
                                               "", self.tokens['AuthenticationResult']['IdToken'],
                                               self.getWanApiEndpoint(), "general")
                    batch['dir'] = os.path.dirname(local_file)
                    orders[bi]['dir'] = os.path.dirname(local_file)
                    worklink['dir'] = os.path.dirname(local_file)


                    print("local file....", local_file)
                    print("local dir:", os.path.dirname(local_file))

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorDownloadForFullfillGenECBLabels:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorDownloadForFullfillGenECBLabels traceback information not available:" + str(e)
            print(ex_stat)


    # do any download if needed by the missions ONLY IF the mission will be run on this computer.
    # otherwise, don't do download and leave this to whichever computer that will run this mission.
    def prepareMissionRunAsServer(self, new_works):
        try:
            if new_works['added_missions'][0]['type'] == "sellFullfill_genECBLabels":
                first_v = next(iter(new_works['task_groups']))
                if self.machine_name in first_v:
                    self.downloadForFullfillGenECBLabels(new_works['added_missions'][0]['config'][1], new_works['task_groups'][first_v]['eastern'][0]['other_works'][0]['config'][1][0])

                print("updated new work:", new_works)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorPrepareMissionRunAsServer:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorPrepareMissionRunAsServer traceback information not available:" + str(e)
            print(ex_stat)

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
                    if v.getFieldLink()["transport"] and not v.getFieldLink()["transport"].is_closing():
                        v.getFieldLink()["transport"].write(cmd_str.encode('utf8'))
                    # v.getFieldLink()["transport"].get_loop().call_soon(lambda: print("CHAT MSG SENT2..."))

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


    async def send_file_to_platoon(self, platoon_link, file_type, file_name_full_path):
        if os.path.exists(file_name_full_path) and platoon_link:
            self.showMsg(f"Sending File [{file_name_full_path}] to platoon: "+platoon_link["ip"])
            with open(file_name_full_path, 'rb') as fileTBSent:
                binary_data = fileTBSent.read()
                encoded_data = base64.b64encode(binary_data).decode('utf-8')

                # Embed in JSON
                json_data = json.dumps({"cmd": "reqSendFile", "file_name": file_name_full_path, "file_type": file_type, "file_contents": encoded_data})
                length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                # Send data
                self.showMsg(f"About to send file json with "+str(len(json_data.encode('utf-8')))+ " BYTES!")
                if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                    platoon_link["transport"].write(length_prefix+json_data.encode('utf-8'))
                    # await platoon_link["transport"].drain()
                    asyncio.get_running_loop().call_soon(lambda: print("FILE MSG SENT2PLATOON..."))
                # await xport.drain()

                fileTBSent.close()
        else:
            if not os.path.exists(file_name_full_path):
                self.showMsg(f"ErrorSendFileToPlatoon: File [{file_name_full_path}] not found")
            else:
                self.showMsg(f"ErrorSendFileToPlatoon: TCP link doesn't exist")


    def send_json_to_platoon(self, platoon_link, json_data):
        if json_data and platoon_link:
            json_string = json.dumps(json_data)
            if len(json_string) < 128:
                log3(f"Sending JSON Data to platoon " + platoon_link["ip"] + "::" + json_string, "sendLAN",
                     self)
            else:
                log3(f"Sending JSON Data to platoon " + platoon_link["ip"] + ":: ..." + json_string[-127:], "sendLAN",
                     self)
            encoded_json_string = json_string.encode('utf-8')
            length_prefix = len(encoded_json_string).to_bytes(4, byteorder='big')
            # Send data
            if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                platoon_link["transport"].write(length_prefix+encoded_json_string)
                # await platoon_link["transport"].drain()
        else:
            if json_data == None:
                log3(f"ErrorSendJsonToPlatoon: JSON empty", "sendLAN", self)
            else:
                log3(f"ErrorSendJsonToPlatoon: TCP link doesn't exist", "sendLAN", self)


    async def send_json_to_commander(self, commander_link, json_data):
        if json_data and commander_link:
            json_string = json.dumps(json_data)
            if len(json_string) < 128:
                log3(f"Sending JSON Data to commander ::" + json.dumps(json_data), "sendLAN", self)
            else:
                log3(f"Sending JSON Data to commander " + platoon_link["ip"] + ":: ..." + json_string[-127:], "sendLAN",
                     self)
            encoded_json_string = json_string.encode('utf-8')
            length_prefix = len(encoded_json_string).to_bytes(4, byteorder='big')
            # Send data
            if commander_link and not commander_link.is_closing():
                commander_link.write(length_prefix+encoded_json_string)
                # await commander_link.drain()
                asyncio.get_running_loop().call_soon(lambda: print("JSON MSG SENT2COMMANDER..."))

        else:
            if json_data == None:
                log3(f"ErrorSendJsonToCommander: JSON empty", "sendLAN", self)
            else:
                log3(f"ErrorSendJsonToCommander: TCP link doesn't exist", "sendLAN", self)

    async def send_ads_profile_to_commander(self, commander_link, file_type, file_name_full_path):
        if os.path.exists(file_name_full_path) and commander_link:
            log3(f"Sending File [{file_name_full_path}] to commander: " + self.commanderIP, "sendLAN", self)
            with open(file_name_full_path, 'rb') as fileTBSent:
                binary_data = fileTBSent.read()
                encoded_data = base64.b64encode(binary_data).decode('utf-8')

                # Embed in JSON
                json_data = json.dumps({"type": "botsADSProfilesUpdate", "file_name": file_name_full_path, "file_type": file_type,
                                        "file_contents": encoded_data})
                length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                # Send data
                if commander_link and not commander_link.is_closing():
                    commander_link.write(length_prefix + json_data.encode('utf-8'))
                    await commander_link.drain()
                # asyncio.get_running_loop().call_soon(lambda: print("FILE SENT2COMMANDER..."))

                # await xport.drain()

                fileTBSent.close()
        else:
            if not os.path.exists(file_name_full_path):
                self.showMsg(f"ErrorSendFileToCommander: File [{file_name_full_path}] not found")
            else:
                self.showMsg(f" : TCP link doesn't exist")

    def batch_send_ads_profiles_to_commander(self, commander_link, file_type, file_paths):
        try:
            if not commander_link:
                log3("ErrorSendFilesToCommander: TCP link doesn't exist", "sendLAN", self)
                return

            profiles = []
            for file_name_full_path in file_paths:
                if os.path.exists(file_name_full_path):
                    log3(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}", "sendLAN", self)
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        file_timestamp = os.path.getmtime(file_name_full_path)

                        profiles.append({
                            "file_name": file_name_full_path,
                            "file_type": file_type,
                            "timestamp": file_timestamp,  # Include file timestamp
                            "file_contents": encoded_data
                        })

                else:
                    self.showMsg(f"ErrorSendFileToCommander: File [{file_name_full_path}] not found")

            # Send data
            json_data = json.dumps({
                "type": "botsADSProfilesBatchUpdate",
                "ip": self.ip,
                "profiles": profiles
            })
            length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
            if len(json_data) < 128:
                print("About to send botsADSProfilesBatchUpdate to commander: "+json_data)
            else:
                print("About to send botsADSProfilesBatchUpdate to commander: ..." + json_data[-127:])

            if commander_link and not commander_link.is_closing():
                commander_link.write(length_prefix + json_data.encode('utf-8'))
                asyncio.get_running_loop().call_soon(lambda: print("ADS FILES SENT2COMMANDER..."))

            # await commander_link.drain()  # Uncomment if using asyncio
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendingBatchProfilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendingBatchProfilesToCommander traceback information not available:" + str(e)


    def batch_send_ads_profiles_to_platoon(self, platoon_link, file_type, file_paths):
        try:
            if not platoon_link:
                log3("ErrorSendFilesToCommander: TCP link doesn't exist", "sendLAN", self)
                return

            print("# files", len(file_paths))
            profiles = []
            for file_name_full_path in file_paths:
                print("checking", file_name_full_path)
                if os.path.exists(file_name_full_path):
                    print("exists!")
                    # log3(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}", "gatherFingerPrints", self)
                    # print(f"Sending File [{file_name_full_path}] to commander: {self.commanderIP}")
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        file_timestamp = os.path.getmtime(file_name_full_path)

                        profiles.append({
                            "file_name": file_name_full_path,
                            "file_type": file_type,
                            "timestamp": file_timestamp,  # Include file timestamp
                            "file_contents": encoded_data
                        })

                else:
                    log3(f"Warning: ADS Profile [{file_name_full_path}] not found", "sendLAN", self)
                    print(f"Warning: ADS Profile [{file_name_full_path}] not found")

            # Send data
            print("profiles ready")
            json_data = json.dumps({
                "cmd": "botsADSProfilesBatchUpdate",
                "ip": self.ip,
                "profiles": profiles
            })

            if len(json_data) < 128:
                print("About to send botsADSProfilesBatchUpdate to platoon: " + json_data)
            else:
                print("About to send botsADSProfilesBatchUpdate to platoon: ..." + json_data[-127:])


            length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
            if platoon_link["transport"] and not platoon_link["transport"].is_closing():
                platoon_link["transport"].write(length_prefix + json_data.encode('utf-8'))
            # asyncio.get_running_loop().call_soon(lambda: print("ADS FILES SENT2PLATOON..."))

            # await commander_link.drain()  # Uncomment if using asyncio
        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendingBatchProfilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendingBatchProfilesToCommander traceback information not available:" + str(e)



    def send_mission_result_files_to_commander(self, commander_link, mid, file_type, file_name_full_paths):
        try:
            validFiles = [fn for fn in file_name_full_paths if os.path.exists(fn)]

            nFiles = len(validFiles)
            for fidx, file_name_full_path in enumerate(validFiles):
                if os.path.exists(file_name_full_path) and commander_link:
                    self.showMsg(f"Sending File [{file_name_full_path}] to commander: " + self.commanderIP)
                    with open(file_name_full_path, 'rb') as fileTBSent:
                        binary_data = fileTBSent.read()
                        encoded_data = base64.b64encode(binary_data).decode('utf-8')

                        # Embed in JSON
                        json_data = json.dumps({"type": "missionResultFile", "mid": mid, "nFiles": nFiles, "fidx": fidx, "file_name": file_name_full_path, "file_type": file_type,
                                                "file_contents": encoded_data})
                        length_prefix = len(json_data.encode('utf-8')).to_bytes(4, byteorder='big')
                        # Send data
                        if commander_link and not commander_link.is_closing():
                            commander_link.write(length_prefix + json_data.encode('utf-8'))
                        # asyncio.get_running_loop().call_soon(lambda: print("RESULT FILES SENT2COMMANDER..."))
                        # await xport.drain()

                        fileTBSent.close()
                else:
                    if not os.path.exists(file_name_full_path):
                        self.showMsg(f"ErrorSendMissionResultsFilesToCommander: File [{file_name_full_path}] not found")
                    else:
                        self.showMsg(f"ErrorSendMissionResultsFilesToCommander: TCP link doesn't exist")

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSendMissionResultsFilesToCommander:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSendMissionResultsFilesToCommander: traceback information not available:" + str(e)
            log3(ex_stat)


    def getEncryptKey(self):
        key, salt = derive_key(self.main_key)
        return key


    async def halt_action(self):
        print("escape hotkey pressed!")
        # send a message to RPA virtual machine engine.
        msg = {"cmd": "halt missions", "target": "current"}
        rpa_ctl_msg = json.dumps(msg)
        asyncio.create_task(self.gui_rpa_msg_queue.put(rpa_ctl_msg))

    async def resume_action(self):
        print("space hotkey pressed!")
        # send a message to RPA virtual machine engine.
        msg = {"cmd": "resume missions", "target": "current"}
        rpa_ctl_msg = json.dumps(msg)
        asyncio.create_task(self.gui_rpa_msg_queue.put(rpa_ctl_msg))

    async def quit_action(self):
        print("quit hotkey pressed!")
        # Show the dialog and wait for the user to respond
        self.rpa_quit_confirmation_future = asyncio.get_event_loop().create_future()
        self.rpa_quit_dialog.show()
        while not self.rpa_quit_confirmation_future.done():
            await asyncio.sleep(0.1)
        if self.rpa_quit_confirmation_future.result():
            print("reqCancelAllMissions")
            msg = {"cmd": "cancel missions", "target": "all"}
            rpa_ctl_msg = json.dumps(msg)
            asyncio.create_task(self.gui_rpa_msg_queue.put(rpa_ctl_msg))



    # Coroutine to listen for hotkey and run the action
    async def listen_for_hotkey(self):
        loop = asyncio.get_running_loop()

        def esc_callback():
            asyncio.run_coroutine_threadsafe(self.halt_action(), loop)

        def space_callback():
            asyncio.run_coroutine_threadsafe(self.resume_action(), loop)

        def q_callback():
            asyncio.run_coroutine_threadsafe(self.quit_action(), loop)
        #
        # keyboard.add_hotkey('esc', esc_callback)
        # keyboard.add_hotkey('space', space_callback)
        # keyboard.add_hotkey('q', q_callback)

        # Keep the coroutine running to listen for the hotkey indefinitely

        while True:
            await asyncio.sleep(1)

    def set_wan_connected(self, wan_stat):
        self.wan_connected = wan_stat

    def set_websocket(self, ws):
        self.websocket = ws

    def get_wan_connected(self):
        return self.wan_connected

    def get_websocket(self):
        return self.websocket

    def get_wan_msg_queue(self):
        return self.wan_chat_msg_queue

    def set_wan_msg_subscribed(self, ss):
        self.wan_msg_subscribed = ss

    def get_wan_msg_subscribed(self):
        return self.wan_msg_subscribed

    def set_staff_officer_online(self, ol):
        self.staff_officer_on_line = ol

    def get_staff_officer_online(self):
        return self.staff_officer_on_line

    # this is an empty task
    async def wait_forever(self):
        await asyncio.Event().wait()  # This will wait indefinitely

    async def wan_ping(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            ping_msg = {
                "chatID": commander_chat_id,
                "sender": self.chat_id,
                "receiver": commander_chat_id,
                "type": "ping",
                "contents": json.dumps({"msg": "hello?"}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }

            self.wan_sub_task = asyncio.create_task(wanSendMessage(ping_msg, self))

    async def wan_self_ping(self):
        if self.host_role == "Staff Officer":
            self_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
        else:
            self_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
        print("Self:", self_chat_id)
        ping_msg = {
            "chatID": self_chat_id,
            "sender": self.chat_id,
            "receiver": self_chat_id,
            "type": "loopback",
            "contents": json.dumps({"msg": "hello?"}).replace('"', '\\"'),
            "parameters": json.dumps({})
        }

        self.wan_sub_task = asyncio.create_task(wanSendMessage(ping_msg, self))


    async def wan_pong(self):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            pong_msg = {
                # "chatID": sa_chat_id,
                "chatID": self.chat_id,
                "sender": "Commander",
                "receiver": sa_chat_id,
                "type": "pong",
                "contents": json.dumps({"type": "cmd", "cmd": "pong"}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(pong_msg, self))

    def wan_send_log(self, logmsg):
        if self.host_role != "Staff Officer":
            so_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            contents = {"msg": logmsg}
            parameters = {}
            req_msg = {
                "chatID": so_chat_id,
                "sender": "Commander",
                "receiver": self.user,
                "type": "logs",
                "contents": logmsg.replace('"', '\\"'),
                # "contents": json.dumps({"msg": logmsg}).replace('"', '\\"'),
                "parameters": json.dumps(parameters)
            }
            wanSendMessage(req_msg, self)

    async def wan_send_log8(self, logmsg):
        if self.host_role != "Staff Officer":
            so_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            req_msg = {
                "chatID": so_chat_id,
                "sender": "Commander",
                "receiver": self.user,
                "type": "logs",
                "contents": json.dumps({"msg": logmsg}).replace('"', '\\"'),
                "parameters": json.dumps({})
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))


    async def wan_request_log(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": self.chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "request",
                "contents": json.dumps({"type": "cmd", "cmd": "start log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

    def wan_stop_log(self):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            log_msg = {
                "chatID": sa_chat_id,
                "sender": self.chat_id,
                "receiver": sa_chat_id,
                "type": "command",
                "contents": json.dumps({"type": "cmd", "cmd": "stop log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            wanSendMessage(log_msg, self)

    async def wan_stop_log(self):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": commander_chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "command",
                "contents": json.dumps({"type": "cmd", "cmd": "stop log", "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

    def wan_rpa_ctrl(self, cmd):
        if self.host_role == "Staff Officer":
            commander_chat_id = self.user.replace("@", "_").replace(".", "_") + "_Commander"
            req_msg = {
                "chatID": self.chat_id,
                "sender": "",
                "receiver": commander_chat_id,
                "type": "command",
                "contents": json.dumps({"cmd": cmd, "settings": ["all"]}).replace('"', '\\"'),
                "parameters": ""
            }
            self.wan_sub_task = asyncio.create_task(wanSendMessage(req_msg, self))

    async def wan_send_heartbeat(self, heartbeatInfo):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.replace("@", "_").replace(".", "_") + "_StaffOfficer"
            req_msg = {
                "chatID": sa_chat_id,
                "sender": self.user.replace("@", "_").replace(".", "_") + "_Commander",
                "receiver": sa_chat_id,
                "type": "heartbeat",
                "contents": json.dumps(heartbeatInfo).replace('"', '\\"'),
                "parameters": json.dumps({}),
            }
            # self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self.tokens["AuthenticationResult"]["IdToken"], self.websocket))
            await wanSendMessage8(req_msg, self)


    def send_heartbeat(self):
        if "Commander" in self.host_role:
            print("sending wan heartbeat")
            asyncio.ensure_future(self.wan_send_heartbeat())


    def wan_chat_test(self):
        if self.host_role == "Staff Officer":
            asyncio.ensure_future(self.wan_ping())
            time.sleep(1)
            asyncio.ensure_future(self.wan_self_ping())
        elif self.host_role != "Platoon":
            asyncio.ensure_future(self.wan_pong())
            # asyncio.ensure_future(self.wan_c_send_chat("got it!!!"))
            # time.sleep(1)
            # asyncio.ensure_future(self.wan_self_ping())
            # self.think_about_a_reponse("[abc]'hello?'")


    async def wan_sa_send_chat(self, msg):
        try:
            if self.host_role == "Staff Officer":
                commander_chat_id = self.user.split("@")[0] + "_Commander"
                req_msg = {
                    "chatID": commander_chat_id,
                    "sender": self.chat_id,
                    "receiver": commander_chat_id,
                    "type": "chat",
                    "contents": msg,
                    "parameters": json.dumps({})
                }

                self.wan_sub_task = asyncio.create_task(wanSendMessage8(req_msg, self))

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorWanSaSendChat:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorWanSaSendChat: traceback information not available:" + str(e)
            log3(ex_stat)


    def sa_send_chat(self, msg):
        asyncio.ensure_future(self.wan_sa_send_chat(msg))


    async def wan_c_send_chat(self, msg):
        if "Commander" in self.host_role:
            sa_chat_id = self.user.split("@")[0] + "_StaffOfficer"
            req_msg = {
                "chatID": sa_chat_id,
                "sender": self.chat_id,
                "receiver": sa_chat_id,
                "type": "chat",
                "contents": msg,
                "parameters": json.dumps({})
            }

            self.wan_sub_task = asyncio.create_task(wanSendMessage(req_msg, self))


    def c_send_chat(self, msg):
        asyncio.ensure_future(self.wan_c_send_chat(msg))

        current_time = datetime.now(timezone.utc)
        # Convert to the required AWSDateTime format
        aws_datetime_string = current_time.isoformat()


    def think_about_a_reponse(self, thread):
        print("Thinking about response.")
        current_time = datetime.now(timezone.utc)
        aws_datetime_string = current_time.isoformat()

        session = self.session
        token = self.tokens['AuthenticationResult']['IdToken']
        qs = [{
            "msgID": "1",
            "user": self.user,
            "timeStamp": aws_datetime_string,
            "products": "",
            "goals": "",
            "options": "",
            "background": thread,
            "msg": "provide answer"
        }]
        resp = send_query_chat_request_to_cloud(session, token, qs, self.getWanApiEndpoint())

        print("THINK RESP:", resp)

    # if some kind of wait until step is running, this would stop the wait with a click.
    def stopWaitUntilTest(self):
        print("SETTING LABELS READY")
        setLabelsReady()
        setupExtSkillRunReportResultsTestData(self)

    # from ip find vehicle, and update its status, and
    def updateVehicleStatusToRunningIdle(self, ip):
        found_vehicles = [v for v in self.vehicles if v.getIP() == ip]
        if found_vehicles:
            found_vehicle = found_vehicles[0]
            found_vehicle.setStatus("running_idle")       # this vehicle is ready to take more work if needed.
            vehicle_report = self.prepVehicleReportData(found_vehicle)
            log3("vehicle status report"+json.dumps(vehicle_report))
            if self.general_settings["schedule_mode"] != "test":
                resp = send_report_vehicles_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'],
                                                 vehicle_report, self.getWanApiEndpoint())
            self.saveVehiclesJsonFile()

    def updateVehicles(self, vehicles):
        vjs=[self.prepVehicleReportData(v) for v in vehicles]

        resp = send_update_vehicles_request_to_cloud(self.session, vjs, self.tokens['AuthenticationResult']['IdToken'], self.getWanApiEndpoint())
        # for now simply update json file, can put in local db if needed in future.... sc-01/06/2025
        self.saveVehiclesJsonFile()


    # capture current state and send in heartbeat signal to the cloud
    def stateCapture(self):
        current_time = datetime.now()
        for v in self.vehicles:
            current_time = datetime.now()
            if (current_time - v.getLastUpdateTime()).total_seconds() > 480:    # 8 minutes no contact is considered "offline"
                v.setStatus("offline")


        stateInfo = {"vehiclesInfo": [{"vehicles_status": v.getStatus(), "vname": v.getName()} for v in self.vehicles]}

        # we'll capture these info:
        # all vehicle status running_idle/running_working/offline
        # all the mission running status.??? may be this is not the good place for that, we'd have to ping vehicles
        # plus, don't they update periodically already?


        return stateInfo

    def vRunnable(self, vehicle):
        print("vname", vehicle.getName(), self.machine_name, self.host_role)
        runnable = True
        if self.machine_name in vehicle.getName() and self.host_role == "Commander Only":
            runnable = False
        return runnable

    # check whether there is vehicle for hire, if so, check any contract work in the queue
    # if so grab it.
    async def checkCloudWorkQueue(self):
        try:
            taskGroups = {}
            # some debugging here
            # print("N vehicles:", len(self.vehicles))
            # if len(self.vehicles) > 0:
            #     for v in self.vehicles:
            #         print("vname:", v.getName(), "status:", v.getStatus(), )
            # check whether there is any thing in the local mirror: virutal cloud task queue
            if not self.virtual_cloud_task_queue.empty():
                print("something on queue...")
                item = await self.virtual_cloud_task_queue.get()

                # in case there is anything, go ahead and dequeue the cloud side.
                print("all vehicles:", [v.getName() for v in self.vehicles])
                idle_vehicles = [{"vname": v.getName()} for v in self.vehicles if v.getStatus() == "running_idle" and self.vRunnable(v)]
                print("running idel vehicles:", idle_vehicles)
                resp = send_dequeue_tasks_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], idle_vehicles, self.getWanApiEndpoint())
                print("RESP:", resp)
                if "body" in resp:
                    cloudQSize = resp['body']['remainingQSize']
                    taskGroups = resp['body']['task_groups']
                    print("cloudQSize:", cloudQSize)
                    print("newTaskGroups:", taskGroups)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorCheckCloudWorkQueue:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorCheckCloudWorkQueue: traceback information not available:" + str(e)
            log3(ex_stat)
            taskGroups = {"task_groups": None, "added_missions": []}

        return taskGroups

    # if there is actual work, 1) deque from virutal cloud queue, 2) put it into local unassigned work list.
    # and the rest will be taken care of by the work dispatcher...
    # works organized as following....
    # { win: {computer1: {"estern": ..... "central":...} , computer2: ...} , mac:, linux:...}
    def arrangeContractWorks(self, contractWorks):
        if "added_missions" in contractWorks:
            if contractWorks["added_missions"] and contractWorks["task_groups"]:
                # first, download the files.

                log3("ARRANGE external contract work....")
                self.prepareMissionRunAsServer(contractWorks)

                print("updated contract works....", contractWorks)
                # first flatten timezone.
                newlyAddedMissions = self.addNewlyAddedMissions(contractWorks)

                print("newlyAddedMissions config:", newlyAddedMissions[0].getConfig())

                newTaskGroups = self.reGroupByBotVehicles(contractWorks["task_groups"])
                self.unassigned_reactive_task_groups = self.todays_scheduled_task_groups
                for vname in contractWorks["task_groups"]:
                    if vname in self.unassigned_reactive_task_groups:
                        if self.unassigned_reactive_task_groups[vname]:
                            self.unassigned_reactive_task_groups[vname] = self.merge_dicts(self.unassigned_reactive_task_groups[vname], newTaskGroups[vname])
                        else:
                            self.unassigned_reactive_task_groups[vname] = newTaskGroups[vname]
                    else:
                        self.unassigned_reactive_task_groups[vname] = newTaskGroups[vname]

                print("unassigned_reactive_task_groups after adding contract:", self.unassigned_reactive_task_groups)
                self.build_cookie_site_lists(newlyAddedMissions)

    def merge_dicts(self, dict1, dict2):
        merged_dict = {}
        for key in dict1.keys():
            merged_dict[key] = dict1[key] + dict2.get(key, [])
        return merged_dict

    # upon clicking here, it would simulate receiving a websocket message(cmd) and send this
    # message to the relavant queue which will trigger a mission run. (For unit testing purpose)
    def simWanRequest(self):
        contents_data = {
            "task_groups": {
                "DESKTOP-DLLV0:win":
                {
                    "eastern": [],
                    "central": [],
                    "mountain": [],
                    "pacific": [
                        {
                            "bid": 73,
                            "cuspas": "win,ads,ebay",
                            "tz": "pacific",
                            "bw_works": [],
                            "other_works": [{
                                "name": "sellFullfill_routine",
                                "mid": 697,
                                "cuspas": "win,ads,ebay",
                                "config": {
                                    "estRunTime": 2,
                                    "searches": []
                                },
                                "start_time": 30
                            }]
                        }
                    ],
                    "alaska": [],
                    "hawaii": []
                }
            },
            "added_missions": [
                {
                    "mid": 697,
                    "ticket": 0,
                    "owner": "songc@yahoo.com",
                    "botid": 73,
                    "status": "ASSIGNED",
                    "createon": "2024-03-31 05:44:15",
                    "esd": "2024-03-16 05:44:15",
                    "ecd": "2024-03-16 05:44:15",
                    "asd": "2124-03-16 05:44:15",
                    "abd": "2124-03-16 05:44:15",
                    "aad": "2124-03-16 05:44:15",
                    "afd": "2124-03-16 05:44:15",
                    "acd": "2124-03-16 05:44:15",
                    "esttime": 30,
                    "runtime": 2,
                    "trepeat": 3,
                    "cuspas": "win,ads,ebay",
                    "category": "",
                    "phrase": "",
                    "pseudoStore": "",
                    "pseudoBrand": "",
                    "pseudoASIN": "",
                    "type": "sellFullfill_routine",
                    "as_server": True,
                    "config": [
                        "sale",
                        [
                            {
                                "file": "",
                                "dir": ""
                            }
                        ]
                    ],
                    "skills": "87",
                    "delDate": "2124-03-16 05:44:15"
                }
            ]
        }
        sim_contents = json.dumps(contents_data)

        in_message = {
            "type": "request mission",
            "sender": "",
            "id": 0,
            "contents": sim_contents
        }

        asyncio.ensure_future((self.gui_monitor_msg_queue.put(in_message)))

    # check default directory and see whether there is any file dated within the past 24 hrs
    # if so return that file name.
    def checkNewBotsFiles(self):
        bfiles = []

        if "new_bots_file_path" in self.general_settings:
            bfiles = self.get_new_bot_files(self.general_settings["new_bots_file_path"])

        return bfiles

    def get_new_bot_files(self, base_dir="new_bot"):
        # Calculate the timestamp for yesterday at 12 AM
        yesterday_12am = datetime.combine(datetime.now() - timedelta(days=1), datetime.min.time())

        # Convert the timestamp to a Unix timestamp (seconds since epoch)
        timestamp_cutoff = yesterday_12am.timestamp()

        # Get all .xlsx files in the base directory
        bot_files = glob.glob(os.path.join(base_dir, "new_bots_*.xlsx"))

        # Filter files modified after yesterday's 12 AM
        new_bot_files = [file for file in bot_files if os.path.getmtime(file) > timestamp_cutoff]

        if "last_bots_file" not in self.general_settings:
            latest_file = ""
            latest_time = 0
            last_time = 0
        else:
            latest_file = self.general_settings["last_bots_file"]
            latest_time = self.general_settings["last_bots_file_time"]
            last_time = latest_time

        not_yet_touched_files = []
        # Print the new bot files (optional)
        if new_bot_files:
            print(f"Found {len(new_bot_files)} new bot files modified after {yesterday_12am}:")
            for file_path in new_bot_files:
                # Get the modification time for each file
                file_mtime = os.path.getmtime(file_path)
                # Update if this file is more recent
                if file_mtime > last_time:
                    not_yet_touched_files.append(file_path)

                if file_mtime > latest_time:
                    latest_time = file_mtime
                    latest_file = file_path

        else:
            print("No new bot files found since yesterday at 12 AM.")

        self.general_settings["last_bots_file"] = latest_file
        self.general_settings["last_bots_file_time"] = latest_time
        return not_yet_touched_files



    def checkNewMissionsFiles(self):
        mfiles = []

        if "new_orders_path" in self.general_settings:
            log3("new_orders_path:" + self.general_settings["new_orders_dir"])
            mfiles = self.get_yesterday_orders_files(self.general_settings["new_orders_dir"])
            log3("New order files since yesterday" + json.dumps(mfiles))

        return mfiles

    # make sure the networked dir is escapped correctly: "\\\\HP-ECBOT\\shared"
    def get_yesterday_orders_files(self, base_dir="new orders"):
        # Get yesterday's date
        yesterday = datetime.now() - timedelta(days=1)
        year = yesterday.strftime("%Y")
        month = yesterday.strftime("m%m")  # 'm01' format
        day = yesterday.strftime("d%d")  # 'd01' format

        # Build the path for yesterday's directory
        yesterday_dir = os.path.join(base_dir, year, month, day)

        # Check if the directory exists
        if not os.path.isdir(yesterday_dir):
            print(f"Directory {yesterday_dir} does not exist.")
            return []

        # Find all .xlsx files in yesterday's directory
        order_files = glob.glob(os.path.join(yesterday_dir, "Order*.xlsx"))
        if self.general_settings.get("last_order_file", ""):
            latest_file = ""
            latest_time = 0
            last_time = 0
        else:
            latest_file = self.general_settings["last_order_file"]
            latest_time = self.general_settings["last_order_file_time"]
            last_time = latest_time

        not_yet_touched_files = []
        # Print found files (optional)
        if order_files:
            print(f"Found {len(order_files)} order files for {yesterday.strftime('%Y-%m-%d')}:")
            for file_path in order_files:
                # Get the modification time for each file
                file_mtime = os.path.getmtime(file_path)

                if file_mtime > last_time:
                    not_yet_touched_files.append(file_path)

                # Update if this file is more recent
                if file_mtime > latest_time:
                    latest_time = file_mtime
                    latest_file = file_path
        else:
            print(f"No order files found for {yesterday.strftime('%Y-%m-%d')}.")

        self.general_settings["last_order_file"] = latest_file
        self.general_settings["last_order_file_time"] = latest_time
        return not_yet_touched_files

    # assume one sheet only in the xlsx file. at this moment no support for multi-sheet.
    def convert_orders_xlsx_to_json(self, file_path):
        header_to_db_column = {
            "store": "store",
            "brand": "brand",
            "execution time": "execution_time",
            "quantity": "quantity",
            "asin": "asin",
            "search term": "phrase",
            "title": "title",
            "page number": "page_number",
            "price": "price",
            "variations": "variations",
            "follow seller": "follow_seller",
            "follow price": "follow_price",
            "product image": "img",
            "fb type": "feedback_type",
            "fb title": "feedback_title",
            "fb contents": "feedback_contents",
            "notes": "order_notes",
            "email": "customer"
        }

        # Load the Excel file
        log3("working on new order xlsx file:"+file_path)
        df = pd.read_excel(file_path, header=2, dtype=str)  # Start reading from the 3rd row

        df.rename(columns=header_to_db_column, inplace=True)

        # Drop any completely empty columns, if there are any
        df.dropna(how="all", axis=1, inplace=True)
        df.dropna(how="all", axis=0, inplace=True)

        # Convert DataFrame to a list of dictionaries (JSON format)
        orders_json = df.to_dict(orient="records")
        return orders_json

    def generate_key_from_string(self, password: str) -> bytes:
        """Generate a 32-byte key from the given string (password) using a key derivation function."""
        password = password.encode()  # Convert string to bytes
        salt = b'some_salt_value'  # You can generate this securely if you want, here it's fixed for simplicity
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key

    def encrypt_string(self, key: bytes, plaintext: str) -> str:
        """Encrypt the given plaintext using the derived key."""
        fernet = Fernet(key)
        encrypted = fernet.encrypt(plaintext.encode())  # Encrypt the plaintext
        return encrypted.decode()  # Return as a string

    def decrypt_string(self, key: bytes, encrypted_text: str) -> str:
        """Decrypt the given encrypted text using the derived key."""
        fernet = Fernet(key)
        decrypted = fernet.decrypt(encrypted_text.encode())  # Decrypt the text
        return decrypted.decode()  # Return as a string

    def genPseudo(self, keyString, inString):
        # Generate a key from string A
        key = self.generate_key_from_string(keyString)

        # Encrypt string B to get string C
        encrypted = self.encrypt_string(key, inString)
        print("Encrypted:", encrypted)

        return encrypted

    def generateShortHash(self, text: str, length: int = 32) -> str:
        """Generate a fixed-length hash for the input text."""
        hash_obj = hashlib.sha256(text.encode())
        hashed_bytes = hash_obj.digest()
        # Encode in base64 to make it URL-safe and take the desired length
        hashed = base64.urlsafe_b64encode(hashed_bytes).decode()[:length]
        # log3("hashed:"+hashed)
        return hashed

    def createNewMissionsFromOrdersXlsx(self):
        newMisionsFiles = self.checkNewMissionsFiles()
        if newMisionsFiles:
            log3("last_order_file:"+self.general_settings["last_order_file"]+"..."+str(self.general_settings["last_order_file_time"]))
            self.createMissionsFromFilesOrJsData(newMisionsFiles)

    def createNewBotsFromBotsXlsx(self):
        newBotsFiles = self.checkNewBotsFiles()
        log3("newBotsFiles:"+json.dumps(newBotsFiles))
        if newBotsFiles:
            firstNewBid, addedBots = self.createBotsFromFilesOrJsData(newBotsFiles)

    def isPlatoon(self):
        return (self.machine_role == "Platoon")


    def findManagerOfThisVehicle(self):
        # for bot in self.bots:
        #     print("bot:", bot.getRoles(), bot.getVehicle(), self.machine_name)
        foundBots = [x for x in self.bots if "manage" in x.getRoles().lower() and self.machine_name in x.getVehicle()]
        return foundBots

    def findManagerMissionsOfThisVehicle(self):
        managerBots = self.findManagerOfThisVehicle()
        print("#manager::", len(managerBots))
        managerBids = [x.getBid() for x in managerBots]
        print("#managerBids::", managerBids)
        managerMissions = [x for x in self.missions if x.getBid() in managerBids and ("completed" not in x.getStatus().lower())]
        return managerBots, managerMissions

    def getDailyFailedBots(self):
        failed = [b for b in self.bots if b.getStatus().lower() == "failed"]
        return failed

    def isValidAddr(self, addr):
        val = True

        if "Any,Any" in addr or not addr.split("\n")[0].strip():
            val = False

        return val

    def screenBuyerBotCandidates(self, acctRows, all_bots):
        # note the acctRows is in format of following....
        # just look at the ip, vccard, bot assignment
        allBotEmails = [b.getEmail() for b in all_bots]
        botsNeedsUpdate = [b for b in all_bots if (not b.getEmail()) or (not b.getBackEm()) or (not self.isValidAddr(b.getAddr())) or (not self.isValidAddr(b.getShippingAddr())) or (not b.getVehicle()) or (not b.getOrg())]

        print('allBotEmails:', allBotEmails)
        qualified = [row for row in acctRows if row["email"] and row["vcard_num"] and row["proxy_host"] and (not row["bot"]) and (row["email"] not in allBotEmails)]
        rowsNeedsUpdate = [row for row in acctRows if row["email"] and row["proxy_host"] and (not row["bot"]) and (row["email"] in allBotEmails)]
        vehiclesNeedsUpdate = []
        # for rows missing bot id, fill it in.
        for row in rowsNeedsUpdate:
            foundBot = next((x for x in self.bots if x.getEmail() == row["email"]), None)
            if foundBot:
                row["bot"] = foundBot.getBid()

        # update in data structure
        print("row bot:", [r["bot"] for r in acctRows])
        for bot in botsNeedsUpdate:
            print("ids:", bot.getBid())
            row = next((r for i, r in enumerate(acctRows) if bot.getBid() == r["bot"]), None)
            if row:
                print("found row....", row["addr_street_line1"])
                if row["email"]:
                    bot.setEmail(row["email"])
                    bot.setEPW(row["email_pw"])

                if row["backup_email"]:
                    bot.setBackEmail(row["backup_email"])
                    bot.setEBPW(row["backup_email_pw"])

                if row["addr_street_line1"]:
                    print("set address....")
                    bot.setAddr(row["addr_street_line1"], row["addr_street_line2"], row["addr_city"], row["addr_state"], row["addr_zip"])
                    print("after set addr:", bot.getAddr())

                if not self.isValidAddr(bot.getShippingAddr()) and row["addr_street_line1"]:
                    bot.setShippingAddr(row["addr_street_line1"], row["addr_street_line2"], row["addr_city"], row["addr_state"], row["addr_zip"])

            self.assignBotVehicle(bot)

            if not bot.getOrg():
                bot.setOrg("{}")


        print("bot ids for ones need update:", [b.getBid() for b in botsNeedsUpdate])
        return qualified, rowsNeedsUpdate, botsNeedsUpdate, vehiclesNeedsUpdate

    def assignBotVehicle(self, bot):
        if not bot.getVehicle():
            bv = self.genBotVehicle(bot)
            if bv:
                bot.setVehicle(bv.getName())
                print("setting vehicle:", bot.getVehicle())
                bv.addBot(bot.getBid())
                if bv not in vehiclesNeedsUpdate:
                    vehiclesNeedsUpdate.append(bv)
            else:
                log3("vehicle not found for a bot")

    # turn acct into bots/agents
    def hireBuyerBotCandidates(self, acctRows):
        newBotsJs = []
        for row in acctRows:
            # format conversion and some.
            newBotJS = {
                "pubProfile": {
                    "bid":0,
                    "pseudo_nick_name":row["first_name"],
                    "pseudo_name": self.genPseudoName(row["first_name"],row["last_name"]),
                    "location": self.genBotLoc(row["addr_state"]),
                    "pubbirthday": self.genBotPubBirthday(),
                    "gender": self.getBotGender(),
                    "interests":"Any,Any,Any,Any,Any",
                    "roles": "amz:buyer",
                    "org":"{}",
                    "levels": "amz:green:buyer",
                    "levelStart": "",
                    "vehicle": self.genBotVehicle("buyer").getName(),
                    "status": "Active"
                },
                "privateProfile":{
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "email": row["email"],
                    "email_pw": row["email_pw"],
                    "phone": "",
                    "backup_email": row["backup_email"],
                    "acct_pw": row["backup_email_pw"],
                    "backup_email_site": "",
                    "birthday": "2000-02-02",
                    "addrl1": row["addr_street_line1"],
                    "addrl2": row["addr_street_line2"],
                    "addrcity": row["addr_city"],
                    "addrstate": row["addr_state"],
                    "addrzip": row["addr_zip"],
                    "shipaddrl1": row["addr_street_line1"],
                    "shipaddrl2": row["addr_street_line2"],
                    "shipaddrcity": row["addr_city"],
                    "shipaddrstate": row["addr_state"],
                    "shipaddrzip": row["addr_zip"],
                    "adsProfile": ""
                },
                "settings": {
                    "platform":"win",
                    "os":"win",
                    "browser":"ads",
                    "machine":""
                }
            }
            newBotsJs.append(newBotJS)

        print("newBotsJs:", newBotsJs)
        firstNewBid, addedBots = self.createBotsFromFilesOrJsData(newBotsJs)
        print("firstNewBid:", firstNewBid)
        if firstNewBid:
            newBid = firstNewBid
            for row in acctRows:
                row["bot"] = newBid
                newBid = newBid + 1


    def genPseudoName(self, fn, ln):
        pfn = fn
        pln = ln

        return pfn+" "+pln


    def genBotLoc(self,state):
        LARGEST_CITY = { "CA": "Los Angeles", "NY": "New York", "IL": "Chicago", "D.C.": "Washington", "WA": "Seattle", "TX": "Dallas"}
        # for simplicity, just use largest city of that state.
        loc = LARGEST_CITY[state]+","+state
        print("gen loc:", loc)
        return loc

    def genBotPubBirthday(self):
        # Randomly pick
        yyyy = random.randint(1995, 2005)
        mm = random.randint(1, 12)
        dd = random.randint(1, 28)
        # Format with leading zeros
        pbd = f"{yyyy}-{str(mm).zfill(2)}-{str(dd).zfill(2)}"
        print("pbd:", pbd)
        return pbd

    def getBotGender(self):
        # randomely pick
        gends = ["F", "M"]
        random_number = random.randint(0, 1)
        gend = gends[random_number]
        print("gend", gend)
        return gend

    def botFunctionMatchVehicle(self, b, v):
        fit = False
        if isinstance(b, str):
            roles = b.lower()
        else:
            roles = b.getRoles().lower()

        vfws = v.getFunctions().split(",")
        vfs = [r.strip().lower() for r in vfws]
        for vf in vfs:
            if vf in roles:
                fit = True

        return fit

        
    def genBotVehicle(self, bot):
        # fill the least filled vehicle first.
        fitV = ""
        functionMatchedV = [v for v in self.vehicles if self.botFunctionMatchVehicle(bot, v)]
        sortedV = sorted(functionMatchedV, key=lambda v: len(v.getBotIds()), reverse=False)
        print("sorted vehicles:", [(v.getName(), len(v.getBotIds())) for v in sortedV])
        fitV = ""
        for v in sortedV:
            if not v.getBotsOverCapStatus():
                fitV = v
                break

        return fitV

    # this function sends request to all on-line platoons and request they send back
    # all the latest finger print profiles of the troop members on that team.
    # we will store them onto the local dir, if there is existing ones, compare the time stamp of incoming file and existing file,
    # if the incoming file has a later time stamp, then overwrite the existing one.
    def syncFingerPrintRequest(self):
        try:
            self.botFingerPrintsReady = False
            if self.machine_role == "Commander":
                log3("syncing finger prints...")

                reqMsg = {"cmd": "reqSyncFingerPrintProfiles", "content": "now"}

                # send over scheduled tasks to platton.
                self.expected_vehicle_responses = {}
                for vehicle in self.vehicles:
                    print("vehicle:", vehicle.getName(), vehicle.getStatus())
                    if vehicle.getFieldLink() and "running" in vehicle.getStatus():
                        self.showMsg(get_printable_datetime() + "SENDING [" + vehicle.getName() + "]PLATOON[" + vehicle.getFieldLink()[
                            "ip"] + "]: " + json.dumps(reqMsg))

                        self.send_json_to_platoon(vehicle.getFieldLink(), reqMsg)
                        self.expected_vehicle_responses[vehicle.getName()] = None

                #now wait for the response to all come back. for each v, give it 10 seconds.
                VTIMEOUT = 2
                sync_time_out =  len(self.expected_vehicle_responses.keys())*VTIMEOUT
                sync_time_out = VTIMEOUT
                print("waiting for ", sync_time_out, "seconds...")
                time.sleep(8)
                # while not( sync_time_out == 0):
                #     time.sleep(2)
                #     sync_time_out = sync_time_out-1
                #     print("tick...", sync_time_out)


        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSyncFingerPrintRequest:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSyncFingerPrintRequest: traceback information not available:" + str(e)
            log3(ex_stat)


    def syncFingerPrintOnConnectedVehicle(self, vehicle):
        try:
            self.botFingerPrintsReady = False
            if self.machine_role == "Commander":
                log3("syncing finger prints", "gatherFingerPrints", self)

                reqMsg = {"cmd": "reqSyncFingerPrintProfiles", "content": "now"}

                # send over scheduled tasks to platton.
                self.expected_vehicle_responses = {}

                log3(f"vehicle: {vehicle.getName()} {vehicle.getStatus()}", "gatherFingerPrints", self)
                if vehicle.getFieldLink() and "running" in vehicle.getStatus():
                    self.showMsg(get_printable_datetime() + "SENDING [" + vehicle.getName() + "]PLATOON[" + vehicle.getFieldLink()[
                        "ip"] + "]: " + json.dumps(reqMsg))

                    self.send_json_to_platoon(vehicle.getFieldLink(), reqMsg)
                    self.expected_vehicle_responses[vehicle.getName()] = None

                #now wait for the response to all come back. for each v, give it 10 seconds.
                VTIMEOUT = 12
                sync_time_out = VTIMEOUT
                print("waiting for ", sync_time_out, "seconds....")
                while not( sync_time_out == 0):
                    time.sleep(1)
                    sync_time_out = sync_time_out-1
                    print("tick...", sync_time_out)


        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorSyncFingerPrintOnConnectedVehicle:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorSyncFingerPrintOnConnectedVehicle: traceback information not available:" + str(e)
            log3(ex_stat)


    # this function updates latest finger prints on this vehicle.
    # 1) go to ads dir, look for all xlsx, gather unique emails from username column
    # 2) then string part before "@" will be the user name to use.
    #    in the finger prints directory, there could be three types of files:
    #    i) individual user's text version of finger print profile named {username}.txt for example, JohnSmith.txt, (may or may not exist)
    #    ii) text version of batched finger print profiles which starts with "profiles", for example profiles*.txt file, this file could contains multiple individual user's finger print profile
    #    iii) xlsx version of batched finger print profiles which starts with "profiles", for example profiles*.txt file, this file could contains multiple individual user's finger print profile (may or may not exist)
    # 3) a individual's profile could exist in all three type of files.
    # 4) is it easier to just call batch to singles?
    # 5) finally make a backup copy of all updated profiles for record keeping. the backup
    #    dir should be self.ads_profile_dir/backup_datestring for example backup_20250110
    #    and at the same time, get rid of backup folders dated more than 2 weeks older than
    #    current date.
    def gatherFingerPrints(self):
        try:
            updated_profiles = []
            duplicated_profiles = []
            if self.machine_role == "Platoon":
                log3("gathering finger prints....", "gatherFingerPrints", self)
                print("gaterhing fp profiles", self.ads_profile_dir)

                # Define the directory containing profiles*.txt and individual profiles

                # Get all profiles*.txt files, sorted by timestamp (latest first)
                batch_files = sorted(
                    [
                        os.path.join(self.ads_profile_dir, f)
                        for f in os.listdir(self.ads_profile_dir)
                        if f.startswith("profiles") and f.endswith(".txt")
                    ],
                    key=os.path.getmtime,
                    reverse=True,
                )
                log3("time sorted batch_files:"+json.dumps(batch_files), "gatherFingerPrints", self)

                # Track already updated usernames
                updated_usernames = set()

                # Process each batch file
                for batch_file in batch_files:

                    # Extract usernames from the batch file
                    with open(batch_file, "r") as bf:
                        batch_content = bf.readlines()

                    usernames = set(
                        line.split("=")[1].strip().split("@")[0]  # Extract username before "@"
                        for line in batch_content
                        if line.startswith("username=")
                    )
                    # print("usernames in this batch file:", batch_file, usernames)
                    # Exclude already updated usernames when processing this batch
                    remaining_usernames = usernames - updated_usernames
                    log3(f"remaining_usernames: {remaining_usernames}", "gatherFingerPrints", self)

                    if remaining_usernames:
                        updateIndividualProfileFromBatchSavedTxt(self, batch_file,
                                                                      excludeUsernames=list(updated_usernames))
                        # obtain batch file's time stamp
                        batch_file_timestamp = os.path.getmtime(batch_file)

                        # Add updated profiles to the list
                        for username in remaining_usernames:
                            individual_profile_path = os.path.join(self.ads_profile_dir, f"{username}.txt")
                            updated_profiles.append(individual_profile_path)

                            # Set the timestamp of the individual profile to match the batch profile's timestamp
                            if os.path.exists(individual_profile_path):
                                os.utime(individual_profile_path, (batch_file_timestamp, batch_file_timestamp))
                    else:
                        duplicated_profiles.append(batch_file)

                    # Add processed usernames to the updated list
                    updated_usernames.update(usernames)

                log3(f"Updating usernames: {len(updated_usernames)} {updated_usernames}", "gatherFingerPrints", self)
                # **Point #5: Save Backups and Delete Old Backup Directories**
                # Create backup directory with a date suffix
                today_date = datetime.now().strftime("%Y%m%d")
                backup_dir = os.path.join(self.ads_profile_dir, f"backup_{today_date}")
                os.makedirs(backup_dir, exist_ok=True)
                # print(f"backup_dir: {backup_dir}")

                # Backup all updated profiles
                for profile in updated_profiles:
                    if os.path.exists(profile):
                        shutil.copy2(profile, backup_dir)  # Preserve file metadata during copy

                log3(f"Backup created at: {backup_dir}", "gatherFingerPrints", self)

                # Delete old backups (older than 2 weeks)
                two_weeks_ago = datetime.now() - timedelta(weeks=2)
                for folder in os.listdir(self.ads_profile_dir):
                    if folder.startswith("backup_"):
                        folder_path = os.path.join(self.ads_profile_dir, folder)
                        # Parse the date suffix from the folder name
                        try:
                            folder_date = datetime.strptime(folder.split("_")[1], "%Y%m%d")
                            if folder_date < two_weeks_ago:
                                shutil.rmtree(folder_path)
                                log3(f"Deleted old backup folder: {folder_path}", "gatherFingerPrints", self)
                        except (IndexError, ValueError):
                            log3(f"Skipped invalid backup folder: {folder_path}", "gatherFingerPrints", self)

                # **Remove Old Duplicated Profiles**
                for duplicate_file in duplicated_profiles:
                    duplicate_file_date = os.path.basename(duplicate_file).split("_")[1:4]  # Extract yyyy, mm, dd
                    try:
                        duplicate_file_date = datetime.strptime("_".join(duplicate_file_date),
                                                                         "%Y_%m_%d")
                        if duplicate_file_date < two_weeks_ago:
                            os.remove(duplicate_file)
                            log3(f"Deleted old duplicate profile: {duplicate_file}", "gatherFingerPrints", self)
                    except (IndexError, ValueError):
                        log3(f"Skipped invalid duplicate file: {duplicate_file}", "gatherFingerPrints", self)

            return updated_profiles

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorGatherFingerPrints:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorGatherFingerPrints: traceback information not available:" + str(e)
            log3(ex_stat)
            return []

    async def vehicleSetupTeam(self, vehicle):
        vname = vehicle.getName()
        print("send all ads profiles to the vehicle", vname)

        # find all bots on this vehicle,
        vbs = [b for b in self.bots if b.getVehicle() == vname]
        allvbids = [b.getBid() for b in vbs]
        print([(b.getBid(), b.getVehicle(), b.getEmail()) for b in self.bots])
        print("all bids on vehicle:", len(vbs), allvbids)
        # gather all ads profiles fo the bots, and send over the files.
        bot_profile_paths = [os.path.join(self.ads_profile_dir, b.getEmail().split("@")[0]+".txt") for b in vbs]
        # bot_profile_paths = [b.getADSProfile() for b in vbs]
        print("all vb profiles:", bot_profile_paths)
        print("all fl names:", [fl["name"] for fl in fieldLinks])
        #
        vlink = next((fl for i, fl in enumerate(fieldLinks) if fl["name"] in vname), None)

        # if not self.tcpServer == None:
        if vlink:
            print("sending all bot profiles to platoon...")
            self.batch_send_ads_profiles_to_platoon(vlink, "text", bot_profile_paths)
        else:
            print("WARNING: vehicle not connected!")


    async def setUpBotADSProfilesOnVehicles(self):
        print("send all ads profiles to all running vehicle")
        for v in self.vehicles:
            if "running" in v.getStatus():
                await self.vehicleSetupTeam(v)

    # from task group extract the vehicle related work, and get bots, missions, skills
    # all ready and send over to the vehicle to get the work started.
    async def vehicleSetupWorkSchedule(self, vehicle, p_task_groups, scheduled=True):
        try:
            vname = vehicle.getName()
            if vehicle and "running" in vehicle.getStatus():
                log3("working on remote task group vehicle : " + vname, "assignWork", self)
                # flatten tasks and regroup them based on sites, and divide them into batches
                # all_works = [work for tg in p_task_groups for work in tg.get("works", [])]
                batched_tasks, ads_profiles = formADSProfileBatchesFor1Vehicle(p_task_groups, vehicle, self)
                # print("add buy search", batched_tasks)
                # self.add_buy_searchs(batched_tasks)

                print("ads_profiles:", ads_profiles)
                # send fingerprint browser profiles to platoon/vehicle
                # for profile in ads_profiles:
                #     self.send_file_to_platoon(vehicle.getFieldLink(), "ads profile", profile)
                await self.vehicleSetupTeam(vehicle)

                # now need to fetch this task associated bots, mission, skills
                # get all bots IDs involved. get all mission IDs involved.
                tg_botids, tg_mids, tg_skids = self.getAllBotidsMidsSkidsFromTaskGroup(p_task_groups)
                vehicle.setBotIds(tg_botids)
                vehicle.setMids(tg_botids)

                log3("tg_skids:" + json.dumps(tg_skids), "assignWork", self)
                # put togehter all bots, missions, needed skills infommation in one batch and put onto the vehicle to
                # execute
                # resource_string = self.formBotsMissionsSkillsString(tg_botids, tg_mids, tg_skids)
                resource_bots, resource_missions, resource_skills = self.formBotsMissionsSkillsJsonData(tg_botids, tg_mids,
                                                                                                        tg_skids)
                if scheduled:
                    workCmd = "reqSetSchedule"
                else:
                    workCmd = "reqSetReactiveWorks"
                schedule = {"cmd": workCmd, "todos": batched_tasks, "bots": resource_bots,
                            "missions": resource_missions, "skills": resource_skills}

                # send over scheduled tasks to platton.
                if vehicle.getFieldLink():
                    log3(get_printable_datetime() + "SENDING [" + vname + "]PLATOON[" + vehicle.getFieldLink()[
                        "ip"] + "] SCHEDULE::: " + json.dumps(schedule), "assignWork", self)

                    self.send_json_to_platoon(vehicle.getFieldLink(), schedule)

                    # send over skills to platoon
                    await self.empower_platoon_with_skills(vehicle.getFieldLink(), tg_skids)

                else:
                    log3(get_printable_datetime() + "scheduled vehicle " + vname + " is not FOUND on LAN.", "assignWork", self)
            else:
                log3("WARNING: scheduled vehicle not found on network at the moment: " + vname, "assignWork", self)

        except Exception as e:
            # Get the traceback information
            traceback_info = traceback.extract_tb(e.__traceback__)
            # Extract the file name and line number from the last entry in the traceback
            if traceback_info:
                ex_stat = "ErrorVehicleSetupWorkSchedule:" + traceback.format_exc() + " " + str(e)
            else:
                ex_stat = "ErrorVehicleSetupWorkSchedule: traceback information not available:" + str(e)
            log3(ex_stat, "assignWork", self)


    def vehiclePing(self, vehicle):
        self.sendToVehicleByVip(vehicle.getIP())

    def vehicleShowMonitor(self, vehicle):
        if self.vehicleMonitor:
            self.vehicleMonitor.show()
        else:
            self.vehicleMonitor = VehicleMonitorWin(self, vehicle)
            self.vehicleMonitor.show()

    def genFeedbacks(self, mids):
        #assumption: all mids corresponds to the same product, there is only 1 product invovled here
        fbs = {}
        dtnow = datetime.now()
        date_word = dtnow.isoformat()
        foundM = next((x for x in self.missions if x.getMid() == mids[0]), None)

        if foundM:
            products = foundM.getTitle()
            qs = [{
                "msgID": "1",
                "user": "000",
                "timeStamp": date_word,
                "products": "",
                "goals": "",
                "options": json.dumps({}).replace('"', '\\"'),
                "background": "assume you are happy customers, and would like to write good reviews for both the seller and the product",
                "msg": f"please help generate {len(mids)} review for both seller and the product ({product}), each review should have a title and a review body, \n" +
                       f"the titles sh ould satisfy the following criteria: 1) concise, no more than 6 words long, 2) non repeating 3) title contents should match the body contents.\n"+
                       f"the body of the seller reivew should satisfy the following criteria: 1) concise, no more 2 sentences long, each sentence should have no more than 8 words, 2) non repeating 3) for seller usually, the good review is about a combinartion of good products, fast deliver, prompt communication, fiendly support etc.\n" +
                       f"the body of the product reivew  the following criteria: 1) no more 5 sentences long, best to be less than 3 sentences long, each sentence should contain no more than 12 words. 2) non repeating 3) try comment on product's quality, price, or particular attributes or good for certain occassions (for example, a gift to a closed friend or relative). 4) avoid exaggerating wording, it's perferrable to sound cliche \n" +
                       f"the return reponse should be json structure data, it should a list of json dicts with seller_fb_title, sell_fb_body, product_fb_title, product_fb_body as the key, and the corresponding text as the value.\n"
            }]
            response = send_query_chat_request_to_cloud(self.session, self.tokens, qs, self.getWanApiEndpoint())
            for midx, mid in enumerate(mids):
                fbs[str(mid)] = response[midx]

        return fbs

    def getRPAReports(self, start_date, end_date):
        base_dir = self.log_settings[""]
        """
        Get report files from start_date (non-inclusive) to end_date (inclusive),
        clean up the files, and return a dictionary with report data.

        :param base_dir: The base directory containing year-named folders.
        :param start_date: Start date in YYYYMMDD format (non-inclusive).
        :param end_date: End date in YYYYMMDD format (inclusive).
        :return: A dictionary with keys as report dates (YYYYMMDD) and values as JSON data.
        """
        reports = {}

        # Convert start_date and end_date to datetime objects
        start_date = datetime.strptime(start_date, "%Y%m%d")
        end_date = datetime.strptime(end_date, "%Y%m%d")

        # Ensure the base directory exists
        if not os.path.exists(base_dir):
            print(f"Base directory does not exist: {base_dir}")
            return reports

        # Iterate over year-named folders
        for year_folder in sorted(os.listdir(base_dir)):
            year_path = os.path.join(base_dir, year_folder)

            # Skip non-directory or invalid year folders
            if not os.path.isdir(year_path) or not year_folder.isdigit() or len(year_folder) != 4:
                continue

            # Iterate over files in the year folder
            for file_name in sorted(os.listdir(year_path)):
                # Check if the file matches the report naming convention
                if re.match(r"reports\d{8}", file_name):
                    report_date_str = file_name[7:15]
                    report_date = datetime.strptime(report_date_str, "%Y%m%d")

                    # Include only files within the date range
                    if start_date < report_date <= end_date:
                        file_path = os.path.join(year_path, file_name)
                        try:
                            # Read and clean the file content
                            with open(file_path, "r") as f:
                                cleaned_content = []
                                for line in f:
                                    if not re.match(r"^========+", line):
                                        cleaned_content.append(line.strip())
                                cleaned_json = "\n".join(cleaned_content)

                            # Load cleaned content as JSON and add to reports
                            report_data = json.loads(cleaned_json)
                            reports[report_date_str] = report_data
                        except Exception as e:
                            print(f"Error processing file {file_path}: {e}")

        return reports

    def dailyHousekeeping(self):
        # send a message to manager task to trigger the daily housekeeping task
        in_message = {"type": "ALL_WORK_DONE"}
        print("sending manager msg:", in_message)
        asyncio.ensure_future((self.gui_manager_msg_queue.put(in_message)))


    def dailyTeamPrep(self):
        # send a message to manager task to trigger the daily team prep task
        in_message = {"type": "SCHEDULE_READY"}
        print("sending manager msg:", in_message)
        asyncio.ensure_future((self.gui_manager_msg_queue.put(in_message)))


    def runExternalHook(self, hook, params):
        global symTab
        symTab["hook_flag"] = False
        symTab["hook_result"] = None
        symTab["hook_params"] = params
        hook_path = self.my_ecb_data_homepath + '/my_skills/hooks'
        hook_file = hook+".py"
        stepjson = {
            "type": "External Hook",
            "file_name_type": "direct",
            "file_path": hook_path,
            "file_name": hook_file,
            "params": "hook_params",  # Optional dictionary of parameters for the external script
            "result": "hook_result",
            "flag": "hook_flag"
        }
        i, runStat = processExternalHook(stepjson, 1)
        # print("hook result:", symTab["hook_result"])
        return runStat

    def exit(self):
        # skill all agents
        for agent in self.agents:
            agent.exit()

        #close all windows.

        #kill all tasks, process, threads.

        #tear down networking.

        # take care of any data needs to be saved.

        log3("Good Bye")

