import json

from PySide6.QtCore import Qt, QSize, QEvent
from PySide6.QtGui import QFont, QStandardItem, QIcon, QAction, QStandardItemModel
from PySide6.QtWidgets import QStyledItemDelegate, QTableView, QHeaderView, QListView, QMainWindow, QWidget, \
    QPushButton, QTabWidget, QVBoxLayout, QSplitter, QLabel, QFrame, QScrollArea, QMenu

from gui.FlowLayout import DragPanel


class IconDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.DecorationRole) is not None:
            icon = index.data(Qt.DecorationRole)
            pixmap = icon.pixmap(QSize(64, 64))  # Adjust the size as needed
            painter.drawPixmap(option.rect, pixmap)

class MovieDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.DecorationRole) is not None:
            label = index.data(Qt.DecorationRole)
            # label.movie().setCacheMode(QMovie.CacheAll)  # Corrected method
            label.movie().setSpeed(100)
            label.movie().jumpToFrame(0)
            label.movie().start()
            movie_rect = label.movie().frameRect()
            movie_rect.moveCenter(option.rect.center())
            label.movie().setScaledSize(QSize(16, 16))  # Adjust the size as needed
            label.movie().render(painter, movie_rect)

class PlatoonListView(QListView):
    def __init__(self, parent):
        super(PlatoonListView, self).__init__()
        self.selected_row = None
        self.parent = parent

    def mousePressEvent(self, e):
        if e.type() == QEvent.MouseButtonDblClick:
            if e.button() == Qt.LeftButton:
                self.parent.showMsg("row:"+str(self.indexAt(e.pos()).row()))
                self.selected_row = self.indexAt(e.pos()).row()
                self.parent.fetchVehicleStatus([self.selected_row])



class PLATOON(QStandardItem):
    def __init__(self, ip, hostname, env, homepath):
        super().__init__()
        self.name = hostname
        self.ip = ip
        self.env = env
        self.homepath = homepath

        self.setText(self.name)
        self.icon = QIcon(homepath + '/resource/images/icons/vehicle1-62.png')
        self.setIcon(self.icon)

    def getData(self):
        return self.name, self.ip, self.env



# class MainWindow(QWidget):
class PlatoonWindow(QMainWindow):
    def __init__(self, parent, entrance="msg"):
        super(PlatoonWindow, self).__init__()
        self.parent = parent
        self.mainWidget = QWidget()

        self.platoonTableViews = []

        self.refresh_button = QPushButton("Refresh")
        # self.refresh_button.clicked.connect(self.fetchVehicleStatus)

        self.cancel_button = QPushButton("Cancel")
        # self.cancel_button.clicked.connect(self.cancelMission)


        self.tabs = QTabWidget()
        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignTop)
        self.layout.addWidget(self.tabs)


        self.mainWidget = QWidget()
        self.main_menu_font = QFont("Helvetica", 10)
        self.main_menu_bar_font = QFont("Helvetica", 12)
        self.setWindowTitle("Platoon Editor")

        #creating QActions

        # self.fetchScheduleAction = self._createFetchScheduleAction()

        centralWidget = DragPanel()


        #centralWidget.setPlainText("Central widget")

        self.centralSplitter = QSplitter(Qt.Horizontal)
        self.bottomSplitter = QSplitter(Qt.Vertical)

        if entrance != "conn":
            for v in self.parent.vehicles:
                self.parent.showMsg("adding vehicle tab")
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

    # this function is called when a new vehicle is added to the platoonWin.
    def updatePlatoonWinWithMostRecentlyAddedVehicle(self):
        if len(self.parent.vehicles) > 0:
            v = self.parent.vehicles[len(self.parent.vehicles)-1]
            self.parent.showMsg("adding most recently added vehicle tab")
            ip_last = v.getIP().split(".")[len(v.getIP().split(".")) - 1]
            print("what??", v.getMStats())
            self.tabs.addTab(self._createVehicleTab(v.getMStats()), "Platoon" + ip_last)
            print("tab added....")

    def updatePlatoonWinWithMostRecentlyRemovedVehicle(self):
        v = self.parent.vehicles[len(self.parent.vehicles)-1]
        # self.parent.showMsg("adding most recently added vehicle tab")
        # ip_last = v.getIP().split(".")[len(v.getIP().split(".")) - 1]
        # self.tabs.addTab(self._createVehicleTab(v.getMStats()), "Platoon" + ip_last)

    def updatePlatoonStatAndShow(self, rx_data):
        ip_last = rx_data["ip"].split(".")[len(rx_data["ip"].split(".")) - 1]
        tab_names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        new_tab_name = "Platoon"+ip_last
        if new_tab_name in tab_names:
            tab_index = tab_names.index(new_tab_name)
        else:
            # need to add a new tab.
            self.parent.showMsg("adding a new tab....")
            # find vehicle based on IP address.
            found_v = next((v  for v in self.parent.vehicles if v.getIP().split(".")[len(v.getIP().split(".")) - 1] == ip_last), None)
            if found_v:
                self.tabs.addTab(self._createVehicleTab(found_v.getMStats()), "Platoon" + ip_last)

        vmodel = self.platoonTableViews[tab_index].model()
        rx_jd = json.loads(rx_data["content"])

        self.updatePlatoonStat(vmodel, rx_jd)

        self.tabs.setCurrentIndex(tab_index)

    def fill1TableRow(self, rowIdx, rowDataJson, model):
        self.parent.showMsg("filling table row #"+str(rowIdx))

        text_item = QStandardItem(str(rowDataJson["mid"]))
        model.setItem(rowIdx, 0, text_item)

        text_item = QStandardItem(str(rowDataJson["botid"]))
        model.setItem(rowIdx, 1, text_item)

        text_item = QStandardItem(rowDataJson["sst"])
        model.setItem(rowIdx, 2, text_item)

        text_item = QStandardItem(str(rowDataJson["sd"]))
        model.setItem(rowIdx, 3, text_item)

        text_item = QStandardItem(rowDataJson["ast"])
        model.setItem(rowIdx, 4, text_item)

        text_item = QStandardItem(rowDataJson["aet"])
        model.setItem(rowIdx, 5, text_item)

        icon_item = QStandardItem()
        if rowDataJson["status"] == "scheduled":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/timer0_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "running":
            # icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/c_mission96_1.png'))
            # gif_item = QStandardItem()
            # gif_item.setData(QMovie("path_to_animated.gif"), Qt.DecorationRole)
            # model.setItem(rowIdx, 6, gif_item)
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/progress1_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "completed":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/checked1_256.png'))
            model.setItem(rowIdx, 6, icon_item)
        elif rowDataJson["status"] == "warned":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/warning2_480.png'))
            model.setItem(rowIdx, 6, icon_item)
        else:
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/close0_480.png'))
            model.setItem(rowIdx, 6, icon_item)

        # gif_item = QStandardItem()
        # # gif_item.setData(QMovie(self.parent.getHomePath() + '/resource/images/icons/botpushup.gif'), Qt.DecorationRole)
        # label = QLabel()
        # movie = QMovie(self.parent.getHomePath() + '/resource/images/icons/botpushup.gif')
        # label.setMovie(movie)
        # gif_item.setData(label, Qt.DecorationRole)
        # model.setItem(rowIdx, 6, gif_item)
        # gif_item = QStandardItem()
        # gif_item.setData(QMovie("path_to_animated.gif"), Qt.DecorationRole)

        text_item = QStandardItem(rowDataJson["error"])
        model.setItem(rowIdx, 7, text_item)



    def createLabel(self, text):
        label = QLabel(text)
        label.setFrameStyle(QFrame.Box | QFrame.Raised)
        return label



    def _createReportsShowAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&View")
        return new_action

    def _createReportsGenAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Generate")
        return new_action



    def _createVehicleTab(self, statsJson):
        vTab = QWidget()
        vTab.layout = QVBoxLayout(self)
        font = QFont("Arial", 10)

        centralScroll = QScrollArea()
        centralScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        centralScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        centralScroll.setWidgetResizable(True)

        completedMissionTableView = QTableView()

        header = completedMissionTableView.horizontalHeader()
        header.setFont(font)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        completedMissionModel = QStandardItemModel(0, 8)
        completedMissionModel.setHorizontalHeaderLabels(['Mission ID', 'Bot', 'Scheduled Start Time', 'Actual Start Time', 'Scheduled Duration', 'Actual End Time', 'status', 'error'])
        completedMissionTableView.setModel(completedMissionModel)

        i = 0
        for stat in statsJson:
            self.fill1TableRow(i, stat, completedMissionModel)
            completedMissionTableView.setRowHeight(i, 40)
            i = i + 1

          # Replace "Arial" and 12 with your desired font family and size
        completedMissionTableView.setFont(font)
        # completedMissionTableView.installEventFilter(self)
        # column 6 could be either an icon or an animating gif....
        completedMissionTableView.setItemDelegateForColumn(6, IconDelegate())

        # completedMissionTableView.setItemDelegateForColumn(6, MovieDelegate())

        self.platoonTableViews.append(completedMissionTableView)
        print("55555555")

        centralScroll.setWidget(completedMissionTableView)
        print("6666666")

        vTab.layout.addWidget(centralScroll)

        vTab.setLayout(vTab.layout)
        return vTab


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
        self.parent.showMsg("runn all")

    def eventFilter(self, source, event):
        self.parent.showMsg("Source:"+source)
        if event.type() == QEvent.ContextMenu and source in self.platoonTableViews:
            #self.parent.showMsg("bot RC menu....")
            self.popMenu = QMenu(self)
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
            self.parent.showMsg("selected:"+selected_act)

            if selected_act:
                self.selected_vehicle_row = source.rowAt(event.pos().y())
                self.parent.showMsg("selected row:"+str(self.selected_vehicle_row))
                if self.selected_vehicle_row == -1:
                    self.selected_vehicle_row = source.model().rowCount() - 1
                self.selected_mission_column = source.columnAt(event.pos().x())
                if self.selected_mission_column == -1:
                    self.selected_mission_column = source.model().columnCount() - 1

                self.parent.showMsg("selected col :"+str(self.selected_mission_column))
                self.selected_vehicle_item = self.parent.runningVehicleModel.item(self.selected_vehicle_row)
                self.parent.showMsg("selected item1 :"+self.selected_vehicle_item)

                platoon_idx = self.platoonTableViews.index(source)
                self.parent.showMsg("selected platoon_idx :"+str(platoon_idx))

                if platoon_idx < 0 or platoon_idx >= self.parent.runningVehicleModel.rowCount():
                    platoon_idxs = []
                else:
                    platoon_idxs = [platoon_idx]


                self.selected_vehicle_item = source.model().item(self.selected_vehicle_row, 0)
                self.parent.showMsg("selected item2 :"+self.selected_vehicle_item)

                if self.selected_vehicle_item:
                    mid = int(self.selected_vehicle_item.text())
                    mids = [mid]
                else:
                    mids = []

                self.parent.showMsg("selected mids :"+json.dumps(mids))

                if selected_act == self.platoonRefreshAction:
                    self.parent.showMsg("set to refresh status..."+json.dumps(platoon_idxs)+" "+json.dumps(mids))
                    self.parent.sendPlatoonCommand("refresh", platoon_idxs, mids)
                elif selected_act == self.platoonHaltAction:
                    self.parent.sendPlatoonCommand("halt", platoon_idxs, mids)
                elif selected_act == self.platoonResumeAction:
                    self.parent.sendPlatoonCommand("resume", platoon_idxs, mids)
                elif selected_act == self.platoonCancelThisAction:
                    self.parent.sendPlatoonCommand("cancel this", platoon_idxs, mids)
                elif selected_act == self.platoonCancelAllAction:
                    self.parent.sendPlatoonCommand("cancel all", platoon_idxs, mids)
            return True

        return super().eventFilter(source, event)


    def _createPlatoonRefreshMissionsStatAction(self):
       new_action = QAction(self)
       new_action.setText("&Refresh Status")
       return new_action


    def _createPlatoonHaltMissionsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Halt Missions")
        return new_action

    def _createPlatoonResumeMissionsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Resume Missions")
        return new_action

    def _createPlatoonCancelThisMissionAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Cancel This Mission")
        return new_action

    def _createPlatoonCancelAllMissionsAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Cancel All Missions")
        return new_action
