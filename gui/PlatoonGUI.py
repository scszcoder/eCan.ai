from BotGUI import *
from MissionGUI import *
from ScheduleGUI import *
from ebbot import *
from csv import reader
from signio import *
import platform
from os.path import exists
import webbrowser
from Cloud import *
from TrainGUI import *
from BorderLayout import *
import lzstring
from vehicles import *

class IconDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.DecorationRole) is not None:
            icon = index.data(Qt.DecorationRole)
            pixmap = icon.pixmap(QSize(64, 64))  # Adjust the size as needed
            painter.drawPixmap(option.rect, pixmap)

class MovieDelegate(QtWidgets.QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.DecorationRole) is not None:
            label = index.data(Qt.DecorationRole)
            # label.movie().setCacheMode(QtGui.QMovie.CacheAll)  # Corrected method
            label.movie().setSpeed(100)
            label.movie().jumpToFrame(0)
            label.movie().start()
            movie_rect = label.movie().frameRect()
            movie_rect.moveCenter(option.rect.center())
            label.movie().setScaledSize(QSize(16, 16))  # Adjust the size as needed
            label.movie().render(painter, movie_rect)

class PlatoonListView(QtWidgets.QListView):
    def __init__(self, parent):
        super(PlatoonListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QtCore.QEvent.MouseButtonDblClick:
            if e.button() == QtCore.Qt.LeftButton:
                print("row:", self.indexAt(e.pos()).row())
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.fetchVehicleStatus([self.selected_row])



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
    def __init__(self, parent, entrance="msg"):
        super(PlatoonWindow, self).__init__()
        self.BOTS_FILE = parent.homepath + "/resource/bots.json"
        self.MISSIONS_FILE = parent.homepath + "/resource/missions.json"
        self.session = set_up_cloud()
        self.parent = parent
        self.mainWidget = QtWidgets.QWidget()
        self.owner = ""

        self.platoonTableViews = []

        self.refresh_button = QtWidgets.QPushButton("Refresh")
        # self.refresh_button.clicked.connect(self.fetchVehicleStatus)

        self.cancel_button = QtWidgets.QPushButton("Cancel")
        # self.cancel_button.clicked.connect(self.cancelMission)


        self.tabs = QtWidgets.QTabWidget()
        self.layout = QtWidgets.QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.addWidget(self.tabs)


        self.mainWidget = QtWidgets.QWidget()
        self.main_menu_font = QFont("Helvetica", 10)
        self.main_menu_bar_font = QtGui.QFont("Helvetica", 12)

        #creating QActions

        # self.fetchScheduleAction = self._createFetchScheduleAction()

        centralWidget = DragPanel()


        #centralWidget.setPlainText("Central widget")

        self.centralSplitter = QtWidgets.QSplitter(Qt.Horizontal)
        self.bottomSplitter = QtWidgets.QSplitter(Qt.Vertical)

        if entrance != "conn":
            for v in self.parent.vehicles:
                ip_last = v.getIP().split(".")[len(v.getIP().split("."))-1]
                self.tabs.addTab(self._createVehicleTab(v.getMStats()), "Platoon"+ip_last)


        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

        self.setWindowTitle("Main Bot&Mission Scheduler")

    def updatePlatoonStat(self, model, statsJson):
        i = 0
        for stat in statsJson:
            self.fill1TableRow(i, stat, model)
            i = i + 1



    def updatePlatoonStatAndShow(self, rx_data):
        ip_last = rx_data["ip"].split(".")[len(rx_data["ip"].split(".")) - 1]
        tab_names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        new_tab_name = "Platoon"+ip_last
        if new_tab_name in tab_names:
            tab_index = tab_names.index(new_tab_name)
        else:
            # need to add a new tab.
            print("adding a new tab....")


        vmodel = self.platoonTableViews[tab_index].model()
        rx_jd = json.loads(rx_data["content"])

        self.updatePlatoonStat(vmodel, rx_jd)

        self.tabs.setCurrentIndex(tab_index)

    def fill1TableRow(self, rowIdx, rowDataJson, model):
        print("filling table row #", rowIdx)

        text_item = QtGui.QStandardItem(str(rowDataJson["mid"]))
        model.setItem(rowIdx, 0, text_item)

        text_item = QtGui.QStandardItem(str(rowDataJson["botid"]))
        model.setItem(rowIdx, 1, text_item)

        text_item = QtGui.QStandardItem(rowDataJson["sst"])
        model.setItem(rowIdx, 2, text_item)

        text_item = QtGui.QStandardItem(str(rowDataJson["sd"]))
        model.setItem(rowIdx, 3, text_item)

        text_item = QtGui.QStandardItem(rowDataJson["ast"])
        model.setItem(rowIdx, 4, text_item)

        text_item = QtGui.QStandardItem(rowDataJson["aet"])
        model.setItem(rowIdx, 5, text_item)

        icon_item = QtGui.QStandardItem()
        if rowDataJson["status"] == "scheduled":
            icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/timer0_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "running":
            # icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/c_mission96_1.png'))
            # gif_item = QtGui.QStandardItem()
            # gif_item.setData(QtGui.QMovie("path_to_animated.gif"), Qt.DecorationRole)
            # model.setItem(rowIdx, 6, gif_item)
            icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/progress1_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "completed":
            icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/checked1_256.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "warned":
            icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/warning2_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        else:
            icon_item.setIcon(QtGui.QIcon(self.parent.getHomePath() + '/resource/images/icons/close0_480.png'))
            model.setItem(rowIdx, 6, icon_item)

        # gif_item = QtGui.QStandardItem()
        # # gif_item.setData(QtGui.QMovie(self.parent.getHomePath() + '/resource/images/icons/botpushup.gif'), Qt.DecorationRole)
        # label = QtWidgets.QLabel()
        # movie = QtGui.QMovie(self.parent.getHomePath() + '/resource/images/icons/botpushup.gif')
        # label.setMovie(movie)
        # gif_item.setData(label, Qt.DecorationRole)
        # model.setItem(rowIdx, 6, gif_item)
        # gif_item = QtGui.QStandardItem()
        # gif_item.setData(QtGui.QMovie("path_to_animated.gif"), Qt.DecorationRole)

        text_item = QtGui.QStandardItem(rowDataJson["error"])
        model.setItem(rowIdx, 7, text_item)



    def createLabel(self, text):
        label = QtWidgets.QLabel(text)
        label.setFrameStyle(QtWidgets.QFrame.Box | QtWidgets.QFrame.Raised)
        return label



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



    def _createVehicleTab(self, statsJson):
        vTab = QtWidgets.QWidget()
        vTab.layout = QtWidgets.QVBoxLayout(self)
        font = QtGui.QFont("Arial", 10)

        centralScroll = QtWidgets.QScrollArea()
        centralScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        centralScroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        centralScroll.setWidgetResizable(True)

        completedMissionTableView = QtWidgets.QTableView()

        header = completedMissionTableView.horizontalHeader()
        header.setFont(font)
        header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        completedMissionModel = QtGui.QStandardItemModel(0, 8)
        completedMissionModel.setHorizontalHeaderLabels(['Mission ID', 'Bot', 'Scheduled Start Time', 'Actual Start Time', 'Scheduled Duration', 'Actual End Time', 'status', 'error'])
        completedMissionTableView.setModel(completedMissionModel)

        i = 0
        for stat in statsJson:
            self.fill1TableRow(i, stat, completedMissionModel)
            completedMissionTableView.setRowHeight(i, 40)
            i = i + 1

          # Replace "Arial" and 12 with your desired font family and size
        completedMissionTableView.setFont(font)
        completedMissionTableView.installEventFilter(self)
        # column 6 could be either an icon or an animating gif....
        completedMissionTableView.setItemDelegateForColumn(6, IconDelegate())
        # completedMissionTableView.setItemDelegateForColumn(6, MovieDelegate())

        self.platoonTableViews.append(completedMissionTableView)
        centralScroll.setWidget(completedMissionTableView)
        vTab.layout.addWidget(centralScroll)
        vTab.setLayout(vTab.layout)

        return vTab


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
            for v in self.parent.vehicles:
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



    def saveAll(self):
        # Logic for creating a new bot:
        self.writeBotJsonFile()
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



    def runAll(self):
        # Logic for removing a bot, remove the data and remove the file.
        print("runn all")




        self.popMenu = QtWidgets.QMenu(self)
        self.popMenu.addAction(QtGui.QAction('Refresh Stat', self))
        self.popMenu.addAction(QtGui.QAction('Halt', self))
        self.popMenu.addAction(QtGui.QAction('Resume', self))
        self.popMenu.addSeparator()
        self.popMenu.addAction(QtGui.QAction('Cancel', self))

    def eventFilter(self, source, event):
        print("Source:", source)
        if event.type() == QtCore.QEvent.ContextMenu and source in self.platoonTableViews:
            #print("bot RC menu....")
            self.popMenu = QtWidgets.QMenu(self)
            self.platoonRefreshAction = self._createPlatoonRefreshMissionsStatAction()
            self.platoonHaltAction = self._createPlatoonHaltMissionsAction()
            self.platoonResumeAction = self._createPlatoonResumeMissionsAction()
            self.platoonCancelThisAction = self._createPlatoonCancelThisMissionAction()
            self.platoonCancelAllAction = self._createPlatoonCancelAllMissionsAction()

            self.popMenu.addAction(self.platoonRefreshAction)
            self.popMenu.addAction(self.platoonHaltAction)
            self.popMenu.addAction(self.platoonResumeAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.platoonCancelThisAction)
            self.popMenu.addAction(self.platoonCancelAllAction)
            self.popMenu.setFont(self.main_menu_font)

            selected_act = self.popMenu.exec_(event.globalPos())
            print("selected:", selected_act)

            if selected_act:
                self.selected_mission_row = source.rowAt(event.pos().y())
                if self.selected_mission_row == -1:
                    self.selected_mission_row = source.model().rowCount() - 1
                self.selected_mission_column = source.columnAt(event.pos().x())
                if self.selected_mission_column == -1:
                    self.selected_mission_column = source.model().columnCount() - 1

                self.selected_mission_item = self.botModel.item(self.selected_mission_row)

                platoon_idx = self.platoonTableViews.index(source)

                self.selected_mission_item = source.model().item(self.selected_mission_row, 0)
                if self.selected_mission_item:
                    mid = int(self.selected_mission_item.text())
                    mids = [mid]
                else:
                    mids = []

                if selected_act == self.platoonRefreshAction:
                    self.sendPlatoonCommand("refresh", platoon_idx, mids)
                elif selected_act == self.platoonHaltAction:
                    self.sendPlatoonCommand("halt", platoon_idx)
                elif selected_act == self.platoonResumeAction:
                    self.sendPlatoonCommand("resume", platoon_idx)
                elif selected_act == self.platoonCancelThisAction:
                    self.sendPlatoonCommand("cancel this", platoon_idx, mids)
                elif selected_act == self.platoonCancelAllAction:
                    self.sendPlatoonCommand("cancel all", platoon_idx)
            return True

        return super().eventFilter(source, event)


    def _createPlatoonRefreshMissionsStatAction(self):
       new_action = QtGui.QAction(self)
       new_action.setText("&Refresh Status")
       return new_action


    def _createPlatoonHaltMissionsAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Halt Missions")
        return new_action

    def _createPlatoonResumeMissionsAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Resume Missions")
        return new_action

    def _createPlatoonCancelThisMissionAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Cancel This Mission")
        return new_action

    def _createPlatoonCancelAllMissionsAction(self):
        # File actions
        new_action = QtGui.QAction(self)
        new_action.setText("&Cancel All Missions")
        return new_action

    def sendPlatoonCommand(self, action, vidx, mids):
        # File actions
        self.missionWin.setMission(self.selected_cus_mission_item)
        print("edit bot" + str(self.selected_cus_mission_row))
