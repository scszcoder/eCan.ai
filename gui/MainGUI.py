from BotGUI import *
from MissionGUI import *
from ScheduleGUI import *
from PlatoonGUI import *

from ebbot import *
from csv import reader
from tasks import *
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
import pytz
import tzlocal


START_TIME = 15      # 15 x 20 minute = 5 o'clock in the morning
FETCH_ROUTINE = {
    "eastern": [{
        "bid": 0,
        "tz": "eastern",
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

Tzs = ["eastern", "central", "mountain", "pacific", "alaska", "hawaii"]

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
    def __init__(self, inTokens, tcpserver, user):
        super(MainWindow, self).__init__()
        self.BOTS_FILE = "C:/Users/Teco/PycharmProjects/ecbot/resource/bots.json"
        self.MISSIONS_FILE = "C:/Users/Teco/PycharmProjects/ecbot/resource/missions.json"
        self.session = set_up_cloud()
        self.tokens = inTokens
        self.tcpServer = tcpserver
        self.user = user
        self.hostrole = "CommanderOnly"
        self.workingState = "Idle"
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]
        self.platform = platform.system().lower()[0:3]
        self.readBotJsonFile()
        self.vehicles = []                      # computers on LAN that can carry out bots's tasks.， basically tcp transports
        self.bots = []
        self.missions = []
        self.missionsToday = []
        self.platoons = []
        self.zipper = lzstring.LZString()
        self.threadPool = QtCore.QThreadPool()
        self.selected_row = -1
        self.BotNewWin = None
        self.missionWin = None
        self.trainNewSkillWin = None
        self.reminderWin = None
        self.platoonWin = None
        self.SettingsWin = SettingsWidget(self)
        self.netLogWin = CommanderLogWin(self)
        self.logConsoleBox = Expander(self, "Log Console:")
        self.commanderName = ""
        self.todaysReport = []
        self.todaysReports = []

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

        self.save_all_button = QtWidgets.QPushButton("Save All")
        self.log_out_button = QtWidgets.QPushButton("Logout")
        self.south_layout = QtWidgets.QVBoxLayout(self)
        self.south_layout.addWidget(self.logConsoleBox)
        # self.south_layout.addWidget(self.save_all_button)
        # self.south_layout.addWidget(self.log_out_button)
        self.save_all_button.clicked.connect(self.saveAll)
        self.log_out_button.clicked.connect(self.logOut)

        self.southWidget = QtWidgets.QWidget()
        self.southWidget.setLayout(self.south_layout)

        self.mainWidget = QtWidgets.QWidget()
        self.westScrollArea = QtWidgets.QWidget()
        self.westScrollLayout = QtWidgets.QVBoxLayout(self)
        self.westScrollLabel = QtWidgets.QLabel("Missions:", alignment=QtCore.Qt.AlignLeft)

        self.centralScrollArea = QtWidgets.QWidget()
        self.centralScrollLayout = QtWidgets.QVBoxLayout(self)
        self.centralScrollLabel = QtWidgets.QLabel("Bots:", alignment=QtCore.Qt.AlignLeft)

        self.east0ScrollArea = QtWidgets.QWidget()
        self.east0ScrollLayout = QtWidgets.QVBoxLayout(self)
        self.east0ScrollLabel = QtWidgets.QLabel("Vehicles:", alignment=QtCore.Qt.AlignLeft)

        self.east1ScrollArea = QtWidgets.QWidget()
        self.east1ScrollLayout = QtWidgets.QVBoxLayout(self)
        self.east1ScrollLabel = QtWidgets.QLabel("Completed Missions:", alignment=QtCore.Qt.AlignLeft)

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

        self.missionNewAction = self._createMissionNewAction()
        self.missionDelAction = self._createMissionDelAction()
        self.missionEditAction = self._createMissionEditAction()
        self.missionImportAction = self._createMissionImportAction()


        self.mtvViewAction = self._createMTVViewAction()
        self.fieldMonitorAction = self._createFieldMonitorAction()
        self.commandSendAction = self._createCommandSendAction()

        self.settingsAccountAction = self._createSettingsAccountAction()
        self.settingsEditAction = self._createSettingsEditAction()

        self.runRunAllAction = self._createRunRunAllAction()

        self.scheduleCalendarViewAction = self._createScheduleCalendarViewAction()
        self.fetchScheduleAction = self._createFetchScheduleAction()

        self.reportsShowAction = self._createReportsShowAction()
        self.reportsGenAction = self._createReportsGenAction()
        self.reportsLogConsoleAction = self._createReportsLogConsoleAction()

        self.skillNewAction = self._createSkillNewAction()
        self.skillEditAction = self._createSkillEditAction()
        self.skillDeleteAction = self._createSkillDeleteAction()
        self.skillShowAction = self._createSkillShowAction()


        self.helpUGAction = self._createHelpUGAction()
        self.helpCommunityAction = self._createHelpCommunityAction()
        self.helpAboutAction = self._createHelpAboutAction()


        self.popMenu = QtWidgets.QMenu(self)
        self.popMenu.addAction(QtGui.QAction('Edit', self))
        self.popMenu.addAction(QtGui.QAction('Clone', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QtGui.QAction('Delete', self))

        self.botListView = BotListView()
        self.botListView.installEventFilter(self)
        self.botModel = QtGui.QStandardItemModel(self.botListView)

        self.missionListView = MissionListView()
        self.missionListView.installEventFilter(self)
        self.missionModel = QtGui.QStandardItemModel(self.missionListView)

        self.vehicleListView = VehicleListView()
        self.vehicleListView.installEventFilter(self)
        self.runningVehicleModel = QtGui.QStandardItemModel(self.vehicleListView)

        self.completed_missionListView = MissionListView()
        self.completedMissionModel = QtGui.QStandardItemModel(self.completed_missionListView)


        # Apply the model to the list view
        self.botListView.setModel(self.botModel)
        self.botListView.setViewMode(QtWidgets.QListView.IconMode)
        self.botListView.setMovement(QtWidgets.QListView.Snap)

        self.mission0 = EBMISSION(self)
        self.missionModel.appendRow(self.mission0)
        self.missions.append(self.mission0)

        self.missionListView.setModel(self.missionModel)
        self.missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.missionListView.setMovement(QtWidgets.QListView.Snap)

        self.vehicleListView.setModel(self.runningVehicleModel)
        self.vehicleListView.setViewMode(QtWidgets.QListView.ListMode)
        self.vehicleListView.setMovement(QtWidgets.QListView.Snap)

        self.completed_missionListView.setModel(self.completedMissionModel)
        self.completed_missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.completed_missionListView.setMovement(QtWidgets.QListView.Snap)

        centralWidget = DragPanel()


        # ic0 = DragIcon("<html><img src='C:/Users/Teco/PycharmProjects/ecbot/resource/c_robot64_0.png'><br><p style='text-align:center;max-width:64px;'>bot0</p></html>")
        # ic0.install_rc_menu()
        #
        # ic1 = DragIcon("<html><img src='C:/Users/Teco/PycharmProjects/ecbot/resource/c_robot64_1.png'><br><p style='text-align:center;max-width:64px;'>bot0</p></html>")
        # ic1.install_rc_menu()
        #
        # centralWidget.addBot(ic0)
        # centralWidget.addBot(ic1)

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

        self.east0Scroll.setWidget(self.vehicleListView)
        label_e1 = self.createLabel("East 1")
        # layout.addWidget(self.east0Scroll, BorderLayout.East)

        self.east1Scroll.setWidget(self.completed_missionListView)
        label_e2 = self.createLabel("East 2")
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

        self.todays_work = {"tbd": [{"name": "fetch schedule", "works": FETCH_ROUTINE, "status": "yet to start", "current tz": "eastern", "current grp": "other_works", "current bidx": 0, "current widx": 0, "current oidx": 0, "completed" : [], "aborted": []}], "allstat": "working"}
        # point to the 1st task to run for the day.
        self.updateRunStatus(self.todays_work["tbd"][0])

    def on_tg_pressed(self):
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            QtCore.Qt.DownArrow if not checked else QtCore.Qt.RightArrow
        )

        if self.toggle_button.arrowType() == QtCore.Qt.DownArrow:
            self.logConsole.setVisible(True)
        else:
            self.logConsole.setVisible(False)



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
        label = QtWidgets.QLabel(text)
        label.setFrameStyle(QtWidgets.QFrame.Box | QtWidgets.QFrame.Raised)
        return label

    def _createMenuBar(self):
        menu_bar = QtWidgets.QMenuBar()
        # Creating menus using a QMenu object
        bot_menu = QtWidgets.QMenu("&Bots", self)

        bot_menu.addAction(self.botNewAction)
        bot_menu.addAction(self.botGetAction)
        bot_menu.addAction(self.botEditAction)
        bot_menu.addAction(self.botCloneAction)
        bot_menu.addAction(self.botDelAction)
        menu_bar.addMenu(bot_menu)

        mission_menu = QtWidgets.QMenu("&Missions", self)
        mission_menu.addAction(self.missionNewAction)
        mission_menu.addAction(self.missionImportAction)
        mission_menu.addAction(self.missionEditAction)
        mission_menu.addAction(self.missionDelAction)
        menu_bar.addMenu(mission_menu)

        platoon_menu = QtWidgets.QMenu("&Platoons", self)
        platoon_menu.addAction(self.mtvViewAction)
        platoon_menu.addAction(self.fieldMonitorAction)
        platoon_menu.addAction(self.commandSendAction)
        menu_bar.addMenu(platoon_menu)

        settings_menu = QtWidgets.QMenu("&Settings", self)
        # settings_menu.addAction(self.settingsAccountAction)
        #settings_menu.addAction(self.settingsImportAction)
        settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(settings_menu)

        reports_menu = QtWidgets.QMenu("&Reports", self)
        reports_menu.addAction(self.reportsShowAction)
        reports_menu.addAction(self.reportsGenAction)
        reports_menu.addAction(self.reportsLogConsoleAction)
        menu_bar.addMenu(reports_menu)

        run_menu = QtWidgets.QMenu("&Run", self)
        run_menu.addAction(self.runRunAllAction)
        menu_bar.addMenu(run_menu)

        schedule_menu = QtWidgets.QMenu("&Schedule", self)
        schedule_menu.addAction(self.fetchScheduleAction)

        schedule_menu.addAction(self.scheduleCalendarViewAction)
        menu_bar.addMenu(schedule_menu)

        skill_menu = QtWidgets.QMenu("&Skills", self)
        skill_menu.addAction(self.skillNewAction)
        skill_menu.addAction(self.skillEditAction)
        skill_menu.addAction(self.skillDeleteAction)
        skill_menu.addAction(self.skillShowAction)
        menu_bar.addMenu(skill_menu)

        help_menu = QtWidgets.QMenu("&Help", self)
        help_menu.addAction(self.helpUGAction)
        help_menu.addAction(self.helpCommunityAction)
        help_menu.addAction(self.helpAboutAction)
        menu_bar.addMenu(help_menu)
        # Creating menus using a title
        #editMenu = menuBar.addMenu("&Edit")
        #helpMenu = menuBar.addMenu("&Help")
        return menu_bar

    def _createBotNewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&New")
        new_action.triggered.connect(self.newBotGui)
        # ew_action.connect(QtGui.QAction.)


        # new_action.connect(self.newBot)
        # self.newAction.setIcon(QtGui.QIcon(":file-new.svg"))
        #self.openAction = QtGui.QAction(QtGui.QIcon(":file-open.svg"), "&Open...", self)
        #self.saveAction = QtGui.QAction(QtGui.QIcon(":file-save.svg"), "&Save", self)
        #self.exitAction = QtGui.QAction("&Exit", self)
        return new_action


    def _createGetBotsAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Load All Bots")
        new_action.triggered.connect(self.getAllBots)
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
        new_action.setText("&Save All")
        new_action.triggered.connect(self.saveAll)
        return new_action

    def _createBotDelAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Remove")
        return new_action

    def _createBotEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        return new_action

    def _createBotCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createBotEnDisAbleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Disable")
        return new_action

    def _createMissionNewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Create")
        new_action.triggered.connect(self.newMissionView)

        return new_action

    def _createMTVViewAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Vehicles View")
        #new_action.triggered.connect(self.newMissionView)

        return new_action


    def _createFieldMonitorAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Field Monitor")
        #new_action.triggered.connect(self.newMissionView)

        return new_action


    def _createCommandSendAction(self):
        new_action = QtGui.QAction(self)
        new_action.setText("&Send Command")
        new_action.triggered.connect(self.sendToPlatoons)

        return new_action


    def _createMissionDelAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete M")
        return new_action


    def _createMissionImportAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Import")
        return new_action


    def _createMissionEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        return new_action

    def _createSettingsAccountAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Account")
        return new_action

    def _createSettingsEditAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Edit")
        new_action.triggered.connect(self.editSettings)
        return new_action


    def _createRunRunAllAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Run All")
        new_action.triggered.connect(self.manualRunAll)
        return new_action

    def _createScheduleCalendarViewAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Calendar View")
        new_action.triggered.connect(self.scheduleCalendarView)
        return new_action


    def _createFetchScheduleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Fetch Schedules")
        new_action.triggered.connect(self.fetchSchedule)
        return new_action


    def _createReportsShowAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&View")
        return new_action

    def _createReportsGenAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Generate")
        return new_action

    def _createReportsLogConsoleAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Log Console")
        new_action.triggered.connect(self.showLogs)
        return new_action

    def _createSettingsGenAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Generate")
        return new_action

    # after click, should pop up a windows to ask user to choose from 3 options
    # start from scratch, start from template, start by interactive show and learn tip bubble "most popular".
    def _createSkillNewAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText("&Create New")
            new_action.triggered.connect(self.trainNewSkill)
            return new_action

    def _createSkillEditAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText("&Edit")
            return new_action

    def _createSkillDeleteAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText("&Delete")
            return new_action

    def _createSkillShowAction(self):
            # File actions
            new_action = QtGui.QAction(self)
            new_action.setText("&Show All")
            return new_action


    def _createHelpUGAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&User Guide")
        return new_action


    def _createHelpCommunityAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Community")
        new_action.triggered.connect(self.gotoForum)
        return new_action

    def _createHelpAboutAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&About")
        new_action.triggered.connect(self.showAbout)
        return new_action

    def showLogs(self):
        self.netLogWin.show()

    def fetchSchedule(self):
        jresp = send_schedule_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            # first, need to decompress the body.
            # very important to use compress and decompress on Base64
            uncompressed = self.zipper.decompressFromBase64(jresp["body"])
            print("decomppressed response:", uncompressed, "!")
            if uncompressed != "":
                # print("body string:", uncompressed, "!", len(uncompressed), "::")
                bodyobj = json.loads(uncompressed)

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
                if len(bodyobj) > 0:
                    self.assignWork(bodyobj)
                else:
                    self.warn("Warning: NO schedule generated.")
            else:
                self.warn("Warning: Empty Network Response.")


    def warn(self, msg):
        warnText = "<span style=\" font-size:12pt; font-weight:300; color:#ff0000;\" >"
        warnText += msg
        warnText += "</span>"
        # self.netLogWin.appendLogs([warnText])
        self.appendNetLogs([warnText])


    def showMsg(self, msg):
        MsgText = "<span style=\" font-size:12pt; font-weight:300; color:#ff0000;\" >"
        MsgText += msg
        MsgText += "</span>"
        # self.netLogWin.appendLogs([MsgText])
        self.appendNetLogs([MsgText])

    # assign work, if this commander runs, assign works for commander,
    # otherwise, send works to platoons to execute.
    def assignWork(self, task_groups):
        # tasks should already be sorted by botid,
        if self.hostrole == "CommanderOnly":
            nsites = len(fieldLinks)
        else:
            nsites = 1 + len(fieldLinks)
        if len(task_groups) > nsites:
            # there will be unserved tasks due to over capacity
            self.netLogWin.appendLogs("Run Capacity Spilled, some tasks will NOT be served!!!")

        # distribute work to all available sites, which is the limit for the total capacity.
        for i in range(nsites):
            if i == 0 and not self.hostrole == "CommanderOnly":
                # if commander participate work, give work to here.
                self.todays_work["tbd"].append = {"name": "automation", "works": task_groups[0], "status": "yet to start", "current tz": "eastern", "current grp": None, "current bidx": 0, "current widx": 0, "current oidx": 0, "competed": [], "aborted": []}
            else:
                #otherwise, send work to platoons in the field.
                fieldLinks[i-1]["link"].transport.write(json.dumps(task_groups[i]).encode("utf-8"))


    # find to todos.,
    # 1) check whether need to fetch schedules,
    # 2) checking whether need to do RPA
    # 3)
    def checkToDos(self):
        nextrun = None
        # go thru tasks and check the 1st task whose designated start_time has passed.
        pt = datetime.now()
        if not self.todays_work["tbd"][0]["status"] == "done":
            if self.ts2time(self.todays_work["tbd"][0]["works"]["eastern"][0]["other_works"][0]["start_time"]) < pt:
                nextrun = self.todays_work["tbd"][0]
        elif len(self.todays_work["tbd"]) > 1 and not self.todays_work["tbd"][1]["status"] == "done":
            tz = self.todays_work["tbd"][1]["current tz"]
            bith = self.todays_work["tbd"][1]["current bidx"]
            grp = self.todays_work["tbd"][1]["current grp"]
            if grp == "other_works":
                wjth = self.todays_work["tbd"][1]["current oidx"]
            else:
                wjth = self.todays_work["tbd"][1]["current widx"]
            if self.ts2time(self.todays_work["tbd"][1]["works"][tz][bith][grp][wjth]["start_time"]) < pt:
                nextrun = self.todays_work["tbd"][1]
        # elif len(self.todays_work["tbd"]) > 1 and self.todays_work["tbd"][1]["status"] == "done":


        return nextrun


    # run one bot one time slot at a time.
    async def runRPA(self, worksTBD):
        works = worksTBD["works"]
        tz = worksTBD["current tz"]
        grp = worksTBD["current grp"]
        bidx = worksTBD["current bidx"]
        widx = worksTBD["current widx"]
        oidx = worksTBD["current oidx"]
        if grp == "other_works":
            idx = oidx
        else:
            idx = widx

        settings = self.missions[works[tz][bidx][grp][idx].mid].parent_settings

        #now run the steps
        runAllSteps(works[tz][bidx][grp][idx].todos, settings)

        #now update the pointer, status, and so on.....
        self.updateRunStatus(worksTBD)


    def updateRunStatus(self, worksTBD):
        works = worksTBD["works"]
        tz = worksTBD["current tz"]
        grp = worksTBD["current grp"]
        bidx = worksTBD["current bidx"]
        widx = worksTBD["current widx"]
        oidx = worksTBD["current oidx"]
        switch_tz = False
        switch_grp = False
        worksTBD["status"] == "working"
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
                        # all other_works are done. simply go to the next wb_works if there are more
                        # simply switch group
                        grp = "bw_works"
                        # but if no more work after switching grp, switch timezone.
                        if len(works[tz][bidx][grp]) > 0:
                            if not len(works[tz][bidx][grp])-1 > widx:
                                #switch tz
                                switch_tz = True
                            else:
                                switch_grp = True
                                widx = widx + 1
                        else:
                            # all other_works and wh_works of this region(timezone) are done, switch tz.
                            switch_tz = True
                else:
                    if len(works[tz][bidx][grp])-1 > widx:
                        widx = widx + 1
                    else:
                        # all walk-buy works are done. simply go to the next other_works  if there are more
                        grp = "other_works"
                        if len(works[tz][bidx][grp]) > 0:
                            if not len(works[tz][bidx][grp])-1 > oidx:
                                #switch tz
                                switch_tz = True
                            else:
                                switch_grp = True
                                oidx = oidx + 1
                        else:
                            # switch tz.
                            switch_tz = True
                # now compare time.
                if switch_tz == False:
                    if switch_grp == False:
                        if works[tz][bidx]["other_works"][oidx]["start_time"] < works[tz][bidx]["bw_works"][widx]["start_time"]:
                            worksTBD["current grp"] = "other_works"
                        else:
                            worksTBD["current grp"] = "wb_works"
                    else:
                        worksTBD["current grp"] = grp

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
                if len(works[tz][bidx]["other_works"]) > 0 and len(works[tz][bidx]["bw_works"]) > 0:
                    # see which one's start time is earlier
                    if works[tz][bidx]["other_works"][0]["start_time"] < works[tz][bidx]["bw_works"][0]["start_time"]:
                        worksTBD["current grp"] = "other_works"
                        worksTBD["current bidx"] = 0
                        worksTBD["current widx"] = -1
                        worksTBD["current oidx"] = 0
                    else:
                        worksTBD["current grp"] = "wb_works"
                        worksTBD["current bidx"] = 0
                        worksTBD["current widx"] = 0
                        worksTBD["current oidx"] = -1
                elif len(works[tz][bidx]["other_works"]) > 0:
                    worksTBD["current grp"] = "other_works"
                    worksTBD["current bidx"] = 0
                    worksTBD["current widx"] = -1
                    worksTBD["current oidx"] = 0
                elif len(works[tz][bidx]["bw_works"]) > 0:
                    worksTBD["current grp"] = "wb_works"
                    worksTBD["current bidx"] = 0
                    worksTBD["current widx"] = 0
                    worksTBD["current oidx"] = -1

            else:
                worksTBD["status"] == "done"


        worksTBD["current tz"] = tz


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
        tzinfo = datetime.now().astimezone().tzinfo
        return runtime


    def runBotTask(self, task):
        self.workingState = "Working"
        task_mission = self.missions[task.mid]
        # run all the todo steps
        runAllSteps(task.todos, task_mission.parent_settings)


    def showAbout(self):
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText("E-Commerce Bots. \n (V1.0 2022-05-12 AIPPS LLC) \n")
        # msgBox.setInformativeText("Do you want to save your changes?")
        # msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        # msgBox.setDefaultButton(QMessageBox.Save)
        ret = msgBox.exec()


    def gotoForum(self):
        url="https://www.fastprecisiontech.com"
        webbrowser.open(url, new=0, autoraise=True)

    def newBotGui(self):
        # Logic for creating a new bot:
        # pop out a new windows for user to set parameters for a new bot.
        # at the moment, just add an icon.
        #new_bot = EBBOT()
        #new_icon = QtGui.QIcon((":file-open.svg"))
        #self.centralWidget.setText("<b>File > New</b> clicked")
        if self.BotNewWin == None:
            self.BotNewWin = BotNewWin(self)
        #self.BotNewWin.resize(400, 200)
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
        self.writeBotJsonFile()
        self.writeMissionJsonFile()


    def logOut(self):
        self.cog.logout()
        # now should close the main window and bring back up the login screen?


    def addNewBot(self, new_bot):
        # Logic for creating a new bot:
        print("adding a .... new... bot")
        self.bots.append(new_bot)
        self.botModel.appendRow(new_bot)
        api_bots = [{
            "bid": new_bot.getBid(),
            "owner": "",
            "role": new_bot.getRole(),
            "age": new_bot.getAge(),
            "gender": new_bot.getGender(),
            "location": new_bot.getLocation(),
            "interests": new_bot.getInterests()
        }]
        jresp = send_add_bots_request_to_cloud(self.session, api_bots, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            #now that add is successfull, update local file as well.
            self.writeBotJsonFile()



    def updateABot(self, abot):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        jresp = {"body": []}
        api_bots = [{
            "bid": abot.getBid(),
            "owner": "",
            "role": abot.getRole(),
            "age": abot.getAge(),
            "gender": abot.getGender(),
            "location": abot.getLocation(),
            "interests": abot.getInterests()
        }]
        jresp = send_update_bots_request_to_cloud(self.session, api_bots, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            #now that add is successfull, update local file as well.
            self.writeBotJsonFile()


    def addNewMission(self, new_mission):
        # Logic for creating a new mission:
        print("adding a .... new... mission")
        self.missions.append(new_mission)
        self.missionModel.appendRow(new_mission)
        api_missions = [{
            "mid": new_mission.getMid(),
            "owner": "",
            "search_kw": new_mission.getSearchKW(),
            "search_cat": new_mission.getSearchCat(),
            "botid": new_mission.getBid(),
            "repeat": new_mission.getRepeat(),
            "status": new_mission.getStatus(),
            "mtype": new_mission.getMtype()
        }]
        jresp = send_add_missions_request_to_cloud(self.session, api_missions, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            # now that delete is successfull, update local file as well.
            self.writeMissionJsonFile()

    def updateAMission(self, amission):
        # potential optimization here, only if cloud side related attributes changed, then we do update on the cloud side.
        # otherwise, only update locally.
        jresp = {"body": []}
        api_bots = [{
            "bid": amission.getBid(),
            "owner": "",
            "role": amission.getRole(),
            "age": amission.getAge(),
            "gender": amission.getGender(),
            "location": amission.getLocation(),
            "interests": amission.getInterests()
        }]
        jresp = send_update_missions_request_to_cloud(self.session, api_bots, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
            #now that add is successfull, update local file as well.
            self.writeMissionJsonFile()

    # this function sends commands to platoon(s)
    def sendToPlatoons(self):
        # this shall bring up a windows, but for now, simply send something to a platoon for network testing purpose...
        #if self.platoonWin == None:
        #    self.platoonWin = PlatoonWindow(self)
        #self.BotNewWin.resize(400, 200)
        #self.platoonWin.show()
        print("sending commands.....")
        print("tcp connections.....", fieldLinks)
        print("tcp server.....", self.tcpServer)
        print("commander server.....", commanderServer)

        # if not self.tcpServer == None:
        if len(fieldLinks) > 0:
            print("Currently, there are (", len(fieldLinks), ") connection to this server.....")
            for i in range(len(fieldLinks)):
                fieldLinks[i]["link"].transport.write(('what the hell!!!! ' + str(i)).encode('utf8'))
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
            new_bot = EBBOT()
            new_bot.setJsonData(bj)
            self.bots.append(new_bot)


    def readBotJsonFile(self):
        if exists(self.BOTS_FILE):
            with open(self.BOTS_FILE, 'r') as file:
                self.botJsonData = json.load(file)
                self.translateBotsJson(self.botJsonData)


    def writeBotJsonFile(self):
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

    # This function translate bots data structure matching ebbot.py to Json format for file storage.
    def genMissionsJson(self):
        mjs = []
        for mission in self.missions:
            print("bot gen json0...." + str(len(self.bots)))
            mjs.append(mission.genJson())
        #print(json.dumps(bjs))
        return mjs


    # This function translate bots data from Json format to the data structure matching ebbot.py
    def translateMissionsJson(self):
        for mj in self.missionJsonData:
            new_mission = EBMISSION()
            new_mission.setJsonData(mj)
            self.bots.append(new_mission)


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
                botjson["status"]["level"] = rows[1][i]
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
        #new_bot = EBBOT()
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

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.ContextMenu and source is self.botListView:
            #print("bot RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
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
            self.cusMissionEditAction = self._createCusMissionEditAction()
            self.cusMissionCloneAction = self._createCusMissionCloneAction()
            self.cusMissionDeleteAction = self._createCusMissionDeleteAction()

            self.popMenu.addAction(self.cusMissionEditAction)
            self.popMenu.addAction(self.cusMissionCloneAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.cusMissionDeleteAction)

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
            return True
        # else:
        #     print("unknwn.... RC menu....", source, " EVENT: ", event)
        return super().eventFilter(source, event)


    def _createCusMissionEditAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText("&Edit")
       return new_action

    def _createCusMissionCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createCusMissionDeleteAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action

    def editCusMission(self):
        # File actions
        self.missionWin.setMission(self.selected_cus_mission_item)
        self.missionWin.show()
        print("edit bot" + str(self.selected_cus_mission_row))

    def cloneCusMission(self):
        # File actions
        print("clone bot" + str(self.selected_bot_row))

    def deleteCusMission(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText("The mission will be removed and won't be able recover from it..")
        msgBox.setInformativeText("Are you sure about deleting this mission?")
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

    def _createBotRCEditAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText("&Edit")
       return new_action

    def _createBotRCCloneAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Clone")
        return new_action

    def _createBotRCDeleteAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Delete")
        return new_action

    def editBot(self):
        # File actions
        self.BotNewWin.setBot(self.selected_bot_item)
        self.BotNewWin.show()
        print("edit bot" + str(self.selected_bot_row))

    def cloneBot(self):
        # File actions
        print("clone bot" + str(self.selected_bot_row))

    def deleteBot(self):
        # File actions
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText("The bot will be removed and won't be able recover from it..")
        msgBox.setInformativeText("Are you sure about deleting this bot?")
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
                    self.writeBotJsonFile()

        #self.botModel.removeRow(self.selected_bot_row)
        #print("delete bot" + str(self.selected_bot_row))

    # fetch all bots stored in the cloud.
    def getAllBots(self):
        # File actions
        #resp = send_get_bots_request_to_cloud(self.session, self.cog.access_token)
        jresp = send_get_bots_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'])
        if "errorType" in jresp:
            screen_error = True
            print("Gat All Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
        else:
            jbody = json.loads(jresp["body"])
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

        # file_name = "C:/AmazonSeller/JSRPA/AIData/EB/D20220202/fox0_000.png"
        # send_screen(file_name)
        #  rid = "0", app = "na", domain = "na", req_type = "na", intent = "uk", last_move = "uk", image_file = "uk"):
        # req = SCRN_READ_REQEST("00", "ff", "ebay", "page", "get label", "ou", file_name)
        # txt_results = req_cloud_read_screen(self.session, [req], token)
        # print(txt_results)
        # print(ico_results)

        for m in self.missions:
            status = m.run()

    def runbotworks(self):
        # run all the work
        botTodos = None
        if self.workingState == "Idle":
            botTodos = self.checkToDos()
            self.showMsg("check todos....")
            if not botTodos == None:
                self.workingState = "Working"
                if botTodos["name"] == "fetch schedule":
                    self.fetchSchedule()
                    botTodos["status"] = "done"
                elif botTodos["name"] == "automation":
                    # run 1 bot's work
                    if not botTodos["status"] == "done":
                        self.runRPA(botTodos)
                    else:
                        self.doneWithToday()

                # elif botTodos["name"] == "report":
                #     self.doneWithToday()
                self.workingState = "Idle"
            else:
                # nothing to do right now. check if all of today's work are done.
                # if my own works are done and all platoon's reports are collected.
                if self.todays_work["allstat"] == "all done":
                    self.doneWithToday()

    # msg in json format
    # { sender: "ip addr", type: "intro/status/report", content : "another json" }
    # content format varies according to type.
    def processPlatoonMsgs(self, msgString):
        msg = json.loads(msgString)
        found = next((x for x in fieldLinks if x["ip"] == self.peername), None)

        # first, check ip and make sure this from a know vehicle.
        if msg["type"] == "intro":
            if found:
                found["name"] = msg["content"]["name"]
        elif msg["type"] == "status":
            # update vehicle status display.
            self.showMsg(msg["content"])
        elif msg["type"] == "report":
            # collect report, the report should be already organized in json format and ready to submit to the network.
            self.todaysReports.append(json.loads(msg["content"]))
            # keep statistics on all platoon runs.
            if len(self.todaysReports) == len(self.todays_work["tbd"][1]):
                # check = all(item in List1 for item in List2)
                # this means all reports are collected, ready to send to cloud.
                self.todays_work["allstat"] = "all done"


    # { sender: "ip addr", type: "intro/config/missions", content : "another json" }
    # content format varies according to type.
    def processCommanderMsgs(self, msgString):
        msg = json.loads(msgString)
        # first, check ip and make sure this from a know vehicle.
        if msg["type"] == "intro":
            self.commanderName = msg["content"]["name"]
        elif msg["type"] == "config":
            # update vehicle status display.
            self.showMsg(msg["content"])
        elif msg["type"] == "missions":
            # schedule work now..... append to array data structure and set up the pointer to the 1st task.
            # the actual running of the tasks will be taken care of by the schduler.
            localworks = json.loads(msg["content"])
            self.todays_work["tbd"].append({"name": "automation", "works": localworks, "status": "yet to start", "current tz": "eastern", "current grp": None, "current bidx": 0, "current widx": 0, "current oidx": 0, "competed": [], "aborted": []})
            self.updateRunStatus(self.todays_work["tbd"][1])

    # just an array of the following object:
    # MissionStatus {
    #     mid: ID!
    #     bid: ID!
    #     blevel: String!
    #     status: String!
    #     }
    def genRunReport(self):
        statReport = None
        tzi = 0
        #only generate report when all done.
        works = self.todays_work["tbd"][1]

        if not self.hostrole == "CommanderOnly":
            while tzi in range(len(Tzs)):
                if len(works[tzi]) > 0:
                    for bi in range(len(works[tzi])):
                        if len(works[tzi][bi]["other_works"]) > 0:
                            for oi in range(len(works[tzi][bi]["other_works"])):
                                self.todaysReport.append({ "mid": works[tzi][bi]["other_works"][oi].mid, "bid": works[tzi][bi].bid, "blevel": "", "status": works[tzi][bi]["other_works"][oi].stat})

                        if len(works[tzi][bi]["wb_works"]) > 0:
                            for wi in range(len(works[tzi][bi]["wb_works"])):
                                self.todaysReport.append({ "mid": works[tzi][bi]["wb_works"][wi].mid, "bid": works[tzi][bi].bid, "blevel": "", "status": works[tzi][bi]["wb_works"][wi].stat})


        if not self.hostrole == "Platoon":
            # generate complete report based on reports generated on this local host and the ones sent from platoons on the network.
            rpt = {"ip": self.ip, "type": "report", "content": self.todaysReport}
            self.todaysReports.append(str.encode(json.dumps(rpt)))
            statReport = [item for pr in self.todaysReports for item in pr]         #pr - platoon report, statReport is list of list.
        else:
            # generate report only for this machine.
            statReport = self.todaysReport

        return statReport

    # all work done today, now
    # 1) send report to the network,
    # 2) save report to local logs,
    # 3) clear today's work data structures.
    def doneWithToday(self):
        global commanderXport
        # call reportStatus API to send today's report to API
        todays_stat = self.genRunReport()

        if not self.hostrole == "Platoon":
            if todays_stat:
                #send report to cloud
                send_completion_status_to_cloud(self.session, todays_stat, self.tokens['AuthenticationResult']['IdToken'])
        else:
            rpt = {"ip": self.ip, "type": "report", "content": todays_stat}
            commanderXport.write(str.encode(json.dumps(rpt)))
        # 2) log reports.

        # 3) clear data structure, set up for tomorrow morning.
        self.todays_work = {"tbd": [{"name": "fetch schedule", "works": FETCH_ROUTINE, "status": "yet to start", "current tz": "eastern", "current grp": "other_works", "current bidx": 0, "current widx": 0, "current oidx": 0, "completed" : [], "aborted": []}]}
