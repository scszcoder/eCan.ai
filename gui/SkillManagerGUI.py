from PySide6.QtWidgets import QStyledItemDelegate, QTextEdit, QTableView, QHeaderView

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
from WorkSkill import *

class IconDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        if index.data(Qt.DecorationRole) is not None:
            icon = index.data(Qt.DecorationRole)
            pixmap = icon.pixmap(QSize(64, 64))  # Adjust the size as needed
            painter.drawPixmap(option.rect, pixmap)



# class MainWindow(QWidget):
class SkillManagerWindow(QMainWindow):
    def __init__(self, parent, entrance="msg"):
        super(SkillManagerWindow, self).__init__()
        self.parent = parent
        self.mainWidget = QWidget()
        self.skills = []
        self.fetch_mine_button = QPushButton(QApplication.translate("QPushButton", "Get Mine"))
        self.fetch_mine_button.clicked.connect(self.fetchMySkills)

        # self.refresh_button.clicked.connect(self.fetchVehicleStatus)

        self.cancel_button = QPushButton(QApplication.translate("QPushButton", "Cancel"))
        # self.cancel_button.clicked.connect(self.cancelMission)
        self.layout = QVBoxLayout(self)

        self.sm_layout = QVBoxLayout(self)
        self.tp_layout = QHBoxLayout(self)

        self.sk_info_label = QLabel(QApplication.translate("QLabel", "Skill Info:"), alignment=Qt.AlignLeft)
        self.skill_search_edit = QLineEdit()
        self.skill_search_edit.setClearButtonEnabled(True)
        self.skill_search_edit.addAction(QIcon(self.parent.getHomePath() + '/resource/images/icons/search1_80.png'), QLineEdit.LeadingPosition)
        self.skill_search_edit.setPlaceholderText(QApplication.translate("QLineEdit", "Search Skill With Keywords"))
        self.skill_search_edit.returnPressed.connect(self.fetch_mine_button.click)

        self.skillInfoConsole = QTextEdit()
        self.skillInfoConsole.setLineWrapMode(QTextEdit.FixedPixelWidth)
        self.skillInfoConsole.verticalScrollBar().setValue(self.skillInfoConsole.verticalScrollBar().minimum())
        self.skillInfoConsole.setReadOnly(True)

        font = QFont("Arial", 10)

        self.centralScroll = QScrollArea()
        self.centralScroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.centralScroll.setWidgetResizable(True)

        self.skillTableView = QTableView()

        header = self.skillTableView.horizontalHeader()
        header.setFont(font)
        header.setSectionResizeMode(QHeaderView.ResizeToContents)

        self.skillModel = QStandardItemModel(0, 8)
        self.skillModel.setHorizontalHeaderLabels(['Skill ID', 'Name', 'Owner', 'Users', 'Created On', 'Privacy', 'Platform/App/Site', ''])
        self.skillTableView.setModel(self.skillModel)

        i = 0
        for skill in self.skills:
            self.fill1TableRow(i, skill, self.skillModel)
            self.skillTableView.setRowHeight(i, 40)
            i = i + 1

        # Replace "Arial" and 12 with your desired font family and size
        self.skillTableView.setFont(font)
        self.skillTableView.installEventFilter(self)
        # column 6 could be either an icon or an animating gif....
        self.skillTableView.setItemDelegateForColumn(6, IconDelegate())
        # completedMissionTableView.setItemDelegateForColumn(6, MovieDelegate())


        self.centralScroll.setWidget(self.skillTableView)
        self.sm_layout.addWidget(self.centralScroll)
        self.tp_layout.addWidget(self.fetch_mine_button)
        self.tp_layout.addWidget(self.skill_search_edit)
        self.layout.addLayout(self.tp_layout)
        self.layout.addLayout(self.sm_layout)


        self.main_menu_font = QFont("Helvetica", 10)
        self.main_menu_bar_font = QFont("Helvetica", 12)

        #creating QActions

        # self.fetchScheduleAction = self._createFetchScheduleAction()

        centralWidget = DragPanel()


        #centralWidget.setPlainText("Central widget")

        self.centralSplitter = QSplitter(Qt.Horizontal)
        self.bottomSplitter = QSplitter(Qt.Vertical)


        self.mainWidget.setLayout(self.layout)
        self.setCentralWidget(self.mainWidget)

        self.setWindowTitle(QApplication.translate("QtWidget", "Skill Manager"))

    def updateSkills(self, model, skillData):
        i = 0
        for sk in skillData:
            self.fill1TableRow(i, sk, model)
            i = i + 1


    def updateSkillStatAndShow(self, rx_data):
        ip_last = rx_data["ip"].split(".")[len(rx_data["ip"].split(".")) - 1]
        tab_names = [self.tabs.tabText(i) for i in range(self.tabs.count())]
        new_tab_name = "Skill"+ip_last
        if new_tab_name in tab_names:
            tab_index = tab_names.index(new_tab_name)
        else:
            # need to add a new tab.
            print("adding a new tab....")


        vmodel = self.SkillTableViews[tab_index].model()
        rx_jd = json.loads(rx_data["content"])

        self.updateSkillStat(vmodel, rx_jd)

        self.tabs.setCurrentIndex(tab_index)


    def fill1TableRow(self, rowIdx, rowData, model):
        print("filling table row #", rowIdx)

        text_item = QStandardItem(str(rowData[rowIdx].getSkid()))
        model.setItem(rowIdx, 0, text_item)

        text_item = QStandardItem(rowData[rowIdx].getName())
        model.setItem(rowIdx, 1, text_item)

        text_item = QStandardItem(rowData[rowIdx].getOwner())
        model.setItem(rowIdx, 2, text_item)

        text_item = QStandardItem(rowData[rowIdx].getUsers())
        model.setItem(rowIdx, 3, text_item)

        text_item = QStandardItem(rowData[rowIdx].getCreatedOn())
        model.setItem(rowIdx, 4, text_item)

        text_item = QStandardItem(rowData[rowIdx].getPrivacy())
        model.setItem(rowIdx, 5, text_item)

        text_item = QStandardItem(rowData[rowIdx].getPlatform() + "/" + rowData[rowIdx].getApp() + "/" + rowData[rowIdx].getSite())
        model.setItem(rowIdx, 6, text_item)

        icon_item = QStandardItem()
        if rowData[rowIdx].getPrivacy() == "pub":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/skills_78.png'))
            model.setItem(rowIdx, 7, icon_item)
        elif rowData[rowIdx].getPrivacy() == "prv":
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/private_skills_78.png'))
            model.setItem(rowIdx, 6, icon_item)
        else:
            icon_item.setIcon(QIcon(self.parent.getHomePath() + '/resource/images/icons/private_usable_skills_78.png'))
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




    def copySelectedSkill(self, row):
        self.selected_Skill_row = row
        self.selected_role_item = self.roleModel.item(self.selected_Skill_row)
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


    def eventFilter(self, source, event):
        print("Source:", source)
        if event.type() == QEvent.ContextMenu and source is self.skillTableView:
            print("skill menu....")
            self.popMenu = QMenu(self)
            self.SkillOpenAction = self._createSkillOpenAction()
            self.SkillCopyAction = self._createSkillCopyAction()
            self.SkillDeleteAction = self._createSkillDeleteAction()

            self.popMenu.addAction(self.SkillOpenAction)
            self.popMenu.addAction(self.SkillCopyAction)
            self.popMenu.addSeparator()
            self.popMenu.addAction(self.SkillDeleteAction)
            self.popMenu.setFont(self.main_menu_font)

            selected_act = self.popMenu.exec_(event.globalPos())
            print("selected:", selected_act)

            if selected_act:
                self.selected_skill_row = source.rowAt(event.pos().y())
                print("selected row:", self.selected_skill_row)
                if self.selected_skill_row == -1:
                    self.selected_skill_row = source.model().rowCount() - 1
                self.selected_skill_column = source.columnAt(event.pos().x())
                if self.selected_skill_column == -1:
                    self.selected_skill_column = source.model().columnCount() - 1

                print("selected col :", self.selected_skill_column)
                self.selected_mission_item = self.skillModel.item(self.selected_skill_row)
                print("selected item1 :", self.selected_mission_item)

                skill_idx = self.skillTableView.index(source)
                print("selected Skill_idx :", skill_idx)

                if skill_idx < 0 or skill_idx >= self.skillModel.rowCount():
                    Skill_idxs = []
                else:
                    Skill_idxs = [skill_idx]


                self.selected_skill_item = source.model().item(self.selected_skill_row, 0)
                print("selected item2 :", self.selected_skill_item)

                if self.selected_skill_item:
                    skid = int(self.selected_skill_item.text())
                    skids = [skid]
                else:
                    skids = []

                print("selected mids :", skids)

                if selected_act == self.SkillOpenAction:
                    print("set to refresh status...", Skill_idxs, skids)
                    self.openSkill("open", Skill_idxs, skids)
                elif selected_act == self.SkillCopyAction:
                    self.copySkill("copy", Skill_idxs, skids)
                elif selected_act == self.SkillDeleteAction:
                    self.deleteSkill("delete", Skill_idxs, skids)
            return True

        return super().eventFilter(source, event)


    def _createSkillOpenAction(self):
       new_action = QAction(self)
       new_action.setText("&Open")
       return new_action


    def _createSkillCopyAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Copy")
        return new_action


    def _createSkillDeleteAction(self):
        # File actions
        new_action = QAction(self)
        new_action.setText("&Delete")
        return new_action

    def fetchMySkills(self):
        print("Start fetching......")
        if self.skill_search_edit.text() == "":
            qsettings = {"byowneruser": True, "qphrase": ""}
        else:
            qsettings = {"byowneruser": False, "qphrase": self.skill_search_edit.text()}

        resp = send_query_skills_request_to_cloud(self.parent.session, self.parent.tokens['AuthenticationResult']['IdToken'], qsettings)
        print("fetch skills results:", resp)


    def openSkill(self, skill):
        print("opening skill....")
        self.parent.trainNewSkillWin.show()


    def deleteSkill(self, skill):
        msgBox = QMessageBox()
        msgBox.setText(QApplication.translate("QMessageBox",
                                                        "The skill will be deleted and won't be able recover from it.."))
        msgBox.setInformativeText(
            QApplication.translate("QMessageBox", "Are you sure about deleting this skill?"))
        msgBox.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        msgBox.setDefaultButton(QMessageBox.Yes)
        ret = msgBox.exec_()

        if ret == QMessageBox.Yes:
            print("deleting skill....")
            items = [self.selected_skill_item]
            # if len(items):
            #     for item in items:
            #         # remove file first, then the item in the model.
            #         # shutil.rmtree(temp_page_dir)
            #         # os.remove(full_temp_page)
            #
            #         # remove the local data and GUI.
            #         self.missionModel.removeRow(item.row())
            #
            #     # remove on the cloud side
            #     jresp = send_remove_skills_request_to_cloud(self.session, api_removes, self.tokens['AuthenticationResult']['IdToken'])
            #     if "errorType" in jresp:
            #         screen_error = True
            #         print("Delete Bots ERROR Type: ", jresp["errorType"], "ERROR Info: ", jresp["errorInfo"], )
            #     else:
            #         jbody = json.loads(jresp["body"])
            #         #now that delete is successfull, update local file as well.
            #         self.writeMissionJsonFile()