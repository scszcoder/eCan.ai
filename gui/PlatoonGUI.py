from BotGUI import *
from MissionGUI import *
from ScheduleGUI import *
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


class PlatoonListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(PlatoonListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonPress:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.updateSelectedPlatoon(self.selected_row)

class PLATOON(QtGui.QStandardItem):
    def __init__(self, ip, hostname, env, homepath):
        super().__init__()
        self.name = hostname
        self.ip = ip
        self.env = env
        self.homepath = homepath

        self.setText(self.name)
        self.icon = QtGui.QIcon(homepath + '/resource/images/icons/vehicle1-62.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.name, self.ip, self.env


# class MainWindow(QtWidgets.QWidget):
class PlatoonWindow(QtWidgets.QMainWindow):
    def __init__(self, inTokens, user, xport):
        super(PlatoonWindow, self).__init__()
        self.BOTS_FILE = "C:/Users/Teco/PycharmProjects/ecbot/resource/bots.json"
        self.MISSIONS_FILE = "C:/Users/Teco/PycharmProjects/ecbot/resource/missions.json"
        self.session = set_up_cloud()
        self.tokens = inTokens
        self.user = user
        self.commanderXport = xport
        usrparts = self.user.split("@")
        usrdomainparts = usrparts[1].split(".")
        self.uid = usrparts[0] + "_" + usrdomainparts[0]
        self.platform = platform.system().lower()[0:3]
        self.readBotJsonFile()
        self.vehicles = []                      # computers on LAN that can carry out bots's tasks.， basically tcp transports
        self.bots = []
        self.missions = []
        self.missionsToday = []
        self.zipper = lzstring.LZString()
        self.threadPool = QtCore.QThreadPool()
        self.selected_row = -1
        self.BotNewWin = None
        self.missionWin = None
        self.trainNewSkillWin = None
        self.reminderWin = None
        self.owner = "NA"
        self.botRank = "soldier"              # this should be read from a file which is written during installation phase, user will select this during installation phase

        self.save_all_button = QtWidgets.QPushButton("Save All")
        self.log_out_button = QtWidgets.QPushButton("Logout")
        self.south_layout = QtWidgets.QHBoxLayout(self)
        self.south_layout.addWidget(self.save_all_button)
        self.south_layout.addWidget(self.log_out_button)
        self.save_all_button.clicked.connect(self.saveAll)
        self.log_out_button.clicked.connect(self.logOut)

        self.southWidget = QtWidgets.QWidget()
        self.southWidget.setLayout(self.south_layout)

        self.mainWidget = QtWidgets.QWidget()
        self.westScroll = QtWidgets.QScrollArea()
        self.centralScroll = QtWidgets.QScrollArea()
        self.east0Scroll = QtWidgets.QScrollArea()
        self.east1Scroll = QtWidgets.QScrollArea()

        self.westScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.westScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.westScroll.setWidgetResizable(True)

        self.centralScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.centralScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.centralScroll.setWidgetResizable(True)

        self.east0Scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east0Scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.east0Scroll.setWidgetResizable(True)

        self.east1Scroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        self.east1Scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
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

        self.settingsAccountAction = self._createSettingsAccountAction()

        self.runRunAllAction = self._createRunRunAllAction()

        self.scheduleCalendarViewAction = self._createScheduleCalendarViewAction()
        self.fetchScheduleAction = self._createFetchScheduleAction()

        self.reportsShowAction = self._createReportsShowAction()
        self.reportsGenAction = self._createReportsGenAction()

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

        self.running_missionListView = MissionListView()
        self.runningMissionModel = QtGui.QStandardItemModel(self.running_missionListView)

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

        self.running_missionListView.setModel(self.runningMissionModel)
        self.running_missionListView.setViewMode(QtWidgets.QListView.ListMode)
        self.running_missionListView.setMovement(QtWidgets.QListView.Snap)

        self.netconsolelabel = QtWidgets.QLabel("Network Console", alignment=QtCore.Qt.AlignLeft)
        self.netconsole = QtWidgets.QTextBrowser()

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

        self.east0Scroll.setWidget(self.running_missionListView)
        label_e1 = self.createLabel("East 1")
        # layout.addWidget(self.east0Scroll, BorderLayout.East)

        self.consoleWidget = QtWidgets.QWidget()
        self.consoleLayout = QtWidgets.QVBoxLayout(self)
        self.consoleLayout.addWidget(self.netconsolelabel)
        self.consoleLayout.addWidget(self.netconsole)
        self.consoleWidget.setLayout(self.consoleLayout)


        self.east1Scroll.setWidget(self.consoleWidget)
        label_e2 = self.createLabel("East 2")
        # layout.addWidget(self.east1Scroll, BorderLayout.East)

        label_s = self.createLabel("South")

        self.centralSplitter.addWidget(self.westScroll)
        self.centralSplitter.addWidget(self.centralScroll)
        self.centralSplitter.addWidget(self.east1Scroll)
        self.centralSplitter.addWidget(self.east0Scroll)

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

    def setTokens(self, intoken):
        self.tokens = intoken

    def createLabel(self, text):
        label = QtWidgets.QLabel(text)
        label.setFrameStyle(QtWidgets.QFrame.Box | QtWidgets.QFrame.Raised)
        return label

    def _createMenuBar(self):
        print("PLATOON Creating Menu Bar")
        self.main_menu_bar_font = QtGui.QFont("Helvetica", 12)
        self.main_menu_font = QFont("Helvetica", 10)
        # menu = QMenu()
        # self.main_menu_font = menu.font()
        # self.main_menu_font.setPointSize(10)
        menu_bar = QtWidgets.QMenuBar()
        menu_bar.setFont(self.main_menu_bar_font)
        # Creating menus using a QMenu object
        bot_menu = QtWidgets.QMenu("&Bots", self)
        bot_menu.setFont(self.main_menu_font)
        bot_menu.addAction(self.botGetAction)
        menu_bar.addMenu(bot_menu)

        mission_menu = QtWidgets.QMenu("&Missions", self)
        mission_menu.setFont(self.main_menu_font)
        mission_menu.addAction(self.missionImportAction)
        menu_bar.addMenu(mission_menu)

        settings_menu = QtWidgets.QMenu("&Settings", self)
        settings_menu.setFont(self.main_menu_font)
        settings_menu.addAction(self.settingsAccountAction)
        #settings_menu.addAction(self.settingsImportAction)
        #settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(settings_menu)

        reports_menu = QtWidgets.QMenu("&Reports", self)
        reports_menu.setFont(self.main_menu_font)
        reports_menu.addAction(self.reportsShowAction)
        reports_menu.addAction(self.reportsGenAction)
        menu_bar.addMenu(reports_menu)

        run_menu = QtWidgets.QMenu("&Run", self)
        run_menu.setFont(self.main_menu_font)
        run_menu.addAction(self.runRunAllAction)
        #settings_menu.addAction(self.settingsImportAction)
        #settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(run_menu)

        schedule_menu = QtWidgets.QMenu("&Schedule", self)
        schedule_menu.setFont(self.main_menu_font)
        schedule_menu.addAction(self.fetchScheduleAction)

        schedule_menu.addAction(self.scheduleCalendarViewAction)

        #settings_menu.addAction(self.settingsImportAction)
        #settings_menu.addAction(self.settingsEditAction)
        #settings_menu.addAction(self.settingsDelAction)
        menu_bar.addMenu(schedule_menu)

        skill_menu = QtWidgets.QMenu("&Skills", self)
        skill_menu.setFont(self.main_menu_font)
        skill_menu.addAction(self.skillShowAction)
        menu_bar.addMenu(skill_menu)

        help_menu = QtWidgets.QMenu("&Help", self)
        help_menu.setFont(self.main_menu_font)
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

    def fetchSchedule(self, ts_name, settings):
        jresp = send_schedule_request_to_cloud(self.session, self.tokens['AuthenticationResult']['IdToken'], ts_name, settings)
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

                # body object will be a list of tasks [...]
                # each task is a json, { skill steps. [...]
                # each step is a json
                ##print("resp body: ", bodyobj)
                #if len(bodyobj.keys()) > 0:
                    #jbody = json.loads(jresp["body"])
                    #jbody = json.loads(originalS)
                if len(bodyobj) > 0:
                    self.assign_work(bodyobj)
                else:
                    print("Warning: NO schedule generated.")

    def assignWork(self, tasks):
        # tasks should already be sorted by botid,
        if len(tasks) > self.LOCAL_BOT_LIMIT:
            localwork = tasks[:self.LOCAL_BOT_LIMIT]
            remaining = tasks[self.LOCAL_BOT_LIMIT:]
            for v in self.vehicles:
                # allocate max of LOCAL_BOT_LIMIT number of bot-tasks to this vehicle
                if len(remaining) > self.LOCAL_BOT_LIMIT:
                    thiswork = remaining[:self.LOCAL_BOT_LIMIT]
                    remaining = remaining[self.LOCAL_BOT_LIMIT:]
                    thiswork_string = self.zipper.compressToBase64(json.dumps(thiswork))

                    # send thiswork_string to v
                    v.transport.write(thiswork_string)

                else:
                    # send remaining to this vehicle v. and break out of the loop.
                    thiswork_string = self.zipper.compressToBase64(json.dumps(remaining))
                    v.transport.write(thiswork_string)
                    break

            # after send networked tasks out, now do the local work
        else:
            localwork = tasks

        self.dowork(localwork)
        #now get to work.


    def dowork(self, tasks):
        # tasks should be already sorted according to the time of the day.
        # simply setup a timer for each task.
        # this is actually tricky due to the fact that:
        # 1) scheduled task start time might be blocked due to previous task is not yet finished.
        #   a) this should be a serial process. after task N is done, if task N+1's designated
        #      start time is passed, immediately starts task N+1, if not schedule it to happen
        #      as designed.
        print("Setting up timers for the tasks....")


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
        #new_bot = EBBOT(self)
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



    def updateSelectedPlatoon(self, row):
        self.selected_platoon_row = row
        self.selected_role_item = self.roleModel.item(self.selected_platoon_row)
        platform, level, role = self.selected_role_item.getData()

        self.role_level_sel.setCurrentText(level)
        self.role_name_sel.setCurrentText(role)

        if self.role_platform_sel.findText(platform) < 0:
            self.role_platform_sel.setCurrentText("Custom")
            self.role_custom_platform_edit.setText(platform)

        else:
            self.role_platform_sel.setCurrentText(platform)
            self.role_custom_platform_edit.setText("")

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


    # fetch schedule for the next # of days.
    def getSchedule(self, days=1):
        # File actions
        self.botModel.removeRow(self.selected_bot_row)
        print("delete bot" + str(self.selected_bot_row))

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



